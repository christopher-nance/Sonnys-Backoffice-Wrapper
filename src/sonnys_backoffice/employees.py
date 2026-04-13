"""create_employee / disable_employee orchestration and form builders."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from bs4 import BeautifulSoup

from .exceptions import (
    BackofficeServerError,
    DuplicateError,
    NotFoundError,
    ValidationError,
)
from .models import (
    CreateEmployeeRequest,
    Department,
    DisableEmployeeRequest,
    EmployeeCreated,
    EmployeeDisabled,
    Permission,
    PermissionFieldMeta,
)
from .passwords import generate_pos_pin
from .sites import SiteTree

_NEW_EMP_ID_RE = re.compile(r"/employee/(?:edit|permissions|compensation)/(\d+)")

_EMP_ID_RE = re.compile(r"/employee/(?:edit|permissions|compensation)/(\d+)")
_DIGITS_ONLY_RE = re.compile(r"\D")


@dataclass
class EmployeeIndex:
    """Per-tenant employee index, keyed by POS User ID, email, and phone."""

    by_pos_user_id: dict[int, int] = field(default_factory=dict)
    by_email: dict[str, int] = field(default_factory=dict)
    by_phone: dict[str, int] = field(default_factory=dict)

    def check(
        self,
        *,
        pos_user_id: int,
        email: str,
        phone: str,
    ) -> None:
        """Raise DuplicateError if any of the three fields collides."""
        if pos_user_id in self.by_pos_user_id:
            existing = self.by_pos_user_id[pos_user_id]
            raise DuplicateError(
                f"pos_user_id={pos_user_id} already exists on employee_id={existing}"
            )
        normalized_email = email.strip().lower()
        if normalized_email in self.by_email:
            existing = self.by_email[normalized_email]
            raise DuplicateError(
                f"email={email!r} already exists on employee_id={existing}"
            )
        normalized_phone = _DIGITS_ONLY_RE.sub("", phone)
        if normalized_phone in self.by_phone:
            existing = self.by_phone[normalized_phone]
            raise DuplicateError(
                f"phone={phone!r} (normalized: {normalized_phone}) "
                f"already exists on employee_id={existing}"
            )


def parse_employee_list(html: str) -> tuple[dict[int, int], dict[str, int]]:
    """Parse /employee?limit=... HTML. Returns (pos_user_id_map, phone_map).

    Both maps are keyed by the respective field value and valued by employee_id.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="table-employees-list")
    if table is None:
        return {}, {}
    pos_map: dict[int, int] = {}
    phone_map: dict[str, int] = {}
    for row in table.find_all("tr"):
        emp_id: int | None = None
        for a in row.find_all("a", href=True):
            m = _EMP_ID_RE.search(a["href"])
            if m:
                emp_id = int(m.group(1))
                break
        if emp_id is None:
            continue
        pos_cell = row.find("td", class_="employees-col-pos-user-id")
        phone_cell = row.find("td", class_="employees-col-phone")
        if pos_cell is not None:
            pos_text = pos_cell.get_text(strip=True)
            if pos_text.isdigit():
                pos_map[int(pos_text)] = emp_id
        if phone_cell is not None:
            phone_digits = _DIGITS_ONLY_RE.sub("", phone_cell.get_text(strip=True))
            if phone_digits:
                phone_map[phone_digits] = emp_id
    return pos_map, phone_map


def parse_user_create_employee_options(html: str) -> dict[str, int]:
    """Parse /user/create HTML. Returns {email: employee_id} from `user[employeeId]` options."""
    soup = BeautifulSoup(html, "html.parser")
    sel = soup.find("select", attrs={"name": "user[employeeId]"})
    if sel is None:
        return {}
    email_map: dict[str, int] = {}
    for opt in sel.find_all("option"):
        val = (opt.get("value") or "").strip()
        if not val:
            continue
        try:
            emp_id = int(val)
        except ValueError:
            continue
        email = (opt.get("data-email") or "").strip().lower()
        if email:
            email_map[email] = emp_id
    return email_map


def build_employee_index(
    *,
    employee_list_html: str,
    user_create_html: str,
) -> EmployeeIndex:
    """Combine both sources into a single EmployeeIndex."""
    pos_map, phone_map = parse_employee_list(employee_list_html)
    email_map = parse_user_create_employee_options(user_create_html)
    return EmployeeIndex(
        by_pos_user_id=pos_map,
        by_email=email_map,
        by_phone=phone_map,
    )


