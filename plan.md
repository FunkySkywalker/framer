# Framer — Technical Plan (Phase 1) & Build Instructions (Phase 2)

> **STATUS:** Phase 1 (Plan) is **COMPLETE** as of 2025-06. Phase 2 (Build) is **GATED** —
> no application source code may be written until the user explicitly approves this plan.
> In a new session: present this plan (or its summary), get explicit approval, then execute
> the Phase 2 build instructions in section 6 exactly as written.
>
> **REVISION:** v2 — user-configurable frame thickness: `Adw.SpinRow` (slider + numeric entry,
> two decimal places, range 0.00–20.00%, default 5.00%), persisted via GSettings key
> `frame-percent`; framing math parameterized (§4).
>
> **REVISION:** v3 — user-defined **output canvas**: aspect-ratio presets (5:4, 19:16, custom
> configurable A:B), landscape/portrait flip, target short-edge resolution with live result
> preview. Source content is contain-fitted (no cropping) inside the frame of the target
> canvas. **Supersedes** the v1 rule "output identical to source" — output size/AR is now
> user-chosen; content may be upscaled (LANCZOS) to fill the frame when the source is
> smaller. Math verified by 200k-combo exhaustive random sweep during planning.

App: **Framer** — a GNOME 47+/GTK4 + Libadwaita desktop app (PyGObject) that batch-frames
images onto a user-defined **target canvas**: aspect ratio (presets 5:4 / 19:16 / custom
configurable A:B), landscape/portrait orientation, and short-edge resolution — with a white
frame (thickness configurable 0.00–20.00%, default 5.00%, per side, **inside** the canvas)
and the source content contain-fitted inside the frame without cropping, at maximum save
quality with EXIF/ICC preservation.

---

## 1. Verified Environment (measured 2025-06 on this machine)

| Fact | Measured |
|---|---|
| OS | Ubuntu 26.04.1 LTS (Resolute Raccoon) |
| Python | 3.14.4 (system `/usr/bin/python3.14`) |
| Project venv | `.venv` is an isolated venv (`include-system-site-packages = false`) containing **only pip** — it cannot see system PyGObject |
| PyGObject | 3.56.2 (system, `/usr/lib/python3/dist-packages/gi`) |
| GTK | 4.22.4 — `gi.require_version('Gtk','4.0')` imports cleanly; typelibs in `/usr/lib/x86_64-linux-gnu/girepository-1.0/` |
| Libadwaita | 1.9 — `gi.require_version('Adw','1')` imports cleanly |
| GLib | 2.88 |
| Pillow | 12.1.1 (system) — JPEG, PNG (+APNG), TIFF, BMP, WEBP, GIF registered; **no** AVIF/JXL/HEIC plugins |
| piexif | not installed (not needed — EXIF bytes passed through verbatim) |
| `pkg-config` | finds no `gtk4.pc`/`libadwaita-1.pc` (missing `.pc` files only — runtime imports work; do not rely on pkg-config) |
| Repo state | `main.py` is the PyCharm scaffold sample (must be replaced), 1 initial commit, `.mcp.json` points at a PyCharm MCP server on port 64344 (usually down) |

**Runtime consequence:** run the app with system `python3`, or recreate the venv with
`python3 -m venv --system-site-packages .venv` (document both in the README). No downloads
required to run.

---

## 2. Phase 1 Proposal — 1. Dynamic File Structure

Single top-level package `framer/` with strict layering:
**`core/` has zero GTK imports** (pure, unit-testable); `workers/` is the only place threads
and main-loop dispatch meet; `views/` + `ui/` are pure GTK.

```
framer/                              (repo root)
├── main.py                          # Thin CLI entry: arg parsing → FramerApplication.run()
├── requirements.txt                 # PyGObject, Pillow
├── pyproject.toml                   # metadata only (name, version, deps)
├── README.md
├── AGENTS.md
├── plan.md                          # this file
├── data/
│   ├── com.funkyskywalker.Framer.desktop          # .desktop entry
│   └── com.funkyskywalker.Framer.gschema.xml      # GSettings schema (output dir, suffix, frame %, output canvas)
└── framer/                          # Python package
    ├── __init__.py                  # __version__, APP_ID
    ├── __main__.py                  # `python -m framer`
    ├── app.py                       # FramerApplication (Adw.Application): activate/open signals,
    │                                #   settings service, window lifecycle
    ├── window.py                    # FramerWindow (Adw.ApplicationWindow): HeaderBar,
    │                                #   ToastOverlay, drag-drop wiring, action registration
    ├── core/                        # ── PURE LOGIC, NO GTK IMPORTS ─────────────────
    │   ├── __init__.py
    │   ├── models.py                # ItemState enum, QueueItem, JobSummary dataclasses
    │   ├── framing.py               # framing math (white canvas, 5% insets, LANCZOS downscale)
    │   ├── image_io.py              # open/probe, mode-aware save, per-format params,
    │   │                            #   EXIF + ICC pass-through, multi-frame (GIF/APNG/WebP)
    │   ├── scanner.py               # folder scan (recursive) + dedupe, image-file detection
    │   └── output.py                # output path resolution, collision suffixing, "same file" guard
    ├── workers/                     # ── THREADS + MAIN-LOOP BRIDGE ──────────────────
    │   ├── __init__.py
    │   ├── signals.py               # SignalBus (GObject.Object with declared GObject signals)
    │   ├── batch_worker.py          # BatchJob: single worker thread, cancel Event, event queue
    │   └── dispatcher.py            # 60 ms GLib tick: drains event queue → emits signals on main thread
    ├── views/
    │   ├── __init__.py
    │   ├── queue_row.py             # QueueRow composite widget (thumb, name, meta, per-file status)
    │   └── queue_view.py            # StatusPage empty state + ListBox queue + job bar (progress/cancel)
    ├── ui/
    │   ├── __init__.py
    │   ├── actions.py               # GSimpleActionGroup: add-files, add-folder, start, cancel,
    │   │                            #   clear, clear-finished, about, settings + accelerator wiring
    │   └── toast.py                 # Adw.Toast helpers (added / finished / errors)
    └── utils/
        ├── __init__.py
        ├── thumbnails.py            # PIL → in-memory PNG → GdkPixbuf → Gdk.Texture (thread-pooled)
        └── paths.py                 # human sizes, supported-extension sets, is_image_file()
```

