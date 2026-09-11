#!/usr/bin/env python3
"""Phase 4 offscreen verification: bottom control bar (3 rows).

Run:
    .venv-qt/bin/python scripts/verify_controls.py

Self-configures the offscreen environment (QT_QPA_PLATFORM + the dev-VM
libEGL shim) and re-execs itself once if needed. Expected result-label
values are computed through ``framer.core.framing.target_canvas`` (the
single source of truth) — no hardcoded canvas sizes here. Writes:
  - .agent/feature-migration-qt/screenshots/phase4-controls-idle.png
  - .agent/feature-migration-qt/screenshots/phase4-controls-running.png

Exit code 0 = all pass.
"""
from __future__ import annotations

import os
import sys
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

from PySide6.QtWidgets import QApplication  # noqa: E402

from framer.core.framing import target_canvas  # noqa: E402
from framer.core.models import OutputSpec  # noqa: E402
from framer.qt.controls import Controls  # noqa: E402

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"[{'ok' if cond else 'FAIL'}] {label}" + (
        f" — {detail}" if detail and not cond else ""
    ))
    if not cond:
        FAILURES.append(label)


def expect_result(c: Controls, label: str, a: int, b: int,
                  portrait: bool, se: int) -> None:
    w, h = target_canvas(a, b, portrait, se)
    check(f"result {label}: '{w} × {h}'",
          c.result_label.text() == f"Result: {w} × {h}",
          f"got {c.result_label.text()!r}")


def main() -> int:
    app = QApplication.instance()
    if app is None:
        app = QApplication(["verify-q4"])
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)

    c = Controls()
    c.resize(1100, 220)
    c.show()
    app.processEvents()

    # -- output row -----------------------------------------------------------
    check("combo shows the 5 presets",
          c.aspect_combo.count() == 5
          and [c.aspect_combo.itemText(i) for i in range(5)]
          == ["3:4", "3:2", "4:5", "19:16", "Custom"],
          f"got {[c.aspect_combo.itemText(i) for i in range(c.aspect_combo.count())]}")
    check("default preset 3:4", c.aspect_combo.currentText() == "3:4")
    check("custom pair hidden initially", not c.custom_box.isVisible())
    check("default orientation Portrait",
          c.orientation_button.isChecked()
          and c.orientation_button.text() == "Portrait")
    expect_result(c, "default 3:4/1080 portrait", 3, 4, True, 1080)
    w, h = target_canvas(3, 4, True, 1080)
    check("default canvas is portrait-shaped (w < h)", w < h,
          f"got {w} × {h}")

    c.orientation_button.click()  # -> Landscape
    app.processEvents()
    check("orientation label flips to Landscape",
          c.orientation_button.text() == "Landscape"
          and not c.orientation_button.isChecked())
    expect_result(c, "3:4/1080 landscape", 3, 4, False, 1080)
    w, h = target_canvas(3, 4, False, 1080)
    check("3:4 landscape canvas is landscape-shaped (w > h)", w > h,
          f"got {w} × {h}")
    c.orientation_button.click()  # -> Portrait again
    app.processEvents()
    check("orientation label flips back to Portrait",
          c.orientation_button.text() == "Portrait"
          and c.orientation_button.isChecked())

    c.aspect_combo.setCurrentText("19:16")
    app.processEvents()
    expect_result(c, "19:16/1080 portrait", 19, 16, True, 1080)

    c.aspect_combo.setCurrentText("Custom")
    app.processEvents()
    check("custom pair visible for Custom", c.custom_box.isVisible())
    c.aspect_num_spin.setValue(4)
    c.aspect_den_spin.setValue(3)
    app.processEvents()
    expect_result(c, "custom 4:3/1080 portrait", 4, 3, True, 1080)

    c.aspect_combo.setCurrentText("4:5")
    app.processEvents()
    check("custom pair hidden for preset", not c.custom_box.isVisible())
    c.short_edge_spin.setValue(720)
    app.processEvents()
    expect_result(c, "4:5/720 portrait", 4, 5, True, 720)
    w, h = target_canvas(4, 5, True, 720)
    check("4:5 + portrait stays portrait-shaped (w < h)", w < h,
          f"got {w} × {h}")
    c.short_edge_spin.setValue(1080)

    # -- frame row: slider <-> spinbox sync -----------------------------------
    check("initial frame value 5.00",
          c.frame_spin.value() == 5.0 and c.frame_slider.value() == 500)
    c.frame_spin.setValue(7.5)
    app.processEvents()
    check("spin 7.5 -> slider 750", c.frame_slider.value() == 750,
          f"got {c.frame_slider.value()}")
    c.frame_slider.setValue(300)
    app.processEvents()
    check("slider 300 -> spin 3.00", c.frame_spin.value() == 3.0,
          f"got {c.frame_spin.value()}")
    c.frame_spin.setValue(5.0)
    app.processEvents()

    spec = c.output_spec()
    check("output_spec() snapshot",
          spec == OutputSpec(4, 5, True, 1080, 5.0), f"got {spec}")

    # -- running state ------------------------------------------------------------
    c.set_running(True)
    app.processEvents()
    check("running: output/frame controls disabled",
          not c.aspect_combo.isEnabled()
          and not c.custom_box.isEnabled()
          and not c.aspect_num_spin.isEnabled()
          and not c.aspect_den_spin.isEnabled()
          and not c.orientation_button.isEnabled()
          and not c.short_edge_spin.isEnabled()
          and not c.frame_slider.isEnabled()
          and not c.frame_spin.isEnabled())
    check("running: start disabled, cancel enabled",
          not c.start_button.isEnabled() and c.cancel_button.isEnabled())
    check("running: progress spinner visible + spinning",
          c.progress_spinner.isVisible() and c.progress_spinner.spinning)

    c.set_progress(1, 3, 0.4, "a.jpg")
    app.processEvents()
    check("progress: status text '1 of 3 — a.jpg'",
          c.status_label.text() == "1 of 3 — a.jpg",
          f"got {c.status_label.text()!r}")
    check("progress: bar ≈ 40", c.progress_bar.value() == 40,
          f"got {c.progress_bar.value()}")

    for _ in range(6):
        app.processEvents()
    c.grab().save(str(SCREENSHOTS / "phase4-controls-running.png"))
    print(f"wrote {SCREENSHOTS / 'phase4-controls-running.png'}")

    # -- back to idle -------------------------------------------------------------
    c.set_running(False, "Batch finished")
    app.processEvents()
    check("idle: status label = current_label",
          c.status_label.text() == "Batch finished")
    check("idle: cancel disabled", not c.cancel_button.isEnabled())
    check("idle: spinner hidden", not c.progress_spinner.isVisible())
    c.set_start_enabled(True)
    check("set_start_enabled(True)", c.start_button.isEnabled())

    # idle screenshot with a neutral progress state
    c.set_progress(0, 0, 0.0)
    c.status_label.setText("")
    for _ in range(3):
        app.processEvents()
    c.grab().save(str(SCREENSHOTS / "phase4-controls-idle.png"))
    print(f"wrote {SCREENSHOTS / 'phase4-controls-idle.png'}")

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
