from pathlib import Path

import pytest

from sonnys_backoffice.employees import (
    EmployeeIndex,
    build_employee_index,
    parse_employee_list,
    parse_user_create_employee_options,
)
from sonnys_backoffice.exceptions import DuplicateError

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html"


def test_parse_employee_list_extracts_pos_id_and_phone():
    html = (FIXTURES / "employee_list.html").read_text(encoding="utf-8")
    pos_map, phone_map = parse_employee_list(html)
    assert len(pos_map) >= 20
    # aaliyah roylance = emp 54, pos 7217, phone (702) 845-6915
    assert pos_map[7217] == 54
    assert phone_map["7028456915"] == 54
    assert all(isinstance(k, int) for k in pos_map)
    assert all(phone.isdigit() for phone in phone_map)


def test_parse_user_create_builds_email_map():
    html = (FIXTURES / "user_create.html").read_text(encoding="utf-8")
    email_map = parse_user_create_employee_options(html)
    assert len(email_map) > 100  # WashU has hundreds
    assert email_map["aaliyahroylance9@gmail.com"] == 54
    assert all("@" in e for e in email_map)
    assert all(e == e.lower() for e in email_map)


def test_build_employee_index_from_fixtures():
    list_html = (FIXTURES / "employee_list.html").read_text(encoding="utf-8")
    user_html = (FIXTURES / "user_create.html").read_text(encoding="utf-8")
    index = build_employee_index(
        employee_list_html=list_html,
        user_create_html=user_html,
    )
    assert index.by_pos_user_id[7217] == 54
    assert index.by_email["aaliyahroylance9@gmail.com"] == 54


def test_employee_index_check_raises_on_pos_id_collision():
    idx = EmployeeIndex(by_pos_user_id={1234: 99})
    with pytest.raises(DuplicateError, match="pos_user_id=1234"):
        idx.check(pos_user_id=1234, email="new@example.com", phone="6155551234")


def test_employee_index_check_raises_on_email_collision_case_insensitive():
    idx = EmployeeIndex(by_email={"taken@example.com": 42})
    with pytest.raises(DuplicateError, match="email"):
        idx.check(pos_user_id=99999, email="Taken@Example.com", phone="6155551234")


def test_employee_index_check_raises_on_phone_collision_with_symbols():
    idx = EmployeeIndex(by_phone={"6155551234": 17})
    with pytest.raises(DuplicateError, match="phone"):
        idx.check(pos_user_id=99999, email="new@example.com", phone="(615) 555-1234")


def test_employee_index_check_ok_when_all_clear():
    idx = EmployeeIndex(
        by_pos_user_id={1234: 99},
        by_email={"taken@example.com": 42},
        by_phone={"6155551234": 17},
    )
    idx.check(pos_user_id=5678, email="new@example.com", phone="6155559999")
