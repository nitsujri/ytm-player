# Changelog

All notable changes to ytm-player are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/).

---

### v1.5.2 (2026-03-17)

**Fixes**
- Fixed RTL lyrics displaying in wrong word order — disabled manual RTL reordering which was reversing text on both BiDi and non-BiDi terminals. Added `bidi_mode` config option (`auto`/`reorder`/`passthrough`) for users who need explicit control
- Fixed lyrics sidebar ignoring custom `lyrics_played`/`lyrics_current`/`lyrics_upcoming` theme colors — CSS was wired to wrong variables (`$success`, `$text-muted`, `$text` instead of `$lyrics-*`)
- Fixed album art placeholder and context page cursor using hard-coded colors instead of theme — all UI colors now flow through `ThemeColors` for full theme customization support

---

### v1.5.1 (2026-03-12)

**New**
- Multi-account auth support — `ytm setup` now handles Google accounts logged into multiple YouTube Music profiles, probing all `x-goog-authuser` indices automatically (thanks @glywil, PR [#15](https://github.com/peternaame-boop/ytm-player/pull/15))
- Gentoo packaging — available in the GURU overlay via `emerge media-sound/ytm-player` (thanks @dsafxP, PR [#21](https://github.com/peternaame-boop/ytm-player/pull/21))

**Fixes**
- Fixed `nix build` failing — added missing `pillow` to core Nix deps, resolved `python-mpv` vs `mpv` dist-info name mismatch with `pythonRemoveDeps`, added `transliteration` optional dep (fixes [#18](https://github.com/peternaame-boop/ytm-player/issues/18), thanks @muhmud)
- Fixed Browse page showing "Unknown" artist in notifications — raw API items now normalized before playback (fixes [#19](https://github.com/peternaame-boop/ytm-player/issues/19), thanks @Gimar250, PR [#20](https://github.com/peternaame-boop/ytm-player/pull/20))
- Fixed `d d` / `delete` keybind not removing tracks on the Queue page — was matching `TRACK_ACTIONS` instead of `DELETE_ITEM` (fixes [#22](https://github.com/peternaame-boop/ytm-player/issues/22), thanks @CarterSnich)

---

### v1.5.0 (2026-03-09)

**Refactor**
- Decomposed `app.py` (2000+ lines) into a package with 7 focused mixins — playback, navigation, keys, session, sidebar, track actions, MPRIS, IPC. Zero behavioral changes; all 370 tests pass unchanged.

**New**
- Lyrics transliteration — toggle ASCII transliteration of non-Latin lyrics with `T` (Shift+T), useful for Japanese, Korean, Arabic, Cyrillic, etc. Requires optional `anyascii` package (thanks @Kineforce, [#14](https://github.com/peternaame-boop/ytm-player/issues/14))
- Add to Library button — albums and playlists that aren't in your library now show a clickable `[+ Add to Library]` button on their context page
- Delete/remove playlist confirmation — deleting a playlist now asks for confirmation first; also supports removing non-owned playlists from your library
- Search mode toggle is now clickable — click the `Music`/`All` label to toggle (was keyboard-only before)
- Page state preservation — Search, Browse, Liked Songs, and Recently Played pages now remember their state (query, results, cursor position, active tab) when navigating away and back

**Fixes**
- Fixed RTL text word order — restored BiDi reordering for Arabic/Hebrew track titles, artists, and lyrics (UAX #9 algorithm)
- Fixed right-click targeting wrong track — right-click now opens actions for the row under the cursor, not the previously highlighted row (thanks @glywil, PR [#16](https://github.com/peternaame-boop/ytm-player/pull/16))
- Fixed artist search results showing "Unknown" instead of artist name
- Fixed radio tracks crashing playback — radio API responses are now normalized before adding to queue
- Fixed browse page items not opening — capitalized `resultType` values and missing routing for radio/mix entries
- Fixed session restore crash when saved tracks become unavailable (deleted/region-locked videos)
- Fixed actions popup crash when album field is a plain string instead of dict (thanks @glywil, PR [#16](https://github.com/peternaame-boop/ytm-player/pull/16))
- Fixed double-click playing a track twice (1-second debounce)
- Fixed back navigation ping-ponging between two pages
- Fixed lyrics sidebar performance — batch-mount widgets instead of mounting individually
- Fixed transliteration toggle highlight flash — forces immediate lyrics re-sync after toggle
- Transliteration toggle state now persists across restarts via session.json
- Sidebar refreshes after adding or removing playlists from library

---

### v1.4.0 (2026-03-07)

**New**
- Native macOS media key and Now Playing support — hardware media keys (play/pause, next, previous) now work via Quartz event taps, and track metadata appears in macOS Control Center (thanks @Thayrov, PR [#12](https://github.com/peternaame-boop/ytm-player/pull/12))

**Fixes**
- Documented how to install optional features for AUR users — pip doesn't work on Arch due to PEP 668 (fixes [#13](https://github.com/peternaame-boop/ytm-player/issues/13))

---

### v1.3.6 (2026-03-05)

**Windows Fix**
- Fixed mpv crash inside Textual TUI on Windows — locale was being set via the legacy `msvcrt.dll` CRT, but Python 3.12+ uses `ucrtbase.dll`, so the `setlocale(LC_NUMERIC, "C")` call had no effect and mpv refused to initialize (access violation on null handle)
- Fixed mpv DLL not found on Windows when installed via scoop/chocolatey — auto-locates `libmpv-2.dll` in common install directories
- Improved error messages for service init failures

### v1.3.4 (2026-03-05)

**Windows Compatibility**
- Fixed crash on Windows caused by config file encoding (em-dash written as cp1252 instead of UTF-8)
- Added TCP localhost IPC for Windows (Unix sockets unavailable), with proper stale port cleanup
- Fixed PID liveness check on Windows using `OpenProcess` API
- Config now stored in `%APPDATA%\ytm-player`, cache in `%LOCALAPPDATA%\ytm-player`
- Fixed crash log path, libc detection (`msvcrt`), and `ytm config` command for Windows
- Added `encoding="utf-8"` to all file I/O (Windows defaults to cp1252)
- Added clipboard support for Windows (`Set-Clipboard`) and macOS (`pbcopy`)
- Corrupted config files are backed up to `.toml.bak` before recreating defaults

### v1.3.3 (2026-03-05)

**Bug Fixes**
- Disabled media key listener on macOS — pynput can't intercept keys, causing previous track to open iTunes. Media keys on macOS will be implemented properly with MPRemoteCommandCenter in a future release.
- Suppressed noisy warnings on macOS startup ("dbus-next not installed", "process not trusted")

### v1.3.1 (2026-03-05)

**New**
- Cross-platform media key support — play/pause, next, and previous media keys now work on macOS and Windows via `pynput` (Linux already supported via MPRIS)
- Pillow (album art) is now a default dependency — no longer requires `pip install ytm-player[images]`

### v1.3.0 (2026-03-05)

**New**
- `ytm setup --manual` — skip browser detection, paste request headers directly (thanks @uhs-robert, [#10](https://github.com/peternaame-boop/ytm-player/issues/10))
- `ytm setup --browser <name>` — extract cookies from a specific browser (chrome, firefox, brave, etc.)
- Theme variables `$surface` and `$text` now properly defined — fixes unstyled popups, sidebars, and scrollbars (thanks @ahloiscreamo, [#6](https://github.com/peternaame-boop/ytm-player/issues/6))
- NixOS packaging — `flake.nix` with `ytm-player` and `ytm-player-full` packages, dev shell, and overlay
- Free-tier support — tracks without a video ID (Premium-only) are now filtered from playlists/albums/search with an "unavailable tracks hidden" notice, instead of silently failing on click

**Bug Fixes**
- Fixed MPRIS crash (`SignatureBodyMismatchError`) when track metadata contains None values (thanks @markvincze, [#9](https://github.com/peternaame-boop/ytm-player/issues/9))
- Fixed large playlists only loading 200-300 songs — now fetches all tracks via ytmusicapi pagination (thanks @bananarne, [#5](https://github.com/peternaame-boop/ytm-player/issues/5))
- Fixed search results missing `video_id` — songs from search couldn't play (thanks @firedev, PR [#4](https://github.com/peternaame-boop/ytm-player/pull/4))
- Fixed browse/charts page same missing normalization bug
- Fixed macOS `Player` init crash — hardcoded `libc.so.6` replaced with platform-aware detection (thanks @hanandewa5, PR [#2](https://github.com/peternaame-boop/ytm-player/pull/2))
- Fixed auth validation crashing with raw tracebacks on network errors — now shows friendly message with recovery suggestion (thanks @CarterSnich [#7](https://github.com/peternaame-boop/ytm-player/issues/7), @Tohbuu [#11](https://github.com/peternaame-boop/ytm-player/issues/11))
- Rewrote auth validation to use `get_account_info()` instead of monkey-patching — more reliable across platforms and ytmusicapi versions
- Unplayable tracks (no video ID) now auto-skip to the next track instead of stopping playback dead

---

### v1.2.11 (2026-03-03)

**New**
- yt-dlp configuration support: `cookies.txt` auth, `remote_components`, `js_runtimes` via `[yt_dlp]` config section (thanks @gitiy1, [PR #1](https://github.com/peternaame-boop/ytm-player/pull/1))

### v1.2.10 (2026-03-03)

**Bug Fixes**
- Fixed RTL text (Arabic/Hebrew) in track table columns — added BiDi isolation (LRI/PDI) so RTL album/artist names don't bleed into adjacent columns

### v1.2.9 (2026-03-02)

**New**
- Published to PyPI — install with `pip install ytm-player` or `pipx install ytm-player`

**Bug Fixes**
- Fixed track auto-advance stopping after song ends — three root causes: mpv end-file reason read from wrong event object, event loop reference permanently lost under thread race condition, and `CancelledError` not caught in track-end handler
- Fixed RTL text (Arabic/Hebrew) display — removed manual word-reordering that double-reversed text on terminals with native BiDi support; added Unicode directional isolation to prevent RTL titles from displacing playback bar controls
- Fixed shuffle state corrupting queue after clear, and `jump_to()` desyncing the current index when shuffle is on
- Fixed column resize triggering sort, and Title column not staying at user-set width

### v1.2.4 (2026-02-17)

**Bug Fixes**
- Fixed intermittent playback stopping mid-queue — consecutive stream failures (stale yt-dlp session, network hiccup) now reset the stream resolver automatically, preventing the queue index from advancing past all remaining tracks
- Fixed playlists appearing empty after prolonged use — YTMusic API client now auto-reinitializes after 3 consecutive failures (handles expired sessions/cookies)
- Fixed misleading "Queue is empty" message when queue has tracks but playback index reached the end — now says "End of queue"

### v1.2.3 (2026-02-17)

**Bug Fixes**
- Fixed MPRIS silently disabled on Python 3.14 — `from __future__ import annotations` caused dbus-next to reject `-> None` return types, disabling media keys and desktop player widgets
- Fixed RTL lyrics line-wrap reading bottom-to-top — long lines are now pre-wrapped in logical order before reordering, so sentence start is on top

### v1.2.2 (2026-02-15)

**Bug Fixes**
- Fixed play/pause doing nothing after session restore — player had no stream loaded so toggling pause was a no-op; now starts playback from the restored queue position
- Fixed MPRIS play/pause also being a no-op after session restore (same root cause)
- Fixed RTL (Hebrew, Arabic, etc.) lyrics displaying in wrong order — segment-level reordering now renders bidirectional text correctly
- Fixed lyrics sidebar crash from dict-style access on LyricLine objects — switched to attribute access
- Fixed lyrics sidebar unnecessarily reloading when reopened for the same track

**Features**
- Right-click on playback bar (album art or track info) now opens the track actions popup, matching right-click behavior on track tables

### v1.2.1 (2026-02-14)

**Features**
- Synced (timestamped) lyrics — lyrics highlight and auto-scroll with the song in real time
- Click-to-seek on lyrics — click any synced lyric line to jump to that part of the song
- LRCLIB.net fallback — when YouTube Music doesn't provide synced lyrics, fetches them from LRCLIB.net (no API key needed)
- Lyrics auto-center — current lyric line stays centered in the viewport as the song plays

**Bug Fixes**
- Fixed crash on song change with both sidebars open — Textual's `LoadingIndicator` timer raced with widget pruning during track transitions
- Fixed crash from unhandled exceptions in player event callbacks — sync callbacks dispatched via `call_soon_threadsafe` now wrapped in error handlers
- Wrapped `notify()` and `_prefetch_next_track()` in `_on_track_change` with try/except to prevent crashes during app transitions
- Lyrics sidebar always starts closed on launch regardless of previous session state
- Fixed synced lyrics not being requested — `timestamps=True` now passed to ytmusicapi with automatic fallback to plain text

### v1.2.0 (2026-02-14)

**Features**
- Persistent playlist sidebar (left) — visible across all views, toggleable per-view with state memory (`Ctrl+e`)
- Persistent lyrics sidebar (right) — synced lyrics with auto-scroll, replaces the old full-page Lyrics view (`l` to toggle)
- Header bar with toggle buttons for both sidebars
- Pinned navigation items (Liked Songs, Recently Played) in the playlist sidebar
- Per-view sidebar state — sidebar visibility is remembered per page and restored on navigation
- Lyrics sidebar registers player events lazily and skips updates when hidden for performance

**Removed**
- Lyrics page — replaced entirely by the lyrics sidebar
- Lyrics button from footer bar — use header bar toggle or `l` key instead

---

### v1.1.3 (2026-02-14)

**Features**
- Click column headers to sort — click any column header (Title, Artist, Album, Duration, #) to sort; click again to reverse
- Drag-to-resize columns — drag column header borders to adjust widths; Title column auto-fills remaining space
- Playlist sort order — requests "recently added" order from YouTube Music API when loading playlists
- `#` column preserves original playlist position and can be clicked to reset sort order

**Bug Fixes**
- Fixed click-to-sort not working (ColumnKey.value vs str(ColumnKey) mismatch)
- Fixed horizontal scroll position resetting when sorting
- Fixed session restore with shuffle — queue is now populated before enabling shuffle so the saved index points at the correct track
- Fixed `jump_to_real()` fallback when track not in shuffle order (was a silent no-op, now inserts into shuffle order)
- Fixed crash on Python 3.14 from dbus-next annotation parsing (MPRIS gracefully disables)
- Pinned Textual dependency to `>=7.0,<8.0` to protect against internal API breakage

### v1.1.2 (2026-02-14)

**Features**
- Shuffle-aware playlist playback — double-clicking a playlist with shuffle on now starts from a random track instead of always the first
- Table sorting — sort any track list by Title (`s t`), Artist (`s a`), Album (`s A`), Duration (`s d`), or reverse (`s r`)
- Session resume — on startup, restores last queue position and shows the track in the footer (without auto-playing)
- Quit action (`q` / `Ctrl+Q`) — clean exit that clears resume state; unclean exits (terminal close/kill) preserve it

**Bug Fixes**
- Fixed queue position desync when selecting tracks with shuffle enabled (all pages: Library, Context, Liked Songs, Recently Played)
- Fixed search mode toggle showing empty box due to Rich markup interpretation (`[Music]` → `Music`)

### v1.1.1 (2026-02-13)

**Bug Fixes**
- Fixed right-click on track table triggering playback instead of only opening context menu
- Fixed auto-advance bug: songs after the 2nd track would not play due to stale `_end_file_skip` counter
- Fixed thread-safe skip counter — check+increment now atomic under lock
- Fixed duplicate end-file events causing track skipping (debounce guard)
- Fixed `player.play()` failure leaving stale `_current_track` state
- Fixed unhandled exceptions in stream resolution crashing the playback chain
- Fixed `player.play()` exceptions silently stopping all playback
- Fixed Browse page crash from unawaited async mount operations
- Fixed API error tracebacks polluting TUI with red stderr overlay
- Reset skip counter on mpv crash recovery
- Fixed terminal image protocol detection (`TERM_FEATURES` returning wrong protocol)
- Fixed encapsulation break (cache private method called from app)
- Always-visible Lyrics button in footer bar (dimmed when no track playing, active during playback)
- Clicking the active footer page navigates back to the previous page
- Library remembers selected playlist when navigating away and back
- Click outside popups to dismiss — actions menu and Spotify import close when clicking the background

### v1.1.0 (2026-02-12)

**Features**
- Liked Songs page (`g y`) — browse and play your liked music
- Recently Played page (`g r`) — local history from SQLite
- Download for offline — right-click any track → "Download for Offline"
- Discord Rich Presence — show what you're listening to (optional, `pip install -e ".[discord]"`)
- Last.fm scrobbling — automatic scrobbling + Now Playing (optional, `pip install -e ".[lastfm]"`)
- Gapless playback enabled by default
- Queue persistence across restarts (saved in session.json)
- Track change notifications wired to `[notifications]` config section
- New config sections: `[discord]`, `[lastfm]`, `[playback].gapless`, `[playback].api_timeout`
- Configurable column widths via `[ui]` settings (`col_index`, `col_title`, `col_artist`, `col_album`, `col_duration`)
- Liked Songs and Recently Played pinned in library sidebar

**Security & Stability**
- IPC socket security hardening (permissions, command whitelist, input validation)
- File permissions hardened to 0o600 across all config/state files
- Thread safety for queue manager (prevents race conditions)
- mpv crash detection and automatic recovery
- Auth validation distinguishes network errors from invalid credentials
- Disk-full (OSError) handling in cache and history managers
- API timeout handling (15s default, prevents TUI hangs on slow networks)

**Performance**
- Batch DELETE for cache eviction (replaces per-row deletes)
- Deferred cache-hit commits (every 10 hits instead of every hit)
- Reuse yt-dlp instance across stream resolves (was creating new per call)
- Concurrent Spotify import matching with ThreadPoolExecutor
- Stream URL expiry checks before playback

**Testing & CI**
- GitHub Actions CI pipeline (ruff lint + pytest with coverage)
- 231 tests covering queue, IPC, stream resolver, cache, history, auth, downloads, Discord RPC, Last.fm, and settings

---

### v1.0.0 (2026-02-07)

- Initial release
- Full TUI with 7 pages (Library, Search, Browse, Context, Lyrics, Queue, Help)
- Vim-style keybindings with multi-key sequences and count prefixes
- Audio playback via mpv with shuffle, repeat, queue management
- Predictive search with music-first mode
- Spotify playlist import (API + scraper)
- Play and search history in SQLite
- Audio cache with LRU eviction (1GB default)
- Album art with colored half-block rendering
- MPRIS D-Bus integration for media key support
- Unix socket IPC for CLI↔TUI control
- CLI subcommands for headless usage
- TOML configuration for settings, keybindings, and theme
