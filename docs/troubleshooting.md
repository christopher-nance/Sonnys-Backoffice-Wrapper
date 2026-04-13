# Troubleshooting

## `AuthenticationError: Login failed — credentials rejected by Backoffice`

The bot user's username or password is wrong, or the account has been disabled in Backoffice.

**Fix:**
1. Verify you can log into Backoffice manually at `https://<subdomain>.sonnyscontrols.com/login` using the exact same credentials.
2. Check that the bot user is active (shield icon should be green on the `/user` list).
3. If you recently rotated the password, update whichever environment variable or secret store your code reads from.

## `DuplicateError: pos_user_id=XXXXX already exists on employee_id=YY`

Another employee already uses that POS User ID. POS User IDs are unique per tenant and the library pre-flights the check against a cached index.

**Fix:** either pick a different POS User ID or, if you believe the existing record is stale, disable the old employee first:

```python
client.disable_employee(pos_user_id=12345)
client.create_employee(pos_user_id=12345, ...)  # now reusable
```

Actually — even after disable, Sonny's **retains** the POS User ID on the disabled record. You cannot reuse it without a support request to Sonny's Controls. Use a different number.

## `DuplicateError` on email or phone

Same story as POS User ID: emails and phones are unique per tenant. Pre-flight with `client.is_email_available(...)` or `client.is_phone_available(...)`.

## `ValidationError: phone must be 9 or 10 digits after symbols are stripped`

The phone number has too many or too few digits. The library strips everything that isn't a digit before counting. Examples:

- ✅ `"6155551234"` — 10 digits
- ✅ `"(615) 555-1234"` — 10 digits after stripping
- ✅ `"615-555-1234 ext. 5"` — 11 digits → **fails** (extensions aren't supported)
- ❌ `"1-615-555-1234"` — 11 digits (leading "1" country code) → **fails**

**Fix:** strip the country code or extension before calling the library. Store it separately if you need to preserve it.

## `NotFoundError: no employee found for pos_user_id=XXXXX`

`disable_employee` couldn't find the target in the employee list.

**Causes:**
- The POS User ID doesn't exist on the tenant (typo).
- The employee is not in the first 10,000 list rows — extremely unlikely.
- The tenant has a non-standard employee list page (Sonny's UI migration).

**Fix:** verify the POS User ID exists in the Backoffice UI at `/employee`. If you're trying to disable by email, switch to `pos_user_id` — email lookup only works when the email appears in the visible list columns, which it usually doesn't.

## `BackofficeServerError: disable POST accepted but employee XXX is still active`

The disable round-trip went through (HTTP 302) but the re-GET verification saw the `isActive` checkbox still checked.

**Causes:**
- Backoffice UI was migrated and the form field name changed.
- A different form on the page has the same field name.
- The parser is skipping a field that the server now requires.

**Fix:** file a bug with the tenant subdomain. This is a structural wrapper issue, not something a retry will fix.

## `BackofficeServerError: linked BO user creation requires the employee to be active`

You're trying to link a BO user to a disabled employee. This is a Sonny's server-side rule — not a library limitation.

**Fix:** re-enable the employee first (manually, via the Backoffice UI — `enable_employee` is on the Milestone 2 roadmap), then create the linked BO user, then re-disable if needed.

## `LookupError: Unknown Site: 'Nolensville'`

The site name doesn't exist on the tenant. Site names are case-sensitive and must exactly match the Backoffice UI label.

**Fix:** list the tenant's sites to see valid names:

```python
for s in client.list_sites():
    print(s.name)
```

## BO user created but no permissions apply

This is expected in Milestone 1. `create_backoffice_user` (and the linked BO path of `create_employee`) creates the account but deliberately does not assign a permission template — see [Creating a Backoffice user](guides/create-backoffice-user.md). Check the `result.warnings` list, and click the shield icon in the Backoffice UI to apply a template manually.

## Session keeps re-authenticating in a loop

If you're seeing "Re-authentication failed" errors, the Backoffice session cookie is being rejected by the server on every request.

**Causes:**
- You're running multiple concurrent calls against the same client instance (not thread-safe).
- The bot user got disabled while your process was running.
- Backoffice's session table was cleared server-side (e.g., during a deploy).

**Fix:** don't share one client across threads. If you need parallelism, create one client per thread and be mindful of the rate limit.

## `mkdocs build --strict` warnings

Not a library issue — see the development section of the [installation guide](getting-started/installation.md) for doc build instructions.

## Where to report bugs

File issues at <https://github.com/christopher-nance/Sonnys-Backoffice-Wrapper/issues>. Include:
- Subdomain (or a representative anonymized one).
- Exact exception message.
- The HTML response body if the error is a parse failure (with PII redacted).
- Library version (`sonnys_backoffice.__version__`).
