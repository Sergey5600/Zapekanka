# SPDX-License-Identifier: GPL-3.0-or-later
"""Pre-flight checks run before baking, with optional fixes.

Checks look at the *evaluated* low poly (what the baker sees).  Fixes modify
the user's objects, so they only run on explicit request and are undoable.
"""

import os

import bmesh
import bpy
import numpy as np
from bpy.app.translations import pgettext_iface


class Issue:
    """A pre-flight finding. ``message`` is a string or ``(template, *args)``
    so the UI can translate the template before formatting."""

    def __init__(self, severity, code, message, obj=None, pair=None, fix=None):
        self.severity = severity
        self.code = code
        if isinstance(message, tuple):
            self.template, self.args = message[0], tuple(message[1:])
        else:
            self.template, self.args = message, ()
        self.message = self.template % self.args if self.args else self.template
        self.object_name = obj.name if obj is not None else ""
        self.pair_name = pair.name if pair is not None else ""
        self.fix = fix  # label of the fix, None if not fixable


FIX_LABELS = {
    "SCALE": "Apply Scale",
    "NEG_SCALE": "Apply Scale",
    "NO_UV": "Smart UV Project",
    "UV_OVERLAP": "Pack Islands",
    "FLIPPED": "Recalculate Normals",
    "DOUBLES": "Merge by Distance",
    "CUSTOM_NORMALS": "Clear Custom Normals",
    "NOT_TRIANGULATED": "Add Triangulate Modifier",
}


# ----------------------------------------------------------------------------
# Mesh analysis helpers


def _evaluated_mesh(obj, depsgraph):
    ev = obj.evaluated_get(depsgraph)
    return ev, ev.to_mesh()


def rasterize_uv(mesh, uv_layer, res=256):
    """Return (pixel_index, triangle_index) pairs for pixel centres strictly inside UV triangles."""
    mesh.calc_loop_triangles()
    nt = len(mesh.loop_triangles)
    if nt == 0:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    tl = np.empty(nt * 3, np.int32)
    mesh.loop_triangles.foreach_get("loops", tl)
    uv = np.empty(len(mesh.loops) * 2, np.float32)
    uv_layer.data.foreach_get("uv", uv)
    tri = uv.reshape(-1, 2)[tl.reshape(-1, 3)].astype(np.float64) * res  # (nt, 3, 2)
    mn = np.floor(tri.min(axis=1)).astype(np.int64)
    mx = np.floor(tri.max(axis=1)).astype(np.int64)
    mn = np.clip(mn, 0, res - 1)
    mx = np.clip(mx, 0, res - 1)
    w = mx[:, 0] - mn[:, 0] + 1
    h = mx[:, 1] - mn[:, 1] + 1
    count = w * h
    pix_list, isl_list = [], []
    chunk = 200000
    starts = np.concatenate([[0], np.cumsum(count)])
    total = int(starts[-1])
    if total == 0:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    # process triangles in batches to bound memory
    idx = 0
    while idx < nt:
        end = idx
        acc = 0
        while end < nt and (acc + count[end] <= chunk or end == idx):
            acc += count[end]
            end += 1
        sel = np.arange(idx, end)
        c = count[sel]
        t = np.repeat(sel, c)
        local = np.arange(int(c.sum())) - np.repeat(np.cumsum(c) - c, c)
        px = mn[t, 0] + local % w[t]
        py = mn[t, 1] + local // w[t]
        p = np.column_stack([px + 0.5, py + 0.5])
        a, b, cc = tri[t, 0], tri[t, 1], tri[t, 2]
        v0, v1, v2 = cc - a, b - a, p - a
        d00 = (v0 * v0).sum(1)
        d01 = (v0 * v1).sum(1)
        d02 = (v0 * v2).sum(1)
        d11 = (v1 * v1).sum(1)
        d12 = (v1 * v2).sum(1)
        den = d00 * d11 - d01 * d01
        ok = np.abs(den) > 1e-12
        inv = np.where(ok, 1.0 / np.where(ok, den, 1.0), 0.0)
        u = (d11 * d02 - d01 * d12) * inv
        v = (d00 * d12 - d01 * d02) * inv
        eps = 1e-6
        inside = ok & (u > eps) & (v > eps) & (u + v < 1.0 - eps)
        pix_list.append((py[inside] * res + px[inside]).astype(np.int64))
        isl_list.append(t[inside].astype(np.int64))
        idx = end
    return np.concatenate(pix_list), np.concatenate(isl_list)


