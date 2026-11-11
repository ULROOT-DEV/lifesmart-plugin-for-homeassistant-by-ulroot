"""Account discovery, station isolation, and registry-preserving migration."""

import asyncio
from copy import deepcopy
from types import MappingProxyType
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from test_integration import client_mock, setup  # noqa: F401

from custom_components.lifesmart_ulroot.config_flow import LifeSmartConfigFlow
from custom_components.lifesmart_ulroot.const import DOMAIN
from custom_components.lifesmart_ulroot.exceptions import AuthenticationError, ProtocolError
from custom_components.lifesmart_ulroot.identity import account_id, identity, occupied_stations
from custom_components.lifesmart_ulroot.migration import async_migrate_entry
from custom_components.lifesmart_ulroot.models import Station


def entry_for(hass, data, *, agt=None, options=None, version=2):
    data = dict(data)
    if agt:
        data["agt"] = agt
        uid = agt
    else:
        data.pop("agt", None)
        data["account_scope"] = True
        uid = account_id(data)
    entry = ConfigEntry(
        domain=DOMAIN,
        title=agt or "Cloud account",
        unique_id=uid,
        data=data,
        options=options or {"enable_push": False},
        version=version,
        minor_version=1,
        source="user",
        discovery_keys=MappingProxyType({}),
        subentries_data=[],
    )
    hass.config_entries._entries[entry.entry_id] = entry
    return entry


def stations_payload(device_payload, *stations):
    return [{**deepcopy(device), "agt": agt} for agt in stations for device in device_payload]


async def test_all_stations_one_snapshot_collisions_commands_and_push(
    hass,
    cloud_data,
    device_payload,
    client_mock,  # noqa: F811
):
    entry = entry_for(hass, cloud_data)
    client_mock.stations.return_value = [Station("a", "A"), Station("b", "B")]
    client_mock.snapshot.return_value = stations_payload(device_payload, "a", "b")
    client_mock.scenes.return_value = [{"id": "same-scene", "name": "Scene", "cls": "scene"}]
    client_mock.activate_scene = AsyncMock()
    await setup(hass, entry)
    runtime = entry.runtime_data
    assert len(runtime.data) == 12
    assert set(runtime.stations) == {"a", "b"}
    client_mock.snapshot.assert_awaited_once()
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    switches = {
        next(
            e.entity_id
            for e in entities
            if e.domain == "switch" and e.unique_id.startswith(agt + ":")
        ): agt
        for agt in ("a", "b")
    }
    for entity_id, agt in switches.items():
        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": entity_id}, blocking=True
        )
        assert client_mock.set_channel.await_args.kwargs == {"agt": agt}
        assert client_mock.set_channel.await_args.args[0] == "relay-test"
    scenes = [e for e in entities if e.domain == "scene"]
    assert {e.unique_id for e in scenes} == {"a:scene:same-scene", "b:scene:same-scene"}
    for scene in scenes:
        await hass.services.async_call(
            "scene", "turn_on", {"entity_id": scene.entity_id}, blocking=True
        )
        client_mock.activate_scene.assert_awaited_with("same-scene", agt=scene.unique_id[0])
    before = runtime.data["b:env-test"]
    runtime._event({"agt": "a", "me": "env-test", "idx": "T", "val": 333, "type": 95, "valts": 999})
    assert runtime.data["a:env-test"].channels["T"].raw == 333
    assert runtime.data["b:env-test"] is before
    registry = dr.async_get(hass)
    for agt in ("a", "b"):
        product = registry.async_get_device_by_identifier(
            (DOMAIN, identity(agt, "env-test")), entry.entry_id
        )
        assert product.via_device_id == runtime.station_device_ids[agt]
    await hass.config_entries.async_unload(entry.entry_id)
    client_mock.close.assert_awaited_once()


