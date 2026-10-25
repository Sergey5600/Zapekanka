# SPDX-License-Identifier: GPL-3.0-or-later
"""Isolated bake scene: duplicates, explode layout, joined low polys and cages.

Nothing in the user's data is modified.  High polys are linked duplicates
(sharing mesh data; overrides happen on the *object* level only), low polys
and cages are fresh meshes owned by the session.  Everything lives in a
private scene that is deleted in :meth:`BakeSession.cleanup`.
"""

from contextlib import contextmanager

import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import cage as cage_mod
from . import compat, shaders

HIGH_TYPES = {"MESH", "CURVE", "SURFACE", "FONT", "META"}
LOW_TYPES = {"MESH", "CURVE", "SURFACE", "FONT", "META"}
UV_NAME = "ZB_UV"
_RAY_FLAGS = (
    "visible_camera",
    "visible_diffuse",
    "visible_glossy",
    "visible_transmission",
    "visible_volume_scatter",
    "visible_shadow",
)


class SessionError(Exception):
    pass


def _matrix(values):
    if values is None:
        return None
    m = Matrix()
    for r in range(4):
        for c in range(4):
            m[r][c] = values[r * 4 + c]
    return m


def world_matrix(obj):
    """World matrix from the transform chain, valid even if never evaluated.

    Constraints and drivers are ignored; the job builder passes evaluated
    matrices for that case.
    """
    m = obj.matrix_basis.copy()
    while obj.parent is not None:
        m = obj.parent.matrix_basis @ obj.matrix_parent_inverse @ m
        obj = obj.parent
    return m


def matrix_to_list(m):
    return [m[r][c] for r in range(4) for c in range(4)]


@contextmanager
def scene_context(scene, active=None, selected=()):
    """Context override that makes ``scene`` current for operators."""
    vl = scene.view_layers[0]
    selected = [o for o in selected if o is not None]
    # Selecting forces the lazy base resync of this (non-active) view layer;
    # the depsgraph is rebuilt afterwards so it never points at stale bases.
    for obj in scene.objects:
        if obj.select_get(view_layer=vl):
            obj.select_set(False, view_layer=vl)
    for obj in selected:
        obj.select_set(True, view_layer=vl)
    if active is not None:
        vl.objects.active = active
    vl.update()
    override = {
        "scene": scene,
        "view_layer": vl,
        "selected_objects": selected,
        "selected_editable_objects": selected,
    }
    if active is not None:
        override["active_object"] = active
        override["object"] = active
    # Never pass ``window``: its scene differs from ``scene`` and that mismatch
    # crashes the depsgraph update performed before every operator call.
    with bpy.context.temp_override(**override):
        yield


class HighDup:
    """A linked duplicate of a high poly with switchable shading state."""

    def __init__(self, session, original, matrix):
        self.session = session
        self.original_name = original.name
        reg = session.reg
        if original.type == "MESH":
            obj = original.copy()
        else:
            obj = session.convert_to_mesh_object(original, matrix, "ZB_High_" + original.name)
        reg.objects.append(obj)
        obj.parent = None
        obj.constraints.clear()
        obj.animation_data_clear()
        obj.matrix_world = matrix
        obj.hide_render = False
        obj.hide_viewport = False
        for flag in _RAY_FLAGS:
            if hasattr(obj, flag):
                setattr(obj, flag, True)
        session.link(obj)
        self.obj = obj
        self.base_matrix = matrix.copy()
        self.initial_slots = [(slot.link, slot.material) for slot in obj.material_slots]
        self.effective_materials = [slot.material for slot in obj.material_slots]
        self.gn_mod = None
        self.state = "ORIGINAL"

    @property
    def has_slots(self):
        return bool(self.initial_slots)

    def set_offset(self, offset):
        self.obj.matrix_world = Matrix.Translation(offset) @ self.base_matrix
        self.obj["zb_offset"] = tuple(offset)

    def _restore_slots(self):
        for slot, (link, mat) in zip(self.obj.material_slots, self.initial_slots):
            if slot.link != link:
                slot.link = link
            if link == "OBJECT" and slot.material != mat:
                slot.material = mat

    def _gn(self, group):
        if self.gn_mod is None:
            self.gn_mod = self.obj.modifiers.new("ZB_Override", "NODES")
        self.gn_mod.node_group = group
        self.gn_mod.show_render = True
        self.gn_mod.show_viewport = True

    def _gn_off(self):
        if self.gn_mod is not None:
            self.gn_mod.show_render = False
            self.gn_mod.show_viewport = False

    def set_original(self):
        self._gn_off()
        self._restore_slots()
        self.state = "ORIGINAL"

    def set_uniform(self, group):
        """All faces use one material, assigned through a geometry nodes modifier."""
        for slot in self.obj.material_slots:
            if slot.link != "DATA":
                slot.link = "DATA"
        self._gn(group)
        self.state = "UNIFORM"

    def set_per_slot(self, mapper, fallback_group):
        """Each slot gets ``mapper(original_material)``; slot-less objects use the fallback."""
        if not self.has_slots:
            self.set_uniform(fallback_group)
            return
        self._gn_off()
        for slot, mat in zip(self.obj.material_slots, self.effective_materials):
            slot.link = "OBJECT"
            slot.material = mapper(mat)
        self.state = "PER_SLOT"


