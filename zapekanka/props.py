# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene settings stored in ``Scene.zapekanka``."""

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)

from . import presets


def _geometry_poll(self, obj):
    return obj.type in {"MESH", "CURVE", "SURFACE", "FONT", "META"}


def _mesh_poll(self, obj):
    return obj.type == "MESH"


def _cage_changed(self, context):
    settings = context.scene.zapekanka
    if settings.show_cage_preview:
        from .operators import cage as cage_ops

        cage_ops.refresh_previews(context)


def _preset_changed(self, context):
    if self.preset != "CUSTOM":
        presets.apply_preset(self, self.preset)


class ZB_ObjectRef(bpy.types.PropertyGroup):
    obj: PointerProperty(type=bpy.types.Object, poll=_geometry_poll)


class ZB_Pair(bpy.types.PropertyGroup):
    name: StringProperty(name="Name", default="Pair")
    enabled: BoolProperty(name="Enabled", description="Include this pair in 'Bake All'", default=True)
    texture_set: StringProperty(
        name="Texture Set",
        description="Pairs with the same texture set are baked into the same textures (atlas). "
        "Empty: use the pair name",
        default="",
    )
    lows: CollectionProperty(type=ZB_ObjectRef)
    highs: CollectionProperty(type=ZB_ObjectRef)
    lows_index: IntProperty()
    highs_index: IntProperty()
    cage: PointerProperty(
        type=bpy.types.Object,
        name="Custom Cage",
        description="Optional cage mesh with the same topology as the low poly. Empty: automatic cage",
        poll=_mesh_poll,
    )
    use_custom_extrusion: BoolProperty(
        name="Custom Extrusion",
        description="Override the cage extrusion for this pair",
        default=False,
        update=_cage_changed,
    )
    extrusion: FloatProperty(
        name="Extrusion",
        description="How far the automatic cage is pushed out from the low poly",
        default=0.02,
        min=0.0,
        soft_max=1.0,
        subtype="DISTANCE",
        precision=4,
        update=_cage_changed,
    )

    @property
    def set_name(self):
        return self.texture_set.strip() or self.name

    def low_objects(self):
        return [r.obj for r in self.lows if r.obj is not None]

    def high_objects(self):
        return [r.obj for r in self.highs if r.obj is not None]


class ZB_Issue(bpy.types.PropertyGroup):
    severity: EnumProperty(
        items=(
            ("ERROR", "Error", "", "CANCEL", 0),
            ("WARNING", "Warning", "", "ERROR", 1),
            ("INFO", "Info", "", "INFO", 2),
        ),
        default="WARNING",
    )
    code: StringProperty()
    object_name: StringProperty()
    pair_name: StringProperty()
    message: StringProperty()
    fixable: BoolProperty(default=False)
    fix_label: StringProperty()


