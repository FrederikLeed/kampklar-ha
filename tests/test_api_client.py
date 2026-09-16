"""Tests for the KampKlar API client."""

from __future__ import annotations

import re

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.kampklar.api import (
    KampKlarApiClient,
    KampKlarApiError,
    KampKlarAuthError,
    KampKlarConnectionError,
)
from custom_components.kampklar.api.client import API_BASE_URL

from .conftest import load_fixture

LOGIN_URL = re.compile(rf"^{re.escape(API_BASE_URL)}/api/User/GetUserByCredentials\b")
ACTIVITIES_URL = re.compile(rf"^{re.escape(API_BASE_URL)}/api/PersonActivity/GetList\b")
STADIUM_SEARCH_URL = re.compile(rf"^{re.escape(API_BASE_URL)}/api/Stadium/GetListStadiumSearch\b")


@pytest.fixture
def mock_aiohttp():
    """Provide aioresponses context."""
    with aioresponses() as m:
        yield m


@pytest.fixture
async def client(mock_aiohttp):
    """Create an API client with a session mocked by aioresponses."""
    # Use ThreadedResolver to avoid pycares daemon thread that trips HA's
    # verify_cleanup fixture. All HTTP is mocked by aioresponses anyway.
    resolver = aiohttp.resolver.ThreadedResolver()
    connector = aiohttp.TCPConnector(resolver=resolver)
    session = aiohttp.ClientSession(connector=connector)
    yield KampKlarApiClient(session)
    await session.close()


async def test_authenticate_success(mock_aiohttp, client):
    """Test successful authentication."""
    login_data = load_fixture("login_response.json")
    mock_aiohttp.post(LOGIN_URL, payload=login_data)

    user = await client.authenticate("testuser", "testpass")
    assert user.user_id == 100001
    assert user.person_id == 200001
    assert user.first_name == "Test"
    assert user.last_name == "Ansen"


async def test_authenticate_invalid_credentials(mock_aiohttp, client):
    """Test authentication with invalid credentials."""
    mock_aiohttp.post(
        LOGIN_URL,
        payload={"returnValue": 0, "messageText": "Invalid credentials", "isSuccess": False, "data": None},
    )
    with pytest.raises(KampKlarAuthError, match="Invalid credentials"):
        await client.authenticate("bad", "creds")


async def test_authenticate_http_401(mock_aiohttp, client):
    """Test authentication returning 401."""
    mock_aiohttp.post(LOGIN_URL, status=401)
    with pytest.raises(KampKlarAuthError):
        await client.authenticate("user", "pass")


async def test_authenticate_connection_error(mock_aiohttp, client):
    """Test authentication with connection error."""
    mock_aiohttp.post(LOGIN_URL, exception=aiohttp.ClientConnectionError("Connection refused"))
    with pytest.raises(KampKlarConnectionError):
        await client.authenticate("user", "pass")


async def test_get_person_activities(mock_aiohttp, client):
    """Test fetching person activities."""
    activities_data = load_fixture("person_activities.json")
    mock_aiohttp.get(ACTIVITIES_URL, payload=activities_data)

    activities = await client.get_person_activities(300001)
    assert len(activities) == 3
    assert activities[0].name == "Testby BK - FC Eksempel"
    assert activities[0].type_id == 2
    assert activities[0].match is not None
    assert activities[0].match.home_team_name == "Testby BK"
    assert activities[1].name == "Træning"
    assert activities[1].match is None


async def test_get_person_activities_keeps_null_person_contact(mock_aiohttp, client):
    """Activities with null personContactId are kept: the live API sets it null on a person's own activities."""
    activities_data = load_fixture("person_activities.json")
    # Inject an entry with null personContactId (real API returns these)
    null_entry = {
        "activity": {
            "id": 9999,
            "name": "Ghost Activity",
            "typeId": 1,
            "typeName": "Træning",
            "startTime": "2026-03-20T10:00:00",
            "endTime": None,
            "meetingTime": None,
            "meetingPlace": "",
            "teamId": 100,
            "teamName": "U14",
            "clubName": "Test",
            "clubLogoUrl": "",
            "signupStatusId": 0,
            "signupStatusName": "Ikke svaret",
            "subscribed": 0,
            "subscribedText": "",
            "personContactId": None,
            "personContactName": None,
            "match": None,
        },
        "activityDateTime": "2026-03-20T10:00:00",
        "eType": 1,
        "sortingIndex": 0,
    }
    mock_aiohttp.get(ACTIVITIES_URL, payload=[null_entry, *activities_data])

    activities = await client.get_person_activities(300001)
    assert len(activities) == 4
    assert activities[0].name == "Ghost Activity"
    assert activities[0].person_contact_id is None
    assert activities[0].person_contact_name == ""


