#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GIMP 3: replace an existing border with stretched inner artwork."""

import sys
from array import array

import gi

gi.require_version("Gimp", "3.0")
gi.require_version("Gegl", "0.4")
from gi.repository import Gegl, Gimp, GLib, GObject


PROCEDURE_NAME = "plug-in-trading-card-bleed"
BLEND_WIDTH = 16


def checked(success, operation):
    if not success:
        raise RuntimeError("GIMP could not " + operation + ".")


def read_linear_pixels(buffer, x, y, width, height):
    """Read linear-light, unassociated RGBA without an 8-bit intermediate."""
    values = array("f")
    values.frombytes(bytes(buffer.get(Gegl.Rectangle.new(x, y, width, height),
                                     1.0, "RGBA float", Gegl.AbyssPolicy.NONE)))
    return values


def capture_inner_edges(layer, width, height, border):
    """Save only the four INNER edge lines, before cropping and scaling."""
    buffer = layer.get_buffer()
    inner_width, inner_height = width - 2 * border, height - 2 * border
    return {
        "top": read_linear_pixels(buffer, border, border, inner_width, 1),
        "bottom": read_linear_pixels(buffer, border, height-border-1, inner_width, 1),
        "left": read_linear_pixels(buffer, border, border, 1, inner_height),
        "right": read_linear_pixels(buffer, width-border-1, border, 1, inner_height),
    }


def blend_inner_edge(layer, edges, width, height, border):
    """Join edge-clamped artwork to the stretch, entirely inside the bleed.

    Keep the masks hard: feathering both the erase and artwork masks would
    leave an alpha dip and let the discarded border show through. Instead,
    blend the replacement pixels themselves with premultiplied linear color.
    Read/write narrow strips so memory scales with the perimeter, not area.
    """
    blend_width = min(BLEND_WIDTH, border)
    if blend_width < 2:
        return  # A one-pixel border has no room for a transition.
    extent = blend_width - 1
    inner_width, inner_height = width - 2 * border, height - 2 * border
    strips = [
        (border-extent, border-extent, inner_width+2*extent, extent, "top", True),
        (border-extent, height-border, inner_width+2*extent, extent, "bottom", True),
        (border-extent, border, extent, inner_height, "left", False),
        (width-border, border, extent, inner_height, "right", False),
    ]
    buffer = layer.get_buffer()
    for x0, y0, strip_width, strip_height, side, horizontal in strips:
        data = read_linear_pixels(buffer, x0, y0, strip_width, strip_height)
        edge = edges[side]
        for row in range(strip_height):
            y = y0 + row
            for column in range(strip_width):
                x = x0 + column
                distance = max(border-x, x-(width-border-1),
                               border-y, y-(height-border-1))
                t = (distance - 1) / (blend_width - 1)
                t = t * t * (3.0 - 2.0 * t)  # Smoothstep with flat endpoints.
                source = (min(max(x-border, 0), inner_width-1) if horizontal
                          else min(max(y-border, 0), inner_height-1)) * 4
                target = (row * strip_width + column) * 4
                if distance == 1:
                    data[target:target+4] = edge[source:source+4]
                    continue
                edge_alpha = edge[source+3] * (1.0 - t)
                stretch_alpha = data[target+3] * t
                alpha = edge_alpha + stretch_alpha
                for component in range(3):
                    data[target+component] = (
                        (edge[source+component] * edge_alpha +
                         data[target+component] * stretch_alpha) / alpha
                        if alpha > 0.0 else 0.0)
                data[target+3] = alpha
        buffer.set(Gegl.Rectangle.new(x0, y0, strip_width, strip_height),
                   "RGBA float", data.tobytes())
    buffer.flush()
    layer.update(0, 0, width, height)


