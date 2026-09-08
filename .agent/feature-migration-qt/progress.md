# Progress: Framer GTK → PySide6 Migration

> Plan: `.agent/feature-migration-qt/plan.md`
> Started: 2026-09-08T09:27:26+00:00
> Plan written: 2026-09-08 — branch `feature/migration-qt`, PySide6 chosen
> (PySide6 6.11.2 abi3 wheel verified installable under Python 3.14.4).
> Theming requirement added 2026-09-08 (GNOME/KDE/Windows appearance, 8 phases):
> PySide6 bundles `libqgtk3.so` but NO `kde` plugin (checked
> `PySide6/Qt/plugins/platformthemes/`); dev VM needs the `LD_LIBRARY_PATH` EGL
> shim; gtk3 theme needs a real display (offscreen verification = Fusion +
> explicit palettes; native look verified on user's real machines). Awaiting
> execution.

## Phase Status

| # | Phase | Status | Notes |
|---|-------|--------|-------|
| 1 | Environment + scaffolding | ✅ Done | venv + EGL shim + minimal app + shot.py verified offscreen |
| 2 | Qt event plumbing (bus, dispatcher, thumbnails) | ✅ Done | 18/18 offscreen checks pass; BatchJob `bus` hint decoupled |
| 3 | Queue UI (empty state + rows) | ✅ Done | 22/22 checks pass; both screenshots reviewed |
| 4 | Bottom control bar (output / frame / progress rows) | ✅ Done | 24/24 checks pass; idle + running screenshots reviewed |
| 5 | Window chrome: toolbar, menu, accelerators, dialogs, DnD, toasts | ✅ Done | 25/25 checks pass; 3 screenshots reviewed |
| 6 | Settings persistence, settings dialog, full wiring | ⬜ Pending | |
| 7 | Theming — cross-DE/OS appearance (GNOME/KDE/Windows) | ⬜ Pending | |
| 8 | Cutover, GTK removal, docs | ⬜ Pending | |

## Completed Phases

<!-- After each phase, append a summary block: -->

### ✅ Phase 1: Environment + scaffolding
- **Finished:** 2026-09-08T10:09:00+00:00
- **Commits:** `2cfd89a` — Phase 1: Qt env + scaffolding (venv, EGL shim, minimal app, shot.py)
- **Notes:** `.venv-qt` (Python 3.14.4, PySide6 6.11.2, Pillow) installed; Electron-bundled
  libEGL copied to `.agent/feature-migration-qt/qtlibs/libEGL.so.1` (dev-VM shim only).
  `framer/qt/app.py` (FramerQtApp + placeholder FramerWindow 1100×760/min 980×480,
  QSettings org/app `com.funkyskywalker`/`Framer`), `main_qt.py` (CLI arg forwarding,
  stub `add_paths`), `scripts/shot.py` (offscreen grab helper: sets QT_QPA_PLATFORM,
  re-execs itself to put the shim on LD_LIBRARY_PATH, writes PNG under
  `.agent/feature-migration-qt/screenshots/`). Verified: import ok, main loop quits
  with code 0 after 1 s timer, empty-window screenshot looked at (plain Fusion light
  background, 1100×760 — expected for the placeholder). `ty check --python
  .venv-qt/bin/python` clean on all new files. `.gitignore` now excludes `.venv-qt/`
  and the migration dev artifacts (shim, screenshots, install log).

### ✅ Phase 2: Qt event plumbing (bus, dispatcher, thumbnails)
- **Finished:** 2026-09-08T10:22:00+00:00
- **Commits:** `17da938` — Phase 2: Qt event plumbing (bus, dispatcher, thumbnails)
- **Notes:** `framer/qt/bus.py` (SignalBus: item_started/item_progress/item_finished/
  job_finished/thumbnail; `object` signal types for the thumbnail payload,
  documented), `framer/qt/dispatcher.py` (QObject + 60 ms QTimer tick,
  `attach(queue)`, MAX_EVENTS_PER_TICK=1000, thumbnail pool → PNG bytes →
  QPixmap created on the main thread in the tick; tick is now
  exception-safe per event), `framer/qt/thumbnails.py` (`make_thumbnail_png`
  → PNG bytes, same logic as the GTK util, PIL-only, thread-safe).
  **Deviations:** `framer/workers/batch_worker.py` lost its unused
  `from .signals import SignalBus` import and the `bus` parameter is now
  typed `object` (bus was never used; avoids a GTK import in the retained
  module — plan step 4 explicitly allowed this). `ty check` clean.
  Verification `scripts/verify_qt_plumbing.py` (committed): 18/18 pass —
  5-item batch (2 JPEG + corrupt + 3-frame GIF + RGBA PNG with EXIF/ICC):
  job_finished(5,4,1,0), per-item error isolation, GIF DONE, 4 real
  QPixmaps + None for the corrupt file delivered on the main thread;
  cancel run with a large middle JPEG → job_finished(3,1,0,2) deterministic.

### ⚠️ Infra note (2026-09-08T10:40)
- Subagent delegation failed twice with the same host bug: the
  `pi-telegram-plus` extension crashes the async runner process
  (`formatTelegramStatusLine` → theme getter before `initTheme()`), killing
  the child before it does any work. Per the stop-delegating rule, Phases 3+
  are executed inline by the main agent.

### ✅ Phase 3: Queue UI (empty state + rows)
- **Finished:** 2026-09-08T10:58:00+00:00
- **Commits:** `7d04f2a` — Phase 3: queue UI (widgets, icons, queue row/view)
- **Notes:** `framer/qt/widgets.py` (Spinner: 16 px QPainter arc, 100 ms
  timer, palette Highlight; `icon(name)`: system theme → QStyle standard →
  bundled SVG; `dim_label()` = palette Text @ alpha 140 + `dim` property for
  Phase 7 QSS), `framer/qt/icons/` (9 bundled mid-gray SVGs),
  `framer/qt/queue_row.py` (48 px thumb, ellipsizing name label via
  sizeHint override, dim meta, status: spinner/ok/error/Queued/Cancelled —
  exact GTK set_state parity incl. error tooltip),
  `framer/qt/queue_view.py` (empty state w/ icon+title+desc+AddImages
  button + `add_clicked` signal; QScrollArea + rows layout; queue API:
  add_item/update_item/set_row_thumbnail/set_row_meta/items/clear/
  clear_finished, finished = DONE/ERROR/CANCELLED).
  **Deviations:** `add_item` returns the row (GTK returned None).
  **Qt pitfalls found (keep for later phases):** (1) a child widget created
  while its parent is ALREADY visible starts hidden — only children created
  before the parent's show() inherit visibility; `add_item` now calls
  `row.show()` explicitly — Phase 5 toast widgets need the same treatment;
  (2) word-wrapped QLabel defaults to a tiny hint width — empty-state
  description needed Expanding size policy. Verification
  `scripts/verify_queue_ui.py`: 22/22 pass. ty clean. Both screenshots
  (phase3-empty, phase3-queue-mixed) reviewed by the main agent: empty state
  centered (icon/title/desc/button), rows show meta line, blue spinner arc,
  green ok check, red error icon, slashed-image placeholder, Queued/
  Cancelled labels.

### ✅ Phase 4: Bottom control bar (output / frame / progress rows)
- **Finished:** 2026-09-08T11:07:00+00:00
- **Commits:** `xxxxx` — Phase 4: bottom control bar (controls.py)
- **Notes:** `framer/qt/controls.py` (Controls: output row — aspect combo
  5:4/19:16/Custom + plain-widget "revealer" for the 1–999 A:B spin pair,
  Landscape/Portrait checkable toggle with label flip, short-edge spin
  16–8192, dim live `Result: W × H` label refreshed via
  `core.framing.target_canvas` on EVERY control change; frame row —
  title + subtitle, QSlider(0–2000)/100 ↔ QDoubleSpinBox(0.00–20.00, step
  0.01, 2 decimals) with change-guards, % label, Start Framing (play icon,
  objectName StartFramingButton, initially disabled) + Cancel (stop icon,
  disabled); progress row — Spinner, hexpanding dim status label, 160 px
  QProgressBar with percent text). Signals: aspect_changed,
  orientation_changed, short_edge_changed, frame_percent_changed; hooks:
  set_running/set_progress/set_start_enabled/set_result_label/output_spec.
  **Change from draft:** short-edge change refreshes the result label
  internally (plan item 16: recompute on every control change).
  Verification `scripts/verify_controls.py`: 24/24 pass, incl.
  1350 × 1080 (5:4/1080 landscape), 1080 × 1350 (portrait), 1283 × 1080
  (19:16), 1440 × 1080 (custom 4:3), 900 × 720 (short edge); bidirectional
  slider↔spin sync; full set_running/set_progress state. ty clean. Both
  screenshots (phase4-controls-idle, phase4-controls-running) reviewed by
  the main agent. **Process change (user request):** phase verification
  screenshots are now COMMITTED to git (un-ignored
  `.agent/feature-migration-qt/screenshots/`; the EGL shim + install log
  stay local); this commit includes the Phase 1 + 3 screenshots too.

### ✅ Phase 5: Window chrome (toolbar, menu, accelerators, dialogs, DnD, toasts)
- **Finished:** 2026-09-08T11:25:00+00:00
- **Commits:** `xxxxx` — Phase 5: window chrome (toasts, window, app wiring)
- **Notes:** `framer/qt/toasts.py` (ToastHost wraps the content, floats toasts
  bottom-right newest-last, 3 s normal / 5 s high auto-hide, high = 2 px
  error-red border — Qt 6.11 has NO QPalette.Error role (checked at
  runtime), semantic Qt.GlobalColor.red used instead; module helpers
  success()/error() match the GTK helper names; toast_history for tests),
  `framer/qt/window.py` (FramerWindow(QMainWindow): QToolBar with
  add-images/add-folder tool buttons + right-aligned hamburger QMenu
  [Clear finished · Clear all · – · Settings… · About Framer · – · Quit],
  single `_handlers` dict shared by toolbar/menu/QShortcuts; 5 shortcuts
  Ctrl+O, Ctrl+Shift+O, Ctrl+Return, Ctrl+Period, Ctrl+W; Qt non-native
  file dialogs with IMAGE_EXTENSIONS filter; dropEvent via
  mimeData().urls(); add_paths ported 1:1 (scan_folder, is_image_file,
  resolved-path dedup, probe fallback, "· N frames" meta, thumbnail
  requests, "N images added"/"N files skipped…" toasts, start re-enable);
  closeEvent cancels running job + toast + dispatcher.stop());
  `framer/qt/app.py` now builds the real FramerWindow (placeholder removed).
  Start/Cancel/Settings handlers are marked Phase 6 stubs (plan split).
  **Qt pitfalls found:** (1) `QKeySequence("Ctrl+Period")` parses EMPTY —
  the key-string form is `"Ctrl+."` (Ctrl+Key_Period); (2) build order:
  hamburger needs the menu before the toolbar is built. Verification
  `scripts/verify_window.py`: 25/25 pass (mixed add_paths incl. dir + dup +
  text file, synthesized QDropEvent, all handlers, shortcut key set
  exactly the plan's five, close). ty clean. Screenshots reviewed: empty
  window (toolbar + empty state + controls, Start disabled), full window
  (4 real thumbnails, meta lines, toast bottom-right), menu (exact GTK
  items).
