"""Documented position motors and open/stop/close pulse controllers."""

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.exceptions import HomeAssistantError

from .entity import LifeSmartEntity, setup_platform
from .manual_devices import cover_profile


async def async_setup_entry(hass, entry, async_add_entities):
    await setup_platform(entry, async_add_entities, "cover", LifeSmartCover)


class LifeSmartCover(LifeSmartEntity, CoverEntity):
    _attr_device_class = CoverDeviceClass.CURTAIN
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, coordinator, device, capability):
        super().__init__(coordinator, device, capability)
        self.profile = cover_profile(device)
        if self.profile[0] == "pulse":
            self._attr_supported_features &= ~CoverEntityFeature.SET_POSITION
        if device.model == "SL_ETDOOR":
            self._attr_device_class = CoverDeviceClass.GARAGE

    @property
    def current_cover_position(self):
        value = self.channel.raw if self.channel else None
        if self.profile[0] != "position" or value is None or not 0 <= value <= 255:
            return None
        value = int(value) & 127
        return value if value <= 100 else None

    @property
    def is_closed(self):
        value = self.current_cover_position
        return value == 0 if value is not None else None

    @property
    def is_opening(self):
        return bool(
            self.channel
            and self.channel.raw_type is not None
            and self.channel.raw_type % 2
            and self.profile[0] == "position"
            and self.channel.raw is not None
            and int(self.channel.raw) & 128
        )

    @property
    def is_closing(self):
        return bool(
            self.channel
            and self.channel.raw_type is not None
            and self.channel.raw_type % 2
            and self.profile[0] == "position"
            and self.channel.raw is not None
            and not int(self.channel.raw) & 128
        )

    async def async_open_cover(self, **kwargs):
        if self.profile[0] == "pulse":
            await self.command(self.profile[1], 129, 1)
        else:
            await self.command(self.profile[2], 207, 100)

    async def async_close_cover(self, **kwargs):
        if self.profile[0] == "pulse":
            await self.command(self.profile[3], 129, 1)
        else:
            await self.command(self.profile[2], 207, 0)

    async def async_stop_cover(self, **kwargs):
        if self.profile[0] == "pulse":
            await self.command(self.profile[2], 129, 1)
        else:
            await self.command(self.profile[2], 206, 128)

    async def async_set_cover_position(self, **kwargs):
        position = kwargs[ATTR_POSITION]
        if self.profile[0] != "position" or not 0 <= position <= 100:
            raise HomeAssistantError("Cover position must be between 0 and 100")
        await self.command(self.profile[2], 207, int(position))
