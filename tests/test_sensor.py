"""Tests for KampKlar sensor platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kampklar.api import Activity
from custom_components.kampklar.const import CONF_PERSON_ID, CONF_PERSON_NAME, CONF_PERSONS, DOMAIN

from .conftest import load_fixture

pytestmark = pytest.mark.usefixtures("auto_enable_custom_integrations")

PERSON_ID = 300001


@pytest.fixture
def config_entry(hass: HomeAssistant):
    """Create a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="KampKlar",
        data={
            CONF_USERNAME: "testuser",
            CONF_PASSWORD: "testpass",
            "user_id": 100001,
            CONF_PERSONS: [
                {CONF_PERSON_ID: PERSON_ID, CONF_PERSON_NAME: "Test Ansen"},
            ],
        },
        unique_id="100001",
    )


@pytest.fixture
def mock_activities() -> list[Activity]:
    """Return parsed activities from fixture."""
    data = load_fixture("person_activities.json")
    return [Activity.from_api(entry) for entry in data]


async def test_sensors_created(hass: HomeAssistant, config_entry, mock_activities):
    """Test that sensors are created for each person."""
    with (
        patch("custom_components.kampklar.KampKlarApiClient") as mock_client_cls,
        patch(
            "custom_components.kampklar.KampKlarCoordinator._async_update_data",
            return_value={PERSON_ID: mock_activities},
        ),
    ):
        mock_client_cls.return_value = AsyncMock()
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.test_ansen_naeste_aktivitet")
    assert state is not None
    assert state.state == "Testby BK - FC Eksempel"
    assert state.attributes["type"] == "Kamp"
    assert state.attributes["team"] == "U14 Drenge"
    assert state.attributes["signup_status"] == "Tilmeldt"
    assert state.attributes["match_id"] == 500001

    state = hass.states.get("sensor.test_ansen_naeste_kamp")
    assert state is not None
    assert state.state == "Testby BK - FC Eksempel"
    assert state.attributes["stadium"] == "Testby Stadion"

    state = hass.states.get("sensor.test_ansen_afventende_tilmeldinger")
    assert state is not None
    assert state.state == "2"
    assert len(state.attributes["activities"]) == 2


async def test_sensors_no_data(hass: HomeAssistant, config_entry):
    """Test sensors when coordinator has no data."""
    with (
        patch("custom_components.kampklar.KampKlarApiClient") as mock_client_cls,
        patch(
            "custom_components.kampklar.KampKlarCoordinator._async_update_data",
            return_value={PERSON_ID: []},
        ),
    ):
        mock_client_cls.return_value = AsyncMock()
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.test_ansen_naeste_aktivitet")
    assert state is not None
    assert state.state == "unknown"

    state = hass.states.get("sensor.test_ansen_naeste_kamp")
    assert state is not None
    assert state.state == "unknown"

    state = hass.states.get("sensor.test_ansen_afventende_tilmeldinger")
    assert state is not None
    assert state.state == "0"