class ZB_MapSettings(bpy.types.PropertyGroup):
    use_normal: BoolProperty(name="Normal", default=True)
    use_ao: BoolProperty(name="Ambient Occlusion", default=True)
    use_curvature: BoolProperty(name="Curvature", default=False)
    use_thickness: BoolProperty(name="Thickness", default=False)
    use_position: BoolProperty(name="Position", default=False)
    use_world_normal: BoolProperty(name="World Normal", default=False)
    use_height: BoolProperty(name="Height", default=False)
    use_id: BoolProperty(name="ID Color", default=False)
    use_base_color: BoolProperty(name="Base Color", default=False)
    use_roughness: BoolProperty(name="Roughness", default=False)
    use_metallic: BoolProperty(name="Metallic", default=False)
    use_emission: BoolProperty(name="Emission", default=False)
    use_opacity: BoolProperty(name="Opacity", default=False)

    ao_samples: IntProperty(name="AO Samples", description="Cycles samples for the AO and thickness pass",
                            default=32, min=1, soft_max=512)
    ao_distance: FloatProperty(name="AO Distance", description="Maximum occlusion distance",
                               default=0.5, min=0.0001, soft_max=10.0, subtype="DISTANCE")
    ao_only_self: BoolProperty(name="Only Self", description="Only the object itself occludes (ignore other parts)",
                               default=False)
    curvature_method: EnumProperty(
        name="Method",
        items=(
            ("NORMAL", "From Normal Map", "Derived from the baked normal map: matches the normal details, "
             "independent of mesh density"),
            ("POINTINESS", "From Mesh", "Cycles pointiness of the high poly: needs a dense mesh"),
        ),
        default="NORMAL",
    )
    curvature_strength: FloatProperty(name="Strength", default=1.0, min=0.0, soft_max=5.0)
    curvature_radius: FloatProperty(name="Radius", description="Sampling radius (pixels at 1K)", default=1.0,
                                    min=0.1, soft_max=8.0)
    thickness_samples: IntProperty(name="Thickness Samples", default=32, min=1, soft_max=512)
    thickness_distance: FloatProperty(name="Thickness Distance", default=0.5, min=0.0001, soft_max=10.0,
                                      subtype="DISTANCE")
    height_range_mode: EnumProperty(
        name="Range",
        items=(("AUTO", "Auto", "Use the full 0-1 range for the largest offset"),
               ("MANUAL", "Manual", "Fixed range in scene units (consistent between assets)")),
        default="AUTO",
    )
    height_range: FloatProperty(name="Height Range", description="Offset mapped to black/white",
                                default=0.05, min=0.0001, subtype="DISTANCE")
    id_source: EnumProperty(
        name="ID Source",
        items=(
            ("MATERIAL", "Material", "One color per high poly material"),
            ("OBJECT", "Object", "One color per high poly object"),
            ("ISLAND", "Mesh Island", "One color per connected part of the high poly"),
            ("VERTEX_COLOR", "Vertex Color", "Use a color attribute of the high poly"),
        ),
        default="MATERIAL",
    )
    id_attribute: StringProperty(name="Attribute", description="Color attribute name (Vertex Color mode)",
                                 default="Color")

    MAP_KEYS = ("normal", "ao", "curvature", "thickness", "position", "world_normal", "height", "id",
                "base_color", "roughness", "metallic", "emission", "opacity")

    def enabled(self):
        return {k for k in self.MAP_KEYS if getattr(self, "use_" + k)}


EXPORT_TARGETS = (
    ("UE5", "Unreal Engine 5", "FBX + textures + material, sent live or as an import script"),
    ("UNITY", "Unity", "FBX + textures into the project, materials created by an editor script"),
    ("GODOT", "Godot 4", "glTF binary with embedded PBR material + ORMMaterial3D resource"),
    ("SUBSTANCE", "Substance 3D Painter", "Low/high FBX with matching names + baked maps"),
    ("MARMOSET", "Marmoset Toolbag", "Low/high/cage FBX with bake group suffixes"),
    ("GLTF", "glTF / Sketchfab", "Self-contained .glb"),
    ("ROBLOX", "Roblox", "FBX + SurfaceAppearance textures"),
)


class ZB_ExportSettings(bpy.types.PropertyGroup):
    target: EnumProperty(name="Target", items=EXPORT_TARGETS, default="UE5")
    directory: StringProperty(name="Export Folder", subtype="DIR_PATH", default="//export/")
    ue_content_path: StringProperty(name="Content Path", description="Destination inside the Unreal project",
                                    default="/Game/Zapekanka")
    ue_live: BoolProperty(name="Send Live", description="Send to a running Unreal Editor via Python remote "
                          "execution; falls back to writing an import script", default=True)
    unity_project: StringProperty(name="Unity Project", description="Root folder of the Unity project",
                                  subtype="DIR_PATH", default="")
    unity_folder: StringProperty(name="Assets Subfolder", default="Zapekanka")
    unity_pipeline: EnumProperty(name="Pipeline", items=(("URP", "URP", ""), ("HDRP", "HDRP", ""),
                                                         ("BUILTIN", "Built-in", "")), default="URP")
    godot_project: StringProperty(name="Godot Project", description="Folder containing project.godot",
                                  subtype="DIR_PATH", default="")
    godot_folder: StringProperty(name="Subfolder", default="zapekanka")
    include_textures: BoolProperty(name="Include Textures", default=True)
    include_highs: BoolProperty(name="Include High Polys", description="Export high polys (Substance/Marmoset)",
                                default=True)
    include_cage: BoolProperty(name="Include Cage", description="Export the automatic cage (Marmoset)",
                               default=True)
    triangulate: BoolProperty(name="Triangulate", description="Triangulate on export so tangents match the bake",
                              default=True)
    apply_modifiers: BoolProperty(name="Apply Modifiers", default=True)
    scale: FloatProperty(name="Scale", default=1.0, min=0.0001, soft_max=100.0)
    open_after: BoolProperty(name="Open Folder", description="Open the export folder when done", default=False)


