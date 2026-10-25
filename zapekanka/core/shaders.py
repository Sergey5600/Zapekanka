# SPDX-License-Identifier: GPL-3.0-or-later
"""Temporary shader networks used by the baker.

Everything created here is registered with a :class:`Registry` so the bake
session can delete it afterwards.  Source materials are never modified: PBR
channel extraction works on copies of materials and node groups.
"""

import colorsys
import hashlib

import bpy

from . import compat

# Shader node -> (base colour socket, roughness socket or constant, metallic)
_BSDF_TABLE = {
    "ShaderNodeBsdfPrincipled": ("Base Color", "Roughness", "Metallic"),
    "ShaderNodeBsdfDiffuse": ("Color", 1.0, 0.0),
    "ShaderNodeBsdfAnisotropic": ("Color", "Roughness", 1.0),
    "ShaderNodeBsdfGlossy": ("Color", "Roughness", 1.0),
    "ShaderNodeBsdfMetallic": ("Base Color", "Roughness", 1.0),
    "ShaderNodeBsdfGlass": ("Color", "Roughness", 0.0),
    "ShaderNodeBsdfRefraction": ("Color", "Roughness", 0.0),
    "ShaderNodeBsdfTranslucent": ("Color", 1.0, 0.0),
    "ShaderNodeBsdfSheen": ("Color", 1.0, 0.0),
    "ShaderNodeBsdfVelvet": ("Color", 1.0, 0.0),
    "ShaderNodeBsdfToon": ("Color", 0.5, 0.0),
    "ShaderNodeSubsurfaceScattering": ("Color", 1.0, 0.0),
    "ShaderNodeBsdfHair": ("Color", 0.5, 0.0),
    "ShaderNodeBsdfHairPrincipled": ("Color", "Roughness", 0.0),
    "ShaderNodeEeveeSpecular": ("Base Color", "Roughness", 0.0),
    "ShaderNodeBsdfRayPortal": (None, 1.0, 0.0),
}
_TRANSPARENT = {"ShaderNodeBsdfTransparent", "ShaderNodeHoldout"}
_EMISSION = {"ShaderNodeEmission"}


class Registry:
    """Collects temporary datablocks for later removal."""

    def __init__(self):
        self.materials = []
        self.node_groups = []
        self.images = []
        self.meshes = []
        self.objects = []
        self.scenes = []
        self._cache = {}

    def material(self, name):
        mat = compat.new_material(name)
        self.materials.append(mat)
        return mat

    def cached(self, key, factory):
        if key not in self._cache:
            self._cache[key] = factory()
        return self._cache[key]

    def cleanup(self):
        def _remove(collection, items):
            for item in reversed(items):
                try:
                    collection.remove(item, do_unlink=True)
                except (ReferenceError, RuntimeError, TypeError):
                    try:
                        collection.remove(item)
                    except (ReferenceError, RuntimeError):
                        pass
            items.clear()

        # Scenes first: freeing the private scene drops its view layers, so no
        # stale bases can point at the objects removed afterwards.
        for scene in reversed(self.scenes):
            try:
                bpy.data.scenes.remove(scene)
            except (ReferenceError, RuntimeError):
                pass
        self.scenes.clear()
        _remove(bpy.data.objects, self.objects)
        _remove(bpy.data.meshes, self.meshes)
        _remove(bpy.data.materials, self.materials)
        _remove(bpy.data.node_groups, self.node_groups)
        _remove(bpy.data.images, self.images)
        self._cache.clear()


# ----------------------------------------------------------------------------
# Small node helpers


def _nodes(nt, idname, location=(0, 0)):
    node = nt.nodes.new(idname)
    node.location = location
    return node


def _emission_output(nt, location=(400, 0)):
    out = _nodes(nt, "ShaderNodeOutputMaterial", location)
    out.target = "ALL"
    em = _nodes(nt, "ShaderNodeEmission", (location[0] - 200, location[1]))
    em.inputs["Strength"].default_value = 1.0
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return em


def _combine_rgb(nt, location=(0, 0)):
    node = _nodes(nt, "ShaderNodeCombineColor", location)
    node.mode = "RGB"
    return node


def _feed(nt, value, socket):
    """Connect ``value`` (a socket or a constant) to ``socket``."""
    if isinstance(value, bpy.types.NodeSocket):
        nt.links.new(value, socket)
    elif isinstance(value, (tuple, list)):
        if len(socket.default_value) == len(value):
            socket.default_value = value
        else:
            socket.default_value = tuple(value[:3]) + (1.0,) * (len(socket.default_value) - 3)
    else:
        try:
            socket.default_value = value
        except TypeError:
            socket.default_value = (value, value, value, 1.0)[: len(socket.default_value)]


