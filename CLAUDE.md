# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

ytm-player is a YouTube Music TUI client built with Python 3.12+ and [Textual](https://textual.textualize.io/). It provides vim-style navigation, synced lyrics, playlist management, queue control, and integrations (MPRIS, Discord, Last.fm, Spotify import). Audio playback uses mpv via python-mpv; stream URLs are resolved via yt-dlp.

## Commands

```bash
# Install (editable, all features + dev tools)
pip install -e ".[spotify,mpris,images,discord,lastfm,dev]"

# Run the TUI
ytm

# Lint
ruff check src/ tests/
ruff format --check src/ tests/

# Auto-format
ruff format src/ tests/

# Tests
pytest
pytest --cov=ytm_player --cov-report=term-missing

# Single test file
pytest tests/test_services/test_queue.py

# Single test
pytest tests/test_services/test_queue.py::test_add_track -v
```

System dependency: `mpv` must be installed (`sudo pacman -S mpv` on Arch).

## Architecture

**Entry point:** `ytm` CLI command → `src/ytm_player/cli.py` (Click). Running `ytm` with no args launches the Textual TUI app (`app.py`). Subcommands (`ytm search`, `ytm play`, etc.) communicate with a running TUI instance via Unix socket IPC (`ipc.py`).

**Three-layer structure:**

- **`services/`** — Backend singletons: `Player` (mpv wrapper), `QueueManager` (shuffle/repeat), `StreamResolver` (yt-dlp), `YTMusicService` (ytmusicapi), `CacheManager` (LRU audio cache), `HistoryManager` (SQLite via aiosqlite), `AuthManager` (browser cookie extraction), `lrclib` (LRCLIB.net lyrics fallback). Optional: `MPRISService`, `DiscordRPC`, `LastFMService`.
- **`ui/`** — Textual widgets: `pages/` (library, search, browse, context, queue, etc.), `sidebars/` (playlist list, synced lyrics), `popups/` (modals), `widgets/` (track table, progress bar, album art). Styling via `theme.py` with CSS variables.
- **`config/`** — `Settings` dataclass loaded from `~/.config/ytm-player/config.toml`. `KeyMap` system supports multi-key vim sequences and count prefixes. All paths centralized in `paths.py`.

**Key patterns:**

- **Event-driven playback:** `Player` emits `PlayerEvent` enums (`TRACK_END`, `TRACK_CHANGE`, etc.) dispatched to the Textual event loop via `call_soon_threadsafe`. The app registers callbacks to update UI.
- **Thread safety:** `Player` and `QueueManager` are singletons with `threading.Lock`. Player events bridge from mpv's callback thread to asyncio.
- **Track format:** All services use a standardized track dict with keys: `video_id`, `title`, `artist`, `artists` (list of dicts with `name`/`id`), `album`, `album_id`, `duration` (seconds, int or None), `thumbnail_url`, `is_video`. The `normalize_tracks()` function in `utils/formatting.py` converts inconsistent ytmusicapi response shapes into this format — always use it when ingesting API data.
- **Session persistence:** Volume, queue contents, shuffle/repeat state saved to `session.json` and restored on startup.
- **Prefetching:** Next track's stream URL is resolved in background for instant skip.
- **Page navigation:** `app.py` manages a nav stack (max 20) with `_push_page()`/`_pop_page()`. Each page widget implements `handle_action(action, count)` for vim-style keybinding dispatch.
- **LC_NUMERIC quirk:** `cli.py` forces `LC_NUMERIC=C` at import time — mpv segfaults without it. Don't remove this.

## Pre-commit Checklist

**MANDATORY before every commit — run BOTH:**
```bash
ruff format src/ tests/
ruff check src/ tests/
```
`ruff check` alone is NOT enough. `ruff format` catches line length and style issues that `ruff check` does not. Always format first, then lint.

## Ruff Configuration

- Line length: 100, target Python 3.12
- Rules: E, F, I, N, W (E501 ignored — line length handled separately)
- Per-file exemptions: `mpris.py` (N802, N803, F821, F722 for D-Bus conventions), `spotify_import.py` (N803)
- CI pins `ruff==0.15.1` — match this locally to avoid lint drift

## Testing

- pytest with `asyncio_mode = "auto"` — async test functions are auto-detected, no `@pytest.mark.asyncio` needed
- UI code (`src/ytm_player/ui/*`) is excluded from coverage; services and config are covered
- Coverage floor: 10%
- Heavy mocking of mpv, ytmusicapi, yt-dlp, D-Bus — tests never hit real APIs or require mpv installed
- Test fixtures in `tests/conftest.py`: `sample_track`/`sample_tracks` use `_make_track()` helper to create standardized track dicts; `queue_manager` provides a fresh `QueueManager` instance
- CI runs on GitHub Actions (ubuntu, Python 3.12): ruff lint + format check, then pytest with coverage

## AUR Package

This project is published on AUR as `ytm-player-git`. The PKGBUILD lives in `aur/PKGBUILD`.

**When pushing changes to GitHub, always update the AUR package too.** The process:

1. If it's a new version: bump `__version__` in `src/ytm_player/__init__.py`, tag it (`git tag vX.Y.Z`), push the tag
2. If dependencies changed: update `depends`/`optdepends`/`makedepends` in `aur/PKGBUILD`
3. Push the AUR update:

```bash
git clone ssh://aur@aur.archlinux.org/ytm-player-git.git /tmp/ytm-player-aur
cp aur/PKGBUILD /tmp/ytm-player-aur/
cd /tmp/ytm-player-aur && makepkg --printsrcinfo > .SRCINFO
git add PKGBUILD .SRCINFO && git commit -m "Update to vX.Y.Z" && git push
rm -rf /tmp/ytm-player-aur
```

AUR package URL: https://aur.archlinux.org/packages/ytm-player-git

## Future Plans

- **PyPI publishing** — planned but not yet set up. The project already has a proper `pyproject.toml` with hatchling, so `pipx install ytm-player` is the target. Distribution is currently AUR + GitHub only.
