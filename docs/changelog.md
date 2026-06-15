# Changelog

## v0.5.0 — 2026-06-15

### Features — name-based lookup

- **`find_employee(first_name=…, last_name=…, phone=None, active="active")`** — resolve a single
  employee by first + last name (normalized: trim + casefold), using `phone` as a tiebreaker when
  names collide (compared digits-only on the last 10, so a leading country code or formatting
  doesn't matter). Returns an `EmployeeSummary`. This is the reliable lookup when you don't have a
  POS User ID: the roster page has no email column and Sonny's accounts often use a personal email,
  so email lookups frequently miss.
- **`find_employees(first_name=…, last_name=…, active="active")`** — all roster rows matching a
  name (no phone narrowing), for inspecting candidates.
- **`AmbiguousMatchError`** (new, exported) — raised by `find_employee` when a name matches multiple
  and phone doesn't narrow it to one; the message lists the candidate POS User IDs so callers can
  fall back to manual confirmation. `NotFoundError` is still raised for zero matches, keeping
  "couldn't confidently pick one" distinct from "none found".

Both reuse the existing single roster GET (`list_employees` / `parse_employee_summaries`); the
matching logic is a pure, unit-tested helper in `employees.py`. Additive — the existing
`disable_employee` / `get_employee` POS-id and email lookups are unchanged.

## v0.4.0 — 2026-06-15

### Features — employee read surface

The wrapper is now a full read/write interface, not just write. All reads are live (uncached).

- **`list_employees(active="active"|"inactive"|"all")`** — lightweight roster rows (`EmployeeSummary`) in one request.
- **`get_employee(pos_user_id=… | email=…)`** — full current-state snapshot (`Employee`): identity, contact, departments, sites, active state, current wage + full wage history, and current permission level.
- **Granular getters** — `get_employee_profile` (`EmployeeProfile`), `get_employee_compensation` (`EmployeeCompensation` with `current` + `history`), `get_employee_permission` (`EmployeePermission`) — fetch only the slice a screen needs.
- New read models: `EmployeeSummary`, `Employee`, `EmployeeProfile`, `EmployeeCompensation`, `WageRecord`, `EmployeePermission`.
- `EmployeePermission.template_name` is a best-effort exact match of the employee's granted permission IDs against the tenant's templates (Sonny's doesn't store a clean "current template"); `is_custom` + the raw grant/override ID sets are exposed for customized employees.

## v0.3.0 — 2026-06-15

### Features

- **`modify_employee(activate=...)`** — reactivate a disabled employee (`activate=True`) or deactivate one (`activate=False`) via the `employee[isActive]` presence semantics. Composes with any other change, so you can reactivate and (re)assign sites/pay/permission in a single call.
- **`modify_employee(wage_effective_date=...)`** and **`EmployeeModified.wage_effective_date`** — control and report the effective date of a pay change (see bug fixes below for the rule).

### Bug fixes

- **Hierarchical site restriction now works.** `create_employee` and `modify_employee` previously sent `employee[isAllRegionsAllowed]=0` plus per-site `isAvailable` flags when restricting to specific sites on a hierarchical tenant. Because the Backoffice form binds checkbox *presence* as true, this silently granted **all** regions/sites. Both paths now omit the flag and submit the *complement* of the granted sites by `siteId` only — verified live to grant exactly the requested sites.
- **Pay-rate changes effective the same day now apply.** A new wage record must be effective strictly after the most recent rate's effective date; the previous code defaulted to today, so changing pay the same day an employee was created (or last raised) silently kept the old rate. The effective date now defaults to `max(today, most_recent + 1 day)`.
- **Overtime eligibility is preserved on pay changes.** `modify_employee` read overtime-eligibility from the always-blank "add wage" form, which dropped eligibility on every raise. It now reads the employee's current wage record and preserves eligibility (recomputing overtime at 1.5× when not explicitly provided).

## v0.2.0 — 2026-05-08 (Phase 1 Complete)

### Features

- **`modify_employee`** — modify an existing employee's properties, compensation, or permission template via three independent form submissions:
    - **Properties** (name, phone, email, departments, sites, emergency contact, ADP ID) via full-form round-trip on `/employee/update`.
    - **Compensation** (hourly wage, overtime rate) via `/employee/compensation/update` — creates a new wage record effective today.
    - **Permission template** via `/employee/permissions/update` with the full grant/override matrix.
- **`available_sites` modification** — switch employees between `"all"` and specific-site access. Correctly handles both hierarchical tenants (region/district/site tree) and flat tenants (siteIds blocklist semantics).
- **`ModifyEmployeeRequest`** and **`EmployeeModified`** Pydantic models with full validation.

### Breaking changes

- **`resolve_permission` now raises `NotFoundError`** with the list of available template names when the requested name doesn't match any tenant template. Previously it silently fell back to "General User".

### Bug fixes

- **`data-value` fallback in form parser** — pickadate date pickers render server-side with `data-value` instead of `value` (JavaScript populates the value at runtime). The form parser now reads `data-value` as a fallback, fixing round-trip failures on the `employee[startDate]` field that caused disable and modify to silently fail.
- **Flat-tenant site payload** — `employee[siteIds][]` checkboxes represent *disabled* sites (presence = excluded), not enabled sites. Both `create_employee` and `modify_employee` now send the correct inverted list.
- **Cache invalidation after `create_employee`** — the employee list and index caches are now cleared after creation, so subsequent `modify_employee`/`disable_employee` calls find newly created employees.

## v0.1.0 — 2026-04-13 (Milestone 1)

Initial release.

### Features

- `create_employee` — two-step POST flow (`/employee/insert` + `/employee/permissions/update`), with uniqueness pre-flight across POS User ID / email / phone, full permission matrix submission, wage-site attribution, hierarchical site detection, and optional linked Backoffice user creation.
- `disable_employee` — full-form round-trip via `/employee/update` with `isActive` omitted, followed by a re-GET verification.
- `create_backoffice_user` — standalone and linked modes via `/user/insert`.
- `list_sites`, `list_departments`, `list_permissions` — cached discovery helpers.
- `is_pos_user_id_available`, `is_email_available`, `is_phone_available` — pre-flight uniqueness checks backed by a lazy per-tenant employee index.
- Pydantic v2 request models with field-level validation (phone normalization, email shape, 5-digit POS PIN range, etc.).
- Typed `EmployeeCreated` / `BackofficeUserCreated` / `EmployeeDisabled` result models.
- Auto-detection of flat vs hierarchical tenants from `/employee/create`.
- Case-insensitive permission name resolution with a "General User" fallback and `UserWarning` on mismatches.
- Transparent session re-authentication on cookie expiration.
- MkDocs Material documentation site with mkdocstrings API reference.

### Known limitations

- **Backoffice user permission template assignment is not automated.** `create_backoffice_user` (and the linked path of `create_employee`) creates the account but does not POST to `/user/permissions/update`. Deferred to Phase 2.
- **Email lookup in `disable_employee` only works when the email appears in the visible employee-list columns.** Use `pos_user_id` lookup instead.
- **`list_employees` is not exposed.** The internal `EmployeeIndex` has most of what's needed, but the public API is minimal.
- **No parallelism.** The `_BackofficeSession` wraps a single `requests.Session`. Do not share a client across threads.
