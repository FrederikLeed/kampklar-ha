"""Tests for KampKlar diagnostics."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kampklar.const import CONF_PERSON_ID, CONF_PERSON_NAME, CONF_PERSONS, DOMAIN
from custom_components.kampklar.diagnostics import async_get_config_entry_diagnostics

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
            CONF_PERSONS: [{CONF_PERSON_ID: PERSON_ID, CONF_PERSON_NAME: "Test Ansen"}],
        },
        unique_id="100001",
    )


async def test_diagnostics_redacts_personal_data(hass: HomeAssistant, config_entry, mock_activities):
    """Diagnostics keep the activity data but never credentials, names or person ids."""
    with (
        patch("custom_components.kampklar.KampKlarApiClient", return_value=AsyncMock()),
        patch(
            "custom_components.kampklar.KampKlarCoordinator._async_update_data",
            return_value={PERSON_ID: mock_activities},
        ),
    ):
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)

    assert diagnostics["entry"][CONF_PASSWORD] == "**REDACTED**"
    assert diagnostics["entry"][CONF_USERNAME] == "**REDACTED**"
    assert diagnostics["entry"][CONF_PERSONS] == "**REDACTED**"
    assert diagnostics["persons"][0]["person"] == "person_1"
    assert diagnostics["persons"][0]["activity_count"] == len(mock_activities)
    assert diagnostics["persons"][0]["activities"][0]["name"] == mock_activities[0].name

    blob = str(diagnostics)
    for secret in ("testuser", "testpass", "Test Ansen", str(PERSON_ID), "100001"):
        assert secret not in blob, secret


async def test_diagnostics_leave_out_venue_address_and_coordinates(
    hass: HomeAssistant, config_entry, mock_activities, mock_venue
):
    """A venue keeps its name and field in diagnostics, but not its street address or coordinates."""
    activities = [replace(mock_activities[0], venue=mock_venue), *mock_activities[1:]]
    with (
        patch("custom_components.kampklar.KampKlarApiClient", return_value=AsyncMock()),
        patch(
            "custom_components.kampklar.KampKlarCoordinator._async_update_data",
            return_value={PERSON_ID: activities},
        ),
    ):
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)

    assert diagnostics["persons"][0]["activities"][0]["venue"] == {"name": "Testby Stadion", "field_name": "Bane 2"}
    assert diagnostics["persons"][0]["activities"][1]["venue"] is None
    blob = str(diagnostics)
    for secret in ("Prøvevej", "56.123456", "9.654321"):
        assert secret not in blob, secret
