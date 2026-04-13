"""One-time Backoffice exploration script — captures HTML fixtures and form payloads.

Usage:
    SONNYS_BOT_PASSWORD='...' python scripts/explore.py --subdomain washu --username SonnysWrapperTestAccount

Writes fixtures to:
    tests/fixtures/html/<page_name>.html
    tests/fixtures/payloads/<action_name>.json

SAFETY: Intercepts all mutating POST/PUT/DELETE/PATCH requests by default and
aborts them, recording the would-be payload for inspection. To allow a specific
write through, pass --allow-write <tag> (repeatable). Login is always allowed.

Scope tags for --allow-write:
    login                      (always allowed internally)
    employee_insert            create one exploration employee (Task 1.4)
    employee_permissions       submit step-2 permissions for that employee
    user_insert                create one BO user (linked or standalone)
    user_permissions           submit step-2 permissions for that BO user
    employee_disable           disable/terminate the exploration employee
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import Route, sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_HTML = REPO_ROOT / "tests" / "fixtures" / "html"
FIXTURES_PAYLOADS = REPO_ROOT / "tests" / "fixtures" / "payloads"
FIXTURES_HTML.mkdir(parents=True, exist_ok=True)
FIXTURES_PAYLOADS.mkdir(parents=True, exist_ok=True)


def save_html(name: str, html: str) -> Path:
    path = FIXTURES_HTML / f"{name}.html"
    path.write_text(html, encoding="utf-8")
    print(f"  [html] {path.relative_to(REPO_ROOT)}  ({len(html)} bytes)")
    return path


def save_payload(name: str, payload: dict) -> Path:
    path = FIXTURES_PAYLOADS / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"  [payload] {path.relative_to(REPO_ROOT)}")
    return path


def _tag_from_url(url: str, base: str) -> str:
    return url.split(base, 1)[-1].lstrip("/").split("?", 1)[0].replace("/", "_") or "root"


def _build_route_handler(base_url: str, allow_writes: set[str]) -> callable:
    counter = {"blocked": 0, "allowed_writes": 0}

    def handler(route: Route) -> None:
        req = route.request
        method = req.method.upper()
        if method in ("POST", "PUT", "DELETE", "PATCH"):
            tag = _tag_from_url(req.url, base_url)
            is_login = "login" in tag
            is_allowed = is_login or any(a in tag for a in allow_writes)
            if is_allowed:
                counter["allowed_writes"] += 1
                # Record the allowed write too for fixture use
                save_payload(
                    f"allowed_{tag}",
                    {
                        "method": method,
                        "url": req.url,
                        "post_data": req.post_data,
                        "headers": dict(req.headers),
                    },
                )
                print(f"  [WRITE-ALLOWED] {method} {req.url}  (tag={tag})")
                route.continue_()
            else:
                counter["blocked"] += 1
                save_payload(
                    f"blocked_{tag}_{counter['blocked']:02d}",
                    {
                        "method": method,
                        "url": req.url,
                        "post_data": req.post_data,
                        "headers": dict(req.headers),
                    },
                )
                print(f"  [WRITE-BLOCKED] {method} {req.url}  (tag={tag})")
                route.abort()
        else:
            route.continue_()

    return handler


def _capture_read_only_pages(page, base_url: str) -> None:
    """Navigate to key pages and save their HTML."""
    pages = [
        ("home", "/"),
        ("employee_list", "/employee"),
        ("employee_create", "/employee/create"),
        ("user_list", "/user"),
        ("user_create", "/user/create"),
    ]
    for name, path in pages:
        print(f"[capture] GET {path}")
        try:
            page.goto(f"{base_url}{path}", wait_until="domcontentloaded")
            # Give JS toggles a moment to initialize
            page.wait_for_timeout(500)
            save_html(name, page.content())
        except Exception as exc:
            print(f"  [ERROR] failed to capture {path}: {exc}")


def _capture_user_create_modes(page, base_url: str) -> None:
    """Capture both linked and standalone modes of /user/create."""
    print("[capture] /user/create — linked mode (default)")
    page.goto(f"{base_url}/user/create", wait_until="domcontentloaded")
    page.wait_for_timeout(500)
    save_html("user_create_linked", page.content())

    print("[capture] /user/create — standalone mode (toggle off)")
    # Toggle "Is this user an Employee of the Wash?" off
    try:
        # The toggle is a Bootstrap toggle — click the label for the input
        label = page.locator("label[for='employee-of-the-wash-toggle']")
        if label.count() > 0:
            label.first.click()
            page.wait_for_timeout(500)
        else:
            # Fallback: click the label wrapper or the toggle div
            page.locator(".toggle[data-toggle='toggle']").first.click()
            page.wait_for_timeout(500)
        save_html("user_create_standalone", page.content())
    except Exception as exc:
        print(f"  [WARN] could not toggle to standalone mode: {exc}")


def login(page, base_url: str, username: str, password: str) -> bool:
    """Navigate to /login, save the page, submit credentials. Returns True on success."""
    print(f"[auth] navigating to {base_url}/login")
    page.goto(f"{base_url}/login", wait_until="domcontentloaded")
    save_html("login_page", page.content())

    # Find username and password inputs — generic selectors
    username_input = page.locator(
        "input[name='username'], input[type='text'][name*='user'], input#username"
    ).first
    password_input = page.locator("input[name='password'], input[type='password']").first

    username_input.fill(username)
    password_input.fill(password)

    # Submit — try common patterns
    submit = page.locator(
        "button[type='submit'], input[type='submit'], button:has-text('Log')"
    ).first
    print("[auth] submitting credentials")
    submit.click()
    # Wait for navigation away from /login
    import contextlib

    with contextlib.suppress(Exception):
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
    page.wait_for_timeout(1000)

    if "/login" in page.url:
        print(f"  [FAIL] still on {page.url} after submit")
        save_html("login_after_fail", page.content())
        return False

    print(f"  [OK] landed on {page.url}")
    save_html("post_login_landing", page.content())
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Explore Sonny's Backoffice")
    parser.add_argument("--subdomain", required=True, help="e.g. washu")
    parser.add_argument("--username", required=True)
    parser.add_argument(
        "--allow-write",
        action="append",
        default=[],
        help="Allow specific write tags through the safety filter (repeatable)",
    )
    parser.add_argument("--headed", action="store_true", help="Show the browser window")
    parser.add_argument(
        "--skip-user-create", action="store_true", help="Skip /user/create captures"
    )
    args = parser.parse_args()

    password = os.environ.get("SONNYS_BOT_PASSWORD")
    if not password:
        print("ERROR: SONNYS_BOT_PASSWORD environment variable is required")
        return 2

    base_url = f"https://{args.subdomain}.sonnyscontrols.com"
    allow_writes = set(args.allow_write)

    print(f"[explore] tenant: {base_url}")
    print(f"[explore] user:   {args.username}")
    print(f"[explore] allow-write tags: {sorted(allow_writes) or '(read-only)'}")
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent="SonnysBackofficeWrapper/0.1-exploration",
        )
        page = context.new_page()
        page.route("**/*", _build_route_handler(base_url, allow_writes))

        started = time.time()
        if not login(page, base_url, args.username, password):
            print("\n[explore] login failed — aborting")
            browser.close()
            return 1

        _capture_read_only_pages(page, base_url)
        if not args.skip_user_create:
            _capture_user_create_modes(page, base_url)

        elapsed = time.time() - started
        print(f"\n[explore] done in {elapsed:.1f}s")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