def overlap_ratio(pixels, owners):
    """Fraction of covered pixels claimed by more than one owner (triangle or object)."""
    if len(pixels) == 0:
        return 0.0
    pairs = np.unique(np.column_stack([pixels, owners]), axis=0)
    pix, counts = np.unique(pairs[:, 0], return_counts=True)
    return float((counts > 1).sum()) / float(len(pix))


def inconsistent_winding_edges(bm):
    count = 0
    for edge in bm.edges:
        if len(edge.link_loops) == 2:
            l1, l2 = edge.link_loops
            if l1.vert == l2.vert:
                count += 1
    return count


def signed_volume(bm):
    vol = 0.0
    for face in bm.faces:
        verts = [v.co for v in face.verts]
        for i in range(1, len(verts) - 1):
            vol += verts[0].dot(verts[i].cross(verts[i + 1]))
    return vol / 6.0


# ----------------------------------------------------------------------------
# Checks


class _SelectionPair:
    """Stands in for the pair Bake All creates for a selected object."""

    def __init__(self, obj):
        self.name = obj.name
        self.set_name = obj.name
        self.cage = None
        self.use_custom_extrusion = False
        self._obj = obj

    def low_objects(self):
        return [self._obj]

    def high_objects(self):
        return []


def run_checks(context):
    s = context.scene.zapekanka
    depsgraph = context.evaluated_depsgraph_get()
    issues = []
    pairs = [p for p in s.pairs if p.enabled]
    if not pairs and not s.pairs:
        # Bake All falls back to the selection; check what it would bake.
        pairs = [_SelectionPair(o) for o in context.selected_objects if o.type == "MESH" and not o.get("zb_preview")]
        if pairs:
            issues.append(Issue("INFO", "SELECTION", "No pairs: the selected objects will be baked with their own "
                                                     "materials"))
    if not pairs:
        issues.append(Issue("ERROR", "NO_PAIRS", "Nothing to bake. Name objects Name_low / Name_high and press "
                                                 "Detect Pairs, or select the objects to bake"))
        return issues

    out_dir = s.output_dir
    if out_dir.startswith("//") and not bpy.data.filepath:
        issues.append(Issue("ERROR", "UNSAVED", "Output folder is relative but the file is not saved. "
                                                "Save the .blend or choose an absolute folder"))
    else:
        path = bpy.path.abspath(out_dir)
        parent = path if os.path.isdir(path) else os.path.dirname(path.rstrip("/\\"))
        if parent and os.path.isdir(parent) and not os.access(parent, os.W_OK):
            issues.append(Issue("ERROR", "NOT_WRITABLE", ("Output folder is not writable: %s", path)))

    w, h = s.resolution_xy()
    ss = int(s.supersample)
    if max(w, h) * ss > 16384:
        issues.append(Issue("INFO", "TILED", ("%dx%d with %dx supersampling will be baked in tiles "
                                              "(needs time and RAM)", w, h, ss)))
    if s.preset == "ROBLOX" and max(w, h) > 1024:
        issues.append(Issue("WARNING", "ROBLOX_RES", "Roblox accepts SurfaceAppearance textures up to 1024px"))
    if s.cage_extrusion <= 0.0 and any(not p.use_custom_extrusion for p in pairs):
        issues.append(Issue("WARNING", "NO_EXTRUSION", "Cage extrusion is 0: rays start on the low poly "
                                                       "surface and miss details above it"))

    by_set = {}
    for pair in pairs:
        lows = pair.low_objects()
        if not lows:
            issues.append(Issue("ERROR", "NO_LOW", "Pair has no low poly", pair=pair))
            continue
        by_set.setdefault(pair.set_name, []).append(pair)
        highs = pair.high_objects()
        if not highs:
            issues.append(Issue("INFO", "NO_HIGH", "No high poly: the low poly's own materials will be baked",
                                pair=pair))
        for obj in lows:
            issues.extend(_check_low(obj, pair, depsgraph, s))
        for obj in highs:
            issues.extend(_check_high(obj, pair, lows, depsgraph))
        if pair.cage is not None and len(lows) != 1:
            issues.append(Issue("WARNING", "CAGE_MULTI", "Custom cage only works with a single low poly; "
                                                         "the automatic cage will be used", pair=pair))

    for set_name, set_pairs in by_set.items():
        lows = [o for p in set_pairs for o in p.low_objects()]
        if len(lows) > 1:
            ratio = _cross_object_overlap(lows, depsgraph, s.uv_map)
            if ratio > 0.002:
                issues.append(Issue(
                    "ERROR", "SET_OVERLAP",
                    ("Texture set '%s': UVs of different low polys overlap (%.1f%%). Arrange them in one "
                     "UV layout or use separate texture sets", set_name, ratio * 100.0)))
    issues.extend(_check_images(pairs))
    order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
    issues.sort(key=lambda i: order[i.severity])
    return issues


