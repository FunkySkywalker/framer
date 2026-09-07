"""Dispatcher: 60 ms GLib tick draining worker queues on the main thread.

The only place events become GObject signal emissions. Also manages the
thumbnail thread pool (thumbnails are produced off the main thread and
delivered through the same tick).
"""
from __future__ import annotations

import os
import queue as queue_mod
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib

from ..utils.thumbnails import make_thumbnail
from .signals import SignalBus

TICK_MS = 60
MAX_EVENTS_PER_TICK = 1000


class Dispatcher:
    """Owns the :class:`SignalBus`; emits its signals from the main thread."""

    def __init__(self) -> None:
        self.bus = SignalBus()
        self._queues: list[queue_mod.Queue] = []
        self._thumb_queue: "queue_mod.Queue" = queue_mod.Queue()
        self._timeout_id: Optional[int] = None
        self._thumb_cb: Optional[Callable[[object, object], None]] = None
        self._executor = ThreadPoolExecutor(
            max_workers=min(4, os.cpu_count() or 2),
            thread_name_prefix="framer-thumb",
        )

    # -- queue wiring -----------------------------------------------------

    def attach(self, q: "queue_mod.Queue") -> None:
        """Attach a worker event queue to the tick."""
        if q not in self._queues:
            self._queues.append(q)

    def add_thumbnail_provider(self, fn: Callable[[object, object], None]) -> None:
        """Register the callback receiving ``(item, texture | None)``."""
        self._thumb_cb = fn

    def request_thumbnail(self, item, path) -> None:
        """Generate a thumbnail for ``path`` on the pool (never main thread)."""
        self._executor.submit(self._thumb_task, item, Path(path))

    def _thumb_task(self, item, path: Path) -> None:
        try:
            texture = make_thumbnail(path)
        except Exception:
            texture = None
        self._thumb_queue.put(("thumbnail", item, texture))

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        if self._timeout_id is None:
            self._timeout_id = GLib.timeout_add(TICK_MS, self._tick)

    def stop(self) -> None:
        if self._timeout_id is not None:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = None

    # -- tick ---------------------------------------------------------------

    def _tick(self) -> bool:
        count = 0
        for q in (*self._queues, self._thumb_queue):
            while count < MAX_EVENTS_PER_TICK:
                try:
                    event = q.get_nowait()
                except queue_mod.Empty:
                    break
                self._dispatch(event)
                count += 1
        return True

    def _dispatch(self, event: tuple) -> None:
        kind = event[0]
        if kind == "item-started":
            self.bus.emit("item-started", event[1])
        elif kind == "item-progress":
            self.bus.emit("item-progress", event[1], event[2])
        elif kind == "item-finished":
            self.bus.emit("item-finished", event[1], bool(event[2]), event[3])
        elif kind == "job-finished":
            self.bus.emit("job-finished", event[1], event[2], event[3], event[4])
        elif kind == "thumbnail":
            if self._thumb_cb is not None:
                self._thumb_cb(event[1], event[2])
