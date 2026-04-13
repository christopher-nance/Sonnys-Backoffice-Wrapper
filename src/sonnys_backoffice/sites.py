"""Site/region/district tree parser and resolver."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from bs4 import BeautifulSoup

from .models import District, Region, Site


@dataclass
class SiteTree:
    is_hierarchical: bool
    regions: list[Region] = field(default_factory=list)
    districts: list[District] = field(default_factory=list)
    sites: list[Site] = field(default_factory=list)

    def resolve(self, name: str) -> Site:
        for s in self.sites:
            if s.name == name:
                return s
        raise LookupError(f"Unknown Site: {name!r}")

    def resolve_all(self, sites: list[str] | Literal["all"]) -> list[Site]:
        if sites == "all":
            return list(self.sites)
        return [self.resolve(n) for n in sites]


def parse_site_tree(html: str) -> SiteTree:
    """Parse /employee/create HTML into a SiteTree."""
    soup = BeautifulSoup(html, "html.parser")
    region_options = soup.select("input.boac-permission-region-option")
    is_hierarchical = len(region_options) > 0

    if is_hierarchical:
        return _parse_hierarchical(soup)
    return _parse_flat(soup)


def _extract_label_name(label_el) -> str:
    """Extract 'WashU Fiesta' from 'Site <strong>(WashU Fiesta)</strong>'."""
    strong = label_el.find("strong")
    if strong is None:
        return label_el.get_text(strip=True)
    text = strong.get_text(strip=True)
    return text.strip("()")


def _parse_hierarchical(soup) -> SiteTree:
    regions: list[Region] = []
    districts: list[District] = []
    sites: list[Site] = []

    for region_input in soup.select("input.boac-permission-region-option"):
        region_id = int(region_input["data-region-id"])
        label_el = soup.select_one(f'label[for="boac-permission-region-{region_id}"]')
        region_name = _extract_label_name(label_el) if label_el else f"Region {region_id}"
        regions.append(Region(id=region_id, name=region_name))

    for district_input in soup.select("input.boac-permission-district-option"):
        district_id = int(district_input["data-district-id"])
        region_id = int(district_input["data-region-id"])
        label_el = soup.select_one(f'label[for="boac-permission-district-{district_id}"]')
        district_name = _extract_label_name(label_el) if label_el else f"District {district_id}"
        districts.append(District(id=district_id, name=district_name, region_id=region_id))

    for site_input in soup.select("input.boac-permission-site-option"):
        site_id = int(site_input["value"])
        district_id_raw = site_input.get("data-district-id")
        district_id = int(district_id_raw) if district_id_raw else None
        region_id: int | None = None
        if district_id is not None:
            match = next((d for d in districts if d.id == district_id), None)
            if match:
                region_id = match.region_id
        label_el = soup.select_one(f'label[for="boac-permission-site-{site_id}"]')
        site_name = _extract_label_name(label_el) if label_el else f"Site {site_id}"
        sites.append(Site(id=site_id, name=site_name, district_id=district_id, region_id=region_id))

    return SiteTree(is_hierarchical=True, regions=regions, districts=districts, sites=sites)


def _parse_flat(soup) -> SiteTree:
    sites: list[Site] = []
    for site_input in soup.select("input.boac-permission-site-option"):
        site_id = int(site_input["value"])
        label_el = soup.select_one(f'label[for="boac-permission-site-{site_id}"]')
        site_name = _extract_label_name(label_el) if label_el else f"Site {site_id}"
        sites.append(Site(id=site_id, name=site_name))
    return SiteTree(is_hierarchical=False, sites=sites)
