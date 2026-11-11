"""Device Attribute List v2.29 and ZigBee v2.4 mappings, independent of RootON.

Pages refer to the supplied English attribute PDF unless marked ZigBee.
Only documented output channels become controls. Missing functional specifications
remain visible as connectivity/diagnostics, never guessed control commands.
"""

import re

CATALOG = {}


def models(codes, name, page):
    for model in codes.split():
        CATALOG[model] = (name, str(page))
    return tuple(codes.split())


OUTLETS = models("SL_OL SL_OL_3C SL_OL_DE SL_OL_UK SL_OL_UL", "Smart socket / 스마트 콘센트", 6)
models("OD_WE_OT1 SL_OL_W SL_OE_3C SL_OE_DE", "Socket / 콘센트", "6–9")
SWITCHES = {model: ("O",) for model in OUTLETS}
SWITCHES.update(
    {
        "OD_WE_OT1": ("P1",),
        "SL_OL_W": ("L1",),
        "SL_OE_3C": ("P1",),
        "SL_S": ("P2",),
        "SL_P_SW": tuple(f"P{i}" for i in range(1, 10)),
        "SL_SW_RC": ("L1", "L2", "L3"),
        "SL_SF_RC": ("L1", "L2", "L3"),
        "SL_SW_NS6": tuple(f"P{i}" for i in range(1, 7)),
    }
)
for family, count, prefix, name in (
    ("SL_SW_IF", 3, "L", "BLEND switch / BLEND 스위치"),
    ("SL_SF_IF", 3, "L", "BLEND live-line switch / BLEND 스위치"),
    ("SL_SW_CP", 3, "L", "Orange BLEND switch / BLEND 스위치"),
    ("SL_SW_FE", 2, "L", "Senna/Gezhi switch / Senna·Gezhi 스위치"),
    ("SL_SW_RC", 3, "L", "120 switch / 120 스위치"),
    ("SL_SW_NS", 3, "L", "Nature switch / Nature 스위치"),
    ("SL_SW_ND", 3, "P", "Stellar/Polar switch / Stellar·Polar 스위치"),
    ("SL_MC_ND", 3, "P", "Stellar accessory / Stellar 보조 스위치"),
    ("SL_SW_BS", 3, "P", "Polar switch / Polar 스위치"),
    ("SL_SW_MJ", 3, "P", "CUBE switch module / CUBE 스위치 모듈"),
):
    for n in range(1, count + 1):
        model = f"{family}{n}"
        models(model, f"{name} {n}", "7–28")
        SWITCHES[model] = tuple(f"{prefix}{i}" for i in range(1, n + 1))