**30 build files** (23 package source + 2 data + 5 top-level; `plan.md` itself is not part of
the build). No single-file script; every layer has one job.

---

## 3. Phase 1 Proposal — 2. Batch Processing Architecture (UI never freezes)

**Choice: one Python worker thread + `queue.Queue` + 60 ms GLib main-loop tick.**

Why not asyncio/GTask/Gio.Async: PyGObject's asyncio integration (`gi-loop`) is unofficial
and fragile; a plain thread is deterministic, trivially cancellable, and **Pillow releases
the GIL inside its C decode/encode paths** (libjpeg-turbo/libpng/zlib), so a single worker
thread still saturates a core while the GLib main loop keeps rendering at 60 fps.

```
┌──────────────────────────── main thread (GLib loop) ────────────────────────────┐
│ FramerWindow  ◄── signals ─── Dispatcher.tick()  ◄── drains ── queue.Queue ────┤
│  (all GTK calls happen here only)        every 60 ms (non-blocking poll)        │
└──────────────────────────────────────────────┬──────────────────────────────────┘
                                               │ put() events
┌──────────────────────────── worker thread ───▼──────────────────────────────────┐
│ BatchJob.run():  for item in items: if cancel: break                            │
│   open → resize → composite white canvas → save (max quality) → emit events    │
│   events: item-started / item-progress / item-finished / job-finished / error  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

- `SignalBus` is a `GObject.Object` subclass with declared signals; the `Dispatcher`
  (`GLib.timeout_add(60, …)`) is the **only** object allowed to emit them, so signal emission
  always lands on the main thread. Polling cost ≈ 16 non-blocking `queue.get_nowait()`/s.
- **Cancellation**: a `threading.Event` the worker checks between files and between
  open/resize/save stages. A file mid-encode finishes (PIL encode is one C call — no safe
  in-encode interrupt); everything after stops.
- **Thumbnails**: separate `ThreadPoolExecutor` (≤4 workers) producing pixbufs, delivered
  through the same dispatcher — never on the main thread.
- **Per-file progress**: worker emits coarse stage fractions (opened 0.33 → resized 0.66 →
  saved 1.0); global bar = `(completed + current_fraction) / total`; per-row status flips
  queued → processing (spinner) → done/error (status icon).
- Failures are **per-item**: a corrupt file marks that row red and the batch continues.

---

## 4. Phase 1 Proposal — 3. Framing Algorithm (exact math)

Inputs: source image `W × H` (any aspect ratio); **output aspect ratio** `A:B` (presets
5:4 / 19:16, or custom configurable integers 1–999); **orientation** landscape (`A:B` as
entered) or portrait (flipped `B:A`); **short-edge resolution** `S` (pixels, 16–8192,
default 1080); **frame thickness** `p` (percent of each canvas edge, default **5.00**,
adjustable **0.00 – 20.00** with two decimal places). Frame fraction `f = p/100`, content
scale `s = 1 − 2f` (default 0.90).

| Step | Formula |
|---|---|
| 1. Target canvas | Effective ratio `(Ae : Be)` = `(A, B)` landscape, `(B, A)` portrait. If `Ae ≥ Be`: `Hc = S`, `Wc = (2·S·Ae + Be) // (2·Be)`; else: `Wc = S`, `Hc = (2·S·Be + Ae) // (2·Ae)` — exact integer round-half-up on the long edge; the short edge is **exactly S**. Canvas is filled **white** (mode map: `RGB→(255,255,255)`, `RGBA→(255,255,255,255)`, `LA→(255,255,255)`, `L→255`, `CMYK→(0,0,0,0)`, `I;16→65535`; `P`/`1`/`F`/`YCbCr` → converted to `RGBA`/`RGB` first) |
| 2. Frame (inside canvas) | `Wi = max(1, round(s·Wc))`, `Hi = max(1, round(s·Hc))` — the inner box |
| 3. Frame inset | `L = (Wc − Wi)//2`, `R = Wc − Wi − L` (likewise `T`, `B`) — remainder pixel to right/bottom edge, box pixel-centered in the canvas |
| 4. Content fit | `k = min(Wi/W, Hi/H)` — uniform scale, source AR preserved, **upscaling allowed** when source < inner box; `W′ = max(1, min(Wi, round(W·k)))`, `H′ = max(1, min(Hi, round(H·k)))` (independent rounding from `k` — avoids ratio-amplified clamps on extreme ratios; clamps make no-cropping airtight) |
| 5. Composite | `content = source.resize((W′, H′), LANCZOS)`; paste at `ox = L + (Wi − W′)//2`, `oy = T + (Hi − H′)//2` (centered inside the frame) → output is exactly `Wc × Hc` |

