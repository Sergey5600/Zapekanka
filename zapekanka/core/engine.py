# SPDX-License-Identifier: GPL-3.0-or-later
"""Bake engine: runs a job (see :mod:`job`) and writes texture files.

The same code runs inside the user's Blender session (foreground mode) and in
a ``blender --background`` worker.  Work is organised *pass-major*: every bake
pass is executed for all tiles before the next pass starts, so only the maps
that are still needed by pending outputs are kept in memory.
"""

import json
import os
import time
import zlib

import bpy
import numpy as np

from . import compat, imageio, imageops, shaders
from . import job as jobmod
from .maps import MAPS, expand_channels, output_maps
from .session import UV_NAME, BakeSession, SessionError, scene_context


class BakeCancelled(Exception):
    pass


# Pass definitions -----------------------------------------------------------
# self: bake the joined low onto itself (no ray casting).
# normal: result channels are encoded unit vectors.
PASSES = {
    "COVER": {"self": True, "type": "EMIT", "margin": False, "samples": "one"},
    "NORMAL_T": {"type": "NORMAL", "space": "TANGENT", "normal": True},
    "NORMAL_O": {"type": "NORMAL", "space": "OBJECT", "normal": True},
    "MESH": {"type": "EMIT", "samples": "ao"},
    "ID": {"type": "EMIT"},
    "BASE": {"type": "EMIT"},
    "RMO": {"type": "EMIT"},
    "RM": {"type": "EMIT"},
    "OP": {"type": "EMIT"},
    "EMIT": {"type": "EMIT"},
    "P_LOW": {"self": True, "type": "EMIT", "samples": "one"},
    "N_LOW": {"self": True, "type": "EMIT", "samples": "one"},
    "P_HIGH": {"type": "EMIT"},
}


def plan_passes(required, maps_cfg, transparency):
    passes = ["COVER"]
    curv_method = maps_cfg["curvature"].get("method", "NORMAL")
    if "normal" in required or ("curvature" in required and curv_method == "NORMAL"):
        passes.append("NORMAL_T")
    if "world_normal" in required:
        passes.append("NORMAL_O")
    if "ao" in required or "thickness" in required or ("curvature" in required and curv_method == "POINTINESS"):
        passes.append("MESH")
    if "id" in required:
        passes.append("ID")
    if "base_color" in required:
        passes.append("BASE")
    want_rm = "roughness" in required or "metallic" in required
    want_op = "opacity" in required
    if transparency:
        if want_rm:
            passes.append("RM")
        if want_op:
            passes.append("OP")
    elif want_rm or want_op:
        passes.append("RMO")
    if "emission" in required:
        passes.append("EMIT")
    if "position" in required or "height" in required:
        passes.append("P_LOW")
    if "height" in required:
        passes.extend(["N_LOW", "P_HIGH"])
    return passes


def tile_plan(width, height, ss, max_tile):
    """Split the supersampled image into the fewest tiles that fit ``max_tile``."""

    def count(n_out):
        for n in range(1, n_out + 1):
            if n_out % n == 0 and n_out * ss // n <= max_tile:
                return n
        return n_out

    return count(width), count(height)


def configure_cycles_device(settings, log=print):
    """Worker only: enable the GPU devices chosen in the UI session."""
    if settings.get("device") != "GPU":
        return
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
    except KeyError:
        log("Cycles add-on not available, falling back to CPU")
        settings["device"] = "CPU"
        return
    backend = settings.get("gpu_backend") or "NONE"
    if backend == "NONE":
        settings["device"] = "CPU"
        return
    try:
        prefs.compute_device_type = backend
    except TypeError:
        log("GPU backend %s is not available here, using CPU" % backend)
        settings["device"] = "CPU"
        return
    if hasattr(prefs, "refresh_devices"):
        prefs.refresh_devices()
    else:
        prefs.get_devices()
    wanted = set(settings.get("gpu_devices") or [])
    any_used = False
    for dev in prefs.devices:
        use = (dev.id in wanted) if wanted else dev.type != "CPU"
        dev.use = use
        any_used = any_used or use
    if not any_used:
        log("No GPU device enabled, using CPU")
        settings["device"] = "CPU"


