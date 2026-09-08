#!/usr/bin/env python3
"""Phase 3 offscreen verification: queue UI (empty state + rows).

Run:
    .venv-qt/bin/python scripts/verify_queue_ui.py

Self-configures the offscreen environment (QT_QPA_PLATFORM + the dev-VM
libEGL shim) and re-execs itself once if needed. Writes screenshots:
  - .agent/feature-migration-qt/screenshots/phase3-empty.png
  - .agent/feature-migration-qt/screenshots/phase3-queue-mixed.png

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
    """Set offscreen env, re-exec once so LD_LIBRARY_PATH reaches the linker."""
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

from PySide6.QtCore import QSize  # noqa: E402
from PySide6.QtGui import QImage, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from framer.core.models import ItemState, QueueItem  # noqa: E402
from framer.qt.queue_view import QueueView  # noqa: E402
from framer.utils.paths import format_meta, human_size  # noqa: E402

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"[{'ok' if cond else 'FAIL'}] {label}" + (
        f" — {detail}" if detail and not cond else ""
    ))
    if not cond:
        FAILURES.append(label)


def make_item(tmp: Path, name: str, with_meta: bool = True) -> QueueItem:
    p = tmp / name
    p.write_bytes(b"stub")
    item = QueueItem(path=p, uri=p.as_uri(), size_bytes=p.stat().st_size)
    if with_meta:
        item.width, item.height, item.format = 4032, 3024, "jpeg"
        item.size_bytes = 3_100_000
    return item


def solid_pixmap(color: tuple[int, int, int] = (120, 200, 120)) -> QPixmap:
    img = QImage(40, 30, QImage.Format.Format_RGB32)
    img.fill((color[0] << 16) | (color[1] << 8) | color[2])
    return QPixmap.fromImage(img)


def main() -> int:
    app = QApplication.instance()
    if app is None:
        app = QApplication(["verify-q3"])
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="framer-q3-"))

    view = QueueView()
    view.resize(1100, 760)
    view.show()
    app.processEvents()

    # -- empty state ---------------------------------------------------------
    check("empty state visible initially", view.empty_state.isVisibleTo(view))
    check("scroller hidden initially", not view.scroller.isVisibleTo(view))
    view.grab().save(str(SCREENSHOTS / "phase3-empty.png"))
    print(f"wrote {SCREENSHOTS / 'phase3-empty.png'}")

    # -- add 5 items -----------------------------------------------------------
    items = [
        make_item(tmp, f"photo_{i:02d}.jpg") for i in range(4)
    ] + [make_item(tmp, "notes.txt.jpg", with_meta=False)]
    for i, it in enumerate(items):
        row = view.add_item(it)
        check(f"add_item returns a row ({i})", row is not None)
        meta = (
            format_meta(it.width, it.height, it.format, it.size_bytes)
            if with_meta_ok(it)
            else human_size(it.size_bytes)
        )
        view.set_row_meta(i, meta)
    check("empty state hidden with items", not view.empty_state.isVisibleTo(view))
    check("scroller visible with items", view.scroller.isVisibleTo(view))
    check("5 rows added", len(view.rows) == 5, f"got {len(view.rows)}")
    check("items() order preserved", view.items() == items)

    # -- drive states ---------------------------------------------------------
    items[0].state = ItemState.QUEUED
    view.rows[0].set_state(ItemState.QUEUED)
    items[1].state = ItemState.PROCESSING
    view.rows[1].set_state(ItemState.PROCESSING)
    items[2].state = ItemState.DONE
    view.rows[2].set_state(ItemState.DONE)
    items[3].state = ItemState.ERROR
    items[3].error = "boom"
    view.rows[3].set_state(ItemState.ERROR)
    items[4].state = ItemState.CANCELLED
    view.rows[4].set_state(ItemState.CANCELLED)

    r0, r1, r2, r3, r4 = view.rows
    check("row0 QUEUED: 'Queued' label visible",
          r0.queued_label.isVisible() and r0.queued_label.text() == "Queued")
    check("row1 PROCESSING: spinner visible + spinning",
          r1.spinner.isVisible() and r1.spinner.spinning)
    check("row1 PROCESSING: ok/error hidden, label hidden",
          not r1.done_icon.isVisible() and not r1.error_icon.isVisible()
          and not r1.queued_label.isVisible())
    check("row2 DONE: ok icon visible, spinner stopped",
          r2.done_icon.isVisible() and not r2.spinner.spinning
          and not r2.spinner.isVisible())
    check("row3 ERROR: error icon + tooltip 'boom'",
          r3.error_icon.isVisible() and r3.toolTip() == "boom")
    check("row4 CANCELLED: 'Cancelled' label visible",
          r4.queued_label.isVisible() and r4.queued_label.text() == "Cancelled")

    # -- thumbnails -------------------------------------------------------------
    view.set_row_thumbnail(items[2], solid_pixmap())
    # 40x30 scaled KeepAspectRatio into 48x48 -> 48x36
    check("set_row_thumbnail: pixmap set on the right row",
          r2.thumb.pixmap() is not None and r2.thumb.pixmap().size() == QSize(48, 36),
          f"got {None if r2.thumb.pixmap() is None else r2.thumb.pixmap().size()}")
    view.set_row_thumbnail(items[4], None)
    check("set_row_thumbnail(None): placeholder fallback",
          r4.thumb.pixmap() is not None and r4.thumb.pixmap().width() == 48,
          f"got {None if r4.thumb.pixmap() is None else r4.thumb.pixmap().size()}")

    for _ in range(6):  # let the spinner rotate a bit for the screenshot
        app.processEvents()
    view.grab().save(str(SCREENSHOTS / "phase3-queue-mixed.png"))
    print(f"wrote {SCREENSHOTS / 'phase3-queue-mixed.png'}")

    # -- clear -------------------------------------------------------------------
    view.clear()
    check("clear(): rows empty", len(view.rows) == 0)
    check("clear(): empty state visible again", view.empty_state.isVisibleTo(view))

    # -- clear_finished -------------------------------------------------------------
    fresh = [make_item(tmp, f"cf_{i:02d}.jpg") for i in range(5)]
    states = [ItemState.DONE, ItemState.QUEUED, ItemState.ERROR,
              ItemState.CANCELLED, ItemState.QUEUED]
    for it, st in zip(fresh, states):
        it.state = st
        it.error = "x" if st is ItemState.ERROR else None
        view.add_item(it)
    view.clear_finished()
    check("clear_finished(): exactly 2 rows remain", len(view.rows) == 2,
          f"got {len(view.rows)}")
    check("clear_finished(): the QUEUED ones, original order",
          view.items() == [fresh[1], fresh[4]],
          f"got {[it.path.name for it in view.items()]}")
    check("clear_finished(): empty state still hidden",
          not view.empty_state.isVisibleTo(view))

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
        return 1
    print("ALL PASS")
    return 0


def with_meta_ok(item: QueueItem) -> bool:
    return item.width is not None


if __name__ == "__main__":
    raise SystemExit(main())
