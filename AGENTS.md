# Framer — Agent Rules

Hard rules for agentic work in this repository.

Two frontends exist during the Qt migration: `framer/gtk/` (frozen, the
current default via `main.py`) and `framer/qt/` (migration target via
`main_qt.py`). Plan + status: `.agent/feature-migration-qt/{plan,progress}.md`.

## Layering law (do not break)

- `framer/core/` must **never import GTK/GObject** (or anything from
  `gi.repository`). It is pure Python + Pillow and must stay unit-testable
  headless. (`grep -rln "gi.repository\|import gi" framer/core/` → no hits.)
- **All GTK calls happen on the main thread only**, and only through the
  Dispatcher's signal emissions. Worker threads push plain event tuples
  onto `queue.Queue`s; they never touch GTK, GLib UI APIs, or the UI tree.
- `framer/gtk/thumbnails.py` is the one sanctioned exception: it
  produces `Gdk.Texture`s on the Dispatcher's thread pool (thread-safe
  load path) and the *result* is consumed on the main thread.
- The two frontends are symmetric: `framer/gtk/` (PyGObject) and
  `framer/qt/` (PySide6) are the only places that import their GUI
  toolkit; `framer/core/`, `framer/workers/`, and `framer/utils/` are
  pure and shared. (`grep -rln "PySide6\|shiboken" framer/core/`
  framer/workers/ framer/utils/ → no hits.)
- The Qt side mirrors the GLib rules: `framer/qt/dispatcher.py` drains
  the same queue pattern with a 60 ms `QTimer` on the main thread;
  `framer/qt/thumbnails.py` is the Qt-side sanctioned exception (PIL →
  PNG bytes on the pool, QPixmap built on the main thread).

## Geometry law

- All output/frame geometry goes through `framer/core/framing.py`
  (`target_canvas` + `frame_geometry` + `content_fit`) — the single
  source of truth. No hardcoded aspect ratios, `0.05`, or `1080` anywhere
  downstream.
- `OutputSpec` is clamped in **both** core (`models.py`) and the UI
  (GTK SpinRow/spin ranges, Qt `controls.py` spin+slider ranges) and is
  **snapshotted at job start**; all output/frame controls are
  insensitive while a batch runs.

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

Two frontends exist during the Qt migration (see
`.agent/feature-migration-qt/plan.md`); Phase 8 removes the GTK one.

- GTK app: `python3 main.py` (Ubuntu 26.04 desktop has PyGObject, GTK
  4.22, Libadwaita 1.9, Pillow 12).
- GTK app in a venv: `python3 -m venv --system-site-packages .venv &&
  .venv/bin/pip install -r requirements.txt && .venv/bin/python main.py`
  (the isolated default venv cannot see system PyGObject).
- Qt app: `.venv-qt/bin/python main_qt.py` (venv: `python3 -m venv
  .venv-qt && .venv-qt/bin/pip install PySide6 Pillow`).

## Headless smoke test (no display needed)

- GTK import: `python3 -c "import gi; gi.require_version('Gtk','4.0');
  gi.require_version('Adw','1'); import framer.gtk.app; print('ok')"`
- Qt import: `QT_QPA_PLATFORM=offscreen
  LD_LIBRARY_PATH=.agent/feature-migration-qt/qtlibs .venv-qt/bin/python
  -c "import framer.qt.app; print('ok')"` (the LD_LIBRARY_PATH is the EGL
  shim — see Qt frontend notes)
- Qt phase verifications (offscreen, all must print ALL PASS):
  `scripts/verify_qt_plumbing.py`, `verify_queue_ui.py`,
  `verify_controls.py`, `verify_window.py`, `verify_settings_batch.py`,
  `scripts/theme_report.py` (each self-re-execs with the offscreen env +
  shim baked in, so they run plain).
- Math: exercise `framer.core.framing` (target_canvas vectors,
  frame_geometry sweeps, content_fit no-cropping invariant) and
  `framer.core.image_io.frame_image` with synthetic images (EXIF/ICC
  byte-identity, corner white, multi-frame GIF frame count/durations).

## File map

```
main.py                      thin CLI entry — GTK (Phase 8 → Qt)
main_qt.py                   thin CLI entry — Qt
data/                        .desktop + GSettings schema
framer/
  core/                      PURE (models, framing, image_io, scanner, output)
  workers/                   batch_worker (BatchJob thread) — pure, shared
  utils/                     paths (pure)
  gtk/                       GTK4/Libadwaita frontend (frozen; removed in Phase 8)
    app.py                   Adw.Application, settings service (fallback)
    window.py                window, file input, settings binding, jobs
    views/                   QueueRow, QueueView (+ 3-row bottom controls)
    ui/                      Actions (menu/accels), toast helpers
    dispatcher.py            SignalBus + 60 ms GLib tick
    thumbnails.py            thread-pool Gdk.Texture factory
  qt/                        PySide6 frontend (migration target)
    app.py                   FramerQtApp (QApplication + theme + window)
    window.py                window, file input, settings binding, jobs
    queue_row.py / queue_view.py / controls.py / dialogs.py / settings.py
    bus.py / dispatcher.py   SignalBus + 60 ms QTimer tick
    theme.py / toasts.py / widgets.py / thumbnails.py / icons/
```

