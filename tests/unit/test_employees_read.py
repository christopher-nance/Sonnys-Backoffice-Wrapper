"""Unit tests for the read-surface parsers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sonnys_backoffice.employees import (
    parse_employee_permission,
    parse_employee_profile,
    parse_employee_summaries,
    parse_wage_history,
)
from sonnys_backoffice.models import Department, Permission, Site
from sonnys_backoffice.sites import SiteTree


def _tree() -> SiteTree:
    return SiteTree(
        is_hierarchical=True,
        sites=[
            Site(id=1, name="WashU Fiesta"),
            Site(id=4, name="WashU Niles"),
            Site(id=17, name="Wash 37135"),
        ],
    )


# ── roster ───────────────────────────────────────────────────────────────────

_ROSTER = """
<table class="table-employees-list">
  <tr>
    <td class="employees-col-first-name">Ada</td>
    <td class="employees-col-last-name">Lovelace</td>
    <td class="employees-col-pos-user-id">12345</td>
    <td class="employees-col-phone">(615) 555-1234</td>
    <td class="employees-col-active"><i class="fa fa-check"></i></td>
    <td><a href="/employee/edit/501">edit</a></td>
  </tr>
  <tr>
    <td class="employees-col-first-name">Grace</td>
    <td class="employees-col-last-name">Hopper</td>
    <td class="employees-col-pos-user-id">67890</td>
    <td class="employees-col-phone">6155559999</td>
    <td class="employees-col-active"><i class="fa fa-times"></i></td>
    <td><a href="/employee/edit/502">edit</a></td>
  </tr>
</table>
"""


def test_parse_employee_summaries():
    rows = parse_employee_summaries(_ROSTER)
    assert len(rows) == 2
    ada = rows[0]
    assert ada.employee_id == 501
    assert ada.pos_user_id == 12345
    assert ada.first_name == "Ada" and ada.last_name == "Lovelace"
    assert ada.phone == "6155551234"
    assert ada.is_active is True
    assert rows[1].is_active is False


# ── profile ──────────────────────────────────────────────────────────────────

_EDIT = """
<form action="/employee/update">
  <input name="employee[id]" value="501">
  <input name="posCredential[POSLoginID]" value="12345">
  <input name="employee[firstName]" value="Ada">
  <input name="employee[lastName]" value="Lovelace">
  <input name="employee[email]" value="ada@example.com">
  <input name="employee[phone]" value="6155551234">
  <input name="employee[adpEmployeeId]" value="ADP-9">
  <input name="employee[emergencyContactName]" value="Charles">
  <input name="employee[emergencyContactPhone]" value="6155550000">
  <input name="employee[startDate]" type="text" data-value="06/15/2026">
  <input type="checkbox" name="employee[isActive]" checked>
  <select name="employee[departments][]" multiple>
    <option value="1" selected>Cashier</option>
    <option value="2">Line</option>
    <option value="3" selected>Greeter</option>
  </select>
  <input type="checkbox" name="employee[isAllRegionsAllowed]">
  <input type="checkbox" name="employee[sites][1][isAvailable]">
  <input name="employee[sites][1][siteId]" value="1">
  <input type="checkbox" name="employee[sites][4][isAvailable]">
  <input name="employee[sites][4][siteId]" value="4">
  <input type="checkbox" name="employee[sites][17][isAvailable]" checked>
  <input name="employee[sites][17][siteId]" value="17" disabled>
</form>
"""

_DEPTS = [
    Department(id=1, name="Cashier"),
    Department(id=2, name="Line"),
    Department(id=3, name="Greeter"),
]


def test_parse_employee_profile():
    p = parse_employee_profile(_EDIT, site_tree=_tree(), departments=_DEPTS)
    assert p.employee_id == 501
    assert p.pos_user_id == 12345
    assert p.first_name == "Ada" and p.last_name == "Lovelace"
    assert p.email == "ada@example.com"
    assert p.phone == "6155551234"
    assert p.adp_employee_id == "ADP-9"
    assert p.emergency_contact_name == "Charles"
    assert p.emergency_contact_phone == "6155550000"
    assert p.start_date == date(2026, 6, 15)
    assert p.is_active is True
    assert sorted(p.departments) == ["Cashier", "Greeter"]
    assert p.available_sites == ["WashU Fiesta", "WashU Niles"]


def test_parse_employee_profile_all_regions():
    edit = _EDIT.replace(
        '<input type="checkbox" name="employee[isAllRegionsAllowed]">',
        '<input type="checkbox" name="employee[isAllRegionsAllowed]" checked>',
    )
    p = parse_employee_profile(edit, site_tree=_tree(), departments=_DEPTS)
    assert p.available_sites == "all"


# ── compensation ─────────────────────────────────────────────────────────────

_COMP = """
<table class="table-employee-compensation-history"><tbody>
  <tr>
    <td class="employee-compensation-col-wage-type">Hourly</td>
    <td class="employee-compensation-col-wage">$17.25/hr</td>
    <td class="employee-compensation-col-overtime-eligible"><i class="fa fa-check"></i></td>
    <td class="employee-compensation-col-overtime-rate">$25.88/hr</td>
    <td class="employee-compensation-col-effective-date">06/16/2026</td>
    <td class="employee-compensation-col-end-date"></td>
  </tr>
  <tr>
    <td class="employee-compensation-col-wage-type">Hourly</td>
    <td class="employee-compensation-col-wage">$14.00/hr</td>
    <td class="employee-compensation-col-overtime-eligible"><i class="fa fa-check"></i></td>
    <td class="employee-compensation-col-overtime-rate">$21.00/hr</td>
    <td class="employee-compensation-col-effective-date">06/15/2026</td>
    <td class="employee-compensation-col-end-date">06/16/2026</td>
  </tr>
</tbody></table>
"""


def test_parse_wage_history():
    comp = parse_wage_history(_COMP)
    assert len(comp.history) == 2
    assert comp.current is not None
    assert comp.current.rate == Decimal("17.25")
    assert comp.current.overtime_rate == Decimal("25.88")
    assert comp.current.overtime_eligible is True
    assert comp.current.effective_date == date(2026, 6, 16)
    assert comp.current.end_date is None
    ended = comp.history[1]
    assert ended.rate == Decimal("14.00")
    assert ended.is_current is False
    assert ended.end_date == date(2026, 6, 16)


# ── permission ───────────────────────────────────────────────────────────────

_PERM = """
<form>
  <input type="checkbox" name="permissions[10][hasGrantAccess]" checked>
  <input type="checkbox" name="permissions[11][hasGrantAccess]" checked>
  <input type="checkbox" name="permissions[12][hasGrantAccess]" checked>
  <input type="checkbox" name="permissions[13][hasGrantAccess]">
  <input type="checkbox" name="permissions[11][requiresOverride]" checked>
</form>
"""

_POS_PERMS = [
    Permission(id=1, name="Manager", scope="pos", grants=frozenset({10, 11, 12})),
    Permission(id=3, name="General User", scope="pos", grants=frozenset({10})),
]


def test_parse_employee_permission_matches_template():
    perm = parse_employee_permission(_PERM, pos_permissions=_POS_PERMS)
    assert perm.granted_permission_ids == frozenset({10, 11, 12})
    assert perm.override_permission_ids == frozenset({11})
    assert perm.template_name == "Manager"
    assert perm.is_custom is False


def test_parse_employee_permission_custom_when_no_match():
    perm = parse_employee_permission(_PERM, pos_permissions=[_POS_PERMS[1]])
    assert perm.template_name is None
    assert perm.is_custom is True
    assert perm.granted_permission_ids == frozenset({10, 11, 12})