models("SL_S SL_P_SW SL_SW_RC SL_SF_RC SL_SW_NS6", "Switch/controller / 스위치·제어기", "7–26")
models("SL_SC_BB SL_SC_BB_V2", "CUBE Clicker / CUBE 버튼", "11,15")
models("SL_SPWM SL_SW_DM1 SL_SW_DM1_V1 SL_SW_DM1_V2", "Dimmer / 조광기", "11–14,23")
models("SL_SW_WW SL_LI_WW", "White light / 색온도 조명", "23,35")
models("SL_NATURE SL_NATURE_X", "Nature panel / Nature 패널", "20,80–85")
models("SL_CN_IF SL_CN_FE SL_SW_WIN SL_P_V2", "Curtain controller / 커튼 제어기", "29–32")
models(
    "SL_DOOYA SL_DOOYA_V1 SL_DOOYA_V2 SL_DOOYA_V3 SL_DOOYA_V4",
    "DOOYA motor / DOOYA 모터",
    "29–32,87–88",
)
models(
    "SL_LI_RGBW SL_CT_RGBW SL_SC_RGB OD_WE_QUAN SL_LI_GD1 SL_LI_UG1",
    "Color/landscape light / 컬러·조경 조명",
    "33–38",
)
SPOT_MODELS = models(
    "MSL_IRCTL OD_WE_IRCTL SL_SPOT SL_P_IR SL_P_IR_V2",
    "SPOT IR controller / SPOT 적외선 제어기",
    "38–40",
)
models("SL_SC_G SL_SC_BG", "Door sensor / 문열림 센서", "40–41")
models("SL_SC_MHW SL_SC_CM SL_SC_BM SL_P_RM", "Motion sensor / 동작 센서", "41–42,48–49")
models("SL_SC_THL SL_SC_BE", "Environmental sensor / 환경 센서", 43)
models("SL_SC_WA", "Water leak sensor / 누수 센서", 43)
models("SL_SC_CH", "Formaldehyde sensor / 포름알데히드 센서", 44)
models("SL_SC_CP", "Gas sensor / 가스 센서", 45)
models("SL_SC_CQ SL_SC_CA", "CO2/air quality sensor / CO2·공기질 센서", "46–48")
models("ELIQ_EM", "ELIQ electricity monitor / ELIQ 전력계", 47)
models("SL_P_A", "Smoke sensor / 연기 센서", 47)
models("SL_DF_GG", "DEFED door sensor / DEFED 문열림 센서", 49)
models("SL_DF_MM", "DEFED motion sensor / DEFED 동작 센서", 50)
models("SL_DF_SR", "DEFED siren / DEFED 사이렌", 51)
models("SL_DF_BB", "DEFED key fob / DEFED 리모컨", 52)
models("SL_SC_CN", "Noise sensor / 소음 센서", "53–55")
models("OD_MFRESH_M8088", "Air purifier / 공기청정기", "55–56")
LOCKS = models(
    "SL_LK_LS SL_LK_GTM SL_LK_AG SL_LK_SG SL_LK_YL SL_LK_TY SL_LK_DJ", "Door lock / 도어록", "56–60"
)
models(
    "V_AIR_P V_SZJSXR_P V_T8600_P SL_UACCB", "HVAC controller / 냉난방 제어기", "60–61,65–66,100"
)
models("SL_CP_DN SL_CP_AIR SL_CP_VL", "Thermostat / 온도조절기", "62–67")
models("SL_TR_ACIPM V_FRESH_P", "Ventilation controller / 환기 제어기", "61–62,68")
models("SL_P SL_JEMA", "General/HA controller / 범용·HA 제어기", "69–72")
models("V_DLT645_P V_DLT_645_P V_485_P", "Meter/485 controller / 전력계·485 제어기", "72–76")
models("SL_ETDOOR", "Garage door / 차고문", "76–77")
models("SL_ALM", "Smart alarm / 스마트 알람", "77–78")
CAMERAS = models(
    "cam LSCAM:LSI_CAM_GOS1 LSCAM:LSI_CAM_EZ1 LSCAM:SL_CAM LSCAM:LSCAMV1 LSCAM:LSICAMEZ1 LSCAM:LSICAMEZ2 LSCAM:LSLKCAMV1 LSCAM:LSICAMGOS1",
    "Camera telemetry / 카메라 상태",
    "79,90",
)
# Listed in appendix only: no complete channel or media/control contract supplied.
INVENTORY_ONLY = models(
    "SL_SC_CV LSSSMINIV1 OD_JIUWANLI_LOCK1 SL_P_BDLK",
    "Appendix-listed device / 부록 등재 장치",
    "89–90",
)
CATALOG.update(
    {
        "SL_SC_CV": ("Qrobot / 큐로봇", "89"),
        "LSSSMINIV1": ("Multi-function alarm / 다기능 알람", "90"),
        "OD_JIUWANLI_LOCK1": ("JiuWanLi door lock / JiuWanLi 도어록", "90"),
        "SL_P_BDLK": ("BE-TECH door lock module / BE-TECH 도어록 모듈", "90"),
    }
)
models(
    "ZG#MIR-SM100-E ZG#JT-GA102 ZG#PMT300-S-ZTN ZG#MIR-HE200",
    "ZigBee sensor / ZigBee 센서",
    "ZigBee 72–73",
)
ZIGBEE_LOCKS = models(
    "ZG#c700000202 ZG#INAHO.Door_Lock ZG#YMC420D ZG#RH8005",
    "ZigBee door lock / ZigBee 도어록",
    "ZigBee 73–74",
)
models(
    "ZG#ZBT-OnOffPlug-D0# ZG#TS0121", "ZigBee metering plug / ZigBee 전력 콘센트", "ZigBee 74–75"
)

DIMMERS = {"SL_SPWM", "SL_SW_DM1", "SL_SW_DM1_V1", "SL_SW_DM1_V2", "SL_LI_GD1", "OD_WE_QUAN"}
COLOR_LIGHTS = {
    "SL_LI_RGBW": ("RGBW", True, 255),
    "SL_CT_RGBW": ("RGBW", True, 255),
    "MSL_IRCTL": ("RGBW", True, 255),
    "SL_SC_RGB": ("RGB", False, 255),
    "OD_WE_IRCTL": ("RGB", False, 255),
    "SL_SPOT": ("RGB", False, 255),
    "SL_LI_UG1": ("P1", True, 100),
    "OD_WE_QUAN": ("P2", False, 255),
}
PULSE_COVERS = {
    "SL_SW_WIN": ("OP", "ST", "CL"),
    "SL_CN_IF": ("P1", "P2", "P3"),
    "SL_CN_FE": ("P1", "P2", "P3"),
    "SL_P_V2": ("P2", "P4", "P3"),
}


