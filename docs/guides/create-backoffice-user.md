# Creating a Backoffice User

A Backoffice user is an account that can log into the Backoffice web UI. Two modes:

- **Linked** — tied to an existing employee record, using the employee's email and site inheritance.
- **Standalone** — an independent account with its own name, email, and site assignments. Used for district managers, auditors, and the wrapper's own bot user.

## Linked mode

```python
with SonnysBackofficeClient(...) as client:
    result = client.create_backoffice_user(
        username="janedoe",
        email="jane.doe@example.com",
        permission="Manager",
        link_to_employee_pos_user_id="12345",
    )
    print(result.user_id, result.password)
```

Alternatively, look up by email:

```python
result = client.create_backoffice_user(
    username="janedoe",
    email="jane.doe@example.com",
    permission="Manager",
    link_to_employee_email="jane.doe@example.com",
)
```

The employee must be **active**. Linking to a disabled employee returns `BackofficeServerError` with the message "please make sure that the related employee is active and try again".

## Standalone mode

```python
result = client.create_backoffice_user(
    username="districtmgr",
    email="dm@example.com",
    first_name="District",
    last_name="Manager",
    permission="Administrator",
)
```

`first_name` and `last_name` are both required for standalone mode. They're stored on the user's profile (not on any employee record).

## Milestone 1 limitation — manual permission template assignment

!!! warning "Permission template assignment is deferred to Milestone 2"
    In Milestone 1, `create_backoffice_user` creates the account successfully but does **not** assign a permission template. You'll need to:

    1. Open `/user` in the Backoffice UI.
    2. Click the shield icon (`fa-shield`) next to the new user.
    3. Select a template from the dropdown.
    4. Click save.

    The returned `result.warnings` list contains a reminder message. `permission_applied` is populated with the name you requested (so you know which template to pick) but no HTTP call was made to actually apply it.

### Why

Phase 1 exploration confirmed that `POST /user/permissions/update` requires a valid site-inheritance payload. When the wrapper tries to parse the form state from `/user/permissions/<id>` and replay it, the server returns `"Accessible Sites requires no less than 1 valid selection."` — the bootstrap-toggle semantics for `disabledRegions[]` / `isAllSitesAllowedByDistrict[N]` don't cleanly round-trip. A Playwright-driven capture of the browser POST hits the same error. Until the site-inheritance semantics are fully understood, the wrapper refuses to silently send a broken payload that might wipe a user's access.

## What the library *does* send

`POST /user/insert` with these fields:

**Linked mode:**

```
employee[isOnSiteEmployee] = "1"
user[employeeId]           = "<employee_id>"
employee[email]            = "<linked employee's email>"
user[username]             = "<your username>"
user[password]             = "<password>"
user[confirmPassword]      = "<password>"
```

**Standalone mode:**

```
employee[isOnSiteEmployee] = "0"
employee[firstName]        = "<first_name>"
employee[lastName]         = "<last_name>"
employee[email]            = "<email>"
user[username]             = "<username>"
user[password]             = "<password>"
user[confirmPassword]      = "<password>"
```

On success the server redirects to `/user/permissions/<new_user_id>?userIsNew=1` — the wrapper extracts `user_id` from that location header.

## The returned `BackofficeUserCreated` object

```python
class BackofficeUserCreated:
    user_id: int
    username: str
    password: str                   # echo of provided or auto-generated
    email: str
    linked_employee_id: int | None  # None for standalone
    permission_applied: str         # the template you requested (not actually applied in M1)
    sites_granted: list[str]        # what you requested (not actually applied in M1 BO path)
    warnings: list[str]             # includes the M1 deferral note
```
