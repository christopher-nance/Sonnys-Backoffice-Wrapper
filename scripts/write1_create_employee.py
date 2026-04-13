"""WRITE 1: Create one disposable exploration employee.

Uses Playwright only for login, then switches to a requests.Session with the
same cookies. Performs a pre-flight uniqueness check against /employee?limit=10000
and /user/create. Then POSTs /employee/insert with a fully-populated payload and
captures the response.

Safety:
- Pre-flight verifies pos_user_id (99001), phone (5555550001), and email do NOT
  already exist on the tenant. Aborts if any collision.
- Only ONE POST to /employee/insert is performed.
- Captures the request body, response status, response headers, and landed URL
  into tests/fixtures/.

Usage:
    SONNYS_BOT_PASSWORD='...' python scripts/write1_create_employee.py
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

# Exploration employee field values
SUFFIX = "A3F9"
FIELDS = {
    "first_name": "WrapperExplore",
    "last_name": f"DeleteMe-{SUFFIX}",
    "phone": "5555550001",
    "email": f"wrapper-explore-{SUFFIX}@example.invalid",
    "pos_user_id": "99001",
    "pos_pin": "99999",
    "wage_rate": "1.00",
    "overtime_rate": "1.50",
    "wage_site_id": "17",  # NOLO
    "department_id": "3",  # Greeter
    "start_date": "04/13/2026",
}

# Sites to grant availability: 17, 18, 19 (all in Global Region=1 / Global District=1)
ENABLED_SITE_IDS = {17, 18, 19}
# All sites visible in the employee create form
ALL_SITE_IDS = {1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20}
# All regions on WashU
ALL_REGION_IDS = {1, 2}
ENABLED_REGION_IDS = {1}  # only Global Region
# All districts
ALL_DISTRICT_IDS = {1, 2}
ENABLED_DISTRICT_IDS = {1}  # only Global District


def _login_and_get_cookies() -> dict[str, str]:
    """Login via Playwright and return the cookie jar as a dict."""
    password = os.environ.get("SONNYS_BOT_PASSWORD")
    if not password:
        raise SystemExit("ERROR: SONNYS_BOT_PASSWORD required")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="SonnysBackofficeWrapper/0.1-write1")
        page = context.new_page()
        page.goto(f"{BASE_URL}/login")
        page.fill("input[name='_username']", USERNAME)
        page.fill("input[name='_password']", password)
        page.click("button[type='submit'], input[type='submit']")
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        landed = page.url
        print(f"[login] landed on {landed}")
        cookies = {c["name"]: c["value"] for c in context.cookies()}
        browser.close()
    return cookies


def _preflight_uniqueness(session: requests.Session) -> None:
    """GET /employee?limit=10000 and /user/create; abort if any of our target fields collide."""
    target_pos_id = int(FIELDS["pos_user_id"])
    target_phone = FIELDS["phone"]
    target_email = FIELDS["email"].lower()

    print("[preflight] GET /employee?limit=10000")
    r = session.get(f"{BASE_URL}/employee?limit=10000")
    r.raise_for_status()
    print(f"  response: HTTP {r.status_code}, {len(r.text)} bytes")

    soup = BeautifulSoup(r.text, "html.parser")
    tbl = soup.find("table", class_="table-employees-list")
    if tbl is None:
        print("  WARN: employee list table not found")
    else:
        rows = tbl.find_all("tr")
        print(f"  {len(rows)} rows in table")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 7:
                continue
            row_text = " | ".join(c.get_text(strip=True) for c in cells)
            # POS ID is in column 5 (index 4)
            pos_text = cells[4].get_text(strip=True) if len(cells) > 4 else ""
            phone_text = cells[6].get_text(strip=True) if len(cells) > 6 else ""
            phone_digits = re.sub(r"\D", "", phone_text)
            if pos_text == str(target_pos_id):
                print(f"  [COLLISION] pos_user_id {target_pos_id} already used: {row_text[:100]}")
                raise SystemExit(1)
            if phone_digits == target_phone:
                print(f"  [COLLISION] phone {target_phone} already used: {row_text[:100]}")
                raise SystemExit(1)
        print(f"  pos_user_id={target_pos_id} and phone={target_phone}: CLEAR")

    print("[preflight] GET /user/create")
    r = session.get(f"{BASE_URL}/user/create")
    r.raise_for_status()
    print(f"  response: HTTP {r.status_code}, {len(r.text)} bytes")
    soup = BeautifulSoup(r.text, "html.parser")
    sel = soup.find("select", attrs={"name": "user[employeeId]"})
    if sel is None:
        print("  WARN: user[employeeId] dropdown not found")
    else:
        emails = set()
        for opt in sel.find_all("option"):
            e = (opt.get("data-email") or "").strip().lower()
            if e:
                emails.add(e)
        print(f"  {len(emails)} unique emails in dropdown")
        if target_email in emails:
            print(f"  [COLLISION] email {target_email} already used")
            raise SystemExit(1)
        print(f"  email={target_email}: CLEAR")


def _build_payload() -> list[tuple[str, str]]:
    """Construct the form payload as a list of (key, value) tuples (preserves ordering
    and allows repeated keys for array fields)."""
    payload: list[tuple[str, str]] = [
        ("employee[firstName]", FIELDS["first_name"]),
        ("employee[lastName]", FIELDS["last_name"]),
        ("employee[phone]", FIELDS["phone"]),
        ("employee[email]", FIELDS["email"]),
        ("employee[startDate]", FIELDS["start_date"]),
        ("posCredential[POSLoginID]", FIELDS["pos_user_id"]),
        ("posCredential[POSLoginPassword]", FIELDS["pos_pin"]),
        ("wage[isHourly]", "1"),
        ("wage[regularRate]", FIELDS["wage_rate"]),
        ("wage[overtimeRate]", FIELDS["overtime_rate"]),
        ("wage[isOvertimeEligible]", "1"),
        ("wage[siteId]", FIELDS["wage_site_id"]),
        ("employee[departments][]", FIELDS["department_id"]),
        # Region/district gating
        ("employee[isAllRegionsAllowed]", "0"),
    ]
    for rid in sorted(ALL_REGION_IDS - ENABLED_REGION_IDS):
        payload.append(("employee[disabledRegions][]", str(rid)))
    for did in sorted(ALL_DISTRICT_IDS - ENABLED_DISTRICT_IDS):
        payload.append(("employee[disabledDistricts][]", str(did)))
    # Site availability
    for sid in sorted(ALL_SITE_IDS):
        is_avail = "1" if sid in ENABLED_SITE_IDS else "0"
        payload.append((f"employee[sites][{sid}][isAvailable]", is_avail))
        payload.append((f"employee[sites][{sid}][siteId]", str(sid)))
    return payload


def _submit_and_capture(session: requests.Session, payload: list[tuple[str, str]]) -> None:
    """POST /employee/insert and capture request/response into fixtures."""
    print(f"\n[write] POST {BASE_URL}/employee/insert ({len(payload)} fields)")
    # Save the payload we're about to send
    payload_path = FIXTURES_PAYLOADS / "allowed_employee_insert_request.json"
    payload_path.write_text(
        json.dumps(
            {
                "method": "POST",
                "url": f"{BASE_URL}/employee/insert",
                "fields": [{"name": k, "value": v} for k, v in payload],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"  recorded outbound payload -> {payload_path.relative_to(REPO_ROOT)}")

    # Disable automatic redirects so we can inspect the 302 target
    r = session.post(
        f"{BASE_URL}/employee/insert",
        data=payload,
        allow_redirects=False,
    )
    print(f"  response status: HTTP {r.status_code}")
    print(f"  Location header: {r.headers.get('Location', '(none)')}")
    print(f"  Content-Type:    {r.headers.get('Content-Type', '(none)')}")
    print(f"  body length:     {len(r.text)} bytes")

    # Save the raw response
    resp_path = FIXTURES_HTML / "employee_insert_response.html"
    resp_path.write_text(r.text, encoding="utf-8")
    print(f"  recorded response -> {resp_path.relative_to(REPO_ROOT)}")

    # Save metadata
    meta_path = FIXTURES_PAYLOADS / "allowed_employee_insert_response.json"
    meta_path.write_text(
        json.dumps(
            {
                "status_code": r.status_code,
                "headers": {k: v for k, v in r.headers.items()},
                "url": r.url,
                "body_length": len(r.text),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"  recorded response metadata -> {meta_path.relative_to(REPO_ROOT)}")

    # Extract employee_id if the redirect is to /employee/{edit,permissions}/<id>
    location = r.headers.get("Location", "")
    m = re.search(r"/employee/(?:edit|permissions|compensation)/(\d+)", location)
    if m:
        emp_id = int(m.group(1))
        print(f"\n  [SUCCESS] new employee_id = {emp_id}")
        # Follow the redirect and save that too
        follow = session.get(f"{BASE_URL}{location}" if location.startswith("/") else location)
        follow_path = FIXTURES_HTML / f"employee_permissions_after_insert_{emp_id}.html"
        follow_path.write_text(follow.text, encoding="utf-8")
        print(f"  recorded landed page -> {follow_path.relative_to(REPO_ROOT)}")
        # Write the final employee_id to a sentinel file for subsequent write scripts
        sentinel = FIXTURES_PAYLOADS / "exploration_employee_id.txt"
        sentinel.write_text(str(emp_id))
        print(f"  employee_id sentinel -> {sentinel.relative_to(REPO_ROOT)}")
    else:
        print(f"\n  [WARN] could not extract employee_id from Location={location!r}")
        if r.status_code == 200 and "has-error" in r.text:
            print("  response body contains form errors — likely a validation failure")


def main() -> int:
    print("=" * 60)
    print("WRITE 1: Create exploration employee")
    print("=" * 60)
    for k, v in FIELDS.items():
        print(f"  {k:<20} = {v}")
    print(f"  enabled_sites        = {sorted(ENABLED_SITE_IDS)}")
    print(f"  enabled_regions      = {sorted(ENABLED_REGION_IDS)}")
    print(f"  enabled_districts    = {sorted(ENABLED_DISTRICT_IDS)}")
    print()

    cookies = _login_and_get_cookies()
    session = requests.Session()
    session.headers["User-Agent"] = "SonnysBackofficeWrapper/0.1-write1"
    for name, value in cookies.items():
        session.cookies.set(name, value, domain="washu.sonnyscontrols.com")

    _preflight_uniqueness(session)
    payload = _build_payload()
    _submit_and_capture(session, payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
