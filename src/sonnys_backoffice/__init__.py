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
    Permission,
    Region,
    Site,
)

__version__ = "0.1.0"

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
    "EmployeeCreated",
    "BackofficeUserCreated",
    "EmployeeDisabled",
    "Site",
    "Region",
    "Department",
    "Permission",
    "__version__",
]
