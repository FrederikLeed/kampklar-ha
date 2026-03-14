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


async def test_get_person_activities_skips_null_person_contact(mock_aiohttp, client):
    """Test that activities with null personContactId are filtered out."""
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
    assert len(activities) == 3  # null entry filtered out
    assert all(a.person_contact_id is not None for a in activities)


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
