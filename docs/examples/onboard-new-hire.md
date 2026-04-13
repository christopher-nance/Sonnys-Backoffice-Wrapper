# Onboard a New Hire

Complete runnable script for a single new-hire workflow: pick a free POS User ID, create the employee, create a linked Backoffice user, and print the credentials the new hire needs on their first day.

```python
"""
onboard_new_hire.py — one-employee onboarding script.

Usage:
    SONNYS_SUBDOMAIN=washu \
    SONNYS_BOT_USERNAME=automation-bot \
    SONNYS_BOT_PASSWORD=... \
    python onboard_new_hire.py
"""
import os
import random
from datetime import datetime
from decimal import Decimal

from sonnys_backoffice import SonnysBackofficeClient, DuplicateError


def find_free_pos_id(client: SonnysBackofficeClient, preferred: int | None = None) -> int:
    """Return `preferred` if free, else a random 5-digit integer that is free."""
    if preferred is not None and client.is_pos_user_id_available(preferred):
        return preferred
    for _ in range(100):
        candidate = random.randint(10000, 99999)
        if client.is_pos_user_id_available(candidate):
            return candidate
    raise RuntimeError("could not find a free POS User ID after 100 attempts")


def main() -> None:
    with SonnysBackofficeClient(
        subdomain=os.environ["SONNYS_SUBDOMAIN"],
        username=os.environ["SONNYS_BOT_USERNAME"],
        password=os.environ["SONNYS_BOT_PASSWORD"],
    ) as client:
        pos_user_id = find_free_pos_id(client, preferred=50001)

        result = client.create_employee(
            first_name="Jane",
            last_name="Doe",
            phone="6155551234",
            email="jane.doe@example.com",
            pos_user_id=pos_user_id,
            wage_rate=Decimal("15.50"),
            start_date=datetime(2026, 5, 1),
            available_sites=["Wash 37135"],
            permission="General User",
            emergency_contact_name="John Doe",
            emergency_contact_phone="6155559999",
            requires_backoffice=True,
            backoffice_username="janedoe",
        )

        print("=" * 60)
        print(f"Employee created: {result.first_name} {result.last_name}")
        print(f"  Employee ID:          {result.employee_id}")
        print(f"  POS User ID:          {result.pos_user_id}")
        print(f"  POS PIN:              {result.pos_pin}")
        print(f"  Wage site:            {result.wage_site}")
        print(f"  Role:                 {result.permission_applied}")
        print()
        print(f"  Backoffice user ID:   {result.backoffice_user_id}")
        print(f"  Backoffice username:  {result.backoffice_username}")
        print(f"  Backoffice password:  {result.backoffice_password}")
        print()
        for w in result.warnings:
            print(f"  WARNING: {w}")
        print("=" * 60)


if __name__ == "__main__":
    main()
```

## What to expect

On a fresh run you'll see something like:

```
============================================================
Employee created: Jane Doe
  Employee ID:          487
  POS User ID:          50001
  POS PIN:              34182
  Wage site:            Wash 37135
  Role:                 General User

  Backoffice user ID:   3312200
  Backoffice username:  janedoe
  Backoffice password:  Kx7!mP2wQ8rT

  WARNING: permission template assignment is deferred to Milestone 2 — assign via the Backoffice UI (shield icon) on /user
============================================================
```

The Milestone 1 BO deferral warning is expected — hand the new hire the credentials and remember to click the shield icon in the Backoffice UI to apply their role before their first day.

## Notes

- `find_free_pos_id` is a defensive pattern — if `preferred=50001` is already taken (e.g., a previous hire used it), fall back to a random integer. You can customize the range if your organization uses specific POS ID ranges per site or department.
- `requires_backoffice=True` creates the linked BO user in the same call. The library returns the auto-generated password in `result.backoffice_password` — capture it, because Backoffice won't display it again.
- Always log `result.warnings`. Permission fallbacks, missed departments, and the BO deferral are surfaced there.
