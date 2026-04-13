# Sonny's Backoffice Wrapper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Milestone 1 of `sonnys-backoffice-wrapper` — a pip-installable Python library with `create_employee`, `disable_employee`, and `create_backoffice_user`, plus discovery helpers, tests, and a published MkDocs Material docs site.

**Architecture:** Pure-`requests` HTTP client that drives Sonny's Backoffice HTML forms directly. `SonnysBackofficeClient` is a thin façade over feature modules. `_BackofficeSession` owns auth and transparent re-login (cookie-based, no CSRF). Form builders are deterministic pure functions tested against captured HTML fixtures. Pydantic v2 handles input validation and result typing. Site hierarchy (flat vs regions/districts) is auto-detected from the `/employee/create` page on first use.

**Tech Stack:** Python 3.10+, requests, beautifulsoup4, pydantic 2.x, pytest, ruff, hatchling, mkdocs-material, mkdocstrings, playwright (dev-only for fixture recording).

**Spec:** See `docs/superpowers/specs/2026-04-13-sonnys-backoffice-wrapper-design.md`.

**Phase gate:** Phase 1 (exploration) must complete before any code in Phases 4–8 is written. Form builders depend on fixtures captured in Phase 1.

**⚠ Post-exploration deltas (2026-04-13):** Phase 1 read-only exploration is complete. Fixtures are committed and `tests/fixtures/exploration_notes.md` is authoritative for URLs, form field names, and required fields. Several code examples in Tasks 2.3, 3.1, 4.3, 5.1, 5.2, 5.3, 6.1, 6.2, 7.1 were written before exploration and contain guessed field names that **do not match reality**. See the "Post-Exploration Deltas" appendix at the end of this document for the authoritative replacements. When dispatching subagents for those tasks, pass the delta text alongside the original task text — the delta overrides.

**Durable rules from memory:**
- No writes to Backoffice without explicit per-action approval. Read-only exploration is pre-approved. Any form submission requires a pause-and-confirm.
- Site names are globally unique per tenant — safe as a natural key.
- POS User ID and email are both unique per tenant — either can serve as a lookup key.
- Permission names matched case-insensitively; unknown → warn and fall back to "General User"; POS/BO names must match for linked creation.
- Employee and BO user creation are two-step POST flows.

---

## Phase 0: Project Bootstrap

Sets up the repo skeleton, dependencies, and tooling. No production code yet.

### Task 0.1: Create `pyproject.toml`

**Files:**
- Create: `pyproject.toml`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "sonnys-backoffice-wrapper"
version = "0.1.0"
description = "Programmatic user management for Sonny's Carwash Controls Backoffice via pure HTTP requests"
readme = "README.md"
requires-python = ">=3.10"
license = { file = "LICENSE" }
license-files = ["LICENSE"]
authors = [{ name = "Christopher Nance" }]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: Other/Proprietary License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Typing :: Typed",
]
dependencies = [
    "requests>=2.28,<3",
    "beautifulsoup4>=4.12,<5",
    "pydantic>=2.10,<3",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "ruff>=0.1",
    "playwright>=1.40",
]
docs = [
    "mkdocs-material>=9.5",
    "mkdocstrings[python]>=0.24",
]

[project.urls]
Homepage = "https://github.com/christopher-nance/Sonnys-Backoffice-Wrapper"
Documentation = "https://christopher-nance.github.io/Sonnys-Backoffice-Wrapper/"
Issues = "https://github.com/christopher-nance/Sonnys-Backoffice-Wrapper/issues"

[tool.hatch.build.targets.wheel]
packages = ["src/sonnys_backoffice"]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM"]
ignore = ["E501"]  # line length handled by formatter

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "integration: hits the live Backoffice tenant; requires credentials; skipped by default",
]
addopts = "-m 'not integration'"
```

- [ ] **Step 2: Commit**

```bash
git add pyproject.toml
git commit -m "chore: scaffold pyproject.toml with hatchling + pydantic 2 deps"
```

### Task 0.2: Copy LICENSE and create repo scaffolding

**Files:**
- Create: `LICENSE` (copied from sibling repo)
- Create: `.gitignore`
- Create: `README.md` (stub)
- Create: `src/sonnys_backoffice/__init__.py`
- Create: `src/sonnys_backoffice/py.typed` (empty marker file for PEP 561)
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/integration/__init__.py`

- [ ] **Step 1: Fetch LICENSE from sibling repo**

```bash
gh api repos/christopher-nance/Sonnys-Data-API-Client/contents/LICENSE --jq '.content' | base64 -d > LICENSE
```

Verify: `head -3 LICENSE` should show `# Wash Associates Business Internal Use License 1.0`.

- [ ] **Step 2: Write `.gitignore`**

```
# Python
__pycache__/
*.py[cod]
*.egg-info/
.eggs/
build/
dist/
.pytest_cache/
.ruff_cache/
.coverage
htmlcov/

# Venvs
.venv/
venv/
env/

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db

# MkDocs
site/

# Playwright
.playwright/
test-results/
```

- [ ] **Step 3: Write stub `README.md`**

```markdown
# Sonny's Backoffice Wrapper

Programmatic user management for Sonny's Carwash Controls Backoffice.

Status: **alpha — under active development**. See [docs](https://christopher-nance.github.io/Sonnys-Backoffice-Wrapper/) for usage.

## Install

```bash
pip install git+https://github.com/christopher-nance/Sonnys-Backoffice-Wrapper.git
```

## Quickstart

See the docs site.

## License

Wash Associates Business Internal Use License 1.0 — see [LICENSE](LICENSE).
```

- [ ] **Step 4: Create empty package and test directories**

```bash
mkdir -p src/sonnys_backoffice tests/unit tests/integration tests/fixtures/html tests/fixtures/payloads scripts docs/getting-started docs/guides docs/examples docs/reference
touch src/sonnys_backoffice/__init__.py src/sonnys_backoffice/py.typed tests/__init__.py tests/unit/__init__.py tests/integration/__init__.py
```

- [ ] **Step 5: Write package version into `__init__.py`**

```python
"""Sonny's Backoffice Wrapper — programmatic user management for Sonny's Carwash Controls Backoffice."""

__version__ = "0.1.0"
```

- [ ] **Step 6: Commit**

```bash
git add LICENSE .gitignore README.md src/ tests/
git commit -m "chore: add LICENSE, .gitignore, README stub, and package scaffolding"
```

### Task 0.3: Install dev dependencies and verify the toolchain

**Files:**
- None

- [ ] **Step 1: Create a venv and install in editable mode**

```bash
python -m venv .venv
source .venv/Scripts/activate  # Windows Git Bash; on POSIX use bin/activate
pip install -e ".[dev,docs]"
```

- [ ] **Step 2: Verify pytest runs (no tests yet = 0 collected)**

```bash
pytest
```

Expected: `no tests ran in 0.XXs`. Exit code 5 (no tests collected) is OK here.

- [ ] **Step 3: Verify ruff is happy**

```bash
ruff check .
```

Expected: `All checks passed!`

- [ ] **Step 4: No commit — venv is gitignored.**

---

## Phase 1: Backoffice Exploration (hard gate)

Captures HTML fixtures and recorded form payloads from the live Backoffice test tenant. Produces the raw material every form builder in later phases will be written against. **No production code is written during this phase.**

**Credentials:** `SonnysWrapperTestAccount` / `ThisIsATestAccount123!` on the `washu` tenant.

**Write-safety protocol:** Every step below is either read-only or record-and-cancel. When a step requires an actual form submission (Task 1.4 specifically), pause and request explicit user approval before executing.

### Task 1.1: Install Playwright browsers and bootstrap the exploration script

**Files:**
- Create: `scripts/explore.py`
- Create: `scripts/README.md`

- [ ] **Step 1: Install Playwright browsers**

```bash
playwright install chromium
```

- [ ] **Step 2: Write `scripts/explore.py` skeleton**

```python
"""One-time Backoffice exploration script — captures HTML fixtures and form payloads.

Usage:
    python scripts/explore.py --subdomain washu --username SonnysWrapperTestAccount

Writes fixtures to:
    tests/fixtures/html/<page_name>.html
    tests/fixtures/payloads/<action_name>.json
    tests/fixtures/exploration_notes.md

SAFETY: Intercepts all mutating POST/PUT/DELETE requests by default and aborts them.
To allow a specific write through, pass --allow-write <action_name> on the command line.
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

from playwright.sync_api import Playwright, Route, sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_HTML = REPO_ROOT / "tests" / "fixtures" / "html"
FIXTURES_PAYLOADS = REPO_ROOT / "tests" / "fixtures" / "payloads"
FIXTURES_HTML.mkdir(parents=True, exist_ok=True)
FIXTURES_PAYLOADS.mkdir(parents=True, exist_ok=True)


def save_html(name: str, html: str) -> Path:
    path = FIXTURES_HTML / f"{name}.html"
    path.write_text(html, encoding="utf-8")
    print(f"  ↳ saved HTML: {path.relative_to(REPO_ROOT)}")
    return path


def save_payload(name: str, payload: dict) -> Path:
    path = FIXTURES_PAYLOADS / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"  ↳ saved payload: {path.relative_to(REPO_ROOT)}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Explore Sonny's Backoffice")
    parser.add_argument("--subdomain", required=True, help="e.g. washu")
    parser.add_argument("--username", required=True)
    parser.add_argument(
        "--allow-write",
        action="append",
        default=[],
        help="Allow specific write actions through the safety filter (e.g. --allow-write employee_create_step1)",
    )
    parser.add_argument("--headed", action="store_true", help="Show the browser window")
    args = parser.parse_args()

    password = getpass.getpass(f"Password for {args.username}: ")
    base_url = f"https://{args.subdomain}.sonnyscontrols.com"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        context = browser.new_context()
        page = context.new_page()

        # Install a request interceptor that blocks mutating methods unless allow-listed
        allowed = set(args.allow_write)

        def route_handler(route: Route) -> None:
            req = route.request
            method = req.method.upper()
            if method in ("POST", "PUT", "DELETE", "PATCH"):
                # Derive a tag for this request from the URL path
                tag = req.url.split(base_url, 1)[-1].lstrip("/").replace("/", "_")
                if tag in allowed or any(a in tag for a in allowed):
                    print(f"  ↳ ALLOWING write: {method} {req.url}")
                    route.continue_()
                else:
                    print(f"  ↳ BLOCKING write: {method} {req.url}  (tag={tag})")
                    # Record the payload we would have sent
                    post_data = req.post_data
                    headers = dict(req.headers)
                    save_payload(
                        f"blocked_{tag}",
                        {
                            "method": method,
                            "url": req.url,
                            "post_data": post_data,
                            "headers": headers,
                        },
                    )
                    route.abort()
            else:
                route.continue_()

        page.route("**/*", route_handler)

        # Step 1: login
        print(f"[1] Navigating to {base_url}/login")
        page.goto(f"{base_url}/login")
        save_html("login_page", page.content())
        # Login POST is intentionally allowed — we need a session
        allowed.add("login")  # allow the login POST
        # ... subsequent exploration steps will be added in Task 1.2+ ...

        print("\nDONE. Review tests/fixtures/ for captured data.")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Write `scripts/README.md`**

```markdown
# Exploration Scripts

`explore.py` captures HTML fixtures and recorded form payloads from the live Backoffice test tenant. It is a developer tool, not a runtime dependency.

## Safety

By default the script blocks all POST/PUT/DELETE/PATCH requests and records the intended payload as `tests/fixtures/payloads/blocked_*.json`. To allow a specific write through:

```bash
python scripts/explore.py --subdomain washu --username SonnysWrapperTestAccount --allow-write login
```

Only use `--allow-write` for actions that have been explicitly approved for submission.

## Outputs

- `tests/fixtures/html/<page_name>.html` — raw HTML snapshots
- `tests/fixtures/payloads/<action>.json` — recorded form payloads (sent or blocked)
- `tests/fixtures/exploration_notes.md` — human-readable notes, gotchas, URL patterns
```

- [ ] **Step 4: Commit**

```bash
git add scripts/ tests/fixtures/
git commit -m "chore(explore): add Playwright exploration script skeleton with write-safety filter"
```

### Task 1.2: Capture read-only pages (login, employee list, create forms, permission pages)

**Files:**
- Modify: `scripts/explore.py`

- [ ] **Step 1: Extend `explore.py` to capture read-only pages**

After the login POST in `main()`, add:

```python
        # --- Read-only capture phase ---
        pages_to_capture = [
            ("home", "/"),
            ("employee_list", "/employee"),
            ("employee_create", "/employee/create"),
            ("user_list", "/user"),
            ("user_create", "/user/create"),
        ]
        for name, path in pages_to_capture:
            print(f"[capture] {path}")
            page.goto(f"{base_url}{path}")
            page.wait_for_load_state("networkidle")
            save_html(name, page.content())

        # The "Set Permissions" pages are reached from the create pages.
        # On /employee/create, fill the form with dummy values, then click "Set Permissions"
        # but intercept the resulting navigation without submitting.
        print("[capture] employee_create permissions page (dry run)")
        page.goto(f"{base_url}/employee/create")
        # Fill minimum required fields so the JS validator lets us click Set Permissions.
        # Field names captured from spec — update after this run if they differ.
        page.fill("input[name='employee[firstName]']", "Exploration")
        page.fill("input[name='employee[lastName]']", "Test")
        page.fill("input[name='employee[email]']", "exploration@example.invalid")
        # ... more fields as needed — to be filled in during actual run based on form HTML
        # Clicking Set Permissions triggers a POST we want to BLOCK and record, then we
        # can't navigate to the permissions page without a real record. For this first
        # pass we just capture the pre-submit HTML of the form.
        save_html("employee_create_filled", page.content())

        # Same for /user/create in both modes
        print("[capture] user_create linked mode")
        page.goto(f"{base_url}/user/create")
        save_html("user_create_default", page.content())
        # Toggle "Is this user an Employee of the Wash?" off to capture standalone mode
        page.click("label[for='employee-of-the-wash-toggle']")
        page.wait_for_timeout(500)
        save_html("user_create_standalone", page.content())
```

- [ ] **Step 2: Run exploration (read-only)**

```bash
python scripts/explore.py --subdomain washu --username SonnysWrapperTestAccount
```

Expected: `tests/fixtures/html/` contains `login_page.html`, `home.html`, `employee_list.html`, `employee_create.html`, `employee_create_filled.html`, `user_list.html`, `user_create.html`, `user_create_default.html`, `user_create_standalone.html`. If any page fails to load, the script aborts — diagnose before proceeding.

- [ ] **Step 3: Inspect fixtures**

Open `tests/fixtures/html/login_page.html` and search for `csrf` / `_token` / `authenticity` to locate the CSRF token field name. Open `employee_create.html` and confirm the site/region/district toggle markup matches what we expected from the spec. Record findings in a scratch file — they go into `exploration_notes.md` next.

- [ ] **Step 4: Commit fixtures**

```bash
git add tests/fixtures/html/ scripts/explore.py
git commit -m "chore(fixtures): capture read-only Backoffice pages"
```

### Task 1.3: Write `exploration_notes.md` documenting what was found

**Files:**
- Create: `tests/fixtures/exploration_notes.md`

- [ ] **Step 1: Document every finding from Task 1.2's inspection**

Template:

```markdown
# Exploration Notes

Captured against `washu.sonnyscontrols.com` using `SonnysWrapperTestAccount` on <date>.

## Authentication

- **Login page URL:** `/login`
- **Login form action:** `<fill from login_page.html form[action]>`
- **CSRF token field name:** `<fill — e.g. _token or authenticity_token>`
- **CSRF token source:** `<meta name="csrf-token" content="...">` or hidden `<input>`?
- **Session cookie name:** `<fill — check browser devtools>`
- **Success-redirect target after login:** `<fill — which page does /login/authenticate redirect to?>`
- **Session-expired signal:** `<fill — does an authed GET to /employee return 302→/login, 401, or HTML with a login form?>`

## Employee creation form (`/employee/create`)

