"""Run by GIMP's python-fu-eval in a disposable profile (see run-tests.ps1)."""

import json
import traceback
from pathlib import Path

import gi
gi.require_version("Gimp", "3.0")
gi.require_version("Gegl", "0.4")
from gi.repository import Gimp, Gegl

Gegl.init(None)
ROOT = Path.cwd()
REPORT = ROOT / "test-results.json"


def rectangle(width, height):
    return Gegl.Rectangle.new(0, 0, width, height)


def pixels(drawable):
    return bytes(drawable.get_buffer().get(
        rectangle(drawable.get_width(), drawable.get_height()),
        1.0, "R'G'B'A u8", Gegl.AbyssPolicy.NONE))


def projection(image):
    snapshot = Gimp.Layer.new_from_visible(image, image, "Test snapshot")
    result = pixels(snapshot)
    snapshot.delete()
    return result


def layer_with_pixels(image, width, height, data, name="Original"):
    layer = Gimp.Layer.new(image, name, width, height,
                           Gimp.ImageType.RGBA_IMAGE, 100, Gimp.LayerMode.NORMAL)
    assert image.insert_layer(layer, None, 0)
    buffer = layer.get_buffer()
    buffer.set(rectangle(width, height), "R'G'B'A u8", data)
    buffer.flush()
    layer.update(0, 0, width, height)
    return layer


