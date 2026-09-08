"""Application shell for the Qt frontend.

Owns the QApplication (QSettings identity: organization
``com.funkyskywalker``, application ``Framer`` → INI in
``~/.config/com.funkyskywalker/Framer/``) and the main window
(:class:`framer.qt.window.FramerWindow`, built in Phase 5).
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from .window import FramerWindow

ORGANIZATION = "com.funkyskywalker"
APPLICATION = "Framer"


class FramerQtApp(QObject):
    """Owns the QApplication and the main window."""

    def __init__(
        self,
        argv: list[str] | None = None,
        files: list[Path] | None = None,
    ) -> None:
        super().__init__()
        self.app = QApplication(argv if argv is not None else sys.argv)
        self.app.setOrganizationName(ORGANIZATION)
        self.app.setApplicationName(APPLICATION)
        self.app.setApplicationDisplayName(APPLICATION)
        self.window = FramerWindow(files=files)

    def run(self) -> int:
        self.window.show()
        return self.app.exec()
