"""Write E2E: full create -> permissions -> disable happy path.

One fresh disposable employee (suffix E5F7), one script, one result:
1. Pre-flight uniqueness via /employee?limit=10000&active=all + /user/create
2. POST /employee/insert with corrected site-availability payload
3. Verify sites 17/18/19 are set via /employee/edit/<id>
4. GET /employee/permissions/<id>, parse templates + permission schema
5. Build full permissions matrix for General User template (template 3)
6. POST /employee/permissions/update
7. Verify Access = "General User" in the employee list
8. GET /employee/edit/<id>, parse via fixed parser (data-value fallback +
   skip sites[N][isAvailable]), POST /employee/update with isActive omitted
9. Verify disabled

All captured fixtures land in tests/fixtures/ for unit-test replay in Phase 5+.
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

SUFFIX = "E5F7"
FIELDS = {
    "first_name": "WrapperExplore",
    "last_name": f"DeleteMe-{SUFFIX}",
    "phone": "5555550003",
    "email": f"wrapper-explore-{SUFFIX}@example.invalid",
    "pos_user_id": "99003",
    "pos_pin": "99997",
    "wage_rate": "1.00",
    "overtime_rate": "1.50",
    "wage_site_id": "17",
    "department_id": "3",
    "start_date": "04/13/2026",
}

ENABLED_SITE_IDS = {17, 18, 19}
ALL_SITE_IDS = {1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20}
ALL_REGION_IDS = {1, 2}
ENABLED_REGION_IDS = {1}
ALL_DISTRICT_IDS = {1, 2}
ENABLED_DISTRICT_IDS = {1}

TARGET_TEMPLATE_NAME = "General User"  # template id 3, grants perm 22

_SKIP_UPDATE_PATTERNS = [
    re.compile(r"^employee\[sites\]\[\d+\]\[isAvailable\]$"),
]


# ---------- shared helpers ----------


def login_and_session() -> requests.Session:
    password = os.environ.get("SONNYS_BOT_PASSWORD")
    if not password:
        raise SystemExit("ERROR: SONNYS_BOT_PASSWORD required")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent="SonnysBackofficeWrapper/0.1-e2e")
        page = ctx.new_page()
        page.goto(f"{BASE_URL}/login")
        page.fill("input[name='_username']", USERNAME)
        page.fill("input[name='_password']", password)
        page.click("button[type='submit'], input[type='submit']")
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        cookies = {c["name"]: c["value"] for c in ctx.cookies()}
        browser.close()
    s = requests.Session()
    s.headers["User-Agent"] = "SonnysBackofficeWrapper/0.1-e2e"
    for n, v in cookies.items():
        s.cookies.set(n, v, domain="washu.sonnyscontrols.com")
    return s


def save_html(name: str, html: str) -> None:
    (FIXTURES_HTML / f"{name}.html").write_text(html, encoding="utf-8")
    print(f"    [html] tests/fixtures/html/{name}.html")


def save_payload(name: str, data: dict) -> None:
    (FIXTURES_PAYLOADS / f"{name}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"    [payload] tests/fixtures/payloads/{name}.json")


# ---------- step 1: preflight ----------


def preflight_uniqueness(session: requests.Session) -> None:
    print("\n[step 1] PREFLIGHT uniqueness check")
    target_pos = int(FIELDS["pos_user_id"])
    target_phone = FIELDS["phone"]
    target_email = FIELDS["email"].lower()

    r = session.get(f"{BASE_URL}/employee?limit=10000&active=all")
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    tbl = soup.find("table", class_="table-employees-list")
    rows = [row for row in (tbl.find_all("tr") if tbl else []) if row.find("td")]
    print(f"  {len(rows)} employees in tenant")

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 7:
            continue
        pos_txt = cells[4].get_text(strip=True)
        phone_txt = cells[6].get_text(strip=True)
        phone_digits = re.sub(r"\D", "", phone_txt)
        if pos_txt == str(target_pos):
            print(f"  [COLLISION] pos_user_id {target_pos} already exists")
            raise SystemExit(1)
        if phone_digits == target_phone:
            print(f"  [COLLISION] phone {target_phone} already exists")
            raise SystemExit(1)

    r = session.get(f"{BASE_URL}/user/create")
    soup = BeautifulSoup(r.text, "html.parser")
    sel = soup.find("select", attrs={"name": "user[employeeId]"})
    emails = {
        (opt.get("data-email") or "").strip().lower()
        for opt in (sel.find_all("option") if sel else [])
    }
    emails.discard("")
    if target_email in emails:
        print(f"  [COLLISION] email {target_email} already exists")
        raise SystemExit(1)
    print(f"  all three clean")


# ---------- step 2: create employee ----------


def build_create_payload() -> list[tuple[str, str]]:
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
    print("\n[step 2] CREATE employee via /employee/insert")
    payload = build_create_payload()
    save_payload("e2e_create_employee_request", {
        "method": "POST",
        "url": f"{BASE_URL}/employee/insert",
        "fields": [{"name": k, "value": v} for k, v in payload],
    })
    r = session.post(f"{BASE_URL}/employee/insert", data=payload, allow_redirects=False)
    save_html("e2e_create_employee_response", r.text)
    save_payload("e2e_create_employee_response", {
        "status_code": r.status_code,
        "headers": dict(r.headers),
        "body_length": len(r.text),
    })
    loc = r.headers.get("Location", "")
    print(f"  HTTP {r.status_code}, Location: {loc}")
    m = re.search(r"/employee/(?:edit|permissions|compensation)/(\d+)", loc)
    if not m:
        print(f"  [FAIL] could not extract employee_id")
        raise SystemExit(1)
    emp_id = int(m.group(1))
    print(f"  [SUCCESS] new employee_id = {emp_id}")
    return emp_id


# ---------- step 3: verify sites ----------


def verify_sites(session: requests.Session, emp_id: int) -> None:
    print(f"\n[step 3] VERIFY sites on /employee/edit/{emp_id}")
    r = session.get(f"{BASE_URL}/employee/edit/{emp_id}")
    save_html(f"e2e_employee_edit_{emp_id}_after_create", r.text)
    soup = BeautifulSoup(r.text, "html.parser")
    form = soup.find("form", action=re.compile(r"/employee/update"))
    unchecked_available = []
    checked_not_available = []
    for inp in form.find_all("input", attrs={"name": re.compile(r"employee\[sites\]\[\d+\]\[isAvailable\]")}):
        m = re.search(r"\[sites\]\[(\d+)\]", inp.get("name", ""))
        if not m:
            continue
        sid = int(m.group(1))
        if inp.has_attr("checked"):
            checked_not_available.append(sid)
        else:
            unchecked_available.append(sid)
    print(f"  AVAILABLE: {sorted(unchecked_available)}")
    print(f"  NOT available: {sorted(checked_not_available)}")
    if sorted(unchecked_available) == sorted(ENABLED_SITE_IDS):
        print(f"  [SUCCESS] sites match intent")
    else:
        print(f"  [FAIL] expected {sorted(ENABLED_SITE_IDS)}, got {sorted(unchecked_available)}")
        raise SystemExit(1)


# ---------- step 4: permissions ----------


def parse_templates_and_schema(html: str) -> tuple[list[dict], list[dict]]:
    """Return (templates, schema). Template: {id, name, grants, overrides}.
    Schema entry: {id, label, description}."""
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
            grants_raw = (opt.get("data-permissions-set") or "").strip()
            overrides_raw = (opt.get("data-manager-override-permissions-set") or "").strip()
            grants = [int(x) for x in grants_raw.split(",") if x.strip().isdigit()]
            overrides = [int(x) for x in overrides_raw.split(",") if x.strip().isdigit()]
            templates.append({
                "id": tid,
                "name": opt.get_text(strip=True),
                "grants": grants,
                "overrides": overrides,
            })

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
    schema_list = [schema[k] for k in sorted(schema.keys())]
    return templates, schema_list


def build_permissions_payload(
    *,
    employee_id: int,
    template: dict,
    schema: list[dict],
    has_action_approval_authority: bool = False,
) -> list[tuple[str, str]]:
    grants = set(template["grants"])
    overrides = set(template["overrides"])
    payload: list[tuple[str, str]] = [
        ("employeeId", str(employee_id)),
        ("templateId", str(template["id"])),
        ("hasActionApprovalAuthority", "1" if has_action_approval_authority else "0"),
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
    return payload


def assign_permissions(session: requests.Session, emp_id: int) -> None:
    print(f"\n[step 4] ASSIGN permissions ({TARGET_TEMPLATE_NAME}) to employee {emp_id}")
    r = session.get(f"{BASE_URL}/employee/permissions/{emp_id}")
    save_html(f"e2e_permissions_page_{emp_id}_initial", r.text)
    templates, schema = parse_templates_and_schema(r.text)
    print(f"  parsed {len(templates)} templates, {len(schema)} permission metadata entries")

    target = next((t for t in templates if t["name"].lower() == TARGET_TEMPLATE_NAME.lower()), None)
    if target is None:
        print(f"  [FAIL] template {TARGET_TEMPLATE_NAME!r} not found")
        raise SystemExit(1)
    print(f"  template: id={target['id']} name={target['name']!r} grants={target['grants']} overrides={target['overrides']}")

    payload = build_permissions_payload(
        employee_id=emp_id, template=target, schema=schema
    )
    save_payload("e2e_permissions_request", {
        "method": "POST",
        "url": f"{BASE_URL}/employee/permissions/update",
        "fields": [{"name": k, "value": v} for k, v in payload],
    })
    r_post = session.post(
        f"{BASE_URL}/employee/permissions/update",
        data=payload,
        allow_redirects=False,
    )
    save_html("e2e_permissions_response", r_post.text)
    save_payload("e2e_permissions_response", {
        "status_code": r_post.status_code,
        "headers": dict(r_post.headers),
        "body_length": len(r_post.text),
    })
    print(f"  HTTP {r_post.status_code}, Location: {r_post.headers.get('Location', '(none)')}")


def verify_access(session: requests.Session, emp_id: int) -> None:
    print(f"\n[step 5] VERIFY Access = '{TARGET_TEMPLATE_NAME}' in employee list")
    r = session.get(f"{BASE_URL}/employee?posUserId={FIELDS['pos_user_id']}&active=all")
    soup = BeautifulSoup(r.text, "html.parser")
    tbl = soup.find("table", class_="table-employees-list")
    if tbl:
        for row in tbl.find_all("tr"):
            cells = [c.get_text(strip=True) for c in row.find_all("td")]
            if cells and FIELDS["pos_user_id"] in " ".join(cells):
                access = cells[3] if len(cells) > 3 else "?"
                print(f"  list row Access column: {access!r}")
                if TARGET_TEMPLATE_NAME.lower() in access.lower():
                    print(f"  [SUCCESS] Access shows {TARGET_TEMPLATE_NAME!r}")
                else:
                    print(f"  [FAIL] Access is {access!r}, not {TARGET_TEMPLATE_NAME!r}")
                    raise SystemExit(1)
                return
    print("  [FAIL] employee row not found in list")
    raise SystemExit(1)


# ---------- step 6: disable ----------


def parse_edit_form_for_update(
    html: str,
    *,
    drop_fields: set[str],
) -> list[tuple[str, str]]:
    """Parser with data-value fallback and sites-isAvailable skip."""
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", action=re.compile(r"/employee/update"))
    if form is None:
        raise RuntimeError("could not locate /employee/update form")

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
    print(f"\n[step 6] DISABLE employee {emp_id} via /employee/update (isActive omitted)")
    r = session.get(f"{BASE_URL}/employee/edit/{emp_id}")
    save_html(f"e2e_employee_edit_{emp_id}_before_disable", r.text)
    payload = parse_edit_form_for_update(r.text, drop_fields={"employee[isActive]"})
    print(f"  parsed {len(payload)} fields")
    save_payload("e2e_disable_request", {
        "method": "POST",
        "url": f"{BASE_URL}/employee/update",
        "fields": [{"name": k, "value": v} for k, v in payload],
    })
    r_post = session.post(f"{BASE_URL}/employee/update", data=payload, allow_redirects=False)
    save_html("e2e_disable_response", r_post.text)
    save_payload("e2e_disable_response", {
        "status_code": r_post.status_code,
        "headers": dict(r_post.headers),
        "body_length": len(r_post.text),
    })
    loc = r_post.headers.get("Location", "")
    print(f"  HTTP {r_post.status_code}, Location: {loc}")
    if loc != "/employee":
        print(f"  [WARN] expected Location=/employee, got {loc!r}")


def verify_disabled(session: requests.Session, emp_id: int) -> None:
    print(f"\n[step 7] VERIFY employee {emp_id} is disabled")
    r = session.get(f"{BASE_URL}/employee/edit/{emp_id}")
    save_html(f"e2e_employee_edit_{emp_id}_after_disable", r.text)
    soup = BeautifulSoup(r.text, "html.parser")
    active = soup.find("input", attrs={"name": "employee[isActive]"})
    is_checked = active is not None and active.has_attr("checked")
    # Sample other fields to confirm nothing wiped
    form = soup.find("form", action=re.compile(r"/employee/update"))
    fn = form.find("input", attrs={"name": "employee[firstName]"})
    ln = form.find("input", attrs={"name": "employee[lastName]"})
    pos = form.find("input", attrs={"name": "posCredential[POSLoginID]"})
    print(f"  isActive checked: {is_checked}")
    print(f"  firstName preserved: {fn.get('value') if fn else None!r}")
    print(f"  lastName preserved:  {ln.get('value') if ln else None!r}")
    print(f"  POSLoginID preserved: {pos.get('value') if pos else None!r}")
    if is_checked:
        print("  [FAIL] isActive is still checked")
        raise SystemExit(1)
    if fn and fn.get("value") != FIELDS["first_name"]:
        print("  [FAIL] firstName was wiped or changed")
        raise SystemExit(1)
    print("  [SUCCESS] employee disabled, other fields preserved")


# ---------- main ----------


def main() -> int:
    print("=" * 66)
    print(f"WRITE E2E: full create->permissions->disable flow for suffix {SUFFIX}")
    print("=" * 66)
    for k, v in FIELDS.items():
        print(f"  {k:<20} = {v}")
    print(f"  enabled_sites        = {sorted(ENABLED_SITE_IDS)}")

    session = login_and_session()
    preflight_uniqueness(session)
    emp_id = create_employee(session)
    (FIXTURES_PAYLOADS / "e2e_employee_id.txt").write_text(str(emp_id))
    verify_sites(session, emp_id)
    assign_permissions(session, emp_id)
    verify_access(session, emp_id)
    disable_employee(session, emp_id)
    verify_disabled(session, emp_id)

    print("\n" + "=" * 66)
    print(f"E2E HAPPY PATH SUCCESS: employee {emp_id} created, permissioned, disabled")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())
