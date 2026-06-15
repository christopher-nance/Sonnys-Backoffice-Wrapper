"""Sonny's Backoffice Wrapper — programmatic user management for Sonny's Carwash Controls Backoffice."""

from .client import SonnysBackofficeClient
from .exceptions import (
    AuthenticationError,
    BackofficeServerError,
    DuplicateError,
    NotFoundError,
    PermissionDeniedError,
    SonnysBackofficeError,
    ValidationError,
)
from .models import (
    BackofficeUserCreated,
    CreateBackofficeUserRequest,
    CreateEmployeeRequest,
    Department,
    DisableEmployeeRequest,
    Employee,
    EmployeeCompensation,
    EmployeeCreated,
    EmployeeDisabled,
    EmployeeModified,
    EmployeePermission,
    EmployeeProfile,
    EmployeeSummary,
    ModifyEmployeeRequest,
    Permission,
    Region,
    Site,
    WageRecord,
)

__version__ = "0.4.0"

__all__ = [
    "SonnysBackofficeClient",
    "SonnysBackofficeError",
    "AuthenticationError",
    "NotFoundError",
    "ValidationError",
    "PermissionDeniedError",
    "DuplicateError",
    "BackofficeServerError",
    "CreateEmployeeRequest",
    "CreateBackofficeUserRequest",
    "DisableEmployeeRequest",
    "ModifyEmployeeRequest",
    "EmployeeCreated",
    "BackofficeUserCreated",
    "EmployeeDisabled",
    "EmployeeModified",
    "EmployeeSummary",
    "EmployeeProfile",
    "EmployeeCompensation",
    "EmployeePermission",
    "Employee",
    "WageRecord",
    "Site",
    "Region",
    "Department",
    "Permission",
    "__version__",
]
