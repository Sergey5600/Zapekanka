# SPDX-License-Identifier: GPL-3.0-or-later
"""All operators of the add-on."""

from . import bake, cage, checks, export, misc, pairs

classes = bake.classes + pairs.classes + checks.classes + cage.classes + misc.classes + export.classes
