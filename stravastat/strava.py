"""Thin client for the Strava API v3 (OAuth refresh-token flow)."""

from __future__ import annotations

import time
from typing import Any, Iterator

import requests

TOKEN_URL = "https://www.strava.com/oauth/token"
API_BASE = "https://www.strava.com/api/v3"


class StravaError(RuntimeError):
    pass


class StravaClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        timeout: float = 30.0,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.timeout = timeout
        self._access_token: str | None = None
        self._expires_at: float = 0.0
        self._session = requests.Session()

    def _authenticate(self) -> str:
        response = self._session.post(
            TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise StravaError(
                f"Could not refresh Strava access token "
                f"(HTTP {response.status_code}): {response.text[:300]}"
            )
        payload = response.json()
        if payload.get("refresh_token") and payload["refresh_token"] != self.refresh_token:
            print(
                "WARNING: Strava rotated the refresh token. Update "
                "STRAVA_REFRESH_TOKEN to the new value, otherwise the job "
                "will stop working when the old token is invalidated."
            )
        self._access_token = payload["access_token"]
        self._expires_at = float(payload.get("expires_at", time.time() + 3500))
        return self._access_token

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if self._access_token is None or time.time() >= self._expires_at - 60:
            self._authenticate()
        response = self._session.get(
            f"{API_BASE}{path}",
            headers={"Authorization": f"Bearer {self._access_token}"},
            params=params,
            timeout=self.timeout,
        )
        if response.status_code == 401:
            self._authenticate()
            response = self._session.get(
                f"{API_BASE}{path}",
                headers={"Authorization": f"Bearer {self._access_token}"},
                params=params,
                timeout=self.timeout,
            )
        if response.status_code == 404:
            return None
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", "60"))
            time.sleep(min(retry_after, 120))
            return self._get(path, params)
        if response.status_code != 200:
            raise StravaError(
                f"Strava API error on {path} (HTTP {response.status_code}): "
                f"{response.text[:300]}"
            )
        return response.json()

    def get_activities(
        self, after_epoch: int | None = None, per_page: int = 100
    ) -> Iterator[dict[str, Any]]:
        page = 1
        while True:
            params: dict[str, Any] = {"per_page": per_page, "page": page}
            if after_epoch is not None:
                params["after"] = after_epoch
            batch = self._get("/athlete/activities", params)
            if not batch:
                return
            yield from batch
            if len(batch) < per_page:
                return
            page += 1

    def get_streams(self, activity_id: int, keys: tuple[str, ...] = ("time", "watts", "heartrate")) -> dict[str, list[float]] | None:
        payload = self._get(
            f"/activities/{activity_id}/streams",
            {"keys": ",".join(keys), "key_by_type": "true"},
        )
        if not payload:
            return None
        return {key: entry["data"] for key, entry in payload.items() if "data" in entry}