def add_target_image_node(nt, image, location=(-600, 400)):
    node = _nodes(nt, "ShaderNodeTexImage", location)
    node.image = image
    node.name = "ZB_BakeTarget"
    node.label = "Zapekanka bake target"
    for other in nt.nodes:
        other.select = False
    node.select = True
    nt.nodes.active = node
    return node


def target_material(reg, name, image):
    mat = reg.material(name)
    add_target_image_node(mat.node_tree, image)
    return mat


# ----------------------------------------------------------------------------
# Uniform override materials (applied to high polys via geometry nodes)


def _vector_math(nt, op, a, b=None, location=(0, 0)):
    node = _nodes(nt, "ShaderNodeVectorMath", location)
    node.operation = op
    _feed(nt, a, node.inputs[0])
    if b is not None:
        _feed(nt, b, node.inputs[1])
    return node.outputs["Vector"]


def encode_position(nt, position_socket, lo, size, location=(-400, 0)):
    """(p - lo) / size so positions are stored as positive values."""
    shifted = _vector_math(nt, "SUBTRACT", position_socket, tuple(lo), location)
    inv = tuple(1.0 / max(s, 1e-9) for s in size)
    return _vector_math(nt, "MULTIPLY", shifted, inv, (location[0] + 180, location[1]))


def mesh_maps_material(reg, *, ao=False, ao_distance=1.0, ao_only_self=False, thickness=False,
                       thickness_distance=1.0, pointiness=False, ao_node_samples=16):
    """R = ambient occlusion, G = thickness, B = Cycles pointiness."""
    mat = reg.material("ZB_MeshMaps")
    nt = mat.node_tree
    em = _emission_output(nt)
    comb = _combine_rgb(nt, (-400, 0))
    nt.links.new(comb.outputs["Color"], em.inputs["Color"])
    if ao:
        node = _nodes(nt, "ShaderNodeAmbientOcclusion", (-800, 200))
        node.samples = ao_node_samples
        node.only_local = ao_only_self
        node.inside = False
        node.inputs["Distance"].default_value = ao_distance
        nt.links.new(node.outputs["AO"], comb.inputs[0])
    else:
        comb.inputs[0].default_value = 1.0
    if thickness:
        node = _nodes(nt, "ShaderNodeAmbientOcclusion", (-800, 0))
        node.samples = ao_node_samples
        node.only_local = True
        node.inside = True
        node.inputs["Distance"].default_value = thickness_distance
        nt.links.new(node.outputs["AO"], comb.inputs[1])
    else:
        comb.inputs[1].default_value = 1.0
    if pointiness:
        geo = _nodes(nt, "ShaderNodeNewGeometry", (-800, -200))
        nt.links.new(geo.outputs["Pointiness"], comb.inputs[2])
    else:
        comb.inputs[2].default_value = 0.5
    return mat


def high_position_material(reg, lo, size):
    """Original-space world position of the high poly (compensates explode offsets)."""
    mat = reg.material("ZB_PositionHigh")
    nt = mat.node_tree
    em = _emission_output(nt)
    geo = _nodes(nt, "ShaderNodeNewGeometry", (-1000, 0))
    attr = _nodes(nt, "ShaderNodeAttribute", (-1000, -200))
    attr.attribute_type = "OBJECT"
    attr.attribute_name = "zb_offset"
    orig = _vector_math(nt, "SUBTRACT", geo.outputs["Position"], attr.outputs["Vector"], (-800, 0))
    nt.links.new(encode_position(nt, orig, lo, size), em.inputs["Color"])
    return mat


def id_attribute_material(reg, attribute, attribute_type="GEOMETRY"):
    mat = reg.material("ZB_ID_" + attribute)
    nt = mat.node_tree
    em = _emission_output(nt)
    attr = _nodes(nt, "ShaderNodeAttribute", (-400, 0))
    attr.attribute_type = attribute_type
    attr.attribute_name = attribute
    nt.links.new(attr.outputs["Color"], em.inputs["Color"])
    return mat


def constant_emission_material(reg, name, color):
    mat = reg.material(name)
    em = _emission_output(mat.node_tree)
    em.inputs["Color"].default_value = tuple(color[:3]) + (1.0,)
    return mat


# ----------------------------------------------------------------------------
# Self-bake materials for the joined low poly (contain the target image node)