def fixture(width, height, border, alpha):
    data = bytearray()
    inner = bytearray()
    for y in range(height):
        for x in range(width):
            if border <= x < width-border and border <= y < height-border:
                u, v = x-border, y-border
                a = (0, 85, 170, 255)[(u//9 + v//11) % 4] if alpha else 255
                color = (20 + u % 190, 30 + v % 180, 55, a)
                inner.extend(color)
            else:
                color = (255, 0, 255, 255)  # Old bleed must disappear.
            data.extend(color)
    return bytes(data), bytes(inner)


def visible_pixels_equal(actual, expected):
    # The RGB values of a fully transparent composited pixel are undefined.
    return actual == expected or actual[3] == expected[3] == 0


def check_image(width, height, border, alpha=False, gray=False, blend=None):
    data, inner = fixture(width, height, border, alpha)
    image = Gimp.Image.new(width, height, Gimp.ImageBaseType.RGB)
    reference = Gimp.Image.new(width-2*border, height-2*border, Gimp.ImageBaseType.RGB)
    try:
        original = layer_with_pixels(image, width, height, data)
        layer_with_pixels(reference, width-2*border, height-2*border, inner)
        if gray:
            assert image.convert_grayscale()
            assert reference.convert_grayscale()
        before = projection(image)
        original_pixels = pixels(original)

        # Use a separate image containing ONLY known inner artwork to provide
        # the expected stretch. This catches wrong crop offsets/source regions.
        Gimp.context_set_interpolation(Gimp.InterpolationType.CUBIC)
        assert reference.scale(width, height)
        expected_border = projection(reference)

        Gimp.context_set_feather(True)
        Gimp.context_set_feather_radius(4.0, 6.0)
        assert image.select_rectangle(Gimp.ChannelOps.REPLACE, 18, 23, 60, 72)
        before_selection = pixels(image.get_selection())
        Gimp.context_set_interpolation(Gimp.InterpolationType.NONE)
        Gimp.context_set_opacity(17.0)
        Gimp.context_set_paint_mode(Gimp.LayerMode.ERASE)
        procedure = Gimp.get_pdb().lookup_procedure("plug-in-trading-card-bleed")
        assert procedure is not None, "Plugin was not discovered"
        config = procedure.create_config()
        config.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
        config.set_property("image", image)
        config.set_core_object_array("drawables", [original])
        config.set_property("border-width", border)
        assert config.get_property("blend-border") is False, "Blending must default to off"
        if blend is not None:
            config.set_property("blend-border", blend)
        result = procedure.run(config)
        assert result.index(0) == Gimp.PDBStatusType.SUCCESS, str(result.index(1))
        after = projection(image)

        assert (image.get_width(), image.get_height()) == (width, height)
        assert len(image.get_layers()) == 2
        group = image.get_layers()[0]
        assert group.is_group() and len(group.get_children()) == 2
        assert pixels(original) == original_pixels, "Original layer was changed"
        assert pixels(image.get_selection()) == before_selection, "Selection was changed"
        assert image.get_selected_layers() == [original], "Layer selection was changed"
        assert len(image.get_channels()) == 0, "Temporary selection channel was left behind"
        assert Gimp.context_get_feather(), "Feather setting was changed"
        assert Gimp.context_get_interpolation() == Gimp.InterpolationType.NONE
        assert Gimp.context_get_opacity() == 17.0, "Paint opacity was changed"
        assert Gimp.context_get_paint_mode() == Gimp.LayerMode.ERASE, "Paint mode was changed"
        changed_border_pixels = 0
        transition_changes = 0
        seam_pixels_checked = 0
        outer_pixels_checked = 0
        blend_width = min(16, border)
        for y in range(height):
            for x in range(width):
                i = 4*(y*width+x)
                actual = after[i:i+4]
                center = border <= x < width-border and border <= y < height-border
                stretched_pixel = expected_border[i:i+4]
                if center:
                    assert actual == before[i:i+4], f"Center changed at ({x}, {y})"
                elif not blend or border == 1:
                    # A one-pixel border cannot hold a transition; it must keep
                    # the original stretched result even when blending is on.
                    assert visible_pixels_equal(actual, stretched_pixel), (
                        f"Stretch mismatch at ({x}, {y}): "
                        f"{tuple(actual)} != {tuple(stretched_pixel)}")
                else:
                    # Test endpoints and invariants, independently of the
                    # implementation's interpolation curve and pixel loop.
                    outer = (x <= border-blend_width or
                             x >= width-border+blend_width-1 or
                             y <= border-blend_width or
                             y >= height-border+blend_width-1)
                    seam = (border-1 <= x <= width-border and
                            border-1 <= y <= height-border)
                    if outer:
                        assert visible_pixels_equal(actual, stretched_pixel), (
                            f"Outer stretch changed at ({x}, {y})")
                        outer_pixels_checked += 1
                    else:
                        edge_x = min(max(x, border), width-border-1)
                        edge_y = min(max(y, border), height-border-1)
                        edge_index = 4*(edge_y*width+edge_x)
                        edge_pixel = before[edge_index:edge_index+4]
                        if seam:
                            assert visible_pixels_equal(actual, edge_pixel), (
                                f"Join mismatch at ({x}, {y}): "
                                f"{tuple(actual)} != edge {tuple(edge_pixel)}")
                            seam_pixels_checked += 1
                        else:
                            assert (min(edge_pixel[3], stretched_pixel[3])-1 <=
                                    actual[3] <=
                                    max(edge_pixel[3], stretched_pixel[3])+1), (
                                f"Transition alpha dipped/overshot at ({x}, {y})")
                            if not visible_pixels_equal(actual, stretched_pixel):
                                transition_changes += 1
                        # All source colors have the same blue component.
                        # Old magenta bleed contamination or a dark alpha halo
                        # would violate this invariant without needing an
                        # implementation-shaped reference blend.
                        if not gray and actual[3] > 0:
                            assert abs(actual[2]-55) <= 1, (
                                f"Transition color contamination at ({x}, {y})")
                if not alpha:
                    assert actual[3] == 255, f"Opaque artwork lost opacity at ({x}, {y})"
                if not center and actual != before[i:i+4]:
                    changed_border_pixels += 1
        assert changed_border_pixels > 0
        if blend and border > 1:
            # The full one-pixel ring includes all four diagonal corner pixels.
            assert seam_pixels_checked == 2*(width-2*border) + 2*(height-2*border) + 4
            assert outer_pixels_checked > 0
            if border > 2 and width-2*border > 20 and height-2*border > 20:
                assert transition_changes > 0, "Blending did not change the transition band"
        group.set_visible(False)
        assert projection(image) == before, "Hiding the group did not restore the image"
        return {"size": [width, height], "border": border, "alpha": alpha,
                "gray": gray, "blend_border": bool(blend),
                "default_blend_setting_used": blend is None,
                "changed_border_pixels": changed_border_pixels,
                "center_pixel_exact": True,
                "unblended_border_matches_reference": True if not blend or border == 1 else None,
                "blend_endpoints_match": True if blend and border > 1 else None,
                "seam_pixels_checked": seam_pixels_checked,
                "outer_pixels_checked": outer_pixels_checked,
                "transition_changes": transition_changes,
                "state_restored": True}
    finally:
        image.delete()
        reference.delete()


def check_rejection():
    image = Gimp.Image.new(146, 220, Gimp.ImageBaseType.RGB)
    try:
        original = layer_with_pixels(image, 146, 220, bytes([99, 40, 22, 255])*146*220)
        before = projection(image)
        procedure = Gimp.get_pdb().lookup_procedure("plug-in-trading-card-bleed")
        config = procedure.create_config()
        config.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
        config.set_property("image", image)
        config.set_core_object_array("drawables", [original])
        config.set_property("border-width", 73)
        result = procedure.run(config)
        assert result.index(0) == Gimp.PDBStatusType.CALLING_ERROR
        assert len(image.get_layers()) == 1 and projection(image) == before
        return {"invalid_size_rejected_without_changes": True}
    finally:
        image.delete()


report = {"gimp_version": Gimp.version(), "passed": False, "cases": []}
try:
    for case in [(311, 419, 73, False, False), (311, 419, 73, True, False),
                 (147, 149, 73, False, False), (32, 43, 1, False, False),
                 (217, 253, 73, True, True),
                 (311, 419, 73, False, False, False),
                 (311, 419, 73, False, False, True),
                 (311, 419, 73, True, False, True),
                 (217, 253, 73, True, True, True),
                 (147, 149, 73, False, False, True),
                 (64, 85, 2, False, False, True),
                 (64, 85, 3, True, False, True),
                 (32, 43, 1, False, False, True)]:
        report["cases"].append(check_image(*case))
    report["cases"].append(check_rejection())
    report["passed"] = True
    print("PASS: all GIMP integration checks passed", flush=True)
except Exception:
    report["error"] = traceback.format_exc()
    print(report["error"], flush=True)
    raise
finally:
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
