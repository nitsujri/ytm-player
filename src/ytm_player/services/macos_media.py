"""
Purpose: Integrate ytm-player with macOS media keys and Now Playing center.
Interface: MacOSMediaService.start/stop/update_metadata/update_playback_status/update_position.
Invariants: Missing MediaPlayer bindings degrade to no-op behavior without crashing the app.
Decisions: Keep metadata updates local (no artwork download) and dispatch callbacks on the app loop.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)

try:
    _MP = importlib.import_module("MediaPlayer")

    _MEDIA_PLAYER_AVAILABLE = True
except ImportError:
    _MP = None
    _MEDIA_PLAYER_AVAILABLE = False

PlayerCallback = Callable[..., Coroutine[Any, Any, None]]

_STATUS_SUCCESS = 0
_STATUS_FAILED = 200

if _MEDIA_PLAYER_AVAILABLE:
    _STATUS_SUCCESS = int(getattr(_MP, "MPRemoteCommandHandlerStatusSuccess", 0))
    _STATUS_FAILED = int(getattr(_MP, "MPRemoteCommandHandlerStatusCommandFailed", 200))

_TITLE_KEY = "title"
_ARTIST_KEY = "artist"
_ALBUM_KEY = "albumTitle"
_DURATION_KEY = "playbackDuration"
_ELAPSED_KEY = "elapsedPlaybackTime"
_RATE_KEY = "playbackRate"

if _MEDIA_PLAYER_AVAILABLE:
    _TITLE_KEY = str(getattr(_MP, "MPMediaItemPropertyTitle", _TITLE_KEY))
    _ARTIST_KEY = str(getattr(_MP, "MPMediaItemPropertyArtist", _ARTIST_KEY))
    _ALBUM_KEY = str(getattr(_MP, "MPMediaItemPropertyAlbumTitle", _ALBUM_KEY))
    _DURATION_KEY = str(getattr(_MP, "MPMediaItemPropertyPlaybackDuration", _DURATION_KEY))
    _ELAPSED_KEY = str(getattr(_MP, "MPNowPlayingInfoPropertyElapsedPlaybackTime", _ELAPSED_KEY))
    _RATE_KEY = str(getattr(_MP, "MPNowPlayingInfoPropertyPlaybackRate", _RATE_KEY))

_PLAYBACK_STATE_PLAYING = None
_PLAYBACK_STATE_PAUSED = None
_PLAYBACK_STATE_STOPPED = None
if _MEDIA_PLAYER_AVAILABLE:
    _PLAYBACK_STATE_PLAYING = getattr(_MP, "MPNowPlayingPlaybackStatePlaying", None)
    _PLAYBACK_STATE_PAUSED = getattr(_MP, "MPNowPlayingPlaybackStatePaused", None)
    _PLAYBACK_STATE_STOPPED = getattr(_MP, "MPNowPlayingPlaybackStateStopped", None)


class MacOSMediaService:
    """Connect app playback state to macOS media controls."""

    def __init__(self) -> None:
        self._running = False
        self._callbacks: dict[str, PlayerCallback] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._registered_targets: list[tuple[Any, Any]] = []
        self._now_playing: dict[str, Any] = {}
        self._is_playing = False

    async def start(
        self,
        callbacks: dict[str, PlayerCallback],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        """Register MPRemoteCommandCenter handlers."""
        if not _MEDIA_PLAYER_AVAILABLE:
            logger.info("MediaPlayer framework bindings not installed — macOS media keys disabled")
            return

        self._callbacks = callbacks
        self._loop = loop

        mp = _MP
        if mp is None:
            logger.info("MediaPlayer bindings unavailable at runtime")
            return
        self._register_all_commands()

        self._running = True
        self._publish_now_playing()
        logger.info("macOS media key integration enabled")

    def _register_all_commands(self) -> None:
        """Register MPRemoteCommandCenter handlers. Safe to call repeatedly."""
        if not _MEDIA_PLAYER_AVAILABLE or _MP is None:
            return
        if self._registered_targets:
            return
        center = _MP.MPRemoteCommandCenter.sharedCommandCenter()
        # AirPods in-ear detection fires togglePlayPauseCommand in both
        # directions — removal and insertion.  We map it to a one-way
        # "pause-only" action so pulling an earbud stops playback but
        # reinserting does NOT auto-resume.  The discrete play command
        # is still honored (UI / keyboard / explicit user intent).
        self._register_command(center.playCommand(), "play")
        self._register_command(center.pauseCommand(), "pause")
        self._register_command(center.togglePlayPauseCommand(), "pause_only")
        self._register_command(center.nextTrackCommand(), "next")
        self._register_command(center.previousTrackCommand(), "previous")

    def handoff_to_system(self) -> None:
        """Release control of the macOS Now Playing slot.

        Removes MPRemoteCommand handlers and clears Now Playing info so
        macOS stops forwarding play/pause/next commands to ytm-player
        and hands the active-media-app slot to whichever other source
        (iPhone, Apple Music, etc.) wants it. The service remains
        ``_running`` so a later update_playback_status("playing") can
        re-register and republish via :meth:`_reactivate`.
        """
        if not self._running or _MP is None:
            return
        for command, target in self._registered_targets:
            try:
                command.removeTarget_(target)
            except Exception:
                logger.debug("Failed to remove media command target", exc_info=True)
        self._registered_targets.clear()
        try:
            _MP.MPNowPlayingInfoCenter.defaultCenter().setNowPlayingInfo_(None)
        except Exception:
            logger.debug("Failed to clear macOS Now Playing info", exc_info=True)
        self._is_playing = False
        logger.info("macOS media control handed off to system")

    @property
    def is_handling_commands(self) -> bool:
        """True when MPRemoteCommandCenter handlers are registered."""
        return self._running and bool(self._registered_targets)

    def _reactivate(self) -> None:
        """Re-register command handlers after a previous handoff."""
        if not self._running:
            return
        if not self._registered_targets:
            self._register_all_commands()
            logger.info("macOS media control reactivated")

    def stop(self) -> None:
        """Unregister command handlers and clear Now Playing state."""
        if not _MEDIA_PLAYER_AVAILABLE:
            return
        mp = _MP
        if mp is None:
            return

        for command, target in self._registered_targets:
            try:
                command.removeTarget_(target)
            except Exception:
                logger.debug("Failed to remove media command target", exc_info=True)
        self._registered_targets.clear()

        try:
            mp.MPNowPlayingInfoCenter.defaultCenter().setNowPlayingInfo_(None)
        except Exception:
            logger.debug("Failed to clear macOS Now Playing info", exc_info=True)

        self._running = False
        self._now_playing.clear()
        self._is_playing = False
        logger.info("macOS media key integration stopped")

    async def update_metadata(
        self,
        title: str,
        artist: str,
        album: str,
        length_us: int,
    ) -> None:
        """Publish track metadata to macOS Now Playing center."""
        if not self._running:
            return

        duration_seconds = max(0.0, length_us / 1_000_000)
        self._now_playing[_TITLE_KEY] = title or ""
        self._now_playing[_ARTIST_KEY] = artist or ""
        self._now_playing[_ALBUM_KEY] = album or ""
        self._now_playing[_DURATION_KEY] = duration_seconds
        self._now_playing.setdefault(_ELAPSED_KEY, 0.0)
        self._now_playing.setdefault(_RATE_KEY, 1.0 if self._is_playing else 0.0)
        # Updating metadata implies we want the Now Playing slot back.
        self._reactivate()
        self._publish_now_playing()

    async def update_playback_status(self, status: str) -> None:
        """Update playback rate/state visible to the macOS media panel."""
        if not self._running:
            return

        normalized = status.lower()
        self._is_playing = normalized == "playing"
        # If we handed off and we're transitioning back to playing,
        # reclaim the Now Playing slot before republishing.
        if self._is_playing:
            self._reactivate()
        elif not self._registered_targets:
            # We're paused and already handed off — stay quiet so we
            # don't re-register ourselves as the active media app.
            return
        self._now_playing[_RATE_KEY] = 1.0 if self._is_playing else 0.0
        self._publish_now_playing(playback_status=normalized)

    def update_position(self, position_us: int) -> None:
        """Update elapsed playback position in seconds."""
        if not self._running or not self._registered_targets:
            return

        self._now_playing[_ELAPSED_KEY] = max(0.0, position_us / 1_000_000)
        self._publish_now_playing()

    def _register_command(self, command: Any, action_name: str) -> None:
        command.setEnabled_(True)
        target = command.addTargetWithHandler_(self._make_handler(action_name))
        self._registered_targets.append((command, target))

    def _make_handler(self, action_name: str):
        def _handler(_event: Any) -> int:
            callback = self._callbacks.get(action_name)
            if callback is None or self._loop is None or self._loop.is_closed():
                return _STATUS_FAILED

            try:
                self._loop.call_soon_threadsafe(lambda cb=callback: asyncio.ensure_future(cb()))
            except RuntimeError:
                logger.debug("Event loop closed, cannot dispatch macOS media key event")
                return _STATUS_FAILED
            return _STATUS_SUCCESS

        return _handler

    def _publish_now_playing(self, playback_status: str | None = None) -> None:
        if not _MEDIA_PLAYER_AVAILABLE:
            return
        mp = _MP
        if mp is None:
            return
        try:
            center = mp.MPNowPlayingInfoCenter.defaultCenter()
            center.setNowPlayingInfo_(self._now_playing or None)
            if hasattr(center, "setPlaybackState_"):
                state = self._playback_state(playback_status)
                if state is not None:
                    center.setPlaybackState_(state)
        except Exception:
            logger.debug("Failed to publish macOS Now Playing info", exc_info=True)

    def _playback_state(self, status: str | None) -> Any:
        if status == "playing":
            return _PLAYBACK_STATE_PLAYING
        if status == "paused":
            return _PLAYBACK_STATE_PAUSED
        if status == "stopped":
            return _PLAYBACK_STATE_STOPPED
        return _PLAYBACK_STATE_PLAYING if self._is_playing else _PLAYBACK_STATE_PAUSED
