"""WRITE 3b: Capture the exact browser POST for disabling an employee.

Uses Playwright route interception (reliable, unlike page.on('request'))
to capture the body of the POST /employee/update when the user clicks
the isActive toggle off and saves.

Compares the captured browser payload with the parsed-and-reposted
payload from Write 3 to find what's missing.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import parse_qsl

from playwright.sync_api import Route, sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_HTML = REPO_ROOT / "tests" / "fixtures" / "html"
FIXTURES_PAYLOADS = REPO_ROOT / "tests" / "fixtures" / "payloads"

BASE_URL = "https://washu.sonnyscontrols.com"
USERNAME = "SonnysWrapperTestAccount"
EMPLOYEE_ID = 485


def main() -> int:
    password = os.environ.get("SONNYS_BOT_PASSWORD")
    if not password:
        raise SystemExit("ERROR: SONNYS_BOT_PASSWORD required")

    captured: list[dict] = []

    def route_handler(route: Route) -> None:
        req = route.request
        method = req.method.upper()
        if method == "POST" and req.url.endswith("/employee/update"):
            captured.append(
                {
                    "method": method,
                    "url": req.url,
                    "post_data": req.post_data,
                    "headers": dict(req.headers),
                }
            )
            print(f"  [CAPTURED] POST {req.url} ({len(req.post_data or '')} bytes)")
            route.continue_()
            return
        if method in ("POST", "PUT", "DELETE", "PATCH") and "login_check" not in req.url:
            print(f"  [BLOCKED] {method} {req.url}")
            route.abort()
            return
        route.continue_()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent="SonnysBackofficeWrapper/0.1-write3b")
        page = ctx.new_page()
        page.route("**/*", route_handler)

        # Login
        page.goto(f"{BASE_URL}/login")
        page.fill("input[name='_username']", USERNAME)
        page.fill("input[name='_password']", password)
        page.click("button[type='submit'], input[type='submit']")
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        print(f"[login] ok")

        # Navigate to edit
        print(f"[nav] /employee/edit/{EMPLOYEE_ID}")
        page.goto(f"{BASE_URL}/employee/edit/{EMPLOYEE_ID}", wait_until="domcontentloaded")
        page.wait_for_timeout(1500)

        # Click the isActive toggle off via JS (reliable for bootstrap-toggle)
        print("[toggle] clicking isActive off")
        page.evaluate(
            """() => {
                const cb = document.querySelector('input[name="employee[isActive]"]');
                if (!cb.checked) return;
                const wrapper = cb.closest('.toggle');
                if (wrapper) wrapper.click();
                else cb.click();
            }"""
        )
        page.wait_for_timeout(500)
        checked = page.evaluate(
            "() => document.querySelector('input[name=\\'employee[isActive]\\']').checked"
        )
        print(f"  isActive checkbox state: {checked}")

        # Click save
        print("[save] submitting form")
        try:
            with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                page.click(
                    "form[action='/employee/update'] button[type='submit'], "
                    "form[action='/employee/update'] input[type='submit']"
                )
            print(f"  landed on: {page.url}")
        except Exception as exc:
            print(f"  [warn] nav wait failed: {exc}")
        page.wait_for_timeout(1000)

        if not captured:
            print("\n[ERROR] no /employee/update POST captured")
            browser.close()
            return 1

        out = FIXTURES_PAYLOADS / "allowed_employee_update_browser_disable.json"
        out.write_text(json.dumps(captured, indent=2), encoding="utf-8")
        print(f"\n[saved] {out.relative_to(REPO_ROOT)}")

        browser.close()

    # Analyze captured vs write3's parsed payload
    print("\n" + "=" * 60)
    print("DIFF vs Write 3's pure-requests parse")
    print("=" * 60)

    browser_payload = captured[0]["post_data"] or ""
    browser_pairs = parse_qsl(browser_payload, keep_blank_values=True)
    browser_keys = set(k for k, _ in browser_pairs)
    print(f"\nbrowser POST: {len(browser_pairs)} fields, {len(browser_keys)} unique keys")

    write3_path = FIXTURES_PAYLOADS / "allowed_employee_update_full_disable_request.json"
    if write3_path.exists():
        write3_data = json.loads(write3_path.read_text())
        write3_pairs = [(f["name"], f["value"]) for f in write3_data["fields"]]
        write3_keys = set(k for k, _ in write3_pairs)
        print(f"write3 POST:  {len(write3_pairs)} fields, {len(write3_keys)} unique keys")

        missing_from_write3 = browser_keys - write3_keys
        extra_in_write3 = write3_keys - browser_keys
        print(f"\nkeys in browser but NOT in write3 ({len(missing_from_write3)}):")
        for k in sorted(missing_from_write3)[:30]:
            # Show what value browser sent
            vals = [v for kk, v in browser_pairs if kk == k]
            print(f"  + {k} = {vals}")
        print(f"\nkeys in write3 but NOT in browser ({len(extra_in_write3)}):")
        for k in sorted(extra_in_write3)[:30]:
            print(f"  - {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
