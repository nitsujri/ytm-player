"""Untouched and failed starts must preserve the last playable session."""

import asyncio
import json
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

_original_mpv = sys.modules.get("mpv")
sys.modules["mpv"] = ModuleType("mpv")
try:
    from ytm_player.app._playback import PlaybackMixin
    from ytm_player.app._session import SessionMixin
    from ytm_player.config.settings import Settings
    from ytm_player.services.queue import QueueManager
finally:
    if _original_mpv is None:
        sys.modules.pop("mpv", None)
    else:
        sys.modules["mpv"] = _original_mpv


class SessionHost(PlaybackMixin, SessionMixin):
    def __init__(self):
        self.settings = Settings()
        self.player = SimpleNamespace(
            set_volume=AsyncMock(), current_track=None, volume=80, position=0.0, play=AsyncMock()
        )
        self.queue = QueueManager()
        self._session_restored = False
        self._loaded_resume = None
        self._active_library_playlist_id = None
        self._sidebar_per_page = {}
        self._lyrics_sidebar_open = False
        self._clean_exit = True
        self._last_play_video_id = ""
        self._last_play_time = 0.0
        self._play_generation = 0
        self._play_lock = asyncio.Lock()
        self._consecutive_failures = 0
        self._log_current_listen = AsyncMock()
        self.stream_resolver = SimpleNamespace(
            resolve=AsyncMock(return_value=SimpleNamespace(url="stream", duration=120)),
            clear_cache=MagicMock(),
        )
        self.notify = MagicMock()
        self.call_later = MagicMock()
        self.discord = self.lastfm = self.mpris = self.mac_media = None

    def query_one(self, *_args):
        raise LookupError("No widgets in this session test")


@pytest.fixture
def saved_session(tmp_path, monkeypatch, sample_track):
    path = tmp_path / "session.json"
    state = {
        "volume": 60,
        "queue_tracks": [sample_track],
        "queue_index": 0,
        "resume": {
            "video_id": sample_track["video_id"],
            "position": 77.5,
            "playlist_id": "saved-playlist",
        },
    }
    path.write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setattr("ytm_player.config.paths.SESSION_STATE_FILE", path)
    return path, state


async def test_launch_and_clean_quit_without_playing_preserves_resume(saved_session):
    path, state = saved_session
    host = SessionHost()
    await host._restore_session_state()
    assert host.queue.current_track["video_id"] == state["resume"]["video_id"]
    host._save_session_state()
    assert json.loads(path.read_text())["resume"] == state["resume"]


async def test_partial_restore_cannot_overwrite_previous_session(saved_session):
    path, _state = saved_session
    before = path.read_bytes()
    host = SessionHost()
    host.player.set_volume.side_effect = RuntimeError("Player startup failed")
    with pytest.raises(RuntimeError):
        await host._restore_session_state()
    host._save_session_state()
    assert path.read_bytes() == before


def test_failure_before_restore_cannot_overwrite_previous_session(saved_session):
    path, _state = saved_session
    before = path.read_bytes()
    SessionHost()._save_session_state()
    assert path.read_bytes() == before


@pytest.mark.parametrize("failure", ["resolve", "load"])
async def test_failed_play_keeps_previous_resume(saved_session, sample_track, failure):
    path, state = saved_session
    host = SessionHost()
    await host._restore_session_state()
    if failure == "resolve":
        host.stream_resolver.resolve.return_value = None
    # The fake player leaves current_track unset, like a rejected mpv load.
    await host.play_track(sample_track)
    host._save_session_state()
    assert json.loads(path.read_text())["resume"] == state["resume"]


@pytest.mark.parametrize("clean_exit, expected_position", [(True, 0.0), (False, 12.5)])
async def test_new_play_replaces_resume_and_preserves_exit_policy(
    saved_session, sample_track, clean_exit, expected_position
):
    path, _state = saved_session
    host = SessionHost()
    await host._restore_session_state()

    async def accept(_url, track):
        host.player.current_track = track
        host.player.position = 12.5

    host.player.play.side_effect = accept
    await host.play_track(sample_track)
    assert host._loaded_resume is None
    host._clean_exit = clean_exit
    host._save_session_state()
    assert json.loads(path.read_text())["resume"]["position"] == expected_position


async def test_play_then_stop_does_not_resurrect_previous_resume(saved_session, sample_track):
    path, _state = saved_session
    host = SessionHost()
    await host._restore_session_state()

    async def accept(_url, track):
        host.player.current_track = track

    host.player.play.side_effect = accept
    await host.play_track(sample_track)
    host.player.current_track = None
    host._save_session_state()
    assert json.loads(path.read_text())["resume"] is None
