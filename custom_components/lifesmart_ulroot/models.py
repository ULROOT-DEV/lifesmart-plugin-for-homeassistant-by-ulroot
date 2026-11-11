"""Validated, transport-independent endpoint data and race-safe state merging."""

import math
import struct
from dataclasses import dataclass, field, replace
from typing import Any

from .exceptions import ProtocolError


def number(value: Any) -> float | None:
    """Reject bools, strings, NaN and infinity, preserving legitimate zero."""
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return value
    return None


@dataclass(frozen=True, slots=True)
class Station:
    agt: str
    name: str = "Smart Station"
    firmware: str | None = None


def parse_scenes(payload, station):
    if payload == {}:
        return {}
    if not isinstance(payload, list):
        raise ProtocolError("Expected a scene list")
    result = {}
    for item in payload:
        if not isinstance(item, dict):
            raise ProtocolError("Invalid scene record")
        if item.get("cls") != "scene" or item.get("agt", station) != station:
            continue
        scene_id = item.get("id")
        if not isinstance(scene_id, str) or not scene_id:
            raise ProtocolError("Scene identity missing")
        result[scene_id] = str(item.get("name") or item.get("desc") or scene_id)
    return result


@dataclass(frozen=True, slots=True)
class Channel:
    raw_type: int | None = None
    raw: float | None = None
    display: float | None = None
    timestamp: float | None = None
    received: float = 0

    def decoded(self, scale: float = 1, codec: str = "scaled") -> float | None:
        if self.raw_type is not None and self.raw_type & 0x7E == 0x1E:
            return None
        if codec == "display_only":
            return self.display if self.display is not None and 0 <= self.display <= 100 else None
        if self.display is not None:
            return self.display
        if self.raw is None:
            return None
        if codec == "float32" or (self.raw_type is not None and self.raw_type & 0x7E == 2):
            if self.raw != int(self.raw) or not -(2**31) <= self.raw < 2**32:
                return None
            return number(struct.unpack("!f", struct.pack("!I", int(self.raw) & 0xFFFFFFFF))[0])
        if self.raw_type is not None and self.raw_type & 0x78 == 8:
            raw = self.raw - 65536 if self.raw > 32767 else self.raw
            return raw / 10 ** (((self.raw_type & 6) // 2) + 1)
        return self.raw * scale

    def value(self, scale: float = 1) -> float | None:
        return (
            self.display
            if self.display is not None
            else (self.raw * scale if self.raw is not None else None)
        )


@dataclass(frozen=True, slots=True)
class Device:
    agt: str
    me: str
    model: str
    name: str
    online: bool | None = None
    firmware: str | None = None
    channels: dict[str, Channel] = field(default_factory=dict)
    full_class: str | None = None


def parse_channel(data: dict, received: float, old: Channel | None = None) -> Channel:
    """Merge partial reports. A new raw value invalidates an older display value."""
    old = old or Channel()
    raw_type = data.get("type", old.raw_type)
    if not isinstance(raw_type, int) or isinstance(raw_type, bool):
        raw_type = None
    raw = number(data["val"]) if "val" in data else old.raw
    display = number(data["v"]) if "v" in data else (None if "val" in data else old.display)
    ts = number(data.get("valts", data.get("ts")))
    return Channel(raw_type, raw, display, ts if ts is not None else old.timestamp, received)


def parse_devices(payload: Any, station: str, received: float) -> dict[str, Device]:
    # LifeSmart returns {} for an account/station with no endpoints.
    if payload == {}:
        return {}
    if not isinstance(payload, list):
        raise ProtocolError("Expected a device list")
    result = {}
    for item in payload:
        if not isinstance(item, dict):
            raise ProtocolError("Invalid device record")
        if item.get("agt") != station:
            continue
        me, model, data = item.get("me"), item.get("devtype"), item.get("data", {})
        if (
            not isinstance(me, str)
            or not me
            or not isinstance(model, str)
            or not isinstance(data, dict)
        ):
            raise ProtocolError("Device identity or channels missing")
        channels = {}
        for idx, value in data.items():
            if isinstance(idx, str) and isinstance(value, dict):
                channels[idx] = parse_channel(value, received)
        stat = item.get("stat")
        online = (stat != 0) if type(stat) is int else None
        result[me] = Device(
            station,
            me,
            model,
            str(item.get("name") or model),
            online,
            str(item["ver"]) if item.get("ver") else None,
            channels,
            item.get("fullCls") or item.get("fullcls"),
        )
    return result


def event_records(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [record for item in payload for record in event_records(item)]
    if not isinstance(payload, dict):
        return []
    if "msg" in payload:
        return event_records(payload["msg"])
    return [payload] if isinstance(payload.get("me"), str) else []


def merge_event(devices: dict[str, Device], event: dict, received: float) -> dict[str, Device]:
    """Ignore foreign/unknown devices and stale source timestamps."""
    old = devices.get(event.get("me"))
    if old is None or event.get("agt") != old.agt:
        return devices
    data = event.get("data", {})
    if isinstance(event.get("idx"), str):
        data = {event["idx"]: event}
    if not isinstance(data, dict):
        return devices
    channels = dict(old.channels)
    for idx, value in data.items():
        if not isinstance(idx, str) or not isinstance(value, dict):
            continue
        previous = channels.get(idx)
        incoming_ts = number(value.get("valts", value.get("ts")))
        if (
            previous
            and incoming_ts is not None
            and previous.timestamp is not None
            and incoming_ts < previous.timestamp
        ):
            continue
        channels[idx] = parse_channel(value, received, previous)
    stat = event.get("stat")
    online = stat != 0 if type(stat) is int else old.online
    return {**devices, old.me: replace(old, channels=channels, online=online)}


def reconcile_snapshot(
    snapshot: dict[str, Device], current: dict[str, Device], started: float
) -> dict[str, Device]:
    """Do not let a slow snapshot undo push changes received after it started."""
    result = {}
    for me, device in snapshot.items():
        old = current.get(me)
        channels = dict(device.channels)
        if old:
            for idx, previous in old.channels.items():
                incoming = channels.get(idx)
                if previous.received > started or (
                    incoming
                    and incoming.timestamp is not None
                    and previous.timestamp is not None
                    and previous.timestamp > incoming.timestamp
                ):
                    channels[idx] = previous
        result[me] = replace(device, channels=channels)
    return result


def parse_remotes(payload, devices):
    from .manual_devices import SPOT_MODELS

    if not isinstance(payload, dict):
        raise ProtocolError("Expected a remote dictionary")
    result = {}
    for remote_id, item in payload.items():
        if not isinstance(remote_id, str) or not isinstance(item, dict):
            raise ProtocolError("Invalid remote record")
        category, brand = item.get("category"), item.get("brand")
        if not isinstance(category, str) or category == "ac" or not isinstance(brand, str):
            continue
        matches = [
            d.me
            for d in devices.values()
            if d.model in SPOT_MODELS
            and (
                item.get("me") == d.me
                or (not item.get("me") and remote_id.startswith(f"AI_IR_{d.me}_"))
            )
        ]
        if len(matches) != 1:
            continue
        result[remote_id] = {
            "id": remote_id,
            "me": matches[0],
            "category": category,
            "brand": brand,
            "name": str(item.get("name") or remote_id),
        }
    return result
