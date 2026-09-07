# Framer — Technical Plan (Phase 1) & Build Instructions (Phase 2)

> **STATUS:** Phase 1 (Plan) is **COMPLETE** as of 2025-06. Phase 2 (Build) is **GATED** —
> no application source code may be written until the user explicitly approves this plan.
> In a new session: present this plan (or its summary), get explicit approval, then execute
> the Phase 2 build instructions in section 6 exactly as written.
>
> **REVISION:** v2 — user-configurable frame thickness: `Adw.SpinRow` (slider + numeric entry,
> two decimal places, range 0.00–20.00%, default 5.00%), persisted via GSettings key
> `frame-percent`; framing math parameterized (§4).

App: **Framer** — a GNOME 47+/GTK4 + Libadwaita desktop app (PyGObject) that batch-processes
images by adding a white frame occupying 5% of each dimension on each side, applied **inside**
the original image boundaries (output is never enlarged, never cropped, same resolution and
aspect ratio as the source), with maximum save quality and EXIF/ICC preservation.

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
│   └── com.funkyskywalker.Framer.gschema.xml      # GSettings schema (output dir, suffix)
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

Source: `W × H` pixels; user-configurable **frame thickness** `p` (percent of each image edge,
default **5.00**, adjustable **0.00 – 20.00** with two decimal places); frame fraction
`f = p/100` (default 0.05); content scale factor `s = 1 − 2f` (default 0.90). Interpretation:
**the frame occupies `p`% of each image dimension on each side** (default 5%).

| Step | Formula |
|---|---|
| 1. Canvas | New image exactly `W × H` in the **same mode** as source, filled **white** (mode map: `RGB→(255,255,255)`, `RGBA→(255,255,255,255)`, `LA→(255,255,255)`, `L→255`, `CMYK→(0,0,0,0)`, `I;16→65535`; `P`/`1`/`F`/`YCbCr` → converted to `RGBA`/`RGB` first) |
| 2. Inner box | `W′ = max(1, round(s·W))`, `H′ = max(1, round(s·H))` |
| 3. Inset | `L = (W − W′)//2`, `R = W − W′ − L` (likewise `T`, `B`) — remainder pixel goes to the right/bottom edge, content stays pixel-centered |
| 4. Content | `content = source.resize((W′, H′), Image.Resampling.LANCZOS)` |
| 5. Composite | `canvas.paste(content, (L, T))` → output is exactly `W × H` |

**Guarantees:**
- **Never enlarges**: for the full allowed range `p ∈ [0, 20]` (`s ∈ [0.6, 1.0]`),
  `round(s·W) ≤ W` holds for all `W ≥ 1` (verified by exhaustive random sweep); for tiny
  images below roughly `0.5/(1−s)` px on an axis, that axis' frame degenerates to zero and
  the content passes through unmodified — output is still exactly `W×H`.
- **Aspect ratio exact**: the output canvas is literally the source's dimensions; the inner
  box deviates from perfect `s` proportion by ≤ 1 px per axis, absorbed by asymmetric
  padding — **zero cropping**, 100% of original content visible.
- **Resolution identical**: same pixel dimensions; same DPI metadata if present.
- **EXIF**: the raw EXIF byte blob from the source is re-injected **verbatim** on save
  (`im.info['exif']`). No tags are re-encoded, dropped, or "fixed". We deliberately do
  **not** apply `exif_transpose` to pixels, so an orientation-tagged file stays semantically
  identical (pixels pre-transposed, tag intact → renders exactly as the source did,
  uniformly scaled).
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
| Window | `Adw.ApplicationWindow` | default 1100×720; dark mode **automatic** (Adw follows system, zero code) |
| Header | `Adw.HeaderBar` | start: **Add Images** button (`list-add-symbolic`), **Add Folder** button (`folder-symbolic`); end: `Gtk.MenuButton` hamburger (`GMenu`: Clear finished, Clear all, Settings, About, Quit); center: `Adw.WindowTitle` "Framer" |
| File pickers | `Adw.FileDialog` | `open_files()` with a `Gtk.FileFilter` of image suffixes; `open_folder()` for whole folders |
| Status toasts | `Adw.ToastOverlay` + `Adw.Toast` | "N images added", "Batch finished X/Y", per-error HIGH-priority toasts |
| Empty state | `Adw.StatusPage` | "No images yet" + primary action; swapped out when queue non-empty |
| Queue list | `Adw.ToolbarView` → `Gtk.ScrolledWindow` → `Gtk.ListBox` | selection mode NONE; rows = `QueueRow` composites |
| Queue row | custom `Gtk.Box` (HBox) | `Gtk.Image` thumbnail (48 px `Gdk.Texture`) · `Gtk.Label` filename (ellipsized) + dim-label (`W×H · JPEG · 2.3 MB`) · right side: `Adw.Spinner` (processing) / `Adw.StatusIcon` `emblem-ok-symbolic` (done) / `Adw.StatusIcon` `dialog-error-symbolic` (error) / dim label "Queued" |
| Job bar | `Gtk.Box` (vertical) in `Adw.ToolbarView` bottom bar | **Controls row**: `Adw.SpinRow` "Frame thickness" (below, `hexpand`) + **Start Framing** `Gtk.Button` (`suggested-action`, `media-playback-start-symbolic`) + **Cancel** button (`process-stop-symbolic`). **Progress row**: `Adw.Spinner` (visible while running) + status label ("3 of 12 — beach.jpg", `hexpand`) + `Gtk.ProgressBar` (`set_show_text(True)`, `set_fraction`) |
| Frame thickness | `Adw.SpinRow` (native Libadwaita slider + numeric entry composite, Adw ≥ 1.5 — we have 1.9) | `Gtk.Adjustment(5.00, 0.00, 20.00, step 0.01, page 0.1)`, `set_digits(2)`, `add_suffix("%")`, title "Frame thickness", subtitle "White frame on each side, % of the image edge"; bound to the `frame-percent` GSettings key (load on startup, persist on change); **insensitive while a batch runs** — the value is snapshotted at job start |
| Drag & drop | `widget.set_drag_dest(Gdk.Uri)` on the window | `drag-data-received` → `GLib.Value.get_string()` → URI filter by extension + magic probe |
| Settings | `Gio.Settings` (schema `com.funkyskywalker.Framer`) | keys: `output-directory` ("" = next to source), `suffix` (default `_framed`), `frame-percent` (double, default 5.00, range 0.00–20.00); graceful in-memory fallback if schema not installed (wrap in try/except, hardcoded defaults) |
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
  path `/com/funkyskywalker/Framer/`; string key `output-directory` (default `""`), string key
  `suffix` (default `"_framed"`), double key `frame-percent` (default 5.0, range 0.0–20.0,
  "Frame thickness in percent of each image edge"), all with summaries/descriptions.
