"""Wire-level contract tests, including forbidden credential forwarding."""

import asyncio
import hashlib
import json
from collections import defaultdict
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import aiohttp
import pytest

from custom_components.lifesmart_ulroot.api.base import require_success
from custom_components.lifesmart_ulroot.api.cloud import CloudClient, cloud_url, signature
from custom_components.lifesmart_ulroot.api.localweb import LocalWebClient, local_url
from custom_components.lifesmart_ulroot.api.push import (
    HEADER,
    MAX_FRAME,
    encode_frame,
    local_stream,
    read_frame,
)
from custom_components.lifesmart_ulroot.exceptions import (
    AuthenticationError,
    CommandOutcomeUnknown,
    IdentityMismatch,
    MissingIdentity,
    ProtocolError,
    RateLimited,
)

BASE = "https://api.us.ilifesmart.com/app/"


@asynccontextmanager
async def http_mock():
    """Mock the public HTTP boundary, without pinning aiohttp private constructors."""
    responses = defaultdict(list)
    requests = defaultdict(list)

    def register(url, **response):
        responses[url].append(response)

    @asynccontextmanager
    async def post(url, **kwargs):
        assert kwargs["allow_redirects"] is False
        requests[url].append(SimpleNamespace(kwargs=kwargs))
        assert responses[url], f"Unexpected HTTP request: {url}"
        response = responses[url].pop(0)
        if "exception" in response:
            raise response["exception"]

        async def chunks(size):
            yield json.dumps(response.get("payload", {})).encode()

        yield SimpleNamespace(
            status=response.get("status", 200),
            headers=response.get("headers", {}),
            content=SimpleNamespace(iter_chunked=chunks),
        )

    async with aiohttp.ClientSession() as session:
        with patch.object(session, "post", post):
            yield session, SimpleNamespace(post=register, requests=requests)


def test_signing_uses_exact_order_and_retains_zero(cloud_data):
    text = "method:EpSet,agt:station-test,idx:P1,me:relay-test,type:128,val:0,time:123,userid:8123456,usertoken:test-token,appkey:test-app,apptoken:test-app-secret"
    params = {
        "val": 0,
        "type": 128,
        "me": "relay-test",
        "idx": "P1",
        "agt": "station-test",
        "unused": None,
    }
    assert (
        signature("EpSet", params, cloud_data, 123)
        == hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()
    )


async def test_account_commands_sign_the_explicit_station_without_changing_shared_target(
    cloud_data,
):
    data = {key: value for key, value in cloud_data.items() if key != "agt"}
    async with http_mock() as (session, mock):
        client = CloudClient(session, data)
        for _ in range(2):
            mock.post(BASE + "api.EpSet", payload={"code": 0})
        with patch("custom_components.lifesmart_ulroot.api.cloud.time.time", return_value=123):
            await asyncio.gather(
                client.set_channel("same-device", "P1", 128, 0, agt="station-a"),
                client.set_channel("same-device", "P1", 129, 1, agt="station-b"),
            )
        bodies = [r.kwargs["json"] for r in mock.requests[BASE + "api.EpSet"]]
        assert {b["params"]["agt"] for b in bodies} == {"station-a", "station-b"}
        for body in bodies:
            expected = f"method:EpSet,agt:{body['params']['agt']},idx:P1,me:same-device,type:{body['params']['type']},val:{body['params']['val']},time:123,userid:8123456,usertoken:test-token,appkey:test-app,apptoken:test-app-secret"
            assert (
                body["system"]["sign"]
                == hashlib.md5(expected.encode(), usedforsecurity=False).hexdigest()
            )
        assert client.agt == ""
        with pytest.raises(MissingIdentity):
            await client.set_channel("same-device", "P1", 128, 0)


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"code": False},
        {"code": "0"},
        {"status": "ENL", "message": "sensitive"},
        {"code": "success"},
    ],
)
def test_http_200_is_not_success(response):
    with pytest.raises(ProtocolError):
        require_success(response)


def test_auth_success_is_a_separate_contract():
    assert require_success({"code": "success"}, auth=True)
    assert require_success({"code": 0})


@pytest.mark.parametrize(
    "url",
    [
        "http://api.us.ilifesmart.com/app/",
        "https://api.us.ilifesmart.com.evil.example/app/",
        "https://api.us.ilifesmart.com@app.evil.example/app/",
        "https://api.us.ilifesmart.com/app/?token=x",
        "https://api.us.ilifesmart.com:8443/app/",
    ],
)
def test_cloud_endpoint_allowlist(url):
    with pytest.raises(ProtocolError):
        cloud_url(url)


