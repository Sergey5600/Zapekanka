# SPDX-License-Identifier: GPL-3.0-or-later
"""Test utilities (require bpy)."""

import os
import shutil
import stat
import sys
import tempfile

import bpy
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from zapekanka.core import engine, imageops  # noqa: E402
from zapekanka.core import job as jobmod  # noqa: E402
from zapekanka.core.session import matrix_to_list  # noqa: E402

KEEP_OUTPUT = os.environ.get("ZAPEKANKA_KEEP_TEST_OUTPUT")


class TempDir:
    def __init__(self):
        self.path = tempfile.mkdtemp(prefix="zb_test_")

    def cleanup(self):
        if not KEEP_OUTPUT:
            shutil.rmtree(self.path, ignore_errors=True)


def make_job(out_dir, texture_sets, outputs, maps=(), **settings):
    job = jobmod.new_job()
    job["output_dir"] = out_dir
    job["settings"].update({"resolution": [128, 128], "aa_samples": 1, "margin": 4})
    job["settings"].update(settings)
    for key in maps:
        job["maps"][key]["enabled"] = True
    for key in ("ao", "thickness"):
        job["maps"][key]["samples"] = 8
    job["texture_sets"] = texture_sets
    job["outputs"] = outputs
    names = set()
    for ts in texture_sets:
        for pair in ts["pairs"]:
            names.update(pair["lows"])
            names.update(pair.get("highs", []))
    bpy.context.view_layer.update()
    job["objects"] = {n: {"matrix": matrix_to_list(bpy.data.objects[n].matrix_world)} for n in names}
    return job


def pair(name, lows, highs=(), extrusion=0.05, cage=None):
    return {"name": name, "lows": list(lows), "highs": list(highs), "extrusion": extrusion, "cage": cage}


def output(oid, channels, srgb=False, fmt="PNG", depth=8, file=None):
    return {"id": oid, "file": file or ("T_{name}_" + oid), "channels": channels, "srgb": srgb,
            "format": fmt, "depth": depth}


def run(job):
    logs = []
    result = engine.Engine(job, log=logs.append).run()
    result["log"] = logs
    return result


def files_by_id(result, set_name):
    for ts in result["texture_sets"]:
        if ts["name"] == set_name:
            return {f["id"]: f["path"] for f in ts["files"]}
    return {}


def load(path):
    img = bpy.data.images.load(path)
    try:
        img.colorspace_settings.name = "Non-Color"
        w, h = img.size
        buf = np.empty(w * h * 4, np.float32)
        img.pixels.foreach_get(buf)
        return buf.reshape(h, w, 4)
    finally:
        bpy.data.images.remove(img)


def island_mask(obj, res, erode=2):
    """Pixels whose centre lies inside the UV islands of ``obj`` (eroded)."""
    from zapekanka.preflight import rasterize_uv

    mesh = obj.data
    pix, _ = rasterize_uv(mesh, mesh.uv_layers.active, res)
    mask = np.zeros(res * res, bool)
    mask[pix] = True
    mask = mask.reshape(res, res)
    for _ in range(erode):
        m = mask.copy()
        m[1:] &= mask[:-1]
        m[:-1] &= mask[1:]
        m[:, 1:] &= mask[:, :-1]
        m[:, :-1] &= mask[:, 1:]
        mask = m
    return mask


def datablock_counts():
    return {
        "objects": len(bpy.data.objects),
        "meshes": len(bpy.data.meshes),
        "materials": len(bpy.data.materials),
        "images": len(bpy.data.images),
        "node_groups": len(bpy.data.node_groups),
        "scenes": len(bpy.data.scenes),
        "collections": len(bpy.data.collections),
    }


def object_snapshot(obj):
    return {
        "name": obj.name,
        "matrix": [round(v, 6) for row in obj.matrix_world for v in row],
        "modifiers": [(m.name, m.type, m.show_render) for m in obj.modifiers],
        "slots": [(s.link, s.material.name if s.material else None) for s in obj.material_slots],
        "data": obj.data.name if obj.data else None,
        "verts": len(obj.data.vertices) if obj.type == "MESH" else None,
        "uv": [u.name for u in obj.data.uv_layers] if obj.type == "MESH" else None,
        "hide_render": obj.hide_render,
        "props": sorted(obj.keys()),
    }


def srgb(value):
    return float(imageops.linear_to_srgb(np.array([value], np.float32))[0])


def fake_blender(directory):
    """A stand-in for the Blender executable that runs the worker with this Python (bpy module)."""
    path = os.path.join(directory, "fake_blender")
    with open(path, "w") as fh:
        fh.write('#!/bin/sh\n# args: --background --factory-startup --python-exit-code 1 --python WORKER -- JOB\n'
                 'exec "%s" "$6" -- "$8"\n' % sys.executable)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path
