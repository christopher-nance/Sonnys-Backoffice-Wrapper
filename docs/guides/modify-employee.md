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

Creates a new wage record effective today:

```python
from decimal import Decimal

result = client.modify_employee(
    pos_user_id=12345,
    wage_rate=Decimal("25.00"),
)
# If the employee is overtime-eligible, overtime auto-computes to 1.5x
```

To set overtime explicitly:

```python
result = client.modify_employee(
    pos_user_id=12345,
    wage_rate=Decimal("25.00"),
    overtime_wage_rate=Decimal("40.00"),
)
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
