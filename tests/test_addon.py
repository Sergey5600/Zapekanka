# SPDX-License-Identifier: GPL-3.0-or-later
"""Add-on level tests: registration, operators, background worker, exporters."""

import ast
import json
import os
import socket
import struct
import threading
import time
import unittest

import bpy
import helpers
import scenes

import zapekanka
from zapekanka import background, materials, pairing, preflight, translations


def setUpModule():
    zapekanka.register()


def tearDownModule():
    zapekanka.unregister()


class AddonTestCase(unittest.TestCase):
    def setUp(self):
        scenes.reset()
        self.tmp = helpers.TempDir()
        self.s = bpy.context.scene.zapekanka
        self.s.output_dir = os.path.join(self.tmp.path, "textures")
        self.s.export.directory = os.path.join(self.tmp.path, "export")
        self.s.resolution = "CUSTOM"
        self.s.resolution_x = self.s.resolution_y = 64
        self.s.supersample = "1"
        self.s.aa_samples = 1
        self.s.maps.ao_samples = 4

    def tearDown(self):
        self.tmp.cleanup()


class PairingTest(AddonTestCase):
    def test_suffix_detection(self):
        scenes.cube("Gun_low")
        scenes.cube("Gun_high")
        scenes.cube("Gun_high_bolt")
        scenes.cube("gun_HP.001")
        scenes.cube("Gun_cage")
        scenes.cube("Lonely_high")
        scenes.cube("Prop_LP")
        self.assertEqual(bpy.ops.zapekanka.detect_pairs(), {"FINISHED"})
        pairs = {p.name: p for p in self.s.pairs}
        self.assertEqual(sorted(pairs), ["Gun", "Prop"])
        gun = pairs["Gun"]
        self.assertEqual([r.obj.name for r in gun.lows], ["Gun_low"])
        self.assertEqual(sorted(r.obj.name for r in gun.highs), ["Gun_high", "Gun_high_bolt", "gun_HP.001"])
        self.assertEqual(gun.cage.name, "Gun_cage")
        self.assertEqual(len(pairs["Prop"].highs), 0)

    def test_collection_detection(self):
        low_coll = bpy.data.collections.new("Crate_low")
        high_coll = bpy.data.collections.new("Crate_high")
        for coll in (low_coll, high_coll):
            bpy.context.scene.collection.children.link(coll)
        a = scenes.cube("body")
        b = scenes.cube("body_sculpt")
        c = scenes.cube("screws")
        bpy.context.scene.collection.objects.unlink(a)
        low_coll.objects.link(a)
        for obj in (b, c):
            bpy.context.scene.collection.objects.unlink(obj)
            high_coll.objects.link(obj)
        self.s.pair_mode = "COLLECTION"
        bpy.ops.zapekanka.detect_pairs()
        self.assertEqual(len(self.s.pairs), 1)
        pair = self.s.pairs[0]
        self.assertEqual(pair.name, "Crate")
        self.assertEqual([r.obj.name for r in pair.lows], ["body"])
        self.assertEqual(sorted(r.obj.name for r in pair.highs), ["body_sculpt", "screws"])

    def test_redetect_keeps_settings(self):
        scenes.cube("Gun_low")
        scenes.cube("Gun_high")
        bpy.ops.zapekanka.detect_pairs()
        self.s.pairs[0].use_custom_extrusion = True
        self.s.pairs[0].extrusion = 0.3
        bpy.ops.zapekanka.detect_pairs()
        self.assertEqual(len(self.s.pairs), 1)
        self.assertAlmostEqual(self.s.pairs[0].extrusion, 0.3)

    def test_deleted_objects_are_pruned(self):
        scenes.cube("Gun_low")
        high = scenes.cube("Gun_high")
        bpy.ops.zapekanka.detect_pairs()
        bpy.data.objects.remove(high)
        pairing.prune_missing(self.s, bpy.context.scene)
        self.assertEqual(len(self.s.pairs[0].highs), 0)


