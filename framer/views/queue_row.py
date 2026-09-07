"""Queue row: 48 px thumbnail, filename/meta, per-file status widget."""
from __future__ import annotations

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk, Pango

from ..core.models import ItemState, QueueItem


class QueueRow(Gtk.ListBoxRow):
    """One row of the queue list. Not selectable, not activatable."""

    def __init__(self, item: QueueItem) -> None:
        super().__init__()
        self.item = item
        self.set_selectable(False)
        self.set_activatable(False)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(12)
        box.set_margin_end(12)

        self.thumb = Gtk.Image()
        self.thumb.set_pixel_size(48)
        self.thumb.set_from_icon_name("image-missing-symbolic")
        box.append(self.thumb)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text.set_hexpand(True)
        self.name_label = Gtk.Label(label=item.path.name)
        self.name_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.name_label.set_halign(Gtk.Align.START)
        self.meta_label = Gtk.Label(label="")
        self.meta_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.meta_label.set_halign(Gtk.Align.START)
        self.meta_label.add_css_class("dim-label")
        text.append(self.name_label)
        text.append(self.meta_label)
        box.append(text)

        self.status_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8
        )
        self.status_box.set_valign(Gtk.Align.CENTER)
        self.spinner = Adw.Spinner()
        self.spinner.spinning = False
        self.spinner.set_visible(False)
        self.done_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
        self.done_icon.add_css_class("success")
        self.done_icon.set_visible(False)
        self.error_icon = Gtk.Image.new_from_icon_name("dialog-error-symbolic")
        self.error_icon.add_css_class("error")
        self.error_icon.set_visible(False)
        self.queued_label = Gtk.Label(label="Queued")
        self.queued_label.add_css_class("dim-label")
        self.status_box.append(self.spinner)
        self.status_box.append(self.done_icon)
        self.status_box.append(self.error_icon)
        self.status_box.append(self.queued_label)
        box.append(self.status_box)

        self.set_child(box)
        self.set_state(item.state)

    # -- updates -----------------------------------------------------------

    def set_thumbnail(self, texture) -> None:
        if texture is not None:
            self.thumb.set_from_paintable(texture)
        else:
            self.thumb.set_from_icon_name("image-missing-symbolic")

    def set_meta(self, meta: str) -> None:
        self.meta_label.set_text(meta)

    def set_state(self, state: ItemState) -> None:
        processing = state is ItemState.PROCESSING
        self.spinner.set_visible(processing)
        self.spinner.spinning = processing
        self.done_icon.set_visible(state is ItemState.DONE)
        self.error_icon.set_visible(state is ItemState.ERROR)
        if state is ItemState.QUEUED:
            self.queued_label.set_text("Queued")
            self.queued_label.set_visible(True)
        elif state is ItemState.CANCELLED:
            self.queued_label.set_text("Cancelled")
            self.queued_label.set_visible(True)
        else:
            self.queued_label.set_visible(False)
        if state is ItemState.ERROR and self.item.error:
            self.set_tooltip_text(self.item.error)
        else:
            self.set_tooltip_text(None)
