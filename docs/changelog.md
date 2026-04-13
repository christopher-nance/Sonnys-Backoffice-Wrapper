# Changelog

## v0.1.0 — 2026-04-XX (Milestone 1)

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

### Known limitations in Milestone 1

- **Backoffice user permission template assignment is not automated.** `create_backoffice_user` (and the linked path of `create_employee`) creates the account but does not POST to `/user/permissions/update`. The caller must click the shield icon in the Backoffice UI to apply a template. Deferred to Milestone 2 — the site-inheritance semantics on the BO permissions form do not cleanly round-trip through the wrapper's form parser yet. See [Creating a Backoffice user](guides/create-backoffice-user.md).
- **`modify_employee` is not included.** Different fields live behind different Backoffice URLs and deserve targeted functions. Deferred to Milestone 2+.
- **Email lookup in `disable_employee` only works when the email appears in the visible employee-list columns**, which is rare. Use `pos_user_id` lookup instead. A hidden-dropdown resolver is on the Milestone 2 roadmap.
- **`list_employees` is not exposed.** The internal `EmployeeIndex` has most of what's needed, but the public API is minimal for M1.
- **No parallelism.** The `_BackofficeSession` wraps a single `requests.Session`. Do not share a client across threads.

### Infrastructure

- 136+ unit tests covering every public function, including fixture-driven parsers exercised against real captured Backoffice HTML.
- CI-ready GitHub Actions workflow for docs deploy to GitHub Pages.
- Strict MkDocs build with a Google-style docstring convention.
