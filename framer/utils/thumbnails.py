"""Thumbnail generation: PIL → in-memory PNG → GdkPixbuf → Gdk.Texture.

Run on worker threads only (the Dispatcher's thread pool). Any failure
yields ``None`` and the UI shows the missing-image icon instead.
"""
from __future__ import annotations

import io
from typing import Optional

from PIL import Image, ImageOps

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib


def make_thumbnail(path, pixel_size: int = 96) -> Optional[Gdk.Texture]:
    """Create a <= ``pixel_size``-square thumbnail texture for ``path``."""
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
            png = buf.getvalue()
        stream = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes(png))
        pixbuf = GdkPixbuf.Pixbuf.new_from_stream(stream, None)
        return Gdk.Texture.new_for_pixbuf(pixbuf)
    except Exception:
        return None
