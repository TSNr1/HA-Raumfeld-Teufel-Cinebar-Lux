from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory

from .definitions import SWITCHES
from .entity import CinebarEntity


async def async_setup_entry(hass, entry, async_add_entities):
    hub = entry.runtime_data
    async_add_entities(CinebarSwitch(hub, entry, key, cfg) for key, (_, cfg) in SWITCHES.items())


class CinebarSwitch(CinebarEntity, SwitchEntity):
    def __init__(self, hub, entry, key, config_category) -> None:
        super().__init__(hub, entry, key)
        if config_category:
            self._attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self):
        return None if self.value is None else bool(self.value)

    async def async_turn_on(self, **kwargs) -> None:
        await self.hub.async_set(self.setting, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.hub.async_set(self.setting, False)
