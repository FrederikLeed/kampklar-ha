"""Tests for the call-up notification blueprint."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import voluptuous as vol
from homeassistant.components.automation.config import async_validate_config_item
from homeassistant.components.blueprint import models
from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.template import Template
from homeassistant.util.yaml import load_yaml_dict
from pytest_homeassistant_custom_component.common import MockConfigEntry

BLUEPRINT = Path(__file__).parent.parent / "blueprints" / "automation" / "kampklar" / "udtaget.yaml"
SENSOR = "sensor.emma_next_call_up"

# Importing the real mobile_app integration pulls in conversation and tts with optional libraries the
# test environment does not install. This mirrors mobile_app's device action schema
# (homeassistant/components/mobile_app/device_action.py) so the notify step is still validated.
MOBILE_APP_ACTIONS = SimpleNamespace(
    ACTION_SCHEMA=cv.DEVICE_ACTION_BASE_SCHEMA.extend(
        {
            vol.Required("type"): "notify",
            vol.Required("message"): cv.template,
            vol.Optional("title"): cv.template,
            vol.Optional("data"): cv.template_complex,
        }
    )
)


def _blueprint() -> models.Blueprint:
    return models.Blueprint(load_yaml_dict(str(BLUEPRINT)), expected_domain="automation", schema=BLUEPRINT_SCHEMA)


def test_blueprint_schema() -> None:
    """The blueprint loads as an automation blueprint with the documented inputs."""
    blueprint = _blueprint()
    assert blueprint.domain == "automation"
    assert set(blueprint.inputs) == {"call_up_sensor", "notify_device", "title"}


async def test_blueprint_substitutes_to_valid_automation(hass: HomeAssistant) -> None:
    """With inputs filled in, the result validates as a working automation."""
    phone_entry = MockConfigEntry(domain="mobile_app")
    phone_entry.add_to_hass(hass)
    phone = dr.async_get(hass).async_get_or_create(
        config_entry_id=phone_entry.entry_id, identifiers={("mobile_app", "phone")}, name="Phone"
    )
    config = models.BlueprintInputs(
        _blueprint(),
        {
            "use_blueprint": {
                "path": "kampklar/udtaget.yaml",
                "input": {"call_up_sensor": SENSOR, "notify_device": phone.id},
            }
        },
    ).async_substitute()

    platform = AsyncMock(return_value=MOBILE_APP_ACTIONS)
    with patch("homeassistant.components.device_automation.helpers.async_get_device_automation_platform", platform):
        result = await async_validate_config_item(hass, "udtaget", config)

    assert result is not None
    assert result.validation_error is None, result.validation_error
    assert platform.await_args.args[1] == "mobile_app"


def _condition(hass: HomeAssistant, from_state: State | None, to_state: State | None) -> bool:
    template = load_yaml_dict(str(BLUEPRINT))["conditions"][0]["value_template"]
    return Template(template, hass).async_render(
        {"trigger": {"entity_id": SENSOR, "from_state": from_state, "to_state": to_state}}
    )


async def test_condition_fires_only_for_a_new_call_up(hass: HomeAssistant) -> None:
    """Notify for a new call-up, but not on restart and not when only other attributes change."""
    callup = State(SENSOR, "Eksempelby IF - Testby BK", {"activity_id": 7000002})

    # Not called up -> called up: notify.
    assert _condition(hass, State(SENSOR, "unknown"), callup) is True
    # Sensor coming back after a restart or reload: no notification.
    assert _condition(hass, State(SENSOR, "unavailable"), callup) is False
    # Same call-up, some other attribute changed: no notification.
    same = State(SENSOR, "Eksempelby IF - Testby BK", {"activity_id": 7000002, "subscribed": 12})
    assert _condition(hass, callup, same) is False
    # A different match: notify.
    other = State(SENSOR, "Testby BK - Prøveby B", {"activity_id": 7000003})
    assert _condition(hass, callup, other) is True
    # Call-up removed: no notification.
    assert _condition(hass, callup, State(SENSOR, "unknown")) is False
