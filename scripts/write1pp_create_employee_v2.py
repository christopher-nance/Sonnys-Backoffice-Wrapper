"""WRITE 1'': Create fresh exploration employee with CORRECTED site availability payload.

Differences from write1_create_employee.py:
- Uses the Symfony-correct site availability pattern:
  - Omit isAllRegionsAllowed, isAllDistrictsAllowedByRegion, isAllSitesAllowedByDistrict
  - Send only disabledRegions[] for regions to disable
  - Send only disabledDistricts[] for districts to disable
  - For AVAILABLE sites: send only sites[N][siteId]=N (hidden input)
  - For NOT-AVAILABLE sites: send only sites[N][isAvailable]=N (checkbox value)
  - Never send both for the same site.
- Uses a different suffix (B2D8) and POS/phone/email to avoid collision with employee 484.
- Uniqueness pre-flight uses &active=all so it catches disabled employees too.

Usage:
    SONNYS_BOT_PASSWORD='...' python scripts/write1pp_create_employee_v2.py
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

SUFFIX = "B2D8"
FIELDS = {
    "first_name": "WrapperExplore",
    "last_name": f"DeleteMe-{SUFFIX}",
    "phone": "5555550002",
    "email": f"wrapper-explore-{SUFFIX}@example.invalid",
    "pos_user_id": "99002",
    "pos_pin": "99998",
    "wage_rate": "1.00",
    "overtime_rate": "1.50",
    "wage_site_id": "17",
    "department_id": "3",
    "start_date": "04/13/2026",
}

# Grant availability to sites 17, 18, 19 only (all in Global Region=1, Global District=1).
ENABLED_SITE_IDS = {17, 18, 19}
ALL_SITE_IDS = {1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20}
ALL_REGION_IDS = {1, 2}
ENABLED_REGION_IDS = {1}
ALL_DISTRICT_IDS = {1, 2}
ENABLED_DISTRICT_IDS = {1}


def _login_and_get_cookies() -> dict[str, str]:
    password = os.environ.get("SONNYS_BOT_PASSWORD")
    if not password:
        raise SystemExit("ERROR: SONNYS_BOT_PASSWORD required")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent="SonnysBackofficeWrapper/0.1-write1pp")
        page = ctx.new_page()
        page.goto(f"{BASE_URL}/login")
        page.fill("input[name='_username']", USERNAME)
        page.fill("input[name='_password']", password)
        page.click("button[type='submit'], input[type='submit']")
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        cookies = {c["name"]: c["value"] for c in ctx.cookies()}
        browser.close()
    return cookies


def _preflight(session: requests.Session) -> None:
    target_pos_id = int(FIELDS["pos_user_id"])
    target_phone = FIELDS["phone"]
    target_email = FIELDS["email"].lower()

    print("[preflight] GET /employee?limit=10000&active=all")
    r = session.get(f"{BASE_URL}/employee?limit=10000&active=all")
    r.raise_for_status()
    print(f"  {len(r.text)} bytes")
    soup = BeautifulSoup(r.text, "html.parser")
    tbl = soup.find("table", class_="table-employees-list")
    rows = [row for row in (tbl.find_all("tr") if tbl else []) if row.find("td")]
    print(f"  {len(rows)} data rows")

    pos_used = set()
    phones_used = set()
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 7:
            continue
        pos_txt = cells[4].get_text(strip=True)
        if pos_txt.isdigit():
            pos_used.add(int(pos_txt))
        phone_txt = cells[6].get_text(strip=True)
        phone_digits = re.sub(r"\D", "", phone_txt)
        if phone_digits:
            phones_used.add(phone_digits)
    print(f"  indexed {len(pos_used)} pos_ids, {len(phones_used)} phones")

    if target_pos_id in pos_used:
        print(f"  [COLLISION] pos_user_id {target_pos_id} already exists")
        raise SystemExit(1)
    if target_phone in phones_used:
        print(f"  [COLLISION] phone {target_phone} already exists")
        raise SystemExit(1)
    print(f"  pos_user_id={target_pos_id}, phone={target_phone}: CLEAR")

    print("[preflight] GET /user/create (for email lookup)")
    r = session.get(f"{BASE_URL}/user/create")
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    sel = soup.find("select", attrs={"name": "user[employeeId]"})
    emails_used = set()
    if sel:
        for opt in sel.find_all("option"):
            e = (opt.get("data-email") or "").strip().lower()
            if e:
                emails_used.add(e)
    print(f"  indexed {len(emails_used)} emails")
    if target_email in emails_used:
        print(f"  [COLLISION] email {target_email} already exists")
        raise SystemExit(1)
    print(f"  email={target_email}: CLEAR")


def _build_payload() -> list[tuple[str, str]]:
    """Corrected site availability: only siteId for available sites, only isAvailable for disabled."""
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
    ]

    # Region/district gating — ONLY send disabled* for the regions/districts to disable.
    # Do NOT send isAllRegionsAllowed, isAllDistrictsAllowedByRegion, isAllSitesAllowedByDistrict
    # (their absence means "not all allowed" which is what we want).
    for rid in sorted(ALL_REGION_IDS - ENABLED_REGION_IDS):
        payload.append(("employee[disabledRegions][]", str(rid)))
    for did in sorted(ALL_DISTRICT_IDS - ENABLED_DISTRICT_IDS):
        payload.append(("employee[disabledDistricts][]", str(did)))

    # Site availability:
    # - AVAILABLE sites: send ONLY the hidden siteId (no isAvailable)
    # - NOT-AVAILABLE sites: send ONLY isAvailable (no siteId)
    for sid in sorted(ALL_SITE_IDS):
        if sid in ENABLED_SITE_IDS:
            payload.append((f"employee[sites][{sid}][siteId]", str(sid)))
        else:
            payload.append((f"employee[sites][{sid}][isAvailable]", str(sid)))

    return payload


def _submit(session: requests.Session, payload: list[tuple[str, str]]) -> int | None:
    print(f"\n[write] POST /employee/insert ({len(payload)} fields)")
    (FIXTURES_PAYLOADS / "allowed_employee_insert_v2_request.json").write_text(
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
    r = session.post(f"{BASE_URL}/employee/insert", data=payload, allow_redirects=False)
    print(f"  status: HTTP {r.status_code}")
    print(f"  Location: {r.headers.get('Location', '(none)')}")
    (FIXTURES_HTML / "employee_insert_v2_response.html").write_text(r.text, encoding="utf-8")
    (FIXTURES_PAYLOADS / "allowed_employee_insert_v2_response.json").write_text(
        json.dumps(
            {
                "status_code": r.status_code,
                "headers": dict(r.headers),
                "body_length": len(r.text),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    location = r.headers.get("Location", "")
    m = re.search(r"/employee/(?:edit|permissions|compensation)/(\d+)", location)
    if m:
        emp_id = int(m.group(1))
        print(f"  [SUCCESS] new employee_id = {emp_id}")
        return emp_id
    print(f"  [WARN] could not extract employee_id from Location={location!r}")
    return None


def _verify_sites(session: requests.Session, emp_id: int) -> None:
    print(f"\n[verify] GET /employee/edit/{emp_id}")
    r = session.get(f"{BASE_URL}/employee/edit/{emp_id}")
    r.raise_for_status()
    (FIXTURES_HTML / f"employee_edit_{emp_id}_v2_verify.html").write_text(r.text, encoding="utf-8")
    soup = BeautifulSoup(r.text, "html.parser")
    form = soup.find("form", action=re.compile(r"/employee/update"))
    if form is None:
        print("  [ERROR] could not find edit form")
        return

    # Check region/district/site availability
    all_regions_allowed = form.find("input", attrs={"name": "employee[isAllRegionsAllowed]"})
    if all_regions_allowed:
        print(f"  isAllRegionsAllowed: checked={all_regions_allowed.has_attr('checked')}")

    disabled_regions = [int(i.get("value")) for i in form.find_all("input", attrs={"name": "employee[disabledRegions][]"}) if i.has_attr("checked")]
    disabled_districts = [int(i.get("value")) for i in form.find_all("input", attrs={"name": "employee[disabledDistricts][]"}) if i.has_attr("checked")]
    print(f"  disabledRegions (checked): {disabled_regions}")
    print(f"  disabledDistricts (checked): {disabled_districts}")

    # For sites, the edit form renders each site's isAvailable — checked means "No (not available)"
    checked_not_available = []
    unchecked_available = []
    for inp in form.find_all("input", attrs={"name": re.compile(r"employee\[sites\]\[\d+\]\[isAvailable\]")}):
        name = inp.get("name")
        m = re.search(r"\[sites\]\[(\d+)\]", name)
        if not m:
            continue
        sid = int(m.group(1))
        if inp.has_attr("checked"):
            checked_not_available.append(sid)
        else:
            unchecked_available.append(sid)

    print(f"  sites marked NOT available (checked): {sorted(checked_not_available)}")
    print(f"  sites marked AVAILABLE (unchecked): {sorted(unchecked_available)}")

    intended = sorted(ENABLED_SITE_IDS)
    if sorted(unchecked_available) == intended:
        print(f"  [SUCCESS] sites match intent: {intended}")
    else:
        print(f"  [MISMATCH] intended {intended}, got {sorted(unchecked_available)}")


def main() -> int:
    print("=" * 60)
    print("WRITE 1'': Create exploration employee v2 (corrected sites)")
    print("=" * 60)
    for k, v in FIELDS.items():
        print(f"  {k:<20} = {v}")
    print(f"  enabled_sites        = {sorted(ENABLED_SITE_IDS)}")
    print()

    cookies = _login_and_get_cookies()
    session = requests.Session()
    session.headers["User-Agent"] = "SonnysBackofficeWrapper/0.1-write1pp"
    for name, value in cookies.items():
        session.cookies.set(name, value, domain="washu.sonnyscontrols.com")

    _preflight(session)
    payload = _build_payload()
    emp_id = _submit(session, payload)
    if emp_id:
        # Update sentinel
        (FIXTURES_PAYLOADS / "exploration_employee_id_v2.txt").write_text(str(emp_id))
        _verify_sites(session, emp_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
