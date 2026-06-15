# Modify an employee

Use `modify_employee` to change any combination of an employee's properties, compensation, site availability, or permission template in a single call.

## Basic usage

```python
from sonnys_backoffice import SonnysBackofficeClient

with SonnysBackofficeClient(
    subdomain="washu",
    username="bot",
    password="secret",
) as client:
    # Change permission template
    result = client.modify_employee(
        pos_user_id=12345,
        permission="Shift Leader",
    )
    print(result.changes_applied)   # ["permission"]
    print(result.permission_applied) # "Shift Leader"
```

## Change compensation

A pay change creates a **new** wage record (the old one is given an end date — the rate history is preserved):

```python
from decimal import Decimal

result = client.modify_employee(
    pos_user_id=12345,
    wage_rate=Decimal("25.00"),
)
print(result.wage_effective_date)   # the date the new rate took effect
# Overtime eligibility is preserved from the current rate; if eligible and you
# don't pass overtime_wage_rate, overtime auto-computes to 1.5x the new rate.
```

To set overtime explicitly:

```python
result = client.modify_employee(
    pos_user_id=12345,
    wage_rate=Decimal("25.00"),
    overtime_wage_rate=Decimal("40.00"),
)
```

### Effective date rule

A new wage record must be effective **strictly after** the most recent existing rate's effective date. The wrapper handles this for you: the new rate defaults to **`max(today, most_recent_effective_date + 1 day)`** — i.e. effective today in the normal case, but automatically rolled forward to the earliest legal date when the current rate is *also* effective today (which happens, for example, if you change pay the same day you created the employee). The applied date is returned in `result.wage_effective_date`.

You can request a specific effective date — useful for backdating a raise:

```python
from datetime import datetime

result = client.modify_employee(
    pos_user_id=12345,
    wage_rate=Decimal("25.00"),
    wage_effective_date=datetime(2026, 6, 14),
)
```

If the date you ask for is on or before the most recent rate's effective date, it's clamped up to the earliest legal date and a note is added to `result.warnings`.

## Reactivate or deactivate

Pass `activate=True` to bring a disabled employee back, or `activate=False` to deactivate (equivalent to `disable_employee`). It can be combined with any other change in the same call:

```python
# Reactivate a former employee and restrict them to one site in one call
result = client.modify_employee(
    pos_user_id=12345,
    activate=True,
    available_sites=["WashU Niles"],
)
print(result.changes_applied)   # ["properties", "activated"]
```

## Change site availability

Switch from full access to specific sites:

```python
result = client.modify_employee(
    pos_user_id=12345,
    available_sites=["WashU Berwyn", "WashU Niles"],
)
```

Switch back to all sites:

```python
result = client.modify_employee(
    pos_user_id=12345,
    available_sites="all",
)
```

## Change multiple things at once

Properties, compensation, and permission can all be changed in one call. Each targets a different Backoffice form — only the forms with changes are submitted:

```python
result = client.modify_employee(
    pos_user_id=12345,
    first_name="Jane",
    last_name="Smith",
    phone="6155551234",
    departments=["Cashier", "Line"],
    wage_rate=Decimal("18.00"),
    permission="Manager",
    available_sites=["WashU Berwyn"],
)
print(result.changes_applied)
# ["properties", "compensation", "permission"]
```

## Lookup by email

You can look up by email instead of POS User ID, but `pos_user_id` is more reliable since the employee list page doesn't always show emails:

```python
result = client.modify_employee(
    email="jane@example.com",
    permission="CSA",
)
```

## Permission template errors

If the requested template name doesn't exist on the tenant, a `NotFoundError` is raised listing all available templates:

```python
from sonnys_backoffice import NotFoundError

try:
    client.modify_employee(pos_user_id=12345, permission="NonExistent")
except NotFoundError as e:
    print(e)
    # "permission template 'NonExistent' not found on this tenant.
    #  Available templates: ['Manager', 'Cashier', 'General User', 'CSA', 'Shift Leader']"
```
