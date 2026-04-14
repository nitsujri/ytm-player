"""Playlist metadata and track cache backed by SQLite.

Cache-first architecture: callers get cached data instantly via
``get_cached()``, then kick off ``refresh()`` in a background worker.
Each playlist has at most one active refresh task — concurrent callers
(including navigating away and back) reattach to the same in-flight
operation rather than starting a new one.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

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

_MAX_AGE_SECONDS = 7 * 24 * 3600  # 1 week


class PlaylistCacheService:
    """SQLite-backed playlist cache with per-playlist background refresh."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or str(CACHE_DB)
        self._db: aiosqlite.Connection | None = None
        self._refreshing: dict[str, asyncio.Task[dict[str, Any] | None]] = {}

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

    async def get_cached(self, playlist_id: str) -> dict[str, Any] | None:
        """Read from cache instantly. No API calls, no staleness checks.

        Returns None only if the playlist has never been cached.
        """
        row = await self._get_cached(playlist_id)
        if row is None:
            return None
        return self._reconstruct(row)

    async def refresh(
        self,
        ytmusic: Any,
        playlist_id: str,
        order: str | None = None,
        force: bool = False,
    ) -> dict[str, Any] | None:
        """Check staleness and update the cache if needed.

        At most one refresh task runs per playlist.  If a refresh is
        already in progress, the caller transparently awaits the same
        task — no duplicate API calls.

        Returns:
            Fresh playlist data if the cache was updated, or ``None`` if
            the cache was already fresh (caller can keep showing what
            ``get_cached()`` returned).
        """
        existing = self._refreshing.get(playlist_id)
        if existing is not None and not existing.done():
            return await asyncio.shield(existing)

        async def _task() -> dict[str, Any] | None:
            try:
                return await self._do_refresh(ytmusic, playlist_id, order, force)
            finally:
                self._refreshing.pop(playlist_id, None)

        task = asyncio.create_task(_task())
        self._refreshing[playlist_id] = task
        return await asyncio.shield(task)

    def is_refreshing(self, playlist_id: str) -> bool:
        """True if a background refresh is in progress for this playlist."""
        task = self._refreshing.get(playlist_id)
        return task is not None and not task.done()

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
    # Refresh logic
    # ------------------------------------------------------------------

    async def _do_refresh(
        self,
        ytmusic: Any,
        playlist_id: str,
        order: str | None,
        force: bool,
    ) -> dict[str, Any] | None:
        if self._db is None:
            data = await ytmusic.get_playlist(playlist_id, limit=500, order=order)
            return data or None

        cached = await self._get_cached(playlist_id)

        if cached is not None and not force:
            if order and cached["order_param"] != order:
                return await self._fetch_full(ytmusic, playlist_id, order)

            age = self._cache_age_seconds(cached["fetched_at"])
            if age > _MAX_AGE_SECONDS:
                return await self._fetch_full(ytmusic, playlist_id, order)

            try:
                probe = await ytmusic.get_playlist(playlist_id, limit=1)
                if self._is_stale(cached, probe):
                    return await self._fetch_full(ytmusic, playlist_id, order)
            except Exception:
                logger.debug("Metadata probe failed for %r, keeping cache", playlist_id)

            return None

        return await self._fetch_full(ytmusic, playlist_id, order)

    async def _fetch_full(
        self,
        ytmusic: Any,
        playlist_id: str,
        order: str | None,
    ) -> dict[str, Any] | None:
        """Fetch a playlist, cache it, and fetch all remaining tracks."""
        try:
            data = await ytmusic.get_playlist(playlist_id, limit=500, order=order)
        except Exception:
            logger.warning("Playlist fetch failed for %r", playlist_id)
            return None

        if not data or not data.get("tracks"):
            return None

        tracks = data["tracks"]
        track_count = data.get("trackCount")

        # Cache the initial batch so navigating away/back shows it.
        await self._store(playlist_id, data, order)

        needs_more = (track_count is not None and len(tracks) < track_count) or (
            track_count is None and len(tracks) >= 500
        )

        if needs_more:
            try:
                full = await ytmusic.get_playlist_uncapped(playlist_id, order=order)
                if full and full.get("tracks"):
                    await self._store(playlist_id, full, order)
                    return full
            except Exception:
                logger.debug("Uncapped fetch failed for %r, returning partial", playlist_id)

        return data

    # ------------------------------------------------------------------
    # SQLite helpers
    # ------------------------------------------------------------------

    async def _get_cached(self, playlist_id: str) -> dict[str, Any] | None:
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

    # ------------------------------------------------------------------
    # Staleness detection
    # ------------------------------------------------------------------

    def _is_stale(self, cached: dict[str, Any], probe: dict[str, Any]) -> bool:
        cached_tc = cached.get("track_count")
        probe_tc = probe.get("trackCount")

        if cached_tc is not None and probe_tc is not None and cached_tc != probe_tc:
            return True

        # Radio/mix playlists have randomized content — skip duration check.
        if cached_tc is None and probe_tc is None:
            return False

        cached_dur = cached.get("duration_seconds")
        probe_dur = probe.get("duration_seconds")
        if cached_dur and probe_dur:
            diff = abs(cached_dur - probe_dur)
            threshold = max(cached_dur, probe_dur) * 0.05
            if diff > threshold:
                return True

        return False

    def _reconstruct(self, cached: dict[str, Any]) -> dict[str, Any]:
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
        if not fetched_at:
            return float("inf")
        try:
            dt = datetime.fromisoformat(fetched_at).replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).total_seconds()
        except (ValueError, TypeError):
            return float("inf")
