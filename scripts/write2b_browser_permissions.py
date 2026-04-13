"""WRITE 2b: Drive the permissions page UI for employee 485, select General User template,
save, and capture the real browser-sent POST payload along with any AJAX calls made
when the template is selected.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import Request, Route, sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_HTML = REPO_ROOT / "tests" / "fixtures" / "html"
FIXTURES_PAYLOADS = REPO_ROOT / "tests" / "fixtures" / "payloads"

BASE_URL = "https://washu.sonnyscontrols.com"
USERNAME = "SonnysWrapperTestAccount"
EMPLOYEE_ID = 485
TEMPLATE_ID = "3"  # General User


def main() -> int:
    password = os.environ.get("SONNYS_BOT_PASSWORD")
    if not password:
        raise SystemExit("ERROR: SONNYS_BOT_PASSWORD required")

    all_requests: list[dict] = []
    captured_posts: list[dict] = []

    def on_request(req: Request) -> None:
        # Log everything
        all_requests.append(
            {
                "method": req.method,
                "url": req.url,
                "post_data": req.post_data,
                "headers": {k: v for k, v in req.headers.items() if k.lower() not in ("cookie",)},
            }
        )
        # Special-case: capture POSTs to /employee/permissions/update
        if req.method.upper() == "POST" and "/employee/permissions/update" in req.url:
            captured_posts.append(
                {
                    "method": req.method,
                    "url": req.url,
                    "post_data": req.post_data,
                    "headers": {k: v for k, v in req.headers.items() if k.lower() not in ("cookie",)},
                }
            )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent="SonnysBackofficeWrapper/0.1-write2b")
        page = ctx.new_page()
        page.on("request", on_request)

        # Login
        page.goto(f"{BASE_URL}/login")
        page.fill("input[name='_username']", USERNAME)
        page.fill("input[name='_password']", password)
        page.click("button[type='submit'], input[type='submit']")
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        print(f"[login] ok")

        # Navigate to permissions page
        print(f"[nav] /employee/permissions/{EMPLOYEE_ID}")
        page.goto(f"{BASE_URL}/employee/permissions/{EMPLOYEE_ID}", wait_until="networkidle")
        page.wait_for_timeout(1500)
        before_requests = len(all_requests)

        # Select General User template
        print(f"[select] templateId={TEMPLATE_ID}")
        page.select_option("select[name='templateId']", TEMPLATE_ID)
        page.wait_for_timeout(2000)  # wait for any AJAX triggered by the change
        after_select_requests = len(all_requests)
        print(f"  requests during select: {after_select_requests - before_requests}")
        for req in all_requests[before_requests:after_select_requests]:
            print(f"    {req['method']:<6} {req['url']}")

        # Save the page state after selection (shows what JS applied client-side)
        Path(FIXTURES_HTML / f"employee_permissions_{EMPLOYEE_ID}_after_template_select.html").write_text(
            page.content(), encoding="utf-8"
        )
        # Count how many permissions checkboxes are now checked client-side
        checked_count = page.evaluate(
            """() => {
                return document.querySelectorAll('input[name^="permissions["][name$="[hasGrantAccess]"]:checked').length;
            }"""
        )
        print(f"  permissions checked client-side after template select: {checked_count}")

        # Now submit the form
        print("[submit] clicking save")
        try:
            with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                page.click("form#employee-permission-update-form button[type='submit']")
            print(f"  landed on: {page.url}")
        except Exception as exc:
            print(f"  [warn] navigation wait: {exc}")
        page.wait_for_timeout(1000)

        # Save captured POSTs
        if captured_posts:
            outp = FIXTURES_PAYLOADS / "allowed_employee_permissions_update_browser.json"
            outp.write_text(json.dumps(captured_posts, indent=2), encoding="utf-8")
            print(f"\n[captured] {len(captured_posts)} POST(s) to /employee/permissions/update")
            from urllib.parse import parse_qsl
            for i, cap in enumerate(captured_posts):
                post_data = cap.get("post_data") or ""
                print(f"\n  POST {i+1}: {len(post_data)} bytes")
                pairs = parse_qsl(post_data, keep_blank_values=True)
                print(f"  {len(pairs)} fields")
                # Show the key structure
                templateId_pairs = [p for p in pairs if p[0] == "templateId"]
                employeeId_pairs = [p for p in pairs if p[0] == "employeeId"]
                perm_pairs = [p for p in pairs if p[0].startswith("permissions[")]
                hasApp_pairs = [p for p in pairs if p[0] == "hasActionApprovalAuthority"]
                print(f"    templateId: {templateId_pairs}")
                print(f"    employeeId: {employeeId_pairs}")
                print(f"    hasActionApprovalAuthority: {hasApp_pairs}")
                print(f"    permissions[...]: {len(perm_pairs)} fields")
                # Show first 10 permission fields
                for k, v in perm_pairs[:10]:
                    print(f"      {k} = {v!r}")
        else:
            print("\n[WARN] no POSTs captured — form may have submitted outside the intercepted scope")

        # Verify
        print("\n[verify] GET /employee/permissions/485")
        page.goto(f"{BASE_URL}/employee/permissions/{EMPLOYEE_ID}", wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        selected = page.evaluate(
            "() => document.querySelector('select[name=\\'templateId\\']').value"
        )
        actual_checked = page.evaluate(
            """() => document.querySelectorAll('input[name^="permissions["][name$="[hasGrantAccess]"]:checked').length"""
        )
        print(f"  persisted templateId: {selected!r}")
        print(f"  persisted checked permissions: {actual_checked}")

        # Also check employee list Access column
        print("\n[list check]")
        page.goto(f"{BASE_URL}/employee?posUserId=99002&active=all", wait_until="domcontentloaded")
        page.wait_for_timeout(500)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(page.content(), "html.parser")
        tbl = soup.find("table", class_="table-employees-list")
        if tbl:
            for row in tbl.find_all("tr"):
                cells = row.find_all("td")
                if cells and "99002" in " ".join(c.get_text() for c in cells):
                    access = cells[3].get_text(strip=True) if len(cells) > 3 else "?"
                    print(f"  employee 485 Access column: {access!r}")

        browser.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