def controller_mode(device):
    channel = device.channels.get("P1")
    return (int(channel.raw) >> 24) & 14 if channel and channel.raw is not None else None


def nature_thermostat(device):
    ch = device.channels.get("P5")
    if device.model != "SL_NATURE":
        return False
    if ch and ch.raw is not None:
        return int(ch.raw) & 255 == 3
    return "P8" in device.channels and "P7" in device.channels


def cover_profile(device):
    if device.model in PULSE_COVERS:
        return ("pulse", *PULSE_COVERS[device.model])
    if device.model in ("SL_P", "SL_JEMA") and controller_mode(device) in (2, 4, 6):
        return ("pulse", "P2", "P4", "P3")
    if device.model == "SL_ETDOOR":
        return ("position", "P2", "P3")
    if device.model in {"SL_DOOYA", "SL_DOOYA_V1", "SL_DOOYA_V2", "SL_DOOYA_V3", "SL_DOOYA_V4"}:
        return ("position", "P1", "P2")
    return None


def climate_profile(device):
    # power, target, current, mode, fan; packed configuration models handled separately.
    if device.model in ("V_AIR_P", "V_SZJSXR_P", "V_T8600_P"):
        return ("O", "tT", "T", "MODE", "F")
    if device.model == "SL_UACCB":
        return ("P1", "P3", "P6", "P2", "P4")
    if device.model in ("SL_CP_DN", "SL_CP_VL"):
        return ("P1", "P3", "P4", None, None)
    if device.model == "SL_CP_AIR":
        return ("P1", "P4", "P5", "packed", "packed")
    if nature_thermostat(device):
        return ("P1", "P8", "P4", "P7", "P9")
    return None


