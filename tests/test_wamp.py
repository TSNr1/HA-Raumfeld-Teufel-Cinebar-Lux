"""Test des WAMP-Clients gegen einen minimalen Fake-Host (aiohttp-Server)."""
import asyncio
import importlib.util
import os
import sys
import types
import unittest

import aiohttp
from aiohttp import web

ROOT = os.path.join(os.path.dirname(__file__), "..", "custom_components", "teufel_cinebar_lux")


def load(name):
    pkg = types.ModuleType("cinebar_pkg")
    pkg.__path__ = [ROOT]
    sys.modules.setdefault("cinebar_pkg", pkg)
    spec = importlib.util.spec_from_file_location(f"cinebar_pkg.{name}", os.path.join(ROOT, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"cinebar_pkg.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


wamp = load("wamp")
defs = load("definitions")
UUID = "uuid:81a25d10-e759-42ba-840b-76624e4d00cd"


class FakeHost:
    def __init__(self):
        self.state = {"audio_dynamore": True, "lip_sync": 0}
        self.subs = {}
        self.sets = []
        self.drop_next = False
        self.runner = None
        self.ws = None

    async def handler(self, request):
        ws = web.WebSocketResponse(protocols=(wamp.PROTOCOL,))
        await ws.prepare(request)
        self.ws = ws
        sid = 100
        async for msg in ws:
            d = msg.json()
            if d[0] == 1:
                await ws.send_json([2, 7, {"roles": {"broker": {}}}])
            elif d[0] == 32:
                sid += 1
                self.subs[d[3]] = sid
                await ws.send_json([33, d[1], sid])
            elif d[0] == 48:
                topic, args = d[3], d[4]
                if topic == wamp.ROOMS_TOPIC:
                    await ws.send_json([50, d[1], {}, [{"room1": {"players": {UUID: {"name": "Cinebar", "type": 27}}}}], {}])
                    continue
                key = topic.rsplit(".", 1)[1]
                if key == "kaputt":
                    await ws.send_json([8, 48, d[1], {}, "wamp.error.no_such_procedure"])
                elif args[0] == "get":
                    await ws.send_json([50, d[1], {}, [self.state.get(key)], {}])
                else:
                    self.sets.append((key, args[1]))
                    self.state[key] = args[1]
                    await ws.send_json([50, d[1], {}, [None], {}])
                    await ws.send_json([36, self.subs[topic], 5, {}, [args[1]]])
        return ws

    async def start(self):
        app = web.Application()
        app.router.add_get("/", self.handler)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        return site._server.sockets[0].getsockname()[1]

    async def stop(self):
        await self.runner.cleanup()


class WampTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.host = FakeHost()
        self.port = await self.host.start()
        self.session = aiohttp.ClientSession()

    async def asyncTearDown(self):
        await self.session.close()
        await self.host.stop()

    def test_topic(self):
        self.assertEqual(
            wamp.device_topic(UUID, "lip_sync"),
            "com.raumfeld.devices.uuid_81a25d10_e759_42ba_840b_76624e4d00cd.settings.lip_sync",
        )

    async def test_initial_values_events_and_set(self):
        client = wamp.WampClient(self.session, "127.0.0.1", self.port)
        got = {}
        ev = asyncio.Event()

        def cb(name):
            def f(v):
                got[name] = v
                ev.set()
            return f

        t1 = wamp.device_topic(UUID, "audio_dynamore")
        t2 = wamp.device_topic(UUID, "lip_sync")
        client.subscribe(t1, cb("dyn"))
        client.subscribe(t2, cb("lip"))
        await client.connect()
        for _ in range(50):
            if len(got) == 2:
                break
            await asyncio.sleep(0.05)
        self.assertEqual(got, {"dyn": True, "lip": 0})
        await client.set(t1, False)
        for _ in range(50):
            if got["dyn"] is False:
                break
            await asyncio.sleep(0.05)
        self.assertEqual(self.host.sets, [("audio_dynamore", False)])
        self.assertIs(got["dyn"], False)
        with self.assertRaises(wamp.WampError):
            await client.get("com.raumfeld.devices.x.settings.kaputt")
        await client.close()
        self.assertFalse(client.connected)

    async def test_fetch_once_rooms(self):
        rooms = await wamp.WampClient(self.session, "127.0.0.1", self.port).fetch_once(wamp.ROOMS_TOPIC)
        self.assertEqual(rooms["room1"]["players"][UUID]["type"], defs.CINEBAR_LUX_TYPE)

    async def test_reconnect_resubscribes(self):
        client = wamp.WampClient(self.session, "127.0.0.1", self.port)
        got = []
        client.subscribe(wamp.device_topic(UUID, "lip_sync"), got.append)
        await client.connect()
        for _ in range(50):
            if got:
                break
            await asyncio.sleep(0.05)
        self.host.state["lip_sync"] = 4
        await self.host.ws.close()
        for _ in range(100):
            if 4 in got:
                break
            await asyncio.sleep(0.1)
        self.assertIn(4, got)
        await client.close()


class DefinitionsTest(unittest.TestCase):
    def test_options(self):
        self.assertEqual(defs.option_label(defs.INPUT_SOURCES, 3), "TV")
        self.assertEqual(defs.option_label(defs.INPUT_SOURCES, 9), "Unbekannt (9)")
        self.assertEqual(defs.option_value(defs.INPUT_SOURCES, "HDMI"), 4)
        self.assertEqual(defs.option_value(defs.INPUT_SOURCES, "Unbekannt (9)"), 9)
        self.assertEqual(defs.option_value(defs.SOUND_MODES, "Nacht"), 2)

    def test_bluetooth(self):
        self.assertEqual(defs.bluetooth_state({"connected": False, "device": None, "pairing": False, "ready": True}), "ready")
        self.assertEqual(defs.bluetooth_state({"connected": False, "pairing": True, "ready": True}), "pairing")
        self.assertEqual(defs.bluetooth_state({"connected": True, "pairing": False, "ready": True}), "connected")

    def test_translations_cover_entities(self):
        import json
        for lang in ("de", "en"):
            tr = json.load(open(os.path.join(ROOT, "translations", f"{lang}.json")))["entity"]
            for key in defs.SWITCHES:
                self.assertIn(key, tr["switch"])
            for key in defs.SELECTS:
                self.assertIn(key, tr["select"])
            for key in defs.NUMBERS:
                self.assertIn(key, tr["number"])


if __name__ == "__main__":
    unittest.main()
