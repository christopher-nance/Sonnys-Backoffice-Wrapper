from pathlib import Path

from sonnys_backoffice.employees import build_employee_step2_permissions_payload
from sonnys_backoffice.models import Permission, PermissionFieldMeta
from sonnys_backoffice.permissions import parse_permissions_and_schema

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html"


def test_parse_permissions_and_schema_yields_templates_with_grants():
    html = (FIXTURES / "employee_permissions_54.html").read_text(encoding="utf-8")
    templates, schema = parse_permissions_and_schema(html, scope="pos")
    names = {t.name for t in templates}
    assert "General User" in names
    general_user = next(t for t in templates if t.name == "General User")
    # General User grants permission id 22 only (per fixture inspection)
    assert 22 in general_user.grants
    assert len(general_user.grants) == 1


def test_parse_schema_extracts_unique_permissions():
    html = (FIXTURES / "employee_permissions_54.html").read_text(encoding="utf-8")
    _, schema = parse_permissions_and_schema(html, scope="pos")
    assert len(schema) >= 30  # WashU has 34 POS permissions
    ids = [p.id for p in schema]
    assert ids == sorted(set(ids))  # sorted, deduplicated
    # Every entry has a label
    assert all(p.label for p in schema)


def test_manager_template_grants_all_permissions():
    html = (FIXTURES / "employee_permissions_54.html").read_text(encoding="utf-8")
    templates, schema = parse_permissions_and_schema(html, scope="pos")
    manager = next(t for t in templates if t.name == "Manager")
    # Manager grants every permission id in the schema
    schema_ids = {p.id for p in schema}
    assert manager.grants == frozenset(schema_ids)


def test_step2_payload_emits_full_matrix_in_order():
    perm = Permission(
        id=3,
        name="General User",
        scope="pos",
        grants=frozenset({22}),
        overrides=frozenset(),
    )
    schema = [
        PermissionFieldMeta(id=1, label="Perm 1", description="desc 1"),
        PermissionFieldMeta(id=22, label="Perm 22", description="desc 22"),
    ]
    payload = build_employee_step2_permissions_payload(
        permission=perm,
        permission_schema=schema,
        employee_id=42,
    )
    assert ("employeeId", "42") in payload
    assert ("templateId", "3") in payload
    assert ("hasActionApprovalAuthority", "0") in payload
    assert ("permissions[1][id]", "1") in payload
    assert ("permissions[1][label]", "Perm 1") in payload
    assert ("permissions[1][description]", "desc 1") in payload
    assert ("permissions[22][id]", "22") in payload
    assert ("permissions[22][hasGrantAccess]", "1") in payload
    # Not granted → absent
    assert ("permissions[1][hasGrantAccess]", "1") not in payload


def test_step2_payload_emits_override_flag_only_when_present():
    perm = Permission(
        id=2,
        name="Cashier",
        scope="pos",
        grants=frozenset({2, 3}),
        overrides=frozenset({3}),
    )
    schema = [
        PermissionFieldMeta(id=2, label="a", description="a"),
        PermissionFieldMeta(id=3, label="b", description="b"),
    ]
    payload = build_employee_step2_permissions_payload(
        permission=perm, permission_schema=schema, employee_id=7
    )
    assert ("permissions[2][hasGrantAccess]", "1") in payload
    assert ("permissions[3][hasGrantAccess]", "1") in payload
    assert ("permissions[3][requiresOverride]", "1") in payload
    assert ("permissions[2][requiresOverride]", "1") not in payload


def test_action_approval_authority_defaults_to_zero():
    perm = Permission(id=3, name="General User", scope="pos")
    payload = build_employee_step2_permissions_payload(
        permission=perm, permission_schema=[], employee_id=1
    )
    assert ("hasActionApprovalAuthority", "0") in payload


def test_action_approval_authority_one_when_set():
    perm = Permission(id=1, name="Manager", scope="pos")
    payload = build_employee_step2_permissions_payload(
        permission=perm,
        permission_schema=[],
        employee_id=1,
        has_action_approval_authority=True,
    )
    assert ("hasActionApprovalAuthority", "1") in payload