def find_employee_in_list_html(
    html: str,
    *,
    pos_user_id: int | None = None,
    email: str | None = None,
) -> int:
    """Scan /employee list HTML for a matching row, return the employee_id.

    Employee IDs are extracted from the action links in the edit/permissions/
    compensation columns. POS User ID matching scans the visible row text.
    Email matching usually fails because emails are not in the list columns —
    callers should use `build_employee_index` + `parse_user_create_employee_options`
    for email lookup instead.
    """
    if pos_user_id is None and email is None:
        raise ValueError("pos_user_id or email is required")
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="table-employees-list")
    if table is None:
        raise NotFoundError("employee list table not found in HTML")
    pos_user_id_str = str(pos_user_id) if pos_user_id is not None else None
    email_lower = email.lower() if email is not None else None
    for row in table.find_all("tr"):
        emp_id: int | None = None
        for a in row.find_all("a", href=True):
            m = _EMP_ID_RE.search(a["href"])
            if m:
                emp_id = int(m.group(1))
                break
        if emp_id is None:
            continue
        if pos_user_id_str is not None:
            pos_cell = row.find("td", class_="employees-col-pos-user-id")
            if pos_cell is not None and pos_cell.get_text(strip=True) == pos_user_id_str:
                return emp_id
        if email_lower is not None:
            row_text = row.get_text(" ", strip=True).lower()
            if email_lower in row_text:
                return emp_id
    raise NotFoundError(
        f"no employee found for "
        f"{'pos_user_id=' + str(pos_user_id) if pos_user_id is not None else 'email=' + (email or '')}"
    )


def build_employee_step1_payload(
    request: CreateEmployeeRequest,
    *,
    site_tree: SiteTree,
    departments_by_name: Mapping[str, int],
    wage_site_id: int,
) -> dict[str, Any]:
    """Build the `/employee/insert` payload.

    Field names are sourced from `tests/fixtures/payloads/e2e_create_employee_request.json`.
    """
    payload: dict[str, Any] = {
        "employee[firstName]": request.first_name,
        "employee[lastName]": request.last_name,
        "employee[phone]": request.phone,
        "employee[email]": request.email,
        "employee[startDate]": request.start_date.strftime("%m/%d/%Y"),
        "posCredential[POSLoginID]": str(request.pos_user_id),
        "posCredential[POSLoginPassword]": str(request.pos_pin) if request.pos_pin is not None else "",
        "wage[isHourly]": "1",
        "wage[regularRate]": f"{request.wage_rate:.2f}",
        "wage[overtimeRate]": f"{request.overtime_wage_rate:.2f}",
        "wage[isOvertimeEligible]": "1",
        "wage[siteId]": str(wage_site_id),
    }
    if request.adp_employee_id:
        payload["employee[adpEmployeeId]"] = request.adp_employee_id
    if request.emergency_contact_name:
        payload["employee[emergencyContactName]"] = request.emergency_contact_name
    if request.emergency_contact_phone:
        payload["employee[emergencyContactPhone]"] = request.emergency_contact_phone

    dept_ids: list[int] = []
    for dept_name in request.departments or []:
        did = departments_by_name.get(dept_name)
        if did is not None:
            dept_ids.append(did)
    payload["employee[departments][]"] = dept_ids

    resolved_sites = site_tree.resolve_all(request.available_sites)
    if site_tree.is_hierarchical:
        enabled_region_ids = {s.region_id for s in resolved_sites if s.region_id}
        enabled_district_ids = {s.district_id for s in resolved_sites if s.district_id}
        if request.available_sites == "all":
            payload["employee[isAllRegionsAllowed]"] = "1"
        else:
            payload["employee[isAllRegionsAllowed]"] = "0"
            payload["employee[disabledRegions][]"] = [
                r.id for r in site_tree.regions if r.id not in enabled_region_ids
            ]
            payload["employee[disabledDistricts][]"] = [
                d.id for d in site_tree.districts if d.id not in enabled_district_ids
            ]
            enabled_site_ids = {s.id for s in resolved_sites}
            for s in site_tree.sites:
                payload[f"employee[sites][{s.id}][isAvailable]"] = (
                    "1" if s.id in enabled_site_ids else "0"
                )
                payload[f"employee[sites][{s.id}][siteId]"] = str(s.id)
    else:
        if request.available_sites == "all":
            payload["employee[isAllSitesAllowed]"] = "1"
        else:
            payload["employee[isAllSitesAllowed]"] = "0"
            payload["employee[siteIds][]"] = [s.id for s in resolved_sites]

    return payload


