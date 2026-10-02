from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory

from .definitions import BLUETOOTH, HARDWARE_ID, bluetooth_state
from .entity import CinebarEntity


async def async_setup_entry(hass, entry, async_add_entities):
    hub = entry.runtime_data
    async_add_entities([CinebarBluetooth(hub, entry), CinebarHardwareId(hub, entry)])


class CinebarBluetooth(CinebarEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["connected", "pairing", "ready", "off"]

    def __init__(self, hub, entry) -> None:
        super().__init__(hub, entry, BLUETOOTH)

    @property
    def native_value(self):
        return bluetooth_state(self.value)

    @property
    def extra_state_attributes(self):
        value = self.value if isinstance(self.value, dict) else {}
        return {"device": value.get("device")}


class CinebarHardwareId(CinebarEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, hub, entry) -> None:
        super().__init__(hub, entry, HARDWARE_ID)

    @property
    def native_value(self):
        return self.value
