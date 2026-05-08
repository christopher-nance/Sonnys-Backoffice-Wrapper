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
    find_employee_in_list_html,
)
from .employees import (
    create_employee as _create_employee,
)
from .employees import (
    disable_employee as _disable_employee,
)
from .employees import (
    modify_employee as _modify_employee,
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
    EmployeeModified,
    ModifyEmployeeRequest,
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
        """Create a new client for a single Sonny's Backoffice tenant.

        Login is deferred until the first request that needs the session
        (lazy). Use as a context manager to guarantee session cleanup:

            with SonnysBackofficeClient(...) as client:
                ...

        Args:
            subdomain: Tenant subdomain, e.g. ``"washu"`` for
                ``https://washu.sonnyscontrols.com``.
            username: Backoffice bot user username.
            password: Backoffice bot user password.
            timeout: Per-request HTTP timeout in seconds. Defaults to 30.
            user_agent: Optional custom User-Agent header.
        """
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

    def __enter__(self) -> SonnysBackofficeClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP session.

        Called automatically by ``__exit__`` when used as a context manager.
        """
        self._session.close()

    def list_sites(self, *, refresh: bool = False) -> list[Site]:
        """List all sites the bot user can see on the tenant.

        The result is cached on the client after the first call. Pass
        ``refresh=True`` to re-fetch.

        Args:
            refresh: If True, bypass the cache and re-fetch.

        Returns:
            list[Site]: Every site visible to the bot user. On a hierarchical
            tenant the returned ``Site`` objects carry ``district_id`` and
            ``region_id``; on a flat tenant those fields are ``None``.
        """
        self._ensure_site_tree(refresh=refresh)
        assert self._site_tree is not None
        return list(self._site_tree.sites)

    def list_departments(self, *, refresh: bool = False) -> list[Department]:
        """List the department options configured on the tenant.

        Args:
            refresh: If True, bypass the cache and re-fetch.

        Returns:
            list[Department]: Every department option, e.g. Cashier, Greeter,
            Line, Management.
        """
        self._ensure_departments(refresh=refresh)
        assert self._departments is not None
        return list(self._departments)

    def list_permissions(
        self,
        *,
        scope: Literal["pos", "backoffice"],
        refresh: bool = False,
    ) -> list[Permission]:
        """List the role templates available on the tenant for a given scope.

        POS templates come from ``/employee/permissions/<id>`` on an existing
        employee; Backoffice templates come from ``/user/permissions/<id>``
        on an existing BO user. Both lookups are cached per scope.

        Args:
            scope: ``"pos"`` for POS employee templates, ``"backoffice"`` for
                Backoffice user templates.
            refresh: If True, bypass the cache and re-fetch.

        Returns:
            list[Permission]: Every template on the tenant for the requested
            scope. POS templates carry ``grants`` and ``overrides`` ID sets;
            Backoffice templates are name-only in Milestone 1.

        Raises:
            NotFoundError: If the tenant has no existing records from which to
                extract templates (e.g., an empty tenant with no employees).
        """
        if scope == "pos":
            self._ensure_pos_permissions(refresh=refresh)
            assert self._pos_permissions is not None
            return list(self._pos_permissions)
        else:
            self._ensure_bo_permissions(refresh=refresh)
            assert self._bo_permissions is not None
            return list(self._bo_permissions)

    def is_pos_user_id_available(self, pos_user_id: int, *, refresh: bool = False) -> bool:
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
        """Create a new POS employee, optionally with a linked Backoffice user.

        The call goes through a two-step flow:

        1. ``POST /employee/insert`` with personal, wage, department, and site
           fields.
        2. ``POST /employee/permissions/update`` with the full permission
           matrix for the resolved template.

        If ``requires_backoffice=True``, a third step creates the linked BO
        user via ``POST /user/insert``. Note that in Milestone 1 the BO user's
        permission template is **not** applied automatically and must be
        assigned manually via the Backoffice UI — see the
        ``Creating a Backoffice user`` guide.

        Args:
            first_name: Employee first name. Leading/trailing whitespace is stripped.
            last_name: Employee last name.
            phone: Phone number. 9 or 10 digits after non-digit characters
                are stripped.
            email: Email address. Must contain a valid ``@domain.tld``.
            pos_user_id: Caller-assigned unique POS login ID. Must be unique
                per tenant. Pre-flight with ``is_pos_user_id_available``.
            wage_rate: Hourly wage in dollars. Prefer ``Decimal`` to avoid
                floating-point drift.
            start_date: Employment start date.
            available_sites: List of site *names* or the literal ``"all"``.
                Unknown names raise ``LookupError`` before any HTTP call.
            permission: POS template name. Matched case-insensitively; unknown
                names fall back to ``"General User"`` with a warning.
            pos_pin: 5-digit POS PIN integer (10000-99999). If ``None``, a
                random PIN is generated. The final value is always returned
                in the result.
            overtime_wage_rate: Overtime hourly wage. Defaults to
                ``wage_rate * 1.5``.
            departments: Department names. ``"Greeter"`` is always auto-added
                if omitted — see the guide for why.
            adp_employee_id: ADP payroll employee ID, if applicable.
            emergency_contact_name: Optional emergency contact name.
            emergency_contact_phone: Optional emergency contact phone (same
                validation as ``phone``).
            requires_backoffice: If True, also creates a linked BO user.
            backoffice_username: BO username. Required when
                ``requires_backoffice=True``.
            backoffice_password: BO password. If ``None``, a 12-character
                random password is generated.

        Returns:
            EmployeeCreated: The created record including the auto-generated
            POS PIN, resolved permission, wage attribution site, and any
            warnings (permission fallbacks, BO M1 deferral, etc.).

        Raises:
            ValidationError: If any input fails validation or Backoffice
                rejects the form.
            DuplicateError: If pos_user_id, email, or phone already exists on
                the tenant (pre-flight or server-side).
            AuthenticationError: If login or re-authentication fails.
            BackofficeServerError: If Backoffice returns an unexpected
                response (HTTP 5xx, unparseable HTML, etc.).
            LookupError: If ``available_sites`` contains an unknown site name.
        """
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
        result = _create_employee(
            session=self._session,
            request=req,
            site_tree=self._site_tree,
            departments=self._departments,
            pos_permissions=self._pos_permissions,
            pos_permission_schema=self._pos_permission_schema,
            bo_permissions=self._bo_permissions,
            employee_index=self._employee_index,
        )
        self._employee_index = None
        self._employee_list_html = None
        return result

    def disable_employee(
        self,
        *,
        pos_user_id: int | None = None,
        email: str | None = None,
    ) -> EmployeeDisabled:
        """Disable an employee looked up by POS User ID or email.

        Disable uses a full-form round-trip: fetch the employee list to
        resolve the internal employee_id, GET the edit form, parse every
        field, re-POST with ``employee[isActive]`` **omitted** (Symfony binds
        checkbox presence as true regardless of value), and re-GET to verify
        the change took effect.

        Exactly one of ``pos_user_id`` or ``email`` is required.

        Args:
            pos_user_id: POS User ID to look up.
            email: Email to look up. Note: the employee list page does not
                usually contain an email column, so email lookup may fail
                with ``NotFoundError`` even when the employee exists.
                Prefer ``pos_user_id`` when possible.

        Returns:
            EmployeeDisabled: The internal employee_id, echoed lookup key,
            and the UTC timestamp of the disable.

        Raises:
            ValidationError: If neither or both lookup keys are provided.
            NotFoundError: If no employee matches the lookup key.
            BackofficeServerError: If the disable POST is accepted but the
                verification GET shows the employee is still active (the
                full-form round-trip didn't take effect — usually means the
                form structure has changed).
            AuthenticationError: If login or re-authentication fails.
        """
        req = DisableEmployeeRequest(pos_user_id=pos_user_id, email=email)
        result = _disable_employee(session=self._session, request=req)
        self._employee_index = None
        self._employee_list_html = None
        return result

    def modify_employee(
        self,
        *,
        pos_user_id: int | None = None,
        email: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        phone: str | None = None,
        new_email: str | None = None,
        departments: list[str] | None = None,
        available_sites: list[str] | Literal["all"] | None = None,
        adp_employee_id: str | None = None,
        emergency_contact_name: str | None = None,
        emergency_contact_phone: str | None = None,
        wage_rate: Decimal | float | None = None,
        overtime_wage_rate: Decimal | float | None = None,
        permission: str | None = None,
    ) -> EmployeeModified:
        """Modify an existing employee's properties, compensation, or permission template.

        Looks up the employee by ``pos_user_id`` or ``email`` (exactly one
        required), then applies only the changes you provide.  Unchanged fields
        are round-tripped from the current form state.

        Three independent forms may be submitted depending on which arguments
        are provided:

        - **Properties** (name, phone, email, departments, emergency contact,
          ADP ID) → ``POST /employee/update``
        - **Compensation** (wage rate, overtime rate) → ``POST
          /employee/compensation/update`` — creates a new wage record
          effective today.
        - **Permission template** → ``POST /employee/permissions/update``
          with the full grant/override matrix.

        Args:
            pos_user_id: Lookup key — the employee's POS User ID.
            email: Lookup key — the employee's email (alternative to
                ``pos_user_id``).
            first_name: New first name.
            last_name: New last name.
            phone: New phone number (9-10 digits after stripping).
            new_email: New email address (distinct from the ``email`` lookup
                key).
            departments: New department list. ``"Greeter"`` is auto-added if
                omitted.
            available_sites: New site availability. Pass ``"all"`` for
                full access or a list of site names for limited access.
                Unknown site names raise ``LookupError``.
            adp_employee_id: New ADP employee ID.
            emergency_contact_name: New emergency contact name.
            emergency_contact_phone: New emergency contact phone.
            wage_rate: New hourly wage.  Prefer ``Decimal`` to avoid
                floating-point drift.
            overtime_wage_rate: New overtime hourly wage.  If omitted when
                ``wage_rate`` is provided and the employee is currently
                overtime-eligible, overtime is auto-computed at 1.5×.
            permission: POS template name.  Matched case-insensitively;
                unknown names fall back to ``"General User"`` with a warning.

        Returns:
            EmployeeModified: Confirmation of which forms were submitted and
            any warnings.
        """
        self._ensure_employee_list_html()
        assert self._employee_list_html is not None
        employee_id = find_employee_in_list_html(
            self._employee_list_html,
            pos_user_id=pos_user_id,
            email=email,
        )

        req = ModifyEmployeeRequest(
            pos_user_id=pos_user_id,
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            new_email=new_email,
            departments=departments,
            available_sites=available_sites,
            adp_employee_id=adp_employee_id,
            emergency_contact_name=emergency_contact_name,
            emergency_contact_phone=emergency_contact_phone,
            wage_rate=Decimal(str(wage_rate)) if wage_rate is not None else None,
            overtime_wage_rate=Decimal(str(overtime_wage_rate))
            if overtime_wage_rate is not None
            else None,
            permission=permission,
        )

        need_departments = req.departments is not None
        need_sites = req.available_sites is not None
        need_permissions = req.permission is not None

        if need_departments:
            self._ensure_departments()
        if need_sites:
            self._ensure_site_tree()
        if need_permissions:
            self._ensure_pos_permissions()

        assert not need_departments or self._departments is not None
        assert not need_sites or self._site_tree is not None
        assert not need_permissions or self._pos_permissions is not None
        assert not need_permissions or self._pos_permission_schema is not None

        result = _modify_employee(
            session=self._session,
            employee_id=employee_id,
            request=req,
            site_tree=self._site_tree if need_sites else None,
            departments=self._departments if need_departments else None,
            pos_permissions=self._pos_permissions if need_permissions else None,
            pos_permission_schema=self._pos_permission_schema
            if need_permissions
            else None,
        )

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
        """Create a Backoffice user — standalone or linked to an employee.

        In **linked mode** the user inherits site access from the employee
        (pass ``link_to_employee_pos_user_id`` or ``link_to_employee_email``).
        The linked employee must currently be active.

        In **standalone mode** the user gets its own profile (pass
        ``first_name`` and ``last_name``, no link fields).

        !!! warning "Milestone 1 limitation"
            The account is created successfully but the permission template is
            **not** assigned automatically. Click the shield icon next to the
            new user in the Backoffice ``/user`` list, pick a template, and
            save. A reminder is included in the returned ``warnings`` list.

        Args:
            username: New BO username. Must match the pattern
                ``[A-Za-z][\\w]{2,63}``.
            email: New user email.
            permission: BO template name for documentation and future use.
                Currently stored in the result but not applied to the server.
            password: BO password. If ``None``, a 12-character random
                password is generated and returned in the result.
            link_to_employee_pos_user_id: Link mode — look up the employee by
                POS User ID.
            link_to_employee_email: Link mode — look up the employee by email.
            first_name: Standalone mode — first name.
            last_name: Standalone mode — last name.
            available_sites: Documented in the result but not applied in M1
                BO-permission path. Defaults to ``"all"``.

        Returns:
            BackofficeUserCreated: The new user record, including the
            auto-generated password and a warning about the M1 deferral.

        Raises:
            ValidationError: If neither linked nor standalone mode fields are
                provided (or both are provided).
            NotFoundError: In linked mode, if the linked employee cannot be
                resolved.
            DuplicateError: If the username or email already exists.
            BackofficeServerError: If Backoffice rejects the insert (e.g.,
                linked employee is inactive) or returns an unexpected
                response.
            AuthenticationError: If login or re-authentication fails.
        """
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
            except ValueError as exc:
                raise NotFoundError(
                    f"link_to_employee_pos_user_id={pos_user_id!r} is not an integer"
                ) from exc
            emp_id = self._employee_index.by_pos_user_id.get(pid)
            if emp_id is None:
                raise NotFoundError(f"no employee found with pos_user_id={pid} for BO user linking")
            return emp_id
        if email is not None:
            emp_id = self._employee_index.by_email.get(email.strip().lower())
            if emp_id is None:
                raise NotFoundError(f"no employee found with email={email!r} for BO user linking")
            return emp_id
        raise ValueError("link_to_employee_pos_user_id or link_to_employee_email required")
