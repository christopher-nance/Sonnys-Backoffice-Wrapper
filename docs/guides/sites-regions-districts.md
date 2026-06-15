# Sites, Regions & Districts

Sonny's Backoffice has two tenant shapes for site management:

- **Flat** — a tenant with 1-N sites and no hierarchy. The create form uses a simple site checklist.
- **Hierarchical** — a tenant with Regions → Districts → Sites. The form has a tree of toggles and submits a complex payload.

The library auto-detects which shape your tenant uses by inspecting the `/employee/create` page and routes the payload accordingly. **You never need to know which shape your tenant has.**

## Referring to sites by name

Always use the human-readable site *name* from the Backoffice UI, not the internal numeric ID:

```python
result = client.create_employee(
    ...,
    available_sites=["Wash 37135", "WashU Fiesta"],
)
```

Under the hood the library parses the site tree from `/employee/create` into a `SiteTree` object, resolves each name to its internal `site_id`, and builds the payload.

## The `"all"` shorthand

Pass the literal string `"all"` to grant access to every site on the tenant:

```python
result = client.create_employee(
    ...,
    available_sites="all",
)
```

On a flat tenant this sends `employee[isAllSitesAllowed]=1`. On a hierarchical tenant it sends `employee[isAllRegionsAllowed]=1`, which cascades down to every district and site.

## Restricting to specific sites

When you pass a list of site names (rather than `"all"`), the wrapper grants exactly those sites and no others — verified live against a hierarchical tenant.

The encoding is subtle, so the wrapper hides it for you:

- **Flat tenants** use a *blocklist*: `employee[siteIds][]` lists the sites to **exclude**.
- **Hierarchical tenants** also work by exclusion. The `employee[isAllRegionsAllowed]` flag is **omitted entirely** (the Backoffice form binds a checkbox's mere *presence* as "true", so sending it — even as `0` — would grant every region). Each non-granted site is then marked unavailable by submitting only its `employee[sites][N][siteId]`; sites left unmentioned stay available. In other words, the wrapper submits the *complement* of your requested list.

This is the same "presence = true" gotcha that `disable_employee` works around for `employee[isActive]`.

## Unknown site names

Passing a site name the tenant doesn't have raises `LookupError` immediately — the wrapper does not silently drop unknown names, because that would mean creating an employee with narrower access than the caller asked for. Instead, you get a clear error before any HTTP call is made.

## Inspecting the tree

If you want to see what sites exist on a tenant (e.g., for a UI dropdown), use the discovery helper:

```python
for site in client.list_sites():
    print(site.name, "-", site.id)
```

`list_sites()` returns a list of `Site` objects. It's cached on the client after the first call; pass `refresh=True` to re-fetch.

## How hierarchy detection works

The parser looks for `<input class="boac-permission-region-option">` inputs inside the `/employee/create` page. If found, the tenant is hierarchical and the parser walks the tree:

- Regions from `<input class="boac-permission-region-option" data-region-id="N">`
- Districts from `<input class="boac-permission-district-option" data-district-id="N" data-region-id="M">`
- Sites from `<input class="boac-permission-site-option" value="N" data-district-id="M">` (region is resolved via the district)

If no region inputs are found, the tenant is flat and the parser just reads `<input class="boac-permission-site-option">` as a top-level list.

## Wage attribution

Even on a hierarchical tenant with a thousand sites, each employee's wage is attributed to a **single** site on the form. The library picks the first site from your `available_sites` list (or the first site in the tree if you passed `"all"`) and uses that as the wage attribution. You can see which site was chosen in `result.wage_site`.

## Domain models

```python
class Region:
    id: int
    name: str

class District:
    id: int
    name: str
    region_id: int | None

class Site:
    id: int
    name: str
    district_id: int | None
    region_id: int | None
```

On a flat tenant, `district_id` and `region_id` are always `None`.
