# Exploration Notes

Captured against `washu.sonnyscontrols.com` using `SonnysWrapperTestAccount` on 2026-04-13.

All captures in this document are **read-only** — no state was mutated on the tenant. Writes captured here come from recorded-but-blocked POST interception, not from actual submissions.

## Stack

Backoffice is a **Symfony + PHP** application. Evidence:

- Login form field names are `_username` / `_password` (Symfony Security Component convention)
- Login POST target is `/login_check` (Symfony default)
- Session cookie is `PHPSESSID`
- Form field naming uses `entity[field]` bracket syntax (Symfony Forms)

## Authentication

- **Login page:** `GET /login`
- **Login submit:** `POST /login_check`
- **Form field names:**
  - `_username` (type=text, id=login-username)
  - `_password` (type=password, id=login-password)
- **CSRF token:** **none**. The login form has no CSRF input and no `csrf-token` meta tag. Backoffice does not protect login with CSRF.
- **Session cookie:** `PHPSESSID`
- **Success redirect:** `POST /login_check` → 302 → `/` (home dashboard)
- **Failure mode:** not yet observed — need to test with bad credentials to see what happens. Hypothesis: re-renders `/login` with an error. Session implementation should treat "landed back on `/login`" as the failure signal.
- **Session expiration signal:** not yet observed. Hypothesis: authenticated GET to any resource returns 302 → `/login` when the session expires. Confirm during implementation by letting a session go idle.

## Employee Create Form

- **URL:** `GET /employee/create`
- **Form ID:** `employee-create-edit-form`
- **Submit action:** `POST /employee/insert`
- **CSRF token:** none
- **Total distinct named fields:** 77

### Required fields (HTML `required` attribute)

- `employee[firstName]`
- `employee[lastName]`
- `employee[departments][]`
- `posCredential[POSLoginID]` (type=number)
- `posCredential[POSLoginPassword]` (type=number — this is the POS PIN)
- `wage[regularRate]` (type=number)
- `wage[overtimeRate]` (type=number)
- `wage[siteId]` (select)

**Note:** `employee[phone]` and `employee[email]` are NOT marked `required` in the HTML, even though the user brief lists them as required fields. The wrapper treats them as required per the brief.

### Key field groups

**Personal info:**
- `employee[firstName]` text
- `employee[lastName]` text
- `employee[phone]` tel
- `employee[email]` text
- `employee[emergencyContactName]` text (optional)
- `employee[emergencyContactPhone]` tel (optional)

**POS credentials (separate `posCredential[...]` prefix, NOT `employee[...]`):**
- `posCredential[POSLoginID]` type=**number**
- `posCredential[POSLoginPassword]` type=**number**

Both are numeric in the HTML form — the wrapper should accept and emit them as integers / digit strings.

**Departments (multi-select):**
- `employee[departments][]` with these option values on WashU:
  - `1` → Cashier
  - `2` → Line
  - `3` → **Greeter**
  - `4` → Management

**Start date:**
- `employee[startDate]` is `type=hidden` and is pre-populated by JavaScript to today's date (e.g. `04/13/2026`). The server accepts `MM/DD/YYYY` format.

**Wage (new subsystem — significant design gap from the plan):**
- `wage[isHourly]` select — `1` = Hourly, `0` = Salary
- `wage[regularRate]` number (required) — hourly wage in dollars
- `wage[isOvertimeEligible]` checkbox
- `wage[overtimeRate]` number (required)
- `wage[salaryRate]` number (only if `isHourly=0`)
- `wage[hoursPerWeek]` number (only if salary)
- `wage[ignoreSalarySchedule]` radio
- `wage[siteId]` **select, required** — wages are *scoped to one site*. Options use SHORT names, not the long names seen elsewhere:
  - `1`=FIESTA, `2`=CENT, `4`=NILES, `5`=VILLAP, `6`=DESPLN, `7`=NAPER, `8`=CAROL, `9`=WHEAT, `10`=JOLIET, `11`=PLNFLD, `12`=BERWYN, `13`=BURBT1, `14`=EVRGRN, `15`=EVERG2, `16`=BurbT2, `17`=NOLO, `18`=DKSN, `19`=FRVW, `20`=JKSN
  - (IDs match the `employee[sites][N]` IDs, just with alternate labels)
