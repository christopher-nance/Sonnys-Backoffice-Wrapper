# CLAUDE.md

Guidance for working in this repo.

## What this is

`sonnys-backoffice-wrapper` — programmatic user management for Sonny's Carwash Controls Backoffice (a Symfony/PHP app) over plain HTTP. No public API exists; the wrapper logs in, scrapes/parses HTML forms with BeautifulSoup, and POSTs form payloads. Pure `requests` + `pydantic` v2.

## Layout

- `src/sonnys_backoffice/`
  - `client.py` — public `SonnysBackofficeClient` façade (lazy caches; use as a context manager).
  - `employees.py` — `create_employee` / `disable_employee` / `modify_employee` orchestration and form/payload builders, plus the read-surface parsers (`parse_employee_summaries`, `parse_employee_profile`, `parse_wage_history`, `parse_employee_permission`).
  - `bo_users.py` — back-office user creation (standalone + linked). BO permission templates are **not** auto-applied (M2).
  - `sites.py`, `departments.py`, `permissions.py` — HTML parsers for the `/employee/create` form tree.
  - `session.py` — login (`/login_check`, `_username`/`_password`, `PHPSESSID`) + transparent re-auth. `models.py` — pydantic models. `exceptions.py`.
- `tests/unit/` — fast, mocked. `tests/integration/` — live-tenant, opt-in. `docs/` — MkDocs Material (deployed by `.github/workflows/docs.yml`).

## Dev commands

```bash
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[dev,docs]"
./.venv/Scripts/python.exe -m pytest -q          # unit tests (integration deselected by default)
./.venv/Scripts/python.exe -m ruff check src tests && ./.venv/Scripts/python.exe -m ruff format src tests
./.venv/Scripts/python.exe -m mkdocs build       # build docs site
./.venv/Scripts/python.exe -m build              # build wheel/sdist (needs the `build` package)
```

Integration tests need `SONNYS_SUBDOMAIN` / `SONNYS_BOT_USERNAME` / `SONNYS_BOT_PASSWORD` (root `.env`, gitignored) and run only with `-m integration`; write-mutating ones also need `SONNYS_ALLOW_WRITES=1`.

## Key gotchas (learned the hard way)

- **Symfony binds checkbox *presence* as true**, regardless of value. To set a checkbox false you must **omit the field entirely** — sending `name=0` still reads as true. This affects `employee[isActive]` (disable omits it), `employee[isAllRegionsAllowed]` (site restriction omits it), and `wage[isOvertimeEligible]`.
- **Hierarchical site restriction** is an *allowlist*, encoded exactly as the Backoffice form submits it: omit the all-regions flag **and every region/district "all allowed" rollup** (`isAllRegionsAllowed`, `isAllDistrictsAllowedByRegion`, `isAllSitesAllowedByDistrict`), emit the hidden `employee[sites][N][siteId]` for **every** site, and emit `employee[sites][N][isAvailable]` only for the sites to **grant**. Omitting a district's rollup binds it false; leaving it (or sending it) keeps that whole district allowed and silently leaks every site in it — the bug behind "employee got sites they shouldn't have." (The old "submit only the complement's siteId" encoding did exactly this leak.) Flat tenants use the `employee[siteIds][]` blocklist (unverified — no flat tenant available).
- **Wage changes create a new record** that must be effective strictly **after** the most recent rate's effective date. `modify_employee` defaults to `max(today, most_recent + 1 day)`. Overtime eligibility must be read from the current wage-history row (the "add wage" form is always blank).
- **Date fields render with `data-value`, not `value`** (pickadate populates `value` via JS). The form parser reads `data-value` as a fallback.
- **The roster page has no email column**, and Sonny's accounts often use a personal (not work) email — so email lookups are unreliable. The dependable key is first + last name with phone as a tiebreaker (`find_employee`). Phone matching compares digits-only on the last 10 (ignores a leading country code).

## Live testing safety

Only a **production** tenant (WashU) is available — no staging. When live-testing writes:

- Use first name `WrapperExplore` for throwaway employees; `scripts/cleanup_exploration_artifacts.py` finds and disables leftovers (dry-run by default, `--execute` to act).
- Use a reserved POS ID range (90000–99999), `@example.invalid` emails, dedicated test phones; pre-flight with the `is_*_available` helpers.
- Before disabling, re-resolve the POS ID to the expected employee and assert its first name is `WrapperExplore`.
- Never print the bot password to stdout. For Playwright UI checks, drive a Python `playwright` script that reads `.env` in-process.

## Conventions

- Commit only when asked. Match existing code style; run ruff before finishing. Keep `__version__` (in `__init__.py`) and `pyproject.toml` version in sync, and add a `docs/changelog.md` entry for user-facing changes.
