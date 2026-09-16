"""KampKlar integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import KampKlarApiClient
from .const import DOMAIN as DOMAIN
from .coordinator import KampKlarCoordinator, venue_store
from .services import async_setup_services, async_unload_services

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
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    async_setup_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KampKlarConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        async_unload_services(hass)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: KampKlarConfigEntry) -> None:
    """Delete the entry's stored venue cache when the entry is removed."""
    await venue_store(hass, entry.entry_id).async_remove()


async def _async_reload_entry(hass: HomeAssistant, entry: KampKlarConfigEntry) -> None:
    """Reload the entry when its options (e.g. scan interval) change."""
    await hass.config_entries.async_reload(entry.entry_id)