def build_employee_step2_permissions_payload(
    *,
    permission: Permission,
    permission_schema: list[PermissionFieldMeta],
    employee_id: int,
    has_action_approval_authority: bool = False,
) -> list[tuple[str, str]]:
    """Build the `/employee/permissions/update` payload.

    Symfony's form binding treats the *presence* of a checkbox field as
    "checked = true" regardless of the value, so `hasGrantAccess` and
    `requiresOverride` are only emitted when their respective flags are set.
    """
    payload: list[tuple[str, str]] = [
        ("employeeId", str(employee_id)),
        ("templateId", str(permission.id)),
        ("hasActionApprovalAuthority", "1" if has_action_approval_authority else "0"),
    ]
    for perm in permission_schema:
        payload.append((f"permissions[{perm.id}][id]", str(perm.id)))
        payload.append((f"permissions[{perm.id}][label]", perm.label))
        payload.append((f"permissions[{perm.id}][description]", perm.description))
        if perm.id in permission.grants:
            payload.append((f"permissions[{perm.id}][hasGrantAccess]", "1"))
        if perm.id in permission.overrides:
            payload.append((f"permissions[{perm.id}][requiresOverride]", "1"))
    return payload


def _check_create_response(resp) -> None:
    """Raise on server errors or known failure signals in the response body."""
    if resp.status_code >= 500:
        raise BackofficeServerError(f"server error: HTTP {resp.status_code}")
    text = getattr(resp, "text", "") or ""
    lowered = text.lower()
    if "already exists" in lowered or "already taken" in lowered:
        raise DuplicateError("record with this email or POS User ID already exists")


def _extract_employee_id_from_response(resp) -> int:
    """Pull the new employee_id out of the /employee/insert response."""
    location = resp.headers.get("Location", "") if hasattr(resp, "headers") else ""
    url = getattr(resp, "url", "") or ""
    for candidate in (location, url):
        m = _NEW_EMP_ID_RE.search(candidate or "")
        if m:
            return int(m.group(1))
    text = getattr(resp, "text", "") or ""
    m = re.search(r'name="employee\[id\]"\s+value="(\d+)"', text)
    if m:
        return int(m.group(1))
    raise BackofficeServerError(
        "could not extract new employee_id from /employee/insert response"
    )


def create_employee(
    *,
    session,
    request: CreateEmployeeRequest,
    site_tree: SiteTree,
    departments: list[Department],
    pos_permissions: list[Permission],
    pos_permission_schema: list[PermissionFieldMeta],
    bo_permissions: list[Permission] | None = None,
    employee_index: EmployeeIndex | None = None,
) -> EmployeeCreated:
    """Orchestrate the two-step employee creation flow.

    Pre-flight uniqueness check → POST /employee/insert → POST /employee/permissions/update.
    """
    from .permissions import resolve_permission

    warnings_list: list[str] = []

    pos_pin = request.pos_pin if request.pos_pin is not None else generate_pos_pin()
    resolved_request = request.model_copy(update={"pos_pin": pos_pin})

    if employee_index is not None:
        employee_index.check(
            pos_user_id=resolved_request.pos_user_id,
            email=resolved_request.email,
            phone=resolved_request.phone,
        )

    pos_perm, perm_warnings = resolve_permission(request.permission, pos_permissions)
    warnings_list.extend(perm_warnings)

    resolved_sites_for_wage = site_tree.resolve_all(resolved_request.available_sites)
    if not resolved_sites_for_wage:
        raise ValidationError("available_sites is empty — cannot resolve wage attribution site")
    wage_site = resolved_sites_for_wage[0]

    departments_by_name = {d.name: d.id for d in departments}

    step1_payload = build_employee_step1_payload(
        resolved_request,
        site_tree=site_tree,
        departments_by_name=departments_by_name,
        wage_site_id=wage_site.id,
    )
    resp1 = session.post("/employee/insert", data=step1_payload)
    _check_create_response(resp1)
    employee_id = _extract_employee_id_from_response(resp1)

    step2_payload = build_employee_step2_permissions_payload(
        permission=pos_perm,
        permission_schema=pos_permission_schema,
        employee_id=employee_id,
    )
    resp2 = session.post("/employee/permissions/update", data=step2_payload)
    _check_create_response(resp2)

    bo_user_id: int | None = None
    bo_password: str | None = None
    if resolved_request.requires_backoffice:
        from .bo_users import create_linked_backoffice_user

        bo_perm, bo_warnings = resolve_permission(
            resolved_request.permission, bo_permissions or []
        )
        warnings_list.extend(bo_warnings)
        bo_result = create_linked_backoffice_user(
            session=session,
            username=resolved_request.backoffice_username,
            email=resolved_request.email,
            password=resolved_request.backoffice_password,
            linked_employee_id=employee_id,
            permission=bo_perm,
            site_tree=site_tree,
            available_sites=resolved_request.available_sites,
        )
        bo_user_id = bo_result.user_id
        bo_password = bo_result.password
        warnings_list.extend(bo_result.warnings)

    return EmployeeCreated(
        employee_id=employee_id,
        pos_user_id=resolved_request.pos_user_id,
        pos_pin=pos_pin,
        first_name=resolved_request.first_name,
        last_name=resolved_request.last_name,
        email=resolved_request.email,
        backoffice_user_id=bo_user_id,
        backoffice_username=resolved_request.backoffice_username,
        backoffice_password=bo_password,
        permission_applied=pos_perm.name,
        sites_granted=[s.name for s in site_tree.resolve_all(resolved_request.available_sites)],
        departments=list(resolved_request.departments or []),
        wage_site=wage_site.name,
        warnings=warnings_list,
    )


