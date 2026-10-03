"""Raumfeld-Web-Dienst (Port 47365): Standby lesen und schalten. Ohne Home-Assistant-Importe."""
from __future__ import annotations

import xml.etree.ElementTree as ET

WEBSERVICE_PORT = 47365
POWER_ACTIVE = "ACTIVE"
POWER_STANDBY_AUTOMATIC = "AUTOMATIC_STANDBY"
POWER_STANDBY_MANUAL = "MANUAL_STANDBY"


def parse_power_state(xml_text: str, player_uuid: str) -> tuple[str | None, str | None]:
    """Raum-UDN und Betriebszustand des Raums, in dem der Player (Renderer) liegt."""
    root = ET.fromstring(xml_text)
    for room in root.iter("room"):
        for renderer in room.findall("renderer"):
            if renderer.get("udn") == player_uuid:
                return room.get("udn"), room.get("powerState")
    return None, None


def standby_path(on: bool) -> str:
    """Pfad am Host: einschalten = leaveStandby, ausschalten = enterManualStandby."""
    return "/leaveStandby" if on else "/enterManualStandby"
