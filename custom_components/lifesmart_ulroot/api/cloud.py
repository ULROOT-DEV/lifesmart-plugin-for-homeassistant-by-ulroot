"""LifeSmart signed Cloud API, login and direct-token authentication."""

import asyncio
import hashlib
import json
import math
import time
from collections.abc import Callable
from urllib.parse import urlsplit

from ..const import DEFAULT_CLOUD_URL
from ..credentials import renewal_enabled
from ..exceptions import AuthenticationError, MissingIdentity, ProtocolError
from ..models import Station
from .base import HttpClient

REGIONS = {
    "us": "api.us.ilifesmart.com",
    "global": "api.ilifesmart.com",
    "eur": "api.eur.ilifesmart.com",
    "jp": "api.jp.ilifesmart.com",
    "apz": "api.apz.ilifesmart.com",
    "cn0": "api.cn0.ilifesmart.com",
    "cn1": "api.cn1.ilifesmart.com",
    "cn2": "api.cn2.ilifesmart.com",
}
# Preserve stored addresses without claiming these old choices are documented servers.
LEGACY_HOSTS = {"api.eu.ilifesmart.com", "api.ap.ilifesmart.com", "api.cn.ilifesmart.com"}
REGION_ALIASES = {
    "gs": "global",
    "ame": "us",
    "europe": "eur",
    "eu": "eur",
    "jap": "jp",
    "ap": "apz",
    "vip1": "cn1",
}


def cloud_url(value: str) -> str:
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or host not in set(REGIONS.values()) | LEGACY_HOSTS
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != "/app"
    ):
        raise ProtocolError("Unsupported LifeSmart Cloud endpoint")
    return f"https://{host}/app/"


def wire_value(value):
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ProtocolError("Non-finite command value")
        return str(int(value)) if value == int(value) else str(value)
    raise ProtocolError("Structured parameters must be serialized explicitly")


def signature(method: str, params: dict, credentials: dict, timestamp: int) -> str:
    parts = [f"method:{method}"]
    parts.extend(
        f"{key}:{wire_value(value)}" for key, value in sorted(params.items()) if value is not None
    )
    parts.append(f"time:{timestamp}")
    parts.extend(
        f"{key}:{credentials[key]}" for key in ("userid", "usertoken", "appkey", "apptoken")
    )
    return hashlib.md5(",".join(parts).encode("utf-8"), usedforsecurity=False).hexdigest()


def payload_fields(payload: dict) -> dict:
    inner = payload.get("message")
    return {**payload, **inner} if isinstance(inner, dict) else payload


