"""Batch job: one worker thread, a cancel event, an event queue.

The worker never touches GTK. It updates the ``QueueItem`` objects in
place (only the worker writes them; the main thread reads them through
the events pushed to the queue) and pushes plain event tuples.
"""
from __future__ import annotations

import queue as queue_mod
import threading
from typing import Optional

from ..core.image_io import ProcessingCancelled, frame_image
from ..core.models import ItemState, OutputSpec, QueueItem
from ..core.output import resolve_output
from .signals import SignalBus


class BatchJob:
    """Runs ``items`` through the framing pipeline on a daemon thread.

    ``spec`` is the immutable ``OutputSpec`` snapshotted by the UI at job
    start (all output/frame controls are insensitive while running), so
    nothing can change mid-batch.
    """

    def __init__(
        self,
        items: list[QueueItem],
        bus: SignalBus,
        suffix: str,
        output_dir: str,
        spec: OutputSpec,
    ) -> None:
        self.items = list(items)
        self.bus = bus
        self.suffix = suffix
        self.output_dir = output_dir
        self.spec = spec
        self._events: "queue_mod.Queue" = queue_mod.Queue()
        self._cancel = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def event_queue(self) -> "queue_mod.Queue":
        """Worker→main event queue (attach to the Dispatcher)."""
        return self._events

    def start(self) -> None:
        self._cancel.clear()
        self._thread = threading.Thread(
            target=self._run, name="framer-batch", daemon=True
        )
        self._thread.start()

    def cancel(self) -> None:
        """Request cancellation; checked between files and between stages."""
        self._cancel.set()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _emit(self, *event: object) -> None:
        self._events.put(event)

    def _run(self) -> None:
        try:
            self._run_batch()
        except BaseException:
            # Last resort: the UI must always learn the batch is over.
            for item in self.items:
                if item.state in (ItemState.QUEUED, ItemState.PROCESSING):
                    item.state = ItemState.ERROR
                    item.error = "worker thread crashed"
            self._emit("job-finished", len(self.items), 0, len(self.items), 0)

    def _run_batch(self) -> None:
        items = self.items
        done = failed = cancelled = 0
        for i, item in enumerate(items):
            if self._cancel.is_set():
                cancelled = len(items) - i
                for j in range(i, len(items)):
                    items[j].state = ItemState.CANCELLED
                break

            self._emit("item-started", i)
            item.state = ItemState.PROCESSING
            item.fraction = 0.0
            try:
                out = resolve_output(item.path, self.suffix, self.output_dir)

                def progress_cb(frac: float, _i: int = i) -> None:
                    item.fraction = frac
                    self._emit("item-progress", _i, frac)

                result = frame_image(
                    item.path,
                    out,
                    self.spec,
                    progress_cb=progress_cb,
                    cancel_event=self._cancel,
                )
                item.state = ItemState.DONE
                item.output_path = out
                item.error = None
                item.warnings = list(result.warnings)
                done += 1
                self._emit("item-finished", i, True, "")
            except ProcessingCancelled:
                # Stopped before anything was written for this item.
                item.state = ItemState.CANCELLED
                cancelled += 1
                for j in range(i + 1, len(items)):
                    items[j].state = ItemState.CANCELLED
                    cancelled += 1
                self._emit("item-finished", i, True, "")
                break
            except Exception as exc:  # per-item isolation: batch continues
                item.state = ItemState.ERROR
                item.error = str(exc) or exc.__class__.__name__
                failed += 1
                self._emit("item-finished", i, False, item.error)
        self._emit("job-finished", len(items), done, failed, cancelled)
