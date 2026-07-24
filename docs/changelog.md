# Changelog

## v0.7.0 — 2026-07-24

### Features

- **`SonnysBackofficeClient.search_employees(first_name=…, last_name=…, pos_user_id=…, active=…)`**
  — server-side filtered roster search. The Backoffice applies the filters (`first_name` /
  `last_name` case-insensitive prefix, `pos_user_id` exact, AND-combined), so only the matching
  rows are fetched instead of the whole roster. Returns `EmployeeSummary` rows.
- `list_employees(...)` gained optional `first_name` / `last_name` server-side filters.

### Performance

- **Employee lookups no longer download the entire roster.** `find_employee` / `find_employees`
  now filter by name server-side (then apply the same exact match + phone tiebreaker), and every
  resolve-by-POS-User-ID path — `disable_employee`, `modify_employee`, and the `get_employee*`
  readers — resolves via a targeted `posUserId` query. On a ~500-employee tenant this is roughly a
  15× smaller response (~2.5 MB → ~165 KB) per lookup, and the result is always live.
- Discovered that the roster page **does** support server-side filtering via the Symfony form
  fields `first_name` / `last_name` / `posUserId` (the earlier "no server-side search" finding had
  probed the wrong param names). `pos_user_id_exists` now shares this search path.

## v0.6.0 — 2026-07-24

### Features

- **`SonnysBackofficeClient.pos_user_id_exists(pos_user_id)`** — returns `True` if a POS
  User ID is already in use by any employee, **active or inactive** (POS User IDs stay
  reserved even after an employee is disabled). Use it to pre-flight a POS User ID before
  assigning it, so onboarding doesn't fail on a duplicate.
  - The positive counterpart to `is_pos_user_id_available`; unlike the `is_*_available`
    helpers it issues a fresh, targeted search on every call (`/employee` filtered by
    `posUserId` with `active=all`) instead of building/reusing the cached employee index —
    so the result is always live.
  - Matches on an exact POS-User-ID comparison of the returned rows, so it stays correct
    even on a tenant that ignores the filter and returns the full roster.
  - Checks the POS User ID you assign, not the internal Backoffice employee id shown in
    `/employee/edit/<id>` URLs.

## v0.5.3 — 2026-07-21

### Fixed — hierarchical site restriction (`disabledRegions` meaning was inverted)

- **Supersedes the v0.5.2 fix**, which still mis-restricted new hires: it emitted
  `employee[disabledRegions][]=<regionId>` for every region the employee should **not** be in,
  believing that flag *excluded* a region. It does the opposite — `disabledRegions[]=R` marks a
  region as **fully granted**. So a single-store hire was granted every store in every *other*
  region (the "employee's active sites are all the sites except the one they need" bug).
- Verified live on the WashU tenant by creating an employee restricted to one store and reading the
  server-stored access back: before the fix the account held 7 stores across the wrong regions;
  after the fix it holds exactly the one selected store. The corrected encoding was also byte-matched
  against 59 real restricted employees' edit forms.
- Correct encoding now used by `create_employee` / `modify_employee`:
  - a region (or district) whose sites are **all** granted → its `disabledRegions[]` /
    `disabledDistricts[]` "fully-allowed" flag plus each of its sites as `[isAvailable]`;
  - any **partially** granted region/district → walked to per-site, listing every site once
    (granted → `[isAvailable]`, denied → `[siteId]`), including denied sites in fully-denied regions
    (previously omitted, which is what leaked them);
  - `isAll*` rollups omitted (`available_sites="all"` still uses `isAllRegionsAllowed`).
- Flat-tenant encoding (`employee[siteIds][]` blocklist) is unchanged and still unverified.

## v0.5.2 — 2026-06-18

### Fixed — hierarchical site restriction (correct encoding, verified against the live form)

- **Supersedes the incomplete v0.5.1 fix**, which granted **all** sites: it emitted
  `employee[sites][N][siteId]` for every site *and* `employee[sites][N][isAvailable]` for granted
  ones, so granted sites carried both fields and the server read the payload as "grant everything."
- `create_employee` / `modify_employee` now reproduce the Backoffice form's own `FormData`
  submission, captured byte-for-byte from the live tenant:
  - a region with **no** granted site is excluded wholesale via
    `employee[disabledRegions][]=<regionId>` (its sites drop out of the form);
  - each site in a region that keeps a grant is listed **once** — granted →
    `employee[sites][N][isAvailable]`, denied → `employee[sites][N][siteId]`;
  - all "all allowed" rollups are omitted.
  The generated payload is verified equal to a real browser `FormData` capture for the same
  selection. No public API change.

## v0.5.1 — 2026-06-18

### Fixed — hierarchical site restriction leaked entire districts

- **`create_employee` / `modify_employee` now restrict sites correctly on hierarchical
  (region → district → site) tenants.** The previous encoding submitted only the *complement's*
  `employee[sites][N][siteId]`, which left every untouched district's "all allowed" rollup flag
  (`isAllSitesAllowedByDistrict[N]`) at its default **true** — silently granting the employee every
  site in any district that wasn't the target's. An employee meant for one site (e.g. Niles) also
  received all sites in the other district (the Global/Tennessee region).
- The builder now mirrors exactly what the Backoffice form submits, verified against real
  UI-configured employees: emit the hidden `employee[sites][N][siteId]` for **every** site,
  `employee[sites][N][isAvailable]` only for the **granted** sites, and omit all region/district
  rollup flags so Symfony binds them false. No public API change.
- Flat-tenant encoding (`employee[siteIds][]` blocklist) is unchanged (no flat tenant available to
  re-verify).

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