async def test_get_person_activities_empty(mock_aiohttp, client):
    """Test fetching activities when response is not a list."""
    mock_aiohttp.get(ACTIVITIES_URL, payload={})
    activities = await client.get_person_activities(123)
    assert activities == []


async def test_get_person_activities_server_error(mock_aiohttp, client):
    """Test server error when fetching activities."""
    mock_aiohttp.get(ACTIVITIES_URL, status=500)
    with pytest.raises(KampKlarApiError, match="status 500"):
        await client.get_person_activities(123)


UPDATE_SIGNUP_URL = re.compile(rf"^{re.escape(API_BASE_URL)}/api/TeamActivity/UpdateTeamActivityPerson\b")


async def test_set_signup_status_success(mock_aiohttp, client):
    """A successful sign-up change returns the backend message."""
    mock_aiohttp.post(
        UPDATE_SIGNUP_URL,
        payload={"isSuccess": True, "returnValue": 1, "messageText": "OK", "extraReturnObj": None},
    )
    msg = await client.set_signup_status(7000001, 9000000001, 2, 100001)
    assert msg == "OK"


async def test_set_signup_status_failure(mock_aiohttp, client):
    """A non-success result raises with the backend message."""
    mock_aiohttp.post(
        UPDATE_SIGNUP_URL,
        payload={"isSuccess": False, "messageText": "Tilmelding lukket", "extraReturnObj": None},
    )
    with pytest.raises(KampKlarApiError, match="Tilmelding lukket"):
        await client.set_signup_status(7000001, 9000000001, 2, 100001)


async def test_authenticate_captures_calendar_urls(mock_aiohttp, client):
    """The login response's ical URLs are captured on the user."""
    data = load_fixture("login_response.json")["data"]
    data = {
        **data,
        "refCalendarUrl": "webcal://ical.dbu.dk/ref",
        "myTeamCalendarUrl": "webcal://ical.dbu.dk/team",
        "teamActivityCalendarUrl": "webcal://ical.dbu.dk/activity",
    }
    mock_aiohttp.post(LOGIN_URL, payload={"isSuccess": True, "data": data})
    user = await client.authenticate("u", "p")
    assert user.team_calendar_url == "webcal://ical.dbu.dk/team"
    assert user.activity_calendar_url == "webcal://ical.dbu.dk/activity"


GET_MATCH_URL = re.compile(rf"^{re.escape(API_BASE_URL)}/api/Match/GetMatch\b")
LIVE_URL = re.compile(rf"^{re.escape(API_BASE_URL)}/api/MatchLiveScore/GetMatchLiveScoreData\b")


async def test_get_match_live_in_progress(mock_aiohttp, client):
    """A live match uses the live result and minute and parses events."""
    mock_aiohttp.get(
        GET_MATCH_URL,
        payload={
            "id": 500001,
            "matchDate": "2026-09-19T00:00:00",
            "matchTime": "12:00",
            "homeTeamName": "Eksempelby IF",
            "awayTeamName": "Testby BK",
            "homeScore": None,
            "awayScore": None,
            "stadiumName": "Hallen",
        },
    )
    mock_aiohttp.get(
        LIVE_URL,
        payload={
            "currentMinute": 33,
            "homeResult": 1,
            "awayResult": 2,
            "messageText": "",
            "matchLengthText": "2. halvleg",
            "matchLiveScoreList": [
                {
                    "eventTypeName": "Maal",
                    "minute": 30,
                    "isHomeTeamPlayer": False,
                    "isGoal": True,
                    "isCard": False,
                    "person": {"firstName": "A", "lastName": "B"},
                },
            ],
        },
    )
    m = await client.get_match_live(500001, 500002, 100001)
    assert m is not None
    assert m.is_live is True
    assert (m.home_score, m.away_score, m.current_minute) == (1, 2, 33)
    assert m.away_team == "Testby BK"
    assert len(m.events) == 1
    assert m.events[0].is_goal and not m.events[0].is_home
    assert m.events[0].player == "A B"


