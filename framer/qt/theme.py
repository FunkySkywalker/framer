"""Theming: follow the system, with a minimal palette-derived QSS layer.

``pre_setup_environment()`` runs BEFORE any QApplication exists;
``apply_theme(app)`` runs before any window is built (production:
``FramerQtApp``; tests: ``FramerWindow`` self-applies — idempotent).

Platform decisions (explicit, no implicit auto-selection):
- ``FRAMER_COLOR_SCHEME=light|dark`` env override forces the palette —
  also the offscreen test hook (the gtk3 platform theme needs a display
  and aborts under the offscreen platform).
- Windows: no style, no palette — the native ``windows11``/``Windows``
  style, system palette, accent color, and dark-mode following are all
  automatic; the accent QSS is skipped (the native default button
  carries the accent — Start Framing is set as the default button).
- GNOME: ``QT_QPA_PLATFORMTHEME=gtk3`` (set in pre_setup_environment)
  delivers the Yaru palette, font, icon theme, and light/dark following
  via the bundled gtk3 platform-theme plugin.
- Plasma: no native Qt plugin exists → Fusion + the built-in Breeze
  palette table (the only color literals in this file); scheme from
  ``QStyleHints.colorScheme`` when known, else light.
- Otherwise: Fusion + system palette.

The QSS layer (``build_qss``) computes every color from the live
palette; it is re-applied on ``QStyleHints.colorSchemeChanged`` for
live light/dark switching without restart. No font rules (the
platform theme supplies fonts).
"""
from __future__ import annotations

import os
import sys

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyle, QStyleFactory

#: The ONLY color literals in this file: the Breeze palette table
#: (used only when no native Plasma plugin is available).
BREEZE: dict[str, dict[str, str]] = {
    "light": {
        "Window": "#eff0f1",
        "WindowText": "#232629",
        "Base": "#ffffff",
        "Text": "#232629",
        "Button": "#eff0f1",
        "ButtonText": "#232629",
        "Highlight": "#3daee9",
        "HighlightedText": "#ffffff",
    },
    "dark": {
        "Window": "#31363b",
        "WindowText": "#eff0f1",
        "Base": "#232629",
        "Text": "#eff0f1",
        "Button": "#31363b",
        "ButtonText": "#eff0f1",
        "Highlight": "#3daee9",
        "HighlightedText": "#ffffff",
    },
}

_BREEZE_ROLES = {
    name: getattr(QPalette.ColorRole, name) for name in BREEZE["light"]
}

#: Neutral roles inverted for the generic dark palette (test hook).
#: Vivid roles (Highlight, HighlightedText, Link, disabled text) are
#: kept as-is — a dark palette needs light text, which falls out of
#: inverting the light palette's dark text.
_INVERT_ROLES = (
    QPalette.ColorRole.Window,
    QPalette.ColorRole.WindowText,
    QPalette.ColorRole.Base,
    QPalette.ColorRole.AlternateBase,
    QPalette.ColorRole.Text,
    QPalette.ColorRole.Button,
    QPalette.ColorRole.ButtonText,
    QPalette.ColorRole.BrightText,
    QPalette.ColorRole.Light,
    QPalette.ColorRole.Midlight,
    QPalette.ColorRole.Mid,
    QPalette.ColorRole.Dark,
    QPalette.ColorRole.Shadow,
    QPalette.ColorRole.PlaceholderText,
)


def detect_desktop() -> str:
    """``'windows' | 'gnome' | 'plasma' | 'other'``."""
    if sys.platform.startswith("win"):
        return "windows"
    xd = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    if "GNOME" in xd:
        return "gnome"
    if "KDE" in xd or "PLASMA" in xd:
        return "plasma"
    return "other"


def pre_setup_environment() -> None:
    """Must run before the QApplication exists.

    GNOME: enable the bundled gtk3 platform-theme plugin (Yaru palette,
    font, icon theme, light/dark following). No-op elsewhere.
    """
    if detect_desktop() == "gnome":
        os.environ["QT_QPA_PLATFORMTHEME"] = "gtk3"


def build_breeze_palette(scheme: str) -> QPalette:
    """A Breeze palette (``'light' | 'dark'``) from the table above."""
    table = BREEZE["dark" if scheme == "dark" else "light"]
    pal = QPalette()
    for role_name, hex_color in table.items():
        pal.setColor(_BREEZE_ROLES[role_name], QColor(hex_color))
    return pal


