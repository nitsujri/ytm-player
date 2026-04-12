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
poll on a background asyncio task.
"""

from __future__ import annotations

import asyncio
import ctypes
import logging
import sys
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

RouteChangeCallback = Callable[[], Awaitable[None]]

# Poll interval — fast enough to feel responsive when AirPods drop,
# slow enough to be invisible in CPU usage. CoreAudio queries are
# microseconds.
_POLL_INTERVAL = 1.0


def _fourcc(s: str) -> int:
    """Convert a 4-char ASCII code to its CoreAudio uint32 constant."""
    return (ord(s[0]) << 24) | (ord(s[1]) << 16) | (ord(s[2]) << 8) | ord(s[3])


class _AudioObjectPropertyAddress(ctypes.Structure):
    _fields_ = [
        ("mSelector", ctypes.c_uint32),
        ("mScope", ctypes.c_uint32),
        ("mElement", ctypes.c_uint32),
    ]


class _CoreAudio:
    """Minimal ctypes binding for the one CoreAudio call we need."""

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


class MacOSAudioRouteMonitor:
    """Polls the macOS default output device and invokes a callback on change.

    The callback is expected to pause playback and release any macOS media
    control state so ytm-player doesn't fight with whichever other source
    (iPhone, Apple Music, etc.) is taking over the active audio route.
    """

    def __init__(self, on_route_change: RouteChangeCallback) -> None:
        self._on_route_change = on_route_change
        self._task: asyncio.Task | None = None
        self._coreaudio: _CoreAudio | None = None
        self._last_device_id: int | None = None

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
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(
            "macOS audio route monitor started (initial device id=%s)",
            self._last_device_id,
        )
        return True

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception):
            pass
        self._task = None

    async def _poll_loop(self) -> None:
        assert self._coreaudio is not None
        try:
            while True:
                await asyncio.sleep(_POLL_INTERVAL)
                current = self._coreaudio.get_default_output_device()
                if current is None or current == self._last_device_id:
                    continue
                logger.info(
                    "Audio route changed (device id %s → %s)",
                    self._last_device_id,
                    current,
                )
                self._last_device_id = current
                try:
                    await self._on_route_change()
                except Exception:
                    logger.exception("Audio route change callback failed")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Audio route monitor crashed")