@pytest.mark.parametrize(
    ("host", "websocket"),
    [
        ("api.ilifesmart.com", "wss://api.ilifesmart.com:8443/wsapp/"),
        ("api.us.ilifesmart.com", "wss://api.us.ilifesmart.com:8443/wsapp/"),
        ("api.eur.ilifesmart.com", "wss://api.eur.ilifesmart.com/wsapp/"),
        ("api.jp.ilifesmart.com", "wss://api.jp.ilifesmart.com:8443/wsapp/"),
        ("api.apz.ilifesmart.com", "wss://api.apz.ilifesmart.com:8443/wsapp/"),
        ("api.cn0.ilifesmart.com", None),
        ("api.cn1.ilifesmart.com", "wss://api.cn1.ilifesmart.com:8443/wsapp/"),
        ("api.cn2.ilifesmart.com", "wss://api.cn2.ilifesmart.com:8443/wsapp/"),
    ],
)
async def test_documented_cloud_endpoints(cloud_data, host, websocket):
    url = f"https://{host}/app/"
    assert cloud_url(url) == url
    async with http_mock() as (session, _):
        client = CloudClient(session, {**cloud_data, "server": url})
        assert client.websocket_url == websocket


@pytest.mark.parametrize(
    ("partition", "host"),
    [
        ("EUROPE", "api.eur.ilifesmart.com"),
        ("APZ", "api.apz.ilifesmart.com"),
        ("VIP1", "api.cn1.ilifesmart.com"),
        ("CN0", "api.cn0.ilifesmart.com"),
    ],
)
async def test_login_uses_returned_server_partition_before_country(cloud_data, partition, host):
    async with http_mock() as (session, mock):
        mock.post(
            BASE + "auth.login",
            payload={"code": "success", "userid": "8123456", "token": "temporary", "rgn": "kr"},
        )
        mock.post(
            BASE + "auth.do_auth",
            payload={"code": "success", "usertoken": "issued", "svrrgnid": partition},
        )
        client = CloudClient(session, cloud_data)
        await client.login("8123456", "password")
        assert client.base_url == f"https://{host}/app/"
        assert client.credentials["server"] == client.base_url


async def test_password_login_passes_returned_region_and_does_not_store_password(cloud_data):
    async with http_mock() as (session, mock):
        mock.post(
            BASE + "auth.login",
            payload={
                "code": "success",
                "userid": "resolved-user",
                "token": "temporary",
                "rgn": "us",
            },
        )
        mock.post(
            BASE + "auth.do_auth",
            payload={
                "code": "success",
                "userid": "resolved-user",
                "usertoken": "issued-token",
                "svrurl": BASE,
            },
        )
        client = CloudClient(session, cloud_data)
        await client.login("8123456", "private-password")
        requests = [request for calls in mock.requests.values() for request in calls]
        assert requests[0].kwargs["json"] == {
            "uid": "8123456",
            "pwd": "private-password",
            "appkey": "test-app",
        }
        assert requests[1].kwargs["json"] == {
            "userid": "resolved-user",
            "token": "temporary",
            "rgn": "us",
            "appkey": "test-app",
        }
        assert client.credentials["usertoken"] == "issued-token"
        assert "private-password" not in json.dumps(client.credentials)
        assert "temporary" not in json.dumps(client.credentials)


async def test_login_missing_region_stops_before_authorization(cloud_data):
    async with http_mock() as (session, mock):
        mock.post(
            BASE + "auth.login",
            payload={"code": "success", "userid": "resolved", "token": "temporary"},
        )
        with pytest.raises(ProtocolError):
            await CloudClient(session, cloud_data).login("user", "pw")
        assert len(mock.requests) == 1


@pytest.mark.parametrize("expiry", [None, 1, 9999999999])
async def test_direct_token_failure_does_not_rotate_shared_token(cloud_data, expiry):
    cloud_data.update(auto_refresh=False, expires_at=expiry)
    async with http_mock() as (session, mock):
        mock.post(BASE + "api.EpGetAll", payload={"code": 10004, "message": "test-token"})
        with pytest.raises(AuthenticationError) as error:
            await CloudClient(session, cloud_data).snapshot()
        assert "test-token" not in str(error.value)
        assert len(mock.requests) == 1


