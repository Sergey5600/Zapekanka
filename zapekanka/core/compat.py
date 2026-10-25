# SPDX-License-Identifier: GPL-3.0-or-later
"""Small helpers that hide API differences between Blender 4.2 and 5.x."""

import warnings

import bpy

BLENDER_VERSION = bpy.app.version

_COLORSPACE_CANDIDATES = {
    "data": ("Non-Color", "Generic Data", "Raw", "Utility - Raw"),
    "srgb": ("sRGB", "sRGB - Texture", "Utility - sRGB - Texture"),
    "linear": ("Linear Rec.709", "Linear", "Linear BT.709", "scene_linear"),
}


def set_colorspace(image, kind):
    """Assign a colorspace by role ('data', 'srgb' or 'linear') and return the name used."""
    for name in _COLORSPACE_CANDIDATES[kind]:
        try:
            image.colorspace_settings.name = name
            return name
        except (TypeError, ValueError):
            continue
    if kind == "data":
        try:
            image.colorspace_settings.is_data = True
        except AttributeError:
            pass
    return image.colorspace_settings.name


def new_material(name):
    """Create a material that is guaranteed to have an (empty) node tree."""
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            mat.use_nodes = True
    nt = mat.node_tree
    for node in list(nt.nodes):
        nt.nodes.remove(node)
    return mat


def ensure_node_tree(mat):
    if mat.node_tree is None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            mat.use_nodes = True
    return mat.node_tree


def material_uses_nodes(mat):
    if mat is None or mat.node_tree is None:
        return False
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return bool(getattr(mat, "use_nodes", True))


def find_socket(sockets, name, type_=None):
    """Return the first enabled socket with ``name`` (and optional ``type``)."""
    fallback = None
    for sock in sockets:
        if sock.name != name and sock.identifier != name:
            continue
        if type_ is not None and sock.type != type_:
            continue
        if getattr(sock, "enabled", True):
            return sock
        fallback = fallback or sock
    return fallback


def corner_normals(mesh):
    """Per-corner normals as a flat float list (Blender 4.1+ API)."""
    import numpy as np

    out = np.empty(len(mesh.loops) * 3, np.float32)
    mesh.corner_normals.foreach_get("vector", out)
    return out.reshape(-1, 3)


def set_material_alpha_mode(mat, use_alpha):
    """Configure EEVEE transparency in a version independent way."""
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "DITHERED"
    if use_alpha and hasattr(mat, "blend_method"):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                mat.blend_method = "HASHED"
            except (TypeError, AttributeError):
                pass


def link_object(collection, obj):
    if obj.name not in collection.objects:
        collection.objects.link(obj)
