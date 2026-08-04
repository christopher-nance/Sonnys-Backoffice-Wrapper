"""Regression tests for Sonny's inverted-looking hierarchical site controls."""

from pathlib import Path

from sonnys_backoffice.employees import (
    _build_site_availability_fields,
    parse_employee_profile,
)
from sonnys_backoffice.models import District, Region, Site
from sonnys_backoffice.sites import SiteTree, parse_site_tree

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html"


def test_employee_54_fixture_parses_as_fiesta_only():
    """Checked hierarchical isAvailable controls mean "No", not "Yes"."""
    html = (FIXTURES / "employee_edit_54.html").read_text(encoding="utf-8")
    tree = parse_site_tree(html)

    profile = parse_employee_profile(html, site_tree=tree)

    assert profile.employee_id == 54
    assert profile.available_sites == ["WashU Fiesta"]


def test_fiesta_only_encoder_matches_captured_control_polarity():
    """Changing granted/denied polarity must fail this production-fixture contract."""
    html = (FIXTURES / "employee_edit_54.html").read_text(encoding="utf-8")
    tree = parse_site_tree(html)
    fields = _build_site_availability_fields(tree, ["WashU Fiesta"])
    names = {name for name, _ in fields}

    assert ("employee[disabledRegions][]", "1") in fields
    assert ("employee[disabledDistricts][]", "1") in fields
    assert ("employee[sites][1][siteId]", "1") in fields
    assert "employee[sites][1][isAvailable]" not in names

    denied_ids = {site.id for site in tree.sites} - {1}
    for site_id in denied_ids:
        assert (f"employee[sites][{site_id}][isAvailable]", str(site_id)) in fields
        assert f"employee[sites][{site_id}][siteId]" not in names


def _multi_district_tree() -> SiteTree:
    return SiteTree(
        is_hierarchical=True,
        regions=[Region(id=1, name="Region")],
        districts=[
            District(id=10, name="Allowed District", region_id=1),
            District(id=11, name="Denied District", region_id=1),
        ],
        sites=[
            Site(id=1, name="Allowed A", district_id=10, region_id=1),
            Site(id=2, name="Allowed B", district_id=10, region_id=1),
            Site(id=3, name="Denied", district_id=11, region_id=1),
        ],
    )


def test_fully_allowed_district_is_not_marked_disabled():
    fields = _build_site_availability_fields(_multi_district_tree(), ["Allowed A", "Allowed B"])

    assert ("employee[disabledDistricts][]", "10") not in fields
    assert ("employee[sites][1][siteId]", "1") in fields
    assert ("employee[sites][2][siteId]", "2") in fields
    assert ("employee[disabledDistricts][]", "11") in fields
    assert ("employee[sites][3][isAvailable]", "3") in fields


def test_parent_rollups_override_stale_site_checkbox_state():
    tree = _multi_district_tree()
    html = """
    <form action="/employee/update">
      <input type="checkbox" name="employee[disabledDistricts][]" value="10" checked>
      <input type="checkbox" name="employee[isAllSitesAllowedByDistrict][11]" checked>
      <input type="checkbox" name="employee[sites][1][isAvailable]">
      <input type="checkbox" name="employee[sites][2][isAvailable]">
      <input type="checkbox" name="employee[sites][3][isAvailable]" checked>
    </form>
    """

    profile = parse_employee_profile(html, site_tree=tree)

    assert profile.available_sites == ["Denied"]


def test_per_site_grant_requires_unchecked_control_and_enabled_site_id():
    tree = SiteTree(
        is_hierarchical=True,
        sites=[Site(id=1, name="Target")],
    )

    contradictory_forms = [
        # The checkbox says Yes, but the membership field is absent.
        '<input type="checkbox" name="employee[sites][1][isAvailable]">',
        # The checkbox says Yes, but the membership field is disabled.
        (
            '<input type="checkbox" name="employee[sites][1][isAvailable]">'
            '<input name="employee[sites][1][siteId]" value="1" disabled>'
        ),
        # The membership field is enabled, but the checkbox explicitly says No.
        (
            '<input type="checkbox" name="employee[sites][1][isAvailable]" checked>'
            '<input name="employee[sites][1][siteId]" value="1">'
        ),
    ]

    for controls in contradictory_forms:
        profile = parse_employee_profile(
            f'<form action="/employee/update">{controls}</form>',
            site_tree=tree,
        )
        assert profile.available_sites == []
