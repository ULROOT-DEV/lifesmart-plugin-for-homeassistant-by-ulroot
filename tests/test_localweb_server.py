"""Exercise real HTTP/TCP sockets against a synthetic LocalWeb station."""

import asyncio
from contextlib import suppress

import aiohttp
from aiohttp import web

from custom_components.lifesmart_ulroot.api.localweb import LocalWebClient
from custom_components.lifesmart_ulroot.api.push import encode_frame, local_stream, read_frame


async def test_station_that_rejects_reused_http_connections(device_payload):
    connections = set()
    requests = []

    async def handle(request):
        connection = request.transport
        if connection in connections:
            # Reproduce firmware that accepts the first request and drops the next.
            connection.close()
            return web.Response(status=500)
        connections.add(connection)
        body = await request.json()
        requests.append(body["method"])
        message = (
            {"agt": "station-test", "name": "Station"}
            if body["method"] == "EpGetAgtState"
            else device_payload
        )
        return web.json_response({"id": body["id"], "code": 0, "message": message})

    app = web.Application()
    app.router.add_post("/mgaweb/{endpoint}", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    client = LocalWebClient(
        {"host": "127.0.0.1", "port": port, "username": "test-local", "password": "fixture-only"}
    )
    try:
        assert (await client.validate()).agt == "station-test"
        assert await client.snapshot() == device_payload
        assert await client.snapshot() == device_payload
        assert requests == ["EpGetAgtState", "EpGetAll", "EpGetAll", "EpGetAll"]
        assert len(connections) == 4
    finally:
        await client.close()
        await runner.cleanup()
    assert client.session.closed


async def test_injected_session_is_not_closed_by_local_client():
    async with aiohttp.ClientSession() as session:
        client = LocalWebClient(
            {"host": "station.example", "username": "u", "password": "p"}, session=session
        )
        await client.close()
        assert not session.closed


async def test_localweb_http_read_and_write_contract(device_payload):
    received = []

    async def handle(request):
        body = await request.json()
        received.append(body)
        assert body["user"] == "test-local"
        assert body["password"] == "fixture-only"
        assert request.match_info["endpoint"] == "api." + body["method"]
        if body["method"] == "EpGetAgtState":
            message = {"agt": "station-test", "name": "Fixture station"}
        elif body["method"] == "EpGetAll":
            message = device_payload
        else:
            message = "ok"
        return web.json_response({"id": body["id"], "code": 0, "message": message})

    app = web.Application()
    app.router.add_post("/mgaweb/{endpoint}", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        async with aiohttp.ClientSession() as session:
            client = LocalWebClient(
                {
                    "host": "127.0.0.1",
                    "port": port,
                    "username": "test-local",
                    "password": "fixture-only",
                },
                session=session,
            )
            assert (await client.validate()).agt == "station-test"
            await client.set_channel("relay-test", "P1", 129, 1)
            assert received[-1]["params"] == {
                "me": "relay-test",
                "idx": "P1",
                "type": 129,
                "val": 1,
            }
    finally:
        await runner.cleanup()


async def test_localweb_tcp_auth_notify_ack_and_clean_close():
    acknowledged = asyncio.Event()
    handler_finished = asyncio.Event()
    got_event = asyncio.Event()
    received = []
    activation_requests = []

    async def activate(request):
        body = await request.json()
        assert body["user"] == "test-local"
        assert body["password"] == "fixture-only"
        assert body["method"] == "EpConfigAgt"
        assert body["params"] == {"act": "notifyTcpCfg", "actargs": {}}
        activation_requests.append(body)
        return web.json_response({"id": body["id"], "code": 0, "message": "success"})

    async def station(reader, writer):
        try:
            assert activation_requests  # HTTP enable must precede the TCP connection.
            kind, auth = await read_frame(reader)
            assert kind == 5 and auth["act"] == "Login"
            assert auth["args"] == {"uid": "test-local", "pwd": "fixture-only"}
            writer.write(encode_frame(6, {"code": 0}))
            event = encode_frame(
                9,
                {
                    "type": "io",
                    "msg": {
                        "agt": "station-test",
                        "me": "env-test",
                        "idx": "T",
                        "val": 210,
                        "ts": 100,
                    },
                },
            )
            writer.write(event[:7])
            await writer.drain()
            await asyncio.sleep(0.01)
            writer.write(event[7:])
            await writer.drain()
            kind, reply = await read_frame(reader)
            assert kind == 10 and reply["req"] == "NotifyReply"
            acknowledged.set()
            await reader.read()
        finally:
            writer.close()
            await writer.wait_closed()
            handler_finished.set()

    server = await asyncio.start_server(station, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    app = web.Application()
    app.router.add_post("/mgaweb/api.EpConfigAgt", activate)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    http_port = site._server.sockets[0].getsockname()[1]

    def event(payload):
        received.append(payload)
        got_event.set()

    try:
        async with aiohttp.ClientSession() as session:
            client = LocalWebClient(
                {
                    "host": "127.0.0.1",
                    "port": http_port,
                    "push_port": port,
                    "username": "test-local",
                    "password": "fixture-only",
                },
                session=session,
            )
            for attempt in range(2):
                got_event.clear()
                acknowledged.clear()
                handler_finished.clear()
                task = asyncio.create_task(local_stream(client, event, lambda: None))
                try:
                    await asyncio.wait_for(got_event.wait(), 3)
                    await asyncio.wait_for(acknowledged.wait(), 3)
                    assert received[-1]["msg"]["val"] == 210
                    assert len(activation_requests) == attempt + 1
                finally:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
                await asyncio.wait_for(handler_finished.wait(), 3)
    finally:
        server.close()
        await server.wait_closed()
        await runner.cleanup()
