"""16-case marching-squares terrain autotiling (no colour averaging).

Convention
----------
Artwork is a **procedural 16-case marching-squares tileset**, not a 47-tile
blob atlas and not a simple 4-neighbour edge/corner set. There is no external
spritesheet in this repository — cases are generated once and cached.

Shared corner grid (visual only; gameplay still uses per-cell TerrainType):

    top-left     = bit 1
    top-right    = bit 2
    bottom-right = bit 4
    bottom-left  = bit 8

Screen directions (verified):

    north = (x, y - 1)
    east  = (x + 1, y)
    south = (x, y + 1)
    west  = (x - 1, y)

Each cell reads the same four vertex values as its neighbours, so the east
edge of (x,y) always matches the west edge of (x+1,y).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable

import pygame

from settings import (
    CELL_SIZE,
    COLOUR_GRASS,
    COLOUR_ROCK_TERRAIN,
    COLOUR_SOIL,
    COLOUR_WATER,
    TERRAIN_SUBDIV,
)
from world import TerrainType

TILE = TERRAIN_SUBDIV

# Bit masks for marching-squares corners (user-specified).
TL, TR, BR, BL = 1, 2, 4, 8

# Layer order: earlier = background.
_PRIORITY: tuple[TerrainType, ...] = (
    TerrainType.GRASS,
    TerrainType.SOIL,
    TerrainType.ROCK,
    TerrainType.WATER,
)

_COLOURS: dict[TerrainType, tuple[int, int, int]] = {
    TerrainType.SOIL: COLOUR_SOIL,
    TerrainType.GRASS: COLOUR_GRASS,
    TerrainType.WATER: COLOUR_WATER,
    TerrainType.ROCK: COLOUR_ROCK_TERRAIN,
}

CASE_NAMES: dict[int, str] = {
    0: "empty",
    1: "TL",
    2: "TR",
    3: "N-edge",
    4: "BR",
    5: "diag-TL-BR",
    6: "E-edge",
    7: "not-BL",
    8: "BL",
    9: "W-edge",
    10: "diag-TR-BL",
    11: "not-BR",
    12: "S-edge",
    13: "not-TR",
    14: "not-TL",
    15: "full",
}

# Atlas layout for diagnostics: cases 0..15 in row-major 4×4.
ATLAS_COLS = 4
ATLAS_ROWS = 4


def atlas_row_col(mask: int) -> tuple[int, int]:
    """Canonical atlas position for a 16-case mask (row, col)."""
    mask = mask & 15
    return divmod(mask, ATLAS_COLS)[0], mask % ATLAS_COLS


def _hash01(x: int, y: int, salt: int = 0) -> float:
    n = (x * 374761393 + y * 668265263 + salt * 1274126177) & 0x7FFFFFFF
    return (n % 10007) / 10007.0


def _shift(colour: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    r, g, b = colour
    if amount >= 0:
        return (
            min(255, int(r + (255 - r) * amount)),
            min(255, int(g + (255 - g) * amount)),
            min(255, int(b + (255 - b) * amount)),
        )
    a = -amount
    return (
        max(0, int(r * (1.0 - a))),
        max(0, int(g * (1.0 - a))),
        max(0, int(b * (1.0 - a))),
    )


def _opaque_fill(terrain: TerrainType, lx: int, ly: int) -> tuple[int, int, int]:
    """Fully opaque flat terrain colour (no spatial noise — keeps shared edges exact)."""
    return _COLOURS[terrain]


def resolve_corner_type(
    t00: TerrainType,
    t10: TerrainType,
    t01: TerrainType,
    t11: TerrainType,
) -> TerrainType:
    """Unused by the dual sampler; kept for diagnostics / experiments."""
    votes = (t00, t10, t01, t11)
    counts = Counter(votes)
    best = max(counts.values())
    cands = [t for t, n in counts.items() if n == best]
    if len(cands) == 1:
        return cands[0]
    for p in reversed(_PRIORITY):
        if p in cands:
            return p
    return cands[0]


def corner_type_at(
    terrain_at: Callable[[int, int], TerrainType], vx: int, vy: int
) -> TerrainType:
    """Shared vertex (vx, vy): highest-priority terrain among the 2×2 cells.

    Priority WATER > ROCK > SOIL > GRASS (no colour averaging). Adjacent cells
    read the same vertex, so shared edges cannot disagree.
    """
    types = (
        terrain_at(vx - 1, vy - 1),
        terrain_at(vx, vy - 1),
        terrain_at(vx - 1, vy),
        terrain_at(vx, vy),
    )
    for p in reversed(_PRIORITY):
        if p in types:
            return p
    return types[0]


def mask_for_corners(
    tl: TerrainType,
    tr: TerrainType,
    br: TerrainType,
    bl: TerrainType,
    fg: TerrainType,
) -> int:
    mask = 0
    if tl == fg:
        mask |= TL
    if tr == fg:
        mask |= TR
    if br == fg:
        mask |= BR
    if bl == fg:
        mask |= BL
    return mask


def _unit_polygons(mask: int) -> list[list[tuple[float, float]]]:
    """FG coverage polygons in unit square (origin top-left, +y south)."""
    n, e, s, w = (0.5, 0.0), (1.0, 0.5), (0.5, 1.0), (0.0, 0.5)
    tl, tr, br, bl = (0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)
    table: dict[int, list[list[tuple[float, float]]]] = {
        0: [],
        1: [[tl, n, w]],
        2: [[tr, e, n]],
        3: [[tl, tr, e, w]],
        4: [[br, s, e]],
        5: [[tl, n, w], [br, s, e]],
        6: [[tr, br, s, n]],
        7: [[tl, tr, br, s, w]],
        8: [[bl, w, s]],
        9: [[tl, n, s, bl]],
        10: [[tr, e, n], [bl, w, s]],
        11: [[tl, tr, e, s, bl]],
        12: [[bl, br, e, w]],
        13: [[tl, n, e, br, bl]],
        14: [[tr, br, bl, w, n]],
        15: [[tl, tr, br, bl]],
    }
    return table[mask & 15]


def _fg_coverage_mask(mask: int) -> pygame.Surface:
    """Opaque white where FG should be for this MS case."""
    surf = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0))
    if mask == 0:
        return surf
    if mask == 15:
        surf.fill((255, 255, 255, 255))
        return surf
    for poly in _unit_polygons(mask):
        pts = [(int(round(x * (TILE - 1))), int(round(y * (TILE - 1)))) for x, y in poly]
        if len(pts) >= 3:
            pygame.draw.polygon(surf, (255, 255, 255, 255), pts)
    return surf


def build_tile_from_corners(
    tl: TerrainType,
    tr: TerrainType,
    br: TerrainType,
    bl: TerrainType,
) -> tuple[pygame.Surface, pygame.Surface, int, TerrainType, TerrainType]:
    """Opaque MS composition from four shared corner types.

    Returns (rgb, water, primary_mask, fg, bg).
    """
    corners = (tl, tr, br, bl)
    present: list[TerrainType] = []
    for p in _PRIORITY:
        if p in corners and p not in present:
            present.append(p)
    for t in corners:
        if t not in present:
            present.append(t)

    bg = present[0]
    rgb = pygame.Surface((TILE, TILE))
    water = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
    water.fill((0, 0, 0, 0))
    for ly in range(TILE):
        for lx in range(TILE):
            rgb.set_at((lx, ly), _opaque_fill(bg, lx, ly))
    if bg == TerrainType.WATER:
        water.fill((255, 255, 255, 255))

    primary_mask = 15 if len(present) == 1 else 0
    primary_fg = bg

    for fg in present[1:]:
        mask = mask_for_corners(tl, tr, br, bl, fg)
        if mask == 0:
            continue
        cov = _fg_coverage_mask(mask)
        for ly in range(TILE):
            for lx in range(TILE):
                if cov.get_at((lx, ly))[3] > 128:
                    rgb.set_at((lx, ly), _opaque_fill(fg, lx, ly))
                    if fg == TerrainType.WATER:
                        water.set_at((lx, ly), (255, 255, 255, 255))
                    else:
                        water.set_at((lx, ly), (0, 0, 0, 0))
        primary_mask = mask
        primary_fg = fg

    return rgb, water, primary_mask, primary_fg, bg


class TerrainAtlas:
    def __init__(self) -> None:
        self._cell_size = -1
        self._tile_res = -1
        self._cache: dict[
            tuple[TerrainType, TerrainType, TerrainType, TerrainType],
            tuple[pygame.Surface, pygame.Surface, int, TerrainType, TerrainType],
        ] = {}

    def ensure(self, cell_size: int | None = None) -> None:
        size = CELL_SIZE if cell_size is None else cell_size
        if size == self._cell_size and self._tile_res == TILE:
            return
        self._cell_size = size
        self._tile_res = TILE
        self._cache.clear()

    def tile_for_corners(
        self,
        tl: TerrainType,
        tr: TerrainType,
        br: TerrainType,
        bl: TerrainType,
    ) -> tuple[pygame.Surface, pygame.Surface, int, TerrainType, TerrainType]:
        self.ensure()
        key = (tl, tr, br, bl)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        native_rgb, native_w, mask, fg, bg = build_tile_from_corners(tl, tr, br, bl)
        size = self._cell_size
        out = (
            pygame.transform.scale(native_rgb, (size, size)),
            pygame.transform.scale(native_w, (size, size)),
            mask,
            fg,
            bg,
        )
        self._cache[key] = out
        return out


_ATLAS: TerrainAtlas | None = None


def get_atlas() -> TerrainAtlas:
    global _ATLAS
    if _ATLAS is None:
        _ATLAS = TerrainAtlas()
    _ATLAS.ensure()
    return _ATLAS


def cell_corners(
    terrain_at: Callable[[int, int], TerrainType], x: int, y: int
) -> tuple[TerrainType, TerrainType, TerrainType, TerrainType]:
    """Shared corners for cell (x, y) in order TL, TR, BR, BL."""
    return (
        corner_type_at(terrain_at, x, y),
        corner_type_at(terrain_at, x + 1, y),
        corner_type_at(terrain_at, x + 1, y + 1),
        corner_type_at(terrain_at, x, y + 1),
    )


def paint_cell(
    layer: pygame.Surface,
    water_mask: pygame.Surface,
    x: int,
    y: int,
    *,
    terrain_at: Callable[[int, int], TerrainType],
    cell_size: int | None = None,
) -> tuple[int, TerrainType, TerrainType, tuple[TerrainType, TerrainType, TerrainType, TerrainType]]:
    """Blit MS tile. Returns (mask, fg, bg, corners) for diagnostics."""
    size = CELL_SIZE if cell_size is None else cell_size
    atlas = get_atlas()
    atlas.ensure(size)
    corners = cell_corners(terrain_at, x, y)
    rgb, wmask, mask, fg, bg = atlas.tile_for_corners(*corners)
    dest = (x * size, y * size)
    layer.fill(_COLOURS[bg], pygame.Rect(dest[0], dest[1], size, size))
    layer.blit(rgb, dest)
    water_mask.fill((0, 0, 0, 0), pygame.Rect(dest[0], dest[1], size, size))
    water_mask.blit(wmask, dest)
    return mask, fg, bg, corners


def describe_system() -> str:
    return (
        "convention=16-case marching-squares (procedural; no spritesheet on disk)\n"
        "bits: TL=1 TR=2 BR=4 BL=8\n"
        "dirs: N=(0,-1) E=(+1,0) S=(0,+1) W=(-1,0)\n"
        "corners: shared vertex grid; value = max-priority among 2x2 cells\n"
        "  (WATER>ROCK>SOIL>GRASS). No colour averaging.\n"
        "atlas: logical 4x4 of cases 0..15 (row=mask//4, col=mask%4)\n"
    )


def verify_shared_edges(
    terrain_at: Callable[[int, int], TerrainType],
    x: int,
    y: int,
) -> tuple[bool, bool]:
    """Check east/west and south/north corner agreement with neighbours."""
    tl, tr, br, bl = cell_corners(terrain_at, x, y)
    east_ok = True
    south_ok = True
    # Neighbour (x+1,y) west corners must equal this cell's east corners.
    etl, etr, ebr, ebl = cell_corners(terrain_at, x + 1, y)
    east_ok = tr == etl and br == ebl
    # Neighbour (x,y+1) north corners must equal this cell's south corners.
    stl, str_, sbr, sbl = cell_corners(terrain_at, x, y + 1)
    south_ok = bl == stl and br == str_
    return east_ok, south_ok
