"""Activate existing LifeSmart scenes; never recreate or edit their definitions."""

from homeassistant.components.scene import Scene
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .entity import identity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    added = set()

    @callback
    def discover():
        entities = []
        for scene_id in coordinator.scenes:
            if scene_id not in added:
                entities.append(LifeSmartScene(coordinator, scene_id))
                added.add(scene_id)
        if entities:
            async_add_entities(entities)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class LifeSmartScene(CoordinatorEntity, Scene):
    _attr_has_entity_name = True

    def __init__(self, coordinator, scene_id):
        super().__init__(coordinator)
        self.scene_id = scene_id
        self.agt, wire_id = (
            coordinator.scene_targets[scene_id]
            if coordinator.account_scope
            else (coordinator.station.agt, scene_id)
        )
        self._attr_unique_id = identity(self.agt, "scene", wire_id)
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, self.agt)})

    @property
    def name(self):
        return self.coordinator.scenes.get(self.scene_id, self.scene_id)

    @property
    def available(self):
        return (
            super().available
            and self.coordinator.scenes_available
            and self.scene_id in self.coordinator.scenes
            and (
                not self.coordinator.account_scope
                or self.agt in self.coordinator.scene_stations_available
            )
        )

    async def async_activate(self, **kwargs):
        await self.coordinator.activate_scene(self.scene_id)
