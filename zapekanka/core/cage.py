# SPDX-License-Identifier: GPL-3.0-or-later
"""Automatic cage generation.

The cage is the low poly pushed outwards along *averaged* normals.  Normals are
averaged over all vertices that share a position (within the same part), so
hard edges and split vertices never open gaps in the cage, and offsets are
compensated so every face moves out by roughly the requested distance.
"""

import numpy as np


def _read_attr(mesh, name, comps, dtype, default):
    n = len(mesh.vertices)
    attr = mesh.attributes.get(name)
    if attr is None or attr.domain != "POINT":
        return np.full((n, comps) if comps > 1 else n, default, dtype=dtype)
    key = "vector" if comps == 3 else "value"
    raw = np.int32 if np.issubdtype(dtype, np.integer) else np.float32
    if attr.data_type == "BOOLEAN":
        raw = bool
    buf = np.empty(n * comps, dtype=raw)
    attr.data.foreach_get(key, buf)
    buf = buf.astype(dtype)
    return buf.reshape(-1, comps) if comps > 1 else buf


def averaged_normals(co, loop_vert, loop_poly, poly_normals, starts, totals, part, eps):
    """Angle-weighted normals averaged over coincident vertices of the same part."""
    nl = len(loop_vert)
    base = np.repeat(starts, totals)
    count = np.repeat(totals, totals)
    local = np.arange(nl) - base
    nxt = base + (local + 1) % count
    prv = base + (local - 1) % count
    p = co[loop_vert]
    a = co[loop_vert[nxt]] - p
    b = co[loop_vert[prv]] - p
    la = np.linalg.norm(a, axis=1)
    lb = np.linalg.norm(b, axis=1)
    denom = np.maximum(la * lb, 1e-20)
    cosang = np.clip(np.einsum("ij,ij->i", a, b) / denom, -1.0, 1.0)
    angle = np.arccos(cosang)
    angle[(la < 1e-12) | (lb < 1e-12)] = 0.0
    weighted = poly_normals[loop_poly] * angle[:, None]

    key = np.floor(co / eps + 0.5).astype(np.int64)
    key = np.column_stack([key, part.astype(np.int64)])
    _, cluster = np.unique(key, axis=0, return_inverse=True)
    cluster = cluster.reshape(-1)
    ncl = int(cluster.max()) + 1 if len(cluster) else 0
    acc = np.zeros((ncl, 3), np.float64)
    np.add.at(acc, cluster[loop_vert], weighted)
    length = np.linalg.norm(acc, axis=1)
    good = length > 1e-12
    acc[good] /= length[good][:, None]
    # fallback for degenerate clusters: plain sum of face normals
    if not good.all():
        plain = np.zeros((ncl, 3), np.float64)
        np.add.at(plain, cluster[loop_vert], poly_normals[loop_poly])
        pl = np.linalg.norm(plain, axis=1)
        fix = ~good & (pl > 1e-12)
        acc[fix] = plain[fix] / pl[fix][:, None]
    normals = acc[cluster]
    # uniform thickness: the most tilted adjacent face controls the push length
    dots = np.einsum("ij,ij->i", normals[loop_vert], poly_normals[loop_poly])
    min_dot = np.ones(ncl, np.float64)
    np.minimum.at(min_dot, cluster[loop_vert], dots)
    factor = 1.0 / np.clip(min_dot[cluster], 0.3, 1.0)
    return normals, factor


def cage_positions(mesh, default_extrusion=0.01):
    """Return displaced vertex positions for ``mesh`` (world space mesh).

    Reads the per-vertex attributes written by the session:
    ``zb_ext`` (extrusion), ``zb_part`` (part id), and optionally
    ``zb_cage_off`` + ``zb_has_cage`` for user supplied cages.
    """
    nv = len(mesh.vertices)
    np_ = len(mesh.polygons)
    nl = len(mesh.loops)
    co = np.empty(nv * 3, np.float32)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3).astype(np.float64)
    if nv == 0 or np_ == 0:
        return co
    starts = np.empty(np_, np.int32)
    totals = np.empty(np_, np.int32)
    mesh.polygons.foreach_get("loop_start", starts)
    mesh.polygons.foreach_get("loop_total", totals)
    starts = starts.astype(np.int64)
    totals = totals.astype(np.int64)
    pn = np.empty(np_ * 3, np.float32)
    mesh.polygons.foreach_get("normal", pn)
    pn = pn.reshape(-1, 3).astype(np.float64)
    loop_vert = np.empty(nl, np.int32)
    mesh.loops.foreach_get("vertex_index", loop_vert)
    loop_vert = loop_vert.astype(np.int64)
    loop_poly = np.repeat(np.arange(np_), totals)

    part = _read_attr(mesh, "zb_part", 1, np.int64, 0)
    ext = _read_attr(mesh, "zb_ext", 1, np.float64, default_extrusion)
    span = co.max(axis=0) - co.min(axis=0)
    eps = max(float(np.linalg.norm(span)) * 1e-6, 1e-7)

    normals, factor = averaged_normals(co, loop_vert, loop_poly, pn, starts, totals, part, eps)
    offset = normals * (ext * factor)[:, None]

    if mesh.attributes.get("zb_has_cage") is not None:
        has = _read_attr(mesh, "zb_has_cage", 1, np.int64, 0).astype(bool)
        if has.any():
            user = _read_attr(mesh, "zb_cage_off", 3, np.float64, 0.0)
            offset[has] = user[has]
    return co + offset


def apply_positions(mesh, positions):
    mesh.vertices.foreach_set("co", np.asarray(positions, np.float32).ravel())
    mesh.update()


def max_offset(mesh, positions):
    co = np.empty(len(mesh.vertices) * 3, np.float32)
    mesh.vertices.foreach_get("co", co)
    d = np.linalg.norm(np.asarray(positions).reshape(-1, 3) - co.reshape(-1, 3), axis=1)
    return float(d.max()) if len(d) else 0.0
