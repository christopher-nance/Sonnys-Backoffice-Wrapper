from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from sonnys_backoffice.employees import EmployeeIndex, create_employee
from sonnys_backoffice.exceptions import DuplicateError
from sonnys_backoffice.models import (
    CreateEmployeeRequest,
    Department,
    EmployeeCreated,
    Permission,
    PermissionFieldMeta,
    Site,
)
from sonnys_backoffice.sites import SiteTree


def _flat_tree() -> SiteTree:
    return SiteTree(
        is_hierarchical=False,
        sites=[Site(id=17, name="Wash 37135")],
    )


def _depts() -> list[Department]:
    return [Department(id=3, name="Greeter"), Department(id=1, name="Cashier")]


def _pos_perms() -> list[Permission]:
    return [
        Permission(
            id=3,
            name="General User",
            scope="pos",
            grants=frozenset({22}),
        ),
        Permission(
            id=1,
            name="Manager",
            scope="pos",
            grants=frozenset({1, 2, 22}),
        ),
    ]


def _pos_schema() -> list[PermissionFieldMeta]:
    return [
        PermissionFieldMeta(id=1, label="Manager Approval", description="desc 1"),
        PermissionFieldMeta(id=2, label="Something", description="desc 2"),
        PermissionFieldMeta(id=22, label="General View", description="desc 22"),
    ]


def _make_mock_session(employee_id: int = 42) -> MagicMock:
    session = MagicMock()
    insert_resp = MagicMock()
    insert_resp.status_code = 302
    insert_resp.headers = {"Location": f"/employee/edit/{employee_id}"}
    insert_resp.url = ""
    insert_resp.text = ""

    perms_resp = MagicMock()
    perms_resp.status_code = 302
    perms_resp.headers = {}
    perms_resp.text = ""

    session.post.side_effect = [insert_resp, perms_resp]
    return session


def _valid_request(**overrides) -> CreateEmployeeRequest:
    base = dict(
        first_name="Jane",
        last_name="Doe",
        phone="6155551234",
        email="jane@example.com",
        pos_user_id=12345,
        pos_pin=54321,
        wage_rate=Decimal("15.00"),
        start_date=datetime(2026, 5, 1),
        available_sites=["Wash 37135"],
        permission="General User",
    )
    base.update(overrides)
    return CreateEmployeeRequest(**base)


def test_create_employee_happy_path_returns_result():
    session = _make_mock_session(employee_id=42)
    req = _valid_request()
    result = create_employee(
        session=session,
        request=req,
        site_tree=_flat_tree(),
        departments=_depts(),
        pos_permissions=_pos_perms(),
        pos_permission_schema=_pos_schema(),
    )
    assert isinstance(result, EmployeeCreated)
    assert result.employee_id == 42
    assert result.pos_user_id == 12345
    assert result.pos_pin == 54321
    assert result.permission_applied == "General User"
    assert result.wage_site == "Wash 37135"
    assert session.post.call_count == 2


def test_create_employee_hits_correct_urls():
    session = _make_mock_session(employee_id=42)
    req = _valid_request()
    create_employee(
        session=session,
        request=req,
        site_tree=_flat_tree(),
        departments=_depts(),
        pos_permissions=_pos_perms(),
        pos_permission_schema=_pos_schema(),
    )
    step1_call = session.post.call_args_list[0]
    step2_call = session.post.call_args_list[1]
    assert step1_call.args[0] == "/employee/insert"
    assert step2_call.args[0] == "/employee/permissions/update"


def test_create_employee_generates_pin_if_not_provided():
    session = _make_mock_session(employee_id=42)
    req = _valid_request(pos_pin=None)
    result = create_employee(
        session=session,
        request=req,
        site_tree=_flat_tree(),
        departments=_depts(),
        pos_permissions=_pos_perms(),
        pos_permission_schema=_pos_schema(),
    )
    assert isinstance(result.pos_pin, int)
    assert 10000 <= result.pos_pin <= 99999


def test_create_employee_falls_back_to_general_user_on_unknown_permission():
    session = _make_mock_session(employee_id=42)
    req = _valid_request(permission="NonExistentRole")
    result = create_employee(
        session=session,
        request=req,
        site_tree=_flat_tree(),
        departments=_depts(),
        pos_permissions=_pos_perms(),
        pos_permission_schema=_pos_schema(),
    )
    assert result.permission_applied == "General User"
    assert any("NonExistentRole" in w for w in result.warnings)


def test_create_employee_extracts_id_from_permissions_redirect():
    session = MagicMock()
    insert_resp = MagicMock()
    insert_resp.status_code = 302
    insert_resp.headers = {"Location": "/employee/permissions/99"}
    insert_resp.url = ""
    insert_resp.text = ""
    perms_resp = MagicMock()
    perms_resp.status_code = 302
    perms_resp.headers = {}
    perms_resp.text = ""
    session.post.side_effect = [insert_resp, perms_resp]

    req = _valid_request()
    result = create_employee(
        session=session,
        request=req,
        site_tree=_flat_tree(),
        departments=_depts(),
        pos_permissions=_pos_perms(),
        pos_permission_schema=_pos_schema(),
    )
    assert result.employee_id == 99


def test_create_employee_raises_duplicate_on_preflight_hit():
    session = _make_mock_session(employee_id=42)
    idx = EmployeeIndex(by_pos_user_id={12345: 1}, by_email={}, by_phone={})
    req = _valid_request(pos_user_id=12345)
    with pytest.raises(DuplicateError, match="pos_user_id=12345"):
        create_employee(
            session=session,
            request=req,
            site_tree=_flat_tree(),
            departments=_depts(),
            pos_permissions=_pos_perms(),
            pos_permission_schema=_pos_schema(),
            employee_index=idx,
        )
    # Uniqueness failure must short-circuit before any HTTP call
    assert session.post.call_count == 0


def test_create_employee_raises_on_already_exists_in_response_body():
    session = MagicMock()
    insert_resp = MagicMock()
    insert_resp.status_code = 200
    insert_resp.headers = {}
    insert_resp.url = ""
    insert_resp.text = "<html>That email already exists</html>"
    session.post.return_value = insert_resp
    session.post.side_effect = None

    req = _valid_request()
    with pytest.raises(DuplicateError):
        create_employee(
            session=session,
            request=req,
            site_tree=_flat_tree(),
            departments=_depts(),
            pos_permissions=_pos_perms(),
            pos_permission_schema=_pos_schema(),
        )
