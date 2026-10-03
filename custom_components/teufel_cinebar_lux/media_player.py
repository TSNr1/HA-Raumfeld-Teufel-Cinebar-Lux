"""Media Player für die Cinebar Lux (Wiedergabe, Lautstärke, Quelle, Ansagen, Durchsuchen)."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.components.media_player import (
    ATTR_MEDIA_ANNOUNCE,
    BrowseMedia,
    MediaClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    async_process_play_media_url,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .definitions import INPUT_SOURCES, STREAMING_INPUT, option_label, option_value
from .entity import device_info
from .hub import POWER_KEY
from .upnp import (
    STATE_NO_MEDIA,
    STATE_PAUSED,
    STATE_PLAYING,
    STATE_STOPPED,
    STATE_TRANSITIONING,
    build_didl,
    parse_didl,
    parse_time,
)
from .zones import POWER_ACTIVE

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=5)
PARALLEL_UPDATES = 1
CONTAINER_TYPE = "raumfeld_container"
ITEM_TYPE = "raumfeld_item"
ANNOUNCE_MAX_SECONDS = 180
POWER_ON_WAIT = 4

TRANSPORT_FEATURES = (
    MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.SEEK
)

FEATURES = (
    MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.PLAY_MEDIA
    | MediaPlayerEntityFeature.BROWSE_MEDIA
    | MediaPlayerEntityFeature.SELECT_SOURCE
    | MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.MEDIA_ANNOUNCE
)


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([CinebarMediaPlayer(entry.runtime_data, entry)])


def _mime(protocol: str) -> str:
    parts = protocol.split(":")
    return parts[2] if len(parts) > 2 and "/" in parts[2] else "audio/mpeg"


class CinebarMediaPlayer(MediaPlayerEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = True
    _attr_volume_step = 0.02
    _attr_media_content_type = MediaType.MUSIC

    def __init__(self, hub, entry) -> None:
        self.hub = hub
        self._up = hub.upnp
        self._attr_unique_id = f"{hub.player_uuid}_media_player"
        self._attr_device_info = device_info(hub, entry)
        self._available = False
        self._state = MediaPlayerState.OFF
        self._volume: float | None = None
        self._muted: bool | None = None
        self._track: dict = {}
        self._duration: int | None = None
        self._position: int | None = None
        self._position_at = None

    async def async_added_to_hass(self) -> None:
        for key in (POWER_KEY, "audio_input_source"):
            self.async_on_remove(self.hub.add_listener(key, self._values_changed))

    def _values_changed(self) -> None:
        self.async_schedule_update_ha_state(True)

    # ---- Zustand ---------------------------------------------------------
    @property
    def _streaming(self) -> bool:
        """Wiedergabe-Befehle gelten nur am Eingang „Teufel Streaming“ (bei TV/HDMI/Analog/Optisch gibt es nichts zu steuern)."""
        source = self.hub.values.get("audio_input_source")
        return source is None or source == STREAMING_INPUT

    @property
    def supported_features(self):
        return FEATURES | TRANSPORT_FEATURES if self._streaming else FEATURES

    @property
    def available(self) -> bool:
        return self._available

    @property
    def state(self):
        return self._state

    @property
    def volume_level(self):
        return self._volume

    @property
    def is_volume_muted(self):
        return self._muted

    @property
    def media_title(self):
        return self._track.get("title") or None

    @property
    def media_artist(self):
        return self._track.get("artist") or None

    @property
    def media_album_name(self):
        return self._track.get("album") or None

    @property
    def media_image_url(self):
        return self._track.get("art") or None

    @property
    def media_duration(self):
        return self._duration

    @property
    def media_position(self):
        return self._position

    @property
    def media_position_updated_at(self):
        return self._position_at

    @property
    def source_list(self):
        return list(INPUT_SOURCES.values())

    @property
    def source(self):
        return option_label(INPUT_SOURCES, self.hub.values.get("audio_input_source"))

    async def async_update(self) -> None:
        power = self.hub.values.get(POWER_KEY)
        if power is not None and power != POWER_ACTIVE:
            self._available = True
            self._state = MediaPlayerState.OFF
            self._track, self._duration, self._position = {}, None, None
            return
        try:
            transport = await self._up.transport_info()
            self._volume = (await self._up.get_volume()) / 100
            self._muted = await self._up.get_mute()
            self._track, self._duration, self._position = {}, None, None
            if not self._streaming:
                self._available = True
                self._state = MediaPlayerState.ON
                return
            if transport in (STATE_PLAYING, STATE_PAUSED, STATE_TRANSITIONING):
                info = await self._up.position_info()
                items = parse_didl(info.get("TrackMetaData"))
                self._track = items[0] if items else {}
                self._duration = parse_time(info.get("TrackDuration"))
                self._position = parse_time(info.get("RelTime"))
                self._position_at = dt_util.utcnow()
            self._available = True
            if transport == STATE_PLAYING or transport == STATE_TRANSITIONING:
                self._state = MediaPlayerState.PLAYING
            elif transport == STATE_PAUSED:
                self._state = MediaPlayerState.PAUSED
            elif transport in (STATE_STOPPED, STATE_NO_MEDIA):
                self._state = MediaPlayerState.IDLE
            else:
                self._state = MediaPlayerState.ON
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Cinebar nicht erreichbar: %s", err)
            self._available = False

    async def _refresh(self) -> None:
        await self.async_update()
        self.async_write_ha_state()

    async def _run(self, coro):
        try:
            await coro
        except Exception as err:  # noqa: BLE001
            text = str(err)
            if "701" in text or "not allowed" in text:
                text = "Gerade nichts zum Steuern (am Eingang „Teufel Streaming“ erst etwas abspielen)"
            raise HomeAssistantError(f"Cinebar: {text}") from err
        await self._refresh()

    # ---- Steuerung ---------------------------------------------------------
    async def async_turn_on(self) -> None:
        await self.hub.async_set_power(True)
        await self._refresh()

    async def async_turn_off(self) -> None:
        await self.hub.async_set_power(False)
        await self._refresh()

    async def async_media_play(self) -> None:
        await self._run(self._up.play())

    async def async_media_pause(self) -> None:
        await self._run(self._up.pause())

    async def async_media_stop(self) -> None:
        await self._run(self._up.stop())

    async def async_media_next_track(self) -> None:
        await self._run(self._up.next())

    async def async_media_previous_track(self) -> None:
        await self._run(self._up.previous())

    async def async_media_seek(self, position: float) -> None:
        await self._run(self._up.seek(int(position)))

    async def async_set_volume_level(self, volume: float) -> None:
        await self._run(self._up.set_volume(round(volume * 100)))

    async def async_mute_volume(self, mute: bool) -> None:
        await self._run(self._up.set_mute(mute))

    async def async_select_source(self, source: str) -> None:
        await self.hub.async_set("audio_input_source", option_value(INPUT_SOURCES, source))
        await self._refresh()

    # ---- Wiedergabe von URLs, Ansagen ---------------------------------------
    async def async_play_media(self, media_type: str, media_id: str, **kwargs) -> None:
        announce = bool(kwargs.get(ATTR_MEDIA_ANNOUNCE))
        mime = "audio/mpeg"
        title = "Ansage" if announce else "Wiedergabe"
        if media_type == ITEM_TYPE:
            items = await self._up.browse(media_id, metadata=True)
            if not items or not items[0]["uri"]:
                raise HomeAssistantError("Eintrag nicht abspielbar")
            uri, title, mime = items[0]["uri"], items[0]["title"] or title, _mime(items[0]["protocol"])
        else:
            try:
                from homeassistant.components import media_source

                if media_source.is_media_source_id(media_id):
                    sourced = await media_source.async_resolve_media(self.hass, media_id, self.entity_id)
                    media_id, mime = sourced.url, sourced.mime_type or mime
            except ImportError:  # pragma: no cover
                pass
            uri = async_process_play_media_url(self.hass, media_id)
        didl = build_didl(uri, title, mime)
        try:
            if announce:
                await self._announce(uri, didl)
            else:
                if self._state == MediaPlayerState.OFF:
                    await self.hub.async_set_power(True)
                    await asyncio.sleep(POWER_ON_WAIT)
                if not self._streaming:
                    await self.hub.async_set("audio_input_source", STREAMING_INPUT)
                    await asyncio.sleep(1)
                await self._up.set_uri(uri, didl)
                await self._up.play()
        except Exception as err:  # noqa: BLE001
            raise HomeAssistantError(f"Cinebar: {err}") from err
        await self._refresh()

    async def _announce(self, uri: str, didl: str) -> None:
        """Ansage abspielen und danach den vorherigen Zustand wiederherstellen (bestmöglich)."""
        was_off = self._state == MediaPlayerState.OFF
        if was_off:
            await self.hub.async_set_power(True)
            await asyncio.sleep(POWER_ON_WAIT)
        before_source = self.hub.values.get("audio_input_source")
        before_state = await self._up.transport_info()
        before = await self._up.position_info()
        await self._up.set_uri(uri, didl)
        await self._up.play()
        waited = 0.0
        started = False
        while waited < ANNOUNCE_MAX_SECONDS:
            await asyncio.sleep(0.7)
            waited += 0.7
            state = await self._up.transport_info()
            if state in (STATE_PLAYING, STATE_TRANSITIONING):
                started = True
            elif started or waited > 8:
                break
        if was_off:
            await self.hub.async_set_power(False)
            return
        if before_source is not None and self.hub.values.get("audio_input_source") != before_source:
            await self.hub.async_set("audio_input_source", before_source)
            return
        old_uri = before.get("TrackURI")
        if before_source in (None, STREAMING_INPUT) and before_state in (STATE_PLAYING, STATE_PAUSED) and old_uri:
            await self._up.set_uri(old_uri, before.get("TrackMetaData", ""))
            if before_state == STATE_PLAYING:
                await self._up.play()
                position = parse_time(before.get("RelTime"))
                if position:
                    try:
                        await self._up.seek(position)
                    except Exception:  # noqa: BLE001  (Live-Streams lassen kein Springen zu)
                        pass

    # ---- Durchsuchen --------------------------------------------------------
    async def async_browse_media(self, media_content_type=None, media_content_id=None) -> BrowseMedia:
        object_id = media_content_id or "0"
        try:
            meta = await self._up.browse(object_id, metadata=True)
            children = await self._up.browse(object_id)
        except Exception as err:  # noqa: BLE001
            raise HomeAssistantError(f"Raumfeld-Mediathek nicht erreichbar: {err}") from err
        title = meta[0]["title"] if meta and meta[0]["title"] else "Raumfeld"
        entries = []
        for child in children:
            if child["kind"] == "container":
                entries.append(
                    BrowseMedia(
                        title=child["title"],
                        media_class=MediaClass.DIRECTORY,
                        media_content_id=child["id"],
                        media_content_type=CONTAINER_TYPE,
                        can_play=False,
                        can_expand=True,
                        thumbnail=child["art"] or None,
                    )
                )
            else:
                entries.append(
                    BrowseMedia(
                        title=child["title"],
                        media_class=MediaClass.MUSIC,
                        media_content_id=child["id"],
                        media_content_type=ITEM_TYPE,
                        can_play=bool(child["uri"]),
                        can_expand=False,
                        thumbnail=child["art"] or None,
                    )
                )
        return BrowseMedia(
            title=title,
            media_class=MediaClass.DIRECTORY,
            media_content_id=object_id,
            media_content_type=CONTAINER_TYPE,
            can_play=False,
            can_expand=True,
            children=entries,
        )
