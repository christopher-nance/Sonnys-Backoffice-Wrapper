"""Permission name resolution and parsing."""
from __future__ import annotations

import warnings
from typing import Iterable, Literal

from bs4 import BeautifulSoup

from .models import Permission

_DEFAULT_FALLBACK = "General User"


def resolve_permission(
    requested: str,
    available: Iterable[Permission],
) -> tuple[Permission, list[str]]:
    """Resolve a permission name against the tenant's available list.

    Returns (matched_permission, warnings_list). Matching is case-insensitive.
    Unknown names fall back to "General User" with a warning. Raises ValueError
    if "General User" is not present in the available list (tenant misconfig).
    """
    available_list = list(available)
    target = requested.strip().lower()
    for perm in available_list:
        if perm.name.lower() == target:
            return perm, []

    fallback_msg = (
        f"permission {requested!r} not found in tenant, "
        f"falling back to {_DEFAULT_FALLBACK!r}"
    )
    warnings.warn(fallback_msg, stacklevel=2)
    for perm in available_list:
        if perm.name.lower() == _DEFAULT_FALLBACK.lower():
            return perm, [fallback_msg]
    raise ValueError(
        f"{_DEFAULT_FALLBACK!r} not found in tenant's permission list — "
        "cannot apply fallback. Check tenant role configuration."
    )


def parse_permissions(
    html: str, *, scope: Literal["pos", "backoffice"]
) -> list[Permission]:
    """Extract role templates from a captured permissions page.

    The POS page uses `<select name="templateId">` and the Backoffice page uses
    `<select name="template">`. Both carry option values with integer IDs.
    """
    soup = BeautifulSoup(html, "html.parser")
    perms: list[Permission] = []
    sel = soup.find("select", attrs={"name": "templateId"}) or soup.find(
        "select", attrs={"name": "template"}
    )
    if sel is None:
        return perms
    for opt in sel.find_all("option"):
        val = (opt.get("value") or "").strip()
        if not val:
            continue
        try:
            pid = int(val)
        except ValueError:
            continue
        perms.append(Permission(id=pid, name=opt.get_text(strip=True), scope=scope))
    return perms
