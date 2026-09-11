"""Bottom control bar: output row, frame row, progress row (3 rows).

Port of the GTK bottom bar from ``framer/views/queue_view.py``. All
canvas math goes through ``framer.core.framing.target_canvas`` (geometry
law — no hardcoded ratios downstream). Phase 6 wires the change signals
to settings and the start/cancel buttons to the batch job.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core.framing import (
    ASPECT_PRESETS,
    CUSTOM_PRESET,
    DEFAULT_PORTRAIT,
    FRAME_PERCENT_DEFAULT,
    FRAME_PERCENT_MAX,
    FRAME_PERCENT_MIN,
    PRESET_VALUES,
    SHORT_EDGE_DEFAULT,
    SHORT_EDGE_MAX,
    SHORT_EDGE_MIN,
    target_canvas,
)
from ..core.models import OutputSpec
from .widgets import Spinner, dim_label, icon


class Controls(QWidget):
    """The 3-row bottom bar below the queue list.

    Change signals (consumed by the window in Phase 6 to persist settings
    and refresh the live result): ``aspect_changed`` (combo or custom
    A:B spins), ``orientation_changed`` (toggle pressed),
    ``short_edge_changed``, ``frame_percent_changed(float)``.
    """

    aspect_changed = Signal()  # combo selection changed
    custom_aspect_changed = Signal()  # custom A:B spin changed
    orientation_changed = Signal()
    short_edge_changed = Signal()
    frame_percent_changed = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 6, 12, 10)
        root.setSpacing(6)
        root.addWidget(self._build_output_row())
        root.addWidget(self._build_frame_row())
        root.addWidget(self._build_progress_row())
        # portrait is the default orientation (core default) — set after
        # the build so the toggle handler can refresh every widget.
        self.orientation_button.setChecked(DEFAULT_PORTRAIT)
        self._refresh_result()

    # -- output row ---------------------------------------------------------

    def _build_output_row(self) -> QWidget:
        row = QWidget(self)
        box = QHBoxLayout(row)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)

        label = QLabel("Output", row)
        dim_label(label)
        box.addWidget(label)

        self.aspect_combo = QComboBox(row)
        self.aspect_combo.addItems(list(ASPECT_PRESETS))
        self.aspect_combo.currentIndexChanged.connect(
            self._on_aspect_combo_changed
        )
        box.addWidget(self.aspect_combo)

        # Custom A:B pair — Qt has no Revealer, so a plain widget toggled
        # visible only when "Custom" is selected.
        self.custom_box = QWidget(row)
        cbox = QHBoxLayout(self.custom_box)
        cbox.setContentsMargins(0, 0, 0, 0)
        cbox.setSpacing(4)
        self.aspect_num_spin = QSpinBox(self.custom_box)
        self.aspect_num_spin.setRange(1, 999)
        self.aspect_num_spin.valueChanged.connect(self._on_custom_aspect_changed)
        self.aspect_den_spin = QSpinBox(self.custom_box)
        self.aspect_den_spin.setRange(1, 999)
        self.aspect_den_spin.valueChanged.connect(self._on_custom_aspect_changed)
        cbox.addWidget(self.aspect_num_spin)
        cbox.addWidget(QLabel(":", self.custom_box))
        cbox.addWidget(self.aspect_den_spin)
        self.custom_box.setVisible(False)
        box.addWidget(self.custom_box)

        self.orientation_button = QPushButton("Landscape", row)
        self.orientation_button.setCheckable(True)
        self.orientation_button.setToolTip("Flip orientation")
        # toggled (not clicked): programmatic setChecked at startup must
        # flip the label and refresh the result too
        self.orientation_button.toggled.connect(self._on_orientation_toggled)
        box.addWidget(self.orientation_button)

        se_label = QLabel("Short edge", row)
        dim_label(se_label)
        box.addWidget(se_label)

        self.short_edge_spin = QSpinBox(row)
        self.short_edge_spin.setRange(SHORT_EDGE_MIN, SHORT_EDGE_MAX)
        self.short_edge_spin.setValue(SHORT_EDGE_DEFAULT)
        self.short_edge_spin.setToolTip("Short edge in pixels")
        self.short_edge_spin.valueChanged.connect(self._on_short_edge_changed)
        box.addWidget(self.short_edge_spin)

        self.result_label = QLabel("Result: …", row)
        dim_label(self.result_label)
        box.addWidget(self.result_label)
        box.addStretch(1)
        return row

    # -- frame row ------------------------------------------------------------

    def _build_frame_row(self) -> QWidget:
        row = QWidget(self)
        box = QHBoxLayout(row)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title_box.addWidget(QLabel("Frame thickness", row))
        subtitle = QLabel(
            "White frame on each side, % of the image edge", row
        )
        dim_label(subtitle)
        title_box.addWidget(subtitle)
        box.addLayout(title_box)

        # One value bound to both slider (int 0–2000, /100) and spin
        # (0.00–20.00, step 0.01), with change-guards against loops.
        self.frame_slider = QSlider(Qt.Orientation.Horizontal, row)
        self.frame_slider.setRange(0, int((FRAME_PERCENT_MAX - FRAME_PERCENT_MIN) * 100))
        self.frame_slider.setValue(int(FRAME_PERCENT_DEFAULT * 100))
        self.frame_slider.setSingleStep(1)
        self.frame_slider.setPageStep(100)
        self.frame_slider.setTracking(True)
        self.frame_slider.setToolTip("Drag to set frame thickness")
        self.frame_slider.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.frame_spin = QDoubleSpinBox(row)
        self.frame_spin.setRange(FRAME_PERCENT_MIN, FRAME_PERCENT_MAX)
        self.frame_spin.setSingleStep(0.01)
        self.frame_spin.setDecimals(2)
        self.frame_spin.setValue(FRAME_PERCENT_DEFAULT)
        self.frame_spin.setToolTip("Frame thickness in percent")
        pct = QLabel("%", row)
        dim_label(pct)

        self._frame_guard = False
        self.frame_slider.valueChanged.connect(self._on_frame_slider_changed)
        self.frame_spin.valueChanged.connect(self._on_frame_spin_changed)

        box.addWidget(self.frame_slider, 1)
        box.addWidget(self.frame_spin)
        box.addWidget(pct)

        self.start_button = QPushButton(row)
        self.start_button.setObjectName("StartFramingButton")
        self.start_button.setIcon(icon("play"))
        self.start_button.setText("Start Framing")
        self.start_button.setEnabled(False)
        box.addWidget(self.start_button)

        self.cancel_button = QPushButton(row)
        self.cancel_button.setObjectName("CancelButton")
        self.cancel_button.setIcon(icon("stop"))
        self.cancel_button.setText("Cancel")
        self.cancel_button.setEnabled(False)
        box.addWidget(self.cancel_button)
        return row

    # -- progress row ---------------------------------------------------------

    def _build_progress_row(self) -> QWidget:
        row = QWidget(self)
        box = QHBoxLayout(row)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(12)

        self.progress_spinner = Spinner(16, row)
        self.progress_spinner.setVisible(False)
        box.addWidget(self.progress_spinner)

        self.status_label = QLabel("", row)
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        dim_label(self.status_label)
        box.addWidget(self.status_label, 1)

        self.progress_bar = QProgressBar(row)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedWidth(160)
        self.progress_bar.setTextVisible(True)
        box.addWidget(self.progress_bar)
        return row

    # -- change handlers ------------------------------------------------------

    def _on_aspect_combo_changed(self, _index: int) -> None:
        self.custom_box.setVisible(self.aspect_combo.currentText() == CUSTOM_PRESET)
        self._refresh_result()
        self.aspect_changed.emit()

    def _on_custom_aspect_changed(self, _value: int) -> None:
        self._refresh_result()
        self.custom_aspect_changed.emit()

    def _on_short_edge_changed(self, _value: int) -> None:
        self._refresh_result()
        self.short_edge_changed.emit()

    def _on_orientation_toggled(self, _checked: bool) -> None:
        self.orientation_button.setText(
            "Portrait"
            if self.orientation_button.isChecked()
            else "Landscape"
        )
        self._refresh_result()
        self.orientation_changed.emit()

    def _on_frame_slider_changed(self, value: int) -> None:
        if self._frame_guard:
            return
        percent = value / 100
        self._frame_guard = True
        self.frame_spin.setValue(percent)
        self._frame_guard = False
        self._refresh_result()
        self.frame_percent_changed.emit(percent)

    def _on_frame_spin_changed(self, value: float) -> None:
        if self._frame_guard:
            return
        self._frame_guard = True
        self.frame_slider.setValue(int(round(value * 100)))
        self._frame_guard = False
        self._refresh_result()
        self.frame_percent_changed.emit(value)

    # -- value getters ---------------------------------------------------------

    def aspect_preset(self) -> str:
        return self.aspect_combo.currentText()

    def aspect_ratio(self) -> tuple[int, int]:
        if self.aspect_preset() == CUSTOM_PRESET:
            return (
                self.aspect_num_spin.value(),
                self.aspect_den_spin.value(),
            )
        return PRESET_VALUES[self.aspect_preset()]

    def is_portrait(self) -> bool:
        return self.orientation_button.isChecked()

    def short_edge(self) -> int:
        return self.short_edge_spin.value()

    def frame_percent(self) -> float:
        return self.frame_spin.value()

    def output_spec(self) -> OutputSpec:
        """Snapshot the current controls as an ``OutputSpec`` (clamped)."""
        num, den = self.aspect_ratio()
        return OutputSpec(num, den, self.is_portrait(), self.short_edge(), self.frame_percent())

    # -- window hooks ------------------------------------------------------------

    def set_running(self, running: bool, current_label: str = "") -> None:
        """Insensitize output/frame controls while running (inventory 19)."""
        for w in (
            self.aspect_combo,
            self.custom_box,
            self.aspect_num_spin,
            self.aspect_den_spin,
            self.orientation_button,
            self.short_edge_spin,
            self.frame_slider,
            self.frame_spin,
        ):
            w.setEnabled(not running)
        self.start_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.progress_spinner.setVisible(running)
        self.progress_spinner.set_spinning(running)
        if not running:
            self.status_label.setText(current_label)

    def set_progress(
        self,
        done: int,
        total: int,
        fraction: float,
        current_name: str | None = None,
    ) -> None:
        self.progress_bar.setValue(int(max(0.0, min(1.0, fraction)) * 100))
        text = f"{done} of {total}" if total else ""
        if current_name:
            text = f"{text} — {current_name}" if text else current_name
        self.status_label.setText(text)

    def set_start_enabled(self, enabled: bool) -> None:
        self.start_button.setEnabled(enabled)

    def set_result_label(self, w: int, h: int) -> None:
        self.result_label.setText(f"Result: {w} × {h}")

    def refresh_result(self) -> None:
        """Public alias of the live result refresh (window startup sync)."""
        self._refresh_result()

    def _refresh_result(self) -> None:
        num, den = self.aspect_ratio()
        canvas_w, canvas_h = target_canvas(
            num, den, self.is_portrait(), self.short_edge()
        )
        self.set_result_label(canvas_w, canvas_h)
