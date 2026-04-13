from unittest.mock import MagicMock

import pytest

from sonnys_backoffice.bo_users import (
    create_linked_backoffice_user,
    create_standalone_backoffice_user,
)
from sonnys_backoffice.exceptions import BackofficeServerError, DuplicateError
from sonnys_backoffice.models import (
    BackofficeUserCreated,
    CreateBackofficeUserRequest,
    Permission,
    Site,
)
from sonnys_backoffice.sites import SiteTree


def _flat_tree() -> SiteTree:
    return SiteTree(is_hierarchical=False, sites=[Site(id=17, name="Wash 37135")])


def _bo_perms() -> list[Permission]:
    return [
        Permission(id=1, name="Administrator", scope="backoffice"),
        Permission(id=3, name="General User", scope="backoffice"),
    ]


def _insert_response(user_id: int = 99) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 302
    resp.headers = {"Location": f"/user/permissions/{user_id}?userIsNew=1"}
    resp.url = ""
    resp.text = ""
    return resp


def test_create_standalone_bo_user_returns_result():
    session = MagicMock()
    session.post.return_value = _insert_response(user_id=99)

    req = CreateBackofficeUserRequest(
        username="districtmgr",
        email="mgr@example.com",
        first_name="District",
        last_name="Manager",
        permission="Administrator",
    )
    result = create_standalone_backoffice_user(
        session=session,
        request=req,
        site_tree=_flat_tree(),
        bo_permissions=_bo_perms(),
    )
    assert isinstance(result, BackofficeUserCreated)
    assert result.user_id == 99
    assert result.linked_employee_id is None
    assert result.username == "districtmgr"
    assert len(result.password) == 12
    assert result.permission_applied == "Administrator"
    assert any("deferred to Milestone 2" in w for w in result.warnings)


def test_standalone_posts_to_user_insert_with_correct_fields():
    session = MagicMock()
    session.post.return_value = _insert_response(user_id=42)

    req = CreateBackofficeUserRequest(
        username="abcdef",
        email="abc@example.com",
        first_name="Abc",
        last_name="Def",
        permission="General User",
    )
    create_standalone_backoffice_user(
        session=session,
        request=req,
        site_tree=_flat_tree(),
        bo_permissions=_bo_perms(),
    )
    session.post.assert_called_once()
    call = session.post.call_args
    assert call.args[0] == "/user/insert"
    data = call.kwargs["data"]
    assert data["employee[isOnSiteEmployee]"] == "0"
    assert data["employee[firstName]"] == "Abc"
    assert data["employee[lastName]"] == "Def"
    assert data["employee[email]"] == "abc@example.com"
    assert data["user[username]"] == "abcdef"
    assert data["user[password]"] == data["user[confirmPassword]"]


def test_standalone_does_not_post_to_permissions_endpoint():
    session = MagicMock()
    session.post.return_value = _insert_response(user_id=1)

    req = CreateBackofficeUserRequest(
        username="abcdef",
        email="abc@example.com",
        first_name="A",
        last_name="B",
        permission="Administrator",
    )
    create_standalone_backoffice_user(
        session=session,
        request=req,
        site_tree=_flat_tree(),
        bo_permissions=_bo_perms(),
    )
    assert session.post.call_count == 1  # no /user/{id}/permissions call


def test_standalone_respects_provided_password():
    session = MagicMock()
    session.post.return_value = _insert_response()

    req = CreateBackofficeUserRequest(
        username="abcdef",
        email="abc@example.com",
        first_name="A",
        last_name="B",
        permission="Administrator",
        password="MyPreset1!",
    )
    result = create_standalone_backoffice_user(
        session=session,
        request=req,
        site_tree=_flat_tree(),
        bo_permissions=_bo_perms(),
    )
    assert result.password == "MyPreset1!"


def test_standalone_falls_back_on_unknown_permission_name():
    session = MagicMock()
    session.post.return_value = _insert_response()

    req = CreateBackofficeUserRequest(
        username="abcdef",
        email="abc@example.com",
        first_name="A",
        last_name="B",
        permission="NotAReal",
    )
    result = create_standalone_backoffice_user(
        session=session,
        request=req,
        site_tree=_flat_tree(),
        bo_permissions=_bo_perms(),
    )
    assert result.permission_applied == "General User"
    assert any("NotAReal" in w for w in result.warnings)


def test_standalone_raises_duplicate_on_existing_username():
    session = MagicMock()
    dup_resp = MagicMock()
    dup_resp.status_code = 200
    dup_resp.headers = {}
    dup_resp.url = ""
    dup_resp.text = "<html>That username already taken</html>"
    session.post.return_value = dup_resp

    req = CreateBackofficeUserRequest(
        username="abcdef",
        email="abc@example.com",
        first_name="A",
        last_name="B",
        permission="Administrator",
    )
    with pytest.raises(DuplicateError):
        create_standalone_backoffice_user(
            session=session,
            request=req,
            site_tree=_flat_tree(),
            bo_permissions=_bo_perms(),
        )


def test_linked_raises_if_employee_inactive():
    session = MagicMock()
    err_resp = MagicMock()
    err_resp.status_code = 200
    err_resp.headers = {}
    err_resp.url = ""
    err_resp.text = (
        "<html>please make sure that the related employee is active and try again</html>"
    )
    session.post.return_value = err_resp

    perm = Permission(id=1, name="Administrator", scope="backoffice")
    with pytest.raises(BackofficeServerError, match="active"):
        create_linked_backoffice_user(
            session=session,
            username="linked1",
            email="linked@example.com",
            password=None,
            linked_employee_id=42,
            permission=perm,
            site_tree=_flat_tree(),
            available_sites="all",
        )
