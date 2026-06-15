"""create_employee / disable_employee orchestration and form builders."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from bs4 import BeautifulSoup

from .exceptions import (
    AmbiguousMatchError,
    BackofficeServerError,
    DuplicateError,
    NotFoundError,
    ValidationError,
)
from .models import (
    CreateEmployeeRequest,
    Department,
    DisableEmployeeRequest,
    EmployeeCompensation,
    EmployeeCreated,
    EmployeeDisabled,
    EmployeeModified,
    EmployeePermission,
    EmployeeProfile,
    EmployeeSummary,
    ModifyEmployeeRequest,
    Permission,
    PermissionFieldMeta,
    WageRecord,
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
            raise DuplicateError(f"email={email!r} already exists on employee_id={existing}")
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


# ── read-surface parsers ─────────────────────────────────────────────────────

_MONEY_RE = re.compile(r"[\d,]+(?:\.\d+)?")


def _parse_money(text: str) -> Decimal | None:
    m = _MONEY_RE.search(text or "")
    if not m:
        return None
    return Decimal(m.group(0).replace(",", ""))


def _parse_mdy(text: str | None) -> date | None:
    if not text:
        return None
    try:
        return datetime.strptime(text.strip(), "%m/%d/%Y").date()
    except ValueError:
        return None


def _input_value(soup: BeautifulSoup, name: str) -> str | None:
    el = soup.find(["input", "textarea"], attrs={"name": name})
    if el is None:
        return None
    if el.name == "textarea":
        return el.get_text() or None
    return el.get("value") or el.get("data-value") or None


def parse_employee_summaries(html: str) -> list[EmployeeSummary]:
    """Parse the /employee roster page into lightweight summary rows."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="table-employees-list")
    out: list[EmployeeSummary] = []
    if table is None:
        return out
    for tr in table.find_all("tr"):
        emp_id: int | None = None
        for a in tr.find_all("a", href=True):
            m = _EMP_ID_RE.search(a["href"])
            if m:
                emp_id = int(m.group(1))
                break
        if emp_id is None:
            continue
        first = tr.find("td", class_="employees-col-first-name")
        last = tr.find("td", class_="employees-col-last-name")
        pos = tr.find("td", class_="employees-col-pos-user-id")
        phone = tr.find("td", class_="employees-col-phone")
        active = tr.find("td", class_="employees-col-active")
        pos_text = pos.get_text(strip=True) if pos else ""
        phone_digits = _DIGITS_ONLY_RE.sub("", phone.get_text(strip=True)) if phone else ""
        out.append(
            EmployeeSummary(
                employee_id=emp_id,
                pos_user_id=int(pos_text) if pos_text.isdigit() else None,
                first_name=first.get_text(strip=True) if first else "",
                last_name=last.get_text(strip=True) if last else "",
                phone=phone_digits or None,
                is_active=bool(active and active.find("i", class_="fa-check")),
            )
        )
    return out


def _normalize_name(value: str) -> str:
    return (value or "").strip().casefold()


def _phone_last10(phone: str | None) -> str:
    """Digits-only, last 10 — so a leading 1/country code doesn't matter."""
    digits = _DIGITS_ONLY_RE.sub("", phone or "")
    return digits[-10:]


def match_employees_by_name(
    rows: list[EmployeeSummary],
    *,
    first_name: str,
    last_name: str,
) -> list[EmployeeSummary]:
    """Roster rows whose first AND last name match, normalized (trim + casefold)."""
    fn = _normalize_name(first_name)
    ln = _normalize_name(last_name)
    return [
        r
        for r in rows
        if _normalize_name(r.first_name) == fn and _normalize_name(r.last_name) == ln
    ]