class PreflightTest(AddonTestCase):
    def codes(self):
        bpy.ops.zapekanka.preflight()
        return {(i.code, i.object_name) for i in self.s.issues}

    def test_detects_and_fixes(self):
        low = scenes.cube("Box_low")
        scenes.cube("Box_high")
        low.scale = (2.0, 1.0, 1.0)
        bpy.context.view_layer.update()
        for layer in list(low.data.uv_layers):
            low.data.uv_layers.remove(layer)
        low.data.flip_normals()
        bpy.ops.zapekanka.detect_pairs()
        codes = self.codes()
        for code in ("SCALE", "NO_UV", "FLIPPED", "NOT_TRIANGULATED"):
            self.assertIn((code, "Box_low"), codes)
        self.assertTrue(any(i.severity == "ERROR" for i in self.s.issues))
        # an operator that reports an error raises when called from Python
        with self.assertRaises(RuntimeError):
            bpy.ops.zapekanka.bake()
        self.assertEqual(os.listdir(self.tmp.path), [], "a blocked bake must not write anything")
        bpy.ops.zapekanka.preflight_fix(index=-1)
        codes = self.codes()
        for code in ("SCALE", "NO_UV", "FLIPPED", "NOT_TRIANGULATED"):
            self.assertNotIn((code, "Box_low"), codes)
        self.assertEqual(tuple(low.scale), (1.0, 1.0, 1.0))

    def test_selection_without_pairs(self):
        tower = scenes.cube("ElecLaneBig")
        for obj in bpy.context.scene.objects:
            obj.select_set(obj is tower)
        codes = self.codes()
        self.assertIn(("SELECTION", ""), codes)
        self.assertIn(("NO_UV", "ElecLaneBig"), codes, "selected objects are checked like a pair")
        self.assertNotIn(("NO_PAIRS", ""), codes)
        tower.select_set(False)
        self.assertIn(("NO_PAIRS", ""), self.codes())

    def test_uv_overlap(self):
        low = scenes.cube("Box_low")
        scenes.unwrap(low)
        scenes.cube("Box_high")
        bpy.ops.zapekanka.detect_pairs()
        self.assertNotIn(("UV_OVERLAP", "Box_low"), self.codes())
        # stack every face on the same square: overlapping and mirrored islands
        uv = low.data.uv_layers.active.data
        corners = ((0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9))
        for poly in low.data.polygons:
            for k, li in enumerate(range(poly.loop_start, poly.loop_start + poly.loop_total)):
                uv[li].uv = corners[k % 4]
        low.data.update()
        self.assertIn(("UV_OVERLAP", "Box_low"), self.codes())

    def test_folded_island(self):
        low = scenes.cube("Box_low")
        scenes.unwrap(low)
        # twist one quad into a bow tie: its two triangles overlap each other
        uv = low.data.uv_layers.active.data
        poly = low.data.polygons[0]
        loops = list(range(poly.loop_start, poly.loop_start + poly.loop_total))
        a, b = uv[loops[0]].uv.copy(), uv[loops[1]].uv.copy()
        uv[loops[0]].uv, uv[loops[1]].uv = b, a
        low.data.update()
        scenes.cube("Box_high")
        bpy.ops.zapekanka.detect_pairs()
        self.assertIn(("UV_OVERLAP", "Box_low"), self.codes())

    def test_overlap_between_objects_in_one_texture_set(self):
        a = scenes.cube("A_low")
        b = scenes.cube("B_low", 2.0, (3, 0, 0))
        scenes.unwrap(a)
        scenes.unwrap(b)
        scenes.cube("A_high")
        scenes.cube("B_high", 2.0, (3, 0, 0))
        bpy.ops.zapekanka.detect_pairs()
        for pair in self.s.pairs:
            pair.texture_set = "Shared"
        self.assertIn(("SET_OVERLAP", ""), self.codes())

    def test_clean_scene_has_no_warnings(self):
        low, high = scenes.box_pair()
        tri = low.modifiers.new("Triangulate", "TRIANGULATE")
        tri.quad_method = "BEAUTY"
        bpy.ops.zapekanka.detect_pairs()
        self.codes()
        bad = [(i.code, i.message) for i in self.s.issues if i.severity != "INFO"]
        self.assertEqual(bad, [])

    def test_uv_rasterizer_coverage(self):
        low = scenes.cube("Box_low")
        scenes.unwrap(low)
        pix, tri = preflight.rasterize_uv(low.data, low.data.uv_layers.active, 256)
        self.assertEqual(len(pix), len(set(pix.tolist())), "a clean unwrap covers every pixel once")
        self.assertGreater(len(pix), 0.3 * 256 * 256)


