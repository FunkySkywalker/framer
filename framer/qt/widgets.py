"""Shared small Qt widgets: arc spinner, dim-label helper, icon resolution.

Icon resolution order (see :func:`icon`): system icon theme (Yaru on
GNOME via the gtk3 platform theme, Breeze on KDE, shell icons on
Windows) → ``QStyle`` standard icon → bundled SVG fallback under
``framer/qt/icons/`` so the app also renders headless/offscreen. Phase 7
adds the palette-derived QSS layer; until then colors come straight from
the live palette (no hardcoded widget colors).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QTimer
from PySide6.QtGui import (
    QPaintEvent,
    QPainter,
    QPalette,
    QPen,
)
from PySide6.QtWidgets import QApplication, QLabel, QStyle, QWidget

from PySide6.QtCore import Qt

#: Base icon name → system icon theme name (matches the GTK app's usage).
THEME_NAMES: dict[str, str] = {
    "add": "list-add",
    "folder": "folder",
    "open-menu": "open-menu",
    "play": "media-playback-start",
    "stop": "process-stop",
    "ok": "emblem-ok",
    "error": "dialog-error",
    "missing-image": "image-missing",
    "generic-image": "image-x-generic",
}

#: Base icon name → QStyle standard icon (None = go straight to bundled SVG).
STANDARD_NAMES: dict[str, QStyle.StandardPixmap | None] = {
    "add": QStyle.StandardPixmap.SP_FileDialogNewFolder,
    "folder": QStyle.StandardPixmap.SP_DirIcon,
    "open-menu": None,
    "play": QStyle.StandardPixmap.SP_MediaPlay,
    "stop": QStyle.StandardPixmap.SP_MediaStop,
    "ok": QStyle.StandardPixmap.SP_DialogApplyButton,
    "error": QStyle.StandardPixmap.SP_MessageBoxCritical,
    "missing-image": None,
    "generic-image": QStyle.StandardPixmap.SP_FileIcon,
}

_BUNDLED_DIR = Path(__file__).resolve().parent / "icons"


class Spinner(QWidget):
    """A small rotating-arc spinner (Qt has no built-in one).

    ``set_spinning(True)`` starts the rotation timer, ``False`` stops it
    (and resets the arc). Visibility is controlled by the caller.
    """

    def __init__(self, size: int = 16, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._spinning = False
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._tick)

    def set_spinning(self, spinning: bool) -> None:
        self._spinning = spinning
        if spinning:
            self._timer.start()
        else:
            self._timer.stop()
            self._angle = 0
            self.update()

    @property
    def spinning(self) -> bool:
        return self._spinning

    def _tick(self) -> None:
        self._angle = (self._angle + 30) % 360
        self.update()

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self.palette().color(QPalette.ColorRole.Highlight))
        pen.setWidthF(2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        s = self.width()
        m = pen.widthF()
        rect = QRectF(m / 2, m / 2, s - m, s - m)
        # 270° arc, rotated by the current angle (Qt angles: 1/16 degree).
        painter.drawArc(rect, self._angle * 16, -270 * 16)
        painter.end()


def dim_label(widget: QLabel) -> None:
    """Make a label's text dim: palette Text at ~55 % alpha, no hex.

    Also tags the widget with the dynamic property ``dim`` so Phase 7's
    palette-derived QSS can target dim labels.
    """
    palette = widget.palette()
    color = palette.color(QPalette.ColorRole.Text)
    color.setAlpha(140)
    palette.setColor(QPalette.ColorRole.Text, color)
    widget.setPalette(palette)
    widget.setProperty("dim", True)


def icon(name: str):
    """Resolve an icon by base name: theme → standard → bundled SVG → null.

    See :data:`THEME_NAMES` / :data:`STANDARD_NAMES` / ``icons/*.svg``.
    """
    from PySide6.QtGui import QIcon

    themed = QIcon.fromTheme(THEME_NAMES.get(name, name))
    if not themed.isNull():
        return themed
    standard = STANDARD_NAMES.get(name)
    app = QApplication.instance()
    if standard is not None and isinstance(app, QApplication):
        std = app.style().standardIcon(standard)
        if not std.isNull():
            return std
    path = _BUNDLED_DIR / f"{name}.svg"
    if path.exists():
        bundled = QIcon(str(path))
        if not bundled.isNull():
            return bundled
    return QIcon()
