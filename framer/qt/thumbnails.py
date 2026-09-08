"""Thumbnail generation: PIL → in-memory PNG bytes (pure, thread-safe).

Runs on the Dispatcher's thread pool (never the main thread). The main
thread converts the PNG bytes into a ``QPixmap`` during the dispatcher
tick (Qt object thread-affinity). Any failure yields ``None`` and the UI
shows the missing-image icon instead.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps


def make_thumbnail_png(path, pixel_size: int = 96) -> Optional[bytes]:
    """Create a <= ``pixel_size``-square PNG thumbnail for ``path`` as bytes."""
    try:
        with Image.open(path) as im:
            # Display only — the framed output never gets transposed pixels.
            im = ImageOps.exif_transpose(im)
            im.seek(0)
            im.thumbnail((pixel_size, pixel_size), Image.Resampling.LANCZOS)
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA")
            if im.mode == "RGBA":
                flat = Image.new("RGB", im.size, (255, 255, 255))
                flat.paste(im, (0, 0), im)
                im = flat
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            return buf.getvalue()
    except Exception:
        return None
