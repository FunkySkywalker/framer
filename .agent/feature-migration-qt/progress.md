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
| 3 | Queue UI (empty state + rows) | ⬜ Pending | |
| 4 | Bottom control bar (output / frame / progress rows) | ⬜ Pending | |
| 5 | Window chrome: toolbar, menu, accelerators, dialogs, DnD, toasts | ⬜ Pending | |
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
- **Commits:** `xxxxx` — Phase 2: Qt event plumbing (bus, dispatcher, thumbnails)
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
