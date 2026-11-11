"""Explicit model/capability registry. Unknown IO points never become controls."""

from dataclasses import dataclass

from .models import Channel, Device


@dataclass(frozen=True, slots=True)
class Capability:
    key: str
    platform: str
    idx: str
    translation: str
    unit: str | None = None
    device_class: str | None = None
    scale: float = 1
    binary_rule: str = "val"
    diagnostic: bool = False
    codec: str = "scaled"
    enabled: bool = True


SWITCHES = {
    "SL_SW_BJ84": tuple(f"P{i}" for i in range(1, 9)),
    "SL_NATURE": ("P1", "P2", "P3"),
    "SL_NATURE_X": ("P1", "P2", "P3"),
    "SL_OE_DE": ("P1",),
    "SL_P": ("P2", "P3", "P4"),
    "V_IND_S": tuple(f"{p}{i}" for p in ("L", "P") for i in range(1, 9)),
    "V_SI": tuple(f"{p}{i}" for p in ("L", "P") for i in range(1, 9)),
}
for family in ("SL_SW_BS", "SL_SW_ND", "SL_MC_ND", "SL_SW_MJ"):
    for count in (1, 2, 3):
        SWITCHES[f"{family}{count}"] = tuple(f"P{i}" for i in range(1, count + 1))
for family in ("SL_SW_IF", "SL_SW_NS"):
    for count in (1, 2, 3):
        SWITCHES[f"{family}{count}"] = tuple(f"L{i}" for i in range(1, count + 1))

LIGHTS = {
    "SL_LI_WW": ("P1", "P2"),
    "SL_SW_WW": ("P1", "P2"),
    "SL_SW_DM1_V1": ("P1", None),
    "SL_SW_DM1_V2": ("P1", None),
    "V_HG_WW": ("L", None),
}
BINARY = {
    "SL_DF_MM": ("M", "motion", "type"),
    "SL_SC_BM": ("M", "motion", "val"),
    "SL_BP_MZ": ("P1", "motion", "val"),
    "ZG#TS06012": ("M1", "occupancy", "val"),
    "SL_DF_GG": ("A", "door", "type"),
    "SL_SC_BG": ("G", "door", "inverted"),
    "SL_SC_WA": ("WA", "moisture", "positive"),
    "ZG#MIR-SM100-E": ("A1", "smoke", "positive"),
}


def capabilities(device: Device) -> list[Capability]:
    from .manual_devices import expand_capabilities

    model, channels = device.model, device.channels
    result = []
    sensors = []
    if model in ("SL_SC_BE", "SL_SC_THL"):
        sensors = [
            ("T", "temperature", "°C", 0.1),
            ("H", "humidity", "%", 0.1),
            ("Z", "illuminance", "lx", 1),
        ]
    elif model in ("ZG#PMT300-S-ZTN", "ZG#PMT300-SGMR-ZTN"):
        sensors = [
            ("T1", "temperature", "°C", 0.1),
            ("H1", "humidity", "%", 0.1),
            ("Z1", "illuminance", "lx", 1),
            ("PM1", "pm25", "µg/m³", 1),
            ("PM(10)1", "pm10", "µg/m³", 1),
            ("CO2PPM1", "carbon_dioxide", "ppm", 1),
        ]
    elif model == "V_HTTP_P":
        sensors = [
            ("T", "temperature", "°C", 0.1),
            ("H", "humidity", "%", 0.1),
            ("CO2PPM", "carbon_dioxide", "ppm", 1),
        ]
        # PM scaling differs from normal display-value handling; defer until proven.
    for idx, kind, unit, scale in sensors:
        if idx in channels:
            result.append(Capability(f"{kind}:{idx}", "sensor", idx, kind, unit, kind, scale))
    if model in BINARY:
        idx, kind, rule = BINARY[model]
        if idx in channels:
            result.append(
                Capability(
                    f"{kind}:{idx}", "binary_sensor", idx, kind, device_class=kind, binary_rule=rule
                )
            )
    if model == "SL_SC_BE" and "s" in channels:
        result.append(
            Capability(
                "battery_low:s",
                "binary_sensor",
                "s",
                "battery_low",
                device_class="battery",
                binary_rule="low_battery",
                diagnostic=True,
            )
        )
    for idx in SWITCHES.get(model, ()):
        if idx in channels:
            result.append(Capability(f"switch:{idx}", "switch", idx, "channel"))
    if model in LIGHTS and LIGHTS[model][0] in channels:
        result.append(Capability("light:main", "light", LIGHTS[model][0], "light"))
    if model == "SL_DOOYA" and "P1" in channels:
        result.append(Capability("cover:main", "cover", "P1", "cover"))
    if model == "V_AIR_P" and all(idx in channels for idx in ("O", "MODE", "tT")):
        result.append(Capability("climate:main", "climate", "O", "climate"))
    return expand_capabilities(device, result, Capability)


def binary_value(channel: Channel | None, rule: str) -> bool | None:
    if channel is None:
        return None
    if rule == "type":
        return bool(channel.raw_type & 1) if channel.raw_type is not None else None
    value = channel.value()
    if value is None:
        return None
    if rule == "low_battery":
        return value == 3
    if rule == "positive":
        return value > 0
    if value not in (0, 1):
        return None
    return value == (0 if rule == "inverted" else 1)