**Guarantees (verified by 200k-combo exhaustive random sweep during planning):**
- **Exact target size**: the short edge is exactly `S`; the long edge realizes `A:B` within
  round-half-up (≤ 0.5 px); the output is always exactly `Wc × Hc`, uniform for the whole batch.
- **Frame strictly inside**: `Wi ≤ Wc`, `Hi ≤ Hc` for all `p ∈ [0, 20]` (`s ∈ [0.6, 1.0]`)
  and all canvas sizes; `p=0` → inner == canvas (zero frame).
- **Zero cropping (universal)**: `1 ≤ W′ ≤ Wi`, `1 ≤ H′ ≤ Hi` for **all** inputs — 100% of
  the original content is always visible (the `max(1, …)` clamps make this airtight).
- **Aspect ratio preserved**: the content box keeps the source ratio within ±0.5 px per axis
  (relative deviation ≤ `0.5·(r + 1/r)/min(W′, H′)`, `r` = source ratio) whenever both true
  scaled dimensions are ≥ 0.5 px; in the degenerate sub-pixel case (extreme-ratio strips
  whose constrained axis scales below 0.5 px) that axis clamps to 1 px and the ratio
  deviation is bounded by the 1-px quantum — fitting/no-cropping still airtight.
- **Upscaling policy (v3 decision)**: the v1 "never enlarge" rule is **superseded** — the
  output size is user-defined; when the source is smaller than the inner box, content is
  upscaled with LANCZOS to fill it (best framed result at the chosen resolution).
- **EXIF**: the raw EXIF byte blob from the source is re-injected **verbatim** on save
  (`im.info['exif']`). No tags are re-encoded, dropped, or "fixed". We deliberately do
  **not** apply `exif_transpose` to pixels, so an orientation-tagged file stays semantically
  identical (pixels pre-transposed, tag intact → renders exactly as the source did,
  uniformly scaled). Note: since v3 the canvas may differ from the source dimensions, so
  pixel-dimension tags inside the preserved blob (e.g. `ExifImageWidth/Height`) are stale by
  design — rendering is unaffected; documented as a README limitation.
- **ICC**: `im.info['icc_profile']` bytes passed through verbatim where the format supports
  it (JPEG/PNG/WebP/TIFF).

**Per-format save parameters** (max quality; lossless where the format is natively lossless):

| Format | Params |
|---|---|
| JPEG | `quality=100`, `subsampling=0` (4:4:4 chroma), `exif=…`, `icc_profile=…` |
| PNG | lossless; palette sources saved as RGBA (still lossless, color-exact), `transparency` info preserved for 1-bit masks |
| WebP | `quality=100`, `method=6` (best), exif/icc pass-through |
| TIFF | original compression tag 259 read from `tag_v2` and reused when lossless (LZW=5/Deflate=8/ZSTD=34677), else LZW; exif/icc pass-through |
| BMP | lossless, as-is |
| GIF / APNG / animated WebP | **per-frame** framing (every frame resized onto the white canvas), original `duration`, `disposal`, `loop` preserved, `save_all=True` |
| Anything else multi-frame | first frame + warning toast |

---

## 5. Phase 1 Proposal — 4. & 5. GTK4/Libadwaita Component Mapping + Dependencies

### Component mapping

