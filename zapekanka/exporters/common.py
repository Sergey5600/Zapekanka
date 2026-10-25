# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared export helpers.

Exports never touch the user's objects permanently: meshes are exported from
temporary evaluated copies that carry the requested names and materials.
"""

import json
import os
import shutil
from contextlib import contextmanager

import bpy
from mathutils import Matrix

from .. import materials
from ..core import cage as cage_mod


class ExportError(Exception):
    pass


class TextureSet:
    def __init__(self, name):
        self.name = name
        self.pairs = []
        self.lows = []
        self.highs = []
        self.files = []
        self.normal_format = "OPENGL"
        self.meta = {}
        self.sidecar = None

    @property
    def baked(self):
        return bool(self.files)


def texture_sets(context, only_enabled=True):
    s = context.scene.zapekanka
    sets = {}
    for pair in s.pairs:
        if only_enabled and not pair.enabled:
            continue
        if not pair.low_objects():
            continue
        ts = sets.get(pair.set_name)
        if ts is None:
            ts = sets[pair.set_name] = TextureSet(pair.set_name)
        ts.pairs.append(pair)
        ts.lows.extend(o for o in pair.low_objects() if o not in ts.lows)
        ts.highs.extend(o for o in pair.high_objects() if o not in ts.highs)
    out_dir = bpy.path.abspath(s.output_dir)
    for ts in sets.values():
        sidecar = os.path.join(out_dir, "%s.zapekanka.json" % ts.name)
        if os.path.isfile(sidecar):
            _, files, normal_format, meta = materials.read_sidecar(sidecar)
            ts.files = [f for f in files if os.path.isfile(f["path"])]
            ts.normal_format = normal_format
            ts.meta = meta
            ts.sidecar = sidecar
    return list(sets.values())


TARGET_FOLDERS = {"UE5": "Unreal", "UNITY": "Unity", "GODOT": "Godot", "SUBSTANCE": "Substance",
                  "MARMOSET": "Marmoset", "GLTF": "glTF", "ROBLOX": "Roblox"}


def export_dir(settings, target=None):
    """Export folder; each target gets its own subfolder so exports never mix."""
    raw = settings.export.directory.strip() or "//export/"
    if raw.startswith("//") and not bpy.data.filepath:
        raise ExportError("Save the .blend file first or choose an absolute export folder")
    path = os.path.normpath(bpy.path.abspath(raw))
    if target in TARGET_FOLDERS:
        path = os.path.join(path, TARGET_FOLDERS[target])
    os.makedirs(path, exist_ok=True)
    return path


def baked_material(context, ts):
    """The material built from the texture set's files (created if needed, not assigned)."""
    s = context.scene.zapekanka
    if not ts.baked:
        return None
    name = s.material_template.replace("{name}", ts.name)
    mat = bpy.data.materials.get(name)
    if mat is None or not mat.get("zb_texture_set"):
        mat = materials.build_material(name, ts.files, ts.normal_format, ts.meta, s.uv_map.strip())
    return mat


def copy_textures(ts, dest):
    os.makedirs(dest, exist_ok=True)
    copied = []
    for f in ts.files:
        target = os.path.join(dest, os.path.basename(f["path"]))
        if os.path.normcase(os.path.abspath(target)) != os.path.normcase(os.path.abspath(f["path"])):
            shutil.copy2(f["path"], target)
        copied.append(dict(f, path=target))
    return copied


# ----------------------------------------------------------------------------
# Temporary export objects


@contextmanager
def _free_names(names):
    """Temporarily rename user objects whose names collide with ``names``."""
    renamed = []
    try:
        for name in names:
            obj = bpy.data.objects.get(name)
            if obj is not None:
                tmp = "%s__zb_export_tmp" % name
                obj.name = tmp
                renamed.append((obj, name))
        yield
    finally:
        for obj, name in reversed(renamed):
            try:
                obj.name = name
            except ReferenceError:
                pass


def _evaluated_copy(obj, depsgraph, to_space, triangulate):
    ev = obj.evaluated_get(depsgraph)
    mesh = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=depsgraph)
    mesh.transform(to_space @ obj.matrix_world)
    if (to_space @ obj.matrix_world).to_3x3().determinant() < 0:
        mesh.flip_normals()
    if triangulate:
        import bmesh

        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method="BEAUTY", ngon_method="BEAUTY")
        bm.to_mesh(mesh)
        bm.free()
    return mesh


