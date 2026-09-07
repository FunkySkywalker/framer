"""Pure logic layer — no GTK/GObject imports anywhere in this package.

Modules:
    models   — dataclasses for queue items, output spec, job summary
    framing  — the single source of truth for output canvas / frame math
    image_io — probe + framed save pipeline (Pillow only)
    scanner  — folder scanning and selection normalization
    output   — output path resolution with collision suffixing
"""
