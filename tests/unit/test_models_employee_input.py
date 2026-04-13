from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError

from sonnys_backoffice.models import CreateEmployeeRequest


def _valid_kwargs(**overrides):
    base = dict(
        first_name="Jane",
        last_name="Doe",
        phone="6155551234",
        email="jane@example.com",
        pos_user_id=12345,
        wage_rate=Decimal("15.50"),
        start_date=datetime(2026, 5, 1),
        available_sites=["Wash 37135"],
        permission="General User",
    )
    base.update(overrides)
    return base


def test_phone_strips_symbols_and_spaces():
    req = CreateEmployeeRequest(**_valid_kwargs(phone="(615) 555-1234"))
    assert req.phone == "6155551234"


def test_phone_accepts_nine_digits():
    req = CreateEmployeeRequest(**_valid_kwargs(phone="155551234"))
    assert req.phone == "155551234"


def test_phone_rejects_eight_digits():
    with pytest.raises(PydanticValidationError, match="9 or 10"):
        CreateEmployeeRequest(**_valid_kwargs(phone="15551234"))


def test_phone_rejects_eleven_digits():
    with pytest.raises(PydanticValidationError, match="9 or 10"):
        CreateEmployeeRequest(**_valid_kwargs(phone="16155551234"))


def test_name_is_stripped():
    req = CreateEmployeeRequest(**_valid_kwargs(first_name="  Jane  ", last_name=" Doe "))
    assert req.first_name == "Jane"
    assert req.last_name == "Doe"


def test_name_preserves_unicode_and_symbols():
    req = CreateEmployeeRequest(**_valid_kwargs(first_name="José", last_name="O'Neal-García"))
    assert req.first_name == "José"
    assert req.last_name == "O'Neal-García"


def test_email_requires_at_and_domain():
    with pytest.raises(PydanticValidationError, match="email"):
        CreateEmployeeRequest(**_valid_kwargs(email="not-an-email"))


def test_email_accepts_standard_formats():
    for email in ("user@gmail.com", "user@icloud.com", "user.name@washucarwash.com"):
        CreateEmployeeRequest(**_valid_kwargs(email=email))


def test_departments_defaults_to_greeter():
    req = CreateEmployeeRequest(**_valid_kwargs(departments=None))
    assert req.departments == ["Greeter"]


def test_departments_auto_adds_greeter_if_missing():
    req = CreateEmployeeRequest(**_valid_kwargs(departments=["Cashier"]))
    assert "Greeter" in req.departments
    assert "Cashier" in req.departments


def test_departments_does_not_duplicate_greeter():
    req = CreateEmployeeRequest(**_valid_kwargs(departments=["Greeter", "Cashier"]))
    assert req.departments.count("Greeter") == 1


def test_overtime_defaults_to_time_and_a_half():
    req = CreateEmployeeRequest(**_valid_kwargs(wage_rate=Decimal("10.00")))
    assert req.overtime_wage_rate == Decimal("15.00")


def test_overtime_honors_explicit_value():
    req = CreateEmployeeRequest(
        **_valid_kwargs(wage_rate=Decimal("10.00"), overtime_wage_rate=Decimal("20.00"))
    )
    assert req.overtime_wage_rate == Decimal("20.00")


def test_available_sites_accepts_all_literal():
    req = CreateEmployeeRequest(**_valid_kwargs(available_sites="all"))
    assert req.available_sites == "all"


def test_available_sites_rejects_empty_list():
    with pytest.raises(PydanticValidationError, match="at least one"):
        CreateEmployeeRequest(**_valid_kwargs(available_sites=[]))


def test_requires_backoffice_requires_username():
    with pytest.raises(PydanticValidationError, match="backoffice_username"):
        CreateEmployeeRequest(**_valid_kwargs(requires_backoffice=True))


def test_pos_user_id_is_int():
    req = CreateEmployeeRequest(**_valid_kwargs(pos_user_id=98765))
    assert req.pos_user_id == 98765
    assert isinstance(req.pos_user_id, int)


def test_pos_pin_accepts_valid_int():
    req = CreateEmployeeRequest(**_valid_kwargs(pos_pin=12345))
    assert req.pos_pin == 12345


def test_pos_pin_none_is_allowed():
    req = CreateEmployeeRequest(**_valid_kwargs(pos_pin=None))
    assert req.pos_pin is None


def test_pos_pin_rejects_too_small():
    with pytest.raises(PydanticValidationError, match="5"):
        CreateEmployeeRequest(**_valid_kwargs(pos_pin=123))


def test_pos_pin_rejects_too_large():
    with pytest.raises(PydanticValidationError, match="5"):
        CreateEmployeeRequest(**_valid_kwargs(pos_pin=123456))


def test_permission_is_required():
    kwargs = _valid_kwargs()
    del kwargs["permission"]
    with pytest.raises(PydanticValidationError):
        CreateEmployeeRequest(**kwargs)


def test_adp_employee_id_optional():
    req = CreateEmployeeRequest(**_valid_kwargs(adp_employee_id="EMP-0042"))
    assert req.adp_employee_id == "EMP-0042"


def test_adp_employee_id_default_none():
    req = CreateEmployeeRequest(**_valid_kwargs())
    assert req.adp_employee_id is None


def test_extra_kwargs_rejected():
    with pytest.raises(PydanticValidationError):
        CreateEmployeeRequest(**_valid_kwargs(mystery_field="nope"))
