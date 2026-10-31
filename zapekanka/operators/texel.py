# SPDX-License-Identifier: GPL-3.0-or-later
"""Texel density operators."""

import bpy

from .. import texel


def _uv_layer(mesh, name):
    if name:
        layer = mesh.uv_layers.get(name)
        if layer is not None:
            return layer
    return mesh.uv_layers.active


def _targets(context):
    """Low polys of the enabled pairs, or the selected meshes when there are no pairs."""
    s = context.scene.zapekanka
    objs = []
    for pair in s.pairs:
        if pair.enabled:
            objs.extend(o for o in pair.low_objects() if o not in objs)
    if not objs:
        objs = [o for o in context.selected_objects if o.type == "MESH" and not o.get("zb_preview")]
    return objs


def _resolution(settings):
    w, h = settings.resolution_xy()
    return (w * h) ** 0.5


def _meters_per_unit(context):
    unit = context.scene.unit_settings
    return unit.scale_length if unit.system != "NONE" else 1.0


class ZB_OT_texel_measure(bpy.types.Operator):
    bl_idname = "zapekanka.texel_measure"
    bl_label = "Measure"
    bl_description = "Measure the texel density (texture pixels per meter) of the low polys at the bake resolution"

    def execute(self, context):
        s = context.scene.zapekanka
        s.texel_results.clear()
        depsgraph = context.evaluated_depsgraph_get()
        resolution = _resolution(s)
        mpu = _meters_per_unit(context)
        for obj in _targets(context):
            ev = obj.evaluated_get(depsgraph)
            mesh = ev.to_mesh()
            try:
                layer = _uv_layer(mesh, s.uv_map.strip())
                result = texel.measure(mesh, obj.matrix_world, layer, resolution, mpu) if layer else None
            finally:
                ev.to_mesh_clear()
            item = s.texel_results.add()
            item.name = obj.name
            if result is None:
                item.valid = False
                continue
            item.valid = True
            item.average, item.low, item.high = result
        if not s.texel_results:
            self.report({"WARNING"}, "Nothing to measure: detect pairs or select meshes")
            return {"CANCELLED"}
        return {"FINISHED"}


class ZB_OT_texel_apply(bpy.types.Operator):
    bl_idname = "zapekanka.texel_apply"
    bl_label = "Set UV to Target"
    bl_description = "Scale the UVs of the selected meshes so they reach the target texel density at the bake " \
                     "resolution (pack the islands afterwards if they leave the 0-1 square)"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and any(o.type == "MESH" for o in context.selected_objects)

    def execute(self, context):
        s = context.scene.zapekanka
        resolution = _resolution(s)
        mpu = _meters_per_unit(context)
        outside = []
        changed = 0
        done = set()
        for obj in context.selected_objects:
            if obj.type != "MESH" or obj.data in done:
                continue
            mesh = obj.data
            layer = _uv_layer(mesh, s.uv_map.strip())
            if layer is None:
                continue
            result = texel.measure(mesh, obj.matrix_world, layer, resolution, mpu)
            if result is None or result[0] <= 0:
                continue
            done.add(mesh)
            if texel.scale_uvs(mesh, layer, s.texel_target / result[0]):
                outside.append(obj.name)
            changed += 1
        if not changed:
            self.report({"WARNING"}, "No selected mesh with UVs to scale")
            return {"CANCELLED"}
        bpy.ops.zapekanka.texel_measure()
        if outside:
            self.report({"WARNING"}, "UVs now leave the 0-1 square on %s: pack the islands or lower the target"
                        % ", ".join(outside[:3]))
        else:
            self.report({"INFO"}, "Scaled the UVs of %d mesh(es)" % changed)
        return {"FINISHED"}


classes = (ZB_OT_texel_measure, ZB_OT_texel_apply)
