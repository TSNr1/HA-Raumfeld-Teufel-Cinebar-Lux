"""Verbindung zur Cinebar und Werte-Cache."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from functools import partial
from typing import Any

import aiohttp

from .definitions import ALL_SETTINGS
from .upnp import UpnpClient
from .zones import WEBSERVICE_PORT, parse_power_state, standby_path
from .wamp import ROOMS_TOPIC, WampClient, device_topic


_LOGGER = logging.getLogger(__name__)
POWER_POLL_SECONDS = 20
POWER_KEY = "power_state"


class CinebarHub:
    """Hält Werte aller Einstellungen und benachrichtigt die Entitäten."""

    def __init__(self, session: aiohttp.ClientSession, host: str, player_uuid: str) -> None:
        self.host = host
        self.player_uuid = player_uuid
        self._session = session
        self.client = WampClient(session, host)
        self.upnp = UpnpClient(session, host, player_uuid)
        self.room_udn: str | None = None
        self._power_task: asyncio.Task | None = None
        self.values: dict[str, Any] = {}
        self._listeners: dict[str, list[Callable[[], None]]] = {}
        self._status_listeners: list[Callable[[], None]] = []
        self.client.add_status_callback(self._on_status)

    @property
    def available(self) -> bool:
        return self.client.connected

    def topic(self, setting: str) -> str:
        return device_topic(self.player_uuid, setting)

    async def async_start(self) -> None:
        for setting in ALL_SETTINGS:
            self.client.subscribe(self.topic(setting), partial(self._on_value, setting))
        await self.client.connect()
        await self.async_update_power()
        self._power_task = asyncio.create_task(self._power_loop())

    async def async_stop(self) -> None:
        if self._power_task:
            self._power_task.cancel()
        await self.client.close()

    def add_listener(self, setting: str, cb: Callable[[], None]) -> Callable[[], None]:
        self._listeners.setdefault(setting, []).append(cb)
        return lambda: self._listeners[setting].remove(cb)

    def add_status_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._status_listeners.append(cb)
        return lambda: self._status_listeners.remove(cb)

    async def async_set(self, setting: str, value: Any) -> None:
        await self.client.set(self.topic(setting), value)
        self._on_value(setting, value)

    async def _power_loop(self) -> None:
        while True:
            await asyncio.sleep(POWER_POLL_SECONDS)
            await self.async_update_power()

    async def async_update_power(self) -> None:
        """Betriebszustand des Raums über den Web-Dienst des Hosts lesen."""
        try:
            async with self._session.get(
                f"http://{self.host}:{WEBSERVICE_PORT}/getZones", timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                text = await resp.text()
            self.room_udn, state = parse_power_state(text, self.player_uuid)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Betriebszustand nicht lesbar: %s", err)
            state = None
        self._on_value(POWER_KEY, state)

    async def async_set_power(self, on: bool) -> None:
        if self.room_udn is None:
            await self.async_update_power()
        if self.room_udn is None:
            raise RuntimeError("Raum der Cinebar nicht gefunden")
        async with self._session.get(
            f"http://{self.host}:{WEBSERVICE_PORT}{standby_path(on)}",
            params={"roomUDN": self.room_udn},
            timeout=aiohttp.ClientTimeout(total=10),
        ):
            pass
        await asyncio.sleep(2)
        await self.async_update_power()

    def _on_value(self, setting: str, value: Any) -> None:
        if setting in self.values and self.values[setting] == value:
            return
        self.values[setting] = value
        for cb in list(self._listeners.get(setting, [])):
            cb()

    def _on_status(self, _state: bool) -> None:
        for cb in list(self._status_listeners):
            cb()
        for cbs in list(self._listeners.values()):
            for cb in list(cbs):
                cb()


async def async_list_players(session: aiohttp.ClientSession, host: str) -> dict[str, dict]:
    """Alle Player (uuid -> {name, type}) des Raumfeld-Hosts auslesen."""
    rooms = await WampClient(session, host).fetch_once(ROOMS_TOPIC)
    players: dict[str, dict] = {}
    for room_data in (rooms or {}).values():
        for uuid, info in room_data.get("players", {}).items():
            players[uuid] = {"name": info.get("name", uuid), "type": info.get("type")}
    return players
