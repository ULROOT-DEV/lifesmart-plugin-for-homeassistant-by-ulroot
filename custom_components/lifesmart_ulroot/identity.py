"""Stable account and station identities, independent of token rotation."""

from urllib.parse import quote

from .api.cloud import cloud_url
from .const import DOMAIN


def identity(*parts):
    return ":".join(quote(str(part), safe="") for part in parts)


def account_id(data):
    return identity("cloud", cloud_url(data["server"]), data["appkey"], data["userid"])


def station_claims(entry):
    if entry.data.get("migrated_into"):
        return set()
    if entry.data.get("account_scope"):
        return set(entry.data.get("stations", {})) - set(entry.options.get("excluded_stations", []))
    return {entry.data["agt"]} if entry.data.get("agt") else set()


def occupied_stations(hass, entry_id=None, *, prioritize=False):
    # LocalWeb/legacy station entries take precedence. For shared Cloud stations,
    # the earliest account entry wins, including simultaneous discovery.
    return set().union(
        *(
            station_claims(entry)
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.entry_id != entry_id
            and (not prioritize or not entry.data.get("account_scope") or entry.entry_id < entry_id)
        )
    )
