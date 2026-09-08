#!/usr/bin/env python3
"""Framer (Qt) entry point — thin CLI wrapper around FramerQtApp.

Usage:
    python3 main_qt.py [IMAGE ...]

Runs from the PySide6 venv:

    python3 -m venv .venv-qt
    .venv-qt/bin/pip install PySide6 Pillow
    .venv-qt/bin/python main_qt.py

The GTK entry point (main.py) stays alive until the cutover phase.
"""
from __future__ import annotations

import sys
from pathlib import Path

from framer.qt.app import FramerQtApp


def main() -> int:
    files = [Path(arg) for arg in sys.argv[1:]]
    return FramerQtApp(files=files).run()


if __name__ == "__main__":
    raise SystemExit(main())