async def test_station_discovery_exclusion_removal_and_partial_scene_outage(
    hass,
    cloud_data,
    device_payload,
    client_mock,  # noqa: F811
):
    local = entry_for(hass, {"connection_type": "localweb"}, agt="local")
    entry = entry_for(
        hass, cloud_data, options={"enable_push": False, "excluded_stations": ["excluded"]}
    )
    client_mock.stations.return_value = [Station(s, s) for s in ("a", "local", "excluded")]
    client_mock.snapshot.return_value = stations_payload(device_payload, "a", "local", "excluded")
    client_mock.scenes.return_value = [{"id": "s", "cls": "scene", "name": "Scene"}]
    await setup(hass, entry)
    runtime = entry.runtime_data
    assert set(runtime.stations) == {"a"}
    client_mock.stations.return_value += [Station("b", "B")]
    client_mock.snapshot.return_value += stations_payload(device_payload, "b")
    runtime._scene_next = 0
    await runtime.async_refresh()
    await hass.async_block_till_done()
    assert set(runtime.stations) == {"a", "b"}
    assert len(runtime.data) == 12

    async def scene_by_station(*, agt):
        if agt == "a":
            raise ProtocolError("unsupported scene API")
        return [{"id": "s", "cls": "scene", "name": "Scene"}]

    client_mock.scenes.side_effect = scene_by_station
    runtime._scene_next = 0
    await runtime.async_refresh()
    assert runtime.last_update_success
    assert runtime.scene_stations_available == {"b"}
    with pytest.raises(HomeAssistantError):
        await runtime.activate_scene("a:s")
    client_mock.stations.return_value = [Station("b", "B")]
    client_mock.snapshot.return_value = stations_payload(device_payload, "b")
    runtime._scene_next = 0
    await runtime.async_refresh()
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    sensor_a = next(e for e in entries if e.domain == "sensor" and e.unique_id.startswith("a:"))
    sensor_b = next(e for e in entries if e.domain == "sensor" and e.unique_id.startswith("b:"))
    assert hass.states.get(sensor_a.entity_id).state == "unavailable"
    assert hass.states.get(sensor_b.entity_id).state not in ("unknown", "unavailable")
    assert hass.config_entries.async_get_entry(local.entry_id) is local


async def test_remote_collision_routes_to_correct_station(hass, cloud_data, client_mock):  # noqa: F811
    entry = entry_for(hass, cloud_data)
    client_mock.stations.return_value = [Station("a", "A"), Station("b", "B")]
    client_mock.snapshot.return_value = [
        {"agt": agt, "me": "spot", "devtype": "SL_SPOT", "stat": 1, "data": {}}
        for agt in ("a", "b")
    ]
    client_mock.remotes = AsyncMock(
        return_value={"AI_IR_spot_1": {"category": "tv", "brand": "test", "name": "TV"}}
    )
    client_mock.send_remote = AsyncMock()
    await setup(hass, entry)
    entries = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    remotes = [e for e in entries if e.domain == "remote"]
    assert len(remotes) == 2
    for remote in remotes:
        await hass.services.async_call(
            "remote",
            "send_command",
            {"entity_id": remote.entity_id, "command": ["POWER"]},
            blocking=True,
        )
        call = client_mock.send_remote.await_args
        assert call.kwargs == {"agt": remote.unique_id[0]}
        assert call.args[0]["id"] == "AI_IR_spot_1"
        assert call.args[0]["me"] == "spot"


