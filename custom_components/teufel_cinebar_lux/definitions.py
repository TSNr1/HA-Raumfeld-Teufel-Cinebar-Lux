"""Einstellungen der Cinebar Lux – ohne Home-Assistant-Importe (testbar).

Namen und Werte stammen aus dem Mitschnitt der Raumfeld-App. Wertebereiche,
die nicht beobachtet wurden, sind vorsichtig geschätzt und in der README markiert.
"""
from __future__ import annotations

DOMAIN = "teufel_cinebar_lux"
CONF_HOST = "host"
CONF_PLAYER = "player_uuid"
CONF_NAME = "name"
CINEBAR_LUX_TYPE = 27  # "type" im Raumfeld-Host / hardware_id der Cinebar Lux

# Auswahllisten: Wert -> Anzeigename. Unbekannte Werte werden dynamisch ergänzt.
INPUT_SOURCES = {3: "TV", 4: "HDMI"}
SOUND_MODES = {0: "Pur", 1: "Sprache", 2: "Nacht"}
SUBWOOFER_PHASES = {0: "0°", 180: "180°"}

# key -> (Standard an?, Konfigurationskategorie?)
SWITCHES = {
    "audio_dynamore": (True, False),
    "audio_dynamic_range_control": (True, False),
    "rears_stereo_upmix": (True, True),
    "cec": (True, True),
    "auto_on_opt": (True, True),
}

# key -> (Optionen, Standard aktiv?, Konfigurationskategorie?)
SELECTS = {
    "audio_input_source": (INPUT_SOURCES, True, False),
    "sound_mode": (SOUND_MODES, True, False),
    "subwoofer_phase": (SUBWOOFER_PHASES, True, True),
}

# key -> (min, max, step, Einheit, Standard aktiv?, Konfigurationskategorie?)
NUMBERS = {
    "lip_sync": (0, 5, 1, None, True, False),
    "subwoofer_volume_adjustment": (-10, 10, 1, None, True, True),
    "subwoofer_distance": (0, 500, 1, None, True, True),
    "soundbar_distance": (0, 500, 1, None, True, True),
    "rears_level_left": (-10, 10, 1, None, True, True),
    "rears_level_right": (-10, 10, 1, None, True, True),
    "rears_distance_left": (0, 500, 1, None, True, True),
    "rears_distance_right": (0, 500, 1, None, True, True),
    "led_brightness": (0, 10, 1, None, True, True),
    "display_max_brightness": (0, 100, 1, "%", True, True),
    "display_min_brightness": (0, 100, 1, "%", True, True),
    "auto_standby_delay": (0, 7200, 60, "s", True, True),
    "auto_on_aux": (0, 10, 1, None, False, True),
    "display_language": (0, 10, 1, None, False, True),
}

BLUETOOTH = "bluetooth.status"
EXTERNAL_SPEAKERS = "external_speakers"
HARDWARE_ID = "hardware_id"
EXTERNAL_SPEAKER_KEYS = {"subwoofer": "subwoofer", "rearLeft": "rear_left", "rearRight": "rear_right"}

ALL_SETTINGS = (
    list(SWITCHES) + list(SELECTS) + list(NUMBERS) + [BLUETOOTH, EXTERNAL_SPEAKERS, HARDWARE_ID]
)


def bluetooth_state(value) -> str | None:
    """Zustandstext aus {connected, device, pairing, ready}."""
    if not isinstance(value, dict):
        return None
    if value.get("pairing"):
        return "pairing"
    if value.get("connected"):
        return "connected"
    if value.get("ready"):
        return "ready"
    return "off"


def option_label(mapping: dict[int, str], value) -> str | None:
    if value is None:
        return None
    return mapping.get(value, f"Unbekannt ({value})")


def option_value(mapping: dict[int, str], label: str):
    for val, lab in mapping.items():
        if lab == label:
            return val
    if label.startswith("Unbekannt (") and label.endswith(")"):
        try:
            return int(label[11:-1])
        except ValueError:
            pass
    raise ValueError(label)
