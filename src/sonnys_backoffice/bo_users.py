"""Backoffice user creation.

Milestone 1 scope: create the BO user account (linked or standalone). Permission
template assignment is deferred to Milestone 2 — callers must click the shield
icon in the Backoffice UI to assign a template after creation. The linked mode
additionally requires the linked employee to be currently ACTIVE; linking to a
disabled employee returns a server-side error.
"""

from __future__ import annotations

import re
from typing import Any

from .exceptions import BackofficeServerError, DuplicateError
from .models import (
    BackofficeUserCreated,
    CreateBackofficeUserRequest,
    Permission,
)
from .passwords import generate_bo_password
from .sites import SiteTree

_BO_USER_ID_RE = re.compile(r"/user/(?:permissions|edit)/(\d+)")

_PERMISSION_DEFERRAL_WARNING = (
    "permission template assignment is deferred to Milestone 2 — "
    "assign via the Backoffice UI (shield icon) on /user"
)


def _extract_user_id_from_response(resp) -> int:
    location = resp.headers.get("Location", "") if hasattr(resp, "headers") else ""
    url = getattr(resp, "url", "") or ""
    for candidate in (location, url):
        m = _BO_USER_ID_RE.search(candidate or "")
        if m:
            return int(m.group(1))
    text = getattr(resp, "text", "") or ""
    m = re.search(r'name="user\[id\]"\s+value="(\d+)"', text)
    if m:
        return int(m.group(1))
    raise BackofficeServerError("could not extract new user_id from /user/insert response")


def _check_bo_insert_response(resp) -> None:
    if resp.status_code >= 500:
        raise BackofficeServerError(f"server error: HTTP {resp.status_code}")
    text = getattr(resp, "text", "") or ""
    lowered = text.lower()
    if "already exists" in lowered or "already taken" in lowered:
        raise DuplicateError("BO user with this username or email already exists")
    if "related employee is active" in lowered:
        raise BackofficeServerError("linked BO user creation requires the employee to be active")


def create_linked_backoffice_user(
    *,
    session: Any,
    username: str,
    email: str,
    password: str | None,
    linked_employee_id: int,
    permission: Permission,
    site_tree: SiteTree,
    available_sites,
) -> BackofficeUserCreated:
    """Create a Backoffice user linked to an existing (active) employee.

    Milestone 1: creates the account only. Permission template assignment
    is deferred — the returned `BackofficeUserCreated.warnings` contains
    a note about the manual UI step required.
    """
    pwd = password or generate_bo_password()
    payload = {
        "employee[isOnSiteEmployee]": "1",
        "user[employeeId]": str(linked_employee_id),
        "employee[email]": email,
        "user[username]": username,
        "user[password]": pwd,
        "user[confirmPassword]": pwd,
    }
    resp = session.post("/user/insert", data=payload)
    _check_bo_insert_response(resp)
    user_id = _extract_user_id_from_response(resp)

    return BackofficeUserCreated(
        user_id=user_id,
        username=username,
        password=pwd,
        email=email,
        linked_employee_id=linked_employee_id,
        permission_applied=permission.name,
        sites_granted=[s.name for s in site_tree.resolve_all(available_sites)],
        warnings=[_PERMISSION_DEFERRAL_WARNING],
    )


def create_standalone_backoffice_user(
    *,
    session: Any,
    request: CreateBackofficeUserRequest,
    site_tree: SiteTree,
    bo_permissions: list[Permission],
) -> BackofficeUserCreated:
    """Create a standalone (not employee-linked) Backoffice user.

    Milestone 1: creates the account only. Permission template assignment
    is deferred to Milestone 2 via the Backoffice UI.
    """
    from .permissions import resolve_permission

    warnings_list: list[str] = []
    pwd = request.password or generate_bo_password()
    perm, perm_warnings = resolve_permission(request.permission, bo_permissions)
    warnings_list.extend(perm_warnings)

    payload = {
        "employee[isOnSiteEmployee]": "0",
        "employee[firstName]": request.first_name,
        "employee[lastName]": request.last_name,
        "employee[email]": request.email,
        "user[username]": request.username,
        "user[password]": pwd,
        "user[confirmPassword]": pwd,
    }
    resp = session.post("/user/insert", data=payload)
    _check_bo_insert_response(resp)
    user_id = _extract_user_id_from_response(resp)

    warnings_list.append(_PERMISSION_DEFERRAL_WARNING)
    return BackofficeUserCreated(
        user_id=user_id,
        username=request.username,
        password=pwd,
        email=request.email,
        linked_employee_id=None,
        permission_applied=perm.name,
        sites_granted=[s.name for s in site_tree.resolve_all(request.available_sites)],
        warnings=warnings_list,
    )
