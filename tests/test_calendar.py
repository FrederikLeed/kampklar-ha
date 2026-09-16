"""Tests for the KampKlar calendar platform."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.calendar import CalendarEvent
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kampklar.api import Activity
from custom_components.kampklar.const import (
    CONF_PERSON_ID,
    CONF_PERSON_NAME,
    CONF_PERSONS,
    CONF_START_AT_MEETING_TIME,
    DOMAIN,
)

from .conftest import load_fixture

pytestmark = pytest.mark.usefixtures("auto_enable_custom_integrations")

PERSON_ID = 300001
CALENDAR = "calendar.test_ansen_calendar"


def _make_entry(options: dict | None = None) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="KampKlar",
        data={
            CONF_USERNAME: "testuser",
            CONF_PASSWORD: "testpass",
            "user_id": 100001,
            CONF_PERSONS: [{CONF_PERSON_ID: PERSON_ID, CONF_PERSON_NAME: "Test Ansen"}],
        },
        options=options or {},
        unique_id="100001",
    )


@pytest.fixture
def config_entry(hass: HomeAssistant):
    """Create a mock config entry."""
    return _make_entry()


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
    state = hass.states.get("calendar.test_ansen_calendar")
    assert state is not None


async def test_calendar_event_from_activities(hass: HomeAssistant, config_entry, mock_activities):
    """Test that the calendar shows the next upcoming event."""
    now = dt_util.as_local(mock_activities[0].start_time - timedelta(hours=1))
    with patch("custom_components.kampklar.calendar.dt_util.now", return_value=now):
        await _setup(hass, config_entry, mock_activities)
        state = hass.states.get("calendar.test_ansen_calendar")
        assert state is not None
        assert state.attributes.get("message") == mock_activities[0].name


async def test_calendar_signup_status_attribute(hass: HomeAssistant, config_entry, mock_activities):
    """Test that signup_status is exposed as a state attribute."""
    now = dt_util.as_local(mock_activities[0].start_time - timedelta(hours=1))
    with patch("custom_components.kampklar.calendar.dt_util.now", return_value=now):
        await _setup(hass, config_entry, mock_activities)
        state = hass.states.get("calendar.test_ansen_calendar")
        assert state.attributes.get("signup_status") == "Tilmeldt"
        assert state.attributes.get("signup_status_id") == 2


async def test_calendar_get_events(hass: HomeAssistant, config_entry, mock_activities):
    """Test async_get_events returns events in range."""
    await _setup(hass, config_entry, mock_activities)

    entity = hass.data["entity_components"]["calendar"].get_entity("calendar.test_ansen_calendar")
    assert entity is not None

    start = dt_util.as_local(mock_activities[0].start_time - timedelta(days=1))
    end = dt_util.as_local(mock_activities[-1].start_time + timedelta(days=1))
    events = await entity.async_get_events(hass, start, end)
    assert len(events) == len(mock_activities)
    assert events[0].summary == mock_activities[0].name


async def test_calendar_empty(hass: HomeAssistant, config_entry):
    """Test calendar with no activities."""
    await _setup(hass, config_entry, [])
    state = hass.states.get("calendar.test_ansen_calendar")
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

        state = hass.states.get("calendar.test_ansen_calendar")
        # signup_status directly available for automations
        assert state.attributes.get("signup_status") == "Udtaget"
        assert state.attributes.get("signup_status_id") == 4

        # Also in the event description
        entity = hass.data["entity_components"]["calendar"].get_entity("calendar.test_ansen_calendar")
        events = await entity.async_get_events(
            hass,
            dt_util.as_local(udtaget_activity.start_time - timedelta(hours=2)),
            dt_util.as_local(udtaget_activity.start_time + timedelta(hours=4)),
        )
        assert len(events) == 1
        assert "Udtaget" in events[0].description


async def _all_events(hass: HomeAssistant, activities: list[Activity]) -> list[CalendarEvent]:
    entity = hass.data["entity_components"]["calendar"].get_entity(CALENDAR)
    start = dt_util.as_local(min(a.start_time for a in activities) - timedelta(days=1))
    end = dt_util.as_local(max(a.start_time for a in activities) + timedelta(days=1))
    return await entity.async_get_events(hass, start, end)


async def test_event_with_venue_has_address_and_map_link(
    hass: HomeAssistant, config_entry, mock_activities, mock_venue
):
    """A match with a venue: the address is the location, the meeting time leads, and a map link closes."""
    match = replace(mock_activities[0], venue=replace(mock_venue, name="Testby Idrætspark"))
    await _setup(hass, config_entry, [match])

    [event] = await _all_events(hass, [match])

    assert event.location == "Testby Idrætspark\nPrøvevej 1, 1234 Testby"
    assert event.start == dt_util.as_local(match.start_time)
    assert event.end == dt_util.as_local(match.end_time)
    assert event.description.splitlines() == [
        "Mødetid: 09:45",
        "Mødested: Sportsvej 1, 1234 Testby",
        "Type: Kamp",
        "Hold: U14 Drenge",
        "Status: Tilmeldt",
        "Tilmeldte: 13",
        "Stadion: Testby Idrætspark, Prøvevej 1, 1234 Testby",
        "Bane: Bane 1",
        "Kort: https://maps.apple.com/?ll=56.123456,9.654321&q=Testby%20Idr%C3%A6tspark",
    ]


async def test_event_without_venue_keeps_meeting_place(hass: HomeAssistant, config_entry, mock_activities):
    """Without a venue the location stays the meeting place and the stadium is its name only."""
    await _setup(hass, config_entry, mock_activities[:1])

    [event] = await _all_events(hass, mock_activities[:1])

    assert event.location == "Sportsvej 1, 1234 Testby"
    lines = event.description.splitlines()
    assert lines[0] == "Mødetid: 09:45"
    assert "Stadion: Testby Stadion" in lines
    assert not any(line.startswith("Kort:") for line in lines)


async def test_staevne_event_uses_its_stadium(hass: HomeAssistant, config_entry, mock_activities, mock_venue):
    """A stævne has no match, so the stadium found for its round is the location and the map link."""
    hallen = replace(mock_venue, name="Testby Hallen", address="Hallevej 1", field_name="")
    staevne = replace(
        mock_activities[1],
        name="Stævne: Testby Hallen",
        type_id=7,
        type_name="DBU-Stævne",
        signup_status_id=4,
        signup_status_name="Udtaget",
        stadium_name="Testby Hallen",
        venue=hallen,
    )
    await _setup(hass, config_entry, [staevne])

    [event] = await _all_events(hass, [staevne])

    assert event.summary == "⭐ Udtaget: Stævne: Testby Hallen"
    assert event.location == "Testby Hallen\nHallevej 1, 1234 Testby"
    lines = event.description.splitlines()
    assert "Type: DBU-Stævne" in lines
    assert lines[-1] == "Kort: https://maps.apple.com/?ll=56.123456,9.654321&q=Testby%20Hallen"
    # The stadium is the location; only a match repeats it in the description.
    assert not any(line.startswith(("Stadion:", "Bane:")) for line in lines)


async def test_staevne_without_a_placed_stadium_keeps_its_name_as_location(
    hass: HomeAssistant, config_entry, mock_activities
):
    """When the register does not place the stadium, its name is still a better location than none."""
    staevne = replace(
        mock_activities[1], type_id=7, type_name="DBU-Stævne", meeting_place="", stadium_name="Klubbens anlæg"
    )
    await _setup(hass, config_entry, [staevne])

    [event] = await _all_events(hass, [staevne])

    assert event.location == "Klubbens anlæg"
    assert not any(line.startswith("Kort:") for line in event.description.splitlines())


async def test_event_venue_without_coordinates_or_field(hass: HomeAssistant, config_entry, mock_activities, mock_venue):
    """A venue without coordinates gives no map link, and its field fills in when the activity has none."""
    act = mock_activities[0]
    act = replace(
        act,
        meeting_time=None,
        meeting_place="",
        match=replace(act.match, field_name=""),
        venue=replace(mock_venue, latitude=None, longitude=None),
    )
    await _setup(hass, config_entry, [act])

    [event] = await _all_events(hass, [act])

    assert event.location == "Testby Stadion\nPrøvevej 1, 1234 Testby"
    lines = event.description.splitlines()
    assert lines[0] == "Type: Kamp"
    assert "Bane: Bane 2" in lines
    assert not any(line.startswith(("Kort:", "Mødetid:")) for line in lines)


async def test_events_start_at_meeting_time_when_enabled(hass: HomeAssistant, mock_activities, mock_venue):
    """With the option on, events with a meeting time start then and name the real start."""
    entry = _make_entry({CONF_START_AT_MEETING_TIME: True})
    match = replace(mock_activities[0], venue=mock_venue)
    training = replace(mock_activities[1], meeting_time=datetime(2026, 3, 1, 9, 30))
    no_meeting = mock_activities[2]
    activities = [match, training, no_meeting]
    await _setup(hass, entry, activities)

    events = await _all_events(hass, activities)

    assert [e.start for e in events] == [
        dt_util.as_local(datetime(2026, 3, 14, 9, 45)),
        dt_util.as_local(datetime(2026, 3, 15, 9, 30)),
        dt_util.as_local(no_meeting.start_time),
    ]
    assert [e.end for e in events] == [dt_util.as_local(a.end_time) for a in activities]
    assert events[0].description.splitlines()[:4] == [
        "Mødetid: 09:45",
        "Kampstart: 11:00",
        "Mødested: Sportsvej 1, 1234 Testby",
        "Type: Kamp",
    ]
    assert events[0].location == "Testby Stadion\nPrøvevej 1, 1234 Testby"
    assert events[1].description.splitlines()[:3] == ["Mødetid: 09:30", "Start: 10:00", "Type: Træning"]
    assert events[2].description.splitlines()[0] == "Type: Træning"


@pytest.mark.parametrize(("start_at_meeting", "expected"), [(False, 0), (True, 1)])
async def test_event_range_uses_event_start(hass: HomeAssistant, mock_activities, start_at_meeting, expected):
    """A range ending between the meeting time and kickoff holds the event only when it starts at the meeting."""
    match = mock_activities[0]
    await _setup(hass, _make_entry({CONF_START_AT_MEETING_TIME: start_at_meeting}), [match])
    entity = hass.data["entity_components"]["calendar"].get_entity(CALENDAR)

    events = await entity.async_get_events(
        hass,
        dt_util.as_local(match.start_time - timedelta(hours=3)),
        dt_util.as_local(match.start_time - timedelta(minutes=30)),
    )

    assert len(events) == expected


async def test_calendar_on_from_meeting_time_keeps_real_call_up_start(hass: HomeAssistant, mock_activities):
    """With the option on the calendar is on from the meeting time; next_udtaget_start stays the real start."""
    match = replace(mock_activities[0], signup_status_id=4, signup_status_name="Udtaget")
    now = dt_util.as_local(match.start_time - timedelta(minutes=30))
    with patch("custom_components.kampklar.calendar.dt_util.now", return_value=now):
        await _setup(hass, _make_entry({CONF_START_AT_MEETING_TIME: True}), [match])
        state = hass.states.get(CALENDAR)

    assert state.state == "on"
    assert state.attributes["start_time"] == "2026-03-14 09:45:00"
    assert state.attributes["next_udtaget_start"] == dt_util.as_local(match.start_time).isoformat()


@pytest.mark.parametrize(
    ("start_at_meeting", "expected"),
    [
        (True, ("on", "⭐ Udtaget: Testby BK - FC Eksempel", "2026-03-14 09:30:00", "Udtaget", "Kamp")),
        (False, ("off", "Træning", "2026-03-14 10:00:00", "Ikke svaret", "Træning")),
    ],
)
async def test_calendar_state_follows_the_earliest_event_start(
    hass: HomeAssistant, mock_activities, start_at_meeting, expected
):
    """The state and its attributes describe the event that starts first, which can be a later activity's meeting."""
    training = replace(
        mock_activities[1],
        start_time=datetime(2026, 3, 14, 10, 0),
        end_time=datetime(2026, 3, 14, 11, 0),
        meeting_time=None,
    )
    match = replace(
        mock_activities[0],
        meeting_time=datetime(2026, 3, 14, 9, 30),
        signup_status_id=4,
        signup_status_name="Udtaget",
    )
    now = dt_util.as_local(datetime(2026, 3, 14, 9, 40))
    with patch("custom_components.kampklar.calendar.dt_util.now", return_value=now):
        await _setup(hass, _make_entry({CONF_START_AT_MEETING_TIME: start_at_meeting}), [training, match])
        state = hass.states.get(CALENDAR)

    attrs = state.attributes
    assert (state.state, attrs["message"], attrs["start_time"], attrs["signup_status"], attrs["activity_type"]) == (
        expected
    )


