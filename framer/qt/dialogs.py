"""Dialogs: the settings dialog.

About lives in the window (non-blocking QMessageBox, Phase 5). The
settings dialog mirrors the GTK PreferencesWindow: an "Output" group
with the output-directory row (current path or "Next to source images"
subtitle + Choose… folder picker) and the suffix entry.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .settings import Settings
from .widgets import dim_label


class SettingsDialog(QDialog):
    """Modal settings dialog (window modality; shown non-blocking)."""

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(520)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        group_title = QLabel("Output", self)
        font = group_title.font()
        font.setBold(True)
        group_title.setFont(font)
        root.addWidget(group_title)

        # -- output directory row -------------------------------
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        dir_title = QLabel("Output directory", self)
        self.dir_subtitle = QLabel(self._dir_subtitle_text(), self)
        dim_label(self.dir_subtitle)
        choose = QPushButton("Choose…", self)
        choose.clicked.connect(self._choose_output_dir)
        grid.addWidget(dir_title, 0, 0)
        grid.addWidget(self.dir_subtitle, 1, 0)
        grid.addWidget(choose, 0, 1, 2, 1)
        root.addLayout(grid)

        # -- suffix row -------------------------------------------
        self.suffix_edit = QLineEdit(self)
        self.suffix_edit.setText(self.settings.get_string("suffix"))
        self.suffix_edit.setToolTip(
            "Appended to the file name, before the extension"
        )
        self.suffix_edit.textChanged.connect(self._on_suffix_changed)
        suffix_row = QHBoxLayout()
        suffix_row.addWidget(QLabel("Suffix", self))
        suffix_row.addWidget(self.suffix_edit, 1)
        root.addLayout(suffix_row)

        # -- buttons ----------------------------------------------
        # (QButtonBox was removed from the PySide6 6.11 API — plain buttons)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        ok = QPushButton("OK", self)
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel", self)
        cancel.clicked.connect(self.reject)
        button_row.addWidget(ok)
        button_row.addWidget(cancel)
        root.addLayout(button_row)

    def _dir_subtitle_text(self) -> str:
        return (
            self.settings.get_string("output-directory")
            or "Next to source images"
        )

    def _choose_output_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Choose Output Directory",
            "",
            QFileDialog.Option.DontUseNativeDialog,
        )
        if folder:
            self.settings.set_string("output-directory", folder)
            self.dir_subtitle.setText(self._dir_subtitle_text())

    def _on_suffix_changed(self, text: str) -> None:
        self.settings.set_string("suffix", text)