- **Step 1 form action:** `<fill from employee_create.html form[action]>`
- **Step 1 method:** POST
- **Required text fields:** (name attributes and any validator hints)
  - `employee[firstName]`
  - `employee[lastName]`
  - `employee[email]`
  - `employee[phone]` (or whatever it's actually called)
  - ...
- **POS credentials fields:** `<fill>`
- **Wage rate field:** `<fill>`
- **Overtime rate field:** `<fill>`
- **Start date field:** `<fill — format?>`
- **Departments field:** `<fill — multi-select name, option values, how "Greeter" is represented>`
- **Emergency contact fields:** `<fill>`

## Site hierarchy markup (captured from `employee_create.html` on WashU — hierarchical tenant)

- **All-regions toggle:** `employee[isAllRegionsAllowed]` (from spec; confirm)
- **Per-region disable:** `employee[disabledRegions][]`
- **Per-district disable:** `employee[disabledDistricts][]`
- **Per-region "all districts" toggle:** `employee[isAllDistrictsAllowedByRegion][]`
- **Per-district "all sites" toggle:** `employee[isAllSitesAllowedByDistrict][<district_id>]`
- **Per-site availability:** `employee[sites][<site_id>][isAvailable]` + hidden `employee[sites][<site_id>][siteId]`
- **Site name extraction:** Site names appear inside `<label>` elements as `Site <strong>(Name)</strong>`. Confirm and document the exact selector.

**Flat-tenant markup** (from a non-region fixture — if we captured one, reference it):
- **All-sites toggle:** `employee[isAllSitesAllowed]`
- **Per-site checkbox:** `employee[siteIds][]` with `value="<site_id>"` and label `<strong>(Name)</strong>`

## POS Permissions page (step 2 of employee creation)

- **URL pattern:** `<fill — e.g. /employee/<id>/permissions or /employee/permissions/set?id=X>`
- **Permission field name:** `<fill — single select? radio group? checkbox?>`
- **Submit URL:** `<fill>`
- **Available roles on this tenant:** `<fill — list of names>`

## Backoffice user creation (`/user/create`)

- **Form action:** `/user/insert` (confirmed from spec)
- **Linked mode toggle:** `employee[isOnSiteEmployee]` = 1 (yes) or 0 (no)
- **Linked mode selector:** `user[employeeId]` (select with employee options)
- **Standalone mode fields:** `employee[firstName]`, `employee[lastName]`, `employee[email]`, `user[username]`, `user[password]`, `user[confirmPassword]`
- **Username pattern:** `[A-Za-z][\w]{2,63}` (from HTML pattern attribute)

## BO Permissions page (step 2 of BO user creation)

- **URL pattern:** `<fill>`
- **Field names:** `<fill — confirm they match the POS permissions page field names for the "POS/BO permission name must match" rule to hold>`

## Employee list (`/employee`)

- **Row structure:** `<fill — does each row have a data attribute with employee_id?>`
- **Search/filter query params:** `<fill — can we filter by email or pos_user_id via ?search=... or similar?>`
- **Pagination:** `<fill — query param for page, total count indicator>`

## Disable employee

- **URL:** `<fill — found where? edit page toggle? separate endpoint?>`
- **Method + payload:** `<fill>`

## Session expiration

- **After the session cookie is cleared, what does a GET to `/employee` return?** `<fill>`
- **Detection strategy for re-auth:** `<fill based on above>`

## Gotchas

- `<any weirdness encountered>`
```

- [ ] **Step 2: Fill in every `<fill>` by inspecting the captured HTML**

For each placeholder, open the relevant fixture, find the answer, replace the placeholder. If any answer is genuinely unknown after inspection, note it as "requires write to confirm" and defer to Task 1.4.

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/exploration_notes.md
git commit -m "docs(fixtures): document read-only exploration findings"
```

### Task 1.4: Capture actual create POSTs (APPROVAL GATE)

**Files:**
- Modify: `scripts/explore.py`
- Update: `tests/fixtures/payloads/*.json`

**⛔ APPROVAL REQUIRED:** This task submits real form writes to the test tenant. Before running each sub-step, state exactly what write will happen and wait for explicit user approval. Clean up any created records at the end of the task.

- [ ] **Step 1: Propose the writes to the user and wait for approval**

State in chat:

> "Task 1.4 is about to perform three real writes on the washu test tenant:
>  1. Create one employee via /employee/create → /employee/insert (step 1 only) — captures the real payload and the redirect-to-permissions-page URL.
>  2. Submit the POS permissions form for that employee (step 2).
>  3. Create one Backoffice user via /user/create → /user/insert, both modes if feasible.
> All created records will be disabled at the end of the task.
> Approve step-by-step or all at once?"

Wait for approval. Do not proceed to Step 2 without it.

- [ ] **Step 2: Extend `explore.py` to perform and record one employee creation**

Add a branch guarded by `--allow-write employee_insert` that fills the employee creation form with throwaway data (first_name="WrapperExplore", last_name="DeleteMe", unique email and pos_user_id), clicks Submit, and records:
- the exact POST URL
- the full form payload as `tests/fixtures/payloads/employee_insert.json`
- the response HTML as `tests/fixtures/html/employee_insert_response.html`
- the URL the browser landed on afterwards (this is the permissions page URL — critical)

Code to append inside `main()`:

```python
        if "employee_insert" in args.allow_write:
            print("[WRITE] Creating exploration employee")
            page.goto(f"{base_url}/employee/create")
            page.wait_for_load_state("networkidle")
            # Fill the form — field names confirmed from Task 1.3 notes
            page.fill("input[name='employee[firstName]']", "WrapperExplore")
            page.fill("input[name='employee[lastName]']", "DeleteMe")
            page.fill("input[name='employee[email]']", "wrapper-explore-delete-me@example.invalid")
            # ... more fields as dictated by the real form; use the exploration notes as the source of truth
            # Click Set Permissions / Submit button and capture resulting navigation
            with page.expect_navigation() as nav_info:
                page.click("button[type='submit']")
            response = nav_info.value
            print(f"  ↳ landed on: {page.url}")
            print(f"  ↳ response status: {response.status if response else 'unknown'}")
            save_html("employee_insert_response", page.content())
            # Save the landed URL so we know the permissions-page URL pattern
            save_payload(
                "employee_insert_redirect",
                {"landed_url": page.url, "response_status": response.status if response else None},
            )
```

- [ ] **Step 3: Run with approval**

```bash
python scripts/explore.py --subdomain washu --username SonnysWrapperTestAccount --allow-write login --allow-write employee_insert
```

Expected: one exploration employee is created, `employee_insert.json` contains the full field dump (captured via the route handler's `post_data`), and `employee_insert_redirect.json` shows the permissions page URL.

- [ ] **Step 4: Capture the step-2 permissions POST**

The permissions page is now loaded in the browser. Extend `explore.py` with an `employee_permissions_insert` guarded block that fills out the permissions form (set role to "General User", access to all sites, submit), and records that POST's URL + payload. Run again with `--allow-write employee_permissions_insert` after approval.

- [ ] **Step 5: Repeat for `/user/create`**

Same pattern: extend `explore.py` with guarded blocks for `user_insert` (both linked and standalone modes) and `user_permissions_insert`. Run each with approval.

- [ ] **Step 6: Capture the disable flow**

Navigate to the exploration employee's edit page, identify the disable control, and record the disable POST (payload, URL, method) with approval. This completes the exploration for `disable_employee`.

- [ ] **Step 7: Clean up — disable the exploration employee and BO user**

Use the `user_permissions_insert` disable flow to terminate the exploration records. Verify in the employee list that they appear as disabled.

- [ ] **Step 8: Update `exploration_notes.md` with all newly-confirmed URLs and payload shapes**

Fill in every remaining `<fill>` placeholder.

- [ ] **Step 9: Commit**

```bash
git add tests/fixtures/ scripts/explore.py
git commit -m "chore(fixtures): capture create and disable POSTs for employee and BO user flows"
```

**Phase gate:** After Task 1.4, the fixtures directory must contain (at minimum):
- `html/login_page.html`, `html/employee_create.html`, `html/user_create.html`, `html/user_create_standalone.html`, `html/employee_list.html`
- `html/employee_insert_response.html`, `html/employee_permissions_page.html`, `html/user_insert_response.html`
- `payloads/employee_insert.json`, `payloads/employee_permissions_insert.json`, `payloads/user_insert_linked.json`, `payloads/user_insert_standalone.json`, `payloads/user_permissions_insert.json`, `payloads/employee_disable.json`, `payloads/employee_insert_redirect.json`
- `exploration_notes.md` with no `<fill>` markers

Phases 2-9 reference these by path. Do not proceed to Phase 2 if any are missing.

---

## Phase 2: Foundation — Exceptions, Passwords, Models

Small pure modules with no dependencies on session/HTTP. Fully unit-testable.

### Task 2.1: Exception hierarchy

**Files:**
- Create: `src/sonnys_backoffice/exceptions.py`
- Create: `tests/unit/test_exceptions.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_exceptions.py
import pytest

from sonnys_backoffice.exceptions import (
    AuthenticationError,
    BackofficeServerError,
    DuplicateError,
    NotFoundError,
    PermissionDeniedError,
    SonnysBackofficeError,
    ValidationError,
)


def test_all_exceptions_inherit_from_base():
    for exc_cls in (
        AuthenticationError,
        NotFoundError,
        ValidationError,
        PermissionDeniedError,
        DuplicateError,
        BackofficeServerError,
    ):
        assert issubclass(exc_cls, SonnysBackofficeError)


def test_base_exception_is_exception():
    assert issubclass(SonnysBackofficeError, Exception)


def test_exceptions_carry_message():
    exc = ValidationError("phone must be 9 or 10 digits")
    assert "phone" in str(exc)


def test_catch_any_as_base():
    with pytest.raises(SonnysBackofficeError):
        raise DuplicateError("email already exists")
```

- [ ] **Step 2: Run — expect ImportError / ModuleNotFoundError**

```bash
pytest tests/unit/test_exceptions.py -v
```

- [ ] **Step 3: Implement `exceptions.py`**

```python
# src/sonnys_backoffice/exceptions.py
"""Exception hierarchy for the Sonny's Backoffice Wrapper."""


class SonnysBackofficeError(Exception):
    """Base class for all errors raised by this library."""


class AuthenticationError(SonnysBackofficeError):
    """Login failed, or session expired and re-authentication failed."""


class NotFoundError(SonnysBackofficeError):
    """Lookup (by POS User ID or email) did not match any record."""


class ValidationError(SonnysBackofficeError):
    """Caller input violated a constraint, or Backoffice rejected the payload."""


class PermissionDeniedError(SonnysBackofficeError):
    """The bot user lacks sufficient rights for the requested operation."""


class DuplicateError(SonnysBackofficeError):
    """A record with the given email or POS User ID already exists on this tenant."""


class BackofficeServerError(SonnysBackofficeError):
    """Unexpected server response — HTTP 5xx or unparseable HTML."""
```

- [ ] **Step 4: Run — expect pass**

```bash
pytest tests/unit/test_exceptions.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/sonnys_backoffice/exceptions.py tests/unit/test_exceptions.py
git commit -m "feat(exceptions): add exception hierarchy"
```

### Task 2.2: Password generators

**Files:**
- Create: `src/sonnys_backoffice/passwords.py`
- Create: `tests/unit/test_passwords.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_passwords.py
import re
import string

from sonnys_backoffice.passwords import generate_bo_password, generate_pos_pin


def test_pos_pin_is_five_digits():
    for _ in range(100):
        pin = generate_pos_pin()
        assert pin.isdigit()
        assert len(pin) == 5


def test_bo_password_length_is_twelve():
    for _ in range(100):
        pw = generate_bo_password()
        assert len(pw) == 12


def test_bo_password_has_alphanumeric_and_symbol():
    pw = generate_bo_password()
    has_alpha = any(c.isalpha() for c in pw)
    has_digit = any(c.isdigit() for c in pw)
    has_symbol = any(c in string.punctuation for c in pw)
    assert has_alpha and has_digit and has_symbol


def test_bo_password_matches_expected_character_set():
    pw = generate_bo_password()
    # alphanumeric + symbols only, no whitespace
    assert re.fullmatch(r"[A-Za-z0-9!@#$%^&*()_+=\-\[\]{};:,.<>?]+", pw)


def test_pos_pin_is_randomized():
    pins = {generate_pos_pin() for _ in range(50)}
    assert len(pins) > 1  # should not always return the same value


def test_bo_password_is_randomized():
    pws = {generate_bo_password() for _ in range(50)}
    assert len(pws) > 1
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement `passwords.py`**

```python
# src/sonnys_backoffice/passwords.py
"""Password and PIN generators for newly-created users."""
from __future__ import annotations

import secrets
import string

_POS_PIN_DIGITS = 5
_BO_PASSWORD_LENGTH = 12
_BO_SYMBOLS = "!@#$%^&*()_+=-[]{};:,.<>?"
_BO_ALPHABET = string.ascii_letters + string.digits + _BO_SYMBOLS


def generate_pos_pin() -> str:
    """Return a 5-digit numeric PIN suitable for POS login."""
    return "".join(secrets.choice(string.digits) for _ in range(_POS_PIN_DIGITS))


def generate_bo_password() -> str:
    """Return a 12-character password containing letters, digits, and at least one symbol."""
    while True:
        pw = "".join(secrets.choice(_BO_ALPHABET) for _ in range(_BO_PASSWORD_LENGTH))
        if (
            any(c.isalpha() for c in pw)
            and any(c.isdigit() for c in pw)
            and any(c in _BO_SYMBOLS for c in pw)
        ):
            return pw
```

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Commit**

```bash
git add src/sonnys_backoffice/passwords.py tests/unit/test_passwords.py
git commit -m "feat(passwords): add POS PIN and BO password generators"
```

### Task 2.3: Input models — `CreateEmployeeRequest`

**Files:**
- Create: `src/sonnys_backoffice/models.py`
- Create: `tests/unit/test_models_employee_input.py`

- [ ] **Step 1: Write failing tests for phone normalization**

```python
# tests/unit/test_models_employee_input.py
from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError

from sonnys_backoffice.models import CreateEmployeeRequest


def _valid_kwargs(**overrides):
    base = dict(
        first_name="Jane",
        last_name="Doe",
        phone="6155551234",
        email="jane@example.com",
        pos_user_id="jdoe",
        wage_rate=Decimal("15.50"),
        start_date=datetime(2026, 5, 1),
        available_sites=["Wash 37135"],
    )
    base.update(overrides)
    return base


def test_phone_strips_symbols_and_spaces():
    req = CreateEmployeeRequest(**_valid_kwargs(phone="(615) 555-1234"))
    assert req.phone == "6155551234"


def test_phone_accepts_nine_digits():
    req = CreateEmployeeRequest(**_valid_kwargs(phone="155551234"))
    assert req.phone == "155551234"


def test_phone_rejects_eight_digits():
    with pytest.raises(PydanticValidationError, match="9 or 10"):
        CreateEmployeeRequest(**_valid_kwargs(phone="15551234"))


def test_phone_rejects_eleven_digits():
    with pytest.raises(PydanticValidationError, match="9 or 10"):
        CreateEmployeeRequest(**_valid_kwargs(phone="16155551234"))


def test_name_is_stripped():
    req = CreateEmployeeRequest(**_valid_kwargs(first_name="  Jane  ", last_name=" Doe "))
    assert req.first_name == "Jane"
    assert req.last_name == "Doe"


def test_name_preserves_unicode_and_symbols():
    req = CreateEmployeeRequest(**_valid_kwargs(first_name="José", last_name="O'Neal-García"))
    assert req.first_name == "José"
    assert req.last_name == "O'Neal-García"


def test_email_requires_at_and_domain():
    with pytest.raises(PydanticValidationError, match="email"):
        CreateEmployeeRequest(**_valid_kwargs(email="not-an-email"))


def test_email_accepts_standard_formats():
    for email in ("user@gmail.com", "user@icloud.com", "user.name@washucarwash.com"):
        CreateEmployeeRequest(**_valid_kwargs(email=email))


def test_departments_defaults_to_greeter():
    req = CreateEmployeeRequest(**_valid_kwargs(departments=None))
    assert req.departments == ["Greeter"]


def test_departments_auto_adds_greeter_if_missing():
    req = CreateEmployeeRequest(**_valid_kwargs(departments=["Cashier"]))
    assert "Greeter" in req.departments
    assert "Cashier" in req.departments


def test_departments_does_not_duplicate_greeter():
    req = CreateEmployeeRequest(**_valid_kwargs(departments=["Greeter", "Cashier"]))
    assert req.departments.count("Greeter") == 1


def test_overtime_defaults_to_time_and_a_half():
    req = CreateEmployeeRequest(**_valid_kwargs(wage_rate=Decimal("10.00")))
    assert req.overtime_wage_rate == Decimal("15.00")


def test_overtime_honors_explicit_value():
    req = CreateEmployeeRequest(**_valid_kwargs(wage_rate=Decimal("10.00"), overtime_wage_rate=Decimal("20.00")))
    assert req.overtime_wage_rate == Decimal("20.00")


def test_available_sites_accepts_all_literal():
    req = CreateEmployeeRequest(**_valid_kwargs(available_sites="all"))
    assert req.available_sites == "all"


def test_available_sites_rejects_empty_list():
    with pytest.raises(PydanticValidationError, match="at least one"):
        CreateEmployeeRequest(**_valid_kwargs(available_sites=[]))


def test_requires_backoffice_requires_username():
    with pytest.raises(PydanticValidationError, match="backoffice_username"):
        CreateEmployeeRequest(**_valid_kwargs(requires_backoffice=True))


def test_pos_pin_must_be_five_digits_if_provided():
    with pytest.raises(PydanticValidationError, match="5 digits"):
        CreateEmployeeRequest(**_valid_kwargs(pos_pin="123"))


def test_extra_kwargs_rejected():
    with pytest.raises(PydanticValidationError):
        CreateEmployeeRequest(**_valid_kwargs(mystery_field="nope"))
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement `CreateEmployeeRequest`**

```python
# src/sonnys_backoffice/models.py
"""Pydantic v2 models for inputs, outputs, and domain objects."""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_PHONE_SYMBOL_RE = re.compile(r"[^\d]")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_GREETER = "Greeter"


class _BackofficeBaseModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class CreateEmployeeRequest(_BackofficeBaseModel):
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    phone: str
    email: str
    pos_user_id: str = Field(min_length=1)
    pos_pin: str | None = None
    wage_rate: Decimal
    overtime_wage_rate: Decimal | None = None
    start_date: datetime
    available_sites: list[str] | Literal["all"]
    departments: list[str] | None = None
    permission: str = "General User"
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    requires_backoffice: bool = False
    backoffice_username: str | None = None
    backoffice_password: str | None = None

    @field_validator("phone", "emergency_contact_phone", mode="before")
    @classmethod
    def _normalize_phone(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = _PHONE_SYMBOL_RE.sub("", v)
        if len(stripped) not in (9, 10):
            raise ValueError("phone must be 9 or 10 digits after symbols are stripped")
        return stripped

    @field_validator("email", mode="before")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        if not isinstance(v, str) or not _EMAIL_RE.match(v.strip()):
            raise ValueError(f"email must contain a valid @domain.tld: {v!r}")
        return v.strip()

    @field_validator("pos_pin", mode="before")
    @classmethod
    def _validate_pos_pin(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not (v.isdigit() and len(v) == 5):
            raise ValueError("pos_pin must be exactly 5 digits if provided")
        return v

    @field_validator("departments", mode="before")
    @classmethod
    def _default_departments(cls, v: list[str] | None) -> list[str]:
        if v is None or len(v) == 0:
            return [_GREETER]
        cleaned = [d.strip() for d in v if d.strip()]
        if _GREETER not in cleaned:
            cleaned.append(_GREETER)
        # dedupe while preserving order
        seen: set[str] = set()
        out: list[str] = []
        for d in cleaned:
            if d not in seen:
                seen.add(d)
                out.append(d)
        return out

    @field_validator("available_sites", mode="before")
    @classmethod
    def _validate_sites(cls, v):
        if v == "all":
            return v
        if isinstance(v, list) and len(v) == 0:
            raise ValueError("available_sites must contain at least one site name (or be 'all')")
        return v

    @model_validator(mode="after")
    def _check_wage_and_backoffice(self) -> "CreateEmployeeRequest":
        if self.overtime_wage_rate is None:
            # default to time and a half
            object.__setattr__(self, "overtime_wage_rate", (self.wage_rate * Decimal("1.5")).quantize(Decimal("0.01")))
        if self.requires_backoffice and not self.backoffice_username:
            raise ValueError("backoffice_username is required when requires_backoffice=True")
        return self
```

- [ ] **Step 4: Run — expect pass**

```bash
pytest tests/unit/test_models_employee_input.py -v
```

Iterate on the implementation until every assertion passes. If a test fails due to ambiguity in Pydantic's error messages vs. the regex the test uses, relax the regex (not the assertion — keep the behavior).

- [ ] **Step 5: Commit**

```bash
git add src/sonnys_backoffice/models.py tests/unit/test_models_employee_input.py
git commit -m "feat(models): add CreateEmployeeRequest with phone/email/departments/backoffice validators"
```

### Task 2.4: Input models — `DisableEmployeeRequest` and `CreateBackofficeUserRequest`

**Files:**
- Modify: `src/sonnys_backoffice/models.py`
- Create: `tests/unit/test_models_disable_and_bo_user.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_models_disable_and_bo_user.py
import pytest
from pydantic import ValidationError as PydanticValidationError

from sonnys_backoffice.models import CreateBackofficeUserRequest, DisableEmployeeRequest


def test_disable_requires_exactly_one_lookup_key():
    with pytest.raises(PydanticValidationError, match="exactly one"):
        DisableEmployeeRequest()
    with pytest.raises(PydanticValidationError, match="exactly one"):
        DisableEmployeeRequest(pos_user_id="x", email="y@z.com")


def test_disable_accepts_pos_user_id_alone():
    req = DisableEmployeeRequest(pos_user_id="jdoe")
    assert req.pos_user_id == "jdoe"
    assert req.email is None


def test_disable_accepts_email_alone():
    req = DisableEmployeeRequest(email="jane@example.com")
    assert req.email == "jane@example.com"
    assert req.pos_user_id is None


def _bo_kwargs(**overrides):
    base = dict(username="janedoe", email="jane@example.com")
    base.update(overrides)
    return base


def test_bo_user_requires_link_or_standalone():
    with pytest.raises(PydanticValidationError, match="link_to_employee"):
        CreateBackofficeUserRequest(**_bo_kwargs())


def test_bo_user_linked_mode_valid():
    req = CreateBackofficeUserRequest(**_bo_kwargs(link_to_employee_pos_user_id="jdoe"))
    assert req.link_to_employee_pos_user_id == "jdoe"


def test_bo_user_standalone_mode_requires_first_and_last_name():
    with pytest.raises(PydanticValidationError, match="first_name"):
        CreateBackofficeUserRequest(**_bo_kwargs(last_name="Doe"))


def test_bo_user_standalone_mode_valid():
    req = CreateBackofficeUserRequest(**_bo_kwargs(first_name="Jane", last_name="Doe"))
    assert req.first_name == "Jane"


def test_bo_user_link_and_standalone_are_mutually_exclusive():
    with pytest.raises(PydanticValidationError, match="either link"):
        CreateBackofficeUserRequest(
            **_bo_kwargs(
                first_name="Jane",
                last_name="Doe",
                link_to_employee_pos_user_id="jdoe",
            )
        )


def test_bo_user_username_pattern():
    # HTML form enforces [A-Za-z][\w]{2,63}
    with pytest.raises(PydanticValidationError):
        CreateBackofficeUserRequest(**_bo_kwargs(username="1starts_with_digit", first_name="a", last_name="b"))
    with pytest.raises(PydanticValidationError):
        CreateBackofficeUserRequest(**_bo_kwargs(username="ab", first_name="a", last_name="b"))  # too short
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Extend `models.py`**

Append to `models.py`:

```python
_USERNAME_RE = re.compile(r"^[A-Za-z][\w]{2,63}$")


class DisableEmployeeRequest(_BackofficeBaseModel):
    pos_user_id: str | None = None
    email: str | None = None

    @field_validator("email", mode="before")
    @classmethod
    def _validate_email(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not _EMAIL_RE.match(v.strip()):
            raise ValueError(f"email must contain a valid @domain.tld: {v!r}")
        return v.strip()

    @model_validator(mode="after")
    def _check_exactly_one(self) -> "DisableEmployeeRequest":
        provided = [x for x in (self.pos_user_id, self.email) if x]
        if len(provided) != 1:
            raise ValueError("exactly one of pos_user_id or email is required")
        return self


class CreateBackofficeUserRequest(_BackofficeBaseModel):
    username: str
    email: str
    password: str | None = None
    permission: str = "General User"
    link_to_employee_pos_user_id: str | None = None
    link_to_employee_email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    available_sites: list[str] | Literal["all"] = "all"

    @field_validator("username", mode="before")
    @classmethod
    def _validate_username(cls, v: str) -> str:
        if not _USERNAME_RE.match(v):
            raise ValueError(
                "username must start with a letter and contain 3-64 alphanumeric characters"
            )
        return v

    @field_validator("email", mode="before")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v.strip()):
            raise ValueError(f"email must contain a valid @domain.tld: {v!r}")
        return v.strip()

    @model_validator(mode="after")
    def _check_link_or_standalone(self) -> "CreateBackofficeUserRequest":
        has_link = bool(self.link_to_employee_pos_user_id or self.link_to_employee_email)
        has_standalone = bool(self.first_name or self.last_name)
        if has_link and has_standalone:
            raise ValueError(
                "provide either link_to_employee_* or first_name+last_name — not both"
            )
        if not has_link and not has_standalone:
            raise ValueError(
                "provide either link_to_employee_pos_user_id / link_to_employee_email or first_name+last_name"
            )
        if has_standalone and not (self.first_name and self.last_name):
            raise ValueError("standalone BO user requires both first_name and last_name")
        return self
```

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Commit**

```bash
git add src/sonnys_backoffice/models.py tests/unit/test_models_disable_and_bo_user.py
git commit -m "feat(models): add DisableEmployeeRequest and CreateBackofficeUserRequest"
```

### Task 2.5: Output and domain models

**Files:**
- Modify: `src/sonnys_backoffice/models.py`
- Create: `tests/unit/test_models_outputs.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_models_outputs.py
from datetime import datetime

from sonnys_backoffice.models import (
    BackofficeUserCreated,
    Department,
    EmployeeCreated,
    EmployeeDisabled,
    Permission,
    Region,
    Site,
)


def test_employee_created_round_trips():
    r = EmployeeCreated(
        employee_id=42,
        pos_user_id="jdoe",
        pos_pin="12345",
        first_name="Jane",
        last_name="Doe",
        email="jane@example.com",
        permission_applied="General User",
        sites_granted=["Nolensville"],
        departments=["Greeter"],
    )
    assert r.warnings == []
    d = r.model_dump()
    assert d["pos_pin"] == "12345"


def test_employee_created_with_backoffice():
    r = EmployeeCreated(
        employee_id=42,
        pos_user_id="jdoe",
        pos_pin="12345",
        first_name="Jane",
        last_name="Doe",
        email="jane@example.com",
        backoffice_user_id=99,
        backoffice_username="janedoe",
        backoffice_password="SecretPW1!",
        permission_applied="Administrator",
        sites_granted=["Nolensville"],
        departments=["Greeter"],
        warnings=["permission 'Admin' not found, fell back to 'Administrator'"],
    )
    assert r.backoffice_user_id == 99
    assert len(r.warnings) == 1


def test_bo_user_created():
    r = BackofficeUserCreated(
        user_id=99,
        username="janedoe",
        password="SecretPW1!",
        email="jane@example.com",
        permission_applied="Administrator",
        sites_granted=["Nolensville"],
    )
    assert r.linked_employee_id is None


def test_employee_disabled():
    r = EmployeeDisabled(
        employee_id=42,
        pos_user_id="jdoe",
        email="jane@example.com",
        disabled_at=datetime(2026, 4, 13),
    )
    assert r.pos_user_id == "jdoe"


def test_domain_models():
    site = Site(id=17, name="Wash 37135", district_id=1, region_id=1)
    assert site.name == "Wash 37135"

    dept = Department(id=5, name="Greeter")
    assert dept.name == "Greeter"

    perm = Permission(id=3, name="Administrator", scope="pos")
    assert perm.scope == "pos"

    region = Region(id=2, name="WashU Illinois")
    assert region.name == "WashU Illinois"
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Extend `models.py` with output and domain types**

Append:

```python
# --- Output models ---


class EmployeeCreated(_BackofficeBaseModel):
    employee_id: int
    pos_user_id: str
    pos_pin: str
    first_name: str
    last_name: str
    email: str
    backoffice_user_id: int | None = None
    backoffice_username: str | None = None
    backoffice_password: str | None = None
    permission_applied: str
    sites_granted: list[str]
    departments: list[str]
    warnings: list[str] = Field(default_factory=list)


class BackofficeUserCreated(_BackofficeBaseModel):
    user_id: int
    username: str
    password: str
    email: str
    linked_employee_id: int | None = None
    permission_applied: str
    sites_granted: list[str]
    warnings: list[str] = Field(default_factory=list)


class EmployeeDisabled(_BackofficeBaseModel):
    employee_id: int
    pos_user_id: str
    email: str | None = None
    disabled_at: datetime


# --- Domain models ---


class Region(_BackofficeBaseModel):
    id: int
    name: str


class District(_BackofficeBaseModel):
    id: int
    name: str
    region_id: int | None = None


class Site(_BackofficeBaseModel):
    id: int
    name: str
    district_id: int | None = None
    region_id: int | None = None


class Department(_BackofficeBaseModel):
    id: int
    name: str


class Permission(_BackofficeBaseModel):
    id: int
    name: str
    scope: Literal["pos", "backoffice"]
```

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Commit**

```bash
git add src/sonnys_backoffice/models.py tests/unit/test_models_outputs.py
git commit -m "feat(models): add output and domain models"
```

### Task 2.6: Permission resolver

**Files:**
- Create: `src/sonnys_backoffice/permissions.py`
- Create: `tests/unit/test_permissions.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_permissions.py
import warnings

import pytest

from sonnys_backoffice.models import Permission
from sonnys_backoffice.permissions import resolve_permission

_POS_LIST = [
    Permission(id=1, name="General User", scope="pos"),
    Permission(id=2, name="Administrator", scope="pos"),
    Permission(id=3, name="CSA", scope="pos"),
]


def test_exact_match():
    match, warnings_list = resolve_permission("Administrator", _POS_LIST)
    assert match.name == "Administrator"
    assert warnings_list == []


def test_case_insensitive_match():
    match, warnings_list = resolve_permission("administrator", _POS_LIST)
    assert match.name == "Administrator"
    assert warnings_list == []


def test_unknown_falls_back_to_general_user():
    match, warnings_list = resolve_permission("NonExistentRole", _POS_LIST)
    assert match.name == "General User"
    assert len(warnings_list) == 1
    assert "NonExistentRole" in warnings_list[0]
    assert "General User" in warnings_list[0]


def test_unknown_also_emits_python_warning():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        resolve_permission("NonExistentRole", _POS_LIST)
        assert len(w) == 1
        assert "NonExistentRole" in str(w[0].message)


def test_raises_if_general_user_not_in_list():
    short_list = [Permission(id=2, name="Administrator", scope="pos")]
    with pytest.raises(ValueError, match="General User"):
        resolve_permission("Unknown", short_list)
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement `permissions.py`**

```python
# src/sonnys_backoffice/permissions.py
"""Permission name resolution with case-insensitive matching and General User fallback."""
from __future__ import annotations

import warnings
from typing import Iterable

from .models import Permission

_DEFAULT_FALLBACK = "General User"


def resolve_permission(
    requested: str,
    available: Iterable[Permission],
) -> tuple[Permission, list[str]]:
    """Resolve a permission name against the tenant's available list.

    Returns (matched_permission, warnings_list). Matching is case-insensitive.
    Unknown names fall back to "General User" with a warning. Raises ValueError
    if "General User" is not present in the available list (tenant misconfig).
    """
    available_list = list(available)
    target = requested.strip().lower()
    for perm in available_list:
        if perm.name.lower() == target:
            return perm, []

    # Fallback
    fallback_msg = (
        f"permission {requested!r} not found in tenant, "
        f"falling back to {_DEFAULT_FALLBACK!r}"
    )
    warnings.warn(fallback_msg, stacklevel=2)
    for perm in available_list:
        if perm.name.lower() == _DEFAULT_FALLBACK.lower():
            return perm, [fallback_msg]
    raise ValueError(
        f"{_DEFAULT_FALLBACK!r} not found in tenant's permission list — "
        "cannot apply fallback. Check tenant role configuration."
    )
```

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Commit**

```bash
git add src/sonnys_backoffice/permissions.py tests/unit/test_permissions.py
git commit -m "feat(permissions): add case-insensitive resolver with General User fallback"
```

---

## Phase 3: Session and Authentication

Implements `_BackofficeSession` — the private class that owns the `requests.Session`, login, CSRF handling, and transparent re-authentication. All logic is tested against captured fixtures from Phase 1.

### Task 3.1: Session skeleton and login

**Files:**
- Create: `src/sonnys_backoffice/session.py`
- Create: `tests/unit/test_session.py`

- [ ] **Step 1: Write failing tests (fixture-driven)**

```python
# tests/unit/test_session.py
from pathlib import Path

import pytest
import requests_mock

from sonnys_backoffice.session import _BackofficeSession
from sonnys_backoffice.exceptions import AuthenticationError

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html"
LOGIN_HTML = (FIXTURES / "login_page.html").read_text(encoding="utf-8")


def test_base_url_construction():
    s = _BackofficeSession(subdomain="washu", username="u", password="p")
    assert s.base_url == "https://washu.sonnyscontrols.com"


def test_login_extracts_csrf_and_posts_credentials():
    s = _BackofficeSession(subdomain="washu", username="bot", password="secret")
    with requests_mock.Mocker() as m:
        m.get("https://washu.sonnyscontrols.com/login", text=LOGIN_HTML)
        # Use the real login form action from fixtures — adjust path after Task 1.3
        m.post(
            "https://washu.sonnyscontrols.com/login/authenticate",
            status_code=302,
            headers={"Location": "/"},
        )
        m.get("https://washu.sonnyscontrols.com/", text="<html><body>Home</body></html>")
        s.login()

        # Verify the POST was made with CSRF token and credentials
        login_post = [req for req in m.request_history if req.method == "POST"][0]
        # These assertions should match the CSRF field name from exploration_notes.md
        assert "bot" in login_post.text or "bot" in str(login_post.body)
        assert "secret" in login_post.text or "secret" in str(login_post.body)


def test_login_failure_raises_authentication_error():
    s = _BackofficeSession(subdomain="washu", username="bot", password="wrong")
    with requests_mock.Mocker() as m:
        m.get("https://washu.sonnyscontrols.com/login", text=LOGIN_HTML)
        m.post(
            "https://washu.sonnyscontrols.com/login/authenticate",
            status_code=200,
            text=LOGIN_HTML,  # still on login page = failed
        )
        with pytest.raises(AuthenticationError):
            s.login()
```

Add `requests-mock` to dev dependencies in `pyproject.toml` if not already present:

```toml
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "ruff>=0.1",
    "playwright>=1.40",
    "requests-mock>=1.11",
]
```

Install: `pip install -e ".[dev]"`.

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement `session.py`**

```python
# src/sonnys_backoffice/session.py
"""Private HTTP session management — login, CSRF, transparent re-auth."""
from __future__ import annotations

from typing import Any

import requests
from bs4 import BeautifulSoup

from .exceptions import AuthenticationError, BackofficeServerError


class _BackofficeSession:
    """Owns auth state for a single Backoffice tenant. Not part of the public API."""

    def __init__(
        self,
        *,
        subdomain: str,
        username: str,
        password: str,
        timeout: float = 30.0,
        user_agent: str | None = None,
    ) -> None:
        self.base_url = f"https://{subdomain}.sonnyscontrols.com"
        self._username = username
        self._password = password
        self._timeout = timeout
        self._http = requests.Session()
        if user_agent:
            self._http.headers["User-Agent"] = user_agent
        self._logged_in = False

    def login(self) -> None:
        """Perform the full login flow. Safe to call repeatedly."""
        login_page = self._http.get(f"{self.base_url}/login", timeout=self._timeout)
        login_page.raise_for_status()
        csrf_token, form_action = _parse_login_form(login_page.text)
        post_url = form_action if form_action.startswith("http") else f"{self.base_url}{form_action}"
        # CSRF field name is captured from fixtures — `_token` is a placeholder to be
        # updated during implementation to match the real field name in exploration_notes.md
        resp = self._http.post(
            post_url,
            data={
                "_token": csrf_token,
                "username": self._username,
                "password": self._password,
            },
            timeout=self._timeout,
            allow_redirects=True,
        )
        if _looks_like_login_page(resp.text):
            raise AuthenticationError("Login failed — credentials rejected by Backoffice")
        if resp.status_code >= 400:
            raise BackofficeServerError(f"Unexpected login response: HTTP {resp.status_code}")
        self._logged_in = True

    def get(self, path: str, **kwargs: Any) -> requests.Response:
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> requests.Response:
        return self._request("POST", path, **kwargs)

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        if not self._logged_in:
            self.login()
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        kwargs.setdefault("timeout", self._timeout)
        resp = self._http.request(method, url, **kwargs)
        # Detect session expiration and retry once
        if _looks_like_login_page(resp.text) or resp.status_code in (401, 403):
            self._logged_in = False
            self.login()
            resp = self._http.request(method, url, **kwargs)
            if _looks_like_login_page(resp.text) or resp.status_code in (401, 403):
                raise AuthenticationError("Re-authentication failed")
        return resp

    def close(self) -> None:
        self._http.close()


def _parse_login_form(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form")
    if form is None:
        raise BackofficeServerError("Login page contains no <form> — Backoffice HTML may have changed")
    action = form.get("action", "/login/authenticate")
    # Locate CSRF token — try common names. Update after exploration confirms the actual name.
    token_input = form.find("input", attrs={"name": "_token"}) or form.find(
        "input", attrs={"name": "authenticity_token"}
    )
    if token_input is None:
        raise BackofficeServerError("Login form contains no CSRF token input")
    return token_input.get("value", ""), action


def _looks_like_login_page(html: str) -> bool:
    """Heuristic: a session-expired response usually re-renders the login form."""
    return 'name="username"' in html and 'name="password"' in html and 'type="password"' in html
```

- [ ] **Step 4: Run tests**

After Task 1.3, update the CSRF field name, login POST URL, and any other placeholders in this file to match `exploration_notes.md`. Re-run until tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/sonnys_backoffice/session.py tests/unit/test_session.py pyproject.toml
git commit -m "feat(session): add _BackofficeSession with login, CSRF, re-auth"
```

### Task 3.2: Session re-authentication on expiration

**Files:**
- Modify: `tests/unit/test_session.py`

- [ ] **Step 1: Add re-auth tests**

```python
def test_request_retries_once_on_session_expired():
    s = _BackofficeSession(subdomain="washu", username="bot", password="secret")
    with requests_mock.Mocker() as m:
        m.get("https://washu.sonnyscontrols.com/login", text=LOGIN_HTML)
        m.post(
            "https://washu.sonnyscontrols.com/login/authenticate",
            status_code=302,
            headers={"Location": "/"},
        )
        # First call to /employee returns a login page (session expired)
        # Second call (after re-login) returns normal content
        m.get(
            "https://washu.sonnyscontrols.com/employee",
            [
                {"text": LOGIN_HTML, "status_code": 200},
                {"text": "<html><body>employees</body></html>", "status_code": 200},
            ],
        )
        resp = s.get("/employee")
        assert "employees" in resp.text


def test_request_raises_after_second_expiration():
    s = _BackofficeSession(subdomain="washu", username="bot", password="secret")
    with requests_mock.Mocker() as m:
        m.get("https://washu.sonnyscontrols.com/login", text=LOGIN_HTML)
        m.post(
            "https://washu.sonnyscontrols.com/login/authenticate",
            status_code=302,
            headers={"Location": "/"},
        )
        # Both calls return the login page — re-auth fails
        m.get("https://washu.sonnyscontrols.com/employee", text=LOGIN_HTML)
        with pytest.raises(AuthenticationError, match="Re-authentication"):
            s.get("/employee")
```

- [ ] **Step 2: Run — the implementation from Task 3.1 already handles this**

```bash
pytest tests/unit/test_session.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_session.py
git commit -m "test(session): cover transparent re-auth path"
```

---

## Phase 4: Discovery Helpers — Sites, Departments, Permissions

### Task 4.1: Site resolver with hierarchy detection

**Files:**
- Create: `src/sonnys_backoffice/sites.py`
- Create: `tests/unit/test_sites.py`

- [ ] **Step 1: Write failing tests using the captured `employee_create.html` fixture**

```python
# tests/unit/test_sites.py
from pathlib import Path

import pytest

from sonnys_backoffice.sites import SiteTree, parse_site_tree

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html"


def test_parses_hierarchical_tenant_fixture():
    html = (FIXTURES / "employee_create.html").read_text(encoding="utf-8")
    tree = parse_site_tree(html)
    assert tree.is_hierarchical is True
    assert len(tree.regions) >= 1
    # Check specific names from the WashU fixture
    site_names = [s.name for s in tree.sites]
    assert "WashU Fiesta" in site_names
    fiesta = next(s for s in tree.sites if s.name == "WashU Fiesta")
    assert fiesta.id == 1
    assert fiesta.district_id == 2
    assert fiesta.region_id == 2


def test_resolve_by_name():
    html = (FIXTURES / "employee_create.html").read_text(encoding="utf-8")
    tree = parse_site_tree(html)
    site = tree.resolve("WashU Fiesta")
    assert site.id == 1


def test_resolve_unknown_raises():
    html = (FIXTURES / "employee_create.html").read_text(encoding="utf-8")
    tree = parse_site_tree(html)
    with pytest.raises(LookupError, match="Unknown Site"):
        tree.resolve("Unknown Site")


def test_resolve_all_returns_every_site():
    html = (FIXTURES / "employee_create.html").read_text(encoding="utf-8")
    tree = parse_site_tree(html)
    all_sites = tree.resolve_all("all")
    assert len(all_sites) == len(tree.sites)
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement `sites.py`**

```python
# src/sonnys_backoffice/sites.py
"""Site/region/district tree parser and resolver."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal

from bs4 import BeautifulSoup

from .models import District, Region, Site


@dataclass
class SiteTree:
    is_hierarchical: bool
    regions: list[Region] = field(default_factory=list)
    districts: list[District] = field(default_factory=list)
    sites: list[Site] = field(default_factory=list)

    def resolve(self, name: str) -> Site:
        for s in self.sites:
            if s.name == name:
                return s
        raise LookupError(f"Unknown Site: {name!r}")

    def resolve_all(self, sites: list[str] | Literal["all"]) -> list[Site]:
        if sites == "all":
            return list(self.sites)
        return [self.resolve(n) for n in sites]


def parse_site_tree(html: str) -> SiteTree:
    """Parse /employee/create HTML into a SiteTree.

    Detects flat vs hierarchical tenants by looking for the presence of
    region toggle markup.
    """
    soup = BeautifulSoup(html, "html.parser")
    # Hierarchical markers — these class names confirmed from the brief's HTML sample
    region_options = soup.select("input.boac-permission-region-option")
    is_hierarchical = len(region_options) > 0

    if is_hierarchical:
        return _parse_hierarchical(soup)
    return _parse_flat(soup)


def _extract_label_name(label_el) -> str:
    """Extract 'WashU Fiesta' from: Site <strong>(WashU Fiesta)</strong>"""
    strong = label_el.find("strong")
    if strong is None:
        return label_el.get_text(strip=True)
    text = strong.get_text(strip=True)
    return text.strip("()")


def _parse_hierarchical(soup) -> SiteTree:
    regions: list[Region] = []
    districts: list[District] = []
    sites: list[Site] = []

    for region_input in soup.select("input.boac-permission-region-option"):
        region_id = int(region_input["data-region-id"])
        label_el = soup.select_one(f'label[for="boac-permission-region-{region_id}"]')
        region_name = _extract_label_name(label_el) if label_el else f"Region {region_id}"
        regions.append(Region(id=region_id, name=region_name))

    for district_input in soup.select("input.boac-permission-district-option"):
        district_id = int(district_input["data-district-id"])
        region_id = int(district_input["data-region-id"])
        label_el = soup.select_one(f'label[for="boac-permission-district-{district_id}"]')
        district_name = _extract_label_name(label_el) if label_el else f"District {district_id}"
        districts.append(District(id=district_id, name=district_name, region_id=region_id))

    for site_input in soup.select("input.boac-permission-site-option"):
        site_id = int(site_input["value"])
        # district_id lives in data-district-id; walk up to find region_id via the district record
        district_id = int(site_input.get("data-district-id", 0)) or None
        region_id = None
        if district_id:
            match = next((d for d in districts if d.id == district_id), None)
            if match:
                region_id = match.region_id
        label_el = soup.select_one(f'label[for="boac-permission-site-{site_id}"]')
        site_name = _extract_label_name(label_el) if label_el else f"Site {site_id}"
        sites.append(Site(id=site_id, name=site_name, district_id=district_id, region_id=region_id))

    return SiteTree(is_hierarchical=True, regions=regions, districts=districts, sites=sites)


def _parse_flat(soup) -> SiteTree:
    sites: list[Site] = []
    for site_input in soup.select("input.boac-permission-site-option"):
        site_id = int(site_input["value"])
        label_el = soup.select_one(f'label[for="boac-permission-site-{site_id}"]')
        site_name = _extract_label_name(label_el) if label_el else f"Site {site_id}"
        sites.append(Site(id=site_id, name=site_name))
    return SiteTree(is_hierarchical=False, sites=sites)
```

- [ ] **Step 4: Run — iterate until tests pass**

The specific assertions in the test depend on the real fixture. If the fixture's first site is not "WashU Fiesta" with those IDs, update the test assertions to match. Keep the *structure* of the test, change the expected values.

- [ ] **Step 5: Commit**

```bash
git add src/sonnys_backoffice/sites.py tests/unit/test_sites.py
git commit -m "feat(sites): parse site/region/district tree from /employee/create HTML"
```

### Task 4.2: Departments parser

**Files:**
- Create: `src/sonnys_backoffice/departments.py`
- Create: `tests/unit/test_departments.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_departments.py
from pathlib import Path

from sonnys_backoffice.departments import parse_departments

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html"


def test_parses_departments_from_employee_create_fixture():
    html = (FIXTURES / "employee_create.html").read_text(encoding="utf-8")
    depts = parse_departments(html)
    names = [d.name for d in depts]
    assert "Greeter" in names
    assert all(d.id > 0 for d in depts)
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement `departments.py`**

```python
# src/sonnys_backoffice/departments.py
"""Department list parser."""
from __future__ import annotations

from bs4 import BeautifulSoup

from .models import Department


def parse_departments(html: str) -> list[Department]:
    """Extract the list of departments from the /employee/create page.

    Selectors based on fixtures captured in Phase 1. The exact department
    control — checkbox group, multi-select, or Select2 widget — is confirmed
    by inspecting employee_create.html during implementation. Adjust the
    selector below to match the real markup.
    """
    soup = BeautifulSoup(html, "html.parser")
    depts: list[Department] = []
    # Placeholder selector — update after inspecting the real fixture.
    # Likely candidates: <select name="employee[departments][]"> options,
    # or <input name="employee[departmentIds][]"> checkboxes.
    for opt in soup.select("select[name='employee[departmentIds][]'] option"):
        try:
            dept_id = int(opt.get("value", "0"))
        except ValueError:
            continue
        if dept_id == 0:
            continue
        depts.append(Department(id=dept_id, name=opt.get_text(strip=True)))
    if not depts:
        # Fallback: checkbox-style rendering
        for cb in soup.select("input[name='employee[departmentIds][]']"):
            try:
                dept_id = int(cb.get("value", "0"))
            except ValueError:
                continue
            label = soup.select_one(f"label[for='{cb.get('id', '')}']")
            name = label.get_text(strip=True) if label else f"Department {dept_id}"
            depts.append(Department(id=dept_id, name=name))
    return depts
```

- [ ] **Step 4: Run — iterate selector until tests pass**

Open the fixture, find the actual department control, fix the selector. This is expected — the exact HTML is unknowable until exploration.

- [ ] **Step 5: Commit**

```bash
git add src/sonnys_backoffice/departments.py tests/unit/test_departments.py
git commit -m "feat(departments): parse department list from /employee/create"
```

### Task 4.3: Permissions list parser

**Files:**
- Modify: `src/sonnys_backoffice/permissions.py`
- Create: `tests/unit/test_permissions_parser.py`

- [ ] **Step 1: Write failing tests against captured permissions pages**

```python
# tests/unit/test_permissions_parser.py
from pathlib import Path

from sonnys_backoffice.permissions import parse_permissions

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html"


def test_parses_pos_permissions():
    html = (FIXTURES / "employee_permissions_page.html").read_text(encoding="utf-8")
    perms = parse_permissions(html, scope="pos")
    names = [p.name for p in perms]
    assert "General User" in names
    assert all(p.scope == "pos" for p in perms)
    assert all(p.id > 0 for p in perms)


def test_parses_bo_permissions():
    html = (FIXTURES / "user_permissions_page.html").read_text(encoding="utf-8")
    perms = parse_permissions(html, scope="backoffice")
    names = [p.name for p in perms]
    assert "General User" in names
    assert all(p.scope == "backoffice" for p in perms)
```

- [ ] **Step 2: Run — expect AttributeError / ImportError**

- [ ] **Step 3: Extend `permissions.py`**

Append:

```python
from typing import Literal

from bs4 import BeautifulSoup


def parse_permissions(html: str, *, scope: Literal["pos", "backoffice"]) -> list[Permission]:
    """Extract the permission/role list from a captured permissions page.

    The selector below must match the real markup captured in
    `employee_permissions_page.html` / `user_permissions_page.html`.
    """
    soup = BeautifulSoup(html, "html.parser")
    perms: list[Permission] = []
    # Typical candidates — update after fixture inspection:
    for opt in soup.select("select[name*='permissionId'] option, select[name*='roleId'] option"):
        try:
            pid = int(opt.get("value", "0"))
        except ValueError:
            continue
        if pid == 0:
            continue
        perms.append(Permission(id=pid, name=opt.get_text(strip=True), scope=scope))
    if not perms:
        for radio in soup.select("input[type='radio'][name*='permission']"):
            try:
                pid = int(radio.get("value", "0"))
            except ValueError:
                continue
            label = soup.select_one(f"label[for='{radio.get('id', '')}']")
            name = label.get_text(strip=True) if label else f"Permission {pid}"
            perms.append(Permission(id=pid, name=name, scope=scope))
    return perms
```

- [ ] **Step 4: Run — iterate until tests pass**

- [ ] **Step 5: Commit**

```bash
git add src/sonnys_backoffice/permissions.py tests/unit/test_permissions_parser.py
git commit -m "feat(permissions): parse permission lists from captured HTML"
```

---

## Phase 5: `create_employee`

The centerpiece. Builds on everything from Phases 2-4.

### Task 5.1: Employee step-1 payload builder

**Files:**
- Create: `src/sonnys_backoffice/employees.py`
- Create: `tests/unit/test_employees_build_payload.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_employees_build_payload.py
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sonnys_backoffice.employees import build_employee_step1_payload
from sonnys_backoffice.models import CreateEmployeeRequest, Site
from sonnys_backoffice.sites import SiteTree

FIXTURES_PAYLOADS = Path(__file__).parent.parent / "fixtures" / "payloads"


def _sample_request():
    return CreateEmployeeRequest(
        first_name="Jane",
        last_name="Doe",
        phone="6155551234",
        email="jane@example.com",
        pos_user_id="jdoe1",
        pos_pin="12345",
        wage_rate=Decimal("15.50"),
        start_date=datetime(2026, 5, 1),
        available_sites=["Wash 37135"],
        departments=["Cashier"],
    )


def _sample_tree_flat():
    return SiteTree(
        is_hierarchical=False,
        sites=[Site(id=17, name="Wash 37135")],
    )


def _sample_tree_hierarchical():
    return SiteTree(
        is_hierarchical=True,
        sites=[Site(id=17, name="Wash 37135", district_id=1, region_id=1)],
    )


def test_payload_contains_required_basic_fields():
    req = _sample_request()
    payload = build_employee_step1_payload(req, site_tree=_sample_tree_flat(), departments_by_name={"Cashier": 5, "Greeter": 1})
    assert payload["employee[firstName]"] == "Jane"
    assert payload["employee[lastName]"] == "Doe"
    assert payload["employee[email]"] == "jane@example.com"


def test_payload_flat_tenant_uses_siteIds_list():
    req = _sample_request()
    payload = build_employee_step1_payload(req, site_tree=_sample_tree_flat(), departments_by_name={"Cashier": 5, "Greeter": 1})
    assert "employee[siteIds][]" in payload or payload.get("employee[siteIds][]") is not None


def test_payload_hierarchical_tenant_uses_site_indexed_fields():
    req = _sample_request()
    payload = build_employee_step1_payload(req, site_tree=_sample_tree_hierarchical(), departments_by_name={"Cashier": 5, "Greeter": 1})
    # With hierarchy, each enabled site has sites[<id>][isAvailable] and sites[<id>][siteId]
    assert "employee[sites][17][isAvailable]" in payload or any("sites[17]" in k for k in payload)


def test_payload_matches_recorded_fixture():
    """Structural comparison: payload keys are a subset of fields seen in the live recording."""
    recorded_path = FIXTURES_PAYLOADS / "employee_insert.json"
    if not recorded_path.exists():
        # Fixture not yet captured — this test is skipped during early development
        import pytest
        pytest.skip("employee_insert.json fixture not yet captured")
    recorded = json.loads(recorded_path.read_text())
    recorded_keys = set(_parse_post_data_keys(recorded["post_data"]))

    req = _sample_request()
    payload = build_employee_step1_payload(req, site_tree=_sample_tree_flat(), departments_by_name={"Cashier": 5, "Greeter": 1})
    built_keys = set(payload.keys())
    # Every key the real form sends should also appear in our built payload (modulo hidden CSRF)
    missing = recorded_keys - built_keys - {"_token", "authenticity_token"}
    assert not missing, f"form fields missing from built payload: {missing}"


def _parse_post_data_keys(post_data: str) -> list[str]:
    """Parse a www-form-urlencoded string into its list of keys."""
    from urllib.parse import parse_qsl
    return [k for k, _ in parse_qsl(post_data, keep_blank_values=True)]
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement `employees.py` with `build_employee_step1_payload`**

```python
# src/sonnys_backoffice/employees.py
"""create_employee / disable_employee orchestration and form builders."""
from __future__ import annotations

from typing import Any, Mapping

from .models import CreateEmployeeRequest
from .sites import SiteTree


def build_employee_step1_payload(
    request: CreateEmployeeRequest,
    *,
    site_tree: SiteTree,
    departments_by_name: Mapping[str, int],
) -> dict[str, Any]:
    """Translate a validated CreateEmployeeRequest into the form payload for /employee/insert.

    Field names are sourced from tests/fixtures/payloads/employee_insert.json and
    tests/fixtures/exploration_notes.md captured during Phase 1.
    """
    payload: dict[str, Any] = {
        "employee[firstName]": request.first_name,
        "employee[lastName]": request.last_name,
        "employee[email]": request.email,
        "employee[phone]": request.phone,
        "employee[posUserId]": request.pos_user_id,
        "employee[posPin]": request.pos_pin,
        "employee[wageRate]": str(request.wage_rate),
        "employee[overtimeWageRate]": str(request.overtime_wage_rate),
        "employee[startDate]": request.start_date.strftime("%Y-%m-%d"),
    }
    if request.emergency_contact_name:
        payload["employee[emergencyContactName]"] = request.emergency_contact_name
    if request.emergency_contact_phone:
        payload["employee[emergencyContactPhone]"] = request.emergency_contact_phone

    # Departments
    for dept_name in request.departments or []:
        dept_id = departments_by_name.get(dept_name)
        if dept_id is None:
            continue  # unknown department — soft drop (warning handled in orchestrator)
        payload.setdefault("employee[departmentIds][]", []).append(dept_id)

    # Site availability
    resolved_sites = site_tree.resolve_all(request.available_sites)

    if site_tree.is_hierarchical:
        # Enable regions/districts/sites for each resolved site
        enabled_region_ids = {s.region_id for s in resolved_sites if s.region_id}
        enabled_district_ids = {s.district_id for s in resolved_sites if s.district_id}
        if request.available_sites == "all":
            payload["employee[isAllRegionsAllowed]"] = "1"
        else:
            payload["employee[isAllRegionsAllowed]"] = "0"
            # disabledRegions[] = every region NOT in enabled set
            for region in site_tree.regions:
                if region.id not in enabled_region_ids:
                    payload.setdefault("employee[disabledRegions][]", []).append(region.id)
            for district in site_tree.districts:
                if district.id not in enabled_district_ids:
                    payload.setdefault("employee[disabledDistricts][]", []).append(district.id)
            for site in site_tree.sites:
                is_available = "1" if site.id in {s.id for s in resolved_sites} else "0"
                payload[f"employee[sites][{site.id}][isAvailable]"] = is_available
                payload[f"employee[sites][{site.id}][siteId]"] = site.id
    else:
        # Flat tenant
        if request.available_sites == "all":
            payload["employee[isAllSitesAllowed]"] = "1"
        else:
            payload["employee[isAllSitesAllowed]"] = "0"
            for s in resolved_sites:
                payload.setdefault("employee[siteIds][]", []).append(s.id)

    return payload
```

- [ ] **Step 4: Run — iterate field names until tests pass**

The field names (`employee[firstName]`, `employee[posUserId]`, etc.) are best-guess based on the spec HTML. After Task 1.4 captures the real `employee_insert.json`, replace the guesses with the actual field names. The `test_payload_matches_recorded_fixture` test is the authoritative check.

- [ ] **Step 5: Commit**

```bash
git add src/sonnys_backoffice/employees.py tests/unit/test_employees_build_payload.py
git commit -m "feat(employees): add step-1 form payload builder with hierarchy handling"
```

### Task 5.2: Employee step-2 (permissions) payload builder

**Files:**
- Modify: `src/sonnys_backoffice/employees.py`
- Modify: `tests/unit/test_employees_build_payload.py`

- [ ] **Step 1: Write failing tests**

```python
def test_permissions_payload_includes_role_id():
    from sonnys_backoffice.employees import build_employee_step2_permissions_payload
    from sonnys_backoffice.models import Permission

    perm = Permission(id=7, name="General User", scope="pos")
    payload = build_employee_step2_permissions_payload(permission=perm, employee_id=42)
    # Field name confirmed from fixtures
    assert payload.get("employee[permissionId]") == 7 or any("permissionId" in k for k in payload)
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement**

Append to `employees.py`:

```python
from .models import Permission


def build_employee_step2_permissions_payload(
    *,
    permission: Permission,
    employee_id: int,
) -> dict[str, Any]:
    """Build the permissions-page POST payload. Field name sourced from fixtures."""
    return {
        "employee[permissionId]": permission.id,
        "employee[id]": employee_id,
    }
```

- [ ] **Step 4: Run — pass**

- [ ] **Step 5: Commit**

```bash
git add src/sonnys_backoffice/employees.py tests/unit/test_employees_build_payload.py
git commit -m "feat(employees): add step-2 permissions payload builder"
```

### Task 5.3: `create_employee` orchestrator (POS-only path)

**Files:**
- Modify: `src/sonnys_backoffice/employees.py`
- Create: `tests/unit/test_employees_create.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_employees_create.py
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

from sonnys_backoffice.employees import create_employee
from sonnys_backoffice.models import (
    CreateEmployeeRequest,
    Department,
    EmployeeCreated,
    Permission,
    Site,
)
from sonnys_backoffice.sites import SiteTree


def _make_session_and_resolvers(employee_id: int = 42):
    session = MagicMock()
    insert_resp = MagicMock()
    insert_resp.status_code = 302
    insert_resp.headers = {"Location": f"/employee/{employee_id}/permissions"}
    insert_resp.url = f"https://washu.sonnyscontrols.com/employee/{employee_id}/permissions"
    insert_resp.text = f'<html><input name="employee[id]" value="{employee_id}"></html>'

    perms_resp = MagicMock()
    perms_resp.status_code = 302
    perms_resp.text = "<html>ok</html>"

    session.post.side_effect = [insert_resp, perms_resp]

    site_tree = SiteTree(
        is_hierarchical=False,
        sites=[Site(id=17, name="Wash 37135")],
    )
    departments = [Department(id=1, name="Greeter"), Department(id=5, name="Cashier")]
    permissions = [Permission(id=7, name="General User", scope="pos")]
    return session, site_tree, departments, permissions


def test_create_employee_pos_only_returns_result():
    session, tree, depts, perms = _make_session_and_resolvers(employee_id=42)
    req = CreateEmployeeRequest(
        first_name="Jane",
        last_name="Doe",
        phone="6155551234",
        email="jane@example.com",
        pos_user_id="jdoe",
        pos_pin="12345",
        wage_rate=Decimal("15.00"),
        start_date=datetime(2026, 5, 1),
        available_sites=["Wash 37135"],
    )
    result = create_employee(
        session=session,
        request=req,
        site_tree=tree,
        departments=depts,
        pos_permissions=perms,
        bo_permissions=[],
    )
    assert isinstance(result, EmployeeCreated)
    assert result.employee_id == 42
    assert result.pos_user_id == "jdoe"
    assert result.pos_pin == "12345"
    assert result.permission_applied == "General User"
    assert session.post.call_count == 2  # step 1 + step 2


def test_create_employee_generates_pin_if_not_provided():
    session, tree, depts, perms = _make_session_and_resolvers(employee_id=42)
    req = CreateEmployeeRequest(
        first_name="Jane",
        last_name="Doe",
        phone="6155551234",
        email="jane@example.com",
        pos_user_id="jdoe",
        wage_rate=Decimal("15.00"),
        start_date=datetime(2026, 5, 1),
        available_sites="all",
    )
    result = create_employee(
        session=session,
        request=req,
        site_tree=tree,
        departments=depts,
        pos_permissions=perms,
        bo_permissions=[],
    )
    assert len(result.pos_pin) == 5
    assert result.pos_pin.isdigit()
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement `create_employee` in `employees.py`**

Append:

```python
import re

from .exceptions import BackofficeServerError, DuplicateError, ValidationError
from .models import Department, EmployeeCreated, Permission
from .passwords import generate_pos_pin


def create_employee(
    *,
    session: Any,  # _BackofficeSession — typed as Any to avoid circular imports
    request: CreateEmployeeRequest,
    site_tree: SiteTree,
    departments: list[Department],
    pos_permissions: list[Permission],
    bo_permissions: list[Permission],
) -> EmployeeCreated:
    """Orchestrate the two-step employee creation flow."""
    from .permissions import resolve_permission

    warnings_list: list[str] = []

    # Generate POS PIN if needed
    pos_pin = request.pos_pin or generate_pos_pin()
    # Build a request object with the resolved PIN. Pydantic models are immutable
    # after construction; use model_copy.
    resolved_request = request.model_copy(update={"pos_pin": pos_pin})

    # Resolve permission
    pos_perm, perm_warnings = resolve_permission(request.permission, pos_permissions)
    warnings_list.extend(perm_warnings)

    # Departments lookup table
    departments_by_name = {d.name: d.id for d in departments}

    # Step 1: POST /employee/insert
    step1_payload = build_employee_step1_payload(
        resolved_request,
        site_tree=site_tree,
        departments_by_name=departments_by_name,
    )
    resp1 = session.post("/employee/insert", data=step1_payload)
    _check_create_response(resp1)
    employee_id = _extract_employee_id_from_response(resp1)

    # Step 2: POST permissions
    permissions_url = _permissions_url_from_response(resp1, employee_id)
    step2_payload = build_employee_step2_permissions_payload(
        permission=pos_perm, employee_id=employee_id
    )
    resp2 = session.post(permissions_url, data=step2_payload)
    _check_create_response(resp2)

    # Build result (POS-only path — BO-user path added in Task 5.4)
    return EmployeeCreated(
        employee_id=employee_id,
        pos_user_id=resolved_request.pos_user_id,
        pos_pin=pos_pin,
        first_name=resolved_request.first_name,
        last_name=resolved_request.last_name,
        email=resolved_request.email,
        permission_applied=pos_perm.name,
        sites_granted=[s.name for s in site_tree.resolve_all(resolved_request.available_sites)],
        departments=list(resolved_request.departments or []),
        warnings=warnings_list,
    )


def _check_create_response(resp) -> None:
    if resp.status_code >= 500:
        raise BackofficeServerError(f"server error: HTTP {resp.status_code}")
    # Error signals in the HTML (e.g., "already exists") — patterns sourced from fixtures
    text = getattr(resp, "text", "") or ""
    if "already exists" in text.lower() or "already taken" in text.lower():
        raise DuplicateError("record with this email or POS User ID already exists")
    if "has-error" in text and "field-required" in text:
        raise ValidationError("Backoffice rejected the submission — see response for details")


def _extract_employee_id_from_response(resp) -> int:
    """Pull the new employee_id out of the step-1 response.

    The server redirects to /employee/<id>/permissions or embeds the id in the body.
    Both strategies are tried in order.
    """
    # Strategy 1: Location header
    location = resp.headers.get("Location", "") if hasattr(resp, "headers") else ""
    m = re.search(r"/employee/(\d+)/", location or getattr(resp, "url", ""))
    if m:
        return int(m.group(1))

    # Strategy 2: hidden input in the response body
    text = getattr(resp, "text", "") or ""
    m = re.search(r'name="employee\[id\]"\s+value="(\d+)"', text)
    if m:
        return int(m.group(1))

    raise BackofficeServerError(
        "could not extract new employee_id from /employee/insert response"
    )


def _permissions_url_from_response(resp, employee_id: int) -> str:
    """Derive the step-2 permissions-page URL from the step-1 response."""
    location = resp.headers.get("Location", "") if hasattr(resp, "headers") else ""
    if "/permissions" in location:
        return location
    if "/permissions" in getattr(resp, "url", ""):
        return resp.url
    # Fallback: canonical pattern (confirmed from fixtures)
    return f"/employee/{employee_id}/permissions"
```

- [ ] **Step 4: Run — iterate until tests pass**

Real URL patterns and error phrases come from `exploration_notes.md`. Update `_extract_employee_id_from_response` and `_check_create_response` as needed after Phase 1 completes.

- [ ] **Step 5: Commit**

```bash
git add src/sonnys_backoffice/employees.py tests/unit/test_employees_create.py
git commit -m "feat(employees): create_employee orchestrator for POS-only path"
```

### Task 5.4: `create_employee` — linked BO user path

**Files:**
- Modify: `src/sonnys_backoffice/employees.py`
- Modify: `tests/unit/test_employees_create.py`

- [ ] **Step 1: Write failing test**

```python
def test_create_employee_with_backoffice_user():
    session, tree, depts, perms = _make_session_and_resolvers(employee_id=42)
    # Additional mock responses for the BO user creation calls
    bo_insert_resp = MagicMock()
    bo_insert_resp.status_code = 302
    bo_insert_resp.headers = {"Location": "/user/99/permissions"}
    bo_insert_resp.url = "https://washu.sonnyscontrols.com/user/99/permissions"
    bo_insert_resp.text = '<html><input name="user[id]" value="99"></html>'
    bo_perms_resp = MagicMock()
    bo_perms_resp.status_code = 302
    bo_perms_resp.text = "<html>ok</html>"
    session.post.side_effect = [
        MagicMock(status_code=302, headers={"Location": "/employee/42/permissions"}, url="https://washu.sonnyscontrols.com/employee/42/permissions", text='<input name="employee[id]" value="42">'),
        MagicMock(status_code=302, text="<html>ok</html>"),
        bo_insert_resp,
        bo_perms_resp,
    ]
    bo_perms = [Permission(id=7, name="General User", scope="backoffice")]

    req = CreateEmployeeRequest(
        first_name="Jane",
        last_name="Doe",
        phone="6155551234",
        email="jane@example.com",
        pos_user_id="jdoe",
        wage_rate=Decimal("15.00"),
        start_date=datetime(2026, 5, 1),
        available_sites="all",
        requires_backoffice=True,
        backoffice_username="janedoe",
    )
    result = create_employee(
        session=session,
        request=req,
        site_tree=tree,
        departments=depts,
        pos_permissions=perms,
        bo_permissions=bo_perms,
    )
    assert result.backoffice_user_id == 99
    assert result.backoffice_username == "janedoe"
    assert result.backoffice_password is not None
    assert len(result.backoffice_password) == 12
    assert session.post.call_count == 4
```

- [ ] **Step 2: Run — expect failure (BO path not implemented)**

- [ ] **Step 3: Extend `create_employee` with the BO branch**

Replace the function's post-step-2 return with:

```python
    # BO user path
    bo_user_id: int | None = None
    bo_password: str | None = None
    if resolved_request.requires_backoffice:
        from .bo_users import create_linked_backoffice_user  # local import to avoid cycles

        bo_perm, bo_warnings = resolve_permission(resolved_request.permission, bo_permissions)
        warnings_list.extend(bo_warnings)
        bo_result = create_linked_backoffice_user(
            session=session,
            username=resolved_request.backoffice_username,
            email=resolved_request.email,
            password=resolved_request.backoffice_password,
            linked_employee_id=employee_id,
            permission=bo_perm,
            site_tree=site_tree,
            available_sites=resolved_request.available_sites,
        )
        bo_user_id = bo_result.user_id
        bo_password = bo_result.password

    return EmployeeCreated(
        employee_id=employee_id,
        pos_user_id=resolved_request.pos_user_id,
        pos_pin=pos_pin,
        first_name=resolved_request.first_name,
        last_name=resolved_request.last_name,
        email=resolved_request.email,
        backoffice_user_id=bo_user_id,
        backoffice_username=resolved_request.backoffice_username,
        backoffice_password=bo_password,
        permission_applied=pos_perm.name,
        sites_granted=[s.name for s in site_tree.resolve_all(resolved_request.available_sites)],
        departments=list(resolved_request.departments or []),
        warnings=warnings_list,
    )
```

`create_linked_backoffice_user` is implemented in Phase 7. For now, stub it so this task's tests can run — it will be filled in during Task 7.1.

- [ ] **Step 4: Add a stub `src/sonnys_backoffice/bo_users.py`**

```python
# src/sonnys_backoffice/bo_users.py
"""Backoffice user creation — linked and standalone modes."""
from __future__ import annotations

from typing import Any

from .models import BackofficeUserCreated, Permission
from .passwords import generate_bo_password
from .sites import SiteTree


def create_linked_backoffice_user(
    *,
    session: Any,
    username: str,
    email: str,
    password: str | None,
    linked_employee_id: int,
    permission: Permission,
    site_tree: SiteTree,
    available_sites,
) -> BackofficeUserCreated:
    """Create a Backoffice user linked to an existing employee. Stub — full impl in Phase 7."""
    pwd = password or generate_bo_password()
    # Minimal stub: POST step 1, POST step 2 (permissions), return result.
    # Full field-level payload handled in Task 7.1.
    step1 = {
        "employee[isOnSiteEmployee]": "1",
        "user[employeeId]": linked_employee_id,
        "user[username]": username,
        "user[password]": pwd,
        "user[confirmPassword]": pwd,
        "employee[email]": email,
    }
    resp1 = session.post("/user/insert", data=step1)
    # Extract user id
    import re
    m = re.search(r"/user/(\d+)/", (resp1.headers.get("Location", "") or "") + (getattr(resp1, "url", "") or ""))
    if not m:
        m = re.search(r'name="user\[id\]"\s+value="(\d+)"', getattr(resp1, "text", "") or "")
    user_id = int(m.group(1)) if m else 0

    step2 = {"user[permissionId]": permission.id, "user[id]": user_id}
    resp2 = session.post(f"/user/{user_id}/permissions", data=step2)

    return BackofficeUserCreated(
        user_id=user_id,
        username=username,
        password=pwd,
        email=email,
        linked_employee_id=linked_employee_id,
        permission_applied=permission.name,
        sites_granted=[s.name for s in site_tree.resolve_all(available_sites)],
    )
```

- [ ] **Step 5: Run tests — expect pass**

- [ ] **Step 6: Commit**

```bash
git add src/sonnys_backoffice/employees.py src/sonnys_backoffice/bo_users.py tests/unit/test_employees_create.py
git commit -m "feat(employees): support requires_backoffice=True via linked BO user creation"
```

---

## Phase 6: `disable_employee`

### Task 6.1: Employee lookup by POS User ID or email

**Files:**
- Modify: `src/sonnys_backoffice/employees.py`
- Create: `tests/unit/test_employees_lookup.py`

- [ ] **Step 1: Write failing tests against captured `employee_list.html`**

```python
# tests/unit/test_employees_lookup.py
from pathlib import Path

import pytest

from sonnys_backoffice.employees import find_employee_in_list_html
from sonnys_backoffice.exceptions import NotFoundError

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html"


def test_find_by_pos_user_id():
    html = (FIXTURES / "employee_list.html").read_text(encoding="utf-8")
    # Pick a POS User ID that the fixture is known to contain — captured in exploration_notes.md
    employee_id = find_employee_in_list_html(html, pos_user_id="SOME_REAL_POS_ID")
    assert employee_id > 0


def test_find_by_email():
    html = (FIXTURES / "employee_list.html").read_text(encoding="utf-8")
    employee_id = find_employee_in_list_html(html, email="some-real@example.com")
    assert employee_id > 0


def test_not_found_raises():
    html = (FIXTURES / "employee_list.html").read_text(encoding="utf-8")
    with pytest.raises(NotFoundError):
        find_employee_in_list_html(html, pos_user_id="definitely-not-a-real-id-xyz")
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement `find_employee_in_list_html`**

Append to `employees.py`:

```python
from bs4 import BeautifulSoup

from .exceptions import NotFoundError


def find_employee_in_list_html(
    html: str,
    *,
    pos_user_id: str | None = None,
    email: str | None = None,
) -> int:
    """Scan /employee list HTML for a row matching the lookup key, return employee_id.

    Selectors based on employee_list.html captured in Phase 1. Adjust row/cell
    selectors to match the real table structure.
    """
    if not (pos_user_id or email):
        raise ValueError("pos_user_id or email is required")

    soup = BeautifulSoup(html, "html.parser")
    # Candidate selectors — one of these should match after inspection:
    rows = soup.select("tr[data-employee-id], tr.employee-row, table.employees tbody tr")

    for row in rows:
        row_id = row.get("data-employee-id") or row.get("data-id")
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        row_text = " ".join(cells).lower()
        match = False
        if pos_user_id and pos_user_id.lower() in row_text:
            match = True
        if email and email.lower() in row_text:
            match = True
        if match and row_id:
            try:
                return int(row_id)
            except ValueError:
                continue

    raise NotFoundError(
        f"no employee found for {'pos_user_id=' + pos_user_id if pos_user_id else 'email=' + (email or '')}"
    )
```

- [ ] **Step 4: Run — iterate selectors and update test fixture values**

Open `employee_list.html`, find a real row, copy its data attributes into both the implementation selectors and the test's expected values.

- [ ] **Step 5: Commit**

```bash
git add src/sonnys_backoffice/employees.py tests/unit/test_employees_lookup.py
git commit -m "feat(employees): parse employee list HTML to find by pos_user_id/email"
```

### Task 6.2: `disable_employee` orchestrator

**Files:**
- Modify: `src/sonnys_backoffice/employees.py`
- Create: `tests/unit/test_employees_disable.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_employees_disable.py
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from sonnys_backoffice.employees import disable_employee
from sonnys_backoffice.models import DisableEmployeeRequest, EmployeeDisabled

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html"


def test_disable_employee_by_pos_user_id():
    session = MagicMock()
    list_resp = MagicMock()
    list_resp.text = (FIXTURES / "employee_list.html").read_text(encoding="utf-8")
    list_resp.status_code = 200
    disable_resp = MagicMock()
    disable_resp.status_code = 302
    disable_resp.text = "<html>ok</html>"
    session.get.return_value = list_resp
    session.post.return_value = disable_resp

    req = DisableEmployeeRequest(pos_user_id="SOME_REAL_POS_ID")
    result = disable_employee(session=session, request=req)

    assert isinstance(result, EmployeeDisabled)
    assert result.pos_user_id == "SOME_REAL_POS_ID"
    assert isinstance(result.disabled_at, datetime)
    session.post.assert_called_once()
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement `disable_employee`**

Append to `employees.py`:

```python
from datetime import datetime, timezone

from .models import DisableEmployeeRequest, EmployeeDisabled


def disable_employee(
    *,
    session: Any,
    request: DisableEmployeeRequest,
) -> EmployeeDisabled:
    """Disable an existing employee looked up by POS User ID or email."""
    # Step 1: find the employee_id from the list page
    list_resp = session.get("/employee")
    _check_create_response(list_resp)
    employee_id = find_employee_in_list_html(
        list_resp.text,
        pos_user_id=request.pos_user_id,
        email=request.email,
    )

    # Step 2: POST the disable action
    # URL and payload shape sourced from fixtures — update after Phase 1
    disable_payload = {"employee[id]": employee_id, "employee[isDisabled]": "1"}
    disable_resp = session.post(f"/employee/{employee_id}/disable", data=disable_payload)
    _check_create_response(disable_resp)

    return EmployeeDisabled(
        employee_id=employee_id,
        pos_user_id=request.pos_user_id or "",
        email=request.email,
        disabled_at=datetime.now(timezone.utc),
    )
```

- [ ] **Step 4: Run — pass**

- [ ] **Step 5: Commit**

```bash
git add src/sonnys_backoffice/employees.py tests/unit/test_employees_disable.py
git commit -m "feat(employees): disable_employee orchestrator"
```

---

## Phase 7: `create_backoffice_user` (standalone + full linked)

### Task 7.1: Standalone BO user creation

**Files:**
- Modify: `src/sonnys_backoffice/bo_users.py`
- Create: `tests/unit/test_bo_users_standalone.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_bo_users_standalone.py
from unittest.mock import MagicMock

from sonnys_backoffice.bo_users import create_standalone_backoffice_user
from sonnys_backoffice.models import BackofficeUserCreated, CreateBackofficeUserRequest, Permission, Site
from sonnys_backoffice.sites import SiteTree


def test_create_standalone_bo_user():
    session = MagicMock()
    insert_resp = MagicMock()
    insert_resp.status_code = 302
    insert_resp.headers = {"Location": "/user/99/permissions"}
    insert_resp.url = "https://washu.sonnyscontrols.com/user/99/permissions"
    insert_resp.text = '<input name="user[id]" value="99">'
    perms_resp = MagicMock()
    perms_resp.status_code = 302
    perms_resp.text = "<html>ok</html>"
    session.post.side_effect = [insert_resp, perms_resp]

    tree = SiteTree(is_hierarchical=False, sites=[Site(id=1, name="Nolensville")])
    perm = Permission(id=7, name="Administrator", scope="backoffice")

    req = CreateBackofficeUserRequest(
        username="districtmgr",
        email="mgr@example.com",
        first_name="District",
        last_name="Manager",
        permission="Administrator",
    )
    result = create_standalone_backoffice_user(
        session=session,
        request=req,
        site_tree=tree,
        bo_permissions=[perm],
    )
    assert isinstance(result, BackofficeUserCreated)
    assert result.user_id == 99
    assert result.linked_employee_id is None
    assert len(result.password) == 12
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement `create_standalone_backoffice_user`**

Replace the stub in `bo_users.py`:

```python
# src/sonnys_backoffice/bo_users.py
"""Backoffice user creation — linked and standalone modes."""
from __future__ import annotations

import re
from typing import Any, Literal

from .exceptions import BackofficeServerError, DuplicateError
from .models import (
    BackofficeUserCreated,
    CreateBackofficeUserRequest,
    Permission,
)
from .passwords import generate_bo_password
from .sites import SiteTree


def create_standalone_backoffice_user(
    *,
    session: Any,
    request: CreateBackofficeUserRequest,
    site_tree: SiteTree,
    bo_permissions: list[Permission],
) -> BackofficeUserCreated:
    """Create a standalone (not employee-linked) Backoffice user."""
    from .permissions import resolve_permission

    warnings_list: list[str] = []
    pwd = request.password or generate_bo_password()
    perm, perm_warnings = resolve_permission(request.permission, bo_permissions)
    warnings_list.extend(perm_warnings)

    step1 = _build_bo_user_step1_standalone(request, password=pwd)
    resp1 = session.post("/user/insert", data=step1)
    _check_response(resp1)
    user_id = _extract_user_id(resp1)

    step2 = _build_bo_user_step2(user_id=user_id, permission=perm, site_tree=site_tree, available_sites=request.available_sites)
    resp2 = session.post(f"/user/{user_id}/permissions", data=step2)
    _check_response(resp2)

    return BackofficeUserCreated(
        user_id=user_id,
        username=request.username,
        password=pwd,
        email=request.email,
        linked_employee_id=None,
        permission_applied=perm.name,
        sites_granted=[s.name for s in site_tree.resolve_all(request.available_sites)],
        warnings=warnings_list,
    )


def create_linked_backoffice_user(
    *,
    session: Any,
    username: str,
    email: str,
    password: str | None,
    linked_employee_id: int,
    permission: Permission,
    site_tree: SiteTree,
    available_sites: list[str] | Literal["all"],
) -> BackofficeUserCreated:
    """Create a Backoffice user linked to an existing employee."""
    pwd = password or generate_bo_password()
    step1 = {
        "employee[isOnSiteEmployee]": "1",
        "user[employeeId]": linked_employee_id,
        "user[username]": username,
        "user[password]": pwd,
        "user[confirmPassword]": pwd,
        "employee[email]": email,
    }
    resp1 = session.post("/user/insert", data=step1)
    _check_response(resp1)
    user_id = _extract_user_id(resp1)

    step2 = _build_bo_user_step2(user_id=user_id, permission=permission, site_tree=site_tree, available_sites=available_sites)
    resp2 = session.post(f"/user/{user_id}/permissions", data=step2)
    _check_response(resp2)

    return BackofficeUserCreated(
        user_id=user_id,
        username=username,
        password=pwd,
        email=email,
        linked_employee_id=linked_employee_id,
        permission_applied=permission.name,
        sites_granted=[s.name for s in site_tree.resolve_all(available_sites)],
    )


def _build_bo_user_step1_standalone(request: CreateBackofficeUserRequest, *, password: str) -> dict[str, Any]:
    return {
        "employee[isOnSiteEmployee]": "0",
        "employee[firstName]": request.first_name,
        "employee[lastName]": request.last_name,
        "employee[email]": request.email,
        "user[username]": request.username,
        "user[password]": password,
        "user[confirmPassword]": password,
    }


def _build_bo_user_step2(
    *,
    user_id: int,
    permission: Permission,
    site_tree: SiteTree,
    available_sites: list[str] | Literal["all"],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "user[id]": user_id,
        "user[permissionId]": permission.id,
    }
    resolved = site_tree.resolve_all(available_sites)
    if site_tree.is_hierarchical:
        if available_sites == "all":
            payload["user[isAllRegionsAllowed]"] = "1"
        else:
            payload["user[isAllRegionsAllowed]"] = "0"
            enabled_ids = {s.id for s in resolved}
            for s in site_tree.sites:
                payload[f"user[sites][{s.id}][isAvailable]"] = "1" if s.id in enabled_ids else "0"
                payload[f"user[sites][{s.id}][siteId]"] = s.id
    else:
        if available_sites == "all":
            payload["user[isAllSitesAllowed]"] = "1"
        else:
            payload["user[isAllSitesAllowed]"] = "0"
            for s in resolved:
                payload.setdefault("user[siteIds][]", []).append(s.id)
    return payload


def _extract_user_id(resp) -> int:
    location = resp.headers.get("Location", "") if hasattr(resp, "headers") else ""
    m = re.search(r"/user/(\d+)/", (location or "") + (getattr(resp, "url", "") or ""))
    if m:
        return int(m.group(1))
    m = re.search(r'name="user\[id\]"\s+value="(\d+)"', getattr(resp, "text", "") or "")
    if m:
        return int(m.group(1))
    raise BackofficeServerError("could not extract new user_id from /user/insert response")


def _check_response(resp) -> None:
    if resp.status_code >= 500:
        raise BackofficeServerError(f"server error: HTTP {resp.status_code}")
    text = getattr(resp, "text", "") or ""
    if "already exists" in text.lower() or "already taken" in text.lower():
        raise DuplicateError("username or email already exists")
```

- [ ] **Step 4: Run — pass**

- [ ] **Step 5: Commit**

```bash
git add src/sonnys_backoffice/bo_users.py tests/unit/test_bo_users_standalone.py
git commit -m "feat(bo_users): add standalone create_backoffice_user path"
```

---

## Phase 8: Public Façade — `SonnysBackofficeClient`

### Task 8.1: Client class that ties everything together

**Files:**
- Create: `src/sonnys_backoffice/client.py`
- Modify: `src/sonnys_backoffice/__init__.py`
- Create: `tests/unit/test_client_facade.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_client_facade.py
from unittest.mock import MagicMock, patch

from sonnys_backoffice import SonnysBackofficeClient


def test_client_lazy_login():
    client = SonnysBackofficeClient(subdomain="washu", username="u", password="p")
    assert client._session._logged_in is False


def test_client_context_manager_closes_session():
    with patch("sonnys_backoffice.client._BackofficeSession") as mock_session_cls:
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        with SonnysBackofficeClient(subdomain="washu", username="u", password="p") as client:
            pass
        mock_session.close.assert_called_once()


def test_client_list_sites_caches():
    with patch("sonnys_backoffice.client._BackofficeSession") as mock_session_cls:
        mock_session = MagicMock()
        get_resp = MagicMock()
        get_resp.text = '<html><input class="boac-permission-site-option" value="1"><label for="boac-permission-site-1">Site <strong>(Test)</strong></label></html>'
        get_resp.status_code = 200
        mock_session.get.return_value = get_resp
        mock_session_cls.return_value = mock_session
        client = SonnysBackofficeClient(subdomain="washu", username="u", password="p")
        sites1 = client.list_sites()
        sites2 = client.list_sites()
        assert sites1 == sites2
        assert mock_session.get.call_count == 1  # cached
        sites3 = client.list_sites(refresh=True)
        assert mock_session.get.call_count == 2
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement `client.py`**

```python
# src/sonnys_backoffice/client.py
"""Public SonnysBackofficeClient façade."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from .bo_users import create_standalone_backoffice_user
from .departments import parse_departments
from .employees import create_employee as _create_employee
from .employees import disable_employee as _disable_employee
from .models import (
    BackofficeUserCreated,
    CreateBackofficeUserRequest,
    CreateEmployeeRequest,
    Department,
    DisableEmployeeRequest,
    EmployeeCreated,
    EmployeeDisabled,
    Permission,
    Site,
)
from .permissions import parse_permissions
from .session import _BackofficeSession
from .sites import SiteTree, parse_site_tree


class SonnysBackofficeClient:
    """Programmatic access to Sonny's Backoffice user management."""

    def __init__(
        self,
        *,
        subdomain: str,
        username: str,
        password: str,
        timeout: float = 30.0,
        max_retries: int = 2,
        user_agent: str | None = None,
    ) -> None:
        self._session = _BackofficeSession(
            subdomain=subdomain,
            username=username,
            password=password,
            timeout=timeout,
            user_agent=user_agent,
        )
        self._site_tree: SiteTree | None = None
        self._departments: list[Department] | None = None
        self._pos_permissions: list[Permission] | None = None
        self._bo_permissions: list[Permission] | None = None

    def __enter__(self) -> "SonnysBackofficeClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._session.close()

    # ── Discovery ─────────────────────────────────────────────────

    def list_sites(self, *, refresh: bool = False) -> list[Site]:
        if refresh or self._site_tree is None:
            resp = self._session.get("/employee/create")
            self._site_tree = parse_site_tree(resp.text)
        return list(self._site_tree.sites)

    def list_departments(self, *, refresh: bool = False) -> list[Department]:
        if refresh or self._departments is None:
            resp = self._session.get("/employee/create")
            self._departments = parse_departments(resp.text)
        return list(self._departments)

    def list_permissions(
        self,
        *,
        scope: Literal["pos", "backoffice"],
        refresh: bool = False,
    ) -> list[Permission]:
        cache = self._pos_permissions if scope == "pos" else self._bo_permissions
        if refresh or cache is None:
            # Permissions are only visible on the Set Permissions page, reached after
            # creating a throwaway record — but during discovery we fetch the create
            # page and scrape the list if it's embedded, or fall back to a known URL.
            url = "/employee/create" if scope == "pos" else "/user/create"
            resp = self._session.get(url)
            parsed = parse_permissions(resp.text, scope=scope)
            if scope == "pos":
                self._pos_permissions = parsed
            else:
                self._bo_permissions = parsed
            return list(parsed)
        return list(cache)

    def _ensure_caches(self) -> None:
        if self._site_tree is None:
            self.list_sites()
        if self._departments is None:
            self.list_departments()
        if self._pos_permissions is None:
            self.list_permissions(scope="pos")
        if self._bo_permissions is None:
            self.list_permissions(scope="backoffice")

    # ── Employee operations ──────────────────────────────────────

    def create_employee(
        self,
        *,
        first_name: str,
        last_name: str,
        phone: str,
        email: str,
        pos_user_id: str,
        pos_pin: str | None = None,
        wage_rate: Decimal | float,
        overtime_wage_rate: Decimal | float | None = None,
        start_date: datetime,
        available_sites: list[str] | Literal["all"],
        departments: list[str] | None = None,
        permission: str = "General User",
        emergency_contact_name: str | None = None,
        emergency_contact_phone: str | None = None,
        requires_backoffice: bool = False,
        backoffice_username: str | None = None,
        backoffice_password: str | None = None,
    ) -> EmployeeCreated:
        self._ensure_caches()
        req = CreateEmployeeRequest(
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
            pos_user_id=pos_user_id,
            pos_pin=pos_pin,
            wage_rate=Decimal(str(wage_rate)),
            overtime_wage_rate=Decimal(str(overtime_wage_rate)) if overtime_wage_rate is not None else None,
            start_date=start_date,
            available_sites=available_sites,
            departments=departments,
            permission=permission,
            emergency_contact_name=emergency_contact_name,
            emergency_contact_phone=emergency_contact_phone,
            requires_backoffice=requires_backoffice,
            backoffice_username=backoffice_username,
            backoffice_password=backoffice_password,
        )
        return _create_employee(
            session=self._session,
            request=req,
            site_tree=self._site_tree,
            departments=self._departments,
            pos_permissions=self._pos_permissions,
            bo_permissions=self._bo_permissions,
        )

    def disable_employee(
        self,
        *,
        pos_user_id: str | None = None,
        email: str | None = None,
    ) -> EmployeeDisabled:
        req = DisableEmployeeRequest(pos_user_id=pos_user_id, email=email)
        return _disable_employee(session=self._session, request=req)

    def create_backoffice_user(
        self,
        *,
        username: str,
        email: str,
        password: str | None = None,
        permission: str = "General User",
        link_to_employee_pos_user_id: str | None = None,
        link_to_employee_email: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        available_sites: list[str] | Literal["all"] = "all",
    ) -> BackofficeUserCreated:
        self._ensure_caches()
        req = CreateBackofficeUserRequest(
            username=username,
            email=email,
            password=password,
            permission=permission,
            link_to_employee_pos_user_id=link_to_employee_pos_user_id,
            link_to_employee_email=link_to_employee_email,
            first_name=first_name,
            last_name=last_name,
            available_sites=available_sites,
        )
        # Linked-mode: look up employee_id first, then delegate to create_linked_backoffice_user
        # Standalone: delegate straight to create_standalone_backoffice_user
        if req.link_to_employee_pos_user_id or req.link_to_employee_email:
            from .bo_users import create_linked_backoffice_user
            from .employees import find_employee_in_list_html
            from .permissions import resolve_permission

            list_resp = self._session.get("/employee")
            employee_id = find_employee_in_list_html(
                list_resp.text,
                pos_user_id=req.link_to_employee_pos_user_id,
                email=req.link_to_employee_email,
            )
            bo_perm, _ = resolve_permission(req.permission, self._bo_permissions)
            return create_linked_backoffice_user(
                session=self._session,
                username=req.username,
                email=req.email,
                password=req.password,
                linked_employee_id=employee_id,
                permission=bo_perm,
                site_tree=self._site_tree,
                available_sites=req.available_sites,
            )
        return create_standalone_backoffice_user(
            session=self._session,
            request=req,
            site_tree=self._site_tree,
            bo_permissions=self._bo_permissions,
        )
```

- [ ] **Step 4: Update `src/sonnys_backoffice/__init__.py`**

```python
"""Sonny's Backoffice Wrapper — programmatic user management for Sonny's Carwash Controls Backoffice."""

from .client import SonnysBackofficeClient
from .exceptions import (
    AuthenticationError,
    BackofficeServerError,
    DuplicateError,
    NotFoundError,
    PermissionDeniedError,
    SonnysBackofficeError,
    ValidationError,
)
from .models import (
    BackofficeUserCreated,
    Department,
    EmployeeCreated,
    EmployeeDisabled,
    Permission,
    Region,
    Site,
)

__version__ = "0.1.0"

__all__ = [
    "SonnysBackofficeClient",
    "SonnysBackofficeError",
    "AuthenticationError",
    "NotFoundError",
    "ValidationError",
    "PermissionDeniedError",
    "DuplicateError",
    "BackofficeServerError",
    "EmployeeCreated",
    "BackofficeUserCreated",
    "EmployeeDisabled",
    "Site",
    "Region",
    "Department",
    "Permission",
    "__version__",
]
```

- [ ] **Step 5: Run all unit tests**

```bash
pytest tests/unit/ -v
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/sonnys_backoffice/client.py src/sonnys_backoffice/__init__.py tests/unit/test_client_facade.py
git commit -m "feat(client): add SonnysBackofficeClient public façade"
```

---

## Phase 9: Documentation Site

### Task 9.1: MkDocs scaffolding

**Files:**
- Create: `mkdocs.yml`
- Create: `docs/index.md`
- Create: `docs/getting-started/installation.md`
- Create: `docs/getting-started/quickstart.md`
- Create: `docs/getting-started/auth.md`

- [ ] **Step 1: Write `mkdocs.yml`**

```yaml
site_name: Sonny's Backoffice Wrapper
site_url: https://christopher-nance.github.io/Sonnys-Backoffice-Wrapper/
site_description: Programmatic user management for Sonny's Carwash Controls Backoffice
repo_url: https://github.com/christopher-nance/Sonnys-Backoffice-Wrapper
repo_name: christopher-nance/Sonnys-Backoffice-Wrapper

theme:
  name: material
  features:
    - navigation.tabs
    - navigation.sections
    - navigation.expand
    - navigation.top
    - content.code.copy
    - content.code.annotate
  palette:
    - media: "(prefers-color-scheme: light)"
      scheme: default
      primary: blue
      toggle:
        icon: material/brightness-7
        name: Switch to dark mode
    - media: "(prefers-color-scheme: dark)"
      scheme: slate
      primary: blue
      toggle:
        icon: material/brightness-4
        name: Switch to light mode

plugins:
  - search
  - mkdocstrings:
      handlers:
        python:
          options:
            show_source: false
            show_root_heading: true
            members_order: source
            docstring_style: google

markdown_extensions:
  - admonition
  - pymdownx.details
  - pymdownx.highlight:
      anchor_linenums: true
  - pymdownx.inlinehilite
  - pymdownx.snippets
  - pymdownx.superfences
  - tables
  - toc:
      permalink: true

nav:
  - Home: index.md
  - Getting Started:
      - Installation: getting-started/installation.md
      - Quickstart: getting-started/quickstart.md
      - Authentication & bot setup: getting-started/auth.md
  - Guides:
      - Creating an employee: guides/create-employee.md
      - Creating a Backoffice user: guides/create-backoffice-user.md
      - Disabling an employee: guides/disable-employee.md
      - Sites, regions & districts: guides/sites-regions-districts.md
      - Permissions & roles: guides/permissions.md
      - Bulk operations: guides/bulk-operations.md
      - Error handling: guides/error-handling.md
  - Examples:
      - Onboard a new hire: examples/onboard-new-hire.md
      - Bulk disable from CSV: examples/bulk-disable-from-csv.md
      - Sync from an HRIS: examples/hris-sync.md
  - API Reference:
      - Client: reference/client.md
      - Models: reference/models.md
      - Exceptions: reference/exceptions.md
  - Troubleshooting: troubleshooting.md
  - Changelog: changelog.md
```

- [ ] **Step 2: Write `docs/index.md`**

```markdown
# Sonny's Backoffice Wrapper

Programmatic user management for Sonny's Carwash Controls Backoffice — create, link, and disable employees and Backoffice users from Python.

## Why this exists

Sonny's Controls offers a [read-only Data API](https://github.com/christopher-nance/Sonnys-Data-API-Client) for reporting, but **no API for user management**. Every change to an employee or Backoffice user has to be made by hand in the web UI. That's fine for a handful of users, but painful at scale — especially for bulk onboarding, HRIS sync, and offboarding former employees.

This library closes the gap by driving Backoffice's HTTP endpoints directly with a pure-`requests` session. No headless browser at runtime, no manual clicking.

## Install

```bash
pip install git+https://github.com/christopher-nance/Sonnys-Backoffice-Wrapper.git
```

## Ten-second quickstart

```python
from datetime import datetime
from decimal import Decimal
from sonnys_backoffice import SonnysBackofficeClient

with SonnysBackofficeClient(
    subdomain="washu",
    username="your-bot-user",
    password="your-bot-password",
) as client:
    result = client.create_employee(
        first_name="Jane",
        last_name="Doe",
        phone="6155551234",
        email="jane.doe@example.com",
        pos_user_id="jdoe",
        wage_rate=Decimal("15.50"),
        start_date=datetime(2026, 5, 1),
        available_sites=["Nolensville"],
    )
    print(f"created employee {result.employee_id}, POS PIN: {result.pos_pin}")
```

## What's in the box

- `create_employee` — with or without a linked Backoffice user
- `disable_employee` — looked up by POS User ID or email
- `create_backoffice_user` — standalone or linked to an existing employee
- `list_sites`, `list_departments`, `list_permissions` — discovery helpers
- Pydantic v2 input validation and result typing
- Automatic site/region/district hierarchy detection
- Case-insensitive permission name matching with a "General User" fallback

## Status

Alpha. The public API is stable for Milestone 1. `modify_employee` is deliberately not included — it's deferred to a later release because different fields live behind different Backoffice URLs and deserve targeted functions.
```

- [ ] **Step 3: Write `docs/getting-started/installation.md`**

```markdown
# Installation

## Requirements

- Python 3.10 or newer
- A dedicated Backoffice bot user with Administrator rights and full site access

## Install from GitHub

```bash
pip install git+https://github.com/christopher-nance/Sonnys-Backoffice-Wrapper.git
```

For production use, pin to a tag:

```bash
pip install git+https://github.com/christopher-nance/Sonnys-Backoffice-Wrapper.git@v0.1.0
```

## Verify

```python
import sonnys_backoffice
print(sonnys_backoffice.__version__)
```
```

- [ ] **Step 4: Write `docs/getting-started/quickstart.md`**

```markdown
# Quickstart

This walks through creating one employee and then disabling them.

## 1. Set up a bot user in Backoffice

Before running the library, create a dedicated user in Backoffice with Administrator permissions and access to all sites. Do **not** use a human's login — bot accounts are more stable and create a clean audit trail. See [Authentication & bot setup](auth.md).

## 2. Store credentials outside your code

```python
import os

subdomain = os.environ["SONNYS_SUBDOMAIN"]     # e.g. "washu"
username = os.environ["SONNYS_BOT_USERNAME"]
password = os.environ["SONNYS_BOT_PASSWORD"]
```

## 3. Create a client and call `create_employee`

```python
from datetime import datetime
from decimal import Decimal
from sonnys_backoffice import SonnysBackofficeClient

with SonnysBackofficeClient(
    subdomain=subdomain,
    username=username,
    password=password,
) as client:
    result = client.create_employee(
        first_name="Jane",
        last_name="Doe",
        phone="6155551234",
        email="jane.doe@example.com",
        pos_user_id="jdoe",
        wage_rate=Decimal("15.50"),
        start_date=datetime(2026, 5, 1),
        available_sites=["Nolensville"],
        permission="General User",
    )

    print(f"Employee ID: {result.employee_id}")
    print(f"POS User ID: {result.pos_user_id}")
    print(f"POS PIN:     {result.pos_pin}")
    if result.warnings:
        for w in result.warnings:
            print(f"warning: {w}")
```

## 4. Disable the employee

```python
    disabled = client.disable_employee(pos_user_id="jdoe")
    print(f"Disabled at: {disabled.disabled_at}")
```

## What next?

- [Creating an employee](../guides/create-employee.md) — every parameter explained
- [Bulk operations](../guides/bulk-operations.md) — the pattern for loops
- [Error handling](../guides/error-handling.md) — the exception hierarchy
```

- [ ] **Step 5: Write `docs/getting-started/auth.md`**

```markdown
# Authentication & Bot Setup

## Why a dedicated bot user?

- **Session stability** — a bot account isn't used by a human whose active browser session might rotate cookies mid-call.
- **Audit trail** — every action the wrapper performs is attributed to the bot user in Backoffice's audit log, not a random employee.
- **Rotation** — you can rotate the bot's password without disrupting a real person's access.

## Create the bot user

1. Log into Backoffice as an existing Administrator.
2. Navigate to **User Management → Create User**.
3. Choose "Is this user an Employee of the Wash? **No**" — the bot is an external user.
4. Fill in a recognizable name like `Automation Bot`.
5. Set a username and a strong password.
6. Grant role **Administrator**.
7. On the permissions page, enable **Access all Sites** (on a flat tenant) or **Available all Regions** (on a multi-region tenant). The wrapper needs full visibility to resolve site names into IDs.
8. Save.

## Store credentials safely

Never commit credentials. Use environment variables or a secret manager:

```bash
export SONNYS_SUBDOMAIN=washu
export SONNYS_BOT_USERNAME=automation-bot
export SONNYS_BOT_PASSWORD='your-strong-password-here'
```

In Python:

```python
import os
from sonnys_backoffice import SonnysBackofficeClient

client = SonnysBackofficeClient(
    subdomain=os.environ["SONNYS_SUBDOMAIN"],
    username=os.environ["SONNYS_BOT_USERNAME"],
    password=os.environ["SONNYS_BOT_PASSWORD"],
)
```
```

- [ ] **Step 6: Verify MkDocs builds**

```bash
mkdocs build --strict
```

Expected: `INFO - Documentation built in 0.XX seconds`. Warnings are OK; errors are not.

- [ ] **Step 7: Commit**

```bash
git add mkdocs.yml docs/
git commit -m "docs: add mkdocs config, index, getting-started pages"
```

### Task 9.2: Guide pages

**Files:**
- Create: `docs/guides/create-employee.md`
- Create: `docs/guides/create-backoffice-user.md`
- Create: `docs/guides/disable-employee.md`
- Create: `docs/guides/sites-regions-districts.md`
- Create: `docs/guides/permissions.md`
- Create: `docs/guides/bulk-operations.md`
- Create: `docs/guides/error-handling.md`

- [ ] **Step 1: Write `docs/guides/create-employee.md`**

Content outline (write the full page during execution, with code samples and a complete parameter table):

```markdown
# Creating an Employee

## Minimal call

[full minimal working example]

## Every parameter explained

| Parameter | Type | Required | Default | Notes |
|---|---|---|---|---|
| first_name | str | yes | — | Leading/trailing whitespace is stripped. Unicode and symbols preserved. |
| last_name | str | yes | — | Same rules. |
| phone | str | yes | — | 9 or 10 digits after stripping all symbols. |
| email | str | yes | — | Must contain `@domain.tld`. |
| pos_user_id | str | yes | — | Must be unique on the tenant. |
| pos_pin | str \| None | no | auto-generated 5 digits | Always returned in the result. |
| wage_rate | Decimal \| float | yes | — | Dollars per hour. |
| overtime_wage_rate | Decimal \| float \| None | no | wage_rate × 1.5 | |
| start_date | datetime | yes | — | |
| available_sites | list[str] \| "all" | yes | — | Site names (not IDs). See [Sites, regions & districts](sites-regions-districts.md). |
| departments | list[str] \| None | no | ["Greeter"] | "Greeter" is auto-added if missing — see below. |
| permission | str | no | "General User" | Case-insensitive. See [Permissions & roles](permissions.md). |
| emergency_contact_name | str \| None | no | None | |
| emergency_contact_phone | str \| None | no | None | Same validation as phone. |
| requires_backoffice | bool | no | False | Creates a linked BO user in the same call. |
| backoffice_username | str \| None | no | None | Required when requires_backoffice=True. |
| backoffice_password | str \| None | no | auto-generated 12 chars | Always returned. |

## Why "Greeter" is always present

[explanation of greeter commission]

## Creating with a linked Backoffice user

[warning callout: POS and BO permission names must match, lowercased]

## The returned `EmployeeCreated` object

[every field explained with types]
```

- [ ] **Step 2: Write the other six guide pages** using similar outlines based on the spec's docs section.

Each guide is 1-3 pages. Write complete prose, not just outlines. Use the content described in Section 5 of the spec as the source of truth.

- [ ] **Step 3: Build and verify**

```bash
mkdocs build --strict
```

- [ ] **Step 4: Commit**

```bash
git add docs/guides/
git commit -m "docs: write guide pages for create/disable/permissions/bulk/errors"
```

### Task 9.3: API Reference pages (mkdocstrings)

**Files:**
- Create: `docs/reference/client.md`
- Create: `docs/reference/models.md`
- Create: `docs/reference/exceptions.md`

- [ ] **Step 1: Write `docs/reference/client.md`**

```markdown
# Client

::: sonnys_backoffice.SonnysBackofficeClient
    options:
      show_root_heading: true
      show_source: false
      members:
        - __init__
        - create_employee
        - disable_employee
        - create_backoffice_user
        - list_sites
        - list_departments
        - list_permissions
        - close
```

- [ ] **Step 2: Write `docs/reference/models.md`**

```markdown
# Models

## Result models

::: sonnys_backoffice.EmployeeCreated
::: sonnys_backoffice.BackofficeUserCreated
::: sonnys_backoffice.EmployeeDisabled

## Domain models

::: sonnys_backoffice.Site
::: sonnys_backoffice.Region
::: sonnys_backoffice.Department
::: sonnys_backoffice.Permission
```

- [ ] **Step 3: Write `docs/reference/exceptions.md`**

```markdown
# Exceptions

::: sonnys_backoffice.SonnysBackofficeError
::: sonnys_backoffice.AuthenticationError
::: sonnys_backoffice.NotFoundError
::: sonnys_backoffice.ValidationError
::: sonnys_backoffice.PermissionDeniedError
::: sonnys_backoffice.DuplicateError
::: sonnys_backoffice.BackofficeServerError
```

- [ ] **Step 4: Verify docstrings are rich enough**

Open every public method and model in `src/sonnys_backoffice/` and ensure each has a Google-style docstring with `Args`, `Returns`, and `Raises` sections. Add them where missing.

- [ ] **Step 5: Build and verify the API reference renders**

```bash
mkdocs serve
```

Open `http://127.0.0.1:8000/reference/client/` in a browser. Every method should appear with its signature and docstring.

- [ ] **Step 6: Commit**

```bash
git add docs/reference/ src/sonnys_backoffice/
git commit -m "docs: add mkdocstrings-backed API reference pages and docstrings"
```

### Task 9.4: Example scripts and troubleshooting page

**Files:**
- Create: `docs/examples/onboard-new-hire.md`
- Create: `docs/examples/bulk-disable-from-csv.md`
- Create: `docs/examples/hris-sync.md`
- Create: `docs/troubleshooting.md`
- Create: `docs/changelog.md`

- [ ] **Step 1: Write `docs/examples/onboard-new-hire.md`**

A complete, runnable script with explanation. ~60 lines.

- [ ] **Step 2: Write `docs/examples/bulk-disable-from-csv.md`**

Reads a CSV, disables each row, writes a result CSV. ~80 lines.

- [ ] **Step 3: Write `docs/examples/hris-sync.md`**

Conceptual sketch of reconciliation. ~100 lines.

- [ ] **Step 4: Write `docs/troubleshooting.md` covering every item in spec Section 5.**

- [ ] **Step 5: Write `docs/changelog.md`**

```markdown
# Changelog

## v0.1.0 — 2026-04-XX

Initial release.

**Features:**
- `create_employee` with optional linked Backoffice user
- `disable_employee` lookup by POS User ID or email
- `create_backoffice_user` standalone or linked modes
- `list_sites`, `list_departments`, `list_permissions` discovery helpers
- Auto-detection of flat vs hierarchical site trees
- Case-insensitive permission name resolution with "General User" fallback
- Transparent session re-authentication
- MkDocs Material documentation site
```

- [ ] **Step 6: Build and serve locally to smoke-test**

```bash
mkdocs build --strict
```

- [ ] **Step 7: Commit**

```bash
git add docs/
git commit -m "docs: add example scripts, troubleshooting, and changelog"
```

### Task 9.5: GitHub Pages deploy configuration

**Files:**
- Create: `.github/workflows/docs.yml`

- [ ] **Step 1: Write the CI workflow**

```yaml
name: Deploy docs

on:
  push:
    branches: [main]
    paths:
      - "docs/**"
      - "mkdocs.yml"
      - "src/**"
      - ".github/workflows/docs.yml"
  workflow_dispatch:

permissions:
  contents: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install
        run: |
          pip install -e ".[docs]"
      - name: Deploy
        run: mkdocs gh-deploy --force
```

- [ ] **Step 2: Commit**

```bash
git add .github/
git commit -m "ci: deploy docs to GitHub Pages on push to main"
```

---

## Phase 10: Integration Tests, Polish, Release

### Task 10.1: Integration test suite

**Files:**
- Create: `tests/integration/conftest.py`
- Create: `tests/integration/test_full_flow.py`

- [ ] **Step 1: Write integration conftest**

```python
# tests/integration/conftest.py
import os
import uuid

import pytest

from sonnys_backoffice import SonnysBackofficeClient


@pytest.fixture(scope="session")
def client():
    subdomain = os.environ.get("SONNYS_SUBDOMAIN")
    username = os.environ.get("SONNYS_BOT_USERNAME")
    password = os.environ.get("SONNYS_BOT_PASSWORD")
    if not (subdomain and username and password):
        pytest.skip("integration credentials not set")
    with SonnysBackofficeClient(
        subdomain=subdomain, username=username, password=password
    ) as c:
        yield c


@pytest.fixture
def unique_suffix():
    return uuid.uuid4().hex[:8]
```

- [ ] **Step 2: Write a smoke-level integration test**

```python
# tests/integration/test_full_flow.py
from datetime import datetime
from decimal import Decimal

import pytest


@pytest.mark.integration
def test_list_sites_returns_non_empty(client):
    sites = client.list_sites()
    assert len(sites) > 0


@pytest.mark.integration
def test_list_departments_includes_greeter(client):
    depts = client.list_departments()
    names = [d.name for d in depts]
    assert "Greeter" in names


@pytest.mark.integration
def test_create_and_disable_employee(client, unique_suffix):
    # REQUIRES EXPLICIT APPROVAL to run — this performs writes on the live tenant.
    # Set SONNYS_ALLOW_WRITES=1 in the environment to enable.
    import os
    if not os.environ.get("SONNYS_ALLOW_WRITES"):
        pytest.skip("SONNYS_ALLOW_WRITES not set — skipping live-write test")

    pos_id = f"wrapper_it_{unique_suffix}"
    email = f"wrapper-integration-{unique_suffix}@example.invalid"
    sites = [client.list_sites()[0].name]
    try:
        created = client.create_employee(
            first_name="WrapperIntegration",
            last_name=f"Test{unique_suffix}",
            phone="6155551234",
            email=email,
            pos_user_id=pos_id,
            wage_rate=Decimal("10.00"),
            start_date=datetime(2026, 1, 1),
            available_sites=sites,
        )
        assert created.pos_user_id == pos_id
    finally:
        # Always attempt cleanup even if create succeeded partway
        try:
            client.disable_employee(pos_user_id=pos_id)
        except Exception:
            pass
```

- [ ] **Step 3: Run unit tests to ensure the integration skips cleanly**

```bash
pytest
```

Expected: unit tests pass; integration tests skipped (the default `-m 'not integration'` addopt from `pyproject.toml` excludes them).

- [ ] **Step 4: Commit**

```bash
git add tests/integration/
git commit -m "test(integration): add live-tenant smoke tests guarded by env var"
```

### Task 10.2: Ensure all public methods have docstrings

**Files:**
- Modify: `src/sonnys_backoffice/client.py`

- [ ] **Step 1: Audit docstrings**

For every public method on `SonnysBackofficeClient`, write a Google-style docstring:

```python
def create_employee(...) -> EmployeeCreated:
    """Create a new POS employee, optionally with a linked Backoffice user.

    Args:
        first_name: The employee's first name. Whitespace is stripped.
        last_name: The employee's last name. Whitespace is stripped.
        phone: Phone number. Must resolve to 9 or 10 digits after stripping all symbols.
        email: Email address. Must contain ``@domain.tld``.
        pos_user_id: Caller-assigned unique POS login ID.
        pos_pin: 5-digit POS PIN. If ``None``, a random 5-digit PIN is generated.
        wage_rate: Hourly wage in dollars.
        overtime_wage_rate: Overtime hourly wage. Defaults to ``wage_rate * 1.5``.
        start_date: Employment start date.
        available_sites: List of site names or the literal ``"all"``.
        departments: Department names. ``"Greeter"`` is always included.
        permission: Role name. Matched case-insensitively; unknown names fall back to "General User".
        emergency_contact_name: Optional emergency contact name.
        emergency_contact_phone: Optional emergency contact phone. Same validation as ``phone``.
        requires_backoffice: If True, also creates a linked Backoffice user.
        backoffice_username: BO username. Required when ``requires_backoffice=True``.
        backoffice_password: BO password. If ``None``, a 12-character random password is generated.

    Returns:
        EmployeeCreated: The created record, including any generated secrets and warnings.

    Raises:
        ValidationError: If any input fails pydantic validation or Backoffice rejects the form.
        DuplicateError: If the email or POS User ID already exists.
        AuthenticationError: If the bot user lacks rights or the session cannot be re-established.
        BackofficeServerError: If Backoffice returns an unexpected response.
    """
```

Do the same for `disable_employee`, `create_backoffice_user`, `list_sites`, `list_departments`, `list_permissions`, and `close`.

- [ ] **Step 2: Rebuild docs and verify the API Reference pages render with full docstrings**

```bash
mkdocs build --strict
```

- [ ] **Step 3: Commit**

```bash
git add src/sonnys_backoffice/
git commit -m "docs: add Google-style docstrings to all public client methods"
```

### Task 10.3: Lint, format, full test run, and tag v0.1.0

**Files:**
- None

- [ ] **Step 1: Run ruff**

```bash
ruff check . --fix
ruff format .
```

- [ ] **Step 2: Run full unit test suite with coverage**

```bash
pytest --cov=sonnys_backoffice --cov-report=term-missing
```

Expected: ≥80% coverage overall, ≥90% on `models.py`, `permissions.py`, `sites.py`, `passwords.py`, and the form builders in `employees.py` / `bo_users.py`.

- [ ] **Step 3: Run integration tests against the live test tenant (with approval)**

```bash
SONNYS_SUBDOMAIN=washu \
SONNYS_BOT_USERNAME=SonnysWrapperTestAccount \
SONNYS_BOT_PASSWORD='ThisIsATestAccount123!' \
pytest -m integration
```

Before enabling `SONNYS_ALLOW_WRITES=1` for the create/disable integration test, stop and request approval.

- [ ] **Step 4: Commit any formatting changes**

```bash
git add -A
git commit -m "chore: ruff format pass"
```

- [ ] **Step 5: Tag v0.1.0**

```bash
git tag -a v0.1.0 -m "v0.1.0 — initial release: create_employee, disable_employee, create_backoffice_user"
```

- [ ] **Step 6: Push**

```bash
git push origin main --tags
```

The docs workflow deploys to GitHub Pages automatically on push.

---

## Self-Review Checklist (performed by plan author)

**Spec coverage:**

- §1 Scope & Goals → Phases 0-10 implement every listed deliverable.
- §2 Architecture & Module Layout → Phase 0 scaffolds, Phases 2-8 implement each module.
- §3 Public API → Phase 8 exposes `SonnysBackofficeClient` with every documented method.
- §4 Exploration Plan → Phase 1 captures every fixture referenced by later phases.
- §5 Documentation Outline → Phase 9 writes every page in the nav.
- §6 Testing Strategy → Unit tests appear in every implementation task; integration tests in Phase 10.
- §7 Resolved questions → Encoded as implementation decisions throughout.
- §8 Risks → Mitigations live in `_BackofficeSession` (re-auth), exception handling (transaction rollback), and `scripts/explore.py` (fixture regeneration).

**Placeholder scan:** Searched for "TODO", "TBD", "fill in", "etc." — only legitimate "update after Phase 1 exploration" notes remain, and those are paired with specific instructions on *what* to update.

**Type consistency:** `SiteTree`, `_BackofficeSession`, `CreateEmployeeRequest`, `EmployeeCreated`, etc. are referenced consistently across tasks. `resolve_permission` returns `(Permission, list[str])` in both definition and call sites. `create_linked_backoffice_user` signature in `bo_users.py` matches the call site in `employees.py`.

**Deferred dependencies on exploration fixtures:** Every fixture-dependent task (Tasks 3.1, 4.1, 4.2, 4.3, 5.1, 6.1) explicitly notes that selectors and field names must be updated after Phase 1 completes, and the `test_payload_matches_recorded_fixture` test in Task 5.1 is the authoritative check that the form builder matches the real recorded POST.

---

## Post-Exploration Deltas (2026-04-13)

This appendix lists authoritative corrections to the task code examples above, based on findings in `tests/fixtures/exploration_notes.md`. When dispatching a subagent for any task below, pass the delta **alongside** the original task text and instruct the subagent that the delta takes precedence.

### General

- **No CSRF tokens** anywhere in Backoffice. Delete any CSRF-scraping logic from `session.py` task code. The `_parse_login_form` function in Task 3.1 should only return the form action — no token.
- **Session cookie:** `PHPSESSID`.
- **Stack:** Symfony + PHP.
- **Session-expired detection signal:** the `_looks_like_login_page` helper from Task 3.1 is correct in spirit — look for `name="_username"` and `name="_password"` in response bodies. Update the specific string from `"username"` to `"_username"` (Symfony convention).

### Delta D-2.3 (Task 2.3: `CreateEmployeeRequest`)

- **Type changes:**
  - `pos_user_id: int` (was `str`). The underlying field `posCredential[POSLoginID]` is `type=number`.
  - `pos_pin: int | None = None` (was `str | None`). The underlying field `posCredential[POSLoginPassword]` is `type=number`.
- **Add optional kwarg:** `adp_employee_id: str | None = None` (maps to `employee[adpEmployeeId]`, text input).
- **Remove `_validate_pos_pin` regex test** that requires "exactly 5 digits as a string". Replace with a validator that accepts either a 5-digit int or `None`, and rejects ints outside the 5-digit range (10000-99999).
- **Tests that check `pos_pin="12345"`** must pass an int `12345` instead.
- **`permission: str` is now required (no default).** Remove the `= "General User"` default. The field becomes a plain `permission: str` declaration in `CreateEmployeeRequest`. The existing test `test_departments_defaults_to_greeter` and similar should NOT be replicated for permission — permission omission must raise `pydantic.ValidationError`. Update any call-site test fixture that previously relied on the default to pass `permission="General User"` explicitly. The "unknown name fallback" logic in `_resolve_permission` is unchanged.
- **Same change applies to `CreateBackofficeUserRequest`:** `permission: str` is required, no default.

### Delta D-2.2 (Task 2.2: `generate_pos_pin`)

- Return type: `int` (was `str`). The generator should return a 5-digit random integer in the range 10000-99999. Update the test assertions accordingly (`isinstance(pin, int)` and `10000 <= pin <= 99999`). The existing string-based `isdigit()` test is wrong for the new signature — replace it.

### Delta D-3.1 (Task 3.1: `_BackofficeSession.login`)

Replace the `login()` method implementation with:

```python
def login(self) -> None:
    """Perform login. Safe to call repeatedly."""
    login_page = self._http.get(f"{self.base_url}/login", timeout=self._timeout)
    login_page.raise_for_status()
    # Symfony login form — no CSRF, just _username/_password
    resp = self._http.post(
        f"{self.base_url}/login_check",
        data={
            "_username": self._username,
            "_password": self._password,
        },
        timeout=self._timeout,
        allow_redirects=True,
    )
    if _looks_like_login_page(resp.text):
        raise AuthenticationError("Login failed — credentials rejected by Backoffice")
    if resp.status_code >= 400:
        raise BackofficeServerError(f"Unexpected login response: HTTP {resp.status_code}")
    self._logged_in = True
```

Delete `_parse_login_form` entirely — there's no CSRF token to extract. Update `_looks_like_login_page` to:

```python
def _looks_like_login_page(html: str) -> bool:
    return 'name="_username"' in html and 'name="_password"' in html
```

Update `test_login_extracts_csrf_and_posts_credentials` to drop the CSRF assertion and just verify `_username`/`_password` appear in the POST body, target URL is `/login_check`.

### Delta D-4.3 (Task 4.3: `parse_permissions`)

The real permissions page (`/employee/permissions/<id>`) has a `templateId` select as the public-facing role picker and a hidden `permissions[N][...]` matrix of individual permissions. The wrapper's `Permission` domain model represents the *template*, not individual matrix entries.

Replace the `parse_permissions` implementation with:

```python
from typing import Literal
from bs4 import BeautifulSoup

def parse_permissions(html: str, *, scope: Literal["pos", "backoffice"]) -> list[Permission]:
    """Extract role templates from a captured /employee/permissions/<id> (or BO equivalent) page."""
    soup = BeautifulSoup(html, "html.parser")
    perms: list[Permission] = []
    sel = soup.find("select", attrs={"name": "templateId"})
    if sel is None:
        return perms
    for opt in sel.find_all("option"):
        val = (opt.get("value") or "").strip()
        if not val:
            continue
        try:
            pid = int(val)
        except ValueError:
            continue
        perms.append(Permission(id=pid, name=opt.get_text(strip=True), scope=scope))
    return perms
```

Tests should point at `employee_permissions_54.html` for `scope="pos"`. On WashU, expected templates: Manager, Cashier, General User, General Manager, Assistant Manager, Shift Leader, CSA (note no Administrator on POS side).

### Delta D-4.2 (Task 4.2: `parse_departments`)

The real field is a `<select name="employee[departments][]">` (multi-select), with options `1`=Cashier, `2`=Line, `3`=Greeter, `4`=Management on WashU. The selector in the task's first-try implementation is close but not quite right — the correct selector is `select[name='employee[departments][]'] option`. Update accordingly. Expected test: `"Greeter"` is in the result with id=3.

### Delta D-8.2 (new task: public availability-check helpers on the client)

Insert this as a new Task 8.2 in Phase 8, after the façade exists. These are small convenience methods exposed on `SonnysBackofficeClient` that callers use to pre-check uniqueness *before* building a `CreateEmployeeRequest` — typically to implement a "try preferred ID, generate a random one if taken" onboarding flow.

**Files:**
- Modify: `src/sonnys_backoffice/client.py` (add 3 methods)
- Create: `tests/unit/test_client_availability.py`

**Public API additions:**

```python
class SonnysBackofficeClient:
    # ... existing methods ...

    def is_pos_user_id_available(self, pos_user_id: int, *, refresh: bool = False) -> bool:
        """Return True if no active or disabled employee on this tenant currently uses this POS User ID.

        Uses the cached employee index built from /employee?limit=10000&active=all.
        Pass refresh=True to re-fetch the index before checking.
        """
        self._ensure_employee_index(refresh=refresh)
        return pos_user_id not in self._employee_index.by_pos_user_id

    def is_email_available(self, email: str, *, refresh: bool = False) -> bool:
        """Return True if no employee on this tenant currently uses this email."""
        self._ensure_employee_index(refresh=refresh)
        return email.strip().lower() not in self._employee_index.by_email

    def is_phone_available(self, phone: str, *, refresh: bool = False) -> bool:
        """Return True if no employee on this tenant currently uses this phone number.

        The phone argument is normalized by stripping all non-digit characters before comparison.
        """
        import re as _re
        self._ensure_employee_index(refresh=refresh)
        normalized = _re.sub(r"\D", "", phone)
        return normalized not in self._employee_index.by_phone
```

`_ensure_employee_index` is the same helper that `create_employee` uses for its pre-flight uniqueness check (Delta D-5.0) — the index is built lazily on first use, cached on the client instance, and reusable.

**Example usage** (the onboarding flow the user described):

```python
import random

def find_free_pos_id(client: SonnysBackofficeClient, preferred: int | None = None) -> int:
    """Return preferred if free, else a random 5-digit alternative."""
    if preferred is not None and client.is_pos_user_id_available(preferred):
        return preferred
    for _ in range(100):
        candidate = random.randint(10000, 99999)
        if client.is_pos_user_id_available(candidate):
            return candidate
    raise RuntimeError("could not find a free POS User ID after 100 attempts")
```

**Tests** should cover:
- Returns True when the index doesn't contain the value
- Returns True after `refresh=True` refetches the index
- Returns False when the value is in the index (both active and disabled employees — the index includes both via `active=all`)
- Phone normalization: `is_phone_available("(615) 555-1234")` compares against `"6155551234"` internally
- Email comparison is case-insensitive

**Note on staleness:** the cache is populated on first use and reused for subsequent calls. If a caller is running a long-lived client that needs to check-then-act atomically (avoid races), they should pass `refresh=True` before the final `create_employee` call. Document this tradeoff in the guide.

### Delta D-5.0 (new task: pre-flight uniqueness check)

Insert this as a new Task 5.0 in Phase 5, executed before Task 5.1. `create_employee` must pre-flight check the caller's `pos_user_id`, `email`, and `phone` against the tenant's existing employees and raise `DuplicateError` if any collide — all three are unique per tenant (see `project_uniqueness_constraints.md`).

**Files:**
- Modify: `src/sonnys_backoffice/employees.py` (add `EmployeeIndex` helper and `_check_uniqueness`)
- Create: `tests/unit/test_employees_uniqueness.py`

**Strategy:**
- `EmployeeIndex` is an in-memory cache lazily built from two HTTP calls:
  1. `GET /employee?limit=10000&active=all` — parsed via `parse_employee_list` helper → yields `{pos_user_id: employee_id, phone: employee_id}` for every row (emails are NOT in the list)
  2. `GET /user/create` — parsed via `parse_user_create_employee_options` helper → yields `{email: employee_id}` from the `user[employeeId]` dropdown's `data-email` attributes
- `SonnysBackofficeClient._employee_index` is the cache, populated lazily on first `create_employee` call, reused for subsequent calls in the same client, refreshable via `refresh=True`
- `_check_uniqueness(request, index)` raises `DuplicateError` with a structured message: `"pos_user_id=XXXXX already exists on employee_id=YY (first_name last_name)"`

**Code sketch** for the new `EmployeeIndex` class and helpers in `employees.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from bs4 import BeautifulSoup

from .exceptions import DuplicateError

_EMP_ID_RE = re.compile(r"/employee/(?:edit|permissions|compensation)/(\d+)")
_DIGITS_ONLY_RE = re.compile(r"\D")


@dataclass
class EmployeeIndex:
    by_pos_user_id: dict[int, int] = field(default_factory=dict)
    by_email: dict[str, int] = field(default_factory=dict)
    by_phone: dict[str, int] = field(default_factory=dict)

    def check(
        self,
        *,
        pos_user_id: int,
        email: str,
        phone: str,
    ) -> None:
        """Raise DuplicateError if any of the three fields collides with an existing employee."""
        if pos_user_id in self.by_pos_user_id:
            existing = self.by_pos_user_id[pos_user_id]
            raise DuplicateError(
                f"pos_user_id={pos_user_id} already exists on employee_id={existing}"
            )
        normalized_email = email.strip().lower()
        if normalized_email in self.by_email:
            existing = self.by_email[normalized_email]
            raise DuplicateError(
                f"email={email!r} already exists on employee_id={existing}"
            )
        normalized_phone = _DIGITS_ONLY_RE.sub("", phone)
        if normalized_phone in self.by_phone:
            existing = self.by_phone[normalized_phone]
            raise DuplicateError(
                f"phone={phone!r} (normalized: {normalized_phone}) already exists on employee_id={existing}"
            )


def parse_employee_list(html: str) -> tuple[dict[int, int], dict[str, int]]:
    """Parse /employee?limit=... HTML. Return (pos_user_id_map, phone_map)."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="table-employees-list")
    if table is None:
        return {}, {}
    pos_map: dict[int, int] = {}
    phone_map: dict[str, int] = {}
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 7:
            continue
        # Extract employee_id from any action link in the row
        emp_id: int | None = None
        for a in row.find_all("a", href=True):
            m = _EMP_ID_RE.search(a["href"])
            if m:
                emp_id = int(m.group(1))
                break
        if emp_id is None:
            continue
        # Column positions: first_name, last_name, site, role, pos_login_id, department, phone, wage_mode, ...
        # The exact indices come from employee_list.html in the fixtures — verify and adjust.
        pos_id_text = cells[4].get_text(strip=True)
        phone_text = cells[6].get_text(strip=True)
        if pos_id_text.isdigit():
            pos_map[int(pos_id_text)] = emp_id
        phone_digits = _DIGITS_ONLY_RE.sub("", phone_text)
        if phone_digits:
            phone_map[phone_digits] = emp_id
    return pos_map, phone_map


def parse_user_create_employee_options(html: str) -> dict[str, int]:
    """Parse /user/create HTML. Return {email: employee_id} from the user[employeeId] dropdown's data-email attrs."""
    soup = BeautifulSoup(html, "html.parser")
    sel = soup.find("select", attrs={"name": "user[employeeId]"})
    if sel is None:
        return {}
    email_map: dict[str, int] = {}
    for opt in sel.find_all("option"):
        val = (opt.get("value") or "").strip()
        if not val:
            continue
        try:
            emp_id = int(val)
        except ValueError:
            continue
        email = (opt.get("data-email") or "").strip().lower()
        if email:
            email_map[email] = emp_id
    return email_map


def build_employee_index(
    *,
    employee_list_html: str,
    user_create_html: str,
) -> EmployeeIndex:
    """Combine both sources into a single index."""
    pos_map, phone_map = parse_employee_list(employee_list_html)
    email_map = parse_user_create_employee_options(user_create_html)
    return EmployeeIndex(
        by_pos_user_id=pos_map,
        by_email=email_map,
        by_phone=phone_map,
    )
```

**Tests** (`tests/unit/test_employees_uniqueness.py`):

```python
from pathlib import Path

import pytest

from sonnys_backoffice.employees import (
    EmployeeIndex,
    build_employee_index,
    parse_employee_list,
    parse_user_create_employee_options,
)
from sonnys_backoffice.exceptions import DuplicateError

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html"


def test_parse_employee_list_extracts_pos_id_and_phone():
    html = (FIXTURES / "employee_list.html").read_text(encoding="utf-8")
    pos_map, phone_map = parse_employee_list(html)
    assert len(pos_map) >= 20  # default page has 25 employees
    # Spot-check: at least one known employee from the fixture
    assert any(eid > 0 for eid in pos_map.values())
    assert all(isinstance(k, int) for k in pos_map.keys())
    assert all(phone.isdigit() for phone in phone_map.keys())


def test_parse_user_create_builds_email_map():
    html = (FIXTURES / "user_create.html").read_text(encoding="utf-8")
    email_map = parse_user_create_employee_options(html)
    assert len(email_map) > 100  # WashU has hundreds
    assert all("@" in e for e in email_map.keys())
    assert all(e == e.lower() for e in email_map.keys())


def test_employee_index_check_raises_on_pos_id_collision():
    idx = EmployeeIndex(by_pos_user_id={1234: 99}, by_email={}, by_phone={})
    with pytest.raises(DuplicateError, match="pos_user_id=1234"):
        idx.check(pos_user_id=1234, email="new@example.com", phone="6155551234")


def test_employee_index_check_raises_on_email_collision():
    idx = EmployeeIndex(by_pos_user_id={}, by_email={"taken@example.com": 42}, by_phone={})
    with pytest.raises(DuplicateError, match="email"):
        idx.check(pos_user_id=99999, email="Taken@Example.com", phone="6155551234")  # case-insensitive


def test_employee_index_check_raises_on_phone_collision():
    idx = EmployeeIndex(by_pos_user_id={}, by_email={}, by_phone={"6155551234": 17})
    with pytest.raises(DuplicateError, match="phone"):
        idx.check(pos_user_id=99999, email="new@example.com", phone="(615) 555-1234")  # symbol strip


def test_employee_index_check_ok_when_all_clear():
    idx = EmployeeIndex(by_pos_user_id={1234: 99}, by_email={"taken@example.com": 42}, by_phone={"6155551234": 17})
    # No exception
    idx.check(pos_user_id=5678, email="new@example.com", phone="6155559999")
```

**Orchestrator wiring (Delta D-5.3 update):** at the start of `create_employee`, after input validation and before building the step-1 payload:

```python
    # Uniqueness pre-flight
    if client_employee_index is None:
        list_resp = session.get("/employee?limit=10000")
        _check_create_response(list_resp)
        user_create_resp = session.get("/user/create")
        _check_create_response(user_create_resp)
        client_employee_index = build_employee_index(
            employee_list_html=list_resp.text,
            user_create_html=user_create_resp.text,
        )
    client_employee_index.check(
        pos_user_id=resolved_request.pos_user_id,
        email=resolved_request.email,
        phone=resolved_request.phone,
    )
```

The client façade (Task 8.1) caches `_employee_index` on the `SonnysBackofficeClient` instance and passes it through.

### Delta D-5.1 (Task 5.1: `build_employee_step1_payload`)

Replace the field-mapping section with the authoritative mapping from `exploration_notes.md`:

```python
def build_employee_step1_payload(
    request: CreateEmployeeRequest,
    *,
    site_tree: SiteTree,
    departments_by_name: Mapping[str, int],
    wage_site_id: int,            # new required arg — resolved by the orchestrator
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        # Personal
        "employee[firstName]": request.first_name,
        "employee[lastName]": request.last_name,
        "employee[phone]": request.phone,
        "employee[email]": request.email,
        "employee[startDate]": request.start_date.strftime("%m/%d/%Y"),
        # POS credentials (separate prefix, numeric)
        "posCredential[POSLoginID]": str(request.pos_user_id),
        "posCredential[POSLoginPassword]": str(request.pos_pin),
        # Wage (hourly only for Milestone 1)
        "wage[isHourly]": "1",
        "wage[regularRate]": f"{request.wage_rate:.2f}",
        "wage[overtimeRate]": f"{request.overtime_wage_rate:.2f}",
        "wage[isOvertimeEligible]": "1",
        "wage[siteId]": str(wage_site_id),
    }
    if request.adp_employee_id:
        payload["employee[adpEmployeeId]"] = request.adp_employee_id
    if request.emergency_contact_name:
        payload["employee[emergencyContactName]"] = request.emergency_contact_name
    if request.emergency_contact_phone:
        payload["employee[emergencyContactPhone]"] = request.emergency_contact_phone

    # Departments (array of ids)
    dept_ids = []
    for dept_name in request.departments or []:
        did = departments_by_name.get(dept_name)
        if did is not None:
            dept_ids.append(did)
    payload["employee[departments][]"] = dept_ids

    # Site availability (hierarchy vs flat — same shape as original task code)
    resolved_sites = site_tree.resolve_all(request.available_sites)
    if site_tree.is_hierarchical:
        enabled_region_ids = {s.region_id for s in resolved_sites if s.region_id}
        enabled_district_ids = {s.district_id for s in resolved_sites if s.district_id}
        if request.available_sites == "all":
            payload["employee[isAllRegionsAllowed]"] = "1"
        else:
            payload["employee[isAllRegionsAllowed]"] = "0"
            payload["employee[disabledRegions][]"] = [
                r.id for r in site_tree.regions if r.id not in enabled_region_ids
            ]
            payload["employee[disabledDistricts][]"] = [
                d.id for d in site_tree.districts if d.id not in enabled_district_ids
            ]
            enabled_site_ids = {s.id for s in resolved_sites}
            for s in site_tree.sites:
                payload[f"employee[sites][{s.id}][isAvailable]"] = "1" if s.id in enabled_site_ids else "0"
                payload[f"employee[sites][{s.id}][siteId]"] = str(s.id)
    else:
        # Flat tenant: uncertain field shape until a flat-tenant fixture is captured.
        # Use the spec's assumed shape as a first cut; revisit when a flat fixture exists.
        if request.available_sites == "all":
            payload["employee[isAllSitesAllowed]"] = "1"
        else:
            payload["employee[isAllSitesAllowed]"] = "0"
            payload["employee[siteIds][]"] = [s.id for s in resolved_sites]

    return payload
```

The test file must pass a `wage_site_id` fixture value and set `pos_user_id` and `pos_pin` as ints.

### Delta D-5.2 (Task 5.2: `build_employee_step2_permissions_payload`) — UPDATED after Phase 1.4 Write 2/2b

**Finding from Phase 1.4 Write 2 and 2b:** the minimal payload approach (`templateId` + `employeeId` + `hasActionApprovalAuthority` only) is **accepted by the server** (HTTP 302) **but has no effect** — the employee's Access column stays at "None". The server requires the **full `permissions[N]` matrix** to be submitted, where N is every permission ID in the tenant's system (typically 1-34).

**Where the template data lives:** `<option>` elements in the `templateId` `<select>` on `/employee/permissions/<id>` carry `data-permissions-set` and `data-manager-override-permissions-set` attributes containing comma-separated lists of permission IDs. The wrapper parses these at runtime; no hardcoded template mapping needed.

**Required payload structure:**

```
employeeId=<new_id>
templateId=<N>
hasActionApprovalAuthority=0  (or 1)
permissions[1][id]=1
permissions[1][label]=<from form>
permissions[1][description]=<from form>
# permissions[1][hasGrantAccess]=1   only if 1 is in the template's grants set
# permissions[1][requiresOverride]=1 only if 1 is in the template's overrides set
permissions[2][id]=2
permissions[2][label]=...
# ... repeat for every permission in the tenant's system ...
```

Every permission in the tenant's system must appear in the POST with its `id`, `label`, and `description` fields (these are static metadata). Only the permissions granted by the template have `hasGrantAccess=1` added. Only permissions requiring override have `requiresOverride=1`. Omit both flags to leave them unchecked — **do not send `=0`, that gets bound as true by Symfony's presence-is-boolean rule**.

**Revised data model.** `Permission` in `models.py` needs to carry the template's grant/override sets:

```python
class Permission(_BackofficeBaseModel):
    id: int
    name: str                        # e.g. "General User"
    scope: Literal["pos", "backoffice"]
    grants: frozenset[int] = Field(default_factory=frozenset)   # permission IDs this template grants
    overrides: frozenset[int] = Field(default_factory=frozenset)  # permission IDs this template requires-override for
```

**New domain type** `PermissionFieldMeta` representing static permission metadata from the form:

```python
class PermissionFieldMeta(_BackofficeBaseModel):
    id: int
    label: str
    description: str
```

**Updated `parse_permissions` signature** — now returns both the template list AND the permission metadata schema from the same page:

```python
def parse_permissions_and_schema(
    html: str,
    *,
    scope: Literal["pos", "backoffice"],
) -> tuple[list[Permission], list[PermissionFieldMeta]]:
    """Parse /employee/permissions/<id> into a template list and a permission schema."""
    soup = BeautifulSoup(html, "html.parser")
    # Templates from the templateId select
    templates: list[Permission] = []
    sel = soup.find("select", attrs={"name": "templateId"})
    if sel is not None:
        for opt in sel.find_all("option"):
            val = (opt.get("value") or "").strip()
            if not val:
                continue
            try:
                tid = int(val)
            except ValueError:
                continue
            grants_raw = opt.get("data-permissions-set", "") or ""
            overrides_raw = opt.get("data-manager-override-permissions-set", "") or ""
            grants = frozenset(int(x) for x in grants_raw.split(",") if x.strip().isdigit())
            overrides = frozenset(int(x) for x in overrides_raw.split(",") if x.strip().isdigit())
            templates.append(
                Permission(
                    id=tid,
                    name=opt.get_text(strip=True),
                    scope=scope,
                    grants=grants,
                    overrides=overrides,
                )
            )

    # Schema — one entry per unique permission id found in the form
    schema: dict[int, PermissionFieldMeta] = {}
    for inp in soup.find_all("input", attrs={"name": re.compile(r"permissions\[\d+\]\[id\]")}):
        m = re.match(r"permissions\[(\d+)\]\[id\]", inp.get("name", ""))
        if not m:
            continue
        pid = int(m.group(1))
        if pid in schema:
            continue  # first occurrence wins
        # Find the corresponding label/description inputs
        label_inp = soup.find("input", attrs={"name": f"permissions[{pid}][label]"})
        desc_inp = soup.find("input", attrs={"name": f"permissions[{pid}][description]"})
        schema[pid] = PermissionFieldMeta(
            id=pid,
            label=(label_inp.get("value") or "") if label_inp else "",
            description=(desc_inp.get("value") or "") if desc_inp else "",
        )
    return templates, [schema[k] for k in sorted(schema.keys())]
```

**Updated `build_employee_step2_permissions_payload`:**

```python
def build_employee_step2_permissions_payload(
    *,
    permission: Permission,             # the selected template, with grants/overrides populated
    permission_schema: list[PermissionFieldMeta],  # all permissions in the tenant's system
    employee_id: int,
    has_action_approval_authority: bool = False,
) -> list[tuple[str, str]]:
    payload: list[tuple[str, str]] = [
        ("employeeId", str(employee_id)),
        ("templateId", str(permission.id)),
        ("hasActionApprovalAuthority", "1" if has_action_approval_authority else "0"),
    ]
    for perm in permission_schema:
        payload.append((f"permissions[{perm.id}][id]", str(perm.id)))
        payload.append((f"permissions[{perm.id}][label]", perm.label))
        payload.append((f"permissions[{perm.id}][description]", perm.description))
        if perm.id in permission.grants:
            payload.append((f"permissions[{perm.id}][hasGrantAccess]", "1"))
        if perm.id in permission.overrides:
            payload.append((f"permissions[{perm.id}][requiresOverride]", "1"))
    return payload
```

**Client cache update:** `SonnysBackofficeClient._pos_permissions` now stores the parsed `(templates, schema)` tuple instead of just a list. The `list_permissions(scope="pos")` method returns just the templates list to callers — the schema is an internal detail used by the form builder. `list_permissions(scope="pos")` is triggered either on first call to `create_employee` (via `_ensure_caches`) or explicitly by the caller.

**Important:** the permission schema is cached per-client but is extracted from an *existing employee's* permissions page. If the tenant has zero employees, the wrapper cannot populate the schema. For Milestone 1, assume at least one employee exists on the tenant (true for the bot user at minimum).

### Delta D-5.3 (Task 5.3: `create_employee` orchestrator)

Before building the step-1 payload, the orchestrator must resolve the wage site:

```python
# Wage site resolution: pick the first resolvable site from the caller's request
# (wage rate applies globally but the form requires attribution to one site).
resolved_sites_for_wage = site_tree.resolve_all(resolved_request.available_sites)
if not resolved_sites_for_wage:
    raise ValidationError("available_sites is empty — cannot resolve wage attribution site")
wage_site = resolved_sites_for_wage[0]
```

Pass `wage_site_id=wage_site.id` to `build_employee_step1_payload`. Include `wage_site.name` in the returned `EmployeeCreated.wage_site` field.

Update POST URLs:
- Step 1 target is `/employee/insert` (unchanged).
- Step 2 target is `/employee/permissions/update` (not `/employee/<id>/permissions`).
- New employee ID is extracted from the redirect location (typically `/employee/edit/<id>` or `/employee/permissions/<id>`); the existing regex `r"/employee/(?:edit|permissions)/(\d+)"` covers both.

Add `wage_site=wage_site.name` to the `EmployeeCreated(...)` constructor call. The `EmployeeCreated` model (Task 2.5) must have a `wage_site: str` field — add it there.

### Delta D-2.5 (Task 2.5: output models)

Add `wage_site: str` to `EmployeeCreated`:

```python
class EmployeeCreated(_BackofficeBaseModel):
    employee_id: int
    pos_user_id: int
    pos_pin: int
    first_name: str
    last_name: str
    email: str
    backoffice_user_id: int | None = None
    backoffice_username: str | None = None
    backoffice_password: str | None = None
    permission_applied: str
    sites_granted: list[str]
    departments: list[str]
    wage_site: str
    warnings: list[str] = Field(default_factory=list)
```

Same for `EmployeeDisabled`:

```python
class EmployeeDisabled(_BackofficeBaseModel):
    employee_id: int
    pos_user_id: int
    email: str | None = None
    disabled_at: datetime
```

### Delta D-6.1 (Task 6.1: `find_employee_in_list_html`)

The real employee list table doesn't have `data-employee-id` attributes on `<tr>`. Employee IDs must be extracted from the action links in the last column (`/employee/edit/<id>`, `/employee/permissions/<id>`, etc.).

Replace the lookup implementation:

```python
import re
from bs4 import BeautifulSoup

from .exceptions import NotFoundError


_EMP_ID_RE = re.compile(r"/employee/(?:edit|permissions|compensation)/(\d+)")


def find_employee_in_list_html(
    html: str,
    *,
    pos_user_id: int | None = None,
    email: str | None = None,
) -> int:
    if not (pos_user_id or email):
        raise ValueError("pos_user_id or email is required")
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="table-employees-list")
    if table is None:
        raise NotFoundError("employee list table not found in HTML")
    rows = table.find_all("tr")
    pos_user_id_str = str(pos_user_id) if pos_user_id is not None else None
    for row in rows:
        # Extract candidate employee_id from any action link in the row
        emp_id: int | None = None
        for a in row.find_all("a", href=True):
            m = _EMP_ID_RE.search(a["href"])
            if m:
                emp_id = int(m.group(1))
                break
        if emp_id is None:
            continue
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        row_text = " | ".join(cells)
        if pos_user_id_str and pos_user_id_str in row_text:
            return emp_id
        if email and email.lower() in row_text.lower():
            return emp_id
    raise NotFoundError(
        f"no employee found for "
        f"{'pos_user_id=' + str(pos_user_id) if pos_user_id else 'email=' + (email or '')}"
    )
```

**Known limitation:** the visible list columns may not include email. If email lookup fails via the list scan, the wrapper falls back to iterating the list and fetching each `/employee/edit/<id>` to check the email field server-side — that's too slow for production and is deferred. For Milestone 1, **document that email lookup on `disable_employee` requires the email to appear in the employee list's visible columns**. If the caller has only an email and it's not in the list, they get `NotFoundError` with a hint to use `pos_user_id` instead. (Alternatively, a server-side search param `/employee?search=...` may exist — test during Task 1.4.)

### Delta D-6.2 (Task 6.2: `disable_employee`) — UPDATED after Phase 1.4 write testing

**Finding from Phase 1.4 Write 1.5 test:** the minimal-POST approach does NOT work. Sending `{employee[id]=X, employee[isActive]=0}` to `/employee/update` returns HTTP 302 but does NOT actually disable the employee. Symfony's form binding reads the *presence* of `employee[isActive]` in the POST as "checked = true", regardless of the value (`"0"` or `"1"`). To uncheck a checkbox via the wire, the field must be **absent** from the POST entirely.

Additionally, a POST containing only `employee[id]` without the other form fields also fails to update anything — the form is effectively ignored.

**The only reliable disable mechanism is a full form round-trip:**

1. `GET /employee/edit/<id>` — load the full edit form HTML
2. Parse every input/select/textarea inside `<form action="/employee/update">` into a payload dict, preserving all current values
3. **OMIT** `employee[isActive]` from the payload (this is the "flip to unchecked" action)
4. Preserve all other checkboxes based on their current `checked` state — include them only if they were checked
5. `POST /employee/update` with the full payload

Replacement implementation:

```python
from datetime import datetime, timezone
from typing import Any

import re
from bs4 import BeautifulSoup

from .exceptions import BackofficeServerError, NotFoundError
from .models import DisableEmployeeRequest, EmployeeDisabled


def disable_employee(
    *,
    session: Any,
    request: DisableEmployeeRequest,
) -> EmployeeDisabled:
    # Step 1: look up employee_id via the employee list (pre-flight cache not
    # applicable here since we want a fresh snapshot)
    list_resp = session.get("/employee?limit=10000")
    _check_create_response(list_resp)
    employee_id = find_employee_in_list_html(
        list_resp.text,
        pos_user_id=request.pos_user_id,
        email=request.email,
    )

    # Step 2: GET the edit form and parse it into a payload dict
    edit_resp = session.get(f"/employee/edit/{employee_id}")
    _check_create_response(edit_resp)
    payload = _parse_edit_form_into_payload(edit_resp.text, drop_fields={"employee[isActive]"})

    # Ensure the employee id is in the payload
    payload.setdefault("employee[id]", str(employee_id))

    # Step 3: POST the full payload with isActive omitted
    resp = session.post("/employee/update", data=payload, allow_redirects=False)
    _check_create_response(resp)

    # Step 4: verify the disable took effect
    verify_resp = session.get(f"/employee/edit/{employee_id}")
    soup = BeautifulSoup(verify_resp.text, "html.parser")
    active_input = soup.find("input", attrs={"name": "employee[isActive]"})
    still_active = active_input is not None and active_input.has_attr("checked")
    if still_active:
        raise BackofficeServerError(
            f"disable POST accepted but employee {employee_id} is still active — "
            "full-form round-trip did not take effect"
        )

    return EmployeeDisabled(
        employee_id=employee_id,
        pos_user_id=request.pos_user_id or 0,
        email=request.email,
        disabled_at=datetime.now(timezone.utc),
    )


def _parse_edit_form_into_payload(
    html: str,
    *,
    drop_fields: set[str],
) -> list[tuple[str, str]]:
    """Parse an /employee/edit/<id> form into a list of (name, value) tuples
    suitable for a requests POST.

    - Text/hidden/number/email/tel/password fields are always included with their
      current value (empty string if no value).
    - Checkboxes are included (with their `value` attribute as the posted value)
      only if they are currently checked.
    - Radios are included only if currently checked.
    - Select single: include the selected option's value; skip if placeholder is selected.
    - Select multiple: include each selected option as a separate entry.
    - Textareas are included with their current text content.
    - Fields in `drop_fields` are always excluded (used to uncheck a checkbox by omission).
    """
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", action=re.compile(r"/employee/update"))
    if form is None:
        raise BackofficeServerError("could not locate /employee/update form on edit page")

    out: list[tuple[str, str]] = []
    for el in form.find_all(["input", "select", "textarea"]):
        name = el.get("name")
        if not name or name in drop_fields:
            continue
        if el.name == "input":
            t = (el.get("type") or "text").lower()
            if t in ("text", "hidden", "number", "email", "tel", "password", "search", "url", "date", "time"):
                out.append((name, el.get("value") or ""))
            elif t == "checkbox":
                if el.has_attr("checked"):
                    out.append((name, el.get("value") or "on"))
                # otherwise omit
            elif t == "radio":
                if el.has_attr("checked"):
                    out.append((name, el.get("value") or ""))
            elif t in ("submit", "button", "reset"):
                continue
            else:
                # unknown type — include by value for safety
                out.append((name, el.get("value") or ""))
        elif el.name == "select":
            if el.has_attr("multiple"):
                for opt in el.find_all("option"):
                    if opt.has_attr("selected"):
                        out.append((name, opt.get("value") or ""))
            else:
                sel_opt = next((o for o in el.find_all("option") if o.has_attr("selected")), None)
                if sel_opt is None:
                    # Default: first non-empty option if the form had no explicit selection
                    sel_opt = next((o for o in el.find_all("option") if (o.get("value") or "").strip()), None)
                if sel_opt is not None:
                    out.append((name, sel_opt.get("value") or ""))
        elif el.name == "textarea":
            out.append((name, el.get_text()))
    return out
```

**Important note about disabled hidden inputs:** the site availability markup contains hidden `<input type="hidden" name="employee[sites][N][siteId]" disabled value="N">` for sites that are NOT available to the employee. `_parse_edit_form_into_payload` must NOT include fields with the `disabled` attribute, because browsers do not submit disabled fields. Add this check:

```python
        if el.get("disabled") is not None:
            continue  # disabled inputs are not submitted by real browsers
```

...at the top of the element loop, right after the `drop_fields` check.

### Delta D-7.1 (Task 7.1: BO user creation)

- `/user/insert` form fields confirmed: `employee[isOnSiteEmployee]`, `user[employeeId]`, `employee[firstName]`, `employee[lastName]`, `employee[email]`, `user[username]`, `user[password]`, `user[confirmPassword]`, `user[linkExistingAccount]`.
- The step-2 permissions URL for BO users is not yet captured. Hypothesis: `GET /user/permissions/<id>` and `POST /user/permissions/update` (mirroring the employee pattern). **Confirm in Task 1.4 before writing this task.**
- BO permissions payload follows the same minimal-`templateId` pattern as the employee side (Delta D-5.2).
- Linked mode: set `employee[isOnSiteEmployee]=1` and `user[employeeId]=<id>`. Leave `employee[firstName]`/`employee[lastName]` empty.
- Standalone mode: set `employee[isOnSiteEmployee]=0`, provide `employee[firstName]`, `employee[lastName]`. Leave `user[employeeId]` empty.

### Delta D-1.4 (Task 1.4: reduced scope)

Tasks 1.1–1.3 already captured the read-only fixtures and notes. The remaining Task 1.4 work is narrowed to these specific write experiments, each requiring explicit user approval at the moment of submission:

1. **Create one exploration employee** via `/employee/insert` to capture the real response payload (including the new `employee_id`) and the redirect-to-permissions URL pattern. Record fixture: `tests/fixtures/payloads/allowed_employee_insert.json`, `tests/fixtures/html/employee_insert_response.html`.
2. **Submit the permissions template** (`templateId` only) for that employee via `/employee/permissions/update`. Confirms whether the minimal payload is accepted. Record fixture: `tests/fixtures/payloads/allowed_employee_permissions_update.json`.
3. **Test minimal disable** — `POST /employee/update` with only `employee[id]` + `employee[isActive]=0`. Verify via follow-up GET `/employee/edit/<id>` that: (a) `isActive` is now 0, (b) all other fields (name, wage, sites, departments) are unchanged. If they were wiped, document the failure and mark Delta D-6.2's fallback as required.
4. **Create a linked BO user** pointing at the exploration employee, to confirm the `/user/permissions/...` URL pattern and BO template list.
5. **Cleanup:** ensure the exploration employee is left disabled and the BO user is disabled or deleted.

Each of the above requires explicit user approval at dispatch time, per the durable no-writes-without-approval rule. They produce the fixtures that unblock Phase 5's `test_payload_matches_recorded_fixture` test and the `parse_permissions` test for the BO scope.
