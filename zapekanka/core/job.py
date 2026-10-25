# SPDX-License-Identifier: GPL-3.0-or-later
"""Bake job description.

A job is a plain JSON-serialisable dict so the exact same description can be
run in-process (foreground) or by a ``blender -b`` worker (background).
"""

import copy

JOB_FORMAT = 1

DEFAULT_SETTINGS = {
    "resolution": [2048, 2048],
    "supersample": 1,
    "max_tile": 8192,
    "aa_samples": 4,
    "device": "CPU",
    "gpu_backend": "NONE",
    "gpu_devices": [],
    "margin": 16,
    "margin_type": "ADJACENT_FACES",
    "fill_empty": True,
    "normal_format": "OPENGL",
    "ray_distance": 0.0,  # 0 = automatic (twice the largest cage offset)
    "explode": True,
    "uv_map": "",
    "triangulate": False,
    "skip_empty": True,
    "low_priority": True,
}

DEFAULT_MAPS = {
    "normal": {"enabled": True},
    "ao": {"enabled": False, "samples": 32, "distance": 0.5, "only_self": False},
    "curvature": {"enabled": False, "method": "NORMAL", "strength": 1.0, "radius": 1.0},
    "thickness": {"enabled": False, "samples": 32, "distance": 0.5},
    "position": {"enabled": False},
    "world_normal": {"enabled": False},
    "height": {"enabled": False, "range_mode": "AUTO", "range": 0.1},
    "id": {"enabled": False, "source": "MATERIAL", "attribute": ""},
    "base_color": {"enabled": False},
    "roughness": {"enabled": False},
    "metallic": {"enabled": False},
    "emission": {"enabled": False},
    "opacity": {"enabled": False},
}


class JobError(Exception):
    pass


def new_job():
    return {
        "format": JOB_FORMAT,
        "output_dir": "",
        "settings": copy.deepcopy(DEFAULT_SETTINGS),
        "maps": copy.deepcopy(DEFAULT_MAPS),
        "outputs": [],
        "objects": {},
        "texture_sets": [],
    }


def normalize(job):
    """Fill defaults and validate structure. Returns a new dict."""
    if job.get("format") != JOB_FORMAT:
        raise JobError("Unsupported job format %r" % job.get("format"))
    out = new_job()
    out.update({k: v for k, v in job.items() if k not in ("settings", "maps")})
    out["settings"].update(job.get("settings", {}))
    for key, value in job.get("maps", {}).items():
        if key in out["maps"]:
            out["maps"][key].update(value)
    s = out["settings"]
    s["supersample"] = int(s["supersample"])
    if s["supersample"] not in (1, 2, 4, 8):
        raise JobError("Supersample must be 1, 2, 4 or 8")
    w, h = (int(v) for v in s["resolution"])
    if w < 8 or h < 8 or w > 32768 or h > 32768:
        raise JobError("Resolution out of range: %dx%d" % (w, h))
    s["resolution"] = [w, h]
    if not out["texture_sets"]:
        raise JobError("Nothing to bake: no texture sets")
    for ts in out["texture_sets"]:
        if not ts.get("name"):
            raise JobError("Texture set without name")
        if not ts.get("pairs"):
            raise JobError("Texture set %r has no pairs" % ts["name"])
        for pair in ts["pairs"]:
            if not pair.get("lows"):
                raise JobError("Pair %r has no low poly" % pair.get("name"))
    if not out["outputs"]:
        raise JobError("No outputs requested")
    return out


def enabled_maps(job):
    return {k for k, v in job["maps"].items() if v.get("enabled")}
