# Framer — Agent Rules

Hard rules for agentic work in this repository.

## Layering law (do not break)

- `framer/core/` must **never import GTK/GObject** (or anything from
  `gi.repository`). It is pure Python + Pillow and must stay unit-testable
  headless. (`grep -rln "gi.repository\|import gi" framer/core/` → no hits.)
- **All GTK calls happen on the main thread only**, and only through the
  Dispatcher's signal emissions. Worker threads push plain event tuples
  onto `queue.Queue`s; they never touch GTK, GLib UI APIs, or the UI tree.
- `framer/utils/thumbnails.py` is the one sanctioned exception: it
  produces `Gdk.Texture`s on the Dispatcher's thread pool (thread-safe
  load path) and the *result* is consumed on the main thread.
- `framer/workers/` is the only layer where threads and the GLib main
  loop meet.

## Geometry law

- All output/frame geometry goes through `framer/core/framing.py`
  (`target_canvas` + `frame_geometry` + `content_fit`) — the single
  source of truth. No hardcoded aspect ratios, `0.05`, or `1080` anywhere
  downstream.
- `OutputSpec` is clamped in **both** core (`models.py`) and the UI
  (spin ranges / SpinRow adjustment) and is **snapshotted at job start**;
  all output/frame controls are insensitive while a batch runs.

## Do-not-break list

- EXIF and ICC pass **verbatim** (`im.info['exif']`,
  `im.info['icc_profile']`) — never re-encode, drop, or "fix" tags.
- Never apply `ImageOps.exif_transpose` to output pixels (display
  thumbnails only).
- Frame is strictly inside the canvas; content is **never cropped**
  (`1 ≤ W′ ≤ inner_w`, `1 ≤ H′ ≤ inner_h` always).
- Output size is derived ONLY from `OutputSpec` via `core.framing`.
- Per-item error isolation: one corrupt file must not kill the batch.
- Single writer thread: only the `BatchJob` worker mutates `QueueItem`s.
- Cancellation: a file mid-encode finishes; everything after stops.

## How to run

- System Python: `python3 main.py` (Ubuntu 26.04 desktop has PyGObject,
  GTK 4.22, Libadwaita 1.9, Pillow 12).
- venv: `python3 -m venv --system-site-packages .venv && .venv/bin/pip
  install -r requirements.txt && .venv/bin/python main.py`
  (the isolated default venv cannot see system PyGObject).

## Headless smoke test (no display needed)

- Import: `python3 -c "import gi; gi.require_version('Gtk','4.0');
  gi.require_version('Adw','1'); import framer.app; print('ok')"`
- Math: exercise `framer.core.framing` (target_canvas vectors,
  frame_geometry sweeps, content_fit no-cropping invariant) and
  `framer.core.image_io.frame_image` with synthetic images (EXIF/ICC
  byte-identity, corner white, multi-frame GIF frame count/durations).

## File map

```
main.py                      thin CLI entry
data/                        .desktop + GSettings schema
framer/
  app.py                     Adw.Application, settings service (fallback)
  window.py                  window, file input, settings binding, jobs
  core/                      PURE (models, framing, image_io, scanner, output)
  workers/                   SignalBus, BatchJob (thread), Dispatcher (60 ms tick)
  views/                     QueueRow, QueueView (+ 3-row bottom controls)
  ui/                        Actions (menu/accels), toast helpers
  utils/                     paths (pure), thumbnails (thread-pool)
```

## Adding image formats

1. `framer/utils/paths.py` — `IMAGE_EXTENSIONS`
2. `framer/core/image_io.py` — save table in `_save` / `_resolve_save_mode`
   (and working-mode map in `framer/core/framing.py` if a new mode appears)

## Commit style

When pushing to Gitea: author `picode <roman.mikula.picode@funkyskywalker.at>`.

## API notes (this machine: GTK 4.22 / Libadwaita 1.9)

- No `Adw.StatusIcon` — use `Gtk.Image` with symbolic icons.
- No `Adw.FileDialog` — use `Gtk.FileChooserNative` + `Gtk.FileFilter`. Constructor is `new(title: str|None, parent: Gtk.Window|None, action, accept_label, cancel_label)` — first arg is a *string*, not the window. Present it with `show()` — no `present()`; use the `response` signal.
- `Gtk.ComboBox` is deprecated — use `Gtk.DropDown`
  (`new_from_strings`, `set_selected`, `notify::selected`).
- `Adw.SpinRow` (1.9): construct with `Adw.SpinRow()` +
  `set_adjustment(adj)`; `add_suffix` takes a widget. **It renders NO slider
  track** — it is a drag-to-scrub row + spin button only (verified against the
  1.9.3 template and official doc image). For a *visible* slider use
  `Adw.ActionRow` + suffix box with `Gtk.Scale` + `Gtk.SpinButton` sharing one
  `Gtk.Adjustment` (see the frame row in `views/queue_view.py`).
- `Gtk.Scale.set_width_chars` does not exist in this GTK4 build — size the
  slider with `set_hexpand`/CSS.
- `Adw.Spinner`: toggle via the `spinning` property (no `set_spinning` in
  this build).
- `Gtk.SpinButton.new_with_range(...)`; no `set_page_increment` in GTK4.
- `Adw.ToolbarView.add_top_bar(...)`; `Adw.PreferencesWindow.add(page)`
  (`set_child` aborts on AdwWindow in 1.9).
- `Gtk.Image`: no `set_from_texture` — use `set_from_paintable(texture)`;
  thumbnails: `Gdk.Texture.new_for_pixbuf(pixbuf)`.
- `Gio.SimpleActionGroup` (not Gtk); no `ActionGroup.set_enabled` — set it
  on each `Gio.SimpleAction`.
- `Adw.ToastPriority` has only NORMAL/HIGH (no LOW).
- MIT license enum value is `Gtk.License.MIT_X11`.
- Drag & drop: `Gtk.DropController` and `Gdk.Uri` are GONE — use
  `Gtk.DropTarget.new(Gdk.FileList.__gtype__, Gdk.DragAction.COPY)` +
  `"drop"` signal (`value.get_boxed().get_files()` → `list[Gio.File]`).
- No `set_application_icon_name` (GTK3) — use `window.set_icon_name(...)`.
- Overriding `do_startup` on an `Adw.Application` subclass SEGFAULTS on
  this stack — initialize lazily instead (see `FramerApplication.get_settings`).
- `Gio.Settings.new()` aborts the process on a missing schema — probe
  `Gio.SettingsSchemaSource.lookup()` first.
- PyGObject vfunc chain-up on Gio.Application subclasses: use
  `Gio.Application.do_startup(self)`-style explicit self, never
  `super().do_*()`.
