import pytest

from sonnys_backoffice.exceptions import NotFoundError
from sonnys_backoffice.models import Permission
from sonnys_backoffice.permissions import resolve_permission

_POS_LIST = [
    Permission(id=1, name="General User", scope="pos"),
    Permission(id=2, name="Administrator", scope="pos"),
    Permission(id=3, name="CSA", scope="pos"),
]


def test_exact_match():
    match, warnings_list = resolve_permission("Administrator", _POS_LIST)
    assert match.name == "Administrator"
    assert warnings_list == []


def test_case_insensitive_match():
    match, warnings_list = resolve_permission("administrator", _POS_LIST)
    assert match.name == "Administrator"
    assert warnings_list == []


def test_unknown_raises_with_available_list():
    with pytest.raises(NotFoundError, match="NonExistentRole") as exc_info:
        resolve_permission("NonExistentRole", _POS_LIST)
    msg = str(exc_info.value)
    assert "General User" in msg
    assert "Administrator" in msg
    assert "CSA" in msg


def test_unknown_raises_even_with_general_user_present():
    with pytest.raises(NotFoundError, match="Available templates"):
        resolve_permission("Unknown", _POS_LIST)
