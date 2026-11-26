"""Shared utility helpers for glean_core."""


def escape_like_pattern(pattern: str) -> str:
    """Escape SQL LIKE/ILIKE wildcards (\\, %, _) using backslash as escape char."""
    return pattern.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
