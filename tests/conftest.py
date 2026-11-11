"""Synthetic devices only. No real credentials, addresses or station IDs."""

from copy import deepcopy
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

import aiohttp
import pytest
from homeassistant import loader
from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry, entity_registry, frame

from custom_components.lifesmart_ulroot.const import DOMAIN

DATA = {
    "connection_type": "cloud",
    "auth_method": "token",
    "server": "https://api.us.ilifesmart.com/app/",
    "appkey": "test-app",
    "apptoken": "test-app-secret",
    "userid": "8123456",
    "usertoken": "test-token",
    "auto_refresh": False,
    "agt": "station-test",
}
DEVICES = [
    {
        "agt": "station-test",
        "me": "env-test",
        "devtype": "SL_SC_BE",
        "name": "Environment",
        "stat": 1,
        "data": {
            "T": {"type": 95, "val": 202, "v": 20.2, "valts": 10},
            "H": {"type": 95, "val": 419, "v": 41.9},
            "Z": {"type": 95, "val": 15, "v": 15},
        },
    },
    {
        "agt": "station-test",
        "me": "relay-test",
        "devtype": "SL_SW_BS2",
        "name": "Relay",
        "stat": 1,
        "data": {"P1": {"type": 129, "val": 1}, "P2": {"type": 128, "val": 0}},
    },
    {
        "agt": "station-test",
        "me": "light-test",
        "devtype": "SL_SW_WW",
        "name": "Light",
        "stat": 1,
        "data": {"P1": {"type": 207, "val": 48}, "P2": {"type": 207, "val": 232}},
    },
    {
        "agt": "station-test",
        "me": "cover-test",
        "devtype": "SL_DOOYA",
        "name": "Curtain",
        "stat": 1,
        "data": {"P1": {"type": 78, "val": 100}, "P2": {"type": 207, "val": 100}},
    },
    {
        "agt": "station-test",
        "me": "air-test",
        "devtype": "V_AIR_P",
        "name": "Air conditioner",
        "stat": 1,
        "data": {
            "O": {"type": 128, "val": 0},
            "MODE": {"type": 206, "val": 4},
            "tT": {"type": 136, "val": 285, "v": 28.5},
            "T": {"type": 8, "val": 207, "v": 20.7},
        },
    },
    {
        "agt": "station-test",
        "me": "door-test",
        "devtype": "SL_SC_BG",
        "name": "Door",
        "stat": 1,
        "data": {"G": {"type": 0, "val": 0}},
    },
]


@pytest.fixture
async def hass(tmp_path):
    (tmp_path / "custom_components").symlink_to(
        Path.cwd() / "custom_components", target_is_directory=True
    )
    instance = HomeAssistant(str(tmp_path))
    instance.config.time_zone = "UTC"
    loader.async_setup(instance)
    frame.async_setup(instance)
    instance.config_entries = ConfigEntries(instance, {})
    await instance.config_entries.async_initialize()
    device_registry.async_setup(instance)
    await device_registry.async_load(instance)
    await entity_registry.async_load(instance)
    async with aiohttp.ClientSession() as session:
        with (
            patch(
                "custom_components.lifesmart_ulroot.config_flow.async_get_clientsession",
                return_value=session,
            ),
            patch(
                "custom_components.lifesmart_ulroot.coordinator.async_get_clientsession",
                return_value=session,
            ),
        ):
            yield instance
    await instance.async_stop(force=True)
    await instance.async_block_till_done()


@pytest.fixture
def device_payload():
    return deepcopy(DEVICES)


@pytest.fixture
def cloud_data():
    return dict(DATA)


@pytest.fixture
def config_entry(hass):
    entry = ConfigEntry(
        domain=DOMAIN,
        title="Test Station",
        unique_id="station-test",
        data=dict(DATA),
        options={"enable_push": False},
        version=1,
        minor_version=1,
        source="user",
        discovery_keys=MappingProxyType({}),
        subentries_data=[],
    )
    hass.config_entries._entries[entry.entry_id] = entry
    return entry