| Role | Widget | Notes |
|---|---|---|
| App object | `Adw.Application` (`com.funkyskywalker.Framer`) | `activate` + `open` signals → CLI args & drag-drop URIs both land in the same add-path |
| Window | `Adw.ApplicationWindow` | default 1100×760, min width ~980 (the three bottom control rows must fit); dark mode **automatic** (Adw follows system, zero code) |
| Header | `Adw.HeaderBar` | start: **Add Images** button (`list-add-symbolic`), **Add Folder** button (`folder-symbolic`); end: `Gtk.MenuButton` hamburger (`GMenu`: Clear finished, Clear all, Settings, About, Quit); center: `Adw.WindowTitle` "Framer" |
| File pickers | `Adw.FileDialog` | `open_files()` with a `Gtk.FileFilter` of image suffixes; `open_folder()` for whole folders |
| Status toasts | `Adw.ToastOverlay` + `Adw.Toast` | "N images added", "Batch finished X/Y", per-error HIGH-priority toasts |
| Empty state | `Adw.StatusPage` | "No images yet" + primary action; swapped out when queue non-empty |
| Queue list | `Adw.ToolbarView` → `Gtk.ScrolledWindow` → `Gtk.ListBox` | selection mode NONE; rows = `QueueRow` composites |
| Queue row | custom `Gtk.Box` (HBox) | `Gtk.Image` thumbnail (48 px `Gdk.Texture`) · `Gtk.Label` filename (ellipsized) + dim-label (`W×H · JPEG · 2.3 MB`) · right side: `Adw.Spinner` (processing) / `Adw.StatusIcon` `emblem-ok-symbolic` (done) / `Adw.StatusIcon` `dialog-error-symbolic` (error) / dim label "Queued" |
| Bottom controls | `Gtk.Box` (vertical, 3 rows) in `Adw.ToolbarView` bottom bar | **Output row**: dim "Output" label + aspect preset `Gtk.ComboBox` (`new_from_strings`: "5:4", "19:16", "Custom") + custom A:B pair (`Gtk.Revealer` with two integer `Gtk.SpinButton` 1–999, shown only on "Custom") + orientation `Gtk.ToggleButton` (label flips "Landscape" ↔ "Portrait") + dim "Short edge" label + short-edge `Gtk.SpinButton` (16–8192 px, default 1080) + **result preview** dim `Gtk.Label` ("Result: 1350 × 1080", live). **Frame row**: `Adw.SpinRow` "Frame thickness" (below, `hexpand`) + **Start Framing** `Gtk.Button` (`suggested-action`, `media-playback-start-symbolic`) + **Cancel** button (`process-stop-symbolic`). **Progress row**: `Adw.Spinner` (visible while running) + status label ("3 of 12 — beach.jpg", `hexpand`) + `Gtk.ProgressBar` (`set_show_text(True)`, `set_fraction`) |
| Frame thickness | `Adw.SpinRow` (native Libadwaita slider + numeric entry composite, Adw ≥ 1.5 — we have 1.9) | `Gtk.Adjustment(5.00, 0.00, 20.00, step 0.01, page 0.1)`, `set_digits(2)`, `add_suffix("%")`, title "Frame thickness", subtitle "White frame on each side, % of the image edge"; bound to the `frame-percent` GSettings key (load on startup, persist on change); **insensitive while a batch runs** (together with the whole output row) — the complete `OutputSpec` is snapshotted at job start |
| Drag & drop | `widget.set_drag_dest(Gdk.Uri)` on the window | `drag-data-received` → `GLib.Value.get_string()` → URI filter by extension + magic probe |
| Settings | `Gio.Settings` (schema `com.funkyskywalker.Framer`) | keys: `output-directory` ("" = next to source), `suffix` (default `_framed`), `frame-percent` (double, default 5.00, range 0.00–20.00), `aspect-preset` (string "5:4" | "19:16" | "custom", default "5:4"), `aspect-num` / `aspect-den` (int, default 3/2, range 1–999), `orientation-portrait` (bool, default false), `short-edge` (int, default 1080, range 16–8192); graceful in-memory fallback if schema not installed (wrap in try/except, hardcoded defaults) |
| About | `Adw.AboutWindow` | name, version, MIT license, developer |
| Accelerators | `app.set_accels_for_action` | `Ctrl+O` files · `Ctrl+Shift+O` folder · `Ctrl+Return` start · `Ctrl+.` cancel (GNOME stop convention) · `Ctrl+W` close |

### Dependency checklist

**System packages (Ubuntu 26.04) — all already satisfied (verified by import):**

| Package | Provides | Status |
|---|---|---|
| `python3-gi` + `gir1.2-gtk-4.0` | PyGObject, GTK 4.22 typelibs | ✅ installed (PyGObject 3.56.2) |
| `gir1.2-adw-1` (+ `libadwaita-1`) | Libadwaita 1.9 | ✅ installed |
| `libglib2.0-bin` | `glib-compile-schemas` for the GSettings schema | present on desktop base |
| Pillow C runtime (libjpeg-turbo, libpng, libwebp, zlib) | decode/encode | ✅ Pillow 12.1.1 |

**Python libraries** (`requirements.txt`):
- `PyGObject >= 3.50` — provided by the **system** package (not pip-installable on this setup)
- `Pillow >= 10.0` — system has 12.1.1

**Known limitations (documented in README, enforced with error toasts, never silent):**
- AVIF / JXL / HEIC: no Pillow plugins on this system → file rejected with a per-row error.
- 16-bit / palette / CMYK sources: handled via the mode map in §4 (lossless where the format
  is lossless).
- Preserved EXIF blobs keep their original pixel-dimension tags, which are stale when the
  target canvas differs from the source size (rendering unaffected).

---

## 6. Phase 2 Build Instructions (execute only after explicit user approval)

### 6.1 File generation sequence

