"""WRITE 2: Submit permissions template (minimal payload) for employee 485.

Tests whether POST /employee/permissions/update accepts just templateId +
employeeId + hasActionApprovalAuthority, or whether it requires the full
permissions[N][...] matrix.

Captures the request payload and the response, then verifies by GETing
the permissions page and checking that templateId is selected and some
permissions[N] entries are now checked.
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
EMPLOYEE_ID = 485
TEMPLATE_ID = 3  # General User


def _login_and_get_cookies() -> dict[str, str]:
    password = os.environ.get("SONNYS_BOT_PASSWORD")
    if not password:
        raise SystemExit("ERROR: SONNYS_BOT_PASSWORD required")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent="SonnysBackofficeWrapper/0.1-write2")
        page = ctx.new_page()
        page.goto(f"{BASE_URL}/login")
        page.fill("input[name='_username']", USERNAME)
        page.fill("input[name='_password']", password)
        page.click("button[type='submit'], input[type='submit']")
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        cookies = {c["name"]: c["value"] for c in ctx.cookies()}
        browser.close()
    return cookies


def _count_checked_permissions(html: str) -> int:
    """Count how many permissions[N][hasGrantAccess] checkboxes are checked."""
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", id="employee-permission-update-form")
    if form is None:
        return 0
    count = 0
    for inp in form.find_all(
        "input", attrs={"name": re.compile(r"permissions\[\d+\]\[hasGrantAccess\]")}
    ):
        if inp.has_attr("checked"):
            count += 1
    return count


def _current_template(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    sel = soup.find("select", attrs={"name": "templateId"})
    if sel is None:
        return None
    selected = sel.find("option", selected=True)
    if selected is None:
        return None
    return f"{selected.get('value')} ({selected.get_text(strip=True)})"


def main() -> int:
    print("=" * 60)
    print(f"WRITE 2: assign template {TEMPLATE_ID} to employee {EMPLOYEE_ID}")
    print("=" * 60)

    cookies = _login_and_get_cookies()
    session = requests.Session()
    session.headers["User-Agent"] = "SonnysBackofficeWrapper/0.1-write2"
    for name, value in cookies.items():
        session.cookies.set(name, value, domain="washu.sonnyscontrols.com")

    # BEFORE state
    print(f"\n[before] GET /employee/permissions/{EMPLOYEE_ID}")
    r = session.get(f"{BASE_URL}/employee/permissions/{EMPLOYEE_ID}")
    r.raise_for_status()
    (FIXTURES_HTML / f"employee_permissions_{EMPLOYEE_ID}_before.html").write_text(
        r.text, encoding="utf-8"
    )
    before_template = _current_template(r.text)
    before_checked = _count_checked_permissions(r.text)
    print(f"  current templateId: {before_template}")
    print(f"  checked permissions: {before_checked}")

    # Minimal POST
    print("\n[write] POST /employee/permissions/update")
    payload = [
        ("employeeId", str(EMPLOYEE_ID)),
        ("templateId", str(TEMPLATE_ID)),
        ("hasActionApprovalAuthority", "0"),
    ]
    print(f"  payload: {payload}")
    (FIXTURES_PAYLOADS / "allowed_employee_permissions_update_minimal_request.json").write_text(
        json.dumps(
            {
                "method": "POST",
                "url": f"{BASE_URL}/employee/permissions/update",
                "fields": [{"name": k, "value": v} for k, v in payload],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    post_resp = session.post(
        f"{BASE_URL}/employee/permissions/update",
        data=payload,
        allow_redirects=False,
    )
    print(f"  status: HTTP {post_resp.status_code}")
    print(f"  Location: {post_resp.headers.get('Location', '(none)')}")
    print(f"  body length: {len(post_resp.text)} bytes")
    (FIXTURES_HTML / "employee_permissions_update_minimal_response.html").write_text(
        post_resp.text, encoding="utf-8"
    )
    (FIXTURES_PAYLOADS / "allowed_employee_permissions_update_minimal_response.json").write_text(
        json.dumps(
            {
                "status_code": post_resp.status_code,
                "headers": dict(post_resp.headers),
                "body_length": len(post_resp.text),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # AFTER state
    print(f"\n[after] GET /employee/permissions/{EMPLOYEE_ID}")
    r = session.get(f"{BASE_URL}/employee/permissions/{EMPLOYEE_ID}")
    (FIXTURES_HTML / f"employee_permissions_{EMPLOYEE_ID}_after_minimal.html").write_text(
        r.text, encoding="utf-8"
    )
    after_template = _current_template(r.text)
    after_checked = _count_checked_permissions(r.text)
    print(f"  current templateId: {after_template}")
    print(f"  checked permissions: {after_checked}")

    # Also check the employee list for "Access" column
    print("\n[verify] GET /employee?posUserId=99002&active=all")
    r = session.get(f"{BASE_URL}/employee?posUserId=99002&active=all")
    soup = BeautifulSoup(r.text, "html.parser")
    tbl = soup.find("table", class_="table-employees-list")
    if tbl:
        rows = [row for row in tbl.find_all("tr") if row.find("td")]
        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all("td")]
            if "WrapperExplore" in " ".join(cells) or "99002" in " ".join(cells):
                print(f"  list row: {cells}")
                break
        else:
            print("  employee 485 not found in filtered list")

    # Conclusion
    print()
    print("=" * 60)
    if after_template and "3" in str(after_template) and after_checked > 0:
        print(f"SUCCESS: template {TEMPLATE_ID} applied, {after_checked} permissions now checked")
        return 0
    elif after_template and "3" in str(after_template) and after_checked == 0:
        print(f"PARTIAL: template {TEMPLATE_ID} is selected but no permissions are checked.")
        print(
            "  Either the template has no defaults (unlikely) or the server needs the full matrix."
        )
        return 1
    else:
        print(
            f"FAIL: templateId did not change. before={before_template!r} after={after_template!r}"
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
