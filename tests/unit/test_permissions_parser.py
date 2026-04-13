from pathlib import Path

from sonnys_backoffice.permissions import parse_permissions

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html"


def test_parses_pos_permissions_from_employee_permissions_54():
    html = (FIXTURES / "employee_permissions_54.html").read_text(encoding="utf-8")
    perms = parse_permissions(html, scope="pos")
    names = {p.name for p in perms}
    # Per D-4.3, WashU POS templates
    assert "Manager" in names
    assert "Cashier" in names
    assert "General User" in names
    assert "General Manager" in names
    assert "Assistant Manager" in names
    assert "Shift Leader" in names
    assert "CSA" in names
    assert all(p.scope == "pos" for p in perms)
    assert all(p.id > 0 for p in perms)


def test_pos_general_user_id():
    html = (FIXTURES / "employee_permissions_54.html").read_text(encoding="utf-8")
    perms = parse_permissions(html, scope="pos")
    general_user = next(p for p in perms if p.name == "General User")
    assert general_user.id == 3


def test_parses_bo_permissions_from_user_permissions_fixture():
    html = (FIXTURES / "w45f_user_permissions_2944451.html").read_text(encoding="utf-8")
    perms = parse_permissions(html, scope="backoffice")
    names = {p.name for p in perms}
    assert "Administrator" in names
    assert "Manager" in names
    assert "General User" in names
    assert all(p.scope == "backoffice" for p in perms)


def test_bo_administrator_id():
    html = (FIXTURES / "w45f_user_permissions_2944451.html").read_text(encoding="utf-8")
    perms = parse_permissions(html, scope="backoffice")
    admin = next(p for p in perms if p.name == "Administrator")
    assert admin.id == 1


def test_empty_html_yields_empty_list():
    assert parse_permissions("<html></html>", scope="pos") == []
