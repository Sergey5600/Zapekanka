# SPDX-License-Identifier: GPL-3.0-or-later
"""Running bake jobs in a separate ``blender --background`` process.

The UI never blocks: a reader thread collects the worker's stdout, and a
``bpy.app.timers`` callback (main thread) applies progress and finishes the
job.  Only one job runs at a time; further jobs are queued.
"""

import collections
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time

import bpy

from . import worker

LOG_LINES = 400


class JobState:
    def __init__(self):
        self.running = False
        self.progress = 0.0
        self.message = ""
        self.title = ""
        self.started = 0.0
        self.log = collections.deque(maxlen=LOG_LINES)
        self.last_result = None
        self.last_error = ""
        self.job_dir = ""

    def elapsed(self):
        return time.time() - self.started if self.running else 0.0


STATE = JobState()

_lock = threading.Lock()
_events = queue.Queue()
_pending = collections.deque()
_current = None


class _Running:
    def __init__(self, process, job_dir, result_path, on_finish, title, keep_files):
        self.process = process
        self.job_dir = job_dir
        self.result_path = result_path
        self.on_finish = on_finish
        self.title = title
        self.keep_files = keep_files
        self.cancelled = False
        self.log_file = open(os.path.join(job_dir, "worker.log"), "w", encoding="utf-8", errors="replace")
        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()

    def _reader(self):
        stream = self.process.stdout
        try:
            for raw in iter(stream.readline, ""):
                line = raw.rstrip("\n")
                try:
                    self.log_file.write(line + "\n")
                except ValueError:
                    pass
                if line.startswith(worker.MARK):
                    try:
                        _events.put(json.loads(line[len(worker.MARK):]))
                    except json.JSONDecodeError:
                        pass
                elif line.strip() and not line.startswith("Fra:"):
                    _events.put({"kind": "raw", "message": line})
        finally:
            _events.put({"kind": "eof"})


def blender_executable():
    from .prefs import get_prefs

    prefs = get_prefs()
    custom = prefs.blender_path if prefs is not None else ""
    if custom and os.path.isfile(bpy.path.abspath(custom)):
        return bpy.path.abspath(custom)
    return bpy.app.binary_path


def new_job_dir():
    from .prefs import get_prefs

    prefs = get_prefs()
    base = bpy.path.abspath(prefs.temp_dir) if prefs is not None and prefs.temp_dir else None
    if base:
        os.makedirs(base, exist_ok=True)
    return tempfile.mkdtemp(prefix="zapekanka_", dir=base)


def submit(job, job_dir, on_finish, title="Bake", low_priority=True, keep_files=False):
    """Queue ``job`` (dict, already referencing ``source_blend`` inside job_dir)."""
    job = dict(job)
    job["result_path"] = os.path.join(job_dir, "result.json")
    job_path = os.path.join(job_dir, "job.json")
    with open(job_path, "w", encoding="utf-8") as fh:
        json.dump(job, fh, indent=1)
    _pending.append((job_path, job_dir, job["result_path"], on_finish, title, low_priority, keep_files))
    _ensure_timer()
    if _current is None:
        _start_next()


def queued_count():
    return len(_pending)


def cancel(all_jobs=False):
    if all_jobs:
        while _pending:
            _, job_dir, _, _, _, _, keep = _pending.popleft()
            if not keep:
                shutil.rmtree(job_dir, ignore_errors=True)
    if _current is not None:
        _current.cancelled = True
        _terminate(_current.process)


def _terminate(process):
    try:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
    except OSError:
        pass


def _start_next():
    global _current
    if not _pending:
        return
    job_path, job_dir, result_path, on_finish, title, low_priority, keep = _pending.popleft()
    cmd = [
        blender_executable(),
        "--background",
        "--factory-startup",
        "--python-exit-code",
        "1",
        "--python",
        worker.__file__,
        "--",
        job_path,
    ]
    kwargs = {}
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if low_priority:
            flags |= getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
        kwargs["creationflags"] = flags
    elif low_priority:
        kwargs["preexec_fn"] = lambda: os.nice(5)
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONUNBUFFERED"] = "1"
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
            **kwargs,
        )
    except OSError as exc:
        STATE.last_error = "Could not start Blender: %s" % exc
        on_finish({"ok": False, "errors": [STATE.last_error], "warnings": [], "texture_sets": []})
        return
    _current = _Running(process, job_dir, result_path, on_finish, title, keep)
    STATE.running = True
    STATE.progress = 0.0
    STATE.message = "Starting Blender"
    STATE.title = title
    STATE.started = time.time()
    STATE.job_dir = job_dir
    STATE.log.clear()
    STATE.last_error = ""


def _ensure_timer():
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=0.2, persistent=True)


def _redraw():
    wm = bpy.context.window_manager
    if wm is None:
        return
    for window in wm.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            if area.type in {"VIEW_3D", "PROPERTIES"}:
                area.tag_redraw()


def _finish(eof_seen):
    global _current
    job = _current
    _current = None
    if job is None:
        return
    try:
        job.process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        _terminate(job.process)
    try:
        job.log_file.close()
    except OSError:
        pass
    result = None
    if os.path.isfile(job.result_path):
        try:
            with open(job.result_path, encoding="utf-8") as fh:
                result = json.load(fh)
        except (OSError, json.JSONDecodeError):
            result = None
    if result is None:
        tail = "\n".join(list(STATE.log)[-15:])
        msg = "Cancelled" if job.cancelled else "Worker exited with code %s" % job.process.returncode
        result = {"ok": False, "errors": [msg], "warnings": [], "texture_sets": [], "log_tail": tail}
    if job.cancelled:
        result["ok"] = False
        if "Cancelled" not in result.get("errors", []):
            result.setdefault("errors", []).append("Cancelled")
    result["log_path"] = os.path.join(job.job_dir, "worker.log")
    STATE.running = False
    STATE.progress = 1.0 if result.get("ok") else STATE.progress
    STATE.message = "Done" if result.get("ok") else "; ".join(result.get("errors", [])) or "Failed"
    STATE.last_result = result
    try:
        job.on_finish(result)
    except Exception as exc:  # never let a UI callback kill the timer
        STATE.last_error = "Post-processing failed: %s" % exc
        print("Zapekanka:", STATE.last_error)
        import traceback

        traceback.print_exc()
    if not job.keep_files and result.get("ok"):
        # keep the folder (with worker.log) when something went wrong
        for name in ("source.blend", "source.blend1"):
            try:
                os.remove(os.path.join(job.job_dir, name))
            except OSError:
                pass
    _start_next()


def _tick():
    eof = False
    changed = False
    while True:
        try:
            event = _events.get_nowait()
        except queue.Empty:
            break
        changed = True
        kind = event.get("kind")
        if kind == "progress":
            STATE.progress = float(event.get("value", 0.0))
            STATE.message = event.get("message", "")
        elif kind in ("log", "raw", "error"):
            STATE.log.append(event.get("message", ""))
        elif kind == "eof":
            eof = True
    if _current is not None and (eof or _current.process.poll() is not None):
        if eof or _events.empty():
            _finish(eof)
            changed = True
    if changed:
        _redraw()
    if _current is None and not _pending:
        return None  # idle: unregister, submit() registers the timer again
    return 0.25


def shutdown():
    """Called on unregister: stop the worker, keep nothing running."""
    cancel(all_jobs=True)
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
