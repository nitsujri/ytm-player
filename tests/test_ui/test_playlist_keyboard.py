"""Keyboard-only navigation between the persistent sidebar and pages."""

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from textual.widgets import ListView

from ytm_player.config import KeyMap

# These tests exercise widgets, not audio. Importing the app should not
# require the system libmpv library on developer machines or CI.
_original_mpv = sys.modules.get("mpv")
sys.modules["mpv"] = ModuleType("mpv")
try:
    from ytm_player.app import YTMPlayerApp
    from ytm_player.ui.sidebars.playlist_sidebar import PlaylistSidebar
    from ytm_player.ui.widgets.track_table import TrackTable
finally:
    if _original_mpv is None:
        sys.modules.pop("mpv", None)
    else:
        sys.modules["mpv"] = _original_mpv


class _KeyboardApp(YTMPlayerApp):
    """Use the real UI without starting playback, IPC, or network services."""

    def __init__(self, tracks):
        super().__init__()
        self.keymap = KeyMap()
        self.keymap._load_defaults()
        self.ytmusic = SimpleNamespace(
            get_library_playlists=AsyncMock(
                return_value=[
                    {"playlistId": f"playlist-{i}", "title": f"Playlist {i}"} for i in range(3)
                ]
            ),
            get_playlist=AsyncMock(return_value={"title": "Test playlist", "tracks": tracks}),
        )
        self.play_track = AsyncMock()

    def _mount_test_ui(self) -> None:
        self.call_after_refresh(self._load_test_ui)

    async def _load_test_ui(self) -> None:
        await self.query_one(PlaylistSidebar).ensure_loaded()
        await self.navigate_to("library", playlist_id="playlist-0")

    def _unmount_test_ui(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _ui_only_lifecycle(monkeypatch):
    monkeypatch.setattr(YTMPlayerApp, "on_mount", _KeyboardApp._mount_test_ui)
    monkeypatch.setattr(YTMPlayerApp, "on_unmount", _KeyboardApp._unmount_test_ui)


async def test_library_shortcut_focuses_playlists_without_toggling_page(sample_tracks):
    app = _KeyboardApp(sample_tracks)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        table = app.query_one("#library-tracks", TrackTable)
        table.focus()
        await pilot.pause()
        await pilot.press("g", "s")
        assert app.current_page_name == "search"

        await pilot.press("g", "l")
        await pilot.pause()
        playlists = app.query_one("#ps-playlists-list", ListView)
        assert app.current_page_name == "library"
        assert app.focused is playlists
        assert playlists.index is not None

        await pilot.press("g", "l")
        assert app.current_page_name == "library"
        assert app.focused is playlists


async def test_tab_and_shift_tab_move_between_tracks_and_playlists(sample_tracks):
    app = _KeyboardApp(sample_tracks)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        table = app.query_one("#library-tracks", TrackTable)
        playlists = app.query_one("#ps-playlists-list", ListView)
        table.focus()
        await pilot.pause()

        await pilot.press("tab")
        assert app.focused is playlists
        await pilot.press("shift+tab")
        assert app.focused is table


async def test_playlist_movement_and_selection_work_without_mouse(sample_tracks):
    app = _KeyboardApp(sample_tracks)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("g", "l")
        playlists = app.query_one("#ps-playlists-list", ListView)
        table = app.query_one("#library-tracks", TrackTable)
        playlists.index = 0

        await pilot.press("j")
        assert playlists.index == 1
        assert table.cursor_row == 0
        await pilot.press("G")
        assert playlists.index == 2
        await pilot.press("g", "g")
        assert playlists.index == 0
        await pilot.press("down")
        assert playlists.index == 1
        await pilot.press("enter")
        await pilot.pause()
        app.ytmusic.get_playlist.assert_awaited_with(
            "playlist-1", limit=500, order="recently_added"
        )

        await pilot.press("tab")
        assert app.focused is app.query_one("#library-tracks", TrackTable)
        await pilot.press("j", "enter")
        await pilot.pause()
        app.play_track.assert_awaited_once()
        assert app.play_track.await_args.args[0]["video_id"] == sample_tracks[1]["video_id"]


async def test_search_tab_reaches_persistent_playlists(sample_tracks):
    app = _KeyboardApp(sample_tracks)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("g", "s")
        app.query_one("#songs-table", TrackTable).focus()
        await pilot.pause()
        playlists = app.query_one("#ps-playlists-list", ListView)
        for _ in range(len(app.screen.focus_chain)):
            await pilot.press("tab")
            if app.focused is playlists:
                break
        assert app.focused is playlists
        playlists.index = 0
        await pilot.press("j")
        assert playlists.index == 1


async def test_library_shortcut_reveals_hidden_playlists(sample_tracks):
    app = _KeyboardApp(sample_tracks)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._toggle_playlist_sidebar()
        app.query_one("#library-tracks", TrackTable).focus()
        await pilot.pause()
        await pilot.press("g", "l")
        await pilot.pause()
        assert not app.query_one(PlaylistSidebar).has_class("hidden")
        assert app.focused is app.query_one("#ps-playlists-list", ListView)
