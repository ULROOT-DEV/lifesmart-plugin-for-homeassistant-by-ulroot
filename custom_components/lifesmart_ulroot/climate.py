"""Model-specific climate controls, including packed and Nature configurations."""

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError

from .devices import binary_value
from .entity import LifeSmartEntity, setup_platform
from .manual_devices import climate_profile, nature_thermostat

MODES = {
    HVACMode.AUTO: 1,
    HVACMode.FAN_ONLY: 2,
    HVACMode.COOL: 3,
    HVACMode.HEAT: 4,
    HVACMode.DRY: 5,
}
FANS = {"low": 15, "medium": 45, "high": 75}


async def async_setup_entry(hass, entry, async_add_entities):
    await setup_platform(entry, async_add_entities, "climate", LifeSmartClimate)


class LifeSmartClimate(LifeSmartEntity, ClimateEntity):
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 18
    _attr_max_temp = 30
    _attr_target_temperature_step = 0.1
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator, device, capability):
        super().__init__(coordinator, device, capability)
        self._power, self._target, self._current, self._mode, self._fan = climate_profile(device)
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )
        self._modes = dict(MODES)
        self._fans = dict(FANS)
        if device.model in ("SL_CP_DN", "SL_CP_VL"):
            self._modes = {HVACMode.HEAT: 4}
            self._attr_min_temp = 5
            self._attr_target_temperature_step = 0.5
        elif device.model == "SL_CP_AIR":
            self._modes = {HVACMode.COOL: 0, HVACMode.HEAT: 1, HVACMode.FAN_ONLY: 2}
            self._fans = {"auto": 0, "low": 1, "medium": 2, "high": 3}
            self._attr_target_temperature_step = 0.5
        elif nature_thermostat(device):
            cfg = device.channels.get("P6")
            cfg = (int(cfg.raw) >> 6) & 7 if cfg and cfg.raw is not None else None
            allowed = {
                0: [],
                1: [2, 3, 4],
                2: [],
                3: [2, 3, 4],
                4: [1, 2, 3, 4],
                5: [2],
                6: [2, 3, 4],
            }.get(cfg, [])
            self._modes = {mode: value for mode, value in MODES.items() if value in allowed}
            self._fans.update(stop=0, auto=101)
            if cfg == 2:
                self._modes = {HVACMode.HEAT: 7}
                self._mode = None
                self._fan = None
            if cfg == 0:
                self._modes = {HVACMode.FAN_ONLY: 2}
                self._mode = None
            if cfg == 6:
                self._fans = {"stop": 0, "low": 15}
        self._attr_hvac_modes = [HVACMode.OFF, *self._modes]
        if self._fan == "packed" or self._fan in device.channels:
            self._attr_supported_features |= ClimateEntityFeature.FAN_MODE
            self._attr_fan_modes = list(self._fans)

    def _value(self, idx, scale=1):
        ch = self.device.channels.get(idx) if self.device else None
        return ch.decoded(scale) if ch else None

    def _raw(self, idx):
        ch = self.device.channels.get(idx) if self.device else None
        if not ch or ch.raw is None:
            raise HomeAssistantError("Current thermostat configuration is unavailable")
        return int(ch.raw)

    def _type(self, idx, fallback):
        ch = self.device.channels.get(idx) if self.device else None
        return ch.raw_type if ch and ch.raw_type is not None else fallback

    @property
    def native_current_temperature(self):
        return self._value(self._current, 0.1)

    @property
    def native_target_temperature(self):
        return self._value(self._target, 0.1)

    @property
    def hvac_mode(self):
        power = binary_value(self.device.channels.get(self._power) if self.device else None, "type")
        if power is False:
            return HVACMode.OFF
        if power is None:
            return None
        if not self._mode:
            return next(iter(self._modes), None)
        value = self._value(self._power if self._mode == "packed" else self._mode)
        if value is None:
            return None
        if self._mode == "packed":
            value = (int(value) >> 13) & 3
        if nature_thermostat(self.device) and value in (7, 8):
            return HVACMode.HEAT
        return next((mode for mode, val in self._modes.items() if val == value), None)

    @property
    def fan_mode(self):
        value = self._value(self._power if self._fan == "packed" else self._fan)
        if value is None:
            return None
        if self._fan == "packed":
            value = (int(value) >> 15) & 3
        elif value not in (0, 101):
            value = 15 if value < 30 else 45 if value < 65 else 75
        return next((mode for mode, val in self._fans.items() if val == value), None)

    async def async_turn_on(self):
        await self.command(self._power, 129, 1)

    async def async_turn_off(self):
        await self.command(self._power, 128, 0)

    async def async_set_hvac_mode(self, hvac_mode):
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
            return
        if hvac_mode not in self._modes:
            raise HomeAssistantError("Unsupported HVAC mode")
        if self._mode == "packed":
            value = (self._raw(self._power) & ~(3 << 13)) | (self._modes[hvac_mode] << 13)
            await self.command(self._power, self._type(self._power, 255), value)
        elif self._mode:
            await self.command(self._mode, self._type(self._mode, 206), self._modes[hvac_mode])
        await self.async_turn_on()

    async def async_set_temperature(self, **kwargs):
        value = kwargs.get(ATTR_TEMPERATURE)
        if value is None or not self._attr_min_temp <= value <= self._attr_max_temp:
            raise HomeAssistantError("Temperature is outside the supported range")
        await self.command(self._target, self._type(self._target, 136), round(value * 10))

    async def async_set_fan_mode(self, fan_mode):
        if not self._fan or fan_mode not in self._fans:
            raise HomeAssistantError("Unsupported fan mode")
        if self._fan == "packed":
            value = (self._raw(self._power) & ~(3 << 15)) | (self._fans[fan_mode] << 15)
            await self.command(self._power, self._type(self._power, 255), value)
        else:
            await self.command(self._fan, self._type(self._fan, 206), self._fans[fan_mode])