def build_generic_dark_palette() -> QPalette:
    """Generic dark palette derived by inverting the neutral roles of
    the style's standard (light) palette. Test hook only
    (``FRAMER_COLOR_SCHEME=dark`` on non-Plasma desktops)."""
    style = QStyleFactory.create("Fusion")
    pal = style.standardPalette() if style is not None else QPalette()
    for role in _INVERT_ROLES:
        c = pal.color(role)
        pal.setColor(
            role, QColor(255 - c.red(), 255 - c.green(), 255 - c.blue(), 255)
        )
    return pal


def build_qss(pal: QPalette, accent: bool) -> str:
    """The palette-derived QSS layer.

    Every color is computed from the live palette (no hex literals).
    ``accent=False`` (Windows) skips the accent-button rules — the
    native default button carries the system accent there, and QSS
    would break the Fluent look.
    """
    window = pal.color(QPalette.ColorRole.Window)
    text = pal.color(QPalette.ColorRole.Text)
    button = pal.color(QPalette.ColorRole.Button)
    highlight = pal.color(QPalette.ColorRole.Highlight)
    highlighted_text = pal.color(QPalette.ColorRole.HighlightedText)

    def rgba(c: QColor, alpha: int) -> str:
        return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"

    rules = [
        # toasts (Qt 6.11 has no Error palette role — the palette
        # highlight doubles as the "needs attention" accent)
        "#toast { background-color: %s; color: %s; border: 1px solid %s;"
        " border-radius: 8px; }" % (window.name(), text.name(), button.name()),
        "#toast-high { background-color: %s; color: %s; border: 2px solid %s;"
        " border-radius: 8px; }" % (window.name(), text.name(), highlight.name()),
        "#toast QLabel, #toast-high QLabel { background: transparent;"
        " color: %s; }" % text.name(),
        # dim labels: Text at ~55 % alpha
        'QLabel[dim="true"] { color: %s; }' % rgba(text, 140),
        # queue rows: hover tint, no selection highlight
        "QueueRow { background: transparent; border: none; }",
        "QueueRow:hover { background-color: %s; }" % rgba(button, 31),
    ]
    if accent:
        rules += [
            # accent buttons (Start Framing, empty-state Add Images)
            'QPushButton[suggested="true"] { background-color: %s; color: %s;'
            " border: none; border-radius: 6px; padding: 5px 14px; }"
            % (highlight.name(), highlighted_text.name()),
            'QPushButton[suggested="true"]:disabled { background-color: %s;'
            " color: %s; }" % (rgba(highlight, 110), rgba(highlighted_text, 120)),
        ]
    return "\n".join(rules)


def _reapply_qss(app: QApplication, *signal_args: object) -> None:
    # colorSchemeChanged passes the ColorScheme enum — the slot must
    # accept it (PySide does NOT drop extra signal arguments)
    accent_prop = app.property("_framer_accent")
    accent = bool(accent_prop) if accent_prop is not None else True
    app.setStyleSheet(build_qss(app.palette(), accent))


def apply_theme(app: QApplication) -> None:
    """Idempotent platform theming + QSS layer.

    Call before any window is built so widgets inherit the final
    palette. ``FramerWindow`` self-applies for direct construction
    (verification scripts).
    """
    if app.property("_framer_theme"):
        return
    desktop = detect_desktop()
    env_scheme = os.environ.get("FRAMER_COLOR_SCHEME", "").strip().lower()

    accent = desktop != "windows"
    if accent:
        if desktop == "plasma":
            scheme = env_scheme
            if scheme not in ("light", "dark"):
                # this PySide6 build exposes colorScheme() as a method
                # and does not export the enum class — compare by name
                hints_scheme = str(app.styleHints().colorScheme())
                scheme = "dark" if hints_scheme.endswith("Dark") else "light"
            app.setStyle("Fusion")
            app.setPalette(build_breeze_palette(scheme))
        elif env_scheme in ("light", "dark"):
            # offscreen test hook (the gtk3 theme cannot load offscreen)
            app.setStyle("Fusion")
            if env_scheme == "dark":
                app.setPalette(build_generic_dark_palette())
    # GNOME / other / Windows: the platform supplies style + palette
    # (or, on GNOME offscreen, Qt's generic defaults are fine).
    app.setStyleSheet(build_qss(app.palette(), accent))
    app.styleHints().colorSchemeChanged.connect(_reapply_qss)
    app.setProperty("_framer_theme", True)
    app.setProperty("_framer_accent", accent)
