# Sonny's Backoffice Wrapper — Milestone 1 Design

**Date:** 2026-04-13
**Status:** Approved — revised after Phase 1 exploration on 2026-04-13
**Owner:** Christopher Nance

> **Revision note (2026-04-13, post-exploration):** This spec was originally written before the `washu` test tenant was explored with Playwright. That exploration surfaced several deltas from the pre-exploration assumptions (wage subsystem, permission template matrix, disable via `employee[isActive]`, numeric POS credentials, Symfony stack with no CSRF tokens). The sections below have been revised in place to match what the live tenant actually serves. The authoritative source for exact form field names, URL patterns, and HTML selectors is `tests/fixtures/exploration_notes.md`.

## 1. Scope & Goals

A pip-installable Python library that provides programmatic user-management for Sonny's Backoffice, the web-based admin console for Sonny's Carwash Controls POS systems. Sonny's offers a read-only Data API (wrapped by the sibling `sonnys-data-client` library), but has no API surface for creating, modifying, or disabling users. This library closes that gap by driving the Backoffice HTTP endpoints directly with a pure-`requests` session — no headless browser at runtime.

### Deliverables

- Python package `sonnys-backoffice-wrapper` (import name `sonnys_backoffice`), installable via `pip install git+https://github.com/christopher-nance/Sonnys-Backoffice-Wrapper.git`.
- Three public operations on a `SonnysBackofficeClient`:
  1. `create_employee(...)` — creates a POS employee, optionally with a linked Backoffice user in the same call.
  2. `disable_employee(pos_user_id=... | email=...)` — deactivates an existing employee (preserves history, no hard delete).
  3. `create_backoffice_user(...)` — creates a standalone Backoffice-only user (no POS access), or links to an existing employee.
- Three discovery helpers: `list_sites()`, `list_departments()`, `list_permissions(scope=...)`.
- MkDocs Material documentation site deployed to GitHub Pages.
- Unit tests against captured HTML fixtures; integration tests (marked and skipped by default) against the live test tenant.

### Explicitly out of scope (deferred to later milestones)

- `modify_employee()` of any kind (wage rate, permissions, departments, personal info). Each of these lives behind a different Backoffice URL and deserves its own targeted function. A unified modify endpoint is not a goal.
- Reporting / data scraping. That is `sonnys-data-client`'s job.
- Async support.
- A CLI wrapper.
- Cross-process session persistence (pickling cookies, etc.).

### Success criteria

- A user can install via pip and, in under ten lines of Python, successfully create an employee on their tenant.
- The same caller code works unchanged on a flat tenant (sites only) and a multi-region tenant (regions → districts → sites).
- Bulk operations (loops invoking `create_employee` hundreds of times) do not re-authenticate per call.
- The docs site ships with a Getting Started section, Guides, auto-generated API Reference, runnable Examples, and a Troubleshooting page.

## 2. Architecture & Module Layout

### Repository structure

```
Sonnys-Backoffice-Wrapper/
├── src/sonnys_backoffice/
│   ├── __init__.py              # Re-exports SonnysBackofficeClient, exceptions, models
│   ├── client.py                # SonnysBackofficeClient — public façade
│   ├── session.py               # _BackofficeSession — requests.Session + login, CSRF, re-auth
│   ├── employees.py             # create_employee / disable_employee (form builders + POST orchestration)
│   ├── bo_users.py              # create_backoffice_user logic
│   ├── permissions.py           # _resolve_permission (case-insensitive match + "General User" fallback)
│   ├── sites.py                 # Site-tree fetcher + name→(site_id, district_id, region_id) resolver
│   ├── departments.py           # Department list fetcher + "Greeter" default
│   ├── passwords.py             # _generate_pos_pin (5-digit) + _generate_bo_password (12-char alphanum+symbol)
│   ├── models.py                # Pydantic v2 models — inputs (with @field_validator), outputs, domain objects
│   └── exceptions.py            # Exception hierarchy
├── docs/                        # MkDocs Material source
│   ├── index.md
│   ├── getting-started/
│   ├── guides/
│   ├── examples/
│   ├── reference/               # mkdocstrings-generated API ref
│   ├── troubleshooting.md
│   └── changelog.md
├── tests/
│   ├── unit/                    # Fixture-based, no network
│   ├── integration/             # Live tenant, @pytest.mark.integration, skipped by default
│   └── fixtures/
│       ├── html/                # Captured HTML snapshots from exploration
│       ├── payloads/             # Recorded-but-not-sent form payloads (JSON)
│       └── exploration_notes.md
├── scripts/
│   └── explore.py               # One-time Playwright exploration script (committed for re-runs)
├── mkdocs.yml
├── pyproject.toml               # hatchling; requests, beautifulsoup4, pydantic
├── LICENSE                      # Wash Associates Business Internal Use License 1.0 (copied from sibling repo)
└── README.md
```

