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
| 1 | Environment + scaffolding | ⬜ Pending | |
| 2 | Qt event plumbing (bus, dispatcher, thumbnails) | ⬜ Pending | |
| 3 | Queue UI (empty state + rows) | ⬜ Pending | |
| 4 | Bottom control bar (output / frame / progress rows) | ⬜ Pending | |
| 5 | Window chrome: toolbar, menu, accelerators, dialogs, DnD, toasts | ⬜ Pending | |
| 6 | Settings persistence, settings dialog, full wiring | ⬜ Pending | |
| 7 | Theming — cross-DE/OS appearance (GNOME/KDE/Windows) | ⬜ Pending | |
| 8 | Cutover, GTK removal, docs | ⬜ Pending | |

## Completed Phases

<!-- After each phase, append a summary block: -->
<!-- ### ✅ Phase N: <Name> -->
<!-- - **Finished:** <ISO timestamp> -->
<!-- - **Commits:** `<short-hash>` — <message> -->
<!-- - **Notes:** -->
