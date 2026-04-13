from datetime import datetime

from sonnys_backoffice.models import (
    BackofficeUserCreated,
    Department,
    EmployeeCreated,
    EmployeeDisabled,
    Permission,
    Region,
    Site,
)


def test_employee_created_round_trips():
    r = EmployeeCreated(
        employee_id=42,
        pos_user_id=12345,
        pos_pin=54321,
        first_name="Jane",
        last_name="Doe",
        email="jane@example.com",
        permission_applied="General User",
        sites_granted=["Nolensville"],
        departments=["Greeter"],
        wage_site="Nolensville",
    )
    assert r.warnings == []
    d = r.model_dump()
    assert d["pos_pin"] == 54321


def test_employee_created_with_backoffice():
    r = EmployeeCreated(
        employee_id=42,
        pos_user_id=12345,
        pos_pin=54321,
        first_name="Jane",
        last_name="Doe",
        email="jane@example.com",
        backoffice_user_id=99,
        backoffice_username="janedoe",
        backoffice_password="SecretPW1!",
        permission_applied="Administrator",
        sites_granted=["Nolensville"],
        departments=["Greeter"],
        wage_site="Nolensville",
        warnings=["permission 'Admin' not found, fell back to 'Administrator'"],
    )
    assert r.backoffice_user_id == 99
    assert len(r.warnings) == 1


def test_bo_user_created():
    r = BackofficeUserCreated(
        user_id=99,
        username="janedoe",
        password="SecretPW1!",
        email="jane@example.com",
        permission_applied="Administrator",
        sites_granted=["Nolensville"],
    )
    assert r.linked_employee_id is None


def test_employee_disabled():
    r = EmployeeDisabled(
        employee_id=42,
        pos_user_id=12345,
        email="jane@example.com",
        disabled_at=datetime(2026, 4, 13),
    )
    assert r.pos_user_id == 12345


def test_domain_models():
    site = Site(id=17, name="Wash 37135", district_id=1, region_id=1)
    assert site.name == "Wash 37135"

    dept = Department(id=5, name="Greeter")
    assert dept.name == "Greeter"

    perm = Permission(id=3, name="Administrator", scope="pos")
    assert perm.scope == "pos"

    region = Region(id=2, name="WashU Illinois")
    assert region.name == "WashU Illinois"
