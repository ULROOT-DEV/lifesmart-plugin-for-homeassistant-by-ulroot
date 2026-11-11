"""Manual examples, station isolation, and real HA services with synthetic I/O."""

import json
import struct
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from test_integration import client_mock, setup  # noqa: F401, F811
from test_protocol import BASE, http_mock

from custom_components.lifesmart_ulroot.api.cloud import CloudClient, signature
from custom_components.lifesmart_ulroot.api.localweb import LocalWebClient
from custom_components.lifesmart_ulroot.devices import capabilities
from custom_components.lifesmart_ulroot.exceptions import CommandOutcomeUnknown, ProtocolError
from custom_components.lifesmart_ulroot.manual_devices import CATALOG
from custom_components.lifesmart_ulroot.models import (
    Channel,
    number,
    parse_devices,
    parse_remotes,
    parse_scenes,
)


def record(model, channels, me="device"):
    return {
        "agt": "station-test",
        "me": me,
        "devtype": model,
        "name": me,
        "stat": 1,
        "data": {idx: {"type": kind, "val": value} for idx, (kind, value) in channels.items()},
    }


def device(model, channels):
    return parse_devices([record(model, channels)], "station-test", 1)["device"]


@pytest.mark.parametrize("value", [0.0, -12.5, 123456.75])
def test_ieee754_meter_examples(value):
    bits = struct.unpack(">I", struct.pack(">f", value))[0]
    assert Channel(raw=bits, raw_type=2).decoded() == value
    assert Channel(raw=bits).decoded(codec="float32") == value


def test_typed_values_and_battery_do_not_guess():
    assert Channel(raw=65511, raw_type=8).decoded() == -2.5
    assert Channel(raw=202, display=20.2, raw_type=8).decoded(0.1) == 20.2
    assert Channel(raw=0x7FC00000).decoded(codec="float32") is None
    assert Channel(raw=10, raw_type=30).decoded() is None
    assert Channel(raw=3000).decoded(codec="display_only") is None
    assert Channel(raw=3000, display=75).decoded(codec="display_only") == 75
    assert number(2**60 + 1) == 2**60 + 1


@pytest.mark.parametrize(
    ("model", "channels", "platform"),
    [
        ("SL_OE_3C", {"P1": (129, 1), "P2": (2, 0), "P3": (2, 0)}, "sensor"),
        ("SL_LI_RGBW", {"RGBW": (255, 0xFF112233)}, "light"),
        ("SL_CP_DN", {"P1": (129, 1), "P3": (136, 220), "P4": (8, 200)}, "climate"),
        ("SL_DF_SR", {"SR": (129, 1), "P1": (255, 7)}, "siren"),
        ("V_FRESH_P", {"O": (129, 1), "F1": (206, 15), "F2": (206, 75)}, "fan"),
        ("SL_SW_WIN", {"OP": (128, 0), "ST": (128, 0), "CL": (128, 0)}, "cover"),
        ("ZG#TS0121", {"O1": (129, 1), "EE1": (8, 100)}, "switch"),
        ("SL_SC_CV", {}, "binary_sensor"),
    ],
)
def test_documented_families(model, channels, platform):
    caps = capabilities(device(model, channels))
    assert platform in {c.platform for c in caps}
    assert len({(c.platform, c.key) for c in caps}) == len(caps)


def test_configuration_changes_do_not_expose_motor_relays():
    channels = {"P1": (255, 2 << 24), "P2": (128, 0), "P3": (128, 0), "P4": (128, 0)}
    caps = capabilities(device("SL_P", channels))
    assert "cover" in {c.platform for c in caps}
    assert "switch" not in {c.platform for c in caps}
    channels["P1"] = (255, 0)
    caps = capabilities(device("SL_P", channels))
    assert len([c for c in caps if c.platform == "switch"]) == 3
    channels = {"P1": (129, 1), "P5": (255, 3), "P7": (206, 3), "P8": (136, 230)}
    caps = capabilities(device("SL_NATURE", channels))
    assert "climate" in {c.platform for c in caps}
    assert "switch" not in {c.platform for c in caps}
    channels["P5"] = (255, 1)
    caps = capabilities(device("SL_NATURE", channels))
    assert "switch" in {c.platform for c in caps}
    assert "climate" not in {c.platform for c in caps}
    assert capabilities(device("UNDOCUMENTED", {"P1": (129, 1)})) == []


