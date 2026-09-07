"""Adw.Toast helpers."""
from __future__ import annotations

import gi

gi.require_version("Adw", "1")
from gi.repository import Adw


def toast(
    overlay,
    message: str,
    priority=Adw.ToastPriority.NORMAL,
    timeout: float = 3.0,
):
    """Add a toast to ``overlay`` and return the toast object."""
    t = Adw.Toast.new(message)
    t.set_priority(priority)
    t.set_timeout(timeout)
    overlay.add_toast(t)
    return t


def success_overlay(overlay, message: str, timeout: float = 3.0) -> None:
    """Normal-priority success toast (Adw 1.9 has no LOW priority)."""
    toast(overlay, message, Adw.ToastPriority.NORMAL, timeout)


def error_overlay(overlay, message: str, timeout: float = 5.0) -> None:
    """High-priority error toast."""
    toast(overlay, message, Adw.ToastPriority.HIGH, timeout)
