# SPDX-License-Identifier: GPL-3.0-or-later
"""Export operators."""

import bpy
from bpy.props import BoolProperty

from .. import exporters
from ..exporters.common import ExportError


class ZB_OT_export(bpy.types.Operator):
    bl_idname = "zapekanka.export"
    bl_label = "Export"
    bl_description = "Export low polys, textures and materials for the selected target"
    bl_options = {"REGISTER"}

    launch: BoolProperty(name="Open in Application", default=False, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    def execute(self, context):
        s = context.scene.zapekanka
        try:
            path = exporters.run(context, s.export.target, self.report, self.launch)
        except (ExportError, OSError, RuntimeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        if s.export.open_after and path:
            import os

            folder = path if os.path.isdir(path) else os.path.dirname(path)
            bpy.ops.wm.path_open(filepath=folder)
        return {"FINISHED"}


classes = (ZB_OT_export,)