class Engine:
    def __init__(self, job, progress=None, log=None, check_cancel=None):
        self.job = jobmod.normalize(job)
        self.settings = self.job["settings"]
        self.maps_cfg = self.job["maps"]
        self._progress = progress or (lambda frac, msg: None)
        self.log = log or print
        self._cancel = check_cancel or (lambda: False)
        self.session = None
        self.writer = None
        self.steps_done = 0
        self.steps_total = 1

    # ---------------------------------------------------------------- helpers

    def progress(self, message, advance=0):
        self.steps_done += advance
        frac = min(1.0, self.steps_done / max(1, self.steps_total))
        self._progress(frac, message)
        if self._cancel():
            raise BakeCancelled()

    # ---------------------------------------------------------------- run

    def run(self):
        start = time.time()
        result = {"ok": False, "texture_sets": [], "warnings": [], "errors": [], "elapsed": 0.0}
        required = set()
        for out in self.job["outputs"]:
            required |= output_maps(out)
        self.required = required
        try:
            self.progress("Preparing bake scene")
            self.session = BakeSession(self.job, log=self.log)
            self.session.setup()
            self.writer = imageio.ImageWriter()
            plans = {}
            ss = self.settings["supersample"]
            w, h = self.settings["resolution"]
            nx, ny = tile_plan(w, h, ss, int(self.settings.get("max_tile", 8192)))
            for ts in self.job["texture_sets"]:
                highs = self.session.highs[ts["name"]]
                mats = [m for hd in highs for m in hd.effective_materials if m is not None]
                transparency = shaders.has_transparency_nodes(mats)
                plans[ts["name"]] = plan_passes(required, self.maps_cfg, transparency)
            self.steps_total = 1 + sum(len(p) * nx * ny + 1 for p in plans.values())
            self.progress("Scene ready", advance=1)
            for ts in self.job["texture_sets"]:
                info = self.bake_texture_set(ts, plans[ts["name"]], (nx, ny))
                result["texture_sets"].append(info)
            result["ok"] = True
        except BakeCancelled:
            result["errors"].append("Cancelled")
        except (SessionError, jobmod.JobError, RuntimeError) as exc:
            result["errors"].append(str(exc))
            self.log("ERROR: %s" % exc)
        finally:
            if self.session is not None:
                result["warnings"].extend(self.session.warnings)
                self.session.cleanup()
            if self.writer is not None:
                self.writer.close()
        result["elapsed"] = time.time() - start
        return result

    # ---------------------------------------------------------------- texture set

    def bake_texture_set(self, ts, passes, tiles):
        name = ts["name"]
        sess = self.session
        low = sess.lows[name]
        cage = sess.cages[name]
        ss = self.settings["supersample"]
        w, h = self.settings["resolution"]
        nx, ny = tiles
        tw, th = w * ss // nx, h * ss // ny
        tiled = nx * ny > 1
        margin = int(self.settings["margin"])
        max_tile = int(self.settings.get("max_tile", 8192))
        margin_type = self.settings.get("margin_type", "ADJACENT_FACES")
        # Adjacent-faces padding copies pixels from the face across a UV seam,
        # which is usually in another tile.  Tiles are then baked without
        # padding and the padding comes from one extra bake at output size.
        separate_margin = tiled and margin > 0 and margin_type == "ADJACENT_FACES" and max(w, h) <= max_tile
        if tiled and margin > 0 and margin_type == "ADJACENT_FACES" and not separate_margin:
            sess.warn("%s: output is larger than the tile size, padding uses 'Extend' instead of "
                      "'Adjacent Faces'", name)
            margin_type = "EXTEND"
        # Tiles overlap so 'Extend' padding sees islands of neighbouring tiles;
        # the overlap is cropped away after baking.
        pad = 0 if not tiled else (2 if separate_margin else margin * ss + 2)
        self.log("Texture set %s: %dx%d, supersample %dx, %d tile(s) of %dx%d, passes: %s"
                 % (name, w, h, ss, nx * ny, tw, th, ", ".join(passes)))
        image = bpy.data.images.new("ZB_Target_" + name, tw + 2 * pad, th + 2 * pad, alpha=True, float_buffer=True)
        sess.reg.images.append(image)
        compat.set_colorspace(image, "data")
        target = shaders.target_material(sess.reg, "ZB_Target_" + name, image)
        lo, hi = sess.bounds[name]
        enc_pad = 0.5 * float(np.max(hi - lo)) + 4.0 * sess.max_extrusion[name] + 1e-3
        enc_lo = lo - enc_pad
        enc_size = (hi - lo) + 2.0 * enc_pad
        ctx = {
            "name": name, "low": low, "cage": cage, "image": image, "target": target,
            "enc_lo": enc_lo, "enc_size": enc_size,
            "buffer": np.empty((tw + 2 * pad) * (th + 2 * pad) * 4, np.float32),
            "tiles": tiles, "tile_size": (tw, th), "pad": pad,
            "separate_margin": separate_margin, "margin_type": margin_type, "margin_image": None,
        }
        uv_layer = low.data.uv_layers[UV_NAME]
        uv_orig = np.empty(len(low.data.loops) * 2, np.float32)
        uv_layer.data.foreach_get("uv", uv_orig)
        ctx["uv_orig"] = uv_orig

        store = MapStore(self, name, (enc_lo, enc_size))
        meta = {}
        missed = None
        try:
            for pass_id in passes:
                data, weight = self.run_pass(ctx, pass_id)
                if pass_id == "COVER":
                    store.cover = weight > 0
                    continue
                if missed is None and not PASSES[pass_id].get("self") and store.cover is not None:
                    inside = store.cover.sum()
                    if inside:
                        missed = float((store.cover & (weight <= 0)).sum() / inside)
                self.consume_pass(store, pass_id, data, weight, meta)
                store.flush()
        finally:
            uv_layer = low.data.uv_layers.get(UV_NAME)
            if uv_layer is not None:
                uv_layer.data.foreach_set("uv", uv_orig)
        store.flush(final=True)
        if missed is not None and missed > 0.002:
            sess.warn("%s: %.1f%% of texels were not hit by rays (filled from neighbours). "
                      "Increase the cage extrusion or ray distance.", name, missed * 100.0)
        self.progress("Saved %s" % name, advance=1)
        info = {
            "name": name, "files": store.files, "meta": meta, "missed_ratio": missed or 0.0,
            "resolution": [w, h], "ray_distance": sess.ray_distance[name],
        }
        self._write_sidecar(info)
        return info

    def _write_sidecar(self, info):
        out_dir = self.job["output_dir"]
        path = os.path.join(out_dir, "%s.zapekanka.json" % info["name"])
        payload = {
            "generator": "Zapekanka",
            "texture_set": info["name"],
            "resolution": info["resolution"],
            "normal_format": self.settings["normal_format"],
            "outputs": [
                {"id": f["id"], "file": os.path.basename(f["path"]), "channels": f["channels"],
                 "srgb": f["srgb"]}
                for f in info["files"]
            ],
            "meta": info["meta"],
        }
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            info["sidecar"] = path
        except OSError as exc:
            self.session.warn("Could not write %s: %s", path, str(exc))

    # ---------------------------------------------------------------- passes

    def _samples(self, pass_id):
        kind = PASSES[pass_id].get("samples", "aa")
        aa = max(1, int(self.settings["aa_samples"]))
        if kind == "one":
            return 1
        if kind == "ao":
            counts = [aa]
            if "ao" in self.required:
                counts.append(int(self.maps_cfg["ao"].get("samples", 32)))
            if "thickness" in self.required:
                counts.append(int(self.maps_cfg["thickness"].get("samples", 32)))
            return max(counts)
        return aa

    def prepare_pass(self, ctx, pass_id):
        """Switch materials/visibility for ``pass_id``. Returns the bake kwargs."""
        sess = self.session
        reg = sess.reg
        name = ctx["name"]
        highs = sess.highs[name]
        low = ctx["low"]
        info = PASSES[pass_id]
        sess.isolate(name, self_bake=info.get("self", False))
        mesh = low.data
        if info.get("self"):
            kind = {"COVER": "cover", "P_LOW": "position", "N_LOW": "normal"}[pass_id]
            mat = reg.cached(("self", name, kind), lambda: shaders.low_self_material(
                reg, kind, ctx["image"], ctx["enc_lo"], ctx["enc_size"]))
        else:
            mat = ctx["target"]
        if len(mesh.materials) == 0:
            mesh.materials.append(mat)
        else:
            mesh.materials[0] = mat

        maps = self.maps_cfg

        def uniform(key, factory):
            mat_ = reg.cached(("uniform", name, key), factory)
            group = reg.cached(("gn", mat_.name, None), lambda: shaders.gn_set_material(reg, mat_))
            for hd in highs:
                hd.set_uniform(group)

        if pass_id in ("NORMAL_T", "NORMAL_O", "EMIT") or info.get("self"):
            for hd in highs:
                hd.set_original()
        elif pass_id == "MESH":
            uniform("mesh", lambda: shaders.mesh_maps_material(
                reg,
                ao="ao" in self.required,
                ao_distance=float(maps["ao"]["distance"]),
                ao_only_self=bool(maps["ao"].get("only_self")),
                thickness="thickness" in self.required,
                thickness_distance=float(maps["thickness"]["distance"]),
                pointiness="curvature" in self.required and maps["curvature"].get("method") == "POINTINESS",
            ))
        elif pass_id == "P_HIGH":
            uniform("p_high", lambda: shaders.high_position_material(reg, ctx["enc_lo"], ctx["enc_size"]))
        elif pass_id == "ID":
            self._prepare_id(ctx, highs)
        elif pass_id in ("BASE", "RMO", "RM", "OP"):
            kind = "base_color" if pass_id == "BASE" else "rmo"
            bypass = pass_id in ("BASE", "RM")
            conv = reg.cached(("converter", kind, bypass), lambda: shaders.ChannelConverter(reg, kind, bypass))
            fallback_mat = conv.convert(None)
            fallback = reg.cached(("gn", fallback_mat.name, None), lambda: shaders.gn_set_material(reg, fallback_mat))
            for hd in highs:
                hd.set_per_slot(conv.convert, fallback)
        else:
            raise ValueError(pass_id)

        margin = int(self.settings["margin"]) * self.settings["supersample"]
        if not info.get("margin", True) or ctx["separate_margin"]:
            margin = 0
        params = {
            "type": info["type"],
            "pass_filter": set(),
            "margin": margin,
            "margin_type": ctx["margin_type"],
            "use_selected_to_active": not info.get("self", False),
            "max_ray_distance": float(sess.ray_distance[name]),
            "cage_extrusion": 0.0,
            "cage_object": ctx["cage"].name,
            "use_cage": not info.get("self", False),
            "normal_space": info.get("space", "TANGENT"),
            "normal_r": "POS_X",
            "normal_g": "POS_Y",
            "normal_b": "POS_Z",
            "target": "IMAGE_TEXTURES",
            "save_mode": "INTERNAL",
            "use_clear": False,
            "use_split_materials": False,
            "use_automatic_name": False,
            "uv_layer": UV_NAME,
        }
        sess.scene.cycles.samples = self._samples(pass_id)
        selected = [low] if info.get("self") else [low] + [hd.obj for hd in highs]
        return params, selected

    def _prepare_id(self, ctx, highs):
        reg = self.session.reg
        cfg = self.maps_cfg["id"]
        source = cfg.get("source", "MATERIAL")
        name = ctx["name"]
        if source == "MATERIAL":
            def mapper(mat):
                key = mat.name if mat is not None else "<none>"
                return reg.cached(("idmat", key), lambda: shaders.constant_emission_material(
                    reg, "ZB_ID_" + key, shaders.id_color(key)))
            none_mat = mapper(None)
            fallback = reg.cached(("gn", none_mat.name, None), lambda: shaders.gn_set_material(reg, none_mat))
            for hd in highs:
                hd.set_per_slot(mapper, fallback)
        elif source == "OBJECT":
            mat = reg.cached(("idobj",), lambda: shaders.id_attribute_material(reg, "zb_idcol", "OBJECT"))
            group = reg.cached(("gn", mat.name, None), lambda: shaders.gn_set_material(reg, mat))
            for hd in highs:
                hd.obj["zb_idcol"] = shaders.id_color(hd.original_name)
                hd.set_uniform(group)
        elif source == "ISLAND":
            mat = reg.cached(("idisl",), lambda: shaders.id_attribute_material(reg, "zb_island", "GEOMETRY"))
            for i, hd in enumerate(highs):
                group = reg.cached(("gnisl", name, i), lambda: shaders.gn_set_material(
                    reg, mat, island_attribute="zb_island", seed=zlib.crc32(hd.original_name.encode()) % 10000))
                hd.set_uniform(group)
        else:  # VERTEX_COLOR
            attr = cfg.get("attribute") or "Color"
            mat = reg.cached(("idvc", attr), lambda: shaders.id_attribute_material(reg, attr, "GEOMETRY"))
            group = reg.cached(("gn", mat.name, None), lambda: shaders.gn_set_material(reg, mat))
            for hd in highs:
                hd.set_uniform(group)

    def run_pass(self, ctx, pass_id):
        w, h = self.settings["resolution"]
        ss = self.settings["supersample"]
        nx, ny = ctx["tiles"]
        tw, th = ctx["tile_size"]
        pad = ctx["pad"]
        iw, ih = tw + 2 * pad, th + 2 * pad
        image = ctx["image"]
        buf = ctx["buffer"]
        low = ctx["low"]
        is_normal = PASSES[pass_id].get("normal", False)
        channels = 3
        out = np.zeros((h, w, channels), np.float32)
        wout = np.zeros((h, w), np.float32)
        params, selected = self.prepare_pass(ctx, pass_id)
        uv_layer = low.data.uv_layers[UV_NAME]
        uv_orig = ctx["uv_orig"]
        ow, oh = tw // ss, th // ss
        for j in range(ny):
            for i in range(nx):
                label = "%s: %s" % (ctx["name"], pass_id)
                if nx * ny > 1:
                    label += " (tile %d/%d)" % (j * nx + i + 1, nx * ny)
                self.progress(label)
                if nx * ny > 1:
                    full = np.array([w * ss, h * ss], np.float64)
                    origin = np.array([i * tw - pad, j * th - pad], np.float64)
                    size = np.array([iw, ih], np.float64)
                    uv = (uv_orig.reshape(-1, 2) * full - origin) / size
                    uv_layer.data.foreach_set("uv", uv.astype(np.float32).ravel())
                buf.fill(0.0)
                image.pixels.foreach_set(buf)
                with scene_context(self.session.scene, low, selected):
                    res = bpy.ops.object.bake(**params)
                if "FINISHED" not in res:
                    raise RuntimeError("Bake pass %s failed for %s" % (pass_id, ctx["name"]))
                image.pixels.foreach_get(buf)
                tile = buf.reshape(ih, iw, 4)[pad:pad + th, pad:pad + tw]
                if is_normal:
                    data, weight = imageops.downsample_normals(tile[..., :3], tile[..., 3], ss)
                else:
                    data, weight = imageops.downsample(tile[..., :3], tile[..., 3], ss)
                out[j * oh:(j + 1) * oh, i * ow:(i + 1) * ow] = data
                wout[j * oh:(j + 1) * oh, i * ow:(i + 1) * ow] = weight
                self.progress(label, advance=1)
        if ctx["separate_margin"] and PASSES[pass_id].get("margin", True):
            uv_layer.data.foreach_set("uv", uv_orig)
            self._bake_margin(ctx, params, selected, out, wout)
        return out, wout

    def _bake_margin(self, ctx, params, selected, out, wout):
        """Fill the padding of a tiled pass from a bake at output resolution."""
        w, h = self.settings["resolution"]
        low = ctx["low"]
        img = ctx["margin_image"]
        if img is None:
            img = bpy.data.images.new("ZB_Margin_" + ctx["name"], w, h, alpha=True, float_buffer=True)
            self.session.reg.images.append(img)
            compat.set_colorspace(img, "data")
            ctx["margin_image"] = img
        node = low.data.materials[0].node_tree.nodes.get("ZB_BakeTarget")
        previous = node.image
        node.image = img
        buf = np.zeros(w * h * 4, np.float32)
        img.pixels.foreach_set(buf)
        margin_params = dict(params, margin=int(self.settings["margin"]))
        try:
            with scene_context(self.session.scene, low, selected):
                res = bpy.ops.object.bake(**margin_params)
        finally:
            node.image = previous
        if "FINISHED" not in res:
            raise RuntimeError("Padding bake failed for %s" % ctx["name"])
        img.pixels.foreach_get(buf)
        full = buf.reshape(h, w, 4)
        fill = (wout <= 0) & (full[..., 3] > 0)
        out[fill] = full[..., :3][fill]
        wout[fill] = 1.0

    # ---------------------------------------------------------------- maps

    def consume_pass(self, store, pass_id, data, weight, meta):
        maps = self.maps_cfg
        req = self.required
        if pass_id == "NORMAL_T":
            normal = store.finalize("normal", data, weight)
            if "curvature" in req and maps["curvature"].get("method", "NORMAL") == "NORMAL":
                inside = store.cover if store.cover is not None else weight > 0
                curv = imageops.curvature_from_normal(
                    normal, float(maps["curvature"].get("strength", 1.0)),
                    float(maps["curvature"].get("radius", 1.0)), mask=inside)
                # Outside the islands the value is rebuilt from the interior.
                store.put("curvature", curv, inside.astype(np.float32))
            if "normal" in req:
                store.put("normal", normal, weight, finalized=True)
        elif pass_id == "NORMAL_O":
            store.put("world_normal", data, weight)
        elif pass_id == "MESH":
            if "ao" in req:
                store.put("ao", data[..., 0:1], weight)
            if "thickness" in req:
                store.put("thickness", data[..., 1:2], weight)
            if "curvature" in req and maps["curvature"].get("method") == "POINTINESS":
                curv = imageops.remap_pointiness(data[..., 2:3], float(maps["curvature"].get("strength", 1.0)))
                store.put("curvature", curv, weight)
        elif pass_id == "ID":
            store.put("id", data, weight)
        elif pass_id == "BASE":
            store.put("base_color", data, weight)
        elif pass_id in ("RMO", "RM", "OP"):
            if pass_id != "OP":
                if "roughness" in req:
                    store.put("roughness", data[..., 0:1], weight)
                if "metallic" in req:
                    store.put("metallic", data[..., 1:2], weight)
            if pass_id != "RM" and "opacity" in req:
                store.put("opacity", data[..., 2:3], weight)
        elif pass_id == "EMIT":
            store.put("emission", data, weight)
        elif pass_id == "P_LOW":
            ctx_lo, ctx_size = store.encoding
            pos = data * ctx_size + ctx_lo
            if "position" in req:
                lo, hi = self.session.bounds[store.name]
                store.put("position", imageops.normalize_positions(pos, lo, hi), weight)
                meta["position"] = {"min": [float(v) for v in lo], "max": [float(v) for v in hi]}
            if "height" in req:
                store.temp["p_low"] = (pos, weight)
        elif pass_id == "N_LOW":
            store.temp["n_low"] = (data * 2.0 - 1.0, weight)
        elif pass_id == "P_HIGH":
            ctx_lo, ctx_size = store.encoding
            p_high = data * ctx_size + ctx_lo
            p_low, w_low = store.temp.pop("p_low")
            n_low, w_n = store.temp.pop("n_low")
            valid = (weight > 0) & (w_low > 0) & (w_n > 0)
            cfg = maps["height"]
            height, rng = imageops.height_from_positions(
                p_high, p_low, n_low, valid, cfg.get("range_mode", "AUTO"), float(cfg.get("range", 0.1)))
            meta["height"] = {"range": rng, "midlevel": 0.5, "scale": 2.0 * rng}
            store.put("height", height, valid.astype(np.float32))


