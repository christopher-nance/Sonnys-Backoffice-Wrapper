# Bulk Disable From CSV

Read a CSV of `pos_user_id` values, disable each one, and write a results CSV. Useful for offboarding a batch of former employees from an HR export.

```python
"""
bulk_disable_from_csv.py — disable every employee listed in an input CSV.

Input CSV format (header row required):

    pos_user_id
    12345
    12346
    12347

Usage:
    SONNYS_SUBDOMAIN=washu \
    SONNYS_BOT_USERNAME=automation-bot \
    SONNYS_BOT_PASSWORD=... \
    python bulk_disable_from_csv.py input.csv output.csv
"""
import csv
import os
import sys
from datetime import datetime

from sonnys_backoffice import (
    BackofficeServerError,
    NotFoundError,
    SonnysBackofficeClient,
    SonnysBackofficeError,
)


def main(input_path: str, output_path: str) -> int:
    with SonnysBackofficeClient(
        subdomain=os.environ["SONNYS_SUBDOMAIN"],
        username=os.environ["SONNYS_BOT_USERNAME"],
        password=os.environ["SONNYS_BOT_PASSWORD"],
    ) as client, open(input_path, "r", newline="") as in_f, open(
        output_path, "w", newline=""
    ) as out_f:
        reader = csv.DictReader(in_f)
        writer = csv.writer(out_f)
        writer.writerow(["pos_user_id", "status", "employee_id", "disabled_at", "error"])

        success = 0
        failure = 0

        for row in reader:
            raw = row.get("pos_user_id", "").strip()
            if not raw:
                continue
            try:
                pid = int(raw)
            except ValueError:
                writer.writerow([raw, "error", "", "", "pos_user_id not an integer"])
                failure += 1
                continue

            try:
                result = client.disable_employee(pos_user_id=pid)
                writer.writerow(
                    [
                        pid,
                        "disabled",
                        result.employee_id,
                        result.disabled_at.isoformat(),
                        "",
                    ]
                )
                success += 1
                print(f"  disabled {pid} -> employee_id {result.employee_id}")
            except NotFoundError as e:
                writer.writerow([pid, "not_found", "", "", str(e)])
                failure += 1
            except BackofficeServerError as e:
                writer.writerow([pid, "server_error", "", "", str(e)])
                failure += 1
            except SonnysBackofficeError as e:
                writer.writerow([pid, "error", "", "", f"{type(e).__name__}: {e}"])
                failure += 1

            out_f.flush()

        print(f"\ndone. success={success}, failure={failure}")
        return 0 if failure == 0 else 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python bulk_disable_from_csv.py INPUT.csv OUTPUT.csv", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
```

## Notes

- **One client for the whole batch.** The cached employee list and session cookies are reused — no repeated logins.
- **Fail-soft per row.** One broken row doesn't kill the batch. Each failure lands in the output CSV with a reason so you can post-process.
- **`out_f.flush()` after every row.** If the process crashes halfway, the partial output is still on disk.
- **`NotFoundError` vs `BackofficeServerError`.** `NotFoundError` means the POS User ID wasn't in the tenant (typo, already-deleted employee). `BackofficeServerError` means the disable POST went through but the verification check saw the employee still active — a structural problem, usually worth investigating before retrying.

## Rate limiting

For batches over ~50 employees, add a small delay every 10 rows to be polite:

```python
if success % 10 == 0:
    import time
    time.sleep(1.0)
```
