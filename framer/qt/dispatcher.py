"""Dispatcher: 60 ms QTimer tick draining worker queues on the main thread.

The only place events become Qt signal emissions. Also manages the
thumbnail pipeline: PIL work happens off the main thread on a thread
pool, the resulting PNG bytes are queued, and the ``QPixmap`` is created
on the main thread during the tick (Qt object thread-affinity).
"""
from __future__ import annotations

import os
import queue as queue_mod
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QImage, QPixmap

from .bus import SignalBus
from .thumbnails import make_thumbnail_png

TICK_MS = 60
MAX_EVENTS_PER_TICK = 1000


class Dispatcher(QObject):
    """Owns the :class:`SignalBus`; emits its signals from the main thread.

    Must be created on the main thread (QTimer thread-affinity).
    """

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.bus = SignalBus()
        self._queues: list[queue_mod.Queue] = []
        self._thumb_queue: "queue_mod.Queue[tuple[str, object, bytes | None]]" = (
            queue_mod.Queue()
        )
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._thumb_cb: Optional[
            Callable[[object, Optional[QPixmap]], None]
        ] = None
        self._executor = ThreadPoolExecutor(
            max_workers=min(4, os.cpu_count() or 2),
            thread_name_prefix="framer-thumb",
        )

    # -- queue wiring -----------------------------------------------------

    def attach(self, q: "queue_mod.Queue") -> None:
        """Attach a worker event queue to the tick."""
        if q not in self._queues:
            self._queues.append(q)

    def add_thumbnail_provider(self, fn: Callable[[object, Optional[QPixmap]], None]) -> None:
        """Register a callback receiving ``(item, QPixmap | None)``.

        In addition to the ``bus.thumbnail`` signal emission, the provider
        (if any) is called for every thumbnail event.
        """
        self._thumb_cb = fn

    def request_thumbnail(self, item, path) -> None:
        """Generate a thumbnail for ``path`` on the pool (never main thread)."""
        self._executor.submit(self._thumb_task, item, Path(path))

    def _thumb_task(self, item, path: Path) -> None:
        try:
            png = make_thumbnail_png(path)
        except Exception:
            png = None
        self._thumb_queue.put(("thumbnail", item, png))

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    # -- tick ---------------------------------------------------------------

    def _tick(self) -> None:
        count = 0
        for q in (*self._queues, self._thumb_queue):
            while count < MAX_EVENTS_PER_TICK:
                try:
                    event = q.get_nowait()
                except queue_mod.Empty:
                    break
                try:
                    self._dispatch(event)
                except Exception:
                    # One bad event must not kill the tick (parity with the
                    # per-item error isolation of the batch worker).
                    traceback.print_exc()
                count += 1

    def _dispatch(self, event: tuple) -> None:
        kind = event[0]
        if kind == "item-started":
            self.bus.item_started.emit(event[1])
        elif kind == "item-progress":
            self.bus.item_progress.emit(event[1], event[2])
        elif kind == "item-finished":
            self.bus.item_finished.emit(event[1], bool(event[2]), event[3])
        elif kind == "job-finished":
            self.bus.job_finished.emit(event[1], event[2], event[3], event[4])
        elif kind == "thumbnail":
            item, png = event[1], event[2]
            pixmap: Optional[QPixmap] = None
            if png is not None:
                image = QImage()
                if image.loadFromData(png):  # PNG bytes, auto-detected
                    pixmap = QPixmap.fromImage(image)
            self.bus.thumbnail.emit(item, pixmap)
            if self._thumb_cb is not None:
                self._thumb_cb(item, pixmap)
