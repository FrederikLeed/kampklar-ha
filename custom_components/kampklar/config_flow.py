"""Config flow for KampKlar integration."""

from homeassistant.config_entries import ConfigFlow

from .const import DOMAIN


class KampKlarConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for KampKlar."""

    VERSION = 1
