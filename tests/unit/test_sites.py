from pathlib import Path

import pytest

from sonnys_backoffice.sites import parse_site_tree

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html"


def test_parses_hierarchical_tenant_fixture():
    html = (FIXTURES / "employee_create.html").read_text(encoding="utf-8")
    tree = parse_site_tree(html)
    assert tree.is_hierarchical is True
    assert len(tree.regions) >= 1
    site_names = [s.name for s in tree.sites]
    assert "WashU Fiesta" in site_names
    fiesta = next(s for s in tree.sites if s.name == "WashU Fiesta")
    assert fiesta.id == 1
    assert fiesta.district_id == 2
    assert fiesta.region_id == 2


def test_resolve_by_name():
    html = (FIXTURES / "employee_create.html").read_text(encoding="utf-8")
    tree = parse_site_tree(html)
    site = tree.resolve("WashU Fiesta")
    assert site.id == 1


def test_resolve_unknown_raises():
    html = (FIXTURES / "employee_create.html").read_text(encoding="utf-8")
    tree = parse_site_tree(html)
    with pytest.raises(LookupError, match="Unknown Site"):
        tree.resolve("Unknown Site")


def test_resolve_all_returns_every_site():
    html = (FIXTURES / "employee_create.html").read_text(encoding="utf-8")
    tree = parse_site_tree(html)
    all_sites = tree.resolve_all("all")
    assert len(all_sites) == len(tree.sites)


def test_wash_37135_is_global_region():
    html = (FIXTURES / "employee_create.html").read_text(encoding="utf-8")
    tree = parse_site_tree(html)
    wash = next(s for s in tree.sites if s.name == "Wash 37135")
    assert wash.id == 17
    assert wash.district_id == 1
    assert wash.region_id == 1
