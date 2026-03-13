"""Shared fixtures for KampKlar tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from custom_components.kampklar.api import Activity, KampKlarApiClient, User
from custom_components.kampklar.const import CONF_PERSON_ID, CONF_PERSON_NAME, CONF_PERSONS

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True, scope="session")
def _prewarm_pycares():
    """Pre-initialize pycares so its daemon thread exists before any test.

    The pycares library (used by aiodns/aiohttp for DNS) creates a daemon
    thread '_run_safe_shutdown_loop' on first Channel creation. If this
    happens mid-test, HA's verify_cleanup fixture detects it as a lingering
    thread. Pre-warming here ensures it's in threads_before for all tests.
    """
    try:
        import pycares

        pycares.Channel()
    except Exception:
        pass


@pytest.fixture
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations."""


def load_fixture(name: str) -> dict | list:
    """Load a JSON fixture file."""
    return json.loads((FIXTURES_DIR / name).read_text())


@pytest.fixture
def login_response() -> dict:
    """Return sample login response."""
    return load_fixture("login_response.json")


@pytest.fixture
def person_activities_response() -> list:
    """Return sample person activities response."""
    return load_fixture("person_activities.json")


@pytest.fixture
def mock_user(login_response: dict) -> User:
    """Return a User from the login fixture."""
    return User.from_api(login_response["data"])


@pytest.fixture
def mock_activities(person_activities_response: list) -> list[Activity]:
    """Return parsed Activity objects from the fixture."""
    return [Activity.from_api(entry) for entry in person_activities_response]


@pytest.fixture
def mock_config_entry_data() -> dict:
    """Return mock config entry data."""
    return {
        CONF_USERNAME: "testuser",
        CONF_PASSWORD: "testpass",
        "user_id": 100001,
        CONF_PERSONS: [
            {CONF_PERSON_ID: 300001, CONF_PERSON_NAME: "Test Ansen"},
        ],
    }


@pytest.fixture
def mock_client(mock_user: User, mock_activities: list[Activity]) -> AsyncMock:
    """Return a mocked KampKlarApiClient."""
    client = AsyncMock(spec=KampKlarApiClient)
    client.authenticate.return_value = mock_user
    client.get_person_activities.return_value = mock_activities
    return client
