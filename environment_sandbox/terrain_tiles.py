"""Terrain tiling entry point.

Active implementation is selected by ``settings.TERRAIN_FILL_MODE``:

- ``"procedural"`` — 16-case marching-squares with procedural fills
  (``terrain_tiles_procedural``). Default.
- ``"png"`` — PNG fills + soft neighbour joins (``terrain_tiles_png``).
  Kept for a possible return; not the active default.
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
