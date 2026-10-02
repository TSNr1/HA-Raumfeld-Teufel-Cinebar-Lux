from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory

from .definitions import EXTERNAL_SPEAKER_KEYS, EXTERNAL_SPEAKERS
from .entity import CinebarEntity


async def async_setup_entry(hass, entry, async_add_entities):
    hub = entry.runtime_data
    entities = [CinebarConnection(hub, entry)]
    entities += [CinebarExternalSpeaker(hub, entry, raw, key) for raw, key in EXTERNAL_SPEAKER_KEYS.items()]
    async_add_entities(entities)


class CinebarConnection(CinebarEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hub, entry) -> None:
        super().__init__(hub, entry, "connection")
        self._attr_translation_key = "connection"

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.hub.available

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.hub.add_status_listener(self.async_write_ha_state))


class CinebarExternalSpeaker(CinebarEntity, BinarySensorEntity):
    """Zeigt, welche externen Lautsprecher (Subwoofer/Rears) gekoppelt sind."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hub, entry, raw: str, key: str) -> None:
        super().__init__(hub, entry, EXTERNAL_SPEAKERS)
        self._raw = raw
        self._attr_unique_id = f"{hub.player_uuid}_external_{key}"
        self._attr_translation_key = f"external_{key}"

    @property
    def available(self) -> bool:
        return self.hub.available and isinstance(self.raw_value, dict)

    @property
    def is_on(self):
        return bool(self.raw_value.get(self._raw)) if isinstance(self.raw_value, dict) else None
