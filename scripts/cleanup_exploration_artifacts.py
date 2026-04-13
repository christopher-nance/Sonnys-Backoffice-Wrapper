"""Clean up disposable employees and BO users created during exploration.

Scans the WashU employee list for any employee whose first_name is
"WrapperExplore" (the exploration convention) and disables each one via
the library's ``disable_employee``. Also scans the BO user list for usernames
matching the exploration pattern and prints manual-cleanup instructions for
each, since M1 does not expose ``disable_backoffice_user``.

Safety:
    Dry-run by default. Pass ``--execute`` to actually disable records.

Usage:
    SONNYS_SUBDOMAIN=washu \\
    SONNYS_BOT_USERNAME=automation-bot \\
    SONNYS_BOT_PASSWORD=... \\
    python scripts/cleanup_exploration_artifacts.py [--execute]
"""

from __future__ import annotations

import argparse
import os
import re
import sys

from bs4 import BeautifulSoup

from sonnys_backoffice import SonnysBackofficeClient, SonnysBackofficeError

EXPLORATION_FIRST_NAME = "WrapperExplore"
EXPLORATION_BO_USERNAME_RE = re.compile(r"^wrapper[A-Za-z0-9]+bo$", re.IGNORECASE)

_EMP_ID_RE = re.compile(r"/employee/(?:edit|permissions|compensation)/(\d+)")
_USER_ID_RE = re.compile(r"/user/(?:edit|permissions)/(\d+)")


def find_exploration_employees(client: SonnysBackofficeClient) -> list[dict]:
    """Return a list of {employee_id, pos_user_id, full_name, is_active} rows."""
    resp = client._session.get(
        f"/employee?first_name={EXPLORATION_FIRST_NAME}&active=all&limit=1000"
    )
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", class_="table-employees-list")
    if table is None:
        return []
    rows = []
    for tr in table.find_all("tr"):
        emp_id: int | None = None
        for a in tr.find_all("a", href=True):
            m = _EMP_ID_RE.search(a["href"])
            if m:
                emp_id = int(m.group(1))
                break
        if emp_id is None:
            continue
        first_cell = tr.find("td", class_="employees-col-first-name")
        last_cell = tr.find("td", class_="employees-col-last-name")
        pos_cell = tr.find("td", class_="employees-col-pos-user-id")
        active_cell = tr.find("td", class_="employees-col-active")
        if first_cell is None or pos_cell is None:
            continue
        first = first_cell.get_text(strip=True)
        if first != EXPLORATION_FIRST_NAME:
            continue
        last = last_cell.get_text(strip=True) if last_cell else ""
        pos_text = pos_cell.get_text(strip=True)
        pos_user_id = int(pos_text) if pos_text.isdigit() else None
        # Active column has a green check <i class="fa-check"> when active,
        # red X <i class="fa-times"> (or similar) when disabled.
        is_active = bool(active_cell and active_cell.find("i", class_="fa-check"))
        rows.append(
            {
                "employee_id": emp_id,
                "pos_user_id": pos_user_id,
                "full_name": f"{first} {last}".strip(),
                "is_active": is_active,
            }
        )
    return rows


def find_exploration_bo_users(client: SonnysBackofficeClient) -> list[dict]:
    """Return a list of {user_id, username} rows matching the exploration pattern."""
    resp = client._session.get("/user?limit=10000&active=all")
    soup = BeautifulSoup(resp.text, "html.parser")
    rows = []
    seen_ids: set[int] = set()
    for a in soup.find_all("a", href=True):
        m = _USER_ID_RE.search(a["href"])
        if not m:
            continue
        uid = int(m.group(1))
        if uid in seen_ids:
            continue
        seen_ids.add(uid)
    # A more robust approach: look in the user list table for rows whose
    # username cell matches the pattern. Fall back to a full-text scan.
    for td in soup.find_all("td"):
        text = td.get_text(strip=True)
        if not EXPLORATION_BO_USERNAME_RE.match(text):
            continue
        # Walk up to the containing row and find the user id via its links
        row = td.find_parent("tr")
        if row is None:
            continue
        uid: int | None = None
        for a in row.find_all("a", href=True):
            m = _USER_ID_RE.search(a["href"])
            if m:
                uid = int(m.group(1))
                break
        rows.append({"user_id": uid, "username": text})
    return rows


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually disable records. Default is dry-run (report only).",
    )
    args = parser.parse_args(argv)

    subdomain = os.environ.get("SONNYS_SUBDOMAIN")
    username = os.environ.get("SONNYS_BOT_USERNAME")
    password = os.environ.get("SONNYS_BOT_PASSWORD")
    if not (subdomain and username and password):
        print(
            "ERROR: set SONNYS_SUBDOMAIN, SONNYS_BOT_USERNAME, SONNYS_BOT_PASSWORD", file=sys.stderr
        )
        return 2

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"[{mode}] cleanup_exploration_artifacts on {subdomain}.sonnyscontrols.com")
    print(f"[{mode}] will match employees with first_name={EXPLORATION_FIRST_NAME!r}")
    print(f"[{mode}] will match BO users matching {EXPLORATION_BO_USERNAME_RE.pattern!r}")
    print()

    with SonnysBackofficeClient(
        subdomain=subdomain, username=username, password=password
    ) as client:
        # ─── Employees ────────────────────────────────────────────────────
        print("[1/2] Scanning employees...")
        employees = find_exploration_employees(client)
        if not employees:
            print("  no exploration employees found.")
        else:
            print(f"  found {len(employees)} exploration employee(s):")
            for e in employees:
                status = "ACTIVE" if e["is_active"] else "disabled"
                print(
                    f"    [{e['employee_id']:4d}] pos={e['pos_user_id']} "
                    f"{e['full_name']:30s} [{status}]"
                )

            to_disable = [e for e in employees if e["is_active"]]
            if to_disable:
                print(f"\n  {len(to_disable)} active employee(s) will be disabled.")
                if args.execute:
                    for e in to_disable:
                        if e["pos_user_id"] is None:
                            print(f"    [SKIP] {e['employee_id']}: no POS User ID")
                            continue
                        try:
                            result = client.disable_employee(pos_user_id=e["pos_user_id"])
                            print(
                                f"    [OK]   {e['employee_id']}: disabled at "
                                f"{result.disabled_at.isoformat()}"
                            )
                        except SonnysBackofficeError as err:
                            print(f"    [FAIL] {e['employee_id']}: {type(err).__name__}: {err}")
                else:
                    print("  (dry-run — pass --execute to actually disable)")
            else:
                print("\n  nothing to disable.")

        print()

        # ─── BO users ─────────────────────────────────────────────────────
        print("[2/2] Scanning BO users...")
        bo_users = find_exploration_bo_users(client)
        if not bo_users:
            print("  no exploration BO users found.")
        else:
            print(f"  found {len(bo_users)} exploration BO user(s):")
            for u in bo_users:
                print(f"    [{u.get('user_id') or '?'}] {u['username']}")
            print()
            print("  NOTE: disable_backoffice_user is not implemented in Milestone 1.")
            print("  Manually disable or delete these via the Backoffice UI:")
            print(f"    1. Open https://{subdomain}.sonnyscontrols.com/user")
            print("    2. Find each username above")
            print("    3. Click the disable/delete action")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
