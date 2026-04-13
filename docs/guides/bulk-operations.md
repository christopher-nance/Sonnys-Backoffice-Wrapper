# Bulk Operations

The library is designed for one call per operation. Bulk workflows are just loops — the client handles session reuse, caching, and rate-limiting concerns for you. This guide explains the patterns that work and the ones that don't.

## Pattern: reuse one client

Always reuse a single client across many operations. The caches (site tree, departments, permissions, employee index) are populated on the first call and shared across all subsequent calls.

```python
with SonnysBackofficeClient(subdomain=..., username=..., password=...) as client:
    for row in new_hires_csv:
        client.create_employee(**row)
```

Creating a new client per call would re-fetch every page of cache data and re-authenticate. On a 500-employee onboarding batch that's 2000+ wasted HTTP calls.

## Pattern: refresh the employee index between writes

The employee index used by `is_pos_user_id_available()` / `is_email_available()` / `is_phone_available()` is a snapshot, not a live view. After a batch of `create_employee` calls, old checks may still return `True` for IDs that are now taken by earlier iterations of the loop.

Two options:

**Option A — trust the pre-flight inside `create_employee`.** The orchestrator always re-checks uniqueness from the cached index before POSTing. If the cached index is stale, the check passes but the server rejects the create with a duplicate error and you get `DuplicateError`. Handle it in your loop:

```python
for row in rows:
    try:
        client.create_employee(**row)
    except DuplicateError as e:
        log.warning(f"skipping {row['email']}: {e}")
```

**Option B — refresh the index explicitly before each create.** Slower (one extra HTTP call per loop iteration), but gives you a clean check-then-act pattern:

```python
for row in rows:
    if not client.is_pos_user_id_available(row["pos_user_id"], refresh=True):
        log.warning(f"skipping {row['email']}: pos_user_id already taken")
        continue
    client.create_employee(**row)
```

Use Option A for most workloads. Use Option B only if you're doing something like "try to use the same pos_user_id across multiple runs" where a stale index could cause a problem.

## Pattern: fail-fast vs continue-on-error

Most bulk workflows want "continue on error and report at the end":

```python
results = []
errors = []

for row in rows:
    try:
        result = client.create_employee(**row)
        results.append((row["email"], result.employee_id, result.pos_pin))
    except DuplicateError as e:
        errors.append((row["email"], "duplicate", str(e)))
    except ValidationError as e:
        errors.append((row["email"], "invalid", str(e)))
    except BackofficeServerError as e:
        errors.append((row["email"], "server", str(e)))

print(f"created {len(results)}, failed {len(errors)}")
```

See [Error handling](error-handling.md) for the full exception hierarchy.

## Pattern: write results to disk as you go

Don't hold all the created credentials in memory and dump them at the end — if the process crashes halfway through, you'll have a bunch of live accounts with unknown passwords. Append to a file after each successful create:

```python
import csv

with open("new_hires_results.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["email", "employee_id", "pos_pin", "bo_password"])
    for row in rows:
        try:
            result = client.create_employee(**row)
            writer.writerow([
                row["email"],
                result.employee_id,
                result.pos_pin,
                result.backoffice_password or "",
            ])
            f.flush()  # flush after every row
        except Exception as e:
            print(f"failed {row['email']}: {e}")
```

## Pattern: rate limiting

Sonny's Backoffice doesn't publish an explicit rate limit. In practice, a tight loop over `create_employee` works but is impolite — each call does 3-4 HTTP round trips. For batches larger than ~50, sprinkle in a small delay:

```python
import time

for i, row in enumerate(rows):
    client.create_employee(**row)
    if i % 10 == 9:
        time.sleep(1.0)
```

## What the library does NOT do

- No parallelism. The `_BackofficeSession` object wraps a single `requests.Session`, which is not thread-safe. Don't share a client across threads.
- No retry on transient failures. If a call raises `BackofficeServerError`, it's propagated immediately — you decide whether to retry. (The session does have built-in re-authentication for expired cookies, but that's a different kind of recovery.)
- No implicit transactions. If `create_employee` fails halfway through the two-step create → permissions flow, the employee may exist with a default permission set. Catch the error and reconcile manually.