class MapStore:
    """Holds finished maps until every output that needs them is written."""

    def __init__(self, engine, name, encoding):
        self.engine = engine
        self.name = name
        self.cover = None
        self.maps = {}
        self.temp = {}
        self.files = []
        self.pending = list(engine.job["outputs"])
        self.encoding = (np.asarray(encoding[0], np.float32), np.asarray(encoding[1], np.float32))

    def finalize(self, key, data, weight):
        """Fill holes / background according to settings. Returns new array."""
        settings = self.engine.settings
        mdef = MAPS[key]
        valid = weight > 0
        cover = self.cover if self.cover is not None else valid
        region = None if settings.get("fill_empty", True) else cover
        if mdef.normal:
            vec = imageops.decode_normals(data)
            vec = imageops.fill_holes(vec, valid, region)
            data = imageops.encode_normals(imageops.normalize_vectors(vec.reshape(-1, 3)).reshape(vec.shape))
        else:
            data = imageops.fill_holes(data, valid, region)
        if region is not None:
            outside = ~(valid | cover)
            data[outside] = np.asarray(mdef.background, np.float32)[: data.shape[2]]
        return data.astype(np.float32, copy=False)

    def put(self, key, data, weight, finalized=False):
        if not finalized:
            data = self.finalize(key, np.array(data, np.float32), weight)
        self.maps[key] = data

    def _trim_empty(self, out, chans):
        """Drop outputs/alpha channels that carry no information.

        Emission that is black everywhere and opacity that is fully opaque
        are skipped; an opaque alpha channel is removed from packed outputs.
        """
        def constant(key, value):
            data = self.maps.get(key)
            return data is not None and float(np.abs(data - value).max()) < 1e-3

        keys = {c.map for c in chans if not c.is_constant}
        if keys == {"emission"} and constant("emission", 0.0):
            return chans, True
        if keys == {"opacity"} and constant("opacity", 1.0):
            return chans, True
        if len(chans) == 4 and chans[3].map == "opacity" and not chans[3].invert and constant("opacity", 1.0):
            return chans[:3], False
        return chans, False

    def flush(self, final=False):
        writer = self.engine.writer
        settings = self.engine.settings
        out_dir = self.engine.job["output_dir"]
        still = []
        for out in self.pending:
            needed = output_maps(out)
            ready = all(k in self.maps for k in needed)
            if not ready and not final:
                still.append(out)
                continue
            chans = expand_channels(out["channels"])
            if settings.get("skip_empty", True):
                chans, skip = self._trim_empty(out, chans)
                if skip:
                    self.engine.log("Skipped %s: map is empty" % out["id"])
                    continue
            h, w = settings["resolution"][1], settings["resolution"][0]
            arr = np.empty((h, w, len(chans)), np.float32)
            for i, ch in enumerate(chans):
                if ch.is_constant:
                    arr[..., i] = ch.constant
                    continue
                src = self.maps.get(ch.map)
                if src is None:
                    arr[..., i] = MAPS[ch.map].default
                    continue
                v = src[..., ch.index]
                if ch.map == "normal" and ch.index == 1 and settings.get("normal_format") == "DIRECTX":
                    v = 1.0 - v
                if out.get("srgb") and MAPS[ch.map].color:
                    v = imageops.linear_to_srgb(v)
                if ch.invert:
                    v = 1.0 - v
                arr[..., i] = v
            fmt = out.get("format", "PNG")
            filename = out["file"].format(name=self.name) + imageio.FORMAT_EXT.get(fmt, ".png")
            path = os.path.join(out_dir, filename)
            writer.save(arr, path, fmt, int(out.get("depth", 8)))
            self.engine.log("Wrote %s" % path)
            self.files.append({"id": out["id"], "path": path, "channels": out["channels"],
                               "srgb": bool(out.get("srgb"))})
        self.pending = still
        # release maps nobody needs any more
        needed = set()
        for out in self.pending:
            needed |= output_maps(out)
        for key in list(self.maps):
            if key not in needed:
                del self.maps[key]
