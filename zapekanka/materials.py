# SPDX-License-Identifier: GPL-3.0-or-later
"""Building materials from baked texture sets."""

import json
import os

import bpy

from .core import compat
from .core.maps import MAPS, expand_channels

GLTF_GROUP = "glTF Material Output"
UTILITY_MAPS = ("curvature", "thickness", "position", "world_normal", "height", "id")


def _gltf_output_group():
    """Node group recognised by Blender's glTF exporter for occlusion."""
    group = bpy.data.node_groups.get(GLTF_GROUP)
    if group is None:
        group = bpy.data.node_groups.new(GLTF_GROUP, "ShaderNodeTree")
        sock = group.interface.new_socket(name="Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
        sock.default_value = 1.0
        sock.min_value = 0.0
        sock.max_value = 1.0
        group.nodes.new("NodeGroupInput").location = (-200, 0)
    return group


def load_image(path, srgb):
    path = os.path.abspath(path)
    img = None
    for existing in bpy.data.images:
        if existing.source == "FILE" and existing.filepath and \
                os.path.normcase(os.path.abspath(bpy.path.abspath(existing.filepath))) == os.path.normcase(path):
            img = existing
            break
    if img is None:
        img = bpy.data.images.load(path)
    else:
        img.reload()
    compat.set_colorspace(img, "srgb" if srgb else "data")
    if bpy.data.filepath:
        try:
            img.filepath = bpy.path.relpath(path)
        except ValueError:  # different drive on Windows
            pass
    return img


class _Builder:
    def __init__(self, mat, normal_format, uv_map):
        self.mat = mat
        self.nt = mat.node_tree
        self.normal_format = normal_format
        self.uv_map = uv_map
        self.out = self.nt.nodes.new("ShaderNodeOutputMaterial")
        self.out.location = (600, 0)
        self.bsdf = self.nt.nodes.new("ShaderNodeBsdfPrincipled")
        self.bsdf.location = (200, 0)
        self.nt.links.new(self.bsdf.outputs[0], self.out.inputs["Surface"])
        self.y = 400
        self.uses_alpha = False
        self.gltf = None
        self.utility_y = -900

    def _tex(self, image, label, x=-700, utility=False):
        node = self.nt.nodes.new("ShaderNodeTexImage")
        node.image = image
        node.label = label
        if utility:
            node.location = (x - 300, self.utility_y)
            self.utility_y -= 280
        else:
            node.location = (x, self.y)
            self.y -= 300
        return node

    def _input(self, name):
        return compat.find_socket(self.bsdf.inputs, name)

    def _invert(self, socket, location):
        node = self.nt.nodes.new("ShaderNodeMath")
        node.operation = "SUBTRACT"
        node.inputs[0].default_value = 1.0
        node.location = location
        self.nt.links.new(socket, node.inputs[1])
        return node.outputs[0]

    def _connect_scalar(self, key, socket, invert, location):
        if invert:
            socket = self._invert(socket, location)
        if key == "roughness":
            self.nt.links.new(socket, self._input("Roughness"))
        elif key == "metallic":
            self.nt.links.new(socket, self._input("Metallic"))
        elif key == "opacity":
            self.nt.links.new(socket, self._input("Alpha"))
            self.uses_alpha = True
        elif key == "ao":
            if self.gltf is None:
                self.gltf = self.nt.nodes.new("ShaderNodeGroup")
                self.gltf.node_tree = _gltf_output_group()
                self.gltf.location = (300, -650)
                self.gltf.label = "glTF Material Output (AO)"
            self.nt.links.new(socket, self.gltf.inputs["Occlusion"])

    def _connect_normal(self, color_socket, node_location):
        x, y = node_location
        if self.normal_format == "DIRECTX":
            sep = self.nt.nodes.new("ShaderNodeSeparateColor")
            sep.location = (x + 300, y)
            comb = self.nt.nodes.new("ShaderNodeCombineColor")
            comb.location = (x + 650, y)
            self.nt.links.new(color_socket, sep.inputs[0])
            self.nt.links.new(sep.outputs[0], comb.inputs[0])
            self.nt.links.new(self._invert(sep.outputs[1], (x + 480, y - 120)), comb.inputs[1])
            self.nt.links.new(sep.outputs[2], comb.inputs[2])
            color_socket = comb.outputs[0]
        nmap = self.nt.nodes.new("ShaderNodeNormalMap")
        nmap.location = (x + 820 if self.normal_format == "DIRECTX" else x + 300, y)
        nmap.space = "TANGENT"
        if self.uv_map:
            nmap.uv_map = self.uv_map
        self.nt.links.new(color_socket, nmap.inputs["Color"])
        self.nt.links.new(nmap.outputs["Normal"], self._input("Normal"))

    def add_output(self, output, image):
        chans = expand_channels(output["channels"])
        keys = [c.map for c in chans]
        whole = len(chans) >= 3 and len({k for k in keys[:3]}) == 1 and keys[0] and \
            [c.index for c in chans[:3]] == [0, 1, 2] and MAPS[keys[0]].channels == 3
        primary = keys[0] if keys and keys[0] else output["id"]
        utility = whole and primary in UTILITY_MAPS or (len(chans) == 1 and primary in UTILITY_MAPS)
        label = MAPS[primary].label if primary in MAPS else output["id"]
        if len(chans) > 1 and not whole:
            label = output["id"].upper()
        tex = self._tex(image, label, utility=utility)
        if utility:
            return
        loc = (tex.location.x, tex.location.y)
        if whole:
            color = tex.outputs["Color"]
            if primary == "base_color":
                self.nt.links.new(color, self._input("Base Color"))
            elif primary == "normal":
                self._connect_normal(color, loc)
            elif primary == "emission":
                self.nt.links.new(color, self._input("Emission Color"))
                self._input("Emission Strength").default_value = 1.0
            if len(chans) == 4 and not chans[3].is_constant:
                self._connect_scalar(chans[3].map, tex.outputs["Alpha"], chans[3].invert, (loc[0] + 300, loc[1] - 200))
            return
        if len(chans) == 1:
            if not chans[0].is_constant:
                self._connect_scalar(chans[0].map, tex.outputs["Color"], chans[0].invert, (loc[0] + 300, loc[1]))
            return
        sep = self.nt.nodes.new("ShaderNodeSeparateColor")
        sep.location = (loc[0] + 300, loc[1])
        self.nt.links.new(tex.outputs["Color"], sep.inputs[0])
        seen = set()
        for i, ch in enumerate(chans):
            if ch.is_constant or ch.map in seen:
                continue
            seen.add(ch.map)
            socket = sep.outputs[i] if i < 3 else tex.outputs["Alpha"]
            self._connect_scalar(ch.map, socket, ch.invert, (loc[0] + 480, loc[1] - 60 * i))

    def finish(self, meta):
        if self.uses_alpha:
            compat.set_material_alpha_mode(self.mat, True)
        height = (meta or {}).get("height")
        if height:
            self.mat["zb_height_scale"] = height.get("scale", 0.0)


def build_material(name, files, normal_format="OPENGL", meta=None, uv_map="", material=None):
    """Create (or rebuild) a material from ``files`` = [{id, path, channels, srgb}]."""
    mat = material or bpy.data.materials.get(name)
    if mat is None:
        mat = compat.new_material(name)
    else:
        nt = compat.ensure_node_tree(mat)
        for node in list(nt.nodes):
            nt.nodes.remove(node)
    builder = _Builder(mat, normal_format, uv_map)
    for f in files:
        if not os.path.isfile(f["path"]):
            continue
        builder.add_output(f, load_image(f["path"], f.get("srgb", False)))
    builder.finish(meta)
    mat["zb_texture_set"] = True
    return mat


# ----------------------------------------------------------------------------
# Assignment


def assign(objects, mat):
    """Assign ``mat`` to every slot; the previous materials are remembered on the object."""
    for obj in objects:
        if obj.type != "MESH":
            continue
        if "zb_original_materials" not in obj:
            obj["zb_original_materials"] = [s.material.name if s.material else "" for s in obj.material_slots]
            obj["zb_original_links"] = [s.link for s in obj.material_slots]
        if not obj.material_slots:
            obj.data.materials.append(mat)
            continue
        for slot in obj.material_slots:
            slot.material = mat


def restore(objects):
    restored = 0
    for obj in objects:
        names = obj.get("zb_original_materials")
        if names is None:
            continue
        names = list(names)
        links = list(obj.get("zb_original_links", ["DATA"] * len(names)))
        # slots that were added for objects without materials
        while len(obj.material_slots) > len(names) and obj.data.materials:
            obj.data.materials.pop()
        for slot, name, link in zip(obj.material_slots, names, links):
            slot.link = link
            slot.material = bpy.data.materials.get(name) if name else None
        del obj["zb_original_materials"]
        obj.pop("zb_original_links", None)
        restored += 1
    return restored


def preview_copies(objects, mat, set_name):
    coll_name = "Zapekanka Preview"
    coll = bpy.data.collections.get(coll_name)
    if coll is None:
        coll = bpy.data.collections.new(coll_name)
        bpy.context.scene.collection.children.link(coll)
    created = []
    for obj in objects:
        name = "%s_baked" % obj.name
        old = bpy.data.objects.get(name)
        if old is not None and old.get("zb_preview"):
            bpy.data.objects.remove(old, do_unlink=True)
        copy = obj.copy()
        copy.name = name
        copy["zb_preview"] = True
        copy.pop("zb_original_materials", None)
        coll.objects.link(copy)
        if copy.material_slots:
            for slot in copy.material_slots:
                slot.link = "OBJECT"
                slot.material = mat
        else:
            copy.data = obj.data.copy()
            copy.data.materials.append(mat)
        created.append(copy)
    return created


# ----------------------------------------------------------------------------
# Texture set import


def read_sidecar(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    folder = os.path.dirname(path)
    files = [
        {"id": o["id"], "path": os.path.join(folder, o["file"]), "channels": o["channels"],
         "srgb": o.get("srgb", False)}
        for o in data.get("outputs", [])
    ]
    return data.get("texture_set", ""), files, data.get("normal_format", "OPENGL"), data.get("meta", {})


def guess_files(folder, set_name, settings, extensions=(".png", ".tga", ".tif", ".tiff", ".exr", ".jpg")):
    """Find textures named with the current naming template and suffixes."""
    from . import presets

    enabled = set(MAPS)
    candidates = presets.build_outputs(settings, enabled)
    names = {}
    for entry in os.listdir(folder):
        stem, ext = os.path.splitext(entry)
        if ext.lower() in extensions:
            names[stem.lower()] = os.path.join(folder, entry)
    found = []
    taken = set()
    for out in candidates:
        stem = out["file"].format(name=set_name).lower()
        path = names.get(stem)
        if path and path not in taken:
            taken.add(path)
            found.append({"id": out["id"], "path": path, "channels": out["channels"], "srgb": out.get("srgb")})
    return found
