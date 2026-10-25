# SPDX-License-Identifier: GPL-3.0-or-later
"""Map presets, material restore and texture set import."""

import os

import bpy
from bpy.props import EnumProperty, StringProperty
from bpy_extras.io_utils import ImportHelper

from .. import materials, presets

MAP_GROUPS = {
    "PBR": ("base_color", "roughness", "metallic", "normal", "ao", "emission", "opacity"),
    "MESH": ("normal", "ao", "curvature", "thickness", "position", "world_normal", "height", "id"),
    "GAME": ("base_color", "roughness", "metallic", "normal", "ao"),
}


class ZB_OT_maps_preset(bpy.types.Operator):
    bl_idname = "zapekanka.maps_preset"
    bl_label = "Map Preset"
    bl_description = "Enable a typical set of maps"
    bl_options = {"REGISTER", "UNDO"}

    preset: EnumProperty(items=(
        ("PBR", "Full PBR", "Base Color, Roughness, Metallic, Normal, AO, Emission, Opacity"),
        ("MESH", "Mesh Maps", "Normal, AO, Curvature, Thickness, Position, World Normal, Height, ID"),
        ("GAME", "Game Asset", "Base Color, ORM, Normal"),
        ("NONE", "None", "Disable all maps"),
    ))

    def execute(self, context):
        m = context.scene.zapekanka.maps
        wanted = set(MAP_GROUPS.get(self.preset, ()))
        for key in m.MAP_KEYS:
            setattr(m, "use_" + key, key in wanted)
        return {"FINISHED"}


class ZB_OT_apply_preset(bpy.types.Operator):
    bl_idname = "zapekanka.apply_preset"
    bl_label = "Reset to Preset"
    bl_description = "Re-apply naming, packing and format settings of the selected preset"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.zapekanka
        presets.apply_preset(s, s.preset)
        return {"FINISHED"}


class ZB_OT_restore_materials(bpy.types.Operator):
    bl_idname = "zapekanka.restore_materials"
    bl_label = "Restore Original Materials"
    bl_description = "Put back the materials the low polys had before the baked material was assigned"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        objs = context.selected_objects or list(context.scene.objects)
        count = materials.restore(objs)
        self.report({"INFO"}, "Restored materials on %d object(s)" % count)
        return {"FINISHED"}


class ZB_OT_import_texture_set(bpy.types.Operator, ImportHelper):
    bl_idname = "zapekanka.import_texture_set"
    bl_label = "Import Texture Set"
    bl_description = "Build a material from a texture set (Zapekanka .json or textures named like the " \
                     "current preset) and assign it to the selected objects"
    bl_options = {"REGISTER", "UNDO"}

    filter_glob: StringProperty(default="*.json;*.png;*.tga;*.tif;*.tiff;*.exr;*.jpg", options={"HIDDEN"})
    set_name: StringProperty(name="Texture Set", description="Name used in the file names (for textures "
                             "without a .json file). Empty: guessed from the selected file", default="")

    def execute(self, context):
        s = context.scene.zapekanka
        path = self.filepath
        if path.endswith(".zapekanka.json"):
            name, files, normal_format, meta = materials.read_sidecar(path)
        else:
            folder = os.path.dirname(path)
            name = self.set_name.strip() or self._guess_name(os.path.basename(path), s)
            files = materials.guess_files(folder, name, s)
            normal_format, meta = s.normal_format, {}
        if not files:
            self.report({"ERROR"}, "No textures found for texture set '%s'" % name)
            return {"CANCELLED"}
        mat_name = s.material_template.replace("{name}", name)
        mat = materials.build_material(mat_name, files, normal_format, meta, s.uv_map.strip())
        targets = [o for o in context.selected_objects if o.type == "MESH"]
        if targets:
            materials.assign(targets, mat)
        else:
            mat.use_fake_user = True
        self.report({"INFO"}, "Material %s: %d texture(s)" % (mat.name, len(files)))
        return {"FINISHED"}

    @staticmethod
    def _guess_name(filename, s):
        stem = os.path.splitext(filename)[0]
        template = s.naming_template
        prefix, _, rest = template.partition("{name}")
        sep_suffix = rest.replace("{suffix}", "")
        if prefix and stem.startswith(prefix):
            stem = stem[len(prefix):]
        for key in presets.SUFFIX_KEYS:
            suffix = sep_suffix + getattr(s, "suffix_" + key)
            if suffix and stem.endswith(suffix):
                return stem[: -len(suffix)]
        return stem


classes = (ZB_OT_maps_preset, ZB_OT_apply_preset, ZB_OT_restore_materials, ZB_OT_import_texture_set)
