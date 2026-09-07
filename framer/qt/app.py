"""Application shell for the Qt frontend.

Owns the QApplication (QSettings identity: organization
``org.framer``, application ``Framer`` → INI in
``~/.config/org.framer/Framer.conf``) and the main window
(:class:`framer.qt.window.FramerWindow`, built in Phase 5).
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from .theme import apply_theme, pre_setup_environment
from .window import FramerWindow

ORGANIZATION = "org.framer"
APPLICATION = "Framer"


class FramerQtApp(QObject):
    """Owns the QApplication and the main window."""

    def __init__(
        self,
        argv: list[str] | None = None,
        files: list[Path] | None = None,
    ) -> None:
        super().__init__()
        # must run before the QApplication exists (gtk3 platform theme)
        pre_setup_environment()
        self.app = QApplication(argv if argv is not None else sys.argv)
        self.app.setOrganizationName(ORGANIZATION)
        self.app.setApplicationName(APPLICATION)
        self.app.setApplicationDisplayName(APPLICATION)
        apply_theme(self.app)
        self.window = FramerWindow(files=files)

    def run(self) -> int:
        self.window.show()
        return self.app.exec()
