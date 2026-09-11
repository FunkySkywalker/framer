"""Settings service on QSettings (INI).

Replaces the GSettings / in-memory fallback service: same key names and
defaults, preserved for continuity. QSettings identity comes from the
application (organization ``org.framer``, application
``Framer``) → ``~/.config/org.framer/Framer.conf``.
Existing GSettings values are NOT migrated (documented; values are
trivial to re-enter).
"""
from __future__ import annotations

from PySide6.QtCore import QSettings

from ..core.framing import (
    DEFAULT_ASPECT_DEN,
    DEFAULT_ASPECT_NUM,
    DEFAULT_ASPECT_PRESET,
    DEFAULT_PORTRAIT,
    FRAME_PERCENT_DEFAULT,
    SHORT_EDGE_DEFAULT,
)

#: Same keys and defaults as the GTK GSettings fallback (both derived
#: from ``framer.core.framing`` — the single source of truth).
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


class Settings:
    """Typed get/set surface over QSettings (same names as the GTK one).

    Construct after the QApplication exists (org/app name must be set).
    """

    def __init__(self, qs: QSettings | None = None) -> None:
        self._qs = qs if qs is not None else QSettings()

    def _raw(self, key: str) -> str:
        # INI stores everything as text; str() normalizes native types
        # (bool True -> "True") before parsing.
        return str(self._qs.value(key, DEFAULTS[key]))

    def get_string(self, key: str) -> str:
        return self._raw(key)

    def get_int(self, key: str) -> int:
        return int(self._raw(key))

    def get_double(self, key: str) -> float:
        return float(self._raw(key))

    def get_boolean(self, key: str) -> bool:
        return self._raw(key).strip().lower() == "true"

    def set_string(self, key: str, value: str) -> None:
        self._qs.setValue(key, value)

    def set_int(self, key: str, value: int) -> None:
        self._qs.setValue(key, value)

    def set_double(self, key: str, value: float) -> None:
        self._qs.setValue(key, value)

    def set_boolean(self, key: str, value: bool) -> None:
        self._qs.setValue(key, value)

    def sync(self) -> None:
        """Flush pending writes to the INI file."""
        self._qs.sync()
