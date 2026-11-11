"""Load the real Home Assistant platforms and config-flow machinery."""

import asyncio
from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

from custom_components.lifesmart_ulroot.coordinator import LifeSmartCoordinator
from custom_components.lifesmart_ulroot.diagnostics import async_get_config_entry_diagnostics
from custom_components.lifesmart_ulroot.exceptions import (
    AuthenticationError,
    CannotConnect,
    CommandOutcomeUnknown,
)
from custom_components.lifesmart_ulroot.models import Station


async def test_shared_token_renewal_is_serialized_and_saved(hass, config_entry):
    hass.config_entries.async_update_entry(
        config_entry, data={**config_entry.data, "auth_method": "login", "auto_refresh": True}
    )
    entries = [config_entry]
    for station, token in (
        ("second-station", "test-token"),
        ("other-station", "other-token"),
        ("manual-station", "test-token"),
    ):
        entry = ConfigEntry(
            domain=config_entry.domain,
            title=station,
            unique_id=station,
            data={
                **config_entry.data,
                "agt": station,
                "usertoken": token,
                "auth_method": "token",
                "auto_refresh": station != "manual-station",
            },
            options={"enable_push": False},
            version=1,
            minor_version=1,
            source="user",
            discovery_keys=MappingProxyType({}),
            subentries_data=[],
        )
        hass.config_entries._entries[entry.entry_id] = entry
        entries.append(entry)
    runtimes = [LifeSmartCoordinator(hass, entry) for entry in entries]
    for entry, runtime in zip(entries, runtimes, strict=True):
        entry.runtime_data = runtime
    calls = 0

    async def issue_token(*args, **kwargs):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return {"code": "success", "usertoken": "new-token", "expiredtime": 2000000000}

    with (
        patch.object(runtimes[0].client, "request", side_effect=issue_token),
        patch.object(runtimes[1].client, "request", side_effect=issue_token),
    ):
        await asyncio.gather(*(runtime.client.refresh("test-token") for runtime in runtimes[:2]))
    assert calls == 1
    for entry, runtime in zip(entries[:2], runtimes[:2], strict=True):
        assert entry.data["usertoken"] == "new-token"
        assert runtime.client.credentials["usertoken"] == "new-token"
        assert entry.data["expires_at"] == 2000000000
    assert entries[2].data["usertoken"] == "other-token"
    assert runtimes[2].client.credentials["usertoken"] == "other-token"
    assert entries[3].data["usertoken"] == "test-token"
    assert runtimes[3].client.credentials["usertoken"] == "test-token"
    for runtime in runtimes:
        await runtime.async_close()


async def test_cn0_uses_polling_without_guessing_push_endpoint(hass, config_entry):
    hass.config_entries.async_update_entry(
        config_entry,
        data={**config_entry.data, "server": "https://api.cn0.ilifesmart.com/app/"},
        options={"enable_push": True},
    )
    runtime = LifeSmartCoordinator(hass, config_entry)
    runtime.start_push()
    assert runtime._push_task is None
    assert runtime.update_interval.total_seconds() == runtime.poll_interval
    await runtime.async_close()


@pytest.fixture
def client_mock(device_payload):
    with patch("custom_components.lifesmart_ulroot.coordinator.CloudClient") as factory:
        client = factory.return_value
        client.scenes = AsyncMock(return_value=[])
        client.validate = AsyncMock(return_value=Station("station-test", "Test Station"))
        client.stations = AsyncMock(return_value=[Station("station-test", "Test Station")])
        client.snapshot = AsyncMock(return_value=device_payload)
        client.set_channel = AsyncMock()
        client.close = AsyncMock()
        yield client


async def setup(hass, config_entry):
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state == ConfigEntryState.LOADED


