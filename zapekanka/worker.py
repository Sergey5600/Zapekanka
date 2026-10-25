# SPDX-License-Identifier: GPL-3.0-or-later
"""Background bake worker.

Started by the add-on as::

    blender --background --factory-startup --python worker.py -- job.json

It loads the objects from the job's ``source_blend`` (a partial copy of the
user's file), runs the bake engine and reports progress on stdout using
single-line JSON messages prefixed with :data:`MARK`.  This file must not
import anything from the add-on at module level: it is executed as a plain
script and imports the package by path.
"""

import importlib
import json
import os
import sys
import time
import traceback

MARK = "@@ZAPEKANKA@@"


def emit(kind, **data):
    data["kind"] = kind
    sys.stdout.write(MARK + json.dumps(data) + "\n")
    sys.stdout.flush()


def _load_package():
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(pkg_dir))
    name = os.path.basename(pkg_dir)
    return importlib.import_module(name + ".core.engine")


def _append_sources(job):
    """Append the objects referenced by the job and remap their names."""
    import bpy

    src = job.get("source_blend")
    if not src:
        return job
    bpy.ops.wm.read_factory_settings(use_empty=True)
    wanted = []
    for ts in job["texture_sets"]:
        for pair in ts["pairs"]:
            wanted.extend(pair.get("lows", []))
            wanted.extend(pair.get("highs", []))
            if pair.get("cage"):
                wanted.append(pair["cage"])
    wanted = list(dict.fromkeys(wanted))
    with bpy.data.libraries.load(src, link=False) as (data_from, data_to):
        available = set(data_from.objects)
        missing = [n for n in wanted if n not in available]
        if missing:
            raise RuntimeError("Objects missing from the bake source: %s" % ", ".join(missing))
        data_to.objects = list(wanted)
    rename = {}
    for requested, obj in zip(wanted, data_to.objects):
        if obj is None:
            raise RuntimeError("Could not load object %r" % requested)
        rename[requested] = obj.name

    def fix(name):
        return rename.get(name, name)

    for ts in job["texture_sets"]:
        for pair in ts["pairs"]:
            pair["lows"] = [fix(n) for n in pair.get("lows", [])]
            pair["highs"] = [fix(n) for n in pair.get("highs", [])]
            if pair.get("cage"):
                pair["cage"] = fix(pair["cage"])
    job["objects"] = {fix(k): v for k, v in job.get("objects", {}).items()}
    return job


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    if not argv:
        emit("error", message="No job file given")
        return 2
    job_path = argv[0]
    with open(job_path, encoding="utf-8") as fh:
        job = json.load(fh)
    result_path = job.get("result_path") or os.path.splitext(job_path)[0] + ".result.json"
    start = time.time()
    result = {"ok": False, "errors": [], "warnings": [], "texture_sets": []}
    code = 1
    try:
        engine = _load_package()
        emit("progress", value=0.0, message="Loading scene data")
        job = _append_sources(job)

        def log(message):
            emit("log", message=message)

        engine.configure_cycles_device(job["settings"], log)

        last = {"time": 0.0, "message": None}

        def progress(value, message):
            # Throttle repeats, but never drop a new message: the start of a
            # long pass would otherwise show the previous pass until it ends.
            now = time.time()
            if message != last["message"] or now - last["time"] > 0.2 or value >= 1.0:
                last["time"] = now
                last["message"] = message
                emit("progress", value=value, message=message)

        result = engine.Engine(job, progress=progress, log=log).run()
        code = 0 if result.get("ok") else 1
    except Exception as exc:  # report everything to the UI, never die silently
        result["errors"].append("%s: %s" % (type(exc).__name__, exc))
        result["traceback"] = traceback.format_exc()
        emit("log", message=result["traceback"])
    result["elapsed"] = time.time() - start
    try:
        with open(result_path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
    except OSError as exc:
        emit("error", message="Could not write result: %s" % exc)
    emit("done", ok=bool(result.get("ok")), result_path=result_path)
    return code


if __name__ == "__main__":
    status = main()
    sys.stdout.flush()
    # Leave Blender with the proper exit status; os._exit avoids slow teardown
    # of large scenes once results are on disk.
    os._exit(status)
