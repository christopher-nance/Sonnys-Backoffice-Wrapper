"""Unit tests for modify_employee: hierarchical site builder + reactivation."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from sonnys_backoffice.employees import (
    _build_site_availability_fields,
    _current_wage_overtime_eligible,
    _latest_wage_effective_date,
    modify_employee,
)
from sonnys_backoffice.models import District, ModifyEmployeeRequest, Region, Site
from sonnys_backoffice.sites import SiteTree


def _hierarchical_tree() -> SiteTree:
    return SiteTree(
        is_hierarchical=True,
        regions=[Region(id=1, name="Global"), Region(id=2, name="WashU Illinois")],
        districts=[
            District(id=1, name="Global", region_id=1),
            District(id=2, name="WashU", region_id=2),
        ],
        sites=[
            Site(id=17, name="Wash 37135", district_id=1, region_id=1),
            Site(id=1, name="WashU Fiesta", district_id=2, region_id=2),
            Site(id=4, name="WashU Niles", district_id=2, region_id=2),
        ],
    )


def _flat_tree() -> SiteTree:
    return SiteTree(
        is_hierarchical=False,
        sites=[Site(id=17, name="Wash 37135"), Site(id=18, name="Wash 37055")],
    )


# ── _build_site_availability_fields ──────────────────────────────────────────


def test_site_fields_hierarchical_restricted_lists_granted_isavailable():
    # Grant sites 1 + 4 (both in district 2); site 17 (district 1) is denied.
    fields = _build_site_availability_fields(_hierarchical_tree(), ["WashU Fiesta", "WashU Niles"])
    names = [n for n, _ in fields]
    # No all-regions flag, and crucially NO district/region rollup flags — an
    # untouched district's rollup stays true and leaks all of its sites (this is
    # the bug that granted site 17's whole district).
    assert not any("isAllRegionsAllowed" in n for n in names)
    assert not any("isAllSitesAllowedByDistrict" in n for n in names)
    assert not any("isAllDistrictsAllowedByRegion" in n for n in names)
    # siteId is emitted for EVERY site (granted and denied) — the hidden fields
    # a browser always submits.
    assert ("employee[sites][1][siteId]", "1") in fields
    assert ("employee[sites][4][siteId]", "4") in fields
    assert ("employee[sites][17][siteId]", "17") in fields
    # isAvailable only for the granted sites; the denied site 17 has none.
    assert ("employee[sites][1][isAvailable]", "1") in fields
    assert ("employee[sites][4][isAvailable]", "4") in fields
    assert not any(n == "employee[sites][17][isAvailable]" for n in names)


def test_site_fields_hierarchical_all_sets_flag():
    fields = _build_site_availability_fields(_hierarchical_tree(), "all")
    assert fields == [("employee[isAllRegionsAllowed]", "1")]


def test_site_fields_flat_restricted_lists_complement():
    fields = _build_site_availability_fields(_flat_tree(), ["Wash 37135"])
    assert fields == [("employee[siteIds][]", "18")]


# ── modify_employee reactivation ─────────────────────────────────────────────

_EDIT_FORM = """
<form action="/employee/update" method="post">
  <input type="text" name="employee[firstName]" value="WrapperExplore">
  <input type="hidden" name="employee[id]" value="541">
  <input type="checkbox" name="employee[isActive]">