### Key architectural decisions

**Thin façade over feature modules.** `SonnysBackofficeClient` holds a `_BackofficeSession` and delegates to the feature modules (`employees`, `bo_users`, etc.). This keeps each file small enough to reason about in isolation and lets the deferred `modify_employee` work plug in as new modules without touching the façade.

**`_BackofficeSession` owns auth state.** Lazy login on first authed call (not at `__init__`). Caches session cookies and CSRF tokens. On a 401 or a redirect to the login page mid-request, the session transparently re-logs in once and retries the original request. The session is never exposed publicly — callers only touch `SonnysBackofficeClient`.

**Shared resolvers cached per client instance.** `sites`, `departments`, and `permissions` fetch-once-and-cache on first access. Exposed via `client.list_sites()`, `client.list_departments()`, and `client.list_permissions(scope=...)` so callers can discover what is available on their tenant. Each helper accepts `refresh=True` to force a re-fetch. Cache is per-client — constructing a new client re-fetches from scratch.

**Pydantic v2 drives both input validation and output typing.** `models.py` contains:

- **Input models** (`CreateEmployeeRequest`, `CreateBackofficeUserRequest`, `DisableEmployeeRequest`) carrying `@field_validator` for phone normalization (strip all non-digits, require 9 or 10 digits), email format (regex for `@domain.tld`), name trimming (leading/trailing whitespace only, preserve Unicode/symbols), POS PIN format (5-digit check when user-provided), and permission-name handling. `@model_validator` enforces "exactly one of" rules (e.g., `disable_employee` requires exactly one of `pos_user_id` or `email`; `create_backoffice_user` requires exactly one of `link_to_employee_*` or `first_name`+`last_name`). Callers can either construct these models explicitly or pass kwargs to client methods and let the façade build the model internally.
- **Output models** (`EmployeeCreated`, `BackofficeUserCreated`, `EmployeeDisabled`) all `BaseModel` subclasses so callers get `.model_dump()` for free. Every result carries a `warnings: list[str]` field for soft issues such as "permission 'CSA' not found in tenant, fell back to 'General User'".
- **Domain models** (`Site`, `Department`, `Permission`, `Region`, `District`) used by the discovery helpers.
- Model config: `model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")` so typo'd kwargs fail loudly instead of silently.

**Form building is deterministic and testable.** Each feature module has a `_build_*_payload(model)` function that takes a validated pydantic input model and returns a plain `dict` of form fields. No HTTP, no session touching. Unit-tested against captured HTML fixtures. The HTTP POST happens in a separate `_submit_*(session, payload)` function. This split is what makes the "discover via Playwright, then codify as requests" approach work reliably.

**Site hierarchy auto-detection.** The site resolver fetches `/employee/create` on first use, parses the HTML, and detects whether the tenant uses regions/districts or flat sites by looking for the presence of the region/district toggle markup. Both shapes produce the same internal representation: `{site_name → Site(id=..., district_id=..., region_id=...)}`, with `district_id` and `region_id` being `None` on flat tenants. Callers always pass site names; the library always produces the right payload shape. Site names are guaranteed globally unique per tenant (confirmed business invariant), so no disambiguation is needed.

**Permission name resolution** lives in `permissions.py` as a shared helper used by both `create_employee` and `create_backoffice_user`. The rules: (1) lowercase both the caller's input and the tenant's available list before comparing; (2) if no match, emit a `warnings.warn` + log entry and apply `"General User"` as the fallback; (3) do not raise. The docs prominently note that when creating an employee with `requires_backoffice=True`, the POS permission name and the Backoffice permission name must match (after lowercasing) or the BO user creation step will fail.

