# SPDX-License-Identifier: GPL-3.0-or-later
"""Texel density: texture pixels per meter of surface.

Density is measured per triangle as ``resolution * sqrt(uv_area / world_area)``
and summarized area-weighted, so tiny or degenerate faces do not skew it.
"""

import math

import numpy as np


def _triangles(mesh, matrix, uv_layer):
    mesh.calc_loop_triangles()
    nt = len(mesh.loop_triangles)
    if nt == 0:
        return None, None
    loops = np.empty(nt * 3, np.int32)
    mesh.loop_triangles.foreach_get("loops", loops)
    verts = np.empty(nt * 3, np.int32)
    mesh.loop_triangles.foreach_get("vertices", verts)
    co = np.empty(len(mesh.vertices) * 3, np.float32)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3).astype(np.float64)
    m = np.array(matrix, np.float64)
    co = co @ m[:3, :3].T + m[:3, 3]
    uv = np.empty(len(mesh.loops) * 2, np.float32)
    uv_layer.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2).astype(np.float64)
    p = co[verts].reshape(-1, 3, 3)
    t = uv[loops].reshape(-1, 3, 2)
    world = 0.5 * np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1)
    e1 = t[:, 1] - t[:, 0]
    e2 = t[:, 2] - t[:, 0]
    uv_area = 0.5 * np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0])
    return world, uv_area


def _weighted_percentile(values, weights, q):
    order = np.argsort(values)
    v = values[order]
    w = np.cumsum(weights[order])
    return float(v[np.searchsorted(w, q * w[-1])])


def measure(mesh, matrix, uv_layer, resolution, meters_per_unit=1.0):
    """Return ``(average, low, high)`` px/m or None when nothing can be measured.

    ``low``/``high`` are the 5th and 95th area-weighted percentiles: how even
    the density is across the object.
    """
    world, uv_area = _triangles(mesh, matrix, uv_layer)
    if world is None:
        return None
    world = world * meters_per_unit ** 2
    ok = world > 1e-12
    if not ok.any() or uv_area[ok].sum() <= 0:
        return None
    world, uv_area = world[ok], uv_area[ok]
    average = resolution * math.sqrt(uv_area.sum() / world.sum())
    per_tri = resolution * np.sqrt(uv_area / world)
    low = _weighted_percentile(per_tri, world, 0.05)
    high = _weighted_percentile(per_tri, world, 0.95)
    return average, low, high


def resolution_for(density, current_density, resolution, sizes=(256, 512, 1024, 2048, 4096, 8192)):
    """Smallest power-of-two texture size that reaches ``density`` with the current UVs."""
    if current_density <= 0:
        return None
    needed = resolution * density / current_density
    for size in sizes:
        if size >= needed * 0.95:
            return size
    return sizes[-1]


def scale_uvs(mesh, uv_layer, factor):
    """Scale all UVs of ``uv_layer`` around the centre of their bounding box."""
    uv = np.empty(len(mesh.loops) * 2, np.float32)
    uv_layer.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    if not len(uv):
        return False
    centre = 0.5 * (uv.min(axis=0) + uv.max(axis=0))
    uv = (uv - centre) * factor + centre
    uv_layer.data.foreach_set("uv", uv.astype(np.float32).ravel())
    mesh.update()
    return bool(uv.min() < -1e-4 or uv.max() > 1.0 + 1e-4)
