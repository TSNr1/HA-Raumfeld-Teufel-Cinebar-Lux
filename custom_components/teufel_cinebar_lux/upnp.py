"""Standard-UPnP-Zugriff auf den Renderer der Cinebar und den Raumfeld-MediaServer.

Eigenentwicklung nach der offenen UPnP-AV-Spezifikation (SOAP über HTTP). Ohne Home-Assistant-Importe.
"""
from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from urllib.parse import urljoin
from xml.sax.saxutils import escape

import aiohttp

WEBSERVICE_PORT = 47365
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
DEVICE_NS = "{urn:schemas-upnp-org:device-1-0}"
DIDL_NS = "{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}"
DC_NS = "{http://purl.org/dc/elements/1.1/}"
UPNP_NS = "{urn:schemas-upnp-org:metadata-1-0/upnp/}"
AVT = "urn:schemas-upnp-org:service:AVTransport:1"
RCS = "urn:schemas-upnp-org:service:RenderingControl:1"
CDS = "urn:schemas-upnp-org:service:ContentDirectory:1"
REQUEST_TIMEOUT = 10

STATE_PLAYING = "PLAYING"
STATE_PAUSED = "PAUSED_PLAYBACK"
STATE_STOPPED = "STOPPED"
STATE_TRANSITIONING = "TRANSITIONING"
STATE_NO_MEDIA = "NO_MEDIA_PRESENT"


class UpnpError(Exception):
    """Fehler bei einem UPnP-Aufruf."""


# ---- reine Hilfsfunktionen (gut testbar) ------------------------------------
def build_envelope(service_type: str, action: str, args: dict[str, object]) -> str:
    body = "".join(f"<{k}>{escape(str(v))}</{k}>" for k, v in args.items())
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<s:Envelope xmlns:s="{SOAP_NS}" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        f'<s:Body><u:{action} xmlns:u="{service_type}">{body}</u:{action}></s:Body></s:Envelope>'
    )


def parse_response(text: str) -> dict[str, str]:
    root = ET.fromstring(text)
    body = root.find(f"{{{SOAP_NS}}}Body")
    if body is None or len(body) == 0:
        raise UpnpError("leere SOAP-Antwort")
    first = body[0]
    if first.tag == f"{{{SOAP_NS}}}Fault":
        code = first.findtext(".//{urn:schemas-upnp-org:control-1-0}errorCode") or first.findtext("faultstring") or "?"
        desc = first.findtext(".//{urn:schemas-upnp-org:control-1-0}errorDescription") or ""
        raise UpnpError(f"UPnP-Fehler {code} {desc}".strip())
    return {child.tag.split("}")[-1]: (child.text or "") for child in first}


def parse_time(value: str | None) -> int | None:
    """'H:MM:SS(.fff)' -> Sekunden; alles andere (z. B. NOT_IMPLEMENTED) -> None."""
    if not value or ":" not in value:
        return None
    try:
        parts = value.split(".")[0].split(":")
        h, m, s = (int(p) for p in parts[-3:])
        return h * 3600 + m * 60 + s
    except ValueError:
        return None


def format_time(seconds: int) -> str:
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def parse_list_devices(xml_text: str) -> dict[str, dict[str, str]]:
    """/listDevices -> {udn: {type, location, name}}."""
    root = ET.fromstring(xml_text)
    return {
        d.get("udn", ""): {"type": d.get("type", ""), "location": d.get("location", ""), "name": (d.text or "").strip()}
        for d in root.iter("device")
    }


def parse_description(xml_text: str, location: str) -> dict[str, str]:
    """Gerätebeschreibung -> {serviceType: absolute controlURL}."""
    root = ET.fromstring(xml_text)
    services: dict[str, str] = {}
    for svc in root.iter(f"{DEVICE_NS}service"):
        stype = svc.findtext(f"{DEVICE_NS}serviceType")
        ctrl = svc.findtext(f"{DEVICE_NS}controlURL")
        if stype and ctrl:
            services[stype] = urljoin(location, ctrl)
    return services


def parse_didl(didl: str | None) -> list[dict]:
    """DIDL-Lite -> Liste von Einträgen (Container und Items)."""
    if not didl or not didl.strip().startswith("<"):
        return []
    try:
        root = ET.fromstring(didl)
    except ET.ParseError:
        return []
    out = []
    for node in root:
        kind = "container" if node.tag == f"{DIDL_NS}container" else "item"
        res = node.find(f"{DIDL_NS}res")
        out.append(
            {
                "kind": kind,
                "id": node.get("id", ""),
                "parent": node.get("parentID", ""),
                "title": node.findtext(f"{DC_NS}title") or "",
                "artist": node.findtext(f"{UPNP_NS}artist") or node.findtext(f"{DC_NS}creator") or "",
                "album": node.findtext(f"{UPNP_NS}album") or "",
                "art": node.findtext(f"{UPNP_NS}albumArtURI") or "",
                "class": node.findtext(f"{UPNP_NS}class") or "",
                "uri": (res.text or "").strip() if res is not None else "",
                "protocol": res.get("protocolInfo", "") if res is not None else "",
            }
        )
    return out


