"""Settings service on QSettings (INI).

Replaces the GSettings / in-memory fallback service: same key names and
defaults, preserved for continuity. QSettings identity comes from the
application (organization ``com.funkyskywalker``, application
``Framer``) → ``~/.config/com.funkyskywalker/Framer/Framer.conf``.
Existing GSettings values are NOT migrated (documented; values are
trivial to re-enter).
"""
from __future__ import annotations

from PySide6.QtCore import QSettings

#: Same keys and defaults as the GTK GSettings fallback.
DEFAULTS = {
    "output-directory": "",
    "suffix": "_framed",
    "frame-percent": 5.0,
    "aspect-preset": "5:4",
    "aspect-num": 3,
    "aspect-den": 2,
    "orientation-portrait": False,
    "short-edge": 1080,
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
