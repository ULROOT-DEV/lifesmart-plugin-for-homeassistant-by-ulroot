"""Cloud WebSocket and LocalWeb TCP streams with bounded frames."""

import asyncio
import json
import ssl
import struct
import time
from contextlib import suppress

import aiohttp

from ..exceptions import CannotConnect, ProtocolError
from .base import require_success

HEADER = struct.Struct("!2sHHI")
MAX_FRAME = 1024 * 1024


def encode_frame(kind: int, body: dict) -> bytes:
    data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
    if len(data) > MAX_FRAME:
        raise ProtocolError("Push frame exceeds size limit")
    return HEADER.pack(b"JL", 0, kind, len(data)) + data


async def read_frame(reader: asyncio.StreamReader) -> tuple[int, dict]:
    magic, version, kind, size = HEADER.unpack(await reader.readexactly(HEADER.size))
    if magic != b"JL" or version != 0 or size > MAX_FRAME:
        raise ProtocolError("Invalid LocalWeb frame header")
    try:
        body = json.loads(await reader.readexactly(size))
    except (ValueError, UnicodeError) as err:
        raise ProtocolError("Invalid LocalWeb frame JSON") from err
    if not isinstance(body, dict):
        raise ProtocolError("Invalid LocalWeb frame body")
    return kind, body


async def local_stream(client, on_event, on_ready):
    # The station does not listen for TCP notifications until explicitly enabled.
    # Repeat this enable-only configuration on reconnect, including after a reboot.
    # This is separate from actuator commands, which are never replayed.
    await client.enable_notifications()
    data = client.data
    tls = data.get("push_tls", data.get("use_tls", False))
    context = None
    if tls:
        context = await asyncio.to_thread(ssl.create_default_context)
        if not data.get("verify_ssl", True):
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
    port = int(data.get("push_port", 8082 if tls else 8083))
    async with asyncio.timeout(10):
        reader, writer = await asyncio.open_connection(
            data["host"].strip("[]"), port, ssl=context, limit=MAX_FRAME
        )
    sequence = 0
    lock = asyncio.Lock()

    async def send(kind, request, args=None):
        nonlocal sequence
        async with lock:
            sequence += 1
            body = {"id": sequence, "req": request}
            if args is not None:
                body["args"] = args
            if request == "Auth":
                body["act"] = "Login"
            writer.write(encode_frame(kind, body))
            await writer.drain()

    async def heartbeat():
        while True:
            await asyncio.sleep(240)
            await send(11, "Heartbeat", {"ts": int(time.time())})

    heartbeat_task = None
    try:
        async with asyncio.timeout(10):
            await send(5, "Auth", {"uid": data["username"], "pwd": data["password"]})
            kind, reply = await read_frame(reader)
            if kind != 6:
                raise ProtocolError("Expected LocalWeb authentication reply")
            require_success(reply, auth=True)
        on_ready()
        heartbeat_task = asyncio.create_task(heartbeat())
        while True:
            async with asyncio.timeout(300):
                kind, body = await read_frame(reader)
            if heartbeat_task.done():
                heartbeat_task.result()
            if kind == 9:
                on_event(body)
                await send(10, "NotifyReply")
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError, OSError):
                await heartbeat_task
        writer.close()
        with suppress(OSError, TimeoutError):
            async with asyncio.timeout(5):
                await writer.wait_closed()


async def cloud_stream(client, on_event, on_ready):
    async with client.session.ws_connect(
        client.websocket_url,
        heartbeat=30,
        max_msg_size=MAX_FRAME,
        timeout=aiohttp.ClientWSTimeout(ws_receive=90, ws_close=5),
    ) as socket:
        await socket.send_json(client.envelope("WbAuth"))
        async with asyncio.timeout(10):
            response = await socket.receive_json()
            require_success(response, auth=True)
        on_ready()

        async def heartbeat():
            while True:
                await asyncio.sleep(30)
                await socket.send_json({"method": "ping"})

        heartbeat_task = asyncio.create_task(heartbeat())
        try:
            async for message in socket:
                if heartbeat_task.done():
                    heartbeat_task.result()
                if message.type == aiohttp.WSMsgType.TEXT:
                    try:
                        on_event(json.loads(message.data))
                    except (ValueError, UnicodeError) as err:
                        raise ProtocolError("Invalid Cloud event JSON") from err
                elif message.type == aiohttp.WSMsgType.ERROR:
                    raise CannotConnect("Cloud event connection failed")
        finally:
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError, OSError):
                await heartbeat_task
