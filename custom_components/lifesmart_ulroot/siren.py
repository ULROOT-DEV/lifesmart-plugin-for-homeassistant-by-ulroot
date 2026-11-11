"""Documented alarm playback; uses the device's existing tone and volume."""

from homeassistant.components.siren import SirenEntity, SirenEntityFeature

from .devices import binary_value
from .entity import LifeSmartEntity, setup_platform


async def async_setup_entry(hass, entry, async_add_entities):
    await setup_platform(entry, async_add_entities, "siren", LifeSmartSiren)


class LifeSmartSiren(LifeSmartEntity, SirenEntity):
    _attr_supported_features = SirenEntityFeature.TURN_ON | SirenEntityFeature.TURN_OFF

    @property
    def is_on(self):
        idx = "SR" if self._model == "SL_DF_SR" else self.capability.idx
        return binary_value(self.device.channels.get(idx) if self.device else None, "type")

    async def async_turn_on(self, **kwargs):
        await self.command(self.capability.idx, 129, 1)

    async def async_turn_off(self, **kwargs):
        await self.command(self.capability.idx, 128, 0)
