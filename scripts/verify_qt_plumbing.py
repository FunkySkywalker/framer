#!/usr/bin/env python3
"""Phase 2 offscreen verification: Qt event plumbing (bus, dispatcher,
thumbnails).

Run:
    .venv-qt/bin/python scripts/verify_qt_plumbing.py

The script self-configures the offscreen environment (QT_QPA_PLATFORM
plus the dev-VM libEGL shim) and re-execs itself once if needed.

Fixtures (temp dir): 2 plain JPEGs, 1 corrupt .jpg (bad bytes), 1
3-frame GIF, 1 RGBA PNG with EXIF + ICC bytes.

Checks (per the plan):
  1. one ``item_started`` per item (5)
  2. ``job_finished(total=5, done=4, failed=1, cancelled=0)``
  3. corrupt item → ``item_finished(ok=False, non-empty error)`` while the
     batch completes (per-item error isolation)
  4. GIF item reaches DONE via the multi-frame path (warnings intact)
  5. thumbnails: 4 non-null QPixmaps (>= 1×1) delivered via the bus on
     the main thread; the corrupt file delivers None
  6. cancellation: 3-item batch whose middle file is a large JPEG (so the
     cancel reliably lands in a between-stages check), cancel after the
     first item finishes → ``job_finished(3, 1, 0, 2)`` — the mid-encode
     file is stopped, everything after is cancelled.

Exit code 0 = all pass.
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
SHIM_DIR = REPO_ROOT / ".agent" / "feature-migration-qt" / "qtlibs"


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

from PIL import Image, ImageCms  # noqa: E402
from PySide6.QtGui import QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from framer.core.image_io import probe  # noqa: E402
from framer.core.models import ItemState, OutputSpec, QueueItem  # noqa: E402
from framer.qt.dispatcher import Dispatcher  # noqa: E402
from framer.workers.batch_worker import BatchJob  # noqa: E402

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"[{'ok' if cond else 'FAIL'}] {label}" + (
        f" — {detail}" if detail and not cond else ""
    ))
    if not cond:
        FAILURES.append(label)


def make_item(p: Path) -> QueueItem:
    """QueueItem with probe data; probe failure degrades to size-only."""
    item = QueueItem(path=p, uri=p.as_uri(), size_bytes=p.stat().st_size)
    try:
        w, h, fmt, _n, size = probe(p)
        item.width, item.height, item.format, item.size_bytes = w, h, fmt, size
    except Exception:
        pass
    return item


def make_fixtures(tmp: Path) -> dict[str, Path]:
    j1 = tmp / "one.jpg"
    Image.new("RGB", (420, 300), (200, 40, 40)).save(j1, format="JPEG", quality=90)
    j2 = tmp / "two.jpg"
    Image.new("RGB", (300, 420), (40, 60, 200)).save(j2, format="JPEG", quality=90)
    bad = tmp / "bad.jpg"
    bad.write_bytes(b"\xff\xd8\xff\xdb" + os.urandom(96))
    gif = tmp / "anim.gif"
    frames = [
        Image.new("RGB", (120, 80), c).convert("P")
        for c in ((255, 0, 0), (0, 255, 0), (0, 0, 255))
    ]
    frames[0].save(
        gif, format="GIF", save_all=True, append_images=frames[1:],
        duration=100, loop=0,
    )
    png = tmp / "rgba_exif.png"
    im = Image.new("RGBA", (200, 150), (200, 30, 30, 128))
    exif = Image.Exif()
    exif[0x010E] = "framer phase 2 fixture"
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    im.save(png, format="PNG", exif=exif.tobytes(), icc_profile=icc)
    return {"j1": j1, "j2": j2, "bad": bad, "gif": gif, "png": png}


def make_big_jpeg(p: Path) -> None:
    """A slow-to-process JPEG so a cancel reliably lands mid-encode."""
    im = Image.frombytes("RGB", (4000, 3000), os.urandom(4000 * 3000 * 3))
    im.save(p, format="JPEG", quality=95)


def pump(app: QApplication, predicate, timeout: float = 60.0) -> bool:
    """Process events until predicate() is true or the timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