1. `requirements.txt`
2. `data/com.funkyskywalker.Framer.gschema.xml`
3. `data/com.funkyskywalker.Framer.desktop`
4. `framer/__init__.py`
5. `framer/core/__init__.py`
6. `framer/core/models.py`
7. `framer/core/framing.py`
8. `framer/core/image_io.py`
9. `framer/core/scanner.py`
10. `framer/core/output.py`
11. `framer/workers/__init__.py`
12. `framer/workers/signals.py`
13. `framer/workers/batch_worker.py`
14. `framer/workers/dispatcher.py`
15. `framer/utils/__init__.py`
16. `framer/utils/paths.py`
17. `framer/utils/thumbnails.py`
18. `framer/ui/__init__.py`
19. `framer/ui/actions.py`
20. `framer/ui/toast.py`
21. `framer/views/__init__.py`
22. `framer/views/queue_row.py`
23. `framer/views/queue_view.py`
24. `framer/window.py`
25. `framer/app.py`
26. `framer/__main__.py`
27. `main.py` (replace the PyCharm scaffold)
28. `pyproject.toml`
29. `README.md`
30. `AGENTS.md`

### 6.2 Per-file contracts

- **`requirements.txt`**: `PyGObject>=3.50` (with a comment: provided by system `python3-gi`,
  not pip-installable here), `Pillow>=10.0`.
- **`data/com.funkyskywalker.Framer.gschema.xml`**: schema id `com.funkyskywalker.Framer`,
  path `/com/funkyskywalker/Framer/`; keys: `output-directory` (string, default `""`),
  `suffix` (string, default `"_framed"`), `frame-percent` (double, default 5.0, range 0.0–20.0),
  `aspect-preset` (string, default `"5:4"`, values "5:4"/"19:16"/"custom"), `aspect-num`
  (int, default 3, range 1–999), `aspect-den` (int, default 2, range 1–999),
  `orientation-portrait` (bool, default false), `short-edge` (int, default 1080,
  range 16–8192) — all with summaries/descriptions.
- **`data/com.funkyskywalker.Framer.desktop`**: `Type=Application`, `Name=Framer`,
  `Exec=python3 {install-path}/main.py %F`, `MimeType=image/jpeg;image/png;image/webp;image/tiff;image/bmp;image/x-ms-bmp;image/gif;image/apng;`, `Icon=image-x-generic`,
  `Categories=Graphics;`.
- **`framer/__init__.py`**: `APP_ID = "com.funkyskywalker.Framer"`, `__version__ = "1.0.0"`.
- **`core/models.py`** (no GTK): `class ItemState(str, Enum)` — `QUEUED, PROCESSING, DONE,
  ERROR, CANCELLED`. `@dataclass QueueItem` — `path: Path`, `uri: str`, `width/height: int|None`,
  `format: str|None`, `size_bytes: int|None`, `state: ItemState`, `fraction: float`,
  `output_path: Path|None`, `error: str|None`. `@dataclass(frozen=True) OutputSpec` —
  `aspect_num: int, aspect_den: int, portrait: bool, short_edge: int, frame_percent: float`,
  `__post_init__` clamps (aspect 1–999, short_edge 16–8192, percent 0–20);
  `@dataclass JobSummary` — `total, done, failed, cancelled`.
- **`core/framing.py`** (no GTK): constants `FRAME_PERCENT_DEFAULT = 5.0`,
  `FRAME_PERCENT_MIN = 0.0`, `FRAME_PERCENT_MAX = 20.0`, `SHORT_EDGE_MIN = 16`,
  `SHORT_EDGE_MAX = 8192`, `SHORT_EDGE_DEFAULT = 1080`;
  `def target_canvas(a, b, portrait, short_edge) -> tuple[int, int]` (`(w, h)`; §4 step 1,
  exact integer round-half-up, clamps inputs); `def frame_geometry(canvas_w, canvas_h,
  percent) -> FrameGeometry` (dataclass `inner_w, inner_h, pad_l, pad_r, pad_t, pad_b`; §4
  steps 2–3; clamps `percent` to `[0, 20]`); `def content_fit(src_w, src_h, inner_w,
  inner_h) -> ContentFit` (dataclass `w2, h2, dx, dy` — content size + offset **relative to
  the inner box**; §4 step 4; the compositor adds the frame padding: `ox = pad_l + dx`);
  `def white_for_mode(mode) -> tuple|None` (mode map from §4, `None` for modes that must be
  converted first); `def compute_working_mode(mode) -> str` (identity or `RGBA`/`RGB` target).
- **`core/image_io.py`** (no GTK): `def probe(path) -> (w, h, format, size)` (fast open,
  no full decode — `Image.open` + `im.size`/`im.format`/`im.info.get('n_frames',1)`);
  `def frame_image(src_path, dst_path, spec: OutputSpec, progress_cb=None) -> None` — full
  pipeline: open, `target_canvas` + white canvas, `frame_geometry` + `content_fit` per frame
  (multi-frame support: `n_frames > 1` → every frame fit to the **same** canvas/inner box,
  collect durations/disposal/loop from source `info`, `save_all=True`), `progress_cb
  (stage_fraction)` called at 0.33/0.66/1.0; save with the per-format param table from §4
  (JPEG q100 subsampling=0 + exif + icc; PNG RGBA for palette sources; WebP q100 method=6;
  TIFF reuse tag-259 compression map else LZW; GIF/APNG per-frame). EXIF via
  `im.info.get('exif')`, ICC via `im.info.get('icc_profile')` — verbatim bytes, no
  `ImageOps.exif_transpose`. Close images in `finally`.
