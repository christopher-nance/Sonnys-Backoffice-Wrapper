# Disabling an Employee

Disabling an employee in Sonny's Backoffice is deceptively tricky. The UI shows it as a single toggle, but under the hood it's an entire form round-trip. This guide explains the mechanism and the API.

## Basic usage

Look up by POS User ID:

```python
result = client.disable_employee(pos_user_id=12345)
print(f"Disabled employee {result.employee_id} at {result.disabled_at}")
```

Or by email:

```python
result = client.disable_employee(email="jane.doe@example.com")
```

Exactly one of `pos_user_id` or `email` is required. Passing both raises `ValidationError`.

## Finding the employee by name (the reliable key)

In practice, neither POS User ID nor email is always available, and **email is unreliable**:
the roster page has no email column (so an email lookup can return `NotFoundError` for an
employee who is clearly active), and Sonny's accounts are usually created with the employee's
**personal** email rather than a work address. The dependable key is the employee's
**first + last name**, with **phone number** as a tiebreaker when names collide.

`find_employee` resolves a name to a single `EmployeeSummary` (one roster request), which you
then disable by its POS User ID:

```python
emp = client.find_employee(first_name="Jane", last_name="Doe", phone="615-555-0001")
client.disable_employee(pos_user_id=emp.pos_user_id)
```

Resolution rules:

- Exactly one name match → returned.
- Multiple matches **and** `phone` given → narrowed by phone (digits-only, compared on the
  last 10 so a leading country code or formatting doesn't matter). One survivor → returned.
- No name match → `NotFoundError`.
- Still ambiguous (several after the phone step, or several with no phone) →
  `AmbiguousMatchError`, whose message lists the candidate POS User IDs so you can fall back to
  manual confirmation instead of guessing.

`active` defaults to `"active"` (the live employee you'd typically disable); pass `"inactive"`
or `"all"` to widen. Use `find_employees(first_name=…, last_name=…)` to get every name match
(no phone narrowing) when you want to inspect the candidates yourself.

```python
from sonnys_backoffice import AmbiguousMatchError, NotFoundError

try:
    emp = client.find_employee(first_name=first, last_name=last, phone=phone)
    client.disable_employee(pos_user_id=emp.pos_user_id)
except NotFoundError:
    ...  # not on this tenant — try the next one
except AmbiguousMatchError as e:
    ...  # flag for manual confirmation; e lists the candidate POS User IDs
```

## Why the round-trip?

The naive approach — `POST /employee/update` with `{employee[id]: X, employee[isActive]: "0"}` — looks like it works: the server returns HTTP 302. But the employee stays active.

Sonny's runs on Symfony, which binds form checkboxes by **presence, not value**. Sending `employee[isActive]=0` (or any value) is parsed as "the box is checked." To actually uncheck the box over the wire, the field must be absent from the POST body entirely.

Worse, a POST containing only `employee[id]` without the rest of the form fields is rejected outright — the form binds as empty and no fields are updated.

**The only reliable disable mechanism is a full form round-trip:**

1. `GET /employee?limit=10000&active=all` — fetch the complete employee list (including currently-disabled rows, so email lookup works).
2. Find the target row by matching POS User ID (or email) and extract `employee_id` from the row's `/employee/edit/<id>` link.
3. `GET /employee/edit/<id>` — load the full edit form HTML.
4. Parse every input, select, and textarea inside `<form action="/employee/update">` into a list of `(name, value)` tuples, **omitting `employee[isActive]`** and skipping any input that carries the `disabled` HTML attribute (browsers don't submit disabled fields).
5. `POST /employee/update` with that full payload.
6. `GET /employee/edit/<id>` again and verify the `isActive` checkbox is no longer checked. If it still is, raise `BackofficeServerError`.

The library implements all six steps. The entire thing happens inside a single `disable_employee` call.

## Email lookup caveat

The employee list table **does not include an email column**, so an email lookup has to scan row text and will only match if the email happens to appear somewhere in the rendered columns (usually it doesn't). If the email isn't found, the library raises `NotFoundError`. Prefer `pos_user_id`, or resolve by name with [`find_employee`](#finding-the-employee-by-name-the-reliable-key) (above) when you don't have the ID.

## What happens to the Backoffice user?

Disabling an employee does **not** automatically disable any linked Backoffice user. Subsequent login attempts for that BO user will still authenticate. You have two options:

1. Disable the BO user manually in the UI after disabling the employee. Recommended.
2. Delete the BO user via the UI. Irreversible.

Milestone 2 will add `disable_backoffice_user` to the library.

## Verification

The library always re-GETs the edit page after posting the update and re-checks the `isActive` attribute. If the POST went through but the state didn't change, you get a `BackofficeServerError` — you never get a silent no-op.