class BakeSession:
    def __init__(self, job, log=print):
        self.job = job
        self.settings = job["settings"]
        self.log = log
        self.reg = shaders.Registry()
        self.scene = None
        self.highs = {}  # texture set name -> [HighDup]
        self.lows = {}  # texture set name -> joined low object
        self.cages = {}  # texture set name -> cage object
        self.ray_distance = {}
        self.bounds = {}  # texture set name -> (min, max) original-space bounds
        self.max_extrusion = {}
        self.warnings = []
        self.objects_info = job.get("objects", {})

    # ------------------------------------------------------------------ utils

    def warn(self, template, *args):
        """Record a warning as template + args (translated by the UI)."""
        self.warnings.append({"template": template, "args": list(args)})
        self.log("WARNING: " + (template % args if args else template))

    def link(self, obj):
        compat.link_object(self.scene.collection, obj)

    def retire(self, obj):
        """Take a helper object out of the bake without deleting it.

        Removing objects from the private scene mid-session leaves dangling
        view-layer bases (Blender resyncs them lazily against the *context*
        scene), which crashes the baker.  Helpers are hidden instead and
        deleted together with the scene in :meth:`cleanup`.
        """
        obj.hide_render = True
        obj.hide_viewport = True
        obj.hide_select = True

    def find_object(self, name):
        obj = bpy.data.objects.get(name)
        if obj is None:
            raise SessionError("Object %r not found" % name)
        return obj

    def object_matrix(self, obj):
        info = self.objects_info.get(obj.name, {})
        m = _matrix(info.get("matrix"))
        return m if m is not None else world_matrix(obj)

    def evaluated_depsgraph(self):
        # ViewLayer.update() evaluates the private scene without touching the
        # context; evaluated_depsgraph_get() under a scene override can crash
        # in background mode.
        vl = self.scene.view_layers[0]
        vl.update()
        return vl.depsgraph

    def convert_to_mesh_object(self, original, matrix, name):
        """Evaluate any geometry object into a standalone mesh object."""
        tmp = original.copy()
        tmp.parent = None
        tmp.matrix_world = matrix
        self.reg.objects.append(tmp)
        self.link(tmp)
        try:
            dg = self.evaluated_depsgraph()
            mesh = bpy.data.meshes.new_from_object(
                tmp.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg
            )
        finally:
            self.retire(tmp)
        self.reg.meshes.append(mesh)
        return bpy.data.objects.new(name, mesh)

    # ------------------------------------------------------------------ setup

    def create_scene(self):
        scene = bpy.data.scenes.new("ZB_BakeScene")
        self.reg.scenes.append(scene)
        self.scene = scene
        scene.render.engine = "CYCLES"
        cyc = scene.cycles
        cyc.device = "GPU" if self.settings.get("device") == "GPU" else "CPU"
        cyc.samples = max(1, int(self.settings.get("aa_samples", 4)))
        for attr, value in (
            ("use_denoising", False),
            ("use_adaptive_sampling", False),
            ("use_light_tree", False),
        ):
            if hasattr(cyc, attr):
                setattr(cyc, attr, value)
        scene.world = None
        try:
            scene.view_settings.view_transform = "Standard"
        except TypeError:
            pass
        return scene

    def setup(self):
        self.create_scene()
        texture_sets = self.job["texture_sets"]
        explode = bool(self.settings.get("explode")) and sum(len(t["pairs"]) for t in texture_sets) > 1

        # 1. high duplicates and temporary low copies (for bounds)
        pair_records = []
        for ts in texture_sets:
            self.highs[ts["name"]] = []
            for pair in ts["pairs"]:
                rec = {"ts": ts["name"], "pair": pair, "highs": [], "lows": [], "cage": None}
                for name in pair.get("highs") or []:
                    orig = self.find_object(name)
                    if orig.type not in HIGH_TYPES:
                        self.warn("High poly %s is not geometry (%s), skipped", name, orig.type)
                        continue
                    rec["highs"].append(HighDup(self, orig, self.object_matrix(orig)))
                for name in pair["lows"]:
                    orig = self.find_object(name)
                    if orig.type not in LOW_TYPES:
                        raise SessionError("Low poly %r is not a mesh" % name)
                    rec["lows"].append(orig)
                if pair.get("cage"):
                    rec["cage"] = self.find_object(pair["cage"])
                if not rec["highs"]:
                    # Low without high: bake the low's own materials (copy of itself as source).
                    for orig in rec["lows"]:
                        rec["highs"].append(HighDup(self, orig, self.object_matrix(orig)))
                    rec["self_source"] = True
                pair_records.append(rec)
                self.highs[ts["name"]].extend(rec["highs"])

        # 2. low meshes (evaluated, render settings) in world space
        part_id = 0
        for rec in pair_records:
            rec["low_objs"] = []
            ext = float(rec["pair"].get("extrusion", 0.01))
            for orig in rec["lows"]:
                obj = self._make_low_object(orig, "ZB_Low_" + orig.name)
                obj["zb_part"] = part_id
                obj["zb_ext"] = ext
                rec["low_objs"].append(obj)
                part_id += 1
            if rec["cage"] is not None:
                rec["cage_obj"] = self._make_low_object(rec["cage"], "ZB_UserCage_" + rec["cage"].name, need_uv=False)

        # 3. explode layout
        offsets = [Vector((0.0, 0.0, 0.0)) for _ in pair_records]
        if explode:
            offsets = self._explode_offsets(pair_records)
        for rec, off in zip(pair_records, offsets):
            rec["offset"] = off
            for hd in rec["highs"]:
                hd.set_offset(off)
            for obj in rec["low_objs"] + ([rec["cage_obj"]] if rec.get("cage_obj") else []):
                obj.matrix_world = Matrix.Translation(off) @ obj.matrix_world

        # 4. apply transforms, write attributes
        all_lows = [o for rec in pair_records for o in rec["low_objs"]]
        all_lows += [rec["cage_obj"] for rec in pair_records if rec.get("cage_obj")]
        self._apply_transforms(all_lows)
        for rec in pair_records:
            for obj in rec["low_objs"]:
                self._write_low_attributes(obj, rec["offset"])
            if rec.get("cage_obj"):
                self._attach_user_cage(rec)

        # 5. join per texture set + cage
        for ts in texture_sets:
            objs = [o for rec in pair_records if rec["ts"] == ts["name"] for o in rec["low_objs"]]
            low = self._join(objs, "ZB_Low_" + ts["name"])
            self.lows[ts["name"]] = low
            exts = [float(r["pair"].get("extrusion", 0.01)) for r in pair_records if r["ts"] == ts["name"]]
            self.max_extrusion[ts["name"]] = max(exts) if exts else 0.01
            self._build_cage(ts["name"], low)
            self.bounds[ts["name"]] = self._orig_bounds(low)

        for obj in list(self.scene.objects):
            obj.select_set(False, view_layer=self.scene.view_layers[0])

    # ------------------------------------------------------------------ lows

    def _make_low_object(self, original, name, need_uv=True):
        matrix = self.object_matrix(original)
        tmp = original.copy()
        tmp.parent = None
        tmp.constraints.clear()
        tmp.animation_data_clear()
        tmp.matrix_world = matrix
        for mod in tmp.modifiers:
            mod.show_viewport = mod.show_render
            if mod.type in {"SUBSURF", "MULTIRES"} and hasattr(mod, "render_levels"):
                try:
                    mod.levels = mod.render_levels
                except (AttributeError, TypeError):
                    pass
        if self.settings.get("triangulate") and need_uv:
            tri = tmp.modifiers.new("ZB_Triangulate", "TRIANGULATE")
            tri.quad_method = "BEAUTY"
            tri.ngon_method = "BEAUTY"
            if hasattr(tri, "keep_custom_normals"):
                tri.keep_custom_normals = True
        self.reg.objects.append(tmp)
        self.link(tmp)
        try:
            dg = self.evaluated_depsgraph()
            mesh = bpy.data.meshes.new_from_object(
                tmp.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg
            )
        finally:
            self.retire(tmp)
        self.reg.meshes.append(mesh)
        if len(mesh.polygons) == 0:
            raise SessionError("Low poly %r has no faces" % original.name)
        if need_uv:
            self._prepare_uv(mesh, original.name)
        obj = bpy.data.objects.new(name, mesh)
        self.reg.objects.append(obj)
        obj.matrix_world = matrix
        self.link(obj)
        return obj

    def _prepare_uv(self, mesh, label):
        wanted = self.settings.get("uv_map") or ""
        layer = mesh.uv_layers.get(wanted) if wanted else None
        if layer is None:
            layer = mesh.uv_layers.active
        if layer is None:
            raise SessionError("Low poly %r has no UV map" % label)
        if wanted and layer.name != wanted:
            self.warn("UV map %s not found on %s, using %s", wanted, label, layer.name)
        keep = layer.name
        for other in [l.name for l in mesh.uv_layers if l.name != keep]:
            mesh.uv_layers.remove(mesh.uv_layers[other])
        mesh.uv_layers[keep].name = UV_NAME
        mesh.uv_layers.active = mesh.uv_layers[UV_NAME]

    def _apply_transforms(self, objs):
        if not objs:
            return
        expected = {}
        for obj in objs:
            m = obj.matrix_world.copy()
            if m.to_3x3().determinant() < 0 and len(obj.data.polygons):
                nmat = m.to_3x3().inverted_safe().transposed()
                expected[obj.name] = (nmat @ obj.data.polygons[0].normal).normalized()
        with scene_context(self.scene, objs[0], objs):
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        for obj in objs:
            exp = expected.get(obj.name)
            if exp is not None and obj.data.polygons[0].normal.dot(exp) < 0:
                _flip_mesh(obj.data)

    def _write_low_attributes(self, obj, offset):
        mesh = obj.data
        n = len(mesh.vertices)
        co = np.empty(n * 3, np.float32)
        mesh.vertices.foreach_get("co", co)
        orig = co.reshape(-1, 3) - np.asarray(offset, np.float32)
        _set_attr(mesh, "zb_orig", "FLOAT_VECTOR", orig)
        _set_attr(mesh, "zb_part", "INT", np.full(n, int(obj["zb_part"]), np.int32))
        _set_attr(mesh, "zb_ext", "FLOAT", np.full(n, float(obj["zb_ext"]), np.float32))
        _set_attr(mesh, "zb_has_cage", "INT", np.zeros(n, np.int32))
        _set_attr(mesh, "zb_cage_off", "FLOAT_VECTOR", np.zeros((n, 3), np.float32))

    def _attach_user_cage(self, rec):
        cage_obj = rec["cage_obj"]
        lows = rec["low_objs"]
        if len(lows) != 1 or len(lows[0].data.vertices) != len(cage_obj.data.vertices) or len(
            lows[0].data.polygons
        ) != len(cage_obj.data.polygons):
            self.warn("Cage %s does not match the topology of its low poly; using the automatic cage",
                      rec["cage"].name)
        else:
            low = lows[0].data
            n = len(low.vertices)
            a = np.empty(n * 3, np.float32)
            b = np.empty(n * 3, np.float32)
            low.vertices.foreach_get("co", a)
            cage_obj.data.vertices.foreach_get("co", b)
            _set_attr(low, "zb_cage_off", "FLOAT_VECTOR", (b - a).reshape(-1, 3))
            _set_attr(low, "zb_has_cage", "INT", np.ones(n, np.int32))
        self.retire(cage_obj)
        rec["cage_obj"] = None

    def _join(self, objs, name):
        if len(objs) > 1:
            with scene_context(self.scene, objs[0], objs):
                bpy.ops.object.join()
        low = objs[0]
        low.name = name
        mesh = low.data
        mesh.materials.clear()
        if len(mesh.polygons):
            mesh.polygons.foreach_set("material_index", np.zeros(len(mesh.polygons), np.int32))
        return low

    def _build_cage(self, ts_name, low):
        positions = cage_mod.cage_positions(low.data, self.max_extrusion[ts_name])
        mesh = low.data.copy()
        self.reg.meshes.append(mesh)
        cage_mod.apply_positions(mesh, positions)
        obj = bpy.data.objects.new("ZB_Cage_" + ts_name, mesh)
        self.reg.objects.append(obj)
        self.link(obj)
        obj.hide_render = True
        self.cages[ts_name] = obj
        user = float(self.settings.get("ray_distance") or 0.0)
        reach = cage_mod.max_offset(low.data, positions)
        self.ray_distance[ts_name] = user if user > 0 else max(reach * 2.0, 1e-4)

    def _orig_bounds(self, low):
        attr = low.data.attributes.get("zb_orig")
        n = len(low.data.vertices)
        buf = np.empty(n * 3, np.float32)
        attr.data.foreach_get("vector", buf)
        buf = buf.reshape(-1, 3)
        return buf.min(axis=0), buf.max(axis=0)

    # ------------------------------------------------------------------ explode

    def _explode_offsets(self, records):
        dg = self.evaluated_depsgraph()
        boxes = []
        for rec in records:
            pts = []
            for hd in rec["highs"]:
                ev = hd.obj.evaluated_get(dg)
                pts.extend(hd.obj.matrix_world @ Vector(c) for c in ev.bound_box)
            for obj in rec["low_objs"] + ([rec["cage_obj"]] if rec.get("cage_obj") else []):
                pts.extend(obj.matrix_world @ Vector(c) for c in obj.evaluated_get(dg).bound_box)
            arr = np.array([tuple(p) for p in pts], np.float64)
            boxes.append((arr.min(axis=0), arr.max(axis=0)))
        maps = self.job["maps"]
        max_ext = max(float(r["pair"].get("extrusion", 0.01)) for r in records)
        reach = [4.0 * max_ext, 2.0 * float(self.settings.get("ray_distance") or 0.0)]
        if maps["ao"]["enabled"] and not maps["ao"].get("only_self"):
            reach.append(1.25 * float(maps["ao"]["distance"]))
        largest = max(float((hi - lo).max()) for lo, hi in boxes)
        gap = max(reach) + 0.05 * largest + 1e-3
        cursor = min(lo[0] for lo, _ in boxes)
        offsets = []
        for lo, hi in boxes:
            offsets.append(Vector((cursor - lo[0], 0.0, 0.0)))
            cursor += (hi[0] - lo[0]) + gap
        return offsets

    # ------------------------------------------------------------------ visibility per set

    def isolate(self, ts_name, self_bake=False):
        """Render visibility for baking ``ts_name``.

        Highs of all sets stay renderable (they occlude each other's AO unless
        exploded); lows of other sets and all cages are hidden.  Self bakes
        hide everything except the active low.
        """
        for name, low in self.lows.items():
            low.hide_render = name != ts_name
        for cage in self.cages.values():
            cage.hide_render = True
        for name, highs in self.highs.items():
            for hd in highs:
                hd.obj.hide_render = self_bake

    def cleanup(self):
        self.reg.cleanup()
        self.scene = None