_TEXTUAL_INPUT_TYPES = frozenset(
    {"text", "hidden", "number", "email", "tel", "password", "search", "url", "date", "time"}
)


def _parse_edit_form_into_payload(
    html: str,
    *,
    drop_fields: set[str],
) -> list[tuple[str, str]]:
    """Parse an `/employee/edit/<id>` form into POST field tuples.

    - Text/hidden/number/email/tel/password inputs are always included with their
      current value (empty string if no value).
    - Checkboxes and radios are included only if currently checked.
    - Select single: include the currently-selected option (or the first non-empty
      option if none is selected).
    - Select multiple: include every selected option.
    - Textareas are included with their current text content.
    - Inputs carrying the `disabled` attribute are skipped (browsers don't submit
      disabled fields).
    - Fields in `drop_fields` are always excluded.
    """
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", action=re.compile(r"/employee/update"))
    if form is None:
        raise BackofficeServerError("could not locate /employee/update form on edit page")

    out: list[tuple[str, str]] = []
    for el in form.find_all(["input", "select", "textarea"]):
        name = el.get("name")
        if not name or name in drop_fields:
            continue
        if el.get("disabled") is not None:
            continue
        if el.name == "input":
            t = (el.get("type") or "text").lower()
            if t in _TEXTUAL_INPUT_TYPES:
                out.append((name, el.get("value") or ""))
            elif t == "checkbox":
                if el.has_attr("checked"):
                    out.append((name, el.get("value") or "on"))
            elif t == "radio":
                if el.has_attr("checked"):
                    out.append((name, el.get("value") or ""))
            elif t in ("submit", "button", "reset", "image", "file"):
                continue
            else:
                out.append((name, el.get("value") or ""))
        elif el.name == "select":
            if el.has_attr("multiple"):
                for opt in el.find_all("option"):
                    if opt.has_attr("selected"):
                        out.append((name, opt.get("value") or ""))
            else:
                sel_opt = next(
                    (o for o in el.find_all("option") if o.has_attr("selected")),
                    None,
                )
                if sel_opt is None:
                    sel_opt = next(
                        (o for o in el.find_all("option") if (o.get("value") or "").strip()),
                        None,
                    )
                if sel_opt is not None:
                    out.append((name, sel_opt.get("value") or ""))
        elif el.name == "textarea":
            out.append((name, el.get_text()))
    return out


def disable_employee(
    *,
    session,
    request: DisableEmployeeRequest,
) -> EmployeeDisabled:
    """Disable an existing employee via the full-form round-trip.

    Symfony's form binding treats the *presence* of `employee[isActive]` as
    "checked = true" regardless of value, so the only reliable disable is to
    POST every other form field unchanged and omit `isActive` entirely.
    """
    list_resp = session.get("/employee?limit=10000&active=all")
    _check_create_response(list_resp)
    employee_id = find_employee_in_list_html(
        list_resp.text,
        pos_user_id=request.pos_user_id,
        email=request.email,
    )

    edit_resp = session.get(f"/employee/edit/{employee_id}")
    _check_create_response(edit_resp)
    payload = _parse_edit_form_into_payload(
        edit_resp.text, drop_fields={"employee[isActive]"}
    )
    if not any(name == "employee[id]" for name, _ in payload):
        payload.append(("employee[id]", str(employee_id)))

    update_resp = session.post("/employee/update", data=payload, allow_redirects=False)
    _check_create_response(update_resp)

    verify_resp = session.get(f"/employee/edit/{employee_id}")
    soup = BeautifulSoup(verify_resp.text, "html.parser")
    active_input = soup.find("input", attrs={"name": "employee[isActive]"})
    still_active = active_input is not None and active_input.has_attr("checked")
    if still_active:
        raise BackofficeServerError(
            f"disable POST accepted but employee {employee_id} is still active — "
            "full-form round-trip did not take effect"
        )

    resolved_pos_user_id = request.pos_user_id if request.pos_user_id is not None else 0
    return EmployeeDisabled(
        employee_id=employee_id,
        pos_user_id=resolved_pos_user_id,
        email=request.email,
        disabled_at=datetime.now(timezone.utc),
    )
