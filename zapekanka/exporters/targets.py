# SPDX-License-Identifier: GPL-3.0-or-later
"""Godot, Substance 3D Painter, Marmoset Toolbag, glTF and Roblox exports."""

import os
import subprocess

import bpy

from . import common
from ..core import cage as cage_mod
from ..core.maps import expand_channels


def _set_groups_low(context, ts, name, material):
    return [{"name": name, "objects": ts.lows, "material": material, "pivot": ts.lows[0]}]


# ----------------------------------------------------------------------------
# glTF / Sketchfab


def export_gltf(context, sets, root, report):
    s = context.scene.zapekanka
    e = s.export
    written = []
    for ts in sets:
        mat = common.baked_material(context, ts)
        if mat is None:
            report({"WARNING"}, "%s is not baked yet: exporting without baked textures" % ts.name)
        name = s.mesh_template.replace("{name}", ts.name)
        with common.export_objects(context, _set_groups_low(context, ts, name, mat), e.triangulate) as objs:
            path = os.path.join(root, ts.name + ".glb")
            common.export_glb(context, objs, path)
            written.append(path)
    report({"INFO"}, "Wrote %d glb file(s) to %s" % (len(written), root))
    return root


# ----------------------------------------------------------------------------
# Godot 4


def _godot_res(project, path):
    rel = os.path.relpath(path, project).replace("\\", "/")
    return "res://" + rel


def _godot_material(ts, files, project, path):
    entries = []
    props = []

    def ext(file_path, key):
        rid = "%d_%s" % (len(entries) + 1, key)
        entries.append('[ext_resource type="Texture2D" path="%s" id="%s"]' % (_godot_res(project, file_path), rid))
        return 'ExtResource("%s")' % rid

    kind = "ORMMaterial3D" if any(f["id"] == "orm" for f in files) else "StandardMaterial3D"
    for f in files:
        chans = expand_channels(f["channels"])
        keys = [c.map for c in chans]
        if f["id"] == "base_color":
            props.append("albedo_texture = %s" % ext(f["path"], "albedo"))
            if len(chans) == 4 and keys[3] == "opacity":
                props.append("transparency = 2")
                props.append("alpha_scissor_threshold = 0.5")
        elif f["id"] == "normal":
            props.append("normal_enabled = true")
            props.append("normal_texture = %s" % ext(f["path"], "normal"))
        elif f["id"] == "orm":
            props.append("orm_texture = %s" % ext(f["path"], "orm"))
        elif f["id"] == "emission":
            props.append("emission_enabled = true")
            props.append("emission_texture = %s" % ext(f["path"], "emission"))
        elif kind == "StandardMaterial3D" and f["id"] in ("roughness", "metallic", "ao"):
            ref = ext(f["path"], f["id"])
            if f["id"] == "roughness":
                props.append("roughness_texture = %s" % ref)
            elif f["id"] == "metallic":
                props.append("metallic = 1.0")
                props.append("metallic_texture = %s" % ref)
            else:
                props.append("ao_enabled = true")
                props.append("ao_texture = %s" % ref)
    text = ['[gd_resource type="%s" load_steps=%d format=3]' % (kind, len(entries) + 1), ""]
    text.extend(entries)
    text.extend(["", "[resource]", 'resource_name = "%s"' % ts.name])
    text.extend(props)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(text) + "\n")
    return path


def export_godot(context, sets, root, report):
    s = context.scene.zapekanka
    e = s.export
    raw = e.godot_project.strip()
    project = os.path.normpath(bpy.path.abspath(raw)) if raw else ""
    if project and os.path.isfile(os.path.join(project, "project.godot")):
        base = os.path.join(project, e.godot_folder or "zapekanka")
    else:
        if raw:
            report({"WARNING"}, "No project.godot found: exporting to the export folder")
        project = root
        base = os.path.join(root, e.godot_folder or "zapekanka")
    for ts in sets:
        folder = os.path.join(base, ts.name)
        os.makedirs(folder, exist_ok=True)
        files = common.copy_textures(ts, folder) if e.include_textures else []
        mat = common.baked_material(context, ts)
        name = s.mesh_template.replace("{name}", ts.name)
        with common.export_objects(context, _set_groups_low(context, ts, name, mat), e.triangulate) as objs:
            common.export_glb(context, objs, os.path.join(folder, ts.name + ".glb"))
        if files:
            _godot_material(ts, files, project, os.path.join(folder, s.material_template.replace("{name}", ts.name)
                                                             + ".tres"))
    if s.normal_format != "OPENGL":
        report({"WARNING"}, "Godot expects OpenGL normal maps; the bake uses DirectX")
    report({"INFO"}, "Exported to %s" % base)
    return base


# ----------------------------------------------------------------------------
# Substance 3D Painter and Marmoset Toolbag


