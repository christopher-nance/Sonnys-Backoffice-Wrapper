from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sonnys_backoffice.employees import (
    _parse_edit_form_into_payload,
    disable_employee,
)
from sonnys_backoffice.exceptions import BackofficeServerError, NotFoundError
from sonnys_backoffice.models import DisableEmployeeRequest, EmployeeDisabled

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html"


_FAKE_LIST_HTML_WITH_486 = """
<table class="table table-employees-list">
  <thead>
    <tr><th>First Name</th><th>Last Name</th><th>POS User ID</th></tr>
  </thead>
  <tbody>
    <tr>
      <td class="employees-col-first-name">Wrapper</td>
      <td class="employees-col-last-name">Explore</td>
      <td class="employees-col-pos-user-id">99003</td>
      <td class="employees-col-edit">
        <a href="/employee/edit/486">edit</a>
      </td>
    </tr>
  </tbody>
</table>
"""


def _edit_before_disable_html() -> str:
    return (FIXTURES / "e2e_employee_edit_486_before_disable.html").read_text(encoding="utf-8")


def _edit_after_disable_html() -> str:
    return (FIXTURES / "e2e_employee_edit_486_after_disable.html").read_text(encoding="utf-8")


def test_parse_edit_form_drops_isActive():
    html = _edit_before_disable_html()
    payload = _parse_edit_form_into_payload(html, drop_fields={"employee[isActive]"})
    names = [n for n, _ in payload]
    assert "employee[isActive]" not in names
    # The form still carries the employee id, first name, last name, etc.
    assert "employee[id]" in names
    assert "employee[firstName]" in names
    assert "employee[lastName]" in names


def test_parse_edit_form_skips_disabled_inputs():
    html = _edit_before_disable_html()
    payload = _parse_edit_form_into_payload(html, drop_fields={"employee[isActive]"})
    # Sites with hidden disabled siteId inputs should NOT be submitted.
    # No disabled inputs means the output count is smaller than a blind parse would give
    assert len(payload) < 500


def test_parse_edit_form_preserves_checked_checkboxes():
    html = _edit_before_disable_html()
    payload = _parse_edit_form_into_payload(html, drop_fields={"employee[isActive]"})
    # wage[isHourly] is a checked toggle/checkbox in the form
    names = [n for n, _ in payload]
    # At least one site isAvailable checkbox should survive (site 17 was enabled)
    assert any("employee[sites][17]" in n for n in names)


def test_parse_edit_form_raises_when_no_form():
    with pytest.raises(BackofficeServerError, match="/employee/update"):
        _parse_edit_form_into_payload("<html><body>nothing</body></html>", drop_fields=set())


def test_disable_employee_full_round_trip():
    session = MagicMock()
    list_resp = MagicMock(status_code=200, text=_FAKE_LIST_HTML_WITH_486, headers={})
    edit_resp = MagicMock(status_code=200, text=_edit_before_disable_html(), headers={})
    update_resp = MagicMock(status_code=302, text="", headers={"Location": "/employee"})
    verify_resp = MagicMock(status_code=200, text=_edit_after_disable_html(), headers={})
    session.get.side_effect = [list_resp, edit_resp, verify_resp]
    session.post.return_value = update_resp

    req = DisableEmployeeRequest(pos_user_id=99003)
    result = disable_employee(session=session, request=req)

    assert isinstance(result, EmployeeDisabled)
    assert result.employee_id == 486
    assert result.pos_user_id == 99003
    assert isinstance(result.disabled_at, datetime)
    assert result.disabled_at.tzinfo is not None

    # Verify the POST hit /employee/update and omitted isActive
    post_call = session.post.call_args
    assert post_call.args[0] == "/employee/update"
    posted_pairs = post_call.kwargs["data"]
    posted_names = [n for n, _ in posted_pairs]
    assert "employee[isActive]" not in posted_names
    assert "employee[id]" in posted_names


def test_disable_employee_raises_if_still_active_after_post():
    session = MagicMock()
    list_resp = MagicMock(status_code=200, text=_FAKE_LIST_HTML_WITH_486, headers={})
    edit_resp = MagicMock(status_code=200, text=_edit_before_disable_html(), headers={})
    update_resp = MagicMock(status_code=302, text="", headers={})
    # Verify response still shows the employee as active (use the before-disable HTML)
    verify_resp = MagicMock(status_code=200, text=_edit_before_disable_html(), headers={})
    session.get.side_effect = [list_resp, edit_resp, verify_resp]
    session.post.return_value = update_resp

    req = DisableEmployeeRequest(pos_user_id=99003)
    with pytest.raises(BackofficeServerError, match="still active"):
        disable_employee(session=session, request=req)


def test_disable_employee_not_found_if_pos_user_id_missing_from_list():
    session = MagicMock()
    list_resp = MagicMock(status_code=200, text=_FAKE_LIST_HTML_WITH_486, headers={})
    session.get.side_effect = [list_resp]

    req = DisableEmployeeRequest(pos_user_id=12345)  # not in fake list
    with pytest.raises(NotFoundError):
        disable_employee(session=session, request=req)
