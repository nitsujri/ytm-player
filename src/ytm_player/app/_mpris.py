"""MPRIS / media-key callback mixin for YTMPlayerApp."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class MPRISMixin:
    """Builds the callback dict expected by MPRISService / MacOS / Windows media keys."""

    def _build_mpris_callbacks(self) -> dict[str, Any]:
        """Build the callback dict expected by MPRISService.start()."""
        return {
            "play": self._mpris_play,
            "pause": self._mpris_pause,
            "play_pause": self._mpris_play_pause,
            "pause_only": self._mpris_pause_only,
            "stop": self._mpris_stop,
            "next": self._mpris_next,
            "previous": self._mpris_previous,
            "seek": self._mpris_seek,
            "set_position": self._mpris_set_position,
            "quit": self._mpris_quit,
        }

    def _resolve_media_toggle(self) -> str:
        """Resolve a media-key toggle press to an absolute action name.

        Playing → ``"pause"``. Paused with a recent audio route change
        → ``""`` (no-op) so AirPods in-ear / AVRCP events can't resume
        a paused track. Paused otherwise → ``"play"``.
        """
        if self.player and self.player.is_playing:
            return "pause"
        if self._route_change_suppressing_play():
            return ""
        return "play"

    def _route_change_suppressing_play(self) -> bool:
        """True when a macOS audio route just changed and we should drop play.

        AirPods / iPhone Handoff fire AVRCP "play" commands within a few
        milliseconds of a route change. If we act on those we resume
        playback the user explicitly paused. The route monitor tracks
        the last change time; we reject play commands inside its
        suppression window.
        """
        monitor = getattr(self, "mac_audio_route", None)
        if monitor is None:
            return False
        try:
            return bool(monitor.recently_changed())
        except Exception:
            return False

    async def _mpris_play(self) -> None:
        if self._route_change_suppressing_play():
            logger.debug("Suppressing play: macOS audio route just changed")
            return
        if self.player and self.player.is_paused:
            await self.player.resume()

    async def _mpris_pause(self) -> None:
        if self.player:
            await self.player.pause()

    async def _mpris_pause_only(self) -> None:
        # AirPods in-ear detection dispatches togglePlayPauseCommand for
        # both removal and insertion. Honor the pause direction only —
        # never auto-resume on reinsertion.
        if self.player and self.player.is_playing:
            await self.player.pause()

    async def _mpris_play_pause(self) -> None:
        if self._route_change_suppressing_play():
            logger.debug("Suppressing play_pause: macOS audio route just changed")
            return
        await self._toggle_play_pause()

    async def _mpris_stop(self) -> None:
        if self.player:
            await self.player.stop()

    async def _mpris_next(self) -> None:
        await self._play_next()

    async def _mpris_previous(self) -> None:
        await self._play_previous()

    async def _mpris_seek(self, offset_us: int) -> None:
        if self.player:
            await self.player.seek(offset_us / 1_000_000)

    async def _mpris_set_position(self, position_us: int) -> None:
        if self.player:
            await self.player.seek_absolute(position_us / 1_000_000)

    async def _mpris_quit(self) -> None:
        self.exit()
