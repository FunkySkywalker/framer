"""Framing math — the single source of truth for output geometry.

Pure integer arithmetic (round-half-up), no GTK/GObject imports, no
hardcoded aspect ratios or resolutions outside the constants below.
"""
from __future__ import annotations

from dataclasses import dataclass

FRAME_PERCENT_DEFAULT = 5.0
FRAME_PERCENT_MIN = 0.0
FRAME_PERCENT_MAX = 20.0
SHORT_EDGE_MIN = 16
SHORT_EDGE_MAX = 8192
SHORT_EDGE_DEFAULT = 1080
ASPECT_MIN = 1
ASPECT_MAX = 999


@dataclass(frozen=True)
class FrameGeometry:
    """Inner (content) box of the canvas plus pixel paddings.

    The box is centered: the remainder pixel goes to the right/bottom edge.
    ``pad_l + inner_w + pad_r == canvas_w`` (likewise vertically).
    """

    inner_w: int
    inner_h: int
    pad_l: int
    pad_r: int
    pad_t: int
    pad_b: int


@dataclass(frozen=True)
class ContentFit:
    """Fitted content size plus its offset *relative to the inner box*.

    The compositor adds the frame padding: ``ox = pad_l + dx``.
    """

    w2: int
    h2: int
    dx: int
    dy: int


def _clamp_int(value: int, lo: int, hi: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = lo
    return max(lo, min(hi, v))


def _clamp_float(value: float, lo: float, hi: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = lo
    return max(lo, min(hi, v))


def _rhu(num: int, den: int) -> int:
    """Round-half-up of ``num / den`` for non-negative integers."""
    if den <= 0:
        return 0
    return (2 * num + den) // (2 * den)


def target_canvas(a: int, b: int, portrait: bool, short_edge: int) -> tuple[int, int]:
    """Target canvas ``(width, height)`` for aspect ratio ``a:b``.

    Portrait flips the ratio to ``b:a``. The short edge is exactly
    ``short_edge``; the long edge is the round-half-up realization of the
    ratio. Inputs are clamped to their valid ranges.
    """
    a = _clamp_int(a, ASPECT_MIN, ASPECT_MAX)
    b = _clamp_int(b, ASPECT_MIN, ASPECT_MAX)
    s = _clamp_int(short_edge, SHORT_EDGE_MIN, SHORT_EDGE_MAX)
    ae, be = (b, a) if portrait else (a, b)
    # round-half-up of s*ae/be without float error: (2*s*ae + be) // (2*be)
    if ae >= be:
        hc = s
        wc = (2 * s * ae + be) // (2 * be)
    else:
        wc = s
        hc = (2 * s * be + ae) // (2 * ae)
    return wc, hc


def frame_geometry(canvas_w: int, canvas_h: int, percent: float) -> FrameGeometry:
    """Inner content box for a frame thickness of ``percent`` (0–20).

    Frame fraction ``f = percent / 100``, content scale ``s = 1 - 2f``.
    ``percent`` is clamped to ``[0, 20]``; at 0 the inner box equals the
    canvas, and it is always ``<= canvas`` in both axes.
    """
    p = _clamp_float(percent, FRAME_PERCENT_MIN, FRAME_PERCENT_MAX)
    p_cents = int(round(p * 100))
    p_cents = max(0, min(int((FRAME_PERCENT_MAX - FRAME_PERCENT_MIN) * 100), p_cents))
    # s * 10000 as an exact integer: s = (10000 - 2*p_cents) / 10000
    s_num = 10000 - 2 * p_cents
    inner_w = max(1, _rhu(canvas_w * s_num, 10000))
    inner_h = max(1, _rhu(canvas_h * s_num, 10000))
    pad_l = (canvas_w - inner_w) // 2
    pad_r = canvas_w - inner_w - pad_l
    pad_t = (canvas_h - inner_h) // 2
    pad_b = canvas_h - inner_h - pad_t
    return FrameGeometry(inner_w, inner_h, pad_l, pad_r, pad_t, pad_b)


def content_fit(src_w: int, src_h: int, inner_w: int, inner_h: int) -> ContentFit:
    """Uniform contain-fit of ``src_w x src_h`` into the inner box.

    Aspect ratio preserved, upscaling allowed, never cropped: the result
    always satisfies ``1 <= w2 <= inner_w`` and ``1 <= h2 <= inner_h``.
    ``dx``/``dy`` center the content inside the inner box (the compositor
    adds the frame paddings).
    """
    w2 = max(1, min(inner_w, _rhu(src_w * inner_h, src_h)))
    h2 = max(1, min(inner_h, _rhu(src_h * inner_w, src_w)))
    dx = (inner_w - w2) // 2
    dy = (inner_h - h2) // 2
    return ContentFit(w2, h2, dx, dy)


def white_for_mode(mode: str) -> tuple | int | None:
    """White (opaque) fill value for a PIL mode.

    ``None`` for modes that must be converted to a working mode first
    (see :func:`compute_working_mode`).
    """
    return {
        "RGB": (255, 255, 255),
        "RGBA": (255, 255, 255, 255),
        "LA": (255, 255),
        "L": 255,
        "CMYK": (0, 0, 0, 0),
        "I;16": 65535,
    }.get(mode)


def compute_working_mode(mode: str) -> str:
    """Map any PIL source mode to a working mode for the framing pipeline.

    Identity for RGB/RGBA/L/LA/CMYK/I;16; palette sources go to RGBA
    (lossless for PNG); everything else (1, I, F, YCbCr, ...) to RGB.
    """
    if mode in ("RGB", "RGBA", "L", "LA", "CMYK", "I;16"):
        return mode
    if mode == "P":
        return "RGBA"
    return "RGB"
