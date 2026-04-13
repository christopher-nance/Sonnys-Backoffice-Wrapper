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

Cleanup safety net:
    The ``tracked_client`` fixture records every POS User ID the tests ask it
    to create, and a session-scoped teardown disables every tracked ID. Tests
    can still do their own inline cleanup (and should), but if they crash
    mid-test the teardown ensures the tenant doesn't accumulate disposable
    records over time.
"""

from __future__ import annotations

import os
import random

import pytest

from sonnys_backoffice import SonnysBackofficeClient


class _TrackedClient:
    """Thin wrapper around SonnysBackofficeClient that records created POS IDs.

    Pass-through for every public method; adds a ``track(pos_user_id)`` helper
    tests call immediately after a successful create.
    """

    def __init__(self, inner: SonnysBackofficeClient) -> None:
        self._inner = inner
        self.tracked_pos_ids: list[int] = []

    def track(self, pos_user_id: int) -> None:
        """Record a POS User ID for teardown-time cleanup."""
        self.tracked_pos_ids.append(pos_user_id)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


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


@pytest.fixture(scope="session")
def tracked_client(client):
    """Session-scoped wrapper that tracks created POS IDs and disables them on teardown.

    Tests that create employees should call ``tracked_client.track(pos_id)``
    right after ``create_employee`` returns. The teardown runs after the last
    test in the session and attempts to disable every tracked ID. Failures
    during cleanup are reported but do not fail the test session.
    """
    tracked = _TrackedClient(client)
    yield tracked
    # Teardown: disable anything the tests created and forgot to clean up inline.
    if not tracked.tracked_pos_ids:
        return
    print(f"\n[cleanup] teardown disabling {len(tracked.tracked_pos_ids)} tracked employee(s)")
    for pos_id in tracked.tracked_pos_ids:
        try:
            client.disable_employee(pos_user_id=pos_id)
            print(f"[cleanup]   disabled pos_user_id={pos_id}")
        except Exception as err:
            print(f"[cleanup]   FAILED pos_user_id={pos_id}: {type(err).__name__}: {err}")


@pytest.fixture
def unique_suffix() -> str:
    """Short random hex suffix for per-test unique names/emails."""
    return f"{random.randint(0, 0xFFFF):04X}"


@pytest.fixture
def writes_allowed() -> None:
    """Skip a test unless SONNYS_ALLOW_WRITES=1 is set in the environment."""
    if not os.environ.get("SONNYS_ALLOW_WRITES"):
        pytest.skip("SONNYS_ALLOW_WRITES not set — skipping live-write test")
