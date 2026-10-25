# SPDX-License-Identifier: GPL-3.0-or-later
"""Cage preview and automatic extrusion estimate."""

import bpy
import numpy as np
from bpy.props import EnumProperty
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .. import pairing
from ..core import cage as cage_mod

PREVIEW_COLLECTION = "Zapekanka Cage Preview"


def _preview_collection(context, create=True):
    coll = bpy.data.collections.get(PREVIEW_COLLECTION)
    if coll is None and create:
        coll = bpy.data.collections.new(PREVIEW_COLLECTION)
        context.scene.collection.children.link(coll)
        coll.hide_render = True
    return coll


def clear_previews():
    coll = bpy.data.collections.get(PREVIEW_COLLECTION)
    if coll is None:
        return
    for obj in list(coll.objects):
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    bpy.data.collections.remove(coll)


def _extrusion(settings, pair):
    return pair.extrusion if pair.use_custom_extrusion else settings.cage_extrusion


def refresh_previews(context):
    """Rebuild cage previews for all enabled pairs (world space, not exploded)."""
    s = context.scene.zapekanka
    clear_previews()
    if not s.show_cage_preview:
        return
    coll = _preview_collection(context)
    depsgraph = context.evaluated_depsgraph_get()
    for pair in s.pairs:
        if not pair.enabled:
            continue
        for low in pair.low_objects():
            ev = low.evaluated_get(depsgraph)
            mesh = bpy.data.meshes.new_from_object(ev, depsgraph=depsgraph)
            mesh.transform(low.matrix_world)
            if low.matrix_world.to_3x3().determinant() < 0:
                mesh.flip_normals()
            positions = cage_mod.cage_positions(mesh, _extrusion(s, pair))
            cage_mod.apply_positions(mesh, positions)
            mesh.materials.clear()
            obj = bpy.data.objects.new("ZB_CagePreview_" + low.name, mesh)
            obj["zb_preview"] = True
            obj.display_type = "WIRE"
            obj.show_in_front = True
            obj.hide_render = True
            obj.hide_select = True
            obj.color = (1.0, 0.45, 0.1, 1.0)
            coll.objects.link(obj)


class ZB_OT_cage_preview(bpy.types.Operator):
    bl_idname = "zapekanka.cage_preview"
    bl_label = "Update Cage Preview"
    bl_description = "Show the automatic cage as a wireframe (updates when the extrusion changes)"

    def execute(self, context):
        refresh_previews(context)
        return {"FINISHED"}


def estimate_extrusion(context, pair, sample_limit=20000):
    """Largest low-to-high distance (plus 25%) found on low poly samples."""
    depsgraph = context.evaluated_depsgraph_get()
    highs = pair.high_objects()
    if not highs:
        return None
    trees = []
    for high in highs:
        ev = high.evaluated_get(depsgraph)
        try:
            tree = BVHTree.FromObject(ev, depsgraph)
        except (RuntimeError, ValueError):
            continue
        trees.append((tree, high.matrix_world.inverted_safe(), high.matrix_world.to_3x3()))
    if not trees:
        return None
    worst = 0.0
    for low in pair.low_objects():
        ev = low.evaluated_get(depsgraph)
        mesh = ev.to_mesh()
        try:
            n = len(mesh.vertices)
            co = np.empty(n * 3, np.float32)
            mesh.vertices.foreach_get("co", co)
            co = co.reshape(-1, 3)
            np_ = len(mesh.polygons)
            cen = np.empty(np_ * 3, np.float32)
            mesh.polygons.foreach_get("center", cen)
            pts = np.concatenate([co, cen.reshape(-1, 3)])
            if len(pts) > sample_limit:
                pts = pts[np.linspace(0, len(pts) - 1, sample_limit).astype(int)]
            mw = low.matrix_world
            for p in pts:
                world = mw @ Vector(p)
                best = None
                for tree, inv, m3 in trees:
                    hit = tree.find_nearest(inv @ world)
                    if hit[0] is None:
                        continue
                    d = (m3 @ (hit[0] - inv @ world)).length
                    best = d if best is None else min(best, d)
                if best is not None:
                    worst = max(worst, best)
        finally:
            ev.to_mesh_clear()
    return worst * 1.25 + 1e-4


class ZB_OT_cage_estimate(bpy.types.Operator):
    bl_idname = "zapekanka.cage_estimate"
    bl_label = "Estimate Extrusion"
    bl_description = "Measure the distance between low and high polys and set the cage extrusion"
    bl_options = {"REGISTER", "UNDO"}

    target: EnumProperty(items=(("GLOBAL", "All Pairs", "Set the global extrusion from all enabled pairs"),
                                ("ACTIVE", "Active Pair", "Set a custom extrusion on the active pair")),
                         default="GLOBAL")

    def execute(self, context):
        s = context.scene.zapekanka
        if self.target == "ACTIVE":
            pair = pairing.active_pair(s)
            if pair is None:
                return {"CANCELLED"}
            value = estimate_extrusion(context, pair)
            if value is None:
                self.report({"WARNING"}, "The pair has no high poly")
                return {"CANCELLED"}
            pair.use_custom_extrusion = True
            pair.extrusion = value
        else:
            values = [v for v in (estimate_extrusion(context, p) for p in s.pairs if p.enabled) if v is not None]
            if not values:
                self.report({"WARNING"}, "No pairs with high polys")
                return {"CANCELLED"}
            value = max(values)
            s.cage_extrusion = value
        self.report({"INFO"}, "Cage extrusion set to %.4f" % value)
        return {"FINISHED"}


classes = (ZB_OT_cage_preview, ZB_OT_cage_estimate)
