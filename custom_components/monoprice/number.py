"""Number entities for Monoprice tone controls (Bass/Treble)."""

from __future__ import annotations

import logging
from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.components.number import NumberEntity
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DOMAIN,
    FIRST_RUN,
    MONOPRICE_OBJECT,
    CONF_UNITS,
    DEFAULT_UNITS,
)

_LOGGER = logging.getLogger(__name__)

# Per Monoprice protocol manual: 00-14
TONE_MIN: Final[int] = 0
TONE_MAX: Final[int] = 14
TONE_STEP: Final[int] = 1


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Monoprice Bass/Treble number entities."""
    monoprice = hass.data[DOMAIN][config_entry.entry_id][MONOPRICE_OBJECT]

    units = config_entry.options.get(
        CONF_UNITS, config_entry.data.get(CONF_UNITS, DEFAULT_UNITS)
    )

    entities: list[MonopriceToneNumber] = []
    for i in range(1, units + 1):
        for j in range(1, 7):
            zone_id = (i * 10) + j
            entities.append(
                MonopriceToneNumber(
                    monoprice=monoprice,
                    namespace=config_entry.entry_id,
                    zone_id=zone_id,
                    kind="bass",
                )
            )
            entities.append(
                MonopriceToneNumber(
                    monoprice=monoprice,
                    namespace=config_entry.entry_id,
                    zone_id=zone_id,
                    kind="treble",
                )
            )

    # Mirror media_player behavior: only do an initial update on first run
    first_run = hass.data[DOMAIN][config_entry.entry_id][FIRST_RUN]
    async_add_entities(entities, first_run)


class MonopriceToneNumber(NumberEntity, RestoreEntity):
    """Bass or Treble control for a specific Monoprice zone."""

    _attr_has_entity_name = True
    _attr_native_min_value = TONE_MIN
    _attr_native_max_value = TONE_MAX
    _attr_native_step = TONE_STEP
    # Tone is rarely changed and setters update state optimistically. Avoid two
    # extra zone-status requests per zone during every polling cycle.
    _attr_should_poll = False

    def __init__(self, monoprice, namespace: str, zone_id: int, kind: str) -> None:
        self._monoprice = monoprice
        self._namespace = namespace
        self._zone_id = zone_id
        self._kind = kind  # "bass" or "treble"

        # Make these entities belong to the same device as the zone media_player:
        # media_player uses unique_id = f"{namespace}_{zone_id}" and identifiers={(DOMAIN, unique_id)}
        zone_unique = f"{namespace}_{zone_id}"

        self._attr_unique_id = f"{zone_unique}_{kind}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, zone_unique)},
            manufacturer="Monoprice",
            model="6-Zone Amplifier",
            name=f"Zone {zone_id}",
        )

        if kind == "bass":
            self._attr_name = "Bass"
            self._setter = "set_bass"
            self._getter_attr = "bass"
        else:
            self._attr_name = "Treble"
            self._setter = "set_treble"
            self._getter_attr = "treble"

        # We’ll try to read from zone_status when updated, but we also restore the last slider value
        # so you get a usable UI even if polling is slow/unavailable.
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        """Restore last known UI value on restart."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state not in (None, "unknown", "unavailable"):
            try:
                self._attr_native_value = int(float(last.state))
            except ValueError:
                pass

    async def async_update(self) -> None:
        """Read current bass/treble from the device (best effort)."""
        try:
            status = await self.hass.async_add_executor_job(
                self._monoprice.zone_status, self._zone_id
            )
        except Exception as err:  # device/transport errors
            _LOGGER.debug("Tone update failed for zone %s (%s): %s", self._zone_id, self._kind, err)
            return

        if not status:
            return

        value = getattr(status, self._getter_attr, None)
        if value is None:
            return

        try:
            self._attr_native_value = int(value)
        except (TypeError, ValueError):
            return

    async def async_set_native_value(self, value: float) -> None:
        """Set bass/treble on the device."""
        ivalue = int(round(value))
        ivalue = max(TONE_MIN, min(TONE_MAX, ivalue))

        setter = getattr(self._monoprice, self._setter, None)
        if setter is None:
            _LOGGER.error("pymonoprice object has no %s method", self._setter)
            return

        await self.hass.async_add_executor_job(setter, self._zone_id, ivalue)

        # Optimistic UI update
        self._attr_native_value = ivalue
        self.async_write_ha_state()
