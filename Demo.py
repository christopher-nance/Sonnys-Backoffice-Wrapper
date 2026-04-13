"""Demo.py — walk through every public endpoint on SonnysBackofficeClient.

Run:
    SONNYS_SUBDOMAIN=washu \
    SONNYS_BOT_USERNAME=automation-bot \
    SONNYS_BOT_PASSWORD=... \
    python Demo.py

Safety:
    Write-mutating demos (create_employee, disable_employee, create_backoffice_user)
    are gated behind SONNYS_ALLOW_WRITES=1. The discovery / availability sections
    are always safe and run against the live tenant on every invocation.
"""

from __future__ import annotations

import os
import random
from datetime import datetime
from decimal import Decimal

from sonnys_backoffice import (
    BackofficeServerError,
    DuplicateError,
    NotFoundError,
    SonnysBackofficeClient,
    SonnysBackofficeError,
)

# ═══════════════════════════════════════════════════════════════════════════
#  CREDENTIALS
# ═══════════════════════════════════════════════════════════════════════════
#
# Three environment variables are required. Credentials should never be
# hard-coded in source. This script reads them from the environment and
# aborts early if any are missing.

SUBDOMAIN = os.environ.get("SONNYS_SUBDOMAIN")
USERNAME = os.environ.get("SONNYS_BOT_USERNAME")
PASSWORD = os.environ.get("SONNYS_BOT_PASSWORD")
ALLOW_WRITES = bool(os.environ.get("SONNYS_ALLOW_WRITES"))

if not (SUBDOMAIN and USERNAME and PASSWORD):
    raise SystemExit(
        "Missing credentials. Set SONNYS_SUBDOMAIN, SONNYS_BOT_USERNAME, "
        "and SONNYS_BOT_PASSWORD in the environment before running."
    )


def banner(title: str) -> None:
    """Print a section banner to separate demo phases in the output."""
    bar = "═" * 72
    print(f"\n{bar}\n  {title}\n{bar}")