class CageTest(AddonTestCase):
    def test_preview_follows_extrusion(self):
        scenes.box_pair()
        bpy.ops.zapekanka.detect_pairs()
        self.s.cage_extrusion = 0.1
        self.s.show_cage_preview = True
        preview = bpy.data.objects["ZB_CagePreview_Box_low"]
        xs = [v.co.x for v in preview.data.vertices]
        self.assertAlmostEqual(max(xs), 1.1, places=4)
        self.s.cage_extrusion = 0.2
        preview = bpy.data.objects["ZB_CagePreview_Box_low"]
        self.assertAlmostEqual(max(v.co.x for v in preview.data.vertices), 1.2, places=4)
        self.s.show_cage_preview = False
        self.assertNotIn("ZB_CagePreview_Box_low", bpy.data.objects)
        self.assertNotIn("Zapekanka Cage Preview", bpy.data.collections)

    def test_estimate_extrusion(self):
        scenes.cube("Box_low")
        scenes.cube("Box_high", 2.3)
        bpy.ops.zapekanka.detect_pairs()
        bpy.ops.zapekanka.cage_estimate(target="GLOBAL")
        self.assertGreaterEqual(self.s.cage_extrusion, 0.15)
        self.assertLess(self.s.cage_extrusion, 0.5)
        bpy.ops.zapekanka.cage_estimate(target="ACTIVE")
        self.assertTrue(self.s.pairs[0].use_custom_extrusion)


