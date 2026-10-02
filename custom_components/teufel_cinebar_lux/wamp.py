"""Minimaler WAMP-v2-JSON-Client für den Raumfeld-Host (Port 55555).

Bewusst ohne Home-Assistant-Importe, damit er isoliert getestet werden kann.
Protokoll (aus dem Mitschnitt der Raumfeld-App):
  HELLO     [1, "raumfeld", {...}]            -> WELCOME [2, id, {...}]
  SUBSCRIBE [32, req, {}, topic]              -> SUBSCRIBED [33, req, sub]
  EVENT     [36, sub, pub, {}, [wert]]
  CALL      [48, req, {"timeout":1800}, topic, ["get"] | ["set", wert]]
  RESULT    [50, req, {}, [wert], {}]         | ERROR [8, 48, req, {}, fehler]
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

PROTOCOL = "wamp.2.json"
DEFAULT_PORT = 55555
CALL_TIMEOUT = 15
ROOMS_TOPIC = "com.raumfeld.rooms"

HELLO_DETAILS = {
    "agent": "ha-teufel-cinebar-lux",
    "roles": {
        "subscriber": {},
        "caller": {"features": {"call_timeout": True}},
    },
}


class WampError(Exception):
    """Fehler bei einem WAMP-Aufruf."""


def device_topic(player_uuid: str, setting: str) -> str:
    """Adresse einer Geräteeinstellung, z. B. ...devices.uuid_81a2_....settings.lip_sync."""
    safe = player_uuid.replace(":", "_").replace("-", "_")
    return f"com.raumfeld.devices.{safe}.settings.{setting}"


class WampClient:
    """Hält eine WebSocket-Verbindung, abonniert Themen und ruft Werte ab."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int = DEFAULT_PORT,
    ) -> None:
        self._session = session
        self.host = host
        self.port = port
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._task: asyncio.Task | None = None
        self._req = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._subs: dict[str, Callable[[Any], None]] = {}
        self._sub_ids: dict[int, str] = {}
        self._welcomed: asyncio.Event = asyncio.Event()
        self._stop = False
        self.connected = False
        self._status_cbs: list[Callable[[bool], None]] = []

    # ---- öffentliche API -------------------------------------------------
    def add_status_callback(self, cb: Callable[[bool], None]) -> None:
        self._status_cbs.append(cb)

    async def connect(self) -> None:
        """Erste Verbindung aufbauen (wirft bei Fehler) und Hintergrundschleife starten."""
        await self._open()
        self._task = asyncio.create_task(self._run(first=True))

    async def close(self) -> None:
        self._stop = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        self._set_connected(False)

    async def call(self, topic: str, *args: Any) -> Any:
        """CALL ausführen und den ersten Ergebniswert liefern."""
        ws = self._ws
        if ws is None or ws.closed:
            raise WampError("nicht verbunden")
        self._req += 1
        req = self._req
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[req] = fut
        await ws.send_json([48, req, {"timeout": 1800}, topic, list(args)])
        try:
            return await asyncio.wait_for(fut, CALL_TIMEOUT)
        except asyncio.TimeoutError as err:
            raise WampError(f"Zeitüberschreitung bei {topic}") from err
        finally:
            self._pending.pop(req, None)

    async def fetch_once(self, topic: str) -> Any:
        """Kurz verbinden, einen Wert lesen und wieder trennen (z. B. im Config-Flow)."""
        await self._open()
        reader = asyncio.create_task(self._read_loop())
        try:
            return await self.get(topic)
        finally:
            reader.cancel()
            if self._ws is not None and not self._ws.closed:
                await self._ws.close()
            self._set_connected(False)

    async def get(self, topic: str) -> Any:
        return await self.call(topic, "get")

    async def set(self, topic: str, value: Any) -> Any:
        return await self.call(topic, "set", value)

    def subscribe(self, topic: str, callback: Callable[[Any], None]) -> None:
        """Thema merken; wird bei jeder (Wieder-)Verbindung abonniert."""
        self._subs[topic] = callback

    async def subscribe_now(self, topic: str, callback: Callable[[Any], None]) -> None:
        self._subs[topic] = callback
        if self.connected:
            await self._send_subscribe(topic)

    # ---- intern ----------------------------------------------------------
    def _set_connected(self, state: bool) -> None:
        if self.connected != state:
            self.connected = state
            for cb in list(self._status_cbs):
                try:
                    cb(state)
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Status-Callback fehlgeschlagen")

    async def _open(self) -> None:
        url = f"ws://{self.host}:{self.port}/"
        self._welcomed = asyncio.Event()
        self._ws = await self._session.ws_connect(
            url,
            protocols=(PROTOCOL,),
            heartbeat=30,
            headers={"Origin": f"http://{self.host}:47365"},
        )
        await self._ws.send_json([1, "raumfeld", HELLO_DETAILS])
        msg = await asyncio.wait_for(self._ws.receive_json(), CALL_TIMEOUT)
        if not msg or msg[0] != 2:
            raise WampError(f"Unerwartete Antwort auf HELLO: {msg}")
        self._set_connected(True)

    async def _send_subscribe(self, topic: str) -> None:
        ws = self._ws
        if ws is None or ws.closed:
            return
        self._req += 1
        req = self._req
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[req] = fut
        await ws.send_json([32, req, {}, topic])
        try:
            sub_id = await asyncio.wait_for(fut, CALL_TIMEOUT)
            self._sub_ids[int(sub_id)] = topic
        finally:
            self._pending.pop(req, None)

    async def _resubscribe(self) -> None:
        self._sub_ids.clear()
        for topic in list(self._subs):
            try:
                await self._send_subscribe(topic)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Abonnieren von %s fehlgeschlagen: %s", topic, err)
        # aktuelle Werte holen
        for topic, cb in list(self._subs.items()):
            try:
                cb(await self.get(topic))
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Lesen von %s fehlgeschlagen: %s", topic, err)

    async def _run(self, first: bool = False) -> None:
        delay = 2
        while not self._stop:
            try:
                if not first:
                    await self._open()
                reader = asyncio.create_task(self._read_loop())
                await self._resubscribe()
                first = False
                delay = 2
                await reader
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Verbindung zur Cinebar unterbrochen: %s", err)
            self._set_connected(False)
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(WampError("Verbindung getrennt"))
            if self._stop:
                return
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)
            first = False

    async def _read_loop(self) -> None:
        ws = self._ws
        assert ws is not None
        async for msg in ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
                continue
            try:
                self._handle(msg.json())
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Nachricht nicht verarbeitbar: %s", msg.data)

    def _handle(self, data: list) -> None:
        kind = data[0]
        if kind == 33:  # SUBSCRIBED
            self._resolve(data[1], data[2])
        elif kind == 50:  # RESULT
            args = data[3] if len(data) > 3 else []
            self._resolve(data[1], args[0] if args else None)
        elif kind == 8:  # ERROR [8, request_type, request, details, error, ...]
            fut = self._pending.get(data[2])
            if fut and not fut.done():
                fut.set_exception(WampError(str(data[4:])))
        elif kind == 36:  # EVENT
            topic = self._sub_ids.get(data[1])
            cb = self._subs.get(topic) if topic else None
            if cb:
                args = data[4] if len(data) > 4 else []
                cb(args[0] if args else None)

    def _resolve(self, req: int, value: Any) -> None:
        fut = self._pending.get(req)
        if fut and not fut.done():
            fut.set_result(value)
