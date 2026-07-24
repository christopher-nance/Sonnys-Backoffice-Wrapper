# Sonny's Backoffice Wrapper

Programmatic user management for Sonny's Carwash Controls Backoffice — create, link, and disable employees and Backoffice users from Python.

## Why this exists

Sonny's Controls offers a read-only Data API for reporting, but **no API for user management**. Every change to an employee or Backoffice user has to be made by hand in the web UI. That's fine for a handful of users, but painful at scale — especially for bulk onboarding, HRIS sync, and offboarding former employees.

This library closes the gap by driving Backoffice's HTTP endpoints directly with a pure `requests` session. No headless browser at runtime, no manual clicking.

## Install

```bash
pip install git+https://github.com/christopher-nance/Sonnys-Backoffice-Wrapper.git
```

## Ten-second quickstart

```python
from datetime import datetime
from decimal import Decimal

from sonnys_backoffice import SonnysBackofficeClient

with SonnysBackofficeClient(
    subdomain="washu",
    username="your-bot-user",
    password="your-bot-password",
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
    print(f"created employee {result.employee_id}, POS PIN: {result.pos_pin}")
```

## What's in the box

- `create_employee` — with or without a linked Backoffice user
- `modify_employee` — change properties, site availability, compensation, permission template, or active state (incl. reactivating a disabled employee)
- `disable_employee` — looked up by POS User ID or email
- `list_employees` / `get_employee` — read the roster and full current state of an employee (profile, pay rate + history, current permission); granular `get_employee_profile` / `get_employee_compensation` / `get_employee_permission` too
- `find_employee` / `find_employees` — resolve an employee by first + last name (with phone as a tiebreaker) — the reliable lookup when you don't have a POS User ID
- `create_backoffice_user` — standalone or linked to an existing employee
- `list_sites`, `list_departments`, `list_permissions` — discovery helpers
- `is_pos_user_id_available`, `is_email_available`, `is_phone_available` — pre-flight uniqueness checks
- `pos_user_id_exists` — live check for whether a POS User ID is already taken (active or inactive)
- Pydantic v2 input validation and typed result objects
- Automatic site/region/district hierarchy detection
- Case-insensitive permission name matching (unknown names raise `NotFoundError` listing the valid templates)
- Transparent session re-authentication on cookie expiration

## Status

Alpha. The public API is stable for Milestone 1.

!!! warning "Known limitation"
    **Backoffice user permission template assignment is deferred to Milestone 2.** `create_backoffice_user` (and the linked path of `create_employee`) creates the account successfully, but the caller must assign the template manually via the Backoffice UI (shield icon on the user list). See [Creating a Backoffice user](guides/create-backoffice-user.md).