class BakeOperatorTest(AddonTestCase):
    def test_foreground_bake_assigns_material_and_restores(self):
        low, high = scenes.box_pair()
        high.data.materials.append(scenes.principled("Red", (0.8, 0.1, 0.1, 1.0)))
        original = scenes.principled("Original")
        low.data.materials.append(original)
        bpy.ops.zapekanka.detect_pairs()
        bpy.ops.zapekanka.maps_preset(preset="PBR")
        self.s.bake_mode = "FOREGROUND"
        self.assertEqual(bpy.ops.zapekanka.bake(), {"FINISHED"})
        mat = low.data.materials[0]
        self.assertEqual(mat.name, "M_Box")
        images = {n.image.name: n.image.colorspace_settings.name for n in mat.node_tree.nodes
                  if n.bl_idname == "ShaderNodeTexImage"}
        self.assertEqual(images["T_Box_BC.png"], "sRGB")
        self.assertEqual(images["T_Box_N.png"], "Non-Color")
        self.assertEqual(images["T_Box_ORM.png"], "Non-Color")
        bsdf = next(n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
        for name in ("Base Color", "Roughness", "Metallic", "Normal"):
            self.assertTrue(bsdf.inputs[name].is_linked, name)
        bpy.ops.zapekanka.restore_materials()
        self.assertEqual(low.data.materials[0], original)

    def test_bake_all_without_names_bakes_selection(self):
        # the reported case: objects are not named *_low / *_high, one object is selected
        tower = scenes.cube("ElecLaneBig")
        scenes.unwrap(tower)
        tower.data.materials.append(scenes.principled("Steel", (0.5, 0.5, 0.55, 1.0), metallic=1.0))
        scenes.cube("Fence", 2.0, (5, 0, 0))
        for obj in bpy.context.scene.objects:
            obj.select_set(obj is tower)
        bpy.context.view_layer.objects.active = tower
        self.s.bake_mode = "FOREGROUND"
        bpy.ops.zapekanka.maps_preset(preset="GAME")
        self.assertEqual(bpy.ops.zapekanka.bake(scope="ALL"), {"FINISHED"})
        self.assertEqual([p.name for p in self.s.pairs], ["ElecLaneBig"])
        self.assertEqual(len(self.s.pairs[0].highs), 0)
        names = os.listdir(self.s.output_dir)
        self.assertIn("T_ElecLaneBig_BC.png", names)
        self.assertIn("T_ElecLaneBig_ORM.png", names)

    def test_nothing_to_bake_explains_what_to_do(self):
        scenes.cube("ElecLaneBig")
        for obj in bpy.context.scene.objects:
            obj.select_set(False)
        with self.assertRaises(RuntimeError) as ctx:
            bpy.ops.zapekanka.bake(scope="ALL")
        self.assertIn("Detect Pairs", str(ctx.exception))
        self.assertEqual(len(self.s.pairs), 0)

    def test_device_follows_scene(self):
        from zapekanka import jobbuild

        scenes.box_pair()
        bpy.ops.zapekanka.detect_pairs()
        self.assertEqual(self.s.device, "SCENE")
        bpy.context.scene.cycles.device = "GPU"
        self.assertEqual(jobbuild.build_job(bpy.context)["settings"]["device"], "GPU")
        bpy.context.scene.cycles.device = "CPU"
        self.assertEqual(jobbuild.build_job(bpy.context)["settings"]["device"], "CPU")

    def test_background_bake_with_worker_process(self):
        low, high = scenes.box_pair()
        high.data.materials.append(scenes.principled("Red", (0.8, 0.1, 0.1, 1.0)))
        bpy.ops.zapekanka.detect_pairs()
        bpy.ops.zapekanka.maps_preset(preset="GAME")
        self.s.bake_mode = "BACKGROUND"
        original = background.blender_executable
        background.blender_executable = lambda: helpers.fake_blender(self.tmp.path)
        try:
            self.assertEqual(bpy.ops.zapekanka.bake(), {"FINISHED"})
            self.assertTrue(background.STATE.running)
            deadline = time.time() + 300
            while (background.STATE.running or background.queued_count()) and time.time() < deadline:
                background._tick()
                time.sleep(0.05)
        finally:
            background.blender_executable = original
        result = background.STATE.last_result
        self.assertIsNotNone(result)
        self.assertTrue(result["ok"], result)
        names = sorted(os.listdir(self.s.output_dir))
        self.assertIn("T_Box_BC.png", names)
        self.assertIn("T_Box_ORM.png", names)
        self.assertEqual(low.data.materials[0].name, "M_Box")
        self.assertTrue(os.path.isfile(result["log_path"]))

    def test_background_cancel(self):
        scenes.box_pair()
        bpy.ops.zapekanka.detect_pairs()
        self.s.bake_mode = "BACKGROUND"
        original = background.blender_executable
        background.blender_executable = lambda: helpers.fake_blender(self.tmp.path)
        try:
            bpy.ops.zapekanka.bake()
            bpy.ops.zapekanka.cancel()
            deadline = time.time() + 60
            while background.STATE.running and time.time() < deadline:
                background._tick()
                time.sleep(0.05)
        finally:
            background.blender_executable = original
        self.assertFalse(background.STATE.running)
        self.assertFalse(background.STATE.last_result["ok"])
        self.assertIn("Cancelled", background.STATE.last_result["errors"])

    def test_import_texture_set(self):
        low, high = scenes.box_pair()
        bpy.ops.zapekanka.detect_pairs()
        self.s.bake_mode = "FOREGROUND"
        self.s.material_mode = "NONE"
        bpy.ops.zapekanka.bake()
        sidecar = os.path.join(self.s.output_dir, "Box.zapekanka.json")
        self.assertTrue(os.path.isfile(sidecar))
        for obj in bpy.context.selected_objects:
            obj.select_set(False)
        low.select_set(True)
        bpy.ops.zapekanka.import_texture_set(filepath=sidecar)
        self.assertEqual(low.data.materials[0].name, "M_Box")
        # also without the json, from file names only
        _, baked, _, _ = materials.read_sidecar(sidecar)
        guessed = materials.guess_files(self.s.output_dir, "Box", self.s)
        self.assertEqual({os.path.basename(f["path"]) for f in guessed},
                         {os.path.basename(f["path"]) for f in baked})


class ExportTest(AddonTestCase):
    def setUp(self):
        super().setUp()
        low, high = scenes.box_pair()
        high.data.materials.append(scenes.principled("Red", (0.8, 0.1, 0.1, 1.0)))
        bpy.ops.zapekanka.detect_pairs()
        bpy.ops.zapekanka.maps_preset(preset="GAME")
        self.s.bake_mode = "FOREGROUND"
        bpy.ops.zapekanka.bake()
        self.s.export.ue_live = False

    def export(self, target):
        self.s.export.target = target
        self.assertEqual(bpy.ops.zapekanka.export(), {"FINISHED"})
        return os.path.join(self.tmp.path, "export")

    def test_unreal(self):
        root = os.path.join(self.export("UE5"), "Unreal")
        self.assertTrue(os.path.isfile(os.path.join(root, "Box", "SM_Box.fbx")))
        script = open(os.path.join(root, "import_to_unreal.py"), encoding="utf-8").read()
        ast.parse(script)
        manifest = json.loads(script.split('r"""', 1)[1].split('"""', 1)[0])
        ts = manifest["sets"][0]
        self.assertEqual(ts["material"], "M_Box")
        kinds = {t["file"]: t for t in ts["textures"]}
        self.assertEqual(kinds["T_Box_N.png"]["kind"], "normal")
        self.assertTrue(kinds["T_Box_BC.png"]["srgb"])
        self.assertEqual([c[1] for c in kinds["T_Box_ORM.png"]["connect"]], ["ao", "roughness", "metallic"])

    def test_unity(self):
        root = os.path.join(self.export("UNITY"), "Unity")
        self.assertTrue(os.path.isfile(os.path.join(root, "Assets", "Editor", "Zapekanka",
                                                    "ZapekankaPostprocessor.cs")))
        manifest = json.load(open(os.path.join(root, "Assets", "Zapekanka", "Box", "Box.zapekanka-unity.json")))
        self.assertEqual(manifest["model"], "SM_Box.fbx")

    def test_godot(self):
        root = os.path.join(self.export("GODOT"), "Godot", "zapekanka", "Box")
        tres = open(os.path.join(root, "M_Box.tres"), encoding="utf-8").read()
        self.assertIn("ORMMaterial3D", tres)
        self.assertIn("orm_texture", tres)
        self.assertTrue(os.path.isfile(os.path.join(root, "Box.glb")))

    def test_gltf_roundtrip(self):
        root = os.path.join(self.export("GLTF"), "glTF")
        path = os.path.join(root, "Box.glb")
        self.assertTrue(os.path.isfile(path))
        with open(path, "rb") as fh:
            magic, version, length = struct.unpack("<4sII", fh.read(12))
            chunk_len, chunk_type = struct.unpack("<II", fh.read(8))
            doc = json.loads(fh.read(chunk_len))
        self.assertEqual(magic, b"glTF")
        pbr = doc["materials"][0]["pbrMetallicRoughness"]
        self.assertIn("baseColorTexture", pbr)
        self.assertIn("metallicRoughnessTexture", pbr)
        self.assertIn("normalTexture", doc["materials"][0])
        self.assertIn("occlusionTexture", doc["materials"][0])

    def test_painter_marmoset_roblox(self):
        for target, folder, files in (
            ("SUBSTANCE", "Substance", ("Box_low.fbx", "Box_high.fbx")),
            ("MARMOSET", "Marmoset", ("Box_low.fbx", "Box_high.fbx", "Box_cage.fbx")),
            ("ROBLOX", "Roblox", ("SM_Box.fbx", "README.txt")),
        ):
            root = os.path.join(self.export(target), folder, "Box")
            for name in files:
                self.assertTrue(os.path.isfile(os.path.join(root, name)), "%s/%s" % (target, name))

    def test_export_keeps_scene_clean(self):
        before = helpers.datablock_counts()
        names = sorted(o.name for o in bpy.data.objects)
        for target in ("UE5", "UNITY", "GODOT", "SUBSTANCE", "MARMOSET", "GLTF", "ROBLOX"):
            self.export(target)
        self.assertEqual(sorted(o.name for o in bpy.data.objects), names)
        after = helpers.datablock_counts()
        # exporters may create the baked material/images once; nothing else
        for key in ("objects", "meshes", "scenes", "collections"):
            self.assertEqual(after[key], before[key], key)


class UnrealRemoteTest(unittest.TestCase):
    """Talks to a fake Unreal node implementing the remote execution protocol.

    Multicast is replaced by unicast to the fake node, so the test also runs
    where multicast loopback is not routed (containers, CI).
    """

    def test_protocol(self):
        from zapekanka.exporters import ue_remote

        node = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        node.bind(("127.0.0.1", 0))
        node.settimeout(10)
        node_addr = node.getsockname()
        received = {}

        def fake_unreal():
            me = "fake-unreal"
            while True:
                try:
                    raw, sender = node.recvfrom(65536)
                except socket.timeout:
                    return
                msg = json.loads(raw)
                if msg["type"] == "ping":
                    pong = {"version": 1, "magic": "ue_py", "type": "pong", "source": me, "dest": msg["source"],
                            "data": {"project_name": "Test"}}
                    node.sendto(json.dumps(pong).encode(), sender)
                elif msg["type"] == "open_connection" and msg.get("dest") == me:
                    data = msg["data"]
                    conn = socket.create_connection((data["command_ip"], data["command_port"]), timeout=10)
                    command = json.loads(conn.recv(1 << 20))
                    received["command"] = command["data"]["command"]
                    result = {"version": 1, "magic": "ue_py", "type": "command_result", "source": me,
                              "dest": msg["source"], "data": {"success": True, "result": "None",
                                                              "output": [{"type": "Info", "output": "hello"}]}}
                    conn.sendall(json.dumps(result).encode())
                    conn.close()
                elif msg["type"] == "close_connection":
                    return

        original_send = ue_remote.UnrealRemote._send
        original_open = ue_remote.UnrealRemote._open_udp

        def open_unicast(self):
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(("127.0.0.1", 0))
            sock.settimeout(0.1)
            self._udp = sock

        ue_remote.UnrealRemote._send = lambda self, payload: self._udp.sendto(payload, node_addr)
        ue_remote.UnrealRemote._open_udp = open_unicast
        thread = threading.Thread(target=fake_unreal, daemon=True)
        thread.start()
        try:
            ok, message = ue_remote.send("print('hello')", bind="127.0.0.1", timeout=3)
        finally:
            ue_remote.UnrealRemote._send = original_send
            ue_remote.UnrealRemote._open_udp = original_open
        thread.join(5)
        node.close()
        self.assertTrue(ok, message)
        self.assertEqual(message, "hello")
        self.assertEqual(received["command"], "print('hello')")

    def test_no_editor(self):
        from zapekanka.exporters import ue_remote

        ok, message = ue_remote.send("print(1)", port=46767, timeout=1)
        self.assertFalse(ok)


class TranslationTest(unittest.TestCase):
    def test_ui_strings_are_translated(self):
        """Every label/description in the add-on must have a Russian entry."""
        root = os.path.dirname(zapekanka.__file__)
        missing = set()
        keys = {"text", "name", "description", "bl_label", "bl_description"}
        skip = {"", "Zapekanka", "ZB_Override"}
        for dirpath, _, files in os.walk(root):
            for fname in files:
                if not fname.endswith(".py") or fname == "translations.py":
                    continue
                rel = os.path.relpath(os.path.join(dirpath, fname), root)
                if not (rel in ("props.py", "prefs.py", "ui.py") or rel.startswith("operators")):
                    continue
                tree = ast.parse(open(os.path.join(dirpath, fname), encoding="utf-8").read())
                for node in ast.walk(tree):
                    if isinstance(node, ast.keyword) and node.arg in keys:
                        value = node.value
                    elif isinstance(node, ast.Assign) and len(node.targets) == 1 and \
                            isinstance(node.targets[0], ast.Name) and node.targets[0].id in keys:
                        value = node.value
                    else:
                        continue
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        text = value.value
                    elif isinstance(value, ast.BinOp) and isinstance(value.left, ast.Constant):
                        continue  # formatted at runtime from a translated template
                    else:
                        continue
                    if text in skip or text.startswith(("ZB_", "zapekanka.")) or "%" in text and \
                            text in translations.RU:
                        continue
                    if text not in translations.RU:
                        missing.add(text)
        # enum item labels/descriptions
        import zapekanka.presets as presets_mod
        import zapekanka.props as props_mod

        for items in (presets_mod.PACK_ITEMS, props_mod.EXPORT_TARGETS, presets_mod.PRESET_ITEMS):
            for item in items:
                for text in item[1:3]:
                    if text and text not in translations.RU:
                        missing.add(text)
        self.assertEqual(sorted(missing), [])

    def test_preflight_templates_are_translated(self):
        src = open(preflight.__file__, encoding="utf-8").read()
        tree = ast.parse(src)
        missing = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Issue" and len(node.args) >= 3:
                msg = node.args[2]
                if isinstance(msg, ast.Tuple):
                    msg = msg.elts[0]
                if isinstance(msg, ast.Constant) and msg.value not in translations.RU:
                    missing.append(msg.value)
        for label in preflight.FIX_LABELS.values():
            if label not in translations.RU:
                missing.append(label)
        self.assertEqual(missing, [])

    def test_placeholders_match(self):
        import re

        pattern = re.compile(r"%[-+ #0]*\d*(?:\.\d+)?[sdfgr%]")
        for en, ru in translations.RU.items():
            self.assertEqual(sorted(pattern.findall(en)), sorted(pattern.findall(ru)), en)


if __name__ == "__main__":
    unittest.main()