def _uv_layer(mesh, name):
    if name:
        layer = mesh.uv_layers.get(name)
        if layer is not None:
            return layer
    return mesh.uv_layers.active


def _check_low(obj, pair, depsgraph, s):
    issues = []
    scale = obj.matrix_world.to_scale()
    if min(scale) < 0 or obj.matrix_world.to_3x3().determinant() < 0:
        issues.append(Issue("WARNING", "NEG_SCALE", "Negative scale (mirrored object)", obj, pair, "NEG_SCALE"))
    elif max(abs(v - 1.0) for v in obj.scale) > 1e-4:
        issues.append(Issue("WARNING", "SCALE", ("Unapplied scale %.3g, %.3g, %.3g",) + tuple(obj.scale),
                            obj, pair, "SCALE"))
    ev, mesh = _evaluated_mesh(obj, depsgraph)
    try:
        if len(mesh.polygons) == 0:
            issues.append(Issue("ERROR", "NO_FACES", "Low poly has no faces", obj, pair))
            return issues
        layer = _uv_layer(mesh, s.uv_map)
        if layer is None:
            issues.append(Issue("ERROR", "NO_UV", "No UV map", obj, pair, "NO_UV"))
        else:
            if s.uv_map and mesh.uv_layers.get(s.uv_map) is None:
                issues.append(Issue("WARNING", "UV_NAME", ("UV map '%s' not found, the active one is used",
                                    s.uv_map), obj, pair))
            uv = np.empty(len(mesh.loops) * 2, np.float32)
            layer.data.foreach_get("uv", uv)
            if len(uv) and (uv.min() < -1e-4 or uv.max() > 1.0 + 1e-4):
                issues.append(Issue("WARNING", "UV_RANGE", "UVs outside the 0-1 range are not baked", obj, pair))
            # A pixel inside two triangles means stacked, mirrored or folded UVs.
            pix, tri = rasterize_uv(mesh, layer)
            ratio = overlap_ratio(pix, tri)
            if ratio > 0.002:
                issues.append(Issue("WARNING", "UV_OVERLAP", ("Overlapping UV islands (%.1f%% of the UV area). "
                                    "Stacked/mirrored islands are baked once", ratio * 100.0),
                                    obj, pair, "UV_OVERLAP"))
        non_tris = sum(1 for p in mesh.polygons if p.loop_total != 3)
        if non_tris and not s.triangulate:
            issues.append(Issue("WARNING", "NOT_TRIANGULATED", ("%d faces are not triangles: engines may "
                                "triangulate differently and break the tangent basis", non_tris),
                                obj, pair, "NOT_TRIANGULATED"))
        if mesh.has_custom_normals:
            issues.append(Issue("INFO", "CUSTOM_NORMALS", "Custom normals: export them with the mesh "
                                "(FBX: normals + tangents) or the bake will not match", obj, pair,
                                "CUSTOM_NORMALS"))
        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            flipped = inconsistent_winding_edges(bm)
            non_manifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)
            open_edges = sum(1 for e in bm.edges if e.is_boundary)
            closed = open_edges == 0 and non_manifold == 0
            if flipped:
                issues.append(Issue("WARNING", "FLIPPED", ("%d edges between faces with opposite normals",
                                    flipped), obj, pair, "FLIPPED"))
            elif closed and signed_volume(bm) < 0:
                issues.append(Issue("WARNING", "FLIPPED", "Normals point inwards", obj, pair, "FLIPPED"))
            if non_manifold:
                issues.append(Issue("WARNING", "NON_MANIFOLD", ("%d non-manifold edges (3+ faces per edge)",
                                    non_manifold), obj, pair))
            loose = sum(1 for v in bm.verts if not v.link_faces)
            if loose:
                issues.append(Issue("INFO", "LOOSE", ("%d loose vertices/edges", loose), obj, pair, "DOUBLES"))
            doubles = _count_doubles(bm)
            if doubles:
                issues.append(Issue("WARNING", "DOUBLES", ("%d duplicate vertices", doubles), obj, pair, "DOUBLES"))
        finally:
            bm.free()
    finally:
        ev.to_mesh_clear()
    return issues


