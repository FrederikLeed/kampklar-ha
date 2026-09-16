"""KampKlar API client."""

from __future__ import annotations

import logging
from base64 import b64encode

import aiohttp

from .exceptions import KampKlarApiError, KampKlarAuthError, KampKlarConnectionError
from .models import Activity, MatchLive, MatchVenue, User

_LOGGER = logging.getLogger(__name__)

API_BASE_URL = "https://dbuappwebapi.dbu.dk"
_BASIC_AUTH = b64encode(b"AppService:!Fodbold!23").decode()
_DEFAULT_DEVICE_ID = 0
_APP_VERSION = "6.16.2"


class KampKlarApiClient:
    """Async client for the DBU KampKlar API."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialize the client."""
        self._session = session

    def _headers(self) -> dict[str, str]:
        """Return common request headers."""
        return {"Authorization": f"Basic {_BASIC_AUTH}"}

    async def authenticate(self, username: str, password: str) -> User:
        """Authenticate and return the User object."""
        url = f"{API_BASE_URL}/api/User/GetUserByCredentials"
        params = {"deviceId": _DEFAULT_DEVICE_ID}
        payload = {"UserName": username, "Password": password}
        data = await self._post(url, params=params, json=payload)
        if not data.get("isSuccess"):
            raise KampKlarAuthError(data.get("messageText", "Authentication failed"))
        return User.from_api(data["data"])

    async def get_person_activities(self, person_id: int) -> list[Activity]:
        """Fetch upcoming activities for a person."""
        url = f"{API_BASE_URL}/api/PersonActivity/GetList"
        params = {"deviceId": _DEFAULT_DEVICE_ID, "personId": person_id}
        data = await self._get(url, params=params)
        if not isinstance(data, list):
            return []
        # personContactId is null on a person's own activities in the live API, so it
        # must not be used as a filter: the list is already scoped by personId.
        return [Activity.from_api(entry) for entry in data if entry.get("activity")]

    async def get_match_live(self, match_id: int, pool_id: int, user_id: int) -> MatchLive | None:
        """Fetch the fixture and its live-score data for a match, combined into MatchLive."""
        live_url = f"{API_BASE_URL}/api/MatchLiveScore/GetMatchLiveScoreData"
        common = {"deviceId": _DEFAULT_DEVICE_ID}
        try:
            match = await self._get_match(match_id, pool_id)
            live = await self._get(
                live_url, params={**common, "matchId": match_id, "poolId": pool_id, "userId": user_id}
            )
        except KampKlarApiError:
            return None
        if not isinstance(match, dict):
            return None
        return MatchLive.from_api(match, live if isinstance(live, dict) else {})

    async def get_match_venue(self, match_id: int, pool_id: int) -> MatchVenue | None:
        """Fetch where a match is played (stadium address, coordinates and field) from Match/GetMatch.

        A failed request raises KampKlarApiError (or a subclass) so the caller can back off; a
        response without a usable stadium returns None.
        """
        match = await self._get_match(match_id, pool_id)
        return MatchVenue.from_api(match) if isinstance(match, dict) else None

    async def get_stadium_venue(self, stadium_name: str) -> MatchVenue | None:
        """Look up a stadium by name in DBU's stadium register and return where it is, or None.

        A tournament round (a DBU stævne) names its stadium but carries no match, so there is nothing to
        ask Match/GetMatch for. A failed request raises KampKlarApiError (or a subclass); a name that the
        register does not place returns None.
        """
        name = stadium_name.strip()
        if not name:
            # An empty name is not a search: the register answers it with all of its ~3,900 stadiums.
            return None
        url = f"{API_BASE_URL}/api/Stadium/GetListStadiumSearch"
        results = await self._get(url, params={"deviceId": _DEFAULT_DEVICE_ID, "name": name})
        return MatchVenue.from_stadium_search(results, name)

    async def _get_match(self, match_id: int, pool_id: int) -> dict | list:
        """GET the Match/GetMatch fixture for a match."""
        url = f"{API_BASE_URL}/api/Match/GetMatch"
        return await self._get(url, params={"deviceId": _DEFAULT_DEVICE_ID, "matchId": match_id, "poolId": pool_id})

    async def set_signup_status(self, activity_id: int, person_id: int, status_id: int, user_id: int) -> str:
        """Set a person's sign-up status for a team activity (tilmeld/afmeld/etc.).

        status_id follows SignUpStatusKind: 1 = afmeld (Frameldt), 2 = tilmeld (Tilmeldt).
        Returns the backend message text; raises KampKlarApiError on a non-success result.
        """
        url = f"{API_BASE_URL}/api/TeamActivity/UpdateTeamActivityPerson"
        params = {
            "userId": user_id,
            "deviceId": _DEFAULT_DEVICE_ID,
            "appversion": _APP_VERSION,
        }
        payload = {
            "ActivityId": activity_id,
            "PersonId": person_id,
            "SignUpStatusId": status_id,
            "TeamPersonId": None,
            "Comment": None,
            "IsPrivateComment": False,
            "CreatedByTeamPerson": False,
        }
        data = await self._post(url, params=params, json=payload)
        if isinstance(data, dict) and not data.get("isSuccess", False):
            raise KampKlarApiError(data.get("messageText", "Sign-up change failed"))
        return data.get("messageText", "OK") if isinstance(data, dict) else "OK"

    async def _get(self, url: str, **kwargs) -> dict | list:
        """Make a GET request."""
        return await self._request("GET", url, **kwargs)

    async def _post(self, url: str, **kwargs) -> dict | list:
        """Make a POST request."""
        return await self._request("POST", url, **kwargs)

    async def _request(self, method: str, url: str, **kwargs) -> dict | list:
        """Execute an HTTP request with error handling."""
        kwargs.setdefault("headers", {}).update(self._headers())
        try:
            async with self._session.request(method, url, **kwargs) as resp:
                if resp.status == 401:
                    raise KampKlarAuthError("Invalid credentials")
                if resp.status != 200:
                    raise KampKlarApiError(f"API returned status {resp.status}")
                return await resp.json(content_type=None)
        except KampKlarApiError:
            raise
        except aiohttp.ClientError as err:
            raise KampKlarConnectionError(f"Connection error: {err}") from err