def build_didl(uri: str, title: str = "Ansage", mime: str = "audio/mpeg") -> str:
    return (
        '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
        '<item id="0" parentID="-1" restricted="1">'
        f"<dc:title>{escape(title)}</dc:title>"
        "<upnp:class>object.item.audioItem.musicTrack</upnp:class>"
        f'<res protocolInfo="http-get:*:{mime}:*">{escape(uri)}</res>'
        "</item></DIDL-Lite>"
    )


# ---- Client ------------------------------------------------------------------
class UpnpClient:
    """Findet über den Raumfeld-Host die Dienste der Cinebar und ruft sie auf."""

    def __init__(
        self, session: aiohttp.ClientSession, host: str, player_uuid: str, webservice_port: int = WEBSERVICE_PORT
    ) -> None:
        self._session = session
        self._port = webservice_port
        self.host = host
        self.player_uuid = player_uuid
        self._controls: dict[str, str] = {}
        self._server_controls: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def _get_text(self, url: str) -> str:
        async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as resp:
            resp.raise_for_status()
            return await resp.text()

    async def resolve(self) -> None:
        """Dienste des Renderers (und des MediaServers) neu ermitteln."""
        async with self._lock:
            devices = parse_list_devices(await self._get_text(f"http://{self.host}:{self._port}/listDevices"))
            renderer = devices.get(self.player_uuid)
            if not renderer:
                raise UpnpError("Renderer der Cinebar nicht in der Geräteliste")
            self._controls = parse_description(await self._get_text(renderer["location"]), renderer["location"])
            self._server_controls = {}
            for dev in devices.values():
                if "MediaServer" in dev["type"]:
                    self._server_controls = parse_description(await self._get_text(dev["location"]), dev["location"])
                    break

    async def _call(self, controls: dict[str, str], service: str, action: str, **args: object) -> dict[str, str]:
        url = controls.get(service)
        if not url:
            raise UpnpError(f"Dienst {service} nicht verfügbar")
        headers = {"Content-Type": 'text/xml; charset="utf-8"', "SOAPACTION": f'"{service}#{action}"'}
        async with self._session.post(
            url,
            data=build_envelope(service, action, args).encode("utf-8"),
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
        ) as resp:
            text = await resp.text()
        return parse_response(text)

    async def call(self, service: str, action: str, **args: object) -> dict[str, str]:
        """Aufruf am Renderer; bei Verbindungsfehlern einmal neu auflösen (Ports ändern sich)."""
        if not self._controls:
            await self.resolve()
        try:
            return await self._call(self._controls, service, action, **args)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            await self.resolve()
            return await self._call(self._controls, service, action, **args)

    async def server_call(self, action: str, **args: object) -> dict[str, str]:
        if not self._server_controls:
            await self.resolve()
        return await self._call(self._server_controls, CDS, action, **args)

    # Renderer: Wiedergabe
    async def transport_info(self) -> str:
        return (await self.call(AVT, "GetTransportInfo", InstanceID=0)).get("CurrentTransportState", "")

    async def position_info(self) -> dict[str, str]:
        return await self.call(AVT, "GetPositionInfo", InstanceID=0)

    async def play(self) -> None:
        await self.call(AVT, "Play", InstanceID=0, Speed=1)

    async def pause(self) -> None:
        await self.call(AVT, "Pause", InstanceID=0)

    async def stop(self) -> None:
        await self.call(AVT, "Stop", InstanceID=0)

    async def next(self) -> None:
        await self.call(AVT, "Next", InstanceID=0)

    async def previous(self) -> None:
        await self.call(AVT, "Previous", InstanceID=0)

    async def seek(self, seconds: int) -> None:
        await self.call(AVT, "Seek", InstanceID=0, Unit="REL_TIME", Target=format_time(seconds))

    async def set_uri(self, uri: str, metadata: str = "") -> None:
        await self.call(AVT, "SetAVTransportURI", InstanceID=0, CurrentURI=uri, CurrentURIMetaData=metadata)

    # Renderer: Lautstärke
    async def get_volume(self) -> int:
        return int((await self.call(RCS, "GetVolume", InstanceID=0, Channel="Master")).get("CurrentVolume", "0"))

    async def set_volume(self, volume: int) -> None:
        await self.call(RCS, "SetVolume", InstanceID=0, Channel="Master", DesiredVolume=max(0, min(100, int(volume))))

    async def get_mute(self) -> bool:
        return (await self.call(RCS, "GetMute", InstanceID=0, Channel="Master")).get("CurrentMute", "0") in ("1", "true")

    async def set_mute(self, mute: bool) -> None:
        await self.call(RCS, "SetMute", InstanceID=0, Channel="Master", DesiredMute=1 if mute else 0)

    # MediaServer: Durchsuchen
    async def browse(self, object_id: str, metadata: bool = False) -> list[dict]:
        res = await self.server_call(
            "Browse",
            ObjectID=object_id,
            BrowseFlag="BrowseMetadata" if metadata else "BrowseDirectChildren",
            Filter="*",
            StartingIndex=0,
            RequestedCount=200,
            SortCriteria="",
        )
        return parse_didl(res.get("Result"))
