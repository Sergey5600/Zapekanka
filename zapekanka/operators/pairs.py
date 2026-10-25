# SPDX-License-Identifier: GPL-3.0-or-later
"""Pair list management."""

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty

from .. import pairing


class ZB_OT_detect_pairs(bpy.types.Operator):
    bl_idname = "zapekanka.detect_pairs"
    bl_label = "Detect Pairs"
    bl_description = "Find high/low pairs by name suffix or collection"
    bl_options = {"REGISTER", "UNDO"}

    replace: BoolProperty(name="Replace List", description="Remove pairs that were not found again",
                          default=False)

    def execute(self, context):
        s = context.scene.zapekanka
        groups = pairing.detect(context)
        if not groups:
            self.report({"WARNING"}, "No pairs found. Check the suffixes (%s / %s)" % (s.low_suffixes,
                                                                                     s.high_suffixes))
            return {"CANCELLED"}
        added = pairing.store(s, groups, replace=self.replace)
        self.report({"INFO"}, "%d pair(s) found, %d new" % (len(groups), added))
        return {"FINISHED"}


class ZB_OT_pair_from_selection(bpy.types.Operator):
    bl_idname = "zapekanka.pair_from_selection"
    bl_label = "Add Pair from Selection"
    bl_description = "Active object becomes the low poly, other selected objects the high polys"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == "MESH"

    def execute(self, context):
        pair = pairing.pair_from_selection(context)
        if pair is None:
            return {"CANCELLED"}
        self.report({"INFO"}, "Added pair %s (%d high)" % (pair.name, len(pair.highs)))
        return {"FINISHED"}


class ZB_OT_pair_remove(bpy.types.Operator):
    bl_idname = "zapekanka.pair_remove"
    bl_label = "Remove Pair"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return pairing.active_pair(context.scene.zapekanka) is not None

    def execute(self, context):
        s = context.scene.zapekanka
        s.pairs.remove(s.pairs_index)
        s.pairs_index = max(0, min(s.pairs_index, len(s.pairs) - 1))
        return {"FINISHED"}


class ZB_OT_pairs_clear(bpy.types.Operator):
    bl_idname = "zapekanka.pairs_clear"
    bl_label = "Clear Pairs"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        s = context.scene.zapekanka
        s.pairs.clear()
        s.pairs_index = 0
        return {"FINISHED"}


class ZB_OT_pair_objects(bpy.types.Operator):
    bl_idname = "zapekanka.pair_objects"
    bl_label = "Edit Pair Objects"
    bl_description = "Add selected objects to, or remove the active entry from, the active pair"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    role: EnumProperty(items=(("LOW", "Low", ""), ("HIGH", "High", "")))
    action: EnumProperty(items=(("ADD", "Add Selected", ""), ("REMOVE", "Remove", "")))

    def execute(self, context):
        pair = pairing.active_pair(context.scene.zapekanka)
        if pair is None:
            return {"CANCELLED"}
        coll = pair.lows if self.role == "LOW" else pair.highs
        if self.action == "REMOVE":
            idx = pair.lows_index if self.role == "LOW" else pair.highs_index
            if 0 <= idx < len(coll):
                coll.remove(idx)
            return {"FINISHED"}
        present = {r.obj for r in coll}
        added = 0
        for obj in context.selected_objects:
            if obj in present or obj.type not in pairing.GEOMETRY_TYPES:
                continue
            if self.role == "LOW" and obj.type != "MESH":
                continue
            coll.add().obj = obj
            added += 1
        self.report({"INFO"}, "Added %d object(s)" % added)
        return {"FINISHED"}


class ZB_OT_pair_select(bpy.types.Operator):
    bl_idname = "zapekanka.pair_select"
    bl_label = "Select Pair Objects"
    bl_description = "Select the objects of the pair in the viewport"
    bl_options = {"REGISTER", "UNDO"}

    index: IntProperty(default=-1, options={"SKIP_SAVE"})

    def execute(self, context):
        s = context.scene.zapekanka
        idx = self.index if self.index >= 0 else s.pairs_index
        if not 0 <= idx < len(s.pairs):
            return {"CANCELLED"}
        pair = s.pairs[idx]
        vl = context.view_layer
        for obj in context.selected_objects:
            obj.select_set(False)
        objs = [o for o in pairing.all_pair_objects(pair) if vl.objects.get(o.name) is not None]
        for obj in objs:
            obj.select_set(True)
        lows = [o for o in pair.low_objects() if o in objs]
        if lows:
            vl.objects.active = lows[0]
        return {"FINISHED"}


class ZB_OT_pairs_texture_set(bpy.types.Operator):
    bl_idname = "zapekanka.pairs_texture_set"
    bl_label = "Set Texture Set"
    bl_description = "Bake several pairs into one texture set (atlas) or split them again"
    bl_options = {"REGISTER", "UNDO"}

    name: StringProperty(name="Texture Set", default="")
    target: EnumProperty(items=(("ENABLED", "Enabled Pairs", ""), ("ACTIVE", "Active Pair", "")),
                         default="ENABLED")

    def invoke(self, context, event):
        pair = pairing.active_pair(context.scene.zapekanka)
        if not self.name and pair is not None:
            self.name = pair.set_name
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        s = context.scene.zapekanka
        pairs = [p for p in s.pairs if p.enabled] if self.target == "ENABLED" else [pairing.active_pair(s)]
        for pair in pairs:
            if pair is not None:
                pair.texture_set = self.name.strip()
        return {"FINISHED"}


classes = (
    ZB_OT_detect_pairs,
    ZB_OT_pair_from_selection,
    ZB_OT_pair_remove,
    ZB_OT_pairs_clear,
    ZB_OT_pair_objects,
    ZB_OT_pair_select,
    ZB_OT_pairs_texture_set,
)
