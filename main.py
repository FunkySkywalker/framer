#!/usr/bin/env python3
"""Framer entry point — thin CLI wrapper around FramerApplication.

Usage:
    python3 main.py [IMAGE ...]

Requires PyGObject + Libadwaita from the system (Ubuntu 26.04 desktop has
both); see README.md for the two supported run paths.
"""
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from framer.gtk.app import FramerApplication


def main() -> int:
    return FramerApplication().run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
