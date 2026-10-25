# SPDX-License-Identifier: GPL-3.0-or-later
"""End-to-end bake tests: real Cycles bakes checked pixel by pixel."""

import os
import unittest

import bpy
import helpers
import numpy as np
import scenes
from helpers import output, pair


class BakeTestCase(unittest.TestCase):
    def setUp(self):
        scenes.reset()
        self.tmp = helpers.TempDir()

    def tearDown(self):
        self.tmp.cleanup()

    def bake(self, texture_sets, outputs, maps=(), **settings):
        job = helpers.make_job(self.tmp.path, texture_sets, outputs, maps, **settings)
        result = helpers.run(job)
        self.assertTrue(result["ok"], "bake failed: %s\n%s" % (result["errors"], "\n".join(result["log"])))
        return result


class NormalMapTest(BakeTestCase):
    def test_identical_high_gives_flat_normals(self):
        low = scenes.cube("Box_low")
        scenes.unwrap(low)
        scenes.cube("Box_high")
        res = self.bake([{"name": "Box", "pairs": [pair("Box", ["Box_low"], ["Box_high"])]}],
                        [output("normal", ["normal"])], maps=["normal"])
        n = helpers.load(helpers.files_by_id(res, "Box")["normal"])
        mask = helpers.island_mask(low, 128)
        np.testing.assert_allclose(n[mask][:, :3].mean(axis=0), (0.5, 0.5, 1.0), atol=0.01)
        self.assertEqual(res["texture_sets"][0]["missed_ratio"], 0.0)

    def test_directx_flips_green_only(self):
        low, high = scenes.box_pair()
        ts = [{"name": "Box", "pairs": [pair("Box", ["Box_low"], ["Box_high"], 0.25)]}]
        gl = helpers.load(helpers.files_by_id(self.bake(ts, [output("n", ["normal"], file="GL")], ["normal"]),
                                              "Box")["n"])
        dx = helpers.load(helpers.files_by_id(self.bake(ts, [output("n", ["normal"], file="DX")], ["normal"],
                                                        normal_format="DIRECTX"), "Box")["n"])
        mask = helpers.island_mask(low, 128)
        np.testing.assert_allclose(dx[..., 0][mask], gl[..., 0][mask], atol=2 / 255)
        np.testing.assert_allclose(dx[..., 1][mask], 1.0 - gl[..., 1][mask], atol=2 / 255)
        self.assertGreater(float(np.abs(gl[..., 1][mask] - 0.5).max()), 0.1, "bevel should tilt normals")

    def test_mirrored_low_poly(self):
        low = scenes.cube("Box_low")
        scenes.unwrap(low)
        low.scale = (-1.0, 1.0, 1.0)
        scenes.cube("Box_high")
        res = self.bake([{"name": "Box", "pairs": [pair("Box", ["Box_low"], ["Box_high"])]}],
                        [output("normal", ["normal"])], maps=["normal"])
        n = helpers.load(helpers.files_by_id(res, "Box")["normal"])
        mask = helpers.island_mask(low, 128)
        np.testing.assert_allclose(n[mask][:, 2].mean(), 1.0, atol=0.01)

    def test_custom_cage_object(self):
        low = scenes.cube("Box_low")
        scenes.unwrap(low)
        cage = scenes.cube("Box_cage", 2.3)
        scenes.cube("Box_high", 2.2)
        ts = [{"name": "Box", "pairs": [pair("Box", ["Box_low"], ["Box_high"], extrusion=0.0, cage="Box_cage")]}]
        res = self.bake(ts, [output("normal", ["normal"])], maps=["normal"])
        self.assertLess(res["texture_sets"][0]["missed_ratio"], 0.01)
        self.assertEqual(cage.name, "Box_cage")

    def test_missed_rays_are_reported(self):
        low = scenes.cube("Box_low")
        scenes.unwrap(low)
        scenes.cube("Box_high", 1.0)  # far inside: an extrusion of 0 never reaches it
        res = self.bake([{"name": "Box", "pairs": [pair("Box", ["Box_low"], ["Box_high"], extrusion=0.0)]}],
                        [output("normal", ["normal"])], maps=["normal"], ray_distance=0.01)
        self.assertGreater(res["texture_sets"][0]["missed_ratio"], 0.5)
        self.assertTrue(any("not hit" in w["template"] for w in res["warnings"]))


