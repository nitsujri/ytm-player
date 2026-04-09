"""Theme system integrating Textual's native theming with app-specific colors."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Self

from textual.theme import Theme

from ytm_player.config.paths import THEME_FILE

# ── App-specific CSS variable names (not provided by Textual themes) ───

_APP_VARS = (
    "playback_bar_bg",
    "active_tab",
    "inactive_tab",
    "selected_item",
    "progress_filled",
    "progress_empty",
    "lyrics_played",
    "lyrics_current",
    "lyrics_upcoming",
)

# ── YTM dark theme — YouTube Music-inspired defaults ──────────────────

YTM_DARK = Theme(
    name="ytm-dark",
    primary="#ff0000",
    secondary="#aaaaaa",
    accent="#ff4e45",
    success="#2ecc71",
    warning="#f39c12",
    error="#e74c3c",
    foreground="#ffffff",
    background="#0f0f0f",
    surface="#1a1a1a",
    dark=True,
    variables={
        "playback-bar-bg": "#1a1a1a",
        "active-tab": "#ffffff",
        "inactive-tab": "#999999",
        "selected-item": "#2a2a2a",
        "progress-filled": "#ff0000",
        "progress-empty": "#555555",
        "lyrics-played": "#999999",
        "lyrics-current": "#2ecc71",
        "lyrics-upcoming": "#aaaaaa",
    },
)


@dataclass
class ThemeColors:
    """Resolved color values for Rich Text rendering in widget render() methods.

    Base colors come from the active Textual theme.  App-specific colors
    can be overridden via ``theme.toml``.
    """

    # Base colors (populated from Textual theme at runtime).
    background: str = "#0f0f0f"
    foreground: str = "#ffffff"
    primary: str = "#ff0000"
    secondary: str = "#aaaaaa"
    accent: str = "#ff4e45"
    success: str = "#2ecc71"
    warning: str = "#f39c12"
    error: str = "#e74c3c"
    surface: str = "#1a1a1a"
    border: str = "#333333"
    muted_text: str = "#999999"
    text: str = "#ffffff"

    # App-specific colors (customisable via theme.toml).
    playback_bar_bg: str = "#1a1a1a"
    active_tab: str = "#ffffff"
    inactive_tab: str = "#999999"
    selected_item: str = "#2a2a2a"
    progress_filled: str = "#ff0000"
    progress_empty: str = "#555555"
    lyrics_played: str = "#999999"
    lyrics_current: str = "#2ecc71"
    lyrics_upcoming: str = "#aaaaaa"

    @classmethod
    def from_css_variables(cls, variables: dict[str, str]) -> Self:
        """Build ThemeColors from resolved Textual CSS variables.

        Maps Textual's variable names to our field names and applies any
        app-specific overrides from ``theme.toml``.
        """
        tc = cls(
            background=variables.get("background", cls.background),
            foreground=variables.get("foreground", cls.foreground),
            primary=variables.get("primary", cls.primary),
            secondary=variables.get("secondary", cls.secondary),
            accent=variables.get("accent", cls.accent),
            success=variables.get("success", cls.success),
            warning=variables.get("warning", cls.warning),
            error=variables.get("error", cls.error),
            surface=variables.get("surface", cls.surface),
            border=variables.get("border", cls.border),
            muted_text=variables.get("text-muted", cls.muted_text),
            text=variables.get("text", cls.text),
            # App-specific: use theme value if present, else derive from base.
            playback_bar_bg=variables.get(
                "playback-bar-bg", variables.get("surface", cls.playback_bar_bg)
            ),
            active_tab=variables.get("active-tab", variables.get("text", cls.active_tab)),
            inactive_tab=variables.get(
                "inactive-tab", variables.get("text-muted", cls.inactive_tab)
            ),
            selected_item=variables.get(
                "selected-item", variables.get("surface", cls.selected_item)
            ),
            progress_filled=variables.get(
                "progress-filled", variables.get("primary", cls.progress_filled)
            ),
            progress_empty=variables.get(
                "progress-empty", variables.get("surface", cls.progress_empty)
            ),
            lyrics_played=variables.get(
                "lyrics-played", variables.get("text-muted", cls.lyrics_played)
            ),
            lyrics_current=variables.get(
                "lyrics-current", variables.get("success", cls.lyrics_current)
            ),
            lyrics_upcoming=variables.get(
                "lyrics-upcoming", variables.get("text", cls.lyrics_upcoming)
            ),
        )

        # Apply user overrides from theme.toml (app-specific vars only).
        tc._apply_toml_overrides()
        return tc

    def _apply_toml_overrides(self, path: Path = THEME_FILE) -> None:
        """Load app-specific color overrides from theme.toml."""
        if not path.exists():
            return
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except (UnicodeDecodeError, tomllib.TOMLDecodeError):
            return

        colors = data.get("colors", data)
        for field_name in _APP_VARS:
            if field_name in colors:
                setattr(self, field_name, colors[field_name])

    @classmethod
    def load(cls, path: Path = THEME_FILE) -> Self:
        """Load from theme.toml (legacy fallback for non-app contexts)."""
        theme = cls()
        if not path.exists():
            return theme
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except (UnicodeDecodeError, tomllib.TOMLDecodeError):
            return theme
        colors = data.get("colors", data)
        for f_info in fields(theme):
            if f_info.name in colors:
                setattr(theme, f_info.name, colors[f_info.name])
        return theme

    def save(self, path: Path = THEME_FILE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["[colors]"]
        for f_info in fields(self):
            value = getattr(self, f_info.name)
            lines.append(f'{f_info.name} = "{value}"')
        lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")


_theme: ThemeColors | None = None


def get_theme() -> ThemeColors:
    global _theme
    if _theme is None:
        _theme = ThemeColors.load()
    return _theme


def set_theme(theme: ThemeColors) -> None:
    """Replace the cached ThemeColors (called when the Textual theme changes)."""
    global _theme
    _theme = theme


def reset_theme() -> None:
    """Invalidate the cached ThemeColors so it's rebuilt on next access."""
    global _theme
    _theme = None