def _meeting_place_lines(event: CalendarEvent) -> list[str]:
    return [line for line in event.description.splitlines() if line.startswith("Mødested:")]


@pytest.mark.parametrize("start_at_meeting", [False, True])
async def test_meeting_place_kept_when_venue_takes_the_location(
    hass: HomeAssistant, mock_activities, mock_venue, start_at_meeting
):
    """A meeting place away from the stadium stays in the description once the venue is the location."""
    match = replace(mock_activities[0], meeting_place="Klubhuset", venue=mock_venue)
    await _setup(hass, _make_entry({CONF_START_AT_MEETING_TIME: start_at_meeting}), [match])

    [event] = await _all_events(hass, [match])

    assert event.location == "Testby Stadion\nPrøvevej 1, 1234 Testby"
    assert _meeting_place_lines(event) == ["Mødested: Klubhuset"]


@pytest.mark.parametrize("place", ["", "testby stadion", "Testby Stadion, Prøvevej 1, 1234 Testby"])
async def test_no_meeting_place_line_when_it_adds_nothing(hass: HomeAssistant, mock_activities, mock_venue, place):
    """No meeting place line when it is empty or only repeats the venue."""
    match = replace(mock_activities[0], meeting_place=place, venue=mock_venue)
    await _setup(hass, _make_entry(), [match])

    [event] = await _all_events(hass, [match])

    assert _meeting_place_lines(event) == []


async def test_no_meeting_place_line_without_venue(hass: HomeAssistant, mock_activities):
    """Without a venue the meeting place is the location, so the description does not repeat it."""
    await _setup(hass, _make_entry(), mock_activities[:1])

    [event] = await _all_events(hass, mock_activities[:1])

    assert event.location == "Sportsvej 1, 1234 Testby"
    assert _meeting_place_lines(event) == []
