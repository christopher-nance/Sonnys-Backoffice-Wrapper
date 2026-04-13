"""WRITE 4+5 v2: Complete BO user happy path with corrected permissions structure.

Uses the correct BO permissions form structure discovered in exploration:
- field name is 'template' (not 'templateId')
- data-permissions-set on template options carries TOKEN STRINGS (not numeric ids)
- perms[N][token] + perms[N][isEnabled] are the permission matrix

Flow:
1. Pre-flight uniqueness (J2K7 suffix)
2. POST /employee/insert -> active employee
3. POST /user/insert (linked mode) -> BO user tied to the fresh active employee
4. GET /user/permissions/<bo_user_id> while the linked employee is active
5. Parse 'template' select for template id + token set; parse perms[N][token] schema
6. Build the BO permissions POST payload for General User template
7. POST /user/permissions/update
8. Verify BO user in /user list
9. Disable employee (cleanup). BO user stays (no BO disable function in M1).
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

SUFFIX = "J2K7"
EMP_FIELDS = {
    "first_name": "WrapperExplore",
    "last_name": f"DeleteMe-{SUFFIX}",
    "phone": "5555550005",
    "email": f"wrapper-explore-{SUFFIX}@example.invalid",
    "pos_user_id": "99005",
    "pos_pin": "99995",
    "wage_rate": "1.00",
    "overtime_rate": "1.50",
    "wage_site_id": "17",
    "department_id": "3",
    "start_date": "04/13/2026",
}
BO_USERNAME = f"wrapper{SUFFIX}bo"
BO_PASSWORD = "TestBoUserPW2!"
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
        ctx = browser.new_context(user_agent="SonnysBackofficeWrapper/0.1-w45v2")
        page = ctx.new_page()
        page.goto(f"{BASE_URL}/login")
        page.fill("input[name='_username']", USERNAME_BOT)
        page.fill("input[name='_password']", password)
        page.click("button[type='submit'], input[type='submit']")
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        cookies = {c["name"]: c["value"] for c in ctx.cookies()}
        browser.close()
    s = requests.Session()
    s.headers["User-Agent"] = "SonnysBackofficeWrapper/0.1-w45v2"
    for n, v in cookies.items():
        s.cookies.set(n, v, domain="washu.sonnyscontrols.com")
    return s


def preflight(session: requests.Session) -> None:
    print("\n[step 1] PRE-FLIGHT uniqueness")
    r = session.get(f"{BASE_URL}/employee?limit=10000&active=all")
    soup = BeautifulSoup(r.text, "html.parser")
    tbl = soup.find("table", class_="table-employees-list")
    for row in (tbl.find_all("tr") if tbl else []):
        cells = row.find_all("td")
        if len(cells) < 7:
            continue
        if cells[4].get_text(strip=True) == EMP_FIELDS["pos_user_id"]:
            raise SystemExit(f"[COLLISION] pos {EMP_FIELDS['pos_user_id']}")
        if re.sub(r"\D", "", cells[6].get_text(strip=True)) == EMP_FIELDS["phone"]:
            raise SystemExit(f"[COLLISION] phone {EMP_FIELDS['phone']}")
    r = session.get(f"{BASE_URL}/user/create")
    soup = BeautifulSoup(r.text, "html.parser")
    sel = soup.find("select", attrs={"name": "user[employeeId]"})
    if sel:
        for opt in sel.find_all("option"):
            e = (opt.get("data-email") or "").strip().lower()
            if e == EMP_FIELDS["email"].lower():
                raise SystemExit(f"[COLLISION] email")
    r = session.get(f"{BASE_URL}/user?limit=10000&active=all")
    if BO_USERNAME.lower() in r.text.lower():
        raise SystemExit(f"[COLLISION] username {BO_USERNAME}")
    print("  clean")


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
    r = session.post(f"{BASE_URL}/employee/insert", data=build_create_employee_payload(), allow_redirects=False)
    loc = r.headers.get("Location", "")
    m = re.search(r"/employee/(?:edit|permissions|compensation)/(\d+)", loc)
    if not m:
        raise SystemExit(f"[FAIL] Location={loc}")
    emp_id = int(m.group(1))
    print(f"  employee_id = {emp_id}")
    return emp_id


def create_bo_user(session: requests.Session, linked_emp_id: int) -> int:
    print(f"\n[step 3] POST /user/insert linked to employee {linked_emp_id}")
    payload = [
        ("employee[isOnSiteEmployee]", "1"),
        ("user[employeeId]", str(linked_emp_id)),
        ("employee[email]", EMP_FIELDS["email"]),
        ("user[username]", BO_USERNAME),
        ("user[password]", BO_PASSWORD),
        ("user[confirmPassword]", BO_PASSWORD),
    ]
    save_payload("w45v2_user_insert_request", {
        "method": "POST",
        "url": f"{BASE_URL}/user/insert",
        "fields": [{"name": k, "value": v} for k, v in payload],
    })
    r = session.post(f"{BASE_URL}/user/insert", data=payload, allow_redirects=False)
    save_html("w45v2_user_insert_response", r.text)
    save_payload("w45v2_user_insert_response", {
        "status_code": r.status_code,
        "headers": dict(r.headers),
        "body_length": len(r.text),
    })
    loc = r.headers.get("Location", "")
    print(f"  HTTP {r.status_code}, Location: {loc}")
    m = re.search(r"/user/permissions/(\d+)", loc)
    if not m:
        raise SystemExit(f"[FAIL] could not extract user_id from Location={loc!r}")
    return int(m.group(1))


def parse_bo_permissions_page(html: str) -> dict:
    """Return {'templates': [...], 'perms_schema': [...], 'current': {...}}."""
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", action="/user/permissions/update")
    if form is None:
        form = soup.find("form")
    result = {"templates": [], "perms_schema": [], "current": {}}

    # Template select — field name is 'template', NOT 'templateId'
    sel = soup.find("select", attrs={"name": "template"})
    if sel:
        for opt in sel.find_all("option"):
            val = (opt.get("value") or "").strip()
            if not val:
                continue
            try:
                tid = int(val)
            except ValueError:
                continue
            tokens_raw = (opt.get("data-permissions-set") or "").strip()
            tokens = [t.strip() for t in tokens_raw.split(",") if t.strip()]
            result["templates"].append({
                "id": tid,
                "name": opt.get_text(strip=True),
                "grant_tokens": tokens,
            })

    # Perms schema (tokens in order)
    for inp in soup.find_all("input", attrs={"name": re.compile(r"perms\[\d+\]\[token\]")}):
        m = re.match(r"perms\[(\d+)\]\[token\]", inp.get("name", ""))
        if not m:
            continue
        idx = int(m.group(1))
        token = inp.get("value", "") or ""
        result["perms_schema"].append({"index": idx, "token": token})
    result["perms_schema"].sort(key=lambda p: p["index"])

    # Current site state — reuse from the form
    # siteIds[] hidden for available sites; disabledRegions[]/disabledDistricts[] for disabled regions
    return result


def build_bo_permissions_payload(
    *,
    user_id: int,
    template: dict,
    perms_schema: list[dict],
    existing_html: str,
) -> list[tuple[str, str]]:
    """Build the /user/permissions/update POST body.
    Preserves the existing site state by re-parsing the form."""
    grant_set = set(template["grant_tokens"])
    soup = BeautifulSoup(existing_html, "html.parser")

    payload: list[tuple[str, str]] = [
        ("userId", str(user_id)),
        ("userIsNew", ""),
        ("template", str(template["id"])),
    ]

    # Sites: preserve from form — include only fields that would be submitted by a browser
    # (i.e., non-disabled hidden siteIds, and checked checkboxes, omit isAllRegionsAllowed if unchecked)
    for inp in soup.find_all("input"):
        name = inp.get("name", "")
        if not name:
            continue
        if inp.get("disabled") is not None:
            continue
        t = (inp.get("type") or "text").lower()
        # Only include the site-related non-perms fields
        if name not in (
            "isAllRegionsAllowed",
            "disabledRegions[]",
            "disabledDistricts[]",
            "siteIds[]",
        ) and not name.startswith("isAllSitesAllowedByDistrict[") and not name.startswith("isAllDistrictsAllowedByRegion"):
            continue
        if t == "checkbox":
            if inp.has_attr("checked"):
                payload.append((name, inp.get("value") or "on"))
        elif t == "hidden":
            payload.append((name, inp.get("value") or ""))

    # Perms: emit every entry with token, and isEnabled=1 only if in template's grant set
    for perm in perms_schema:
        idx = perm["index"]
        token = perm["token"]
        payload.append((f"perms[{idx}][token]", token))
        if token in grant_set:
            payload.append((f"perms[{idx}][isEnabled]", "1"))
        # else: omit isEnabled (unchecked)

    return payload


def assign_bo_permissions(session: requests.Session, user_id: int) -> None:
    print(f"\n[step 4] GET /user/permissions/{user_id}")
    r = session.get(f"{BASE_URL}/user/permissions/{user_id}", allow_redirects=False)
    print(f"  HTTP {r.status_code}, Location: {r.headers.get('Location', '(none)')}")
    if r.status_code == 302:
        raise SystemExit("  [FAIL] redirected — user may be in broken state")
    save_html(f"w45v2_user_permissions_page_{user_id}", r.text)

    parsed = parse_bo_permissions_page(r.text)
    print(f"  parsed {len(parsed['templates'])} BO templates, {len(parsed['perms_schema'])} perms")
    for t in parsed["templates"]:
        print(f"    [{t['id']}] {t['name']!r} grants {len(t['grant_tokens'])} tokens")

    target = next((t for t in parsed["templates"] if t["name"].lower() == TARGET_BO_TEMPLATE.lower()), None)
    if target is None:
        raise SystemExit(f"[FAIL] template {TARGET_BO_TEMPLATE!r} not found")
    print(f"  target: id={target['id']} name={target['name']!r} grants={target['grant_tokens']}")

    payload = build_bo_permissions_payload(
        user_id=user_id,
        template=target,
        perms_schema=parsed["perms_schema"],
        existing_html=r.text,
    )
    save_payload("w45v2_user_permissions_request", {
        "method": "POST",
        "url": f"{BASE_URL}/user/permissions/update",
        "fields": [{"name": k, "value": v} for k, v in payload],
    })
    print(f"  posting {len(payload)} fields")

    r_post = session.post(
        f"{BASE_URL}/user/permissions/update",
        data=payload,
        allow_redirects=False,
    )
    save_html("w45v2_user_permissions_response", r_post.text)
    save_payload("w45v2_user_permissions_response", {
        "status_code": r_post.status_code,
        "headers": dict(r_post.headers),
        "body_length": len(r_post.text),
    })
    print(f"  HTTP {r_post.status_code}, Location: {r_post.headers.get('Location', '(none)')}")


def verify_bo_user(session: requests.Session, user_id: int) -> None:
    print(f"\n[step 5] VERIFY BO user {user_id}")
    # Re-fetch the permissions page and count checked perms
    r = session.get(f"{BASE_URL}/user/permissions/{user_id}", allow_redirects=False)
    if r.status_code != 200:
        print(f"  [WARN] re-GET returned {r.status_code}")
        return
    soup = BeautifulSoup(r.text, "html.parser")
    sel = soup.find("select", attrs={"name": "template"})
    selected = sel.find("option", selected=True) if sel else None
    print(f"  current template selected: {selected.get('value') if selected else None!r} ({selected.get_text(strip=True) if selected else ''})")
    checked = [inp for inp in soup.find_all("input", attrs={"name": re.compile(r"perms\[\d+\]\[isEnabled\]")}) if inp.has_attr("checked")]
    print(f"  checked perms: {len(checked)}")


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
    print(f"\n[step 6] cleanup: disable employee {emp_id}")
    r = session.get(f"{BASE_URL}/employee/edit/{emp_id}")
    payload = parse_edit_form_for_update(r.text, drop_fields={"employee[isActive]"})
    r_post = session.post(f"{BASE_URL}/employee/update", data=payload, allow_redirects=False)
    print(f"  HTTP {r_post.status_code}, Location: {r_post.headers.get('Location', '(none)')}")


def main() -> int:
    print("=" * 66)
    print(f"WRITE 4+5 v2: active employee + linked BO user + BO permissions")
    print("=" * 66)
    session = login_and_session()
    preflight(session)
    emp_id = create_employee(session)
    (FIXTURES_PAYLOADS / "w45v2_employee_id.txt").write_text(str(emp_id))
    try:
        user_id = create_bo_user(session, emp_id)
        (FIXTURES_PAYLOADS / "w45v2_bo_user_id.txt").write_text(str(user_id))
        assign_bo_permissions(session, user_id)
        verify_bo_user(session, user_id)
    finally:
        disable_employee(session, emp_id)
    print("\nDONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
