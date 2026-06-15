# Reading employees

The wrapper is a full read/write interface, not just write. These methods let you
browse the roster and read an employee's current state — so a web app can show
current values, pre-select dropdowns, and then write changes back with
[`modify_employee`](modify-employee.md).

All reads are **live** — employee state is never cached, so you always see current truth.

## List the roster

`list_employees()` returns lightweight rows in one request:

```python
for row in client.list_employees(active="active"):
    print(row.employee_id, row.pos_user_id, row.first_name, row.last_name, row.is_active)
```

`active` is `"active"` (default), `"inactive"`, or `"all"`. Each `EmployeeSummary` carries
`employee_id`, `pos_user_id`, `first_name`, `last_name`, `phone`, and `is_active`. For the
full profile of a selected person, call `get_employee`.

## Find an employee by name

When you don't have a POS User ID, resolve one by name. This is the reliable lookup — the roster
has no email column and Sonny's accounts often use a personal email, so email lookups miss.

```python
emp = client.find_employee(first_name="Jane", last_name="Doe", phone="615-555-0001")
# -> a single EmployeeSummary; then e.g. client.disable_employee(pos_user_id=emp.pos_user_id)
```

`phone` is only used as a tiebreaker when several employees share a name (compared digits-only on
the last 10 digits). A name with no match raises `NotFoundError`; a name that stays ambiguous
raises `AmbiguousMatchError` (its message lists the candidate POS User IDs). Use
`find_employees(first_name=…, last_name=…)` to get every name match without the phone narrowing.
See [Disabling an employee](disable-employee.md#finding-the-employee-by-name-the-reliable-key)
for the full resolution rules.

## Read one employee (full snapshot)

`get_employee()` fetches everything — identity, contact, departments, sites, active state,
current pay + wage history, and the current permission level:

```python
emp = client.get_employee(pos_user_id=12345)   # or email="jane@example.com"

print(emp.first_name, emp.last_name, emp.is_active)
print(emp.departments, emp.available_sites)        # available_sites is a list of names, or "all"
print(emp.emergency_contact_name, emp.adp_employee_id, emp.start_date)

if emp.current_wage:
    print(emp.current_wage.rate, emp.current_wage.overtime_rate, emp.current_wage.overtime_eligible)

print(emp.permission.template_name, emp.permission.is_custom)
```

It raises `NotFoundError` if no employee matches the lookup key.

## Read just one section (fewer requests)

`get_employee()` hits three pages. If a screen only needs one slice, use the granular
getters — each is one resolve request plus one page fetch:

| Method | Returns |
|---|---|
| `get_employee_profile(...)` | `EmployeeProfile` — identity, contact, departments, sites, active state |
| `get_employee_compensation(...)` | `EmployeeCompensation` — `current` wage + full `history` |
| `get_employee_permission(...)` | `EmployeePermission` — current grant state + best-effort template name |

## The permission-level dropdown pattern

The motivating use case: your app shows a permission dropdown and writes the choice back to
Sonny's. Populate the dropdown from Sonny's actual templates, pre-select the employee's
current level, and post the change:

```python
# 1. Options come from Sonny's, so they're always valid to write back.
templates = [p.name for p in client.list_permissions(scope="pos")]

# 2. Pre-select the employee's current level.
current = client.get_employee_permission(pos_user_id=12345)
selected = current.template_name        # None when the grants don't match a template exactly
is_custom = current.is_custom           # show a "Custom" entry in that case

# 3. After the user picks one, write it back.
client.modify_employee(pos_user_id=12345, permission=chosen_template)
```

!!! note "Current permission is best-effort"
    Sonny's doesn't store a clean "current template" — applying a template stamps its grant
    matrix and the dropdown resets to blank. The wrapper reconstructs the level by matching the
    employee's granted permission IDs against the tenant's templates. An exact match yields
    `template_name`; a customized employee yields `template_name=None, is_custom=True`, and you
    can still read the raw `granted_permission_ids` / `override_permission_ids`.

## Wage history

`current_wage` is the active record (no end date). `wage_history` is every record, each with
`effective_date` and `end_date`. A disabled employee may have `current_wage=None` (their wage
record was ended) while still showing history.
