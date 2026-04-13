"""Integration test fixtures.

These tests hit a live Sonny's tenant and are skipped unless the required
environment variables are set:

    SONNYS_SUBDOMAIN        — tenant subdomain (e.g., "washu")
    SONNYS_BOT_USERNAME     — bot user username
    SONNYS_BOT_PASSWORD     — bot user password

Write-mutating tests additionally require:

    SONNYS_ALLOW_WRITES=1

Integration tests are excluded from the default pytest run via the
``-m 'not integration'`` addopt in pyproject.toml. Run them explicitly with
``pytest -m integration``.
"""

from __future__ import annotations

import os
import random

import pytest

from sonnys_backoffice import SonnysBackofficeClient


@pytest.fixture(scope="session")
def client():
    subdomain = os.environ.get("SONNYS_SUBDOMAIN")
    username = os.environ.get("SONNYS_BOT_USERNAME")
    password = os.environ.get("SONNYS_BOT_PASSWORD")
    if not (subdomain and username and password):
        pytest.skip("integration credentials not set (SONNYS_SUBDOMAIN/BOT_USERNAME/BOT_PASSWORD)")
    with SonnysBackofficeClient(
        subdomain=subdomain,
        username=username,
        password=password,
    ) as c:
        yield c


@pytest.fixture
def unique_suffix() -> str:
    """Short random hex suffix for per-test unique names/emails."""
    return f"{random.randint(0, 0xFFFF):04X}"


@pytest.fixture
def writes_allowed() -> None:
    """Skip a test unless SONNYS_ALLOW_WRITES=1 is set in the environment."""
    if not os.environ.get("SONNYS_ALLOW_WRITES"):
        pytest.skip("SONNYS_ALLOW_WRITES not set — skipping live-write test")
