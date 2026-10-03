# Teufel Cinebar Lux für Home Assistant

Ergänzt die Cinebar Lux um alle Einstellungen, die die Raumfeld-App kennt – lokal, ohne Cloud, mit Echtzeit-Updates. Läuft **neben** der bestehenden Integration „Teufel Raumfeld“ (HACS), die weiter für Wiedergabe und Lautstärke zuständig ist.

## Installation

1. HACS → Benutzerdefinierte Repositories → dieses Repository als *Integration* hinzufügen.
2. Installieren, Home Assistant neu starten.
3. *Einstellungen → Geräte & Dienste → Integration hinzufügen → Teufel Cinebar Lux*, IP-Adresse des Raumfeld-Hosts eingeben (die Cinebar wird automatisch erkannt).

## Media Player

Die Cinebar erscheint als Media Player mit Status, Lautstärke, Stumm, Play/Pause/Stop, Titel vor/zurück, Springen, Titel-Infos mit Cover, Ein/Aus und Quellenwahl (Eingang: Teufel Streaming, Analog, Optisch, TV, HDMI). Die Standard-Oberfläche von Home Assistant zum Durchsuchen der Raumfeld-Mediathek (Radio, Podcasts, lokale Musik) ist eingebunden; abspielbare Einträge starten direkt.

**Ansagen und Töne:** Der Media Player unterstützt `announce`. Damit funktionieren zum Beispiel `tts.speak` und `media_player.play_media` mit `announce: true`: Die Cinebar spielt die Ansage, danach wird der vorherige Titel wiederhergestellt (bestmöglich; bei Live-Streams kann das Springen zur alten Position entfallen). War die Bar aus, schaltet sie sich für die Ansage ein und danach wieder aus.

```yaml
action: tts.speak
data:
  media_player_entity_id: media_player.speaker_wohnzimmerteufellux
  message: "Das Paket ist da."
  options:
    preferred_format: mp3
```

## Entitäten

| Bereich | Entitäten |
|---|---|
| Hauptfunktionen | Ein/Aus (Standby), Eingang (Analog, Optisch, Teufel Streaming, TV, HDMI), Klang-Modus (Pur, Sprache, Nacht), Dynamore, Dynamikkompression (DRC), Lip Sync (0–100 ms) |
| Konfiguration | Rear-Stereo-Upmix, HDMI-CEC, Auto-Einschalten (optisch/AUX), Auto-Standby, Subwoofer-Pegel/-Abstand/-Phase, Soundbar-Abstand, Rear-Pegel/-Abstand, LED- und Display-Helligkeit, Display-Sprache |
| Sensoren | Bluetooth (verbunden / Pairing / bereit / aus, mit Gerätename), gekoppelte externe Lautsprecher, Hardware-ID, Verbindungsstatus |

## Technik

Ein/Aus läuft über den Web-Dienst des Raumfeld-Hosts (Port 47365): `/leaveStandby` schaltet ein, `/enterManualStandby` aus. Der Zustand wird alle 20 Sekunden gelesen und gilt als „an“, solange der Raum aktiv ist (Eco- und manueller Standby gelten als „aus“).

Die Raumfeld-App steuert die Bar über einen WebSocket (WAMP v2, Port 55555) am Raumfeld-Host. Jede Einstellung hat die Adresse `com.raumfeld.devices.<UUID>.settings.<name>`; gelesen wird mit `["get"]`, geschrieben mit `["set", wert]`, Änderungen kommen als Event.

## Noch offen

- **Media Player:** Gruppen mehrerer Räume und Snapshots gibt es nicht; die Integration ist für eine einzelne Bar gedacht. Spotify wird weiter über Spotify Connect (Spotify-App) gestartet, nicht über Home Assistant. Ob alle Mediathek-Einträge (zum Beispiel Wiedergabelisten als Ganzes) abspielbar sind, hängt vom Raumfeld-MediaServer ab.

- **Eingänge:** 0 = Teufel Streaming, 1 = Analog, 2 = Optisch, 3 = TV, 4 = HDMI (gegengeprüft). Bluetooth und weitere Quellen fehlen noch; unbekannte Werte erscheinen als „Unbekannt (n)“ und lassen sich trotzdem setzen.
- **Modi:** 0 = Pur, 1 = Sprache, 2 = Nacht.
- **Lip Sync:** 0 bis 100 ms in 1-ms-Schritten, der Wert geht direkt an die Cinebar.
- **Abstände:** Soundbar 0,3 bis 12 m bestätigt, die Rohwerte werden in Schritten von 0,1 m gelesen (46 = 4,6 m, ebenfalls bestätigt). Subwoofer- und Rear-Abstände nutzen dieselbe Skala.
- **Wertebereiche:** Pegel und Helligkeiten sind vorsichtig geschätzt.
- **Ein/Aus:** In der Praxis noch zu prüfen: Verhalten beim Einschalten aus dem Standby.
- **Bluetooth-Pairing starten:** Der Aufruf wurde noch nicht mitgeschnitten, daher gibt es noch keine Taste dafür.