def resolve_employee_by_name(
    rows: list[EmployeeSummary],
    *,
    first_name: str,
    last_name: str,
    phone: str | None = None,
) -> EmployeeSummary:
    """Resolve a single employee by name, using phone as a tiebreaker.

    - Exactly one name match → return it.
    - Multiple name matches + ``phone`` → narrow by phone (digits-only, last 10).
      Exactly one remaining → return it.
    - Zero name matches → ``NotFoundError``.
    - Otherwise (still multiple, or phone narrowed to none/many) →
      ``AmbiguousMatchError`` with the candidate count and POS User IDs.
    """
    matches = match_employees_by_name(rows, first_name=first_name, last_name=last_name)
    if not matches:
        raise NotFoundError(f"no employee found with name {first_name!r} {last_name!r}")
    if len(matches) == 1:
        return matches[0]

    pool = matches
    if phone:
        target = _phone_last10(phone)
        narrowed = [r for r in matches if target and _phone_last10(r.phone) == target]
        if len(narrowed) == 1:
            return narrowed[0]
        if narrowed:
            pool = narrowed

    pos_ids = [r.pos_user_id for r in pool]
    detail = (
        "provide a phone number to disambiguate" if not phone else "phone did not narrow to one"
    )
    raise AmbiguousMatchError(
        f"name {first_name!r} {last_name!r} matched {len(pool)} employees "
        f"(pos_user_ids={pos_ids}); {detail}"
    )


def _parse_available_sites(soup: BeautifulSoup, site_tree: SiteTree | None):
    all_regions = soup.find("input", attrs={"name": "employee[isAllRegionsAllowed]"})
    all_sites = soup.find("input", attrs={"name": "employee[isAllSitesAllowed]"})
    if (all_regions and all_regions.has_attr("checked")) or (
        all_sites and all_sites.has_attr("checked")
    ):
        return "all"
    enabled_ids: set[int] = set()
    for el in soup.find_all("input"):
        n = el.get("name") or ""
        if n.endswith("][isAvailable]") and el.has_attr("checked"):
            inner = n[len("employee[sites][") :].split("]")[0]
            if inner.isdigit():
                enabled_ids.add(int(inner))
    id_to_name = {s.id: s.name for s in site_tree.sites} if site_tree else {}
    return sorted(id_to_name[i] for i in enabled_ids if i in id_to_name)


def parse_employee_profile(
    edit_html: str,
    *,
    site_tree: SiteTree | None = None,
    departments: list[Department] | None = None,
) -> EmployeeProfile:
    """Parse the /employee/edit page into an EmployeeProfile."""
    soup = BeautifulSoup(edit_html, "html.parser")
    emp_id_raw = _input_value(soup, "employee[id]")
    pos_raw = _input_value(soup, "posCredential[POSLoginID]")
    active = soup.find("input", attrs={"name": "employee[isActive]"})

    dept_by_id = {d.id: d.name for d in (departments or [])}
    dept_names: list[str] = []
    sel = soup.find("select", attrs={"name": "employee[departments][]"})
    if sel is not None:
        for opt in sel.find_all("option"):
            if opt.has_attr("selected"):
                v = (opt.get("value") or "").strip()
                if v.isdigit():
                    dept_names.append(dept_by_id.get(int(v), opt.get_text(strip=True)))

    return EmployeeProfile(
        employee_id=int(emp_id_raw) if emp_id_raw and emp_id_raw.isdigit() else 0,
        pos_user_id=int(pos_raw) if pos_raw and pos_raw.isdigit() else None,
        first_name=_input_value(soup, "employee[firstName]") or "",
        last_name=_input_value(soup, "employee[lastName]") or "",
        email=_input_value(soup, "employee[email]"),
        phone=_input_value(soup, "employee[phone]"),
        departments=dept_names,
        available_sites=_parse_available_sites(soup, site_tree),
        start_date=_parse_mdy(_input_value(soup, "employee[startDate]")),
        adp_employee_id=_input_value(soup, "employee[adpEmployeeId]"),
        emergency_contact_name=_input_value(soup, "employee[emergencyContactName]"),
        emergency_contact_phone=_input_value(soup, "employee[emergencyContactPhone]"),
        is_active=bool(active and active.has_attr("checked")),
    )


