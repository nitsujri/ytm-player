"""Overlapping track requests must leave the newest request in control."""

import asyncio
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

_original_mpv = sys.modules.get("mpv")
sys.modules["mpv"] = ModuleType("mpv")
try:
    from ytm_player.app._playback import PlaybackMixin
finally:
    if _original_mpv is None:
        sys.modules.pop("mpv", None)
    else:
        sys.modules["mpv"] = _original_mpv


class PlaybackHost(PlaybackMixin):
    def __init__(self):
        self.player = SimpleNamespace(play=AsyncMock())
        self.stream_resolver = SimpleNamespace(resolve=AsyncMock(), clear_cache=MagicMock())
        self.queue = SimpleNamespace(next_track=MagicMock(return_value=None))
        self._last_play_video_id = ""
        self._last_play_time = 0.0
        self._play_generation = 0
        self._play_lock = asyncio.Lock()
        self._consecutive_failures = 0
        self._track_start_position = 0.0
        self._log_current_listen = AsyncMock()
        self.query_one = MagicMock()
        self.notify = MagicMock()
        self.discord = None
        self.lastfm = None
        self.mpris = None
        self.mac_media = None


@pytest.mark.parametrize("old_result", [None, "stream", RuntimeError("failed")])
async def test_old_resolution_cannot_play_or_advance_after_newer_request(old_result):
    host = PlaybackHost()
    started = asyncio.Event()
    release = asyncio.Event()
    new_stream = SimpleNamespace(url="new-stream", duration=120)

    async def resolve(video_id):
        if video_id == "old":
            started.set()
            await release.wait()
            if isinstance(old_result, Exception):
                raise old_result
            return SimpleNamespace(url="old-stream", duration=120) if old_result else None
        return new_stream

    host.stream_resolver.resolve.side_effect = resolve
    old_task = asyncio.create_task(host.play_track({"video_id": "old"}))
    await asyncio.wait_for(started.wait(), timeout=2)
    await host.play_track({"video_id": "new"})
    release.set()
    await asyncio.wait_for(old_task, timeout=2)

    host.player.play.assert_awaited_once_with("new-stream", {"video_id": "new"})
    host.queue.next_track.assert_not_called()
    host.notify.assert_not_called()
    host.stream_resolver.clear_cache.assert_not_called()


async def test_threaded_play_commands_are_serialized_and_stale_metadata_is_skipped():
    host = PlaybackHost()
    started = asyncio.Event()
    release = asyncio.Event()
    newer_resolved = asyncio.Event()
    commands = []
    host.mac_media = SimpleNamespace(
        update_metadata=AsyncMock(), update_playback_status=AsyncMock()
    )

    async def resolve(video_id):
        if video_id == "new":
            newer_resolved.set()
        return SimpleNamespace(url=video_id, duration=120)

    async def play(url, track):
        commands.append(url)
        if url == "old":
            started.set()
            await release.wait()

    host.stream_resolver.resolve.side_effect = resolve
    host.player.play.side_effect = play
    old_task = asyncio.create_task(host.play_track({"video_id": "old", "title": "Old"}))
    await asyncio.wait_for(started.wait(), timeout=2)
    new_task = asyncio.create_task(host.play_track({"video_id": "new", "title": "New"}))
    await asyncio.wait_for(newer_resolved.wait(), timeout=2)
    assert commands == ["old"]
    release.set()
    await asyncio.wait_for(asyncio.gather(old_task, new_task), timeout=2)

    assert commands == ["old", "new"]
    host.mac_media.update_metadata.assert_awaited_once()
    assert host.mac_media.update_metadata.await_args.kwargs["title"] == "New"


async def test_failed_resolution_can_be_retried_immediately():
    host = PlaybackHost()
    host.stream_resolver.resolve.side_effect = [None, SimpleNamespace(url="retry", duration=120)]
    await host.play_track({"video_id": "same"})
    await host.play_track({"video_id": "same"})
    host.player.play.assert_awaited_once_with("retry", {"video_id": "same"})