@pytest.mark.parametrize(
    "auth_method,auto_refresh", [("login", True), ("login", False), ("token", True)]
)
@pytest.mark.parametrize("remaining", [None, 120, 899])
async def test_enabled_renewal_bootstraps_or_precedes_expiry(
    cloud_data, auth_method, auto_refresh, remaining
):
    import time

    cloud_data.update(
        auth_method=auth_method,
        auto_refresh=auto_refresh,
        expires_at=None if remaining is None else time.time() + remaining,
    )
    saved = []
    async with http_mock() as (session, mock):
        mock.post(
            BASE + "auth.refreshtoken",
            payload={"code": 0, "usertoken": "new-token", "expiredtime": 9999999999},
        )
        mock.post(BASE + "api.EpGetAll", payload={"code": 0, "message": []})
        client = CloudClient(session, cloud_data, saved.append)
        assert await client.snapshot() == []
        assert saved == [{"usertoken": "new-token", "expires_at": 9999999999}]
        mock.post(BASE + "api.EpGetAll", payload={"code": 0, "message": []})
        assert await client.snapshot() == []
        assert len(mock.requests[BASE + "auth.refreshtoken"]) == 1


async def test_direct_token_cannot_call_refresh_when_disabled(cloud_data):
    cloud_data["auto_refresh"] = False
    async with http_mock() as (session, mock):
        with pytest.raises(AuthenticationError):
            await CloudClient(session, cloud_data).refresh("test-token")
        assert not mock.requests


@pytest.mark.parametrize("auth_method", ["login", "token"])
async def test_expired_token_requires_reauthentication_without_refresh(cloud_data, auth_method):
    cloud_data.update(auth_method=auth_method, auto_refresh=True, expires_at=1)
    async with http_mock() as (session, mock):
        with pytest.raises(AuthenticationError):
            await CloudClient(session, cloud_data).snapshot()
        assert not mock.requests


async def test_login_auth_rejection_does_not_attempt_post_expiry_refresh(cloud_data):
    cloud_data.update(auth_method="login", auto_refresh=True, expires_at=9999999999)
    async with http_mock() as (session, mock):
        mock.post(BASE + "api.EpGetAll", payload={"code": 10005})
        with pytest.raises(AuthenticationError):
            await CloudClient(session, cloud_data).snapshot()
        assert len(mock.requests) == 1


async def test_enabled_renewal_leaves_unexpired_token_until_window(cloud_data):
    import time

    cloud_data.update(auto_refresh=True, expires_at=time.time() + 1800)
    async with http_mock() as (session, mock):
        mock.post(BASE + "api.EpGetAll", payload={"code": 0, "message": []})
        assert await CloudClient(session, cloud_data).snapshot() == []
        assert list(mock.requests) == [BASE + "api.EpGetAll"]


async def test_unknown_expiry_and_rejected_renewal_requires_reauthentication(cloud_data):
    cloud_data.update(auto_refresh=True)
    async with http_mock() as (session, mock):
        mock.post(BASE + "auth.refreshtoken", payload={"code": 10005})
        with pytest.raises(AuthenticationError):
            await CloudClient(session, cloud_data).snapshot()
        assert list(mock.requests) == [BASE + "auth.refreshtoken"]


async def test_renewal_missing_expiry_preserves_new_token_and_requests_reauthentication(cloud_data):
    cloud_data.update(auto_refresh=True)
    saved = []
    async with http_mock() as (session, mock):
        mock.post(BASE + "auth.refreshtoken", payload={"code": "success", "usertoken": "new-token"})
        with pytest.raises(AuthenticationError):
            await CloudClient(session, cloud_data, saved.append).snapshot()
        assert saved == [{"usertoken": "new-token", "expires_at": None}]
        assert list(mock.requests) == [BASE + "auth.refreshtoken"]


async def test_write_timeout_is_not_replayed(cloud_data):
    async with http_mock() as (session, mock):
        mock.post(BASE + "api.EpSet", exception=TimeoutError())
        with pytest.raises(CommandOutcomeUnknown):
            await CloudClient(session, cloud_data).set_channel("relay-test", "P1", 129, 1)
        assert sum(map(len, mock.requests.values())) == 1


async def test_redirect_never_forwards_credentials(cloud_data):
    async with http_mock() as (session, mock):
        mock.post(
            BASE + "api.EpGetAll", status=302, headers={"Location": "https://untrusted.example/"}
        )
        from custom_components.lifesmart_ulroot.exceptions import CannotConnect

        with pytest.raises(CannotConnect):
            await CloudClient(session, cloud_data).snapshot()
        assert sum(map(len, mock.requests.values())) == 1


async def test_rate_limit_blocks_followup_request(cloud_data):
    async with http_mock() as (session, mock):
        mock.post(BASE + "api.EpGetAll", status=429, headers={"Retry-After": "123"})
        client = CloudClient(session, cloud_data)
        with pytest.raises(RateLimited):
            await client.snapshot()
        with pytest.raises(RateLimited):
            await client.snapshot()
        assert sum(map(len, mock.requests.values())) == 1


