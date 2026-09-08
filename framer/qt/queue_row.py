"""Queue row: 48 px thumbnail, ellipsized filename/meta, per-file status.

Port of the GTK ``QueueRow``: same visual layout and the same
``set_state`` state-machine parity (spinner / ok / error / "Queued" /
"Cancelled").
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFontMetrics, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..core.models import ItemState, QueueItem
from .widgets import Spinner, dim_label, icon

_ELIDE = Qt.TextElideMode.ElideRight


class _EllidingLabel(QLabel):
    """A QLabel that ellipses its text at the end and can shrink to fit."""

    def sizeHint(self) -> QSize:  # noqa: N807 (Qt naming)
        base = super().sizeHint()
        if not self.text():
            return base
        fm = QFontMetrics(self.font())
        elided = fm.elidedText(self.text(), _ELIDE, max(1, base.width() - 2))
        return QSize(fm.horizontalAdvance(elided), base.height())

    def minimumSizeHint(self) -> QSize:  # noqa: N807 (Qt naming)
        base = super().minimumSizeHint()
        return QSize(24, base.height())


class QueueRow(QWidget):
    """One row of the queue list. Not selectable, not activatable."""

    def __init__(self, item: QueueItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.item = item

        box = QHBoxLayout(self)
        box.setSpacing(12)
        box.setContentsMargins(12, 6, 12, 6)

        # (a) 48 px thumbnail (missing-image placeholder until delivered)
        self.thumb = QLabel(self)
        self.thumb.setFixedSize(48, 48)
        self.thumb.setPixmap(icon("missing-image").pixmap(48, 48))
        self.thumb.setToolTip(str(item.path))
        box.addWidget(self.thumb)

        # (b) name + dim meta, name ellipsizes at the end
        text = QVBoxLayout()
        text.setSpacing(2)
        self.name_label = _EllidingLabel(item.path.name, self)
        self.name_label.setToolTip(str(item.path))
        self.name_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.meta_label = QLabel("", self)
        self.meta_label.setToolTip(str(item.path))
        dim_label(self.meta_label)
        text.addWidget(self.name_label)
        text.addWidget(self.meta_label)
        box.addLayout(text, 1)

        # (c) status: spinner / ok / error / "Queued" / "Cancelled"
        status = QHBoxLayout()
        status.setSpacing(8)
        self.spinner = Spinner(16, self)
        self.spinner.setVisible(False)
        self.done_icon = QLabel(self)
        self.done_icon.setPixmap(icon("ok").pixmap(16, 16))
        self.error_icon = QLabel(self)
        self.error_icon.setPixmap(icon("error").pixmap(16, 16))
        self.queued_label = QLabel("Queued", self)
        dim_label(self.queued_label)
        for w in (self.spinner, self.done_icon, self.error_icon, self.queued_label):
            status.addWidget(w)
        box.addLayout(status)

        self.set_state(item.state)

    # -- updates -----------------------------------------------------------

    def set_thumbnail(self, pixmap: QPixmap | None) -> None:
        if pixmap is not None:
            self.thumb.setPixmap(
                pixmap.scaled(
                    48,
                    48,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self.thumb.setPixmap(icon("missing-image").pixmap(48, 48))

    def set_meta(self, meta: str) -> None:
        self.meta_label.setText(meta)

    def set_state(self, state: ItemState) -> None:
        """Exact GTK parity: which status widget shows for which state."""
        processing = state is ItemState.PROCESSING
        self.spinner.setVisible(processing)
        self.spinner.set_spinning(processing)
        self.done_icon.setVisible(state is ItemState.DONE)
        self.error_icon.setVisible(state is ItemState.ERROR)
        if state is ItemState.QUEUED:
            self.queued_label.setText("Queued")
            self.queued_label.setVisible(True)
        elif state is ItemState.CANCELLED:
            self.queued_label.setText("Cancelled")
            self.queued_label.setVisible(True)
        else:
            self.queued_label.setVisible(False)
        self.setToolTip(
            self.item.error
            if state is ItemState.ERROR and self.item.error
            else ""
        )
