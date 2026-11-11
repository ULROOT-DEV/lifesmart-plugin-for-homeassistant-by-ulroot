"""The station HTTP interface, deliberately separate from the UDP protocol."""

import ipaddress
import json
from urllib.parse import urlsplit

import aiohttp

from ..exceptions import IdentityMismatch, MissingIdentity, ProtocolError
from ..models import Station
from .base import HttpClient


def local_url(host: str, port: int, use_tls: bool) -> str:
    if (
        not isinstance(host, str)
        or not host
        or any(c in host for c in "/\\@?# \t\r\n")
        or not 1 <= port <= 65535
    ):
        raise ProtocolError("Invalid station address")
    hostname = host.strip("[]")
    if ":" in hostname:
        try:
            ipaddress.IPv6Address(hostname)
        except ValueError as err:
            raise ProtocolError("Invalid station IPv6 address") from err
        host = f"[{hostname}]"
    result = f"{'https' if use_tls else 'http'}://{host}:{port}/mgaweb/"
    if not urlsplit(result).hostname:
        raise ProtocolError("Invalid station address")
    return result


class LocalWebClient(HttpClient):
    def __init__(self, data: dict, *, session: aiohttp.ClientSession | None = None):
        self.data = dict(data)
        self.base_url = local_url(
            data["host"], int(data.get("port", 8008)), data.get("use_tls", False)
        )
        # Some stations advertise keep-alive but disconnect the next request.
        # Keep this pool private: changing HA's shared connector would affect Cloud
        # and unrelated integrations. Session injection is for protocol tests.
        self._owns_session = session is None
        if session is None:
            session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(force_close=True),
                cookie_jar=aiohttp.DummyCookieJar(),
            )
        super().__init__(session, verify_ssl=data.get("verify_ssl", True))
        self.agt = data.get("agt", "")
        self._sequence = 0

    async def close(self):
        if self._owns_session:
            await self.session.close()

    async def call(self, method: str, params: dict | None = None, *, write: bool = False):
        self._sequence += 1
        body = {
            "id": self._sequence,
            "user": self.data["username"],
            "password": self.data["password"],
            "method": method,
            "params": params or {},
        }
        result = await self.request(self.base_url + "api." + method, body, write=write)
        return result.get("message")

    async def validate(self) -> Station:
        state = await self.call("EpGetAgtState")
        payload = await self.snapshot()
        if not isinstance(state, dict) or not (isinstance(payload, list) or payload == {}):
            raise ProtocolError("Station response is invalid")
        ids = (
            {
                item["agt"]
                for item in payload
                if isinstance(item, dict) and isinstance(item.get("agt"), str) and item["agt"]
            }
            if isinstance(payload, list)
            else set()
        )
        if isinstance(state.get("agt"), str) and state["agt"]:
            ids.add(state["agt"])
        if not ids:
            raise MissingIdentity("No station identity returned; connect a device and retry")
        if len(ids) != 1 or self.agt and self.agt not in ids:
            raise IdentityMismatch("LocalWeb station identity differs")
        self.agt = next(iter(ids))
        return Station(
            self.agt,
            str(state.get("name") or "Smart Station"),
            str(state["agt_ver"]) if state.get("agt_ver") else None,
        )

    async def snapshot(self):
        return await self.call("EpGetAll", {"degree": 2})

    async def get_device(self, me: str):
        return await self.call("EpGet", {"me": me})

    async def enable_notifications(self):
        """Enable TCP push with the station's existing local login credentials."""
        # LocalWeb manual 5.2.2 uses an object, not a JSON string, for actargs.
        await self.call("EpConfigAgt", {"act": "notifyTcpCfg", "actargs": {}}, write=True)

    async def set_channel(self, me: str, idx: str, kind: int, value: int):
        await self.call("EpSet", {"me": me, "idx": idx, "type": kind, "val": value}, write=True)

    async def set_channels(self, me, channels):
        args = [
            {"agt": self.agt, "me": me, "idx": idx, "type": kind, "val": value}
            for idx, kind, value in channels
        ]
        await self.call("EpsSet", {"args": json.dumps(args, separators=(",", ":"))}, write=True)

    async def scenes(self):
        return await self.call("GetAllAIs")

    async def remotes(self):
        return await self.call("GetRemoteList")

    async def send_remote(self, remote, commands):
        await self.call(
            "SendKeys",
            {
                "me": remote["me"],
                "category": remote["category"],
                "ai": remote["id"],
                "keys": json.dumps(commands, separators=(",", ":")),
            },
            write=True,
        )

    async def activate_scene(self, scene_id):
        await self.call(
            "ControlAI",
            {"id": scene_id, "control": '{"command":"runOnce"}', "nonResp": 1},
            write=True,
        )
