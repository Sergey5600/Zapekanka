# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for pure helpers: image ops, channel specs, presets."""

import types
import unittest

import helpers  # noqa: F401  (sets up sys.path)
import numpy as np

from zapekanka import presets
from zapekanka.core import imageops
from zapekanka.core.maps import expand_channels, output_maps, parse_channel


class ImageOpsTest(unittest.TestCase):
    def test_downsample_is_coverage_weighted(self):
        img = np.zeros((4, 4, 3), np.float32)
        img[0, 0] = (1.0, 0.5, 0.25)
        weight = np.zeros((4, 4), np.float32)
        weight[0, 0] = 1.0
        data, w = imageops.downsample(img, weight, 2)
        np.testing.assert_allclose(data[0, 0], (1.0, 0.5, 0.25))
        self.assertAlmostEqual(float(w[0, 0]), 0.25)
        self.assertEqual(float(w[1, 1]), 0.0)

    def test_downsample_normals_stay_unit_length(self):
        rng = np.random.default_rng(1)
        vec = imageops.normalize_vectors(rng.normal(size=(64, 3)).astype(np.float32))
        rgb = imageops.encode_normals(vec).reshape(8, 8, 3)
        data, _ = imageops.downsample_normals(rgb, np.ones((8, 8), np.float32), 2)
        length = np.linalg.norm(imageops.decode_normals(data), axis=-1)
        np.testing.assert_allclose(length, 1.0, atol=1e-5)

    def test_fill_holes_keeps_valid_and_fills_everything(self):
        rng = np.random.default_rng(2)
        img = rng.random((37, 53, 3)).astype(np.float32)
        valid = rng.random((37, 53)) > 0.8
        original = img.copy()
        out = imageops.fill_holes(img.copy(), valid)
        np.testing.assert_array_equal(out[valid], original[valid])
        self.assertTrue(np.isfinite(out).all())
        self.assertTrue((out >= 0).all() and (out <= 1).all())

    def test_fill_holes_region(self):
        img = np.zeros((16, 16, 1), np.float32)
        img[8, 8] = 1.0
        valid = np.zeros((16, 16), bool)
        valid[8, 8] = True
        region = np.zeros((16, 16), bool)
        region[7:10, 7:10] = True
        out = imageops.fill_holes(img.copy(), valid, region)
        self.assertGreater(float(out[7, 7, 0]), 0.5)
        self.assertEqual(float(out[0, 0, 0]), 0.0)

    def test_fill_constant_is_exact(self):
        img = np.full((20, 20, 3), 0.25, np.float32)
        valid = np.zeros((20, 20), bool)
        valid[5:9, 5:9] = True
        out = imageops.fill_holes(img.copy(), valid)
        np.testing.assert_allclose(out, 0.25, atol=1e-6)

    def test_curvature_flat_is_neutral(self):
        flat = np.zeros((32, 32, 3), np.float32)
        flat[..., :] = (0.5, 0.5, 1.0)
        curv = imageops.curvature_from_normal(flat)
        np.testing.assert_allclose(curv, 0.5, atol=1e-6)

    def test_curvature_ignores_island_borders(self):
        n = np.zeros((32, 32, 3), np.float32)
        n[..., :] = (0.5, 0.5, 1.0)
        n[:, 16:] = (0.9, 0.5, 0.6)  # a different island with another tangent frame
        mask = np.ones((32, 32), bool)
        mask[:, 15:17] = False  # gap between the islands
        curv = imageops.curvature_from_normal(n, mask=mask)
        np.testing.assert_allclose(curv[mask], 0.5, atol=1e-6)

    def test_height(self):
        p_low = np.zeros((2, 2, 3), np.float32)
        n_low = np.zeros((2, 2, 3), np.float32)
        n_low[..., 2] = 1.0
        p_high = p_low.copy()
        p_high[0, 0, 2] = 0.1
        p_high[1, 1, 2] = -0.05
        h, rng = imageops.height_from_positions(p_high, p_low, n_low, np.ones((2, 2), bool))
        self.assertAlmostEqual(rng, 0.1, places=6)
        self.assertAlmostEqual(float(h[0, 0, 0]), 1.0, places=5)
        self.assertAlmostEqual(float(h[0, 1, 0]), 0.5, places=5)
        self.assertAlmostEqual(float(h[1, 1, 0]), 0.25, places=5)

    def test_srgb_roundtrip(self):
        x = np.linspace(0, 1, 101, dtype=np.float32)
        np.testing.assert_allclose(imageops.srgb_to_linear(imageops.linear_to_srgb(x)), x, atol=1e-5)


class ChannelSpecTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_channel("base_color.g").index, 1)
        self.assertTrue(parse_channel("roughness!").invert)
        self.assertAlmostEqual(parse_channel("=0.5").constant, 0.5)
        with self.assertRaises(ValueError):
            parse_channel("roughness.g")
        with self.assertRaises(ValueError):
            parse_channel("nope")

    def test_expand(self):
        chans = expand_channels(["normal"])
        self.assertEqual([(c.map, c.index) for c in chans], [("normal", 0), ("normal", 1), ("normal", 2)])
        self.assertEqual(output_maps({"channels": ["ao", "roughness", "=0"]}), {"ao", "roughness"})


def _settings(**kw):
    s = types.SimpleNamespace(
        file_format="PNG", normal_16bit=False, naming_template="T_{name}_{suffix}", pack_mode="ORM",
        opacity_in_alpha=True, keep_packed_sources=False, material_template="M_{name}", mesh_template="SM_{name}",
        normal_format="DIRECTX",
    )
    for key in presets.SUFFIX_KEYS:
        setattr(s, "suffix_" + key, presets.PRESETS["UE5"]["suffix"][key])
    s.__dict__.update(kw)
    return s


class PresetTest(unittest.TestCase):
    def test_ue5_orm(self):
        outs = presets.build_outputs(_settings(), {"base_color", "roughness", "metallic", "ao", "normal", "opacity"})
        by_id = {o["id"]: o for o in outs}
        self.assertEqual(by_id["orm"]["channels"], ["ao", "roughness", "metallic"])
        self.assertEqual(by_id["orm"]["file"], "T_{name}_ORM")
        self.assertEqual(by_id["base_color"]["channels"][3], "opacity")
        self.assertTrue(by_id["base_color"]["srgb"])
        self.assertFalse(by_id["normal"]["srgb"])
        self.assertNotIn("ao", by_id)

    def test_orm_without_ao_uses_white(self):
        outs = presets.build_outputs(_settings(), {"roughness", "metallic"})
        self.assertEqual(outs[0]["channels"], ["=1", "roughness", "metallic"])

    def test_unity_smoothness_is_inverted_roughness(self):
        s = _settings(pack_mode="UNITY_METALLIC")
        outs = presets.build_outputs(s, {"roughness", "metallic"})
        self.assertEqual(outs[0]["channels"][3], "roughness!")

    def test_hdrp_mask(self):
        s = _settings(pack_mode="UNITY_HDRP_MASK")
        outs = presets.build_outputs(s, {"roughness", "metallic", "ao"})
        self.assertEqual(outs[0]["channels"], ["metallic", "ao", "=1", "roughness!"])

    def test_color_spaces(self):
        outs = presets.build_outputs(_settings(pack_mode="NONE"), {
            "base_color", "roughness", "metallic", "ao", "normal", "emission", "opacity", "curvature",
            "thickness", "position", "world_normal", "height", "id"})
        srgb = {o["id"] for o in outs if o["srgb"]}
        self.assertEqual(srgb, {"base_color", "emission"})

    def test_every_preset_is_complete(self):
        for key, preset in presets.PRESETS.items():
            for suffix in presets.SUFFIX_KEYS:
                self.assertIn(suffix, preset["suffix"], "%s lacks suffix %s" % (key, suffix))


if __name__ == "__main__":
    unittest.main()
