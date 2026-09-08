"""Qt (PySide6) frontend package for Framer.

UI-layer replacement for the GTK 4 / Libadwaita frontend. ``framer.core``
stays pure (never imports Qt); all Qt objects are created and used on the
main thread only. Worker threads communicate through plain event tuples on
``queue.Queue`` objects (see ``framer.workers.batch_worker``) that a main
thread dispatcher drains (see ``framer.qt.dispatcher``).
"""
