# SPDX-License-Identifier: GPL-3.0-or-later
"""Pre-flight operators."""

import bpy
from bpy.props import IntProperty

from .. import pairing, preflight


class ZB_OT_preflight(bpy.types.Operator):
    bl_idname = "zapekanka.preflight"
    bl_label = "Run Pre-flight Check"
    bl_description = "Check pairs for problems that ruin bakes (scale, UVs, normals, triangulation...)"

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    def execute(self, context):
        s = context.scene.zapekanka
        pairing.prune_missing(s, context.scene)
        issues = preflight.run_checks(context)
        preflight.store_issues(s, issues)
        errors = sum(1 for i in issues if i.severity == "ERROR")
        warnings = sum(1 for i in issues if i.severity == "WARNING")
        if not issues:
            self.report({"INFO"}, "Pre-flight: everything looks good")
        else:
            self.report({"WARNING"} if errors or warnings else {"INFO"},
                        "Pre-flight: %d error(s), %d warning(s)" % (errors, warnings))
        return {"FINISHED"}


class ZB_OT_preflight_fix(bpy.types.Operator):
    bl_idname = "zapekanka.preflight_fix"
    bl_label = "Fix"
    bl_description = "Apply the suggested fix (modifies the object, can be undone)"
    bl_options = {"REGISTER", "UNDO"}

    index: IntProperty(default=-1, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    def execute(self, context):
        s = context.scene.zapekanka
        if self.index >= 0:
            targets = [s.issues[self.index]] if self.index < len(s.issues) else []
        else:
            # "Fix all" skips fixes that change the UV layout or shading on purpose
            safe = {"SCALE", "NEG_SCALE", "NO_UV", "FLIPPED", "DOUBLES", "NOT_TRIANGULATED"}
            targets = [i for i in s.issues if i.fixable and i.code in safe]
        done = []
        seen = set()
        for issue in targets:
            key = (issue.code if issue.code != "LOOSE" else "DOUBLES", issue.object_name)
            if key in seen:
                continue
            seen.add(key)
            obj = bpy.data.objects.get(issue.object_name)
            code = "DOUBLES" if issue.code == "LOOSE" else issue.code
            try:
                done.append(preflight.apply_fix(context, code, obj))
            except (RuntimeError, ReferenceError) as exc:
                self.report({"WARNING"}, "%s: %s" % (issue.object_name, exc))
        bpy.ops.zapekanka.preflight()
        if done:
            self.report({"INFO"}, "; ".join(done[:3]) + (" ..." if len(done) > 3 else ""))
        return {"FINISHED"}


class ZB_OT_issue_select(bpy.types.Operator):
    bl_idname = "zapekanka.issue_select"
    bl_label = "Select Object"
    bl_description = "Select the object this issue refers to"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    index: IntProperty(default=-1, options={"SKIP_SAVE"})

    def execute(self, context):
        s = context.scene.zapekanka
        if not 0 <= self.index < len(s.issues):
            return {"CANCELLED"}
        issue = s.issues[self.index]
        obj = bpy.data.objects.get(issue.object_name)
        if obj is None or context.view_layer.objects.get(obj.name) is None:
            for i, pair in enumerate(s.pairs):
                if pair.name == issue.pair_name:
                    s.pairs_index = i
            return {"FINISHED"}
        for o in context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        return {"FINISHED"}


classes = (ZB_OT_preflight, ZB_OT_preflight_fix, ZB_OT_issue_select)
