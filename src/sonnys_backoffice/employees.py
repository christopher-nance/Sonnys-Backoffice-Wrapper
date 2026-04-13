"""create_employee / disable_employee orchestration and form builders."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from bs4 import BeautifulSoup

from .exceptions import DuplicateError
from .models import CreateEmployeeRequest, Permission, PermissionFieldMeta
from .sites import SiteTree

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
