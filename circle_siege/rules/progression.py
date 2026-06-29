from __future__ import annotations

from ..core.config import ARENA_THEMES, DEFAULT_THEME_ID


def get_next_theme_id(current_theme_id: str) -> str:
    theme_ids = [theme.identifier for theme in ARENA_THEMES]
    if not theme_ids:
        return DEFAULT_THEME_ID
    try:
        index = theme_ids.index(current_theme_id)
    except ValueError:
        return theme_ids[0]
    return theme_ids[(index + 1) % len(theme_ids)]

