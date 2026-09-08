# Framer GTK → PySide6 Migration

## Goal

Migrate the Framer GUI from GTK 4 + Libadwaita (PyGObject) to **PySide6 (Qt 6)** with
**full parity of every GUI functionality** the current GTK app provides, and make it
**look native** on Ubuntu 26.04 (GNOME/Yaru light + dark, KDE Plasma/Breeze) and
Windows 11 (native Fluent style, light + dark) — see the appearance item in the
inventory and Phase 7. The pure
`framer/core` package (framing math, image I/O, scanner, output) and the `BatchJob`
worker thread are reused unchanged; everything GTK-specific (window, views, actions,
toasts, dispatcher, thumbnails, GSettings) is rebuilt as Qt.

## Scope

**Chosen toolkit: PySide6.** (Qt 6, LGPL. PyQt6 is API-equivalent for this app's needs;
if PyQt6 is preferred, only Phase 1's import/install step changes — decide then.)
Verified on this machine: PySide6 6.11.2 resolves a `cp310-abi3` manylinux wheel, so it
installs cleanly in a plain venv under the system Python 3.14.4.

**Build strategy: parallel, then cutover.** The Qt app is developed alongside the
working GTK app in a new `framer/qt/` subpackage with its own entry `main_qt.py`.
Each phase is independently runnable/verifiable; the GTK app stays intact until
Phase 7 flips the entry point and deletes the GTK modules.

**Layering law (unchanged):** `framer/core/` must never import Qt either
(`grep -rln "PySide6\|shiboken" framer/core/` → no hits). **Threading law (Qt):**
all Qt calls happen on the main thread only. Worker threads push plain event tuples
onto `queue.Queue`s; a 60 ms `QTimer` tick on the main loop drains them and emits Qt
signals — the exact analog of the current GLib Dispatcher + SignalBus. `BatchJob`
is reused as-is (it only pushes tuples and never calls the bus).

### Feature inventory (parity checklist — every item must work in the Qt app)

Window & chrome
1. Main window "Framer", default 1100×760, min 980×480, app icon.
2. Header/toolbar: **Add images** button (Ctrl+O), **Add folder** button
   (Ctrl+Shift+O), **hamburger menu**.
3. Menu: Clear finished · Clear all · Settings… · About Framer · Quit.
4. Accelerators: Ctrl+O, Ctrl+Shift+O, Ctrl+Return (start), Ctrl+Period (cancel),
   Ctrl+W (close window).
5. Toast notifications: normal (3 s) for "N images added", "N files skipped",
   per-item warnings, "Cancelling after the current file…", "Batch cancelled";
   high-priority (5 s) for per-item errors and failed/cancelled batch summaries;
   success style for clean batch completion.
6. Drag & drop of image files and folders anywhere in the window.
7. CLI file arguments (`main.py IMG ...`) add to queue and show the window.
8. Close request while a batch runs: cancel batch, toast "Batch cancelled", then close.

File input
9. Add-images dialog: multi-select, filter to the supported image extensions
   (from `core`/`utils` `IMAGE_EXTENSIONS`).
10. Add-folder dialog: recursive scan, hidden files/dirs skipped (existing
    `scan_folder` logic, reused).
11. Dedup by resolved path; non-image files counted and reported via skip toast.
12. Per-file header probe → meta line `W×H · FORMAT · size` (+ "· N frames" for
    multi-frame); probe failures degrade to size-only meta.
13. Async thumbnails (thread pool, off main thread; EXIF-transposed display only;
    missing-image placeholder icon on failure).

Queue
14. Empty state: icon + "No images yet" + description + **Add Images** button,
    visible only when the queue is empty.
15. Scrollable queue rows: 48 px thumbnail, ellipsized filename, dim meta line,
    status area: spinner (processing) / ok icon (done) / error icon + tooltip
    (error) / "Queued" or "Cancelled" label.

Bottom controls (3 rows)
16. Output row: aspect combo (5:4 / 19:16 / **Custom** with revealed A:B spin
    pairs, 1–999), **Landscape/Portrait** toggle (label flips), **Short edge**
    spin (16–8192), live **Result: W × H** label recomputed via
    `core.framing.target_canvas` on every control change.
17. Frame row: "Frame thickness" title + subtitle; slider + numeric entry sharing
    one value (0.00–20.00, step 0.01, 2 decimals); **Start Framing** (accent,
    play icon) and **Cancel** (stop icon) buttons.
18. Progress row: spinner (visible while running), status label
    ("N of M — current file"), progress bar with percent text.

Behavior
19. `OutputSpec` snapshotted at job start; all output/frame controls insensitive
    while a batch runs; Cancel enabled only while running; Clear/Clear-finished
    disabled while running; Start disabled with empty queue.
20. Batch semantics (from reused `BatchJob`): per-item error isolation,
    cancel-after-current-file, `job-finished(total, done, failed, cancelled)`
    summary toast, per-item warning toasts.
21. Clear all / Clear finished queue actions (with empty-state re-show).

Settings & dialogs
22. Persistence of: output-directory, suffix, frame-percent, aspect-preset,
    aspect-num, aspect-den, orientation-portrait, short-edge — same keys and
    defaults as today (GSettings → **QSettings**, INI in
    `~/.config/com.funkyskywalker/Framer/`).
23. Settings dialog (modal): Output group — output directory row (current path or
    "Next to source images" subtitle + "Choose…" folder picker) and suffix text entry.
24. About dialog: app name, version, developer, MIT license, icon.

Cross-platform appearance (new requirement, beyond GTK parity)
25. Follows the system style, palette, font, and icon theme — no hardcoded colors,
    no font overrides: Ubuntu GNOME (Yaru light/dark via the bundled gtk3 platform
    theme), KDE Plasma (built-in Breeze palette, light + dark), Windows 11 (native
    Fluent style, automatic light/dark via `appsUseDarkMode`, system accent color),
    anything else (clean Fusion + light/dark). App-specific elements (toasts, dim
    labels, accent Start button, row hover) stay consistent and palette-derived in
    every scheme/OS, and react to a live light↔dark system switch without restart.

**Out of scope:** changes to `framer/core` framing/image behavior; new features
(per-item retry, thumbnails of framed output, i18n); dist packaging (deb/AppImage);
migrating existing GSettings values into QSettings (documented, not migrated);
keeping the GTK app alive after cutover; an in-app theme/appearance switcher
(auto-follow + `FRAMER_COLOR_SCHEME` env override only — revisit if requested).

---

### Phase 1: Environment + scaffolding

Set up the Qt toolchain in isolation and prove an offscreen PySide6 app runs on this
machine (no display: `XDG_SESSION_TYPE=tty`, so all verification uses
`QT_QPA_PLATFORM=offscreen` + `QWidget.grab()` screenshots).

**Steps:**
1. Create a dedicated venv (python-venv skill): `python3 -m venv .venv-qt`, then
   `.venv-qt/bin/pip install PySide6 Pillow`. Confirm `PySide6.__version__`.
2. **Dev-VM EGL shim (this machine only — no display, no libEGL, no root).**
   Qt 6's QtGui import fails on this dev VM with `libEGL.so.1: cannot open shared
   object file`. Verified workaround: copy the Electron-bundled `libEGL.so` as a
   `.so.1` shim and put it on `LD_LIBRARY_PATH` for every offscreen run:
   `mkdir -p .agent/feature-migration-qt/qtlibs && cp
   ~/.hermes/hermes-agent/node_modules/electron/dist/libEGL.so
   .agent/feature-migration-qt/qtlibs/libEGL.so.1`. A real desktop (Ubuntu 26.04)
   has libegl1 and needs no shim. (Verified 2026-09-08: with the shim, Qt 6.11.2
   starts offscreen, default style `fusion`.)
3. Add `framer/qt/` package (`__init__.py`) and `framer/qt/app.py` with a minimal
   `FramerQtApp(QObject)` holding `QApplication` setup (app/org name
   `com.funkyskywalker` / `Framer` for QSettings) and an empty `QMainWindow`
   ("Framer", default/min sizes per inventory item 1).
4. New entry `main_qt.py` (parallel to `main.py`): creates the app, optionally
   passes CLI file args to the window (stub `add_paths` for now), runs the loop.
5. Add `scripts/shot.py`: tiny offscreen helper that sets
   `QT_QPA_PLATFORM=offscreen` + the dev-VM `LD_LIBRARY_PATH` shim itself, imports
   a given widget class, builds it, and saves `widget.grab()` to a PNG under
   `.agent/feature-migration-qt/screenshots/` (used by every later phase; the main
   agent must look at each screenshot before claiming visual state).
6. Update `.gitignore` for `.venv-qt/`.

**Files:**
- `framer/qt/__init__.py`, `framer/qt/app.py`, `main_qt.py`, `scripts/shot.py`,
  `.gitignore`

**Verification:**
- `QT_QPA_PLATFORM=offscreen LD_LIBRARY_PATH=.agent/feature-migration-qt/qtlibs
  .venv-qt/bin/python -c "import framer.qt.app; print('ok')"` (on a real desktop,
  drop the `LD_LIBRARY_PATH` part).
- Same env: `main_qt.py` starts, window constructs, scripted `quit()` after 1 s
  exits with code 0.
- Screenshot of the empty window captured via `scripts/shot.py` and **looked at**.

---

### Phase 2: Qt event plumbing (bus, dispatcher, thumbnails)

The thread-safe event layer — direct analog of `workers/dispatcher.py` +
`workers/signals.py`, with `BatchJob` reused untouched.

**Steps:**
1. `framer/qt/bus.py`: `SignalBus(QObject)` with Qt signals:
   `item_started(int)`, `item_progress(int, float)`, `item_finished(int, bool, str)`,
   `job_finished(int, int, int, int)`, `thumbnail(QueueItem, object)`
   (object = `QPixmap | None`). This replaces the GObject `SignalBus`.
2. `framer/qt/dispatcher.py`: `Dispatcher` owning the bus, an `attach(Queue)` API,
   a `QTimer` (60 ms) tick draining attached queues + its own thumbnail queue
   (same `MAX_EVENTS_PER_TICK` cap), emitting bus signals / calling the registered
   thumbnail provider. `start()/stop()` manage the timer.
3. `framer/qt/thumbnails.py`: pure function `make_thumbnail_png(path, pixel_size)`
   → PNG `bytes | None` (same logic as today's `utils/thumbnails.py`: PIL open,
   `exif_transpose` for display only, seek(0), LANCZOS thumbnail, flatten RGBA to
   white). Runs on a `ThreadPoolExecutor`; the **QPixmap is created on the main
   thread** in the dispatcher tick (Qt object thread-affinity).
4. Confirm `framer/workers/batch_worker.py` needs no changes: `BatchJob` takes any
   bus object by reference but only pushes tuples to its queue. (If the `bus`
   parameter must be dropped, do it here and note it — nothing else may change.)
5. `ty check` on all new/changed files.

**Files:**
- `framer/qt/bus.py`, `framer/qt/dispatcher.py`, `framer/qt/thumbnails.py`

**Verification (offscreen script):**
- Synthetic fixtures: 2 plain JPEGs, 1 corrupt file (bad bytes with `.jpg` name),
  1 multi-frame GIF, 1 RGBA PNG with EXIF + ICC bytes.
- Run `BatchJob` through the new Dispatcher; assert: one `item_started` per item,
   final `job_finished(total=5, done=4, failed=1, cancelled=0)`, corrupt item got
   `item_finished(..., ok=False, error)` while the batch completed (error
   isolation), GIF item's done state carried frame warnings intact.
- Thumbnails: request all five; assert 4 non-null `QPixmap` (≥1×1) delivered via the
   bus on the main thread, corrupt file delivered `None`.
- Cancellation: start a 3-item batch, cancel after first item →
  `job_finished(3, 1, 0, 2)` (mid-encode file finishes, rest cancelled).

---

### Phase 3: Queue UI (empty state + rows)

`framer/qt/queue_row.py` + `framer/qt/queue_view.py` with API parity to the GTK
`QueueView`/`QueueRow` (same method names/signatures where sensible: `add_item`,
`update_item`, `set_row_thumbnail`, `set_row_meta`, `items()`, `clear`,
`clear_finished`, `set_running`, `set_progress`, `set_start_enabled`,
`set_result_label`, `rows` list).

**Steps:**
1. `framer/qt/widgets.py`: shared small widgets —
   `Spinner` (custom: `QPainter` arc + `QTimer` at ~100 ms; `set_spinning(bool)`),
   and a theme-aware icon helper `icon(name)` with resolution order
   `QIcon.fromTheme(name)` (Yaru on GNOME, Breeze on KDE, shell icons on Windows —
   Phase 7 activates the system icon theme) → `QStyle.standardIcon` → **bundled SVG
   fallback** built now (`framer/qt/icons/`: add, folder, open-menu, play, stop, ok,
   error, missing-image, generic-image) so the app renders headless/offscreen before
   theming lands.
2. `QueueRow(QWidget)`: HBox: thumbnail `QLabel` (48 px), name label (ellide end),
   dim meta label, status HBox (spinner / ok icon / error icon / "Queued" /
   "Cancelled" labels); `set_state(ItemState)` toggles them and sets the row
   tooltip to `item.error` on ERROR.
3. `QueueView(QWidget)`: vertical: empty-state widget (icon, "No images yet",
   description, "Add Images" accent button) ↔ scrollable list container
   (`QScrollArea` + `QWidget` + `QVBoxLayout`, no row selection/activation).
   Empty-state visibility toggles on queue content; list resets progress row and
   start-button state on `clear()`/`clear_finished()` exactly like the GTK view.

**Files:**
- `framer/qt/widgets.py`, `framer/qt/icons/`, `framer/qt/queue_row.py`,
  `framer/qt/queue_view.py`

**Verification:**
- Offscreen build script: create view → add 5 items (mixed probe data) → screenshot
  empty→full transition → drive one row through PROCESSING → DONE, one to ERROR
  (with tooltip text set), one CANCELLED → screenshot → **look at screenshots**.
- Assert empty-state hidden with items, visible after `clear()`; `items()` order
  preserved after `clear_finished()` with a mix of states.

---

### Phase 4: Bottom control bar (output / frame / progress rows)

`framer/qt/controls.py`: the 3-row bottom bar with exact widget/behavior parity
(inventory items 16–18).

**Steps:**
1. **Output row** (HBox): `QComboBox` (5:4 / 19:16 / Custom); a custom-reveal
   container (plain `QWidget` shown/hidden — Qt has no Revealer) holding two
   `QSpinBox` (1–999) with a ":" label, visible only when Custom is selected;
   orientation `QToolButton`/`QPushButton` (checkable, label toggles
   "Landscape"↔"Portrait"); "Short edge" `QSpinBox` (16–8192, default 1080);
   dim `Result: W × H` label — recomputed on every change via
   `framer.core.framing.target_canvas` (geometry law: no hardcoded ratios).
2. **Frame row** (HBox): title "Frame thickness" + subtitle
   "White frame on each side, % of the image edge"; one value bound to **both** a
   `QSlider` (int 0–2000, /100) and a `QDoubleSpinBox` (0.00–20.00, step 0.01,
   2 decimals) with change-guards; "%" label; **Start Framing** button (accent
   style + play icon, initially disabled); **Cancel** button (stop icon, disabled).
3. **Progress row** (HBox): `Spinner` (hidden until running), h-expanding status
   label ("N of M — filename"), `QProgressBar` (0–100, percent text).
4. Expose the same binding hooks the window needs: value getters, change signals,
   `set_running(bool)` (insensitize output/frame controls + start, enable cancel,
   show spinner), `set_progress(done, total, fraction, current_name)`,
   `set_start_enabled(bool)`.

**Files:**
- `framer/qt/controls.py` (+ icon additions from Phase 3 if needed)

**Verification:**
- Offscreen script: assert Result label shows `1350 × 1080` for 5:4/1080 landscape,
  `1080 × 1350` after orientation toggle, updates for 19:16, custom 4:3, and
  short-edge changes; slider↔spinbox stay in sync in both directions (set each,
  read the other).
- `set_running(True)` → all output/frame controls + Start disabled, Cancel enabled,
  spinner visible; `set_progress(1, 3, 0.4, "a.jpg")` → status text + bar ≈ 40 %.
- Screenshot of the full bar in both idle and running states — **looked at**.

---

### Phase 5: Window chrome (toolbar, menu, accelerators, dialogs, DnD, toasts)

`framer/qt/toasts.py` + `framer/qt/window.py` (the `QMainWindow` assembling
toolbar, menu, shortcuts, dialogs, DnD, and the content: queue view + controls).

**Steps:**
1. `framer/qt/toasts.py`: `ToastOverlay(QWidget)` overlaying the window content —
   stacked toasts at bottom-right, auto-hide timers (normal 3 s / high 5 s),
   visual distinction for high-priority (Error-role accent; colors formalized in
   Phase 7's palette-derived QSS). Public:
   `toast(message, priority, timeout)` plus convenience `success()` / `error()`
   matching the GTK helper names.
2. Toolbar: Add-images and Add-folder buttons (left), hamburger `QToolButton` with
   `QMenu` on the right: Clear finished, Clear all, separator, Settings…,
   About Framer, separator, Quit.
3. `QShortcut` accelerators: Ctrl+O, Ctrl+Shift+O, Ctrl+Return, Ctrl+Period,
   Ctrl+W — each mapped to the same handler functions as the menu/toolbar (a single
   `Handlers` dict, like the GTK `Actions` class; keep one code path).
4. File dialogs (Qt non-native `QFileDialog` for deterministic offscreen tests):
   Add Images → `getOpenFileNames` with a name filter built from
   `IMAGE_EXTENSIONS` (e.g. `Images (*.jpg *.jpeg *.png ...)`), multi-select;
   Add Folder → `getExistingDirectory`.
5. Drag & drop: `setAcceptDrops(True)`; `dropEvent` reads `event.mimeData().urls()`
   (filter to local files) → shared `add_paths()`.
6. **Shared `add_paths(paths)`** (parity with GTK `FramerWindow.add_paths`):
   dir → `scan_folder`, file → `is_image_file`, dedup by resolved path,
   `probe()` meta (size-only fallback), `view.add_item` + `set_row_meta`
   (+ "· N frames"), thumbnail request, "N images added" / "N files skipped"
   toasts, start-button re-enable.
7. About dialog: `QMessageBox.about` (name, version from `framer.__version__`,
   developer "funkyskywalker", MIT X11 license text, icon).
8. `closeEvent`: if batch running → `job.cancel()` + toast "Batch cancelled";
   `dispatcher.stop()`; accept the close.

**Files:**
- `framer/qt/toasts.py`, `framer/qt/window.py`

**Verification:**
- Offscreen: build window, call `add_paths` with a mixed list (2 images, 1 text
  file, 1 dir with images, 1 duplicate) → assert queue contents and toast texts
  ("3 images added", "1 file(s) skipped…").
- Menu/accelerator wiring test: invoke each action programmatically (clear,
  clear-finished, about shown/hidden, settings shown, quit) — no exceptions;
  QShortcut lookup returns all 5 shortcuts with correct keys.
- Screenshot: toolbar + open menu, a toast visible, empty→full state — **looked at**.

---

### Phase 6: Settings persistence, settings dialog, full batch wiring

`framer/qt/settings.py` + settings dialog + complete window behavior (inventory
items 19–24).

**Steps:**
1. `Settings(QObject)` over `QSettings` (INI, org `com.funkyskywalker`, app
   `Framer`): typed getters/setters for the 8 keys with the exact same defaults as
   the current GSettings fallback (`output-directory ""`, `suffix "_framed"`,
   `frame-percent 5.0`, `aspect-preset "5:4"`, `aspect-num 3`/`aspect-den 2`,
   `orientation-portrait False`, `short-edge 1080`). QSettings always works, so no
   GSettings-style probe/fallback is needed.
2. Settings dialog (modal `QDialog`): "Output" group — output-directory row
   (current path or "Next to source images" + "Choose…" →
   `getExistingDirectory`, updates subtitle immediately) and suffix
   `QLineEdit` → `settings.set_string("suffix", …)` on change.
3. Window wiring (mirror `FramerWindow` exactly):
   - at startup: settings → controls (with a `_settings_guard` flag so initial
     sets don't re-write settings), sync custom reveal + orientation label,
     initial Result label;
   - on control change: write settings + live Result refresh (aspect, custom A:B,
     orientation, short edge, frame percent — same handlers, same round-to-2 for
     frame percent);
   - **Start**: snapshot `OutputSpec` from current controls (clamped in core),
     create `BatchJob(view.items(), bus, suffix, output_dir, spec)`,
     `dispatcher.attach(job.event_queue)`, start job, `view.set_running(True)`,
     enable Cancel / disable Clear;
   - event handlers: `item_started` / `item_progress` / `item_finished`
     (progress fraction math identical to GTK: done/total and (done+frac)/total;
     warning toasts per done item; error toast per failed item) /
     `job_finished` (running off, cancel off, clear on, summary toast with
     success vs error styling);
   - thumbnail provider: `bus.thumbnail` → `view.set_row_thumbnail`.
4. `ty check` on all changed files.

**Files:**
- `framer/qt/settings.py`, `framer/qt/window.py`, `framer/qt/dialogs.py`
  (settings + about can live here or in window — either, keep small)

**Verification (offscreen end-to-end script):**
- Temp HOME (so QSettings is sandboxed) + fixture images with EXIF + ICC bytes.
- Launch app headless, add 3 images, change settings (suffix "x", frame 7.5,
  custom 4:3, portrait, short edge 720), start → wait for `job_finished(3, 3, 0, 0)`
  → assert: outputs exist as `<stem>x.<ext>` with portrait 4:3 720-short-edge
  dimensions (e.g. 720 × 960 for a 3:2 landscape source framed), EXIF + ICC bytes
  **byte-identical** to source in each output, no-cropping invariant visible in
  pixels (white margins present).
- Restart the app (same temp HOME): assert all 8 settings restored into controls.
- Cancel path: 3-image batch, cancel after first → `job_finished(3, 1, 0, 2)` +
  "Batch finished: …" error-style toast.
- Screenshot final state (completed batch: ok icons, full bar, summary toast) —
  **looked at**.

---

### Phase 7: Theming — cross-DE/OS appearance

Make the app look native on Ubuntu 26.04 GNOME (Yaru, light + dark), KDE Plasma
(Breeze), and Windows 11 (Fluent, light + dark), and stay clean on other DEs.
Rule: **follow the system** (style, palette, font, icon theme); add only a minimal,
palette-derived QSS layer for app-specific elements. No hardcoded colors, no font
overrides.

**Verified facts (2026-09-08, PySide6 6.11.2 on this dev VM):**
- PySide6 bundles platform-theme plugins `libqgtk3.so` + `libqxdgdesktopportal.so`
  — **no `kde` plugin** (checked `PySide6/Qt/plugins/platformthemes/`). Fusion and
  `Windows` styles are built into QtWidgets; the native `windows11` style is
  Windows-only (built into Qt's Windows binaries, auto-selected on Win11; Win10
  falls back to the Vista style, which by Qt design is always light).
- The gtk3 platform theme needs a display (aborts "cannot open display" even under
  the offscreen platform) → native GNOME/KDE/Windows rendering is **verified on
  real machines only**; every offscreen check here uses Fusion + explicit palettes.
- Qt ≥ 6.5: `QStyleHints.colorScheme` + `colorSchemeChanged`; the gtk3 theme reads
  the GNOME color-scheme (auto light/dark on GNOME); on Windows Qt reads the dark
  scheme from the registry (`appsUseDarkMode`) and uses the system accent color for
  `QPalette::Highlight`.

**Steps:**
1. `framer/qt/theme.py` — `apply_theme(app)`, called from `framer/qt/app.py` before
   any window is built. Explicit per-platform decision (do not rely on Qt's implicit
   theme auto-selection):
   - env override first: `FRAMER_COLOR_SCHEME=light|dark` forces the palette (also
     the offscreen test hook); unset = follow the system;
   - **Windows**: set no style, no palette — native `windows11`/`Windows` style,
     system palette, and dark-mode following are all automatic; make Start Framing
     the main window's **default button** so the native style paints it with the
     system accent;
   - **GNOME** (`XDG_CURRENT_DESKTOP` contains "GNOME"): set
     `os.environ["QT_QPA_PLATFORMTHEME"] = "gtk3"` *before* `QApplication` exists —
     the bundled plugin then delivers the Yaru palette, font, icon theme, and
     light/dark;
   - **Plasma** (contains "KDE"/"Plasma"): no native plugin available → `Fusion` +
     built-in **Breeze palette** (light and dark variants as a small documented
     color table, e.g. base `#eff0f1`/`#31363b`, highlight `#3daee9`); scheme from
     `QStyleHints.colorScheme` when known, else light (best-effort; the env
     override is the escape hatch);
   - **otherwise**: `Fusion` + system palette (light default).
2. QSS layer (in `theme.py`): `app.setStyleSheet(build_qss(app.palette()))` — every
   color computed from the live palette (no hex literals outside the Breeze table):
   - toasts: normal (Window bg / Text) vs high-priority (Error-role border/icon),
     rounded corners;
   - dim labels: Text color at ~55 % alpha;
   - queue rows: hover tint (Button at ~12 % alpha), no selection highlight;
   - accent button (`.suggested`, Start Framing + empty-state Add Images):
     background Highlight / text HighlightedText — **Linux only**; skip on Windows
     (the native default-button accent covers it; QSS would break the Fluent look);
   - re-apply the QSS on `QStyleHints.colorSchemeChanged` (live light↔dark switch
     without restart).
3. Window icon: `QIcon.fromTheme("image-x-generic")` with the bundled fallback;
   the Phase 3 icon helper already resolves theme → standard → bundled, so this is
   just the wiring (drop to bundled SVG where `fromTheme` returns a null icon).
4. Fonts: never overridden (OS/platform theme supplies them); assert no `font`
   rules in the QSS.
5. Offscreen harness `scripts/theme_report.py`: build the full window (queue with
   items, one processing row, a toast, running state) under five variants —
   (a) light, (b) dark, (c) Breeze light, (d) Breeze dark, (e) Windows-like light
   palette — each Fusion + explicit palette; `grab()` → one PNG per variant under
   `.agent/feature-migration-qt/screenshots/theme/`.
6. **Real-machine pass** (this is a dev VM — no display; run on user machines,
   `scripts/theme_report.py` works standalone and writes a PNG set per OS/scheme):
   Ubuntu 26.04 GNOME (Yaru light + Yaru-dark, gtk3 theme active), Windows 11
   (light + dark, native Fluent), Plasma if available. Screenshot sets are reviewed
   before cutover; iterate on the QSS until they look right.

**Files:**
- `framer/qt/theme.py`, `framer/qt/app.py` (apply hook), `framer/qt/window.py`
  (default button, QSS object names), `scripts/theme_report.py`

**Verification:**
- Offscreen: all five variants render; **every screenshot looked at**; assertions —
  Window color differs between light/dark variants, Start button background ==
  palette Highlight in the Linux variants, QSS re-applies on a simulated
  `colorSchemeChanged` without exceptions.
- `grep -nE "#[0-9a-fA-F]{6}" framer/qt/theme.py` → color literals only inside the
  Breeze palette table.
- Real-machine sets (at minimum GNOME light + dark and Windows 11 light + dark)
  reviewed before Phase 8 starts.

---

### Phase 8: Cutover, GTK removal, docs

After Phases 1–6 verify clean: make the Qt app *the* app.

**Steps:**
1. Flip entry: `main.py` runs the Qt app (delete GTK `gi` import block; keep CLI
   args forwarding). Update `framer/__main__.py` likewise.
2. Delete GTK-only modules: `framer/app.py`, `framer/window.py`, `framer/ui/`,
   `framer/views/`, `framer/utils/thumbnails.py`, `framer/workers/signals.py`,
   `framer/workers/dispatcher.py`, `data/*.gschema.xml`. Keep
   `framer/workers/batch_worker.py` (reused) and everything in `framer/core/`.
3. `requirements.txt` + `pyproject.toml`: `PySide6>=6.8` (replace the PyGObject
   comment); description: "Qt 6 (PySide6) desktop app…". `.desktop`: new Exec path,
   keep MimeType list. `README.md`: rewrite Running/Prerequisites/Settings sections
   (venv + PySide6; QSettings location instead of GSchema install steps).
4. `AGENTS.md`: update File map (Qt layout), Layering law (core stays pure —
   never import PySide6/shiboken; all Qt on main thread; `workers/` + `framer/qt/`
   are the thread boundary), replace the "API notes (GTK 4.22…)" section with the
   Qt pitfalls learned during the migration, keep Geometry law and
   do-not-break list unchanged.
5. Final regression: run the repo's existing headless math checks
   (target_canvas vectors, frame_geometry sweeps, content_fit no-cropping,
   `frame_image` EXIF/ICC byte-identity, corner white, GIF frame count/durations)
   — they must pass untouched, proving core reuse.
6. `ty check` across the tree; remove anything now unused.

**Files:**
- `main.py`, `framer/__main__.py`, deletions above, `requirements.txt`,
  `pyproject.toml`, `data/*.desktop`, `README.md`, `AGENTS.md`

**Verification:**
- `QT_QPA_PLATFORM=offscreen .venv-qt/bin/python main.py` launches; on a real
  desktop `python3 .venv-qt/bin/python main.py IMG...` (or system install) works.
- **Full parity walkthrough against the Feature inventory list** (items 1–25),
  one screenshot batch per area: empty state, populated queue + thumbnails,
  running batch (spinner/progress/status), completed batch + summary toast,
  settings dialog, about dialog, open menu, cancel mid-batch — every screenshot
  **looked at** by the main agent. This pass doubles as the theming regression
  check (Phase 7): same shots must look native on each real machine.
- `grep -rln "PySide6\|shiboken\|gi.repository" framer/core/` → no hits;
  `grep -rln "gi.repository" framer/ main.py` → no hits (GTK fully gone).
- Commit the tree; progress doc gets its `## Summary`.

---

## Risks / Open questions

- **PySide6 vs PyQt6**: plan assumes PySide6 (LGPL, single install path,
  `QApplication.setOrganizationName/ApplicationName` conventions). If the user
  wants PyQt6, only Phase 1 changes (import names differ; `pyqtSignal` vs
  `Signal`). **Decide before Phase 1 executes.**
- **Dev VM limitations** (no display, no libEGL, no root): all automated
  verification is `QT_QPA_PLATFORM=offscreen` with the Phase 1 `LD_LIBRARY_PATH`
  EGL shim; `QWidget.grab()` proves layout but **native** look (gtk3/Yaru, Fluent,
  Breeze, real fonts, native file dialogs) can only be confirmed on real machines —
  the Phase 7 real-machine pass is a hard gate before cutover, and screenshot sets
  come from the user's Ubuntu + Windows machines.
- **Qt has no built-in spinner or toast**: custom `Spinner` (QPainter arc +
  QTimer) and `ToastOverlay` (QFrame stack + QTimer auto-hide) must be written
  from scratch — small, isolated, but real new code.
- **Icons**: `QIcon.fromTheme` only works where a system icon theme is reachable
  (GNOME/KDE via the gtk3 theme, Windows shell icons); the bundled SVG fallback
  keeps offscreen/unknown-DE rendering intact. Icon visuals will *not* be pixel
  identical to the GTK app — parity is functional, not cosmetic.
- **KDE**: PySide6 bundles no `kde` platform-theme plugin → Plasma gets the built-in
  Breeze palette on Fusion; dark-mode detection is best-effort
  (`QStyleHints.colorScheme` + `FRAMER_COLOR_SCHEME` override). Acceptable: the
  look is Breeze-accurate in color, though not the exact Kvantum/KDE shape.
- **Windows**: Win11 gets the native Fluent style + automatic dark mode + system
  accent (Qt 6.5+ behavior, nothing to build); **Win10 stays light** (the Vista
  style forces the light palette by Qt design) — documented, not fixable without
  a third-party Fluent style. Windows verification needs a real Windows machine.
- **Live theme switching**: QSS re-application on `colorSchemeChanged` covers
  palette-level switches; a switch that also changes the *style* (e.g. gtk3 vs
  none) requires an app restart — out of scope.
- **Settings backend change**: GSettings → QSettings means existing users'
  GSettings values are *not* migrated (documented in README; acceptable —
  values are trivial to re-enter). Key names are preserved for continuity.
- **`QFileDialog` native vs Qt style**: plan uses Qt's non-native dialog for
  deterministic offscreen testing; on a desktop the native dialog is preferable
  (`QFileDialog.DontUseNativeDialog` flag is one line — decide at Phase 5).
- **Python 3.14**: verified PySide6 6.11.2 `abi3` wheel installs in a venv
  (checked 2026-09-08). If a future PySide6 drops abi3, fall back to a 3.13
  venv.
- **Widget-tree performance** for very long queues (hundreds of rows): the GTK
  ListBox virtualizes; a plain `QVBoxLayout` of row widgets does not. If a queue
  exceeds ~a few hundred rows, swap the container for a `QListView` with a custom
  model (note for Phase 3, not a blocker — current app has no row limit either).
