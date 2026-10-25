# SPDX-License-Identifier: GPL-3.0-or-later
"""Target presets: normal convention, naming, packing and file formats.

A preset only *fills* scene settings; everything stays editable afterwards.
:func:`build_outputs` turns the settings into the output list of a bake job.
"""

SUFFIX_KEYS = (
    "base_color",
    "normal",
    "orm",
    "metallic_smoothness",
    "mask",
    "ao",
    "roughness",
    "metallic",
    "emission",
    "opacity",
    "curvature",
    "thickness",
    "position",
    "world_normal",
    "height",
    "id",
)

_UE_SUFFIX = {
    "base_color": "BC", "normal": "N", "orm": "ORM", "metallic_smoothness": "MS", "mask": "MASK",
    "ao": "AO", "roughness": "R", "metallic": "M", "emission": "E", "opacity": "O",
    "curvature": "C", "thickness": "TH", "position": "P", "world_normal": "WN", "height": "H", "id": "ID",
}

PRESETS = {
    "UE5": {
        "label": "Unreal Engine 5",
        "normal_format": "DIRECTX",
        "template": "T_{name}_{suffix}",
        "material_template": "M_{name}",
        "mesh_template": "SM_{name}",
        "pack": "ORM",
        "opacity_in_alpha": True,
        "file_format": "PNG",
        "normal_16bit": False,
        "suffix": _UE_SUFFIX,
    },
    "UNITY_URP": {
        "label": "Unity (URP / Built-in)",
        "normal_format": "OPENGL",
        "template": "{name}_{suffix}",
        "material_template": "{name}",
        "mesh_template": "{name}",
        "pack": "UNITY_METALLIC",
        "opacity_in_alpha": True,
        "file_format": "PNG",
        "normal_16bit": False,
        "suffix": dict(_UE_SUFFIX, base_color="Albedo", normal="Normal", metallic_smoothness="MetallicSmoothness",
                       ao="Occlusion", roughness="Roughness", metallic="Metallic", emission="Emission",
                       opacity="Opacity", height="Height", curvature="Curvature", thickness="Thickness",
                       position="Position", world_normal="WorldNormal", id="ID", orm="ORM", mask="MaskMap"),
    },
    "UNITY_HDRP": {
        "label": "Unity (HDRP)",
        "normal_format": "OPENGL",
        "template": "{name}_{suffix}",
        "material_template": "{name}",
        "mesh_template": "{name}",
        "pack": "UNITY_HDRP_MASK",
        "opacity_in_alpha": True,
        "file_format": "PNG",
        "normal_16bit": False,
        "suffix": dict(_UE_SUFFIX, base_color="BaseColor", normal="Normal", mask="MaskMap", ao="Occlusion",
                       roughness="Roughness", metallic="Metallic", emission="Emission", opacity="Opacity",
                       height="Height", curvature="Curvature", thickness="Thickness", position="Position",
                       world_normal="WorldNormal", id="ID", orm="ORM", metallic_smoothness="MetallicSmoothness"),
    },
    "GODOT": {
        "label": "Godot 4",
        "normal_format": "OPENGL",
        "template": "{name}_{suffix}",
        "material_template": "{name}",
        "mesh_template": "{name}",
        "pack": "ORM",
        "opacity_in_alpha": True,
        "file_format": "PNG",
        "normal_16bit": False,
        "suffix": {k: v.lower() for k, v in dict(
            _UE_SUFFIX, base_color="albedo", normal="normal", orm="orm", ao="ao", roughness="roughness",
            metallic="metallic", emission="emission", opacity="opacity", height="height", curvature="curvature",
            thickness="thickness", position="position", world_normal="world_normal", id="id").items()},
    },
    "ROBLOX": {
        "label": "Roblox",
        "normal_format": "OPENGL",
        "template": "{name}_{suffix}",
        "material_template": "{name}",
        "mesh_template": "{name}",
        "pack": "NONE",
        "opacity_in_alpha": True,
        "file_format": "PNG",
        "normal_16bit": False,
        "max_resolution": 1024,
        "suffix": dict(_UE_SUFFIX, base_color="Color", normal="Normal", metallic="Metalness",
                       roughness="Roughness", emission="Emissive", ao="AO", opacity="Opacity", height="Height",
                       curvature="Curvature", thickness="Thickness", position="Position",
                       world_normal="WorldNormal", id="ID"),
    },
    "GLTF": {
        "label": "glTF / Sketchfab",
        "normal_format": "OPENGL",
        "template": "{name}_{suffix}",
        "material_template": "{name}",
        "mesh_template": "{name}",
        "pack": "ORM",
        "opacity_in_alpha": True,
        "file_format": "PNG",
        "normal_16bit": False,
        "suffix": dict(_UE_SUFFIX, base_color="baseColor", normal="normal", orm="occlusionRoughnessMetallic",
                       ao="occlusion", roughness="roughness", metallic="metallic", emission="emissive",
                       opacity="opacity", height="height", curvature="curvature", thickness="thickness",
                       position="position", world_normal="worldNormal", id="id"),
    },
    "SUBSTANCE": {
        "label": "Substance 3D Painter",
        "normal_format": "OPENGL",
        "template": "{name}_{suffix}",
        "material_template": "{name}",
        "mesh_template": "{name}",
        "pack": "NONE",
        "opacity_in_alpha": False,
        "file_format": "PNG",
        "normal_16bit": True,
        "suffix": dict(_UE_SUFFIX, normal="normal_base", ao="ambient_occlusion", curvature="curvature",
                       thickness="thickness", position="position", world_normal="world_space_normals",
                       height="height", id="id", base_color="base_color", roughness="roughness",
                       metallic="metallic", emission="emissive", opacity="opacity"),
    },
    "MARMOSET": {
        "label": "Marmoset Toolbag",
        "normal_format": "OPENGL",
        "template": "{name}_{suffix}",
        "material_template": "{name}",
        "mesh_template": "{name}",
        "pack": "NONE",
        "opacity_in_alpha": False,
        "file_format": "PNG",
        "normal_16bit": True,
        "suffix": dict(_UE_SUFFIX, normal="normal", ao="ao", curvature="curvature", thickness="thickness",
                       position="position", world_normal="normal_obj", height="height", id="material_id",
                       base_color="albedo", roughness="roughness", metallic="metalness", emission="emissive",
                       opacity="alpha"),
    },
}

