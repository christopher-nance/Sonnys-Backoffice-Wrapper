"""Capture the browser's exact POST when saving BO user permissions.

Navigates to an existing BO user's permissions page, selects a template,
clicks save, and intercepts the POST. ABORTS the POST so the user's
actual state is NOT modified.

Uses Amber Booth (2944451) as the reference user since her permissions
page is known to work.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import Request, Route, sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_PAYLOADS = REPO_ROOT / "tests" / "fixtures" / "payloads"

BASE_URL = "https://washu.sonnyscontrols.com"
REFERENCE_USER_ID = 2944451


def main() -> int:
    password = os.environ.get("SONNYS_BOT_PASSWORD")
    if not password:
        raise SystemExit("ERROR: SONNYS_BOT_PASSWORD required")

    captured: list[dict] = []
    other_requests: list[str] = []

    def route_handler(route: Route) -> None:
        req = route.request
        method = req.method.upper()
        if method == "POST" and "/user/permissions/update" in req.url:
            # Capture it AND abort — don't actually modify Amber's state
            captured.append(
                {
                    "method": method,
                    "url": req.url,
                    "post_data": req.post_data,
                    "headers": dict(req.headers),
                }
            )
            print(f"  [CAPTURED+ABORT] {method} {req.url} ({len(req.post_data or '')} bytes)")
            route.abort()
            return
        if method in ("POST", "PUT", "DELETE", "PATCH") and "login_check" not in req.url:
            other_requests.append(f"{method} {req.url}")
            route.abort()
            return
        route.continue_()

    def on_request(req: Request) -> None:
        if req.method.upper() == "POST" and "/user/permissions/update" in req.url:
            captured.append(
                {
                    "method": req.method,
                    "url": req.url,
                    "post_data": req.post_data,
                    "headers": {k: v for k, v in req.headers.items() if k.lower() != "cookie"},
                }
            )
            print(
                f"  [ON_REQUEST_CAPTURED] {req.method} {req.url} ({len(req.post_data or '')} bytes)"
            )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent="SonnysBackofficeWrapper/0.1-bocap")
        page = ctx.new_page()
        page.route("**/*", route_handler)
        page.on("request", on_request)

        # Login
        page.goto(f"{BASE_URL}/login")
        page.fill("input[name='_username']", "SonnysWrapperTestAccount")
        page.fill("input[name='_password']", password)
        page.click("button[type='submit'], input[type='submit']")
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)

        # Navigate to Amber's permissions page
        print(f"[nav] /user/permissions/{REFERENCE_USER_ID}")
        page.goto(f"{BASE_URL}/user/permissions/{REFERENCE_USER_ID}", wait_until="domcontentloaded")
        page.wait_for_timeout(1500)

        # Select a template (General User = 3) — this triggers JS to populate checkboxes
        print("[select] template=3 (General User)")
        page.select_option("select[name='template']", "3")
        page.wait_for_timeout(1000)

        # Click save
        print("[save]")
        try:
            page.click("form[action='/user/permissions/update'] button[type='submit']")
        except Exception as exc:
            print(f"  click: {exc}")
        page.wait_for_timeout(2000)

        browser.close()

    if not captured:
        print("\n[ERROR] no POST captured")
        print(f"other aborted requests: {other_requests[:10]}")
        return 1

    out = FIXTURES_PAYLOADS / "allowed_bo_user_permissions_browser.json"
    out.write_text(json.dumps(captured, indent=2), encoding="utf-8")
    print(f"\n[saved] {out.relative_to(REPO_ROOT)}")

    post_data = captured[0].get("post_data") or ""
    print(f"\n{len(post_data)} bytes")

    from urllib.parse import parse_qsl

    pairs = parse_qsl(post_data, keep_blank_values=True)
    print(f"{len(pairs)} fields")
    print("\nfirst 30 fields (non-perms):")
    non_perms = [p for p in pairs if not p[0].startswith("perms[")]
    for k, v in non_perms[:30]:
        print(f"  {k} = {v!r}")
    perms_pairs = [p for p in pairs if p[0].startswith("perms[")]
    print(f"\nperms[] fields: {len(perms_pairs)}")
    # Show how many isEnabled are set
    enabled = [p for p in perms_pairs if "isEnabled" in p[0]]
    print(f"perms[N][isEnabled] entries: {len(enabled)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
