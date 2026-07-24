"""Live-tenant smoke tests for SonnysBackofficeClient.

Run with:
    pytest -m integration

Write-mutating tests also need ``SONNYS_ALLOW_WRITES=1``.
"""

from __future__ import annotations

import contextlib
import random
from datetime import datetime
from decimal import Decimal

import pytest


@pytest.mark.integration
def test_list_sites_returns_non_empty(client):
    sites = client.list_sites()
    assert len(sites) > 0


@pytest.mark.integration
def test_list_departments_includes_greeter(client):
    depts = client.list_departments()
    names = [d.name for d in depts]
    assert "Greeter" in names


@pytest.mark.integration
def test_list_pos_permissions_includes_general_user(client):
    perms = client.list_permissions(scope="pos")
    names = [p.name for p in perms]
    assert "General User" in names


@pytest.mark.integration
def test_availability_helpers_work(client):
    # A wildly-out-of-range POS ID should not collide
    assert client.is_pos_user_id_available(99_000_000) is True


@pytest.mark.integration
def test_pos_user_id_exists_active_and_inactive(client):
    # POS User IDs are reserved even when the account is disabled, so both of
    # these existing records must report True; the unused id must report False.
    assert client.pos_user_id_exists(9048) is True  # inactive employee
    assert client.pos_user_id_exists(87151) is True  # active employee
    assert client.pos_user_id_exists(7868172) is False  # not used by anyone


@pytest.mark.integration
def test_search_employees_server_side_filter(client):
    # first_name filter returns matches across active AND inactive.
    trevons = client.search_employees(first_name="Trevon")
    names = {(e.first_name, e.last_name) for e in trevons}
    assert ("Trevon", "Roots") in names  # active
    assert ("Trevon", "Johnson") in names  # inactive
    # Filters AND-combine to narrow to a single person.
    roots = client.search_employees(first_name="Trevon", last_name="Roots")
    assert [e.pos_user_id for e in roots] == [87151]
    # POS User ID filter is exact; an unused id yields no rows.
    assert client.search_employees(pos_user_id=7868172) == []
    # The `active` argument filters the returned rows.
    assert all(e.is_active for e in client.search_employees(first_name="Trevon", active="active"))
    assert all(
        not e.is_active for e in client.search_employees(first_name="Trevon", active="inactive")
    )


@pytest.mark.integration
def test_find_employee_resolves_via_server_side_search(client):
    # find_employee now filters server-side by name, then applies exact matching.
    emp = client.find_employee(first_name="Trevon", last_name="Roots")
    assert emp.pos_user_id == 87151
    assert emp.is_active is True


@pytest.mark.integration
def test_create_and_disable_employee(tracked_client, unique_suffix, writes_allowed):
    """Create one throwaway employee, verify the result, then disable.

    Requires ``SONNYS_ALLOW_WRITES=1``. Uses a random 5-digit POS ID in a
    reserved test range to avoid colliding with real records.
    Tracks the POS ID with the session-scoped teardown fixture as a safety
    net in case the inline cleanup fails.
    """
    pos_id = random.randint(90_000, 99_999)
    while not tracked_client.is_pos_user_id_available(pos_id, refresh=True):
        pos_id = random.randint(90_000, 99_999)
    email = f"wrapper-integration-{unique_suffix}@example.invalid"
    first_site = tracked_client.list_sites()[0].name

    tracked_client.track(pos_id)
    created = None
    try:
        created = tracked_client.create_employee(
            first_name="WrapperIntegration",
            last_name=f"Test{unique_suffix}",
            phone="5555550001",
            email=email,
            pos_user_id=pos_id,
            wage_rate=Decimal("1.00"),
            start_date=datetime(2026, 1, 1),
            available_sites=[first_site],
            permission="General User",
        )
        assert created.pos_user_id == pos_id
        assert created.pos_pin is not None
        assert created.employee_id > 0
        assert created.permission_applied == "General User"
    finally:
        # Primary cleanup path — the tracked teardown is a safety net for
        # the case where this finally itself fails.
        with contextlib.suppress(Exception):
            tracked_client.disable_employee(pos_user_id=pos_id)