class CloudClient(HttpClient):
    def __init__(self, session, data: dict, on_credentials: Callable[[dict], None] | None = None):
        super().__init__(session)
        self.credentials = dict(data)
        self.base_url = cloud_url(data.get("server", DEFAULT_CLOUD_URL))
        self.agt = data.get("agt", "")
        self.on_credentials = on_credentials
        self._refresh_lock = asyncio.Lock()
        self._sequence = 0

    def envelope(self, method: str, params: dict | None = None, *, unsigned=()) -> dict:
        self._sequence += 1
        timestamp = int(time.time())
        params = {k: v for k, v in (params or {}).items() if v is not None}
        creds = self.credentials
        result = {
            "id": self._sequence,
            "method": method,
            "system": {
                "ver": "1.0",
                "lang": "en",
                "userid": creds["userid"],
                "appkey": creds["appkey"],
                "time": timestamp,
                "sign": signature(
                    method, {k: v for k, v in params.items() if k not in unsigned}, creds, timestamp
                ),
            },
        }
        if params:
            result["params"] = params
        return result

    def _save(self, changes: dict):
        self.credentials.update(changes)
        if self.on_credentials:
            self.on_credentials(changes)

    @property
    def can_refresh(self) -> bool:
        return renewal_enabled(self.credentials)

    async def login(self, userid: str, password: str):
        """The password and temporary login token are never persisted."""
        login = payload_fields(
            await self.request(
                self.base_url + "auth.login",
                {"uid": userid, "pwd": password, "appkey": self.credentials["appkey"]},
                auth=True,
            )
        )
        if not all(isinstance(login.get(k), str) and login[k] for k in ("userid", "token", "rgn")):
            raise ProtocolError("Login response identity, token or region missing")
        auth = payload_fields(
            await self.request(
                self.base_url + "auth.do_auth",
                {
                    "userid": login["userid"],
                    "token": login["token"],
                    "rgn": login["rgn"],
                    "appkey": self.credentials["appkey"],
                },
                auth=True,
            )
        )
        if not isinstance(auth.get("usertoken"), str) or not auth["usertoken"]:
            raise ProtocolError("Authorization response token missing")
        if auth.get("userid") and auth["userid"] != login["userid"]:
            raise AuthenticationError("Account identity changed during authorization")
        server = auth.get("svrurl")
        if server:
            self.base_url = cloud_url(server)
        else:
            region = str(auth.get("svrrgnid") or login.get("svrrgnid") or login["rgn"]).lower()
            region = REGION_ALIASES.get(region, region)
            if region in REGIONS:
                self.base_url = f"https://{REGIONS[region]}/app/"
        changes = {
            "userid": login["userid"],
            "usertoken": auth["usertoken"],
            "server": self.base_url,
            "rgn": login["rgn"],
        }
        if type(auth.get("expiredtime")) in (int, float):
            changes["expires_at"] = auth["expiredtime"]
        self._save(changes)

    async def refresh(self, previous: str):
        if not self.can_refresh:
            raise AuthenticationError("UserToken must be replaced through reauthentication")
        async with self._refresh_lock:
            if self.credentials.get("usertoken") != previous:
                return
            creds = self.credentials
            timestamp = int(time.time())
            expiry = self.credentials.get("expires_at")
            if type(expiry) in (int, float) and expiry <= timestamp:
                raise AuthenticationError("UserToken expired; reauthentication required")
            text = f"appkey={creds['appkey']}&time={timestamp}&userid={creds['userid']}&apptoken={creds['apptoken']}&usertoken={creds['usertoken']}"
            body = {
                "appkey": creds["appkey"],
                "time": str(timestamp),
                "userid": creds["userid"],
                "usertoken": creds["usertoken"],
                "sign": hashlib.md5(text.encode(), usedforsecurity=False).hexdigest(),
                "id": self._sequence + 1,
            }
            result = payload_fields(
                await self.request(self.base_url + "auth.refreshtoken", body, auth=True)
            )
            if not isinstance(result.get("usertoken"), str) or not result["usertoken"]:
                raise AuthenticationError("Token renewal did not return a token")
            changes = {"usertoken": result["usertoken"], "expires_at": None}
            if type(result.get("expiredtime")) in (int, float):
                changes["expires_at"] = result["expiredtime"]
            self._save(changes)
            if (
                type(changes["expires_at"]) not in (int, float)
                or changes["expires_at"] <= timestamp
            ):
                raise AuthenticationError(
                    "Renewal returned no usable expiry; reauthentication required"
                )

    async def call(
        self,
        method: str,
        params: dict | None = None,
        *,
        write: bool = False,
        namespace="api",
        unsigned=(),
    ):
        previous = self.credentials.get("usertoken", "")
        expiry = self.credentials.get("expires_at")
        # Bootstrap an explicitly managed token whose original expiry is unknown.
        # Fifteen minutes exceeds the maximum normal/recovery polling interval.
        if self.can_refresh and (type(expiry) not in (int, float) or expiry < time.time() + 900):
            await self.refresh(previous)
            previous = self.credentials["usertoken"]
        try:
            response = await self.request(
                self.base_url + namespace + "." + method,
                self.envelope(method, params, unsigned=unsigned),
                write=write,
            )
        except AuthenticationError:
            # Expired tokens cannot be refreshed. Only retry if a concurrent,
            # permitted renewal already replaced the token used by this request.
            if self.credentials.get("usertoken") == previous:
                raise
            response = await self.request(
                self.base_url + namespace + "." + method,
                self.envelope(method, params, unsigned=unsigned),
                write=write,
            )
        return response.get("message")

    async def stations(self) -> list[Station]:
        result = await self.call("EpGetAllAgts")
        if result == {}:
            return []
        if not isinstance(result, list):
            raise ProtocolError("Station list missing")
        stations = []
        for item in result:
            if isinstance(item, dict) and isinstance(item.get("agt"), str) and item["agt"]:
                stations.append(
                    Station(
                        item["agt"],
                        str(item.get("name") or "Smart Station"),
                        str(item["agt_ver"]) if item.get("agt_ver") else None,
                    )
                )
        return stations

    async def validate(self) -> Station:
        for station in await self.stations():
            if station.agt == self.agt:
                return station
        raise MissingIdentity("Selected station is not accessible to this account")

    async def snapshot(self):
        return await self.call("EpGetAll")

    def station_id(self, agt):
        station = self.agt if agt is None else agt
        if not isinstance(station, str) or not station:
            raise MissingIdentity("A target station is required")
        return station

    async def get_device(self, me: str, *, agt=None):
        return await self.call("EpGet", {"agt": self.station_id(agt), "me": me})

    async def set_channel(self, me: str, idx: str, kind: int, value: int, *, agt=None):
        await self.call(
            "EpSet",
            {"agt": self.station_id(agt), "me": me, "idx": idx, "type": kind, "val": value},
            write=True,
        )

    async def set_channels(self, me, channels, *, agt=None):
        args = [
            {"agt": self.station_id(agt), "me": me, "idx": idx, "type": kind, "val": value}
            for idx, kind, value in channels
        ]
        await self.call("EpsSet", {"args": json.dumps(args, separators=(",", ":"))}, write=True)

    async def scenes(self, *, agt=None):
        return await self.call("SceneGet", {"agt": self.station_id(agt)})

    async def activate_scene(self, scene_id, *, agt=None):
        await self.call("SceneSet", {"agt": self.station_id(agt), "id": scene_id}, write=True)

    async def remotes(self, *, agt=None):
        return await self.call("GetRemoteList", {"agt": self.station_id(agt)}, namespace="irapi")

    async def send_remote(self, remote, commands, *, agt=None):
        # SPOT v2 pp.27–29 explicitly excludes keys from the signature.
        keys = [
            {
                "category": remote["category"],
                "brand": remote["brand"],
                "ai": remote["id"],
                "keys": commands,
            }
        ]
        await self.call(
            "SendRemotesKeys",
            {
                "agt": self.station_id(agt),
                "me": remote["me"],
                "keys": json.dumps(keys, separators=(",", ":")),
            },
            write=True,
            namespace="irapi",
            unsigned=("keys",),
        )

    @property
    def websocket_url(self) -> str | None:
        host = urlsplit(self.base_url).hostname
        # Cloud manual p.195 omits CN0; use HTTP polling until push is documented.
        if host == REGIONS["cn0"]:
            return None
        port = "" if host == REGIONS["eur"] else ":8443"
        return f"wss://{host}{port}/wsapp/"
