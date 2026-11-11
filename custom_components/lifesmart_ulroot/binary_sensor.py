"""Explicitly mapped contact, motion, smoke and moisture measurements."""

from homeassistant.components.binary_sensor import BinarySensorEntity

from .devices import binary_value
from .entity import LifeSmartEntity, setup_platform


async def async_setup_entry(hass, entry, async_add_entities):
    await setup_platform(entry, async_add_entities, "binary_sensor", LifeSmartBinarySensor)


class LifeSmartBinarySensor(LifeSmartEntity, BinarySensorEntity):
    def __init__(self, coordinator, device, capability):
        super().__init__(coordinator, device, capability)
        self._attr_device_class = capability.device_class

    @property
    def is_on(self):
        if self.capability.idx == "":
            return self.device.online if self.device else None
        return binary_value(self.channel, self.capability.binary_rule)

    @property
    def available(self):
        if self.capability.idx == "":
            return self.coordinator.last_update_success and self.device is not None
        return super().available