def create_bleed(image, border, blend_border=False):
    """Return a reversible group; keep the canvas and center unchanged.

    Use the visible composite INSIDE the border as the source. A pass-through
    group first erases the old border, then draws the stretched replacement.
    Erasing matters when the source contains transparency: a normal overlay
    alone would leave the old border visible through transparent pixels.
    """
    width, height = image.get_width(), image.get_height()
    if border < 1 or width <= 2 * border or height <= 2 * border:
        raise ValueError(
            f"The image must be wider and taller than {2 * border} pixels "
            f"for a {border}-pixel border (current size: {width} x {height})."
        )
    if image.get_base_type() == Gimp.ImageBaseType.INDEXED:
        raise ValueError("Convert the image to RGB or Grayscale first (Image > Mode).")
    if not image.get_layers():
        raise ValueError("The image needs at least one layer.")

    selected_layers = image.get_selected_layers()
    selected_channels = image.get_selected_channels()
    saved_selection = None
    group = None
    completed = False
    checked(Gimp.context_push(), "save the editing context")
    try:
        checked(image.undo_group_start(), "start an undo group")
        try:
            if not Gimp.Selection.is_empty(image):
                saved_selection = Gimp.Selection.save(image)
                if saved_selection is None:
                    raise RuntimeError("GIMP could not save the selection.")
            checked(Gimp.Selection.none(image), "clear the working selection")
            checked(Gimp.context_set_feather(False), "disable selection feathering")
            checked(Gimp.context_set_antialias(False), "disable selection antialiasing")
            checked(Gimp.context_set_interpolation(Gimp.InterpolationType.CUBIC),
                    "set interpolation")

            # Snapshot before inserting anything that changes the projection.
            stretched = Gimp.Layer.new_from_visible(image, image, "Stretched artwork")
            if stretched is None:
                raise RuntimeError("GIMP could not copy the visible artwork.")
            edges = (capture_inner_edges(stretched, width, height, border)
                     if blend_border and border > 1 else None)
            suffix = " (blended)" if blend_border else ""
            group = Gimp.GroupLayer.new(image, f"Card bleed - {border} px{suffix}")
            checked(image.insert_layer(group, None, 0), "insert the bleed group")
            checked(group.set_mode(Gimp.LayerMode.PASS_THROUGH), "set the group mode")
            checked(image.insert_layer(stretched, group, 0), "insert the artwork copy")

            # New-from-visible is canvas-sized. Discard the old bleed entirely,
            # then enlarge the remaining artwork to the ORIGINAL canvas size.
            checked(stretched.resize(width - 2 * border, height - 2 * border,
                                     -border, -border), "crop the artwork copy")
            checked(stretched.scale(width, height, False), "stretch the artwork copy")
            checked(stretched.set_offsets(0, 0), "align the stretched artwork")
            checked(stretched.set_mode(Gimp.LayerMode.NORMAL), "set the artwork mode")
            if edges is not None:
                blend_inner_edge(stretched, edges, width, height, border)

            checked(image.select_rectangle(Gimp.ChannelOps.REPLACE, border, border,
                                           width - 2 * border, height - 2 * border),
                    "select the protected center")
            checked(Gimp.Selection.invert(image), "select the border")
            mask = stretched.create_mask(Gimp.AddMaskType.SELECTION)
            if mask is None:
                raise RuntimeError("GIMP could not create the border mask.")
            checked(stretched.add_mask(mask), "attach the border mask")
            checked(stretched.set_edit_mask(False), "select the artwork pixels")

            layer_type = (Gimp.ImageType.RGBA_IMAGE
                          if image.get_base_type() == Gimp.ImageBaseType.RGB
                          else Gimp.ImageType.GRAYA_IMAGE)
            eraser = Gimp.Layer.new(image, "Clear original border", width, height,
                                   layer_type, 100.0, Gimp.LayerMode.ERASE)
            checked(eraser.fill(Gimp.FillType.WHITE), "initialize the border eraser")
            checked(image.insert_layer(eraser, group, 1), "insert the border eraser")
            erase_mask = eraser.create_mask(Gimp.AddMaskType.SELECTION)
            if erase_mask is None:
                raise RuntimeError("GIMP could not create the eraser mask.")
            checked(eraser.add_mask(erase_mask), "limit erasing to the border")
            checked(stretched.set_visible(True), "show the stretched artwork")
            checked(eraser.set_visible(True), "enable border replacement")
            checked(group.set_visible(True), "show the bleed group")
            completed = True
        finally:
            try:
                if not completed and group is not None and group.is_valid():
                    image.remove_layer(group)
                if saved_selection is not None:
                    try:
                        checked(image.select_item(Gimp.ChannelOps.REPLACE, saved_selection),
                                "restore the selection")
                    finally:
                        image.remove_channel(saved_selection)
                else:
                    Gimp.Selection.none(image)
                if selected_channels:
                    image.set_selected_channels(selected_channels)
                else:
                    image.set_selected_layers(selected_layers)
            finally:
                image.undo_group_end()
    finally:
        Gimp.context_pop()
        Gimp.displays_flush()
    return group


