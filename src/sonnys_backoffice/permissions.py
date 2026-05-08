"""Permission name resolution and parsing."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Literal

from bs4 import BeautifulSoup

from .exceptions import NotFoundError
from .models import Permission, PermissionFieldMeta


def resolve_permission(
    requested: str,
    available: Iterable[Permission],
) -> tuple[Permission, list[str]]:
    """Resolve a permission name against the tenant's available list.

    Returns ``(matched_permission, warnings_list)``. Matching is
    case-insensitive. Raises ``NotFoundError`` listing the available
    templates when the requested name doesn't match any.
    """
    available_list = list(available)
    target = requested.strip().lower()
    for perm in available_list:
        if perm.name.lower() == target:
            return perm, []

    available_names = [p.name for p in available_list]
    raise NotFoundError(
        f"permission template {requested!r} not found on this tenant. "
        f"Available templates: {available_names}"
    )


def parse_permissions_and_schema(
    html: str, *, scope: Literal["pos", "backoffice"]
) -> tuple[list[Permission], list[PermissionFieldMeta]]:
    """Parse a permissions page into (templates, schema).

    `templates` is the list of role templates from the `templateId`/`template`
    select, each carrying the grant and manager-override permission ID sets.
    `schema` is the tenant-wide permission metadata (id, label, description)
    extracted from the `permissions[N]` hidden-input matrix on the same page.
    """
    soup = BeautifulSoup(html, "html.parser")
    templates: list[Permission] = []
    sel = soup.find("select", attrs={"name": "templateId"}) or soup.find(
        "select", attrs={"name": "template"}
    )
    if sel is not None:
        for opt in sel.find_all("option"):
            val = (opt.get("value") or "").strip()
            if not val:
                continue
            try:
                tid = int(val)
            except ValueError:
                continue
            grants_raw = opt.get("data-permissions-set", "") or ""
            overrides_raw = opt.get("data-manager-override-permissions-set", "") or ""
            grants = frozenset(int(x) for x in grants_raw.split(",") if x.strip().isdigit())
            overrides = frozenset(int(x) for x in overrides_raw.split(",") if x.strip().isdigit())
            templates.append(
                Permission(
                    id=tid,
                    name=opt.get_text(strip=True),
                    scope=scope,
                    grants=grants,
                    overrides=overrides,
                )
            )

    schema: dict[int, PermissionFieldMeta] = {}
    _id_name_re = re.compile(r"permissions\[(\d+)\]\[id\]")
    for inp in soup.find_all("input", attrs={"name": _id_name_re}):
        m = _id_name_re.match(inp.get("name", ""))
        if not m:
            continue
        pid = int(m.group(1))
        if pid in schema:
            continue
        label_inp = soup.find("input", attrs={"name": f"permissions[{pid}][label]"})
        desc_inp = soup.find("input", attrs={"name": f"permissions[{pid}][description]"})
        schema[pid] = PermissionFieldMeta(
            id=pid,
            label=(label_inp.get("value") or "") if label_inp else "",
            description=(desc_inp.get("value") or "") if desc_inp else "",
        )
    ordered_schema = [schema[k] for k in sorted(schema.keys())]
    return templates, ordered_schema


def parse_permissions(html: str, *, scope: Literal["pos", "backoffice"]) -> list[Permission]:
    """Return only the role templates. Convenience wrapper around parse_permissions_and_schema."""
    templates, _ = parse_permissions_and_schema(html, scope=scope)
    return templates
