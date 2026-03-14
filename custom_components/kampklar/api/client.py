"""KampKlar API client."""

from __future__ import annotations

import logging
from base64 import b64encode

import aiohttp

from .exceptions import KampKlarApiError, KampKlarAuthError, KampKlarConnectionError
from .models import Activity, User

_LOGGER = logging.getLogger(__name__)

API_BASE_URL = "https://dbuappwebapi.dbu.dk"
_BASIC_AUTH = b64encode(b"AppService:!Fodbold!23").decode()
_DEFAULT_DEVICE_ID = 0


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
        return [
            Activity.from_api(entry) for entry in data if entry.get("activity", {}).get("personContactId") is not None
        ]

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
