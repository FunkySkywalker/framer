"""``python -m framer`` entry point."""
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from .app import FramerApplication


def main() -> int:
    return FramerApplication().run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