async def test_snapshot_names_update_registered_devices_without_losing_user_names(
    hass, config_entry, client_mock, device_payload
):
    from custom_components.lifesmart_ulroot.const import DOMAIN
    from custom_components.lifesmart_ulroot.identity import identity

    device_payload[0]["name"] = device_payload[0]["me"]
    await setup(hass, config_entry)
    registry = dr.async_get(hass)
    device = registry.async_get_device_by_identifier(
        (DOMAIN, identity("station-test", "env-test")), config_entry.entry_id
    )
    assert device.name == "CUBE Environmental Sensor"
    original_id = device.id
    device_payload[0]["name"] = "Living room environment sensor"
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    device = registry.async_get(original_id)
    assert device.name == "Living room environment sensor"
    registry.async_update_device(original_id, name_by_user="My sensor")
    device_payload[0]["name"] = "Office environment sensor"
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    device = registry.async_get(original_id)
    assert device.name == "Office environment sensor"
    assert device.name_by_user == "My sensor"


@pytest.mark.parametrize("enable_push", [False, True])
async def test_localweb_activation_respects_push_option_and_preserves_polling(
    hass, config_entry, device_payload, enable_push
):
    data = {
        "connection_type": "localweb",
        "agt": "station-test",
        "host": "station.example",
        "port": 8008,
        "username": "u",
        "password": "p",
    }
    hass.config_entries.async_update_entry(
        config_entry, data=data, options={"enable_push": enable_push}
    )
    with patch(
        "custom_components.lifesmart_ulroot.coordinator.LocalWebClient", autospec=True
    ) as factory:
        client = factory.return_value
        client.data = data
        client.validate.return_value = Station("station-test", "Station")
        client.snapshot.return_value = device_payload
        client.scenes.return_value = []
        client.enable_notifications.side_effect = CannotConnect("Activation unavailable")
        await setup(hass, config_entry)
        runtime = config_entry.runtime_data
        if enable_push:
            client.enable_notifications.assert_awaited_once()
        else:
            client.enable_notifications.assert_not_called()
            assert runtime._push_task is None
        assert not runtime.push_connected
        assert runtime.last_update_success
        assert runtime.update_interval.total_seconds() == runtime.poll_interval
        await runtime.async_refresh()
        assert len(runtime.data) == len(device_payload)
        assert runtime.last_update_success
        await hass.config_entries.async_unload(config_entry.entry_id)
        client.close.assert_awaited_once()


async def test_two_localweb_stations_isolate_devices_commands_and_outages(hass, device_payload):
    entries, clients = [], {}
    for index in (1, 2):
        agt = f"local-station-{index}"
        data = {
            "connection_type": "localweb",
            "agt": agt,
            "host": f"192.0.2.{index}",
            "port": 8008,
            "username": f"local-user-{index}",
            "password": f"fixture-password-{index}",
        }
        entry = ConfigEntry(
            domain="lifesmart_ulroot",
            title=agt,
            unique_id=agt,
            data=data,
            options={"enable_push": False},
            version=1,
            minor_version=1,
            source="user",
            discovery_keys=MappingProxyType({}),
            subentries_data=[],
        )
        hass.config_entries._entries[entry.entry_id] = entry
        entries.append(entry)
        # Both stations deliberately have the same product IDs and names.
        payload = [{**device, "agt": agt} for device in device_payload]
        clients[agt] = MagicMock(
            scenes=AsyncMock(return_value=[]),
            validate=AsyncMock(return_value=Station(agt, agt)),
            snapshot=AsyncMock(return_value=payload),
            set_channel=AsyncMock(),
            close=AsyncMock(),
        )

    def client_for_station(data):
        entry = next(entry for entry in entries if entry.unique_id == data["agt"])
        assert data == dict(entry.data)
        return clients[data["agt"]]

    with patch(
        "custom_components.lifesmart_ulroot.coordinator.LocalWebClient",
        side_effect=client_for_station,
    ):
        await asyncio.gather(*(setup(hass, entry) for entry in entries))
        registry = er.async_get(hass)
        groups = [er.async_entries_for_config_entry(registry, entry.entry_id) for entry in entries]
        assert {e.unique_id for e in groups[0]}.isdisjoint(e.unique_id for e in groups[1])
        assert {e.device_id for e in groups[0]}.isdisjoint(e.device_id for e in groups[1])
        sensors = [next(e.entity_id for e in group if e.domain == "sensor") for group in groups]
        switch = next(e.entity_id for e in groups[1] if e.domain == "switch")
        await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
        clients["local-station-1"].set_channel.assert_not_awaited()
        clients["local-station-2"].set_channel.assert_awaited_once()
        first, second = [entry.runtime_data for entry in entries]
        before = first.data
        first._event({"agt": "local-station-2", "me": "env-test", "idx": "T", "val": 999})
        assert first.data is before
        clients["local-station-1"].snapshot.side_effect = CannotConnect("Station offline")
        await first.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(sensors[0]).state == "unavailable"
        assert hass.states.get(sensors[1]).state not in ("unavailable", "unknown")
        assert await hass.config_entries.async_unload(entries[0].entry_id)
        await second.async_refresh()
        await hass.async_block_till_done()
        assert entries[1].state == ConfigEntryState.LOADED
        assert hass.states.get(sensors[1]).state not in ("unavailable", "unknown")
        clients["local-station-2"].close.assert_not_awaited()
        assert await hass.config_entries.async_unload(entries[1].entry_id)


