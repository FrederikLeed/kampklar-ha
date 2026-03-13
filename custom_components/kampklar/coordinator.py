"""DataUpdateCoordinator for KampKlar."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import Activity, KampKlarApiClient, KampKlarAuthError, KampKlarConnectionError
from .const import CONF_PERSON_ID, CONF_PERSONS, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

type KampKlarData = dict[int, list[Activity]]


class KampKlarCoordinator(DataUpdateCoordinator[KampKlarData]):
    """Coordinator that polls activities for all tracked persons."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, client: KampKlarApiClient, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
            config_entry=entry,
        )
        self.client = client

    async def _async_update_data(self) -> KampKlarData:
        """Fetch activities for all tracked persons."""
        persons: list[dict] = self.config_entry.data[CONF_PERSONS]
        result: KampKlarData = {}
        try:
            for person in persons:
                person_id = person[CONF_PERSON_ID]
                result[person_id] = await self.client.get_person_activities(person_id)
        except KampKlarAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except KampKlarConnectionError as err:
            raise UpdateFailed(f"Connection error: {err}") from err
        return result
