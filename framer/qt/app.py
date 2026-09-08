"""Application shell for the Qt frontend.

Phase 1 scope: QApplication setup (QSettings identity) and an empty main
window sized per the feature inventory. The full window (toolbar, queue,
controls, toasts) lands in ``framer.qt.window`` in a later phase and
replaces the placeholder ``FramerWindow`` here.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication, QMainWindow

ORGANIZATION = "com.funkyskywalker"
APPLICATION = "Framer"


class FramerWindow(QMainWindow):
    """Placeholder main window — replaced by the full window in Phase 5."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Framer")
        self.resize(1100, 760)
        self.setMinimumSize(980, 480)

    def add_paths(self, paths: list[Path]) -> None:
        """Add image files/folders to the queue (stub until Phase 5)."""


class FramerQtApp(QObject):
    """Owns the QApplication and the main window.

    QSettings identity: organization ``com.funkyskywalker`` and application
    ``Framer``, so the INI file lands in
    ``~/.config/com.funkyskywalker/Framer/Framer.conf``.
    """

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
        self.window = FramerWindow()
        if files:
            self.window.add_paths(list(files))

    def run(self) -> int:
        self.window.show()
        return self.app.exec()
