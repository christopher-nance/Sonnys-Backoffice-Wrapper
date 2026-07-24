from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sonnys_backoffice import SonnysBackofficeClient
from sonnys_backoffice.exceptions import NotFoundError

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html"


def _make_client_with_mock_session(mock_session: MagicMock) -> SonnysBackofficeClient:
    with patch("sonnys_backoffice.client._BackofficeSession") as cls:
        cls.return_value = mock_session
        return SonnysBackofficeClient(subdomain="washu", username="u", password="p")


def test_client_lazy_login():
    client = SonnysBackofficeClient(subdomain="washu", username="u", password="p")
    assert client._session._logged_in is False


def test_client_context_manager_closes_session():
    mock_session = MagicMock()
    with patch("sonnys_backoffice.client._BackofficeSession") as cls:
        cls.return_value = mock_session
        with SonnysBackofficeClient(subdomain="washu", username="u", password="p"):
            pass
        mock_session.close.assert_called_once()


def test_list_sites_caches_and_refresh_refetches():
    mock_session = MagicMock()
    employee_create_html = (FIXTURES / "employee_create.html").read_text(encoding="utf-8")
    resp = MagicMock(text=employee_create_html, status_code=200)
    mock_session.get.return_value = resp

    client = _make_client_with_mock_session(mock_session)
    sites1 = client.list_sites()
    sites2 = client.list_sites()
    assert sites1 == sites2
    assert mock_session.get.call_count == 1

    client.list_sites(refresh=True)
    assert mock_session.get.call_count == 2


def test_list_departments_parses_from_employee_create():
    mock_session = MagicMock()
    html = (FIXTURES / "employee_create.html").read_text(encoding="utf-8")
    mock_session.get.return_value = MagicMock(text=html, status_code=200)

    client = _make_client_with_mock_session(mock_session)
    depts = client.list_departments()
    names = {d.name for d in depts}
    assert {"Cashier", "Greeter", "Line", "Management"}.issubset(names)


def test_list_permissions_pos_fetches_existing_employee_permissions_page():
    mock_session = MagicMock()
    employee_list_html = (FIXTURES / "employee_list.html").read_text(encoding="utf-8")
    perms_html = (FIXTURES / "employee_permissions_54.html").read_text(encoding="utf-8")

    def get_side_effect(path, *args, **kwargs):
        if path.startswith("/employee?") or path == "/employee":
            return MagicMock(text=employee_list_html, status_code=200)
        if path.startswith("/employee/permissions/"):
            return MagicMock(text=perms_html, status_code=200)
        raise AssertionError(f"unexpected GET: {path}")

    mock_session.get.side_effect = get_side_effect

    client = _make_client_with_mock_session(mock_session)
    perms = client.list_permissions(scope="pos")
    names = {p.name for p in perms}
    assert "General User" in names
    assert "Manager" in names
    assert client._pos_permission_schema is not None
    assert len(client._pos_permission_schema) > 0


def test_list_permissions_bo_fetches_existing_user_permissions_page():
    mock_session = MagicMock()
    user_list_html = '<html><a href="/user/permissions/2944451">edit</a></html>'
    perms_html = (FIXTURES / "w45f_user_permissions_2944451.html").read_text(encoding="utf-8")

    def get_side_effect(path, *args, **kwargs):
        if path == "/user":
            return MagicMock(text=user_list_html, status_code=200)
        if path.startswith("/user/permissions/"):
            return MagicMock(text=perms_html, status_code=200)
        raise AssertionError(f"unexpected GET: {path}")

    mock_session.get.side_effect = get_side_effect

    client = _make_client_with_mock_session(mock_session)
    perms = client.list_permissions(scope="backoffice")
    names = {p.name for p in perms}
    assert "Administrator" in names
    assert all(p.scope == "backoffice" for p in perms)


def test_availability_helpers_use_employee_index():
    mock_session = MagicMock()
    employee_list_html = (FIXTURES / "employee_list.html").read_text(encoding="utf-8")
    user_create_html = (FIXTURES / "user_create.html").read_text(encoding="utf-8")

    def get_side_effect(path, *args, **kwargs):
        if path.startswith("/employee?") or path == "/employee":
            return MagicMock(text=employee_list_html, status_code=200)
        if path == "/user/create":
            return MagicMock(text=user_create_html, status_code=200)
        raise AssertionError(f"unexpected GET: {path}")

    mock_session.get.side_effect = get_side_effect

    client = _make_client_with_mock_session(mock_session)
    # aaliyah roylance: pos 7217, phone 702-845-6915, email aaliyahroylance9@gmail.com
    assert client.is_pos_user_id_available(7217) is False
    assert client.is_pos_user_id_available(99999999) is True

    assert client.is_email_available("AALIYAHROYLANCE9@gmail.com") is False
    assert client.is_email_available("nobody@nowhere.invalid") is True

    assert client.is_phone_available("(702) 845-6915") is False
    assert client.is_phone_available("5555550000") is True


