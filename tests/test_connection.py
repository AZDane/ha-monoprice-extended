"""Tests for the resilient Monoprice transport wrapper."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from pathlib import Path
import sys
import types
import unittest


class FakeSerialException(Exception):
    """Stand-in for pyserial's transport exception."""


def _load_connection_module():
    pymonoprice = types.ModuleType("pymonoprice")
    pymonoprice.get_monoprice = lambda _port: None
    serial = types.ModuleType("serial")
    serial.SerialException = FakeSerialException
    sys.modules["pymonoprice"] = pymonoprice
    sys.modules["serial"] = serial

    path = (
        Path(__file__).parents[1]
        / "custom_components"
        / "monoprice"
        / "connection.py"
    )
    spec = importlib.util.spec_from_file_location("monoprice_connection_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._RECONNECT_DELAY_SECONDS = 0
    return module


connection = _load_connection_module()


@dataclass
class FakeStatus:
    zone: int


class FakePort:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeClient:
    def __init__(self, *, fail_reads: int = 0, empty_reads: int = 0) -> None:
        self._port = FakePort()
        self.fail_reads = fail_reads
        self.empty_reads = empty_reads
        self.status_calls = 0
        self.power_calls: list[tuple[int, bool]] = []

    def all_zone_status(self, unit: int):
        self.status_calls += 1
        if self.fail_reads:
            self.fail_reads -= 1
            raise FakeSerialException("dead socket")
        if self.empty_reads:
            self.empty_reads -= 1
            return []
        return [FakeStatus((unit * 10) + zone) for zone in range(1, 7)]

    def set_power(self, zone: int, power: bool) -> None:
        self.power_calls.append((zone, power))


class ClientFactory:
    def __init__(self, clients: list[FakeClient]) -> None:
        self.clients = clients
        self.calls = 0

    def __call__(self, _port: str) -> FakeClient:
        client = self.clients[self.calls]
        self.calls += 1
        return client


class ResilientMonopriceTests(unittest.TestCase):
    def test_reconnects_and_retries_after_socket_failure(self) -> None:
        first = FakeClient(fail_reads=1)
        second = FakeClient()
        factory = ClientFactory([first, second])
        hub = connection.ResilientMonoprice("socket://example:8235", factory)

        self.assertEqual(11, hub.zone_status(11).zone)
        self.assertEqual(2, factory.calls)
        self.assertTrue(first._port.closed)
        self.assertEqual(1, second.status_calls)

    def test_empty_status_response_also_reconnects(self) -> None:
        first = FakeClient(empty_reads=1)
        second = FakeClient()
        factory = ClientFactory([first, second])
        hub = connection.ResilientMonoprice("socket://example:8235", factory)

        self.assertEqual(12, hub.zone_status(12).zone)
        self.assertEqual(2, factory.calls)
        self.assertTrue(first._port.closed)

    def test_one_unit_read_serves_all_zone_entities(self) -> None:
        client = FakeClient()
        hub = connection.ResilientMonoprice(
            "socket://example:8235", ClientFactory([client])
        )

        self.assertEqual(11, hub.zone_status(11).zone)
        self.assertEqual(16, hub.zone_status(16).zone)
        self.assertEqual(1, client.status_calls)

    def test_write_invalidates_cached_status(self) -> None:
        client = FakeClient()
        hub = connection.ResilientMonoprice(
            "socket://example:8235", ClientFactory([client])
        )

        hub.zone_status(11)
        hub.set_power(11, True)
        hub.zone_status(11)

        self.assertEqual([(11, True)], client.power_calls)
        self.assertEqual(2, client.status_calls)

    def test_close_releases_serial_socket(self) -> None:
        client = FakeClient()
        hub = connection.ResilientMonoprice(
            "socket://example:8235", ClientFactory([client])
        )

        hub.close()

        self.assertTrue(client._port.closed)


if __name__ == "__main__":
    unittest.main()
