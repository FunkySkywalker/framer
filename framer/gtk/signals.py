"""GObject signal bus.

A ``GObject.Object`` with the four declared batch signals. The Dispatcher
is the only object allowed to emit them, so signal emission always lands
on the main thread.
"""
from __future__ import annotations

from gi.repository import GObject  # auto-loaded with Gtk/Adw (version 2.0)


class SignalBus(GObject.GObject):
    """Declared signals:

    - ``item-started``  (int)                       — index in the batch
    - ``item-progress`` (int, float)                — index, stage fraction
    - ``item-finished`` (int, boolean, string)      — index, ok, error message
    - ``job-finished``  (int, int, int, int)        — total, done, failed, cancelled
    """

    __gtype_name__ = "FramerSignalBus"
    _signals_defined = False

    def __init__(self) -> None:
        super().__init__()
        if not SignalBus._signals_defined:
            flags = GObject.SignalFlags.RUN_FIRST
            GObject.signal_new(
                "item-started", SignalBus, flags, GObject.TYPE_NONE, (int,)
            )
            GObject.signal_new(
                "item-progress", SignalBus, flags, GObject.TYPE_NONE, (int, float)
            )
            GObject.signal_new(
                "item-finished", SignalBus, flags, GObject.TYPE_NONE, (int, bool, str)
            )
            GObject.signal_new(
                "job-finished", SignalBus, flags, GObject.TYPE_NONE, (int, int, int, int)
            )
            SignalBus._signals_defined = True
