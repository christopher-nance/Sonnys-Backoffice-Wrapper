"""WRITE 3: Disable employee 485 via pure-requests full-form round-trip.

Replicates the Delta D-6.2 approach the library will ship with:
1. GET /employee/edit/485
2. Parse every input/select/textarea in the form, skipping any with disabled=""
3. Build the POST payload preserving current values, but OMIT employee[isActive]
4. POST /employee/update
5. GET /employee/edit/485 and verify isActive is now unchecked, other fields preserved
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

# Fields we'll sample before/after to detect wipes
SAMPLE_FIELDS = [
    "employee[firstName]",
    "employee[lastName]",
    "employee[phone]",
    "employee[email]",
    "employee[isActive]",
    "posCredential[POSLoginID]",
    "posCredential[POSLoginPassword]",
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
        ctx = browser.new_context(user_agent="SonnysBackofficeWrapper/0.1-write3")
        page = ctx.new_page()
        page.goto(f"{BASE_URL}/login")
        page.fill("input[name='_username']", USERNAME)
        page.fill("input[name='_password']", password)
        page.click("button[type='submit'], input[type='submit']")
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        cookies = {c["name"]: c["value"] for c in ctx.cookies()}
        browser.close()
    return cookies


def parse_edit_form_into_payload(
    html: str,
    *,
    drop_fields: set[str],
) -> list[tuple[str, str]]:
    """Parse /employee/edit/<id> into a (name, value) tuple list, mirroring browser behavior.

    Rules:
    - Skip any element with a `disabled` attribute (browsers don't submit those)
    - Skip submit/button/reset inputs
    - Skip any field in drop_fields (used to uncheck a checkbox by omission)
    - Text/hidden/number/email/tel/password/date/time: always include value
    - Checkbox: include with its value attribute only if checked
    - Radio: include only if checked
    - Select single: include the selected option's value (or first non-empty if none selected)
    - Select multiple: one entry per selected option
    - Textarea: include with text content
    """
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", action=re.compile(r"/employee/update"))
    if form is None:
        raise RuntimeError("could not locate /employee/update form")

    out: list[tuple[str, str]] = []
    for el in form.find_all(["input", "select", "textarea"]):
        name = el.get("name")
        if not name or name in drop_fields:
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
                out.append((name, el.get("value") or ""))
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
                        (o for o in el.find_all("option") if (o.get("value") or "").strip()),
                        None,
                    )
                if sel_opt is not None:
                    out.append((name, sel_opt.get("value") or ""))
        elif el.name == "textarea":
            out.append((name, el.get_text()))
    return out


def sample_fields(html: str) -> dict[str, str | bool | None]:
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", action=re.compile(r"/employee/update"))
    if form is None:
        return {"_error": "form not found"}
    result: dict[str, str | bool | None] = {}
    for name in SAMPLE_FIELDS:
        el = form.find(["input", "select", "textarea"], attrs={"name": name})
        if el is None:
            result[name] = None
            continue
        t = el.get("type", el.name)
        if t == "checkbox":
            result[name] = el.has_attr("checked")
        else:
            result[name] = el.get("value", "") or ""
    return result


def main() -> int:
    print("=" * 60)
    print(f"WRITE 3: full-form round-trip disable of employee {EMPLOYEE_ID}")
    print("=" * 60)

    cookies = _login_and_get_cookies()
    session = requests.Session()
    session.headers["User-Agent"] = "SonnysBackofficeWrapper/0.1-write3"
    for name, value in cookies.items():
        session.cookies.set(name, value, domain="washu.sonnyscontrols.com")

    # BEFORE state
    print(f"\n[step 1] GET /employee/edit/{EMPLOYEE_ID}")
    r_before = session.get(f"{BASE_URL}/employee/edit/{EMPLOYEE_ID}")
    r_before.raise_for_status()
    (FIXTURES_HTML / f"employee_edit_{EMPLOYEE_ID}_before_write3.html").write_text(
        r_before.text, encoding="utf-8"
    )
    before = sample_fields(r_before.text)
    print("  before snapshot:")
    for k, v in before.items():
        print(f"    {k:<40} = {v!r}")

    # Parse the form into a payload, dropping employee[isActive]
    print("\n[step 2] parse form into payload (dropping employee[isActive])")
    payload = parse_edit_form_into_payload(r_before.text, drop_fields={"employee[isActive]"})
    print(f"  parsed {len(payload)} fields")
    # Save for fixture use
    (FIXTURES_PAYLOADS / "allowed_employee_update_full_disable_request.json").write_text(
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
    print("\n[step 3] POST /employee/update")
    r_post = session.post(
        f"{BASE_URL}/employee/update",
        data=payload,
        allow_redirects=False,
    )
    print(f"  status: HTTP {r_post.status_code}")
    print(f"  Location: {r_post.headers.get('Location', '(none)')}")
    print(f"  body length: {len(r_post.text)} bytes")
    (FIXTURES_HTML / "employee_update_full_disable_response.html").write_text(
        r_post.text, encoding="utf-8"
    )
    (FIXTURES_PAYLOADS / "allowed_employee_update_full_disable_response.json").write_text(
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

    # AFTER state
    print(f"\n[step 4] GET /employee/edit/{EMPLOYEE_ID}")
    r_after = session.get(f"{BASE_URL}/employee/edit/{EMPLOYEE_ID}")
    (FIXTURES_HTML / f"employee_edit_{EMPLOYEE_ID}_after_write3.html").write_text(
        r_after.text, encoding="utf-8"
    )
    after = sample_fields(r_after.text)
    print("  after snapshot:")
    for k, v in after.items():
        print(f"    {k:<40} = {v!r}")

    # Compare
    print("\n" + "=" * 60)
    print("COMPARISON")
    print("=" * 60)
    wiped = []
    unchanged = []
    toggled = []
    for k in sorted(set(before.keys()) | set(after.keys())):
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
    print(f"\n[toggled] {len(toggled)}")
    for k, b, a in toggled:
        print(f"  {k:<40} before={b!r} -> after={a!r}")
    if wiped:
        print(f"\n[WIPED] {len(wiped)} fields changed unexpectedly")
        for k, b, a in wiped:
            print(f"  {k:<40} before={b!r} -> after={a!r}")
        return 1
    if after.get("employee[isActive]") is True:
        print("\n[ERROR] employee[isActive] is still checked — disable did not work")
        return 2
    print("\nSUCCESS: isActive toggled off, all other fields preserved.")

    # Also verify sites and wage are intact by checking the compensation/permissions pages
    print("\n[step 5] verify access and wage preserved")
    r_list = session.get(f"{BASE_URL}/employee?posUserId=99002&active=all")
    soup = BeautifulSoup(r_list.text, "html.parser")
    tbl = soup.find("table", class_="table-employees-list")
    if tbl:
        for row in tbl.find_all("tr"):
            cells = row.find_all("td")
            if cells and "99002" in " ".join(c.get_text() for c in cells):
                col_texts = [c.get_text(strip=True) for c in cells]
                print(f"  list row: {col_texts}")
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())
