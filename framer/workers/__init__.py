"""Shared background threads.

``batch_worker`` (BatchJob) is pure — no GTK, no Qt — and is used by
both frontends (``framer.gtk`` and ``framer.qt``). Worker threads push
plain event tuples onto ``queue.Queue``s; each frontend's dispatcher
(Gtk: ``framer.gtk.dispatcher`` with a 60 ms GLib tick, Qt:
``framer.qt.dispatcher`` with a 60 ms QTimer) drains them on the main
thread.
"""
