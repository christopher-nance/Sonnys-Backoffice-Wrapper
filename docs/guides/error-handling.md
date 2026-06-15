# Error Handling

All library errors inherit from a single base class, so you can catch everything the wrapper raises with one `except`:

```python
from sonnys_backoffice import SonnysBackofficeError

try:
    client.create_employee(...)
except SonnysBackofficeError as e:
    log.exception(e)
```

Most of the time you'll want to catch specific subclasses to apply different recovery strategies.

## Exception hierarchy

```
SonnysBackofficeError
├── AuthenticationError
├── DuplicateError
├── NotFoundError
├── AmbiguousMatchError
├── ValidationError
├── PermissionDeniedError
└── BackofficeServerError
```

### `AuthenticationError`

Login failed, or the session expired and re-authentication also failed.

**Common causes:**
- Wrong bot credentials.
- Bot user was disabled in Backoffice.
- Subdomain misspelled.

**Recovery:** inspect credentials, fix, retry. Do not loop on this.

```python
try:
    client.create_employee(...)
except AuthenticationError:
    alert_ops("Sonny's bot credentials broken")
    raise
```

### `DuplicateError`

POS User ID, email, or phone already exists on the tenant.

Raised at two points:

1. **Pre-flight** (before any HTTP call to `/employee/insert`) — the cached employee index already contains the value. This is the common case.
2. **Post-insert** — the server rejected the create with "already exists" in the response body. This usually means the cached index was stale and someone created a colliding record between cache load and your call.

**Recovery:** log the collision and either skip the row or generate a new value. For auto-generated IDs:

```python
for attempt in range(5):
    try:
        result = client.create_employee(pos_user_id=random_id(), **rest)
        break
    except DuplicateError:
        continue
```

### `NotFoundError`

A lookup didn't match. Raised by:
- `disable_employee(pos_user_id=...)` / `modify_employee(...)` when no employee has that POS User ID.
- `disable_employee(email=...)` when the email isn't in the employee list's visible columns (see [Disabling an Employee](disable-employee.md#email-lookup-caveat)).
- `create_backoffice_user(link_to_employee_pos_user_id=...)` when the employee doesn't exist.
- `create_employee` / `modify_employee` when the `permission` name doesn't match any template on the tenant (no silent fallback — the message lists the valid templates).

**Recovery:** inspect the key, double-check the tenant has the record, retry with a corrected lookup.

### `AmbiguousMatchError`

A name lookup (`find_employee`) matched more than one employee and couldn't be narrowed to one —
either no `phone` was given, or the phone didn't single out a candidate. The message lists the
candidate `pos_user_id`s.

**Recovery:** pass a `phone` to disambiguate, widen/narrow with `active`, or surface the
candidates for manual confirmation rather than guessing. This is deliberately distinct from
`NotFoundError` (zero matches) so automation can tell "couldn't confidently pick one" apart from
"not here."

### `ValidationError`

Caller input violated a constraint *or* Backoffice rejected the submitted payload. Common causes:

- Phone that isn't 9 or 10 digits after stripping symbols.
- Email without a valid `@domain.tld`.
- Missing required field (e.g., `permission` omitted).
- `available_sites` is empty and the tenant is not auto-resolvable.
- `requires_backoffice=True` but `backoffice_username` is missing.

Pydantic's error messages are included in the exception text.

**Recovery:** fix the input, don't retry blindly.

### `PermissionDeniedError`

The bot user lacks sufficient rights for the requested operation. Reserved for future use — Milestone 1 raises `BackofficeServerError` when the server rejects an operation on permission grounds, because the server response is indistinguishable from generic 403s without form-specific parsing.

### `BackofficeServerError`

Unexpected server response. Covers:

- HTTP 5xx from Backoffice.
- HTML that the parser couldn't understand (e.g., Backoffice shipped a new UI version).
- Disable round-trip accepted by the server but the employee is still active (bindings changed).
- Linked BO user creation failed because the linked employee is inactive.

**Recovery:** look at the exception message, check Sonny's status, retry with exponential backoff if transient. If the HTML parser is broken against a new Backoffice release, file a bug.

## Warnings vs exceptions

Things that are non-fatal go into `result.warnings` as strings, not exceptions. Examples:

- Department name that didn't match any known department (silently dropped).
- A requested `wage_effective_date` clamped up to the earliest legal date.
- Milestone 1 BO permission template deferral notice.

(An unknown `permission` name is **not** a warning — it raises `NotFoundError`.)

Always log `result.warnings` after a successful create — they're how the library tells you "something unexpected happened but I made a reasonable choice."

```python
result = client.create_employee(...)
for w in result.warnings:
    log.warning(f"create_employee: {w}")
```
