"""Live-tenant smoke tests for SonnysBackofficeClient.

Run with:
    pytest -m integration

Write-mutating tests also need ``SONNYS_ALLOW_WRITES=1``.
"""
from __future__ import annotations

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
def test_create_and_disable_employee(client, unique_suffix, writes_allowed):
    """Create one throwaway employee, verify the result, then disable.

    Requires ``SONNYS_ALLOW_WRITES=1``. Uses a random 5-digit POS ID in a
    reserved test range to avoid colliding with real records.
    """
    pos_id = random.randint(90_000, 99_999)
    while not client.is_pos_user_id_available(pos_id, refresh=True):
        pos_id = random.randint(90_000, 99_999)
    email = f"wrapper-integration-{unique_suffix}@example.invalid"
    first_site = client.list_sites()[0].name

    created = None
    try:
        created = client.create_employee(
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
        # Always attempt cleanup even if the assertions failed partway
        try:
            client.disable_employee(pos_user_id=pos_id)
        except Exception:
            pass
