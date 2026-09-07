"""Output path resolution — no GTK imports."""
from __future__ import annotations

from pathlib import Path


class OutputPathError(Exception):
    """Raised when the resolved output path would overwrite the source."""


def resolve_output(src, suffix: str, out_dir: str) -> Path:
    """Resolve the output path for ``src``.

    ``out_dir`` empty means "same folder as the source"; otherwise that
    directory (created if missing). The name is ``<stem><suffix>.<ext>``
    with the original (lowercase) extension. If the target would be the
    source file itself, :class:`OutputPathError` is raised; if it already
    exists, ``_1``, ``_2``, ... are appended until a free name is found.
    """
    src = Path(src)
    ext = src.suffix.lstrip(".").lower() or "img"
    base = Path(out_dir) if out_dir else src.parent
    if out_dir:
        base.mkdir(parents=True, exist_ok=True)

    target = base / f"{src.stem}{suffix}.{ext}"
    if _same_file(target, src):
        raise OutputPathError(f"output path would overwrite the source file: {target}")
    n = 1
    while target.exists():
        target = base / f"{src.stem}{suffix}_{n}.{ext}"
        n += 1
    return target


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return str(a).lower() == str(b).lower()
