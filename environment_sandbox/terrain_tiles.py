"""Terrain tiling entry point.

Active implementation is selected by ``settings.TERRAIN_FILL_MODE``:

- ``"procedural"`` — 16-case MS opaque joins + world-UV procedural mottling
  (``terrain_mottle``). Preview / knobs: ``python preview_terrain_fills.py``.
- ``"png"`` — legacy soft neighbour-join path (``terrain_tiles_png``).
"""

from __future__ import annotations

from settings import TERRAIN_FILL_MODE

if TERRAIN_FILL_MODE == "png":
    from terrain_tiles_png import *  # noqa: F403
else:
    from terrain_tiles_procedural import *  # noqa: F403


def active_fill_mode() -> str:
    """Return the fill mode currently loaded into this module."""
    return "png" if TERRAIN_FILL_MODE == "png" else "procedural"
