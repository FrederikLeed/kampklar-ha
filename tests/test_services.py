"""Tests for the KampKlar tilmeld/afmeld services."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kampklar.api import KampKlarApiError
from custom_components.kampklar.const import (
    CONF_PERSON_ID,
    CONF_PERSON_NAME,
    CONF_PERSONS,
    DOMAIN,
    SIGNUP_SIGNED_OFF,
    SIGNUP_SIGNED_UP,
)

pytestmark = pytest.mark.usefixtures("auto_enable_custom_integrations")

PERSON_ID = 9000000001
USER_ID = 100001
ACTIVITY_ID = 7000001


@pytest.fixture
def config_entry():
    """A config entry tracking one person with a known user_id."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="KampKlar",
        data={
            CONF_USERNAME: "u",
            CONF_PASSWORD: "p",
            "user_id": USER_ID,
            CONF_PERSONS: [{CONF_PERSON_ID: PERSON_ID, CONF_PERSON_NAME: "Emma"}],
        },
        unique_id=str(USER_ID),
    )


async def _setup(hass: HomeAssistant, config_entry, activities=None) -> AsyncMock:
    activities = activities or []
    client = AsyncMock()
    client.get_person_activities.return_value = activities
    # A service call refreshes through the real coordinator; without this the mock would hand it a mock venue.
    client.get_match_venue.return_value = None
    with (
        patch("custom_components.kampklar.KampKlarApiClient", return_value=client),
        patch(
            "custom_components.kampklar.KampKlarCoordinator._async_update_data",
            return_value={PERSON_ID: activities},
        ),
    ):
        config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    return client


def _child_device(hass: HomeAssistant) -> dr.DeviceEntry:
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, str(PERSON_ID))})
    assert device is not None
    return device


async def test_tilmeld_with_person_and_activity_id(hass: HomeAssistant, config_entry):
    """The original call shape (person_id + activity_id) keeps working."""
    client = await _setup(hass, config_entry)
    await hass.services.async_call(
        DOMAIN, "tilmeld", {"person_id": PERSON_ID, "activity_id": ACTIVITY_ID}, blocking=True
    )
    client.set_signup_status.assert_awaited_once_with(ACTIVITY_ID, PERSON_ID, SIGNUP_SIGNED_UP, USER_ID)


async def test_afmeld_with_person_and_activity_id(hass: HomeAssistant, config_entry):
    """kampklar.afmeld calls the API with status 1."""
    client = await _setup(hass, config_entry)
    await hass.services.async_call(
        DOMAIN, "afmeld", {"person_id": PERSON_ID, "activity_id": ACTIVITY_ID}, blocking=True
    )
    client.set_signup_status.assert_awaited_once_with(ACTIVITY_ID, PERSON_ID, SIGNUP_SIGNED_OFF, USER_ID)


async def test_device_target_defaults_to_next_activity(hass: HomeAssistant, config_entry, mock_activities):
    """Targeting the child's device without an activity uses their next activity and reports it."""
    client = await _setup(hass, config_entry, mock_activities)
    device = _child_device(hass)

    response = await hass.services.async_call(
        DOMAIN, "tilmeld", {"device_id": device.id}, blocking=True, return_response=True
    )

    nxt = mock_activities[0]
    client.set_signup_status.assert_awaited_once_with(nxt.activity_id, PERSON_ID, SIGNUP_SIGNED_UP, USER_ID)
    assert response == {
        "results": [
            {
                "person": "Emma",
                "activity_id": nxt.activity_id,
                "activity": nxt.name.strip(),
                "start_time": nxt.start_time.isoformat(),
                "status": "tilmeldt",
            }
        ]
    }


async def test_entity_target_resolves_to_child(hass: HomeAssistant, config_entry, mock_activities):
    """Targeting any of the child's entities works like targeting the device."""
    client = await _setup(hass, config_entry, mock_activities)
    entity_id = er.async_entries_for_device(er.async_get(hass), _child_device(hass).id)[0].entity_id

    await hass.services.async_call(DOMAIN, "afmeld", {"entity_id": entity_id}, blocking=True)

    client.set_signup_status.assert_awaited_once_with(
        mock_activities[0].activity_id, PERSON_ID, SIGNUP_SIGNED_OFF, USER_ID
    )


async def test_no_target_is_a_validation_error(hass: HomeAssistant, config_entry):
    """A call without a child is rejected with a clear error."""
    await _setup(hass, config_entry)
    with pytest.raises(ServiceValidationError, match="Choose"):
        await hass.services.async_call(DOMAIN, "tilmeld", {}, blocking=True)


async def test_no_upcoming_activity_is_a_validation_error(hass: HomeAssistant, config_entry):
    """Without an activity_id and no upcoming activity there is nothing to sign up for."""
    await _setup(hass, config_entry)
    with pytest.raises(ServiceValidationError, match="no upcoming activity"):
        await hass.services.async_call(DOMAIN, "tilmeld", {"device_id": _child_device(hass).id}, blocking=True)


async def test_service_unknown_person(hass: HomeAssistant, config_entry):
    """Calling for a person not configured is a validation error."""
    await _setup(hass, config_entry)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "tilmeld", {"person_id": 1, "activity_id": ACTIVITY_ID}, blocking=True)


async def test_service_api_error_surfaces(hass: HomeAssistant, config_entry):
    """A backend rejection surfaces as a HomeAssistantError."""
    client = await _setup(hass, config_entry)
    client.set_signup_status.side_effect = KampKlarApiError("Tilmelding lukket")
    with pytest.raises(HomeAssistantError, match="Tilmelding lukket"):
        await hass.services.async_call(
            DOMAIN, "tilmeld", {"person_id": PERSON_ID, "activity_id": ACTIVITY_ID}, blocking=True
        )
