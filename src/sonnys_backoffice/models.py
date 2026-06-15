"""Pydantic v2 models for inputs, outputs, and domain objects."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_PHONE_SYMBOL_RE = re.compile(r"[^\d]")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_GREETER = "Greeter"


class _BackofficeBaseModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class CreateEmployeeRequest(_BackofficeBaseModel):
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    phone: str
    email: str
    pos_user_id: int
    pos_pin: int | None = None
    wage_rate: Decimal
    overtime_wage_rate: Decimal | None = None
    start_date: datetime
    available_sites: list[str] | Literal["all"]
    departments: list[str] | None = None
    permission: str
    adp_employee_id: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    requires_backoffice: bool = False
    backoffice_username: str | None = None
    backoffice_password: str | None = None

    @field_validator("phone", "emergency_contact_phone", mode="before")
    @classmethod
    def _normalize_phone(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = _PHONE_SYMBOL_RE.sub("", v)
        if len(stripped) not in (9, 10):
            raise ValueError("phone must be 9 or 10 digits after symbols are stripped")
        return stripped

    @field_validator("email", mode="before")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        if not isinstance(v, str) or not _EMAIL_RE.match(v.strip()):
            raise ValueError(f"email must contain a valid @domain.tld: {v!r}")
        return v.strip()

    @field_validator("pos_pin", mode="before")
    @classmethod
    def _validate_pos_pin(cls, v: int | None) -> int | None:
        if v is None:
            return None
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValueError("pos_pin must be a 5-digit integer (10000-99999) or None")
        if not (10000 <= v <= 99999):
            raise ValueError("pos_pin must be a 5-digit integer (10000-99999) or None")
        return v

    @field_validator("departments", mode="before")
    @classmethod
    def _default_departments(cls, v: list[str] | None) -> list[str]:
        if v is None or len(v) == 0:
            return [_GREETER]
        cleaned = [d.strip() for d in v if d.strip()]
        if _GREETER not in cleaned:
            cleaned.append(_GREETER)
        seen: set[str] = set()
        out: list[str] = []
        for d in cleaned:
            if d not in seen:
                seen.add(d)
                out.append(d)
        return out

    @field_validator("available_sites", mode="before")
    @classmethod
    def _validate_sites(cls, v):
        if v == "all":
            return v
        if isinstance(v, list) and len(v) == 0:
            raise ValueError("available_sites must contain at least one site name (or be 'all')")
        return v

    @model_validator(mode="after")
    def _check_wage_and_backoffice(self) -> CreateEmployeeRequest:
        if self.overtime_wage_rate is None:
            object.__setattr__(
                self,
                "overtime_wage_rate",
                (self.wage_rate * Decimal("1.5")).quantize(Decimal("0.01")),
            )
        if self.requires_backoffice and not self.backoffice_username:
            raise ValueError("backoffice_username is required when requires_backoffice=True")
        return self


_USERNAME_RE = re.compile(r"^[A-Za-z][\w]{2,63}$")


class DisableEmployeeRequest(_BackofficeBaseModel):
    pos_user_id: int | None = None
    email: str | None = None

    @field_validator("email", mode="before")
    @classmethod
    def _validate_email(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not _EMAIL_RE.match(v.strip()):
            raise ValueError(f"email must contain a valid @domain.tld: {v!r}")
        return v.strip()

    @model_validator(mode="after")
    def _check_exactly_one(self) -> DisableEmployeeRequest:
        provided = [x for x in (self.pos_user_id, self.email) if x is not None]
        if len(provided) != 1:
            raise ValueError("exactly one of pos_user_id or email is required")
        return self


class ModifyEmployeeRequest(_BackofficeBaseModel):
    pos_user_id: int | None = None
    email: str | None = None

    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    new_email: str | None = None
    departments: list[str] | None = None
    available_sites: list[str] | Literal["all"] | None = None
    adp_employee_id: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None

    wage_rate: Decimal | None = None
    overtime_wage_rate: Decimal | None = None
    wage_effective_date: datetime | None = None

    permission: str | None = None

    activate: bool | None = None

    @field_validator("available_sites", mode="before")
    @classmethod
    def _validate_sites(cls, v):
        if v is None or v == "all":
            return v
        if isinstance(v, list) and len(v) == 0:
            raise ValueError("available_sites must contain at least one site name (or be 'all')")
        return v

    @field_validator("phone", "emergency_contact_phone", mode="before")
    @classmethod
    def _normalize_phone(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = _PHONE_SYMBOL_RE.sub("", v)
        if len(stripped) not in (9, 10):
            raise ValueError("phone must be 9 or 10 digits after symbols are stripped")
        return stripped

    @field_validator("email", mode="before")
    @classmethod
    def _validate_lookup_email(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not _EMAIL_RE.match(v.strip()):
            raise ValueError(f"email must contain a valid @domain.tld: {v!r}")
        return v.strip()

    @field_validator("new_email", mode="before")
    @classmethod
    def _validate_new_email(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not _EMAIL_RE.match(v.strip()):
            raise ValueError(f"email must contain a valid @domain.tld: {v!r}")
        return v.strip()

    @model_validator(mode="after")
    def _check_lookup_and_changes(self) -> ModifyEmployeeRequest:
        provided = [x for x in (self.pos_user_id, self.email) if x is not None]
        if len(provided) != 1:
            raise ValueError("exactly one of pos_user_id or email is required as lookup key")
        has_any = any(
            [
                self.first_name is not None,
                self.last_name is not None,
                self.phone is not None,
                self.new_email is not None,
                self.departments is not None,
                self.available_sites is not None,
                self.adp_employee_id is not None,
                self.emergency_contact_name is not None,
                self.emergency_contact_phone is not None,
                self.wage_rate is not None,
                self.overtime_wage_rate is not None,
                self.permission is not None,
                self.activate is not None,
            ]
        )
        if not has_any:
            raise ValueError("at least one change field must be provided")
        return self


class CreateBackofficeUserRequest(_BackofficeBaseModel):
    username: str
    email: str
    password: str | None = None
    permission: str
    link_to_employee_pos_user_id: str | None = None
    link_to_employee_email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    available_sites: list[str] | Literal["all"] = "all"

    @field_validator("username", mode="before")
    @classmethod
    def _validate_username(cls, v: str) -> str:
        if not _USERNAME_RE.match(v):
            raise ValueError(
                "username must start with a letter and contain 3-64 alphanumeric characters"
            )
        return v

    @field_validator("email", mode="before")
    @classmethod
    def _validate_bo_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v.strip()):
            raise ValueError(f"email must contain a valid @domain.tld: {v!r}")
        return v.strip()

    @model_validator(mode="after")
    def _check_link_or_standalone(self) -> CreateBackofficeUserRequest:
        has_link = bool(self.link_to_employee_pos_user_id or self.link_to_employee_email)
        has_standalone = bool(self.first_name or self.last_name)
        if has_link and has_standalone:
            raise ValueError("provide either link_to_employee_* or first_name+last_name — not both")
        if not has_link and not has_standalone:
            raise ValueError(
                "provide either link_to_employee_pos_user_id / link_to_employee_email or first_name+last_name"
            )
        if has_standalone and not (self.first_name and self.last_name):
            raise ValueError("standalone BO user requires both first_name and last_name")
        return self


class EmployeeCreated(_BackofficeBaseModel):
    employee_id: int
    pos_user_id: int
    pos_pin: int
    first_name: str
    last_name: str
    email: str
    backoffice_user_id: int | None = None
    backoffice_username: str | None = None
    backoffice_password: str | None = None
    permission_applied: str
    sites_granted: list[str]
    departments: list[str]
    wage_site: str
    warnings: list[str] = Field(default_factory=list)


class BackofficeUserCreated(_BackofficeBaseModel):
    user_id: int
    username: str
    password: str
    email: str
    linked_employee_id: int | None = None
    permission_applied: str
    sites_granted: list[str]
    warnings: list[str] = Field(default_factory=list)


class EmployeeDisabled(_BackofficeBaseModel):
    employee_id: int
    pos_user_id: int
    email: str | None = None
    disabled_at: datetime


class EmployeeModified(_BackofficeBaseModel):
    employee_id: int
    changes_applied: list[str]
    permission_applied: str | None = None
    wage_rate: Decimal | None = None
    wage_effective_date: date | None = None
    warnings: list[str] = Field(default_factory=list)


class EmployeeSummary(_BackofficeBaseModel):
    """A lightweight roster row from the employee list page."""

    employee_id: int
    pos_user_id: int | None = None
    first_name: str
    last_name: str
    phone: str | None = None
    is_active: bool


class WageRecord(_BackofficeBaseModel):
    """A single wage record from the compensation history."""

    wage_type: str
    rate: Decimal
    overtime_eligible: bool
    overtime_rate: Decimal | None = None
    effective_date: date | None = None
    end_date: date | None = None
    is_current: bool = False


class EmployeeCompensation(_BackofficeBaseModel):
    current: WageRecord | None = None
    history: list[WageRecord] = Field(default_factory=list)


class EmployeePermission(_BackofficeBaseModel):
    """An employee's current POS permission state.

    Sonny's does not store a clean "current template" — the template dropdown
    resets to blank after a template is applied, so the grant matrix is the
    source of truth. ``template_name`` is a best-effort exact match against the
    tenant's templates; ``is_custom`` is True when the grants match none exactly.
    """

    template_name: str | None = None
    is_custom: bool = True
    granted_permission_ids: frozenset[int] = Field(default_factory=frozenset)
    override_permission_ids: frozenset[int] = Field(default_factory=frozenset)


class EmployeeProfile(_BackofficeBaseModel):
    """Identity, contact, and assignment fields from the edit page."""

    employee_id: int
    pos_user_id: int | None = None
    first_name: str
    last_name: str
    email: str | None = None
    phone: str | None = None
    departments: list[str] = Field(default_factory=list)
    available_sites: list[str] | Literal["all"] = Field(default_factory=list)
    start_date: date | None = None
    adp_employee_id: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    is_active: bool = True


class Employee(EmployeeProfile):
    """Full current-state snapshot: profile + compensation + permission."""

    current_wage: WageRecord | None = None
    wage_history: list[WageRecord] = Field(default_factory=list)
    permission: EmployeePermission = Field(default_factory=EmployeePermission)


class Region(_BackofficeBaseModel):
    id: int
    name: str


class District(_BackofficeBaseModel):
    id: int
    name: str
    region_id: int | None = None


class Site(_BackofficeBaseModel):
    id: int
    name: str
    district_id: int | None = None
    region_id: int | None = None


class Department(_BackofficeBaseModel):
    id: int
    name: str


class Permission(_BackofficeBaseModel):
    id: int
    name: str
    scope: Literal["pos", "backoffice"]
    grants: frozenset[int] = Field(default_factory=frozenset)
    overrides: frozenset[int] = Field(default_factory=frozenset)


class PermissionFieldMeta(_BackofficeBaseModel):
    id: int
    label: str
    description: str