def _count_doubles(bm, dist=1e-5):
    co = np.array([v.co[:] for v in bm.verts], np.float64)
    if len(co) < 2:
        return 0
    keys = np.floor(co / dist + 0.5).astype(np.int64)
    _, counts = np.unique(keys, axis=0, return_counts=True)
    return int((counts - 1)[counts > 1].sum())


def _bbox(obj, depsgraph):
    from mathutils import Vector

    ev = obj.evaluated_get(depsgraph)
    pts = [obj.matrix_world @ Vector(c) for c in ev.bound_box]
    arr = np.array([p[:] for p in pts])
    return arr.min(axis=0), arr.max(axis=0)


def _check_high(obj, pair, lows, depsgraph):
    issues = []
    if obj.type != "MESH":
        issues.append(Issue("INFO", "HIGH_CONVERT", ("%s will be converted to a mesh for baking", obj.type),
                            obj, pair))
    if obj.matrix_world.to_3x3().determinant() < 0:
        issues.append(Issue("INFO", "HIGH_NEG_SCALE", "High poly has negative scale", obj, pair))
    lo, hi = _bbox(obj, depsgraph)
    overlap = False
    for low in lows:
        llo, lhi = _bbox(low, depsgraph)
        if np.all(lo <= lhi + 1e-4) and np.all(llo <= hi + 1e-4):
            overlap = True
    if not overlap:
        issues.append(Issue("WARNING", "NO_OVERLAP", "High poly does not overlap its low poly: rays will miss",
                            obj, pair))
    for slot in obj.material_slots:
        if slot.material is None:
            issues.append(Issue("INFO", "EMPTY_SLOT", "Empty material slot (baked as neutral grey)", obj, pair))
            break
    return issues


def _cross_object_overlap(lows, depsgraph, uv_map):
    pixels, islands = [], []
    offset = 0
    for obj in lows:
        ev, mesh = _evaluated_mesh(obj, depsgraph)
        try:
            layer = _uv_layer(mesh, uv_map)
            if layer is None or len(mesh.polygons) == 0:
                continue
            # one id per object: only overlaps *between* objects matter here
            pix, _ = rasterize_uv(mesh, layer)
            pixels.append(pix)
            islands.append(np.full(len(pix), offset, np.int64))
            offset += 1
        finally:
            ev.to_mesh_clear()
    if len(pixels) < 2:
        return 0.0
    return overlap_ratio(np.concatenate(pixels), np.concatenate(islands))


def _check_images(pairs):
    issues = []
    seen = set()
    for pair in pairs:
        for obj in pair.high_objects() + ([] if pair.high_objects() else pair.low_objects()):
            for slot in obj.material_slots:
                mat = slot.material
                if mat is None or mat.node_tree is None:
                    continue
                for node in mat.node_tree.nodes:
                    img = getattr(node, "image", None)
                    if img is None or img.name in seen:
                        continue
                    seen.add(img.name)
                    if img.is_dirty:
                        issues.append(Issue("WARNING", "DIRTY_IMAGE", ("Image '%s' has unsaved changes: background "
                                             "bakes use the saved version", img.name), obj, pair))
                    elif img.source == "FILE" and not img.packed_file:
                        path = bpy.path.abspath(img.filepath, library=img.library)
                        if not os.path.isfile(path):
                            issues.append(Issue("WARNING", "MISSING_IMAGE", ("Image file not found: %s", path),
                                                obj, pair))
    return issues


