# SPDX-License-Identifier: GPL-3.0-or-later
"""High/low pair detection."""

import re

GEOMETRY_TYPES = {"MESH", "CURVE", "SURFACE", "FONT", "META"}
_NUMERIC_TAIL = re.compile(r"\.\d{3,}$")


def parse_suffixes(text):
    items = [t.strip() for t in text.replace(";", ",").split(",")]
    return sorted({t for t in items if t}, key=len, reverse=True)


def _pattern(suffixes):
    alternatives = "|".join(re.escape(s) for s in suffixes)
    # base + suffix + optional tail ("_bolt", ".001", "2")
    return re.compile(r"^(?P<base>.+?)(?P<suffix>%s)(?P<tail>(?:[._\-\d].*)?)$" % alternatives, re.IGNORECASE)


def split_name(name, suffixes):
    """Return the base name if ``name`` carries one of ``suffixes``, else None."""
    if not suffixes:
        return None
    match = _pattern(suffixes).match(name)
    if not match:
        return None
    return match.group("base")


def is_helper(obj):
    return bool(obj.get("zb_preview")) or obj.name.startswith("ZB_")


def _candidates(context, selected_only):
    objs = context.selected_objects if selected_only else context.scene.objects
    return [o for o in objs if o.type in GEOMETRY_TYPES and not is_helper(o)]


def detect_by_suffix(context, low_suffixes, high_suffixes, cage_suffix, selected_only=False):
    lows = parse_suffixes(low_suffixes)
    highs = parse_suffixes(high_suffixes)
    cages = parse_suffixes(cage_suffix)
    groups = {}

    def group(base):
        key = base.lower()
        return groups.setdefault(key, {"name": base, "lows": [], "highs": [], "cage": None})

    for obj in _candidates(context, selected_only):
        name = _NUMERIC_TAIL.sub("", obj.name)
        base = split_name(name, cages)
        if base is not None and obj.type == "MESH":
            group(base)["cage"] = obj
            continue
        base = split_name(name, lows)
        if base is not None and obj.type == "MESH":
            group(base)["lows"].append(obj)
            continue
        base = split_name(name, highs)
        if base is not None:
            group(base)["highs"].append(obj)
    result = [g for g in groups.values() if g["lows"]]
    for g in result:
        g["lows"].sort(key=lambda o: o.name)
        g["highs"].sort(key=lambda o: o.name)
    return sorted(result, key=lambda g: g["name"].lower())


def _collection_objects(coll):
    return [o for o in coll.all_objects if o.type in GEOMETRY_TYPES and not is_helper(o)]


def detect_by_collection(context, low_suffixes, high_suffixes, cage_suffix, selected_only=False):
    lows = parse_suffixes(low_suffixes)
    highs = parse_suffixes(high_suffixes)
    cages = parse_suffixes(cage_suffix)
    groups = {}
    scene_colls = [context.scene.collection] + list(context.scene.collection.children_recursive)
    selected = set(context.selected_objects) if selected_only else None

    def group(base):
        key = base.lower()
        return groups.setdefault(key, {"name": base, "lows": [], "highs": [], "cage": None})

    for coll in scene_colls:
        name = _NUMERIC_TAIL.sub("", coll.name)
        objs = _collection_objects(coll)
        if selected is not None:
            objs = [o for o in objs if o in selected]
        base = split_name(name, lows)
        if base is not None:
            group(base)["lows"].extend(o for o in objs if o.type == "MESH")
            continue
        base = split_name(name, highs)
        if base is not None:
            group(base)["highs"].extend(objs)
            continue
        base = split_name(name, cages)
        if base is not None:
            meshes = [o for o in objs if o.type == "MESH"]
            if len(meshes) == 1:
                group(base)["cage"] = meshes[0]
    result = []
    for g in groups.values():
        g["lows"] = sorted(set(g["lows"]), key=lambda o: o.name)
        g["highs"] = sorted(set(g["highs"]) - set(g["lows"]), key=lambda o: o.name)
        if g["lows"]:
            result.append(g)
    return sorted(result, key=lambda g: g["name"].lower())


def detect(context):
    s = context.scene.zapekanka
    fn = detect_by_collection if s.pair_mode == "COLLECTION" else detect_by_suffix
    return fn(context, s.low_suffixes, s.high_suffixes, s.cage_suffix, s.detect_selected_only)


def store(settings, groups, replace=False):
    """Write detected groups into ``settings.pairs`` keeping per-pair overrides."""
    existing = {p.name.lower(): p for p in settings.pairs}
    if replace:
        keep = {g["name"].lower() for g in groups}
        for i in reversed(range(len(settings.pairs))):
            if settings.pairs[i].name.lower() not in keep:
                settings.pairs.remove(i)
        existing = {p.name.lower(): p for p in settings.pairs}
    added = 0
    for g in groups:
        pair = existing.get(g["name"].lower())
        if pair is None:
            pair = settings.pairs.add()
            pair.name = g["name"]
            added += 1
        pair.lows.clear()
        for obj in g["lows"]:
            pair.lows.add().obj = obj
        pair.highs.clear()
        for obj in g["highs"]:
            pair.highs.add().obj = obj
        pair.cage = g.get("cage")
    settings.pairs_index = min(settings.pairs_index, max(0, len(settings.pairs) - 1))
    return added


def unique_pair_name(settings, base):
    names = {p.name for p in settings.pairs}
    if base not in names:
        return base
    i = 1
    while "%s.%03d" % (base, i) in names:
        i += 1
    return "%s.%03d" % (base, i)


def pair_from_selection(context):
    s = context.scene.zapekanka
    active = context.active_object
    if active is None or active.type != "MESH":
        return None
    low_list = parse_suffixes(s.low_suffixes)
    base = split_name(_NUMERIC_TAIL.sub("", active.name), low_list) or active.name
    pair = s.pairs.add()
    pair.name = unique_pair_name(s, base)
    pair.lows.add().obj = active
    for obj in context.selected_objects:
        if obj is not active and obj.type in GEOMETRY_TYPES:
            pair.highs.add().obj = obj
    s.pairs_index = len(s.pairs) - 1
    return pair


def self_pairs_from_selection(context):
    """One pair per selected mesh, without high polys: each object bakes its own materials."""
    s = context.scene.zapekanka
    objs = [o for o in context.selected_objects if o.type == "MESH" and not is_helper(o)]
    created = []
    for obj in sorted(objs, key=lambda o: o.name):
        pair = s.pairs.add()
        pair.name = unique_pair_name(s, obj.name)
        pair.lows.add().obj = obj
        created.append(pair)
    if created:
        s.pairs_index = len(s.pairs) - 1
    return created


def active_pair(settings):
    if 0 <= settings.pairs_index < len(settings.pairs):
        return settings.pairs[settings.pairs_index]
    return None


def all_pair_objects(pair):
    objs = pair.low_objects() + pair.high_objects()
    if pair.cage is not None:
        objs.append(pair.cage)
    return objs


def scene_has_object(scene, obj):
    try:
        return obj is not None and scene.objects.get(obj.name) is obj
    except ReferenceError:
        return False


def prune_missing(settings, scene):
    """Remove references to deleted objects (pointer cleared or not in scene)."""
    removed = 0
    for pair in settings.pairs:
        for coll in (pair.lows, pair.highs):
            for i in reversed(range(len(coll))):
                obj = coll[i].obj
                if obj is None or not scene_has_object(scene, obj):
                    coll.remove(i)
                    removed += 1
    return removed
