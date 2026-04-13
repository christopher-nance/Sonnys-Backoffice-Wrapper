from datetime import datetime
from decimal import Decimal

from sonnys_backoffice.employees import build_employee_step1_payload
from sonnys_backoffice.models import CreateEmployeeRequest, Site
from sonnys_backoffice.sites import SiteTree


def _sample_request(**overrides) -> CreateEmployeeRequest:
    base = dict(
        first_name="Jane",
        last_name="Doe",
        phone="6155551234",
        email="jane@example.com",
        pos_user_id=12345,
        pos_pin=54321,
        wage_rate=Decimal("15.50"),
        start_date=datetime(2026, 5, 1),
        available_sites=["Wash 37135"],
        departments=["Cashier"],
        permission="General User",
    )
    base.update(overrides)
    return CreateEmployeeRequest(**base)


def _flat_tree() -> SiteTree:
    return SiteTree(
        is_hierarchical=False,
        sites=[Site(id=17, name="Wash 37135")],
    )


def _hierarchical_tree() -> SiteTree:
    from sonnys_backoffice.models import District, Region
    return SiteTree(
        is_hierarchical=True,
        regions=[Region(id=1, name="Global"), Region(id=2, name="WashU Illinois")],
        districts=[
            District(id=1, name="Global", region_id=1),
            District(id=2, name="WashU", region_id=2),
        ],
        sites=[
            Site(id=17, name="Wash 37135", district_id=1, region_id=1),
            Site(id=1, name="WashU Fiesta", district_id=2, region_id=2),
        ],
    )


def test_basic_personal_fields_match():
    req = _sample_request()
    payload = build_employee_step1_payload(
        req,
        site_tree=_flat_tree(),
        departments_by_name={"Cashier": 1, "Greeter": 3},
        wage_site_id=17,
    )
    assert payload["employee[firstName]"] == "Jane"
    assert payload["employee[lastName]"] == "Doe"
    assert payload["employee[phone]"] == "6155551234"
    assert payload["employee[email]"] == "jane@example.com"
    assert payload["employee[startDate]"] == "05/01/2026"


def test_pos_credentials_use_numeric_strings():
    req = _sample_request()
    payload = build_employee_step1_payload(
        req, site_tree=_flat_tree(), departments_by_name={"Greeter": 3}, wage_site_id=17
    )
    assert payload["posCredential[POSLoginID]"] == "12345"
    assert payload["posCredential[POSLoginPassword]"] == "54321"


def test_wage_fields_present():
    req = _sample_request(wage_rate=Decimal("15.50"), overtime_wage_rate=Decimal("23.25"))
    payload = build_employee_step1_payload(
        req, site_tree=_flat_tree(), departments_by_name={"Greeter": 3}, wage_site_id=17
    )
    assert payload["wage[isHourly]"] == "1"
    assert payload["wage[regularRate]"] == "15.50"
    assert payload["wage[overtimeRate]"] == "23.25"
    assert payload["wage[isOvertimeEligible]"] == "1"
    assert payload["wage[siteId]"] == "17"


def test_departments_resolved_to_ids():
    req = _sample_request(departments=["Cashier", "Greeter"])
    payload = build_employee_step1_payload(
        req,
        site_tree=_flat_tree(),
        departments_by_name={"Cashier": 1, "Greeter": 3, "Line": 2},
        wage_site_id=17,
    )
    assert 1 in payload["employee[departments][]"]
    assert 3 in payload["employee[departments][]"]


def test_departments_drops_unknown_names():
    req = _sample_request(departments=["Cashier", "Ghost"])
    payload = build_employee_step1_payload(
        req,
        site_tree=_flat_tree(),
        departments_by_name={"Cashier": 1, "Greeter": 3},
        wage_site_id=17,
    )
    # Ghost is dropped; Greeter is auto-added by the model validator → id 3
    assert 1 in payload["employee[departments][]"]
    assert 3 in payload["employee[departments][]"]


def test_adp_id_included_when_set():
    req = _sample_request(adp_employee_id="ADP-42")
    payload = build_employee_step1_payload(
        req, site_tree=_flat_tree(), departments_by_name={"Greeter": 3}, wage_site_id=17
    )
    assert payload["employee[adpEmployeeId]"] == "ADP-42"


def test_adp_id_omitted_when_none():
    req = _sample_request()
    payload = build_employee_step1_payload(
        req, site_tree=_flat_tree(), departments_by_name={"Greeter": 3}, wage_site_id=17
    )
    assert "employee[adpEmployeeId]" not in payload


def test_hierarchical_tenant_specific_site_selection():
    req = _sample_request(available_sites=["Wash 37135"])
    payload = build_employee_step1_payload(
        req,
        site_tree=_hierarchical_tree(),
        departments_by_name={"Cashier": 1, "Greeter": 3},
        wage_site_id=17,
    )
    assert payload["employee[isAllRegionsAllowed]"] == "0"
    # Region 2 disabled, region 1 enabled
    assert 2 in payload["employee[disabledRegions][]"]
    assert 1 not in payload["employee[disabledRegions][]"]
    # Site 17 enabled, Site 1 disabled
    assert payload["employee[sites][17][isAvailable]"] == "1"
    assert payload["employee[sites][1][isAvailable]"] == "0"
    assert payload["employee[sites][17][siteId]"] == "17"
    assert payload["employee[sites][1][siteId]"] == "1"


def test_hierarchical_tenant_all_sites():
    req = _sample_request(available_sites="all")
    payload = build_employee_step1_payload(
        req,
        site_tree=_hierarchical_tree(),
        departments_by_name={"Greeter": 3},
        wage_site_id=17,
    )
    assert payload["employee[isAllRegionsAllowed]"] == "1"


def test_flat_tenant_specific_sites():
    req = _sample_request(available_sites=["Wash 37135"])
    payload = build_employee_step1_payload(
        req,
        site_tree=_flat_tree(),
        departments_by_name={"Greeter": 3},
        wage_site_id=17,
    )
    assert payload["employee[isAllSitesAllowed]"] == "0"
    assert payload["employee[siteIds][]"] == [17]


def test_flat_tenant_all_sites():
    req = _sample_request(available_sites="all")
    payload = build_employee_step1_payload(
        req,
        site_tree=_flat_tree(),
        departments_by_name={"Greeter": 3},
        wage_site_id=17,
    )
    assert payload["employee[isAllSitesAllowed]"] == "1"
