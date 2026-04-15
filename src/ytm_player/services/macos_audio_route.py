"""macOS audio route monitor — pauses playback on output device change.

Detects any change to the system default output device (AirPods
disconnecting, AirPods switching to another device like an iPhone,
headphones being unplugged, output sink changes) and pauses ytm
playback when one happens while music is playing.

mpv's ``audio-device-list`` observer is unreliable for this on macOS:
when AirPods route away, the device often stays in the device list,
mpv silently follows the new system default, and playback continues
audibly through the built-in speakers. The authoritative signal is
CoreAudio's ``kAudioHardwarePropertyDefaultOutputDevice``, which we
subscribe to via ``AudioObjectAddPropertyListener`` so the change
fires the instant the hardware event lands — much faster than a
polling loop can catch it. That matters because AirPods/iPhone
AVRCP "play" commands also land within milliseconds of removal,
so ``recently_changed()`` needs a timestamp set by the time those
commands are dispatched.

A slow (2 Hz) backup poll is kept so we still notice changes if the
listener silently drops (older macOS releases were buggy around
hot-plug events).
"""

from __future__ import annotations

import asyncio
import ctypes
import logging
import sys
import time
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

RouteChangeCallback = Callable[[], Awaitable[None]]

_POLL_INTERVAL = 0.5
# Default window during which play commands arriving after a route
# change are considered spurious (AirPods AVRCP, in-ear detection).
_DEFAULT_SUPPRESSION_WINDOW = 3.0


def _fourcc(s: str) -> int:
    """Convert a 4-char ASCII code to its CoreAudio uint32 constant."""
    return (ord(s[0]) << 24) | (ord(s[1]) << 16) | (ord(s[2]) << 8) | ord(s[3])


class _AudioObjectPropertyAddress(ctypes.Structure):
    _fields_ = [
        ("mSelector", ctypes.c_uint32),
        ("mScope", ctypes.c_uint32),
        ("mElement", ctypes.c_uint32),
    ]


# CoreAudio listener signature:
#   OSStatus (*AudioObjectPropertyListenerProc)(
#       AudioObjectID, UInt32, const AudioObjectPropertyAddress*, void*);
_LISTENER_PROC = ctypes.CFUNCTYPE(
    ctypes.c_int32,
    ctypes.c_uint32,
    ctypes.c_uint32,
    ctypes.POINTER(_AudioObjectPropertyAddress),
    ctypes.c_void_p,
)


class _CoreAudio:
    """Minimal ctypes binding for the CoreAudio calls we need."""

    _K_SYSTEM_OBJECT = 1
    _K_DEFAULT_OUTPUT = _fourcc("dOut")  # kAudioHardwarePropertyDefaultOutputDevice
    _K_SCOPE_GLOBAL = _fourcc("glob")  # kAudioObjectPropertyScopeGlobal
    _K_ELEMENT_MAIN = 0  # kAudioObjectPropertyElementMain

    def __init__(self) -> None:
        self._lib = ctypes.CDLL("/System/Library/Frameworks/CoreAudio.framework/CoreAudio")
        self._lib.AudioObjectGetPropertyData.argtypes = [
            ctypes.c_uint32,
            ctypes.POINTER(_AudioObjectPropertyAddress),
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_void_p,
        ]
        self._lib.AudioObjectGetPropertyData.restype = ctypes.c_int32
        self._lib.AudioObjectAddPropertyListener.argtypes = [
            ctypes.c_uint32,
            ctypes.POINTER(_AudioObjectPropertyAddress),
            _LISTENER_PROC,
            ctypes.c_void_p,
        ]
        self._lib.AudioObjectAddPropertyListener.restype = ctypes.c_int32
        self._lib.AudioObjectRemovePropertyListener.argtypes = [
            ctypes.c_uint32,
            ctypes.POINTER(_AudioObjectPropertyAddress),
            _LISTENER_PROC,
            ctypes.c_void_p,
        ]
        self._lib.AudioObjectRemovePropertyListener.restype = ctypes.c_int32

    def get_default_output_device(self) -> int | None:
        """Return the AudioDeviceID of the current system default output."""
        addr = _AudioObjectPropertyAddress(
            self._K_DEFAULT_OUTPUT,
            self._K_SCOPE_GLOBAL,
            self._K_ELEMENT_MAIN,
        )
        device_id = ctypes.c_uint32(0)
        size = ctypes.c_uint32(ctypes.sizeof(device_id))
        status = self._lib.AudioObjectGetPropertyData(
            self._K_SYSTEM_OBJECT,
            ctypes.byref(addr),
            0,
            None,
            ctypes.byref(size),
            ctypes.byref(device_id),
        )
        if status != 0:
            return None
        return device_id.value

    def add_default_output_listener(self, proc: Any) -> int:
        addr = _AudioObjectPropertyAddress(
            self._K_DEFAULT_OUTPUT,
            self._K_SCOPE_GLOBAL,
            self._K_ELEMENT_MAIN,
        )
        return int(
            self._lib.AudioObjectAddPropertyListener(
                self._K_SYSTEM_OBJECT,
                ctypes.byref(addr),
                proc,
                None,
            )
        )

    def remove_default_output_listener(self, proc: Any) -> int:
        addr = _AudioObjectPropertyAddress(
            self._K_DEFAULT_OUTPUT,
            self._K_SCOPE_GLOBAL,
            self._K_ELEMENT_MAIN,
        )
        return int(
            self._lib.AudioObjectRemovePropertyListener(
                self._K_SYSTEM_OBJECT,
                ctypes.byref(addr),
                proc,
                None,
            )
        )


