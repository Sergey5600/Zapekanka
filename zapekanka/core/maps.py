# SPDX-License-Identifier: GPL-3.0-or-later
"""Map registry and output channel specification.

A *map* is an intermediate buffer produced by the baker (``normal``, ``ao``,
``base_color`` ...).  An *output* is a file on disk assembled from one or more
map channels, e.g. ORM = ``["ao", "roughness", "metallic"]``.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MapDef:
    key: str
    label: str
    channels: int
    color: bool = False  # stored as linear colour, sRGB-encoded on export
    normal: bool = False  # stored as encoded unit vectors (n * 0.5 + 0.5)
    background: tuple = (0.0, 0.0, 0.0)
    default: float = 0.0  # value used when a packed output references a map that was not baked


MAPS = {
    m.key: m
    for m in (
        MapDef("normal", "Normal", 3, normal=True, background=(0.5, 0.5, 1.0), default=0.5),
        MapDef("ao", "Ambient Occlusion", 1, background=(1.0,), default=1.0),
        MapDef("curvature", "Curvature", 1, background=(0.5,), default=0.5),
        MapDef("thickness", "Thickness", 1, background=(1.0,), default=1.0),
        MapDef("position", "Position", 3, background=(0.0, 0.0, 0.0), default=0.0),
        MapDef("world_normal", "World Normal", 3, normal=True, background=(0.5, 0.5, 0.5), default=0.5),
        MapDef("height", "Height", 1, background=(0.5,), default=0.5),
        MapDef("id", "ID Color", 3, background=(0.0, 0.0, 0.0), default=0.0),
        MapDef("base_color", "Base Color", 3, color=True, background=(0.0, 0.0, 0.0), default=0.5),
        MapDef("roughness", "Roughness", 1, background=(0.5,), default=0.5),
        MapDef("metallic", "Metallic", 1, background=(0.0,), default=0.0),
        MapDef("emission", "Emission", 3, color=True, background=(0.0, 0.0, 0.0), default=0.0),
        MapDef("opacity", "Opacity", 1, background=(0.0,), default=1.0),
    )
}

MESH_MAPS = ("normal", "ao", "curvature", "thickness", "position", "world_normal", "height", "id")
PBR_MAPS = ("base_color", "roughness", "metallic", "normal", "ao", "emission", "opacity")

_CHANNEL_INDEX = {"r": 0, "g": 1, "b": 2, "a": 3, "x": 0, "y": 1, "z": 2}


@dataclass(frozen=True)
class ChannelSource:
    map: str = ""  # empty for constants
    index: int = 0
    invert: bool = False
    constant: float = 0.0

    @property
    def is_constant(self):
        return not self.map


def parse_channel(text):
    """Parse ``"roughness"``, ``"base_color.g"``, ``"roughness!"`` or ``"=0.5"``."""
    text = text.strip()
    if text.startswith("="):
        return ChannelSource(constant=float(text[1:]))
    invert = text.endswith("!")
    if invert:
        text = text[:-1]
    name, _, chan = text.partition(".")
    if name not in MAPS:
        raise ValueError("Unknown map %r in channel spec" % name)
    index = _CHANNEL_INDEX[chan.lower()] if chan else 0
    if index >= MAPS[name].channels:
        raise ValueError("Map %r has no channel %r" % (name, chan))
    return ChannelSource(map=name, index=index, invert=invert)


def expand_channels(spec):
    """Expand a list of channel strings. A single 3-channel map expands to r, g, b."""
    if isinstance(spec, str):
        spec = [spec]
    if len(spec) == 1 and not spec[0].startswith("=") and "." not in spec[0]:
        name = spec[0].rstrip("!")
        if name in MAPS and MAPS[name].channels == 3:
            inv = "!" if spec[0].endswith("!") else ""
            spec = ["%s.%s%s" % (name, c, inv) for c in "rgb"]
    return [parse_channel(s) for s in spec]


def output_maps(output):
    """Set of map keys referenced by an output spec."""
    return {c.map for c in expand_channels(output["channels"]) if not c.is_constant}
