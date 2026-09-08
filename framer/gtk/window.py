"""Main application window: layout, file input, settings binding, jobs."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import gi

gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gdk, Gtk

from .. import __version__
from ..core import framing
from ..core.image_io import probe
from ..core.models import ItemState, OutputSpec, QueueItem
from ..core.scanner import scan_folder
from .ui.actions import Actions
from .ui.toast import error_overlay, success_overlay, toast
from ..utils.paths import IMAGE_EXTENSIONS, format_meta, is_image_file
from .views.queue_view import QueueView
from ..workers.batch_worker import BatchJob
from .dispatcher import Dispatcher

ASPECT_PRESETS = ("5:4", "19:16", "custom")
PRESET_VALUES = {"5:4": (5, 4), "19:16": (19, 16)}


class FramerWindow(Adw.ApplicationWindow):
    """The single application window: header, queue, controls, toasts."""

    def __init__(self, app) -> None:
        super().__init__(application=app)
        self.app = app
        self.settings = app.get_settings()
        self.dispatcher = Dispatcher()
        self.job: Optional[BatchJob] = None
        self._seen: set[Path] = set()
        self._done_count = 0
        self._settings_guard = False
        self._about_window = None
        self._settings_window = None
        self._settings_dir_row = None

        self.set_title("Framer")
        self.set_icon_name("image-x-generic")
        self.set_default_size(1100, 760)
        self.set_size_request(980, 480)

        self.overlay = Adw.ToastOverlay()
        self.set_content(self.overlay)
        self.overlay.set_child(self._build_toolbar_view())

        # dispatcher + signal wiring (all GTK updates land here, main thread)
        self.dispatcher.start()
        bus = self.dispatcher.bus
        bus.connect("item-started", self._on_item_started)
        bus.connect("item-progress", self._on_item_progress)
        bus.connect("item-finished", self._on_item_finished)
        bus.connect("job-finished", self._on_job_finished)
        self.dispatcher.add_thumbnail_provider(self._on_thumbnail)

        # settings → controls (initial values)
        self._settings_guard = True
        self._set_aspect_combo(self.settings.get_string("aspect-preset"))
        self.view.aspect_num_spin.set_value(
            float(self.settings.get_int("aspect-num"))
        )
        self.view.aspect_den_spin.set_value(
            float(self.settings.get_int("aspect-den"))
        )
        self.view.orientation_button.set_active(
            self.settings.get_boolean("orientation-portrait")
        )
        self._sync_orientation_label()
        self.view.short_edge_spin.set_value(float(self.settings.get_int("short-edge")))
        self.view.frame_adjustment.set_value(
            self.settings.get_double("frame-percent")
        )
        self._settings_guard = False

        # control changes → settings + live canvas preview
        self.view.aspect_combo.connect(
            "notify::selected", lambda _w: self._on_aspect_changed()
        )
        self.view.aspect_num_spin.connect(
            "value-changed", self._on_custom_aspect_changed
        )
        self.view.aspect_den_spin.connect(
            "value-changed", self._on_custom_aspect_changed
        )
        self.view.orientation_button.connect("toggled", self._on_orientation_changed)
        self.view.short_edge_spin.connect(
            "value-changed", self._on_short_edge_changed
        )
        self.view.frame_adjustment.connect(
            "value-changed", self._on_frame_changed
        )
        # "clicked" passes the button; the action path calls cb() bare —
        # wrap so both land on the zero-arg handlers.
        self.view.start_button.connect("clicked", lambda _b: self._on_start())
        self.view.cancel_button.connect(
            "clicked", lambda _b: self._on_cancel()
        )
        self._sync_custom_revealer()
        self._refresh_output()

        # drag & drop (GTK 4.22: DropController + FileList, no set_drag_dest)
        drop = Gtk.DropTarget.new(Gdk.FileList.__gtype__, Gdk.DragAction.COPY)
        drop.connect("drop", self._on_drop)
        self.add_controller(drop)

        # actions, menu, accelerators
        self.actions = Actions()
        hamburger = self.actions.install(
            self,
            {
                "add-files": self._on_add_files,
                "add-folder": self._on_add_folder,
                "start": self._on_start,
                "cancel": self._on_cancel,
                "clear": self._on_clear,
                "clear-finished": self._on_clear_finished,
                "about": self._on_about,
                "settings": self._on_settings,
                "close": self.close,
            },
        )
        self.header.pack_end(hamburger)
        self.actions.set_clear_enabled(True)

        self.connect("close-request", self._on_close_request)

    # -- layout ---------------------------------------------------------------

    def _build_toolbar_view(self) -> Adw.ToolbarView:
        tv = Adw.ToolbarView()
        self.header = Adw.HeaderBar()

        add_btn = Gtk.Button.new_from_icon_name("list-add-symbolic")
        add_btn.set_action_name("win.add-files")
        add_btn.set_tooltip_text("Add images (Ctrl+O)")
        self.header.pack_start(add_btn)

        folder_btn = Gtk.Button.new_from_icon_name("folder-symbolic")
        folder_btn.set_action_name("win.add-folder")
        folder_btn.set_tooltip_text("Add a folder (Ctrl+Shift+O)")
        self.header.pack_start(folder_btn)

        title = Adw.WindowTitle(title="Framer")
        self.header.set_title_widget(title)
        tv.add_top_bar(self.header)

        self.view = QueueView()
        tv.set_content(self.view)
        return tv

    # -- file input --------------------------------------------------------------

    def _image_filter(self) -> Gtk.FileFilter:
        f = Gtk.FileFilter()
        f.set_name("Images")
        for ext in sorted(IMAGE_EXTENSIONS):
            f.add_suffix(ext.lstrip("."))
        return f

    def _on_add_files(self) -> None:
        chooser = Gtk.FileChooserNative.new(
            "Add Images", self, Gtk.FileChooserAction.OPEN, "_Add", "_Cancel"
        )
        chooser.set_select_multiple(True)
        chooser.add_filter(self._image_filter())
        chooser.connect("response", self._on_files_response)
        chooser.show()  # FileChooserNative: show(), no present()

    def _on_files_response(self, chooser, response) -> None:
        if response == Gtk.ResponseType.ACCEPT:
            self.add_paths(list(chooser.get_files()))
        chooser.destroy()

    def _on_add_folder(self) -> None:
        chooser = Gtk.FileChooserNative.new(
            "Add Folder",
            self,
            Gtk.FileChooserAction.SELECT_FOLDER,
            "_Select",
            "_Cancel",
        )
        chooser.connect("response", self._on_folder_response)
        chooser.show()  # FileChooserNative: show(), no present()

    def _on_folder_response(self, chooser, response) -> None:
        if response == Gtk.ResponseType.ACCEPT:
            folder = chooser.get_file()
            if folder is not None:
                self.add_paths([folder])
        chooser.destroy()

    def _on_drop(self, _controller, value, _x, _y) -> bool:
        try:
            file_list = value.get_boxed()
            files = file_list.get_files()
        except Exception:
            return False
        if not files:
            return False
        self.add_paths(list(files))
        return True

    def add_paths(self, files) -> None:
        """Shared add-path for dialogs, drag & drop, and CLI file arguments."""
        added = skipped = 0
        for gf in files:
            path_str = gf.get_path()
            if path_str is None:
                skipped += 1
                continue
            p = Path(path_str)
            if p.is_dir():
                candidates = scan_folder(p)
            elif p.is_file():
                candidates = [p] if is_image_file(p) else []
            else:
                candidates = []
            if p.is_file() and not candidates:
                skipped += 1
            for c in candidates:
                try:
                    rp = c.resolve()
                except OSError:
                    skipped += 1
                    continue
                if rp in self._seen:
                    skipped += 1
                    continue
                self._seen.add(rp)
                width = height = n_frames = None
                fmt: Optional[str] = None
                size: Optional[int] = None
                try:
                    width, height, fmt, n_frames, size = probe(c)
                except Exception:
                    try:
                        size = c.stat().st_size
                    except OSError:
                        size = None
                item = QueueItem(
                    path=c,
                    uri=c.as_uri(),
                    width=width,
                    height=height,
                    format=fmt,
                    size_bytes=size,
                )
                self.view.add_item(item)
                meta = format_meta(width, height, fmt, size)
                if n_frames and n_frames > 1:
                    meta += f" · {n_frames} frames"
                self.view.set_row_meta(len(self.view.rows) - 1, meta)
                if width is not None:
                    self.dispatcher.request_thumbnail(item, c)
                added += 1
        if added:
            toast(self.overlay, f"{added} image{'s' if added != 1 else ''} added")
        if skipped:
            toast(
                self.overlay,
                f"{skipped} file{'s' if skipped != 1 else ''} skipped "
                "(not a supported image or duplicate)",
                Adw.ToastPriority.NORMAL,
            )
        self._sync_start_enabled()

    # -- batch lifecycle -------------------------------------------------------------

    def _running(self) -> bool:
        return self.job is not None and self.job.is_running()

    def _sync_start_enabled(self) -> None:
        if self._running():
            self.actions.set_start_enabled(False)
            self.view.set_start_enabled(False)
        else:
            enabled = bool(self.view.rows)
            self.actions.set_start_enabled(enabled)
            self.view.set_start_enabled(enabled)

    def _current_aspect(self) -> tuple[int, int]:
        idx = self.view.aspect_combo.get_selected()
        if 0 <= idx < len(ASPECT_PRESETS) and ASPECT_PRESETS[idx] != "custom":
            return PRESET_VALUES[ASPECT_PRESETS[idx]]
        return (
            int(self.view.aspect_num_spin.get_value()),
            int(self.view.aspect_den_spin.get_value()),
        )

    def _on_start(self) -> None:
        if self._running() or not self.view.rows:
            return
        a, b = self._current_aspect()
        spec = OutputSpec(
            aspect_num=a,
            aspect_den=b,
            portrait=self.view.orientation_button.get_active(),
            short_edge=int(self.view.short_edge_spin.get_value()),
            frame_percent=float(self.view.frame_adjustment.get_value()),
        )
        self.job = BatchJob(
            items=self.view.items(),
            bus=self.dispatcher.bus,
            suffix=self.settings.get_string("suffix"),
            output_dir=self.settings.get_string("output-directory"),
            spec=spec,
        )
        self.dispatcher.attach(self.job.event_queue)
        self._done_count = 0
        self.job.start()
        self.view.set_running(True)
        self.actions.set_cancel_enabled(True)
        self.actions.set_clear_enabled(False)
        self._sync_start_enabled()

    def _on_cancel(self) -> None:
        if not self._running():
            return
        self.job.cancel()
        toast(self.overlay, "Cancelling after the current file…", Adw.ToastPriority.NORMAL)

    def _on_item_started(self, _bus, index: int) -> None:
        if index >= len(self.view.rows):
            return
        item = self.view.rows[index].item
        self.view.update_item(index, 0.0, ItemState.PROCESSING)
        total = len(self.view.rows)
        frac = self._done_count / total if total else 0.0
        self.view.set_progress(self._done_count, total, frac, item.path.name)

    def _on_item_progress(self, _bus, index: int, fraction: float) -> None:
        if index >= len(self.view.rows):
            return
        item = self.view.rows[index].item
        self.view.update_item(index, fraction, ItemState.PROCESSING)
        total = len(self.view.rows)
        frac = (self._done_count + fraction) / total if total else 0.0
        self.view.set_progress(self._done_count, total, frac, item.path.name)

    def _on_item_finished(self, _bus, index: int, ok: bool, error: str) -> None:
        if index >= len(self.view.rows):
            return
        row = self.view.rows[index]
        self.view.update_item(index, 1.0, row.item.state)
        if row.item.state is ItemState.DONE:
            self._done_count += 1
            for warning in row.item.warnings:
                toast(
                    self.overlay,
                    f"{row.item.path.name}: {warning}",
                    Adw.ToastPriority.NORMAL,
                    5.0,
                )
        elif row.item.state is ItemState.ERROR:
            error_overlay(
                self.overlay, f"{row.item.path.name}: {error or 'failed'}"
            )

    def _on_job_finished(
        self, _bus, total: int, done: int, failed: int, cancelled: int
    ) -> None:
        self._done_count = 0
        self.view.set_running(False)
        self.view.set_progress(total, total, 1.0)
        self.actions.set_cancel_enabled(False)
        self.actions.set_clear_enabled(True)
        self._sync_start_enabled()
        parts = [f"{done} framed"]
        if failed:
            parts.append(f"{failed} failed")
        if cancelled:
            parts.append(f"{cancelled} cancelled")
        if failed or cancelled:
            error_overlay(self.overlay, "Batch finished: " + ", ".join(parts))
        else:
            success_overlay(self.overlay, f"Batch finished — {total} image{'s' if total != 1 else ''} framed")

    # -- queue actions ------------------------------------------------------------------

    def _on_clear(self) -> None:
        if self._running():
            return
        self.view.clear()
        self._seen.clear()
        self._sync_start_enabled()

    def _on_clear_finished(self) -> None:
        if self._running():
            return
        self.view.clear_finished()
        self._sync_start_enabled()

    # -- settings ---------------------------------------------------------------------------

    def _set_aspect_combo(self, preset: str) -> None:
        idx = ASPECT_PRESETS.index(preset) if preset in ASPECT_PRESETS else 2
        self.view.aspect_combo.set_selected(idx)

    def _sync_custom_revealer(self) -> None:
        idx = self.view.aspect_combo.get_selected()
        self.view.custom_revealer.set_reveal_child(idx == 2)

    def _sync_orientation_label(self) -> None:
        self.view.orientation_button.set_label(
            "Portrait"
            if self.view.orientation_button.get_active()
            else "Landscape"
        )

    def _refresh_output(self) -> None:
        a, b = self._current_aspect()
        portrait = self.view.orientation_button.get_active()
        s = int(self.view.short_edge_spin.get_value())
        w, h = framing.target_canvas(a, b, portrait, s)
        self.view.set_result_label(w, h)

    def _on_aspect_changed(self) -> None:
        if self._settings_guard:
            return
        idx = self.view.aspect_combo.get_selected()
        preset = ASPECT_PRESETS[idx] if 0 <= idx < len(ASPECT_PRESETS) else "custom"
        self.settings.set_string("aspect-preset", preset)
        self._sync_custom_revealer()
        self._refresh_output()

    def _on_custom_aspect_changed(self, _spin) -> None:
        if self._settings_guard:
            return
        self.settings.set_int(
            "aspect-num", int(self.view.aspect_num_spin.get_value())
        )
        self.settings.set_int(
            "aspect-den", int(self.view.aspect_den_spin.get_value())
        )
        self._refresh_output()

    def _on_orientation_changed(self, _button) -> None:
        self._sync_orientation_label()
        if self._settings_guard:
            return
        self.settings.set_boolean(
            "orientation-portrait", self.view.orientation_button.get_active()
        )
        self._refresh_output()

    def _on_short_edge_changed(self, _spin) -> None:
        if self._settings_guard:
            return
        self.settings.set_int(
            "short-edge", int(self.view.short_edge_spin.get_value())
        )
        self._refresh_output()

    def _on_frame_changed(self, _adjustment) -> None:
        if self._settings_guard:
            return
        self.settings.set_double(
            "frame-percent",
            round(float(self.view.frame_adjustment.get_value()), 2),
        )

    def _on_thumbnail(self, item: QueueItem, texture) -> None:
        self.view.set_row_thumbnail(item, texture)

    # -- settings dialog -----------------------------------------------------------------------

    def _dir_subtitle(self) -> str:
        return self.settings.get_string("output-directory") or "Next to source images"

    def _on_settings(self) -> None:
        if self._settings_window is not None:
            self._settings_window.present()
            return
        win = Adw.PreferencesWindow()
        win.set_title("Settings")
        win.set_transient_for(self)
        win.set_modal(True)

        page = Adw.PreferencesPage()
        # add() is the only supported content API for PreferencesWindow in
        # Adw 1.9 (set_child aborts on AdwWindow); the deprecation warning
        # is expected and harmless on this stack.
        win.add(page)
        group = Adw.PreferencesGroup()
        group.set_title("Output")
        page.add(group)

        dir_row = Adw.ActionRow()
        dir_row.set_title("Output directory")
        dir_row.set_subtitle(self._dir_subtitle())
        choose = Gtk.Button(label="Choose…")
        choose.connect("clicked", lambda _b: self._choose_output_dir(dir_row))
        dir_row.add_suffix(choose)
        group.add(dir_row)
        self._settings_dir_row = dir_row

        suffix_row = Adw.EntryRow()
        suffix_row.set_title("Suffix")
        suffix_row.set_tooltip_text("Appended to the file name, before the extension")
        suffix_row.set_text(self.settings.get_string("suffix"))
        suffix_row.connect("changed", self._on_suffix_changed)
        group.add(suffix_row)

        win.connect(
            "close-request",
            lambda _w: (setattr(self, "_settings_window", None), False)[1],
        )
        self._settings_window = win
        win.present()

    def _choose_output_dir(self, dir_row) -> None:
        chooser = Gtk.FileChooserNative.new(
            "Choose Output Directory",
            self,
            Gtk.FileChooserAction.SELECT_FOLDER,
            "_Select",
            "_Cancel",
        )
        chooser.connect("response", lambda c, r: self._on_output_dir_response(c, r, dir_row))
        chooser.show()  # FileChooserNative: show(), no present()

    def _on_output_dir_response(self, chooser, response, dir_row) -> None:
        if response == Gtk.ResponseType.ACCEPT:
            folder = chooser.get_file()
            path = folder.get_path() if folder is not None else None
            self.settings.set_string("output-directory", path or "")
            dir_row.set_subtitle(self._dir_subtitle())
        chooser.destroy()

    def _on_suffix_changed(self, suffix_row) -> None:
        self.settings.set_string("suffix", suffix_row.get_text())

    # -- about / close -------------------------------------------------------------------------

    def _on_about(self) -> None:
        if self._about_window is not None:
            self._about_window.present()
            return
        about = Adw.AboutWindow()
        about.set_transient_for(self)
        about.set_modal(True)
        about.set_application_name("Framer")
        about.set_version(__version__)
        about.set_developer_name("funkyskywalker")
        about.set_license_type(Gtk.License.MIT_X11)
        about.set_icon_name("image-x-generic")
        about.present()
        self._about_window = about

    def _on_close_request(self, _window) -> None:
        if self._running():
            self.job.cancel()
            toast(self.overlay, "Batch cancelled", Adw.ToastPriority.NORMAL)
        self.dispatcher.stop()
        return False  # allow the close
