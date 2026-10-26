# SPDX-License-Identifier: GPL-3.0-or-later
"""Sidebar panels (3D Viewport > N > Zapekanka)."""

import textwrap

import bpy
from bpy.app.translations import pgettext_iface as iface_

from . import background, pairing
from .operators.bake import LAST_SUMMARY

CATEGORY = "Zapekanka"


def _wrap(layout, text, width=48, icon="NONE"):
    lines = textwrap.wrap(text, width) or [""]
    col = layout.column(align=True)
    for i, line in enumerate(lines):
        col.label(text=line, icon=icon if i == 0 else "BLANK1", translate=False)


class _Panel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = CATEGORY


# ----------------------------------------------------------------------------
# Lists


class ZB_UL_pairs(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        row = layout.row(align=True)
        row.prop(item, "enabled", text="")
        lows, highs = len(item.lows), len(item.highs)
        icon = "MESH_CUBE" if highs else "MATERIAL"
        row.prop(item, "name", text="", emboss=False, icon=icon)
        sub = row.row(align=True)
        sub.alignment = "RIGHT"
        sub.label(text="%d/%d" % (lows, highs), translate=False)
        if item.texture_set.strip() and item.texture_set.strip() != item.name:
            sub.label(text="", icon="TEXTURE")

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        flags = [self.bitflag_filter_item] * len(items)
        if self.filter_name:
            needle = self.filter_name.lower()
            flags = [self.bitflag_filter_item if needle in it.name.lower() else 0 for it in items]
        return flags, []


class ZB_UL_objects(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        obj = item.obj
        if obj is None:
            layout.label(text="(missing)", icon="ERROR")
        else:
            layout.label(text=obj.name, icon="OUTLINER_OB_" + obj.type if obj.type in
                         {"MESH", "CURVE", "SURFACE", "FONT", "META"} else "OBJECT_DATA", translate=False)


class ZB_UL_issues(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        icons = {"ERROR": "CANCEL", "WARNING": "ERROR", "INFO": "INFO"}
        row = layout.row(align=True)
        label = item.object_name or item.pair_name
        text = "%s: %s" % (label, item.message) if label else item.message
        row.label(text=text, icon=icons.get(item.severity, "INFO"), translate=False)
        if item.object_name:
            op = row.operator("zapekanka.issue_select", text="", icon="RESTRICT_SELECT_OFF", emboss=False)
            op.index = index
        if item.fixable:
            op = row.operator("zapekanka.preflight_fix", text="", icon="TOOL_SETTINGS")
            op.index = index


# ----------------------------------------------------------------------------
# Main panel


class ZB_PT_main(_Panel, bpy.types.Panel):
    bl_idname = "ZB_PT_main"
    bl_label = "Zapekanka"

    def draw(self, context):
        layout = self.layout
        s = context.scene.zapekanka
        row = layout.row(align=True)
        row.prop(s, "preset", text="")
        row.operator("zapekanka.apply_preset", text="", icon="FILE_REFRESH")

        state = background.STATE
        if state.running:
            box = layout.box()
            box.label(text=iface_("Baking: %s") % state.title, icon="RENDER_STILL", translate=False)
            box.progress(factor=state.progress, type="BAR",
                         text="%d%%  %s" % (int(state.progress * 100), state.message))
            row = box.row()
            row.label(text=iface_("Elapsed: %ds") % int(state.elapsed()), translate=False)
            queued = background.queued_count()
            if queued:
                row.label(text=iface_("Queued: %d") % queued, translate=False)
            box.operator("zapekanka.cancel", icon="CANCEL")
        col = layout.column(align=True)
        col.scale_y = 1.6
        op = col.operator("zapekanka.bake", text="Bake All", icon="RENDER_STILL")
        op.scope = "ALL"
        row = layout.row(align=True)
        op = row.operator("zapekanka.bake", text="Active Pair")
        op.scope = "ACTIVE"
        op = row.operator("zapekanka.bake", text="Selected")
        op.scope = "SELECTED"
        layout.row().prop(s, "bake_mode", expand=True)
        if s.bake_mode == "FOREGROUND":
            layout.label(text="Blender is blocked while baking", icon="INFO")

        if LAST_SUMMARY["lines"] or LAST_SUMMARY["errors"] or LAST_SUMMARY["warnings"]:
            box = layout.box()
            for err in LAST_SUMMARY["errors"][:3]:
                _wrap(box, err, icon="CANCEL")
            for line in LAST_SUMMARY["lines"]:
                box.label(text=line, icon="CHECKMARK", translate=False)
            for warn in LAST_SUMMARY["warnings"][:4]:
                _wrap(box, warn, icon="ERROR")
            if LAST_SUMMARY["time"]:
                box.label(text=iface_("Time: %.1fs") % LAST_SUMMARY["time"], translate=False)
            row = box.row(align=True)
            row.operator("zapekanka.open_folder", icon="FILE_FOLDER")
            if LAST_SUMMARY.get("log_path"):
                row.operator("zapekanka.open_log", icon="TEXT")


# ----------------------------------------------------------------------------
# Pairs


class ZB_PT_pairs(_Panel, bpy.types.Panel):
    bl_idname = "ZB_PT_pairs"
    bl_label = "High / Low Pairs"
    bl_parent_id = "ZB_PT_main"

    def draw(self, context):
        layout = self.layout
        s = context.scene.zapekanka
        row = layout.row(align=True)
        row.prop(s, "pair_mode", expand=True)
        row = layout.row(align=True)
        row.operator("zapekanka.detect_pairs", icon="VIEWZOOM")
        row.prop(s, "detect_selected_only", text="", icon="RESTRICT_SELECT_OFF")

        row = layout.row()
        row.template_list("ZB_UL_pairs", "", s, "pairs", s, "pairs_index", rows=4)
        col = row.column(align=True)
        col.operator("zapekanka.pair_from_selection", text="", icon="ADD")
        col.operator("zapekanka.pair_remove", text="", icon="REMOVE")
        col.separator()
        col.operator("zapekanka.pair_select", text="", icon="RESTRICT_SELECT_OFF")
        col.operator("zapekanka.pairs_texture_set", text="", icon="TEXTURE")
        col.separator()
        col.operator("zapekanka.pairs_clear", text="", icon="X")

        if not s.pairs:
            box = layout.box()
            _wrap(box, iface_("Name objects Name_low / Name_high and press Detect Pairs."), icon="INFO")
            _wrap(box, iface_("Or select a low poly and its high polys (low poly active) and press +."))
            _wrap(box, iface_("Bake All without pairs bakes the materials of the selected objects."))
            return
        pair = pairing.active_pair(s)
        if pair is None:
            return
        box = layout.box()
        box.prop(pair, "texture_set", icon="TEXTURE")
        split = box.split(factor=0.5)
        for col_layout, role, coll, idx, label in (
            (split.column(), "LOW", pair, "lows_index", "Low"),
            (split.column(), "HIGH", pair, "highs_index", "High"),
        ):
            col_layout.label(text=label)
            col_layout.template_list("ZB_UL_objects", role, pair, role.lower() + "s", pair, idx, rows=2)
            r = col_layout.row(align=True)
            op = r.operator("zapekanka.pair_objects", text="", icon="ADD")
            op.role, op.action = role, "ADD"
            op = r.operator("zapekanka.pair_objects", text="", icon="REMOVE")
            op.role, op.action = role, "REMOVE"
        box.prop(pair, "cage", icon="MOD_SOLIDIFY")
        row = box.row(align=True)
        row.prop(pair, "use_custom_extrusion", text="")
        sub = row.row(align=True)
        sub.active = pair.use_custom_extrusion
        sub.prop(pair, "extrusion")
        op = row.operator("zapekanka.cage_estimate", text="", icon="DRIVER_DISTANCE")
        op.target = "ACTIVE"


class ZB_PT_pairs_detection(_Panel, bpy.types.Panel):
    bl_idname = "ZB_PT_pairs_detection"
    bl_label = "Detection Settings"
    bl_parent_id = "ZB_PT_pairs"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        s = context.scene.zapekanka
        col = self.layout.column(align=True)
        col.prop(s, "low_suffixes")
        col.prop(s, "high_suffixes")
        col.prop(s, "cage_suffix")


# ----------------------------------------------------------------------------
# Maps


class ZB_PT_maps(_Panel, bpy.types.Panel):
    bl_idname = "ZB_PT_maps"
    bl_label = "Maps"
    bl_parent_id = "ZB_PT_main"

    def draw(self, context):
        layout = self.layout
        m = context.scene.zapekanka.maps
        row = layout.row(align=True)
        for key, label in (("PBR", "Full PBR"), ("GAME", "Game"), ("MESH", "Mesh Maps"), ("NONE", "None")):
            row.operator("zapekanka.maps_preset", text=label).preset = key
        split = layout.split(factor=0.5)
        col = split.column(align=True)
        col.label(text="Material", icon="MATERIAL")
        for key in ("base_color", "roughness", "metallic", "emission", "opacity"):
            col.prop(m, "use_" + key, toggle=True)
        col = split.column(align=True)
        col.label(text="Mesh", icon="MESH_DATA")
        for key in ("normal", "ao", "curvature", "thickness", "position", "world_normal", "height", "id"):
            col.prop(m, "use_" + key, toggle=True)

        if m.use_ao or m.use_thickness:
            box = layout.box()
            if m.use_ao:
                box.label(text="Ambient Occlusion", icon="SHADING_RENDERED")
                row = box.row(align=True)
                row.prop(m, "ao_samples", text="Samples")
                row.prop(m, "ao_distance", text="Distance")
                box.prop(m, "ao_only_self")
            if m.use_thickness:
                box.label(text="Thickness", icon="MOD_THICKNESS")
                row = box.row(align=True)
                row.prop(m, "thickness_samples", text="Samples")
                row.prop(m, "thickness_distance", text="Distance")
        if m.use_curvature:
            box = layout.box()
            box.label(text="Curvature", icon="SPHERECURVE")
            box.prop(m, "curvature_method", text="")
            row = box.row(align=True)
            row.prop(m, "curvature_strength")
            if m.curvature_method == "NORMAL":
                row.prop(m, "curvature_radius")
        if m.use_height:
            box = layout.box()
            box.label(text="Height", icon="MOD_DISPLACE")
            row = box.row(align=True)
            row.prop(m, "height_range_mode", expand=True)
            if m.height_range_mode == "MANUAL":
                box.prop(m, "height_range")
        if m.use_id:
            box = layout.box()
            box.label(text="ID Color", icon="COLOR")
            box.prop(m, "id_source", text="")
            if m.id_source == "VERTEX_COLOR":
                box.prop(m, "id_attribute")


# ----------------------------------------------------------------------------
# Cage & rays


class ZB_PT_cage(_Panel, bpy.types.Panel):
    bl_idname = "ZB_PT_cage"
    bl_label = "Cage & Rays"
    bl_parent_id = "ZB_PT_main"

    def draw(self, context):
        layout = self.layout
        s = context.scene.zapekanka
        row = layout.row(align=True)
        row.prop(s, "cage_extrusion")
        row.operator("zapekanka.cage_estimate", text="", icon="DRIVER_DISTANCE").target = "GLOBAL"
        row = layout.row(align=True)
        row.prop(s, "ray_auto", text="", icon="AUTO")
        sub = row.row(align=True)
        sub.active = not s.ray_auto
        sub.prop(s, "ray_distance")
        row = layout.row(align=True)
        row.prop(s, "show_cage_preview", toggle=True, icon="HIDE_OFF" if s.show_cage_preview else "HIDE_ON")
        row.operator("zapekanka.cage_preview", text="", icon="FILE_REFRESH")
        layout.prop(s, "explode")
        col = layout.column(align=True)
        col.prop(s, "uv_map", icon="GROUP_UVS")
        col.prop(s, "triangulate")


# ----------------------------------------------------------------------------
# Output


class ZB_PT_output(_Panel, bpy.types.Panel):
    bl_idname = "ZB_PT_output"
    bl_label = "Output & Quality"
    bl_parent_id = "ZB_PT_main"

    def draw(self, context):
        layout = self.layout
        s = context.scene.zapekanka
        layout.prop(s, "output_dir", text="")
        layout.row().prop(s, "resolution", expand=True)
        if s.resolution == "CUSTOM":
            row = layout.row(align=True)
            row.prop(s, "resolution_x")
            row.prop(s, "resolution_y")
        col = layout.column(align=True)
        col.label(text="Supersampling")
        col.row(align=True).prop(s, "supersample", expand=True)
        col = layout.column(align=True)
        col.prop(s, "aa_samples")
        col.prop(s, "device")
        row = layout.row(align=True)
        row.prop(s, "margin")
        row.prop(s, "margin_type", text="")
        layout.prop(s, "fill_empty")
        layout.row().prop(s, "normal_format", expand=True)
        col = layout.column(align=True)
        col.prop(s, "file_format")
        col.prop(s, "pack_mode")
        col = layout.column(align=True)
        col.prop(s, "normal_16bit")
        col.prop(s, "opacity_in_alpha")
        col.prop(s, "keep_packed_sources")
        col.prop(s, "skip_empty")
        layout.prop(s, "material_mode")


class ZB_PT_naming(_Panel, bpy.types.Panel):
    bl_idname = "ZB_PT_naming"
    bl_label = "Naming"
    bl_parent_id = "ZB_PT_output"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        s = context.scene.zapekanka
        col = layout.column(align=True)
        col.prop(s, "naming_template")
        col.prop(s, "material_template")
        col.prop(s, "mesh_template")
        from .presets import SUFFIX_KEYS

        col = layout.column(align=True)
        for key in SUFFIX_KEYS:
            col.prop(s, "suffix_" + key)


# ----------------------------------------------------------------------------
# Pre-flight


class ZB_PT_preflight(_Panel, bpy.types.Panel):
    bl_idname = "ZB_PT_preflight"
    bl_label = "Pre-flight Check"
    bl_parent_id = "ZB_PT_main"

    def draw(self, context):
        layout = self.layout
        s = context.scene.zapekanka
        row = layout.row(align=True)
        row.operator("zapekanka.preflight", icon="CHECKMARK")
        fixable = [i for i in s.issues if i.fixable]
        if fixable:
            op = row.operator("zapekanka.preflight_fix", text="Fix All", icon="TOOL_SETTINGS")
            op.index = -1
        if not s.preflight_ran:
            return
        if not s.issues:
            layout.label(text="No problems found", icon="CHECKMARK")
            return
        errors = sum(1 for i in s.issues if i.severity == "ERROR")
        warnings = sum(1 for i in s.issues if i.severity == "WARNING")
        layout.label(text=iface_("%d error(s), %d warning(s)") % (errors, warnings), translate=False)
        layout.template_list("ZB_UL_issues", "", s, "issues", s, "issues_index", rows=4)
        if 0 <= s.issues_index < len(s.issues):
            issue = s.issues[s.issues_index]
            box = layout.box()
            if issue.object_name:
                box.label(text=issue.object_name, icon="OBJECT_DATA", translate=False)
            _wrap(box, issue.message)
            if issue.fixable:
                op = box.operator("zapekanka.preflight_fix", text=issue.fix_label or "Fix", icon="TOOL_SETTINGS")
                op.index = s.issues_index


# ----------------------------------------------------------------------------
# Export


class ZB_PT_export(_Panel, bpy.types.Panel):
    bl_idname = "ZB_PT_export"
    bl_label = "Export"
    bl_parent_id = "ZB_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        s = context.scene.zapekanka
        e = s.export
        layout.prop(e, "target", text="")
        layout.prop(e, "directory", text="")
        col = layout.column(align=True)
        if e.target == "UE5":
            col.prop(e, "ue_content_path")
            col.prop(e, "ue_live")
        elif e.target == "UNITY":
            col.prop(e, "unity_project")
            col.prop(e, "unity_folder")
            col.row().prop(e, "unity_pipeline", expand=True)
        elif e.target == "GODOT":
            col.prop(e, "godot_project")
            col.prop(e, "godot_folder")
        elif e.target in ("SUBSTANCE", "MARMOSET"):
            col.prop(e, "include_highs")
            if e.target == "MARMOSET":
                col.prop(e, "include_cage")
        col = layout.column(align=True)
        col.prop(e, "include_textures")
        col.prop(e, "triangulate")
        col.prop(e, "scale")
        col.prop(e, "open_after")
        col = layout.column(align=True)
        col.scale_y = 1.3
        label = "Send to Unreal" if e.target == "UE5" and e.ue_live else "Export"
        col.operator("zapekanka.export", text=label, icon="EXPORT")
        if e.target in ("SUBSTANCE", "MARMOSET"):
            op = col.operator("zapekanka.export", text="Export and Open", icon="WINDOW")
            op.launch = True
        row = layout.row(align=True)
        row.operator("zapekanka.import_texture_set", icon="IMPORT")
        row.operator("zapekanka.restore_materials", text="", icon="LOOP_BACK")


classes = (
    ZB_UL_pairs,
    ZB_UL_objects,
    ZB_UL_issues,
    ZB_PT_main,
    ZB_PT_pairs,
    ZB_PT_pairs_detection,
    ZB_PT_maps,
    ZB_PT_cage,
    ZB_PT_output,
    ZB_PT_naming,
    ZB_PT_preflight,
    ZB_PT_export,
)
