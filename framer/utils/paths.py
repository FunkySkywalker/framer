"""File-type helpers and human-readable formatting — pure Python, no GTK."""
from __future__ import annotations

from pathlib import Path

#: Extensions the app can process (Pillow formats present on this system).
IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".tif",
    ".tiff",
    ".bmp",
    ".webp",
    ".gif",
    ".apng",
    ".jfif",
}


def is_image_file(path) -> bool:
    """True if ``path`` has a known image extension (case-insensitive)."""
    return Path(path).suffix.lower() in IMAGE_EXTENSIONS


def human_size(n) -> str:
    """Human file size: ``B``, ``KiB``, ``MiB``, ``GiB``."""
    if n is None:
        return "?"
    value = float(n)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024.0 or unit == "GiB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} GiB"


def format_meta(w, h, fmt, size) -> str:
    """Queue row meta line, e.g. ``4032×3024 · JPEG · 3.1 MiB``."""
    parts: list[str] = []
    if w and h:
        parts.append(f"{w}×{h}")
    if fmt:
        parts.append(str(fmt).upper())
    parts.append(human_size(size))
    return " · ".join(parts)
