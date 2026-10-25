# SPDX-License-Identifier: GPL-3.0-or-later
"""Export targets."""

from . import common, targets, unity, unreal


def run(context, target, report, launch=False):
    s = context.scene.zapekanka
    sets = common.texture_sets(context)
    if not sets:
        raise common.ExportError("No enabled pairs to export")
    not_baked = [ts.name for ts in sets if not ts.baked]
    if not_baked:
        report({"WARNING"}, "Not baked yet (mesh only): %s" % ", ".join(not_baked))
    root = common.export_dir(s, target)
    if target == "UE5":
        return unreal.export(context, sets, root, report)
    if target == "UNITY":
        return unity.export(context, sets, root, report)
    if target == "GODOT":
        return targets.export_godot(context, sets, root, report)
    if target in ("SUBSTANCE", "MARMOSET"):
        return targets.export_painter_or_marmoset(context, sets, root, report, target, launch)
    if target == "GLTF":
        return targets.export_gltf(context, sets, root, report)
    if target == "ROBLOX":
        return targets.export_roblox(context, sets, root, report)
    raise common.ExportError("Unknown export target %s" % target)