- **`core/scanner.py`**: `def scan_folder(folder: Path) -> list[Path]` — recursive
  `os.walk` (follow dirs, skip hidden dirs `.*`), filter by `is_image_file()`, dedupe by
  resolved path, sorted; `def scan_files(paths) -> list[Path]` — normalize + dedupe a user
  selection (files and/or folders mixed).
- **`core/output.py`**: `def resolve_output(src: Path, suffix: str, out_dir: str) -> Path` —
  `out_dir==""` → same folder as src, else given dir; name `<stem><suffix>.<ext>` (original
  lowercase ext); if target == src (case-insensitive) → raise `OutputPathError`; if target
  exists → append `_1`, `_2`, … until free. `class OutputPathError(Exception)`.
- **`workers/signals.py`** (GObject allowed here): `class SignalBus(GObject.GObject)` with
  signals: `item-started` `(int)`, `item-progress` `(int, float)`, `item-finished`
  `(int, boolean, string)` (index, ok, error-message), `job-finished` `(int, int, int, int)`
  (total, done, failed, cancelled). Declare with `__gtype_name__` + `GObject.signal_new`.
- **`workers/batch_worker.py`**: `class BatchJob` — ctor `(items: list[QueueItem], bus:
  SignalBus, suffix, output_dir, spec: OutputSpec)`; `spec` is snapshotted from the UI at job
  start (all output/frame controls are insensitive while running, so nothing can change
  mid-batch) and passed to `frame_image`; internal `queue.Queue` (worker→main) + `threading.Event`
  cancel flag + `threading.Thread`; `start()`, `cancel()`, `is_running()`; worker loop:
  per item — probe geometry/output resolution, call `frame_image`, update the `QueueItem`
  in place (thread-safe: only worker writes, main reads via events), push events with
  per-item index + stage fractions; on exception push `item-finished` with error text and
  continue; at end push `job-finished` with counts. Never touches GTK.
- **`workers/dispatcher.py`**: `class Dispatcher` — owns a `SignalBus`; `attach(queue)`,
  `start()/stop()` with `GLib.timeout_add(60, tick)`; tick drains the queue via
  `get_nowait()` and emits the corresponding signal (main thread only);
  `add_thumbnail_provider(fn)` — second queue drained the same way (thumbnails).
- **`utils/paths.py`**: `IMAGE_EXTENSIONS` set (jpg, jpeg, png, tif, tiff, bmp, webp, gif,
  apng, jfif); `def is_image_file(path) -> bool` (extension check, case-insensitive);
  `def human_size(n) -> str` (`B/KiB/MiB/GiB`); `def format_meta(w, h, fmt, size) -> str`.
- **`utils/thumbnails.py`**: `def make_thumbnail(path, pixel_size=96) -> Gdk.Texture | None`
  — PIL open (with `ImageOps.exif_transpose` for display only), `thumbnail((size, size))`,
  flatten alpha onto white, save to in-memory PNG (`io.BytesIO`), load via
  `GdkPixbuf.Pixbuf.new_from_stream(Gio.MemoryInputStream.new_from_bytes(GLib.Bytes(png)))`,
  `Gdk.Texture.for_pixbuf()`. Run on a `ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 2))`
  managed by the Dispatcher; returns `None` on any failure (UI shows `image-missing-symbolic`).
- **`ui/actions.py`**: `class Actions` — builds a `Gtk.SimpleActionGroup` with:
  `add-files`, `add-folder`, `start` (enabled when queue non-empty & not running), `cancel`
  (enabled while running), `clear`, `clear-finished`, `about`, `settings`; exposes
  `install(window, callbacks)` wiring the `GMenu` model, the hamburger `Gtk.MenuButton`,
  and `app.set_accels_for_action` for `Ctrl+O`, `Ctrl+Shift+O`, `Ctrl+Return`, `Ctrl+.`.
- **`ui/toast.py`**: `def toast(overlay, message, priority=NORMAL, timeout=3.0)` — wraps
  `Adw.Toast`; `def success_overlay(...)`, `def error_overlay(...)` convenience helpers.
- **`views/queue_row.py`**: `class QueueRow(Gtk.ListBoxRow)` — HBox: `Gtk.Image` (48 px) +
  vbox(filename label ellipsized, dim-label meta) + right status container;
  `set_state(ItemState)` swaps spinner / `Adw.StatusIcon` / dim "Queued" label;
  `set_thumbnail(Gdk.Texture)`; `set_meta(str)`; not selectable
  (`set_selectable(False)`).
