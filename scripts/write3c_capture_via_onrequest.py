"""WRITE 3c: Retry capturing the /employee/update POST using page.on('request').

Strategy: use the same approach that worked in Write 2b (capturing the
permissions POST). Open /employee/edit/485, click save (even though
nothing changed), and capture the POST that goes out.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import parse_qsl

from playwright.sync_api import Request, sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_PAYLOADS = REPO_ROOT / "tests" / "fixtures" / "payloads"

BASE_URL = "https://washu.sonnyscontrols.com"
USERNAME = "SonnysWrapperTestAccount"
EMPLOYEE_ID = 485


def main() -> int:
    password = os.environ.get("SONNYS_BOT_PASSWORD")
    if not password:
        raise SystemExit("ERROR: SONNYS_BOT_PASSWORD required")

    captured: list[dict] = []

    def on_request(req: Request) -> None:
        if req.method.upper() == "POST" and "/employee/update" in req.url:
            captured.append(
                {
                    "method": req.method,
                    "url": req.url,
                    "post_data": req.post_data,
                    "headers": {k: v for k, v in req.headers.items() if k.lower() not in ("cookie",)},
                }
            )
            print(f"  [CAPTURED] {req.method} {req.url} ({len(req.post_data or '')} bytes)")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent="SonnysBackofficeWrapper/0.1-write3c")
        page = ctx.new_page()
        page.on("request", on_request)

        # Login
        page.goto(f"{BASE_URL}/login")
        page.fill("input[name='_username']", USERNAME)
        page.fill("input[name='_password']", password)
        page.click("button[type='submit'], input[type='submit']")
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)

        # Go to edit page and save (re-emits POST even if nothing changed)
        print(f"[nav] /employee/edit/{EMPLOYEE_ID}")
        page.goto(f"{BASE_URL}/employee/edit/{EMPLOYEE_ID}", wait_until="domcontentloaded")
        page.wait_for_timeout(1500)

        print("[save] clicking submit")
        try:
            with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                page.click(
                    "form[action='/employee/update'] button[type='submit']"
                )
            print(f"  landed: {page.url}")
        except Exception as exc:
            print(f"  [warn] {exc}")
        page.wait_for_timeout(1000)
        browser.close()

    if not captured:
        print("\n[ERROR] no POST captured")
        return 1

    out = FIXTURES_PAYLOADS / "allowed_employee_update_browser_full.json"
    out.write_text(json.dumps(captured, indent=2), encoding="utf-8")
    print(f"\n[saved] {out.relative_to(REPO_ROOT)}")

    post_data = captured[0]["post_data"] or ""
    pairs = parse_qsl(post_data, keep_blank_values=True)
    print(f"\n{len(pairs)} fields in captured browser POST")
    print("\nfirst 20 field names:")
    for k, v in pairs[:20]:
        print(f"  {k} = {v!r}")

    # Diff against write3 parsed payload
    write3_path = FIXTURES_PAYLOADS / "allowed_employee_update_full_disable_request.json"
    if write3_path.exists():
        write3 = json.loads(write3_path.read_text())
        write3_pairs = [(f["name"], f["value"]) for f in write3["fields"]]
        write3_keys = {k for k, _ in write3_pairs}
        browser_keys = {k for k, _ in pairs}
        print(f"\n=== DIFF ===")
        print(f"write3 keys: {len(write3_keys)}")
        print(f"browser keys: {len(browser_keys)}")
        missing_from_write3 = browser_keys - write3_keys
        extra_in_write3 = write3_keys - browser_keys
        print(f"\nMISSING from write3 (browser has, write3 doesn't) — {len(missing_from_write3)}:")
        for k in sorted(missing_from_write3):
            vals = [v for kk, v in pairs if kk == k]
            print(f"  + {k} = {vals}")
        print(f"\nEXTRA in write3 (write3 has, browser doesn't) — {len(extra_in_write3)}:")
        for k in sorted(extra_in_write3):
            vals = [v for kk, v in write3_pairs if kk == k]
            print(f"  - {k} = {vals}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