PRESET_ITEMS = [(key, p["label"], "Settings for %s" % p["label"]) for key, p in PRESETS.items()] + [
    ("CUSTOM", "Custom", "Keep the current naming and packing settings")
]

PACK_ITEMS = (
    ("NONE", "Separate Maps", "Every map in its own file"),
    ("ORM", "ORM (R=AO, G=Rough, B=Metal)", "Unreal Engine, Godot, glTF"),
    ("UNITY_METALLIC", "Unity Metallic (R=Metal, A=Smooth)", "Unity URP / Built-in metallic workflow"),
    ("UNITY_HDRP_MASK", "Unity HDRP Mask (R=Metal, G=AO, A=Smooth)", "Unity HDRP mask map"),
)


def build_outputs(s, enabled):
    """Return the job output list for settings ``s`` and the set of enabled maps."""
    outputs = []
    fmt = s.file_format
    data_hi = 16 if fmt in ("PNG", "TIFF") else (32 if fmt == "OPEN_EXR" else 8)
    normal_depth = 16 if s.normal_16bit and fmt in ("PNG", "TIFF") else (16 if fmt == "OPEN_EXR" else 8)

    def suffix(key):
        return getattr(s, "suffix_" + key)

    def add(key, channels, srgb=False, depth=8):
        outputs.append({
            "id": key,
            "file": s.naming_template.replace("{suffix}", suffix(key)),
            "channels": channels,
            "srgb": srgb,
            "format": fmt,
            "depth": depth if fmt != "OPEN_EXR" else 16,
        })

    has = enabled.__contains__
    if has("base_color"):
        if s.opacity_in_alpha and has("opacity"):
            add("base_color", ["base_color.r", "base_color.g", "base_color.b", "opacity"], srgb=True)
        else:
            add("base_color", ["base_color"], srgb=True)
    if has("normal"):
        add("normal", ["normal"], depth=normal_depth)
    packed = set()
    pack = s.pack_mode
    if pack == "ORM" and (has("roughness") or has("metallic")):
        add("orm", [
            "ao" if has("ao") else "=1",
            "roughness" if has("roughness") else "=0.5",
            "metallic" if has("metallic") else "=0",
        ])
        packed = {"ao", "roughness", "metallic"}
    elif pack == "UNITY_METALLIC" and (has("roughness") or has("metallic")):
        metal = "metallic" if has("metallic") else "=0"
        add("metallic_smoothness", [metal, metal, metal, "roughness!" if has("roughness") else "=0.5"])
        packed = {"roughness", "metallic"}
    elif pack == "UNITY_HDRP_MASK" and (has("roughness") or has("metallic") or has("ao")):
        add("mask", [
            "metallic" if has("metallic") else "=0",
            "ao" if has("ao") else "=1",
            "=1",
            "roughness!" if has("roughness") else "=0.5",
        ])
        packed = {"ao", "roughness", "metallic"}
    for key in ("ao", "roughness", "metallic"):
        if has(key) and (key not in packed or s.keep_packed_sources):
            add(key, [key])
    if has("opacity") and not (s.opacity_in_alpha and has("base_color")):
        add("opacity", ["opacity"])
    if has("emission"):
        add("emission", ["emission"], srgb=True)
    for key in ("curvature", "thickness", "id"):
        if has(key):
            add(key, [key])
    if has("world_normal"):
        add("world_normal", ["world_normal"], depth=normal_depth)
    if has("position"):
        add("position", ["position"], depth=data_hi)
    if has("height"):
        add("height", ["height"], depth=data_hi)
    return outputs


def apply_preset(s, key):
    preset = PRESETS.get(key)
    if preset is None:
        return
    s.normal_format = preset["normal_format"]
    s.naming_template = preset["template"]
    s.material_template = preset["material_template"]
    s.mesh_template = preset["mesh_template"]
    s.pack_mode = preset["pack"]
    s.opacity_in_alpha = preset["opacity_in_alpha"]
    s.file_format = preset["file_format"]
    s.normal_16bit = preset["normal_16bit"]
    for k in SUFFIX_KEYS:
        setattr(s, "suffix_" + k, preset["suffix"].get(k, k))
