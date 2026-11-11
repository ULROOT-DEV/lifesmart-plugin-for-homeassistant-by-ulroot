"""LifeSmart by ULROOT: Cloud and LocalWeb integration."""

from .migration import async_migrate_entry as async_migrate_entry


async def async_setup_entry(hass, entry):
    from .const import PLATFORMS
    from .coordinator import LifeSmartCoordinator
    from .migration import finish_migration

    if entry.data.get("migrated_into"):
        # The authenticated account entry transfers registries before removal.
        return

    if (
        entry.data.get("connection_type") == "cloud"
        and entry.data.get("auth_method") == "login"
        and entry.data.get("auto_refresh") is not True
    ):
        hass.config_entries.async_update_entry(entry, data={**entry.data, "auto_refresh": True})

    coordinator = LifeSmartCoordinator(hass, entry)
    try:
        await coordinator.async_initialize()
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = coordinator
        await finish_migration(hass, entry)
        coordinator._register_stations()
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        coordinator.start_push()
    except BaseException:
        # Also release the private LocalWeb session if setup is cancelled.
        await coordinator.async_close()
        raise
    entry.async_on_unload(entry.add_update_listener(_options_updated))


async def _options_updated(hass, entry):
    # Token renewal updates entry.data too. Only options changes need a reload.
    if entry.options != entry.runtime_data.options:
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    from homeassistant.exceptions import HomeAssistantError

    from .const import PLATFORMS

    if entry.data.get("migrated_into"):
        return
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_close()
        return
    raise HomeAssistantError("Could not unload LifeSmart platforms")