def run(procedure, run_mode, image, drawables, config, run_data):
    Gegl.init(None)
    if run_mode == Gimp.RunMode.INTERACTIVE:
        gi.require_version("GimpUi", "3.0")
        from gi.repository import GimpUi

        GimpUi.init("trading-card-bleed")
        dialog = GimpUi.ProcedureDialog.new(procedure, config, "Trading Card Bleed")
        dialog.fill(["border-width", "blend-border"])
        accepted = dialog.run()
        dialog.destroy()
        if not accepted:
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, None)
    try:
        create_bleed(image, config.get_property("border-width"),
                     config.get_property("blend-border"))
    except ValueError as error:
        return procedure.new_return_values(Gimp.PDBStatusType.CALLING_ERROR,
                                           GLib.Error(str(error)))
    except Exception as error:
        return procedure.new_return_values(Gimp.PDBStatusType.EXECUTION_ERROR,
                                           GLib.Error(str(error)))
    return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, None)


class TradingCardBleed(Gimp.PlugIn):
    def do_set_i18n(self, name):
        return False, None, None

    def do_query_procedures(self):
        return [PROCEDURE_NAME]

    def do_create_procedure(self, name):
        if name != PROCEDURE_NAME:
            return None
        procedure = Gimp.ImageProcedure.new(self, name, Gimp.PDBProcType.PLUGIN,
                                            run, None)
        procedure.set_image_types("RGB*, GRAY*")
        procedure.set_sensitivity_mask(Gimp.ProcedureSensitivityMask.DRAWABLE |
                                       Gimp.ProcedureSensitivityMask.DRAWABLES)
        procedure.set_menu_label("Trading Card _Bleed...")
        procedure.add_menu_path("<Image>/Filters/Decor")
        procedure.set_documentation(
            "Replace the existing border with stretched inner artwork.",
            "Copies the visible artwork inside the border, stretches the copy "
            "to the canvas size, and shows it only in the border. The center, "
            "canvas size, original layers and current selection are preserved. "
            "Optionally blend the inner edge within the nearest 16 bleed pixels. "
            "Hide the added group or Undo to restore the original border.",
            name)
        procedure.set_attribution("Trading Card Bleed contributors",
                                  "Trading Card Bleed contributors", "2026")
        procedure.add_int_argument(
            "border-width", "Border width (pixels)",
            "Existing outer border to replace on each of the four sides; "
            "the canvas size stays the same.",
            1, 10000, 73, GObject.ParamFlags.READWRITE)
        procedure.add_boolean_argument(
            "blend-border", "Blend inner edge",
            "Smooth the join to the protected artwork over up to 16 pixels "
            "inside the bleed. The center stays unchanged. A one-pixel border "
            "has no room to blend.",
            False, GObject.ParamFlags.READWRITE)
        return procedure


if __name__ == "__main__":
    Gimp.main(TradingCardBleed.__gtype__, sys.argv)