- `wage[scheduleDay][0..6][startTime]` / `[endTime]` — 14 fields for a weekly schedule, likely optional.

**ADP integration (optional):**
- `employee[adpEmployeeId]` text — likely blank unless explicitly set.

**Site availability (hierarchical tenant markup — confirmed matches spec):**
- `employee[isAllRegionsAllowed]` checkbox
- `employee[disabledRegions][]` checkbox array
- `employee[isAllDistrictsAllowedByRegion][]` checkbox array (one per enabled region)
- `employee[disabledDistricts][]` checkbox array
- `employee[isAllSitesAllowedByDistrict][<district_id>]` — one per district
- `employee[sites][<site_id>][isAvailable]` — checkbox, one per site
- `employee[sites][<site_id>][siteId]` — hidden paired input

This matches the spec HTML from the brief. The site-tree parser in `sites.py` will parse this correctly.

### Fields NOT on the employee create form

- **No `requires_backoffice` toggle.** Creating a linked BO user is a separate call to `/user/create` AFTER the employee exists. The plan's `requires_backoffice=True` flow is correct conceptually but internally becomes two top-level form submissions, not one.
- **No permission / role selector.** Permissions are step 2 (see below).

## Employee Permissions (step 2 of creation, also used for editing)

- **URL:** `GET /employee/permissions/<employee_id>`
- **Form ID:** `employee-permission-update-form`
- **Submit action:** `POST /employee/permissions/update`

### Form structure

This is NOT a simple role-picker. It's a **permission matrix**:

- `templateId` select — the "role" dropdown. Selecting a template pre-fills all the `permissions[N]` checkboxes to that template's defaults. This is what the wrapper should drive when the caller passes `permission="General User"`.
- `employeeId` hidden
- `hasActionApprovalAuthority` hidden
- `permissions[<perm_id>][id]` hidden
- `permissions[<perm_id>][label]` hidden
- `permissions[<perm_id>][description]` hidden
- `permissions[<perm_id>][hasGrantAccess]` checkbox — individual permission toggle
- `permissions[<perm_id>][requiresOverride]` checkbox — secondary toggle

There are 30+ individual permissions (IDs 1-34, not all contiguous).

### Available POS role templates (templateId options on WashU)

| ID | Name |
|---|---|
| 1 | Manager |
| 2 | Cashier |
| 3 | **General User** (library default fallback) |
| 4 | General Manager |
| 5 | Assistant Manager |
| 6 | Shift Leader |
| 8 | CSA |

**Note:** No "Administrator" role on the POS side. Administrator is a Backoffice-only concept. Value `7` is missing from the sequence — probably an internal/hidden template.

### How the wrapper should drive this

**Minimal approach (recommended for Milestone 1):** submit `templateId=<id>` along with `employeeId` and `hasActionApprovalAuthority`, and **let the server apply the template defaults**. Do NOT try to recreate the full `permissions[N][hasGrantAccess]` matrix — the server will fill it from the template.

**Risk:** if the server requires the full permissions[] array, the minimal approach will fail. We'll find out when we submit a real POST during Task 1.4. If it fails, fall back to: load the page for the newly-created employee, extract all the `permissions[N]` checkbox values the template applied client-side, echo them back.

## Employee Edit Page

- **URL:** `GET /employee/edit/<employee_id>`
- **Submit action:** `POST /employee/update`

### Disable / deactivate mechanism

Confirmed with the user during exploration:

> "Disabling a user is done by setting their status from active to inactive on the edit page for a user."

- **Field:** `employee[isActive]` checkbox, section heading "Employee Work Status"
- **Submit:** `POST /employee/update`
- **Mechanism:** the edit form is a full round-trip — you GET the edit page, parse every current field value, flip `isActive` to off, then POST `/employee/update` with all fields preserved. You cannot send a partial update because Symfony forms will reject unknown field shapes.

**Implication for `disable_employee()`:** the function needs to load the edit page, parse all the current values, preserve everything except `isActive`, and POST back. This is heavier than a dedicated `/disable` endpoint would have been.

