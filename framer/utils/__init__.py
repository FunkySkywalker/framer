"""Small shared helpers (paths, thumbnails).

``paths`` is pure Python; ``thumbnails`` crosses into Gdk (run on worker
threads only, per the Dispatcher's thread pool).
"""
