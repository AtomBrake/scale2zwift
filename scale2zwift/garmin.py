"""Garmin Connect access via the garminconnect library.

Only Garmin's login tokens are saved (in the data directory). Your Garmin
password is used once to log in and is never stored.
"""
from __future__ import annotations

import shutil
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from garminconnect import Garmin, GarminConnectAuthenticationError

LOOKBACK_DAYS = 30
MFA_TIMEOUT = 600


class GarminNotConnected(Exception):
    pass


@dataclass
class WeighIn:
    sample_pk: int
    grams: int
    timestamp: datetime
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_pk": self.sample_pk,
            "grams": self.grams,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
        }


def latest_weigh_in(response: dict[str, Any]) -> WeighIn | None:
    """Pick the most recent weigh-in from a /weight/range response."""
    metrics = [
        m
        for summary in response.get("dailyWeightSummaries") or []
        for m in summary.get("allWeightMetrics") or []
        if m.get("weight") and m.get("timestampGMT")
    ]
    if not metrics:
        return None
    m = max(metrics, key=lambda m: m["timestampGMT"])
    return WeighIn(
        sample_pk=m["samplePk"],
        grams=round(m["weight"]),
        timestamp=datetime.fromtimestamp(m["timestampGMT"] / 1000, tz=timezone.utc),
        source=m.get("sourceType") or "UNKNOWN",
    )


class GarminAccount:
    def __init__(self, token_dir: Path):
        self.token_dir = token_dir
        self._pending: tuple[Garmin, Any, float] | None = None
        self._lock = threading.Lock()

    @property
    def connected(self) -> bool:
        return (self.token_dir / "garmin_tokens.json").exists()

    @property
    def mfa_pending(self) -> bool:
        return self._pending is not None and time.time() - self._pending[2] < MFA_TIMEOUT

    def _save(self, garmin: Garmin) -> None:
        self.token_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        garmin.client.dump(str(self.token_dir))

    def login(self, email: str, password: str) -> bool:
        """Log in with email/password. Returns True if an MFA code is needed."""
        garmin = Garmin(email, password, return_on_mfa=True)
        status, state = garmin.login()
        with self._lock:
            if status == "needs_mfa":
                self._pending = (garmin, state, time.time())
                return True
            self._pending = None
        self._save(garmin)
        return False

    def submit_mfa(self, code: str) -> None:
        with self._lock:
            if not self.mfa_pending:
                self._pending = None
                raise GarminConnectAuthenticationError("MFA login expired, please log in again")
            garmin, state, _ = self._pending
            self._pending = None
        garmin.resume_login(state, code)
        self._save(garmin)

    def disconnect(self) -> None:
        self._pending = None
        shutil.rmtree(self.token_dir, ignore_errors=True)

    def fetch_latest(self) -> WeighIn | None:
        if not self.connected:
            raise GarminNotConnected("Garmin is not connected")
        garmin = Garmin()
        try:
            # Refreshed tokens are written back to token_dir by the library.
            garmin.login(tokenstore=str(self.token_dir))
        except GarminConnectAuthenticationError as exc:
            raise GarminNotConnected(f"Garmin login expired, please reconnect ({exc})") from exc
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=LOOKBACK_DAYS)
        return latest_weigh_in(garmin.get_weigh_ins(start.isoformat(), today.isoformat()))