class ZB_Settings(bpy.types.PropertyGroup):
    preset: EnumProperty(name="Preset", items=presets.PRESET_ITEMS, default="UE5", update=_preset_changed)
    output_dir: StringProperty(name="Output Folder", subtype="DIR_PATH", default="//textures/")

    resolution: EnumProperty(
        name="Resolution",
        items=(("512", "512", ""), ("1024", "1K", ""), ("2048", "2K", ""), ("4096", "4K", ""),
               ("8192", "8K", ""), ("CUSTOM", "Custom", "")),
        default="2048",
    )
    resolution_x: IntProperty(name="Width", default=2048, min=8, max=32768)
    resolution_y: IntProperty(name="Height", default=2048, min=8, max=32768)
    supersample: EnumProperty(
        name="Supersampling",
        description="Bake at a higher resolution and downscale for anti-aliased edges",
        items=(("1", "Off", ""), ("2", "2x", ""), ("4", "4x", ""), ("8", "8x", "")),
        default="2",
    )
    aa_samples: IntProperty(name="Samples", description="Cycles samples for regular passes",
                            default=4, min=1, soft_max=64)
    device: EnumProperty(name="Device", items=(("CPU", "CPU", ""), ("GPU", "GPU", "Uses the devices enabled in "
                                                                        "Preferences > System")), default="CPU")
    bake_mode: EnumProperty(
        name="Mode",
        items=(("BACKGROUND", "Background", "Bake in a separate Blender process: the interface stays responsive"),
               ("FOREGROUND", "Foreground", "Bake inside this Blender session (blocks the interface)")),
        default="BACKGROUND",
    )
    margin: IntProperty(name="Padding", description="Island padding in pixels (at output resolution)",
                        default=16, min=0, max=512)
    margin_type: EnumProperty(
        name="Padding Type",
        items=(("ADJACENT_FACES", "Adjacent Faces", "Continue across UV seams (seamless)"),
               ("EXTEND", "Extend", "Extend border pixels")),
        default="ADJACENT_FACES",
    )
    fill_empty: BoolProperty(name="Fill Empty Space", description="Bleed colors into the whole texture "
                             "(prevents seams in mip maps)", default=True)
    normal_format: EnumProperty(
        name="Normal Format",
        items=(("OPENGL", "OpenGL (Y+)", "Blender, Unity, Godot, Substance"),
               ("DIRECTX", "DirectX (Y-)", "Unreal Engine")),
        default="DIRECTX",
    )
    cage_extrusion: FloatProperty(name="Cage Extrusion", description="Distance the automatic cage is pushed out",
                                  default=0.02, min=0.0, soft_max=1.0, subtype="DISTANCE", precision=4,
                                  update=_cage_changed)
    ray_auto: BoolProperty(name="Auto Ray Distance", description="Ray distance = 2x cage extrusion",
                           default=True)
    ray_distance: FloatProperty(name="Ray Distance", description="Maximum ray length from the cage",
                                default=0.04, min=0.0, soft_max=2.0, subtype="DISTANCE", precision=4)
    explode: BoolProperty(name="Exploded Bake", description="Move pairs apart while baking so their AO and "
                          "rays do not interfere", default=True)
    uv_map: StringProperty(name="UV Map", description="UV map to bake into. Empty: active UV map", default="")
    triangulate: BoolProperty(name="Triangulate Low", description="Triangulate a copy of the low poly before "
                              "baking (export it triangulated the same way)", default=False)

    naming_template: StringProperty(name="Texture Name", description="Tokens: {name} (texture set), {suffix}",
                                    default="T_{name}_{suffix}")
    material_template: StringProperty(name="Material Name", default="M_{name}")
    mesh_template: StringProperty(name="Mesh Name", default="SM_{name}")
    pack_mode: EnumProperty(name="Packing", items=presets.PACK_ITEMS, default="ORM")
    opacity_in_alpha: BoolProperty(name="Opacity in Base Color Alpha", default=True)
    keep_packed_sources: BoolProperty(name="Also Save Packed Maps", description="Save AO/Roughness/Metallic "
                                      "separately as well", default=False)
    file_format: EnumProperty(
        name="Format",
        items=(("PNG", "PNG", ""), ("TARGA", "TGA", ""), ("TIFF", "TIFF", ""), ("OPEN_EXR", "OpenEXR", "")),
        default="PNG",
    )
    suffix_base_color: StringProperty(name="Base Color", default="BC")
    suffix_normal: StringProperty(name="Normal", default="N")
    suffix_orm: StringProperty(name="ORM", default="ORM")
    suffix_metallic_smoothness: StringProperty(name="Metallic Smoothness", default="MS")
    suffix_mask: StringProperty(name="Mask Map", default="MASK")
    suffix_ao: StringProperty(name="Ambient Occlusion", default="AO")
    suffix_roughness: StringProperty(name="Roughness", default="R")
    suffix_metallic: StringProperty(name="Metallic", default="M")
    suffix_emission: StringProperty(name="Emission", default="E")
    suffix_opacity: StringProperty(name="Opacity", default="O")
    suffix_curvature: StringProperty(name="Curvature", default="C")
    suffix_thickness: StringProperty(name="Thickness", default="TH")
    suffix_position: StringProperty(name="Position", default="P")
    suffix_world_normal: StringProperty(name="World Normal", default="WN")
    suffix_height: StringProperty(name="Height", default="H")
    suffix_id: StringProperty(name="ID Color", default="ID")
    normal_16bit: BoolProperty(name="16-bit Normals", default=False)
    skip_empty: BoolProperty(name="Skip Empty Maps", description="Do not write emission/opacity maps that are "
                             "completely black/opaque", default=True)

    material_mode: EnumProperty(
        name="Material",
        items=(("ASSIGN", "Create and Assign", "Assign the baked material to the low polys "
                "(original materials can be restored)"),
               ("PREVIEW", "Preview Copy", "Create a copy of the low polys with the baked material"),
               ("CREATE", "Create Only", "Create the material without assigning it"),
               ("NONE", "None", "Do not create a material")),
        default="ASSIGN",
    )

    pair_mode: EnumProperty(
        name="Detect By",
        items=(("SUFFIX", "Name Suffix", "Gun_low + Gun_high, Gun_high_bolt ..."),
               ("COLLECTION", "Collections", "Collections Gun_low and Gun_high")),
        default="SUFFIX",
    )
    low_suffixes: StringProperty(name="Low Suffixes", default="_low, _lp")
    high_suffixes: StringProperty(name="High Suffixes", default="_high, _hp")
    cage_suffix: StringProperty(name="Cage Suffix", default="_cage")
    detect_selected_only: BoolProperty(name="Selected Only", default=False)

    pairs: CollectionProperty(type=ZB_Pair)
    pairs_index: IntProperty()
    issues: CollectionProperty(type=ZB_Issue)
    issues_index: IntProperty()
    preflight_ran: BoolProperty(default=False)
    show_cage_preview: BoolProperty(name="Show Cage", default=False, update=_cage_changed)

    maps: PointerProperty(type=ZB_MapSettings)
    export: PointerProperty(type=ZB_ExportSettings)

    def resolution_xy(self):
        if self.resolution == "CUSTOM":
            return self.resolution_x, self.resolution_y
        value = int(self.resolution)
        return value, value


classes = (ZB_ObjectRef, ZB_Pair, ZB_Issue, ZB_MapSettings, ZB_ExportSettings, ZB_Settings)


def register():
    bpy.types.Scene.zapekanka = PointerProperty(type=ZB_Settings)


def unregister():
    del bpy.types.Scene.zapekanka