def low_self_material(reg, kind, image, lo=(0, 0, 0), size=(1, 1, 1)):
    mat = reg.material("ZB_LowSelf_" + kind)
    nt = mat.node_tree
    em = _emission_output(nt)
    if kind == "cover":
        em.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    elif kind == "position":
        attr = _nodes(nt, "ShaderNodeAttribute", (-800, 0))
        attr.attribute_type = "GEOMETRY"
        attr.attribute_name = "zb_orig"
        nt.links.new(encode_position(nt, attr.outputs["Vector"], lo, size), em.inputs["Color"])
    elif kind == "normal":
        geo = _nodes(nt, "ShaderNodeNewGeometry", (-800, 0))
        half = _vector_math(nt, "MULTIPLY_ADD", geo.outputs["Normal"], (0.5, 0.5, 0.5), (-600, 0))
        node = half.node
        node.inputs[2].default_value = (0.5, 0.5, 0.5)
        nt.links.new(half, em.inputs["Color"])
    else:
        raise ValueError(kind)
    add_target_image_node(nt, image)
    return mat


# ----------------------------------------------------------------------------
# Geometry nodes helpers (applied to *object* modifier stacks, never mesh data)


def _gn_group(reg, name):
    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    reg.node_groups.append(ng)
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    gin = ng.nodes.new("NodeGroupInput")
    gin.location = (-600, 0)
    gout = ng.nodes.new("NodeGroupOutput")
    gout.location = (600, 0)
    return ng, gin, gout


def gn_set_material(reg, material, island_attribute=None, seed=0):
    """Node group that assigns ``material`` to every face, optionally storing an
    island colour attribute used by the ID map."""
    ng, gin, gout = _gn_group(reg, "ZB_SetMaterial")
    setmat = ng.nodes.new("GeometryNodeSetMaterial")
    setmat.inputs["Material"].default_value = material
    ng.links.new(gin.outputs[0], setmat.inputs["Geometry"])
    last = setmat.outputs["Geometry"]
    if island_attribute:
        island = ng.nodes.new("GeometryNodeInputMeshIsland")
        rnd = ng.nodes.new("FunctionNodeRandomValue")
        rnd.data_type = "FLOAT"
        ng.links.new(island.outputs["Island Index"], compat.find_socket(rnd.inputs, "ID"))
        compat.find_socket(rnd.inputs, "Seed").default_value = seed
        hsv = ng.nodes.new("FunctionNodeCombineColor")
        hsv.mode = "HSV"
        ng.links.new(compat.find_socket(rnd.outputs, "Value", "VALUE"), hsv.inputs[0])
        hsv.inputs[1].default_value = 0.75
        hsv.inputs[2].default_value = 0.9
        store = ng.nodes.new("GeometryNodeStoreNamedAttribute")
        store.data_type = "FLOAT_COLOR"
        store.domain = "FACE"
        store.inputs["Name"].default_value = island_attribute
        ng.links.new(last, store.inputs["Geometry"])
        ng.links.new(hsv.outputs["Color"], compat.find_socket(store.inputs, "Value", "RGBA"))
        last = store.outputs["Geometry"]
    ng.links.new(last, gout.inputs[0])
    return ng


# ----------------------------------------------------------------------------
# ID colours


def id_color(name):
    """Stable, well separated display colour for a name."""
    digest = hashlib.md5(name.encode("utf-8")).digest()
    hue = int.from_bytes(digest[:4], "little") / 2 ** 32
    sat = 0.55 + 0.4 * digest[4] / 255.0
    val = 0.65 + 0.35 * digest[5] / 255.0
    return colorsys.hsv_to_rgb(hue, sat, val)


# ----------------------------------------------------------------------------
# PBR channel extraction


def _input_value(node, name):
    """Return the socket feeding ``name`` (if linked) or its default value."""
    if name is None:
        return (0.0, 0.0, 0.0, 1.0)
    if isinstance(name, (int, float)):
        return float(name)
    sock = compat.find_socket(node.inputs, name)
    if sock is None:
        return 0.0
    if sock.is_linked and sock.links:
        link = sock.links[0]
        if link.is_valid and not link.is_muted:
            return link.from_socket
    value = sock.default_value
    try:
        return tuple(value)
    except TypeError:
        return float(value)


def _shader_output(node):
    for out in node.outputs:
        if out.type == "SHADER":
            return out
    return None


def _source_node(socket):
    if not socket.is_linked or not socket.links:
        return None
    return socket.links[0].from_node


def has_transparency_nodes(materials):
    seen = set()

    def walk(tree):
        if tree is None or tree.name in seen:
            return False
        seen.add(tree.name)
        for node in tree.nodes:
            if node.bl_idname in _TRANSPARENT:
                return True
            if node.bl_idname == "ShaderNodeGroup" and walk(node.node_tree):
                return True
        return False

    return any(walk(m.node_tree) for m in materials if m is not None and m.node_tree)


