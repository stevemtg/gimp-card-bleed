# Trading Card Bleed for GIMP 3

Replaces the outer **73 pixels on all four sides** of an image with stretched artwork while preserving the center and the current canvas size. The border width is adjustable. This is a GIMP 3 Python plug-in; use the instructions below for GIMP 3.0.6 on Windows.

To install:

1. In GIMP, open **Edit > Preferences > Folders > Plug-ins** and locate your user plug-ins folder. The usual Windows location for GIMP 3.0.6 is `%APPDATA%\GIMP\3.0\plug-ins`.
2. Copy the entire `trading-card-bleed` folder from this package's `plug-ins` folder into that location. Keep the folder and Python filename unchanged. The resulting path should be:

   ```text
   %APPDATA%\GIMP\3.0\plug-ins\trading-card-bleed\trading-card-bleed.py
   ```

3. Restart GIMP. Run the plug-in from GIMP rather than double-clicking the Python file. GIMP supplies its Python environment.

This folder structure follows GIMP's [Python plug-in installation instructions](https://developer.gimp.org/resource/writing-a-plug-in/tutorial-python/#theory-file-architecture).

To use:

1. Open your card image. Show the layers you want included in the finished card.
2. Choose **Filters > Decor > Trading Card Bleed...**.
3. Leave **Border width (pixels)** at **73**, or enter a different width. Check **Blend inner edge** for a softer join, then run it.
4. Export the finished image using GIMP's usual export command. Save an XCF copy if you want to retain the editable layers.

The plug-in copies the visible artwork **inside** the existing border. For a canvas of `W × H` pixels and border `b`, it crops a copy to `(W − 2b) × (H − 2b)`, then stretches that copy to `W × H`. A hard-edged mask shows the stretched copy only in the outer border. It does not enlarge the canvas or rescale the original center.

**Blend inner edge** is off by default, preserving the original behavior. When checked, the nearest bleed pixels match the adjacent inner artwork, then smoothly transition into the stretched copy over 16 pixels, entirely within the bleed. For a narrower border, the transition fits the available width; a one-pixel border is left unchanged because there is no room to blend. All protected center pixels remain untouched. The blend uses the inner artwork's edge colors, including at corners, so it never brings back the discarded old border. It handles transparency by blending color and alpha together.

To update an existing installation, replace `trading-card-bleed.py` in your installed `trading-card-bleed` folder with the new file, then restart GIMP. Hide or remove an earlier bleed group before applying the new blend option.

The result is added as a **Card bleed - 73 px** layer group. The original layers remain intact. Hide the group using its eye icon, delete the group, or use one **Undo** immediately after running to restore the original border. The group uses GIMP's [Pass through mode](https://docs.gimp.org/3.0/en/gimp-layer-groups.html): its lower layer clears the old border and its upper layer supplies the stretched replacement. Transparent artwork therefore replaces the old border without showing the old border through it. The current selection is restored afterward.

Before rerunning, hide or remove the previous bleed group, especially if changing the border width. The group is a snapshot; rerun after editing the card artwork.

RGB and Grayscale images are supported, including transparency. Convert Indexed images through **Image > Mode > RGB** first. Both image dimensions must exceed twice the border width: with 73 pixels, the minimum is 147 pixels in each dimension.

Stretching the whole inner artwork can create a visible join at the protected center. **Blend inner edge** softens that join but can smear fine details within the transition. Check the result at the intended trim line before printing.

API references: [Copy visible artwork](https://developer.gimp.org/api/3.0/libgimp/ctor.Layer.new_from_visible.html), [scale a layer](https://developer.gimp.org/api/3.0/libgimp/method.Layer.scale.html), and [create a selection mask](https://developer.gimp.org/api/3.0/libgimp/method.Layer.create_mask.html).

Validated in the installed GIMP 3.0.6 using its actual plug-in procedure. Fourteen integration cases covered default/off/on blending, 73-pixel and narrow borders, minimum dimensions, transparency, grayscale, and rejection of an undersized image. Checks verified every protected center pixel, the blend's inner and outer endpoints including corners, unchanged outer stretched artwork, opacity, and absence of old-border contamination. They also verified original layer pixels, selection/context restoration, and restoration of the original image when the group is hidden. A separate dialog check confirmed that **Blend inner edge** is a checkbox, defaults to off, and updates the plug-in setting when toggled. Manual Undo was not automated.