**Alternative to investigate:** some Symfony apps accept form submissions that only include the changed fields if the form is configured with `'empty_data' => $existingEntity`. Worth testing during Task 1.4. If it works, `disable_employee` can be a minimal two-field POST. If it doesn't, we do the full round-trip.

## Employee List Page

- **URL:** `GET /employee`
- **Table class:** `table table-full-width table-striped table-hover table-employees-list`
- **Row structure:** no `data-employee-id` on `<tr>`. Employee ID is discoverable via action links in the last column:
  - `/employee/compensation/<id>`
  - `/employee/permissions/<id>`
  - `/timesheet/<id>`
  - `/employee/edit/<id>`
- **Columns (by position):** first name, last name, site (short code), shift/role, POS Login ID, department, phone, wage mode, active-status text, compensation link
- **Pagination:** not yet investigated. Default page size appears to be ~25 rows.

**Lookup strategy for `find_employee_in_list_html`:** extract the integer from the `/employee/edit/<id>` href in each row, and match the POS Login ID or email cell against the requested lookup key. Note: email is not shown in the table — the wrapper may need to visit the edit page of each candidate to match by email, OR use a server-side search param. **Check for a search query param** on `/employee?search=...` during Task 1.4.

## User Create Form (`/user/create`)

- **Form ID:** `user-create-edit-form`
- **Submit action:** `POST /user/insert`
- **9 named fields:**

| Field | Type | Required | Notes |
|---|---|---|---|
| `employee[isOnSiteEmployee]` | checkbox | | Yes = linked to employee, No = standalone |
| `user[employeeId]` | select | yes (linked mode) | Dropdown of existing employees |
| `employee[firstName]` | text | standalone only | |
| `employee[lastName]` | text | standalone only | |
| `employee[email]` | text | yes | |
| `user[username]` | text | yes | Pattern `[A-Za-z][\w]{2,63}` (HTML validation) |
| `user[linkExistingAccount]` | checkbox | | For linking to an existing SSO account |
| `user[password]` | password | yes | |
| `user[confirmPassword]` | password | yes | |

**Step 1 submission:** the button label is "Set Permissions" — on success, the server redirects to the BO user permissions page (URL pattern TBD — likely `/user/permissions/<id>` by analogy with the employee side).

## BO Permissions (TBD)

Not yet captured. Will be captured by visiting `/user/permissions/<id>` for an existing BO user (or after creating one during Task 1.4). Hypothesis: same form structure as `/employee/permissions/<id>` but with a different set of templates and permissions.

## Gotchas

- **Two different site naming schemes on the same form:** availability uses long names ("WashU Fiesta"), wage uses short codes ("FIESTA"). Same underlying site IDs. The wrapper should resolve by ID and surface long names in the public API.
- **`employee[startDate]` is a hidden field** populated by JavaScript — if you don't set it in the POST, the server will reject with a required-field error. Format: `MM/DD/YYYY`.
- **POS credentials are numeric fields** — the wrapper should accept `pos_user_id: int` (or a digit-only string) and likewise for `pos_pin`.
- **No CSRF tokens anywhere** — do not waste code scraping for them.
- **Schedule fields (`wage[scheduleDay][N][startTime/endTime]`) are tolerated as empty strings** — the wrapper can omit them or send empty values.

## Open questions (for Task 1.4 and beyond)

1. Does `POST /employee/permissions/update` accept just `templateId` + `employeeId`, or does it require the full `permissions[]` matrix?
2. Does `POST /employee/update` accept a minimal `{employee[id], employee[isActive]=0}` payload, or does it require the full form round-trip?
3. What's the response shape for a successful `/employee/insert`? Is the new `employee_id` in the redirect Location, in the response body, or must we re-fetch the employee list?
4. What's the exact URL pattern for BO user permissions — `/user/permissions/<id>` or something else?
5. Does `/employee?search=<query>` support server-side filtering for lookups, or do we always page through the full list?
6. What does Backoffice return on a duplicate email / POS ID submission — a 200 with an error banner, a 302 back to `/employee/create`, something else?
7. What's the session expiration signal — a 302 to `/login`, a 401, or a full login-page HTML response?
