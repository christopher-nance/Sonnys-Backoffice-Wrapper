import pytest
from pydantic import ValidationError as PydanticValidationError

from sonnys_backoffice.models import CreateBackofficeUserRequest, DisableEmployeeRequest


def test_disable_requires_exactly_one_lookup_key():
    with pytest.raises(PydanticValidationError, match="exactly one"):
        DisableEmployeeRequest()
    with pytest.raises(PydanticValidationError, match="exactly one"):
        DisableEmployeeRequest(pos_user_id="x", email="y@z.com")


def test_disable_accepts_pos_user_id_alone():
    req = DisableEmployeeRequest(pos_user_id="jdoe")
    assert req.pos_user_id == "jdoe"
    assert req.email is None


def test_disable_accepts_email_alone():
    req = DisableEmployeeRequest(email="jane@example.com")
    assert req.email == "jane@example.com"
    assert req.pos_user_id is None


def _bo_kwargs(**overrides):
    base = dict(
        username="janedoe",
        email="jane@example.com",
        permission="General User",
    )
    base.update(overrides)
    return base


def test_bo_user_requires_link_or_standalone():
    with pytest.raises(PydanticValidationError, match="link_to_employee"):
        CreateBackofficeUserRequest(**_bo_kwargs())


def test_bo_user_linked_mode_valid():
    req = CreateBackofficeUserRequest(**_bo_kwargs(link_to_employee_pos_user_id="jdoe"))
    assert req.link_to_employee_pos_user_id == "jdoe"


def test_bo_user_standalone_mode_requires_first_and_last_name():
    with pytest.raises(PydanticValidationError, match="first_name"):
        CreateBackofficeUserRequest(**_bo_kwargs(last_name="Doe"))


def test_bo_user_standalone_mode_valid():
    req = CreateBackofficeUserRequest(**_bo_kwargs(first_name="Jane", last_name="Doe"))
    assert req.first_name == "Jane"


def test_bo_user_link_and_standalone_are_mutually_exclusive():
    with pytest.raises(PydanticValidationError, match="either link"):
        CreateBackofficeUserRequest(
            **_bo_kwargs(
                first_name="Jane",
                last_name="Doe",
                link_to_employee_pos_user_id="jdoe",
            )
        )


def test_bo_user_username_pattern():
    with pytest.raises(PydanticValidationError):
        CreateBackofficeUserRequest(
            **_bo_kwargs(username="1starts_with_digit", first_name="a", last_name="b")
        )
    with pytest.raises(PydanticValidationError):
        CreateBackofficeUserRequest(**_bo_kwargs(username="ab", first_name="a", last_name="b"))


def test_bo_user_permission_is_required():
    kwargs = _bo_kwargs(link_to_employee_pos_user_id="jdoe")
    del kwargs["permission"]
    with pytest.raises(PydanticValidationError):
        CreateBackofficeUserRequest(**kwargs)
