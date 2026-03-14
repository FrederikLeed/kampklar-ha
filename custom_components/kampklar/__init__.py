"""KampKlar integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import KampKlarApiClient
from .const import DOMAIN as DOMAIN
from .coordinator import KampKlarCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CALENDAR, Platform.SENSOR]

type KampKlarConfigEntry = ConfigEntry[KampKlarCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: KampKlarConfigEntry) -> bool:
    """Set up KampKlar from a config entry."""
    session = async_get_clientsession(hass)
    client = KampKlarApiClient(session)

    coordinator = KampKlarCoordinator(hass, client, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KampKlarConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
