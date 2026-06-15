"""Unit tests for name-based employee lookup (with phone disambiguation)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sonnys_backoffice import SonnysBackofficeClient
from sonnys_backoffice.employees import (
    match_employees_by_name,
    resolve_employee_by_name,
)
from sonnys_backoffice.exceptions import AmbiguousMatchError, NotFoundError
from sonnys_backoffice.models import EmployeeSummary


def _row(eid, pos, first, last, phone="6155551234", active=True) -> EmployeeSummary:
    return EmployeeSummary(
        employee_id=eid,
        pos_user_id=pos,
        first_name=first,
        last_name=last,
        phone=phone,
        is_active=active,
    )


# ── pure resolver ────────────────────────────────────────────────────────────


def test_single_name_match_returns_it():
    rows = [_row(1, 100, "Ada", "Lovelace"), _row(2, 200, "Grace", "Hopper")]
    emp = resolve_employee_by_name(rows, first_name="Ada", last_name="Lovelace")
    assert emp.pos_user_id == 100


def test_name_normalization_case_and_whitespace():
    rows = [_row(1, 100, "Ada", "Lovelace")]
    emp = resolve_employee_by_name(rows, first_name="  aDA ", last_name="LOVELACE  ")
    assert emp.pos_user_id == 100


def test_no_name_match_raises_not_found():
    rows = [_row(1, 100, "Ada", "Lovelace")]
    with pytest.raises(NotFoundError):
        resolve_employee_by_name(rows, first_name="Charles", last_name="Babbage")


def test_collision_narrowed_by_phone():
    rows = [
        _row(1, 100, "John", "Smith", phone="615-555-0001"),
        _row(2, 200, "John", "Smith", phone="615-555-0002"),
    ]
    emp = resolve_employee_by_name(
        rows, first_name="John", last_name="Smith", phone="(615) 555-0002"
    )
    assert emp.pos_user_id == 200


def test_collision_narrowed_by_phone_ignores_leading_country_code():
    rows = [
        _row(1, 100, "John", "Smith", phone="6155550001"),
        _row(2, 200, "John", "Smith", phone="6155550002"),
    ]
    emp = resolve_employee_by_name(
        rows, first_name="John", last_name="Smith", phone="+1 615 555 0002"
    )
    assert emp.pos_user_id == 200


def test_collision_no_phone_is_ambiguous():
    rows = [_row(1, 100, "John", "Smith"), _row(2, 200, "John", "Smith")]
    with pytest.raises(AmbiguousMatchError) as exc:
        resolve_employee_by_name(rows, first_name="John", last_name="Smith")
    msg = str(exc.value)
    assert "2 employees" in msg
    assert "100" in msg and "200" in msg


def test_collision_phone_narrows_to_none_is_ambiguous():
    rows = [
        _row(1, 100, "John", "Smith", phone="6155550001"),
        _row(2, 200, "John", "Smith", phone="6155550002"),
    ]
    with pytest.raises(AmbiguousMatchError):
        resolve_employee_by_name(rows, first_name="John", last_name="Smith", phone="6155559999")


def test_collision_phone_still_multiple_is_ambiguous():
    rows = [
        _row(1, 100, "John", "Smith", phone="6155550001"),
        _row(2, 200, "John", "Smith", phone="6155550001"),
    ]
    with pytest.raises(AmbiguousMatchError) as exc:
        resolve_employee_by_name(rows, first_name="John", last_name="Smith", phone="6155550001")
    assert "2 employees" in str(exc.value)


def test_match_employees_by_name_returns_all():
    rows = [
        _row(1, 100, "John", "Smith"),
        _row(2, 200, "john", "  smith "),
        _row(3, 300, "Jane", "Smith"),
    ]
    matches = match_employees_by_name(rows, first_name="John", last_name="Smith")
    assert {m.pos_user_id for m in matches} == {100, 200}


# ── client integration (active filtering via one roster GET) ─────────────────

_ROSTER = """
<table class="table-employees-list">
  <tr>
    <td class="employees-col-first-name">John</td>
    <td class="employees-col-last-name">Smith</td>
    <td class="employees-col-pos-user-id">100</td>
    <td class="employees-col-phone">6155550001</td>
    <td class="employees-col-active"><i class="fa fa-check"></i></td>
    <td><a href="/employee/edit/1">edit</a></td>
  </tr>
  <tr>
    <td class="employees-col-first-name">John</td>
    <td class="employees-col-last-name">Smith</td>
    <td class="employees-col-pos-user-id">200</td>
    <td class="employees-col-phone">6155550002</td>
    <td class="employees-col-active"><i class="fa fa-times"></i></td>
    <td><a href="/employee/edit/2">edit</a></td>
  </tr>
</table>
"""


def _client_with_roster() -> SonnysBackofficeClient:
    session = MagicMock()
    session.get.return_value = MagicMock(text=_ROSTER, status_code=200)
    with patch("sonnys_backoffice.client._BackofficeSession") as cls:
        cls.return_value = session
        return SonnysBackofficeClient(subdomain="washu", username="u", password="p")


def test_find_employee_active_default_picks_active_row():
    client = _client_with_roster()
    # Two Johns, but only the active one survives the default filter → unambiguous.
    emp = client.find_employee(first_name="John", last_name="Smith")
    assert emp.pos_user_id == 100
    assert emp.is_active is True


def test_find_employee_inactive_filter_picks_inactive_row():
    client = _client_with_roster()
    emp = client.find_employee(first_name="John", last_name="Smith", active="inactive")
    assert emp.pos_user_id == 200
    assert emp.is_active is False


def test_find_employee_all_needs_phone_to_disambiguate():
    client = _client_with_roster()
    with pytest.raises(AmbiguousMatchError):
        client.find_employee(first_name="John", last_name="Smith", active="all")
    emp = client.find_employee(
        first_name="John", last_name="Smith", phone="6155550002", active="all"
    )
    assert emp.pos_user_id == 200


def test_find_employees_returns_all_matches():
    client = _client_with_roster()
    rows = client.find_employees(first_name="John", last_name="Smith", active="all")
    assert {r.pos_user_id for r in rows} == {100, 200}
