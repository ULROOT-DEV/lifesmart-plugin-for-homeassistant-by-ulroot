"""Documented brightness, color temperature, RGB and RGBW light controls."""

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ATTR_RGBW_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.exceptions import HomeAssistantError

from .devices import LIGHTS, binary_value
from .entity import LifeSmartEntity, setup_platform
from .manual_devices import COLOR_LIGHTS


async def async_setup_entry(hass, entry, async_add_entities):
    await setup_platform(entry, async_add_entities, "light", LifeSmartLight)


class LifeSmartLight(LifeSmartEntity, LightEntity):
    _attr_min_color_temp_kelvin = 2700
    _attr_max_color_temp_kelvin = 6000

    def __init__(self, coordinator, device, capability):
        super().__init__(coordinator, device, capability)
        self._temp_idx = LIGHTS.get(device.model, (None, None))[1]
        self._color = COLOR_LIGHTS.get(device.model)
        mode = (
            (ColorMode.RGBW if self._color[1] else ColorMode.RGB)
            if self._color
            else (
                ColorMode.COLOR_TEMP
                if self._temp_idx and self._temp_idx in device.channels
                else ColorMode.BRIGHTNESS
            )
        )
        self._attr_supported_color_modes = {mode}
        self._attr_color_mode = mode

    @property
    def is_on(self):
        return binary_value(self.channel, "type")

    def _colors(self):
        ch = self.device.channels.get(self._color[0]) if self.device and self._color else None
        if not ch or ch.raw is None or not 0 <= ch.raw < 2**32:
            return None
        value = int(ch.raw)
        white = value >> 24
        if white > self._color[2] or (not self._color[1] and white):
            return None
        rgb = ((value >> 16) & 255, (value >> 8) & 255, value & 255)
        return (*rgb, round(white * 255 / self._color[2])) if self._color[1] else rgb

    @property
    def rgb_color(self):
        colors = self._colors()
        return colors[:3] if colors else None

    @property
    def rgbw_color(self):
        return self._colors() if self._color and self._color[1] else None

    @property
    def brightness(self):
        if self._color and self._model != "OD_WE_QUAN":
            colors = self._colors()
            return max(colors) if colors else None
        value = self.channel.raw if self.channel else None
        maximum = 100 if self._model == "OD_WE_QUAN" else 255
        return round(value * 255 / maximum) if value is not None and 0 <= value <= maximum else None

    @property
    def color_temp_kelvin(self):
        ch = self.device.channels.get(self._temp_idx) if self.device and self._temp_idx else None
        return (
            round(2700 + ch.raw * 3300 / 255)
            if ch and ch.raw is not None and 0 <= ch.raw <= 255
            else None
        )

    async def async_turn_on(self, **kwargs):
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if brightness is not None and not 0 <= brightness <= 255:
            raise HomeAssistantError("Brightness must be between 0 and 255")
        if brightness == 0:
            await self.async_turn_off()
            return
        if self._color:
            colors = kwargs.get(ATTR_RGBW_COLOR if self._color[1] else ATTR_RGB_COLOR)
            if colors is None and brightness is not None and self._model != "OD_WE_QUAN":
                colors = self._colors()
                if colors is None:
                    raise HomeAssistantError("Select a static color before changing its brightness")
            batch = []
            if colors is not None:
                if len(colors) != (4 if self._color[1] else 3) or any(
                    not 0 <= c <= 255 for c in colors
                ):
                    raise HomeAssistantError("Invalid light color")
                colors = tuple(colors)
                if brightness is not None and self._model != "OD_WE_QUAN":
                    maximum = max(colors) or 255
                    colors = tuple(round(c * brightness / maximum) for c in colors)
                r, g, b = colors[:3]
                w = round(colors[3] * self._color[2] / 255) if self._color[1] else 0
                batch.append((self._color[0], 255, (w << 24) | (r << 16) | (g << 8) | b))
                if "DYN" in self.device.channels:
                    batch.append(("DYN", 128, 0))
            if self._model == "OD_WE_QUAN":
                batch.append(
                    ("P1", 207, round(brightness * 100 / 255))
                    if brightness is not None
                    else ("P1", 129, 1)
                )
            elif not batch:
                batch.append((self.capability.idx, 129, 1))
            await self.coordinator.command(self.me, batch=batch)
            return
        kelvin = kwargs.get(ATTR_COLOR_TEMP_KELVIN)
        if kelvin is not None:
            if self._attr_color_mode != ColorMode.COLOR_TEMP or not 2700 <= kelvin <= 6000:
                raise HomeAssistantError("Unsupported color temperature")
            await self.command(self._temp_idx, 207, round((kelvin - 2700) * 255 / 3300))
        if brightness is None:
            await self.command(self.capability.idx, 129, 1)
        else:
            await self.command(self.capability.idx, 207, int(brightness))

    async def async_turn_off(self, **kwargs):
        await self.command(self.capability.idx, 128, 0)
