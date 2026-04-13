"""One-off: capture the employee permissions page for an existing employee (GET only).

Usage:
    SONNYS_BOT_PASSWORD='...' python scripts/capture_permissions.py --employee-id 54
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from playwright.sync_api import Route, sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_HTML = REPO_ROOT / "tests" / "fixtures" / "html"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subdomain", default="washu")
    parser.add_argument("--username", default="SonnysWrapperTestAccount")
    parser.add_argument("--employee-id", type=int, required=True)
    args = parser.parse_args()

    password = os.environ.get("SONNYS_BOT_PASSWORD")
    if not password:
        print("ERROR: SONNYS_BOT_PASSWORD required")
        return 2

    base_url = f"https://{args.subdomain}.sonnyscontrols.com"

    def route_handler(route: Route) -> None:
        req = route.request
        if req.method.upper() in ("POST", "PUT", "DELETE", "PATCH"):
            if "login_check" in req.url:
                route.continue_()  # allow login
            else:
                print(f"  [BLOCKED] {req.method} {req.url}")
                route.abort()
        else:
            route.continue_()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent="SonnysBackofficeWrapper/0.1-exploration",
        )
        page = context.new_page()
        page.route("**/*", route_handler)

        # Login
        page.goto(f"{base_url}/login")
        page.fill("input[name='_username']", args.username)
        page.fill("input[name='_password']", password)
        page.click("button[type='submit'], input[type='submit']")
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)

        # Capture permissions page
        target = f"{base_url}/employee/permissions/{args.employee_id}"
        print(f"[capture] GET {target}")
        page.goto(target, wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        out = FIXTURES_HTML / f"employee_permissions_{args.employee_id}.html"
        out.write_text(page.content(), encoding="utf-8")
        print(f"  -> {out.relative_to(REPO_ROOT)}  ({len(page.content())} bytes)")

        # Also capture /employee/edit/<id> to see the disable control
        target2 = f"{base_url}/employee/edit/{args.employee_id}"
        print(f"[capture] GET {target2}")
        page.goto(target2, wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        out2 = FIXTURES_HTML / f"employee_edit_{args.employee_id}.html"
        out2.write_text(page.content(), encoding="utf-8")
        print(f"  -> {out2.relative_to(REPO_ROOT)}  ({len(page.content())} bytes)")

        # And the compensation page
        target3 = f"{base_url}/employee/compensation/{args.employee_id}"
        print(f"[capture] GET {target3}")
        page.goto(target3, wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        out3 = FIXTURES_HTML / f"employee_compensation_{args.employee_id}.html"
        out3.write_text(page.content(), encoding="utf-8")
        print(f"  -> {out3.relative_to(REPO_ROOT)}  ({len(page.content())} bytes)")

        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
