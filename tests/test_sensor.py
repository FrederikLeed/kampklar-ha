"""Tests for KampKlar sensor platform."""

from __future__ import annotations

import copy
from dataclasses import replace
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

    state = hass.states.get("sensor.test_ansen_next_activity")
    assert state is not None
    assert state.state == "Testby BK - FC Eksempel"
    assert state.attributes["type"] == "Kamp"
    assert state.attributes["team"] == "U14 Drenge"
    assert state.attributes["signup_status"] == "Tilmeldt"
    assert state.attributes["match_id"] == 500001

    state = hass.states.get("sensor.test_ansen_next_match")
    assert state is not None
    assert state.state == "Testby BK - FC Eksempel"
    assert state.attributes["stadium"] == "Testby Stadion"

    state = hass.states.get("sensor.test_ansen_pending_signups")
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

    state = hass.states.get("sensor.test_ansen_next_activity")
    assert state is not None
    assert state.state == "unknown"

    state = hass.states.get("sensor.test_ansen_next_match")
    assert state is not None
    assert state.state == "unknown"

    state = hass.states.get("sensor.test_ansen_pending_signups")
    assert state is not None
    assert state.state == "0"


async def _setup_with(hass: HomeAssistant, config_entry, activities: list[Activity]) -> None:
    """Set up the integration with the given parsed activities."""
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


def _entry(base: dict, **activity_changes) -> dict:
    """Copy a fixture entry and override activity fields."""
    entry = copy.deepcopy(base)
    entry["activity"].update(activity_changes)
    return entry


async def test_pending_counts_open_activities_without_status(hass: HomeAssistant, config_entry):
    """The live API sends signupStatusId null for unanswered activities; open ones are pending."""
    base = load_fixture("person_activities.json")[0]
    data = [
        _entry(base, id=1, name="Open, unanswered", signupStatusId=None, signupStatusName=None, isOpenForSignUp=True),
        _entry(base, id=2, name="Not open yet", signupStatusId=None, signupStatusName=None, isOpenForSignUp=False),
        _entry(base, id=3, name="Signed up", signupStatusId=2, signupStatusName="Tilmeldt", isOpenForSignUp=True),
    ]
    await _setup_with(hass, config_entry, [Activity.from_api(e) for e in data])

    state = hass.states.get("sensor.test_ansen_pending_signups")
    assert state.state == "1"
    assert state.attributes["activities"] == ["Open, unanswered"]


async def test_activity_attributes_enriched(hass: HomeAssistant, config_entry):
    """Next-activity sensor exposes deadline, meeting, open-for-signup, team assignment and tasks."""
    base = load_fixture("person_activities.json")[0]
    entry = _entry(
        base,
        id=77,
        isOpenForSignUp=True,
        subscriptionDeadline="2026-03-13T18:00:00",
        teamAssignmentName="U14 Drenge",
        tasks=2,
        meetingPlace="Sportsvej 1",
        meetingTime="2026-03-14T09:45:00",
    )
    await _setup_with(hass, config_entry, [Activity.from_api(entry)])

    a = hass.states.get("sensor.test_ansen_next_activity").attributes
    assert a["is_open_for_signup"] is True
    assert a["subscription_deadline"] == "2026-03-13T18:00:00"
    assert a["team_assignment"] == "U14 Drenge"
    assert a["tasks"] == 2
    assert a["meeting_place"] == "Sportsvej 1"
    assert a["meeting_time"] == "2026-03-14T09:45:00"


async def test_next_udtagelse_sensor(hass: HomeAssistant, config_entry):
    """The next-udtagelse sensor names the next activity the person is selected for."""
    fixture = load_fixture("person_activities.json")
    match_entry = next(e for e in fixture if e["activity"].get("match"))
    data = [
        _entry(match_entry, id=1, name="Træning", typeId=1, typeName="Træning", match=None, signupStatusId=2),
        _entry(match_entry, id=2, name="Udtaget kamp", signupStatusId=4, signupStatusName="Udtaget"),
    ]
    await _setup_with(hass, config_entry, [Activity.from_api(e) for e in data])

    state = hass.states.get("sensor.test_ansen_next_call_up")
    assert state.state == "Udtaget kamp"
    assert state.attributes["signup_status"] == "Udtaget"


async def test_next_udtagelse_none(hass: HomeAssistant, config_entry):
    """The sensor is unknown when the person is not on anything.

    An unanswered match counts for neither mode, and training never counts even when tilmeldt.
    """
    base = load_fixture("person_activities.json")[0]
    data = [
        _entry(base, id=1, signupStatusId=None, signupStatusName=None),
        _entry(base, id=2, typeId=1, typeName="Træning", match=None, signupStatusId=2, signupStatusName="Tilmeldt"),
    ]
    await _setup_with(hass, config_entry, [Activity.from_api(e) for e in data])
    assert hass.states.get("sensor.test_ansen_next_call_up").state == "unknown"