def test_availability_check_caches_employee_index():
    mock_session = MagicMock()
    employee_list_html = (FIXTURES / "employee_list.html").read_text(encoding="utf-8")
    user_create_html = (FIXTURES / "user_create.html").read_text(encoding="utf-8")
    get_calls: list[str] = []

    def get_side_effect(path, *args, **kwargs):
        get_calls.append(path)
        if path.startswith("/employee?") or path == "/employee":
            return MagicMock(text=employee_list_html, status_code=200)
        if path == "/user/create":
            return MagicMock(text=user_create_html, status_code=200)
        raise AssertionError(f"unexpected GET: {path}")

    mock_session.get.side_effect = get_side_effect

    client = _make_client_with_mock_session(mock_session)
    # email + phone share the cached index: built once (roster + /user/create),
    # reused thereafter. (is_pos_user_id_available no longer uses the index — it
    # runs a live targeted search — so it is excluded from this caching check.)
    client.is_email_available("a@b.com")
    client.is_phone_available("1234567890")
    assert len(get_calls) == 2


def test_is_pos_user_id_available_uses_targeted_search():
    mock_session = MagicMock()
    employee_list_html = (FIXTURES / "employee_list.html").read_text(encoding="utf-8")
    requested: list[str] = []

    def get_side_effect(path, *args, **kwargs):
        requested.append(path)
        return MagicMock(text=employee_list_html, status_code=200)

    mock_session.get.side_effect = get_side_effect
    client = _make_client_with_mock_session(mock_session)

    # 7217 is present in the fixture; 99999999 is not.
    assert client.is_pos_user_id_available(7217) is False
    assert client.is_pos_user_id_available(99999999) is True
    # Live targeted posUserId search — never builds the /user/create-backed index.
    assert requested and all(p.startswith("/employee?") and "posUserId=" in p for p in requested)
    assert not any(p == "/user/create" for p in requested)


def test_pos_user_id_exists_targeted_search():
    mock_session = MagicMock()
    employee_list_html = (FIXTURES / "employee_list.html").read_text(encoding="utf-8")
    requested: list[str] = []

    def get_side_effect(path, *args, **kwargs):
        requested.append(path)
        if path.startswith("/employee?"):
            return MagicMock(text=employee_list_html, status_code=200)
        raise AssertionError(f"unexpected GET: {path}")

    mock_session.get.side_effect = get_side_effect
    client = _make_client_with_mock_session(mock_session)

    # 7217 is present in the roster fixture; 99999999 is not — exact POS-ID match
    # (correct even when the server ignores the filter and returns the roster).
    assert client.pos_user_id_exists(7217) is True
    assert client.pos_user_id_exists(99999999) is False

    # Every call is a fresh targeted search (no /user/create index build), asking
    # the server to filter by posUserId across active AND inactive rows.
    assert all(p.startswith("/employee?") for p in requested)
    assert any("posUserId=7217" in p and "active=all" in p for p in requested)


def test_pos_user_id_exists_false_on_empty_result():
    mock_session = MagicMock()
    # Empty search result (no employees table) → no rows → not in use.
    mock_session.get.return_value = MagicMock(
        text="<html><body>No Employees found based on this search criteria.</body></html>",
        status_code=200,
    )
    client = _make_client_with_mock_session(mock_session)
    assert client.pos_user_id_exists(7868172) is False


def test_search_employees_builds_targeted_path_and_filters_active():
    mock_session = MagicMock()
    employee_list_html = (FIXTURES / "employee_list.html").read_text(encoding="utf-8")
    requested: list[str] = []

    def get_side_effect(path, *args, **kwargs):
        requested.append(path)
        return MagicMock(text=employee_list_html, status_code=200)

    mock_session.get.side_effect = get_side_effect
    client = _make_client_with_mock_session(mock_session)

    rows = client.search_employees(first_name="Aaliyah", last_name="Roylance")
    # A single targeted query carrying the name filters + active=all — no /user/create.
    assert len(requested) == 1
    assert requested[0].startswith("/employee?")
    assert "first_name=Aaliyah" in requested[0]
    assert "last_name=Roylance" in requested[0]
    assert "active=all" in requested[0]
    assert any(r.pos_user_id == 7217 for r in rows)

    # The `active` argument filters the returned rows (fixture is all-active).
    assert len(client.search_employees(pos_user_id=7217, active="active")) > 0
    assert client.search_employees(pos_user_id=7217, active="inactive") == []


def test_find_employee_uses_server_side_name_search():
    mock_session = MagicMock()
    employee_list_html = (FIXTURES / "employee_list.html").read_text(encoding="utf-8")
    requested: list[str] = []

    def get_side_effect(path, *args, **kwargs):
        requested.append(path)
        return MagicMock(text=employee_list_html, status_code=200)

    mock_session.get.side_effect = get_side_effect
    client = _make_client_with_mock_session(mock_session)

    emp = client.find_employee(first_name="Aaliyah", last_name="Roylance")
    assert emp.pos_user_id == 7217
    # Filtered server-side by name; never pulls the full roster.
    assert any("first_name=Aaliyah" in p and "last_name=Roylance" in p for p in requested)
    assert not any(p == "/employee?limit=10000&active=all" for p in requested)


