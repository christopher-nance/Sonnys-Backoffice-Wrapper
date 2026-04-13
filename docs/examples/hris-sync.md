# Sync From an HRIS

This is a **sketch**, not a runnable script. Every HRIS has a different export format and reconciliation policy, so the goal is to show the overall shape of an HRIS → Sonny's sync rather than a turnkey tool.

## The reconciliation model

An HRIS sync has three states per employee:

| HRIS state | Sonny's state | Action |
|---|---|---|
| Active | Missing | `create_employee` |
| Active | Active | No-op (or `modify_employee` in M2+) |
| Inactive / terminated | Active | `disable_employee` |
| Inactive / terminated | Missing / disabled | No-op |

You need a **stable cross-system key** to join HRIS records to Sonny's records. The best options:

1. **ADP Employee ID** — if your tenant uses ADP payroll, Sonny's stores `employee[adpEmployeeId]` on every employee record. You can set it via `create_employee(adp_employee_id=...)` and query it back via the Backoffice export (not currently exposed by this library — you'd read it from `/employee/edit/<id>` directly for M1).
2. **Email** — usable as long as every employee has a unique corporate email. Works for small tenants, breaks down for larger ones where baristas and cashiers might share a family email.
3. **POS User ID** — works if you control the POS ID assignment from the HRIS.

**Do not use first+last name.** Two employees can share a name. One name collision will cause you to overwrite the wrong record.

## Sketch

```python
"""
hris_sync.py — one-way HRIS → Sonny's sync. SKETCH, not production.

Assumes an HRIS export with columns:
    hris_id, first_name, last_name, email, phone, pos_user_id, status, start_date

where `status` is one of {"active", "terminated"}.
"""
import csv
import os
from datetime import datetime
from decimal import Decimal

from sonnys_backoffice import (
    DuplicateError,
    NotFoundError,
    SonnysBackofficeClient,
    SonnysBackofficeError,
)


def main(hris_export_path: str) -> None:
    with SonnysBackofficeClient(
        subdomain=os.environ["SONNYS_SUBDOMAIN"],
        username=os.environ["SONNYS_BOT_USERNAME"],
        password=os.environ["SONNYS_BOT_PASSWORD"],
    ) as client:
        with open(hris_export_path, "r", newline="") as f:
            for row in csv.DictReader(f):
                sync_row(client, row)


def sync_row(client: SonnysBackofficeClient, row: dict[str, str]) -> None:
    """Reconcile one HRIS row against Sonny's."""
    pos_id = int(row["pos_user_id"])
    email = row["email"]
    status = row["status"]

    if status == "active":
        if not client.is_pos_user_id_available(pos_id):
            # Already in Sonny's. For M1 we no-op; a future modify_employee
            # would update changed fields here.
            print(f"  [skip] {email}: already exists in Sonny's")
            return
        try:
            result = client.create_employee(
                first_name=row["first_name"],
                last_name=row["last_name"],
                phone=row["phone"],
                email=email,
                pos_user_id=pos_id,
                wage_rate=Decimal("15.00"),  # TODO: pull from HRIS
                start_date=datetime.fromisoformat(row["start_date"]),
                available_sites="all",
                permission="General User",
                adp_employee_id=row.get("hris_id"),
            )
            print(f"  [create] {email}: employee_id={result.employee_id}")
        except DuplicateError as e:
            # Cache drift: another process created this record between our
            # check and the call. Treat as a skip.
            print(f"  [skip] {email}: created elsewhere ({e})")

    elif status == "terminated":
        try:
            client.disable_employee(pos_user_id=pos_id)
            print(f"  [disable] {email}: pos_user_id={pos_id}")
        except NotFoundError:
            print(f"  [skip] {email}: not in Sonny's (already removed or never synced)")
        except SonnysBackofficeError as e:
            print(f"  [error] {email}: {e}")

    else:
        print(f"  [skip] {email}: unknown status {status!r}")
```

## Gotchas and design decisions

### Don't reassign POS User IDs

Once an employee has been disabled, their POS User ID is still held by their record. If you sync a new hire with the same POS User ID, `create_employee` will fail with `DuplicateError`. Either:

- Use a different ID range for new hires, or
- Generate a random 5-digit ID (`find_free_pos_id` pattern from [Onboard a new hire](onboard-new-hire.md)).

### Site assignment policy

`available_sites="all"` is the simplest default — the employee can work anywhere. If your HRIS tracks home sites, map them to Sonny's site names in the sync layer:

```python
sites = [row["home_site"], row.get("secondary_site")]
sites = [s for s in sites if s]  # drop None
client.create_employee(available_sites=sites, ...)
```

### When to refresh caches

If your sync runs in one long-lived process, call `client.list_sites(refresh=True)` and `client.is_pos_user_id_available(..., refresh=True)` at the start of each reconciliation batch. The site tree and employee index are cached forever otherwise.

### Idempotence

The sketch above is safe to re-run: creating an existing employee is a skip, disabling an already-disabled employee is a NotFoundError-handled skip. Write your sync to be idempotent — partial failures are inevitable and you want to be able to re-run without surgery.

### What's missing for a real HRIS sync

- `modify_employee` for the "update changed fields" path. Deferred to Milestone 2+.
- `list_employees` for pulling the current state from Sonny's. The library does not currently expose this, though the internal `EmployeeIndex` has most of what you'd need.
- An async/parallel mode for very large tenants. Not supported — reuse one synchronous client in a loop.