async def test_next_match_includes_practice_match(hass: HomeAssistant, config_entry):
    """A practice match (typeId 5) carries match details and counts as the next match."""
    fixture = load_fixture("person_activities.json")
    match_entry = next(e for e in fixture if e["activity"].get("match"))
    data = [
        _entry(match_entry, id=10, name="Træning", typeId=1, typeName="Træning", match=None),
        _entry(match_entry, id=11, typeId=5, typeName="Træningskamp"),
    ]
    await _setup_with(hass, config_entry, [Activity.from_api(e) for e in data])

    assert hass.states.get("sensor.test_ansen_next_activity").state == "Træning"
    state = hass.states.get("sensor.test_ansen_next_match")
    assert state.state == "Testby BK - FC Eksempel"
    assert state.attributes["type"] == "Træningskamp"


async def test_live_match_sensor(hass: HomeAssistant, config_entry):
    """The live-match sensor shows the score line and match details from the coordinator."""
    from custom_components.kampklar.api import MatchEvent, MatchLive

    await _setup_with(hass, config_entry, [])
    coordinator = config_entry.runtime_data
    coordinator.live_matches = {
        PERSON_ID: MatchLive(
            match_id=1,
            home_team="Eksempelby IF",
            away_team="Testby BK",
            home_logo="",
            away_logo="",
            home_score=1,
            away_score=2,
            current_minute=33,
            is_live=True,
            status_text="",
            match_length_text="2. halvleg",
            events=[MatchEvent(minute=30, type_name="Maal", is_home=False, player="X Y", is_goal=True, is_card=False)],
            kickoff=None,
            stadium="Hallen",
        )
    }
    coordinator.async_update_listeners()

    state = hass.states.get("sensor.test_ansen_live_match")
    assert state.state == "1 - 2"
    assert state.attributes["minute"] == 33
    assert state.attributes["is_live"] is True
    assert state.attributes["away_team"] == "Testby BK"
    assert len(state.attributes["events"]) == 1
    assert state.attributes["events"][0]["is_goal"] is True


async def test_next_match_and_call_up_expose_venue(hass: HomeAssistant, config_entry, mock_venue):
    """Next match and next call-up carry the stadium address, coordinates and the repaired meeting time."""
    match_entry = load_fixture("person_activities.json")[0]
    data = [
        _entry(
            match_entry,
            id=1,
            name="Træning",
            typeId=1,
            typeName="Træning",
            match=None,
            startTime="2026-03-14T09:00:00",
            endTime="2026-03-14T10:00:00",
            meetingTime="2026-03-14T08:45:00",
        ),
        _entry(match_entry, id=2, signupStatusId=4, signupStatusName="Udtaget", meetingTime="2026-02-20T10:00:00"),
    ]
    activities = [Activity.from_api(e) for e in data]
    activities[1] = replace(activities[1], venue=mock_venue)
    await _setup_with(hass, config_entry, activities)

    for entity_id in ("sensor.test_ansen_next_match", "sensor.test_ansen_next_call_up"):
        attrs = hass.states.get(entity_id).attributes
        assert attrs["stadium"] == "Testby Stadion"
        assert attrs["stadium_address"] == "Testby Stadion, Prøvevej 1, 1234 Testby"
        assert attrs["latitude"] == 56.123456
        assert attrs["longitude"] == 9.654321
        assert attrs["meeting_time"] == "2026-03-14T10:00:00"
        assert attrs["start_time"] == "2026-03-14T11:00:00"

    attrs = hass.states.get("sensor.test_ansen_next_activity").attributes
    assert attrs["meeting_time"] == "2026-03-14T08:45:00"
    assert not {"stadium_address", "latitude", "longitude"} & attrs.keys()


@pytest.mark.parametrize(
    ("meeting_time", "match_meeting_time"),
    [
        # Equal to the start: not a meeting time for the match sensors, but next activity keeps it as before.
        ("2026-03-14T11:00:00", None),
        # Wrong date: next activity shows it as DBU sent it, the match sensors repair it.
        ("2026-02-20T10:00:00", "2026-03-14T10:00:00"),
    ],
)
async def test_next_activity_keeps_meeting_time_as_sent(
    hass: HomeAssistant, config_entry, mock_venue, meeting_time, match_meeting_time
):
    """The next-activity sensor's meeting_time is unchanged from 0.6.1; next match and call-up use the repaired one."""
    base = load_fixture("person_activities.json")[0]
    act = Activity.from_api(_entry(base, meetingTime=meeting_time, signupStatusId=4, signupStatusName="Udtaget"))
    await _setup_with(hass, config_entry, [replace(act, venue=mock_venue)])

    assert hass.states.get("sensor.test_ansen_next_activity").attributes["meeting_time"] == meeting_time
    for entity_id in ("sensor.test_ansen_next_match", "sensor.test_ansen_next_call_up"):
        assert hass.states.get(entity_id).attributes.get("meeting_time") == match_meeting_time


