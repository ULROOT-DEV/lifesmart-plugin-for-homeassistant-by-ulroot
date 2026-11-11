"""Export only allowlisted technical information; never raw payloads."""

from collections import Counter

from .const import VERSION
from .devices import capabilities


async def async_get_config_entry_diagnostics(hass, entry):
    runtime = entry.runtime_data
    devices = list((runtime.data or {}).values())
    return {
        "integration_version": VERSION,
        "connection_type": runtime.mode,
        "poll_interval": runtime.poll_interval,
        "push_connected": runtime.push_connected,
        "last_update_success": runtime.last_update_success,
        "device_count": len(devices),
        "scene_count": len(runtime.scenes),
        "scene_discovery_available": runtime.scenes_available,
        "remote_count": len(runtime.remotes),
        "remote_discovery_available": runtime.remotes_available,
        "model_counts": dict(Counter(d.model for d in devices)),
        "platform_counts": dict(Counter(c.platform for d in devices for c in capabilities(d))),
    }