## Adding image formats

1. `framer/utils/paths.py` — `IMAGE_EXTENSIONS`
2. `framer/core/image_io.py` — save table in `_save` / `_resolve_save_mode`
   (and working-mode map in `framer/core/framing.py` if a new mode appears)

## Commit style

When pushing to Gitea: author `picode <roman.mikula.picode@funkyskywalker.at>`.

## Qt frontend notes (PySide6 6.11.2 — for `framer/qt/`)

- **Offscreen runs need the EGL shim** (this machine has no libEGL):
  `QT_QPA_PLATFORM=offscreen LD_LIBRARY_PATH=.agent/feature-migration-qt/qtlibs
  .venv-qt/bin/python ...`. The shim is a symlink to Electron's bundled
  libEGL: `ln -s ~/.hermes/hermes-agent/node_modules/electron/dist/libEGL.so
  .agent/feature-migration-qt/qtlibs/libEGL.so.1`; `qtlibs/` is
  gitignored — recreate it if missing. Verification scripts self-re-exec
  with the env baked in, so run them plain.
- The gtk3 platform theme ABORTS offscreen ("cannot open display") —
  never set `QT_QPA_PLATFORMTHEME=gtk3` in offscreen harnesses.
- **Type check**: `~/.local/bin/ty check --python .venv-qt/bin/python
  framer/qt/ ...` (system python has no PySide6; the qt venv has no
  `gi`, so a whole-repo run shows pre-existing gi diagnostics — ignore
  those, fix the rest).
- PySide6 6.11.2 pitfalls (all verified on this stack; full history in
  `progress.md`):
  - `QButtonBox` is REMOVED — plain `QPushButton`s.
  - `QKeySequence("Ctrl+Period")` parses empty — the key string is
    `"Ctrl+."` (Ctrl+Key_Period).
  - Children created while the parent is already visible start HIDDEN —
    `show()` them explicitly (queue rows, toasts).
  - `QApplication.instance()` types as `QCoreApplication` — narrow with
    `isinstance`.
  - `QImage.loadFromData(png)` — pass no format arg (str and bytes are
    both rejected at runtime).
  - No `QPalette.Error` role — the palette Highlight doubles as the
    needs-attention accent (high-priority toasts).
  - `.clicked` fires only for user clicks — programmatic state changes
    need `.toggled`.
  - `QSettings.value()` returns mixed types — normalize via `str()`
    before int/float/bool; identity = org `com.funkyskywalker`, app
    `Framer` → `$XDG_CONFIG_HOME/com.funkyskywalker/Framer.conf`.
  - `styleHints().colorScheme()` is a METHOD and the `ColorScheme` enum
    is NOT exported — compare `str(...).endswith("Dark")`.
  - `colorSchemeChanged` passes the enum as an argument — connected slots
    MUST accept extra args.
  - Manual `processEvents()` NEVER flushes DeferredDelete (only `exec()`
    does) — `hide()` before `deleteLater()`.
  - `QScrollArea` frame shape is `QFrame.Shape.NoFrame`; no
    `SP_FileDialogNewFile`/`SP_BrokenImage`; word-wrapped QLabels need an
    `Expanding` size policy; sample pixels with `mapTo` (x()/y() are
    parent-relative).
- **Theming law** (`framer/qt/theme.py`): every QSS color is computed
  from the live palette — no hex literals in widget code, no font rules;
  the Breeze table in `theme.py` is the only sanctioned exception.
  Platform decisions: GNOME → gtk3 platform theme (env set BEFORE
  QApplication), Plasma → Fusion + Breeze table, Windows → native style +
  `setDefault()` accent (no accent QSS), `FRAMER_COLOR_SCHEME=light|dark`
  forces a palette (also the offscreen hook). The QSS re-applies on
  `colorSchemeChanged` (live light/dark switching).
- **Verification convention**: each phase has an offscreen script under
  `scripts/` and committed screenshots under
  `.agent/feature-migration-qt/screenshots/` (qtlibs + venv_install.log +
  theme-fixtures stay gitignored); screenshots must be looked at by the
  main agent before a phase counts as done.

## API notes (this machine: GTK 4.22 / Libadwaita 1.9 — for `framer/gtk/`)

- No `Adw.StatusIcon` — use `Gtk.Image` with symbolic icons.
- No `Adw.FileDialog` — use `Gtk.FileChooserNative` + `Gtk.FileFilter`. Constructor is `new(title: str|None, parent: Gtk.Window|None, action, accept_label, cancel_label)` — first arg is a *string*, not the window. Present it with `show()` — no `present()`; use the `response` signal.
- `Gtk.ComboBox` is deprecated — use `Gtk.DropDown`
  (`new_from_strings`, `set_selected`, `notify::selected`).
- `Adw.SpinRow` (1.9): construct with `Adw.SpinRow()` +
  `set_adjustment(adj)`; `add_suffix` takes a widget. **It renders NO slider
  track** — it is a drag-to-scrub row + spin button only (verified against the
  1.9.3 template and official doc image). For a *visible* slider use
  `Adw.ActionRow` + suffix box with `Gtk.Scale` + `Gtk.SpinButton` sharing one
  `Gtk.Adjustment` (see the frame row in `framer/gtk/views/queue_view.py`).
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