async def test_localweb_envelope_and_station_identity(device_payload):
    data = {
        "host": "station.example",
        "port": 8008,
        "username": "local-test",
        "password": "local-secret",
    }
    async with http_mock() as (session, mock):
        base = "http://station.example:8008/mgaweb/"
        mock.post(base + "api.EpGetAgtState", payload={"code": 0, "message": {"name": "Station"}})
        mock.post(base + "api.EpGetAll", payload={"code": 0, "message": device_payload})
        client = LocalWebClient(data, session=session)
        assert (await client.validate()).agt == "station-test"
        requests = [request for calls in mock.requests.values() for request in calls]
        assert requests[0].kwargs["json"] == {
            "id": 1,
            "user": "local-test",
            "password": "local-secret",
            "method": "EpGetAgtState",
            "params": {},
        }
        assert requests[1].kwargs["json"]["params"] == {"degree": 2}


@pytest.mark.parametrize("tls,port", [(False, 8008), (True, 8080)])
async def test_localweb_notification_activation_payload_and_transport(tls, port):
    data = {
        "host": "station.example",
        "port": port,
        "use_tls": tls,
        "verify_ssl": False,
        "username": "test-local",
        "password": "fixture-only",
    }
    async with http_mock() as (session, mock):
        client = LocalWebClient(data, session=session)
        url = client.base_url + "api.EpConfigAgt"
        mock.post(url, payload={"code": 0, "message": "success"})
        await client.enable_notifications()
        requests = mock.requests[url]
        assert len(requests) == 1
        assert (
            url == f"{'https' if tls else 'http'}://station.example:{port}/mgaweb/api.EpConfigAgt"
        )
        assert requests[0].kwargs["ssl"] is False
        assert requests[0].kwargs["json"] == {
            "id": 1,
            "user": "test-local",
            "password": "fixture-only",
            "method": "EpConfigAgt",
            "params": {"act": "notifyTcpCfg", "actargs": {}},
        }


@pytest.mark.parametrize(
    "response,error",
    [
        ({"status": 401}, AuthenticationError),
        ({"payload": {"code": "invalid"}}, ProtocolError),
        ({"exception": TimeoutError()}, CommandOutcomeUnknown),
    ],
)
async def test_failed_notification_activation_does_not_open_tcp_or_report_ready(response, error):
    async with http_mock() as (session, mock):
        client = LocalWebClient(
            {"host": "station.example", "username": "u", "password": "p"}, session=session
        )
        url = client.base_url + "api.EpConfigAgt"
        mock.post(url, **response)
        ready = MagicMock()
        with patch(
            "custom_components.lifesmart_ulroot.api.push.asyncio.open_connection"
        ) as connect:
            with pytest.raises(error):
                await local_stream(client, MagicMock(), ready)
            connect.assert_not_called()
            ready.assert_not_called()
        assert len(mock.requests[url]) == 1


@pytest.mark.parametrize(
    "identity,expected", [(None, MissingIdentity), ("other-station", IdentityMismatch)]
)
async def test_localweb_does_not_trust_unverified_identity(identity, expected):
    async with http_mock() as (session, mock):
        base = "http://station.example:8008/mgaweb/"
        mock.post(base + "api.EpGetAgtState", payload={"code": 0, "message": {"agt": identity}})
        mock.post(base + "api.EpGetAll", payload={"code": 0, "message": []})
        client = LocalWebClient(
            {"host": "station.example", "username": "u", "password": "p", "agt": "station-test"},
            session=session,
        )
        with pytest.raises(expected):
            await client.validate()


def test_local_ipv6_address():
    assert local_url("::1", 8008, False) == "http://[::1]:8008/mgaweb/"
    with pytest.raises(ProtocolError):
        local_url("host/path", 8008, False)


async def test_fragmented_and_combined_tcp_frames():
    reader = asyncio.StreamReader()
    first = encode_frame(9, {"msg": {"name": "온도", "val": 0}})
    second = encode_frame(12, {"id": 2})
    task = asyncio.create_task(read_frame(reader))
    reader.feed_data(first[:3])
    await asyncio.sleep(0)
    assert not task.done()
    reader.feed_data(first[3:] + second)
    assert await task == (9, {"msg": {"name": "온도", "val": 0}})
    assert await read_frame(reader) == (12, {"id": 2})


async def test_oversized_frame_rejected_before_body():
    reader = asyncio.StreamReader()
    reader.feed_data(HEADER.pack(b"JL", 0, 9, MAX_FRAME + 1))
    with pytest.raises(ProtocolError):
        await read_frame(reader)