class ChannelConverter:
    """Builds emission-only copies of materials that output one PBR channel set.

    ``kind`` is ``"base_color"`` (RGB) or ``"rmo"`` (R = roughness,
    G = metallic, B = opacity).  With ``bypass_transparency`` Mix Shader nodes
    whose input is a Transparent BSDF are bypassed, so cut-out materials keep
    unpremultiplied colours.
    """

    def __init__(self, reg, kind, bypass_transparency):
        self.reg = reg
        self.kind = kind
        self.bypass = bypass_transparency
        self._groups = {}

    # public -----------------------------------------------------------------

    def convert(self, mat):
        key = ("conv", self.kind, self.bypass, mat.name if mat else None)
        return self.reg.cached(key, lambda: self._convert(mat))

    # internals --------------------------------------------------------------

    def _convert(self, src):
        if src is None or not compat.material_uses_nodes(src):
            mat = self.reg.material("ZB_%s_default" % self.kind)
            nt = mat.node_tree
            em = _emission_output(nt)
            color = (0.8, 0.8, 0.8)
            if src is not None and not compat.material_uses_nodes(src):
                color = tuple(src.diffuse_color[:3])
            if self.kind == "base_color":
                _feed(nt, color + (1.0,), em.inputs["Color"])
            else:
                rough = src.roughness if src is not None else 0.5
                metal = src.metallic if src is not None else 0.0
                _feed(nt, (rough, metal, 1.0, 1.0), em.inputs["Color"])
            return mat
        mat = src.copy()
        mat.name = "ZB_%s_%s" % (self.kind, src.name)
        self.reg.materials.append(mat)
        self._process_tree(mat.node_tree)
        return mat

    def _group_copy(self, tree):
        if tree.name not in self._groups:
            copy = tree.copy()
            self.reg.node_groups.append(copy)
            self._groups[tree.name] = copy
            self._process_tree(copy)
        return self._groups[tree.name]

    def _process_tree(self, nt):
        for node in list(nt.nodes):
            if node.bl_idname == "ShaderNodeGroup" and node.node_tree is not None:
                if any(o.type == "SHADER" for o in node.outputs):
                    node.node_tree = self._group_copy(node.node_tree)
        if self.bypass:
            self._bypass_transparency(nt)
        for node in list(nt.nodes):
            idname = node.bl_idname
            if idname in _BSDF_TABLE or idname in _TRANSPARENT or idname in _EMISSION:
                self._replace(nt, node)

    def _bypass_transparency(self, nt):
        for node in list(nt.nodes):
            if node.bl_idname != "ShaderNodeMixShader":
                continue
            a, b = node.inputs[1], node.inputs[2]
            na, nb = _source_node(a), _source_node(b)
            keep = None
            if na is not None and na.bl_idname in _TRANSPARENT and b.is_linked:
                keep = b.links[0].from_socket
            elif nb is not None and nb.bl_idname in _TRANSPARENT and a.is_linked:
                keep = a.links[0].from_socket
            if keep is None:
                continue
            out = node.outputs[0]
            targets = [link.to_socket for link in out.links]
            for target in targets:
                nt.links.new(keep, target)

    def _values(self, node):
        idname = node.bl_idname
        if idname in _TRANSPARENT:
            return (0.0, 0.0, 0.0, 1.0), 0.5, 0.0, 0.0
        if idname in _EMISSION:
            return (0.0, 0.0, 0.0, 1.0), 1.0, 0.0, 1.0
        base_name, rough_name, metal_name = _BSDF_TABLE[idname]
        base = _input_value(node, base_name)
        rough = _input_value(node, rough_name)
        metal = _input_value(node, metal_name)
        alpha = _input_value(node, "Alpha") if compat.find_socket(node.inputs, "Alpha") else 1.0
        return base, rough, metal, alpha

    def _replace(self, nt, node):
        out_socket = _shader_output(node)
        if out_socket is None:
            return
        targets = [link.to_socket for link in out_socket.links]
        base, rough, metal, alpha = self._values(node)
        x, y = node.location
        em = nt.nodes.new("ShaderNodeEmission")
        em.location = (x, y)
        em.inputs["Strength"].default_value = 1.0
        if self.kind == "base_color":
            _feed(nt, base, em.inputs["Color"])
        else:
            comb = _combine_rgb(nt, (x - 200, y))
            _feed(nt, rough, comb.inputs[0])
            _feed(nt, metal, comb.inputs[1])
            _feed(nt, alpha, comb.inputs[2])
            nt.links.new(comb.outputs["Color"], em.inputs["Color"])
        for target in targets:
            nt.links.new(em.outputs["Emission"], target)
        nt.nodes.remove(node)
