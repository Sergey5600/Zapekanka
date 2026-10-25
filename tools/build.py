# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the installable zip.

    python tools/build.py            -> dist/zapekanka-<version>.zip

The archive is a Blender extension (manifest at the archive root) and is
installed with Edit > Preferences > Get Extensions > Install from Disk.
Works with plain Python; Blender is not needed.
"""

import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(ROOT, "zapekanka")
EXCLUDE_DIRS = {"__pycache__"}
EXCLUDE_EXT = {".pyc", ".pyo", ".blend1"}


def manifest_version():
    text = open(os.path.join(PACKAGE, "blender_manifest.toml"), encoding="utf-8").read()
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise SystemExit("version not found in blender_manifest.toml")
    return match.group(1)


def check_versions(version):
    init = open(os.path.join(PACKAGE, "__init__.py"), encoding="utf-8").read()
    match = re.search(r'"version":\s*\((\d+),\s*(\d+),\s*(\d+)\)', init)
    bl = ".".join(match.groups()) if match else None
    if bl != version:
        raise SystemExit("bl_info version %s does not match manifest version %s" % (bl, version))


def build(out_dir=None):
    version = manifest_version()
    check_versions(version)
    out_dir = out_dir or os.path.join(ROOT, "dist")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "zapekanka-%s.zip" % version)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(PACKAGE):
            dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS)
            for name in sorted(filenames):
                if os.path.splitext(name)[1] in EXCLUDE_EXT:
                    continue
                full = os.path.join(dirpath, name)
                zf.write(full, os.path.relpath(full, PACKAGE))
        zf.write(os.path.join(ROOT, "LICENSE"), "LICENSE")
    return path


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else None))