def test_resolve_employee_id_by_pos_uses_targeted_search():
    mock_session = MagicMock()
    employee_list_html = (FIXTURES / "employee_list.html").read_text(encoding="utf-8")
    requested: list[str] = []

    def get_side_effect(path, *args, **kwargs):
        requested.append(path)
        return MagicMock(text=employee_list_html, status_code=200)

    mock_session.get.side_effect = get_side_effect
    client = _make_client_with_mock_session(mock_session)

    # aaliyah roylance = emp 54, pos 7217
    assert client._resolve_employee_id(pos_user_id=7217, email=None) == 54
    # Targeted posUserId search — not the full roster, and no /user/create build.
    assert any("posUserId=7217" in p for p in requested)
    assert not any(p == "/employee?limit=10000&active=all" for p in requested)
    assert not any(p == "/user/create" for p in requested)


def test_disable_employee_invalidates_employee_index():
    mock_session = MagicMock()
    # Build index then disable; second call should re-fetch
    employee_list_html = (FIXTURES / "employee_list.html").read_text(encoding="utf-8")
    user_create_html = (FIXTURES / "user_create.html").read_text(encoding="utf-8")
    edit_html = (FIXTURES / "e2e_employee_edit_486_before_disable.html").read_text(encoding="utf-8")
    after_html = (FIXTURES / "e2e_employee_edit_486_after_disable.html").read_text(encoding="utf-8")

    # aaliyah roylance = emp 54, pos 7217
    def get_side_effect(path, *args, **kwargs):
        if path.startswith("/employee?") or path == "/employee":
            return MagicMock(text=employee_list_html, status_code=200, headers={})
        if path == "/user/create":
            return MagicMock(text=user_create_html, status_code=200, headers={})
        if path.startswith("/employee/edit/"):
            # Two calls: pre and verify. First call return "before", second call return "after"
            if get_side_effect.verify_call_count == 0:
                get_side_effect.verify_call_count += 1
                return MagicMock(text=edit_html, status_code=200, headers={})
            return MagicMock(text=after_html, status_code=200, headers={})
        raise AssertionError(f"unexpected GET: {path}")

    get_side_effect.verify_call_count = 0
    mock_session.get.side_effect = get_side_effect
    mock_session.post.return_value = MagicMock(
        status_code=302, text="", headers={"Location": "/employee"}
    )

    client = _make_client_with_mock_session(mock_session)
    # Prime the cache
    assert client.is_pos_user_id_available(7217) is False
    # Disable an employee — should clear the index
    # Note: the disable flow re-lookups via GET /employee?limit=10000&active=all (the list)
    # and since 7217 is in that list we can disable it
    import sonnys_backoffice.client as client_module

    with patch.object(client_module, "_disable_employee") as mocked:
        from sonnys_backoffice.models import EmployeeDisabled

        mocked.return_value = EmployeeDisabled(
            employee_id=54,
            pos_user_id=7217,
            email=None,
            disabled_at=datetime.now(),
        )
        client.disable_employee(pos_user_id=7217)
    assert client._employee_index is None
    assert client._employee_list_html is None


def test_create_employee_raises_not_found_on_linked_bo_lookup_miss():
    """Linked-mode BO user creation requires an existing employee in the index."""
    mock_session = MagicMock()
    employee_list_html = (FIXTURES / "employee_list.html").read_text(encoding="utf-8")
    user_create_html = (FIXTURES / "user_create.html").read_text(encoding="utf-8")
    user_list_html = '<html><a href="/user/permissions/2944451">e</a></html>'
    bo_perms_html = (FIXTURES / "w45f_user_permissions_2944451.html").read_text(encoding="utf-8")
    emp_create_html = (FIXTURES / "employee_create.html").read_text(encoding="utf-8")

    def get_side_effect(path, *args, **kwargs):
        if path == "/employee/create":
            return MagicMock(text=emp_create_html, status_code=200)
        if path == "/user":
            return MagicMock(text=user_list_html, status_code=200)
        if path.startswith("/user/permissions/"):
            return MagicMock(text=bo_perms_html, status_code=200)
        if path.startswith("/employee?") or path == "/employee":
            return MagicMock(text=employee_list_html, status_code=200)
        if path == "/user/create":
            return MagicMock(text=user_create_html, status_code=200)
        raise AssertionError(f"unexpected GET: {path}")

    mock_session.get.side_effect = get_side_effect

    client = _make_client_with_mock_session(mock_session)
    with pytest.raises(NotFoundError, match="99999999"):
        client.create_backoffice_user(
            username="linkedguy",
            email="lg@example.com",
            permission="Administrator",
            link_to_employee_pos_user_id="99999999",
        )
