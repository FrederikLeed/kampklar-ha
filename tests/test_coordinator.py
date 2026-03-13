"""Tests for the KampKlar coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kampklar.api import KampKlarApiClient, KampKlarAuthError, KampKlarConnectionError
from custom_components.kampklar.const import CONF_PERSON_ID, CONF_PERSON_NAME, CONF_PERSONS, DOMAIN

pytestmark = pytest.mark.usefixtures("auto_enable_custom_integrations")

PERSON_ID = 300001


@pytest.fixture
def config_entry(hass: HomeAssistant):
    """Create a mock config entry."""
    entry = MockConfigEntry(
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
    entry.add_to_hass(hass)
    return entry


async def test_coordinator_update_success(hass: HomeAssistant, config_entry, mock_activities):
    """Test successful coordinator data update via full setup."""
    with (
        patch("custom_components.kampklar.KampKlarApiClient") as mock_client_cls,
        patch(
            "custom_components.kampklar.KampKlarCoordinator._async_update_data",
            return_value={PERSON_ID: mock_activities},
        ),
    ):
        mock_client_cls.return_value = AsyncMock()
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    coordinator = config_entry.runtime_data
    assert coordinator.data is not None
    assert PERSON_ID in coordinator.data
    assert len(coordinator.data[PERSON_ID]) == 3


async def test_coordinator_auth_error(hass: HomeAssistant, config_entry):
    """Test coordinator raises ConfigEntryAuthFailed on auth error."""
    mock_client = AsyncMock(spec=KampKlarApiClient)
    mock_client.get_person_activities.side_effect = KampKlarAuthError("Token expired")

    with patch("custom_components.kampklar.KampKlarApiClient", return_value=mock_client):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    # Auth failure during first refresh causes setup to fail with auth error
    assert config_entry.state.name == "SETUP_ERROR"


async def test_coordinator_connection_error(hass: HomeAssistant, config_entry):
    """Test coordinator raises UpdateFailed on connection error."""
    mock_client = AsyncMock(spec=KampKlarApiClient)
    mock_client.get_person_activities.side_effect = KampKlarConnectionError("Timeout")

    with patch("custom_components.kampklar.KampKlarApiClient", return_value=mock_client):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    # Connection error during first refresh causes setup retry
    assert config_entry.state.name == "SETUP_RETRY"
