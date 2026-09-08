# Progress: Qt file picker — multi-select broken (Ctrl+click)

> Task: bugfix on `feature/migration-qt` (ad-hoc, no plan.md).
> Started: 2026-07-09T15:45:00+00:00

## Symptom (user report)

In the Qt app, the "Add Images" file picker: a plain click selects one
file and it can be added, but Ctrl+click cannot multi-select — nothing
can be selected with Ctrl, so multiple files can never be added.

## Root cause (verified)

Qt 6.11.2 `QFileDialog::getOpenFileNames` (the static call used by
`framer/qt/window.py::_on_add_files`) constructs the dialog via
`QFileDialog(const QFileDialogArgs&)` — `src/widgets/dialogs/qfiledialog.cpp`
on tag v6.11.2:

1. `QFileDialogPrivate::init()` sets
   `nativeDialogInUse = platformFileDialogHelper() != nullptr`.
   On a GNOME desktop our app sets `QT_QPA_PLATFORMTHEME=gtk3`
   (`framer/qt/theme.py`) and the bundled gtk3 platform-theme plugin
   (links `gtk_file_chooser_dialog_new` + `QPlatformDialogHelper`)
   provides a file-dialog helper → **native dialog "in use", no
   widgets created**.
2. `setFileMode(ExistingFiles)` (called from the ctor, right after
   `init`) early-returns because `!usingWidgets()` — the
   `listView->setSelectionMode(ExtendedSelection)` at
   qfiledialog.cpp:1710–1716 never runs.
3. `setOptions(DontUseNativeDialog)` then creates the widgets late
   (`createWidgets()`) — but `createWidgets()` does **not** apply the
   selection mode (only `setFileMode()` does).
4. Result: the file list stays at `QListView`'s default
   **SingleSelection** → plain click picks one file, Ctrl+click
   replaces instead of extending.

Why it never showed up in our verification: offscreen (and any desktop
without a platform file-dialog helper) has no native helper, so the
widgets are created inside `init()` *before* `setFileMode(ExistingFiles)`
→ ExtendedSelection. Verified empirically on this stack:
bare-dialog state = SingleSelection with Ctrl+click BROKEN; the
fixed ordering = ExtendedSelection with Ctrl+click WORKS
(`/tmp/mechanism_test.py` output in session notes).

Could not reproduce on the user's exact GNOME session from this headless
box (xcb needs libxcb-cursor0, not installed, no root); the mechanism is
pinned by the Qt source trace + same-state empirical repro above.

## Fix

`framer/qt/window.py::_on_add_files`: build the dialog by hand in the
order that survives both worlds — `setOption(DontUseNativeDialog)`
**first** (forces widget creation), then `setFileMode(ExistingFiles)`
(applies ExtendedSelection to the live view). `exec()` +
`selectedFiles()` replaces the static call.

## Verification plan

1. Regression section in `scripts/verify_window.py`: drive the real
   `window._on_add_files()` offscreen (timer finds the live dialog),
   assert the file-list view is `ExtendedSelection`, swap a stub model,
   simulate plain click + Ctrl+click, assert two files selected;
   reject. (Full GNOME repro stays pending on the user's machine.)
2. All six offscreen verify scripts + theme_report: ALL PASS.
3. `ty check` on `framer/qt/` + `scripts/`.
4. User-machine confirmation: Ctrl+click multi-select in the picker.

## Status

| # | Step | Status | Notes |
|---|------|--------|-------|
| 1 | Fix `_on_add_files` ordering | ✅ Done | dialog built by hand |
| 2 | Regression test in verify_window.py | ✅ Done | 4 new checks, all pass |
| 3 | Full verification suite + ty | ✅ Done | 6/6 scripts ALL PASS, ty clean |
| 4 | User-machine confirmation | ⬜ | pending: Ctrl+click in picker |

## Summary

- **Fix:** `framer/qt/window.py::_on_add_files` now builds the
  `QFileDialog` by hand — `setOption(DontUseNativeDialog)` **before**
  `setFileMode(ExistingFiles)` — so the `ExtendedSelection` assignment
  lands on the real (late-created) file-list view instead of being
  silently skipped by `setFileMode()`'s `!usingWidgets()` early return.
- **Regression test:** `scripts/verify_window.py` drives the real
  `_on_add_files()` offscreen, asserts `ExtendedSelection` on the live
  dialog's file list and that plain-click + Ctrl+click selects two files
  (stub model, since offscreen `QFileSystemModel` cannot load directory
  contents).
- **Verification:** all 6 offscreen scripts ALL PASS; `ty check` clean
  on `framer/qt/` + `scripts/`.
- **Follow-up:** user confirms multi-select on the desktop (GNOME /
  gtk3 theme); the exact bug path (native helper active) is unreachable
  from this headless box (xcb needs libxcb-cursor0, not installed).