class PbrTest(BakeTestCase):
    def _red_metal(self):
        low, high = scenes.box_pair()
        high.data.materials.append(scenes.principled("Red", (0.8, 0.2, 0.1, 1.0), roughness=0.3, metallic=1.0))
        return low, high

    def test_pbr_values_and_color_spaces(self):
        low, _ = self._red_metal()
        # bright light and world must not leak into the material maps
        light = bpy.data.lights.new("Sun", "SUN")
        light.energy = 50
        bpy.context.scene.collection.objects.link(bpy.data.objects.new("Sun", light))
        res = self.bake(
            [{"name": "Box", "pairs": [pair("Box", ["Box_low"], ["Box_high"], 0.25)]}],
            [output("bc", ["base_color"], srgb=True), output("orm", ["ao", "roughness", "metallic"])],
            maps=["base_color", "roughness", "metallic", "ao"])
        files = helpers.files_by_id(res, "Box")
        mask = helpers.island_mask(low, 128)
        bc = helpers.load(files["bc"])[mask][:, :3].mean(axis=0)
        np.testing.assert_allclose(bc, [helpers.srgb(0.8), helpers.srgb(0.2), helpers.srgb(0.1)], atol=2 / 255)
        orm = helpers.load(files["orm"])[mask]
        self.assertGreater(orm[:, 0].mean(), 0.8)
        np.testing.assert_allclose(orm[:, 1].mean(), 0.3, atol=2 / 255)
        np.testing.assert_allclose(orm[:, 2].mean(), 1.0, atol=2 / 255)

    def test_linked_inputs_and_groups(self):
        low, high = scenes.box_pair()
        mat = scenes.principled("Linked")
        nt = mat.node_tree
        bsdf = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
        rgb = nt.nodes.new("ShaderNodeRGB")
        rgb.outputs[0].default_value = (0.1, 0.6, 0.2, 1.0)
        nt.links.new(rgb.outputs[0], bsdf.inputs["Base Color"])
        val = nt.nodes.new("ShaderNodeValue")
        val.outputs[0].default_value = 0.7
        nt.links.new(val.outputs[0], bsdf.inputs["Roughness"])
        # wrap the BSDF output in a group to make sure groups are converted too
        group = bpy.data.node_groups.new("Wrap", "ShaderNodeTree")
        group.interface.new_socket(name="Shader", in_out="INPUT", socket_type="NodeSocketShader")
        group.interface.new_socket(name="Shader", in_out="OUTPUT", socket_type="NodeSocketShader")
        gi = group.nodes.new("NodeGroupInput")
        go = group.nodes.new("NodeGroupOutput")
        group.links.new(gi.outputs[0], go.inputs[0])
        gnode = nt.nodes.new("ShaderNodeGroup")
        gnode.node_tree = group
        out = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
        nt.links.new(bsdf.outputs[0], gnode.inputs[0])
        nt.links.new(gnode.outputs[0], out.inputs["Surface"])
        high.data.materials.append(mat)
        res = self.bake([{"name": "Box", "pairs": [pair("Box", ["Box_low"], ["Box_high"], 0.25)]}],
                        [output("bc", ["base_color"], srgb=True), output("r", ["roughness"])],
                        maps=["base_color", "roughness"])
        files = helpers.files_by_id(res, "Box")
        mask = helpers.island_mask(low, 128)
        np.testing.assert_allclose(helpers.load(files["bc"])[mask][:, :3].mean(axis=0),
                                   [helpers.srgb(0.1), helpers.srgb(0.6), helpers.srgb(0.2)], atol=2 / 255)
        np.testing.assert_allclose(helpers.load(files["r"])[mask][:, 0].mean(), 0.7, atol=2 / 255)
        # the user's material and group are untouched
        self.assertEqual(len(group.nodes), 2)
        self.assertIn("ShaderNodeBsdfPrincipled", [n.bl_idname for n in nt.nodes])

    def test_cutout_opacity_and_unpremultiplied_color(self):
        low, high = scenes.box_pair()
        mat = scenes.principled("Cut", (0.9, 0.1, 0.1, 1.0))
        nt = mat.node_tree
        bsdf = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
        out = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
        mix = nt.nodes.new("ShaderNodeMixShader")
        mix.inputs[0].default_value = 0.75
        transparent = nt.nodes.new("ShaderNodeBsdfTransparent")
        nt.links.new(transparent.outputs[0], mix.inputs[1])
        nt.links.new(bsdf.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs["Surface"])
        high.data.materials.append(mat)
        res = self.bake([{"name": "Box", "pairs": [pair("Box", ["Box_low"], ["Box_high"], 0.25)]}],
                        [output("bc", ["base_color.r", "base_color.g", "base_color.b", "opacity"], srgb=True)],
                        maps=["base_color", "opacity"])
        img = helpers.load(helpers.files_by_id(res, "Box")["bc"])
        mask = helpers.island_mask(low, 128)
        np.testing.assert_allclose(img[mask][:, 0].mean(), helpers.srgb(0.9), atol=2 / 255)
        np.testing.assert_allclose(img[mask][:, 3].mean(), 0.75, atol=2 / 255)

    def test_emission_and_skip_empty(self):
        low, high = scenes.box_pair()
        high.data.materials.append(scenes.principled("Glow", emission=(0.0, 1.0, 0.0, 1.0)))
        l2, h2 = scenes.box_pair("Dark", (5, 0, 0))
        h2.data.materials.append(scenes.principled("Dark"))
        res = self.bake([{"name": "Box", "pairs": [pair("Box", ["Box_low"], ["Box_high"], 0.25)]},
                         {"name": "Dark", "pairs": [pair("Dark", ["Dark_low"], ["Dark_high"], 0.25)]}],
                        [output("e", ["emission"], srgb=True)], maps=["emission"])
        files = helpers.files_by_id(res, "Box")
        mask = helpers.island_mask(low, 128)
        np.testing.assert_allclose(helpers.load(files["e"])[mask][:, :3].mean(axis=0), (0, 1, 0), atol=2 / 255)
        self.assertNotIn("e", helpers.files_by_id(res, "Dark"), "black emission must be skipped")

    def test_low_without_high_bakes_own_material(self):
        low = scenes.cube("Solo_low")
        scenes.unwrap(low)
        low.data.materials.append(scenes.principled("Blue", (0.1, 0.2, 0.9, 1.0)))
        res = self.bake([{"name": "Solo", "pairs": [pair("Solo", ["Solo_low"])]}],
                        [output("bc", ["base_color"], srgb=True)], maps=["base_color"])
        mask = helpers.island_mask(low, 128)
        bc = helpers.load(helpers.files_by_id(res, "Solo")["bc"])[mask][:, :3].mean(axis=0)
        np.testing.assert_allclose(bc, [helpers.srgb(0.1), helpers.srgb(0.2), helpers.srgb(0.9)], atol=2 / 255)
        self.assertEqual(low.data.materials[0].name, "Blue")


