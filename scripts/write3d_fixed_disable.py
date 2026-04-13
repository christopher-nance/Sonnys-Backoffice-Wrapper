"""WRITE 3d: Fixed full-form round-trip disable.

Two fixes vs Write 3:
1. data-value fallback: when a field has an empty value but a data-value
   attribute (as employee[startDate] does via pickadate), use data-value.
2. Skip employee[sites][N][isAvailable] entirely on update (server uses
   only siteId for collection membership; the checkboxes are UI-only
   and confuse Symfony's CollectionType binding).

Since employee 485 is already disabled, a successful POST with no-op
semantics should land on /employee (success redirect), not
/employee/edit/485?actionXfer=... (failure/no-op redirect).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_HTML = REPO_ROOT / "tests" / "fixtures" / "html"
FIXTURES_PAYLOADS = REPO_ROOT / "tests" / "fixtures" / "payloads"

BASE_URL = "https://washu.sonnyscontrols.com"
USERNAME = "SonnysWrapperTestAccount"
EMPLOYEE_ID = 485

# Field-name patterns to skip entirely in /employee/update payloads
_SKIP_PATTERNS = [
    re.compile(r"^employee\[sites\]\[\d+\]\[isAvailable\]$"),
]


def _login_and_get_cookies() -> dict[str, str]:
    password = os.environ.get("SONNYS_BOT_PASSWORD")
    if not password:
        raise SystemExit("ERROR: SONNYS_BOT_PASSWORD required")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent="SonnysBackofficeWrapper/0.1-write3d")
        page = ctx.new_page()
        page.goto(f"{BASE_URL}/login")
        page.fill("input[name='_username']", USERNAME)
        page.fill("input[name='_password']", password)
        page.click("button[type='submit'], input[type='submit']")
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        cookies = {c["name"]: c["value"] for c in ctx.cookies()}
        browser.close()
    return cookies


def _should_skip(name: str) -> bool:
    return any(p.match(name) for p in _SKIP_PATTERNS)


def parse_edit_form_v2(
    html: str,
    *,
    drop_fields: set[str],
) -> list[tuple[str, str]]:
    """Fixed form parser:
    - Skip elements with disabled attribute
    - Skip fields matching _SKIP_PATTERNS
    - Skip fields in drop_fields (for checkbox-by-omission)
    - For text/hidden/etc: use value, falling back to data-value
    - For checkboxes: only include if checked
    - For radios: only include if checked
    - For selects: include selected option (or first non-placeholder)
    """
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", action=re.compile(r"/employee/update"))
    if form is None:
        raise RuntimeError("could not locate /employee/update form")

    out: list[tuple[str, str]] = []
    for el in form.find_all(["input", "select", "textarea"]):
        name = el.get("name")
        if not name or name in drop_fields or _should_skip(name):
            continue
        if el.get("disabled") is not None:
            continue
        if el.name == "input":
            t = (el.get("type") or "text").lower()
            if t in ("text", "hidden", "number", "email", "tel", "password", "search", "url", "date", "time"):
                value = el.get("value") or ""
                if not value:
                    # FALLBACK to data-value (pickadate and similar widgets)
                    value = el.get("data-value") or ""
                out.append((name, value))
            elif t == "checkbox":
                if el.has_attr("checked"):
                    out.append((name, el.get("value") or "on"))
            elif t == "radio":
                if el.has_attr("checked"):
                    out.append((name, el.get("value") or ""))
            elif t in ("submit", "button", "reset", "image", "file"):
                continue
            else:
                out.append((name, el.get("value") or ""))
        elif el.name == "select":
            if el.has_attr("multiple"):
                for opt in el.find_all("option"):
                    if opt.has_attr("selected"):
                        out.append((name, opt.get("value") or ""))
            else:
                sel_opt = next((o for o in el.find_all("option") if o.has_attr("selected")), None)
                if sel_opt is None:
                    sel_opt = next((o for o in el.find_all("option") if (o.get("value") or "").strip()), None)
                if sel_opt is not None:
                    out.append((name, sel_opt.get("value") or ""))
        elif el.name == "textarea":
            out.append((name, el.get_text()))
    return out


def main() -> int:
    print("=" * 60)
    print(f"WRITE 3d: fixed full-form disable (employee {EMPLOYEE_ID}, already disabled)")
    print("=" * 60)

    cookies = _login_and_get_cookies()
    session = requests.Session()
    session.headers["User-Agent"] = "SonnysBackofficeWrapper/0.1-write3d"
    for name, value in cookies.items():
        session.cookies.set(name, value, domain="washu.sonnyscontrols.com")

    # GET edit
    r_edit = session.get(f"{BASE_URL}/employee/edit/{EMPLOYEE_ID}")
    r_edit.raise_for_status()

    # Parse with fixes
    payload = parse_edit_form_v2(
        r_edit.text, drop_fields={"employee[isActive]"}
    )
    print(f"\nparsed {len(payload)} fields (expected ~17 after fixes)")

    # Show the parsed payload
    for k, v in payload:
        print(f"  {k:<45} = {v!r}")

    # Save
    (FIXTURES_PAYLOADS / "allowed_employee_update_full_disable_v2_request.json").write_text(
        json.dumps(
            {
                "method": "POST",
                "url": f"{BASE_URL}/employee/update",
                "fields": [{"name": k, "value": v} for k, v in payload],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # POST
    print(f"\nPOST /employee/update")
    r_post = session.post(
        f"{BASE_URL}/employee/update",
        data=payload,
        allow_redirects=False,
    )
    print(f"  status: HTTP {r_post.status_code}")
    print(f"  Location: {r_post.headers.get('Location', '(none)')}")
    print(f"  body length: {len(r_post.text)} bytes")

    # Interpretation:
    # - Landing on /employee = success
    # - Landing on /employee/edit/<id>?actionXfer=... = failure/no-op
    loc = r_post.headers.get("Location", "")
    if loc == "/employee":
        print("\n[SUCCESS] landed on /employee — POST accepted as a successful update")
        return 0
    elif "/employee/edit/" in loc:
        print(f"\n[FAILURE] landed on {loc} — POST rejected or treated as no-op")
        # Check flash message on the landed page
        r_verify = session.get(f"{BASE_URL}{loc}")
        soup = BeautifulSoup(r_verify.text, "html.parser")
        for flash in soup.select(".alert, .flash, [class*='error'], [class*='success']"):
            text = flash.get_text(strip=True)
            if text:
                print(f"  flash: {text[:200]}")
        return 1
    else:
        print(f"\n[UNKNOWN] landed on {loc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
