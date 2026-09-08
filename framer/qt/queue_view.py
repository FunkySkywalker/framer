"""Queue view: empty state + the scrollable list of queue rows.

Port of the GTK ``QueueView`` queue parts. The 3-row bottom control bar
lives in ``framer.qt.controls`` (Phase 4); the window assembles both.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..core.models import ItemState, QueueItem
from .queue_row import QueueRow
from .widgets import dim_label, icon

DESCRIPTION = (
    "Add images with the buttons above, or drop image files or folders "
    "anywhere in this window."
)


class QueueView(QWidget):
    """Vertical: empty state ↔ scrollable queue rows."""

    add_clicked = Signal()  # empty-state "Add Images" button pressed

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rows: list[QueueRow] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.empty_state = self._build_empty_state()
        self.scroller = self._build_scroller()
        root.addWidget(self.empty_state)
        root.addWidget(self.scroller, 1)
        self._update_empty()

    # -- construction -------------------------------------------------------

    def _build_empty_state(self) -> QWidget:
        page = QWidget(self)
        box = QVBoxLayout(page)
        box.setContentsMargins(24, 24, 24, 24)

        icon_label = QLabel(page)
        icon_label.setPixmap(icon("generic-image").pixmap(64, 64))
        title = QLabel("No images yet", page)
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        # Word-wrapped labels default to a tiny hint width; let this one
        # span the page and center the text internally.
        desc = QLabel(DESCRIPTION, page)
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        dim_label(desc)

        self.add_button = QPushButton("Add Images", page)
        self.add_button.setObjectName("AddImagesButton")
        self.add_button.clicked.connect(self.add_clicked.emit)

        box.addStretch(1)
        box.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignHCenter)
        box.addWidget(title, 0, Qt.AlignmentFlag.AlignHCenter)
        box.addWidget(desc)
        box.addWidget(self.add_button, 0, Qt.AlignmentFlag.AlignHCenter)
        box.addStretch(1)
        return page

    def _build_scroller(self) -> QScrollArea:
        scroller = QScrollArea(self)
        scroller.setWidgetResizable(True)
        scroller.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroller.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        self.rows_layout = QVBoxLayout(container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(0)
        self.rows_layout.addStretch(1)  # keep rows top-anchored
        scroller.setWidget(container)
        return scroller

    # -- queue API ------------------------------------------------------------

    def add_item(self, item: QueueItem) -> QueueRow:
        row = QueueRow(item, self)
        self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)
        # Children created while the parent is already visible start hidden
        # in Qt (they only inherit visibility at the parent's own show());
        # show explicitly so a row added to a live view is visible.
        row.show()
        self.rows.append(row)
        self._update_empty()
        return row

    def update_item(self, index: int, fraction: float, state: ItemState) -> None:
        if 0 <= index < len(self.rows):
            self.rows[index].set_state(state)

    def set_row_thumbnail(self, item: QueueItem, pixmap: QPixmap | None) -> None:
        for row in self.rows:
            if row.item is item:
                row.set_thumbnail(pixmap)
                return

    def set_row_meta(self, index: int, meta: str) -> None:
        if 0 <= index < len(self.rows):
            self.rows[index].set_meta(meta)

    def items(self) -> list[QueueItem]:
        return [row.item for row in self.rows]

    def clear(self) -> None:
        for row in self.rows:
            row.deleteLater()
        self.rows.clear()
        self._update_empty()

    def clear_finished(self) -> None:
        """Remove DONE / ERROR / CANCELLED rows, keep the rest in order."""
        finished = (ItemState.DONE, ItemState.ERROR, ItemState.CANCELLED)
        keep = [row for row in self.rows if row.item.state not in finished]
        for row in self.rows:
            if row not in keep:
                row.deleteLater()
        self.rows = keep
        self._update_empty()

    # -- internals --------------------------------------------------------------

    def _update_empty(self) -> None:
        has_items = bool(self.rows)
        self.empty_state.setVisible(not has_items)
        self.scroller.setVisible(has_items)
