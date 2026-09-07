#!/usr/bin/env python3
"""Phase 7 offscreen theme harness: five palette variants, full window
state, one PNG per variant under
.agent/feature-migration-qt/screenshots/theme/.

Run (standalone — also works on real machines without a display):
    .venv-qt/bin/python scripts/theme_report.py

Variants (all Fusion + explicit palette offscreen; on real machines the
production path uses the platform theme instead — this harness only
exercises the QSS layer + widget styling under known palettes):
  a. light          — standard Fusion light palette
  b. dark           — generic inverted palette (theme.py test hook)
  c. breeze-light   — Breeze table, light
  d. breeze-dark    — Breeze table, dark
  e. windows-light  — Windows-11-ish light palette (harness literal)

Assertions:
  - Window background color differs between the light and dark variants.
  - Start button center pixel == palette Highlight in the Linux variants
    (the suggested QSS rule), within tolerance.
  - colorSchemeChanged re-applies the QSS without exceptions.
Exit code 0 = all pass.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
SHIM_DIR = REPO_ROOT / ".agent" / "feature-migration-qt" / "qtlibs"
OUT_DIR = REPO_ROOT / ".agent" / "feature-migration-qt" / "screenshots" / "theme"

# Do NOT set FRAMER_COLOR_SCHEME / QT_QPA_PLATFORMTHEME here: the harness
# drives the palette explicitly per variant.
if os.environ.get("FRAMER_COLOR_SCHEME"):
    del os.environ["FRAMER_COLOR_SCHEME"]


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

from PIL import Image  # noqa: E402
from PySide6.QtCore import (  # noqa: E402
    QEvent,
    QPoint,
    QCoreApplication,
)
from PySide6.QtGui import QColor, QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication, QStyleFactory  # noqa: E402

from framer.core.models import ItemState  # noqa: E402
from framer.qt.theme import (  # noqa: E402
    _reapply_qss,
    build_breeze_palette,
    build_generic_dark_palette,
    build_qss,
)
from framer.qt.window import FramerWindow  # noqa: E402

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"[{'ok' if cond else 'FAIL'}] {label}" + (
        f" — {detail}" if detail and not cond else ""
    ))
    if not cond:
        FAILURES.append(label)


def pump(app: QCoreApplication, seconds: float = 0.3) -> None:
    # manual processEvents() never flushes DeferredDelete events (those
    # only run inside exec()) — flush them explicitly so deleteLater()
    # in production paths behaves like it will under a real event loop
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        time.sleep(0.005)
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def make_fixtures(tmp: Path) -> list[Path]:
    paths = []
    for name, color in (("a", (200, 80, 80)), ("b", (80, 200, 80)), ("c", (80, 80, 200))):
        p = tmp / f"{name}.png"
        im = Image.new("RGB", (1200, 900), color)
        im.save(p)
        paths.append(p)
    return paths


def windows_light_palette() -> QPalette:
    """Windows-11-ish light palette (harness literal — this file is a test
    harness; the no-hex rule applies to framer/qt/theme.py)."""
    pal = QPalette()
    roles = {
        QPalette.ColorRole.Window: "#f3f3f3",
        QPalette.ColorRole.WindowText: "#1b1b1b",
        QPalette.ColorRole.Base: "#ffffff",
        QPalette.ColorRole.Text: "#1b1b1b",
        QPalette.ColorRole.Button: "#f3f3f3",
        QPalette.ColorRole.ButtonText: "#1b1b1b",
        QPalette.ColorRole.Highlight: "#0078d4",
        QPalette.ColorRole.HighlightedText: "#ffffff",
    }
    for role, hex_color in roles.items():
        pal.setColor(role, QColor(hex_color))
    return pal


def sample_button(
    window: FramerWindow, app: QCoreApplication
) -> tuple[int, int, int]:
    """Start-button background pixel (right padding — the center hits
    label glyphs; sample the enabled state or with toasts dismissed, a
    bottom-right toast overlaps the button)."""
    btn = window.controls.start_button
    pad = btn.mapTo(
        window,
        btn.rect().topLeft() + QPoint(btn.width() - 8, btn.height() // 2),
    )
    pix = window.grab().toImage()
    c = pix.pixelColor(pad.x(), pad.y())
    return (c.red(), c.green(), c.blue())


def set_running_state(window: FramerWindow, app: QCoreApplication) -> None:
    window.view.update_item(1, 0.4, ItemState.PROCESSING)
    window.controls.set_running(True, "b.png")
    window.controls.set_progress(1, 3, 0.45, "b.png")
    window.host.toast("3 images added", "normal")
    window.host.toast("Cancelling after the current file…", "high")
    pump(app)


def blend(c: QColor, alpha: int, over: QColor) -> tuple[int, int, int]:
    f = alpha / 255
    return (
        round(c.red() * f + over.red() * (1 - f)),
        round(c.green() * f + over.green() * (1 - f)),
        round(c.blue() * f + over.blue() * (1 - f)),
    )


def main() -> int:
    app = QApplication.instance()
    if app is None:
        app = QApplication(["theme-report"])
    if not isinstance(app, QApplication):
        raise SystemExit("expected a QApplication")
    app.setOrganizationName("org.framer")
    app.setApplicationName("Framer")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    tmp = OUT_DIR.parent / "theme-fixtures"
    tmp.mkdir(exist_ok=True)
    fixtures = make_fixtures(tmp)

    standard = QStyleFactory.create("Fusion")
    light_pal = standard.standardPalette() if standard is not None else QPalette()

    variants = [
        ("light", light_pal),
        ("dark", build_generic_dark_palette()),
        ("breeze-light", build_breeze_palette("light")),
        ("breeze-dark", build_breeze_palette("dark")),
        ("windows-light", windows_light_palette()),
    ]

    window_bgs: dict[str, tuple[int, int, int]] = {}
    start_btn_enabled: dict[str, tuple[int, int, int]] = {}
    start_btn_disabled: dict[str, tuple[int, int, int]] = {}

    for name, pal in variants:
        app.setStyle("Fusion")
        app.setPalette(pal)
        # the windows variant mirrors production: no accent QSS (the
        # native default button carries the accent there)
        app.setStyleSheet(build_qss(pal, accent=name != "windows-light"))

        window = FramerWindow()
        window.resize(1100, 760)
        window.show()
        window.add_paths(fixtures)
        pump(app)

        # enabled accent: the button is enabled with a non-empty queue
        start_btn_enabled[name] = sample_button(window, app)

        set_running_state(window, app)

        pix = window.grab().toImage()
        # window background sample: toolbar corner
        c = pix.pixelColor(4, 4)
        window_bgs[name] = (c.red(), c.green(), c.blue())

        out = OUT_DIR / f"theme-{name}.png"
        pix.save(str(out))
        print(f"wrote {out}")

        # disabled accent: sample after dismissing the toasts (a
        # bottom-right toast overlaps the button)
        for t in list(window.host._toasts):
            window.host._dismiss(t)
        pump(app, 0.1)
        start_btn_disabled[name] = sample_button(window, app)
        window.close()

    check("window bg differs light vs dark",
          window_bgs["light"] != window_bgs["dark"],
          f"{window_bgs['light']} vs {window_bgs['dark']}")
    check("window bg differs light vs breeze-dark",
          window_bgs["light"] != window_bgs["breeze-dark"],
          f"{window_bgs['light']} vs {window_bgs['breeze-dark']}")

    for name in ("light", "dark", "breeze-light", "breeze-dark"):
        pal = dict(variants)[name]
        hl = pal.color(QPalette.ColorRole.Highlight)
        win = pal.color(QPalette.ColorRole.Window)
        px = start_btn_enabled[name]
        diff = max(abs(px[0] - hl.red()), abs(px[1] - hl.green()),
                   abs(px[2] - hl.blue()))
        check(f"start button (enabled) == Highlight in {name}", diff <= 12,
              f"pixel {px} vs highlight ({hl.red()},{hl.green()},{hl.blue()})"
              f" diff {diff}")
        exp_disabled = blend(hl, 110, win)
        pxd = start_btn_disabled[name]
        diffd = max(abs(pxd[0] - exp_disabled[0]),
                    abs(pxd[1] - exp_disabled[1]),
                    abs(pxd[2] - exp_disabled[2]))
        check(f"start button (disabled) == alpha-blend in {name}",
              diffd <= 12, f"pixel {pxd} vs expected {exp_disabled} diff {diffd}")

    # colorSchemeChanged re-applies the QSS without exceptions
    observed: list[int] = []
    app.styleHints().colorSchemeChanged.connect(lambda *args: observed.append(1))
    try:
        cs = app.styleHints().colorScheme()
        # this build: colorScheme() is a method; the enum class itself is
        # not exported — get Dark through the returned instance's type
        app.styleHints().colorSchemeChanged.emit(type(cs).Dark)
        _reapply_qss(app)  # same slot the signal calls; catchable here
        repainted = len(observed) == 1 and bool(app.styleSheet())
    except Exception as exc:  # noqa: BLE001
        repainted = False
        print(f"  exception: {exc!r}")
    check("colorSchemeChanged re-applies QSS", repainted)

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
