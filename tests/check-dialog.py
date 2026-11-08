"""Create the dialog without showing a window; check checkbox/config binding."""

import gi
gi.require_version("Gimp", "3.0")
gi.require_version("GimpUi", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gimp, GimpUi, Gtk

GimpUi.init("trading-card-bleed-dialog-check")
procedure = Gimp.get_pdb().lookup_procedure("plug-in-trading-card-bleed")
config = procedure.create_config()
dialog = GimpUi.ProcedureDialog.new(procedure, config, "Trading Card Bleed")
try:
    dialog.fill(["border-width", "blend-border"])
    checkbox = dialog.get_widget("blend-border", Gtk.CheckButton.__gtype__)
    assert isinstance(checkbox, Gtk.CheckButton)
    assert checkbox.get_label() == "Blend inner edge"
    assert not checkbox.get_active()
    checkbox.set_active(True)
    assert config.get_property("blend-border") is True
    checkbox.set_active(False)
    assert config.get_property("blend-border") is False
    print("PASS: Blend inner edge renders as a checkbox and updates the setting", flush=True)
finally:
    dialog.destroy()
