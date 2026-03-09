"""Optional lyrics transliteration using anyascii."""

from __future__ import annotations

from functools import lru_cache


def has_non_ascii(text: str) -> bool:
    """Return True if *text* contains any non-ASCII characters."""
    return bool(text) and not text.isascii()


@lru_cache(maxsize=512)
def transliterate_line(text: str) -> str:
    """Transliterate *text* to ASCII via anyascii.

    Returns the original string unchanged when anyascii is not installed
    or when the text is already pure ASCII.
    """
    if not text or not has_non_ascii(text):
        return text
    try:
        from anyascii import anyascii

        return anyascii(text)
    except ImportError:
        return text
