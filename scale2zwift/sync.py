"""The sync job and the background scheduler that runs it."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .garmin import GarminAccount, GarminNotConnected
from .store import Store
from .zwift import ZwiftClient, ZwiftError

log = logging.getLogger(__name__)

DEFAULT_INTERVAL_HOURS = 4
HISTORY_LIMIT = 50


def now() -> datetime:
    return datetime.now(timezone.utc)


class Syncer:
    def __init__(
        self,
        store: Store,
        garmin: GarminAccount,
        zwift_factory: Callable[..., ZwiftClient] = ZwiftClient,
    ):
        self.store = store
        self.garmin = garmin
        self.zwift_factory = zwift_factory
        self._lock = threading.Lock()
        self._wake = threading.Event()

    # --- settings -----------------------------------------------------------

    @property
    def interval_hours(self) -> float:
        return float(self.store.state.load().get("interval_hours", DEFAULT_INTERVAL_HOURS))

    def set_interval_hours(self, hours: float) -> None:
        self.store.state.update(interval_hours=hours)
        self._wake.set()

    def zwift(self) -> ZwiftClient | None:
        secrets = self.store.secrets.load()
        if not secrets.get("zwift_email") or not secrets.get("zwift_password"):
            return None
        return self.zwift_factory(
            secrets["zwift_email"],
            secrets["zwift_password"],
            tokens=secrets.get("zwift_tokens"),
            on_tokens=lambda tokens: self.store.secrets.update(zwift_tokens=tokens),
        )

    # --- sync ---------------------------------------------------------------

    def _record(self, status: str, message: str, grams: int | None = None) -> dict[str, Any]:
        event = {"time": now().isoformat(), "status": status, "message": message, "grams": grams}
        state = self.store.state.load()
        state["last_run"] = event
        state["history"] = [event, *state.get("history", [])][:HISTORY_LIMIT]
        self.store.state.save(state)
        log.info("sync %s: %s", status, message)
        return event

    def run(self, force: bool = False) -> dict[str, Any]:
        """Push the latest Garmin weigh-in to Zwift.

        Scheduled runs only push weigh-ins that haven't been synced before, so a
        weight you change by hand in Zwift stays until your next weigh-in.
        ``force`` pushes the latest weigh-in even if it was already synced.
        """
        with self._lock:
            try:
                return self._run(force)
            except (GarminNotConnected, ZwiftError) as exc:
                return self._record("error", str(exc))
            except Exception as exc:  # keep the scheduler alive whatever happens
                log.exception("sync failed")
                return self._record("error", f"Unexpected error: {exc}")

    def _run(self, force: bool) -> dict[str, Any]:
        zwift = self.zwift()
        if zwift is None:
            return self._record("error", "Zwift is not connected")
        weigh_in = self.garmin.fetch_latest()
        if weigh_in is None:
            return self._record("skipped", "No weigh-ins in Garmin Connect in the last 30 days")
        self.store.state.update(latest_weigh_in=weigh_in.to_dict())
        when = weigh_in.timestamp.strftime("%Y-%m-%d %H:%M UTC")

        if not force and self.store.state.load().get("synced_sample_pk") == weigh_in.sample_pk:
            return self._record("skipped", f"No new weigh-in since {when}", weigh_in.grams)

        changed = zwift.set_weight(weigh_in.grams)
        self.store.state.update(synced_sample_pk=weigh_in.sample_pk)
        if changed:
            return self._record("updated", f"Zwift weight updated from weigh-in at {when}", weigh_in.grams)
        return self._record("unchanged", f"Zwift already had the weight from {when}", weigh_in.grams)

    # --- scheduler ----------------------------------------------------------

    def next_run(self) -> datetime:
        last = self.store.state.load().get("last_scheduled_run")
        if not last:
            return now()
        return datetime.fromisoformat(last) + timedelta(hours=self.interval_hours)

    def _loop(self) -> None:
        while True:
            wait = (self.next_run() - now()).total_seconds()
            if wait > 0:
                self._wake.wait(timeout=min(wait, 3600))
                self._wake.clear()
                continue
            self.store.state.update(last_scheduled_run=now().isoformat())
            if self.garmin.connected and self.store.secrets.load().get("zwift_password"):
                self.run()

    def run_soon(self) -> None:
        """Make the scheduler run straight away, e.g. after an account is connected."""
        self.store.state.update(last_scheduled_run=None)
        self._wake.set()

    def start(self) -> None:
        threading.Thread(target=self._loop, name="scheduler", daemon=True).start()
