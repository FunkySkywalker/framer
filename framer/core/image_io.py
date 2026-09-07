"""Open/probe and framed save pipeline — pure Pillow, no GTK imports.

The pipeline:

1. open the source (EXIF + ICC bytes captured verbatim),
2. derive the target canvas and frame geometry from ``OutputSpec``,
3. per frame: convert to a working mode, LANCZOS contain-fit, composite
   onto the white canvas,
4. save with per-format max-quality parameters (EXIF/ICC verbatim,
   multi-frame support for GIF / APNG / animated WebP).

Deliberately, ``ImageOps.exif_transpose`` is NOT applied to the output
pixels: an orientation-tagged file keeps its tag, so the framed result
renders with exactly the same orientation as the source did.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from PIL import Image

from .framing import (
    compute_working_mode,
    content_fit,
    frame_geometry,
    target_canvas,
    white_for_mode,
)
from .models import OutputSpec


class ProcessingCancelled(Exception):
    """Raised inside :func:`frame_image` when the cancel event is set."""


@dataclass
class FrameResult:
    """Outcome of one framed save."""

    n_frames: int = 1
    warnings: list[str] = field(default_factory=list)


def probe(path) -> tuple[int, int, str, int, int]:
    """Fast header probe — no full decode.

    Returns ``(width, height, format, n_frames, size_bytes)``.
    Raises on unreadable / unsupported files (Pillow errors pass through).
    """
    p = Path(path)
    size = p.stat().st_size
    with Image.open(p) as im:
        w, h = im.size
        fmt = im.format or ""
        n = getattr(im, "n_frames", None) or im.info.get("n_frames", 1) or 1
    return w, h, fmt, n, size


def frame_image(
    src_path,
    dst_path,
    spec: OutputSpec,
    progress_cb: Optional[Callable[[float], None]] = None,
    cancel_event=None,
) -> FrameResult:
    """Frame one image (all its frames) onto the target canvas.

    ``progress_cb`` is called with coarse stage fractions:
    0.33 (opened) -> 0.66 (composited) -> 1.0 (saved).
    ``cancel_event`` (a ``threading.Event``) is checked between stages;
    a file already in its encode call finishes, everything after stops.
    """
    src = Path(src_path)
    dst = Path(dst_path)
    im = Image.open(src)
    try:
        n_frames = getattr(im, "n_frames", None) or im.info.get("n_frames", 1) or 1
        exif = im.info.get("exif")
        icc = im.info.get("icc_profile")
        if progress_cb is not None:
            progress_cb(0.33)
        if _cancelled(cancel_event):
            raise ProcessingCancelled()

        canvas_w, canvas_h = target_canvas(
            spec.aspect_num, spec.aspect_den, spec.portrait, spec.short_edge
        )
        geo = frame_geometry(canvas_w, canvas_h, spec.frame_percent)
        out_fmt = (im.format or dst.suffix.lstrip(".")).upper()

        working = compute_working_mode(im.mode)
        if out_fmt == "GIF":
            working = "RGB"  # GIF frames are quantized to P afterwards
        white = white_for_mode(working)
        if white is None:  # defensive — compute_working_mode should prevent this
            working = "RGB"
            white = (255, 255, 255)

        gif_palette = None
        if out_fmt == "GIF" and im.mode == "P":
            gif_palette = im.copy()  # reuse the source palette for all frames

        frames: list[Image.Image] = []
        durations: list[int] = []
        disposals: list = []
        for i in range(n_frames):
            if i > 0:
                im.seek(i)
            frame = im.copy()
            if frame.mode != working:
                frame = frame.convert(working)
            fit = content_fit(frame.width, frame.height, geo.inner_w, geo.inner_h)
            if fit.w2 != frame.width or fit.h2 != frame.height:
                frame = frame.resize((fit.w2, fit.h2), Image.Resampling.LANCZOS)
            canvas = Image.new(working, (canvas_w, canvas_h), white)
            ox = geo.pad_l + fit.dx
            oy = geo.pad_t + fit.dy
            if working == "RGBA":
                canvas.paste(frame, (ox, oy), frame)
            elif working == "LA":
                canvas.paste(frame, (ox, oy), frame.split()[1])
            else:
                canvas.paste(frame, (ox, oy))
            if out_fmt == "GIF":
                if gif_palette is not None:
                    canvas = canvas.convert("P", palette=gif_palette)
                else:
                    canvas = canvas.convert("P")
            frames.append(canvas)
            durations.append(int(im.info.get("duration", 0) or 0))
            disposals.append(im.info.get("disposal"))
            if i < n_frames - 1 and _cancelled(cancel_event):
                raise ProcessingCancelled()

        if progress_cb is not None:
            progress_cb(0.66)
        if _cancelled(cancel_event):
            raise ProcessingCancelled()

        warnings: list[str] = []
        multi_ok = out_fmt in ("GIF", "PNG", "WEBP") and n_frames > 1
        if n_frames > 1 and not multi_ok:
            frames = frames[:1]
            durations = durations[:1]
            warnings.append(
                f"{out_fmt} file has {n_frames} frames; only the first frame was framed"
            )

        _save(frames, dst, out_fmt, exif, icc, durations, disposals, im)

        if progress_cb is not None:
            progress_cb(1.0)
        return FrameResult(n_frames=len(frames), warnings=warnings)
    finally:
        im.close()


def _cancelled(cancel_event) -> bool:
    return cancel_event is not None and cancel_event.is_set()


def _flatten(img: Image.Image) -> Image.Image:
    """Flatten an alpha/other-mode image onto an opaque white background."""
    has_alpha = img.mode in ("RGBA", "LA")
    target_mode = "RGBA" if has_alpha else "RGB"
    white = (255, 255, 255, 255) if has_alpha else (255, 255, 255)
    flat = Image.new(target_mode, img.size, white)
    if img.mode == "RGBA":
        flat.paste(img, (0, 0), img)
    elif img.mode == "LA":
        flat.paste(img, (0, 0), img.split()[1])
    elif img.mode in ("RGB", "L"):
        flat.paste(img, (0, 0))
    else:
        flat.paste(img.convert("RGBA" if has_alpha else "RGB"), (0, 0))
    return flat


def _tiff_compression(src_im: Image.Image) -> int:
    """Reuse the source's lossless TIFF compression when possible, else LZW."""
    try:
        tag = src_im.tag_v2.get(259)
        if isinstance(tag, int) and tag in (5, 8, 34677):  # LZW / Deflate / ZSTD
            return tag
    except Exception:
        pass
    return 5  # LZW