def parse_wage_history(comp_html: str) -> EmployeeCompensation:
    """Parse the compensation history table into current + historical WageRecords."""
    soup = BeautifulSoup(comp_html, "html.parser")
    table = soup.find("table", class_="table-employee-compensation-history")
    history: list[WageRecord] = []
    if table is None or table.find("tbody") is None:
        return EmployeeCompensation(current=None, history=[])
    for tr in table.find("tbody").find_all("tr"):
        wage = tr.find("td", class_="employee-compensation-col-wage")
        rate = _parse_money(wage.get_text() if wage else "")
        if rate is None:
            continue
        wtype = tr.find("td", class_="employee-compensation-col-wage-type")
        ot_elig = tr.find("td", class_="employee-compensation-col-overtime-eligible")
        ot_rate = tr.find("td", class_="employee-compensation-col-overtime-rate")
        eff = tr.find("td", class_="employee-compensation-col-effective-date")
        end = tr.find("td", class_="employee-compensation-col-end-date")
        end_text = end.get_text(strip=True) if end else ""
        history.append(
            WageRecord(
                wage_type=wtype.get_text(strip=True) if wtype else "",
                rate=rate,
                overtime_eligible=bool(ot_elig and ot_elig.find("i", class_="fa-check")),
                overtime_rate=_parse_money(ot_rate.get_text() if ot_rate else ""),
                effective_date=_parse_mdy(eff.get_text(strip=True)) if eff else None,
                end_date=_parse_mdy(end_text),
                is_current=(end is not None and not end_text),
            )
        )
    current = next((r for r in history if r.is_current), None)
    return EmployeeCompensation(current=current, history=history)


_PERM_ID_RE = re.compile(r"permissions\[(\d+)\]")


def parse_employee_permission(
    perm_html: str,
    *,
    pos_permissions: list[Permission] | None = None,
) -> EmployeePermission:
    """Parse the /employee/permissions page into the current grant state.

    ``template_name`` is the name of the template whose grant set exactly equals
    the employee's checked grants, or None when no template matches (custom).
    """
    soup = BeautifulSoup(perm_html, "html.parser")
    granted: set[int] = set()
    overrides: set[int] = set()
    for el in soup.find_all("input"):
        n = el.get("name") or ""
        if not el.has_attr("checked"):
            continue
        if n.endswith("][hasGrantAccess]"):
            m = _PERM_ID_RE.search(n)
            if m:
                granted.add(int(m.group(1)))
        elif n.endswith("][requiresOverride]"):
            m = _PERM_ID_RE.search(n)
            if m:
                overrides.add(int(m.group(1)))
    granted_fs = frozenset(granted)
    override_fs = frozenset(overrides)
    template_name: str | None = None
    for p in pos_permissions or []:
        if p.grants == granted_fs:
            template_name = p.name
            break
    return EmployeePermission(
        template_name=template_name,
        is_custom=template_name is None,
        granted_permission_ids=granted_fs,
        override_permission_ids=override_fs,
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
        "posCredential[POSLoginPassword]": str(request.pos_pin)
        if request.pos_pin is not None
        else "",
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
    enabled_ids = {s.id for s in resolved_sites}
    if site_tree.is_hierarchical:
        if request.available_sites == "all":
            payload["employee[isAllRegionsAllowed]"] = "1"
        else:
            # `employee[isAllRegionsAllowed]` is OMITTED on purpose: Symfony binds
            # checkbox *presence* as true regardless of value, so sending "0" would
            # grant all regions (the same gotcha disable_employee handles for
            # isActive). A site is marked unavailable by submitting only its
            # `siteId`; sites left unmentioned stay available. So we list the
            # complement (every non-granted site) to disable it.
            for s in site_tree.sites:
                if s.id not in enabled_ids:
                    payload[f"employee[sites][{s.id}][siteId]"] = str(s.id)
    else:
        if request.available_sites == "all":
            payload["employee[isAllSitesAllowed]"] = "1"
        else:
            payload["employee[siteIds][]"] = [
                s.id for s in site_tree.sites if s.id not in enabled_ids
            ]

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
    raise BackofficeServerError("could not extract new employee_id from /employee/insert response")


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

        bo_perm, bo_warnings = resolve_permission(resolved_request.permission, bo_permissions or [])
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

_EDIT_FORM_RE = re.compile(r"/employee/update")
_COMP_FORM_RE = re.compile(r"/employee/compensation/update")


def _latest_wage_effective_date(html: str) -> date | None:
    """Return the most recent effective date in the compensation history table.

    A new wage record must be effective strictly after the most recent existing
    record's effective date, so callers use this to compute the earliest legal
    effective date (``latest + 1 day``).
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="table-employee-compensation-history")
    if table is None:
        return None
    latest: date | None = None
    for td in table.find_all("td", class_="employee-compensation-col-effective-date"):
        text = td.get_text(strip=True)
        try:
            parsed = datetime.strptime(text, "%m/%d/%Y").date()
        except ValueError:
            continue
        if latest is None or parsed > latest:
            latest = parsed
    return latest


def _current_wage_overtime_eligible(html: str) -> bool | None:
    """Whether the employee's current wage record is overtime-eligible.

    Reads the active row (the one with no end date) of the compensation history
    table. Returns None if no current row is found.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="table-employee-compensation-history")
    if table is None or table.find("tbody") is None:
        return None
    for tr in table.find("tbody").find_all("tr"):
        end_cell = tr.find("td", class_="employee-compensation-col-end-date")
        if end_cell is None or end_cell.get_text(strip=True):
            continue  # ended row — skip; we want the active (no end date) one
        ot_cell = tr.find("td", class_="employee-compensation-col-overtime-eligible")
        if ot_cell is None:
            return None
        return ot_cell.find("i", class_="fa-check") is not None
    return None


