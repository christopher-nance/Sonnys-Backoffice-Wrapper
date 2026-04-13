"""WRITE 1'''' + 4 + 5: create fresh active employee + linked BO user + BO permissions.

Sequence (all on one session):
1. Pre-flight uniqueness: POS 99004, phone 5555550004, email F8A1, username wrapperF8A1bo
2. POST /employee/insert → create active employee 4 (suffix F8A1)
3. POST /user/insert (linked mode) → BO user linked to the new employee
4. GET /user/permissions/<id> → parse templates + schema
5. POST /user/permissions/update → full matrix for General User BO template
6. Verify BO user in /user list with Access set
7. POST /employee/update → disable the linked employee as cleanup
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
USERNAME_BOT = "SonnysWrapperTestAccount"

SUFFIX = "F8A1"
EMP_FIELDS = {
    "first_name": "WrapperExplore",
    "last_name": f"DeleteMe-{SUFFIX}",
    "phone": "5555550004",
    "email": f"wrapper-explore-{SUFFIX}@example.invalid",
    "pos_user_id": "99004",
    "pos_pin": "99996",
    "wage_rate": "1.00",
    "overtime_rate": "1.50",
    "wage_site_id": "17",
    "department_id": "3",
    "start_date": "04/13/2026",
}
BO_USERNAME = f"wrapper{SUFFIX}bo"  # wrapperF8A1bo
BO_PASSWORD = "TestBoUserPW1!"
TARGET_BO_TEMPLATE = "General User"

ENABLED_SITE_IDS = {17, 18, 19}
ALL_SITE_IDS = {1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20}
ALL_REGION_IDS = {1, 2}
ENABLED_REGION_IDS = {1}
ALL_DISTRICT_IDS = {1, 2}
ENABLED_DISTRICT_IDS = {1}

_SKIP_UPDATE_PATTERNS = [re.compile(r"^employee\[sites\]\[\d+\]\[isAvailable\]$")]


def save_html(name: str, html: str) -> None:
    (FIXTURES_HTML / f"{name}.html").write_text(html, encoding="utf-8")


def save_payload(name: str, data: dict) -> None:
    (FIXTURES_PAYLOADS / f"{name}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


def login_and_session() -> requests.Session:
    password = os.environ.get("SONNYS_BOT_PASSWORD")
    if not password:
        raise SystemExit("ERROR: SONNYS_BOT_PASSWORD required")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent="SonnysBackofficeWrapper/0.1-w45f")
        page = ctx.new_page()
        page.goto(f"{BASE_URL}/login")
        page.fill("input[name='_username']", USERNAME_BOT)
        page.fill("input[name='_password']", password)
        page.click("button[type='submit'], input[type='submit']")
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        cookies = {c["name"]: c["value"] for c in ctx.cookies()}
        browser.close()
    s = requests.Session()
    s.headers["User-Agent"] = "SonnysBackofficeWrapper/0.1-w45f"
    for n, v in cookies.items():
        s.cookies.set(n, v, domain="washu.sonnyscontrols.com")
    return s


def build_create_employee_payload() -> list[tuple[str, str]]:
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
    return payload


def create_employee(session: requests.Session) -> int:
    print("\n[step 2] CREATE active employee")
    payload = build_create_employee_payload()
    r = session.post(f"{BASE_URL}/employee/insert", data=payload, allow_redirects=False)
    loc = r.headers.get("Location", "")
    m = re.search(r"/employee/(?:edit|permissions|compensation)/(\d+)", loc)
    if not m:
        print(f"  [FAIL] HTTP {r.status_code} Location={loc}")
        raise SystemExit(1)
    emp_id = int(m.group(1))
    print(f"  [SUCCESS] employee_id = {emp_id}")
    save_payload(
        "w45f_employee_insert_request",
        {
            "fields": [{"name": k, "value": v} for k, v in payload],
        },
    )
    return emp_id


def preflight(session: requests.Session) -> None:
    print("\n[step 1] PRE-FLIGHT uniqueness")
    # Employees
    r = session.get(f"{BASE_URL}/employee?limit=10000&active=all")
    soup = BeautifulSoup(r.text, "html.parser")
    tbl = soup.find("table", class_="table-employees-list")
    for row in tbl.find_all("tr") if tbl else []:
        cells = row.find_all("td")
        if len(cells) < 7:
            continue
        if cells[4].get_text(strip=True) == EMP_FIELDS["pos_user_id"]:
            raise SystemExit(f"  [COLLISION] pos {EMP_FIELDS['pos_user_id']}")
        if re.sub(r"\D", "", cells[6].get_text(strip=True)) == EMP_FIELDS["phone"]:
            raise SystemExit(f"  [COLLISION] phone {EMP_FIELDS['phone']}")
    # Emails via /user/create dropdown
    r = session.get(f"{BASE_URL}/user/create")
    soup = BeautifulSoup(r.text, "html.parser")
    sel = soup.find("select", attrs={"name": "user[employeeId]"})
    if sel:
        for opt in sel.find_all("option"):
            e = (opt.get("data-email") or "").strip().lower()
            if e == EMP_FIELDS["email"].lower():
                raise SystemExit(f"  [COLLISION] email {EMP_FIELDS['email']}")
    # BO username: scan /user list
    r = session.get(f"{BASE_URL}/user?limit=10000&active=all")
    if BO_USERNAME.lower() in r.text.lower():
        raise SystemExit(f"  [COLLISION] username {BO_USERNAME}")
    print("  all four clean")


def create_bo_user(session: requests.Session, linked_employee_id: int) -> int:
    print(f"\n[step 3] POST /user/insert (linked mode, employee_id={linked_employee_id})")
    payload = [
        ("employee[isOnSiteEmployee]", "1"),
        ("user[employeeId]", str(linked_employee_id)),
        ("employee[email]", EMP_FIELDS["email"]),
        ("user[username]", BO_USERNAME),
        ("user[password]", BO_PASSWORD),
        ("user[confirmPassword]", BO_PASSWORD),
    ]
    save_payload(
        "w45f_user_insert_request",
        {
            "method": "POST",
            "url": f"{BASE_URL}/user/insert",
            "fields": [{"name": k, "value": v} for k, v in payload],
        },
    )
    r = session.post(f"{BASE_URL}/user/insert", data=payload, allow_redirects=False)
    save_html("w45f_user_insert_response", r.text)
    save_payload(
        "w45f_user_insert_response",
        {
            "status_code": r.status_code,
            "headers": dict(r.headers),
            "body_length": len(r.text),
        },
    )
    loc = r.headers.get("Location", "")
    print(f"  HTTP {r.status_code}, Location: {loc}")
    # Check for failure: redirect back to /user/create with actionXfer
    if "actionXfer" in loc and "/user/create" in loc:
        print("  [FAIL] failure redirect")
        # Fetch the landed page for error messages
        follow = session.get(f"{BASE_URL}{loc}")
        soup = BeautifulSoup(follow.text, "html.parser")
        for alert in soup.find_all(
            class_=lambda c: c and "alert" in (c if isinstance(c, list) else [c])
        ):
            print(f"  error: {alert.get_text(strip=True)[:200]}")
        raise SystemExit(1)
    # Try patterns
    for pat in [r"/user/permissions/(\d+)", r"/user/(?:edit|show)/(\d+)", r"/user/(\d+)"]:
        m = re.search(pat, loc)
        if m:
            return int(m.group(1))
    raise SystemExit(f"could not extract user_id from {loc!r}")


def parse_templates_and_schema(html: str) -> tuple[list[dict], list[dict]]:
    soup = BeautifulSoup(html, "html.parser")
    templates: list[dict] = []
    sel = soup.find("select", attrs={"name": "templateId"})
    if sel:
        for opt in sel.find_all("option"):
            val = (opt.get("value") or "").strip()
            if not val:
                continue
            try:
                tid = int(val)
            except ValueError:
                continue
            grants = [
                int(x)
                for x in (opt.get("data-permissions-set") or "").split(",")
                if x.strip().isdigit()
            ]
            overrides = [
                int(x)
                for x in (opt.get("data-manager-override-permissions-set") or "").split(",")
                if x.strip().isdigit()
            ]
            templates.append(
                {
                    "id": tid,
                    "name": opt.get_text(strip=True),
                    "grants": grants,
                    "overrides": overrides,
                }
            )

    schema: dict[int, dict[str, str]] = {}
    for inp in soup.find_all("input", attrs={"name": re.compile(r"permissions\[\d+\]\[id\]")}):
        m = re.match(r"permissions\[(\d+)\]\[id\]", inp.get("name", ""))
        if not m:
            continue
        pid = int(m.group(1))
        if pid in schema:
            continue
        label_inp = soup.find("input", attrs={"name": f"permissions[{pid}][label]"})
        desc_inp = soup.find("input", attrs={"name": f"permissions[{pid}][description]"})
        schema[pid] = {
            "id": pid,
            "label": (label_inp.get("value") or "") if label_inp else "",
            "description": (desc_inp.get("value") or "") if desc_inp else "",
        }
    return templates, [schema[k] for k in sorted(schema.keys())]


def detect_user_key_and_action(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    for form in soup.find_all("form"):
        if form.find("select", attrs={"name": "templateId"}):
            action = form.get("action", "/user/permissions/update")
            for inp in form.find_all("input", attrs={"type": "hidden"}):
                n = inp.get("name", "")
                if n in ("userId", "employeeId"):
                    return n, action
            return "userId", action
    raise RuntimeError("permissions form not found")


def fetch_bo_permissions_page(session: requests.Session, user_id: int) -> str:
    print(f"\n[step 4] GET BO permissions page for user {user_id}")
    for path in [
        f"/user/permissions/{user_id}",
        f"/user/{user_id}/permissions",
        f"/user/edit/{user_id}",
    ]:
        r = session.get(f"{BASE_URL}{path}")
        if r.status_code == 200 and "templateId" in r.text:
            print(f"  found at {path}")
            save_html(f"w45f_user_permissions_page_{user_id}", r.text)
            return r.text
    raise SystemExit("BO permissions page not found")


def assign_bo_permissions(session: requests.Session, user_id: int, html: str) -> None:
    print(f"\n[step 5] ASSIGN BO template {TARGET_BO_TEMPLATE!r}")
    templates, schema = parse_templates_and_schema(html)
    print(f"  {len(templates)} BO templates, {len(schema)} permission entries")
    for t in templates:
        print(
            f"    [{t['id']}] {t['name']!r} grants={len(t['grants'])} overrides={len(t['overrides'])}"
        )
    target = next((t for t in templates if t["name"].lower() == TARGET_BO_TEMPLATE.lower()), None)
    if target is None:
        raise SystemExit(f"template {TARGET_BO_TEMPLATE!r} not found")
    user_key, action = detect_user_key_and_action(html)
    print(f"  form action: {action}, primary key: {user_key}")

    grants = set(target["grants"])
    overrides = set(target["overrides"])
    payload: list[tuple[str, str]] = [
        (user_key, str(user_id)),
        ("templateId", str(target["id"])),
        ("hasActionApprovalAuthority", "0"),
    ]
    for perm in schema:
        pid = perm["id"]
        payload.append((f"permissions[{pid}][id]", str(pid)))
        payload.append((f"permissions[{pid}][label]", perm["label"]))
        payload.append((f"permissions[{pid}][description]", perm["description"]))
        if pid in grants:
            payload.append((f"permissions[{pid}][hasGrantAccess]", "1"))
        if pid in overrides:
            payload.append((f"permissions[{pid}][requiresOverride]", "1"))

    save_payload(
        "w45f_user_permissions_request",
        {
            "method": "POST",
            "url": f"{BASE_URL}{action}" if action.startswith("/") else action,
            "fields": [{"name": k, "value": v} for k, v in payload],
        },
    )
    url = f"{BASE_URL}{action}" if action.startswith("/") else action
    r = session.post(url, data=payload, allow_redirects=False)
    save_html("w45f_user_permissions_response", r.text)
    save_payload(
        "w45f_user_permissions_response",
        {
            "status_code": r.status_code,
            "headers": dict(r.headers),
            "body_length": len(r.text),
        },
    )
    print(f"  HTTP {r.status_code}, Location: {r.headers.get('Location', '(none)')}")


def verify_bo_user(session: requests.Session) -> None:
    print("\n[step 6] VERIFY BO user in /user list")
    r = session.get(f"{BASE_URL}/user?limit=10000&active=all")
    save_html("w45f_user_list_after", r.text)
    if BO_USERNAME in r.text:
        print(f"  [SUCCESS] {BO_USERNAME!r} present in /user listing")
    else:
        print(f"  [WARN] {BO_USERNAME!r} not found")


def parse_edit_form_for_update(html: str, *, drop_fields: set[str]) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", action=re.compile(r"/employee/update"))
    if form is None:
        raise RuntimeError("edit form not found")
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
            if t in (
                "text",
                "hidden",
                "number",
                "email",
                "tel",
                "password",
                "search",
                "url",
                "date",
                "time",
            ):
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
                    sel_opt = next(
                        (o for o in el.find_all("option") if (o.get("value") or "").strip()), None
                    )
                if sel_opt is not None:
                    out.append((name, sel_opt.get("value") or ""))
        elif el.name == "textarea":
            out.append((name, el.get_text()))
    return out


def disable_employee(session: requests.Session, emp_id: int) -> None:
    print(f"\n[step 7] CLEANUP — disable employee {emp_id}")
    r = session.get(f"{BASE_URL}/employee/edit/{emp_id}")
    payload = parse_edit_form_for_update(r.text, drop_fields={"employee[isActive]"})
    r_post = session.post(f"{BASE_URL}/employee/update", data=payload, allow_redirects=False)
    print(f"  HTTP {r_post.status_code}, Location: {r_post.headers.get('Location', '(none)')}")
    if r_post.headers.get("Location") == "/employee":
        print("  [SUCCESS] employee disabled")
    else:
        print("  [WARN] unexpected response")


def main() -> int:
    print("=" * 66)
    print("WRITE 1''''+4+5: create active employee + linked BO user + BO perms")
    print("=" * 66)

    session = login_and_session()
    preflight(session)
    emp_id = create_employee(session)
    (FIXTURES_PAYLOADS / "w45f_employee_id.txt").write_text(str(emp_id))

    try:
        user_id = create_bo_user(session, emp_id)
        (FIXTURES_PAYLOADS / "w45f_bo_user_id.txt").write_text(str(user_id))
        html = fetch_bo_permissions_page(session, user_id)
        assign_bo_permissions(session, user_id, html)
        verify_bo_user(session)
    finally:
        # Cleanup: disable the employee even if BO user flow failed
        disable_employee(session, emp_id)

    return 0


if __name__ == "__main__":
    sys.exit(main())