def expand_capabilities(device, existing, C):
    model, channels = device.model, device.channels
    if model == "SL_SC_BB" and device.full_class == "SL_SC_BB_V2":
        model = "SL_SC_BB_V2"
    result = list(existing)

    def add(
        platform,
        idx,
        label="channel",
        unit=None,
        dc=None,
        scale=1,
        rule="val",
        codec="scaled",
        diagnostic=False,
        enabled=True,
    ):
        if idx and idx not in channels:
            return
        key = f"{label}:{idx}" if platform in ("sensor", "binary_sensor") else f"{platform}:{idx}"
        if platform == "switch":
            key = f"switch:{idx}"
        if not any(
            c.platform == platform and c.idx == idx and c.translation == label for c in result
        ):
            result.append(
                C(key, platform, idx, label, unit, dc, scale, rule, diagnostic, codec, enabled)
            )

    def sensor(idx, label, unit=None, dc=None, scale=1, codec="scaled"):
        add("sensor", idx, label, unit, dc, scale, codec=codec)

    def binary(idx, label, dc=None, rule="val"):
        add("binary_sensor", idx, label, dc=dc, rule=rule)

    for idx in SWITCHES.get(model, ()):
        add("switch", idx)
    if model in ("SL_P", "SL_JEMA"):
        mode = controller_mode(device)
        # Do not expose curtain motor directions as independently latched relays.
        if mode not in (0, 8, 10):
            result = [c for c in result if c.platform != "switch"]
        if mode in (0, 8, 10):
            for idx in ("P2", "P3", "P4"):
                add("switch", idx)
        if mode == 0:
            for idx in ("P5", "P6", "P7"):
                binary(idx, "input", rule="type")
        if model == "SL_JEMA":
            for idx in ("P8", "P9", "P10"):
                add("switch", idx)
    if nature_thermostat(device) or (
        model == "SL_NATURE"
        and "P5" in channels
        and not nature_thermostat(device)
        and channels["P5"].raw is not None
        and int(channels["P5"].raw) & 255 != 1
    ):
        result = [c for c in result if c.platform != "switch"]
    profile = cover_profile(device)
    if profile and profile[1] in channels and not any(c.platform == "cover" for c in result):
        result.append(C("cover:main", "cover", profile[1], "cover"))
    profile = climate_profile(device)
    if (
        profile
        and all(idx in channels for idx in profile[:2])
        and not any(c.platform == "climate" for c in result)
    ):
        result.append(C("climate:main", "climate", profile[0], "climate"))
    if model in DIMMERS or model in COLOR_LIGHTS:
        idx = "P1" if model in DIMMERS else COLOR_LIGHTS[model][0]
        if idx in channels and not any(c.platform == "light" for c in result):
            result.append(C("light:main", "light", idx, "light"))
    if model in ("SL_OE_3C", "SL_OE_DE"):
        sensor("P2", "energy", "kWh", "energy", codec="float32")
        sensor("P3", "power", "W", "power", codec="float32")
    if model in ("V_DLT645_P", "V_DLT_645_P", "V_485_P"):
        for idx in channels:
            match = re.fullmatch(r"(EE|EP|EPF|EF|EI|EV)(\d*)", idx)
            if match:
                label, unit, dc = {
                    "EE": ("energy", "kWh", "energy"),
                    "EP": ("power", "W", "power"),
                    "EPF": ("power_factor", None, None),
                    "EF": ("frequency", "Hz", "frequency"),
                    "EI": ("current", "A", "current"),
                    "EV": ("voltage", "V", "voltage"),
                }[match[1]]
                sensor(
                    idx, label, unit, dc, codec="float32" if match[1] in ("EE", "EP") else "typed"
                )
        if model == "V_485_P":
            for idx in channels:
                if idx == "O" or re.fullmatch(r"L[1-9]\d*", idx):
                    add("switch", idx)
            sensor("P1", "measurement", codec="float32")
            for idx, label, unit, dc in (
                ("T", "temperature", "°C", "temperature"),
                ("H", "humidity", "%", "humidity"),
                ("PM", "pm25", "µg/m³", "pm25"),
                ("PM10", "pm10", "µg/m³", "pm10"),
                ("COPPM", "carbon_monoxide", "ppm", "carbon_monoxide"),
                ("CO2PPM", "carbon_dioxide", "ppm", "carbon_dioxide"),
                ("CH2OPPM", "formaldehyde", "ppm", None),
                ("O2VOL", "oxygen", "%", None),
                ("NH3PPM", "ammonia", "ppm", None),
                ("H2SPPM", "hydrogen_sulfide", "ppm", None),
                ("TVOC", "voc", "mg/m³", "volatile_organic_compounds"),
                ("PHM", "noise", "dB", "sound_pressure"),
                ("SMOKE", "smoke_concentration", "ppm", None),
            ):
                sensor(idx, label, unit, dc, codec="typed")
    if model in ("ZG#ZBT-OnOffPlug-D0#", "ZG#TS0121"):
        add("switch", "O1")
        sensor("EE1", "energy", "kWh", "energy", codec="typed")
    if model in ("SL_SC_G", "SL_SC_BG"):
        binary("G", "door", "door", "inverted")
        binary("B", "button_pressed")
        binary("AXS", "vibration", "vibration", "positive")
    for m, idx in {
        "SL_SC_MHW": "M",
        "SL_SC_BM": "M",
        "SL_SC_CM": "P1",
        "SL_P_RM": "P1",
        "SL_LI_GD1": "P2",
    }.items():
        if model == m:
            binary(idx, "motion", "motion")
    if model in ("SL_SC_MHW", "SL_SC_BM"):
        sensor("Z", "illuminance", "lx", "illuminance")
    if model in ("SL_SW_DM1", "SL_SW_DM1_V1", "SL_SW_DM1_V2"):
        binary("P3", "motion", "motion")
        sensor("P4", "illuminance", "lx", "illuminance", 0.1)
    if model == "SL_LI_GD1":
        sensor("P3", "illuminance", "lx", "illuminance", 0.1)
    if model == "SL_LI_UG1":
        sensor("P2", "illuminance", "lx", "illuminance", 0.1)
        binary("P3", "charging", "battery_charging")
        sensor("P4", "battery", "%", "battery", codec="display_only")
    if model in ("SL_SC_CQ", "SL_SC_CA"):
        sensor("P1", "temperature", "°C", "temperature", 0.1)
        sensor("P2", "humidity", "%", "humidity", 0.1)
        sensor("P3", "carbon_dioxide", "ppm", "carbon_dioxide")
        if model == "SL_SC_CQ":
            sensor("P4", "voc", "mg/m³", "volatile_organic_compounds", 0.001)
        sensor(
            "P5" if model == "SL_SC_CQ" else "P4", "battery", "%", "battery", codec="display_only"
        )
    if model in ("SL_SC_CH", "SL_SC_CP", "SL_SC_CN"):
        label, unit, dc = {
            "SL_SC_CH": ("formaldehyde", "µg/m³", None),
            "SL_SC_CP": ("gas_concentration", None, None),
            "SL_SC_CN": ("noise", "dB", "sound_pressure"),
        }[model]
        sensor("P1", label, unit, dc)
        binary("P1", "alarm", "gas" if model == "SL_SC_CP" else "problem", "type")
        add("siren", "P3", "siren")
    if model == "SL_P_A":
        binary("P1", "smoke", "smoke")
        sensor("P2", "battery", "%", "battery", codec="display_only")
    if model == "ELIQ_EM":
        sensor("EPA", "power", "W", "power", codec="typed")
    if model.startswith("SL_DF_"):
        sensor("T", "temperature", "°C", "temperature", 0.1)
        binary("TR", "tamper", "tamper", "type")
        binary("V", "battery_low", "battery", "type")
        if model == "SL_DF_GG":
            binary("A2", "external_contact", "door", "type")
        if model == "SL_DF_SR":
            binary("SR", "alarm", "sound", "type")
            add("siren", "P1", "siren")
        if model == "SL_DF_BB":
            for idx in ("eB1", "eB2", "eB3", "eB4"):
                binary(idx, "button_pressed", rule="type")
    if model in (
        "SL_SC_G",
        "SL_SC_BG",
        "SL_SC_THL",
        "SL_SC_BE",
        "SL_SC_WA",
        "SL_SC_MHW",
        "SL_SC_BM",
        *CAMERAS,
    ) or model.startswith("SL_DF_"):
        sensor("V", "battery", "%", "battery", codec="display_only")
    if model in ("SL_SC_BB", "SL_SC_BB_V2"):
        binary(
            "B" if model == "SL_SC_BB" else "P1",
            "button_pressed",
            rule="val" if model == "SL_SC_BB" else "type",
        )
        sensor("V" if model == "SL_SC_BB" else "P2", "battery", "%", "battery")
        if model == "SL_SC_BB_V2":
            sensor("P1", "button_event")
    if model in LOCKS:
        sensor("BAT", "battery", "%", "battery")
        binary("ALM", "alarm", "problem", "positive")
        binary("EVTBELL", "doorbell", "sound", "type")
    if model in ZIGBEE_LOCKS or model == "ZG#MIR-SM100-E":
        sensor("BAT1", "battery", "%", "battery")
        sensor("V1", "voltage", "V", "voltage", 0.1)
    if model == "ZG#JT-GA102":
        binary("A1", "gas", "gas")
    if model == "ZG#MIR-HE200":
        binary("M1", "occupancy", "occupancy")
        sensor("Z1", "illuminance", "lx", "illuminance")
    if model in ("ZG#PMT300-S-ZTN", "ZG#PMT300-SGMR-ZTN"):
        sensor("PM(1)1", "pm1", "µg/m³", "pm1")
    if model in CAMERAS:
        binary("M", "motion", "motion")
        sensor("CFST", "camera_status")
    if model == "SL_ALM":
        add("siren", "P1", "siren")
    if model == "SL_ETDOOR":
        add("switch", "P1")
    if model in ("OD_MFRESH_M8088", "V_FRESH_P", "SL_TR_ACIPM"):
        power = "P1" if model == "SL_TR_ACIPM" else "O"
        if model == "V_FRESH_P" and any(idx in channels for idx in ("F1", "F2")):
            for idx in ("F1", "F2"):
                add("fan", idx, "supply_fan" if idx == "F1" else "exhaust_fan")
        else:
            add("fan", power, "fan")
        sensor("P6" if model == "SL_TR_ACIPM" else "T", "temperature", "°C", "temperature", 0.1)
    if model == "OD_MFRESH_M8088":
        sensor("RM", "operating_mode")
        sensor("H", "humidity", "%", "humidity", 0.1)
        sensor("PM", "pm25", "µg/m³", "pm25")
        sensor("FL", "filter_life", "h", "duration")
        sensor("UV", "uv_index")
    if model == "SL_TR_ACIPM":
        sensor("P4", "voc_ppm", "ppm", "volatile_organic_compounds_parts", 0.1)
        sensor("P5", "pm25", "µg/m³", "pm25")
    if model == "SL_CP_DN":
        sensor("P5", "floor_temperature", "°C", "temperature", 0.1)
    if model == "SL_CP_VL":
        binary("P5", "alarm", "problem", "positive")
        sensor("P6", "battery", "%", "battery", codec="display_only")
    # Declared models with no usable functional channel still get truthful connectivity.
    if model in CATALOG and not result:
        result.append(
            C(
                "connectivity",
                "binary_sensor",
                "",
                "connectivity",
                device_class="connectivity",
                diagnostic=True,
            )
        )
    return result