### Dependencies

| Package | Version | Purpose |
|---|---|---|
| `requests` | `>=2.28,<3` | HTTP client |
| `beautifulsoup4` | `>=4.12,<5` | Parse Backoffice HTML (CSRF tokens, site tree, permissions list, employee lookups) |
| `pydantic` | `>=2.10,<3` | Input validation and output typing (pin matches `sonnys-data-client`) |
| `pytest` (dev) | `>=7.0` | Tests |
| `ruff` (dev) | `>=0.1` | Lint/format |
| `playwright` (dev) | latest | Fixture recording only — never a runtime dep |
| `mkdocs-material` (docs) | `>=9.5` | Docs site |
| `mkdocstrings[python]` (docs) | `>=0.24` | Auto-generated API reference |

### Data flow: `create_employee()`

```
caller kwargs
   → CreateEmployeeRequest(**kwargs)
     (pydantic validators: phone normalized, email checked, name trimmed, required fields enforced)
   → sites resolver (site names → [(site_id, district_id, region_id), ...], auto-detect hierarchy)
   → departments resolver (ensure "Greeter" is present; default to ["Greeter"] if empty)
   → permissions resolver, scope="pos" (case-insensitive match → "General User" fallback with warning)
   → passwords.generate_pos_pin() if caller did not provide one
   → _build_employee_step1_payload(request) → POST /employee/insert → parse response → new employee_id
   → _build_employee_step2_permissions_payload(request, sites) → POST to POS permissions URL (TBD from exploration)
   → IF requires_backoffice=True:
        permissions resolver, scope="backoffice" (must match POS permission name after lowercasing)
        passwords.generate_bo_password() if caller did not provide one
        → _build_bo_user_step1_payload(request, linked_employee_id=employee_id) → POST /user/insert → bo_user_id
        → _build_bo_user_step2_permissions_payload → POST to BO permissions URL (TBD)
   → return EmployeeCreated(employee_id, pos_user_id, pos_pin, backoffice_*, warnings=[...])
```

Each arrow is a function that can be tested independently given a captured HTML fixture.

### Session and authentication lifecycle

- `SonnysBackofficeClient(subdomain=..., username=..., password=...)` does not log in at construction.
- On first call to any method that needs authentication, `_BackofficeSession` performs a login: GET the login page, extract the CSRF token, POST credentials, verify the success-redirect landed on an authed page.
- All subsequent calls share the same `requests.Session` (cookies, connection pooling).
- On any response that indicates session expiration (to be determined during exploration — candidates: HTTP 401, HTTP 302 to `/login`, or an HTML body containing a login form), the session automatically re-logs in and retries the original request exactly once. A second expiration signal raises `AuthenticationError`.
- `client.close()` closes the underlying `requests.Session`. Context-manager support (`with SonnysBackofficeClient(...) as client:`) calls `close()` on exit.

### Exception hierarchy

```
SonnysBackofficeError (base)
├── AuthenticationError       # Bad credentials, or re-login failed after session expiration
├── NotFoundError              # Employee not found by pos_user_id/email
├── ValidationError            # Bad phone number, bad email format, missing required field, "exactly one of" violation
├── PermissionDeniedError      # Bot user lacks Admin rights or lacks all-sites access
├── DuplicateError             # Email or POS User ID already exists on this tenant
└── BackofficeServerError      # Unexpected HTTP 5xx, or HTML response the parser couldn't handle
```