class MeshMapsTest(BakeTestCase):
    def test_all_mesh_maps_run(self):
        low, high = scenes.box_pair()
        keys = ["normal", "ao", "curvature", "thickness", "position", "world_normal", "height", "id"]
        outs = [output(k, [k], depth=16 if k in ("position", "height") else 8) for k in keys]
        outs.append(output("h_exr", ["height"], fmt="OPEN_EXR", depth=32))
        res = self.bake([{"name": "Box", "pairs": [pair("Box", ["Box_low"], ["Box_high"], 0.25)]}], outs, keys)
        files = helpers.files_by_id(res, "Box")
        for key in keys + ["h_exr"]:
            self.assertTrue(os.path.isfile(files[key]), key)
        meta = res["texture_sets"][0]["meta"]
        self.assertIn("height", meta)
        self.assertIn("position", meta)
        mask = helpers.island_mask(low, 128)
        height = helpers.load(files["height"])[mask][:, 0]
        self.assertLess(height.min(), 0.45, "bevelled edges lie below the low poly")
        pos = helpers.load(files["position"])[mask][:, :3]
        self.assertTrue((pos >= 0).all() and (pos <= 1).all())
        wn = helpers.load(files["world_normal"])[mask][:, :3] * 2 - 1
        np.testing.assert_allclose(np.linalg.norm(wn, axis=1).mean(), 1.0, atol=0.02)

    def test_id_per_material(self):
        low, high = scenes.box_pair()
        high.data.materials.append(scenes.principled("A"))
        high.data.materials.append(scenes.principled("B"))
        polys = high.data.polygons
        polys.foreach_set("material_index", [i % 2 for i in range(len(polys))])
        res = self.bake([{"name": "Box", "pairs": [pair("Box", ["Box_low"], ["Box_high"], 0.25)]}],
                        [output("id", ["id"])], maps=["id"], aa_samples=1)
        img = helpers.load(helpers.files_by_id(res, "Box")["id"])
        mask = helpers.island_mask(low, 128)
        colors = np.unique(np.round(img[mask][:, :3], 1), axis=0)
        self.assertGreaterEqual(len(colors), 2)

    def test_explode_removes_cross_occlusion(self):
        low_a = scenes.cube("A_low")
        scenes.unwrap(low_a)
        scenes.cube("A_high")
        low_b = scenes.cube("B_low", 2.0, (0, 0, 2.05))
        scenes.unwrap(low_b)
        scenes.cube("B_high", 2.0, (0, 0, 2.05))
        sets = [{"name": "A", "pairs": [pair("A", ["A_low"], ["A_high"])]},
                {"name": "B", "pairs": [pair("B", ["B_low"], ["B_high"])]}]
        outs = [output("ao", ["ao"])]
        mask = helpers.island_mask(low_a, 128)
        exploded = helpers.load(helpers.files_by_id(self.bake(sets, outs, ["ao"], explode=True), "A")["ao"])
        together = helpers.load(helpers.files_by_id(self.bake(sets, outs, ["ao"], explode=False), "A")["ao"])
        self.assertGreater(exploded[mask][:, 0].min(), 0.9)
        self.assertLess(together[mask][:, 0].min(), 0.5, "the top face is occluded by B without explode")

    def test_atlas_two_pairs_one_texture_set(self):
        a = scenes.cube("A_low")
        b = scenes.cube("B_low", 2.0, (4, 0, 0))
        scenes.unwrap(a)
        scenes.unwrap(b)
        # move B's UVs to the right half and A's to the left half
        for obj, offset in ((a, 0.0), (b, 0.5)):
            uv = obj.data.uv_layers.active.data
            for loop in uv:
                loop.uv = (loop.uv[0] * 0.5 + offset, loop.uv[1])
        ha = scenes.cube("A_high")
        hb = scenes.cube("B_high", 2.0, (4, 0, 0))
        ha.data.materials.append(scenes.principled("Red", (1, 0, 0, 1)))
        hb.data.materials.append(scenes.principled("Green", (0, 1, 0, 1)))
        res = self.bake([{"name": "Atlas", "pairs": [pair("A", ["A_low"], ["A_high"]),
                                                      pair("B", ["B_low"], ["B_high"])]}],
                        [output("bc", ["base_color"], srgb=True)], maps=["base_color"])
        img = helpers.load(helpers.files_by_id(res, "Atlas")["bc"])
        ma, mb = helpers.island_mask(a, 128), helpers.island_mask(b, 128)
        np.testing.assert_allclose(img[ma][:, :3].mean(axis=0), (1, 0, 0), atol=0.02)
        np.testing.assert_allclose(img[mb][:, :3].mean(axis=0), (0, 1, 0), atol=0.02)

    def test_curve_and_text_highs(self):
        low = scenes.cube("Box_low")
        scenes.unwrap(low)
        curve = bpy.data.curves.new("Text", "FONT")
        curve.body = "Z"
        curve.extrude = 0.2
        text = bpy.data.objects.new("Box_high", curve)
        bpy.context.scene.collection.objects.link(text)
        text.location = (-0.5, -1.05, -0.3)
        text.rotation_euler = (1.5708, 0, 0)
        res = self.bake([{"name": "Box", "pairs": [pair("Box", ["Box_low"], ["Box_high"], 0.2)]}],
                        [output("normal", ["normal"])], maps=["normal"])
        self.assertTrue(os.path.isfile(helpers.files_by_id(res, "Box")["normal"]))


