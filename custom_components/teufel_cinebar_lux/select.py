from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory

from .definitions import SELECTS, option_label, option_value
from .entity import CinebarEntity


async def async_setup_entry(hass, entry, async_add_entities):
    hub = entry.runtime_data
    async_add_entities(
        CinebarSelect(hub, entry, key, opts, enabled, cfg) for key, (opts, enabled, cfg) in SELECTS.items()
    )


class CinebarSelect(CinebarEntity, SelectEntity):
    def __init__(self, hub, entry, key, mapping, enabled, config_category) -> None:
        super().__init__(hub, entry, key)
        self._mapping = dict(mapping)
        self._attr_entity_registry_enabled_default = enabled
        if config_category:
            self._attr_entity_category = EntityCategory.CONFIG

    @property
    def options(self) -> list[str]:
        labels = list(self._mapping.values())
        current = option_label(self._mapping, self.raw_value)
        if current and current not in labels:
            labels.append(current)
        return labels

    @property
    def current_option(self) -> str | None:
        return option_label(self._mapping, self.raw_value)

    async def async_select_option(self, option: str) -> None:
        await self.hub.async_set(self.setting, option_value(self._mapping, option))
