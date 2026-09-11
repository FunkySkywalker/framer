"""Application object: lifecycle, GSettings service, window management."""
from __future__ import annotations

from typing import Optional

import gi

gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
from gi.repository import Adw, Gio

from .. import APP_ID
from ..core.framing import (
    DEFAULT_ASPECT_DEN,
    DEFAULT_ASPECT_NUM,
    DEFAULT_ASPECT_PRESET,
    DEFAULT_PORTRAIT,
    FRAME_PERCENT_DEFAULT,
    SHORT_EDGE_DEFAULT,
)
from .window import FramerWindow

SCHEMA_ID = APP_ID

#: Used when the GSettings schema is not installed (graceful fallback).
DEFAULTS = {
    "output-directory": "",
    "suffix": "_framed",
    "frame-percent": FRAME_PERCENT_DEFAULT,
    "aspect-preset": DEFAULT_ASPECT_PRESET,
    "aspect-num": DEFAULT_ASPECT_NUM,
    "aspect-den": DEFAULT_ASPECT_DEN,
    "orientation-portrait": DEFAULT_PORTRAIT,
    "short-edge": SHORT_EDGE_DEFAULT,
}


class FallbackSettings:
    """In-memory settings with the same get/set surface as ``Gio.Settings``."""

    def __init__(self) -> None:
        self._data = dict(DEFAULTS)

    def get_string(self, key: str) -> str:
        return self._data[key]

    def get_int(self, key: str) -> int:
        return self._data[key]

    def get_double(self, key: str) -> float:
        return self._data[key]

    def get_boolean(self, key: str) -> bool:
        return self._data[key]

    def set_string(self, key: str, value: str) -> None:
        self._data[key] = value

    def set_int(self, key: str, value: int) -> None:
        self._data[key] = value

    def set_double(self, key: str, value: float) -> None:
        self._data[key] = value

    def set_boolean(self, key: str, value: bool) -> None:
        self._data[key] = value


class FramerApplication(Adw.Application):
    """Adw.Application with ``activate`` and ``open`` (CLI args, drag & drop
    URIs, and the .desktop entry all land in the same add-path)."""

    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
        )
        self._window: Optional[FramerWindow] = None
        self._settings = None
        # The "open" vfunc override is not invoked reliably on this stack
        # (GLib 2.88 + PyGObject); a connected handler always is. The base
        # vfunc is a no-op, so nothing double-fires.
        self.connect("open", self._on_open)

    def do_activate(self) -> None:
        Gio.Application.do_activate(self)
        if self._window is None:
            self._window = FramerWindow(self)
        self._window.present()

    def _on_open(self, _app, files, n_files, hint=None) -> None:
        """CLI file arguments (``main.py IMG ...``) and remote activations."""
        if self._window is None:
            self._window = FramerWindow(self)
        self._window.add_paths(list(files))
        self._window.present()

    def get_settings(self):
        """Settings service, built lazily on first use.

        Deliberately not built in a ``do_startup`` override: overriding
        that vfunc on an ``Adw.Application`` subclass segfaults on this
        PyGObject / GTK 4.22 / Libadwaita 1.9 stack.

        ``Gio.Settings.new()`` aborts (fatal g_error) when the schema is
        not installed, so the schema source is probed first and the app
        falls back to an in-memory store with hardcoded defaults.
        """
        if self._settings is None:
            source = Gio.SettingsSchemaSource.get_default()
            schema = source.lookup(SCHEMA_ID, False) if source is not None else None
            if schema is not None:
                self._settings = Gio.Settings.new(SCHEMA_ID)
            else:
                self._settings = FallbackSettings()
        return self._settings
