"""Verbindung zur Cinebar und Werte-Cache."""
from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import Any

import aiohttp

from .definitions import ALL_SETTINGS
from .wamp import ROOMS_TOPIC, WampClient, device_topic


class CinebarHub:
    """Hält Werte aller Einstellungen und benachrichtigt die Entitäten."""

    def __init__(self, session: aiohttp.ClientSession, host: str, player_uuid: str) -> None:
        self.host = host
        self.player_uuid = player_uuid
        self.client = WampClient(session, host)
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

    async def async_stop(self) -> None:
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

    def _on_value(self, setting: str, value: Any) -> None:
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
