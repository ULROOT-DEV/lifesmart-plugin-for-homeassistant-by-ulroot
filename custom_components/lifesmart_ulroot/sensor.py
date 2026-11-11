"""Environmental measurements with native Home Assistant units and statistics."""

from homeassistant.components.sensor import SensorEntity, SensorStateClass

from .entity import LifeSmartEntity, setup_platform


async def async_setup_entry(hass, entry, async_add_entities):
    await setup_platform(entry, async_add_entities, "sensor", LifeSmartSensor)


class LifeSmartSensor(LifeSmartEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, device, capability):
        super().__init__(coordinator, device, capability)
        self._attr_native_unit_of_measurement = capability.unit
        self._attr_device_class = capability.device_class
        if capability.device_class == "energy":
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        elif (capability.diagnostic and capability.unit is None) or capability.translation in (
            "operating_mode",
            "button_event",
            "camera_status",
        ):
            self._attr_state_class = None

    @property
    def native_value(self):
        return (
            self.channel.decoded(self.capability.scale, self.capability.codec)
            if self.channel
            else None
        )
