"""Minimal client for Zwift's (unofficial) profile API.

Zwift has no public API. These are the endpoints the Zwift companion app and
website use. Every weight update is read back to confirm it took effect, so if
Zwift changes the API the sync reports an error instead of a false success.
"""
from __future__ import annotations

import copy
import time
from typing import Any, Callable

import requests

TOKEN_URL = "https://secure.zwift.com/auth/realms/zwift/protocol/openid-connect/token"
PROFILE_URL = "https://us-or-rly101.zwift.com/api/profiles/me"
WRITE_URL = "https://www.zwift.com/api/profiles/me/{profile_id}"
CLIENT_ID = "Zwift_Mobile_Link"
TIMEOUT = 20
REFRESH_MARGIN = 60

MIN_GRAMS = 30_000
MAX_GRAMS = 300_000


class ZwiftError(Exception):
    pass


class ZwiftAuthError(ZwiftError):
    """Zwift rejected the email/password."""


class ZwiftClient:
    def __init__(
        self,
        email: str,
        password: str,
        tokens: dict[str, Any] | None = None,
        on_tokens: Callable[[dict[str, Any]], None] | None = None,
        session: requests.Session | None = None,
    ):
        self.email = email
        self.password = password
        self.tokens = tokens or None
        self.on_tokens = on_tokens
        self.http = session or requests.Session()

    def _store_tokens(self, response: requests.Response, old_refresh: str | None = None) -> None:
        body = response.json()
        refresh = body.get("refresh_token") or old_refresh
        if not body.get("access_token") or not refresh:
            raise ZwiftError("Zwift login returned incomplete tokens")
        self.tokens = {
            "access_token": body["access_token"],
            "refresh_token": refresh,
            "expires_at": time.time() + float(body.get("expires_in", 300)),
        }
        if self.on_tokens:
            self.on_tokens(self.tokens)

    def login(self) -> None:
        response = self.http.post(TOKEN_URL, timeout=TIMEOUT, data={
            "grant_type": "password",
            "client_id": CLIENT_ID,
            "username": self.email,
            "password": self.password,
        })
        if response.status_code in (400, 401, 403):
            raise ZwiftAuthError("Zwift rejected the email or password")
        if not response.ok:
            raise ZwiftError(f"Zwift login failed (HTTP {response.status_code})")
        self._store_tokens(response)

    def _refresh(self) -> bool:
        """Refresh the access token. Returns False if the refresh token is no longer valid."""
        old_refresh = self.tokens["refresh_token"]
        response = self.http.post(TOKEN_URL, timeout=TIMEOUT, data={
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "refresh_token": old_refresh,
        })
        if response.status_code in (400, 401):
            return False
        if not response.ok:
            raise ZwiftError(f"Zwift token refresh failed (HTTP {response.status_code})")
        self._store_tokens(response, old_refresh)
        return True

    def _renew(self) -> None:
        if not self.tokens or not self._refresh():
            self.login()

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        if not self.tokens:
            self.login()
        elif time.time() >= self.tokens["expires_at"] - REFRESH_MARGIN:
            self._renew()
        extra_headers = kwargs.pop("headers", {})
        for attempt in range(2):
            headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {self.tokens['access_token']}",
                **extra_headers,
            }
            response = self.http.request(method, url, headers=headers, timeout=TIMEOUT, **kwargs)
            if response.status_code != 401 or attempt:
                return response
            self._renew()
        return response

    def get_profile(self) -> dict[str, Any]:
        response = self._request("GET", PROFILE_URL)
        if not response.ok:
            raise ZwiftError(f"Could not read Zwift profile (HTTP {response.status_code})")
        profile = response.json()
        if not isinstance(profile, dict) or "id" not in profile or "weight" not in profile:
            raise ZwiftError("Zwift profile response was missing id or weight")
        return profile

    def set_weight(self, grams: int) -> bool:
        """Set the profile weight in grams. Returns False if it already had that value."""
        if not MIN_GRAMS <= grams <= MAX_GRAMS:
            raise ZwiftError(f"Zwift only accepts 30-300 kg, got {grams / 1000:.1f} kg")
        before = self.get_profile()
        if before["weight"] == grams:
            return False
        payload = copy.deepcopy(before)
        payload["weight"] = grams
        response = self._request(
            "PUT",
            WRITE_URL.format(profile_id=before["id"]),
            json=payload,
            headers={"Source": "zwift-web"},
        )
        if not response.ok:
            raise ZwiftError(f"Zwift rejected the weight update (HTTP {response.status_code})")
        after = self.get_profile()
        if after["weight"] != grams:
            raise ZwiftError(
                "Zwift accepted the update but the profile weight did not change. "
                "Weight can't be changed while you're in an event."
            )
        return True
