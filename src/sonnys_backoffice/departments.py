"""Department list parser."""
from __future__ import annotations

from bs4 import BeautifulSoup

from .models import Department


def parse_departments(html: str) -> list[Department]:
    """Extract the list of departments from a /employee/create page.

    Parses the `<select name="employee[departments][]">` multi-select control.
    """
    soup = BeautifulSoup(html, "html.parser")
    depts: list[Department] = []
    for opt in soup.select("select[name='employee[departments][]'] option"):
        val = (opt.get("value") or "").strip()
        if not val:
            continue
        try:
            dept_id = int(val)
        except ValueError:
            continue
        depts.append(Department(id=dept_id, name=opt.get_text(strip=True)))
    return depts
