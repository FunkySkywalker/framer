"""Main application window: toolbar, menu, shortcuts, dialogs, DnD, toasts.

Port of the GTK ``FramerWindow`` chrome. Content is the queue view +
control bar wrapped in a :class:`~framer.qt.toasts.ToastHost`. Batch
event wiring, Start/Cancel behavior, and settings persistence land in
Phase 6 (the handlers exist as clearly marked stubs).
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QMenu,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..core.image_io import probe
from ..core.models import QueueItem
from ..core.scanner import scan_folder
from ..utils.paths import IMAGE_EXTENSIONS, format_meta, is_image_file
from .controls import Controls
from .dispatcher import Dispatcher
from .queue_view import QueueView
from .toasts import ToastHost
from .widgets import icon

#: name → accelerator (single Handlers dict, like the GTK Actions class)
ACCELERATORS: dict[str, str] = {
    "add-files": "Ctrl+O",
    "add-folder": "Ctrl+Shift+O",
    "start": "Ctrl+Return",
    "cancel": "Ctrl+.",  # Ctrl+Period; Qt key-string form is "Ctrl+."
    "close": "Ctrl+W",
}


class FramerWindow(QMainWindow):
    """The single application window: toolbar, menu, queue, controls."""

    def __init__(
        self, files: Optional[list[Path]] = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Framer")
        self.setWindowIcon(icon("generic-image"))
        self.resize(1100, 760)
        self.setMinimumSize(980, 480)

        self.dispatcher = Dispatcher()
        self.job = None  # Phase 6: BatchJob
        self._seen: set[Path] = set()
        self._about_box: Optional[QMessageBox] = None

        # content: queue view + control bar, wrapped in the toast host
        self.view = QueueView()
        self.controls = Controls()
        content = QWidget()
        v = QVBoxLayout(content)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self.view, 1)
        v.addWidget(self.controls)
        self.host = ToastHost(content)
        self.setCentralWidget(self.host)

        self.view.add_clicked.connect(self._on_add_files)

        # one Handlers dict for menu, toolbar, and shortcuts
        self._handlers: dict[str, Callable[..., object]] = {
            "add-files": self._on_add_files,
            "add-folder": self._on_add_folder,
            "start": self._on_start,
            "cancel": self._on_cancel,
            "clear": self._on_clear,
            "clear-finished": self._on_clear_finished,
            "about": self._on_about,
            "settings": self._on_settings,
            "close": lambda: self.close(),
        }
        self._build_menu()  # first: the toolbar's hamburger uses it
        self._build_toolbar()
        self._build_shortcuts()

        # drag & drop of image files and folders anywhere in the window
        self.setAcceptDrops(True)

        self.dispatcher.start()
        self.dispatcher.bus.thumbnail.connect(self.view.set_row_thumbnail)

        if files:
            self.add_paths(list(files))

    # -- chrome ------------------------------------------------------------

    def _build_toolbar(self) -> None:
        bar = QToolBar("Main", self)
        bar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, bar)

        self.add_files_button = QToolButton()
        self.add_files_button.setIcon(icon("add"))
        self.add_files_button.setToolTip("Add images (Ctrl+O)")
        self.add_files_button.clicked.connect(self._handlers["add-files"])
        bar.addWidget(self.add_files_button)

        self.add_folder_button = QToolButton()
        self.add_folder_button.setIcon(icon("folder"))
        self.add_folder_button.setToolTip("Add a folder (Ctrl+Shift+O)")
        self.add_folder_button.clicked.connect(self._handlers["add-folder"])
        bar.addWidget(self.add_folder_button)

        spacer = QWidget()
        spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        bar.addWidget(spacer)

        self.hamburger = QToolButton()
        self.hamburger.setIcon(icon("open-menu"))
        self.hamburger.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        bar.addWidget(self.hamburger)
        self.hamburger.setMenu(self.menu)

    def _build_menu(self) -> None:
        self.menu = QMenu(self)
        self.action_clear_finished = self.menu.addAction(
            "Clear finished", self._handlers["clear-finished"]
        )
        self.action_clear = self.menu.addAction(
            "Clear all", self._handlers["clear"]
        )
        self.menu.addSeparator()
        self.action_settings = self.menu.addAction(
            "Settings…", self._handlers["settings"]
        )
        self.action_about = self.menu.addAction(
            "About Framer", self._handlers["about"]
        )
        self.menu.addSeparator()
        self.action_quit = self.menu.addAction("Quit", self._handlers["close"])
        self._sync_clear_enabled(True)

    def _build_shortcuts(self) -> None:
        self.shortcuts: dict[str, QShortcut] = {}
        for name, seq in ACCELERATORS.items():
            sc = QShortcut(QKeySequence(seq), self)
            sc.setObjectName(f"shortcut-{name}")
            sc.activated.connect(self._handlers[name])
            self.shortcuts[name] = sc

    # -- file input ------------------------------------------------------------

    def _image_filter(self) -> str:
        return "Images (" + " ".join(f"*{ext}" for ext in sorted(IMAGE_EXTENSIONS)) + ")"

    def _on_add_files(self) -> None:
        # Non-native dialog: deterministic offscreen; on a desktop the
        # native one can be enabled with one flag (plan risk note).
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Images",
            "",
            self._image_filter(),
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if paths:
            self.add_paths([Path(p) for p in paths])

    def _on_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Add Folder",
            "",
            QFileDialog.Option.DontUseNativeDialog,
        )
        if folder:
            self.add_paths([Path(folder)])

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile()
        ]
        if paths:
            self.add_paths(paths)
        event.acceptProposedAction()

    def add_paths(self, files: list[Path]) -> None:
        """Shared add-path for dialogs, drag & drop, and CLI file args."""
        added = skipped = 0
        for p in files:
            if p.is_dir():
                candidates = scan_folder(p)
            elif p.is_file():
                candidates = [p] if is_image_file(p) else []
            else:
                candidates = []
            if p.is_file() and not candidates:
                skipped += 1
            for c in candidates:
                try:
                    rp = c.resolve()
                except OSError:
                    skipped += 1
                    continue
                if rp in self._seen:
                    skipped += 1
                    continue
                self._seen.add(rp)
                width = height = n_frames = None
                fmt: Optional[str] = None
                size: Optional[int] = None
                try:
                    width, height, fmt, n_frames, size = probe(c)
                except Exception:
                    try:
                        size = c.stat().st_size
                    except OSError:
                        size = None
                item = QueueItem(
                    path=c,
                    uri=c.as_uri(),
                    width=width,
                    height=height,
                    format=fmt,
                    size_bytes=size,
                )
                self.view.add_item(item)
                meta = format_meta(width, height, fmt, size)
                if n_frames and n_frames > 1:
                    meta += f" · {n_frames} frames"
                self.view.set_row_meta(len(self.view.rows) - 1, meta)
                if width is not None:
                    self.dispatcher.request_thumbnail(item, c)
                added += 1
        if added:
            self.host.toast(f"{added} image{'s' if added != 1 else ''} added")
        if skipped:
            self.host.toast(
                f"{skipped} file{'s' if skipped != 1 else ''} skipped "
                "(not a supported image or duplicate)"
            )
        self._sync_start_enabled()

    # -- batch lifecycle (Phase 6 fills start/cancel + event handlers) --------

    def _running(self) -> bool:
        return self.job is not None and self.job.is_running()

    def _sync_start_enabled(self) -> None:
        if self._running():
            self.controls.set_start_enabled(False)
        else:
            self.controls.set_start_enabled(bool(self.view.rows))

    def _on_start(self) -> None:
        """Start the batch — Phase 6 (OutputSpec snapshot + BatchJob)."""

    def _on_cancel(self) -> None:
        """Cancel the batch — Phase 6."""

    # -- queue actions ------------------------------------------------------------

    def _sync_clear_enabled(self, enabled: bool) -> None:
        self.action_clear.setEnabled(enabled)
        self.action_clear_finished.setEnabled(enabled)

    def _on_clear(self) -> None:
        if self._running():
            return
        self.view.clear()
        self._seen.clear()
        self.controls.set_progress(0, 0, 0.0)
        self.controls.status_label.setText("")
        self._sync_start_enabled()

    def _on_clear_finished(self) -> None:
        if self._running():
            return
        self.view.clear_finished()
        if not self.view.rows:
            self.controls.set_progress(0, 0, 0.0)
            self.controls.status_label.setText("")
            self.controls.set_start_enabled(False)
        self._sync_start_enabled()

    # -- settings / about ---------------------------------------------------------

    def _on_settings(self) -> None:
        """Settings dialog — Phase 6."""

    def _on_about(self) -> None:
        if self._about_box is not None and self._about_box.isVisible():
            return
        box = QMessageBox(self)
        box.setWindowTitle("About Framer")
        box.setIconPixmap(icon("generic-image").pixmap(64, 64))
        box.setText(f"<b>Framer</b> &nbsp;{__version__}")
        box.setInformativeText(
            "Batch-frame images onto a user-defined target canvas.\n\n"
            "Developer: funkyskywalker\n"
            "License: MIT (X11)"
        )
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        self._about_box = box
        # shown non-blocking (parity with the GTK AboutWindow present())
        box.show()

    # -- close ---------------------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        job = self.job
        if job is not None and job.is_running():
            job.cancel()
            self.host.toast("Batch cancelled")
        self.dispatcher.stop()
        event.accept()