async def test_get_match_venue(mock_aiohttp, client, get_match_response):
    """The venue comes from GetMatch's stadium object, stripped, with coordinates and field."""
    mock_aiohttp.get(GET_MATCH_URL, payload=get_match_response)

    venue = await client.get_match_venue(500001, 400001)

    assert venue.formatted_address == "Testby Stadion, Prøvevej 1, 1234 Testby"
    assert (venue.latitude, venue.longitude) == (56.123456, 9.654321)
    assert venue.field_name == "Bane 2"
    [(method, url)] = mock_aiohttp.requests
    assert method == "GET"
    assert (url.query["matchId"], url.query["poolId"], url.query["deviceId"]) == ("500001", "400001", "0")


@pytest.mark.parametrize("payload", [[], {"id": 500001, "stadiumName": "Testby Stadion"}])
async def test_get_match_venue_without_stadium(mock_aiohttp, client, payload):
    """A response without a stadium object gives no venue."""
    mock_aiohttp.get(GET_MATCH_URL, payload=payload)
    assert await client.get_match_venue(500001, 400001) is None


async def test_get_match_venue_raises_on_error(mock_aiohttp, client):
    """A failed request raises, so the coordinator can back off."""
    mock_aiohttp.get(GET_MATCH_URL, status=500)
    with pytest.raises(KampKlarApiError, match="status 500"):
        await client.get_match_venue(500001, 400001)


async def test_get_stadium_venue(mock_aiohttp, client):
    """A stævne's stadium name is searched in the register and the exact match placed."""
    mock_aiohttp.get(
        STADIUM_SEARCH_URL,
        payload=[
            {"id": 1, "name": "Testby Hallen (Inde)", "address": "Indevej 2", "zip": "1234", "city": "Testby"},
            {
                "id": 2,
                "name": "Testby Hallen",
                "address": "Hallevej 1",
                "zip": "1234",
                "city": "Testby",
                "latitude": 56.1,
                "longitude": 9.6,
            },
        ],
    )

    venue = await client.get_stadium_venue(" Testby Hallen ")

    assert venue.formatted_address == "Testby Hallen, Hallevej 1, 1234 Testby"
    assert (venue.latitude, venue.longitude) == (56.1, 9.6)
    [(method, url)] = mock_aiohttp.requests
    assert method == "GET"
    assert (url.query["name"], url.query["deviceId"]) == ("Testby Hallen", "0")


async def test_get_stadium_venue_without_a_name_asks_nothing(mock_aiohttp, client):
    """An empty name is not searched: the register answers it with every stadium it has."""
    assert await client.get_stadium_venue("  ") is None
    assert not mock_aiohttp.requests


async def test_get_stadium_venue_unknown_stadium(mock_aiohttp, client):
    """A name the register does not know gives no venue."""
    mock_aiohttp.get(STADIUM_SEARCH_URL, payload=[])
    assert await client.get_stadium_venue("Klubbens anlæg") is None


async def test_get_stadium_venue_raises_on_error(mock_aiohttp, client):
    """A failed search raises, so the coordinator can back off."""
    mock_aiohttp.get(STADIUM_SEARCH_URL, status=500)
    with pytest.raises(KampKlarApiError, match="status 500"):
        await client.get_stadium_venue("Testby Hallen")


async def test_get_match_live_not_started(mock_aiohttp, client):
    """No live coverage: falls back to the fixture score and is not live."""
    mock_aiohttp.get(
        GET_MATCH_URL,
        payload={"id": 1, "homeTeamName": "H", "awayTeamName": "A", "homeScore": None, "awayScore": None},
    )
    mock_aiohttp.get(
        LIVE_URL,
        payload={
            "currentMinute": None,
            "homeResult": 0,
            "awayResult": 0,
            "messageText": "Ingen livescore",
            "matchLiveScoreList": [],
        },
    )
    m = await client.get_match_live(1, 2, 3)
    assert m.is_live is False
    assert m.home_score is None and m.away_score is None
    assert m.status_text == "Ingen livescore"