class MacOSAudioRouteMonitor:
    """Monitors the macOS default output device and notifies on change.

    Uses a CoreAudio property listener for instant notification; falls
    back to a 2 Hz poll so we still notice if the listener drops an
    event. The *on_route_change* callback is invoked on every detected
    change and is expected to pause playback and release any macOS
    media control state so ytm-player doesn't fight with whichever
    other source (iPhone, Apple Music, etc.) is taking over the
    active audio route.

    ``recently_changed()`` exposes a time window after the most recent
    change so play commands that arrive via MPRemoteCommandCenter
    (AirPods AVRCP, Handoff) immediately after a route change can be
    suppressed — they'd otherwise flip a paused player back to playing
    before :meth:`~MacOSMediaService.handoff_to_system` has had time
    to remove the command handlers.
    """

    def __init__(
        self,
        on_route_change: RouteChangeCallback,
        suppression_window: float = _DEFAULT_SUPPRESSION_WINDOW,
    ) -> None:
        self._on_route_change = on_route_change
        self._suppression_window = suppression_window
        self._task: asyncio.Task | None = None
        self._coreaudio: _CoreAudio | None = None
        self._last_device_id: int | None = None
        self._last_change_time: float = 0.0  # monotonic
        self._loop: asyncio.AbstractEventLoop | None = None
        # Hold a reference to the C callback trampoline so it isn't
        # garbage-collected while CoreAudio still holds the pointer.
        self._listener_proc: Any = None
        self._listener_registered = False

    def start(self) -> bool:
        """Begin monitoring. No-op on non-macOS or if already running."""
        if sys.platform != "darwin" or self._task is not None:
            return False
        try:
            self._coreaudio = _CoreAudio()
            self._last_device_id = self._coreaudio.get_default_output_device()
        except Exception:
            logger.debug("CoreAudio unavailable; route monitor disabled", exc_info=True)
            return False

        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("No running event loop; route monitor needs one")
            return False

        # Register the CoreAudio property listener (immediate notification).
        try:
            self._listener_proc = _LISTENER_PROC(self._on_coreaudio_callback)
            status = self._coreaudio.add_default_output_listener(self._listener_proc)
            if status == 0:
                self._listener_registered = True
            else:
                logger.debug(
                    "AudioObjectAddPropertyListener failed (status=%s); falling back to poll-only",
                    status,
                )
        except Exception:
            logger.debug("CoreAudio property listener registration failed", exc_info=True)

        self._task = asyncio.create_task(self._poll_loop())
        logger.info(
            "macOS audio route monitor started (device id=%s, listener=%s)",
            self._last_device_id,
            self._listener_registered,
        )
        return True

    async def stop(self) -> None:
        if self._listener_registered and self._coreaudio is not None:
            try:
                self._coreaudio.remove_default_output_listener(self._listener_proc)
            except Exception:
                logger.debug("Failed to remove CoreAudio listener", exc_info=True)
            self._listener_registered = False
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception):
            pass
        self._task = None

    def recently_changed(self, window: float | None = None) -> bool:
        """Return True if the default output changed within *window* seconds.

        Thread-safe — callable from any thread. Used by play-command
        handlers to discard spurious AVRCP / in-ear-detection play
        commands that arrive right after a route change.
        """
        if self._last_change_time == 0.0:
            return False
        if window is None:
            window = self._suppression_window
        return (time.monotonic() - self._last_change_time) < window

    # ── Internals ───────────────────────────────────────────────────

    def _on_coreaudio_callback(
        self,
        _object_id: int,
        _num_addresses: int,
        _addresses: Any,
        _client_data: Any,
    ) -> int:
        """CoreAudio listener callback. Runs on the audio daemon thread.

        Must return quickly. We mark the change time synchronously
        (atomic Python attribute write) so ``recently_changed()``
        reflects it immediately, then marshal the heavier work onto
        the event loop.
        """
        # Set the timestamp first — this is the critical hand-off.
        # Any play command arriving after this point can now see that
        # a route change just happened.
        self._last_change_time = time.monotonic()
        loop = self._loop
        if loop is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(self._dispatch_change)
            except RuntimeError:
                pass
        return 0

    def _dispatch_change(self) -> None:
        """Poll the device id and invoke the async callback on the loop."""
        if self._coreaudio is None:
            return
        current = self._coreaudio.get_default_output_device()
        if current is None or current == self._last_device_id:
            return
        logger.info(
            "Audio route changed (device id %s → %s)",
            self._last_device_id,
            current,
        )
        self._last_device_id = current
        # _last_change_time may already be set by the listener
        # callback, but refresh here so the poll path also sets it
        # when the listener isn't active.
        self._last_change_time = time.monotonic()
        try:
            fut = asyncio.ensure_future(self._on_route_change())
        except Exception:
            logger.exception("Audio route change callback scheduling failed")
            return

        def _done(task: asyncio.Task) -> None:
            exc = task.exception()
            if exc is not None:
                logger.debug("Audio route change callback failed", exc_info=exc)

        fut.add_done_callback(_done)

    async def _poll_loop(self) -> None:
        """Backup polling loop in case the CoreAudio listener drops events."""
        assert self._coreaudio is not None
        try:
            while True:
                await asyncio.sleep(_POLL_INTERVAL)
                current = self._coreaudio.get_default_output_device()
                if current is None or current == self._last_device_id:
                    continue
                logger.info(
                    "Audio route changed via poll (device id %s → %s)",
                    self._last_device_id,
                    current,
                )
                self._last_device_id = current
                self._last_change_time = time.monotonic()
                try:
                    await self._on_route_change()
                except Exception:
                    logger.exception("Audio route change callback failed")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Audio route monitor crashed")
