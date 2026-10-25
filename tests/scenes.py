# SPDX-License-Identifier: GPL-3.0-or-later
"""Procedural test scenes shared by the test suite."""

import bmesh
import bpy


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def cube(name, size=2.0, location=(0, 0, 0), smooth=False, bevel=0.0, segments=4):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    bpy.context.scene.collection.objects.link(obj)
    if smooth:
        for poly in mesh.polygons:
            poly.use_smooth = True
    if bevel:
        mod = obj.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = segments
        mod.limit_method = "NONE"
    return obj


def unwrap(obj, margin=0.02):
    vl = bpy.context.view_layer
    for o in vl.objects:
        o.select_set(False)
    vl.objects.active = obj
    obj.select_set(True)
    with bpy.context.temp_override(active_object=obj, object=obj, selected_objects=[obj], selected_editable_objects=[obj]):
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(island_margin=margin)
        bpy.ops.object.mode_set(mode="OBJECT")
    obj.select_set(False)


def principled(name, color=(0.8, 0.2, 0.1, 1.0), roughness=0.3, metallic=1.0, alpha=1.0, emission=None):
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:
        mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Alpha"].default_value = alpha
    if emission:
        bsdf.inputs["Emission Color"].default_value = emission
        bsdf.inputs["Emission Strength"].default_value = 1.0
    return mat


def box_pair(prefix="Box", location=(0, 0, 0), size=2.0):
    low = cube(prefix + "_low", size, location)
    unwrap(low)
    high = cube(prefix + "_high", size, location, smooth=True, bevel=0.1 * size)
    bpy.context.view_layer.update()
    return low, high
