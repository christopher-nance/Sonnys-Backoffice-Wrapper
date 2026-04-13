import warnings

import pytest

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


def test_unknown_falls_back_to_general_user():
    match, warnings_list = resolve_permission("NonExistentRole", _POS_LIST)
    assert match.name == "General User"
    assert len(warnings_list) == 1
    assert "NonExistentRole" in warnings_list[0]
    assert "General User" in warnings_list[0]


def test_unknown_also_emits_python_warning():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        resolve_permission("NonExistentRole", _POS_LIST)
        assert len(w) == 1
        assert "NonExistentRole" in str(w[0].message)


def test_raises_if_general_user_not_in_list():
    short_list = [Permission(id=2, name="Administrator", scope="pos")]
    with pytest.raises(ValueError, match="General User"):
        resolve_permission("Unknown", short_list)
