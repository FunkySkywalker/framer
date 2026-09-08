# Framer

A desktop app that **batch-frames images** onto a user-defined
**target canvas**:

- **Aspect ratio**: presets `5:4` / `19:16`, or a custom configurable `A:B`
  (integers 1–999)
- **Orientation**: landscape (as entered) / portrait (flipped)
- **Short-edge resolution**: 16–8192 px (default 1080) — the short edge of
  the output is exactly this value; the long edge realizes the ratio
  (round-half-up)
- **White frame**: thickness configurable `0.00–20.00%` (slider + numeric
  entry, two decimals, default `5.00%`), on each side, strictly **inside**
  the canvas
- **Content**: contain-fitted inside the frame — **never cropped**, source
  aspect preserved, upscaled with LANCZOS when the source is smaller than
  the frame
- **Save**: maximum quality per format, **EXIF and ICC profiles preserved
  verbatim**, multi-frame (GIF / APNG / animated WebP) supported per-frame

Two frontends exist during the [Qt migration](#qt-migration-in-progress):
the GTK 4 + Libadwaita app (`main.py`, current default) and the PySide6
app (`main_qt.py`, feature-complete, offscreen-verified). Both share the
pure core (`framer/core/`) and the batch worker — everything described
below applies to both.

## Prerequisites

Ubuntu 26.04 desktop already has everything for the GTK app:

| Package | Provides |
|---|---|
| `python3-gi` + `gir1.2-gtk-4.0` | PyGObject, GTK 4.22 typelibs |
| `gir1.2-adw-1` | Libadwaita 1.9 |
| `Pillow` (12.x on this machine) | image decode/encode |

No downloads are required to run the GTK app. The Qt app needs one more
package, installed in an isolated venv (see below): `PySide6` (6.11.x).

## Running

**(a) GTK app — system Python (simplest — recommended):**

```sh
python3 main.py [IMAGE ...]
```

**(b) GTK app — venv with system site packages:**

```sh
rm -rf .venv
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py [IMAGE ...]
```

Note: the bundled `.venv` is isolated (no system site packages) and cannot
see the system PyGObject — recreate it with
`--system-site-packages` if you want to use it.

**(c) Qt app (migration target):**

```sh
python3 -m venv .venv-qt
.venv-qt/bin/pip install PySide6 Pillow
.venv-qt/bin/python main_qt.py [IMAGE ...]
```

Headless/offscreen: `QT_QPA_PLATFORM=offscreen .venv-qt/bin/python
scripts/theme_report.py` (this machine additionally needs the EGL shim —
see `AGENTS.md`, *Qt frontend notes*).

### GSettings persistence (GTK app, optional)

Output directory, suffix, frame thickness, aspect ratio, orientation, and
short edge persist across sessions when the schema is installed:

```sh
install -d ~/.local/share/glib-2.0/schemas
cp data/com.funkyskywalker.Framer.gschema.xml ~/.local/share/glib-2.0/schemas/
glib-compile-schemas ~/.local/share/glib-2.0/schemas
```

Without the schema the app falls back to in-memory defaults — everything
still works, settings just don't survive a restart.

### QSettings persistence (Qt app)

The Qt app persists the **same eight keys with the same defaults** to a
QSettings INI file: `~/.config/com.funkyskywalker/Framer.conf`. The two
stores are independent — values are not migrated between them.

## Qt migration (in progress)

The GTK GUI is being replaced by a PySide6 (Qt 6) frontend with full
functional parity, targeting native appearance on Ubuntu (GNOME/Yaru,
KDE/Breeze) and Windows 11 (Fluent) — the app follows the system's style,
palette, font, and icon theme and adds only a minimal palette-derived QSS
layer.

- **Plan & status**: `.agent/feature-migration-qt/plan.md` (8 phases,
  verification gates) and `progress.md` (what's done, pitfalls found)
- **Current state**: Phases 1–7 done — the Qt frontend lives in
  `framer/qt/` (entry `main_qt.py`) and is verified end-to-end offscreen:
  full batch runs with EXIF/ICC byte-identity, settings persistence with
  restart restore, deterministic cancellation, theming across five palette
  variants. Screenshots: `.agent/feature-migration-qt/screenshots/`
- **Remaining**: a real-machine theme review (GNOME light + dark, Windows
  11 light + dark — `.venv-qt/bin/python scripts/theme_report.py`), then
  the Phase 8 cutover: `main.py` becomes the Qt entry point and
  `framer/gtk/` is deleted

## Usage

- **Add Images** (header, `Ctrl+O`) or **Add Folder** (`Ctrl+Shift+O`), or
  drag & drop files/folders into the window
- **Output row** (bottom): aspect preset (`5:4` / `19:16` / `Custom` with
  A:B entries), **Landscape/Portrait** flip, **Short edge** in pixels, and
  a live **Result: W × H** preview of the target canvas
- **Frame row**: **Frame thickness** (slider + numeric entry,
  `0.00–20.00%`, default `5.00`), **Start Framing** (`Ctrl+Return`),
  **Cancel** (`Ctrl+.`)
- **Hamburger menu**: Clear finished, Clear all, Settings (output
  directory + suffix), About
- `Ctrl+W` closes the window

While a batch runs, the output/frame controls are insensitive — the
complete `OutputSpec` is snapshotted at job start, so nothing can change
mid-batch. Failures are per-item: a corrupt file marks that row red and
the batch continues.

## Output naming

Files are written as `<stem><suffix>.<ext>` (default suffix `_framed`,
original lowercase extension), **next to the source** by default, or in
the configured output directory. Name collisions get `_1`, `_2`, …
suffixes until a free name is found. The source file itself is never
overwritten.

## Framing model

```
canvas  = target_canvas(aspect A:B, orientation, short edge S)   # Wc × Hc
inner   = frame_geometry(canvas, frame %)                        # inside canvas
content = content_fit(source, inner)                             # contain, no crop
output  = white(Wc×Hc) + source.resize(content size, LANCZOS)    # centered in frame
```

All geometry goes through `framer/core/framing.py` — the single source of
truth. Guarantees (verified by exhaustive random sweeps):

- short edge exactly `S`; long edge within round-half-up (≤ 0.5 px)
- frame strictly inside the canvas for all `p ∈ [0, 20]`; `p = 0` → zero frame
- `1 ≤ content ≤ inner` on both axes — 100% of the source is always visible
- source aspect ratio preserved within ±0.5 px per axis

## Per-format save quality

| Format | Parameters |
|---|---|
| JPEG | `quality=100`, `subsampling=0` (4:4:4), EXIF + ICC verbatim |
| PNG | lossless; palette sources saved as RGBA (still lossless, color-exact), EXIF + ICC |
| WebP | `quality=100`, `method=6`, EXIF + ICC |
| TIFF | original lossless compression reused (LZW/Deflate/ZSTD) else LZW, EXIF + ICC |
| BMP | lossless, as-is |
| GIF / APNG / animated WebP | per-frame framing, original `duration`/`disposal`/`loop` preserved |

Other multi-frame formats: first frame + a warning toast.

## Limitations

- **AVIF / JXL / HEIC** are not decodable on this system (no Pillow
  plugins) — such files are rejected with a visible error, never silently.
- Output size/aspect is **user-defined** and not tied to the source size.
- Preserved EXIF blobs keep their original pixel-dimension tags
  (`ExifImageWidth/Height`), which are stale when the canvas differs from
  the source size — rendering is unaffected.
- Cancellation finishes the file currently being encoded (a single C call
  cannot be safely interrupted mid-encode); everything after stops.

## License

MIT