def _set_attr(mesh, name, data_type, values):
    existing = mesh.attributes.get(name)
    if existing is not None:
        mesh.attributes.remove(existing)
    attr = mesh.attributes.new(name, data_type, "POINT")
    key = "vector" if data_type == "FLOAT_VECTOR" else "value"
    attr.data.foreach_set(key, np.ascontiguousarray(values).ravel())
    return attr


def _flip_mesh(mesh):
    """Invert face winding, keeping custom normals pointing the same way."""
    custom = None
    if mesh.has_custom_normals:
        cn = compat.corner_normals(mesh).copy()
        lv = np.empty(len(mesh.loops), np.int32)
        mesh.loops.foreach_get("vertex_index", lv)
        lp = np.empty(len(mesh.loops), np.int32)
        for poly in mesh.polygons:
            lp[poly.loop_start : poly.loop_start + poly.loop_total] = poly.index
        custom = {(int(p), int(v)): tuple(n) for p, v, n in zip(lp, lv, cn)}
    mesh.flip_normals()
    if custom is not None:
        lv = np.empty(len(mesh.loops), np.int32)
        mesh.loops.foreach_get("vertex_index", lv)
        normals = [None] * len(mesh.loops)
        for poly in mesh.polygons:
            for li in range(poly.loop_start, poly.loop_start + poly.loop_total):
                normals[li] = custom.get((poly.index, int(lv[li])), (0.0, 0.0, 1.0))
        mesh.normals_split_custom_set(normals)
    mesh.update()
