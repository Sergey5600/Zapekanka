# SPDX-License-Identifier: GPL-3.0-or-later
"""Add-on preferences."""

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty

ADDON_ID = __package__


def get_prefs():
    addon = bpy.context.preferences.addons.get(ADDON_ID)
    return addon.preferences if addon is not None else None


class ZB_Preferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_ID

    blender_path: StringProperty(
        name="Blender Executable",
        description="Blender used for background bakes. Empty: the running Blender",
        subtype="FILE_PATH",
        default="",
    )
    temp_dir: StringProperty(
        name="Temporary Folder",
        description="Where background jobs store their data. Empty: system temp folder",
        subtype="DIR_PATH",
        default="",
    )
    keep_job_files: BoolProperty(
        name="Keep Job Files",
        description="Keep the background job folder (scene copy, logs) after a successful bake",
        default=False,
    )
    low_priority: BoolProperty(
        name="Low Priority Worker",
        description="Run background bakes with lower process priority so the UI stays responsive",
        default=True,
    )
    max_tile: EnumProperty(
        name="Max Tile Size",
        description="Supersampled bakes larger than this are split into tiles to limit memory use",
        items=(
            ("4096", "4096", "Lowest memory use"),
            ("8192", "8192", "Balanced (about 1 GB per tile buffer)"),
            ("16384", "16384", "Fewest tiles, needs a lot of RAM"),
        ),
        default="8192",
    )
    substance_path: StringProperty(
        name="Substance 3D Painter",
        description="Executable used by 'Open in Substance Painter'",
        subtype="FILE_PATH",
        default="",
    )
    marmoset_path: StringProperty(
        name="Marmoset Toolbag",
        description="Executable used by 'Open in Marmoset Toolbag'",
        subtype="FILE_PATH",
        default="",
    )
    ue_multicast_group: StringProperty(
        name="Multicast Group",
        description="Unreal Python remote execution multicast group (Project Settings > Python)",
        default="239.0.0.1",
    )
    ue_multicast_port: IntProperty(name="Multicast Port", default=6766, min=1, max=65535)
    ue_multicast_bind: StringProperty(
        name="Multicast Bind Address",
        description="Must match 'Multicast Bind Address' in Unreal's Python plugin settings",
        default="127.0.0.1",
    )
    ue_timeout: IntProperty(name="Timeout (s)", default=5, min=1, max=60)

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=False)
        box = col.box()
        box.label(text="Background Baking", icon="RENDER_STILL")
        box.prop(self, "blender_path")
        box.prop(self, "temp_dir")
        row = box.row()
        row.prop(self, "low_priority")
        row.prop(self, "keep_job_files")
        box.prop(self, "max_tile")
        box = col.box()
        box.label(text="External Applications", icon="EXPORT")
        box.prop(self, "substance_path")
        box.prop(self, "marmoset_path")
        box = col.box()
        box.label(text="Unreal Engine Remote Execution", icon="LINKED")
        box.prop(self, "ue_multicast_group")
        row = box.row()
        row.prop(self, "ue_multicast_port")
        row.prop(self, "ue_timeout")
        box.prop(self, "ue_multicast_bind")


classes = (ZB_Preferences,)
