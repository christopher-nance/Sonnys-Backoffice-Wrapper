"""WRITE 4 + 5: Linked BO user creation + permissions template.

Creates one BO user linked to employee 486 (our disposable E5F7 employee)
and assigns them the General User BO template.

Flow:
1. Login, get cookies
2. Pre-flight username uniqueness (GET /user, scan for wrapperE5F7bo)
3. POST /user/insert with linked-mode payload
4. Capture redirect URL (expected /user/permissions/<id>), extract user_id
5. GET the BO permissions page, capture it, parse templates + schema
6. Build full permissions matrix for General User (or first universal template)
7. POST /user/permissions/update
8. Verify BO user appears in /user list with Access set

Safety: the BO user is linked to employee 486 which is already disabled.
The BO user itself will remain on the tenant (no BO disable function in
Milestone 1 scope).
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

LINKED_EMPLOYEE_ID = 486
LINKED_EMPLOYEE_EMAIL = "wrapper-explore-E5F7@example.invalid"
BO_USERNAME = "wrapperE5F7bo"
BO_PASSWORD = "TestBoUserPW1!"
TARGET_TEMPLATE_NAME = "General User"


def save_html(name: str, html: str) -> None:
    (FIXTURES_HTML / f"{name}.html").write_text(html, encoding="utf-8")
    print(f"    [html] tests/fixtures/html/{name}.html")


def save_payload(name: str, data: dict) -> None:
    (FIXTURES_PAYLOADS / f"{name}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"    [payload] tests/fixtures/payloads/{name}.json")


def login_and_session() -> requests.Session:
    password = os.environ.get("SONNYS_BOT_PASSWORD")
    if not password:
        raise SystemExit("ERROR: SONNYS_BOT_PASSWORD required")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent="SonnysBackofficeWrapper/0.1-w45")
        page = ctx.new_page()
        page.goto(f"{BASE_URL}/login")
        page.fill("input[name='_username']", USERNAME_BOT)
        page.fill("input[name='_password']", password)
        page.click("button[type='submit'], input[type='submit']")
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        cookies = {c["name"]: c["value"] for c in ctx.cookies()}
        browser.close()
    s = requests.Session()
    s.headers["User-Agent"] = "SonnysBackofficeWrapper/0.1-w45"
    for n, v in cookies.items():
        s.cookies.set(n, v, domain="washu.sonnyscontrols.com")
    return s


def preflight_username(session: requests.Session) -> None:
    print("\n[step 1] PRE-FLIGHT username uniqueness")
    r = session.get(f"{BASE_URL}/user?limit=10000&active=all")
    r.raise_for_status()
    save_html("w45_user_list_preflight", r.text)
    # Look for the username anywhere in the page
    if BO_USERNAME.lower() in r.text.lower():
        print(f"  [COLLISION] {BO_USERNAME!r} appears in /user listing")
        raise SystemExit(1)
    print(f"  {BO_USERNAME!r}: CLEAR")


def create_bo_user(session: requests.Session) -> int:
    print("\n[step 2] POST /user/insert (linked mode)")
    payload = [
        ("employee[isOnSiteEmployee]", "1"),
        ("user[employeeId]", str(LINKED_EMPLOYEE_ID)),
        ("employee[email]", LINKED_EMPLOYEE_EMAIL),
        ("user[username]", BO_USERNAME),
        ("user[password]", BO_PASSWORD),
        ("user[confirmPassword]", BO_PASSWORD),
    ]
    save_payload(
        "w45_user_insert_request",
        {
            "method": "POST",
            "url": f"{BASE_URL}/user/insert",
            "fields": [{"name": k, "value": v} for k, v in payload],
        },
    )
    r = session.post(f"{BASE_URL}/user/insert", data=payload, allow_redirects=False)
    save_html("w45_user_insert_response", r.text)
    save_payload(
        "w45_user_insert_response",
        {
            "status_code": r.status_code,
            "headers": dict(r.headers),
            "body_length": len(r.text),
        },
    )
    print(f"  HTTP {r.status_code}, Location: {r.headers.get('Location', '(none)')}")
    print(f"  body preview: {r.text[:300]}")

    loc = r.headers.get("Location", "")
    # Try to extract /user/<id> pattern
    m = re.search(r"/user/(?:edit|permissions|show|view)/(\d+)", loc)
    if m:
        user_id = int(m.group(1))
    else:
        # Try /user/permissions/<id>
        m = re.search(r"/user/(\d+)/?", loc)
        if m:
            user_id = int(m.group(1))
        else:
            # Fall through to content scan
            m = re.search(r'name="user\[id\]"\s+value="(\d+)"', r.text)
            if m:
                user_id = int(m.group(1))
            else:
                # Last resort: follow the redirect and see where we land
                if loc:
                    follow = session.get(f"{BASE_URL}{loc}" if loc.startswith("/") else loc)
                    save_html("w45_user_insert_landed", follow.text)
                    print(f"  followed redirect to: {follow.url}")
                    m = re.search(r"/user/(?:edit|permissions|show)/(\d+)", follow.url)
                    if m:
                        user_id = int(m.group(1))
                    else:
                        m = re.search(r'name="user\[id\]"\s+value="(\d+)"', follow.text)
                        if m:
                            user_id = int(m.group(1))
                        else:
                            print("  [FAIL] could not extract user_id from any source")
                            raise SystemExit(1)
                else:
                    print("  [FAIL] no redirect and no user_id extractable")
                    raise SystemExit(1)

    print(f"  [SUCCESS] new user_id = {user_id}")
    return user_id


def fetch_bo_permissions_page(session: requests.Session, user_id: int) -> str:
    """Try a few possible URL patterns to find the BO permissions page."""
    print(f"\n[step 3] GET BO permissions page for user {user_id}")
    candidates = [
        f"/user/permissions/{user_id}",
        f"/user/{user_id}/permissions",
        f"/user/edit/{user_id}",
    ]
    for path in candidates:
        r = session.get(f"{BASE_URL}{path}")
        if r.status_code == 200 and "templateId" in r.text:
            print(f"  found at {path}")
            save_html(f"w45_user_permissions_page_{user_id}", r.text)
            return r.text
        print(f"  {path}: HTTP {r.status_code}, has templateId={('templateId' in r.text)}")
    raise SystemExit("could not find BO permissions page")


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
            grants_raw = (opt.get("data-permissions-set") or "").strip()
            overrides_raw = (opt.get("data-manager-override-permissions-set") or "").strip()
            grants = [int(x) for x in grants_raw.split(",") if x.strip().isdigit()]
            overrides = [int(x) for x in overrides_raw.split(",") if x.strip().isdigit()]
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


def build_permissions_payload(
    *,
    user_id: int,
    template: dict,
    schema: list[dict],
    user_key: str,
) -> list[tuple[str, str]]:
    """user_key is 'userId' or 'employeeId' — TBD from parsing the form."""
    grants = set(template["grants"])
    overrides = set(template["overrides"])
    payload: list[tuple[str, str]] = [
        (user_key, str(user_id)),
        ("templateId", str(template["id"])),
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
    return payload


def detect_user_key_and_action(html: str) -> tuple[str, str]:
    """Return (primary_key_name, form_action_url)."""
    soup = BeautifulSoup(html, "html.parser")
    # The form with a templateId select is the permissions form
    for form in soup.find_all("form"):
        if form.find("select", attrs={"name": "templateId"}):
            action = form.get("action", "/user/permissions/update")
            # Find the id field — could be userId or employeeId
            for inp in form.find_all("input", attrs={"type": "hidden"}):
                n = inp.get("name", "")
                if n in ("userId", "employeeId"):
                    return n, action
            # Fallback: try userId by default
            return "userId", action
    raise RuntimeError("could not find permissions form in HTML")


def assign_bo_permissions(session: requests.Session, user_id: int, html: str) -> None:
    print("\n[step 4] Parse templates + assign permissions")
    templates, schema = parse_templates_and_schema(html)
    print(f"  parsed {len(templates)} BO templates, {len(schema)} permission metadata entries")
    for t in templates:
        print(
            f"    [{t['id']}] {t['name']!r} grants={len(t['grants'])} overrides={len(t['overrides'])}"
        )

    target = next((t for t in templates if t["name"].lower() == TARGET_TEMPLATE_NAME.lower()), None)
    if target is None:
        print(f"  [FAIL] template {TARGET_TEMPLATE_NAME!r} not found in BO template list")
        raise SystemExit(1)
    print(f"  target template: id={target['id']} name={target['name']!r}")

    user_key, form_action = detect_user_key_and_action(html)
    print(f"  form action: {form_action}, primary key: {user_key}")

    payload = build_permissions_payload(
        user_id=user_id, template=target, schema=schema, user_key=user_key
    )
    save_payload(
        "w45_user_permissions_request",
        {
            "method": "POST",
            "url": f"{BASE_URL}{form_action}" if form_action.startswith("/") else form_action,
            "fields": [{"name": k, "value": v} for k, v in payload],
        },
    )

    url = f"{BASE_URL}{form_action}" if form_action.startswith("/") else form_action
    r = session.post(url, data=payload, allow_redirects=False)
    save_html("w45_user_permissions_response", r.text)
    save_payload(
        "w45_user_permissions_response",
        {
            "status_code": r.status_code,
            "headers": dict(r.headers),
            "body_length": len(r.text),
        },
    )
    print(f"  HTTP {r.status_code}, Location: {r.headers.get('Location', '(none)')}")


def verify_bo_user(session: requests.Session, user_id: int) -> None:
    print(f"\n[step 5] VERIFY BO user {user_id} in /user list")
    r = session.get(f"{BASE_URL}/user?limit=10000&active=all")
    save_html("w45_user_list_after", r.text)
    if BO_USERNAME in r.text:
        print(f"  [SUCCESS] {BO_USERNAME!r} appears in /user listing")
    else:
        print(f"  [WARN] {BO_USERNAME!r} not found — may be filtered or in a different view")


def main() -> int:
    print("=" * 66)
    print(f"WRITE 4+5: BO user linked to employee {LINKED_EMPLOYEE_ID}")
    print("=" * 66)
    print(f"  username: {BO_USERNAME}")
    print(f"  linked employee email: {LINKED_EMPLOYEE_EMAIL}")
    print(f"  target template: {TARGET_TEMPLATE_NAME}")

    session = login_and_session()
    preflight_username(session)
    user_id = create_bo_user(session)
    (FIXTURES_PAYLOADS / "w45_bo_user_id.txt").write_text(str(user_id))
    permissions_html = fetch_bo_permissions_page(session, user_id)
    assign_bo_permissions(session, user_id, permissions_html)
    verify_bo_user(session, user_id)

    print("\n" + "=" * 66)
    print(f"WRITE 4+5 DONE: BO user_id = {user_id}")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())
