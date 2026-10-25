# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the release zip, install it with Blender's extension installer and bake from it."""

import os
import sys
import time
import unittest

import bpy
import helpers
import scenes

sys.path.insert(0, os.path.join(helpers.ROOT, "tools"))
import build  # noqa: E402

PKG_ID = "zapekanka"
MODULE = "bl_ext.user_default." + PKG_ID


class ExtensionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = helpers.TempDir()
        scenes.reset()

    def tearDown(self):
        if MODULE in bpy.context.preferences.addons:
            bpy.ops.extensions.package_uninstall(repo_index=self._repo_index(), pkg_id=PKG_ID)
        self.tmp.cleanup()

    @staticmethod
    def _repo_index():
        for i, repo in enumerate(bpy.context.preferences.extensions.repos):
            if repo.module == "user_default":
                return i
        raise RuntimeError("user_default repository missing")

    def test_install_enable_and_background_bake(self):
        zip_path = build.build(self.tmp.path)
        result = bpy.ops.extensions.package_install_files(filepath=zip_path, repo="user_default",
                                                          enable_on_install=True, overwrite=True)
        self.assertEqual(result, {"FINISHED"})
        self.assertIn(MODULE, bpy.context.preferences.addons)
        pkg = sys.modules[MODULE]
        prefs = pkg.prefs.get_prefs()
        self.assertIsNotNone(prefs, "preferences must resolve under the extension module name")
        self.assertTrue(hasattr(bpy.types, "ZB_PT_main"))

        scenes.box_pair()
        s = bpy.context.scene.zapekanka
        s.output_dir = os.path.join(self.tmp.path, "textures")
        s.resolution = "512"
        s.supersample = "1"
        s.aa_samples = 1
        bpy.ops.zapekanka.detect_pairs()
        background = pkg.background
        original = background.blender_executable
        background.blender_executable = lambda: helpers.fake_blender(self.tmp.path)
        try:
            self.assertEqual(bpy.ops.zapekanka.bake(), {"FINISHED"})
            deadline = time.time() + 300
            while (background.STATE.running or background.queued_count()) and time.time() < deadline:
                background._tick()
                time.sleep(0.05)
        finally:
            background.blender_executable = original
        self.assertTrue(background.STATE.last_result["ok"], background.STATE.last_result)
        self.assertIn("T_Box_N.png", os.listdir(s.output_dir))


if __name__ == "__main__":
    unittest.main()