def test_scene_and_remote_discovery_scope():
    scenes = [
        {"id": "s1", "cls": "scene", "name": "Home", "agt": "station-test"},
        {"id": "s1", "cls": "scene", "name": "Foreign", "agt": "other"},
        {"id": "group", "cls": "group"},
        {"id": "timer", "cls": "schedule"},
    ]
    assert parse_scenes(scenes, "station-test") == {"s1": "Home"}
    devices = parse_devices([record("SL_SPOT", {}, "spot")], "station-test", 1)
    base = {"category": "tv", "brand": "example", "name": "TV"}
    remotes = parse_remotes(
        {"AI_IR_spot_1": base, "AI_IR_foreign_1": base, "AI_IR_spot_2": {**base, "category": "ac"}},
        devices,
    )
    assert list(remotes) == ["AI_IR_spot_1"]
    assert remotes["AI_IR_spot_1"]["me"] == "spot"


def test_device_manual_appendix_coverage_and_fullcls():
    # Independent inventory transcribed from Device Attribute List v2.29 pp.85–90.
    appendix = """
    SL_OL SL_OL_3C SL_OL_DE SL_OL_UK SL_OL_UL OD_WE_OT1 SL_OL_W SL_OE_3C SL_OE_DE
    SL_SW_IF1 SL_SW_IF2 SL_SW_IF3 SL_SF_IF1 SL_SF_IF2 SL_SF_IF3
    SL_SW_CP1 SL_SW_CP2 SL_SW_CP3 SL_SW_FE1 SL_SW_FE2 SL_SW_RC SL_SF_RC
    SL_SW_RC1 SL_SW_RC2 SL_SW_RC3 SL_SW_ND1 SL_SW_ND2 SL_SW_ND3
    SL_MC_ND1 SL_MC_ND2 SL_MC_ND3 SL_S SL_SPWM SL_SC_BB SL_P_SW
    SL_SW_MJ1 SL_SW_MJ2 SL_SW_MJ3 SL_SW_NS1 SL_SW_NS2 SL_SW_NS3
    SL_SW_BS1 SL_SW_BS2 SL_SW_BS3 SL_CN_IF SL_CN_FE SL_SW_WIN SL_DOOYA
    SL_P_V2 SL_DOOYA_V2 SL_DOOYA_V3 SL_DOOYA_V4 SL_LI_RGBW SL_CT_RGBW
    SL_SC_RGB OD_WE_QUAN SL_LI_WW SL_LI_GD1 SL_LI_UG1 MSL_IRCTL OD_WE_IRCTL
    SL_SPOT SL_P_IR SL_P_IR_V2 SL_SC_G SL_SC_BG SL_SC_MHW SL_SC_CM SL_SC_BM
    SL_SC_THL SL_SC_BE SL_SC_CQ SL_SC_WA SL_SC_CH SL_SC_CP ELIQ_EM SL_SC_CV
    SL_P_A SL_SC_CA SL_P_RM SL_DF_GG SL_DF_MM SL_DF_SR SL_DF_BB V_AIR_P
    SL_CP_DN SL_CP_AIR SL_TR_ACIPM SL_CP_VL SL_LK_LS SL_LK_GTM SL_LK_AG
    OD_JIUWANLI_LOCK1 SL_P_BDLK SL_LK_SG SL_LK_YL LSCAM:LSI_CAM_GOS1
    LSCAM:LSI_CAM_EZ1 LSCAM:SL_CAM SL_P OD_MFRESH_M8088 LSSSMINIV1
    SL_ETDOOR SL_ALM V_DLT645_P V_485_P
    """.split()
    assert not (set(appendix) - CATALOG.keys())
    for model in appendix:
        # If channels are absent, retain truthful station-reported connectivity.
        assert capabilities(device(model, {}))
    clicker = replace(device("SL_SC_BB", {"P1": (1, 2), "P2": (0, 90)}), full_class="SL_SC_BB_V2")
    assert any(c.idx == "P1" and c.translation == "button_event" for c in capabilities(clicker))


