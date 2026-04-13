from pathlib import Path

from sonnys_backoffice.departments import parse_departments

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html"


def test_parses_departments_from_employee_create_fixture():
    html = (FIXTURES / "employee_create.html").read_text(encoding="utf-8")
    depts = parse_departments(html)
    names = [d.name for d in depts]
    assert "Greeter" in names
    assert "Cashier" in names
    assert "Line" in names
    assert "Management" in names
    assert all(d.id > 0 for d in depts)


def test_greeter_has_id_three():
    html = (FIXTURES / "employee_create.html").read_text(encoding="utf-8")
    depts = parse_departments(html)
    greeter = next(d for d in depts if d.name == "Greeter")
    assert greeter.id == 3


def test_returns_empty_list_when_select_missing():
    depts = parse_departments("<html><body></body></html>")
    assert depts == []
