"""Resilient connection wrapper for the Monoprice controller."""

from __future__ import annotations

from collections.abc import Callable
import logging
from threading import RLock
import time
from typing import Any, TypeVar

from pymonoprice import get_monoprice
from serial import SerialException

_LOGGER = logging.getLogger(__name__)

_CACHE_SECONDS = 2.0
_RECONNECT_DELAY_SECONDS = 0.25
_RECOVERABLE_ERRORS = (SerialException, OSError, TimeoutError)

_T = TypeVar("_T")


class ResilientMonoprice:
    """Serialize access, cache unit status, and reconnect after transport errors."""

    def __init__(
        self,
        port_url: str,
        client_factory: Callable[[str], Any] = get_monoprice,
    ) -> None:
        self._port_url = port_url
        self._client_factory = client_factory
        self._client: Any | None = None
        self._lock = RLock()
        self._unit_cache: dict[int, tuple[float, dict[int, Any]]] = {}

        # Preserve setup-time connection validation. Runtime failures are handled
        # transparently by _execute().
        self._client = self._client_factory(self._port_url)

    def _close_client(self) -> None:
        """Close and discard the current client without raising."""
        client, self._client = self._client, None
        self._unit_cache.clear()
        if client is None:
            return

        try:
            close = getattr(client, "close", None)
            if callable(close):
                close()
                return

            # pymonoprice 0.5 does not expose close(), but its synchronous client
            # owns a pyserial-compatible port. Close it explicitly so a single-
            # client TCP/RS-232 bridge can immediately accept the replacement.
            serial_port = getattr(client, "_port", None)
            close = getattr(serial_port, "close", None)
            if callable(close):
                close()
        except Exception as err:  # Best-effort cleanup before reconnecting.
            _LOGGER.debug("Error closing Monoprice transport: %s", err)

    def close(self) -> None:
        """Close the active controller connection."""
        with self._lock:
            self._close_client()

    def _execute(self, description: str, operation: Callable[[Any], _T]) -> _T:
        """Execute an operation and retry once with a fresh connection."""
        with self._lock:
            for attempt in range(2):
                try:
                    if self._client is None:
                        self._client = self._client_factory(self._port_url)
                    return operation(self._client)
                except _RECOVERABLE_ERRORS as err:
                    self._close_client()
                    if attempt == 0:
                        _LOGGER.warning(
                            "Monoprice %s failed (%s); reconnecting to %s",
                            description,
                            err,
                            self._port_url,
                        )
                        time.sleep(_RECONNECT_DELAY_SECONDS)
                        continue

                    _LOGGER.error(
                        "Monoprice %s failed after reconnecting to %s: %s",
                        description,
                        self._port_url,
                        err,
                    )
                    raise

        raise RuntimeError("Unreachable Monoprice retry state")

    def _invalidate_zone(self, zone: int) -> None:
        self._unit_cache.pop(zone // 10, None)

    def zone_status(self, zone: int):
        """Return zone status, fetching all six zones in one serial request."""
        unit = zone // 10
        with self._lock:
            cached = self._unit_cache.get(unit)
            if cached is not None and time.monotonic() - cached[0] <= _CACHE_SECONDS:
                return cached[1].get(zone)

            def _read_unit(client):
                statuses = client.all_zone_status(unit)
                if not statuses:
                    raise SerialException(
                        f"No valid status returned for Monoprice unit {unit}"
                    )
                return statuses

            statuses = self._execute(f"unit {unit} status request", _read_unit)
            status_by_zone = {status.zone: status for status in statuses}
            self._unit_cache[unit] = (time.monotonic(), status_by_zone)
            return status_by_zone.get(zone)

    def all_zone_status(self, unit: int):
        """Return all statuses for a unit and refresh the shared cache."""
        with self._lock:
            statuses = self._execute(
                f"unit {unit} status request",
                lambda client: client.all_zone_status(unit),
            )
            self._unit_cache[unit] = (
                time.monotonic(),
                {status.zone: status for status in statuses},
            )
            return statuses

    def _set(self, zone: int, method: str, value: Any) -> None:
        with self._lock:
            self._invalidate_zone(zone)
            self._execute(
                f"{method} for zone {zone}",
                lambda client: getattr(client, method)(zone, value),
            )

    def set_power(self, zone: int, power: bool) -> None:
        self._set(zone, "set_power", power)

    def set_mute(self, zone: int, mute: bool) -> None:
        self._set(zone, "set_mute", mute)

    def set_volume(self, zone: int, volume: int) -> None:
        self._set(zone, "set_volume", volume)

    def set_treble(self, zone: int, treble: int) -> None:
        self._set(zone, "set_treble", treble)

    def set_bass(self, zone: int, bass: int) -> None:
        self._set(zone, "set_bass", bass)

    def set_balance(self, zone: int, balance: int) -> None:
        self._set(zone, "set_balance", balance)

    def set_source(self, zone: int, source: int) -> None:
        self._set(zone, "set_source", source)

    def restore_zone(self, status) -> None:
        """Restore a snapshot, reconnecting and retrying if needed."""
        with self._lock:
            self._invalidate_zone(status.zone)
            self._execute(
                f"restore for zone {status.zone}",
                lambda client: client.restore_zone(status),
            )