async def test_migration_merges_entries_without_losing_registry_settings(
    hass,
    cloud_data,
    device_payload,
    client_mock,  # noqa: F811
):
    first = entry_for(hass, {**cloud_data, "auto_refresh": True}, agt="a", version=1)
    second = entry_for(
        hass,
        {**cloud_data, "auto_refresh": False},
        agt="b",
        version=1,
        options={"enable_push": False, "excluded_devices": ["door-test"]},
    )
    devices, entities = dr.async_get(hass), er.async_get(hass)
    originals = []
    for entry, agt in ((first, "a"), (second, "b")):
        station = devices.async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={(DOMAIN, agt)}
        )
        device = devices.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, identity(agt, "env-test"))},
            via_device_id=station.id,
        )
        devices.async_update_device(device.id, name_by_user="Keep device name")
        entity = entities.async_get_or_create(
            "sensor",
            DOMAIN,
            identity(agt, "env-test", "temperature:T"),
            config_entry=entry,
            device_id=device.id,
            suggested_object_id=f"saved_{agt}",
        )
        entities.async_update_entity(
            entity.entity_id,
            name="Keep entity name",
            disabled_by=er.RegistryEntryDisabler.USER if agt == "b" else None,
        )
        originals.append((entity.entity_id, entity.unique_id, device.id))
    client_mock.stations.return_value = [Station("a", "A"), Station("b", "B")]
    client_mock.snapshot.return_value = stations_payload(device_payload, "a", "b")
    # Exercise concurrent Home Assistant startup, including the retired entry.
    await asyncio.wait_for(
        asyncio.gather(*(hass.config_entries.async_setup(e.entry_id) for e in (first, second))),
        timeout=10,
    )
    await hass.async_block_till_done()
    remaining = hass.config_entries.async_entries(DOMAIN)
    assert len(remaining) == 1
    owner = remaining[0]
    assert owner is second  # Unmanaged-token preference is preserved.
    assert owner.version == 2
    assert owner.unique_id == account_id(cloud_data)
    assert owner.data["auto_refresh"] is False
    assert "agt" not in owner.data
    assert owner.options["excluded_devices"] == ["b:door-test"]
    for entity_id, unique_id, device_id in originals:
        entity = entities.async_get(entity_id)
        assert entity.unique_id == unique_id
        assert entity.config_entry_id == owner.entry_id
        assert entity.device_id == device_id
        assert entity.name == "Keep entity name"
        if unique_id.startswith("b:"):
            assert entity.disabled_by == er.RegistryEntryDisabler.USER
        else:
            assert entity.disabled_by is None
            assert hass.states.get(entity_id).state not in ("unknown", "unavailable")
        device = devices.async_get(device_id)
        assert device.name_by_user == "Keep device name"
        assert device.config_entry_id == owner.entry_id
    station_devices = [
        d
        for d in dr.async_entries_for_config_entry(devices, owner.entry_id)
        if d.identifiers in ({(DOMAIN, "a")}, {(DOMAIN, "b")})
    ]
    assert len(station_devices) == 2
    assert await hass.config_entries.async_reload(owner.entry_id)
    assert all(entities.async_get(entity_id) for entity_id, _, _ in originals)


async def test_migration_does_not_remove_sources_when_credentials_fail(
    hass,
    cloud_data,
    client_mock,  # noqa: F811
):
    entries = [entry_for(hass, cloud_data, agt=agt, version=1) for agt in ("a", "b")]
    await async_migrate_entry(hass, entries[0])
    owner = next(e for e in entries if not e.data.get("migrated_into"))
    client_mock.stations.side_effect = AuthenticationError("expired")
    assert not await hass.config_entries.async_setup(owner.entry_id)
    assert len(hass.config_entries.async_entries(DOMAIN)) == 2
    assert owner.data["migration_sources"]


@pytest.mark.parametrize("auth_method,expected", [("login", True), ("token", False)])
async def test_existing_account_renewal_policy(
    hass,
    cloud_data,
    client_mock,  # noqa: F811
    auth_method,
    expected,
):
    entry = entry_for(hass, {**cloud_data, "auth_method": auth_method, "auto_refresh": False})
    await setup(hass, entry)
    assert entry.data["auto_refresh"] is expected
    await hass.config_entries.async_unload(entry.entry_id)


async def test_migration_prefers_direct_token_off_over_legacy_login_off(hass, cloud_data):
    login = entry_for(
        hass, {**cloud_data, "auth_method": "login", "auto_refresh": False}, agt="a", version=1
    )
    token = entry_for(
        hass, {**cloud_data, "auth_method": "token", "auto_refresh": False}, agt="b", version=1
    )
    assert await async_migrate_entry(hass, login)
    assert login.data["migrated_into"] == token.entry_id
    assert token.data["auth_method"] == "token"
    assert token.data["auto_refresh"] is False


@pytest.mark.parametrize("userno", ["someone@example.invalid", "", "１２３４", "123-456"])
async def test_direct_token_rejects_non_numeric_userno_without_api_call(hass, cloud_data, userno):
    flow = LifeSmartConfigFlow()
    flow.hass = hass
    with patch("custom_components.lifesmart_ulroot.config_flow.CloudClient") as factory:
        result = await flow.async_step_cloud_token({**cloud_data, "userid": userno})
    assert result["errors"] == {"userid": "invalid_userno"}
    factory.assert_not_called()


