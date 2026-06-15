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
    EmployeeCreated,
    EmployeeDisabled,
    EmployeeModified,
    ModifyEmployeeRequest,
    Permission,
    Region,
    Site,
)

__version__ = "0.3.0"

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
    "Site",
    "Region",
    "Department",
    "Permission",
    "__version__",
]
