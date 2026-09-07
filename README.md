# Framer

A GNOME (GTK 4 + Libadwaita, PyGObject) desktop app that **batch-frames
images** onto a user-defined **target canvas**:

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

## Prerequisites

Ubuntu 26.04 desktop already has everything:

| Package | Provides |
|---|---|
| `python3-gi` + `gir1.2-gtk-4.0` | PyGObject, GTK 4.22 typelibs |
| `gir1.2-adw-1` | Libadwaita 1.9 |
| `Pillow` (12.x on this machine) | image decode/encode |

No downloads are required to run.

## Running

**(a) System Python (simplest — recommended):**

```sh
python3 main.py [IMAGE ...]
```

**(b) venv with system site packages:**

```sh
rm -rf .venv
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py [IMAGE ...]
```

Note: the bundled `.venv` is isolated (no system site packages) and cannot
see the system PyGObject — recreate it with
`--system-site-packages` if you want to use it.

### GSettings persistence (optional)

Output directory, suffix, frame thickness, aspect ratio, orientation, and
short edge persist across sessions when the schema is installed:

```sh
install -d ~/.local/share/glib-2.0/schemas
cp data/com.funkyskywalker.Framer.gschema.xml ~/.local/share/glib-2.0/schemas/
glib-compile-schemas ~/.local/share/glib-2.0/schemas
```

Without the schema the app falls back to in-memory defaults — everything
still works, settings just don't survive a restart.

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