class QualityTest(BakeTestCase):
    def test_supersampling_and_tiling_match(self):
        low, high = scenes.box_pair()
        ts = [{"name": "Box", "pairs": [pair("Box", ["Box_low"], ["Box_high"], 0.25)]}]
        outs = [output("n", ["normal"], file="T_{name}_N")]
        whole = helpers.load(helpers.files_by_id(self.bake(ts, outs, ["normal"], supersample=2, max_tile=8192,
                                                           resolution=[128, 128]), "Box")["n"])
        os.rename(os.path.join(self.tmp.path, "T_Box_N.png"), os.path.join(self.tmp.path, "whole.png"))
        tiled = helpers.load(helpers.files_by_id(self.bake(ts, outs, ["normal"], supersample=2, max_tile=128,
                                                           resolution=[128, 128]), "Box")["n"])
        self.assertEqual(whole.shape, (128, 128, 4))
        diff = np.abs(whole - tiled)[..., :3]
        self.assertLess(float(diff.mean()), 0.01)
        mask = helpers.island_mask(low, 128)
        self.assertLess(float(diff[mask].max()), 0.03)

    def test_padding_fills_texture(self):
        scenes.box_pair()
        res = self.bake([{"name": "Box", "pairs": [pair("Box", ["Box_low"], ["Box_high"], 0.25)]}],
                        [output("n", ["normal"])], ["normal"], fill_empty=True)
        n = helpers.load(helpers.files_by_id(res, "Box")["n"])
        length = np.linalg.norm(n[..., :3] * 2 - 1, axis=-1)
        np.testing.assert_allclose(length, 1.0, atol=0.03)

    def test_background_color_without_fill(self):
        low, _ = scenes.box_pair()
        res = self.bake([{"name": "Box", "pairs": [pair("Box", ["Box_low"], ["Box_high"], 0.25)]}],
                        [output("n", ["normal"])], ["normal"], fill_empty=False, margin=2)
        n = helpers.load(helpers.files_by_id(res, "Box")["n"])
        np.testing.assert_allclose(n[127, 127, :3], (0.5, 0.5, 1.0), atol=2 / 255)


