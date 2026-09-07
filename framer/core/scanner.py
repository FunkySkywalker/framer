"""Folder scanning and selection normalization — no GTK imports."""
from __future__ import annotations

import os
from pathlib import Path

from ..utils.paths import is_image_file


def scan_folder(folder) -> list[Path]:
    """Recursively scan ``folder`` for image files.

    Hidden directories (and files) are skipped, results are deduped by
    resolved path and sorted for stable queue order.
    """
    folder = Path(folder)
    found: list[Path] = []
    seen: set[Path] = set()
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in filenames:
            if name.startswith("."):
                continue
            p = Path(dirpath) / name
            if not is_image_file(p):
                continue
            try:
                rp = p.resolve()
            except OSError:
                continue
            if rp in seen:
                continue
            seen.add(rp)
            found.append(p)
    return sorted(found, key=lambda p: str(p).lower())


def scan_files(paths) -> list[Path]:
    """Normalize a user selection that may mix files and folders.

    Directories are expanded with :func:`scan_folder`; everything is
    deduped by resolved path while preserving selection order.
    """
    out: list[Path] = []
    seen: set[Path] = set()

    def add(p: Path) -> None:
        try:
            rp = p.resolve()
        except OSError:
            return
        if rp in seen:
            return
        seen.add(rp)
        out.append(p)

    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            for fp in scan_folder(p):
                add(fp)
        elif p.is_file():
            add(p)
    return out