def _parse_form_into_payload(
    html: str,
    *,
    form_action_re: re.Pattern[str],
    drop_fields: set[str] | None = None,
) -> list[tuple[str, str]]:
    """Parse a Symfony form into POST-ready field tuples.

    Works with any form matched by *form_action_re* (edit, compensation, etc.).

    - Text/hidden/number/email/tel/password inputs are always included with their
      current value (empty string if no value).
    - Checkboxes and radios are included only if currently checked.
    - Select single: include the currently-selected option (or the first non-empty
      option if none is selected).
    - Select multiple: include every selected option.
    - Textareas are included with their current text content.
    - Inputs carrying the ``disabled`` attribute are skipped (browsers don't submit
      disabled fields).
    - Fields in *drop_fields* are always excluded.
    """
    _drop = drop_fields or set()
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", action=form_action_re)
    if form is None:
        raise BackofficeServerError(
            f"could not locate form matching {form_action_re.pattern!r} in HTML"
        )

    out: list[tuple[str, str]] = []
    for el in form.find_all(["input", "select", "textarea"]):
        name = el.get("name")
        if not name or name in _drop:
            continue
        if el.get("disabled") is not None:
            continue
        if el.name == "input":
            t = (el.get("type") or "text").lower()
            if t in _TEXTUAL_INPUT_TYPES:
                val = el.get("value") or el.get("data-value") or ""
                out.append((name, val))
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


def _overlay_payload(
    payload: list[tuple[str, str]],
    overrides: dict[str, str | list[str]],
) -> list[tuple[str, str]]:
    """Apply field overrides to a parsed form payload.

    Single-value overrides (str) replace the first matching entry or are appended.
    Multi-value overrides (list[str]) remove all existing entries for that field
    name and append the new values.
    """
    multi_keys = {k for k, v in overrides.items() if isinstance(v, list)}
    single_keys = {k for k in overrides if k not in multi_keys}

    replaced: set[str] = set()
    result: list[tuple[str, str]] = []
    for name, value in payload:
        if name in multi_keys:
            continue
        if name in single_keys:
            if name not in replaced:
                result.append((name, overrides[name]))  # type: ignore[arg-type]
                replaced.add(name)
        else:
            result.append((name, value))

    for name in single_keys:
        if name not in replaced:
            result.append((name, overrides[name]))  # type: ignore[arg-type]

    for name in multi_keys:
        for val in overrides[name]:  # type: ignore[union-attr]
            result.append((name, val))

    return result


_PROPERTY_FIELD_MAP: dict[str, str] = {
    "first_name": "employee[firstName]",
    "last_name": "employee[lastName]",
    "phone": "employee[phone]",
    "new_email": "employee[email]",
    "adp_employee_id": "employee[adpEmployeeId]",
    "emergency_contact_name": "employee[emergencyContactName]",
    "emergency_contact_phone": "employee[emergencyContactPhone]",
}

