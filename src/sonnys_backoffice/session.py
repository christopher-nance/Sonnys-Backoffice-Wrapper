"""Private HTTP session management — login and transparent re-authentication.

Sonny's Backoffice runs on Symfony + PHP. Login has no CSRF token — just an
HTML form that POSTs `_username` and `_password` to `/login_check`. The session
cookie is `PHPSESSID`.
"""
from __future__ import annotations

from typing import Any

import requests

from .exceptions import AuthenticationError, BackofficeServerError


class _BackofficeSession:
    """Owns auth state for a single Backoffice tenant. Not part of the public API."""

    def __init__(
        self,
        *,
        subdomain: str,
        username: str,
        password: str,
        timeout: float = 30.0,
        user_agent: str | None = None,
    ) -> None:
        self.base_url = f"https://{subdomain}.sonnyscontrols.com"
        self._username = username
        self._password = password
        self._timeout = timeout
        self._http = requests.Session()
        if user_agent:
            self._http.headers["User-Agent"] = user_agent
        self._logged_in = False

    def login(self) -> None:
        """Perform login. Safe to call repeatedly."""
        login_page = self._http.get(f"{self.base_url}/login", timeout=self._timeout)
        login_page.raise_for_status()
        resp = self._http.post(
            f"{self.base_url}/login_check",
            data={
                "_username": self._username,
                "_password": self._password,
            },
            timeout=self._timeout,
            allow_redirects=True,
        )
        if _looks_like_login_page(resp.text):
            raise AuthenticationError("Login failed — credentials rejected by Backoffice")
        if resp.status_code >= 400:
            raise BackofficeServerError(
                f"Unexpected login response: HTTP {resp.status_code}"
            )
        self._logged_in = True

    def get(self, path: str, **kwargs: Any) -> requests.Response:
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> requests.Response:
        return self._request("POST", path, **kwargs)

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        if not self._logged_in:
            self.login()
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        kwargs.setdefault("timeout", self._timeout)
        resp = self._http.request(method, url, **kwargs)
        if _looks_like_login_page(resp.text) or resp.status_code in (401, 403):
            self._logged_in = False
            self.login()
            resp = self._http.request(method, url, **kwargs)
            if _looks_like_login_page(resp.text) or resp.status_code in (401, 403):
                raise AuthenticationError("Re-authentication failed")
        return resp

    def close(self) -> None:
        self._http.close()


def _looks_like_login_page(html: str) -> bool:
    """Heuristic: Symfony re-renders the login form on session expiration."""
    return 'name="_username"' in html and 'name="_password"' in html
