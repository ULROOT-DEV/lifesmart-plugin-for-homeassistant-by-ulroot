"""Relay channels, separate from light/cover/climate encodings."""

from homeassistant.components.switch import SwitchEntity

from .entity import LifeSmartEntity, setup_platform


async def async_setup_entry(hass, entry, async_add_entities):
    await setup_platform(entry, async_add_entities, "switch", LifeSmartSwitch)


class LifeSmartSwitch(LifeSmartEntity, SwitchEntity):
    @property
    def is_on(self):
        if not self.channel:
            return None
        if self.channel.raw_type is not None:
            return bool(self.channel.raw_type & 1)
        value = self.channel.value()
        return value == 1 if value in (0, 1) else None

    async def async_turn_on(self, **kwargs):
        await self.command(self.capability.idx, 129, 1)

    async def async_turn_off(self, **kwargs):
        await self.command(self.capability.idx, 128, 0)
