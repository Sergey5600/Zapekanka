# SPDX-License-Identifier: GPL-3.0-or-later
"""Test runner.

Run with a Python that has the ``bpy`` module (``pip install bpy``)::

    python tests/run.py            # everything
    python tests/run.py test_core  # one module

or inside Blender::

    blender -b --factory-startup --python tests/run.py
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    import bpy

    print("Blender", bpy.app.version_string)
    loader = unittest.TestLoader()
    if argv:
        suite = unittest.TestSuite(loader.loadTestsFromName(name) for name in argv)
    else:
        suite = loader.discover(HERE, pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
