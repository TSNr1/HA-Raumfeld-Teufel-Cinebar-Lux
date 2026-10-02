# Teufel Cinebar Lux für Home Assistant

Ergänzt die Cinebar Lux um alle Einstellungen, die die Raumfeld-App kennt – lokal, ohne Cloud, mit Echtzeit-Updates. Läuft **neben** der bestehenden Integration „Teufel Raumfeld“ (HACS), die weiter für Wiedergabe und Lautstärke zuständig ist.

## Installation

1. HACS → Benutzerdefinierte Repositories → dieses Repository als *Integration* hinzufügen.
2. Installieren, Home Assistant neu starten.
3. *Einstellungen → Geräte & Dienste → Integration hinzufügen → Teufel Cinebar Lux*, IP-Adresse des Raumfeld-Hosts eingeben (die Cinebar wird automatisch erkannt).

## Entitäten

| Bereich | Entitäten |
|---|---|
| Hauptfunktionen | Eingang (TV, HDMI), Klang-Modus (Pur, Sprache, Nacht), Dynamore, Dynamikkompression (DRC), Lip Sync (0–5) |
| Konfiguration | Rear-Stereo-Upmix, HDMI-CEC, Auto-Einschalten (optisch/AUX), Auto-Standby, Subwoofer-Pegel/-Abstand/-Phase, Soundbar-Abstand, Rear-Pegel/-Abstand, LED- und Display-Helligkeit, Display-Sprache |
| Sensoren | Bluetooth (verbunden / Pairing / bereit / aus, mit Gerätename), gekoppelte externe Lautsprecher, Hardware-ID, Verbindungsstatus |

## Technik

Die Raumfeld-App steuert die Bar über einen WebSocket (WAMP v2, Port 55555) am Raumfeld-Host. Jede Einstellung hat die Adresse `com.raumfeld.devices.<UUID>.settings.<name>`; gelesen wird mit `["get"]`, geschrieben mit `["set", wert]`, Änderungen kommen als Event.

## Noch offen

- Weitere Eingänge und Modi: Beobachtet und benannt sind Eingang 3 = TV, 4 = HDMI und Modus 0 = Pur, 2 = Nacht (1 = Sprache ist angenommen). Andere Werte erscheinen als „Unbekannt (n)“ und lassen sich trotzdem setzen. Bitte melden, welche Zahl zu welchem Eingang gehört.
- Wertebereiche der Zahlenfelder (Pegel, Abstände, Helligkeit) sind vorsichtig geschätzt; die Einheiten der Abstände sind nicht bestätigt.
- Bluetooth-Pairing starten: Der Aufruf wurde noch nicht mitgeschnitten, daher gibt es noch keine Taste dafür.
