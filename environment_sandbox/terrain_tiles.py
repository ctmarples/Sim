"""Soft-joined terrain tiling from PNG textures.

Convention
----------
Each ``TerrainType`` has one or more pixel-art tiles in ``assets/terrain/``::

    grass_1.png, grass_2.png, …
    soil_1.png, meadow_1.png, water_1.png, rock_1.png, riparian_1.png

Native tile size should match ``TERRAIN_SUBDIV`` (default 25×25), but any
square PNG is accepted and scaled with nearest-neighbour (no blur). Variants
are packed into a repeating sheet and sampled with world-space UVs.

Land cells soft-blend with their east/south neighbours so habitat edges are
gradual and seamless. Water shores stay sharp (thresholded field).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from pathlib import Path

import pygame

from settings import (
    CELL_SIZE,
    COLOUR_GRASS,
    COLOUR_MEADOW,
    COLOUR_RIPARIAN,
    COLOUR_ROCK_TERRAIN,
    COLOUR_SOIL,
    COLOUR_WATER,
    TERRAIN_SUBDIV,
)
from world import TerrainType

TILE = TERRAIN_SUBDIV

_TERRAIN_DIR = Path(__file__).resolve().parent / "assets" / "terrain"

# Bit masks for marching-squares corners (user-specified).
TL, TR, BR, BL = 1, 2, 4, 8

# Layer order: earlier = background.
_PRIORITY: tuple[TerrainType, ...] = (
    TerrainType.GRASS,
    TerrainType.MEADOW,
    TerrainType.RIPARIAN,
    TerrainType.SOIL,
    TerrainType.ROCK,
    TerrainType.WATER,
)

_COLOURS: dict[TerrainType, tuple[int, int, int]] = {
    TerrainType.SOIL: COLOUR_SOIL,
    TerrainType.GRASS: COLOUR_GRASS,
    TerrainType.MEADOW: COLOUR_MEADOW,
    TerrainType.RIPARIAN: COLOUR_RIPARIAN,
    TerrainType.WATER: COLOUR_WATER,
    TerrainType.ROCK: COLOUR_ROCK_TERRAIN,
}

_STEM: dict[TerrainType, str] = {
    TerrainType.SOIL: "soil",
    TerrainType.GRASS: "grass",
    TerrainType.MEADOW: "meadow",
    TerrainType.RIPARIAN: "riparian",
    TerrainType.WATER: "water",
    TerrainType.ROCK: "rock",
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

ATLAS_COLS = 4
ATLAS_ROWS = 4

# terrain -> list of TILE×TILE surfaces (RGB)
_VARIANT_CACHE: dict[TerrainType, list[pygame.Surface]] = {}
_VARIANT_MTIME: dict[TerrainType, tuple[int, ...]] = {}
# (terrain, size) -> repeating sheet of scaled variants for world-space UV
_SHEET_CACHE: dict[tuple[TerrainType, int], pygame.Surface] = {}


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


def _smoothstep(t: float) -> float:
    t = 0.0 if t <= 0.0 else 1.0 if t >= 1.0 else t
    return t * t * (3.0 - 2.0 * t)


def _lerp_colour(
    a: tuple[int, int, int], b: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    t = 0.0 if t <= 0.0 else 1.0 if t >= 1.0 else t
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _opaque_fill(terrain: TerrainType, lx: int, ly: int) -> tuple[int, int, int]:
    """Fallback procedural fill when no PNG variants exist."""
    base = _COLOURS[terrain]
    n1 = (_hash01(lx, ly, 11 + terrain.value * 17) - 0.5) * 0.16
    n2 = (_hash01(lx * 2, ly * 3, 40 + terrain.value) - 0.5) * 0.09
    c = _shift(base, n1 + n2)
    if terrain == TerrainType.GRASS:
        if _hash01(lx, ly, 90) > 0.82:
            c = _shift(c, 0.12)
        elif _hash01(lx, ly, 91) > 0.88:
            c = _shift(c, -0.1)
    elif terrain == TerrainType.MEADOW:
        if _hash01(lx, ly, 88) > 0.8:
            c = _shift(c, 0.14)
        elif _hash01(lx, ly, 89) > 0.86:
            c = _shift(c, -0.08)
    elif terrain == TerrainType.RIPARIAN:
        if _hash01(lx, ly, 86) > 0.78:
            c = _shift(c, 0.1)
        elif _hash01(lx, ly, 87) > 0.85:
            c = _shift(c, -0.1)
    elif terrain == TerrainType.SOIL:
        if _hash01(lx, ly, 92) > 0.8:
            c = _shift(c, -0.12)
        elif _hash01(lx, ly, 93) > 0.85:
            c = _shift(c, 0.08)
    elif terrain == TerrainType.ROCK:
        if _hash01(lx, ly, 94) > 0.75:
            c = _shift(c, -0.14)
        elif _hash01(lx, ly, 95) > 0.9:
            c = _shift(c, 0.1)
    elif terrain == TerrainType.WATER:
        if _hash01(lx, ly, 96) > 0.7:
            c = _shift(c, 0.1)
        ripple = (_hash01(lx + ly, ly, 97) - 0.5) * 0.06
        c = _shift(c, ripple)
    return c


def _variant_paths(terrain: TerrainType) -> list[Path]:
    stem = _STEM[terrain]
    paths = sorted(_TERRAIN_DIR.glob(f"{stem}_*.png"))
    if not paths:
        single = _TERRAIN_DIR / f"{stem}.png"
        if single.is_file():
            paths = [single]
    return paths


def _load_variants(terrain: TerrainType) -> list[pygame.Surface]:
    """Load / refresh PNG variants for ``terrain`` (scaled to TILE×TILE)."""
    paths = _variant_paths(terrain)
    mtimes = tuple(p.stat().st_mtime_ns for p in paths) if paths else ()
    cached = _VARIANT_CACHE.get(terrain)
    if cached is not None and _VARIANT_MTIME.get(terrain) == mtimes:
        return cached
    surfs: list[pygame.Surface] = []
    for path in paths:
        raw = pygame.image.load(str(path)).convert()
        if raw.get_width() != TILE or raw.get_height() != TILE:
            raw = pygame.transform.scale(raw, (TILE, TILE))
        surfs.append(raw)
    _VARIANT_CACHE[terrain] = surfs
    _VARIANT_MTIME[terrain] = mtimes
    return surfs


def clear_texture_cache() -> None:
    _VARIANT_CACHE.clear()
    _VARIANT_MTIME.clear()
    _SHEET_CACHE.clear()
    _COVERAGE_CACHE.clear()
    _SOFT_COVERAGE_CACHE.clear()
    global _ATLAS
    _ATLAS = None


def variant_count(terrain: TerrainType) -> int:
    return max(1, len(_load_variants(terrain)))


def cell_variant_roll(cell_x: int, cell_y: int) -> int:
    """Stable per-cell roll shared by all terrain textures on that cell."""
    return int(_hash01(cell_x, cell_y, 200) * 9973) % 9973


def variant_index(terrain: TerrainType, cell_x: int, cell_y: int) -> int:
    n = variant_count(terrain)
    if n <= 1:
        return 0
    return cell_variant_roll(cell_x, cell_y) % n


def _variant_key(cell_x: int, cell_y: int) -> tuple[int, ...]:
    """Compact cache discriminator: one index per terrain type."""
    return tuple(variant_index(t, cell_x, cell_y) for t in _PRIORITY)


def sample_terrain(
    terrain: TerrainType,
    lx: int,
    ly: int,
    *,
    cell_x: int = 0,
    cell_y: int = 0,
) -> tuple[int, int, int]:
    """Colour at local tile pixel using world-space UV into the variant sheet."""
    sheet = _terrain_sheet(terrain, TILE)
    sw, sh = sheet.get_width(), sheet.get_height()
    wx = cell_x * TILE + lx
    wy = cell_y * TILE + ly
    return sheet.get_at((wx % sw, wy % sh))[:3]


def _procedural_tile(terrain: TerrainType) -> pygame.Surface:
    surf = pygame.Surface((TILE, TILE))
    for ly in range(TILE):
        for lx in range(TILE):
            surf.set_at((lx, ly), _opaque_fill(terrain, lx, ly))
    return surf


def _terrain_sheet(terrain: TerrainType, size: int) -> pygame.Surface:
    """World-UV sheet for ``terrain`` at cell ``size`` (nearest-neighbour, crisp).

    Variants are packed in a grid and sampled with world-space UVs so neighbouring
    cells join without bilinear blur.
    """
    key = (terrain, size)
    hit = _SHEET_CACHE.get(key)
    if hit is not None:
        return hit
    natives = _load_variants(terrain)
    if not natives:
        natives = [_procedural_tile(terrain)]
    scaled = [
        n if (n.get_width() == size and n.get_height() == size)
        else pygame.transform.scale(n, (size, size))
        for n in natives
    ]
    n = len(scaled)
    cols = max(1, int(n**0.5 + 0.5))
    rows = (n + cols - 1) // cols
    sheet = pygame.Surface((cols * size, rows * size))
    for i, surf in enumerate(scaled):
        sheet.blit(surf, ((i % cols) * size, (i // cols) * size))
    _SHEET_CACHE[key] = sheet
    return sheet


def _cell_texture(terrain: TerrainType, cell_x: int, cell_y: int, size: int) -> pygame.Surface:
    """``size``×``size`` window from the world-UV sheet for this cell."""
    sheet = _terrain_sheet(terrain, size)
    sw, sh = sheet.get_width(), sheet.get_height()
    out = pygame.Surface((size, size))
    ox = (cell_x * size) % sw
    oy = (cell_y * size) % sh
    if ox + size <= sw and oy + size <= sh:
        out.blit(sheet, (0, 0), pygame.Rect(ox, oy, size, size))
        return out
    # Wrap across sheet edges (end of variant period).
    for dy in range(size):
        sy = (oy + dy) % sh
        if ox + size <= sw:
            out.blit(sheet, (0, dy), pygame.Rect(ox, sy, size, 1))
        else:
            first = sw - ox
            out.blit(sheet, (0, dy), pygame.Rect(ox, sy, first, 1))
            out.blit(sheet, (first, dy), pygame.Rect(0, sy, size - first, 1))
    return out


def _bilinear(tl: float, tr: float, br: float, bl: float, u: float, v: float) -> float:
    top = tl + (tr - tl) * u
    bot = bl + (br - bl) * u
    return top + (bot - top) * v


def _fg_field(
    tl: TerrainType,
    tr: TerrainType,
    br: TerrainType,
    bl: TerrainType,
    fg: TerrainType,
    u: float,
    v: float,
) -> float:
    """Soft marching-squares coverage from shared corner bits (0..1)."""
    return _bilinear(
        1.0 if tl == fg else 0.0,
        1.0 if tr == fg else 0.0,
        1.0 if br == fg else 0.0,
        1.0 if bl == fg else 0.0,
        u,
        v,
    )


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
    """Shared vertex (vx, vy): highest-priority terrain among the 2×2 cells."""
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


_COVERAGE_CACHE: dict[tuple[int, int], pygame.Surface] = {}
_SOFT_COVERAGE_CACHE: dict[tuple[int, int], pygame.Surface] = {}


def _fg_coverage_mask(mask: int, size: int | None = None) -> pygame.Surface:
    """Hard (binary) MS coverage — used for water edges."""
    size = TILE if size is None else size
    mask = mask & 15
    key = (mask, size)
    hit = _COVERAGE_CACHE.get(key)
    if hit is not None:
        return hit
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0))
    if mask == 0:
        _COVERAGE_CACHE[key] = surf
        return surf
    if mask == 15:
        surf.fill((255, 255, 255, 255))
        _COVERAGE_CACHE[key] = surf
        return surf
    denom = max(1, size - 1)
    for poly in _unit_polygons(mask):
        pts = [(int(round(x * denom)), int(round(y * denom))) for x, y in poly]
        if len(pts) >= 3:
            pygame.draw.polygon(surf, (255, 255, 255, 255), pts)
    _COVERAGE_CACHE[key] = surf
    return surf


def _fg_soft_coverage_mask(mask: int, size: int | None = None) -> pygame.Surface:
    """Soft bilinear MS coverage — land↔land autotile joins."""
    size = TILE if size is None else size
    mask = mask & 15
    key = (mask, size)
    hit = _SOFT_COVERAGE_CACHE.get(key)
    if hit is not None:
        return hit
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    if mask == 0:
        surf.fill((0, 0, 0, 0))
        _SOFT_COVERAGE_CACHE[key] = surf
        return surf
    if mask == 15:
        surf.fill((255, 255, 255, 255))
        _SOFT_COVERAGE_CACHE[key] = surf
        return surf
    tl = 1.0 if mask & TL else 0.0
    tr = 1.0 if mask & TR else 0.0
    br = 1.0 if mask & BR else 0.0
    bl = 1.0 if mask & BL else 0.0
    denom = max(1, size - 1)
    for ly in range(size):
        v = ly / denom
        for lx in range(size):
            u = lx / denom
            field = _bilinear(tl, tr, br, bl, u, v)
            t = _smoothstep((field - 0.08) / 0.84)
            if t <= 0.001:
                continue
            a = max(0, min(255, int(round(t * 255))))
            surf.set_at((lx, ly), (255, 255, 255, a))
    _SOFT_COVERAGE_CACHE[key] = surf
    return surf


def _sheet_colour(terrain: TerrainType, wx: int, wy: int, size: int) -> tuple[int, int, int]:
    """Sample terrain sheet at world pixel coordinates."""
    sheet = _terrain_sheet(terrain, size)
    sw, sh = sheet.get_width(), sheet.get_height()
    return sheet.get_at((wx % sw, wy % sh))[:3]


def _mix_rgb(
    colours: list[tuple[int, int, int]], weights: list[float]
) -> tuple[int, int, int]:
    total = sum(weights)
    if total <= 1e-6:
        return colours[0]
    r = g = b = 0.0
    inv = 1.0 / total
    for (cr, cg, cb), w in zip(colours, weights):
        w *= inv
        r += cr * w
        g += cg * w
        b += cb * w
    return (int(r), int(g), int(b))


def _water_field(
    t00: TerrainType,
    t10: TerrainType,
    t01: TerrainType,
    t11: TerrainType,
    u: float,
    v: float,
) -> float:
    """Bilinear water coverage from the four cells around a point (0..1)."""
    return _bilinear(
        1.0 if t00 == TerrainType.WATER else 0.0,
        1.0 if t10 == TerrainType.WATER else 0.0,
        1.0 if t11 == TerrainType.WATER else 0.0,
        1.0 if t01 == TerrainType.WATER else 0.0,
        u,
        v,
    )


def build_soft_tile(
    t00: TerrainType,
    t10: TerrainType,
    t01: TerrainType,
    t11: TerrainType,
    *,
    cell_x: int = 0,
    cell_y: int = 0,
    size: int | None = None,
) -> tuple[pygame.Surface, pygame.Surface, int, TerrainType, TerrainType]:
    """Continuous soft land join for one cell using PNG world-UV sampling.

    ``t00`` is this cell, ``t10`` east, ``t01`` south, ``t11`` south-east.
    Land colours bilinear-blend across the shared edges with neighbours so
    joins are seamless. Water stays sharp (thresholded field).
    """
    size = TILE if size is None else size
    water = pygame.Surface((size, size), pygame.SRCALPHA)
    water.fill((0, 0, 0, 0))
    corners = (t00, t10, t11, t01)

    # Fast path: four cells agree → solid texture window.
    if t00 == t10 == t01 == t11:
        rgb = _cell_texture(t00, cell_x, cell_y, size).convert()
        if t00 == TerrainType.WATER:
            water.fill((255, 255, 255, 255))
        return rgb, water, 15, t00, t00

    present: list[TerrainType] = []
    for p in _PRIORITY:
        if p in corners and p not in present:
            present.append(p)
    bg = present[0]
    fg = present[-1]
    mask = mask_for_corners(
        # Approximate MS mask from cell-centre domination for diagnostics.
        t00, t10, t11, t01, fg
    )

    rgb = pygame.Surface((size, size))
    denom = max(1, size)
    for ly in range(size):
        # Sample at pixel centres in cell-local [0,1).
        v = (ly + 0.5) / denom
        wy = cell_y * size + ly
        for lx in range(size):
            u = (lx + 0.5) / denom
            wx = cell_x * size + lx
            wfield = _water_field(t00, t10, t01, t11, u, v)
            if wfield >= 0.5:
                rgb.set_at((lx, ly), _sheet_colour(TerrainType.WATER, wx, wy, size))
                a = 255 if wfield >= 0.55 else int(round(_smoothstep((wfield - 0.45) / 0.2) * 255))
                water.set_at((lx, ly), (255, 255, 255, a))
                continue

            # Soft land: bilinear blend of the four neighbouring cells' textures.
            # Replace water samples with a land neighbour so shores stay sharp.
            cells = (
                (t00, (1.0 - u) * (1.0 - v)),
                (t10, u * (1.0 - v)),
                (t01, (1.0 - u) * v),
                (t11, u * v),
            )
            colours: list[tuple[int, int, int]] = []
            weights: list[float] = []
            for terr, w in cells:
                if w <= 0.0001:
                    continue
                if terr == TerrainType.WATER:
                    # Pull land from the highest-weight non-water cell.
                    land = next(
                        (t for t, _ in sorted(cells, key=lambda kv: -kv[1]) if t != TerrainType.WATER),
                        bg if bg != TerrainType.WATER else TerrainType.GRASS,
                    )
                    terr = land
                colours.append(_sheet_colour(terr, wx, wy, size))
                weights.append(w)
            rgb.set_at((lx, ly), _mix_rgb(colours, weights))

    return rgb, water, mask, fg, bg


class TerrainAtlas:
    def __init__(self) -> None:
        self._cell_size = -1
        self._tile_res = -1
        self._cache: dict[
            tuple,
            tuple[pygame.Surface, pygame.Surface, int, TerrainType, TerrainType],
        ] = {}

    def ensure(self, cell_size: int | None = None) -> None:
        size = CELL_SIZE if cell_size is None else cell_size
        if size == self._cell_size and self._tile_res == TILE:
            return
        self._cell_size = size
        self._tile_res = TILE
        self._cache.clear()
        for terrain in TerrainType:
            _terrain_sheet(terrain, TILE)
            if size != TILE:
                _terrain_sheet(terrain, size)

    def _uv_period(self, size: int) -> tuple[int, int]:
        sheet = _terrain_sheet(TerrainType.GRASS, size)
        return max(1, sheet.get_width() // size), max(1, sheet.get_height() // size)

    def tile_for_neighbourhood(
        self,
        t00: TerrainType,
        t10: TerrainType,
        t01: TerrainType,
        t11: TerrainType,
        *,
        cell_x: int = 0,
        cell_y: int = 0,
    ) -> tuple[pygame.Surface, pygame.Surface, int, TerrainType, TerrainType]:
        self.ensure()
        size = self._cell_size
        px, py = self._uv_period(TILE)
        ux, uy = cell_x % px, cell_y % py
        key = (t00, t10, t01, t11, ux, uy, size)
        hit = self._cache.get(key)
        if hit is not None:
            return hit

        # Uniform: direct display-size window (crisp, no soft work).
        if t00 == t10 == t01 == t11:
            rgb = _cell_texture(t00, ux, uy, size).convert()
            water = pygame.Surface((size, size), pygame.SRCALPHA)
            water.fill((0, 0, 0, 0))
            if t00 == TerrainType.WATER:
                water.fill((255, 255, 255, 255))
            out = (rgb, water, 15, t00, t00)
            self._cache[key] = out
            return out

        # Transition: soft-blend at native TILE, then nearest-neighbour scale up.
        n_rgb, n_w, mask, fg, bg = build_soft_tile(
            t00, t10, t01, t11, cell_x=ux, cell_y=uy, size=TILE
        )
        out = (
            pygame.transform.scale(n_rgb, (size, size)),
            pygame.transform.scale(n_w, (size, size)),
            mask,
            fg,
            bg,
        )
        self._cache[key] = out
        return out

    # Back-compat alias used by diagnostics.
    def tile_for_corners(
        self,
        tl: TerrainType,
        tr: TerrainType,
        br: TerrainType,
        bl: TerrainType,
        *,
        cell_x: int = 0,
        cell_y: int = 0,
    ) -> tuple[pygame.Surface, pygame.Surface, int, TerrainType, TerrainType]:
        # Map shared-corner MS args onto the four cells of this neighbourhood.
        # tl/tr/br/bl are corner types, not cell types — keep soft path via cells.
        return self.tile_for_neighbourhood(
            tl, tr, bl, br, cell_x=cell_x, cell_y=cell_y
        )


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


def cell_neighbourhood(
    terrain_at: Callable[[int, int], TerrainType], x: int, y: int
) -> tuple[TerrainType, TerrainType, TerrainType, TerrainType]:
    """This cell + east + south + south-east (for continuous soft joins)."""
    return (
        terrain_at(x, y),
        terrain_at(x + 1, y),
        terrain_at(x, y + 1),
        terrain_at(x + 1, y + 1),
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
    """Blit soft-joined tile. Returns (mask, fg, bg, neighbourhood) for diagnostics."""
    size = CELL_SIZE if cell_size is None else cell_size
    atlas = get_atlas()
    atlas.ensure(size)
    neigh = cell_neighbourhood(terrain_at, x, y)
    rgb, wmask, mask, fg, bg = atlas.tile_for_neighbourhood(
        *neigh, cell_x=x, cell_y=y
    )
    dest = (x * size, y * size)
    layer.fill(_COLOURS[bg], pygame.Rect(dest[0], dest[1], size, size))
    layer.blit(rgb, dest)
    water_mask.fill((0, 0, 0, 0), pygame.Rect(dest[0], dest[1], size, size))
    water_mask.blit(wmask, dest)
    return mask, fg, bg, neigh


def describe_system() -> str:
    counts = {t.name: variant_count(t) for t in TerrainType}
    return (
        "convention=soft bilinear land joins + PNG world-UV in assets/terrain/\n"
        f"variants: {counts}\n"
        "files: {stem}_1.png, {stem}_2.png, … (or {stem}.png)\n"
        "joins: each cell blends with E/S/SE neighbours (seamless edges)\n"
        "water: sharp thresholded shore; land: gradual colour mix\n"
        "uv: world-space into variant sheet (nearest-neighbour, no blur)\n"
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
    etl, etr, ebr, ebl = cell_corners(terrain_at, x + 1, y)
    east_ok = tr == etl and br == ebl
    stl, str_, sbr, sbl = cell_corners(terrain_at, x, y + 1)
    south_ok = bl == stl and br == str_
    return east_ok, south_ok
