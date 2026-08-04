from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from sonnys_backoffice.employees import EmployeeIndex, create_employee
from sonnys_backoffice.exceptions import BackofficeServerError, DuplicateError
from sonnys_backoffice.models import (
    CreateEmployeeRequest,
    Department,
    District,
    EmployeeCreated,
    Permission,
    PermissionFieldMeta,
    Region,
    Site,
)
from sonnys_backoffice.sites import SiteTree


def _flat_tree() -> SiteTree:
    return SiteTree(
        is_hierarchical=False,
        sites=[Site(id=17, name="Wash 37135")],
    )


def _hierarchical_tree() -> SiteTree:
    return SiteTree(
        is_hierarchical=True,
        regions=[Region(id=1, name="Region")],
        districts=[District(id=1, name="District", region_id=1)],
        sites=[
            Site(id=17, name="Wash 37135", district_id=1, region_id=1),
            Site(id=18, name="Wash 37055", district_id=1, region_id=1),
        ],
    )


def _hierarchical_readback(*, available_ids: set[int] | str) -> str:
    all_checked = " checked" if available_ids == "all" else ""
    site_controls: list[str] = []
    for site_id in (17, 18):
        is_available = available_ids == "all" or site_id in available_ids
        checked = "" if is_available else " checked"
        disabled = "" if is_available else " disabled"
        site_controls.extend(
            [
                f'<input type="checkbox" name="employee[sites][{site_id}][isAvailable]"{checked}>',
                f'<input type="hidden" name="employee[sites][{site_id}][siteId]" '
                f'value="{site_id}"{disabled}>',
            ]
        )
    return (
        '<form action="/employee/update">'
        f'<input type="checkbox" name="employee[isAllRegionsAllowed]"{all_checked}>'
        + "".join(site_controls)
        + "</form>"
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


def test_create_employee_raises_on_unknown_permission():
    session = _make_mock_session(employee_id=42)
    req = _valid_request(permission="NonExistentRole")
    with pytest.raises(Exception, match="NonExistentRole"):
        create_employee(
            session=session,
            request=req,
            site_tree=_flat_tree(),
            departments=_depts(),
            pos_permissions=_pos_perms(),
            pos_permission_schema=_pos_schema(),
        )


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


def test_create_employee_with_backoffice_user_link():
    session = MagicMock()
    insert_resp = MagicMock()
    insert_resp.status_code = 302
    insert_resp.headers = {"Location": "/employee/edit/42"}
    insert_resp.url = ""
    insert_resp.text = ""
    perms_resp = MagicMock()
    perms_resp.status_code = 302
    perms_resp.headers = {}
    perms_resp.text = ""
    bo_insert_resp = MagicMock()
    bo_insert_resp.status_code = 302
    bo_insert_resp.headers = {"Location": "/user/permissions/99?userIsNew=1"}
    bo_insert_resp.url = ""
    bo_insert_resp.text = ""
    session.post.side_effect = [insert_resp, perms_resp, bo_insert_resp]

    req = _valid_request(
        requires_backoffice=True,
        backoffice_username="janedoe",
    )
    bo_perms = [Permission(id=3, name="General User", scope="backoffice")]
    result = create_employee(
        session=session,
        request=req,
        site_tree=_flat_tree(),
        departments=_depts(),
        pos_permissions=_pos_perms(),
        pos_permission_schema=_pos_schema(),
        bo_permissions=bo_perms,
    )
    assert result.backoffice_user_id == 99
    assert result.backoffice_username == "janedoe"
    assert result.backoffice_password is not None
    assert len(result.backoffice_password) == 12
    assert session.post.call_count == 3
    assert any("deferred to Milestone 2" in w for w in result.warnings)


def test_create_employee_bo_path_posts_to_user_insert():
    session = MagicMock()
    session.post.side_effect = [
        MagicMock(status_code=302, headers={"Location": "/employee/edit/42"}, url="", text=""),
        MagicMock(status_code=302, headers={}, url="", text=""),
        MagicMock(
            status_code=302,
            headers={"Location": "/user/permissions/99"},
            url="",
            text="",
        ),
    ]
    req = _valid_request(
        requires_backoffice=True,
        backoffice_username="janedoe",
    )
    create_employee(
        session=session,
        request=req,
        site_tree=_flat_tree(),
        departments=_depts(),
        pos_permissions=_pos_perms(),
        pos_permission_schema=_pos_schema(),
        bo_permissions=[Permission(id=3, name="General User", scope="backoffice")],
    )
    third_call = session.post.call_args_list[2]
    assert third_call.args[0] == "/user/insert"
    bo_data = third_call.kwargs["data"]
    assert bo_data["user[username]"] == "janedoe"
    assert bo_data["user[employeeId]"] == "42"
    assert bo_data["employee[isOnSiteEmployee]"] == "1"
    assert bo_data["user[password]"] == bo_data["user[confirmPassword]"]


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


def test_create_employee_verifies_hierarchical_sites_before_permissions():
    session = _make_mock_session(employee_id=42)
    session.get.return_value = MagicMock(
        status_code=200,
        headers={},
        text=_hierarchical_readback(available_ids={17}),
    )

    result = create_employee(
        session=session,
        request=_valid_request(available_sites=["Wash 37135"]),
        site_tree=_hierarchical_tree(),
        departments=_depts(),
        pos_permissions=_pos_perms(),
        pos_permission_schema=_pos_schema(),
    )

    assert result.sites_granted == ["Wash 37135"]
    session.get.assert_called_once_with("/employee/edit/42")
    assert session.post.call_args_list[1].args[0] == "/employee/permissions/update"


def test_create_employee_skips_permissions_when_site_readback_mismatches():
    session = _make_mock_session(employee_id=42)
    session.get.return_value = MagicMock(
        status_code=200,
        headers={},
        text=_hierarchical_readback(available_ids="all"),
    )

    with pytest.raises(BackofficeServerError, match="site access verification failed"):
        create_employee(
            session=session,
            request=_valid_request(available_sites=["Wash 37135"]),
            site_tree=_hierarchical_tree(),
            departments=_depts(),
            pos_permissions=_pos_perms(),
            pos_permission_schema=_pos_schema(),
        )

    assert session.post.call_count == 1
    assert all(
        call.args[0] != "/employee/permissions/update" for call in session.post.call_args_list
    )


def test_create_employee_normalizes_all_and_explicit_full_site_sets():
    session = _make_mock_session(employee_id=42)
    session.get.return_value = MagicMock(
        status_code=200,
        headers={},
        text=_hierarchical_readback(available_ids="all"),
    )

    result = create_employee(
        session=session,
        request=_valid_request(available_sites=["Wash 37135", "Wash 37055"]),
        site_tree=_hierarchical_tree(),
        departments=_depts(),
        pos_permissions=_pos_perms(),
        pos_permission_schema=_pos_schema(),
    )

    assert set(result.sites_granted) == {"Wash 37135", "Wash 37055"}
    session.get.assert_called_once_with("/employee/edit/42")
    assert session.post.call_count == 2
