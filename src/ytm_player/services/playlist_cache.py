"""Playlist metadata and track cache backed by SQLite."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable

import aiosqlite

from ytm_player.config.paths import CACHE_DB, SECURE_FILE_MODE, secure_chmod

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS playlist_cache (
    playlist_id        TEXT PRIMARY KEY,
    title              TEXT,
    track_count        INTEGER,
    duration_seconds   INTEGER,
    tracks_json        TEXT NOT NULL,
    cached_track_count INTEGER NOT NULL,
    order_param        TEXT,
    fetched_at         TEXT DEFAULT (datetime('now')),
    metadata_json      TEXT NOT NULL
);
"""

# Cache entries older than this are always re-fetched.
_MAX_AGE_SECONDS = 7 * 24 * 3600  # 1 week


class PlaylistCacheService:
    """Cache playlist track lists in SQLite to avoid repeated slow API fetches."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or str(CACHE_DB)
        self._db: aiosqlite.Connection | None = None
        # Guards against duplicate concurrent fetches for the same playlist.
        self._fetching: dict[str, asyncio.Event] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def init(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        secure_chmod(self._db_path, SECURE_FILE_MODE)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_playlist(
        self,
        ytmusic: Any,
        playlist_id: str,
        order: str | None = None,
        force_refresh: bool = False,
        on_progress: Callable[[str], None] | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Return playlist data, using cache when possible.

        Returns:
            (playlist_data, needs_background_fetch) — if needs_background_fetch
            is True the caller should kick off ``background_fetch`` in a worker.
        """
        if self._db is None:
            # Cache not available — fall back to direct fetch.
            data = await ytmusic.get_playlist(playlist_id, limit=500, order=order)
            return data, False

        # 1. Force refresh — skip cache entirely.
        if force_refresh:
            if on_progress:
                on_progress("Refreshing playlist...")
            return await self._fetch_and_cache(ytmusic, playlist_id, order, on_progress)

        # 2. Check local cache.
        cached = await self._get_cached(playlist_id)

        if cached is not None:
            # 3a. Order mismatch — re-fetch.
            if order and cached["order_param"] != order:
                if on_progress:
                    on_progress("Loading playlist (re-sorting)...")
                return await self._fetch_and_cache(ytmusic, playlist_id, order, on_progress)

            # 3b. Age check — if older than 1 week, always re-fetch.
            age = self._cache_age_seconds(cached["fetched_at"])
            if age > _MAX_AGE_SECONDS:
                if on_progress:
                    on_progress("Updating stale playlist cache...")
                return await self._fetch_and_cache(ytmusic, playlist_id, order, on_progress)

            # 3c. Quick metadata probe to check freshness.
            try:
                if on_progress:
                    on_progress("Checking for updates...")
                probe = await ytmusic.get_playlist(playlist_id, limit=1)
                if self._is_stale(cached, probe):
                    if on_progress:
                        on_progress("Playlist updated — reloading...")
                    return await self._fetch_and_cache(ytmusic, playlist_id, order, on_progress)
            except Exception:
                logger.debug("Metadata probe failed for %r, using cache", playlist_id)

            # Cache is fresh — return it.
            return self._reconstruct(cached), False

        # 4. No cache — do a standard fetch and cache it.
        if on_progress:
            on_progress("Loading playlist...")
        return await self._fetch_and_cache(ytmusic, playlist_id, order, on_progress)

    async def background_fetch(
        self,
        ytmusic: Any,
        playlist_id: str,
        order: str | None = None,
    ) -> dict[str, Any] | None:
        """Fetch all tracks for a playlist and store in cache.

        Returns the full playlist data, or None on failure.
        Uses a concurrency guard so only one fetch per playlist runs at a time.
        """
        # Concurrency guard.
        if playlist_id in self._fetching:
            event = self._fetching[playlist_id]
            await event.wait()
            # Another fetch completed — return from cache.
            cached = await self._get_cached(playlist_id)
            return self._reconstruct(cached) if cached else None

        event = asyncio.Event()
        self._fetching[playlist_id] = event
        try:
            data = await ytmusic.get_playlist_uncapped(playlist_id, order=order)
            if data and data.get("tracks"):
                await self._store(playlist_id, data, order)
                return data
            return None
        except Exception:
            logger.warning("Background fetch failed for %r", playlist_id, exc_info=True)
            return None
        finally:
            event.set()
            self._fetching.pop(playlist_id, None)

    async def invalidate(self, playlist_id: str) -> None:
        """Remove a single playlist from cache."""
        if self._db is None:
            return
        await self._db.execute("DELETE FROM playlist_cache WHERE playlist_id = ?", (playlist_id,))
        await self._db.commit()

    async def clear(self) -> None:
        """Wipe all cached playlists."""
        if self._db is None:
            return
        await self._db.execute("DELETE FROM playlist_cache")
        await self._db.commit()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_and_cache(
        self,
        ytmusic: Any,
        playlist_id: str,
        order: str | None,
        on_progress: Callable[[str], None] | None,
    ) -> tuple[dict[str, Any], bool]:
        """Fetch with limit=500, cache it, and signal background fetch needed
        if there are likely more tracks."""
        try:
            data = await ytmusic.get_playlist(playlist_id, limit=500, order=order)
        except Exception:
            logger.warning("Playlist fetch failed for %r", playlist_id)
            return {}, False

        if not data:
            return {}, False

        tracks = data.get("tracks", [])
        track_count = data.get("trackCount")

        # If we got fewer tracks than trackCount, a background fetch is needed.
        needs_bg = track_count is not None and len(tracks) < track_count

        # For radio/mix playlists where trackCount is null but we hit the limit,
        # assume there are more.
        if track_count is None and len(tracks) >= 500:
            needs_bg = True

        # Only store if we have more tracks than the existing cache entry,
        # to avoid overwriting a full background-fetched cache with a partial result.
        existing = await self._get_cached(playlist_id)
        if not existing or len(tracks) >= existing["cached_track_count"]:
            await self._store(playlist_id, data, order)

        return data, needs_bg

    async def _get_cached(self, playlist_id: str) -> dict[str, Any] | None:
        """Load a cache entry from SQLite."""
        if self._db is None:
            return None
        async with self._db.execute(
            "SELECT * FROM playlist_cache WHERE playlist_id = ?", (playlist_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def _store(self, playlist_id: str, data: dict[str, Any], order: str | None) -> None:
        """Write playlist data to the cache."""
        if self._db is None:
            return

        tracks = data.get("tracks", [])
        metadata = {k: v for k, v in data.items() if k != "tracks"}

        await self._db.execute(
            """
            INSERT OR REPLACE INTO playlist_cache
                (playlist_id, title, track_count, duration_seconds,
                 tracks_json, cached_track_count, order_param,
                 fetched_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
            """,
            (
                playlist_id,
                data.get("title"),
                data.get("trackCount"),
                data.get("duration_seconds"),
                json.dumps(tracks, default=str),
                len(tracks),
                order,
                json.dumps(metadata, default=str),
            ),
        )
        await self._db.commit()

    def _is_stale(self, cached: dict[str, Any], probe: dict[str, Any]) -> bool:
        """Compare cached entry against a fresh metadata probe."""
        cached_tc = cached.get("track_count")
        probe_tc = probe.get("trackCount")

        # trackCount changed (for playlists that report it).
        if cached_tc is not None and probe_tc is not None and cached_tc != probe_tc:
            return True

        # Radio/mix playlists (trackCount is null) have randomized content —
        # duration_seconds changes on every request.  Rely on age-based expiry
        # and manual refresh instead of the unreliable duration signal.
        if cached_tc is None and probe_tc is None:
            return False

        # For regular playlists with a known trackCount, a duration shift
        # beyond 5% suggests content changed even if count stayed the same.
        cached_dur = cached.get("duration_seconds")
        probe_dur = probe.get("duration_seconds")
        if cached_dur and probe_dur:
            diff = abs(cached_dur - probe_dur)
            threshold = max(cached_dur, probe_dur) * 0.05
            if diff > threshold:
                return True

        return False

    def _reconstruct(self, cached: dict[str, Any]) -> dict[str, Any]:
        """Rebuild the full playlist dict from a cache row."""
        try:
            metadata = json.loads(cached["metadata_json"])
        except (json.JSONDecodeError, TypeError):
            metadata = {}
        try:
            tracks = json.loads(cached["tracks_json"])
        except (json.JSONDecodeError, TypeError):
            tracks = []
        metadata["tracks"] = tracks
        return metadata

    @staticmethod
    def _cache_age_seconds(fetched_at: str | None) -> float:
        """Return the age of a cache entry in seconds."""
        if not fetched_at:
            return float("inf")
        try:
            dt = datetime.fromisoformat(fetched_at).replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).total_seconds()
        except (ValueError, TypeError):
            return float("inf")
