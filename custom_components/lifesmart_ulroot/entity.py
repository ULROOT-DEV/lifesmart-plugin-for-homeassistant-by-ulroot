"""Shared identity and device grouping for all platforms."""

from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .devices import capabilities
from .identity import identity
from .names import device_name


class LifeSmartEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, device, capability):
        super().__init__(coordinator)
        self.me = coordinator.device_key(device)
        self.capability = capability
        self._model = device.model
        self._attr_unique_id = identity(device.agt, device.me, capability.key)
        self._attr_translation_key = capability.translation
        self._attr_translation_placeholders = {"channel": capability.idx}
        self._attr_entity_registry_enabled_default = capability.enabled
        if capability.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identity(device.agt, device.me))},
            via_device_id=coordinator.station_device_ids[device.agt],
            manufacturer="LifeSmart",
            model=device.model,
            name=device_name(device, coordinator.hass.config.language),
            sw_version=device.firmware,
        )

    @property
    def device(self):
        return (self.coordinator.data or {}).get(self.me)

    @property
    def channel(self):
        return self.device.channels.get(self.capability.idx) if self.device else None

    @property
    def available(self):
        return (
            super().available
            and self.device is not None
            and self.device.online is not False
            and (self.channel is not None or self.capability.idx == "")
            and any(
                c.key == self.capability.key and c.platform == self.capability.platform
                for c in capabilities(self.device)
            )
        )

    async def command(self, idx, kind, value):
        await self.coordinator.command(self.me, idx, kind, value)


async def setup_platform(entry, async_add_entities, platform, entity_class):
    coordinator = entry.runtime_data
    added = set()
    excluded = set(entry.options.get("excluded_devices", []))

    @callback
    def discover():
        entities = []
        for device in (coordinator.data or {}).values():
            device_key = coordinator.device_key(device)
            if device_key in excluded:
                continue
            for capability in capabilities(device):
                key = (device_key, capability.key)
                if capability.platform == platform and key not in added:
                    added.add(key)
                    entities.append(entity_class(coordinator, device, capability))
        if entities:
            async_add_entities(entities)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))
