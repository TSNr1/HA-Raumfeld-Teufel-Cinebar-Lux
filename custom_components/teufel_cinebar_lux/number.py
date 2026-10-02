from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory

from .definitions import NUMBERS
from .entity import CinebarEntity


async def async_setup_entry(hass, entry, async_add_entities):
    hub = entry.runtime_data
    async_add_entities(CinebarNumber(hub, entry, key, *cfg) for key, cfg in NUMBERS.items())


class CinebarNumber(CinebarEntity, NumberEntity):
    _attr_mode = NumberMode.BOX

    def __init__(self, hub, entry, key, vmin, vmax, step, unit, enabled, config_category) -> None:
        super().__init__(hub, entry, key)
        self._attr_native_min_value = vmin
        self._attr_native_max_value = vmax
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        self._attr_entity_registry_enabled_default = enabled
        if key == "lip_sync":
            self._attr_mode = NumberMode.SLIDER
        if config_category:
            self._attr_entity_category = EntityCategory.CONFIG

    @property
    def native_value(self):
        return self.value

    async def async_set_native_value(self, value: float) -> None:
        await self.hub.async_set(self.setting, int(value))
