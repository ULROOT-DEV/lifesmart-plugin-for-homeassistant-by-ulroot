"""Device identity, display values, ordering and capability interpretation."""

from dataclasses import replace

import pytest

from custom_components.lifesmart_ulroot.devices import binary_value, capabilities
from custom_components.lifesmart_ulroot.entity import identity
from custom_components.lifesmart_ulroot.models import (
    Channel,
    merge_event,
    number,
    parse_devices,
    reconcile_snapshot,
)


@pytest.mark.parametrize("value", [True, False, "10", float("nan"), float("inf"), None])
def test_invalid_numbers(value):
    assert number(value) is None


def test_values_zero_negative_and_display_not_scaled_twice():
    assert Channel(raw=202, display=20.2).value(0.1) == 20.2
    assert Channel(raw=-50).value(0.1) == -5
    assert Channel(raw=100, display=0).value(0.1) == 0


def test_capabilities_group_by_product_not_arbitrary_idx(device_payload):
    devices = parse_devices(device_payload, "station-test", 1)
    assert len(capabilities(devices["env-test"])) == 3
    assert [c.platform for c in capabilities(devices["light-test"])] == ["light"]
    assert [c.platform for c in capabilities(devices["air-test"])] == ["climate"]
    assert capabilities(replace(devices["relay-test"], model="UNKNOWN")) == []


def test_station_filter_and_collision_free_ids(device_payload):
    assert parse_devices(device_payload, "other-station", 1) == {}
    assert identity("a:b", "c", "d") != identity("a", "b:c", "d")


def test_partial_push_invalidates_old_display_and_ignores_old_timestamp(device_payload):
    current = parse_devices(device_payload, "station-test", 1)
    event = {"agt": "station-test", "me": "env-test", "idx": "T", "val": 210, "ts": 11}
    updated = merge_event(current, event, 3)
    assert updated["env-test"].channels["T"].value(0.1) == 21
    assert updated["env-test"].channels["H"] == current["env-test"].channels["H"]
    assert (
        merge_event(updated, {**event, "val": 999, "ts": 9}, 4)["env-test"].channels["T"].raw == 210
    )


def test_slow_snapshot_does_not_undo_new_push(device_payload):
    current = parse_devices(device_payload, "station-test", 1)
    changed = merge_event(
        current, {"agt": "station-test", "me": "env-test", "idx": "T", "val": 220, "ts": 12}, 3
    )
    snapshot = parse_devices(device_payload, "station-test", 4)
    merged = reconcile_snapshot(snapshot, changed, started=2)
    assert merged["env-test"].channels["T"].raw == 220


def test_foreign_event_does_not_update_station(device_payload):
    current = parse_devices(device_payload, "station-test", 1)
    assert (
        merge_event(current, {"agt": "foreign", "me": "env-test", "idx": "T", "val": 900}, 2)
        is current
    )


def test_binary_polarity_and_type_rules():
    assert binary_value(Channel(raw=0), "inverted") is True
    assert binary_value(Channel(raw=1), "inverted") is False
    assert binary_value(Channel(raw=0, raw_type=1), "type") is True
    assert binary_value(Channel(raw=7), "val") is None
    assert binary_value(None, "val") is None