async def test_venue_attributes_only_when_known(hass: HomeAssistant, config_entry, mock_venue):
    """Without coordinates there is no latitude or longitude; a meeting time after the start is left out."""
    base = load_fixture("person_activities.json")[0]
    act = Activity.from_api(_entry(base, meetingTime="2026-03-14T11:30:00"))
    await _setup_with(hass, config_entry, [replace(act, venue=replace(mock_venue, latitude=None, longitude=None))])

    attrs = hass.states.get("sensor.test_ansen_next_match").attributes
    assert attrs["stadium_address"] == "Testby Stadion, Prøvevej 1, 1234 Testby"
    assert not {"latitude", "longitude", "meeting_time"} & attrs.keys()


async def test_staevne_call_up_has_its_stadium_and_address(hass: HomeAssistant, config_entry, mock_venue):
    """A call-up for a stævne names its stadium and, once looked up, its address and coordinates."""
    base = load_fixture("person_activities.json")[1]
    entry = _entry(
        base,
        name="Stævne: Testby Hallen",
        typeId=7,
        typeName="DBU-Stævne",
        signupStatusId=4,
        signupStatusName="Udtaget",
        stadiumRound={"stadiumName": "Testby Hallen", "rowName": "U9 Piger", "poolName": "Pulje 206"},
    )
    hallen = replace(mock_venue, name="Testby Hallen", address="Hallevej 1")
    await _setup_with(hass, config_entry, [replace(Activity.from_api(entry), venue=hallen)])

    attrs = hass.states.get("sensor.test_ansen_next_call_up").attributes

    assert attrs["stadium"] == "Testby Hallen"
    assert attrs["stadium_address"] == "Testby Hallen, Hallevej 1, 1234 Testby"
    assert (attrs["latitude"], attrs["longitude"]) == (56.123456, 9.654321)
    assert "match_id" not in attrs


@pytest.mark.parametrize(
    ("subscribed_text", "expected"),
    [
        ("14 tilmeldte", False),
        ("8 udtaget", True),
        ("0 udtaget", True),
        ("0 tilmeldte", False),
        ("", None),
        ("13 Tilmeldte", False),
    ],
)
def test_selection_mode_read_from_the_counter(subscribed_text, expected):
    """The counter text is the only place DBU names how an activity picks its players."""
    base = load_fixture("person_activities.json")[0]
    act = Activity.from_api(_entry(base, id=1, subscribedText=subscribed_text))
    assert act.selection_mode is expected


async def test_next_udtagelse_on_a_signup_match(hass: HomeAssistant, config_entry):
    """A team that signs up never reaches udtaget, so tilmeldt is what the sensor reports.

    This is the live shape of Jonas' U15 league match: "14 tilmeldte", signupStatusId 2.
    """
    base = load_fixture("person_activities.json")[0]
    data = [
        _entry(base, id=1, name="Ikke svaret", signupStatusId=None, signupStatusName=None),
        _entry(
            base, id=2, name="Gug B - AaB", signupStatusId=2, signupStatusName="Tilmeldt", subscribedText="14 tilmeldte"
        ),
    ]
    await _setup_with(hass, config_entry, [Activity.from_api(e) for e in data])
    state = hass.states.get("sensor.test_ansen_next_call_up")
    assert state.state == "Gug B - AaB"
    assert state.attributes["selection_mode"] == "tilmelding"
    assert state.attributes["is_playing"] is True


async def test_next_udtagelse_prefers_udtaget_on_a_selection_activity(hass: HomeAssistant, config_entry):
    """Where a coach picks the squad, tilmeldt is not enough - only udtaget counts.

    This is the live shape of Alba's DBU-stævne: "8 udtaget", signupStatusId 4.
    """
    base = load_fixture("person_activities.json")[0]
    data = [
        _entry(
            base, id=1, name="Kun tilmeldt", signupStatusId=2, signupStatusName="Tilmeldt", subscribedText="9 udtaget"
        ),
        _entry(base, id=2, name="Stævne", signupStatusId=4, signupStatusName="Udtaget", subscribedText="8 udtaget"),
    ]
    await _setup_with(hass, config_entry, [Activity.from_api(e) for e in data])
    state = hass.states.get("sensor.test_ansen_next_call_up")
    assert state.state == "Stævne"
    assert state.attributes["selection_mode"] == "udtagelse"


async def test_training_never_counts_as_playing(hass: HomeAssistant, config_entry):
    """Everyone is signed up for training, so counting it would mark every week."""
    base = load_fixture("person_activities.json")[0]
    data = [
        _entry(base, id=1, typeId=1, typeName="Træning", match=None, signupStatusId=2, signupStatusName="Tilmeldt"),
    ]
    await _setup_with(hass, config_entry, [Activity.from_api(e) for e in data])
    assert hass.states.get("sensor.test_ansen_next_call_up").state == "unknown"


async def test_unknown_mode_counts_only_udtaget(hass: HomeAssistant, config_entry):
    """With no counter text the mode is unknown, so the pre-0.9 rule applies: udtaget only."""
    base = load_fixture("person_activities.json")[0]
    data = [_entry(base, id=1, signupStatusId=2, signupStatusName="Tilmeldt", subscribedText="")]
    await _setup_with(hass, config_entry, [Activity.from_api(e) for e in data])
    assert hass.states.get("sensor.test_ansen_next_call_up").state == "unknown"
