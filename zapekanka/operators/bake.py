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


# Foreground bake in progress (at most one): the modal operator instance.
FOREGROUND = {"op": None}


class ForegroundBake:
    """A bake inside the user's Blender, advanced one step (one tile of one pass) at a time."""

    def __init__(self, job, set_lows, scene_name, filepath, uv_map):
        self._args = (scene_name, filepath, set_lows, uv_map)
        self._cancel = False
        self._engine = engine_mod.Engine(job, progress=self._on_progress, log=lambda m: print("Zapekanka:", m),
                                         check_cancel=lambda: self._cancel)
        self._steps = self._engine.steps()
        state = background.STATE
        state.foreground = True
        state.running = True
        state.progress = 0.0
        state.message = "Preparing"
        state.title = ", ".join(ts["name"] for ts in job["texture_sets"])
        state.started = time.time()

    @staticmethod
    def _on_progress(frac, message):
        background.STATE.progress = frac
        background.STATE.message = message

    def cancel(self):
        self._cancel = True

    def step(self):
        """Run one step. Returns None while baking, the result dict when done."""
        try:
            next(self._steps)
        except StopIteration as stop:
            return stop.value
        except Exception as exc:  # never leave Blender stuck in the modal loop
            import traceback

            traceback.print_exc()
            self._steps.close()  # runs the engine's cleanup
            return {"ok": False, "errors": [str(exc)], "warnings": [], "texture_sets": []}
        return None

    def finish(self, result):
        state = background.STATE
        state.foreground = False
        state.running = False
        state.progress = 1.0 if result.get("ok") else state.progress
        result.setdefault("elapsed", time.time() - state.started)
        scene_name, filepath, set_lows, uv_map = self._args
        apply_results(scene_name, filepath, set_lows, result, uv_map)


def _event_window(context):
    """Window that will deliver timer events, or None without an event loop (blender -b, scripts)."""
    if bpy.app.background:
        return None
    return context.window


def _redraw(context):
    wm = context.window_manager
    for window in wm.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            if area.type in {"VIEW_3D", "PROPERTIES", "STATUSBAR"}:
                area.tag_redraw()


class ZB_OT_bake(bpy.types.Operator):
    bl_idname = "zapekanka.bake"
    bl_label = "Bake"
    bl_description = "Bake the texture sets"
    # UNDO: the whole bake becomes one undo step, and helper operators used
    # while baking (join, apply transform) do not push their own steps, which
    # would copy the entire file into memory each time.
    bl_options = {"REGISTER", "UNDO"}

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
        return context.scene is not None and context.mode == "OBJECT" and FOREGROUND["op"] is None

    def invoke(self, context, event):
        prepared = self._prepare(context)
        if prepared is None:
            return {"CANCELLED"}
        window = _event_window(context)
        if context.scene.zapekanka.bake_mode == "FOREGROUND" and window is not None:
            return self._start_modal(context, window, *prepared)
        return self._dispatch(context, *prepared)

    def execute(self, context):
        prepared = self._prepare(context)
        if prepared is None:
            return {"CANCELLED"}
        return self._dispatch(context, *prepared)

    def _dispatch(self, context, job, set_lows, scene_name, filepath, uv_map):
        if context.scene.zapekanka.bake_mode == "FOREGROUND":
            return self._foreground(context, job, set_lows, scene_name, filepath, uv_map)
        return self._background(context, job, set_lows, scene_name, filepath, uv_map)

    def _prepare(self, context):
        """Checks and job building shared by all modes. Returns None when cancelled."""
        s = context.scene.zapekanka
        pairing.prune_missing(s, context.scene)
        if not s.pairs:
            pairing.store(s, pairing.detect(context))
        if not s.pairs and self.scope != "ACTIVE":
            # Nothing named *_low / *_high: bake the selection's own materials.
            created = pairing.self_pairs_from_selection(context)
            if created:
                self.report({"INFO"}, "No *_low / *_high objects found: baking the materials of %d selected "
                                      "object(s). Use + to bake high polys onto a low poly" % len(created))
        pairs = _select_pairs(context, self.scope)
        if not pairs:
            if s.pairs and self.scope == "SELECTED":
                self.report({"ERROR"}, "The selected objects are not part of any pair")
            else:
                self.report({"ERROR"}, "Nothing to bake. Name objects Name_low / Name_high and press Detect Pairs, "
                                       "or select the objects to bake")
            return None
        if not self.skip_checks:
            issues = preflight.run_checks(context)
            preflight.store_issues(s, issues)
            errors = preflight.blocking_errors(issues)
            if errors:
                self.report({"ERROR"}, "Pre-flight: %s (see the Pre-flight panel)" % errors[0].message)
                return None
        try:
            job = jobbuild.build_job(context, pairs)
        except (jobbuild.BuildError, OSError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return None
        return job, _set_lows(job), context.scene.name, bpy.data.filepath, s.uv_map.strip()

    # ------------------------------------------------------------------ foreground, interactive

    def _start_modal(self, context, window, job, set_lows, scene_name, filepath, uv_map):
        """Bake step by step from a timer so Blender keeps redrawing and Esc works.

        Input is swallowed while baking: editing or undoing the scene mid-bake
        would invalidate the data the bake is working on.
        """
        self._bake = ForegroundBake(job, set_lows, scene_name, filepath, uv_map)
        FOREGROUND["op"] = self
        wm = context.window_manager
        self._window = window
        self._timer = wm.event_timer_add(0.05, window=window)
        wm.modal_handler_add(self)
        window.cursor_modal_set("WAIT")
        return {"RUNNING_MODAL"}

    def request_cancel(self):
        self._bake.cancel()

    def modal(self, context, event):
        if event.type == "ESC" and event.value == "PRESS":
            self._bake.cancel()
        if event.type != "TIMER" or event.timer is not self._timer:
            return {"RUNNING_MODAL"}
        result = self._bake.step()
        if result is None:
            _redraw(context)
            return {"RUNNING_MODAL"}
        context.window_manager.event_timer_remove(self._timer)
        try:
            self._window.cursor_modal_restore()
        except ReferenceError:
            pass
        FOREGROUND["op"] = None
        self._bake.finish(result)
        _redraw(context)
        return self._report(result)

    # ------------------------------------------------------------------ foreground, blocking (scripts)

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
        if FOREGROUND["op"] is not None:
            FOREGROUND["op"].request_cancel()
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
