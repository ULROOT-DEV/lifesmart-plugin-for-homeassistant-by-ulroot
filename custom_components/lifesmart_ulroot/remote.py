"""Existing non-AC SPOT remotes. Appliance power and learning are not inferred."""

from homeassistant.components.remote import RemoteEntity
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
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
        for remote_id, remote in coordinator.remotes.items():
            key = (
                identity(remote["agt"], remote["me"]) if coordinator.account_scope else remote["me"]
            )
            if remote_id not in added and key not in entry.options.get("excluded_devices", []):
                entities.append(LifeSmartRemote(coordinator, remote_id, remote))
                added.add(remote_id)
        if entities:
            async_add_entities(entities)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class LifeSmartRemote(CoordinatorEntity, RemoteEntity):
    _attr_has_entity_name = True
    _attr_is_on = True  # Command transmitter readiness; not appliance power state.

    def __init__(self, coordinator, remote_id, remote):
        super().__init__(coordinator)
        self.remote_id = remote_id
        self.agt = remote["agt"] if coordinator.account_scope else coordinator.station.agt
        self.me = identity(self.agt, remote["me"]) if coordinator.account_scope else remote["me"]
        self._attr_name = remote["name"]
        self._attr_unique_id = identity(self.agt, "remote", remote["id"])
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identity(self.agt, remote["me"]))}
        )

    @property
    def available(self):
        device = (self.coordinator.data or {}).get(self.me)
        return (
            super().available
            and self.coordinator.remotes_available
            and self.remote_id in self.coordinator.remotes
            and device is not None
            and device.online is not False
            and (
                not self.coordinator.account_scope
                or self.agt in self.coordinator.remote_stations_available
            )
        )

    async def async_send_command(self, command, **kwargs):
        if kwargs.get("num_repeats", 1) != 1 or kwargs.get("hold_secs", 0):
            raise HomeAssistantError("Repeating or holding is not supported")
        commands = [command] if isinstance(command, str) else list(command)
        await self.coordinator.send_remote(self.remote_id, commands)

    async def async_turn_on(self, **kwargs):
        raise HomeAssistantError("Use send_command with the remote power key")

    async def async_turn_off(self, **kwargs):
        raise HomeAssistantError("Use send_command with the remote power key")
