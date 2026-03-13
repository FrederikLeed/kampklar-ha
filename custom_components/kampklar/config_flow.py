"""Config flow for KampKlar integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import SelectOptionDict, SelectSelector, SelectSelectorConfig

from .api import KampKlarApiClient, KampKlarAuthError, KampKlarConnectionError
from .const import CONF_PERSON_ID, CONF_PERSON_NAME, CONF_PERSONS, DOMAIN

_LOGGER = logging.getLogger(__name__)


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
            except Exception:
                _LOGGER.exception("KampKlar unexpected error during auth")
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(str(user.user_id))
                self._abort_if_unique_id_configured()

                self._user_input = user_input
                self._user_id = user.user_id
                self._person_id = user.person_id

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
                    return self._create_entry()

                return await self.async_step_persons()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_persons(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle person selection step."""
        if user_input is not None:
            selected = {int(pid) for pid in user_input[CONF_PERSONS]}
            self._persons = {pid: name for pid, name in self._persons.items() if pid in selected}
            return self._create_entry()

        options = [SelectOptionDict(value=str(pid), label=name) for pid, name in self._persons.items()]
        persons_schema = vol.Schema(
            {
                vol.Required(CONF_PERSONS, default=[str(pid) for pid in self._persons]): SelectSelector(
                    SelectSelectorConfig(options=options, multiple=True)
                ),
            }
        )

        return self.async_show_form(
            step_id="persons",
            data_schema=persons_schema,
            description_placeholders={"persons": ", ".join(self._persons.values())},
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle reauthentication when credentials expire."""
        self._user_input = {CONF_USERNAME: entry_data[CONF_USERNAME]}
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle reauth credential input."""
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = KampKlarApiClient(session)
            try:
                user = await client.authenticate(self._user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
            except KampKlarAuthError:
                errors["base"] = "invalid_auth"
            except KampKlarConnectionError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(str(user.user_id))
                self._abort_if_unique_id_mismatch()
                reauth_entry = self._get_reauth_entry()
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data={**reauth_entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"username": self._user_input[CONF_USERNAME]},
            errors=errors,
        )

    def _create_entry(self) -> ConfigFlowResult:
        """Create the config entry from collected data."""
        persons_list = [{CONF_PERSON_ID: pid, CONF_PERSON_NAME: name} for pid, name in self._persons.items()]
        if not persons_list:
            persons_list = [{CONF_PERSON_ID: self._person_id, CONF_PERSON_NAME: ""}]

        data = {
            CONF_USERNAME: self._user_input[CONF_USERNAME],
            CONF_PASSWORD: self._user_input[CONF_PASSWORD],
            "user_id": self._user_id,
            CONF_PERSONS: persons_list,
        }
        return self.async_create_entry(title="KampKlar", data=data)
