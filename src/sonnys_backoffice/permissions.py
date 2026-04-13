"""Permission name resolution with case-insensitive matching and General User fallback."""
from __future__ import annotations

import warnings
from typing import Iterable

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
