"""Password/token/local setup and preservation of identity on reconfiguration."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.lifesmart_ulroot.config_flow import LifeSmartConfigFlow
from custom_components.lifesmart_ulroot.const import DOMAIN
from custom_components.lifesmart_ulroot.exceptions import AuthenticationError
from custom_components.lifesmart_ulroot.identity import account_id
from custom_components.lifesmart_ulroot.models import Station


@pytest.fixture
def setup_mock():
    with patch("custom_components.lifesmart_ulroot.async_setup_entry", return_value=None):
        yield


@pytest.mark.parametrize("step", ["cloud_login", "cloud_token"])
async def test_new_cloud_form_defaults_to_us_and_has_documented_servers(step):
    flow = LifeSmartConfigFlow()
    result = await getattr(flow, f"async_step_{step}")()
    schema = result["data_schema"].schema
    server = next(key for key in schema if str(key) == "server")
    assert server.default() == "https://api.us.ilifesmart.com/app/"
    options = schema[server].config["options"]
    assert options[0]["value"] == server.default()
    assert {option["value"] for option in options} == {
        f"https://{host}/app/"
        for host in (
            "api.us.ilifesmart.com",
            "api.ilifesmart.com",
            "api.eur.ilifesmart.com",
            "api.jp.ilifesmart.com",
            "api.apz.ilifesmart.com",
            "api.cn0.ilifesmart.com",
            "api.cn1.ilifesmart.com",
            "api.cn2.ilifesmart.com",
        )
    }


@pytest.mark.parametrize("host", ["api.ilifesmart.com", "api.eu.ilifesmart.com"])
async def test_reconfigure_preserves_stored_server(hass, config_entry, host):
    url = f"https://{host}/app/"
    hass.config_entries.async_update_entry(config_entry, data={**config_entry.data, "server": url})
    flow = LifeSmartConfigFlow()
    flow._target = config_entry
    result = await flow.async_step_cloud_token()
    schema = result["data_schema"].schema
    server = next(key for key in schema if str(key) == "server")
    assert server.default() == url
    assert url in [option["value"] for option in schema[server].config["options"]]
    assert config_entry.data["server"] == url


async def test_setup_renewal_updates_existing_station_using_same_managed_token(hass, config_entry):
    import time

    hass.config_entries.async_update_entry(
        config_entry,
        data={**config_entry.data, "auto_refresh": True, "expires_at": time.time() + 120},
    )
    flow = LifeSmartConfigFlow()
    flow.hass = hass
    flow._data = {key: value for key, value in config_entry.data.items() if key != "expires_at"}
    client = flow._cloud_client()
    assert client.credentials["expires_at"] == config_entry.data["expires_at"]
    with patch.object(
        client,
        "request",
        side_effect=[
            {"code": "success", "usertoken": "new-token", "expiredtime": 9999999999},
            {"code": 0, "message": []},
        ],
    ):
        assert await client.snapshot() == []
    assert config_entry.data["usertoken"] == "new-token"
    assert flow._data["usertoken"] == "new-token"
    assert config_entry.data["expires_at"] == 9999999999


@pytest.mark.parametrize("auto_refresh", [False, True])
async def test_cloud_token_flow(hass, cloud_data, setup_mock, auto_refresh):
    cloud_data["auto_refresh"] = auto_refresh
    with patch("custom_components.lifesmart_ulroot.config_flow.CloudClient") as factory:
        client = factory.return_value
        client.credentials = dict(cloud_data)
        client.stations = AsyncMock(return_value=[Station("station-test", "Station")])
        client.close = AsyncMock()
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.MENU
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "cloud"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "cloud_token"}
        )
        assert "auto_refresh" in {str(key) for key in result["data_schema"].schema}
        form = {
            key: cloud_data[key] for key in ("server", "appkey", "apptoken", "userid", "usertoken")
        }
        form["auto_refresh"] = auto_refresh
        result = await hass.config_entries.flow.async_configure(result["flow_id"], form)
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["result"].unique_id == account_id(cloud_data)
        assert result["data"]["account_scope"] is True
        assert "password" not in result["data"]
        assert result["data"]["auto_refresh"] is auto_refresh
        await hass.async_block_till_done()


async def test_password_flow_never_persists_password(hass, cloud_data, setup_mock):
    with patch("custom_components.lifesmart_ulroot.config_flow.CloudClient") as factory:
        client = factory.return_value
        client.credentials = {**cloud_data, "auth_method": "login", "auto_refresh": True}
        client.login = AsyncMock()
        client.stations = AsyncMock(return_value=[Station("station-test", "Station")])
        client.close = AsyncMock()
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "cloud"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "cloud_login"}
        )
        assert "auto_refresh" not in {str(key) for key in result["data_schema"].schema}
        form = {key: cloud_data[key] for key in ("server", "appkey", "apptoken", "userid")}
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**form, "password": "secret-password"}
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert "password" not in result["data"]
        assert result["data"]["auto_refresh"] is True
        assert factory.call_args.args[1]["auto_refresh"] is True
        client.login.assert_awaited_once_with("8123456", "secret-password")
        await hass.async_block_till_done()


async def test_localweb_setup_and_duplicate(hass, config_entry, setup_mock):
    with patch("custom_components.lifesmart_ulroot.config_flow.LocalWebClient") as factory:
        factory.return_value.close = AsyncMock()
        factory.return_value.validate = AsyncMock(return_value=Station("station-test", "Station"))
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "localweb"}
        )
        assert result["description_placeholders"]["email"] == "ss.kim@ulroot.com"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "host": "station.example",
                "protocol": "http",
                "username": "u",
                "password": "p",
            },
        )
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "already_configured"


async def test_multiple_localweb_stations_keep_separate_credentials(hass, setup_mock):
    forms = [
        {"host": "192.0.2.10", "protocol": "http", "username": "local-a", "password": "fixture-a"},
        {"host": "192.0.2.11", "protocol": "http", "username": "local-b", "password": "fixture-b"},
    ]
    with patch("custom_components.lifesmart_ulroot.config_flow.LocalWebClient") as factory:
        factory.return_value.close = AsyncMock()
        factory.return_value.validate = AsyncMock(
            side_effect=[
                Station("station-a", "First station"),
                Station("station-b", "Second station"),
            ]
        )
        for index, form in enumerate(forms):
            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {"next_step_id": "localweb"}
            )
            result = await hass.config_entries.flow.async_configure(result["flow_id"], form)
            assert result["type"] == FlowResultType.CREATE_ENTRY
            assert result["result"].unique_id == ("station-a", "station-b")[index]
            assert all(
                result["data"][key] == value for key, value in form.items() if key != "protocol"
            )
            assert result["data"]["port"] == 8008
            assert result["data"]["use_tls"] is False
            await hass.async_block_till_done()
        entries = hass.config_entries.async_entries(DOMAIN)
        assert len(entries) == 2
        assert entries[0].data["password"] != entries[1].data["password"]


async def test_localweb_auth_error_shows_form(hass):
    with patch("custom_components.lifesmart_ulroot.config_flow.LocalWebClient") as factory:
        factory.return_value.close = AsyncMock()
        factory.return_value.validate = AsyncMock(side_effect=AuthenticationError("secret"))
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "localweb"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"host": "station.example", "protocol": "http", "username": "u", "password": "p"},
        )
        assert result["errors"] == {"base": "invalid_auth"}
        factory.return_value.close.assert_awaited_once()


async def test_http_form_hides_port_and_tls_controls(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "localweb"}
    )
    fields = {str(key) for key in result["data_schema"].schema}
    assert fields == {"host", "protocol", "username", "password"}


@pytest.mark.parametrize("verify_ssl", [True, False])
async def test_https_selects_8080_and_asks_about_certificate(hass, setup_mock, verify_ssl):
    with patch("custom_components.lifesmart_ulroot.config_flow.LocalWebClient") as factory:
        factory.return_value.close = AsyncMock()
        factory.return_value.validate = AsyncMock(return_value=Station("https-station", "Station"))
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "localweb"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"host": "station.example", "protocol": "https", "username": "u", "password": "p"},
        )
        assert result["step_id"] == "localweb_tls"
        factory.assert_not_called()
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"verify_ssl": verify_ssl}
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"]["port"] == 8080
        assert result["data"]["use_tls"] is True
        assert result["data"]["verify_ssl"] is verify_ssl
        assert "protocol" not in result["data"]
        factory.return_value.close.assert_awaited_once()
        await hass.async_block_till_done()


async def test_reconfigure_changes_mode_in_same_entry(hass, config_entry, setup_mock):
    with patch("custom_components.lifesmart_ulroot.config_flow.LocalWebClient") as factory:
        factory.return_value.close = AsyncMock()
        factory.return_value.validate = AsyncMock(return_value=Station("station-test", "Station"))
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "entry_id": config_entry.entry_id,
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "localweb"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"host": "station.example", "protocol": "http", "username": "u", "password": "p"},
        )
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "reconfigure_successful"
        assert config_entry.data["connection_type"] == "localweb"
        assert config_entry.unique_id == "station-test"
        assert "usertoken" not in config_entry.data
        await hass.async_block_till_done()