def main() -> int:
    inst = QApplication.instance()
    app = inst if isinstance(inst, QApplication) else QApplication(["verify-q2"])
    tmp = Path(tempfile.mkdtemp(prefix="framer-q2-"))
    fix = make_fixtures(tmp)

    dispatcher = Dispatcher()
    started: list[int] = []
    finished: list[tuple[int, bool, str]] = []
    job_result: list[tuple[int, int, int, int]] = []
    thumbs: list[tuple[str, "QPixmap | None"]] = []
    handler_tids: list[int] = []
    main_tid = threading.get_ident()

    def on_item_started(idx: int) -> None:
        started.append(idx)

    def on_item_finished(idx: int, ok: bool, err: str) -> None:
        finished.append((idx, ok, err))

    def on_job_finished(total: int, done: int, failed: int, cancelled: int) -> None:
        job_result.append((total, done, failed, cancelled))

    def on_thumb(item, pixmap) -> None:
        handler_tids.append(threading.get_ident())
        thumbs.append((item.path.name, pixmap))

    dispatcher.bus.item_started.connect(on_item_started)
    dispatcher.bus.item_finished.connect(on_item_finished)
    dispatcher.bus.job_finished.connect(on_job_finished)
    dispatcher.bus.thumbnail.connect(on_thumb)

    # --- run 1: full batch incl. one corrupt file -------------------------
    paths = [fix["j1"], fix["j2"], fix["bad"], fix["gif"], fix["png"]]
    items = [make_item(p) for p in paths]
    spec = OutputSpec(5, 4, False, 1080, 5.0)
    job = BatchJob(items, dispatcher.bus, "_framed", str(tmp / "out"), spec)
    dispatcher.attach(job.event_queue)
    dispatcher.start()
    job.start()

    check("run1: job_finished arrives",
          pump(app, lambda: len(job_result) >= 1),
          "timed out waiting for job_finished")
    t, d, f, c = job_result[0]
    check("run1: job_finished(5, 4, 1, 0)", (t, d, f, c) == (5, 4, 1, 0),
          f"got {(t, d, f, c)}")
    check("run1: one item_started per item", sorted(started) == [0, 1, 2, 3, 4],
          f"got {started}")
    bad_ev = [e for e in finished if e[0] == 2]
    check("run1: corrupt item item_finished(ok=False, error)",
          bool(bad_ev) and bad_ev[0][1] is False and bad_ev[0][2] != "",
          f"got {bad_ev}")
    check("run1: batch completed despite corrupt file (error isolation)",
          len(job_result) == 1)
    gif_item = items[3]
    check("run1: GIF item DONE", gif_item.state is ItemState.DONE,
          f"state={gif_item.state} error={gif_item.error}")
    check("run1: GIF warnings intact (list)", isinstance(gif_item.warnings, list))
    check("run1: 4 items DONE",
          sum(1 for it in items if it.state is ItemState.DONE) == 4,
          f"states={[it.state for it in items]}")
    outs = [it.output_path for it in items if it.state is ItemState.DONE]
    check("run1: output files exist",
          all(o is not None and o.exists() for o in outs))

    # --- thumbnails ---------------------------------------------------------
    for it in items:
        dispatcher.request_thumbnail(it, it.path)
    check("thumbs: 5 events delivered", pump(app, lambda: len(thumbs) >= 5, 30.0),
          f"got {len(thumbs)}")
    good = [pm for _n, pm in thumbs if pm is not None]
    check("thumbs: 4 non-null QPixmaps", len(good) == 4,
          f"got {len(good)}: {[(n, pm is not None) for n, pm in thumbs]}")
    check("thumbs: pixmaps >= 1x1",
          all(pm.width() >= 1 and pm.height() >= 1 for pm in good))
    check("thumbs: corrupt file delivered None",
          any(n == "bad.jpg" and pm is None for n, pm in thumbs))
    check("thumbs: handlers ran on the main thread",
          all(tid == main_tid for tid in handler_tids))

    # --- run 2: cancel after the first item finishes ------------------------
    big = tmp / "big.jpg"
    make_big_jpeg(big)
    cancel_finished: list[int] = []
    cancel_jobs: list[tuple[int, int, int, int]] = []

    def on_cancel_finished(idx: int, _ok: bool, _err: str) -> None:
        cancel_finished.append(idx)

    def on_cancel_job(total: int, done: int, failed: int, cancelled: int) -> None:
        cancel_jobs.append((total, done, failed, cancelled))

    dispatcher.bus.item_finished.connect(on_cancel_finished)
    dispatcher.bus.job_finished.connect(on_cancel_job)

    c_items = [make_item(p) for p in (fix["j1"], big, fix["j2"])]
    job2 = BatchJob(c_items, dispatcher.bus, "_x", str(tmp / "out2"), spec)
    dispatcher.attach(job2.event_queue)
    job2.start()

    check("run2: first item finished",
          pump(app, lambda: len(cancel_finished) >= 1), "timed out")
    job2.cancel()
    check("run2: job_finished arrives",
          pump(app, lambda: len(cancel_jobs) >= 1, 30.0), "timed out")
    j2 = cancel_jobs[0]
    check("run2: job_finished(3, 1, 0, 2)", j2 == (3, 1, 0, 2), f"got {j2}")
    check("run2: trailing items CANCELLED",
          c_items[2].state is ItemState.CANCELLED, f"state={c_items[2].state}")

    dispatcher.stop()

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
