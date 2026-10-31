# SPDX-License-Identifier: GPL-3.0-or-later
"""The background worker must never touch the user's Blender installation.

Regression test: the worker starts with factory settings, and Blender used to
remove the Python libraries (wheels) of the user's extensions from the shared
``extensions/.local`` folder at startup.
"""

import os
import subprocess
import sys
import textwrap
import unittest
import zipfile

import helpers

from zapekanka import background
from zapekanka.core import engine

MANIFEST = """schema_version = "1.0.0"
id = "wheeldemo"
version = "1.0.0"
name = "Wheel Demo"
tagline = "Extension with a wheel"
maintainer = "test"
type = "add-on"
blender_version_min = "4.2.0"
license = ["SPDX:GPL-3.0-or-later"]
wheels = ["./wheels/zbdemo-1.0-py3-none-any.whl"]
"""


def _demo_extension(directory):
    wheel = os.path.join(directory, "zbdemo-1.0-py3-none-any.whl")
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.writestr("zbdemo/__init__.py", "VALUE = 42\n")
        zf.writestr("zbdemo-1.0.dist-info/METADATA", "Metadata-Version: 2.1\nName: zbdemo\nVersion: 1.0\n")
        zf.writestr("zbdemo-1.0.dist-info/WHEEL", "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
        zf.writestr("zbdemo-1.0.dist-info/RECORD", "zbdemo/__init__.py,,\nzbdemo-1.0.dist-info/METADATA,,\n"
                    "zbdemo-1.0.dist-info/WHEEL,,\nzbdemo-1.0.dist-info/RECORD,,\n")
    path = os.path.join(directory, "wheeldemo.zip")
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("blender_manifest.toml", MANIFEST)
        zf.writestr("__init__.py", "def register():\n    import zbdemo\n\n\ndef unregister():\n    pass\n")
        zf.write(wheel, "wheels/zbdemo-1.0-py3-none-any.whl")
    return path


def _run(code, env):
    proc = subprocess.run([sys.executable, "-c", textwrap.dedent(code)], env=env, capture_output=True, text=True,
                          timeout=300)
    if proc.returncode != 0:
        raise AssertionError(proc.stdout + proc.stderr)


class WorkerIsolationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = helpers.TempDir()
        self.user = os.path.join(self.tmp.path, "user")
        base = dict(os.environ)
        base.pop("BLENDER_USER_EXTENSIONS", None)
        base["BLENDER_USER_RESOURCES"] = self.user
        self.base_env = base
        # The user's Blender: an extension with a wheel, installed and enabled.
        _run("""
            import bpy
            bpy.ops.extensions.package_install_files(filepath=%r, repo="user_default", enable_on_install=True)
            bpy.ops.wm.save_userpref()
        """ % _demo_extension(self.tmp.path), base)
        self.site = None
        for root, dirs, _ in os.walk(os.path.join(self.user, "extensions", ".local")):
            if root.endswith("site-packages"):
                self.site = root
        self.assertIsNotNone(self.site)
        self.assertIn("zbdemo", os.listdir(self.site))

    def tearDown(self):
        self.tmp.cleanup()

    def _factory_startup(self, env):
        # What a factory-startup Blender does with extensions when it starts.
        _run("""
            import bpy
            import addon_utils
            addon_utils.extensions_refresh(ensure_wheels=True)
        """, env)

    def test_worker_keeps_user_wheels(self):
        job_dir = os.path.join(self.tmp.path, "job")
        os.makedirs(job_dir)
        env = background.worker_env(job_dir)
        env["BLENDER_USER_RESOURCES"] = self.user
        self._factory_startup(env)
        self.assertIn("zbdemo", os.listdir(self.site), "the worker removed the user's extension libraries")

    def test_without_isolation_blender_removes_wheels(self):
        """Documents the Blender behaviour the isolation protects against."""
        self._factory_startup(self.base_env)
        if "zbdemo" in os.listdir(self.site):
            self.skipTest("this Blender version no longer removes wheels at factory startup")


class CrashMessageTest(unittest.TestCase):
    def test_out_of_memory_from_log(self):
        msg = background.crash_message(3221225477, ["Calloc returns null: len=1073741824 in BakeDifferential"])
        self.assertIn("out of memory", msg)
        self.assertNotIn("3221225477", msg)

    def test_access_violation(self):
        msg = background.crash_message(3221225477, ["something else"])
        self.assertIn("memory access violation", msg)

    def test_linux_kill(self):
        self.assertIn("out of memory", background.crash_message(-9, []))


class MemoryTileTest(unittest.TestCase):
    def test_limits(self):
        gib = 1024 ** 3
        self.assertEqual(engine.memory_tile_limit(None), 16384)
        self.assertEqual(engine.memory_tile_limit(12 * gib), 4096)
        self.assertEqual(engine.memory_tile_limit(40 * gib), 8192)
        self.assertEqual(engine.memory_tile_limit(1 * gib), 1024)

    def test_user_limit(self):
        gib = 1024 ** 3
        # plenty of free memory, but the user allows only 4 GB / 1 GB
        self.assertEqual(engine.memory_tile_limit(64 * gib, 4 * gib), 4096)
        self.assertEqual(engine.memory_tile_limit(64 * gib, 1 * gib), 2048)
        self.assertEqual(engine.memory_tile_limit(64 * gib, 0.5 * gib), 1024)
        # free memory is the tighter bound
        self.assertEqual(engine.memory_tile_limit(4 * gib, 16 * gib), 2048)
        self.assertEqual(engine.memory_tile_limit(None, 4 * gib), 4096)

    def test_available_memory(self):
        free = engine.available_memory()
        self.assertTrue(free is None or free > 0)


if __name__ == "__main__":
    unittest.main()