- **`data/com.funkyskywalker.Framer.desktop`**: `Type=Application`, `Name=Framer`,
  `Exec=python3 {install-path}/main.py %F`, `MimeType=image/jpeg;image/png;image/webp;image/tiff;image/bmp;image/x-ms-bmp;image/gif;image/apng;`, `Icon=image-x-generic`,
  `Categories=Graphics;`.
- **`framer/__init__.py`**: `APP_ID = "com.funkyskywalker.Framer"`, `__version__ = "1.0.0"`.
- **`core/models.py`** (no GTK): `class ItemState(str, Enum)` — `QUEUED, PROCESSING, DONE,
  ERROR, CANCELLED`. `@dataclass QueueItem` — `path: Path`, `uri: str`, `width/height: int|None`,
  `format: str|None`, `size_bytes: int|None`, `state: ItemState`, `fraction: float`,
  `output_path: Path|None`, `error: str|None`. `@dataclass JobSummary` — `total, done,
  failed, cancelled`.
- **`core/framing.py`** (no GTK): constants `FRAME_PERCENT_DEFAULT = 5.0`,
  `FRAME_PERCENT_MIN = 0.0`, `FRAME_PERCENT_MAX = 20.0`; `def frame_geometry(w, h, percent) ->
  Geometry` (dataclass with `canvas_w, canvas_h, inner_w, inner_h, pad_l, pad_r, pad_t, pad_b`)
  implementing the §4 math exactly (clamp `percent` to `[0, 20]`, pure int, unit-testable); `def white_for_mode(mode) ->
  tuple|None` (mode map from §4, returns `None` for modes that must be converted first);
  `def compute_working_mode(mode) -> str` (identity or `RGBA`/`RGB` target).
