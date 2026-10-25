# SPDX-License-Identifier: GPL-3.0-or-later
"""Zapekanka - texture baking for game assets.

High to low poly baking with automatic cages, exploded bakes, supersampling,
PBR conversion, engine presets, background baking and engine export.
"""

bl_info = {
    "name": "Zapekanka",
    "author": "Zapekanka contributors",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "3D Viewport > Sidebar > Zapekanka",
    "description": "High/low texture baking: PBR, mesh maps, auto cage, exploded bake, "
    "background baking, export to Unreal, Unity, Godot, Substance and Marmoset",
    "doc_url": "https://github.com/sergey5600/zapekanka",
    "tracker_url": "https://github.com/sergey5600/zapekanka/issues",
    "category": "Render",
}

if "bpy" in locals():
    import importlib

    for _name in ("prefs", "props", "translations", "operators", "ui", "background"):
        if _name in locals():
            importlib.reload(locals()[_name])

import bpy

from . import background, operators, prefs, props, translations, ui

_classes = prefs.classes + props.classes + operators.classes + ui.classes


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    props.register()
    translations.register()


def unregister():
    background.shutdown()
    translations.unregister()
    props.unregister()
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
