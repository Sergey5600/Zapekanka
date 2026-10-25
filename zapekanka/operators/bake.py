# SPDX-License-Identifier: GPL-3.0-or-later
"""Bake operators (foreground and background) and result post-processing."""

import os
import shutil
import time

import bpy
from bpy.app.translations import pgettext_iface as iface_
from bpy.props import BoolProperty, EnumProperty

from .. import background, jobbuild, materials, pairing, preflight
from ..core import engine as engine_mod
from ..prefs import get_prefs

LAST_SUMMARY = {"lines": [], "warnings": [], "errors": [], "output_dir": "", "log_path": "", "time": 0.0}


def _select_pairs(context, scope):
    s = context.scene.zapekanka
    if scope == "ACTIVE":
        pair = pairing.active_pair(s)
        return [pair] if pair is not None else []
    if scope == "SELECTED":
        selected = set(context.selected_objects)
        return [p for p in s.pairs if selected & set(pairing.all_pair_objects(p))]
    return [p for p in s.pairs if p.enabled]


def _set_lows(job):
    """Texture set name -> low poly object names, captured when the job is submitted."""
    return {ts["name"]: [n for pair in ts["pairs"] for n in pair["lows"]] for ts in job["texture_sets"]}


def message_text(item):
    """Engine warnings are {template, args} dicts so they can be translated here."""
    if isinstance(item, dict):
        template = iface_(item.get("template", ""))
        args = tuple(item.get("args", ()))
        try:
            return template % args if args else template
        except (TypeError, ValueError):
            return item.get("template", "")
    return str(item)


def apply_results(scene_name, filepath, set_lows, result, uv_map):
    """Create/assign materials and build the summary shown in the panel."""
    LAST_SUMMARY["lines"] = []
    LAST_SUMMARY["warnings"] = [message_text(w) for w in result.get("warnings", [])]
    LAST_SUMMARY["errors"] = list(result.get("errors", []))
    LAST_SUMMARY["log_path"] = result.get("log_path", "")
    LAST_SUMMARY["time"] = float(result.get("elapsed", 0.0))
    scene = bpy.data.scenes.get(scene_name)
    if scene is None or bpy.data.filepath != filepath:
        if result.get("ok"):
            LAST_SUMMARY["warnings"].append(iface_("The file changed during the bake: textures were saved, "
                                                   "materials were not created"))
        return
    s = scene.zapekanka
    for ts in result.get("texture_sets", []):
        files = ts.get("files", [])
        LAST_SUMMARY["lines"].append(iface_("%s: %d file(s)") % (ts["name"], len(files)))
        if files:
            LAST_SUMMARY["output_dir"] = os.path.dirname(files[0]["path"])
        if s.material_mode == "NONE" or not files:
            continue
        mat_name = s.material_template.replace("{name}", ts["name"])
        mat = materials.build_material(mat_name, files, s.normal_format, ts.get("meta"), uv_map)
        lows = [bpy.data.objects[n] for n in set_lows.get(ts["name"], []) if n in bpy.data.objects]
        if s.material_mode == "ASSIGN":
            materials.assign(lows, mat)
        elif s.material_mode == "PREVIEW":
            materials.preview_copies(lows, mat, ts["name"])
        else:
            mat.use_fake_user = True