@contextmanager
def export_objects(context, groups, triangulate=False):
    """Yield temporary objects built from ``groups``.

    ``groups`` is a list of dicts: ``name`` (object name), ``objects`` (sources),
    ``material`` (optional material for every face), ``pivot`` (optional
    source object whose transform becomes the object's transform) and
    ``positions`` (optional callable mesh -> new vertex positions, used for cages).
    """
    depsgraph = context.evaluated_depsgraph_get()
    coll = bpy.data.collections.new("ZB_Export")
    context.scene.collection.children.link(coll)
    created = []
    meshes = []
    with _free_names([g["name"] for g in groups]):
        # Temporary objects must be gone before the user's names are restored,
        # otherwise the user's objects would come back as "Name.001".
        try:
            for g in groups:
                pivot = g.get("pivot")
                world = pivot.matrix_world.copy() if pivot is not None else Matrix()
                to_space = world.inverted_safe()
                parts = [_evaluated_copy(o, depsgraph, to_space, triangulate) for o in g["objects"]]
                meshes.extend(parts)
                mesh = _join_meshes(parts, g["name"])
                meshes.append(mesh)
                if g.get("material") is not None:
                    mesh.materials.clear()
                    mesh.materials.append(g["material"])
                    mesh.polygons.foreach_set("material_index", [0] * len(mesh.polygons))
                if g.get("positions") is not None:
                    cage_mod.apply_positions(mesh, g["positions"](mesh))
                obj = bpy.data.objects.new(g["name"], mesh)
                obj.matrix_world = world
                coll.objects.link(obj)
                created.append(obj)
            yield created
        finally:
            for obj in created:
                bpy.data.objects.remove(obj, do_unlink=True)
            for mesh in meshes:
                if mesh.users == 0:
                    bpy.data.meshes.remove(mesh)
            bpy.data.collections.remove(coll)


def _join_meshes(parts, name):
    """Join meshes without operators (keeps UVs by name, custom normals, materials)."""
    if len(parts) == 1:
        mesh = parts[0].copy()
        mesh.name = name
        return mesh
    import bmesh

    # Custom normals do not survive a bmesh round trip: collect them first.
    has_custom = any(p.has_custom_normals for p in parts)
    normals = []
    bm = bmesh.new()
    mat_map = {}
    materials_out = []
    for part in parts:
        if has_custom:
            normals.extend(tuple(n.vector) for n in part.corner_normals)
        # remap material indices into the joined list
        remap = []
        for m in part.materials:
            key = m.name if m else None
            if key not in mat_map:
                mat_map[key] = len(materials_out)
                materials_out.append(m)
            remap.append(mat_map[key])
        if remap:
            idx = [remap[min(p.material_index, len(remap) - 1)] for p in part.polygons]
            part.polygons.foreach_set("material_index", idx)
        bm.from_mesh(part)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for m in materials_out:
        mesh.materials.append(m)
    if has_custom and len(normals) == len(mesh.loops):
        mesh.normals_split_custom_set(normals)
    return mesh


@contextmanager
def selection(context, objs):
    vl = context.view_layer
    prev_sel = list(context.selected_objects)
    prev_active = vl.objects.active
    for o in prev_sel:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    vl.objects.active = objs[0] if objs else None
    try:
        yield
    finally:
        for o in objs:
            try:
                o.select_set(False)
            except ReferenceError:
                pass
        for o in prev_sel:
            try:
                o.select_set(True)
            except ReferenceError:
                pass
        vl.objects.active = prev_active


FBX_PROFILES = {
    "DEFAULT": {"axis_forward": "-Z", "axis_up": "Y", "apply_scale_options": "FBX_SCALE_NONE",
                "bake_space_transform": False},
    "UNITY": {"axis_forward": "-Z", "axis_up": "Y", "apply_scale_options": "FBX_SCALE_ALL",
              "bake_space_transform": True},
    "ROBLOX": {"axis_forward": "-Z", "axis_up": "Y", "apply_scale_options": "FBX_SCALE_UNITS",
               "bake_space_transform": True},
}


def export_fbx(context, objs, filepath, profile="DEFAULT", scale=1.0, triangulate=False):
    p = FBX_PROFILES[profile]
    with selection(context, objs):
        bpy.ops.export_scene.fbx(
            filepath=filepath,
            use_selection=True,
            object_types={"MESH"},
            global_scale=scale,
            apply_unit_scale=True,
            apply_scale_options=p["apply_scale_options"],
            bake_space_transform=p["bake_space_transform"],
            axis_forward=p["axis_forward"],
            axis_up=p["axis_up"],
            use_mesh_modifiers=True,
            mesh_smooth_type="FACE",
            use_tspace=True,
            use_triangles=triangulate,
            use_custom_props=False,
            add_leaf_bones=False,
            bake_anim=False,
            path_mode="STRIP",
            embed_textures=False,
        )
    return filepath


def export_glb(context, objs, filepath):
    with selection(context, objs):
        bpy.ops.export_scene.gltf(
            filepath=filepath,
            export_format="GLB",
            use_selection=True,
            export_apply=True,
            export_tangents=True,
            export_materials="EXPORT",
            export_image_format="AUTO",
        )
    return filepath


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    return path
