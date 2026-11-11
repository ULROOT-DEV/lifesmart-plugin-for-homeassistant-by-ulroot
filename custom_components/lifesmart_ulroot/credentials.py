"""Coordinate login renewal and explicitly managed direct tokens."""

import asyncio

from .const import DOMAIN

TOKEN_KEYS = ("connection_type", "server", "appkey", "apptoken", "userid", "usertoken")


def renewal_enabled(data):
    return data.get("auth_method") == "login" or bool(data.get("auto_refresh", False))


def matching_entries(hass, data):
    return (
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if renewal_enabled(entry.data)
        and all(entry.data.get(key) == data.get(key) for key in TOKEN_KEYS)
    )


def refresh_lock(hass, data):
    key = (data["server"], data["appkey"], data["userid"])
    return hass.data.setdefault(f"{DOMAIN}_auth_locks", {}).setdefault(key, asyncio.Lock())


def save_credentials(hass, previous, changes):
    for entry in matching_entries(hass, previous):
        runtime = getattr(entry, "runtime_data", None)
        if runtime and runtime.mode == "cloud":
            runtime.client.credentials.update(changes)
        hass.config_entries.async_update_entry(entry, data={**entry.data, **changes})
