from pathlib import Path

import pytest
import requests_mock

from sonnys_backoffice.exceptions import AuthenticationError
from sonnys_backoffice.session import _BackofficeSession

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html"
LOGIN_HTML = (FIXTURES / "login_page.html").read_text(encoding="utf-8")


def test_base_url_construction():
    s = _BackofficeSession(subdomain="washu", username="u", password="p")
    assert s.base_url == "https://washu.sonnyscontrols.com"


def test_login_posts_symfony_credentials_to_login_check():
    s = _BackofficeSession(subdomain="washu", username="bot", password="secret")
    with requests_mock.Mocker() as m:
        m.get("https://washu.sonnyscontrols.com/login", text=LOGIN_HTML)
        m.post(
            "https://washu.sonnyscontrols.com/login_check",
            status_code=302,
            headers={"Location": "/"},
        )
        m.get(
            "https://washu.sonnyscontrols.com/",
            text="<html><body>Home</body></html>",
        )
        s.login()

        login_posts = [r for r in m.request_history if r.method == "POST"]
        assert len(login_posts) == 1
        assert login_posts[0].url == "https://washu.sonnyscontrols.com/login_check"
        body = login_posts[0].text or ""
        assert "_username=bot" in body
        assert "_password=secret" in body


def test_login_failure_raises_authentication_error():
    s = _BackofficeSession(subdomain="washu", username="bot", password="wrong")
    with requests_mock.Mocker() as m:
        m.get("https://washu.sonnyscontrols.com/login", text=LOGIN_HTML)
        m.post(
            "https://washu.sonnyscontrols.com/login_check",
            status_code=200,
            text=LOGIN_HTML,
        )
        with pytest.raises(AuthenticationError):
            s.login()