async def test_load_entities_grouping_and_unload(hass, config_entry, client_mock):
    await setup(hass, config_entry)
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, config_entry.entry_id)
    sensors = [e for e in entries if e.domain == "sensor"]
    assert len(sensors) == 3
    assert len({e.device_id for e in sensors}) == 1
    assert sorted(float(hass.states.get(e.entity_id).state) for e in sensors) == [15, 20.2, 41.9]
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), config_entry.entry_id)
    assert len(devices) == 7  # station + six physical products
    assert {e.domain for e in entries} == {
        "sensor",
        "binary_sensor",
        "switch",
        "light",
        "cover",
        "climate",
    }
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    client_mock.close.assert_awaited_once()


async def test_command_encoding_and_readback(hass, config_entry, client_mock):
    await setup(hass, config_entry)
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, config_entry.entry_id)
    light = next(e.entity_id for e in entries if e.domain == "light")
    switch = next(e.entity_id for e in entries if e.domain == "switch")
    cover = next(e.entity_id for e in entries if e.domain == "cover")
    climate = next(e.entity_id for e in entries if e.domain == "climate")
    await hass.services.async_call("light", "turn_off", {"entity_id": light}, blocking=True)
    client_mock.set_channel.assert_awaited_with("light-test", "P1", 128, 0, agt="station-test")
    await hass.services.async_call("switch", "turn_off", {"entity_id": switch}, blocking=True)
    assert client_mock.set_channel.await_args.args[2:] == (128, 0)
    await hass.services.async_call("cover", "stop_cover", {"entity_id": cover}, blocking=True)
    client_mock.set_channel.assert_awaited_with("cover-test", "P2", 206, 128, agt="station-test")
    await hass.services.async_call(
        "climate", "set_temperature", {"entity_id": climate, "temperature": 23.5}, blocking=True
    )
    client_mock.set_channel.assert_awaited_with("air-test", "tT", 136, 235, agt="station-test")
    assert hass.states.get(climate).attributes["current_temperature"] == 20.7


async def test_refresh_failure_unavailable_and_recovery(
    hass, config_entry, client_mock, device_payload
):
    await setup(hass, config_entry)
    runtime = config_entry.runtime_data
    registry = er.async_get(hass)
    sensor = next(
        e.entity_id
        for e in er.async_entries_for_config_entry(registry, config_entry.entry_id)
        if e.domain == "sensor"
    )
    client_mock.snapshot.side_effect = CannotConnect("Test outage")
    await runtime.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(sensor).state == "unavailable"
    client_mock.snapshot.side_effect = None
    client_mock.snapshot.return_value = device_payload
    runtime._next_request = 0
    await runtime.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(sensor).state not in ("unavailable", "unknown")


async def test_diagnostics_are_allowlisted(hass, config_entry, client_mock):
    await setup(hass, config_entry)
    data = await async_get_config_entry_diagnostics(hass, config_entry)
    import json

    serialized = json.dumps(data)
    for secret in (
        "test-token",
        "test-app",
        "8123456",
        "station-test",
        "Environment",
        "relay-test",
    ):
        assert secret not in serialized
    assert data["device_count"] == 6


