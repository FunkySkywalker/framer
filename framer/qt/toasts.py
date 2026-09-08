"""Toast notifications: bottom-right stacked, auto-hiding.

Port of the GTK ``Adw.Toast`` helpers. Qt has no built-in toast, so
:class:`ToastHost` wraps the window content and floats toast frames at
the bottom-right (stacked, newest at the bottom). Auto-hide: normal 3 s,
high-priority 5 s. High-priority toasts get an Error-role border. Colors
are read from the live palette at creation time (no hardcoded hex);
Phase 7 formalizes the palette-derived QSS layer.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

NORMAL_TIMEOUT = 3.0
HIGH_TIMEOUT = 5.0
_MARGIN = 16
_SPACING = 8
_TOAST_MAX_W = 420


class _Toast(QFrame):
    """One toast frame: rounded, palette-derived colors."""

    def __init__(self, parent: "ToastHost", message: str, high: bool) -> None:
        super().__init__(parent)
        self._host = parent

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)
        self.label = QLabel(message, self)
        self.label.setWordWrap(True)
        self.label.setMaximumWidth(_TOAST_MAX_W)
        self.label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        lay.addWidget(self.label)

        pal = parent.palette()
        bg = pal.color(QPalette.ColorRole.Window)
        fg = pal.color(QPalette.ColorRole.Text)
        # Qt 6.11 has no Error palette role (checked at runtime); the
        # semantic Qt red is the error color until a DE palette exposes
        # a better one (Phase 7 may revisit).
        border = QColor(Qt.GlobalColor.red) if high else pal.color(
            QPalette.ColorRole.Button
        )
        border_width = 2 if high else 1
        self.setStyleSheet(
            "QFrame { background: %s; color: %s; border: %dp solid %s;"
            " border-radius: 8px; }"
            "QLabel { background: transparent; color: %s; }"
            % (bg.name(), fg.name(), border_width, border.name(), fg.name())
        )
        self.adjustSize()

    def dismiss(self) -> None:
        self._host._dismiss(self)


class ToastHost(QWidget):
    """Wraps the window content; floats toasts at the bottom-right.

    ``toast_history`` records every toast as ``(message, priority)`` for
    the verification scripts.
    """

    def __init__(self, content: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(content)
        self._toasts: list[_Toast] = []
        self.toast_history: list[tuple[str, str]] = []

    def toast(
        self,
        message: str,
        priority: str = "normal",
        timeout: float | None = None,
    ) -> _Toast:
        """Show a toast; auto-hides after ``timeout`` (3 s / 5 s default)."""
        high = priority == "high"
        t = _Toast(self, message, high)
        self._toasts.append(t)
        self.toast_history.append((message, "high" if high else "normal"))
        if timeout is None:
            timeout = HIGH_TIMEOUT if high else NORMAL_TIMEOUT
        QTimer.singleShot(int(timeout * 1000), t.dismiss)
        # Children created while the parent is already visible start hidden
        # in Qt — show explicitly (see Phase 3 notes).
        t.show()
        self._relayout()
        return t

    def _relayout(self) -> None:
        y = self.height()
        for t in reversed(self._toasts):
            x = max(0, self.width() - _MARGIN - t.width())
            t.move(x, max(0, y - _MARGIN - t.height()))
            y -= t.height() + _SPACING

    def _dismiss(self, t: _Toast) -> None:
        if t in self._toasts:
            self._toasts.remove(t)
        t.deleteLater()
        self._relayout()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self._relayout()


def success(host: ToastHost, message: str, timeout: float = NORMAL_TIMEOUT) -> None:
    """Normal-priority success toast (GTK: success_overlay)."""
    host.toast(message, "normal", timeout)


def error(host: ToastHost, message: str, timeout: float = HIGH_TIMEOUT) -> None:
    """High-priority error toast (GTK: error_overlay)."""
    host.toast(message, "high", timeout)
