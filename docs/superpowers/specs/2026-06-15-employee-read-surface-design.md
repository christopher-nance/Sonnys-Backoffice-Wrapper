# Employee read surface — design

**Date:** 2026-06-15
**Status:** Approved

> **Superseded behavior note (v0.7.2, 2026-08-04):** this historical design described checked
> hierarchical per-site `isAvailable` controls as granted. The live edit form labels checked as
> **No**: unchecked/enabled `siteId` means granted, while checked `isAvailable` means denied.

## Goal

Make the wrapper a full read/write interface to Sonny's Back Office, not just write.
A consumer (e.g. a web app for employee status changes) must be able to:

- discover the permission templates available on the tenant (already exists: `list_permissions(scope=…)`),
- list/browse employees,
- read a single employee's current state (identity, contact, departments, sites, active status, pay rate + history, and current permission level),

so it can populate UI, pre-select dropdowns, and then write changes back with the existing
`create_employee` / `modify_employee` / `disable_employee`.

## Scope

Approach **A** (rich `get_employee` + lightweight `list_employees`) **plus** Approach **B**'s
granular per-section getters so a screen can fetch only what it needs and avoid the 3-request cost.

### New client methods

| Method | Requests | Returns |
|---|---|---|
| `list_employees(active="active"\|"inactive"\|"all")` | 1 (roster page) | `list[EmployeeSummary]` |
| `get_employee_profile(pos_user_id=… \| email=…)` | resolve + 1 (edit page) | `EmployeeProfile` |
| `get_employee_compensation(pos_user_id=… \| email=…)` | resolve + 1 (compensation page) | `EmployeeCompensation` |
| `get_employee_permission(pos_user_id=… \| email=…)` | resolve + 1 (permissions page) | `EmployeePermission` |
| `get_employee(pos_user_id=… \| email=…)` | resolve + 3 | `Employee` (composes the three above) |

`list_permissions(scope=…)` already exists and is the dropdown source — no change.

### New models

```python
class EmployeeSummary:          # roster row (cheap)
    employee_id: int
    pos_user_id: int | None
    first_name: str
    last_name: str
    phone: str | None
    is_active: bool

class WageRecord:
    wage_type: str              # "Hourly" / "Salary"
    rate: Decimal
    overtime_eligible: bool
    overtime_rate: Decimal | None
    effective_date: date
    end_date: date | None       # None ⇒ current
    is_current: bool

class EmployeeCompensation:
    current: WageRecord | None
    history: list[WageRecord]   # newest first

class EmployeePermission:
    template_name: str | None           # exact match against list_permissions, else None
    is_custom: bool                     # True when grants match no template exactly
    granted_permission_ids: frozenset[int]
    override_permission_ids: frozenset[int]

class EmployeeProfile:          # identity / contact / assignment (edit page)
    employee_id: int
    pos_user_id: int | None
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    departments: list[str]
    available_sites: list[str] | Literal["all"]   # resolved names, or "all"
    start_date: date | None
    adp_employee_id: str | None
    emergency_contact_name: str | None
    emergency_contact_phone: str | None
    is_active: bool

class Employee(EmployeeProfile):    # full snapshot = profile + comp + permission
    current_wage: WageRecord | None
    wage_history: list[WageRecord]
    permission: EmployeePermission
```

## Behavior & boundaries

- **Reads are always live** — employee state is never cached (status changes need current truth).
  Discovery (`list_sites`/`list_departments`/`list_permissions`) keeps its lazy cache; `get_employee_*`
  ensure those caches exist (site-tree, departments, pos-permissions) but re-fetch the employee pages every call.
- **Lookup** by `pos_user_id` or `email` (exactly one), consistent with `modify`/`disable`.
  Email resolves through the existing employee index. Unknown → `NotFoundError`.
- **`permission.template_name`** is computed by exact-matching the employee's granted permission IDs
  against `list_permissions(scope="pos")`. No exact match ⇒ `template_name=None, is_custom=True`.
  (Sonny's does not store a clean "current template" — the template dropdown resets to blank after apply,
  so the grant matrix is the source of truth. Best-effort naming is the honest representation.)
- **Sites:** if `employee[isAllRegionsAllowed]`/`isAllSitesAllowed` is checked ⇒ `"all"`; otherwise the
  site names whose per-site `isAvailable` checkbox is checked, resolved via the cached `SiteTree`.

## Parsing (reuse, no new scraping primitives)

All four parsers live in `employees.py` and reuse this session's work:

- `parse_employee_summaries(html)` — roster rows (model on `cleanup_exploration_artifacts.find_exploration_employees`).
- `parse_employee_profile(edit_html, *, site_tree, departments)` — edit-form field reads
  (`value`/`data-value` fallback already handled), department multi-select → names, site availability.
- `parse_wage_history(comp_html)` — generalize `_latest_wage_effective_date` / `_current_wage_overtime_eligible`
  to parse every history row into `WageRecord`s; the no-end-date row is `current`.
- `parse_employee_permission(perm_html, *, pos_permissions)` — checked `permissions[N][hasGrantAccess]` →
  granted IDs, `permissions[N][requiresOverride]` → override IDs, then template match.

## Testing

- Unit tests against fixture HTML in `tests/fixtures/html/*` (capture a couple fresh fixtures if needed).
- A **read-only** live integration smoke test — these methods never write, so they run safely against the
  tenant without `SONNYS_ALLOW_WRITES`.

## Docs

- New guide `docs/guides/read-employees.md`; add methods to `index.md` feature list, API reference, changelog (v0.4.0).