async def test_reload_preserves_registry_identity(hass, config_entry, client_mock):
    await setup(hass, config_entry)
    registry = er.async_get(hass)
    before = {
        e.unique_id: e.entity_id
        for e in er.async_entries_for_config_entry(registry, config_entry.entry_id)
    }
    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    after = {
        e.unique_id: e.entity_id
        for e in er.async_entries_for_config_entry(registry, config_entry.entry_id)
    }
    assert before == after


async def test_uncertain_write_is_not_replayed(hass, config_entry, client_mock):
    await setup(hass, config_entry)
    client_mock.set_channel.side_effect = CommandOutcomeUnknown("uncertain")
    from homeassistant.exceptions import HomeAssistantError

    with pytest.raises(HomeAssistantError, match="outcome unknown"):
        await config_entry.runtime_data.command("station-test:relay-test", "P1", 129, 1)
    client_mock.set_channel.assert_awaited_once()


async def test_initial_authentication_failure_requests_reauth(hass, config_entry, client_mock):
    client_mock.stations.side_effect = AuthenticationError("rejected")
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state == ConfigEntryState.SETUP_ERROR
    assert hass.config_entries.flow.async_progress()


@pytest.mark.parametrize("auto_refresh", [False, True])
async def test_token_failure_creates_repair_and_replacement_preserves_entities(
    hass, config_entry, client_mock, auto_refresh
):
    hass.config_entries.async_update_entry(
        config_entry, data={**config_entry.data, "auto_refresh": auto_refresh}
    )
    await setup(hass, config_entry)
    registry = er.async_get(hass)
    before = {
        e.unique_id: e.entity_id
        for e in er.async_entries_for_config_entry(registry, config_entry.entry_id)
    }
    client_mock.snapshot.side_effect = AuthenticationError("rejected")
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    issue_id = f"config_entry_reauth_lifesmart_ulroot_{config_entry.entry_id}"
    issues = ir.async_get(hass)
    assert issues.async_get_issue("homeassistant", issue_id) is not None
    assert not config_entry.runtime_data.last_update_success
    config_entry.async_start_reauth(hass)
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1
    assert flows[0]["step_id"] == "reauth_token"
    with patch("custom_components.lifesmart_ulroot.config_flow.CloudClient") as factory:
        client = factory.return_value
        client.close = AsyncMock()
        client.credentials = {}
        client.stations = AsyncMock(side_effect=AuthenticationError("invalid token"))
        result = await hass.config_entries.flow.async_configure(
            flows[0]["flow_id"], {"usertoken": "wrong-token"}
        )
        assert result["errors"] == {"base": "invalid_usertoken"}
        assert config_entry.data["usertoken"] == "test-token"
        client.stations.side_effect = None
        client.stations.return_value = [Station("station-test", "Test Station")]
        client_mock.snapshot.side_effect = None
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"usertoken": "updated-by-other-app"}
        )
        assert result["reason"] == "reauth_successful"
        await hass.async_block_till_done()
    assert config_entry.data["usertoken"] == "updated-by-other-app"
    assert config_entry.data["auto_refresh"] is auto_refresh
    assert config_entry.state == ConfigEntryState.LOADED
    assert issues.async_get_issue("homeassistant", issue_id) is None
    assert before == {
        e.unique_id: e.entity_id
        for e in er.async_entries_for_config_entry(registry, config_entry.entry_id)
    }


async def test_command_auth_failure_starts_token_reauthentication(hass, config_entry, client_mock):
    from homeassistant.exceptions import HomeAssistantError

    await setup(hass, config_entry)
    client_mock.set_channel.side_effect = AuthenticationError("rejected")
    with pytest.raises(HomeAssistantError) as error:
        await config_entry.runtime_data.command("station-test:relay-test", "P1", 129, 1)
    assert error.value.translation_key == "invalid_usertoken"
    await hass.async_block_till_done()
    assert hass.config_entries.flow.async_progress()[0]["step_id"] == "reauth_token"
    assert not config_entry.runtime_data.last_update_success
    client_mock.set_channel.assert_awaited_once()