@pytest.mark.parametrize("method", ["scene", "remote", "batch"])
async def test_new_cloud_writes_never_retry_uncertain_outcome(cloud_data, method):
    endpoint = {"scene": "api.SceneSet", "remote": "irapi.SendRemotesKeys", "batch": "api.EpsSet"}[
        method
    ]
    async with http_mock() as (session, mock):
        mock.post(BASE + endpoint, exception=TimeoutError())
        client = CloudClient(session, cloud_data)
        with pytest.raises(CommandOutcomeUnknown):
            if method == "scene":
                await client.activate_scene("s1")
            elif method == "remote":
                await client.send_remote(
                    {"id": "r", "me": "spot", "category": "tv", "brand": "test"}, ["POWER"]
                )
            else:
                await client.set_channels("light", [("RGBW", 255, 65535)])
        assert len(mock.requests[BASE + endpoint]) == 1


async def test_cloud_scene_remote_and_batch_wire_contract(cloud_data):
    async with http_mock() as (session, mock):
        client = CloudClient(session, cloud_data)
        for endpoint in ("api.SceneGet", "api.SceneSet", "api.EpsSet", "irapi.SendRemotesKeys"):
            mock.post(BASE + endpoint, payload={"code": 0, "message": []})
        await client.scenes()
        await client.activate_scene("scene-test")
        await client.set_channels("rgb", [("RGBW", 255, 0xFF123456), ("DYN", 128, 0)])
        await client.send_remote(
            {"id": "AI_IR_spot_1", "me": "spot", "category": "tv", "brand": "test"}, ["POWER"]
        )
        scene = mock.requests[BASE + "api.SceneSet"][0].kwargs["json"]
        assert scene["params"] == {"agt": "station-test", "id": "scene-test"}
        body = mock.requests[BASE + "api.EpsSet"][0].kwargs["json"]
        assert json.loads(body["params"]["args"])[0]["val"] == 0xFF123456
        body = mock.requests[BASE + "irapi.SendRemotesKeys"][0].kwargs["json"]
        assert body["system"]["sign"] == signature(
            "SendRemotesKeys",
            {"agt": "station-test", "me": "spot"},
            cloud_data,
            body["system"]["time"],
        )
        assert json.loads(body["params"]["keys"])[0]["keys"] == ["POWER"]


async def test_local_scene_and_remote_contract():
    client = LocalWebClient(
        {
            "host": "station.example",
            "port": 8008,
            "username": "test",
            "password": "test",
            "agt": "station-test",
        }
    )
    client.call = AsyncMock(return_value=[])
    await client.scenes()
    client.call.assert_awaited_with("GetAllAIs")
    await client.activate_scene("s1")
    client.call.assert_awaited_with(
        "ControlAI", {"id": "s1", "control": '{"command":"runOnce"}', "nonResp": 1}, write=True
    )
    await client.send_remote({"me": "spot", "category": "tv", "id": "remote"}, ["POWER"])
    client.call.assert_awaited_with(
        "SendKeys",
        {"me": "spot", "category": "tv", "ai": "remote", "keys": '["POWER"]'},
        write=True,
    )
    await client.close()