- **`views/queue_view.py`**: `class QueueView(Gtk.Box)` — vertical: (a) `Adw.StatusPage`
  empty state (icon `image-x-generic`, title "No images yet", description with
  add/drop instructions, primary "Add Images" button → `add-files` action), visible only
  when queue empty; (b) `Gtk.ScrolledWindow` + `Gtk.ListBox` (selection NONE) of
  `QueueRow`s; (c) bottom controls — a vertical `Gtk.Box` with 3 rows:
  **output row** — dim "Output" `Gtk.Label` + `Gtk.ComboBox.new_from_strings([b"5:4", b"19:16",
  b"Custom"])` + `Gtk.Revealer` containing a custom A/B `Gtk.SpinButton.new_for_range(1, 999, 1)`
  pair with a ":" label (revealed only when combo index == 2) + orientation `Gtk.ToggleButton`
  (label "Landscape" ↔ "Portrait", tooltip "Flip orientation") + dim "Short edge" label +
  `Gtk.SpinButton.new_for_range(16, 8192, 1)` (`set_page_increment(100)`, tooltip "Short edge
  in pixels") + dim result-preview `Gtk.Label` ("Result: 1350 × 1080");
  **frame row** — `Adw.SpinRow` (`Gtk.Adjustment.new(5.0, 0.0, 20.0, 0.01, 0.1, 0.0)`,
  `set_digits(2)`, `add_suffix("%")`, `set_title("Frame thickness")`,
  `set_subtitle("White frame on each side, % of the image edge")`, `hexpand`) + Start
  button (`suggested-action`, `Adw.ButtonContent` `media-playback-start-symbolic` "Start
  Framing") + Cancel button (`process-stop-symbolic` "Cancel", insensitive unless running);
  **progress row** — `Adw.Spinner` + status `Gtk.Label` (`hexpand`) + `Gtk.ProgressBar`
  (`set_show_text(True)`). API: `add_item(QueueItem)`, `update_item(index, fraction, state)`,
  `set_running(bool, current_label)` (also toggles sensitivity of **all** output/frame
  controls), `set_progress(done, total, fraction)`, `clear()`, `clear_finished()`, `items()`;
  getters for window binding: `get_aspect_combo()`, `get_custom_revealer()`,
  `get_orientation_button()`, `get_short_edge_spin()`, `get_frame_row()`,
  `set_result_label(w, h)` ("Result: W × H").
- **`window.py`**: `class FramerWindow(Adw.ApplicationWindow)` — builds
  `Adw.ToastOverlay` → `Adw.ToolbarView` (top: `Adw.HeaderBar`; content: `QueueView`;
  bottom bar: job bar lives inside QueueView); wires `Adw.FileDialog` (files + folder,
  image `Gtk.FileFilter`); wires `set_drag_dest(Gdk.Uri)` + `drag-data-received`
  (URI → `Gio.File`, filter via `is_image_file`, probe via `core.probe`, build `QueueItem`s,
  toast "N images added"); owns `Dispatcher` + `BatchJob` lifecycle; connects
  `SignalBus` signals to `QueueView` updates + toasts (finished: summary toast, HIGH
  priority if any failures); implements the add-files/add-folder/start/cancel/clear/
  clear-finished/about/settings handlers; `add_paths(paths: list[Gio.File])` shared by
  dialog/drop/CLI-`open`; binds all output/frame controls to GSettings (initial values from
  settings, write back on change, clamped): aspect combo ↔ `aspect-preset`, custom A/B ↔
  `aspect-num`/`aspect-den` (the `Gtk.Revealer` tracks the combo), orientation toggle ↔
  `orientation-portrait`, short edge ↔ `short-edge`, frame `SpinRow` ↔ `frame-percent`;
  a single `refresh_output()` recomputes the preview via `core.target_canvas` and calls
  `set_result_label` on any control change; on Start builds
  `OutputSpec(aspect_num, aspect_den, portrait, short_edge, frame_percent)` from the live
  controls and starts the `BatchJob` with that snapshot.
- **`app.py`**: `class FramerApplication(Adw.Application)` — `__init__(APP_ID,
  default_flags)`, `app.set_application_icon_name("image-x-generic")`; GSettings
  service with graceful fallback (try `Gio.Settings.new("com.funkyskywalker.Framer")`,
  except `GLib.Error` → in-memory defaults `{"output-directory": "", "suffix": "_framed",
  "frame-percent": 5.0, "aspect-preset": "5:4", "aspect-num": 3, "aspect-den": 2,
  "orientation-portrait": False, "short-edge": 1080}` with the same get/set interface);
  `do_activate` creates the window; `do_open(files, n)`
  reuses the existing window (or creates one) and calls `add_paths`; `do_startup` registers
  accelerators.
- **`framer/__main__.py`** and **`main.py`**: both — `gi.require_version('Gtk','4.0')`,
  `gi.require_version('Adw','1')`, then `sys.exit(FramerApplication().run(sys.argv))`
  (`main.py` imports from the `framer` package). `main.py` replaces the PyCharm scaffold.
- **`pyproject.toml`**: `[project]` name `framer`, version `1.0.0`, requires-python
  `>=3.12`, dependencies `Pillow>=10.0`; note PyGObject is system-provided in
  `[project.optional-dependencies]` comments or a README note (keep it simple — metadata
  only, no build backend required; a minimal `[project]` table is fine).
- **`README.md`**: overview, feature list, prerequisites (system packages, note that they
  are already installed on Ubuntu 26.04 desktop), two run paths:
  (a) `python3 main.py` (system Python has everything),
  (b) `.venv`: `rm -rf .venv && python3 -m venv --system-site-packages .venv &&
  .venv/bin/pip install -r requirements.txt && .venv/bin/python main.py`;
  schema install step (optional, for GSettings persistence):
  `install -d ~/.local/share/glib-2.0/schemas && cp data/com.funkyskywalker.Framer.gschema.xml
  ~/.local/share/glib-2.0/schemas/ && glib-compile-schemas ~/.local/share/glib-2.0/schemas`;
  usage (add images/folder, drag & drop, output controls — aspect presets 5:4/19:16/Custom
  with A:B entries, landscape/portrait flip, short-edge resolution with live "Result: W × H"
  preview — frame-thickness control, slider + numeric entry, 0.00–20.00%, two decimals,
  default 5.00, all persisted across sessions — accelerators table), output naming rules
  (`<stem>_framed.<ext>`, collision suffixing), framing model summary (target canvas from
  AR + orientation + short edge; frame strictly inside; content contain-fit, no cropping,
  may upscale to fill; EXIF/ICC verbatim), per-format save-quality table,
  limitations (no AVIF/JXL/HEIC on this system; output size/AR is user-defined and no longer
  tied to the source; stale EXIF pixel-dimension tags when canvas ≠ source size), license MIT.
- **`AGENTS.md`**: project rules for agentic work — layering law (`core/` must never import
  GTK/GObject; all GTK on the main thread only via the Dispatcher; worker thread never
  calls GLib UI APIs), how to run (system python3 or `--system-site-packages` venv),
  how to smoke-test headless (see 6.3), file map, do-not-break list (EXIF/ICC verbatim,
  frame strictly inside canvas, content never cropped, output size derived ONLY from
  `OutputSpec` via `core.framing`, per-item error isolation, single writer thread,
  `OutputSpec` snapshotted at job start and clamped in core AND UI), where to add formats
  (`utils/paths.py` extensions + `core/image_io.py` save table), commit style
  (author `picode <roman.mikula.picode@funkyskywalker.at>` per gitea skill conventions
  if pushing to Gitea).

### 6.3 Acceptance checks (must pass before declaring Phase 2 done)

1. `python3 -c "import gi; gi.require_version('Gtk','4.0'); gi.require_version('Adw','1');
   import framer.app; print('import OK')"` — clean import, no warnings.
2. Headless math test (no display needed):
   - `target_canvas(5, 4, False, 1080)` → (1350, 1080); `target_canvas(19, 16, False, 1080)`
     → (1283, 1080); `target_canvas(5, 4, True, 1080)` → (1080, 1350);
     `target_canvas(4, 5, False, 1080)` → (1080, 1350) (custom ratio < 1 in landscape);
     for 50 random (A, B, portrait, S) combos the short edge is exactly S.
   - `frame_geometry(1350, 1080, 5.0)` → inner (1215, 972), pads (67, 68, 54, 54);
     sweep `p` in {0.00, 2.50, 5.00, 7.37, 12.00, 20.00, 30.00, −2.00} × 50 random canvas
     sizes: `inner ≤ canvas` both axes, `p=0` → inner == canvas, pads sum exactly to
     `canvas − inner`; out-of-range `p` clamped, never raises.
   - `content_fit` sweep (100k random source/canvas/percent combos): always
     `1 ≤ w2 ≤ inner_w`, `1 ≤ h2 ≤ inner_h` (no cropping); when both true scaled dims
     ≥ 0.5 px, ratio deviation ≤ `0.5·(r+1/r)/min(w2, h2)`; upscale case:
     800×600 into 1215×972 inner → (1215, 911).
   - Synthetic end-to-end: `Image.new('RGB', (4032, 3024), (10, 20, 30))` saved as JPEG
     with an `exif` blob + `icc_profile`; run `frame_image` with
     `OutputSpec(5, 4, False, 1080, 5.0)`: output size == (1350, 1080), `info['exif']`
     bytes identical, corner pixel white, content-center pixel matches the source center
     hue (LANCZOS tolerance); portrait spec → (1080, 1350).
   - RGBA PNG with transparency: output stays PNG at canvas size, corner white alpha 255.
   - GIF 2-frame: output GIF `n_frames == 2`, durations preserved, canvas size.
3. `grep -rn "TODO\|FIXME\|XXX\|placeholder\|# later" framer/ main.py` → no hits.
4. `grep -rln "gi.repository\|import gi" framer/core/` → no hits (pure core).
5. UI launch (requires display; user will verify): `.venv/bin/python main.py` opens the
   window, empty state visible, add files → rows with thumbnails appear, Start → progress
   bar + per-row spinners, finished → toast + green status icons, output files created
   beside sources with `_framed` suffix.

### 6.4 Hard rules for the build

- Multi-file structure from §2 is mandatory — no single-file implementations, no
  placeholders, no `# TODO`.
- All code must be complete and production-grade.
- All geometry math goes through `core.framing` (`target_canvas` + `frame_geometry` +
  `content_fit`) — the single source of truth for the user-configurable output canvas and
  frame; no hardcoded aspect ratios, `0.05`, or `1080` anywhere downstream.
- Respect the two-phase protocol: do not start until the user explicitly approves.
- If the PyCharm MCP servers happen to be up in the new session, they may be used for
  project-wide symbols/diagnostics, but native tools are the fallback (they are down by
  default — port 64344 usually unconnected).
