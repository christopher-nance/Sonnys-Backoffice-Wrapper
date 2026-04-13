# Permissions & Roles

Sonny's Backoffice ships two independent permission systems:

- **POS permissions** — grant access to specific POS features (open drawer, void transactions, refund, etc.). Applied at `/employee/permissions/<id>`. ~34 individual permissions on a typical tenant, grouped into numeric templates.
- **Backoffice permissions** — grant access to Backoffice web UI pages (employee.write, report.all, etc.). Applied at `/user/permissions/<id>`. ~105 string-keyed permissions grouped into templates.

Both are template-based: you pick a named role and the server applies the template's full grant set.

## Standard templates

These three are **guaranteed to exist on every Sonny's subdomain**:

- `Manager`
- `Cashier`
- `General User`

Other template names exist on most tenants but aren't universal:

- `Administrator` (BO-only on most tenants; not universally on POS)
- `General Manager`
- `Assistant Manager`
- `Shift Leader`
- `CSA`

If your onboarding workflow needs to run on more than one tenant, stick to the three universal names — or inspect the templates first with `list_permissions()`.

## Case-insensitive name matching

Template names are matched case-insensitively. All of these resolve to the same template:

```python
permission="Manager"
permission="manager"
permission="MANAGER"
permission="mAnAgEr"
```

## Unknown name fallback

If you pass a template name the tenant doesn't have, the library:

1. Emits a Python `UserWarning` with the mismatch details.
2. Falls back to `General User`.
3. Adds a message to `result.warnings` so you can see the fallback in your logs.

```python
result = client.create_employee(
    ...,
    permission="SuperAdmin",  # not a real template
)
for w in result.warnings:
    print(w)
# -> "permission 'SuperAdmin' not found in tenant, falling back to 'General User'"
```

The fallback only works if `General User` itself exists on the tenant. If it doesn't (unusual but possible on a heavily customized tenant), the call raises `ValueError` with instructions to check the tenant's role configuration.

## Inspecting templates

```python
for p in client.list_permissions(scope="pos"):
    print(p.id, p.name, "grants:", len(p.grants), "overrides:", len(p.overrides))

for p in client.list_permissions(scope="backoffice"):
    print(p.id, p.name)
```

`list_permissions` returns a list of `Permission` domain objects. For POS templates, each one carries `grants` (a `frozenset[int]` of permission IDs the template enables) and `overrides` (IDs that require manager approval). The BO template list is name-only in Milestone 1 — see the M1 deferral note below.

## Linked employee + BO user permission matching

When you create an employee with `requires_backoffice=True`, the `permission` parameter is used for **both** the POS side and the BO side. The name is looked up in the POS template list *and* the BO template list separately. If either side fails to match, the respective side falls back to `General User` with a warning.

!!! tip "Use matching template names"
    For linked employee+BO users, pick a template name that exists on both sides. "Manager" and "General User" are safe on every tenant. "Administrator" is safe for BO but is not a POS template on most tenants — passing `permission="Administrator"` for a linked user will fall back to `General User` on the POS side.

## POS step-2 form requires the full matrix

A Phase 1 exploration finding: the `/employee/permissions/update` endpoint accepts a minimal `templateId`-only payload with HTTP 302, but silently has no effect. The server requires you to submit the *entire* permission matrix (one `permissions[N][id]` + `permissions[N][label]` + `permissions[N][description]` block per permission in the tenant's system, plus `hasGrantAccess=1` flags on the template's granted IDs and `requiresOverride=1` flags on its overrides).

The library handles this automatically — it parses the permission schema from the same page as the template list and emits the full matrix. You don't need to think about it.

## Milestone 1: Backoffice permissions assignment is deferred

!!! warning "M1 deferral"
    In Milestone 1, `create_backoffice_user` and the linked BO user path of `create_employee` **create the BO account but do not assign a permission template**. The template must be clicked through manually in the Backoffice UI after creation.

    Why: the BO permissions form has site-inheritance semantics that the library's form parser doesn't yet round-trip correctly. Submitting the parsed form state returns `"Accessible Sites requires no less than 1 valid selection."` even though the linked employee has valid site access. See [Creating a Backoffice user](create-backoffice-user.md#why) for the details and Milestone 2 roadmap.