class SafetyTest(BakeTestCase):
    def test_bake_is_non_destructive(self):
        low, high = scenes.box_pair()
        high.data.materials.append(scenes.principled("Red"))
        low.data.materials.append(scenes.principled("LowMat"))
        low.scale = (1.5, 1.0, 1.0)
        high.scale = (1.5, 1.0, 1.0)
        bpy.context.view_layer.update()
        before = helpers.datablock_counts()
        snap = [helpers.object_snapshot(o) for o in (low, high)]
        self.bake([{"name": "Box", "pairs": [pair("Box", ["Box_low"], ["Box_high"], 0.25)]}],
                  [output("n", ["normal"]), output("bc", ["base_color"], srgb=True), output("ao", ["ao"]),
                   output("id", ["id"]), output("h", ["height"])],
                  ["normal", "base_color", "ao", "id", "height"], supersample=2, max_tile=128)
        self.assertEqual(helpers.datablock_counts(), before)
        self.assertEqual([helpers.object_snapshot(o) for o in (low, high)], snap)
        self.assertEqual(len(bpy.data.scenes), 1)

    def test_errors_clean_up(self):
        low = scenes.cube("NoUV_low")
        for layer in list(low.data.uv_layers):
            low.data.uv_layers.remove(layer)
        scenes.cube("NoUV_high")
        before = helpers.datablock_counts()
        job = helpers.make_job(self.tmp.path, [{"name": "X", "pairs": [pair("X", ["NoUV_low"], ["NoUV_high"])]}],
                               [output("n", ["normal"])], ["normal"])
        result = helpers.run(job)
        self.assertFalse(result["ok"])
        self.assertTrue(any("UV" in e for e in result["errors"]))
        self.assertEqual(helpers.datablock_counts(), before)

    def test_cancel(self):
        scenes.box_pair()
        job = helpers.make_job(self.tmp.path, [{"name": "Box", "pairs": [pair("Box", ["Box_low"], ["Box_high"])]}],
                               [output("n", ["normal"])], ["normal"])
        before = helpers.datablock_counts()
        from zapekanka.core import engine

        result = engine.Engine(job, log=lambda m: None, check_cancel=lambda: True).run()
        self.assertFalse(result["ok"])
        self.assertIn("Cancelled", result["errors"])
        self.assertEqual(helpers.datablock_counts(), before)


if __name__ == "__main__":
    unittest.main()