_SITE_FIELD_PREFIXES = (
    "employee[isAllRegionsAllowed]",
    "employee[isAllSitesAllowed]",
    "employee[disabledRegions]",
    "employee[disabledDistricts]",
    "employee[isAllDistrictsAllowedByRegion]",
    "employee[isAllSitesAllowedByDistrict]",
    "employee[sites]",
    "employee[siteIds]",
)


def _build_site_availability_fields(
    site_tree: SiteTree,
    available_sites: list[str] | str,
) -> list[tuple[str, str]]:
    """Build site availability fields for a hierarchical or flat tenant.

    Encoding (verified live against the WashU tenant): the "all-regions" flag is
    OMITTED when restricting (Symfony binds checkbox *presence* as true, so
    sending it at all grants everything). A site is marked **unavailable** by
    submitting only its ``employee[sites][N][siteId]``; sites left unmentioned
    stay available. So we submit the *complement* — every non-granted site — to
    disable it, and say nothing about the granted ones.
    """
    resolved = site_tree.resolve_all(available_sites)
    fields: list[tuple[str, str]] = []

    if available_sites == "all":
        if site_tree.is_hierarchical:
            fields.append(("employee[isAllRegionsAllowed]", "1"))
        else:
            fields.append(("employee[isAllSitesAllowed]", "1"))
        return fields

    enabled_ids = {s.id for s in resolved}

    if site_tree.is_hierarchical:
        for s in site_tree.sites:
            if s.id not in enabled_ids:
                fields.append((f"employee[sites][{s.id}][siteId]", str(s.id)))
    else:
        for s in site_tree.sites:
            if s.id not in enabled_ids:
                fields.append(("employee[siteIds][]", str(s.id)))

    return fields


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
    payload = _parse_form_into_payload(
        edit_resp.text, form_action_re=_EDIT_FORM_RE, drop_fields={"employee[isActive]"}
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


def modify_employee(
    *,
    session,
    employee_id: int,
    request: ModifyEmployeeRequest,
    site_tree: SiteTree | None = None,
    departments: list[Department] | None = None,
    pos_permissions: list[Permission] | None = None,
    pos_permission_schema: list[PermissionFieldMeta] | None = None,
) -> EmployeeModified:
    """Modify an existing employee across up to three forms.

    Phase 1 — Properties: GET ``/employee/edit/{id}``, overlay changed fields,
    POST ``/employee/update``.

    Phase 2 — Compensation: GET ``/employee/compensation/{id}``, overlay wage
    fields, POST ``/employee/compensation/update`` (creates a new wage record
    effective today).

    Phase 3 — Permission template: build the full permission matrix and POST
    ``/employee/permissions/update``.

    Only phases with caller-provided changes are executed.
    """
    changes_applied: list[str] = []
    warnings_list: list[str] = []
    wage_effective: date | None = None

    has_property = any(
        getattr(request, attr) is not None
        for attr in (
            "first_name",
            "last_name",
            "phone",
            "new_email",
            "departments",
            "available_sites",
            "adp_employee_id",
            "emergency_contact_name",
            "emergency_contact_phone",
            "activate",
        )
    )

    if has_property:
        edit_resp = session.get(f"/employee/edit/{employee_id}")
        _check_create_response(edit_resp)
        payload = _parse_form_into_payload(
            edit_resp.text,
            form_action_re=_EDIT_FORM_RE,
        )

        overrides: dict[str, str | list[str]] = {}
        for attr, form_name in _PROPERTY_FIELD_MAP.items():
            val = getattr(request, attr)
            if val is not None:
                overrides[form_name] = val

        if request.departments is not None:
            dept_names = list(request.departments)
            if "Greeter" not in dept_names:
                dept_names.append("Greeter")
            dept_by_name = {d.name: d.id for d in (departments or [])}
            dept_ids = [str(dept_by_name[n]) for n in dept_names if n in dept_by_name]
            overrides["employee[departments][]"] = dept_ids

        payload = _overlay_payload(payload, overrides)

        if request.available_sites is not None and site_tree is not None:
            payload = [
                (n, v) for n, v in payload if not any(n.startswith(p) for p in _SITE_FIELD_PREFIXES)
            ]
            payload.extend(_build_site_availability_fields(site_tree, request.available_sites))

        if request.activate is not None:
            # Symfony binds checkbox presence as true, so reactivating means
            # emitting employee[isActive]=1; deactivating means omitting it.
            payload = [(n, v) for n, v in payload if n != "employee[isActive]"]
            if request.activate:
                payload.append(("employee[isActive]", "1"))

        if not any(name == "employee[id]" for name, _ in payload):
            payload.append(("employee[id]", str(employee_id)))

        resp = session.post("/employee/update", data=payload, allow_redirects=False)
        _check_create_response(resp)
        changes_applied.append("properties")
        if request.activate is not None:
            changes_applied.append("activated" if request.activate else "deactivated")

    if request.wage_rate is not None:
        comp_resp = session.get(f"/employee/compensation/{employee_id}")
        _check_create_response(comp_resp)
        payload = _parse_form_into_payload(
            comp_resp.text,
            form_action_re=_COMP_FORM_RE,
        )

        # The new wage record must be effective strictly after the most recent
        # existing record's effective date (else it silently fails to apply).
        # Default to today, but roll forward to latest+1 day on a same-day
        # collision. A caller-supplied date is clamped up to that minimum.
        today = datetime.now().date()
        latest_effective = _latest_wage_effective_date(comp_resp.text)
        min_effective = (latest_effective + timedelta(days=1)) if latest_effective else today
        desired = request.wage_effective_date.date() if request.wage_effective_date else today
        effective = max(desired, min_effective)
        wage_effective = effective
        if request.wage_effective_date and effective != desired:
            warnings_list.append(
                f"wage_effective_date {desired:%m/%d/%Y} is on/before the most recent "
                f"rate ({latest_effective:%m/%d/%Y}); clamped to {effective:%m/%d/%Y}"
            )

        comp_overrides: dict[str, str | list[str]] = {
            "wage[regularRate]": f"{request.wage_rate:.2f}",
            "wage[effectiveDate]": effective.strftime("%m/%d/%Y"),
        }

        # Preserve the employee's current overtime eligibility. The blank
        # "add wage" form always reports not-eligible, so read it from the
        # active wage row instead of the parsed form.
        ot_eligible = _current_wage_overtime_eligible(comp_resp.text)
        if ot_eligible is None:
            ot_eligible = any(name == "wage[isOvertimeEligible]" for name, _ in payload)
        if request.overtime_wage_rate is not None:
            comp_overrides["wage[overtimeRate]"] = f"{request.overtime_wage_rate:.2f}"
            ot_eligible = True
        elif ot_eligible:
            ot = (request.wage_rate * Decimal("1.5")).quantize(Decimal("0.01"))
            comp_overrides["wage[overtimeRate]"] = f"{ot:.2f}"

        # Re-emit the eligibility flag explicitly (presence = true in Symfony).
        payload = [(n, v) for n, v in payload if n != "wage[isOvertimeEligible]"]
        if ot_eligible:
            payload.append(("wage[isOvertimeEligible]", "1"))

        payload = _overlay_payload(payload, comp_overrides)

        resp = session.post(
            "/employee/compensation/update",
            data=payload,
            allow_redirects=False,
        )
        _check_create_response(resp)
        changes_applied.append("compensation")

    perm_applied: str | None = None
    if request.permission is not None:
        from .permissions import resolve_permission

        perm, perm_warnings = resolve_permission(
            request.permission,
            pos_permissions or [],
        )
        warnings_list.extend(perm_warnings)
        perm_payload = build_employee_step2_permissions_payload(
            permission=perm,
            permission_schema=pos_permission_schema or [],
            employee_id=employee_id,
        )
        resp = session.post("/employee/permissions/update", data=perm_payload)
        _check_create_response(resp)
        perm_applied = perm.name
        changes_applied.append("permission")

    return EmployeeModified(
        employee_id=employee_id,
        changes_applied=changes_applied,
        permission_applied=perm_applied,
        wage_rate=request.wage_rate,
        wage_effective_date=wage_effective,
        warnings=warnings_list,
    )
