"""Gemeinsame Basis aller Entitäten."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .definitions import CONF_NAME, DOMAIN
from .hub import CinebarHub


class CinebarEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hub: CinebarHub, entry, setting: str) -> None:
        self.hub = hub
        self.setting = setting
        self._attr_translation_key = setting.replace(".", "_")
        self._attr_unique_id = f"{hub.player_uuid}_{setting}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, hub.player_uuid)},
            name=entry.data.get(CONF_NAME, "Cinebar Lux"),
            manufacturer="Teufel",
            model="Cinebar Lux",
            configuration_url=f"http://{hub.host}:47365/",
        )

    @property
    def available(self) -> bool:
        return self.hub.available and self.value is not None

    @property
    def value(self):
        return self.hub.values.get(self.setting)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.hub.add_listener(self.setting, self.async_write_ha_state))
