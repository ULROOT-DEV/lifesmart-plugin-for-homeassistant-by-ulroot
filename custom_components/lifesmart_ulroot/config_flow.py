"""UI configuration, password/token authentication, reauth and mode changes."""

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api.cloud import LEGACY_HOSTS, REGIONS, CloudClient
from .api.localweb import LocalWebClient
from .const import ACTIVATION_EMAIL, DEFAULT_CLOUD_URL, DOMAIN, POLL_CLOUD, POLL_LOCAL
from .credentials import matching_entries, refresh_lock, renewal_enabled, save_credentials
from .exceptions import (
    AuthenticationError,
    CannotConnect,
    IdentityMismatch,
    LifeSmartError,
    MissingIdentity,
    ProtocolError,
)
from .identity import account_id, identity, occupied_stations
from .models import Station
from .names import device_name, station_name

SECRET = selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))
LOCAL_CONNECTION = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            selector.SelectOptionDict(value="http", label="HTTP (8008)"),
            selector.SelectOptionDict(value="https", label="HTTPS (8080)"),
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)


def server_selector(current):
    labels = {"global": "GLOBAL (GS)", "eur": "EUR (EUROPE)", "cn1": "CN1 (VIP1)"}
    options = [
        selector.SelectOptionDict(
            value=f"https://{host}/app/", label=labels.get(region, region.upper())
        )
        for region, host in REGIONS.items()
    ]
    if current in {f"https://{host}/app/" for host in LEGACY_HOSTS}:
        options.append(selector.SelectOptionDict(value=current, label=current))
    return selector.SelectSelector(
        selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.DROPDOWN)
    )


def error_key(error):
    if isinstance(error, AuthenticationError):
        return "invalid_auth"
    if isinstance(error, MissingIdentity):
        return "missing_identity"
    if isinstance(error, IdentityMismatch):
        return "identity_mismatch"
    if isinstance(error, CannotConnect):
        return "cannot_connect"
    if isinstance(error, ProtocolError):
        return "invalid_response"
    return "api_error"


class LifeSmartConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    def __init__(self):
        self._data = {}
        self._stations = []
        self._target = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return LifeSmartOptionsFlow()

    async def async_step_user(self, user_input=None):
        if self._target and self._target.data.get("account_scope"):
            return await self.async_step_cloud()
        return self.async_show_menu(step_id="user", menu_options=["cloud", "localweb"])

    async def async_step_cloud(self, user_input=None):
        return self.async_show_menu(step_id="cloud", menu_options=["cloud_login", "cloud_token"])

    async def async_step_cloud_login(self, user_input=None):
        return await self._cloud_form("cloud_login", user_input)

    async def async_step_cloud_token(self, user_input=None):
        return await self._cloud_form("cloud_token", user_input)

    def _cloud_client(self):
        # Reuse a known deadline when reconfiguring the same managed token.
        if self._data.get("auto_refresh") and self._data.get("usertoken"):
            for entry in matching_entries(self.hass, self._data):
                if type(entry.data.get("expires_at")) in (int, float):
                    self._data["expires_at"] = entry.data["expires_at"]
                    break

        def updated(changes):
            save_credentials(self.hass, self._data, changes)
            self._data.update(changes)

        client = CloudClient(async_get_clientsession(self.hass), self._data, updated)
        client._refresh_lock = refresh_lock(self.hass, self._data)
        return client

    async def _cloud_form(self, step, user_input):
        errors = {}
        is_login = step == "cloud_login"
        defaults = self._target.data if self._target else {}
        if user_input is not None:
            user_input = dict(user_input)
            user_input["userid"] = user_input["userid"].strip()
            if not is_login and (
                not user_input["userid"].isascii() or not user_input["userid"].isdigit()
            ):
                result = await self._cloud_form(step, None)
                result["errors"] = {"userid": "invalid_userno"}
                return result
            self._data = {k: v for k, v in user_input.items() if k != "password"}
            self._data.update(connection_type="cloud", auth_method="login" if is_login else "token")
            self._data["auto_refresh"] = True if is_login else user_input.get("auto_refresh", False)
            if not is_login and self._cloud_duplicate():
                return self.async_abort(reason="already_configured")
            client = self._cloud_client()
            try:
                if is_login:
                    await client.login(user_input["userid"], user_input["password"])
                    self._data.update(client.credentials)
                    if self._cloud_duplicate():
                        return self.async_abort(reason="already_configured")
                self._stations = await client.stations()
                self._data.update(client.credentials)
                if not self._stations:
                    return self.async_abort(reason="no_stations")
                return await self._finish_cloud()
            except LifeSmartError as err:
                errors["base"] = error_key(err)
            finally:
                await client.close()
        schema = {
            vol.Required(
                "server", default=defaults.get("server", DEFAULT_CLOUD_URL)
            ): server_selector(defaults.get("server")),
            vol.Required("appkey", default=defaults.get("appkey", "")): str,
            vol.Required("apptoken"): SECRET,
            vol.Required("userid", default=defaults.get("userid", "")): str,
            vol.Required("password" if is_login else "usertoken"): SECRET,
        }
        if not is_login:
            schema[vol.Optional("auto_refresh", default=defaults.get("auto_refresh", False))] = bool
        return self.async_show_form(step_id=step, data_schema=vol.Schema(schema), errors=errors)

    def _cloud_duplicate(self):
        key = account_id(self._data)
        target_id = self._target.entry_id if self._target else None
        return any(
            entry.entry_id != target_id
            and entry.data.get("connection_type") == "cloud"
            and not entry.data.get("migrated_into")
            and account_id(entry.data) == key
            for entry in self.hass.config_entries.async_entries(DOMAIN)
        )

    async def _finish_cloud(self):
        key = account_id(self._data)
        if self._target:
            if self._target.data.get("connection_type") == "cloud":
                if str(self._data["userid"]) != str(self._target.data["userid"]):
                    return self.async_abort(reason="identity_mismatch")
            elif self._target.data["agt"] not in {s.agt for s in self._stations}:
                return self.async_abort(reason="identity_mismatch")
        if self._cloud_duplicate():
            return self.async_abort(reason="already_configured")
        await self.async_set_unique_id(key)
        data = {k: v for k, v in self._data.items() if k not in ("agt", "password")}
        data["auto_refresh"] = renewal_enabled(data)
        data.update(
            account_scope=True,
            stations={s.agt: {"name": s.name, "firmware": s.firmware} for s in self._stations},
        )
        title = f"LifeSmart Cloud ({data['userid']})"
        if self._target:
            if sources := self._target.data.get("migration_sources"):
                data["migration_sources"] = list(sources)
            options = dict(self._target.options)
            if agt := self._target.data.get("agt"):
                options["excluded_devices"] = [
                    identity(agt, me) for me in options.get("excluded_devices", [])
                ]
            self.hass.config_entries.async_update_entry(
                self._target, unique_id=key, title=title, options=options
            )
            return self.async_update_reload_and_abort(
                self._target,
                data=data,
                reason="reauth_successful"
                if self.source == config_entries.SOURCE_REAUTH
                else "reconfigure_successful",
            )
        self._abort_if_unique_id_configured()
        # Explicitly record stations already managed through another connection.
        excluded = occupied_stations(self.hass) & set(data["stations"])
        return self.async_create_entry(
            title=title, data=data, options={"excluded_stations": sorted(excluded)}
        )

    async def async_step_localweb(self, user_input=None):
        errors = {}
        defaults = (
            self._target.data
            if self._target and self._target.data.get("connection_type") == "localweb"
            else {}
        )
        if user_input is not None:
            use_tls = user_input["protocol"] == "https"
            self._data = {
                "host": user_input["host"].strip(),
                "username": user_input["username"].strip(),
                "password": user_input["password"],
                "port": 8080 if use_tls else 8008,
                "use_tls": use_tls,
                "verify_ssl": True,
                "connection_type": "localweb",
            }
            if self._target:
                self._data["agt"] = self._target.unique_id
            if use_tls:
                self._data["verify_ssl"] = defaults.get("verify_ssl", True)
                return await self.async_step_localweb_tls()
            result, errors = await self._validate_localweb()
            if result is not None:
                return result
            defaults = self._data
        schema = {
            vol.Required("host", default=defaults.get("host", "")): str,
            vol.Required(
                "protocol", default="https" if defaults.get("use_tls", False) else "http"
            ): LOCAL_CONNECTION,
            vol.Required("username", default=defaults.get("username", "")): str,
            vol.Required("password"): SECRET,
        }
        return self.async_show_form(
            step_id="localweb",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={"email": ACTIVATION_EMAIL},
        )

    async def async_step_localweb_tls(self, user_input=None):
        errors = {}
        if user_input is not None:
            self._data["verify_ssl"] = user_input["verify_ssl"]
            result, errors = await self._validate_localweb()
            if result is not None:
                return result
        return self.async_show_form(
            step_id="localweb_tls",
            data_schema=vol.Schema(
                {vol.Required("verify_ssl", default=self._data.get("verify_ssl", True)): bool}
            ),
            errors=errors,
        )

    async def _validate_localweb(self):
        client = None
        try:
            client = LocalWebClient(self._data)
            station = await client.validate()
            return await self._finish(station), {}
        except (LifeSmartError, ValueError) as err:
            return None, {"base": error_key(err)}
        finally:
            if client is not None:
                await client.close()

    async def _finish(self, station):
        if station.agt in occupied_stations(
            self.hass, self._target.entry_id if self._target else None
        ):
            return self.async_abort(reason="already_configured")
        await self.async_set_unique_id(station.agt)
        data = {**self._data, "agt": station.agt}
        if self._target:
            if self._target.unique_id != station.agt:
                return self.async_abort(reason="identity_mismatch")
            # Preserve the whole entry and entity registry, replace only transport data.
            return self.async_update_reload_and_abort(
                self._target,
                data=data,
                reason="reauth_successful"
                if self.source == config_entries.SOURCE_REAUTH
                else "reconfigure_successful",
            )
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=station_name(station, self.hass.config.language), data=data
        )

    async def async_step_reauth(self, entry_data):
        self._target = self._get_reauth_entry()
        if self._target.data.get("connection_type") == "cloud":
            if self._target.data.get("auth_method") != "login":
                return await self.async_step_reauth_token()
            return await self.async_step_cloud_login()
        return await self.async_step_user()

    async def async_step_reauth_token(self, user_input=None):
        errors = {}
        if user_input is not None:
            self._data = {
                key: value
                for key, value in self._target.data.items()
                if key not in ("expires_at", "password")
            }
            self._data.update(
                usertoken=user_input["usertoken"],
                auth_method="token",
                auto_refresh=self._target.data.get("auto_refresh", False),
            )
            client = self._cloud_client()
            try:
                self._stations = await client.stations()
                self._data.update(client.credentials)
                return await self._finish_cloud()
            except LifeSmartError as err:
                errors["base"] = (
                    "invalid_usertoken" if isinstance(err, AuthenticationError) else error_key(err)
                )
            finally:
                await client.close()
        return self.async_show_form(
            step_id="reauth_token",
            data_schema=vol.Schema({vol.Required("usertoken"): SECRET}),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input=None):
        self._target = self._get_reconfigure_entry()
        return await self.async_step_user()


class LifeSmartOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        entry = self.config_entry
        default = POLL_CLOUD if entry.data["connection_type"] == "cloud" else POLL_LOCAL
        devices = getattr(getattr(entry, "runtime_data", None), "data", {}) or {}
        stations = entry.data.get("stations", {})
        language = self.hass.config.language
        station_names = {
            agt: station_name(Station(agt, data.get("name", "")), language)
            for agt, data in stations.items()
        }
        options = [
            selector.SelectOptionDict(
                value=me,
                label=f"{station_names.get(d.agt, d.agt)} / {device_name(d, language)} ({d.me})"
                if entry.data.get("account_scope")
                else f"{device_name(d, language)} ({d.me})",
            )
            for me, d in devices.items()
        ]
        station_options = [
            selector.SelectOptionDict(value=agt, label=f"{name} ({agt})")
            for agt, name in station_names.items()
        ]
        account_options = (
            {
                vol.Optional(
                    "excluded_stations", default=list(entry.options.get("excluded_stations", []))
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=station_options, multiple=True, custom_value=True
                    )
                )
            }
            if entry.data.get("account_scope")
            else {}
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    **account_options,
                    vol.Optional(
                        "poll_interval", default=entry.options.get("poll_interval", default)
                    ): vol.All(vol.Coerce(int), vol.Range(min=15, max=600)),
                    vol.Optional(
                        "enable_push", default=entry.options.get("enable_push", True)
                    ): bool,
                    vol.Optional(
                        "excluded_devices", default=list(entry.options.get("excluded_devices", []))
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options, multiple=True, custom_value=True
                        )
                    ),
                }
            ),
        )
