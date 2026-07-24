# Quickstart

This walks through creating one employee and then disabling them.

## 1. Set up a bot user in Backoffice

Before running the library, create a dedicated user in Backoffice with Administrator permissions and access to all sites. Do **not** use a human's login — bot accounts are more stable and create a clean audit trail. See [Authentication & bot setup](auth.md).

## 2. Store credentials outside your code

```python
import os

subdomain = os.environ["SONNYS_SUBDOMAIN"]     # e.g. "washu"
username = os.environ["SONNYS_BOT_USERNAME"]
password = os.environ["SONNYS_BOT_PASSWORD"]
```

## 3. Create a client and call `create_employee`

```python
from datetime import datetime
from decimal import Decimal

from sonnys_backoffice import SonnysBackofficeClient

with SonnysBackofficeClient(
    subdomain=subdomain,
    username=username,
    password=password,
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

    print(f"Employee ID: {result.employee_id}")
    print(f"POS User ID: {result.pos_user_id}")
    print(f"POS PIN:     {result.pos_pin}")
    print(f"Wage site:   {result.wage_site}")
    if result.warnings:
        for w in result.warnings:
            print(f"warning: {w}")
```

The `pos_pin` field in the result is populated whether the caller supplied one or the library auto-generated a 5-digit integer. Capture it — Backoffice won't show it again after creation.

## 4. Disable the employee

```python
    disabled = client.disable_employee(pos_user_id=12345)
    print(f"Disabled at: {disabled.disabled_at}")
```

The caller passes the *same* `pos_user_id` that was used to create the employee. The library looks up the internal `employee_id` by scanning the tenant's employee list, parses the full edit form, and re-POSTs it with `employee[isActive]` omitted — which is the only reliable way to disable a record on Sonny's Symfony-based Backoffice.

## 5. Pre-flight uniqueness checks

POS User IDs, emails, and phones are all unique per tenant. If you don't know in advance whether a value is taken, check before building the request:

```python
if not client.is_pos_user_id_available(12345):
    raise RuntimeError("POS ID 12345 is already taken")
if not client.is_email_available("jane.doe@example.com"):
    raise RuntimeError("email collision")
```

These helpers reuse the client's cached per-tenant employee index, so repeated checks in the same session are free.

To validate a single POS User ID against the live tenant (including disabled accounts, whose POS User IDs stay reserved), use `pos_user_id_exists` — the positive, always-live counterpart:

```python
if client.pos_user_id_exists(12345):
    raise RuntimeError("POS ID 12345 is already taken")
```

## What next?

- [Creating an employee](../guides/create-employee.md) — every parameter explained
- [Bulk operations](../guides/bulk-operations.md) — the pattern for loops
- [Error handling](../guides/error-handling.md) — the exception hierarchy