All inherit from `SonnysBackofficeError` so callers can catch broadly (`except SonnysBackofficeError`) or narrowly. `ValidationError` is raised both by pydantic validators (wrapped/re-raised as this library's class) and by server-side rejections parsed from response HTML.

## 3. Public API

All methods use keyword-only arguments to prevent breakage when new optional parameters are added.

### Client constructor and lifecycle

```python
class SonnysBackofficeClient:
    def __init__(
        self,
        *,
        subdomain: str,              # e.g. "washu" → https://washu.sonnyscontrols.com
        username: str,
        password: str,
        timeout: float = 30.0,       # Per-request timeout in seconds
        max_retries: int = 2,        # Transient-failure retries (not auth retries)
        user_agent: str | None = None,
    ) -> None: ...

    def __enter__(self) -> "SonnysBackofficeClient": ...
    def __exit__(self, *exc) -> None: ...
    def close(self) -> None: ...
```

### Discovery helpers

```python
    def list_sites(self, *, refresh: bool = False) -> list[Site]: ...
    def list_departments(self, *, refresh: bool = False) -> list[Department]: ...
    def list_permissions(
        self,
        *,
        scope: Literal["pos", "backoffice"],
        refresh: bool = False,
    ) -> list[Permission]: ...
```

### Employee operations

```python
    def create_employee(
        self,
        *,
        first_name: str,
        last_name: str,
        phone: str,                              # 9 or 10 digits after stripping symbols
        email: str,                              # Must contain @domain.tld
        pos_user_id: int,                        # Caller-assigned numeric POS login ID (Backoffice stores as integer)
        pos_pin: int | None = None,              # 5-digit numeric PIN; auto-generated if None
        wage_rate: Decimal | float,              # Dollars per hour. Applies globally across all sites the employee can work at.
        overtime_wage_rate: Decimal | float | None = None,  # Defaults to wage_rate * 1.5
        start_date: datetime,
        available_sites: list[str] | Literal["all"],
        permission: str,                         # REQUIRED. Case-insensitive name of a POS permission template. Unknown names fall back to "General User" with a warning; omission raises a pydantic ValidationError.
        departments: list[str] | None = None,    # Defaults to ["Greeter"]; "Greeter" auto-added if missing
        emergency_contact_name: str | None = None,
        emergency_contact_phone: str | None = None,
        adp_employee_id: str | None = None,      # Optional ADP report linkage
        requires_backoffice: bool = False,
        backoffice_username: str | None = None,  # Required if requires_backoffice=True
        backoffice_password: str | None = None,  # Auto-generated 12-char if None
    ) -> EmployeeCreated: ...

    def disable_employee(
        self,
        *,
        pos_user_id: int | None = None,          # Exactly one of pos_user_id / email required
        email: str | None = None,
    ) -> EmployeeDisabled: ...
```

### Backoffice user operations

```python
    def create_backoffice_user(
        self,
        *,
        username: str,
        email: str,
        password: str | None = None,             # Auto-generated 12-char if None
        permission: str = "General User",
        # Option 1: link to existing employee
        link_to_employee_pos_user_id: str | None = None,
        link_to_employee_email: str | None = None,
        # Option 2: standalone external user
        first_name: str | None = None,           # Required if not linking
        last_name: str | None = None,            # Required if not linking
        available_sites: list[str] | Literal["all"] = "all",
    ) -> BackofficeUserCreated: ...
```

### Result models

```python
class EmployeeCreated(BaseModel):
    employee_id: int                       # Backoffice internal ID
    pos_user_id: int
    pos_pin: int                           # Returned regardless of who generated it (5-digit numeric)
    first_name: str
    last_name: str
    email: str
    backoffice_user_id: int | None = None  # Populated only if requires_backoffice=True
    backoffice_username: str | None = None
    backoffice_password: str | None = None
    permission_applied: str                # Actual permission template name (may differ from requested if fallback fired)
    sites_granted: list[str]
    departments: list[str]
    wage_site: str                         # Site name to which the wage entry was booked (arbitrary tie-breaker among available_sites)
    warnings: list[str] = []

class BackofficeUserCreated(BaseModel):
    user_id: int
    username: str
    password: str
    email: str
    linked_employee_id: int | None = None
    permission_applied: str
    sites_granted: list[str]
    warnings: list[str] = []

class EmployeeDisabled(BaseModel):
    employee_id: int
    pos_user_id: int
    email: str | None
    disabled_at: datetime
```

### API ergonomics decisions

- `available_sites` accepts either `list[str]` (site names) or the literal `"all"`. The literal flips the "Available all Regions / Sites" toggle at whichever hierarchy level is appropriate for the tenant.
- "Exactly one of" constraints (lookup keys on `disable_employee`, link-vs-standalone on `create_backoffice_user`) are validated via `@model_validator` on private pydantic request models, so they raise `ValidationError` before any HTTP round-trip.
- Generated secrets (POS PIN, Backoffice password) are always returned in the result object, even if the caller supplied them explicitly, so bulk-creation scripts can log a single source of truth without threading inputs through separately.
- Result objects always include a `warnings` list. Soft issues (permission fallback, auto-added "Greeter" department) go there rather than raising.

## 4. Exploration Plan

Before writing production code, capture the real HTTP shapes of Backoffice by driving the UI with Playwright using the test account (`SonnysWrapperTestAccount` on the `washu` tenant). Read-only exploration is pre-approved; any action that would commit a write requires explicit per-step approval.

### Write-safety protocol

- Steps that GET pages or intercept would-be POSTs (recording payload, canceling before submit) are pre-approved.
- Steps that require actually committing a write to prove the full flow works (employee creation, permission submission, disable) will stop and request approval before proceeding. These will use a single disposable test employee that is disabled/cleaned up at the end of the exploration session.
- This aligns with the durable rule in `feedback_no_writes_without_approval.md`.

### Exploration targets

| # | Action | URL / Target | Capture |
|---|---|---|---|
| 1 | Login flow | `/login` → POST `/login/authenticate` (path TBD) | Login form HTML, CSRF token location, POST body shape, success-redirect target, session cookie names |
| 2 | Session expiration probe | Any authed page after session timeout | How Backoffice signals "session expired" (302 to `/login`? 401? HTML with login form?). Determines the re-auth trigger logic. |
| 3 | Site tree (flat tenant) | `/employee/create` on a non-region tenant | HTML pattern for `employee[siteIds][]` checkboxes; site ID → name mapping |
| 4 | Site tree (region/district tenant) | `/employee/create` on WashU | Full hierarchy markup: `disabledRegions[]`, `disabledDistricts[]`, `sites[N][isAvailable]`, `sites[N][siteId]`, `isAllRegionsAllowed`, `isAllDistrictsAllowedByRegion[]`, `isAllSitesAllowedByDistrict[]` |
| 5 | Departments list | `/employee/create` | Where department options live (dropdown? multi-select?), option values, how "Greeter" is represented |
| 6 | POS permissions list | "Set Permissions" from `/employee/create` | Permission list HTML, role names, role IDs, form field names, target URL |
| 7 | Employee create — step 1 POST | Fill `/employee/create`, intercept submit | Full form field dump: every `name="..."` field, required vs optional, hidden fields, CSRF placement. Record payload, **cancel before submit**. |
| 8 | Employee create — step 2 POST | Would-be permissions POST | Target URL, payload shape, HTTP method. **Cancel.** |
| 9 | BO user create — linked mode | `/user/create` with "Employee of the Wash" = Yes | Form fields when `employee[isOnSiteEmployee]=1` + `user[employeeId]` selected |
| 10 | BO user create — standalone mode | `/user/create` with toggle = No | Form fields when `isOnSiteEmployee=0` + `firstName`/`lastName` required |
| 11 | BO user create — step 2 POST | Would-be permissions POST | Target URL, payload shape, whether it mirrors POS permissions exactly |
| 12 | BO permissions list | "Set Permissions" on `/user/create` | Same shape as #6, for Backoffice side. Confirms POS/BO field-name symmetry required by the permission-matching rule. |
| 13 | Employee lookup | `/employee` list page | HTML structure of the employee table; how to find `employee_id` by `pos_user_id` or `email`. Likely needs pagination or a search query param. |
| 14 | Disable employee | Employee edit page, find "Disable"/"Terminate"/"Deactivate" control | Is it a toggle on the edit form? A separate URL like `/employee/<id>/disable`? A POST with a specific field? **Record only, do not submit.** |
| 15 | Error responses | Submit intentionally invalid fields (duplicate email, etc.) **with explicit approval at submit-time** | HTML structure of server-side error messages so parsers can extract them for `ValidationError` / `DuplicateError` |

### Exploration deliverables

- `tests/fixtures/html/` — Raw HTML snapshots of every page above
- `tests/fixtures/payloads/` — JSON files with recorded-but-not-sent form payloads (field names, example values)
- `tests/fixtures/exploration_notes.md` — Human-readable notes: field-to-concept mapping, gotchas, exact re-auth signal, URL patterns
- `scripts/explore.py` — The Playwright script used to collect everything, committed for re-runs if Backoffice changes

### Phase gate

Exploration is Phase 1 of the implementation plan. **No production code is written until the fixtures are captured and committed.** This is what makes the pure-`requests` approach viable — every form builder will be written by reading a fixture, not by guessing.

## 5. Documentation Outline

MkDocs Material site, deployed to the `gh-pages` branch via `mkdocs gh-deploy`. Mirrors the style of `sonnys-data-client`'s docs site.

### `mkdocs.yml` navigation

```yaml
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

### Page content

**`index.md`** — Mirrors README. Three parts: what the library is and why it exists (Sonny's has no official user-management API), install one-liner, 10-line quickstart that creates a single employee.

**`getting-started/installation.md`** — `pip install git+https://github.com/christopher-nance/Sonnys-Backoffice-Wrapper.git`, Python 3.10+ requirement, guidance on pinning to a tag for production use.

**`getting-started/quickstart.md`** — End-to-end: import → instantiate client → create one employee → inspect the result object → disable that employee. ~30 lines, copy-pasteable.

**`getting-started/auth.md`** — How to set up the bot user in Backoffice: create a dedicated account, grant Administrator role, grant all-sites access, store credentials in environment variables, pass to `SonnysBackofficeClient`. Explains why a dedicated bot (not a human's login) matters: session stability, audit trail, rotation.

**`guides/create-employee.md`** — The biggest guide. Walks through every argument of `create_employee()` with examples. Covers required vs optional fields; phone normalization rules (9-10 digits, symbols stripped); email format expectations; how `departments` defaults to `["Greeter"]` and why that matters for greeter commission; how `available_sites` works identically on flat and multi-region tenants; how `pos_pin` and `backoffice_password` auto-generation works and that generated values are always returned; the `requires_backoffice=True` flow and the POS/BO permission-name-matching rule (prominent callout); and a worked example showing a full call plus the returned `EmployeeCreated` object.

**`guides/create-backoffice-user.md`** — Covers both modes: linking to an existing employee vs standalone external user. Password generation rules. When to use which mode.

**`guides/disable-employee.md`** — Explains disable vs hard-delete (preserves history, POS ID not immediately reusable), the two lookup keys (`pos_user_id` OR `email`, exactly one), and what happens to any linked Backoffice user.

**`guides/sites-regions-districts.md`** — Explains the hierarchy auto-detection. Shows the same code working against a flat tenant and a multi-region tenant. Shows `client.list_sites()` for discovery. Notes the site-name uniqueness guarantee.

**`guides/permissions.md`** — Permission name resolution rules: case-insensitive match, unknown name falls back to "General User" with a warning, POS/BO names must match when creating both. How to discover available roles via `client.list_permissions(scope="pos")` and `scope="backoffice"`.

**`guides/bulk-operations.md`** — The pattern for loops: one client instance, iterate over a source (CSV, database, HRIS export), handle `ValidationError` / `DuplicateError` per row without aborting the batch, collect result objects, summarize at the end. This is the primary use case the library exists for.

**`guides/error-handling.md`** — The exception hierarchy, how to catch broadly vs narrowly, how to read the `warnings` list on result objects (non-fatal issues), when to retry vs abort.

**`examples/onboard-new-hire.md`** — Single runnable script: takes a dict of new-hire info, calls `create_employee` with `requires_backoffice=True`, prints the generated PIN and BO password for the manager to hand to the employee.

**`examples/bulk-disable-from-csv.md`** — Reads a CSV of former employees, disables each by email, writes a success/failure report CSV.

**`examples/hris-sync.md`** — Sketch of using this library alongside `sonnys-data-client` to reconcile Backoffice state against an HRIS source of truth.

**`reference/`** — Auto-generated from docstrings via `mkdocstrings`. Every public method, every pydantic model, every exception class. Zero manual maintenance — written through docstrings on the code.

**`troubleshooting.md`** — Common errors and what they mean:

- `AuthenticationError` — bad credentials, or the bot user lacks Administrator rights
- `PermissionDeniedError` — bot has Administrator but not all-sites access
- `DuplicateError` — POS ID or email already exists (with a snippet showing how to check first with a lookup)
- `ValidationError` on phone number — reminds about the 9-10 digit rule
- `BackofficeServerError` with unparseable HTML — means Sonny's changed the page structure; opens a GitHub issue link
- How to enable debug logging to see raw HTTP traffic
- How to dump a session cookie for manual debugging

**`changelog.md`** — Hand-maintained, grows with releases. Starts with `v0.1.0 — Initial release: create_employee, disable_employee, create_backoffice_user`.

## 6. Testing Strategy

**Unit tests (`tests/unit/`)** — No network. Read HTML fixtures from `tests/fixtures/html/`, exercise form builders, validators, password generators, the permission resolver, the site resolver against both flat and hierarchical fixtures, and the pydantic input models. Fast enough to run on every save.

**Integration tests (`tests/integration/`)** — Hit the live test tenant. Marked `@pytest.mark.integration`, skipped by default, run manually or in a dedicated CI job with credentials in secrets. Each test creates resources with a unique marker prefix and cleans up at the end. Follows the same "no writes without approval" discipline: integration tests that write will be gated behind explicit opt-in.

**Test coverage targets** — Aim for ≥90% line coverage on `models.py` (including the pydantic validators), `permissions.py`, `sites.py`, `departments.py`, `passwords.py`, and the `_build_*_payload` form builders in `employees.py` and `bo_users.py`. Lower coverage is acceptable on `session.py` (hard to fake auth flow in unit tests — covered by integration).

## 7. Open Questions Resolved During Brainstorming

For the record, these decisions were made through interactive clarification and are codified in the memory system:

- **Transport:** Pure `requests`, not Playwright-at-runtime.
- **Site identification:** Flat site names, library auto-resolves hierarchy. Names are globally unique per tenant.
- **Employee identification for disable:** Either `pos_user_id` or `email` (both unique per tenant).
- **Modify operations:** Deferred to a later milestone; different fields live behind different URLs.
- **Password generation:** 5-digit numeric for POS PIN, 12-char alphanumeric+symbol for Backoffice; caller-provided values always round-trip in the result.
- **Permission matching:** Case-insensitive string compare, fallback to "General User" with a warning on miss, POS/BO names must match for linked creation.
- **User creation flow:** Two-step POST (basic info → permissions page) for both employees and Backoffice users.
- **Result types:** Pydantic v2 models, matching the sibling `sonnys-data-client` repo.
- **Python version:** 3.10+, no legacy support.
- **License:** Copied verbatim from `sonnys-data-client` (Wash Associates Business Internal Use License 1.0).
- **Docs:** MkDocs Material + mkdocstrings, deployed to GitHub Pages via `mkdocs gh-deploy`.

### Additional decisions from Phase 1 exploration (2026-04-13)

- **Stack:** Backoffice is a Symfony + PHP application. No CSRF tokens anywhere (login, create forms, permission forms). Session cookie is `PHPSESSID`. The `_BackofficeSession` implementation does not scrape CSRF tokens — it only manages cookies.
- **Login endpoint:** `POST /login_check` with `_username` / `_password` fields (Symfony Security Component convention). Success redirects to `/` (home dashboard). Failure re-renders `/login`.
- **POS credentials are numeric.** `posCredential[POSLoginID]` and `posCredential[POSLoginPassword]` are both `type=number` in the form. Public API types are `pos_user_id: int` and `pos_pin: int`.
- **Wage applies globally.** Even though the form has a `wage[siteId]` field (required, selects exactly one site), the wage rate applies to the employee at all sites they can work at. Wages are versioned over time via the `/employee/compensation/<id>` page, each entry attached to a site for bookkeeping with `effectiveDate`. For Milestone 1, `create_employee` creates one initial wage entry and uses the first site in `available_sites` as its `wage[siteId]`. The result's `wage_site` field reports which site was used. Managing additional wage entries is deferred to modify work.
- **Hourly only.** `wage[isHourly]=1` is hardcoded for Milestone 1. Salaried employees are out of scope; calling `create_employee` always creates an hourly wage.
- **Permissions are template-driven, not role-picked.** The permissions page is a 30+ permission matrix, but the server applies sensible defaults when a `templateId` is set. The wrapper passes only `templateId` + `employeeId` + `hasActionApprovalAuthority` and lets the server fill the matrix. Available POS templates on WashU: Manager, Cashier, General User, General Manager, Assistant Manager, Shift Leader, CSA. Note: **no "Administrator" on the POS side** — that role exists only on the Backoffice side. The `permission` kwarg is matched against POS templates for the employee flow and against BO templates for the Backoffice user flow independently; the POS/BO permission-name symmetry rule applies only when `requires_backoffice=True`.
- **`permission` is a required kwarg on `create_employee` and `create_backoffice_user`.** Callers must always name a role explicitly. Creating a user with no permission template at all leaves the account in an unusable state (Access = None) — confirmed during Phase 1 exploration when the employee record was visible in the list with no permissions set. Unknown names still fall back to "General User" with a warning (that rule is unchanged); the change is that *omitting* the kwarg now raises a pydantic ValidationError instead of defaulting silently.
- **Disable mechanism.** No dedicated disable endpoint. Disable is a `POST /employee/update` with `employee[isActive]=0`. The wrapper first tries a minimal two-field POST (id + isActive); if the tenant's Symfony configuration rejects that or wipes other fields (detected via a GET-after-POST sanity check during Phase 1.4 testing), fall back to a full-form read-modify-write.
- **`employee[adpEmployeeId]` is optional** and exposed via the `adp_employee_id` kwarg.
- **URL map (confirmed from exploration):**
  - `GET /login` → login page
  - `POST /login_check` → login submit
  - `GET /employee` → employee list
  - `GET /employee/create` → create form
  - `POST /employee/insert` → create submit (step 1)
  - `GET /employee/edit/<id>` → edit form (and the source for disable's full round-trip, if needed)
  - `POST /employee/update` → edit submit (used for disable)
  - `GET /employee/permissions/<id>` → permissions editor
  - `POST /employee/permissions/update` → permissions submit (step 2 of create)
  - `GET /employee/compensation/<id>` → wage editor (future modify work)
  - `GET /user` → BO user list
  - `GET /user/create` → BO user create form
  - `POST /user/insert` → BO user submit (step 1)
  - `GET /user/permissions/<id>` → BO user permissions editor (URL pattern to confirm in Phase 1.4)
  - `POST /user/permissions/update` → BO user permissions submit (URL to confirm in Phase 1.4)

## 8. Risks and Mitigations

**Sonny's changes Backoffice HTML structure.** The form builders read field names from HTML fixtures, so a Sonny's update could break the library silently or produce malformed payloads. **Mitigation:** integration tests against the live tenant catch it immediately. `scripts/explore.py` is committed so regenerating fixtures is a one-command job. `BackofficeServerError` includes the parse failure reason to make diagnosis fast.

**Session expiration semantics.** Exploration confirmed that login succeeds via `POST /login_check` with a 302 redirect to `/`, and Backoffice uses a PHPSESSID cookie. The exact expiration signal (302 → `/login` vs. 401 vs. HTML containing a login form) was not forced during Phase 1 and will be confirmed during integration testing. **Mitigation:** `_BackofficeSession` detects "HTML body contains `_username`/`_password` inputs" as a session-expired sentinel and re-authenticates transparently.

**The two-step create flow has no transaction.** If step 2 (permissions POST) fails after step 1 (basic info POST) succeeded, a half-created user exists on the tenant. **Mitigation:** The library attempts a cleanup POST (disable the half-created user) on step-2 failure, and the error message clearly states whether cleanup succeeded. Documented in the error handling guide.

**Permission-name mismatch between POS and BO.** When `requires_backoffice=True`, the permission name must exist in both lists. A tenant could easily misname roles. **Mitigation:** The permissions resolver runs for both scopes before any POST and raises a clear error ("permission 'X' found in POS but not in Backoffice") before creating any resources. Documented prominently.

**Rate limiting by Backoffice.** Bulk operations could trip rate limits. **Mitigation:** Out of scope for Milestone 1. The `max_retries` parameter handles transient 5xx but not 429. If rate limiting becomes a problem in practice, add retry-with-backoff in a later patch.
