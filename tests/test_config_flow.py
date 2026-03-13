"""Tests for the KampKlar config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.kampklar.api import Activity, KampKlarAuthError, KampKlarConnectionError
from custom_components.kampklar.const import CONF_PERSON_ID, CONF_PERSON_NAME, CONF_PERSONS, DOMAIN

pytestmark = pytest.mark.usefixtures("auto_enable_custom_integrations")


@pytest.fixture
def mock_setup_entry():
    """Mock async_setup_entry."""
    with patch("custom_components.kampklar.async_setup_entry", return_value=True) as mock:
        yield mock


async def test_user_flow_single_person(hass: HomeAssistant, mock_user, mock_activities, mock_setup_entry):
    """Test config flow with a single person (skips person selection)."""
    with patch("custom_components.kampklar.config_flow.KampKlarApiClient") as mock_client_cls:
        client = AsyncMock()
        client.authenticate.return_value = mock_user
        client.get_person_activities.return_value = mock_activities
        mock_client_cls.return_value = client

        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "testuser", CONF_PASSWORD: "testpass"},
        )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["title"] == "KampKlar"
        assert result["data"][CONF_USERNAME] == "testuser"
        assert result["data"]["user_id"] == 100001
        persons = result["data"][CONF_PERSONS]
        assert len(persons) == 1
        assert persons[0][CONF_PERSON_ID] == 300001


async def test_user_flow_invalid_auth(hass: HomeAssistant, mock_setup_entry):
    """Test config flow with invalid credentials."""
    with patch("custom_components.kampklar.config_flow.KampKlarApiClient") as mock_client_cls:
        client = AsyncMock()
        client.authenticate.side_effect = KampKlarAuthError("Invalid credentials")
        mock_client_cls.return_value = client

        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "bad", CONF_PASSWORD: "creds"},
        )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_cannot_connect(hass: HomeAssistant, mock_setup_entry):
    """Test config flow with connection error."""
    with patch("custom_components.kampklar.config_flow.KampKlarApiClient") as mock_client_cls:
        client = AsyncMock()
        client.authenticate.side_effect = KampKlarConnectionError("Timeout")
        mock_client_cls.return_value = client

        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "user", CONF_PASSWORD: "pass"},
        )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_no_activities(hass: HomeAssistant, mock_user, mock_setup_entry):
    """Test config flow when no activities are returned (uses parent person)."""
    with patch("custom_components.kampklar.config_flow.KampKlarApiClient") as mock_client_cls:
        client = AsyncMock()
        client.authenticate.return_value = mock_user
        client.get_person_activities.return_value = []
        mock_client_cls.return_value = client

        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "testuser", CONF_PASSWORD: "testpass"},
        )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        persons = result["data"][CONF_PERSONS]
        assert len(persons) == 1
        assert persons[0][CONF_PERSON_ID] == mock_user.person_id


def _make_activity(person_id: int, person_name: str) -> Activity:
    """Create a minimal Activity for testing person discovery."""
    return Activity.from_api(
        {
            "activity": {
                "id": 1,
                "name": "Test",
                "typeId": 1,
                "typeName": "Træning",
                "startTime": "2026-03-15T10:00:00",
                "endTime": None,
                "meetingTime": None,
                "meetingPlace": "",
                "teamId": 1,
                "teamName": "U14",
                "clubName": "AaB",
                "clubLogoUrl": "",
                "signupStatusId": 0,
                "signupStatusName": "Ikke svaret",
                "subscribed": 0,
                "subscribedText": "",
                "personContactId": person_id,
                "personContactName": person_name,
                "match": None,
            },
            "activityDateTime": "2026-03-15T10:00:00",
            "eType": 1,
            "sortingIndex": 0,
        }
    )


async def test_user_flow_multi_person(hass: HomeAssistant, mock_user, mock_setup_entry):
    """Test config flow with multiple persons shows person selection step."""
    multi_activities = [
        _make_activity(1001, "Child One"),
        _make_activity(1002, "Child Two"),
    ]
    with patch("custom_components.kampklar.config_flow.KampKlarApiClient") as mock_client_cls:
        client = AsyncMock()
        client.authenticate.return_value = mock_user
        client.get_person_activities.return_value = multi_activities
        mock_client_cls.return_value = client

        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "testuser", CONF_PASSWORD: "testpass"},
        )

        # Should show person selection step
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "persons"

        # Select only the first person
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PERSONS: [1001]},
        )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        persons = result["data"][CONF_PERSONS]
        assert len(persons) == 1
        assert persons[0][CONF_PERSON_ID] == 1001
        assert persons[0][CONF_PERSON_NAME] == "Child One"
