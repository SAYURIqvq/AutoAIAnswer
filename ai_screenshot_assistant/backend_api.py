from __future__ import annotations

from dataclasses import dataclass

import requests


@dataclass(frozen=True)
class BackendSession:
    session_id: str
    pair_token: str
    pair_url: str
    mobile_url: str


class BackendApi:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.http = requests.Session()
        # Pairing talks to the embedded server on this PC. System proxy settings
        # (for example a local proxy on 127.0.0.1:9674) must not intercept it.
        self.http.trust_env = False

    def create_session(self) -> BackendSession:
        response = self.http.post(f"{self.base_url}/sessions", timeout=10)
        response.raise_for_status()
        data = response.json()
        return BackendSession(
            session_id=data["session_id"],
            pair_token=data["pair_token"],
            pair_url=self.absolute_url(data["pair_url"]),
            mobile_url=self.absolute_url(data["mobile_url"]),
        )

    def absolute_url(self, path_or_url: str) -> str:
        if path_or_url.startswith(("http://", "https://")):
            return path_or_url
        return f"{self.base_url}{path_or_url}"