class ZB_OT_bake(bpy.types.Operator):
    bl_idname = "zapekanka.bake"
    bl_label = "Bake"
    bl_description = "Bake the texture sets"
    bl_options = {"REGISTER"}

    scope: EnumProperty(
        name="Scope",
        items=(("ALL", "All Pairs", "All enabled pairs"),
               ("ACTIVE", "Active Pair", "Only the active pair"),
               ("SELECTED", "Selected Objects", "Pairs that contain a selected object")),
        default="ALL",
    )
    skip_checks: BoolProperty(name="Skip Pre-flight", default=False, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.mode == "OBJECT"

    def execute(self, context):
        s = context.scene.zapekanka
        pairing.prune_missing(s, context.scene)
        if not s.pairs:
            groups = pairing.detect(context)
            pairing.store(s, groups)
        pairs = _select_pairs(context, self.scope)
        if not pairs:
            self.report({"ERROR"}, "No pairs to bake. Detect pairs first")
            return {"CANCELLED"}
        if not self.skip_checks:
            issues = preflight.run_checks(context)
            preflight.store_issues(s, issues)
            errors = preflight.blocking_errors(issues)
            if errors:
                self.report({"ERROR"}, "Pre-flight: %s (see the Pre-flight panel)" % errors[0].message)
                return {"CANCELLED"}
        try:
            job = jobbuild.build_job(context, pairs)
        except (jobbuild.BuildError, OSError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        set_lows = _set_lows(job)
        scene_name = context.scene.name
        filepath = bpy.data.filepath
        uv_map = s.uv_map.strip()
        if s.bake_mode == "FOREGROUND":
            return self._foreground(context, job, set_lows, scene_name, filepath, uv_map)
        return self._background(context, job, set_lows, scene_name, filepath, uv_map)

    def _foreground(self, context, job, set_lows, scene_name, filepath, uv_map):
        wm = context.window_manager
        wm.progress_begin(0, 1000)
        start = time.time()

        def progress(frac, message):
            wm.progress_update(int(frac * 1000))

        try:
            result = engine_mod.Engine(job, progress=progress, log=lambda m: print("Zapekanka:", m)).run()
        finally:
            wm.progress_end()
        result.setdefault("elapsed", time.time() - start)
        apply_results(scene_name, filepath, set_lows, result, uv_map)
        return self._report(result)

    def _background(self, context, job, set_lows, scene_name, filepath, uv_map):
        prefs = get_prefs()
        job_dir = background.new_job_dir()
        try:
            jobbuild.write_source(job, job_dir)
        except (OSError, RuntimeError) as exc:
            shutil.rmtree(job_dir, ignore_errors=True)
            self.report({"ERROR"}, "Could not write the bake scene: %s" % exc)
            return {"CANCELLED"}

        def on_finish(result):
            apply_results(scene_name, filepath, set_lows, result, uv_map)
            try:
                bpy.ops.ed.undo_push(message="Zapekanka Bake")
            except RuntimeError:
                pass

        names = ", ".join(ts["name"] for ts in job["texture_sets"])
        background.submit(
            job, job_dir, on_finish, title=names,
            low_priority=prefs.low_priority if prefs else True,
            keep_files=prefs.keep_job_files if prefs else False,
        )
        self.report({"INFO"}, "Baking %s in the background" % names)
        return {"FINISHED"}

    def _report(self, result):
        if result.get("ok"):
            n = sum(len(ts.get("files", [])) for ts in result.get("texture_sets", []))
            msg = "Baked %d texture(s) in %.1fs" % (n, result.get("elapsed", 0.0))
            if result.get("warnings"):
                msg += " - %d warning(s)" % len(result["warnings"])
            self.report({"WARNING"} if result.get("warnings") else {"INFO"}, msg)
            return {"FINISHED"}
        self.report({"ERROR"}, "; ".join(result.get("errors", ["Bake failed"])))
        return {"CANCELLED"}


class ZB_OT_cancel(bpy.types.Operator):
    bl_idname = "zapekanka.cancel"
    bl_label = "Cancel Bake"
    bl_description = "Stop the running background bake and clear the queue"

    def execute(self, context):
        background.cancel(all_jobs=True)
        return {"FINISHED"}


class ZB_OT_open_folder(bpy.types.Operator):
    bl_idname = "zapekanka.open_folder"
    bl_label = "Open Folder"
    bl_description = "Open the output folder in the file browser"

    path: bpy.props.StringProperty(options={"SKIP_SAVE"})

    def execute(self, context):
        path = self.path or LAST_SUMMARY.get("output_dir") or bpy.path.abspath(context.scene.zapekanka.output_dir)
        if not path or not os.path.isdir(path):
            self.report({"WARNING"}, "Folder does not exist yet")
            return {"CANCELLED"}
        bpy.ops.wm.path_open(filepath=path)
        return {"FINISHED"}


class ZB_OT_open_log(bpy.types.Operator):
    bl_idname = "zapekanka.open_log"
    bl_label = "Open Log"
    bl_description = "Open the log of the last background bake"

    def execute(self, context):
        path = LAST_SUMMARY.get("log_path")
        if not path or not os.path.isfile(path):
            self.report({"WARNING"}, "No log available")
            return {"CANCELLED"}
        bpy.ops.wm.path_open(filepath=path)
        return {"FINISHED"}


classes = (ZB_OT_bake, ZB_OT_cancel, ZB_OT_open_folder, ZB_OT_open_log)
