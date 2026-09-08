"""Queue view: empty state, the ListBox of queue rows, and the 3-row
bottom control bar (output / frame / progress)."""
from __future__ import annotations

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk

from ...core.framing import (
    FRAME_PERCENT_DEFAULT,
    FRAME_PERCENT_MAX,
    FRAME_PERCENT_MIN,
    SHORT_EDGE_DEFAULT,
    SHORT_EDGE_MAX,
    SHORT_EDGE_MIN,
)
from ...core.models import ItemState, QueueItem
from .queue_row import QueueRow


class QueueView(Gtk.Box):
    """Vertical: empty state → queue list → bottom controls."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.rows: list[QueueRow] = []

        # (a) empty state --------------------------------------------------
        self.empty_state = Adw.StatusPage()
        self.empty_state.set_icon_name("image-x-generic")
        self.empty_state.set_title("No images yet")
        self.empty_state.set_description(
            "Add images with the buttons above, or drop image files or "
            "folders anywhere in this window."
        )
        add_btn = Gtk.Button(label="Add Images")
        add_btn.set_action_name("win.add-files")
        add_btn.add_css_class("suggested-action")
        self.empty_state.set_child(add_btn)
        self.append(self.empty_state)

        # (b) queue list ----------------------------------------------------
        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_vexpand(True)
        self.scroller.set_hexpand(True)
        self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.listbox.set_show_separators(True)
        self.scroller.set_child(self.listbox)
        self.append(self.scroller)

        # (c) bottom controls ------------------------------------------------
        controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        controls.set_margin_top(6)
        controls.set_margin_bottom(10)
        controls.set_margin_start(12)
        controls.set_margin_end(12)

        # -- output row --
        self.output_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8
        )
        label = Gtk.Label(label="Output")
        label.add_css_class("dim-label")
        self.output_row.append(label)

        self.aspect_combo = Gtk.DropDown.new_from_strings(["5:4", "19:16", "Custom"])
        self.output_row.append(self.aspect_combo)

        self.custom_revealer = Gtk.Revealer()
        custom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.aspect_num_spin = Gtk.SpinButton.new_with_range(1, 999, 1)
        self.aspect_den_spin = Gtk.SpinButton.new_with_range(1, 999, 1)
        colon = Gtk.Label(label=":")
        custom_box.append(self.aspect_num_spin)
        custom_box.append(colon)
        custom_box.append(self.aspect_den_spin)
        self.custom_revealer.set_child(custom_box)
        self.output_row.append(self.custom_revealer)

        self.orientation_button = Gtk.ToggleButton(label="Landscape")
        self.orientation_button.set_tooltip_text("Flip orientation")
        self.output_row.append(self.orientation_button)

        se_label = Gtk.Label(label="Short edge")
        se_label.add_css_class("dim-label")
        self.output_row.append(se_label)
        self.short_edge_spin = Gtk.SpinButton.new_with_range(
            SHORT_EDGE_MIN, SHORT_EDGE_MAX, 1
        )
        self.short_edge_spin.set_tooltip_text("Short edge in pixels")
        self.output_row.append(self.short_edge_spin)

        self.result_label = Gtk.Label(label="Result: …")
        self.result_label.add_css_class("dim-label")
        self.output_row.append(self.result_label)
        controls.append(self.output_row)

        # -- frame row --
        # NOTE: Adw.SpinRow in libadwaita 1.9 renders NO slider track
        # (it is a drag-to-scrub row + spin button), so this app builds the
        # slider explicitly: title + Gtk.Scale + SpinButton, one shared
        # adjustment (see self.frame_adjustment).
        self.frame_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.frame_adjustment = Gtk.Adjustment.new(
            FRAME_PERCENT_DEFAULT,
            FRAME_PERCENT_MIN,
            FRAME_PERCENT_MAX,
            0.01,
            0.1,
            0.0,
        )
        self.frame_spinrow = Adw.ActionRow()
        self.frame_spinrow.set_title("Frame thickness")
        self.frame_spinrow.set_subtitle(
            "White frame on each side, % of the image edge"
        )
        frame_children = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8
        )
        frame_children.set_valign(Gtk.Align.CENTER)
        self.frame_slider = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL,
            FRAME_PERCENT_MIN,
            FRAME_PERCENT_MAX,
            0.01,
        )
        self.frame_slider.set_adjustment(self.frame_adjustment)
        self.frame_slider.set_draw_value(False)
        self.frame_slider.set_hexpand(True)
        self.frame_slider.set_tooltip_text("Drag to set frame thickness")
        frame_children.append(self.frame_slider)
        self.frame_spin_button = Gtk.SpinButton.new_with_range(
            FRAME_PERCENT_MIN, FRAME_PERCENT_MAX, 0.01
        )
        self.frame_spin_button.set_adjustment(self.frame_adjustment)
        self.frame_spin_button.set_digits(2)
        self.frame_spin_button.set_tooltip_text("Frame thickness in percent")
        frame_children.append(self.frame_spin_button)
        pct = Gtk.Label(label="%")
        pct.add_css_class("dim-label")
        frame_children.append(pct)
        self.frame_spinrow.add_suffix(frame_children)
        self.frame_spinrow.set_hexpand(True)
        self.frame_row.append(self.frame_spinrow)

        start_content = Adw.ButtonContent()
        start_content.set_label("Start Framing")
        start_content.set_icon_name("media-playback-start-symbolic")
        self.start_button = Gtk.Button()
        self.start_button.set_child(start_content)
        self.start_button.add_css_class("suggested-action")
        self.start_button.set_sensitive(False)
        self.frame_row.append(self.start_button)

        cancel_content = Adw.ButtonContent()
        cancel_content.set_label("Cancel")
        cancel_content.set_icon_name("process-stop-symbolic")
        self.cancel_button = Gtk.Button()
        self.cancel_button.set_child(cancel_content)
        self.cancel_button.set_sensitive(False)
        self.frame_row.append(self.cancel_button)
        controls.append(self.frame_row)

        # -- progress row --
        self.progress_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=12
        )
        self.progress_spinner = Adw.Spinner()
        self.progress_spinner.spinning = False
        self.progress_spinner.set_visible(False)
        self.progress_row.append(self.progress_spinner)
        self.status_label = Gtk.Label(label="")
        self.status_label.set_hexpand(True)
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.add_css_class("dim-label")
        self.progress_row.append(self.status_label)
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        self.progress_bar.set_fraction(0.0)
        self.progress_row.append(self.progress_bar)
        controls.append(self.progress_row)

        self.append(controls)
        self._update_empty()

    # -- queue API -----------------------------------------------------------

    def add_item(self, item: QueueItem) -> None:
        row = QueueRow(item)
        self.listbox.append(row)
        self.rows.append(row)
        self._update_empty()

    def update_item(self, index: int, fraction: float, state: ItemState) -> None:
        if 0 <= index < len(self.rows):
            self.rows[index].set_state(state)

    def set_row_thumbnail(self, item: QueueItem, texture) -> None:
        for row in self.rows:
            if row.item is item:
                row.set_thumbnail(texture)
                return

    def set_row_meta(self, index: int, meta: str) -> None:
        if 0 <= index < len(self.rows):
            self.rows[index].set_meta(meta)

    def items(self) -> list[QueueItem]:
        return [row.item for row in self.rows]

    def clear(self) -> None:
        self.listbox.remove_all()
        self.rows.clear()
        self.progress_bar.set_fraction(0.0)
        self.status_label.set_text("")
        self.start_button.set_sensitive(False)
        self._update_empty()

    def clear_finished(self) -> None:
        finished = (ItemState.DONE, ItemState.ERROR, ItemState.CANCELLED)
        keep = [row for row in self.rows if row.item.state not in finished]
        self.listbox.remove_all()
        for row in keep:
            self.listbox.append(row)
        self.rows = keep
        if not self.rows:
            self.progress_bar.set_fraction(0.0)
            self.status_label.set_text("")
            self.start_button.set_sensitive(False)
        self._update_empty()

    # -- running state ---------------------------------------------------------

    def set_running(self, running: bool, current_label: str = "") -> None:
        for w in (
            self.aspect_combo,
            self.custom_revealer,
            self.orientation_button,
            self.short_edge_spin,
            self.frame_spinrow,
        ):
            w.set_sensitive(not running)
        self.start_button.set_sensitive(not running)
        self.cancel_button.set_sensitive(running)
        self.progress_spinner.set_visible(running)
        self.progress_spinner.spinning = running
        if not running:
            self.status_label.set_text(current_label)

    def set_progress(
        self, done: int, total: int, fraction: float, current_name: str | None = None
    ) -> None:
        self.progress_bar.set_fraction(max(0.0, min(1.0, fraction)))
        text = f"{done} of {total}" if total else ""
        if current_name:
            text = f"{text} — {current_name}" if text else current_name
        self.status_label.set_text(text)

    def set_start_enabled(self, enabled: bool) -> None:
        self.start_button.set_sensitive(enabled)

    # -- output canvas preview ---------------------------------------------------

    def set_result_label(self, w: int, h: int) -> None:
        self.result_label.set_text(f"Result: {w} × {h}")

    # -- getters for window binding -------------------------------------------------

    def get_aspect_combo(self) -> Gtk.DropDown:
        return self.aspect_combo

    def get_custom_revealer(self) -> Gtk.Revealer:
        return self.custom_revealer

    def get_orientation_button(self) -> Gtk.ToggleButton:
        return self.orientation_button

    def get_short_edge_spin(self) -> Gtk.SpinButton:
        return self.short_edge_spin

    def get_frame_row(self) -> Adw.ActionRow:
        return self.frame_spinrow

    # -- internals ---------------------------------------------------------------

    def _update_empty(self) -> None:
        has_items = bool(self.rows)
        self.empty_state.set_visible(not has_items)
        self.scroller.set_visible(has_items)