# ----------------------------------------------------------------------------
# Fixes


def apply_fix(context, code, obj):
    """Apply fix ``code`` to ``obj``. Returns a message."""
    if obj is None:
        return "Object not found"
    if code in ("SCALE", "NEG_SCALE"):
        _with_object(context, obj, lambda: bpy.ops.object.transform_apply(
            location=False, rotation=False, scale=True, isolate_users=True))
        return "Applied scale on %s" % obj.name
    if code == "NO_UV":
        def unwrap():
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.uv.smart_project(island_margin=0.01)
            bpy.ops.object.mode_set(mode="OBJECT")
        if not obj.data.uv_layers:
            obj.data.uv_layers.new(name="UVMap")
        _with_object(context, obj, unwrap)
        return "Unwrapped %s" % obj.name
    if code == "UV_OVERLAP":
        def pack():
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.uv.select_all(action="SELECT")
            bpy.ops.uv.pack_islands(margin=0.01, rotate=True)
            bpy.ops.object.mode_set(mode="OBJECT")
        _with_object(context, obj, pack)
        return "Packed UV islands of %s" % obj.name
    if code == "FLIPPED":
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        return "Recalculated normals of %s" % obj.name
    if code == "DOUBLES":
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        before = len(bm.verts)
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
        loose = [v for v in bm.verts if not v.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context="VERTS")
        removed = before - len(bm.verts)
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        return "Removed %d vertices from %s" % (removed, obj.name)
    if code == "CUSTOM_NORMALS":
        _with_object(context, obj, lambda: bpy.ops.mesh.customdata_custom_splitnormals_clear())
        return "Cleared custom normals of %s" % obj.name
    if code == "NOT_TRIANGULATED":
        if not any(m.type == "TRIANGULATE" for m in obj.modifiers):
            mod = obj.modifiers.new("Triangulate", "TRIANGULATE")
            mod.quad_method = "BEAUTY"
            mod.ngon_method = "BEAUTY"
            if hasattr(mod, "keep_custom_normals"):
                mod.keep_custom_normals = True
        return "Added a Triangulate modifier to %s" % obj.name
    return "No fix available"


def _with_object(context, obj, fn):
    view_layer = context.view_layer
    if view_layer.objects.get(obj.name) is None:
        raise RuntimeError("%s is not in the current view layer" % obj.name)
    prev_active = view_layer.objects.active
    prev_sel = [o for o in context.selected_objects]
    hidden = obj.hide_get()
    if hidden:
        obj.hide_set(False)
    for o in prev_sel:
        o.select_set(False)
    obj.select_set(True)
    view_layer.objects.active = obj
    try:
        with context.temp_override(active_object=obj, object=obj, selected_objects=[obj],
                                   selected_editable_objects=[obj]):
            if obj.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            fn()
    finally:
        obj.select_set(False)
        for o in prev_sel:
            try:
                o.select_set(True)
            except ReferenceError:
                pass
        view_layer.objects.active = prev_active
        if hidden:
            obj.hide_set(True)


def store_issues(settings, issues):
    settings.issues.clear()
    for issue in issues:
        item = settings.issues.add()
        item.severity = issue.severity
        item.code = issue.code
        template = pgettext_iface(issue.template)
        try:
            item.message = template % issue.args if issue.args else template
        except (TypeError, ValueError):
            item.message = issue.message
        item.object_name = issue.object_name
        item.pair_name = issue.pair_name
        item.fixable = issue.fix is not None
        item.fix_label = FIX_LABELS.get(issue.fix, "") if issue.fix else ""
    settings.preflight_ran = True


def blocking_errors(issues):
    return [i for i in issues if i.severity == "ERROR"]

