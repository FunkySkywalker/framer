#!/usr/bin/env python3
"""Phase 6 offscreen verification: settings persistence, settings dialog,
full batch wiring (end-to-end).

Run:
    .venv-qt/bin/python scripts/verify_settings_batch.py

Sandboxes QSettings into a temp XDG_CONFIG_HOME (nothing is written to
the real user config). Runs the full app headless:
  1. add 3 EXIF+ICC JPEGs, change settings (suffix "x", frame 7.5,
     custom 4:3, portrait, short edge 720) -> start ->
     job_finished(3, 3, 0, 0) -> outputs named <stem>x.jpg with portrait
     4:3 / 720-short-edge dimensions, EXIF + ICC bytes byte-identical,
     white corner (no-cropping invariant visible in pixels)
  2. restart (new FramerWindow, same config dir): all 8 settings restored
     into the controls
  3. cancel path: 3-image batch with a large middle file, cancel after
     the first item -> job_finished(3, 1, 0, 2) + error-style summary
  4. settings dialog: suffix edit wiring + directory subtitle logic
Writes .agent/feature-migration-qt/screenshots/phase6-batch-done.png.
Exit code 0 = all pass.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
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

from PIL import Image, ImageCms  # noqa: E402
from PySide6.QtCore import QCoreApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from framer.core.framing import target_canvas  # noqa: E402
from framer.qt.window import FramerWindow  # noqa: E402

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"[{'ok' if cond else 'FAIL'}] {label}" + (
        f" — {detail}" if detail and not cond else ""
    ))
    if not cond:
        FAILURES.append(label)


def pump(app: QCoreApplication, predicate, timeout: float = 60.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


def make_exif_jpeg(p: Path, color: tuple[int, int, int],
                   exif_bytes: bytes, icc_bytes: bytes) -> None:
    Image.new("RGB", (1600, 1200), color).save(
        p, format="JPEG", quality=95, exif=exif_bytes, icc_profile=icc_bytes
    )


def make_big_jpeg(p: Path) -> None:
    im = Image.frombytes("RGB", (4000, 3000), os.urandom(4000 * 3000 * 3))
    im.save(p, format="JPEG", quality=95)


def main() -> int:
    # sandbox QSettings BEFORE any window (which builds the QSettings)
    sandbox = Path(tempfile.mkdtemp(prefix="framer-q6-"))
    os.environ["XDG_CONFIG_HOME"] = str(sandbox / "config")

    app = QApplication.instance()
    if app is None:
        app = QApplication(["verify-q6"])
    app.setOrganizationName("com.funkyskywalker")
    app.setApplicationName("Framer")
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    tmp = sandbox / "imgs"
    tmp.mkdir()

    exif = Image.Exif()
    exif[0x010E] = "framer phase 6 fixture"
    exif_bytes = exif.tobytes()
    icc_bytes = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()

    fa, fb, fc = tmp / "a.jpg", tmp / "b.jpg", tmp / "c.jpg"
    make_exif_jpeg(fa, (180, 60, 60), exif_bytes, icc_bytes)
    make_exif_jpeg(fb, (60, 180, 60), exif_bytes, icc_bytes)
    make_exif_jpeg(fc, (60, 60, 180), exif_bytes, icc_bytes)

    # ---- run 1: full batch with changed settings --------------------------
    window = FramerWindow()
    window.resize(1100, 760)
    window.show()
    pump(app, lambda: True, 0.3)

    window.add_paths([fa, fb, fc])
    pump(app, lambda: True, 0.3)
    check("queue has 3 items", len(window.view.items()) == 3)

    # user changes: suffix, frame 7.5, custom 4:3, portrait, short edge 720
    window.settings.set_string("suffix", "x")
    window.controls.frame_spin.setValue(7.5)
    window.controls.aspect_combo.setCurrentText("Custom")
    window.controls.aspect_num_spin.setValue(4)
    window.controls.aspect_den_spin.setValue(3)
    window.controls.orientation_button.click()
    window.controls.short_edge_spin.setValue(720)
    pump(app, lambda: True, 0.2)

    s = window.settings
    check("settings: suffix 'x'", s.get_string("suffix") == "x")
    check("settings: frame-percent 7.5", s.get_double("frame-percent") == 7.5,
          f"got {s.get_double('frame-percent')}")
    check("settings: aspect-preset 'custom'",
          s.get_string("aspect-preset") == "custom",
          f"got {s.get_string('aspect-preset')!r}")
    check("settings: aspect-num 4 / den 3",
          s.get_int("aspect-num") == 4 and s.get_int("aspect-den") == 3)
    check("settings: orientation-portrait True",
          s.get_boolean("orientation-portrait") is True)
    check("settings: short-edge 720", s.get_int("short-edge") == 720,
          f"got {s.get_int('short-edge')}")
    check("settings: output-directory default ''",
          s.get_string("output-directory") == "")
    check("orientation label shows Portrait",
          window.controls.orientation_button.text() == "Portrait")
    check("custom pair visible", window.controls.custom_box.isVisible())

    jobs: list[tuple[int, int, int, int]] = []
    window.dispatcher.bus.job_finished.connect(
        lambda t, d, f, c: jobs.append((t, d, f, c))
    )
    window._on_start()
    check("run1: job_finished arrives",
          pump(app, lambda: len(jobs) >= 1), "timed out")
    check("run1: job_finished(3, 3, 0, 0)", jobs[0] == (3, 3, 0, 0),
          f"got {jobs[0]}")
    check("run1: success summary toast",
          any(m == "Batch finished — 3 images framed" and p == "normal"
              for m, p in window.host.toast_history),
          f"got {window.host.toast_history}")

    # outputs: next to source, <stem>x.jpg, portrait 4:3 short edge 720
    expect_w, expect_h = target_canvas(4, 3, True, 720)
    check("expected canvas 720x960", (expect_w, expect_h) == (720, 960),
          f"got {(expect_w, expect_h)}")
    outs = [tmp / f"{stem}x.jpg" for stem in ("a", "b", "c")]
    check("outputs exist as <stem>x.jpg", all(o.exists() for o in outs),
          f"got {[str(o) for o in outs]}")
    all_ok = True
    detail = ""
    for src, out in zip((fa, fb, fc), outs):
        with Image.open(src) as sim:
            s_exif, s_icc = sim.info.get("exif"), sim.info.get("icc_profile")
        with Image.open(out) as oim:
            o_exif, o_icc = oim.info.get("exif"), oim.info.get("icc_profile")
            size = oim.size
            corner = oim.convert("RGB").getpixel((0, 0))
        if size != (expect_w, expect_h):
            all_ok = False
            detail = f"{out.name}: size {size}"
        if o_exif != s_exif or o_exif is None:
            all_ok = False
            detail = detail or f"{out.name}: EXIF mismatch"
        if o_icc != s_icc or o_icc is None:
            all_ok = False
            detail = detail or f"{out.name}: ICC mismatch"
        if corner != (255, 255, 255):
            all_ok = False
            detail = detail or f"{out.name}: corner not white {corner}"
    check("outputs: dimensions, EXIF/ICC byte-identical, white corner",
          all_ok, detail)

    for _ in range(3):
        app.processEvents()
    window.grab().save(str(SCREENSHOTS / "phase6-batch-done.png"))
    print(f"wrote {SCREENSHOTS / 'phase6-batch-done.png'}")

    s.sync()  # flush the INI before the restart

    # ---- run 2: restart, all 8 settings restored ---------------------------
    window2 = FramerWindow()
    window2.resize(1100, 760)
    window2.show()
    pump(app, lambda: True, 0.3)
    c2, s2 = window2.controls, window2.settings
    check("restart: aspect combo Custom", c2.aspect_preset() == "Custom")
    check("restart: custom 4:3",
          c2.aspect_num_spin.value() == 4 and c2.aspect_den_spin.value() == 3)
    check("restart: portrait checked + label",
          c2.orientation_button.isChecked()
          and c2.orientation_button.text() == "Portrait")
    check("restart: short edge 720", c2.short_edge() == 720)
    check("restart: frame 7.50", c2.frame_spin.value() == 7.5,
          f"got {c2.frame_spin.value()}")
    check("restart: frame slider in sync", c2.frame_slider.value() == 750)
    check("restart: custom pair visible", c2.custom_box.isVisible())
    check("restart: suffix 'x'", s2.get_string("suffix") == "x")
    check("restart: output-directory ''",
          s2.get_string("output-directory") == "")

    # ---- run 3: cancel path -------------------------------------------------
    big = tmp / "big.jpg"
    make_big_jpeg(big)
    window2.add_paths([fa, big, fc])
    pump(app, lambda: True, 0.3)
    check("cancel: queue has 3 items", len(window2.view.items()) == 3)

    fin: list[int] = []
    cancel_jobs: list[tuple[int, int, int, int]] = []
    window2.dispatcher.bus.item_finished.connect(
        lambda i, _ok, _e: fin.append(i)
    )
    window2.dispatcher.bus.job_finished.connect(
        lambda t, d, f, c: cancel_jobs.append((t, d, f, c))
    )
    window2._on_start()
    check("cancel: first item finished",
          pump(app, lambda: len(fin) >= 1), "timed out")
    assert window2.job is not None
    window2.job.cancel()
    check("cancel: job_finished arrives",
          pump(app, lambda: len(cancel_jobs) >= 1, 60.0), "timed out")
    check("cancel: job_finished(3, 1, 0, 2)", cancel_jobs[0] == (3, 1, 0, 2),
          f"got {cancel_jobs[0]}")
    check("cancel: trailing items CANCELLED",
          window2.view.rows[1].item.state.value == "cancelled"
          and window2.view.rows[2].item.state.value == "cancelled",
          f"got {[r.item.state.value for r in window2.view.rows]}")
    check("cancel: error-style summary toast",
          any(m == "Batch finished: 1 framed, 2 cancelled" and p == "high"
              for m, p in window2.host.toast_history),
          f"got {window2.host.toast_history[-2:]}")

    # ---- settings dialog ------------------------------------------------------
    window2._on_settings()
    pump(app, lambda: True, 0.3)
    dlg = window2._settings_dialog
    check("settings dialog visible", dlg is not None and dlg.isVisible())
    assert dlg is not None
    dlg.suffix_edit.setText("zz")
    check("dialog: suffix edit writes settings",
          s2.get_string("suffix") == "zz",
          f"got {s2.get_string('suffix')!r}")
    dlg.suffix_edit.setText("x")  # restore
    check("dialog: subtitle 'Next to source images'",
          dlg._dir_subtitle_text() == "Next to source images")
    s2.set_string("output-directory", "/tmp/framer-out")
    check("dialog: subtitle shows the path",
          dlg._dir_subtitle_text() == "/tmp/framer-out")
    s2.set_string("output-directory", "")
    dlg.close()
    pump(app, lambda: True, 0.1)

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