async def test_new_platforms_real_ha_services(hass, config_entry, client_mock):  # noqa: F811
    client_mock.snapshot.return_value = [
        record("SL_LI_RGBW", {"RGBW": (255, 0xFF112233), "DYN": (129, 1)}, "rgb"),
        record("SL_SW_WIN", {"OP": (128, 0), "ST": (128, 0), "CL": (128, 0)}, "curtain"),
        record("V_FRESH_P", {"O": (129, 1), "F1": (206, 15), "F2": (206, 75)}, "ventilation"),
        record("SL_DF_SR", {"SR": (129, 1), "P1": (255, 7)}, "alarm"),
        record("SL_SPOT", {}, "spot"),
        record("SL_CP_AIR", {"P1": (255, 0x18005), "P4": (136, 220), "P5": (8, 200)}, "thermostat"),
    ]
    client_mock.scenes.return_value = [{"id": "s1", "cls": "scene", "name": "Home"}]
    client_mock.remotes = AsyncMock(
        return_value={"AI_IR_spot_1": {"category": "tv", "brand": "example", "name": "TV"}}
    )
    client_mock.activate_scene = AsyncMock()
    client_mock.send_remote = AsyncMock()
    client_mock.set_channels = AsyncMock()
    await setup(hass, config_entry)
    entries = er.async_entries_for_config_entry(er.async_get(hass), config_entry.entry_id)

    def eid(domain):
        return next(e.entity_id for e in entries if e.domain == domain)

    assert {"light", "cover", "fan", "siren", "scene", "remote", "climate"} <= {
        e.domain for e in entries
    }
    await hass.services.async_call("scene", "turn_on", {"entity_id": eid("scene")}, blocking=True)
    client_mock.activate_scene.assert_awaited_once_with("s1", agt="station-test")
    await hass.services.async_call(
        "remote", "send_command", {"entity_id": eid("remote"), "command": ["POWER"]}, blocking=True
    )
    client_mock.send_remote.assert_awaited_once()
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": eid("light"), "rgbw_color": [17, 34, 51, 255]},
        blocking=True,
    )
    client_mock.set_channels.assert_awaited_with(
        "rgb", [("RGBW", 255, 0xFF112233), ("DYN", 128, 0)], agt="station-test"
    )
    await hass.services.async_call(
        "cover", "stop_cover", {"entity_id": eid("cover")}, blocking=True
    )
    client_mock.set_channel.assert_awaited_with("curtain", "ST", 129, 1, agt="station-test")
    await hass.services.async_call(
        "climate", "set_fan_mode", {"entity_id": eid("climate"), "fan_mode": "low"}, blocking=True
    )
    client_mock.set_channel.assert_awaited_with("thermostat", "P1", 255, 0x8005, agt="station-test")
    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": eid("fan"), "percentage": 67}, blocking=True
    )
    assert client_mock.set_channel.await_args.args[1:] == ("F1", 206, 45)
    await hass.services.async_call("siren", "turn_off", {"entity_id": eid("siren")}, blocking=True)
    client_mock.set_channel.assert_awaited_with("alarm", "P1", 128, 0, agt="station-test")
    coordinator = config_entry.runtime_data
    client_mock.activate_scene.side_effect = CommandOutcomeUnknown("timeout")
    with pytest.raises(HomeAssistantError, match="outcome unknown"):
        await coordinator.activate_scene("station-test:s1")
    assert client_mock.activate_scene.await_count == 2  # one successful + one failed; no retry
    coordinator._scene_next = 0
    client_mock.scenes.side_effect = ProtocolError("not supported")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.last_update_success
    assert hass.states.get(eid("scene")).state == "unavailable"
    assert hass.states.get(eid("light")).state != "unavailable"
    client_mock.scenes.side_effect = None
    client_mock.scenes.return_value = [{"id": "s2", "cls": "scene", "name": "Night"}]
    coordinator._scene_next = 0
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    scenes = [
        e
        for e in er.async_entries_for_config_entry(er.async_get(hass), config_entry.entry_id)
        if e.domain == "scene"
    ]
    assert len(scenes) == 2
    assert hass.states.get(eid("scene")).state == "unavailable"
    await hass.config_entries.async_unload(config_entry.entry_id)
