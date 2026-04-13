"""WRITE 1.5b: Capture the exact payload a real browser sends when disabling employee 484.

Strategy: use Playwright to open /employee/edit/484, click the isActive toggle off,
click save, and intercept the resulting POST to capture its body. Let the POST
through so the disable actually happens.

This bypasses the Symfony checkbox-value guessing game by using the form's own
JavaScript to build the payload.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import Route, sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_HTML = REPO_ROOT / "tests" / "fixtures" / "html"
FIXTURES_PAYLOADS = REPO_ROOT / "tests" / "fixtures" / "payloads"

BASE_URL = "https://washu.sonnyscontrols.com"
USERNAME = "SonnysWrapperTestAccount"
EMPLOYEE_ID = 484


def main() -> int:
    password = os.environ.get("SONNYS_BOT_PASSWORD")
    if not password:
        raise SystemExit("ERROR: SONNYS_BOT_PASSWORD required")

    captured_payloads: list[dict] = []

    def route_handler(route: Route) -> None:
        req = route.request
        method = req.method.upper()
        if method in ("POST", "PUT", "PATCH", "DELETE"):
            if "login_check" in req.url:
                route.continue_()
                return
            if req.url.endswith("/employee/update"):
                # Capture and allow through
                captured_payloads.append(
                    {
                        "method": method,
                        "url": req.url,
                        "post_data": req.post_data,
                        "headers": dict(req.headers),
                    }
                )
                print(f"  [CAPTURED+ALLOW] {method} {req.url}")
                print(f"    post_data length: {len(req.post_data or '')}")
                route.continue_()
                return
            print(f"  [BLOCKED] {method} {req.url}")
            route.abort()
            return
        route.continue_()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent="SonnysBackofficeWrapper/0.1-write1.5b")
        page = ctx.new_page()
        page.route("**/*", route_handler)

        # Login
        page.goto(f"{BASE_URL}/login")
        page.fill("input[name='_username']", USERNAME)
        page.fill("input[name='_password']", password)
        page.click("button[type='submit'], input[type='submit']")
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        print(f"[login] ok, on {page.url}")

        # Navigate to edit page
        print(f"[edit] GET /employee/edit/{EMPLOYEE_ID}")
        page.goto(f"{BASE_URL}/employee/edit/{EMPLOYEE_ID}", wait_until="domcontentloaded")
        page.wait_for_timeout(1500)  # let bootstrap-toggle initialize

        # Find the isActive toggle — the bootstrap-toggle wraps the checkbox in a clickable div
        # The underlying input has name="employee[isActive]"
        print("[click] isActive toggle")
        # Check current state first
        is_checked_before = page.evaluate(
            "() => document.querySelector('input[name=\\'employee[isActive]\\']').checked"
        )
        print(f"  isActive before click: {is_checked_before}")

        # Click the LABEL of the toggle to flip it (bootstrap-toggle responds to clicks on the wrapper)
        # The toggle div is the parent of the checkbox
        try:
            page.evaluate(
                """() => {
                    const cb = document.querySelector('input[name="employee[isActive]"]');
                    const wrapper = cb.closest('.toggle');
                    if (wrapper) wrapper.click();
                    else cb.click();
                }"""
            )
            page.wait_for_timeout(500)
            is_checked_after = page.evaluate(
                "() => document.querySelector('input[name=\\'employee[isActive]\\']').checked"
            )
            print(f"  isActive after click: {is_checked_after}")
        except Exception as exc:
            print(f"  [WARN] click failed: {exc}")

        # Now submit the form
        print("[submit] clicking form save button")
        # Find the save button — look for any type=submit in the form
        try:
            with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                page.click(
                    "form[action='/employee/update'] button[type='submit'], button.btn-success[type='submit']"
                )
            print(f"  landed on: {page.url}")
        except Exception as exc:
            print(f"  [WARN] navigation waited but failed: {exc}")

        page.wait_for_timeout(1000)

        # Save the captured payloads
        if captured_payloads:
            outp = FIXTURES_PAYLOADS / "allowed_employee_update_browser_disable.json"
            outp.write_text(json.dumps(captured_payloads, indent=2), encoding="utf-8")
            print(
                f"\n[capture] saved {len(captured_payloads)} payload(s) -> {outp.relative_to(REPO_ROOT)}"
            )
            # Show a summary of the first one
            first = captured_payloads[0]
            post_data = first.get("post_data") or ""
            print(f"\n  payload length: {len(post_data)} bytes")
            # Parse as form-urlencoded and show keys
            from urllib.parse import parse_qsl

            pairs = parse_qsl(post_data, keep_blank_values=True)
            print(f"  field count: {len(pairs)}")
            # Show isActive presence
            is_active_pairs = [p for p in pairs if p[0] == "employee[isActive]"]
            print(f"  employee[isActive] in payload: {is_active_pairs}")
            # Show first 30 field names
            print("  first 30 field names:")
            for k, v in pairs[:30]:
                print(f"    {k} = {v!r}")
        else:
            print("\n[ERROR] no payloads captured")

        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
