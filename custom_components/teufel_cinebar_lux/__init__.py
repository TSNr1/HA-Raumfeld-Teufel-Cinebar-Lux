"""Teufel Cinebar Lux – alle Einstellungen der Raumfeld-App in Home Assistant."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .definitions import CONF_HOST, CONF_PLAYER
from .hub import CinebarHub

PLATFORMS = ["select", "switch", "number", "sensor", "binary_sensor"]

type CinebarConfigEntry = ConfigEntry[CinebarHub]


async def async_setup_entry(hass: HomeAssistant, entry: CinebarConfigEntry) -> bool:
    hub = CinebarHub(async_get_clientsession(hass), entry.data[CONF_HOST], entry.data[CONF_PLAYER])
    try:
        await hub.async_start()
    except Exception as err:  # noqa: BLE001
        raise ConfigEntryNotReady(f"Cinebar nicht erreichbar: {err}") from err
    entry.runtime_data = hub
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CinebarConfigEntry) -> bool:
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_stop()
    return unloaded
