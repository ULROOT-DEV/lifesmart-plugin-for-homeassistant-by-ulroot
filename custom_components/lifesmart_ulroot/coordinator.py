"""One Cloud account or LocalWeb station, shared by all entities."""

import asyncio
import logging
import random
import time
from contextlib import suppress
from datetime import timedelta

import aiohttp
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api.cloud import CloudClient
from .api.localweb import LocalWebClient
from .api.push import cloud_stream, local_stream
from .const import DOMAIN, POLL_CLOUD, POLL_LOCAL, POLL_PUSH
from .credentials import refresh_lock, save_credentials
from .exceptions import (
    AuthenticationError,
    CommandOutcomeUnknown,
    IdentityMismatch,
    LifeSmartError,
    RateLimited,
)
from .identity import identity, occupied_stations
from .manual_devices import SPOT_MODELS
from .models import (
    Station,
    event_records,
    merge_event,
    parse_devices,
    parse_remotes,
    parse_scenes,
    reconcile_snapshot,
)
from .names import device_name, station_name

LOGGER = logging.getLogger(__name__)


class LifeSmartCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        self.entry = entry
        self.options = dict(entry.options)
        self.mode = entry.data["connection_type"]
        self.poll_interval = int(
            entry.options.get("poll_interval", POLL_CLOUD if self.mode == "cloud" else POLL_LOCAL)
        )
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=self.poll_interval),
        )
        self.account_scope = self.mode == "cloud" and entry.data.get("account_scope", False)
        self.station = Station(entry.data.get("agt", ""), entry.title)
        self.stations = {}
        self.station_device_ids = {}
        self.scene_targets = {}
        self.scene_stations_available = set()
        self.remote_stations_available = set()
        self.push_connected = False
        self._push_task = None
        self._closed = False
        self._failures = 0
        self._next_request = 0.0
        self._command_locks = {}
        self.scenes = {}
        self.scenes_available = False
        self._scene_next = 0
        self.remotes = {}
        self.remotes_available = False
        self.client = (
            CloudClient(async_get_clientsession(hass), dict(entry.data), self._credentials_updated)
            if self.mode == "cloud"
            else LocalWebClient(dict(entry.data))
        )
        if self.mode == "cloud":
            # Runtime remains on the entry; only the per-account renewal mutex is shared.
            self.client._refresh_lock = refresh_lock(hass, entry.data)

    def _credentials_updated(self, changes):
        save_credentials(self.hass, self.entry.data, changes)

    def _auth_error(self):
        return ConfigEntryAuthFailed(
            translation_domain=DOMAIN,
            translation_key=(
                "invalid_usertoken"
                if self.mode == "cloud" and self.entry.data.get("auth_method") != "login"
                else "invalid_auth"
            ),
        )

    async def async_initialize(self):
        try:
            if self.account_scope:
                await self._refresh_stations()
            else:
                self.station = await self.client.validate()
                self.stations = {self.station.agt: self.station}
                self._register_stations()
        except AuthenticationError as err:
            raise self._auth_error() from err
        except IdentityMismatch as err:
            raise ConfigEntryAuthFailed("Station identity changed; reconfigure") from err
        except LifeSmartError as err:
            raise ConfigEntryNotReady(str(err)) from err

    def device_key(self, device):
        return identity(device.agt, device.me) if self.account_scope else device.me

    def _register_stations(self):
        if self.entry.data.get("migration_sources"):
            # Transfer existing hub devices before creating any for this entry.
            return
        registry = dr.async_get(self.hass)
        for agt, station in self.stations.items():
            device = registry.async_get_or_create(
                config_entry_id=self.entry.entry_id,
                identifiers={(DOMAIN, agt)},
                manufacturer="LifeSmart",
                model="Smart Station",
                name=station_name(station, self.hass.config.language),
                sw_version=station.firmware,
            )
            self.station_device_ids[agt] = device.id
        if not self.account_scope:
            self.station_device_id = self.station_device_ids[self.station.agt]

    async def _refresh_stations(self):
        stations = await self.client.stations()
        metadata = {s.agt: {"name": s.name, "firmware": s.firmware} for s in stations}
        if metadata != self.entry.data.get("stations"):
            self.hass.config_entries.async_update_entry(
                self.entry, data={**self.entry.data, "stations": metadata}
            )
        excluded = set(self.options.get("excluded_stations", []))
        excluded |= occupied_stations(self.hass, self.entry.entry_id, prioritize=True)
        self.stations = {s.agt: s for s in stations if s.agt not in excluded}
        self._register_stations()

    def _sync_device_names(self, devices):
        """Refresh vendor names without overwriting Home Assistant user names."""
        registry = dr.async_get(self.hass)
        for device in devices.values():
            registered = registry.async_get_device_by_identifier(
                (DOMAIN, identity(device.agt, device.me)), self.entry.entry_id
            )
            name = device_name(device, self.hass.config.language)
            if registered is not None and registered.name != name:
                registry.async_update_device(registered.id, name=name)

    async def _account_snapshot(self, payload, refresh_lists):
        snapshot = {}
        if refresh_lists:
            self.scene_stations_available.clear()
            self.remote_stations_available.clear()
            self.scenes = {
                k: v for k, v in self.scenes.items() if self.scene_targets[k][0] in self.stations
            }
            self.remotes = {k: v for k, v in self.remotes.items() if v["agt"] in self.stations}
        for agt in self.stations:
            devices = parse_devices(payload, agt, time.monotonic())
            snapshot.update({self.device_key(d): d for d in devices.values()})
            if not refresh_lists:
                continue
            try:
                scenes = parse_scenes(await self.client.scenes(agt=agt), agt)
                self.scenes = {
                    k: v for k, v in self.scenes.items() if self.scene_targets[k][0] != agt
                }
                for scene_id, name in scenes.items():
                    key = identity(agt, scene_id)
                    self.scenes[key] = name
                    self.scene_targets[key] = (agt, scene_id)
                self.scene_stations_available.add(agt)
            except AuthenticationError:
                raise
            except LifeSmartError as err:
                LOGGER.debug("Scene discovery unavailable: %s", type(err).__name__)
            try:
                remotes = (
                    parse_remotes(await self.client.remotes(agt=agt), devices)
                    if any(d.model in SPOT_MODELS for d in devices.values())
                    else {}
                )
                self.remotes = {k: v for k, v in self.remotes.items() if v["agt"] != agt}
                self.remotes.update(
                    {identity(agt, key): {**remote, "agt": agt} for key, remote in remotes.items()}
                )
                self.remote_stations_available.add(agt)
            except AuthenticationError:
                raise
            except LifeSmartError as err:
                LOGGER.debug("Remote discovery unavailable: %s", type(err).__name__)
        self.scenes_available = bool(self.scene_stations_available)
        self.remotes_available = bool(self.remote_stations_available)
        return snapshot

    async def _async_update_data(self):
        started = time.monotonic()
        if started < self._next_request:
            raise UpdateFailed("Waiting before the next LifeSmart request")
        try:
            refresh_lists = started >= self._scene_next
            if self.account_scope and refresh_lists:
                await self._refresh_stations()
            payload = await self.client.snapshot()
            if self.account_scope:
                snapshot = await self._account_snapshot(payload, refresh_lists)
                if refresh_lists:
                    self._scene_next = started + 300
            else:
                snapshot = parse_devices(payload, self.station.agt, time.monotonic())
            if not self.account_scope and refresh_lists:
                self._scene_next = started + 300
                try:
                    self.scenes = parse_scenes(await self.client.scenes(), self.station.agt)
                    self.scenes_available = True
                except AuthenticationError:
                    raise
                except LifeSmartError as err:
                    self.scenes_available = False
                    LOGGER.debug("Scene discovery unavailable: %s", type(err).__name__)
                if any(device.model in SPOT_MODELS for device in snapshot.values()):
                    try:
                        self.remotes = parse_remotes(await self.client.remotes(), snapshot)
                        self.remotes_available = True
                    except AuthenticationError:
                        raise
                    except LifeSmartError as err:
                        self.remotes_available = False
                        LOGGER.debug("Remote discovery unavailable: %s", type(err).__name__)
                else:
                    self.remotes = {}
                    self.remotes_available = False
            self._failures = 0
            self._sync_device_names(snapshot)
            return reconcile_snapshot(snapshot, self.data or {}, started)
        except AuthenticationError as err:
            raise self._auth_error() from err
        except LifeSmartError as err:
            self._failures += 1
            delay = (
                err.retry_after
                if isinstance(err, RateLimited)
                else min(60, 2 ** min(self._failures, 6))
            )
            self._next_request = time.monotonic() + delay
            raise UpdateFailed(str(err)) from err

    async def command(self, me, idx=None, kind=None, value=None, *, batch=None):
        if (
            self._closed
            or not self.last_update_success
            or me not in (self.data or {})
            or self.data[me].online is False
        ):
            raise HomeAssistantError("LifeSmart device is unavailable")
        device = self.data[me]
        target = {"agt": device.agt} if self.account_scope else {}
        operation = (
            (lambda: self.client.set_channels(device.me, batch, **target))
            if batch is not None
            else (lambda: self.client.set_channel(device.me, idx, kind, value, **target))
        )
        await self._execute(me, operation)

    async def activate_scene(self, scene_id):
        if (
            self._closed
            or not self.last_update_success
            or not self.scenes_available
            or scene_id not in self.scenes
            or (
                self.account_scope
                and self.scene_targets[scene_id][0] not in self.scene_stations_available
            )
        ):
            raise HomeAssistantError("LifeSmart scene is unavailable")
        agt, wire_id = (
            self.scene_targets[scene_id] if self.account_scope else (self.station.agt, scene_id)
        )
        target = {"agt": agt} if self.account_scope else {}
        await self._execute(
            f"scene:{scene_id}", lambda: self.client.activate_scene(wire_id, **target)
        )

    async def _execute(self, key, operation):
        lock = self._command_locks.setdefault(key, asyncio.Lock())
        async with lock:
            try:
                await operation()
            except CommandOutcomeUnknown as err:
                await self.async_request_refresh()
                raise HomeAssistantError(
                    "Command outcome unknown; state refresh requested"
                ) from err
            except AuthenticationError as err:
                self.entry.async_start_reauth(self.hass)
                error = self._auth_error()
                self.async_set_update_error(error)
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key=error.translation_key
                ) from err
            except LifeSmartError as err:
                raise HomeAssistantError(str(err)) from err
            await self.async_request_refresh()

    async def send_remote(self, remote_id, commands):
        if (
            self._closed
            or not self.last_update_success
            or not self.remotes_available
            or remote_id not in self.remotes
        ):
            raise HomeAssistantError("LifeSmart remote is unavailable")
        remote = self.remotes[remote_id]
        key = identity(remote["agt"], remote["me"]) if self.account_scope else remote["me"]
        device = (self.data or {}).get(key)
        if self.account_scope and remote["agt"] not in self.remote_stations_available:
            raise HomeAssistantError("LifeSmart remote is unavailable")
        if not device or device.online is False:
            raise HomeAssistantError("LifeSmart SPOT is unavailable")
        if (
            not commands
            or len(commands) > 50
            or any(not isinstance(key, str) or not key or len(key) > 128 for key in commands)
        ):
            raise HomeAssistantError("Invalid remote command list")
        target = {"agt": remote["agt"]} if self.account_scope else {}
        await self._execute(key, lambda: self.client.send_remote(remote, commands, **target))

    def _event(self, payload):
        data = self.data or {}
        unknown = False
        for event in event_records(payload):
            if self.account_scope:
                agt = event.get("agt")
                if agt not in self.stations:
                    # Periodic station discovery will pick up new stations.
                    continue
                key = identity(agt, event.get("me", ""))
                if key not in data:
                    unknown = True
                    continue
                old = data[key]
                merged = merge_event({old.me: old}, event, time.monotonic())
                if merged[old.me] is not old:
                    data = {**data, key: merged[old.me]}
                continue
            if event.get("agt") != self.station.agt:
                continue
            if event.get("me") not in data:
                unknown = True
            data = merge_event(data, event, time.monotonic())
        if data is not self.data:
            self.async_set_updated_data(data)
        if unknown:
            self.hass.async_create_task(self.async_request_refresh())

    def _ready(self):
        self.push_connected = True
        self.update_interval = timedelta(seconds=POLL_PUSH)
        self.hass.async_create_task(self.async_request_refresh())

    def start_push(self):
        if self.mode == "cloud" and self.client.websocket_url is None:
            return
        if self.options.get("enable_push", True) and self._push_task is None:
            self._push_task = self.entry.async_create_background_task(
                self.hass, self._push_loop(), "lifesmart-ulroot-events"
            )

    async def _push_loop(self):
        attempt = 0
        while not self._closed:
            try:
                if self.mode == "cloud":
                    await cloud_stream(self.client, self._event, self._ready)
                else:
                    await local_stream(self.client, self._event, self._ready)
            except (
                LifeSmartError,
                aiohttp.ClientError,
                OSError,
                TimeoutError,
                asyncio.IncompleteReadError,
                ValueError,
            ) as err:
                # A stream failure falls back to HTTP. HTTP determines reauthentication.
                LOGGER.debug("LifeSmart push reconnect: %s", type(err).__name__)
            finally:
                was_connected = self.push_connected
                self.push_connected = False
                self.update_interval = timedelta(seconds=self.poll_interval)
            if self._closed:
                break
            self.hass.async_create_task(self.async_request_refresh())
            attempt = 1 if was_connected else min(attempt + 1, 6)
            await asyncio.sleep(min(60, 2**attempt) + random.random())

    async def async_close(self):
        self._closed = True
        if self._push_task:
            self._push_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._push_task
            self._push_task = None
        await self.async_shutdown()
        await self.client.close()
