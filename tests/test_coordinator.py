"""Tests for the KampKlar coordinator."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kampklar.api import (
    Activity,
    KampKlarApiClient,
    KampKlarAuthError,
    KampKlarConnectionError,
    MatchVenue,
)
from custom_components.kampklar.const import (
    CONF_PERSON_ID,
    CONF_PERSON_NAME,
    CONF_PERSONS,
    DOMAIN,
    VENUE_LOOKUPS_PER_REFRESH,
    VENUE_MAX_AGE,
    VENUE_RETRY_MAX,
    VENUE_RETRY_MIN,
)
from custom_components.kampklar.coordinator import KampKlarCoordinator, VenueRecord

from .conftest import load_fixture

pytestmark = pytest.mark.usefixtures("auto_enable_custom_integrations")

PERSON_ID = 300001
MATCH_KEY = "500001_400001"


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


def _match_activity(start: str, end: str) -> Activity:
    return Activity.from_api(
        {
            "activity": {
                "id": 1,
                "name": "Home - Away",
                "typeId": 2,
                "typeName": "Kamp",
                "startTime": start,
                "endTime": end,
                "match": {"matchId": 500001, "poolId": 500002, "homeTeamName": "Home", "awayTeamName": "Away"},
            }
        }
    )


async def test_active_match_window_uses_local_time(hass: HomeAssistant, config_entry, freezer):
    """Kickoff times are naive local times; the window must be evaluated in local time, not UTC."""
    coordinator = KampKlarCoordinator(hass, AsyncMock(spec=KampKlarApiClient), config_entry)
    act = _match_activity("2026-03-14T11:00:00", "2026-03-14T12:20:00")

    # One hour before kickoff, local time (the test instance runs in US/Pacific, far from UTC).
    freezer.move_to(dt_util.as_utc(datetime(2026, 3, 14, 10, 0, tzinfo=dt_util.get_default_time_zone())))
    assert coordinator._active_match([act]) is act

    # Four hours before kickoff is outside the two-hour lead-in.
    freezer.move_to(dt_util.as_utc(datetime(2026, 3, 14, 7, 0, tzinfo=dt_util.get_default_time_zone())))
    assert coordinator._active_match([act]) is None

    # Four hours after the end is past the three-hour tail.
    freezer.move_to(dt_util.as_utc(datetime(2026, 3, 14, 16, 30, tzinfo=dt_util.get_default_time_zone())))
    assert coordinator._active_match([act]) is None


def _store_key(entry: MockConfigEntry) -> str:
    return f"{DOMAIN}.venues.{entry.entry_id}"


@pytest.fixture
def venue_client(mock_activities, mock_venue) -> AsyncMock:
    """A client whose person has one match (500001/400001) with a known venue, plus two trainings."""
    client = AsyncMock(spec=KampKlarApiClient)
    client.get_person_activities.return_value = mock_activities
    client.get_match_venue.return_value = mock_venue
    return client


async def _coordinator(hass: HomeAssistant, client: AsyncMock, entry: MockConfigEntry) -> KampKlarCoordinator:
    coordinator = KampKlarCoordinator(hass, client, entry)
    await coordinator._async_setup()
    return coordinator


async def _refresh(coordinator: KampKlarCoordinator) -> list[Activity]:
    return (await coordinator._async_update_data())[PERSON_ID]


async def test_venue_attached_to_match_and_cached(
    hass: HomeAssistant, config_entry, venue_client, mock_venue, hass_storage, freezer
):
    """A match gets its venue from one GetMatch call; later polls within a week use the stored cache."""
    coordinator = await _coordinator(hass, venue_client, config_entry)

    activities = await _refresh(coordinator)
    assert activities[0].venue == mock_venue
    assert [a.venue for a in activities[1:]] == [None, None]
    venue_client.get_match_venue.assert_awaited_once_with(500001, 400001)

    freezer.tick(VENUE_MAX_AGE - timedelta(minutes=1))
    activities = await _refresh(coordinator)
    assert activities[0].venue == mock_venue
    venue_client.get_match_venue.assert_awaited_once()

    stored = hass_storage[_store_key(config_entry)]["data"]["venues"][MATCH_KEY]
    assert stored["stadium_name"] == "Testby Stadion"
    assert stored["venue"] == mock_venue.as_dict()
    assert stored["failures"] == 0
    assert stored["retry_after"] is None


async def test_venue_cache_survives_restart(hass: HomeAssistant, config_entry, venue_client, mock_venue, hass_storage):
    """Setup loads the stored venues before the first refresh, so a restart does not refetch them."""
    await _refresh(await _coordinator(hass, venue_client, config_entry))
    assert _store_key(config_entry) in hass_storage

    with patch("custom_components.kampklar.KampKlarApiClient", return_value=venue_client):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.runtime_data.data[PERSON_ID][0].venue == mock_venue
    venue_client.get_match_venue.assert_awaited_once()


async def test_venue_refetched_when_old_or_moved(
    hass: HomeAssistant, config_entry, venue_client, mock_activities, mock_venue, freezer
):
    """A venue older than a week is fetched again, and so is one whose stadium name changed."""
    coordinator = await _coordinator(hass, venue_client, config_entry)
    await _refresh(coordinator)

    freezer.tick(VENUE_MAX_AGE + timedelta(minutes=1))
    await _refresh(coordinator)
    assert venue_client.get_match_venue.await_count == 2

    moved = replace(mock_venue, name="Nyby Stadion", address="Nyvej 2")
    venue_client.get_match_venue.return_value = moved
    match = mock_activities[0]
    venue_client.get_person_activities.return_value = [
        replace(match, match=replace(match.match, stadium_name="Nyby Stadion"))
    ]
    activities = await _refresh(coordinator)
    assert venue_client.get_match_venue.await_count == 3
    assert activities[0].venue == moved
    assert coordinator.venues[MATCH_KEY].stadium_name == "Nyby Stadion"


@pytest.mark.parametrize(
    "failure",
    [KampKlarConnectionError("Timeout"), KampKlarAuthError("Denied"), TimeoutError(), ValueError("Not JSON"), None],
)
async def test_failed_venue_lookup_backs_off(
    hass: HomeAssistant, config_entry, venue_client, mock_venue, freezer, failure
):
    """A failed lookup leaves the match without a venue and is retried after a doubling wait."""
    if failure is None:
        venue_client.get_match_venue.return_value = None  # a response without a stadium
    else:
        venue_client.get_match_venue.side_effect = failure
    coordinator = await _coordinator(hass, venue_client, config_entry)
    lookups = venue_client.get_match_venue

    activities = await _refresh(coordinator)
    assert len(activities) == 3
    assert activities[0].venue is None
    assert lookups.await_count == 1

    freezer.tick(VENUE_RETRY_MIN - timedelta(minutes=1))
    await _refresh(coordinator)
    assert lookups.await_count == 1

    freezer.tick(timedelta(minutes=2))
    await _refresh(coordinator)
    assert lookups.await_count == 2
    assert coordinator.venues[MATCH_KEY].failures == 2
    assert coordinator.venues[MATCH_KEY].retry_after == dt_util.utcnow() + VENUE_RETRY_MIN * 2

    freezer.tick(VENUE_RETRY_MIN * 2 - timedelta(minutes=1))
    await _refresh(coordinator)
    assert lookups.await_count == 2

    lookups.side_effect = None
    lookups.return_value = mock_venue
    freezer.tick(timedelta(minutes=2))
    activities = await _refresh(coordinator)
    assert lookups.await_count == 3
    assert activities[0].venue == mock_venue
    assert coordinator.venues[MATCH_KEY] == VenueRecord("Testby Stadion", mock_venue, fetched_at=dt_util.utcnow())


async def test_venue_backoff_is_capped(hass: HomeAssistant, config_entry, venue_client):
    """However often a lookup has failed, the next attempt is at most a day away."""
    venue_client.get_match_venue.side_effect = KampKlarConnectionError("Timeout")
    coordinator = await _coordinator(hass, venue_client, config_entry)
    now = dt_util.utcnow()
    coordinator.venues[MATCH_KEY] = VenueRecord("Testby Stadion", failures=40, retry_after=now - timedelta(seconds=1))

    await _refresh(coordinator)

    assert coordinator.venues[MATCH_KEY].failures == 41
    assert coordinator.venues[MATCH_KEY].retry_after - now <= VENUE_RETRY_MAX + timedelta(seconds=1)


async def test_venue_failure_does_not_fail_setup(hass: HomeAssistant, config_entry, venue_client):
    """The entry loads with its activities even when every venue lookup fails."""
    venue_client.get_match_venue.side_effect = KampKlarConnectionError("Timeout")
    with patch("custom_components.kampklar.KampKlarApiClient", return_value=venue_client):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    assert len(config_entry.runtime_data.data[PERSON_ID]) == 3
    assert config_entry.runtime_data.data[PERSON_ID][0].venue is None


async def test_failed_refresh_keeps_known_venue(hass: HomeAssistant, config_entry, venue_client, mock_venue, freezer):
    """When the weekly refresh of a known venue fails, the old venue stays while it is retried."""
    coordinator = await _coordinator(hass, venue_client, config_entry)
    await _refresh(coordinator)
    fetched_at = dt_util.utcnow()

    freezer.tick(VENUE_MAX_AGE + timedelta(minutes=1))
    venue_client.get_match_venue.side_effect = KampKlarConnectionError("Timeout")
    activities = await _refresh(coordinator)
    assert activities[0].venue == mock_venue
    assert coordinator.venues[MATCH_KEY].failures == 1
    assert coordinator.venues[MATCH_KEY].fetched_at == fetched_at

    freezer.tick(timedelta(minutes=1))
    activities = await _refresh(coordinator)
    assert activities[0].venue == mock_venue
    assert venue_client.get_match_venue.await_count == 2


async def test_venues_of_past_matches_are_dropped(
    hass: HomeAssistant, config_entry, venue_client, mock_activities, hass_storage
):
    """A match that left the activity list is removed from the cache and the store."""
    coordinator = await _coordinator(hass, venue_client, config_entry)
    await _refresh(coordinator)
    assert MATCH_KEY in coordinator.venues

    venue_client.get_person_activities.return_value = mock_activities[1:]
    await _refresh(coordinator)

    assert coordinator.venues == {}
    assert hass_storage[_store_key(config_entry)]["data"] == {"venues": {}}


async def test_malformed_venue_cache_entries_are_ignored(
    hass: HomeAssistant, config_entry, venue_client, mock_venue, hass_storage
):
    """Invalid stored records or fields are dropped instead of breaking setup."""
    hass_storage[_store_key(config_entry)] = {
        "version": 1,
        "minor_version": 1,
        "key": _store_key(config_entry),
        "data": {
            "venues": {
                MATCH_KEY: {
                    "stadium_name": "Testby Stadion",
                    "venue": mock_venue.as_dict(),
                    "fetched_at": dt_util.utcnow().isoformat(),
                    "failures": 0,
                    "retry_after": None,
                },
                "1_1": "junk",
                "2_2": {"stadium_name": None},
                "3_3": {
                    "stadium_name": "Andet Stadion",
                    "venue": "junk",
                    "fetched_at": "not a time",
                    "failures": True,
                    "retry_after": "2026-01-01T00:00:00",
                },
            }
        },
    }

    coordinator = await _coordinator(hass, venue_client, config_entry)

    assert set(coordinator.venues) == {MATCH_KEY, "3_3"}
    assert coordinator.venues["3_3"] == VenueRecord("Andet Stadion")
    activities = await _refresh(coordinator)
    assert activities[0].venue == mock_venue
    venue_client.get_match_venue.assert_not_awaited()


@pytest.mark.parametrize("stored", [["not", "a", "dict"], {"venues": ["not", "a", "dict"]}])
async def test_venue_cache_with_wrong_shape_is_ignored(
    hass: HomeAssistant, config_entry, venue_client, hass_storage, stored
):
    """A stored cache of the wrong shape starts empty."""
    hass_storage[_store_key(config_entry)] = {"version": 1, "key": _store_key(config_entry), "data": stored}
    coordinator = await _coordinator(hass, venue_client, config_entry)
    assert coordinator.venues == {}


async def test_unreadable_venue_cache_starts_empty(hass: HomeAssistant, config_entry, venue_client):
    """A venue cache that cannot be read does not block setup."""
    coordinator = KampKlarCoordinator(hass, venue_client, config_entry)
    with patch.object(coordinator._venue_store, "async_load", side_effect=HomeAssistantError("corrupt")):
        await coordinator._async_setup()
    assert coordinator.venues == {}


STADIUM_KEY = "stadium:testby hallen"


def _staevne(base: Activity, stadium_name: str = "Testby Hallen") -> Activity:
    """Return a DBU stævne: no match object, a stadium named by its tournament round."""
    return replace(base, match=None, type_id=7, type_name="DBU-Stævne", stadium_name=stadium_name)


@pytest.fixture
def staevne_venue() -> MatchVenue:
    """The venue the stadium register returns for "Testby Hallen"."""
    return MatchVenue(
        name="Testby Hallen",
        address="Hallevej 1",
        zip="1234",
        city="Testby",
        latitude=56.1,
        longitude=9.6,
    )


async def test_staevne_venue_looked_up_by_stadium_name(
    hass: HomeAssistant, config_entry, venue_client, mock_activities, staevne_venue, hass_storage
):
    """A stævne has no match to ask about, so its stadium name is looked up and cached under that name."""
    venue_client.get_stadium_venue.return_value = staevne_venue
    venue_client.get_person_activities.return_value = [
        _staevne(mock_activities[1]),
        # A second stævne at the same stadium, spelled differently, shares the one lookup.
        _staevne(mock_activities[2], "TESTBY HALLEN"),
    ]
    coordinator = await _coordinator(hass, venue_client, config_entry)

    activities = await _refresh(coordinator)

    assert [a.venue for a in activities] == [staevne_venue, staevne_venue]
    venue_client.get_stadium_venue.assert_awaited_once_with("Testby Hallen")
    venue_client.get_match_venue.assert_not_awaited()
    stored = hass_storage[_store_key(config_entry)]["data"]["venues"][STADIUM_KEY]
    assert stored["stadium_name"] == "Testby Hallen"
    assert stored["venue"] == staevne_venue.as_dict()


async def test_staevne_venue_follows_a_moved_stadium(
    hass: HomeAssistant, config_entry, venue_client, mock_activities, staevne_venue
):
    """A stævne moved to another stadium is looked up again, and the old stadium leaves the cache."""
    venue_client.get_stadium_venue.return_value = staevne_venue
    venue_client.get_person_activities.return_value = [_staevne(mock_activities[1])]
    coordinator = await _coordinator(hass, venue_client, config_entry)
    await _refresh(coordinator)

    moved = replace(staevne_venue, name="Nyby Hallen", address="Nyvej 2")
    venue_client.get_stadium_venue.return_value = moved
    venue_client.get_person_activities.return_value = [_staevne(mock_activities[1], "Nyby Hallen")]
    activities = await _refresh(coordinator)

    assert activities[0].venue == moved
    assert venue_client.get_stadium_venue.await_count == 2
    assert set(coordinator.venues) == {"stadium:nyby hallen"}


async def test_unplaced_stadium_leaves_the_staevne_without_a_venue(
    hass: HomeAssistant, config_entry, venue_client, mock_activities, freezer
):
    """A stadium name the register does not place is retried later, not on every poll."""
    venue_client.get_stadium_venue.return_value = None
    venue_client.get_person_activities.return_value = [_staevne(mock_activities[1], "Klubbens anlæg")]
    coordinator = await _coordinator(hass, venue_client, config_entry)

    activities = await _refresh(coordinator)
    assert activities[0].venue is None
    assert venue_client.get_stadium_venue.await_count == 1

    freezer.tick(VENUE_RETRY_MIN - timedelta(minutes=1))
    await _refresh(coordinator)
    assert venue_client.get_stadium_venue.await_count == 1

    freezer.tick(timedelta(minutes=2))
    await _refresh(coordinator)
    assert venue_client.get_stadium_venue.await_count == 2


async def test_activity_without_a_place_is_never_looked_up(
    hass: HomeAssistant, config_entry, venue_client, mock_activities
):
    """A training names neither a match nor a stadium, so nothing is looked up or cached for it."""
    venue_client.get_person_activities.return_value = mock_activities[1:]
    coordinator = await _coordinator(hass, venue_client, config_entry)

    activities = await _refresh(coordinator)

    assert [a.venue for a in activities] == [None, None]
    venue_client.get_stadium_venue.assert_not_awaited()
    venue_client.get_match_venue.assert_not_awaited()
    assert coordinator.venues == {}


def _matches(base: Activity, count: int) -> list[Activity]:
    """Return count matches with their own match ids, one day apart, listed latest first."""
    return [
        replace(
            base,
            activity_id=base.activity_id + i,
            start_time=base.start_time + timedelta(days=i),
            end_time=base.end_time + timedelta(days=i),
            match=replace(base.match, match_id=600000 + i),
        )
        for i in reversed(range(count))
    ]


async def test_venue_lookups_run_together_and_are_capped(hass: HomeAssistant, config_entry, venue_client, mock_venue):
    """Due lookups run concurrently, at most the cap per refresh, nearest matches first; the rest follow next time."""
    matches = _matches(venue_client.get_person_activities.return_value[0], VENUE_LOOKUPS_PER_REFRESH + 2)
    venue_client.get_person_activities.return_value = matches
    in_flight = peak = 0

    async def lookup(match_id: int, pool_id: int):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0)
        in_flight -= 1
        return mock_venue

    venue_client.get_match_venue.side_effect = lookup
    coordinator = await _coordinator(hass, venue_client, config_entry)

    activities = await _refresh(coordinator)

    assert peak == VENUE_LOOKUPS_PER_REFRESH
    requested = [c.args[0] for c in venue_client.get_match_venue.await_args_list]
    assert sorted(requested) == [600000 + i for i in range(VENUE_LOOKUPS_PER_REFRESH)]
    latest_two = {600000 + VENUE_LOOKUPS_PER_REFRESH, 600001 + VENUE_LOOKUPS_PER_REFRESH}
    assert {a.match.match_id for a in activities if a.venue is None} == latest_two
    # Left over for lack of room, not failed: no backoff record.
    assert not any(record.failures for record in coordinator.venues.values())

    activities = await _refresh(coordinator)

    assert venue_client.get_match_venue.await_count == VENUE_LOOKUPS_PER_REFRESH + 2
    assert all(a.venue == mock_venue for a in activities)


async def test_hanging_venue_lookup_is_cut_off(hass: HomeAssistant, config_entry, venue_client):
    """A lookup that never answers ends after its time limit, the refresh completes, and the match backs off."""
    never = asyncio.Event()

    async def hang(match_id: int, pool_id: int):
        await never.wait()

    venue_client.get_match_venue.side_effect = hang
    coordinator = await _coordinator(hass, venue_client, config_entry)

    with patch("custom_components.kampklar.coordinator.VENUE_LOOKUP_TIMEOUT", 0.01):
        activities = await asyncio.wait_for(_refresh(coordinator), timeout=5)

    assert len(activities) == 3
    assert activities[0].venue is None
    assert coordinator.venues[MATCH_KEY].failures == 1


async def test_backoff_for_match_without_stadium_name_survives_restart(
    hass: HomeAssistant, config_entry, venue_client, hass_storage
):
    """A match whose feed has stadiumName null keeps its stored backoff across a restart."""
    entry = load_fixture("person_activities.json")[0]
    entry["activity"]["match"]["stadiumName"] = None
    venue_client.get_person_activities.return_value = [Activity.from_api(entry)]
    venue_client.get_match_venue.side_effect = KampKlarConnectionError("Timeout")

    await _refresh(await _coordinator(hass, venue_client, config_entry))
    assert hass_storage[_store_key(config_entry)]["data"]["venues"][MATCH_KEY]["stadium_name"] == ""

    restarted = await _coordinator(hass, venue_client, config_entry)
    assert restarted.venues[MATCH_KEY].failures == 1
    await _refresh(restarted)

    venue_client.get_match_venue.assert_awaited_once()


async def test_refresh_finishing_after_removal_does_not_recreate_cache(
    hass: HomeAssistant, config_entry, venue_client, mock_venue, hass_storage
):
    """A refresh still waiting on a lookup when the entry is removed does not write the deleted store back."""
    with patch("custom_components.kampklar.KampKlarApiClient", return_value=venue_client):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    coordinator = config_entry.runtime_data
    gate = asyncio.Event()

    async def slow(match_id: int, pool_id: int):
        await gate.wait()
        return mock_venue

    venue_client.get_match_venue.side_effect = slow
    coordinator.venues.clear()
    refresh = asyncio.get_running_loop().create_task(coordinator.async_refresh())
    while venue_client.get_match_venue.await_count < 2:
        await asyncio.sleep(0)

    await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()
    assert _store_key(config_entry) not in hass_storage

    gate.set()
    await refresh
    await hass.async_block_till_done()

    assert _store_key(config_entry) not in hass_storage


async def test_removing_entry_deletes_venue_cache(hass: HomeAssistant, config_entry, venue_client, hass_storage):
    """Removing the integration deletes its stored venue cache."""
    with patch("custom_components.kampklar.KampKlarApiClient", return_value=venue_client):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    assert _store_key(config_entry) in hass_storage

    await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()

    assert _store_key(config_entry) not in hass_storage
