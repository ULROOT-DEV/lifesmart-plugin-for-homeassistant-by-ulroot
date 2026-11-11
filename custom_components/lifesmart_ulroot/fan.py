"""Ventilation fans and purifier power from the documented per-model channels."""

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.exceptions import HomeAssistantError

from .devices import binary_value
from .entity import LifeSmartEntity, setup_platform


async def async_setup_entry(hass, entry, async_add_entities):
    await setup_platform(entry, async_add_entities, "fan", LifeSmartFan)


class LifeSmartFan(LifeSmartEntity, FanEntity):
    def __init__(self, coordinator, device, capability):
        super().__init__(coordinator, device, capability)
        self._power = "P1" if device.model == "SL_TR_ACIPM" else "O"
        self._speed = (
            "P2"
            if device.model == "SL_TR_ACIPM"
            else (
                capability.idx
                if device.model == "V_FRESH_P" and capability.idx in ("F1", "F2")
                else None
            )
        )
        self._attr_supported_features = FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
        if self._speed and self._speed in device.channels:
            self._attr_supported_features |= FanEntityFeature.SET_SPEED
            self._attr_speed_count = 3

    @property
    def is_on(self):
        power = self.device.channels.get(self._power) if self.device else None
        state = binary_value(power, "type")
        if state is True and self._speed and self.percentage is not None:
            return self.percentage > 0
        return state

    @property
    def percentage(self):
        ch = self.device.channels.get(self._speed) if self.device and self._speed else None
        if not ch or ch.raw is None:
            return None
        value = ch.raw
        if self._model == "SL_TR_ACIPM":
            return round(value * 100 / 3) if 0 <= value <= 3 else None
        if not 0 <= value < 100:
            return None
        return 0 if value == 0 else 33 if value < 30 else 67 if value < 65 else 100

    async def async_set_percentage(self, percentage):
        if not self._speed or not 0 <= percentage <= 100:
            raise HomeAssistantError("Fan speed is not supported")
        ch = self.device.channels.get(self._speed)
        if not ch or ch.raw_type is None:
            raise HomeAssistantError("Fan speed type is unavailable")
        level = 0 if percentage == 0 else 1 if percentage <= 33 else 2 if percentage <= 67 else 3
        if self._model == "SL_TR_ACIPM":
            power = self.device.channels.get("P1")
            if not power or power.raw is None or (int(power.raw) >> 13) & 3 != 2:
                raise HomeAssistantError(
                    "Select manual ventilation mode in the LifeSmart app first"
                )
            value = level
        else:
            value = (0, 15, 45, 75)[level]
        await self.command(self._speed, ch.raw_type, value)

    async def async_turn_on(self, percentage=None, **kwargs):
        if percentage is None and self._model == "V_FRESH_P" and self.percentage == 0:
            percentage = 33
        if percentage is not None:
            await self.async_set_percentage(percentage)
        await self.command(self._power, 129, 1)

    async def async_turn_off(self, **kwargs):
        if self._model == "V_FRESH_P" and self._speed:
            await self.async_set_percentage(0)
        else:
            await self.command(self._power, 128, 0)
