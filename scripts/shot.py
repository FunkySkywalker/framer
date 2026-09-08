#!/usr/bin/env python3
"""Offscreen screenshot helper for the Qt migration (dev-VM friendly).

Usage:
    .venv-qt/bin/python scripts/shot.py <dotted.WidgetClass> <name>
        [--attr PROP] [--size WxH]

Builds the given widget class, pumps events briefly, and saves
``widget.grab()`` to ``.agent/feature-migration-qt/screenshots/<name>.png``.

Dev-VM setup (no display, no libEGL): the script sets
``QT_QPA_PLATFORM=offscreen`` and, when the shim directory
``.agent/feature-migration-qt/qtlibs/`` exists, re-execs itself once with
the libEGL shim on ``LD_LIBRARY_PATH`` (the dynamic linker only reads that
variable at process start, so the re-exec is required). On a real desktop
(Ubuntu 26.04 with libegl1 installed) both mechanisms are no-ops.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SHIM_DIR = REPO_ROOT / ".agent" / "feature-migration-qt" / "qtlibs"
SCREENSHOTS = REPO_ROOT / ".agent" / "feature-migration-qt" / "screenshots"

# Running ``python scripts/shot.py`` puts scripts/ on sys.path, not the repo
# root, so ``import framer`` would fail.
sys.path.insert(0, str(REPO_ROOT))


def _ensure_env() -> None:
    """Set QT_QPA_PLATFORM / LD_LIBRARY_PATH, re-exec once if needed."""
    needs_exec = os.environ.get("QT_QPA_PLATFORM") != "offscreen"
    if SHIM_DIR.is_dir():
        on_path = str(SHIM_DIR) in os.environ.get("LD_LIBRARY_PATH", "").split(os.pathsep)
        needs_exec = needs_exec or not on_path
    if not needs_exec:
        return
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    if SHIM_DIR.is_dir():
        existing = os.environ.get("LD_LIBRARY_PATH", "")
        os.environ["LD_LIBRARY_PATH"] = (
            str(SHIM_DIR) + (os.pathsep + existing if existing else "")
        )
    os.execve(sys.executable, [sys.executable, *sys.argv], os.environ)


def main() -> int:
    _ensure_env()

    argv = sys.argv[1:]
    if len(argv) < 2:
        print(__doc__)
        return 2
    dotted, name = argv[0], argv[1]

    attr: str | None = None
    size: tuple[int, int] | None = None
    rest = argv[2:]
    i = 0
    while i < len(rest):
        if rest[i] == "--attr" and i + 1 < len(rest):
            attr = rest[i + 1]
            i += 2
        elif rest[i] == "--size" and i + 1 < len(rest):
            w, _, h = rest[i + 1].partition("x")
            size = (int(w), int(h))
            i += 2
        else:
            print(f"unknown argument: {rest[i]}", file=sys.stderr)
            return 2

    from PySide6.QtWidgets import QApplication, QWidget

    app = QApplication.instance() or QApplication(["framer-shot"])

    mod_name, _, cls_name = dotted.rpartition(".")
    if not mod_name:
        print(f"expected module.Class, got: {dotted}", file=sys.stderr)
        return 2
    cls = getattr(importlib.import_module(mod_name), cls_name)
    widget: QWidget = cls()
    if attr is not None:
        widget = getattr(widget, attr)
    if not isinstance(widget, QWidget):
        print(f"{dotted} is not a QWidget: {type(widget)!r}", file=sys.stderr)
        return 1
    if size is not None:
        widget.resize(*size)
    widget.show()
    for _ in range(10):
        app.processEvents()

    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    out = SCREENSHOTS / f"{name}.png"
    widget.grab().save(str(out))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
