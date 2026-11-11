"""Merge legacy Cloud station entries while preserving registry identities."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .credentials import renewal_enabled
from .identity import account_id, identity


async def async_migrate_entry(hass, entry):
    if entry.version > 2:
        return False
    if entry.version == 2:
        return True
    if entry.data.get("connection_type") != "cloud":
        hass.config_entries.async_update_entry(entry, version=2)
        return True
    key = account_id(entry.data)
    peers = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.data.get("connection_type") == "cloud"
        and not e.data.get("migrated_into")
        and account_id(e.data) == key
    ]
    # Preserve unmanaged direct tokens before any login/managed credentials.
    # Login always renews, including legacy entries with auto_refresh=False.
    peers.sort(
        key=lambda e: (
            renewal_enabled(e.data),
            not e.data.get("account_scope", False),
            e.entry_id,
        )
    )
    primary = peers[0]
    data = {k: v for k, v in primary.data.items() if k not in ("agt", "password")}
    data["account_scope"] = True
    data["auto_refresh"] = all(renewal_enabled(e.data) for e in peers)
    stations = dict(data.get("stations", {}))
    excluded = set()
    sources = set(data.get("migration_sources", []))
    for peer in peers:
        if agt := peer.data.get("agt"):
            stations[agt] = {"name": peer.title, "firmware": None}
            excluded.update(identity(agt, me) for me in peer.options.get("excluded_devices", []))
        else:
            excluded.update(peer.options.get("excluded_devices", []))
        if peer is not primary:
            sources.add(peer.entry_id)
            hass.config_entries.async_update_entry(
                peer,
                data={**peer.data, "migrated_into": primary.entry_id},
                version=2,
                unique_id=identity("migrated", peer.entry_id),
            )
    data.update(stations=stations, migration_sources=sorted(sources))
    hass.config_entries.async_update_entry(
        primary,
        data=data,
        options={**primary.options, "excluded_devices": sorted(excluded)},
        unique_id=key,
        title=f"LifeSmart Cloud ({data['userid']})",
        version=2,
    )
    return True


async def finish_migration(hass, entry):
    """Only remove old entries after the account authenticated and loaded data."""
    devices, entities = dr.async_get(hass), er.async_get(hass)
    for source_id in entry.data.get("migration_sources", []):
        source = hass.config_entries.async_get_entry(source_id)
        if source is None:
            continue
        if source.state == ConfigEntryState.LOADED:
            await hass.config_entries.async_unload(source_id)
        for device in dr.async_entries_for_config_entry(devices, source_id):
            devices.async_update_device(device.id, new_config_entry_id=entry.entry_id)
        for entity in er.async_entries_for_config_entry(entities, source_id):
            entities.async_update_entity(entity.entity_id, config_entry_id=entry.entry_id)
        await hass.config_entries.async_remove(source_id)
    if "migration_sources" in entry.data:
        data = dict(entry.data)
        data.pop("migration_sources")
        hass.config_entries.async_update_entry(entry, data=data)
