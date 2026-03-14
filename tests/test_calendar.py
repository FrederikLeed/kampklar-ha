"""Tests for the KampKlar calendar platform."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
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
            CONF_PERSONS: [{CONF_PERSON_ID: PERSON_ID, CONF_PERSON_NAME: "Test Ansen"}],
        },
        unique_id="100001",
    )


@pytest.fixture
def mock_activities() -> list[Activity]:
    """Return parsed activities from fixture."""
    data = load_fixture("person_activities.json")
    return [Activity.from_api(entry) for entry in data]


async def _setup(hass, config_entry, activities):
    """Set up the integration with mocked coordinator data."""
    with (
        patch("custom_components.kampklar.KampKlarApiClient") as mock_client_cls,
        patch(
            "custom_components.kampklar.KampKlarCoordinator._async_update_data",
            return_value={PERSON_ID: activities},
        ),
    ):
        mock_client_cls.return_value = AsyncMock()
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()


async def test_calendar_created(hass: HomeAssistant, config_entry, mock_activities):
    """Test that a calendar entity is created per tracked person."""
    await _setup(hass, config_entry, mock_activities)
    state = hass.states.get("calendar.test_ansen_kalender")
    assert state is not None


async def test_calendar_event_from_activities(hass: HomeAssistant, config_entry, mock_activities):
    """Test that the calendar shows the next upcoming event."""
    now = dt_util.as_local(mock_activities[0].start_time - timedelta(hours=1))
    with patch("custom_components.kampklar.calendar.dt_util.now", return_value=now):
        await _setup(hass, config_entry, mock_activities)
        state = hass.states.get("calendar.test_ansen_kalender")
        assert state is not None
        assert state.attributes.get("message") == mock_activities[0].name


async def test_calendar_signup_status_attribute(hass: HomeAssistant, config_entry, mock_activities):
    """Test that signup_status is exposed as a state attribute."""
    now = dt_util.as_local(mock_activities[0].start_time - timedelta(hours=1))
    with patch("custom_components.kampklar.calendar.dt_util.now", return_value=now):
        await _setup(hass, config_entry, mock_activities)
        state = hass.states.get("calendar.test_ansen_kalender")
        assert state.attributes.get("signup_status") == "Tilmeldt"
        assert state.attributes.get("signup_status_id") == 2


async def test_calendar_get_events(hass: HomeAssistant, config_entry, mock_activities):
    """Test async_get_events returns events in range."""
    await _setup(hass, config_entry, mock_activities)

    entity = hass.data["entity_components"]["calendar"].get_entity("calendar.test_ansen_kalender")
    assert entity is not None

    start = dt_util.as_local(mock_activities[0].start_time - timedelta(days=1))
    end = dt_util.as_local(mock_activities[-1].start_time + timedelta(days=1))
    events = await entity.async_get_events(hass, start, end)
    assert len(events) == len(mock_activities)
    assert events[0].summary == mock_activities[0].name


async def test_calendar_empty(hass: HomeAssistant, config_entry):
    """Test calendar with no activities."""
    await _setup(hass, config_entry, [])
    state = hass.states.get("calendar.test_ansen_kalender")
    assert state is not None
    assert state.state == "off"


async def test_calendar_udtaget_in_event(hass: HomeAssistant, config_entry):
    """Test that 'Udtaget' status appears in calendar event and attributes."""
    act_data = {
        "activity": {
            "id": 9999,
            "name": "U14 - Storkamp",
            "typeId": 2,
            "typeName": "Kamp",
            "startTime": "2026-03-20T11:00:00",
            "endTime": "2026-03-20T12:30:00",
            "meetingTime": None,
            "meetingPlace": "Stadion Vej 1",
            "teamId": 100,
            "teamName": "U14 Drenge",
            "clubName": "Testby BK",
            "clubLogoUrl": "",
            "signupStatusId": 4,
            "signupStatusName": "Udtaget",
            "subscribed": 15,
            "subscribedText": "15 tilmeldte",
            "personContactId": 300001,
            "personContactName": "Test Ansen",
            "match": {
                "matchId": 1,
                "poolId": 1,
                "homeTeamName": "Testby BK",
                "awayTeamName": "FC Modstander",
                "stadiumName": "Testby Stadion",
                "fieldName": "Bane 1",
                "rowName": "Liga",
                "homeTeamLogoUrl": "",
                "awayTeamLogoUrl": "",
            },
        },
        "activityDateTime": "2026-03-20T11:00:00",
        "eType": 2,
        "sortingIndex": 0,
    }
    udtaget_activity = Activity.from_api(act_data)
    now = dt_util.as_local(udtaget_activity.start_time - timedelta(hours=1))

    with patch("custom_components.kampklar.calendar.dt_util.now", return_value=now):
        await _setup(hass, config_entry, [udtaget_activity])

        state = hass.states.get("calendar.test_ansen_kalender")
        # signup_status directly available for automations
        assert state.attributes.get("signup_status") == "Udtaget"
        assert state.attributes.get("signup_status_id") == 4

        # Also in the event description
        entity = hass.data["entity_components"]["calendar"].get_entity("calendar.test_ansen_kalender")
        events = await entity.async_get_events(
            hass,
            dt_util.as_local(udtaget_activity.start_time - timedelta(hours=2)),
            dt_util.as_local(udtaget_activity.start_time + timedelta(hours=4)),
        )
        assert len(events) == 1
        assert "Udtaget" in events[0].description
