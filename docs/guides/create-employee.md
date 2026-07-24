# Creating an Employee

## Minimal call

```python
from datetime import datetime
from decimal import Decimal

from sonnys_backoffice import SonnysBackofficeClient

with SonnysBackofficeClient(
    subdomain="washu",
    username="automation-bot",
    password="...",
) as client:
    result = client.create_employee(
        first_name="Jane",
        last_name="Doe",
        phone="6155551234",
        email="jane.doe@example.com",
        pos_user_id=12345,
        wage_rate=Decimal("15.50"),
        start_date=datetime(2026, 5, 1),
        available_sites=["Wash 37135"],
        permission="General User",
    )
    print(result.pos_pin)
```

## Every parameter explained

| Parameter | Type | Required | Default | Notes |
|---|---|---|---|---|
| `first_name` | `str` | yes | — | Leading/trailing whitespace is stripped. Unicode and symbols preserved. |
| `last_name` | `str` | yes | — | Same rules. |
| `phone` | `str` | yes | — | 9 or 10 digits after all non-digit characters are stripped. |
| `email` | `str` | yes | — | Must contain a valid `@domain.tld`. |
| `pos_user_id` | `int` | yes | — | Must be unique per tenant. Pre-flight with `is_pos_user_id_available()`. |
| `pos_pin` | `int \| None` | no | auto-generated 5-digit int | Always returned in the result — capture it! |
| `wage_rate` | `Decimal \| float` | yes | — | Dollars per hour. Prefer `Decimal` to avoid floating-point drift. |
| `overtime_wage_rate` | `Decimal \| float \| None` | no | `wage_rate × 1.5` | |
| `start_date` | `datetime` | yes | — | The form expects `MM/DD/YYYY`; the library formats it. |
| `available_sites` | `list[str] \| "all"` | yes | — | Site *names* (not IDs). The wrapper auto-detects flat vs hierarchical tenants — see [Sites, regions & districts](sites-regions-districts.md). |
| `permission` | `str` | yes | — | POS template name, case-insensitive. Unknown names raise `NotFoundError` listing the valid templates (no silent fallback). |
| `departments` | `list[str] \| None` | no | `["Greeter"]` | "Greeter" is always auto-added — see below. |
| `adp_employee_id` | `str \| None` | no | `None` | ADP employee ID, if your tenant uses ADP payroll integration. |
| `emergency_contact_name` | `str \| None` | no | `None` | |
| `emergency_contact_phone` | `str \| None` | no | `None` | Same validation as `phone`. |
| `requires_backoffice` | `bool` | no | `False` | Creates a linked Backoffice user in the same call. See the BO section below. |
| `backoffice_username` | `str \| None` | no | `None` | Required when `requires_backoffice=True`. |
| `backoffice_password` | `str \| None` | no | auto-generated 12 chars | Always returned on BO-enabled creates. |

## Why "Greeter" is always present

On most Sonny's tenants, the Greeter department is tied to the tip/commission system: if an employee is NOT in Greeter, they won't appear on the pay reports for tipped commissions, even if they work a Greeter shift. The library auto-adds Greeter if you omit it, so you never end up with a "missing from tips" surprise on payday. If you genuinely want an employee without Greeter, pass `departments=["Cashier"]` and then edit them via the Backoffice UI — the library is deliberately opinionated here.

## Wage site attribution

Sonny's wage form requires attributing each employee's wage to a specific site, even though the rate is global. The library resolves this automatically: it picks the first site from `available_sites` (or the first site in the tree if you passed `"all"`) and uses that as the wage attribution site. The chosen site is returned in `result.wage_site`.

## Uniqueness pre-flight

POS User ID, email, and phone are all unique per tenant. Before hitting `create_employee`, the client builds an internal employee index from `/employee?limit=10000&active=all` and `/user/create`, and checks all three — the call fails fast with `DuplicateError` rather than hitting the server and getting a vague form error back.

If you want to avoid the exception path entirely, use the availability helpers first:

```python
if not client.is_pos_user_id_available(12345):
    pos_user_id = find_next_free_id(client, starting_at=12346)
```

### Checking a single POS User ID (`pos_user_id_exists`)

When you only need to validate one POS User ID — for example, before assigning it
during onboarding — use `pos_user_id_exists`. It is the positive counterpart to
`is_pos_user_id_available` and returns `True` if the ID is already taken by **any**
employee, **active or inactive** (POS User IDs stay reserved even after an employee
is disabled):

```python
if client.pos_user_id_exists(12345):
    raise ValueError("POS User ID 12345 is already in use — pick another")
```

Unlike the `is_*_available` helpers, this issues a fresh, targeted search on every
call (`/employee` filtered by `posUserId` with `active=all`) instead of building or
reusing the cached employee index — so the answer is always live, which is what you
want for a last-moment uniqueness guard. It checks the **POS User ID** you assign,
not the internal Backoffice employee id shown in `/employee/edit/<id>` URLs.

## Creating with a linked Backoffice user

Pass `requires_backoffice=True` along with `backoffice_username`:

```python
result = client.create_employee(
    ...,
    requires_backoffice=True,
    backoffice_username="janedoe",
)
print(result.backoffice_password)  # auto-generated 12-char password
```

!!! warning "Milestone 1 limitation"
    The linked Backoffice user is **created**, but its permission template is **not** assigned automatically. You'll need to open `/user` in Backoffice, click the shield icon next to the new user, pick a template, and save. The returned `result.warnings` list contains a reminder. This is a known limitation — see [Creating a Backoffice user](create-backoffice-user.md) for the full story and Milestone 2 roadmap.

The linked employee must be **active** at the moment of BO user creation. Since `create_employee` always creates the employee first and then the BO user, this is automatic for new hires. It only becomes a concern when re-linking a BO account to a previously-disabled employee — which Milestone 1 doesn't support.

## The returned `EmployeeCreated` object

```python
class EmployeeCreated:
    employee_id: int                  # the internal Backoffice ID
    pos_user_id: int                  # echoed from the request
    pos_pin: int                      # either the passed value or auto-generated
    first_name: str
    last_name: str
    email: str
    backoffice_user_id: int | None    # only set when requires_backoffice=True
    backoffice_username: str | None
    backoffice_password: str | None   # auto-generated if not supplied
    permission_applied: str           # the resolved template name
    sites_granted: list[str]          # site names, resolved from available_sites
    departments: list[str]            # with Greeter included
    wage_site: str                    # the wage attribution site name
    warnings: list[str]               # BO template deferral, etc.
```

Always log or persist `pos_pin` and `backoffice_password` — Backoffice does not show them again.