def _pair_groups(context, ts, low_suffix, high_suffix, with_cage, include_highs):
    s = context.scene.zapekanka
    groups_low, groups_high, groups_cage = [], [], []
    mat = common.baked_material(context, ts)
    if mat is None:
        mat = bpy.data.materials.get(ts.name) or bpy.data.materials.new(ts.name)
    for pair in ts.pairs:
        lows = pair.low_objects()
        if not lows:
            continue
        groups_low.append({"name": pair.name + low_suffix, "objects": lows, "material": mat})
        highs = pair.high_objects()
        if include_highs and highs:
            groups_high.append({"name": pair.name + high_suffix, "objects": highs})
        if with_cage:
            ext = pair.extrusion if pair.use_custom_extrusion else s.cage_extrusion
            groups_cage.append({
                "name": pair.name + "_cage",
                "objects": lows,
                "positions": (lambda e: (lambda mesh: cage_mod.cage_positions(mesh, e)))(ext),
            })
    return groups_low, groups_high, groups_cage


def _launch(exe, args, report):
    if not exe:
        return
    exe = bpy.path.abspath(exe)
    if not os.path.isfile(exe):
        report({"WARNING"}, "Application not found: %s" % exe)
        return
    try:
        subprocess.Popen([exe] + args)
    except OSError as exc:
        report({"WARNING"}, "Could not start %s: %s" % (exe, exc))


def export_painter_or_marmoset(context, sets, root, report, target, launch=False):
    s = context.scene.zapekanka
    e = s.export
    marmoset = target == "MARMOSET"
    low_files = []
    for ts in sets:
        folder = os.path.join(root, ts.name)
        os.makedirs(folder, exist_ok=True)
        lows, highs, cages = _pair_groups(context, ts, "_low", "_high", marmoset and e.include_cage,
                                          e.include_highs)
        with common.export_objects(context, lows, e.triangulate) as objs:
            path = os.path.join(folder, ts.name + "_low.fbx")
            common.export_fbx(context, objs, path, "DEFAULT", e.scale, e.triangulate)
            low_files.append(path)
        if highs:
            with common.export_objects(context, highs, False) as objs:
                common.export_fbx(context, objs, os.path.join(folder, ts.name + "_high.fbx"), "DEFAULT", e.scale)
        if cages:
            with common.export_objects(context, cages, e.triangulate) as objs:
                common.export_fbx(context, objs, os.path.join(folder, ts.name + "_cage.fbx"), "DEFAULT", e.scale,
                                  e.triangulate)
        if e.include_textures:
            common.copy_textures(ts, os.path.join(folder, "textures"))
    if launch and low_files:
        from ..prefs import get_prefs

        prefs = get_prefs()
        if marmoset:
            _launch(prefs.marmoset_path if prefs else "", [low_files[0]], report)
        else:
            _launch(prefs.substance_path if prefs else "", ["--mesh", low_files[0]], report)
    report({"INFO"}, "Exported %d texture set(s) to %s" % (len(sets), root))
    return root


# ----------------------------------------------------------------------------
# Roblox


ROBLOX_README = """Zapekanka export for Roblox Studio
==================================

1. Import {mesh} with the 3D Importer (File > Import 3D).
2. Add a SurfaceAppearance to the MeshPart and assign:
{slots}
3. AlphaMode: Overlay for decals, Transparency for cut-outs.

Roblox limits SurfaceAppearance textures to 1024x1024.
"""

_ROBLOX_SLOTS = {"base_color": "ColorMap", "normal": "NormalMap", "metallic": "MetalnessMap",
                 "roughness": "RoughnessMap", "emission": "EmissiveMaskContent"}


def export_roblox(context, sets, root, report):
    s = context.scene.zapekanka
    e = s.export
    for ts in sets:
        folder = os.path.join(root, ts.name)
        os.makedirs(folder, exist_ok=True)
        files = common.copy_textures(ts, folder) if e.include_textures else []
        mat = common.baked_material(context, ts)
        name = s.mesh_template.replace("{name}", ts.name)
        with common.export_objects(context, _set_groups_low(context, ts, name, mat), True) as objs:
            common.export_fbx(context, objs, os.path.join(folder, name + ".fbx"), "ROBLOX", e.scale, True)
        slots = "\n".join("   - %s: %s" % (_ROBLOX_SLOTS[f["id"]], os.path.basename(f["path"]))
                          for f in files if f["id"] in _ROBLOX_SLOTS)
        with open(os.path.join(folder, "README.txt"), "w", encoding="utf-8") as fh:
            fh.write(ROBLOX_README.format(mesh=name + ".fbx", slots=slots or "   (bake textures first)"))
    if max(s.resolution_xy()) > 1024:
        report({"WARNING"}, "Roblox only accepts textures up to 1024px")
    report({"INFO"}, "Exported to %s" % root)
    return root
