#!/usr/bin/env python3
"""Phase 5 offscreen verification: window chrome (toolbar, menu,
accelerators, dialogs, DnD, toasts, add_paths).

Run:
    .venv-qt/bin/python scripts/verify_window.py

Self-configures the offscreen environment (QT_QPA_PLATFORM + the dev-VM
libEGL shim) and re-execs itself once if needed. Writes:
  - .agent/feature-migration-qt/screenshots/phase5-window-empty.png
  - .agent/feature-migration-qt/screenshots/phase5-window-full.png
  - .agent/feature-migration-qt/screenshots/phase5-menu.png

Exit code 0 = all pass.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
SHIM_DIR = REPO_ROOT / ".agent" / "feature-migration-qt" / "qtlibs"
SCREENSHOTS = REPO_ROOT / ".agent" / "feature-migration-qt" / "screenshots"


def _ensure_env() -> None:
    needs = os.environ.get("QT_QPA_PLATFORM") != "offscreen"
    if SHIM_DIR.is_dir() and str(SHIM_DIR) not in os.environ.get(
        "LD_LIBRARY_PATH", ""
    ).split(os.pathsep):
        needs = True
    if not needs:
        return
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    if SHIM_DIR.is_dir():
        existing = os.environ.get("LD_LIBRARY_PATH", "")
        os.environ["LD_LIBRARY_PATH"] = str(SHIM_DIR) + (
            os.pathsep + existing if existing else ""
        )
    os.execve(sys.executable, [sys.executable, *sys.argv], os.environ)


_ensure_env()

import time  # noqa: E402

from PIL import Image  # noqa: E402
from PySide6.QtCore import (  # noqa: E402
    QCoreApplication,
    QMimeData,
    QPoint,
    QUrl,
    QTimer,
)
from PySide6.QtGui import (  # noqa: E402
    QDropEvent,
    QKeySequence,
    QShortcut,
    QStandardItem,
    QStandardItemModel,
)
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (
    QApplication,  # noqa: E402
    QAbstractItemView,
    QFileDialog,
    QListView,
)

from framer.qt.window import ACCELERATORS, FramerWindow  # noqa: E402

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"[{'ok' if cond else 'FAIL'}] {label}" + (
        f" — {detail}" if detail and not cond else ""
    ))
    if not cond:
        FAILURES.append(label)


def make_jpeg(p: Path, color: tuple[int, int, int] = (90, 140, 200)) -> None:
    Image.new("RGB", (320, 240), color).save(p, format="JPEG", quality=90)


def pump(app: QCoreApplication, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)


def main() -> int:
    app = QApplication.instance()
    if app is None:
        app = QApplication(["verify-q5"])
    if not isinstance(app, QApplication):
        raise SystemExit("expected a QApplication")
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="framer-q5-"))

    w1, w2, w3 = tmp / "a.jpg", tmp / "b.jpg", tmp / "c.jpg"
    make_jpeg(w1)
    make_jpeg(w2, (200, 90, 90))
    make_jpeg(w3, (90, 200, 90))
    text = tmp / "notes.txt"
    text.write_text("not an image")
    folder = tmp / "pics"
    folder.mkdir()
    w4 = folder / "d.jpg"
    make_jpeg(w4, (200, 200, 90))
    dropped = tmp / "e.jpg"
    make_jpeg(dropped, (90, 90, 200))

    window = FramerWindow()
    window.resize(1100, 760)
    window.show()
    pump(app, 0.2)

    # thumbnail counter must be connected before any add_paths()
    thumbs: list[int] = []
    window.dispatcher.bus.thumbnail.connect(
        lambda _item, pm: thumbs.append(1) if pm is not None else None
    )

    # -- empty state + chrome ---------------------------------------------------
    check("window title 'Framer'", window.windowTitle() == "Framer")
    check("empty state visible", window.view.empty_state.isVisibleTo(window.view))
    window.grab().save(str(SCREENSHOTS / "phase5-window-empty.png"))
    print(f"wrote {SCREENSHOTS / 'phase5-window-empty.png'}")

    # -- add_paths: 2 images + 1 text + 1 dir(image) + 1 duplicate --------------
    window.add_paths([w1, w2, text, folder, w1])
    pump(app, 0.2)
    check("queue has 3 items", len(window.view.items()) == 3,
          f"got {len(window.view.items())}")
    names = [it.path.name for it in window.view.items()]
    check("queue contents (a, b, d)",
          names == ["a.jpg", "b.jpg", "d.jpg"], f"got {names}")
    msgs = [m for m, _p in window.host.toast_history]
    check("toast '3 images added'", "3 images added" in msgs, f"got {msgs}")
    check("toast '2 files skipped ...'",
          any(m.startswith("2 files skipped") for m in msgs), f"got {msgs}")
    meta = window.view.rows[0].meta_label.text()
    check("meta line has dims + format", "×" in meta and "JPEG" in meta,
          f"got {meta!r}")
    check("start enabled with rows", window.controls.start_button.isEnabled())

    # -- drag & drop (synthesized QDropEvent with a local file URL) --------------
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(dropped))])
    from PySide6.QtCore import Qt as _Qt

    ev = QDropEvent(
        QPoint(20, 20),
        _Qt.DropAction.CopyAction,
        mime,
        _Qt.MouseButton.LeftButton,
        _Qt.KeyboardModifier.NoModifier,
    )
    window.dropEvent(ev)
    pump(app, 0.2)
    check("drop adds 1 image", len(window.view.items()) == 4,
          f"got {len(window.view.items())}")
    check("drop toast '1 image added'",
          any(m == "1 image added" for m, _p in window.host.toast_history),
          f"got {[m for m, _ in window.host.toast_history]}")

    pump(app, 3.0)  # thumbnail pool + dispatcher ticks
    check("thumbnails delivered (4)", len(thumbs) >= 4, f"got {len(thumbs)}")

    # full screenshot with a fresh toast visible
    window.host.toast("4 images in queue", "normal", 10.0)
    pump(app, 0.1)
    window.grab().save(str(SCREENSHOTS / "phase5-window-full.png"))
    print(f"wrote {SCREENSHOTS / 'phase5-window-full.png'}")

    # -- menu screenshot ------------------------------------------------------------
    window.menu.grab().save(str(SCREENSHOTS / "phase5-menu.png"))
    print(f"wrote {SCREENSHOTS / 'phase5-menu.png'}")
    menu_texts = [a.text() for a in window.menu.actions() if a.text()]
    check("menu items",
          menu_texts == ["Clear finished", "Clear all", "Settings…",
                         "About Framer", "Quit"],
          f"got {menu_texts}")

    # -- accelerators ------------------------------------------------------------------
    scs = window.findChildren(QShortcut)
    check("5 QShortcuts registered", len(scs) == 5, f"got {len(scs)}")
    names = {sc.objectName() for sc in scs}
    check("shortcut names cover all 5 actions",
          names == {f"shortcut-{n}" for n in ACCELERATORS}, f"got {names}")
    keys = sorted(QKeySequence(sc.key()).toString() for sc in scs)
    # canonical display strings per the plan (Ctrl+Period renders as Ctrl+.)
    expected = sorted(["Ctrl+O", "Ctrl+Shift+O", "Ctrl+Return", "Ctrl+.", "Ctrl+W"])
    check("shortcut key sequences match the plan", keys == expected,
          f"got {keys}, expected {expected}")
    print("shortcut keys:", keys)

    # -- menu/accelerator handlers: no exceptions -------------------------------------
    window._handlers["clear-finished"]()  # all queued -> nothing removed
    check("clear-finished keeps queued rows", len(window.view.items()) == 4)
    window._handlers["settings"]()  # Phase 6 stub: must not raise
    check("settings handler ran (no exception)", True)
    window._handlers["about"]()
    pump(app, 0.2)
    check("about dialog visible",
          window._about_box is not None and window._about_box.isVisible())
    if window._about_box is not None:
        window._about_box.close()
        pump(app, 0.1)
    check("about dialog closed",
          window._about_box is None or not window._about_box.isVisible())

    # -- file picker: multi-select regression (Qt 6.11 ordering trap) ---------
    # The app uses the plain static getOpenFileNames() (native dialog on
    # desktops, widget dialog as fallback). Offscreen there is no platform
    # dialog helper, so the widget dialog is used and its creation order
    # applies ExtendedSelection. Drive the real _on_add_files() and inspect
    # the live dialog; the offscreen QFileSystemModel cannot load directory
    # contents, so a stub model stands in for the click test.
    picker_state: dict = {}

    def _picker_probe() -> None:
        try:
            dlg = next(w for w in app.topLevelWidgets()
                       if isinstance(w, QFileDialog) and w.isVisible())
            view = dlg.findChild(QListView, "listView")
            if view is None:
                raise RuntimeError("file list view missing")
            picker_state["selmode"] = view.selectionMode()
            stub = QStandardItemModel()
            for n in ("m1.png", "m2.png"):
                stub.appendRow(QStandardItem(n))
            view.setModel(stub)
            sm = view.selectionModel()
            dlg.resize(900, 600)
            app.processEvents()

            def _click(name: str, mods: _Qt.KeyboardModifier) -> None:
                for i in range(stub.rowCount()):
                    if stub.index(i, 0).data() == name:
                        r = view.visualRect(stub.index(i, 0))
                QTest.mouseClick(
                    view.viewport(), _Qt.MouseButton.LeftButton, mods, r.center()
                )
                app.processEvents()

            _click("m1.png", _Qt.KeyboardModifier.NoModifier)
            _click("m2.png", _Qt.KeyboardModifier.ControlModifier)
            picker_state["sel"] = sorted(
                stub.index(x.row(), 0).data() for x in sm.selectedRows()
            )
            dlg.reject()
        except Exception as exc:  # noqa: BLE001
            picker_state["error"] = f"{type(exc).__name__}: {exc}"
            # never leave the modal exec() hanging
            for w in app.topLevelWidgets():
                if isinstance(w, QFileDialog) and w.isVisible():
                    w.reject()

    def _picker_schedule(attempts: int = 0) -> None:
        if attempts > 100:
            picker_state.setdefault("error", "dialog never appeared")
            return
        if not any(isinstance(w, QFileDialog) and w.isVisible()
                   for w in app.topLevelWidgets()):
            QTimer.singleShot(50, lambda: _picker_schedule(attempts + 1))
            return
        _picker_probe()

    QTimer.singleShot(200, _picker_schedule)
    window._handlers["add-files"]()
    pump(app, 1.0)
    check("file picker probe ran",
          "error" not in picker_state, picker_state.get("error", ""))
    check("file picker list view is ExtendedSelection",
          picker_state.get("selmode")
          == QAbstractItemView.SelectionMode.ExtendedSelection,
          f"got {picker_state.get('selmode')}")
    check("file picker Ctrl+click multi-selects",
          picker_state.get("sel") == ["m1.png", "m2.png"],
          f"got {picker_state.get('sel')}")
    check("picker cancel adds nothing", len(window.view.items()) == 4)

    window._handlers["clear"]()
    check("clear removes all rows", len(window.view.items()) == 0)
    check("clear re-shows empty state",
          window.view.empty_state.isVisibleTo(window.view))
    check("start disabled with empty queue",
          not window.controls.start_button.isEnabled())
    check("clear actions enabled now",
          window.action_clear.isEnabled()
          and window.action_clear_finished.isEnabled())

    # -- quit ------------------------------------------------------------------------------
    window._handlers["close"]()
    pump(app, 0.2)
    check("close: window hidden", not window.isVisible())

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