def main() -> int:
    with SonnysBackofficeClient(
        subdomain=SUBDOMAIN,
        username=USERNAME,
        password=PASSWORD,
    ) as client:
        # ═══════════════════════════════════════════════════════════════════
        #  DISCOVERY — list_sites / list_departments / list_permissions
        # ═══════════════════════════════════════════════════════════════════
        #
        # These endpoints are read-only and populate the client's internal
        # caches. They're cheap to call and safe on every invocation.

        banner("1. Discovery — sites")
        sites = client.list_sites()
        print(f"tenant has {len(sites)} sites")
        for s in sites[:5]:
            hierarchy = (
                f"  region={s.region_id} district={s.district_id}"
                if s.region_id is not None
                else "  (flat)"
            )
            print(f"  [{s.id:3d}] {s.name}{hierarchy}")
        if len(sites) > 5:
            print(f"  ... and {len(sites) - 5} more")

        banner("2. Discovery — departments")
        for d in client.list_departments():
            print(f"  [{d.id}] {d.name}")

        banner("3. Discovery — POS role templates")
        pos_perms = client.list_permissions(scope="pos")
        for p in pos_perms:
            print(f"  [{p.id:3d}] {p.name}  (grants={len(p.grants)}, overrides={len(p.overrides)})")

        banner("4. Discovery — Backoffice role templates")
        try:
            bo_perms = client.list_permissions(scope="backoffice")
            for p in bo_perms:
                print(f"  [{p.id:3d}] {p.name}")
        except NotFoundError as e:
            # Tenants with no BO users yet can't populate the template list.
            # Safe to continue — everything else still works.
            print(f"  (skipped: {e})")

        # ═══════════════════════════════════════════════════════════════════
        #  AVAILABILITY — is_pos_user_id_available / is_email_available /
        #                 is_phone_available
        # ═══════════════════════════════════════════════════════════════════
        #
        # Pre-flight uniqueness checks. Backed by a lazy per-tenant employee
        # index built from /employee?limit=10000 + /user/create. The first
        # call fetches both pages; subsequent calls reuse the cached index.

        banner("5. Availability helpers")
        test_pos_id = 99_999_998
        test_email = "nobody-demo@example.invalid"
        test_phone = "555-000-0000"
        print(
            f"  is_pos_user_id_available({test_pos_id}): {client.is_pos_user_id_available(test_pos_id)}"
        )
        print(f"  is_email_available({test_email!r}): {client.is_email_available(test_email)}")
        print(f"  is_phone_available({test_phone!r}): {client.is_phone_available(test_phone)}")

        # ═══════════════════════════════════════════════════════════════════
        #  WRITE DEMOS — create_employee / disable_employee /
        #                create_backoffice_user
        # ═══════════════════════════════════════════════════════════════════
        #
        # Everything below mutates the live tenant. Gated behind
        # SONNYS_ALLOW_WRITES=1 so you can run the discovery half of the demo
        # without fear of accidentally creating records.

        if not ALLOW_WRITES:
            banner("WRITE DEMOS SKIPPED")
            print("  Set SONNYS_ALLOW_WRITES=1 to run create/disable/BO demos.")
            return 0

        # ───────────────────────────────────────────────────────────────────
        #  create_employee — POS-only happy path
        # ───────────────────────────────────────────────────────────────────

        banner("6. create_employee — POS-only happy path")
        pos_id = random.randint(90_000, 99_999)
        while not client.is_pos_user_id_available(pos_id, refresh=True):
            pos_id = random.randint(90_000, 99_999)
        first_site = sites[0].name
        email_a = f"wrapper-demo-a-{pos_id}@example.invalid"

        created_a = client.create_employee(
            first_name="WrapperDemo",
            last_name=f"PosOnly{pos_id}",
            phone="5555550001",
            email=email_a,
            pos_user_id=pos_id,
            wage_rate=Decimal("1.00"),
            start_date=datetime.now(),
            available_sites=[first_site],
            permission="General User",
            departments=["Greeter"],
        )
        print(f"  employee_id:         {created_a.employee_id}")
        print(f"  pos_user_id:         {created_a.pos_user_id}")
        print(f"  pos_pin:             {created_a.pos_pin}  (capture this!)")
        print(f"  permission_applied:  {created_a.permission_applied}")
        print(f"  wage_site:           {created_a.wage_site}")
        print(f"  sites_granted:       {created_a.sites_granted}")
        print(f"  departments:         {created_a.departments}")
        for w in created_a.warnings:
            print(f"  warning:             {w}")

        # ───────────────────────────────────────────────────────────────────
        #  create_employee — linked Backoffice user path
        # ───────────────────────────────────────────────────────────────────
        #
        # Passing requires_backoffice=True creates the employee AND a linked
        # BO user in the same call. The BO user's permission template must
        # still be assigned manually via the Backoffice UI in Milestone 1
        # (shield icon on /user).

        banner("7. create_employee — linked BO user path")
        pos_id_b = random.randint(90_000, 99_999)
        while not client.is_pos_user_id_available(pos_id_b, refresh=True):
            pos_id_b = random.randint(90_000, 99_999)
        email_b = f"wrapper-demo-b-{pos_id_b}@example.invalid"

        created_b = client.create_employee(
            first_name="WrapperDemo",
            last_name=f"LinkedBo{pos_id_b}",
            phone="5555550002",
            email=email_b,
            pos_user_id=pos_id_b,
            wage_rate=Decimal("1.00"),
            start_date=datetime.now(),
            available_sites="all",
            permission="General User",
            requires_backoffice=True,
            backoffice_username=f"demoboB{pos_id_b}",
        )
        print(f"  employee_id:         {created_b.employee_id}")
        print(f"  pos_user_id:         {created_b.pos_user_id}")
        print(f"  pos_pin:             {created_b.pos_pin}")
        print(f"  backoffice_user_id:  {created_b.backoffice_user_id}")
        print(f"  backoffice_username: {created_b.backoffice_username}")
        print(f"  backoffice_password: {created_b.backoffice_password}  (capture this!)")
        for w in created_b.warnings:
            print(f"  warning:             {w}")

        # ───────────────────────────────────────────────────────────────────
        #  create_backoffice_user — standalone mode
        # ───────────────────────────────────────────────────────────────────
        #
        # Standalone BO users have no linked employee — used for district
        # managers, auditors, and the wrapper's own bot user.

        banner("8. create_backoffice_user — standalone")
        bo_suffix = f"{random.randint(0, 0xFFFF):04X}"
        try:
            standalone = client.create_backoffice_user(
                username=f"demosoloS{bo_suffix}",
                email=f"wrapper-demo-solo-{bo_suffix}@example.invalid",
                first_name="WrapperDemo",
                last_name=f"Standalone{bo_suffix}",
                permission="Administrator",
            )
            print(f"  user_id:             {standalone.user_id}")
            print(f"  username:            {standalone.username}")
            print(f"  password:            {standalone.password}")
            print(f"  linked_employee_id:  {standalone.linked_employee_id}  (None = standalone)")
            print(f"  permission_applied:  {standalone.permission_applied}")
            for w in standalone.warnings:
                print(f"  warning:             {w}")
        except (DuplicateError, BackofficeServerError) as e:
            print(f"  standalone BO create failed: {e}")

        # ───────────────────────────────────────────────────────────────────
        #  disable_employee — cleanup
        # ───────────────────────────────────────────────────────────────────
        #
        # Clean up the two test employees we just created. disable_employee
        # uses the full-form round-trip (GET list → find ID → GET edit form →
        # POST update with isActive omitted → re-GET verify).

        banner("9. disable_employee — cleanup")
        for label, pos in [("a", pos_id), ("b", pos_id_b)]:
            try:
                disabled = client.disable_employee(pos_user_id=pos)
                print(
                    f"  disabled {label} (employee_id={disabled.employee_id}) at {disabled.disabled_at}"
                )
            except SonnysBackofficeError as e:
                print(f"  cleanup {label} failed: {e}")

        banner("Demo complete")
        print("  Remember: M1 BO user permission templates still need manual assignment.")
        print("  Open /user in Backoffice and click the shield icon on any new BO user.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
