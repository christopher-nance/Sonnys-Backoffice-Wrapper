"""Probe whether /employee supports a server-side search query param."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import Route, sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_HTML = REPO_ROOT / "tests" / "fixtures" / "html"


def main() -> int:
    password = os.environ.get("SONNYS_BOT_PASSWORD")
    if not password:
        print("ERROR: SONNYS_BOT_PASSWORD required")
        return 2

    base_url = "https://washu.sonnyscontrols.com"

    def route_handler(route: Route) -> None:
        req = route.request
        if req.method.upper() in ("POST", "PUT", "DELETE", "PATCH"):
            if "login_check" in req.url:
                route.continue_()
            else:
                print(f"  [BLOCKED] {req.method} {req.url}")
                route.abort()
        else:
            route.continue_()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="SonnysBackofficeWrapper/0.1-exploration")
        page = context.new_page()
        page.route("**/*", route_handler)

        # Login
        page.goto(f"{base_url}/login")
        page.fill("input[name='_username']", "SonnysWrapperTestAccount")
        page.fill("input[name='_password']", password)
        page.click("button[type='submit'], input[type='submit']")
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)

        # Grab a baseline total row count from /employee with no query
        page.goto(f"{base_url}/employee", wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        baseline = page.content()
        base_rows = baseline.count('<tr')
        print(f'[baseline] /employee has approx {base_rows} <tr tags')

        # Known: employee "aaliyah roylance" with pos_user_id=7217 exists per list
        # Test various query-param patterns
        probes = [
            ("search", "aaliyah"),
            ("search", "7217"),
            ("q", "aaliyah"),
            ("filter", "aaliyah"),
            ("name", "aaliyah"),
            ("posLoginId", "7217"),
        ]
        for param, value in probes:
            url = f"{base_url}/employee?{param}={value}"
            print(f"\n[probe] GET {url}")
            try:
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(500)
                html = page.content()
                row_count = html.count('<tr')
                # Look for expected value in the response
                has_aaliyah = "aaliyah" in html.lower()
                has_7217 = "7217" in html
                print(f"  rows~={row_count}  aaliyah={has_aaliyah}  7217={has_7217}")
                # Save for each first parameter type
                out = FIXTURES_HTML / f"employee_search_{param}_{value}.html"
                out.write_text(html, encoding="utf-8")
                print(f"  -> {out.relative_to(REPO_ROOT)}")
            except Exception as exc:
                print(f"  [ERROR] {exc}")

        # Also try clicking any search input on the list page if one exists
        print("\n[probe] looking for search input on /employee page...")
        page.goto(f"{base_url}/employee", wait_until="domcontentloaded")
        inputs = page.locator("input[type='search'], input[placeholder*='earch'], input[name*='earch']")
        cnt = inputs.count()
        print(f"  found {cnt} search-like inputs on /employee")
        if cnt > 0:
            for i in range(cnt):
                el = inputs.nth(i)
                attrs = el.evaluate("el => ({name: el.name, id: el.id, placeholder: el.placeholder, type: el.type})")
                print(f"  input[{i}] {attrs}")

        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