async def test_account_flow_imports_all_and_rejects_duplicate_account(hass, cloud_data):
    with (
        patch("custom_components.lifesmart_ulroot.async_setup_entry", return_value=None),
        patch("custom_components.lifesmart_ulroot.config_flow.CloudClient") as factory,
    ):
        client = factory.return_value
        client.credentials = {k: v for k, v in cloud_data.items() if k != "agt"}
        client.stations = AsyncMock(return_value=[Station("a", "A"), Station("b", "B")])
        client.close = AsyncMock()
        for duplicate in (False, True):
            result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {"next_step_id": "cloud"}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {"next_step_id": "cloud_token"}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    k: cloud_data[k]
                    for k in ("server", "appkey", "apptoken", "userid", "usertoken", "auto_refresh")
                },
            )
            if duplicate:
                assert result["reason"] == "already_configured"
            else:
                assert result["type"] == "create_entry"
                assert set(result["data"]["stations"]) == {"a", "b"}
                assert "agt" not in result["data"]
            await hass.async_block_till_done()
        factory.assert_called_once()  # A duplicate cannot renew a supplied token.


async def test_shared_station_claims_have_one_stable_cloud_owner(hass, cloud_data):
    a = entry_for(hass, {**cloud_data, "stations": {"shared": {}}})
    b = entry_for(hass, {**cloud_data, "userid": "8765432", "stations": {"shared": {}}})
    first, second = sorted((a, b), key=lambda entry: entry.entry_id)
    assert occupied_stations(hass, first.entry_id, prioritize=True) == set()
    assert occupied_stations(hass, second.entry_id, prioritize=True) == {"shared"}
    local = entry_for(hass, {"connection_type": "localweb"}, agt="shared")
    assert occupied_stations(hass, first.entry_id, prioritize=True) == {"shared"}
    assert local.entry_id not in (first.entry_id, second.entry_id)


async def test_one_push_connection_per_account(hass, cloud_data, device_payload, client_mock):  # noqa: F811
    entry = entry_for(hass, cloud_data, options={"enable_push": True})
    client_mock.stations.return_value = [Station("a", "A"), Station("b", "B")]
    client_mock.snapshot.return_value = stations_payload(device_payload, "a", "b")
    connected, stopped = asyncio.Event(), asyncio.Event()

    async def stream(client, event, ready):
        connected.set()
        try:
            await asyncio.Future()
        finally:
            stopped.set()

    with patch(
        "custom_components.lifesmart_ulroot.coordinator.cloud_stream", side_effect=stream
    ) as push:
        await setup(hass, entry)
        await asyncio.wait_for(connected.wait(), 2)
        entry.runtime_data.start_push()
        push.assert_awaited_once()
        await hass.config_entries.async_unload(entry.entry_id)
        assert stopped.is_set()


async def test_login_recovery_preserves_pending_migration(hass, cloud_data, client_mock):  # noqa: F811
    entries = [entry_for(hass, cloud_data, agt=agt, version=1) for agt in ("a", "b")]
    await async_migrate_entry(hass, entries[0])
    owner = next(e for e in entries if not e.data.get("migrated_into"))
    sources = owner.data["migration_sources"]
    with (
        patch("custom_components.lifesmart_ulroot.async_setup_entry", return_value=None),
        patch("custom_components.lifesmart_ulroot.config_flow.CloudClient") as factory,
    ):
        client = factory.return_value
        client.credentials = {**cloud_data, "auth_method": "login"}
        client.login, client.close = AsyncMock(), AsyncMock()
        client.stations = AsyncMock(return_value=[Station("a", "A"), Station("b", "B")])
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "reconfigure", "entry_id": owner.entry_id}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "cloud_login"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                **{k: cloud_data[k] for k in ("server", "appkey", "apptoken", "userid")},
                "password": "test-password",
            },
        )
        assert result["reason"] == "reconfigure_successful"
        assert owner.data["migration_sources"] == sources
        assert owner.data["auto_refresh"] is True
        assert "password" not in owner.data
        await hass.async_block_till_done()
