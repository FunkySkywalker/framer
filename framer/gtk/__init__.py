"""GTK4 + Libadwaita frontend (PyGObject).

One of two frontends sharing the pure core (``framer.core``) and the
batch worker (``framer.workers.batch_worker``); the other is
``framer.qt`` (PySide6). The GTK app is frozen during the Qt migration
and is removed at the Phase 8 cutover — see
``.agent/feature-migration-qt/plan.md``.

Threading law: all GTK calls happen on the main thread only; worker
threads push plain event tuples onto ``queue.Queue``s that
``framer.gtk.dispatcher.Dispatcher`` drains with a 60 ms GLib tick.
``framer.gtk.thumbnails`` is the one sanctioned exception: it produces
``Gdk.Texture``s on the Dispatcher's thread pool and the result is
consumed on the main thread.
"""
