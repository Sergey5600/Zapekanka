# SPDX-License-Identifier: GPL-3.0-or-later
"""Turn scene settings into a bake job (see :mod:`core.job`)."""

import os

import bpy

from . import presets
from .core import job as jobmod
from .core.session import matrix_to_list, world_matrix


class BuildError(Exception):
    pass


def _gpu_info(context):
    try:
        cprefs = context.preferences.addons["cycles"].preferences
    except KeyError:
        return "NONE", []
    try:
        if hasattr(cprefs, "refresh_devices"):
            cprefs.refresh_devices()
        else:
            cprefs.get_devices()
    except Exception:  # device query can fail on exotic drivers; fall back to CPU
        return "NONE", []
    devices = [d.id for d in cprefs.devices if d.use and d.type != "CPU"]
    return cprefs.compute_device_type, devices


def _device(context, settings):
    if settings.device != "SCENE":
        return settings.device
    cycles = getattr(context.scene, "cycles", None)
    return "GPU" if cycles is not None and cycles.device == "GPU" else "CPU"


def output_directory(settings):
    raw = settings.output_dir.strip() or "//textures/"
    if raw.startswith("//") and not bpy.data.filepath:
        raise BuildError("Save the .blend file first or choose an absolute output folder")
    path = os.path.normpath(bpy.path.abspath(raw))
    os.makedirs(path, exist_ok=True)
    return path


def _object_entry(obj):
    try:
        matrix = obj.matrix_world.copy()
    except ReferenceError:
        matrix = world_matrix(obj)
    return {"matrix": matrix_to_list(matrix)}


def build_job(context, pairs=None):
    """Build a job for ``pairs`` (default: all enabled pairs)."""
    s = context.scene.zapekanka
    if pairs is None:
        pairs = [p for p in s.pairs if p.enabled]
    pairs = [p for p in pairs if p.low_objects()]
    if not pairs:
        raise BuildError("No pairs to bake. Detect pairs or add one from the selection")
    enabled = s.maps.enabled()
    if not enabled:
        raise BuildError("No maps enabled")

    job = jobmod.new_job()
    job["output_dir"] = output_directory(s)
    w, h = s.resolution_xy()
    from .prefs import get_prefs

    prefs = get_prefs()
    st = job["settings"]
    st.update({
        "resolution": [w, h],
        "supersample": int(s.supersample),
        "max_tile": int(prefs.max_tile) if prefs is not None else 8192,
        "aa_samples": s.aa_samples,
        "device": _device(context, s),
        "margin": s.margin,
        "margin_type": s.margin_type,
        "fill_empty": s.fill_empty,
        "normal_format": s.normal_format,
        "ray_distance": 0.0 if s.ray_auto else s.ray_distance,
        "explode": s.explode,
        "uv_map": s.uv_map.strip(),
        "triangulate": s.triangulate,
        "skip_empty": s.skip_empty,
        "low_priority": prefs.low_priority if prefs is not None else True,
    })
    if st["device"] == "GPU":
        st["gpu_backend"], st["gpu_devices"] = _gpu_info(context)
    m = s.maps
    job["maps"].update({
        "normal": {"enabled": m.use_normal},
        "ao": {"enabled": m.use_ao, "samples": m.ao_samples, "distance": m.ao_distance,
               "only_self": m.ao_only_self},
        "curvature": {"enabled": m.use_curvature, "method": m.curvature_method,
                      "strength": m.curvature_strength, "radius": m.curvature_radius},
        "thickness": {"enabled": m.use_thickness, "samples": m.thickness_samples,
                      "distance": m.thickness_distance},
        "position": {"enabled": m.use_position},
        "world_normal": {"enabled": m.use_world_normal},
        "height": {"enabled": m.use_height, "range_mode": m.height_range_mode, "range": m.height_range},
        "id": {"enabled": m.use_id, "source": m.id_source, "attribute": m.id_attribute},
        "base_color": {"enabled": m.use_base_color},
        "roughness": {"enabled": m.use_roughness},
        "metallic": {"enabled": m.use_metallic},
        "emission": {"enabled": m.use_emission},
        "opacity": {"enabled": m.use_opacity},
    })
    job["outputs"] = presets.build_outputs(s, enabled)

    sets = {}
    objects = {}
    for pair in pairs:
        lows = pair.low_objects()
        highs = [o for o in pair.high_objects() if o not in lows]
        entry = {
            "name": pair.name,
            "lows": [o.name for o in lows],
            "highs": [o.name for o in highs],
            "cage": pair.cage.name if pair.cage is not None and len(lows) == 1 else None,
            "extrusion": pair.extrusion if pair.use_custom_extrusion else s.cage_extrusion,
        }
        sets.setdefault(pair.set_name, []).append(entry)
        for obj in lows + highs + ([pair.cage] if pair.cage is not None else []):
            objects[obj.name] = _object_entry(obj)
    job["texture_sets"] = [{"name": name, "pairs": entries} for name, entries in sets.items()]
    job["objects"] = objects
    return jobmod.normalize(job)


def referenced_objects(job):
    names = set()
    for ts in job["texture_sets"]:
        for pair in ts["pairs"]:
            names.update(pair["lows"])
            names.update(pair["highs"])
            if pair.get("cage"):
                names.add(pair["cage"])
    return [bpy.data.objects[n] for n in sorted(names) if n in bpy.data.objects]


def write_source(job, job_dir):
    """Write the objects of ``job`` (plus dependencies) into a small .blend for the worker."""
    path = os.path.join(job_dir, "source.blend")
    objs = set(referenced_objects(job))
    bpy.data.libraries.write(path, objs, path_remap="ABSOLUTE", fake_user=True, compress=False)
    job["source_blend"] = path
    return path