- **`core/image_io.py`** (no GTK): `def probe(path) -> (w, h, format, size)` (fast open,
  no full decode — `Image.open` + `im.size`/`im.format`/`im.info.get('n_frames',1)`);
  `def frame_image(src_path, dst_path, percent=5.0, progress_cb=None) -> None` — full pipeline (`percent` clamped via `frame_geometry`): open,
  build white canvas, per-frame resize+paste (multi-frame support: `n_frames > 1` → iterate
  frames, collect durations/disposal/loop from source `info`, `save_all=True`), `progress_cb
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
  SignalBus, suffix, output_dir, frame_percent)`; `frame_percent` is snapshotted from the UI at
  job start (the `SpinRow` is insensitive while running, so it cannot change mid-batch) and passed
  to `frame_image`; internal `queue.Queue` (worker→main) + `threading.Event`
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
  `QueueRow`s; (c) bottom job bar — a vertical `Gtk.Box`: **controls row** with
  `Adw.SpinRow` (`Gtk.Adjustment.new(5.0, 0.0, 20.0, 0.01, 0.1, 0.0)`, `set_digits(2)`,
  `add_suffix("%")`, `set_title("Frame thickness")`,
  `set_subtitle("White frame on each side, % of the image edge")`, `hexpand`) + Start
  button (`suggested-action`, `Adw.ButtonContent` `media-playback-start-symbolic` "Start
  Framing") + Cancel button (`process-stop-symbolic` "Cancel", insensitive unless running);
  **progress row** with `Adw.Spinner` + status `Gtk.Label` (`hexpand`) + `Gtk.ProgressBar`
  (`set_show_text(True)`). API: `add_item(QueueItem)`, `update_item(index, fraction, state)`,
  `set_running(bool, current_label)` (also toggles `SpinRow` sensitivity),
  `set_progress(done, total, fraction)`, `clear()`, `clear_finished()`, `items()`,
  `get_frame_row() -> Adw.SpinRow` (window binds it to GSettings).
- **`window.py`**: `class FramerWindow(Adw.ApplicationWindow)` — builds
  `Adw.ToastOverlay` → `Adw.ToolbarView` (top: `Adw.HeaderBar`; content: `QueueView`;
  bottom bar: job bar lives inside QueueView); wires `Adw.FileDialog` (files + folder,
  image `Gtk.FileFilter`); wires `set_drag_dest(Gdk.Uri)` + `drag-data-received`
  (URI → `Gio.File`, filter via `is_image_file`, probe via `core.probe`, build `QueueItem`s,
  toast "N images added"); owns `Dispatcher` + `BatchJob` lifecycle; connects
  `SignalBus` signals to `QueueView` updates + toasts (finished: summary toast, HIGH
  priority if any failures); implements the add-files/add-folder/start/cancel/clear/
  clear-finished/about/settings handlers; `add_paths(paths: list[Gio.File])` shared by
  dialog/drop/CLI-`open`; binds `QueueView.get_frame_row()`: initial value from the
  `frame-percent` setting, writes back (clamped to [0, 20]) on `adjustment::value-changed`;
  starts `BatchJob` with `frame_percent = spinrow.get_value()`.
- **`app.py`**: `class FramerApplication(Adw.Application)` — `__init__(APP_ID,
  default_flags)`, `app.set_application_icon_name("image-x-generic")`; GSettings
  service with graceful fallback (try `Gio.Settings.new("com.funkyskywalker.Framer")`,
  except `GLib.Error` → in-memory defaults `{"output-directory": "", "suffix": "_framed",
  "frame-percent": 5.0}` with the same get/set interface); `do_activate` creates the window; `do_open(files, n)`
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
  usage (add images/folder, drag & drop, frame-thickness control — slider + numeric entry,
  0.00–20.00%, two decimals, default 5.00, persisted across sessions — accelerators table),
  output naming rules
  (`<stem>_framed.<ext>`, collision suffixing), framing math summary (5% per side, 0.90
  content scale, never enlarged, EXIF/ICC verbatim), per-format save-quality table,
  limitations (no AVIF/JXL/HEIC on this system; tiny images <5 px), license MIT.
- **`AGENTS.md`**: project rules for agentic work — layering law (`core/` must never import
  GTK/GObject; all GTK on the main thread only via the Dispatcher; worker thread never
  calls GLib UI APIs), how to run (system python3 or `--system-site-packages` venv),
  how to smoke-test headless (see 6.3), file map, do-not-break list (EXIF/ICC verbatim,
  never enlarge, per-item error isolation, single writer thread, frame percent clamped to
  [0, 20] in core AND UI with a snapshot at job start), where to add formats
  (`utils/paths.py` extensions + `core/image_io.py` save table), commit style
  (author `picode <roman.mikula.picode@funkyskywalker.at>` per gitea skill conventions
  if pushing to Gitea).

### 6.3 Acceptance checks (must pass before declaring Phase 2 done)

1. `python3 -c "import gi; gi.require_version('Gtk','4.0'); gi.require_version('Adw','1');
   import framer.app; print('import OK')"` — clean import, no warnings.
2. Headless math test (no display needed):
   - `frame_geometry(2000, 1333, 5.0)` → inner `1800×1200` (`round(0.9*1333)=1200`),
     canvas exactly `2000×1333`, pads sum exactly to `canvas − inner`.
   - Frame-thickness sweep: for `p` in {0.00, 2.50, 5.00, 7.37, 12.00, 20.00} × 50 random
     sizes: never enlarges (`inner ≤ canvas` on both axes), `p=0` → inner == canvas (zero
     frame), `p=20` → inner == `round(0.6·dim)`; out-of-range inputs (e.g. 30, −2) are
     clamped and never raise.
   - Synthetic end-to-end: create `Image.new('RGB', (640, 480), (10, 20, 30))`, save JPEG
     with an `exif` blob + `icc_profile`, run `frame_image`, reopen output:
     assert size == (640, 480), `info['exif']` bytes identical to source's,
     corner pixel of output == white (255,255,255), center pixel unchanged hue.
   - RGBA PNG with transparency: output stays PNG, size identical, corner white with
     alpha 255.
   - GIF 2-frame: output GIF has `n_frames == 2`, durations preserved.
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
- All geometry math goes through `core.framing.frame_geometry` (single source of truth for
  the user-configurable frame thickness); no hardcoded `0.05` anywhere downstream.
- Respect the two-phase protocol: do not start until the user explicitly approves.
- If the PyCharm MCP servers happen to be up in the new session, they may be used for
  project-wide symbols/diagnostics, but native tools are the fallback (they are down by
  default — port 64344 usually unconnected).
