"""WRITE 4+5 v3: Fresh employee + fresh BO user + BROWSER-DRIVEN permissions capture.

The pure-requests path for BO permissions failed with "Unable to locate user".
To get ground truth, drive the UI in Playwright and intercept the real POST
via page.on('request') (same technique that worked in Write 2b).

Creates employee Q3R4 (99006) + BO user wrapperQ3R4bo linked to it, drives
the permissions page UI to select General User, clicks save, captures the
outgoing POST body, then verifies and cleans up.
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
from playwright.sync_api import Request, sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_HTML = REPO_ROOT / "tests" / "fixtures" / "html"
FIXTURES_PAYLOADS = REPO_ROOT / "tests" / "fixtures" / "payloads"

BASE_URL = "https://washu.sonnyscontrols.com"
USERNAME_BOT = "SonnysWrapperTestAccount"

SUFFIX = "Q3R4"
EMP_FIELDS = {
    "first_name": "WrapperExplore",
    "last_name": f"DeleteMe-{SUFFIX}",
    "phone": "5555550006",
    "email": f"wrapper-explore-{SUFFIX}@example.invalid",
    "pos_user_id": "99006",
    "pos_pin": "99994",
    "wage_rate": "1.00",
    "overtime_rate": "1.50",
    "wage_site_id": "17",
    "department_id": "3",
    "start_date": "04/13/2026",
}
BO_USERNAME = f"wrapper{SUFFIX}bo"
BO_PASSWORD = "TestBoUserPW3!"
TARGET_BO_TEMPLATE_VALUE = "3"  # General User

ENABLED_SITE_IDS = {17, 18, 19}
ALL_SITE_IDS = {1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20}
ALL_REGION_IDS = {1, 2}
ENABLED_REGION_IDS = {1}
ALL_DISTRICT_IDS = {1, 2}
ENABLED_DISTRICT_IDS = {1}

_SKIP_UPDATE_PATTERNS = [re.compile(r"^employee\[sites\]\[\d+\]\[isAvailable\]$")]


def login_and_cookies() -> dict:
    password = os.environ.get("SONNYS_BOT_PASSWORD")
    if not password:
        raise SystemExit("ERROR: SONNYS_BOT_PASSWORD required")
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(user_agent="SonnysBackofficeWrapper/0.1-w45v3")
        page = ctx.new_page()
        page.goto(f"{BASE_URL}/login")
        page.fill("input[name='_username']", USERNAME_BOT)
        page.fill("input[name='_password']", password)
        page.click("button[type='submit'], input[type='submit']")
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        cookies = {c["name"]: c["value"] for c in ctx.cookies()}
        b.close()
    return cookies


def requests_session(cookies: dict) -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = "SonnysBackofficeWrapper/0.1-w45v3"
    for k, v in cookies.items():
        s.cookies.set(k, v, domain="washu.sonnyscontrols.com")
    return s


def preflight(session: requests.Session) -> None:
    print("\n[preflight]")
    r = session.get(f"{BASE_URL}/employee?limit=10000&active=all")
    soup = BeautifulSoup(r.text, "html.parser")
    tbl = soup.find("table", class_="table-employees-list")
    for row in (tbl.find_all("tr") if tbl else []):
        cells = row.find_all("td")
        if len(cells) < 7:
            continue
        if cells[4].get_text(strip=True) == EMP_FIELDS["pos_user_id"]:
            raise SystemExit(f"[collision] pos")
        if re.sub(r"\D", "", cells[6].get_text(strip=True)) == EMP_FIELDS["phone"]:
            raise SystemExit(f"[collision] phone")
    r = session.get(f"{BASE_URL}/user/create")
    soup = BeautifulSoup(r.text, "html.parser")
    sel = soup.find("select", attrs={"name": "user[employeeId]"})
    if sel:
        for opt in sel.find_all("option"):
            if (opt.get("data-email") or "").strip().lower() == EMP_FIELDS["email"].lower():
                raise SystemExit("[collision] email")
    r = session.get(f"{BASE_URL}/user?limit=10000&active=all")
    if BO_USERNAME.lower() in r.text.lower():
        raise SystemExit(f"[collision] username {BO_USERNAME}")
    print("  clean")


def create_employee(session: requests.Session) -> int:
    print("\n[create employee]")
    payload: list[tuple[str, str]] = [
        ("employee[firstName]", EMP_FIELDS["first_name"]),
        ("employee[lastName]", EMP_FIELDS["last_name"]),
        ("employee[phone]", EMP_FIELDS["phone"]),
        ("employee[email]", EMP_FIELDS["email"]),
        ("employee[startDate]", EMP_FIELDS["start_date"]),
        ("posCredential[POSLoginID]", EMP_FIELDS["pos_user_id"]),
        ("posCredential[POSLoginPassword]", EMP_FIELDS["pos_pin"]),
        ("wage[isHourly]", "1"),
        ("wage[regularRate]", EMP_FIELDS["wage_rate"]),
        ("wage[overtimeRate]", EMP_FIELDS["overtime_rate"]),
        ("wage[isOvertimeEligible]", "1"),
        ("wage[siteId]", EMP_FIELDS["wage_site_id"]),
        ("employee[departments][]", EMP_FIELDS["department_id"]),
    ]
    for rid in sorted(ALL_REGION_IDS - ENABLED_REGION_IDS):
        payload.append(("employee[disabledRegions][]", str(rid)))
    for did in sorted(ALL_DISTRICT_IDS - ENABLED_DISTRICT_IDS):
        payload.append(("employee[disabledDistricts][]", str(did)))
    for sid in sorted(ALL_SITE_IDS):
        if sid in ENABLED_SITE_IDS:
            payload.append((f"employee[sites][{sid}][siteId]", str(sid)))
        else:
            payload.append((f"employee[sites][{sid}][isAvailable]", str(sid)))
    r = session.post(f"{BASE_URL}/employee/insert", data=payload, allow_redirects=False)
    loc = r.headers.get("Location", "")
    m = re.search(r"/employee/(?:edit|permissions|compensation)/(\d+)", loc)
    if not m:
        raise SystemExit(f"[fail] Location={loc}")
    emp_id = int(m.group(1))
    print(f"  employee_id={emp_id}")
    return emp_id


def create_bo_user(session: requests.Session, linked_emp_id: int) -> int:
    print(f"\n[create BO user linked to {linked_emp_id}]")
    payload = [
        ("employee[isOnSiteEmployee]", "1"),
        ("user[employeeId]", str(linked_emp_id)),
        ("employee[email]", EMP_FIELDS["email"]),
        ("user[username]", BO_USERNAME),
        ("user[password]", BO_PASSWORD),
        ("user[confirmPassword]", BO_PASSWORD),
    ]
    r = session.post(f"{BASE_URL}/user/insert", data=payload, allow_redirects=False)
    loc = r.headers.get("Location", "")
    m = re.search(r"/user/permissions/(\d+)", loc)
    if not m:
        raise SystemExit(f"[fail] Location={loc}")
    user_id = int(m.group(1))
    print(f"  bo_user_id={user_id}")
    return user_id


def drive_bo_permissions_via_browser(cookies: dict, user_id: int) -> list[dict]:
    """Navigate to /user/permissions/<user_id>, select General User template,
    click save, capture the resulting POST body."""
    print(f"\n[browser] assigning BO permissions to user {user_id}")
    captured: list[dict] = []

    def on_request(req: Request) -> None:
        if req.method.upper() == "POST" and "/user/permissions/update" in req.url:
            captured.append({
                "method": req.method,
                "url": req.url,
                "post_data": req.post_data,
                "headers": {k: v for k, v in req.headers.items() if k.lower() != "cookie"},
            })
            print(f"  [captured] POST {req.url} ({len(req.post_data or '')} bytes)")

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(user_agent="SonnysBackofficeWrapper/0.1-w45v3-browser")
        for k, v in cookies.items():
            ctx.add_cookies([{"name": k, "value": v, "domain": "washu.sonnyscontrols.com", "path": "/"}])
        page = ctx.new_page()
        page.on("request", on_request)

        print(f"  goto /user/permissions/{user_id}")
        page.goto(f"{BASE_URL}/user/permissions/{user_id}", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # Save pre-state
        (FIXTURES_HTML / f"w45v3_user_permissions_page_{user_id}_pre.html").write_text(
            page.content(), encoding="utf-8"
        )

        # Select General User template (value="3")
        print(f"  select template={TARGET_BO_TEMPLATE_VALUE}")
        try:
            page.select_option("select[name='template']", TARGET_BO_TEMPLATE_VALUE)
            page.wait_for_timeout(1500)
        except Exception as exc:
            print(f"  [warn] select: {exc}")

        # Click save
        print("  click save")
        try:
            with page.expect_navigation(wait_until="domcontentloaded", timeout=20000):
                page.click("form[action='/user/permissions/update'] button[type='submit']")
            print(f"  landed on: {page.url}")
        except Exception as exc:
            print(f"  [warn] nav: {exc}")
        page.wait_for_timeout(1500)
        (FIXTURES_HTML / f"w45v3_user_permissions_page_{user_id}_post.html").write_text(
            page.content(), encoding="utf-8"
        )
        b.close()

    return captured


def parse_edit_form_for_update(html: str, *, drop_fields: set[str]) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", action=re.compile(r"/employee/update"))
    out: list[tuple[str, str]] = []
    for el in form.find_all(["input", "select", "textarea"]):
        name = el.get("name")
        if not name or name in drop_fields:
            continue
        if any(p.match(name) for p in _SKIP_UPDATE_PATTERNS):
            continue
        if el.get("disabled") is not None:
            continue
        if el.name == "input":
            t = (el.get("type") or "text").lower()
            if t in ("text", "hidden", "number", "email", "tel", "password", "search", "url", "date", "time"):
                value = el.get("value") or ""
                if not value:
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


def disable_employee(session: requests.Session, emp_id: int) -> None:
    print(f"\n[cleanup] disable employee {emp_id}")
    r = session.get(f"{BASE_URL}/employee/edit/{emp_id}")
    payload = parse_edit_form_for_update(r.text, drop_fields={"employee[isActive]"})
    r_post = session.post(f"{BASE_URL}/employee/update", data=payload, allow_redirects=False)
    print(f"  HTTP {r_post.status_code}, Location: {r_post.headers.get('Location')}")


def main() -> int:
    print("=" * 66)
    print(f"WRITE 4+5 v3: fresh employee {SUFFIX} + BO user + browser-driven perms")
    print("=" * 66)
    cookies = login_and_cookies()
    session = requests_session(cookies)
    preflight(session)
    emp_id = create_employee(session)
    (FIXTURES_PAYLOADS / "w45v3_employee_id.txt").write_text(str(emp_id))
    try:
        user_id = create_bo_user(session, emp_id)
        (FIXTURES_PAYLOADS / "w45v3_bo_user_id.txt").write_text(str(user_id))
        captured = drive_bo_permissions_via_browser(cookies, user_id)
        if captured:
            out = FIXTURES_PAYLOADS / "allowed_bo_user_permissions_browser_captured.json"
            out.write_text(json.dumps(captured, indent=2), encoding="utf-8")
            print(f"\n[saved] {out.relative_to(REPO_ROOT)}")
            # Summary
            post_data = captured[0].get("post_data") or ""
            pairs = parse_qsl(post_data, keep_blank_values=True)
            print(f"  {len(pairs)} fields in captured POST")
            non_perms = [p for p in pairs if not p[0].startswith("perms[")]
            print(f"  non-perms fields ({len(non_perms)}):")
            for k, v in non_perms:
                print(f"    {k} = {v!r}")
            enabled = [p for p in pairs if "isEnabled" in p[0]]
            print(f"  perms[N][isEnabled]: {len(enabled)}")
        else:
            print("\n[ERROR] no POST captured")
    finally:
        disable_employee(session, emp_id)

    return 0


if __name__ == "__main__":
    sys.exit(main())
