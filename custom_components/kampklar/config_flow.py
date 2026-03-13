"""Config flow for KampKlar integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import KampKlarApiClient, KampKlarAuthError, KampKlarConnectionError
from .const import CONF_PERSON_ID, CONF_PERSON_NAME, CONF_PERSONS, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class KampKlarConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for KampKlar."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._user_input: dict[str, Any] = {}
        self._user_id: int = 0
        self._person_id: int = 0
        self._persons: dict[int, str] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the login step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = KampKlarApiClient(session)
            try:
                user = await client.authenticate(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
            except KampKlarAuthError:
                errors["base"] = "invalid_auth"
            except KampKlarConnectionError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(str(user.user_id))
                self._abort_if_unique_id_configured()

                self._user_input = user_input
                self._user_id = user.user_id
                self._person_id = user.person_id

                # Discover persons (children) from activities
                try:
                    activities = await client.get_person_activities(user.person_id)
                except (KampKlarAuthError, KampKlarConnectionError):
                    activities = []

                self._persons = {}
                for act in activities:
                    pid = act.person_contact_id
                    if pid not in self._persons:
                        self._persons[pid] = act.person_contact_name

                if len(self._persons) <= 1:
                    # Single person or no activities — skip selection
                    return self._create_entry()

                return await self.async_step_persons()

        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors)

    async def async_step_persons(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle person selection step."""
        if user_input is not None:
            selected: list[int] = user_input[CONF_PERSONS]
            # Filter to selected persons
            self._persons = {pid: name for pid, name in self._persons.items() if pid in selected}
            return self._create_entry()

        persons_schema = vol.Schema(
            {
                vol.Required(CONF_PERSONS, default=list(self._persons.keys())): vol.All(
                    vol.Coerce(list),
                    [vol.In(self._persons)],
                ),
            }
        )

        return self.async_show_form(
            step_id="persons",
            data_schema=persons_schema,
            description_placeholders={"persons": ", ".join(self._persons.values())},
        )

    def _create_entry(self) -> ConfigFlowResult:
        """Create the config entry from collected data."""
        persons_list = [{CONF_PERSON_ID: pid, CONF_PERSON_NAME: name} for pid, name in self._persons.items()]
        # If no persons discovered, use the parent person
        if not persons_list:
            persons_list = [{CONF_PERSON_ID: self._person_id, CONF_PERSON_NAME: ""}]

        data = {
            CONF_USERNAME: self._user_input[CONF_USERNAME],
            CONF_PASSWORD: self._user_input[CONF_PASSWORD],
            "user_id": self._user_id,
            CONF_PERSONS: persons_list,
        }
        return self.async_create_entry(title="KampKlar", data=data)
