"""Test des UPnP-Clients gegen einen minimalen Fake-Host."""
import importlib.util
import os
import sys
import types
import unittest

import aiohttp
from aiohttp import web

ROOT = os.path.join(os.path.dirname(__file__), "..", "custom_components", "teufel_cinebar_lux")


def load(name):
    pkg = sys.modules.get("cinebar_pkg") or types.ModuleType("cinebar_pkg")
    pkg.__path__ = [ROOT]
    sys.modules["cinebar_pkg"] = pkg
    spec = importlib.util.spec_from_file_location(f"cinebar_pkg.{name}", os.path.join(ROOT, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"cinebar_pkg.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


up = load("upnp")
UUID = "uuid:81a25d10-e759-42ba-840b-76624e4d00cd"
DIDL = (
    '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" xmlns:dc="http://purl.org/dc/elements/1.1/" '
    'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
    '<container id="0/Radio" parentID="0" restricted="1"><dc:title>Radio</dc:title>'
    "<upnp:class>object.container</upnp:class></container>"
    '<item id="0/Radio/1" parentID="0/Radio" restricted="1"><dc:title>Sender Eins</dc:title>'
    "<upnp:artist>Künstler</upnp:artist><upnp:albumArtURI>http://x/a.png</upnp:albumArtURI>"
    "<upnp:class>object.item.audioItem.audioBroadcast</upnp:class>"
    '<res protocolInfo="http-get:*:audio/aac:*">http://stream.example/eins</res></item></DIDL-Lite>'
)


def soap(service, action, **vals):
    body = "".join(f"<{k}>{v}</{k}>" for k, v in vals.items())
    return (
        '<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
        f'<s:Body><u:{action}Response xmlns:u="{service}">{body}</u:{action}Response></s:Body></s:Envelope>'
    )


class FakeHost:
    def __init__(self):
        self.calls = []
        self.volume = 12

    async def start(self):
        app = web.Application()
        app.router.add_get("/listDevices", self.list_devices)
        app.router.add_get("/desc.xml", self.desc)
        app.router.add_get("/ms.xml", self.ms)
        app.router.add_post("/{svc}/ctrl", self.ctrl)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self):
        await self.runner.cleanup()

    async def list_devices(self, request):
        base = f"http://127.0.0.1:{self.port}"
        return web.Response(
            text="<?xml version='1.0'?><devices>"
            f"<device udn='{UUID}' type='urn:schemas-upnp-org:device:MediaRenderer:1' location='{base}/desc.xml'>R</device>"
            f"<device udn='uuid:ms' type='urn:schemas-upnp-org:device:MediaServer:1' location='{base}/ms.xml'>M</device>"
            "</devices>"
        )

    def _desc(self, services):
        items = "".join(
            f"<service><serviceType>{t}</serviceType><controlURL>{c}</controlURL></service>" for t, c in services
        )
        return (
            '<?xml version="1.0"?><root xmlns="urn:schemas-upnp-org:device-1-0"><device><serviceList>'
            f"{items}</serviceList></device></root>"
        )

    async def desc(self, request):
        return web.Response(text=self._desc([(up.AVT, "/AVT/ctrl"), (up.RCS, "/RC/ctrl")]))

    async def ms(self, request):
        return web.Response(text=self._desc([(up.CDS, "/CD/ctrl")]))

    async def ctrl(self, request):
        action = request.headers["SOAPACTION"].strip('"')
        service, name = action.split("#")
        body = await request.text()
        self.calls.append((name, body))
        if name == "GetVolume":
            return web.Response(text=soap(service, name, CurrentVolume=self.volume))
        if name == "SetVolume":
            self.volume = int(body.split("<DesiredVolume>")[1].split("<")[0])
            return web.Response(text=soap(service, name))
        if name == "GetMute":
            return web.Response(text=soap(service, name, CurrentMute=0))
        if name == "GetTransportInfo":
            return web.Response(text=soap(service, name, CurrentTransportState="PLAYING"))
        if name == "GetPositionInfo":
            return web.Response(text=soap(service, name, TrackDuration="0:03:25", RelTime="0:00:10", TrackURI="x"))
        if name == "Browse":
            from xml.sax.saxutils import escape

            return web.Response(text=soap(service, name, Result=escape(DIDL), NumberReturned=2))
        if name == "Next":
            fault = (
                '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><s:Fault>'
                "<faultstring>UPnPError</faultstring><detail><UPnPError xmlns=\"urn:schemas-upnp-org:control-1-0\">"
                "<errorCode>701</errorCode><errorDescription>Transition not available</errorDescription>"
                "</UPnPError></detail></s:Fault></s:Body></s:Envelope>"
            )
            return web.Response(text=fault, status=500)
        return web.Response(text=soap(service, name))


class UpnpTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.host = FakeHost()
        self.port = await self.host.start()
        self.session = aiohttp.ClientSession()
        self.client = up.UpnpClient(self.session, "127.0.0.1", UUID, webservice_port=self.port)

    async def asyncTearDown(self):
        await self.session.close()
        await self.host.stop()

    async def test_volume_and_transport(self):
        self.assertEqual(await self.client.get_volume(), 12)
        await self.client.set_volume(40)
        self.assertEqual(self.host.volume, 40)
        await self.client.set_volume(500)  # wird auf 100 begrenzt
        self.assertEqual(self.host.volume, 100)
        self.assertFalse(await self.client.get_mute())
        self.assertEqual(await self.client.transport_info(), "PLAYING")
        info = await self.client.position_info()
        self.assertEqual(up.parse_time(info["TrackDuration"]), 205)

    async def test_set_uri_escapes_metadata(self):
        await self.client.set_uri("http://x/y.mp3?a=1&b=2", up.build_didl("http://x/y.mp3?a=1&b=2", "Ansage & Test"))
        name, body = self.host.calls[-1]
        self.assertEqual(name, "SetAVTransportURI")
        self.assertIn("a=1&amp;b=2", body)
        self.assertIn("&lt;DIDL-Lite", body)

    async def test_fault_raises(self):
        with self.assertRaises(up.UpnpError) as ctx:
            await self.client.next()
        self.assertIn("701", str(ctx.exception))

    async def test_browse(self):
        items = await self.client.browse("0")
        self.assertEqual([i["kind"] for i in items], ["container", "item"])
        self.assertEqual(items[1]["title"], "Sender Eins")
        self.assertEqual(items[1]["uri"], "http://stream.example/eins")
        self.assertEqual(items[1]["artist"], "Künstler")


class UpnpHelpersTest(unittest.TestCase):
    def test_time(self):
        self.assertEqual(up.parse_time("0:03:25"), 205)
        self.assertEqual(up.parse_time("1:00:00.500"), 3600)
        self.assertIsNone(up.parse_time("NOT_IMPLEMENTED"))
        self.assertIsNone(up.parse_time(None))
        self.assertEqual(up.format_time(3725), "1:02:05")

    def test_envelope(self):
        env = up.build_envelope(up.AVT, "SetAVTransportURI", {"CurrentURI": "http://a?x=1&y=2"})
        self.assertIn("x=1&amp;y=2", env)
        self.assertIn(f'xmlns:u="{up.AVT}"', env)

    def test_list_devices_and_description(self):
        xml = (
            "<devices><device udn='uuid:a' type='t' location='http://h:1/a.xml'>Name</device></devices>"
        )
        self.assertEqual(up.parse_list_devices(xml)["uuid:a"]["location"], "http://h:1/a.xml")
        desc = (
            '<root xmlns="urn:schemas-upnp-org:device-1-0"><device><serviceList><service>'
            f"<serviceType>{up.AVT}</serviceType><controlURL>/AVTransport/ctrl</controlURL></service>"
            "</serviceList></device></root>"
        )
        self.assertEqual(up.parse_description(desc, "http://h:1/a.xml")[up.AVT], "http://h:1/AVTransport/ctrl")

    def test_didl_broken(self):
        self.assertEqual(up.parse_didl(""), [])
        self.assertEqual(up.parse_didl("NOT_IMPLEMENTED"), [])
        self.assertEqual(up.parse_didl("<DIDL-Lite"), [])


if __name__ == "__main__":
    unittest.main()
