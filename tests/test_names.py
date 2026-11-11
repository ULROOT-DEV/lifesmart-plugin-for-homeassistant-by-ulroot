"""Fallback localization, custom name preservation and registry identity."""

from unittest.mock import patch

import pytest
from homeassistant.helpers import device_registry as dr
from test_integration import client_mock, setup  # noqa: F401

from custom_components.lifesmart_ulroot.const import DOMAIN
from custom_components.lifesmart_ulroot.identity import identity
from custom_components.lifesmart_ulroot.manual_devices import CATALOG
from custom_components.lifesmart_ulroot.models import Device, Station
from custom_components.lifesmart_ulroot.names import PRODUCT_NAMES, device_name, station_name


@pytest.mark.parametrize("name", ["", "  ", "5dc5", "5DC5", "SL_OE_DE", "station"])
def test_missing_or_identifier_names_use_product_name(name):
    device = Device("station", "5dc5", "SL_OE_DE", name)
    assert device_name(device, "ko") == "스마트 플러그"
    assert device_name(device, "en") == "Smart Plug"
    assert device_name(device, "ko-KR") == "스마트 플러그"
    assert device_name(device, "de") == "Smart Plug"


@pytest.mark.parametrize("name", ["Desk plug", "거실 콘센트", "1234", "Other me 5dc5"])
def test_real_names_are_never_translated(name):
    device = Device("station", "5dc5", "SL_OE_DE", name)
    assert device_name(device, "en") == name
    assert device_name(device, "ko") == name


def test_catalog_and_reference_names_have_both_languages():
    for model in CATALOG.keys() | PRODUCT_NAMES.keys():
        device = Device("station", "endpoint", model, "")
        english, korean = (device_name(device, lang) for lang in ("en", "ko"))
        assert english and korean
        assert " / " not in english and " / " not in korean
        assert not any("가" <= char <= "힣" for char in english)
        assert any("가" <= char <= "힣" for char in korean)
    device = Device("station", "endpoint", "UNLISTED", "")
    assert device_name(device, "en") == "LifeSmart Device"
    assert device_name(device, "ko") == "LifeSmart 장치"
    assert device_name(Device("s", "m", "SL_SW_IF3", ""), "en") == "BLEND Switch 3"


def test_station_defaults_preserve_custom_names():
    for name in ("", "station", "Smart Station"):
        assert station_name(Station("station", name), "ko") == "스마트 스테이션"
        assert station_name(Station("station", name), "en") == "Smart Station"
    assert station_name(Station("station", "Nature Mini PRO 5"), "ko") == "Nature Mini PRO 5"


@pytest.mark.parametrize("mode", ["cloud", "localweb"])
async def test_registry_localizes_initial_and_existing_names_preserving_user_override(
    hass,
    config_entry,
    device_payload,
    client_mock,  # noqa: F811
    mode,
):
    hass.config.language = "ko"
    device_payload[0]["name"] = "env-test"
    client_mock.validate.return_value = Station("station-test", "station-test")
    client_mock.stations.return_value = [Station("station-test", "station-test")]
    if mode == "localweb":
        hass.config_entries.async_update_entry(
            config_entry,
            data={
                "connection_type": "localweb",
                "agt": "station-test",
                "host": "station.example",
                "port": 8008,
                "username": "user",
                "password": "test-password",
                "use_ssl": False,
            },
        )
        with patch(
            "custom_components.lifesmart_ulroot.coordinator.LocalWebClient",
            return_value=client_mock,
        ):
            await setup(hass, config_entry)
    else:
        await setup(hass, config_entry)
    registry = dr.async_get(hass)
    device = registry.async_get_device_by_identifier(
        (DOMAIN, identity("station-test", "env-test")), config_entry.entry_id
    )
    assert device.name == "CUBE 환경 센서"
    original_id = device.id
    station = registry.async_get(config_entry.runtime_data.station_device_ids["station-test"])
    assert station.name == "스마트 스테이션"
    # Simulate the old identifier-only registry and a system language change.
    registry.async_update_device(original_id, name="env-test")
    hass.config.language = "en"
    await config_entry.runtime_data.async_refresh()
    assert registry.async_get(original_id).name == "CUBE Environmental Sensor"
    registry.async_update_device(original_id, name_by_user="My own name")
    device_payload[0]["name"] = "Office sensor"
    await config_entry.runtime_data.async_refresh()
    updated = registry.async_get(original_id)
    assert updated.name == "Office sensor"
    assert updated.name_by_user == "My own name"
    await hass.config_entries.async_unload(config_entry.entry_id)
