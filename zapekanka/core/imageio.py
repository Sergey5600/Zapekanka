# SPDX-License-Identifier: GPL-3.0-or-later
"""Writing numpy buffers to image files with exact, colour-management free values."""

import os

import bpy
import numpy as np

from . import compat

FORMAT_EXT = {
    "PNG": ".png",
    "TARGA": ".tga",
    "TARGA_RAW": ".tga",
    "TIFF": ".tif",
    "OPEN_EXR": ".exr",
    "JPEG": ".jpg",
}
FLOAT_FORMATS = {"OPEN_EXR"}
DEPTHS = {
    "PNG": (8, 16),
    "TARGA": (8,),
    "TARGA_RAW": (8,),
    "TIFF": (8, 16),
    "OPEN_EXR": (16, 32),
    "JPEG": (8,),
}
NO_ALPHA_FORMATS = {"JPEG"}


def resolve_depth(fmt, depth):
    allowed = DEPTHS.get(fmt, (8,))
    if depth in allowed:
        return depth
    if fmt in FLOAT_FORMATS:
        return 16 if depth <= 16 else 32
    return max(d for d in allowed if d <= max(depth, allowed[0]))


class ImageWriter:
    """Saves arrays through a private scene so the user's render settings stay untouched.

    Values are written verbatim: callers are responsible for any sRGB encoding.
    8-bit outputs go through a byte buffer (no premultiplication, exact
    rounding); 16/32-bit outputs through a float buffer.
    """

    def __init__(self):
        self.scene = bpy.data.scenes.new("ZB_ImageWriter")
        vs = self.scene.view_settings
        try:
            self.scene.display_settings.display_device = "sRGB"
        except TypeError:
            pass
        for attr, value in (("view_transform", "Standard"), ("look", "None")):
            try:
                setattr(vs, attr, value)
            except TypeError:
                pass
        vs.exposure = 0.0
        vs.gamma = 1.0

    def close(self):
        if self.scene is not None:
            try:
                bpy.data.scenes.remove(self.scene)
            except ReferenceError:
                pass
            self.scene = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def save(self, array, path, fmt="PNG", depth=8, compression=15):
        """Write ``array`` (H, W, 1|3|4) to ``path``. Returns the final path."""
        h, w, c = array.shape
        if fmt in NO_ALPHA_FORMATS and c == 4:
            array = array[..., :3]
            c = 3
        depth = resolve_depth(fmt, depth)
        float_buffer = fmt in FLOAT_FORMATS or depth > 8
        img = bpy.data.images.new("ZB_Out", w, h, alpha=(c == 4), float_buffer=float_buffer)
        try:
            compat.set_colorspace(img, "data")
            rgba = np.empty((h, w, 4), np.float32)
            if c == 1:
                rgba[..., 0:3] = array[..., 0:1]
                rgba[..., 3] = 1.0
            elif c == 3:
                rgba[..., 0:3] = array
                rgba[..., 3] = 1.0
            else:
                rgba[:] = array
            if fmt not in FLOAT_FORMATS:
                np.clip(rgba, 0.0, 1.0, out=rgba)
            if float_buffer and fmt not in FLOAT_FORMATS and c == 4:
                # Blender treats float buffers as premultiplied and divides on save.
                rgba[..., 0:3] *= rgba[..., 3:4]
            img.pixels.foreach_set(rgba.ravel())
            del rgba
            settings = self.scene.render.image_settings
            settings.file_format = fmt
            settings.color_mode = {1: "BW", 3: "RGB", 4: "RGBA"}[c]
            if fmt in FLOAT_FORMATS:
                settings.color_depth = "16" if depth <= 16 else "32"
                try:
                    settings.exr_codec = "ZIP"
                except TypeError:
                    pass
            elif fmt not in ("TARGA", "TARGA_RAW", "JPEG"):
                settings.color_depth = str(depth)
            if fmt == "PNG":
                settings.compression = compression
            if fmt == "JPEG":
                settings.quality = 95
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            img.save_render(path, scene=self.scene)
        finally:
            bpy.data.images.remove(img)
        return path
