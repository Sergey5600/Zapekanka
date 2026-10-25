# SPDX-License-Identifier: GPL-3.0-or-later
"""Draw every panel against a recording layout.

Background Blender has no windows, so panels are never drawn there.  This
test calls each ``draw`` with a fake layout that checks every property and
operator the UI refers to, in all the states the panels can be in.
"""

import unittest

import bpy
import helpers  # noqa: F401
import scenes

import zapekanka
from zapekanka import background, ui
from zapekanka.operators import bake as bake_ops


class _OpProps:
    def __init__(self, idname, test):
        module, name = idname.split(".")
        self._rna = getattr(getattr(bpy.ops, module), name).get_rna_type()
        self._test = test

    def __setattr__(self, key, value):
        if key.startswith("_"):
            object.__setattr__(self, key, value)
            return
        self._test.assertIn(key, self._rna.properties.keys(), "operator property %s" % key)


class FakeLayout:
    def __init__(self, test):
        self.test = test
        self.scale_y = 1.0
        self.active = True
        self.enabled = True
        self.alignment = "EXPAND"
        self.calls = []

    def _child(self, *args, **kwargs):
        return FakeLayout(self.test)

    row = column = box = split = _child

    def label(self, text="", icon="NONE", translate=True, **kwargs):
        self._icon(icon)
        self.calls.append(("label", text))

    def separator(self, **kwargs):
        pass

    def _icon(self, icon):
        items = bpy.types.UILayout.bl_rna.functions["label"].parameters["icon"].enum_items.keys()
        self.test.assertIn(icon, items, "unknown icon %s" % icon)

    def prop(self, data, name, text=None, icon="NONE", **kwargs):
        self._icon(icon)
        self.test.assertIn(name, data.bl_rna.properties.keys(), "%s has no property %s" % (data, name))
        self.calls.append(("prop", name))

    def operator(self, idname, text=None, icon="NONE", **kwargs):
        self._icon(icon)
        module, name = idname.split(".")
        self.test.assertTrue(hasattr(getattr(bpy.ops, module), name), idname)
        self.calls.append(("operator", idname))
        return _OpProps(idname, self.test)

    def template_list(self, listtype, list_id, data, propname, active_data, active_propname, **kwargs):
        self.test.assertTrue(hasattr(bpy.types, listtype), listtype)
        self.test.assertIn(propname, data.bl_rna.properties.keys())
        self.test.assertIn(active_propname, active_data.bl_rna.properties.keys())

    def progress(self, factor=0.0, type="BAR", text=""):
        self.calls.append(("progress", text))


class UiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        zapekanka.register()

    @classmethod
    def tearDownClass(cls):
        zapekanka.unregister()

    def setUp(self):
        scenes.reset()

    def draw_all(self):
        context = bpy.context
        for cls in ui.classes:
            if not issubclass(cls, bpy.types.Panel):
                continue
            cls.draw(_PanelProxy(FakeLayout(self)), context)

    def test_empty_scene(self):
        self.draw_all()

    def test_full_state(self):
        scenes.box_pair()
        bpy.ops.zapekanka.detect_pairs()
        s = bpy.context.scene.zapekanka
        for key in s.maps.MAP_KEYS:
            setattr(s.maps, "use_" + key, True)
        s.resolution = "CUSTOM"
        s.bake_mode = "FOREGROUND"
        s.maps.height_range_mode = "MANUAL"
        s.maps.id_source = "VERTEX_COLOR"
        bpy.ops.zapekanka.preflight()
        bake_ops.LAST_SUMMARY.update(lines=["Box: 3 file(s)"], warnings=["warn"], errors=["err"], time=1.0,
                                     log_path="/tmp/x.log")
        background.STATE.running = True
        try:
            for target in ("UE5", "UNITY", "GODOT", "SUBSTANCE", "MARMOSET", "GLTF", "ROBLOX"):
                s.export.target = target
                self.draw_all()
        finally:
            background.STATE.running = False
            bake_ops.LAST_SUMMARY.update(lines=[], warnings=[], errors=[], time=0.0, log_path="")

    def test_lists(self):
        scenes.box_pair()
        bpy.ops.zapekanka.detect_pairs()
        s = bpy.context.scene.zapekanka
        bpy.ops.zapekanka.preflight()
        layout = FakeLayout(self)
        ui.ZB_UL_pairs.draw_item(None, bpy.context, layout, s, s.pairs[0], 0, s, "pairs_index", 0)
        pair = s.pairs[0]
        ui.ZB_UL_objects.draw_item(None, bpy.context, layout, pair, pair.lows[0], 0, pair, "lows_index", 0)
        for i, issue in enumerate(s.issues):
            ui.ZB_UL_issues.draw_item(None, bpy.context, layout, s, issue, 0, s, "issues_index", i)

    def test_preferences(self):
        from zapekanka import prefs

        layout = FakeLayout(self)
        prefs.ZB_Preferences.draw(_PrefsProxy(layout), bpy.context)


class _PanelProxy:
    def __init__(self, layout):
        self.layout = layout


class _PrefsProxy(_PanelProxy):
    """Exposes the preference properties' RNA for prop() checks."""

    def __init__(self, layout):
        super().__init__(layout)
        self.bl_rna = zapekanka.prefs.ZB_Preferences.bl_rna


if __name__ == "__main__":
    unittest.main()
