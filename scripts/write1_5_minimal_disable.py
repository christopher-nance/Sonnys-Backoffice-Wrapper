"""WRITE 1.5: Test minimal-POST disable on employee 484.

Posts only {employee[id]=484, employee[isActive]=0} to /employee/update
and checks whether Symfony's form binding accepts it or wipes other
fields.

Captures:
- The before-state of employee 484 (GET /employee/edit/484)
- The POST request body
- The POST response
- The after-state of employee 484 (GET /employee/edit/484)
- A side-by-side comparison of before/after field values

Usage:
    SONNYS_BOT_PASSWORD='...' python scripts/write1_5_minimal_disable.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_HTML = REPO_ROOT / "tests" / "fixtures" / "html"
FIXTURES_PAYLOADS = REPO_ROOT / "tests" / "fixtures" / "payloads"

BASE_URL = "https://washu.sonnyscontrols.com"
USERNAME = "SonnysWrapperTestAccount"
EMPLOYEE_ID = 484

# Fields we'll sample before/after to detect a wipe
FIELDS_TO_SAMPLE = [
    "employee[firstName]",
    "employee[lastName]",
    "employee[phone]",
    "employee[email]",
    "employee[isActive]",
    "posCredential[POSLoginID]",
    "posCredential[POSLoginPassword]",
    "employee[startDate]",
    "employee[emergencyContactName]",
    "employee[emergencyContactPhone]",
    "employee[adpEmployeeId]",
]


def _login_and_get_cookies() -> dict[str, str]:
    password = os.environ.get("SONNYS_BOT_PASSWORD")
    if not password:
        raise SystemExit("ERROR: SONNYS_BOT_PASSWORD required")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent="SonnysBackofficeWrapper/0.1-write1.5")
        page = ctx.new_page()
        page.goto(f"{BASE_URL}/login")
        page.fill("input[name='_username']", USERNAME)
        page.fill("input[name='_password']", password)
        page.click("button[type='submit'], input[type='submit']")
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        cookies = {c["name"]: c["value"] for c in ctx.cookies()}
        browser.close()
    return cookies


def _sample_edit_page(html: str) -> dict[str, str | bool | None]:
    """Extract sample field values from an /employee/edit/<id> page."""
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", action=re.compile(r"/employee/update"))
    if form is None:
        return {"_error": "form not found"}
    sample: dict[str, str | bool | None] = {}
    for fname in FIELDS_TO_SAMPLE:
        inp = form.find(["input", "select", "textarea"], attrs={"name": fname})
        if inp is None:
            sample[fname] = None
            continue
        t = inp.get("type", inp.name)
        if t == "checkbox":
            sample[fname] = inp.has_attr("checked")
        else:
            sample[fname] = inp.get("value", "") or ""
    return sample


def main() -> int:
    print("=" * 60)
    print(f"WRITE 1.5: minimal disable of employee {EMPLOYEE_ID}")
    print("=" * 60)
    cookies = _login_and_get_cookies()
    session = requests.Session()
    session.headers["User-Agent"] = "SonnysBackofficeWrapper/0.1-write1.5"
    for name, value in cookies.items():
        session.cookies.set(name, value, domain="washu.sonnyscontrols.com")

    # 1. BEFORE state
    print(f"\n[before] GET /employee/edit/{EMPLOYEE_ID}")
    r_before = session.get(f"{BASE_URL}/employee/edit/{EMPLOYEE_ID}")
    r_before.raise_for_status()
    (FIXTURES_HTML / f"employee_edit_{EMPLOYEE_ID}_before_disable.html").write_text(
        r_before.text, encoding="utf-8"
    )
    before = _sample_edit_page(r_before.text)
    print("  before snapshot:")
    for k, v in before.items():
        print(f"    {k:<40} = {v!r}")

    # 2. Minimal POST
    print("\n[write] POST /employee/update with minimal payload")
    minimal_payload = [
        ("employee[id]", str(EMPLOYEE_ID)),
        ("employee[isActive]", "0"),
    ]
    payload_path = FIXTURES_PAYLOADS / "allowed_employee_update_minimal_disable_request.json"
    payload_path.write_text(
        json.dumps(
            {
                "method": "POST",
                "url": f"{BASE_URL}/employee/update",
                "fields": [{"name": k, "value": v} for k, v in minimal_payload],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    r_post = session.post(
        f"{BASE_URL}/employee/update",
        data=minimal_payload,
        allow_redirects=False,
    )
    print(f"  status: HTTP {r_post.status_code}")
    print(f"  Location: {r_post.headers.get('Location', '(none)')}")
    print(f"  body len: {len(r_post.text)} bytes")
    (FIXTURES_HTML / "employee_update_minimal_disable_response.html").write_text(
        r_post.text, encoding="utf-8"
    )
    (FIXTURES_PAYLOADS / "allowed_employee_update_minimal_disable_response.json").write_text(
        json.dumps(
            {
                "status_code": r_post.status_code,
                "headers": dict(r_post.headers),
                "body_length": len(r_post.text),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # 3. AFTER state
    print(f"\n[after] GET /employee/edit/{EMPLOYEE_ID}")
    r_after = session.get(f"{BASE_URL}/employee/edit/{EMPLOYEE_ID}")
    (FIXTURES_HTML / f"employee_edit_{EMPLOYEE_ID}_after_minimal_disable.html").write_text(
        r_after.text, encoding="utf-8"
    )
    after = _sample_edit_page(r_after.text)
    print("  after snapshot:")
    for k, v in after.items():
        print(f"    {k:<40} = {v!r}")

    # 4. Compare
    print("\n" + "=" * 60)
    print("COMPARISON")
    print("=" * 60)
    all_keys = set(before.keys()) | set(after.keys())
    wiped = []
    unchanged = []
    toggled = []
    for k in sorted(all_keys):
        b = before.get(k)
        a = after.get(k)
        if b == a:
            unchanged.append((k, a))
        elif k == "employee[isActive]":
            toggled.append((k, b, a))
        else:
            wiped.append((k, b, a))

    print(f"\n[unchanged] {len(unchanged)} fields")
    for k, v in unchanged:
        print(f"  {k:<40} = {v!r}")

    print(f"\n[toggled-expected] {len(toggled)}")
    for k, b, a in toggled:
        print(f"  {k:<40} before={b!r} -> after={a!r}")

    if wiped:
        print(f"\n[WIPED] {len(wiped)} fields changed unexpectedly — minimal POST is UNSAFE")
        for k, b, a in wiped:
            print(f"  {k:<40} before={b!r} -> after={a!r}")
        print("\nCONCLUSION: minimal POST wipes data. disable_employee must use full round-trip.")
        return 1

    if after.get("employee[isActive]") is True:
        print("\n[ERROR] employee[isActive] is still checked — disable did NOT work")
        print("minimal POST was accepted but had no effect. Something else is wrong.")
        return 2

    print("\nCONCLUSION: minimal POST works. isActive toggled off, all other fields preserved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