def _resolve_save_mode(fmt: str, img: Image.Image) -> Image.Image:
    """Convert ``img`` into a mode that ``fmt`` can store (lossless-keeping)."""
    if fmt == "JPEG":
        if img.mode in ("RGB", "L", "CMYK"):
            return img
        if img.mode in ("RGBA", "LA"):
            return _flatten(img).convert("RGB")
        return img.convert("RGB")
    if fmt == "PNG":
        if img.mode in ("L", "LA", "I;16", "P", "RGB", "RGBA"):
            return img
        if img.mode in ("RGBA", "LA"):
            return _flatten(img)
        return img.convert("RGB")
    if fmt == "WEBP":
        if img.mode in ("RGB", "RGBA"):
            return img
        if img.mode in ("RGBA", "LA"):
            return _flatten(img)
        return img.convert("RGB")
    if fmt == "BMP":
        if img.mode in ("L", "P", "RGB", "RGBA"):
            return img
        if img.mode in ("RGBA", "LA"):
            return _flatten(img)
        return img.convert("RGB")
    # TIFF / GIF / anything else: keep the working mode as-is
    return img


def _save(
    frames: list[Image.Image],
    dst: Path,
    out_fmt: str,
    exif: bytes | None,
    icc: bytes | None,
    durations: list[int],
    disposals: list,
    src_im: Image.Image,
) -> None:
    """Write ``frames`` to ``dst`` with per-format max-quality parameters."""
    first = _resolve_save_mode(out_fmt, frames[0])
    if first is not frames[0]:
        frames = [first, *frames[1:]]

    params: dict = {}
    if out_fmt == "JPEG":
        params.update(quality=100, subsampling=0)  # 4:4:4 chroma, max quality
        if exif:
            params["exif"] = exif
        if icc:
            params["icc_profile"] = icc
    elif out_fmt == "PNG":
        if exif:
            params["exif"] = exif
        if icc:
            params["icc_profile"] = icc
    elif out_fmt == "WEBP":
        params.update(quality=100, method=6)  # best compression effort
        if exif:
            params["exif"] = exif
        if icc:
            params["icc_profile"] = icc
    elif out_fmt == "TIFF":
        params["compression"] = _tiff_compression(src_im)
        if exif:
            params["exif"] = exif
        if icc:
            params["icc_profile"] = icc
    # BMP and GIF carry no extra quality parameters (lossless / palette).

    if len(frames) > 1:
        loop = first.info.get("loop", src_im.info.get("loop", 0)) or 0
        kw: dict = {
            "save_all": True,
            "append_images": frames[1:],
            "loop": loop,
        }
        if len(set(durations)) == 1:
            kw["duration"] = durations[0]
        else:
            kw["duration"] = list(durations)
        for fr, disp in zip(frames, disposals):
            if disp is not None:
                fr.info["disposal"] = disp
        frames[0].save(dst, **params, **kw)
    else:
        frames[0].save(dst, **params)
