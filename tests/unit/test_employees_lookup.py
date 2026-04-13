from pathlib import Path

import pytest

from sonnys_backoffice.employees import find_employee_in_list_html
from sonnys_backoffice.exceptions import NotFoundError

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html"


def test_find_by_pos_user_id_aaliyah():
    html = (FIXTURES / "employee_list.html").read_text(encoding="utf-8")
    # aaliyah roylance → emp 54, pos 7217 (confirmed in test_employees_uniqueness)
    employee_id = find_employee_in_list_html(html, pos_user_id=7217)
    assert employee_id == 54


def test_not_found_raises_for_unknown_pos_user_id():
    html = (FIXTURES / "employee_list.html").read_text(encoding="utf-8")
    with pytest.raises(NotFoundError, match="pos_user_id=999999"):
        find_employee_in_list_html(html, pos_user_id=999999)


def test_requires_at_least_one_key():
    html = (FIXTURES / "employee_list.html").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="required"):
        find_employee_in_list_html(html)


def test_email_lookup_not_found_when_emails_absent_from_list():
    # Employee list HTML doesn't contain emails — email lookup should miss
    # and callers should fall back to the /user/create dropdown index.
    html = (FIXTURES / "employee_list.html").read_text(encoding="utf-8")
    with pytest.raises(NotFoundError):
        find_employee_in_list_html(html, email="aaliyahroylance9@gmail.com")


def test_raises_when_no_table_present():
    with pytest.raises(NotFoundError, match="table not found"):
        find_employee_in_list_html("<html><body>nothing</body></html>", pos_user_id=1)
