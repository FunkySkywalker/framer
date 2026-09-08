"""Qt signal bus — direct analog of the GTK ``GObject`` SignalBus.

The Dispatcher is the only object allowed to emit these signals, so all
emissions land on the main thread (the dispatcher's QTimer tick).
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class SignalBus(QObject):
    """Declared signals (same payloads as the GTK signals, Qt naming):

    - ``item_started(idx)``                          — index in the batch
    - ``item_progress(idx, fraction)``               — index, stage fraction
    - ``item_finished(idx, ok, error)``              — index, ok, error message
    - ``job_finished(total, done, failed, cancelled)``
    - ``thumbnail(item, pixmap)`` — item: ``framer.core.models.QueueItem``,
      pixmap: ``QPixmap | None`` (None = thumbnail generation failed, the
      UI shows the missing-image placeholder). ``object`` argument types
      keep the signal free of core/Qt metatype registration issues; the
      payloads are the documented ones above.
    """

    item_started = Signal(int)
    item_progress = Signal(int, float)
    item_finished = Signal(int, bool, str)
    job_finished = Signal(int, int, int, int)
    thumbnail = Signal(object, object)
