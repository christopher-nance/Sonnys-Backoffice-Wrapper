# Changelog

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
