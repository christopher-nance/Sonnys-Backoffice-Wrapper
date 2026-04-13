import pytest

from sonnys_backoffice.exceptions import (
    AuthenticationError,
    BackofficeServerError,
    DuplicateError,
    NotFoundError,
    PermissionDeniedError,
    SonnysBackofficeError,
    ValidationError,
)


def test_all_exceptions_inherit_from_base():
    for exc_cls in (
        AuthenticationError,
        NotFoundError,
        ValidationError,
        PermissionDeniedError,
        DuplicateError,
        BackofficeServerError,
    ):
        assert issubclass(exc_cls, SonnysBackofficeError)


def test_base_exception_is_exception():
    assert issubclass(SonnysBackofficeError, Exception)


def test_exceptions_carry_message():
    exc = ValidationError("phone must be 9 or 10 digits")
    assert "phone" in str(exc)


def test_catch_any_as_base():
    with pytest.raises(SonnysBackofficeError):
        raise DuplicateError("email already exists")
