"""BiDi text utilities for correct RTL display in terminals.

Most terminals (WezTerm default, Kitty, Alacritty) do NOT implement the
Unicode BiDi algorithm.  They render characters left-to-right in the order
received, relying on HarfBuzz for text shaping (ligatures, contextual forms)
but not for paragraph-level reordering.

This module performs word-level reordering based on UAX #9 (Unicode
Bidirectional Algorithm) embedding levels and the L2 reversal rule.
Characters within each word stay in logical order so HarfBuzz shaping
is preserved — only the *word order* is rearranged.

The track table and playback bar wrap reordered text in LRI/PDI
(U+2066/U+2069) isolation so RTL content doesn't pull adjacent
columns into the RTL BiDi context.  The lyrics sidebar uses
``wrap_rtl_line()`` for correct multi-line display.
"""

from __future__ import annotations

import re
import unicodedata

# Matches any character from RTL scripts (Arabic, Hebrew, Thaana, Syriac, N'Ko).
_RTL_RE = re.compile(
    r"[\u0590-\u05FF\u0600-\u06FF\u0700-\u074F\u0750-\u077F"
    r"\u0780-\u07BF\u07C0-\u07FF\u08A0-\u08FF"
    r"\uFB1D-\uFB4F\uFB50-\uFDFF\uFE70-\uFEFF]"
)


def has_rtl(text: str) -> bool:
    """Return True if text contains any RTL script characters."""
    return bool(_RTL_RE.search(text))


def _char_direction(ch: str) -> str:
    """Return simplified BiDi direction: 'R', 'L', or 'N' (neutral)."""
    bidi = unicodedata.bidirectional(ch)
    if bidi in ("R", "AL", "AN"):
        return "R"
    if bidi == "L":
        return "L"
    return "N"


def _word_direction(word: str) -> str:
    """Return direction from the first strong character in *word*."""
    for ch in word:
        d = _char_direction(ch)
        if d != "N":
            return d
    return "N"


def _paragraph_base_direction(text: str) -> str:
    """UAX #9 rules P2/P3: base direction from first strong character."""
    for ch in text:
        d = _char_direction(ch)
        if d != "N":
            return d
    return "L"


def reorder_rtl_line(text: str) -> str:
    """Reorder words in a line for correct display in an LTR terminal.

    Uses a simplified UAX #9 approach:

    1. Determine the paragraph base direction from the first strong
       directional character (P2/P3).
    2. Assign an embedding level to each whitespace-delimited word:
       - RTL words → level 1
       - LTR words in an RTL paragraph → level 2 (embedded LTR in RTL)
       - LTR words in an LTR paragraph → level 0
       - Neutral words → paragraph base level
    3. Apply the L2 reversal rule: from the highest level down to the
       lowest odd level, reverse each contiguous run of words at that
       level or higher.

    Characters within words are NOT reordered — HarfBuzz handles
    intra-word shaping and ligatures.

    Pure LTR text passes through unchanged.
    """
    if not text or not has_rtl(text):
        return text

    words = text.split()
    if not words:
        return text

    base_dir = _paragraph_base_direction(text)
    base_level = 1 if base_dir == "R" else 0

    # Assign embedding levels to each word.
    levels: list[int] = []
    for word in words:
        wd = _word_direction(word)
        if wd == "R":
            levels.append(1)
        elif wd == "L":
            # LTR text embedded in RTL paragraph gets level 2;
            # LTR text in LTR paragraph stays at level 0.
            levels.append(2 if base_level == 1 else 0)
        else:
            # Neutral words (numbers, punctuation-only) inherit
            # the paragraph base level.
            levels.append(base_level)

    if not levels:
        return text

    # L2: reverse contiguous sequences from highest level down to 1.
    max_level = max(levels)
    indices = list(range(len(words)))

    for level in range(max_level, 0, -1):
        i = 0
        while i < len(indices):
            if levels[indices[i]] >= level:
                j = i
                while j < len(indices) and levels[indices[j]] >= level:
                    j += 1
                indices[i:j] = indices[i:j][::-1]
                i = j
            else:
                i += 1

    return " ".join(words[idx] for idx in indices)


def wrap_rtl_line(text: str, width: int) -> str:
    """Pre-wrap and reorder RTL text for correct multi-line terminal display.

    Terminals wrap text left-to-right, which reverses the line order when a
    reordered RTL string exceeds the display width.  This wraps the text in
    *logical* (reading) order first, then reorders each wrapped segment
    independently so that visual line 1 = start of sentence, line 2 =
    continuation, etc.

    Pure LTR or short text passes through to ``reorder_rtl_line`` directly.
    """
    if not text or not has_rtl(text):
        return text

    if len(text) <= width or width <= 0:
        return reorder_rtl_line(text)

    words = text.split()
    if not words:
        return text

    lines: list[str] = []
    current_words: list[str] = []
    current_len = 0

    for word in words:
        word_len = len(word)
        needed = word_len if not current_words else current_len + 1 + word_len
        if needed <= width:
            current_words.append(word)
            current_len = needed
        else:
            if current_words:
                lines.append(" ".join(current_words))
            current_words = [word]
            current_len = word_len

    if current_words:
        lines.append(" ".join(current_words))

    return "\n".join(reorder_rtl_line(line) for line in lines)