</form>
"""


def _session_for_properties() -> MagicMock:
    session = MagicMock()
    get_resp = MagicMock()
    get_resp.status_code = 200
    get_resp.headers = {}
    get_resp.text = _EDIT_FORM
    post_resp = MagicMock()
    post_resp.status_code = 302
    post_resp.headers = {}
    post_resp.text = ""
    session.get.return_value = get_resp
    session.post.return_value = post_resp
    return session


def test_modify_activate_true_emits_isactive():
    session = _session_for_properties()
    req = ModifyEmployeeRequest(pos_user_id=95001, activate=True)
    result = modify_employee(session=session, employee_id=541, request=req)
    posted = session.post.call_args.kwargs["data"]
    assert ("employee[isActive]", "1") in posted
    assert "activated" in result.changes_applied


def test_modify_activate_false_omits_isactive():
    session = _session_for_properties()
    req = ModifyEmployeeRequest(pos_user_id=95001, activate=False)
    modify_employee(session=session, employee_id=541, request=req)
    posted = session.post.call_args.kwargs["data"]
    assert not any(n == "employee[isActive]" for n, _ in posted)


def test_modify_activate_with_sites_in_one_post():
    session = _session_for_properties()
    req = ModifyEmployeeRequest(
        pos_user_id=95001, activate=True, available_sites=["WashU Fiesta", "WashU Niles"]
    )
    modify_employee(
        session=session,
        employee_id=541,
        request=req,
        site_tree=_hierarchical_tree(),
    )
    # Exactly one /employee/update POST carries both activation and site fields.
    assert session.post.call_count == 1
    posted = session.post.call_args.kwargs["data"]
    assert ("employee[isActive]", "1") in posted
    assert ("employee[sites][17][siteId]", "17") in posted
    assert not any("isAllRegionsAllowed" in n for n, _ in posted)


# ── compensation: effective date + overtime preservation ─────────────────────


def _comp_html(effective: date, *, ot_eligible: bool) -> str:
    eff = effective.strftime("%m/%d/%Y")
    ot_cell = '<i class="fa fa-check"></i>' if ot_eligible else '<i class="fa fa-times"></i>'
    return f"""
    <form action="/employee/compensation/update" method="post">
      <input type="number" name="wage[regularRate]" value="">
      <input type="text" name="wage[effectiveDate]" data-value="{eff}">
      <input type="checkbox" name="wage[isOvertimeEligible]" value="1">
      <input type="number" name="wage[overtimeRate]" value="">
    </form>
    <table class="table-employee-compensation-history"><tbody>
      <tr>
        <td class="employee-compensation-col-wage">$14.00/hr</td>
        <td class="employee-compensation-col-overtime-eligible">{ot_cell}</td>
        <td class="employee-compensation-col-effective-date">{eff}</td>
        <td class="employee-compensation-col-end-date"></td>
      </tr>
    </tbody></table>
    """


def _comp_session(html: str) -> MagicMock:
    session = MagicMock()
    session.get.return_value = MagicMock(status_code=200, headers={}, text=html)
    session.post.return_value = MagicMock(status_code=302, headers={}, text="")
    return session


def test_latest_wage_effective_date_parses_history():
    html = _comp_html(date(2026, 6, 1), ot_eligible=True)
    assert _latest_wage_effective_date(html) == date(2026, 6, 1)


def test_current_wage_overtime_eligible_reads_active_row():
    assert _current_wage_overtime_eligible(_comp_html(date(2026, 6, 1), ot_eligible=True)) is True
    assert _current_wage_overtime_eligible(_comp_html(date(2026, 6, 1), ot_eligible=False)) is False


def test_wage_change_same_day_rolls_effective_to_next_day():
    today = datetime.now().date()
    session = _comp_session(_comp_html(today, ot_eligible=True))
    req = ModifyEmployeeRequest(pos_user_id=95001, wage_rate=Decimal("17.25"))
    result = modify_employee(session=session, employee_id=541, request=req)
    posted = dict(session.post.call_args.kwargs["data"])
    # Effective rolls to today+1 because a record is already effective today.
    assert posted["wage[effectiveDate]"] == (today + timedelta(days=1)).strftime("%m/%d/%Y")
    assert result.wage_effective_date == today + timedelta(days=1)


def test_wage_change_preserves_overtime_eligibility_and_recomputes():
    today = datetime.now().date()
    session = _comp_session(_comp_html(today, ot_eligible=True))
    req = ModifyEmployeeRequest(pos_user_id=95001, wage_rate=Decimal("17.25"))
    modify_employee(session=session, employee_id=541, request=req)
    posted = session.post.call_args.kwargs["data"]
    assert ("wage[isOvertimeEligible]", "1") in posted
    assert dict(posted)["wage[overtimeRate]"] == "25.88"  # 1.5 * 17.25


def test_wage_change_drops_overtime_when_not_eligible():
    today = datetime.now().date()
    session = _comp_session(_comp_html(today, ot_eligible=False))
    req = ModifyEmployeeRequest(pos_user_id=95001, wage_rate=Decimal("17.25"))
    modify_employee(session=session, employee_id=541, request=req)
    posted = session.post.call_args.kwargs["data"]
    assert not any(n == "wage[isOvertimeEligible]" for n, _ in posted)


def test_wage_effective_date_clamped_up_to_minimum_with_warning():
    today = datetime.now().date()
    session = _comp_session(_comp_html(today, ot_eligible=True))
    # Ask for an effective date on the same day as the existing record — illegal,
    # must clamp up to today+1 and warn.
    req = ModifyEmployeeRequest(
        pos_user_id=95001,
        wage_rate=Decimal("17.25"),
        wage_effective_date=datetime(today.year, today.month, today.day),
    )
    result = modify_employee(session=session, employee_id=541, request=req)
    assert result.wage_effective_date == today + timedelta(days=1)
    assert any("clamped" in w for w in result.warnings)
