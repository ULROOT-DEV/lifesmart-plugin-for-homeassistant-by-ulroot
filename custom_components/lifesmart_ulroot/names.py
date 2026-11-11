"""Friendly fallback names; never translate names chosen by the user."""

from .manual_devices import CATALOG

# Product terminology checked against RootONWeb DeviceTypeNames.js and
# RootONLocal devtype.map.ts. Other documented models use the manual catalog.
PRODUCT_NAMES = {
    "SL_SW_BJ84": ("Air Switch", "Air 스위치"),
    "SL_NATURE": ("Nature Switch", "Nature 스위치"),
    "SL_NATURE_X": ("Nature Switch", "Nature 스위치"),
    "SL_OE_DE": ("Smart Plug", "스마트 플러그"),
    "SL_SC_BB_V2": ("CUBE Button", "CUBE 버튼"),
    "SL_LI_WW": ("Light Control", "조명 제어기"),
    "SL_SW_WW": ("Light Control", "조명 제어기"),
    "SL_SW_DM1_V1": ("Light Dimmer", "조명 조광기"),
    "SL_SW_DM1_V2": ("Light Dimmer", "조명 조광기"),
    "V_HG_WW": ("Light Dimmer", "조명 조광기"),
    "SL_DOOYA": ("Blind Control", "블라인드 제어기"),
    "SL_DF_MM": ("Motion Sensor", "동작 감지 센서"),
    "SL_SC_BM": ("CUBE Motion Sensor", "CUBE 동작 감지 센서"),
    "SL_BP_MZ": ("Motion Sensor Pro", "동작 감지 센서 Pro"),
    "ZG#TS06012": ("Occupancy Sensor", "재실 센서"),
    "ZG#TS06015": ("Occupancy Sensor", "재실 센서"),
    "SL_DF_GG": ("Door/Window Sensor", "문열림 센서"),
    "SL_SC_BG": ("CUBE Door Sensor", "CUBE 문열림 센서"),
    "SL_SC_BE": ("CUBE Environmental Sensor", "CUBE 환경 센서"),
    "ZG#PMT300-SGMR-ZTN": ("Air Quality Sensor Pro", "공기질 센서 Pro"),
    "ZG#PMT300-S-ZTN": ("Air Quality Sensor Lite", "공기질 센서 Lite"),
    "ZG#MIR-SM100-E": ("Smoke Detector", "화재 감지 센서"),
    "V_AIR_P": ("Air Conditioner Control", "에어컨 제어기"),
    "V_FRESH_P": ("Ventilation Control", "환기 제어기"),
    "V_HTTP_P": ("AWAIR Air Monitor", "AWAIR 공기질 측정기"),
    "SL_P": ("General Controller", "범용 제어기"),
    "V_IND_S": ("Virtual Switch", "가상 스위치"),
    "V_SI": ("Virtual Switch", "가상 스위치"),
}

for family, english, korean in (
    ("SL_SW_BS", "Polar Switch", "Polar 스위치"),
    ("SL_SW_ND", "Polar Switch B", "Polar 스위치 B"),
    ("SL_MC_ND", "Polar Accessory Switch B", "Polar 보조 스위치 B"),
    ("SL_SW_MJ", "CUBE Switch Module", "CUBE 스위치 모듈"),
    ("SL_SW_IF", "BLEND Switch", "BLEND 스위치"),
    ("SL_SW_NS", "NATURE Switch 120", "NATURE 스위치 120"),
    ("SL_SF_IF", "BLEND Live-line Switch", "BLEND 단선식 스위치"),
    ("SL_SW_CP", "Orange BLEND Switch", "Orange BLEND 스위치"),
    ("SL_SW_FE", "Senna/Gezhi Switch", "Senna·Gezhi 스위치"),
    ("SL_SW_RC", "120 Switch", "120 스위치"),
):
    for channels in range(1, 4):
        PRODUCT_NAMES[f"{family}{channels}"] = (
            f"{english} {channels}",
            f"{korean} {channels}",
        )


def _localized(names, language):
    return names[1 if (language or "en").replace("_", "-").lower().split("-")[0] == "ko" else 0]


def _custom_name(name, *placeholders):
    if not isinstance(name, str) or not name.strip():
        return None
    if name.strip().casefold() in {str(value).casefold() for value in placeholders}:
        return None
    return name


def device_name(device, language):
    """Use the API name unless absent or equal to its device/station/model ID."""
    if name := _custom_name(device.name, device.me, device.agt, device.model):
        return name
    if names := PRODUCT_NAMES.get(device.model):
        return _localized(names, language)
    if entry := CATALOG.get(device.model):
        return _localized(entry[0].split(" / ", 1), language)
    return _localized(("LifeSmart Device", "LifeSmart 장치"), language)


def station_name(station, language):
    if name := _custom_name(station.name, station.agt, "Smart Station"):
        return name
    return _localized(("Smart Station", "스마트 스테이션"), language)
