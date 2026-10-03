from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory

from .definitions import SWITCHES
from .hub import POWER_KEY
from .zones import POWER_ACTIVE
from .entity import CinebarEntity


async def async_setup_entry(hass, entry, async_add_entities):
    hub = entry.runtime_data
    entities = [CinebarSwitch(hub, entry, key, cfg) for key, (_, cfg) in SWITCHES.items()]
    entities.append(CinebarPower(hub, entry))
    async_add_entities(entities)


class CinebarSwitch(CinebarEntity, SwitchEntity):
    def __init__(self, hub, entry, key, config_category) -> None:
        super().__init__(hub, entry, key)
        if config_category:
            self._attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self):
        return None if self.raw_value is None else bool(self.raw_value)

    async def async_turn_on(self, **kwargs) -> None:
        await self.hub.async_set(self.setting, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.hub.async_set(self.setting, False)


class CinebarPower(CinebarEntity, SwitchEntity):
    """Ein/Aus der Cinebar (Standby) über den Raumfeld-Web-Dienst."""

    def __init__(self, hub, entry) -> None:
        super().__init__(hub, entry, POWER_KEY)

    @property
    def available(self) -> bool:
        return self.raw_value is not None

    @property
    def is_on(self):
        return None if self.raw_value is None else self.raw_value == POWER_ACTIVE

    @property
    def extra_state_attributes(self):
        return {"power_state": self.raw_value}

    async def async_turn_on(self, **kwargs) -> None:
        await self.hub.async_set_power(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.hub.async_set_power(False)
