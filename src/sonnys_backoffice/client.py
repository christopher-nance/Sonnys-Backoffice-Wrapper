"""Public SonnysBackofficeClient façade."""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Literal

from .bo_users import (
    create_linked_backoffice_user,
    create_standalone_backoffice_user,
)
from .departments import parse_departments
from .employees import (
    EmployeeIndex,
    build_employee_index,
    create_employee as _create_employee,
    disable_employee as _disable_employee,
    find_employee_in_list_html,
)
from .exceptions import NotFoundError
from .models import (
    BackofficeUserCreated,
    CreateBackofficeUserRequest,
    CreateEmployeeRequest,
    Department,
    DisableEmployeeRequest,
    EmployeeCreated,
    EmployeeDisabled,
    Permission,
    PermissionFieldMeta,
    Site,
)
from .permissions import parse_permissions_and_schema, resolve_permission
from .session import _BackofficeSession
from .sites import SiteTree, parse_site_tree

_EMP_PERMISSIONS_LINK_RE = re.compile(r"/employee/permissions/(\d+)")
_USER_PERMISSIONS_LINK_RE = re.compile(r"/user/permissions/(\d+)")
_DIGITS_RE = re.compile(r"\D")


class SonnysBackofficeClient:
    """Programmatic access to Sonny's Backoffice user management.

    Caches are populated lazily on first use and reused for subsequent calls.
    Pass `refresh=True` to discovery methods to force a re-fetch.
    """

    def __init__(
        self,
        *,
        subdomain: str,
        username: str,
        password: str,
        timeout: float = 30.0,
        user_agent: str | None = None,
    ) -> None:
        self._session = _BackofficeSession(
            subdomain=subdomain,
            username=username,
            password=password,
            timeout=timeout,
            user_agent=user_agent,
        )
        self._site_tree: SiteTree | None = None
        self._departments: list[Department] | None = None
        self._pos_permissions: list[Permission] | None = None
        self._pos_permission_schema: list[PermissionFieldMeta] | None = None
        self._bo_permissions: list[Permission] | None = None
        self._employee_index: EmployeeIndex | None = None
        self._employee_list_html: str | None = None

    def __enter__(self) -> "SonnysBackofficeClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._session.close()

    def list_sites(self, *, refresh: bool = False) -> list[Site]:
        self._ensure_site_tree(refresh=refresh)
        assert self._site_tree is not None
        return list(self._site_tree.sites)

    def list_departments(self, *, refresh: bool = False) -> list[Department]:
        self._ensure_departments(refresh=refresh)
        assert self._departments is not None
        return list(self._departments)

    def list_permissions(
        self,
        *,
        scope: Literal["pos", "backoffice"],
        refresh: bool = False,
    ) -> list[Permission]:
        if scope == "pos":
            self._ensure_pos_permissions(refresh=refresh)
            assert self._pos_permissions is not None
            return list(self._pos_permissions)
        else:
            self._ensure_bo_permissions(refresh=refresh)
            assert self._bo_permissions is not None
            return list(self._bo_permissions)

    def is_pos_user_id_available(
        self, pos_user_id: int, *, refresh: bool = False
    ) -> bool:
        """Return True if no existing employee uses this POS User ID.

        The check uses a cached per-tenant employee index built lazily from
        `/employee?limit=10000&active=all` and `/user/create`.
        """
        self._ensure_employee_index(refresh=refresh)
        assert self._employee_index is not None
        return pos_user_id not in self._employee_index.by_pos_user_id

    def is_email_available(self, email: str, *, refresh: bool = False) -> bool:
        """Return True if no existing employee uses this email (case-insensitive)."""
        self._ensure_employee_index(refresh=refresh)
        assert self._employee_index is not None
        return email.strip().lower() not in self._employee_index.by_email

    def is_phone_available(self, phone: str, *, refresh: bool = False) -> bool:
        """Return True if no existing employee uses this phone number.

        The phone argument is normalized to digits-only before comparison.
        """
        self._ensure_employee_index(refresh=refresh)
        assert self._employee_index is not None
        normalized = _DIGITS_RE.sub("", phone)
        return normalized not in self._employee_index.by_phone

    def create_employee(
        self,
        *,
        first_name: str,
        last_name: str,
        phone: str,
        email: str,
        pos_user_id: int,
        wage_rate: Decimal | float,
        start_date: datetime,
        available_sites: list[str] | Literal["all"],
        permission: str,
        pos_pin: int | None = None,
        overtime_wage_rate: Decimal | float | None = None,
        departments: list[str] | None = None,
        adp_employee_id: str | None = None,
        emergency_contact_name: str | None = None,
        emergency_contact_phone: str | None = None,
        requires_backoffice: bool = False,
        backoffice_username: str | None = None,
        backoffice_password: str | None = None,
    ) -> EmployeeCreated:
        self._ensure_site_tree()
        self._ensure_departments()
        self._ensure_pos_permissions()
        self._ensure_employee_index()
        if requires_backoffice:
            self._ensure_bo_permissions()

        req = CreateEmployeeRequest(
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
            pos_user_id=pos_user_id,
            pos_pin=pos_pin,
            wage_rate=Decimal(str(wage_rate)),
            overtime_wage_rate=Decimal(str(overtime_wage_rate))
            if overtime_wage_rate is not None
            else None,
            start_date=start_date,
            available_sites=available_sites,
            departments=departments,
            permission=permission,
            adp_employee_id=adp_employee_id,
            emergency_contact_name=emergency_contact_name,
            emergency_contact_phone=emergency_contact_phone,
            requires_backoffice=requires_backoffice,
            backoffice_username=backoffice_username,
            backoffice_password=backoffice_password,
        )
        assert self._site_tree is not None
        assert self._departments is not None
        assert self._pos_permissions is not None
        assert self._pos_permission_schema is not None
        assert self._employee_index is not None
        return _create_employee(
            session=self._session,
            request=req,
            site_tree=self._site_tree,
            departments=self._departments,
            pos_permissions=self._pos_permissions,
            pos_permission_schema=self._pos_permission_schema,
            bo_permissions=self._bo_permissions,
            employee_index=self._employee_index,
        )

    def disable_employee(
        self,
        *,
        pos_user_id: int | None = None,
        email: str | None = None,
    ) -> EmployeeDisabled:
        req = DisableEmployeeRequest(pos_user_id=pos_user_id, email=email)
        result = _disable_employee(session=self._session, request=req)
        # Invalidate caches that may now be stale
        self._employee_index = None
        self._employee_list_html = None
        return result

    def create_backoffice_user(
        self,
        *,
        username: str,
        email: str,
        permission: str,
        password: str | None = None,
        link_to_employee_pos_user_id: str | None = None,
        link_to_employee_email: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        available_sites: list[str] | Literal["all"] = "all",
    ) -> BackofficeUserCreated:
        self._ensure_site_tree()
        self._ensure_bo_permissions()

        req = CreateBackofficeUserRequest(
            username=username,
            email=email,
            password=password,
            permission=permission,
            link_to_employee_pos_user_id=link_to_employee_pos_user_id,
            link_to_employee_email=link_to_employee_email,
            first_name=first_name,
            last_name=last_name,
            available_sites=available_sites,
        )
        assert self._site_tree is not None
        assert self._bo_permissions is not None

        if req.link_to_employee_pos_user_id or req.link_to_employee_email:
            employee_id = self._lookup_employee_id_for_link(
                pos_user_id=req.link_to_employee_pos_user_id,
                email=req.link_to_employee_email,
            )
            bo_perm, _ = resolve_permission(req.permission, self._bo_permissions)
            return create_linked_backoffice_user(
                session=self._session,
                username=req.username,
                email=req.email,
                password=req.password,
                linked_employee_id=employee_id,
                permission=bo_perm,
                site_tree=self._site_tree,
                available_sites=req.available_sites,
            )
        return create_standalone_backoffice_user(
            session=self._session,
            request=req,
            site_tree=self._site_tree,
            bo_permissions=self._bo_permissions,
        )

    def _ensure_site_tree(self, *, refresh: bool = False) -> None:
        if refresh or self._site_tree is None:
            resp = self._session.get("/employee/create")
            self._site_tree = parse_site_tree(resp.text)

    def _ensure_departments(self, *, refresh: bool = False) -> None:
        if refresh or self._departments is None:
            resp = self._session.get("/employee/create")
            self._departments = parse_departments(resp.text)

    def _ensure_pos_permissions(self, *, refresh: bool = False) -> None:
        if not refresh and self._pos_permissions is not None:
            return
        self._ensure_employee_list_html(refresh=refresh)
        assert self._employee_list_html is not None
        m = _EMP_PERMISSIONS_LINK_RE.search(self._employee_list_html)
        if m is None:
            raise NotFoundError(
                "cannot populate POS permission schema — no existing employee found"
            )
        first_employee_id = int(m.group(1))
        resp = self._session.get(f"/employee/permissions/{first_employee_id}")
        templates, schema = parse_permissions_and_schema(resp.text, scope="pos")
        self._pos_permissions = templates
        self._pos_permission_schema = schema

    def _ensure_bo_permissions(self, *, refresh: bool = False) -> None:
        if not refresh and self._bo_permissions is not None:
            return
        user_list_resp = self._session.get("/user")
        m = _USER_PERMISSIONS_LINK_RE.search(user_list_resp.text)
        if m is None:
            raise NotFoundError(
                "cannot populate BO permission templates — no existing BO user found"
            )
        first_user_id = int(m.group(1))
        resp = self._session.get(f"/user/permissions/{first_user_id}")
        templates, _ = parse_permissions_and_schema(resp.text, scope="backoffice")
        self._bo_permissions = templates

    def _ensure_employee_list_html(self, *, refresh: bool = False) -> None:
        if refresh or self._employee_list_html is None:
            resp = self._session.get("/employee?limit=10000&active=all")
            self._employee_list_html = resp.text

    def _ensure_employee_index(self, *, refresh: bool = False) -> None:
        if not refresh and self._employee_index is not None:
            return
        self._ensure_employee_list_html(refresh=refresh)
        user_create_resp = self._session.get("/user/create")
        assert self._employee_list_html is not None
        self._employee_index = build_employee_index(
            employee_list_html=self._employee_list_html,
            user_create_html=user_create_resp.text,
        )

    def _lookup_employee_id_for_link(
        self,
        *,
        pos_user_id: str | None,
        email: str | None,
    ) -> int:
        self._ensure_employee_index()
        assert self._employee_index is not None
        if pos_user_id is not None:
            try:
                pid = int(pos_user_id)
            except ValueError:
                raise NotFoundError(
                    f"link_to_employee_pos_user_id={pos_user_id!r} is not an integer"
                )
            emp_id = self._employee_index.by_pos_user_id.get(pid)
            if emp_id is None:
                raise NotFoundError(
                    f"no employee found with pos_user_id={pid} for BO user linking"
                )
            return emp_id
        if email is not None:
            emp_id = self._employee_index.by_email.get(email.strip().lower())
            if emp_id is None:
                raise NotFoundError(
                    f"no employee found with email={email!r} for BO user linking"
                )
            return emp_id
        raise ValueError("link_to_employee_pos_user_id or link_to_employee_email required")
