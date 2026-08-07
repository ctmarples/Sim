"""16-case marching-squares terrain autotiling + procedural mottling.

Active via ``settings.TERRAIN_FILL_MODE = "procedural"``.

Land↔land: soft bilinear coverage, **opaque colour lerp** of world-UV mottles
(never alpha-blend onto black). Water edges stay sharp.
Tune mottling: ``python preview_terrain_fills.py``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable

import pygame

from settings import (
    CELL_SIZE,
    COLOUR_FOREST_FLOOR,
    COLOUR_GRASS,
    COLOUR_MEADOW,
    COLOUR_RIPARIAN,
    COLOUR_ROCK_TERRAIN,
    COLOUR_SOIL,
    COLOUR_URBAN,
    COLOUR_PATH,
    COLOUR_WATER,
    TERRAIN_SUBDIV,
)
from world import TerrainType, hardscape_tile_group

TILE = TERRAIN_SUBDIV

# Bit masks for marching-squares corners (user-specified).
TL, TR, BR, BL = 1, 2, 4, 8

# Layer order: earlier = background.
_PRIORITY: tuple[TerrainType, ...] = (
    TerrainType.GRASS,
    TerrainType.MEADOW,
    TerrainType.RIPARIAN,
    TerrainType.SOIL,
    TerrainType.FOREST_FLOOR,
    TerrainType.PATH,
    TerrainType.URBAN,  # above PATH at shared corners
    TerrainType.ROCK,
    TerrainType.WATER,
)

_COLOURS: dict[TerrainType, tuple[int, int, int]] = {
    TerrainType.SOIL: COLOUR_SOIL,
    TerrainType.FOREST_FLOOR: COLOUR_FOREST_FLOOR,
    TerrainType.GRASS: COLOUR_GRASS,
    TerrainType.MEADOW: COLOUR_MEADOW,
    TerrainType.RIPARIAN: COLOUR_RIPARIAN,
    TerrainType.WATER: COLOUR_WATER,
    TerrainType.RIVER: COLOUR_WATER,
    TerrainType.ROCK: COLOUR_ROCK_TERRAIN,
    TerrainType.URBAN: COLOUR_URBAN,
    TerrainType.PATH: COLOUR_PATH,
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
    """Opaque mottling for cached MS atlas tiles (local UV; game uses world_mottle)."""
    from terrain_mottle import sample_mottle

    return sample_mottle(terrain, lx, ly)


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
    """Shared vertex (vx, vy): highest-priority terrain among the 2×2 cells.

    Priority WATER > ROCK > URBAN > PATH > FOREST_FLOOR > SOIL > …
    PATH and URBAN keep distinct colours at transitions.
    """
    types = (
        hardscape_tile_group(terrain_at(vx - 1, vy - 1)),
        hardscape_tile_group(terrain_at(vx, vy - 1)),
        hardscape_tile_group(terrain_at(vx - 1, vy)),
        hardscape_tile_group(terrain_at(vx, vy)),
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


_HARD_COV_CACHE: dict[tuple[int, int], pygame.Surface] = {}


def _fg_coverage_mask(mask: int, size: int | None = None) -> pygame.Surface:
    """Opaque white where FG should be for this MS case (drawn at ``size``)."""
    size = TILE if size is None else size
    mask = mask & 15
    key = (mask, size)
    hit = _HARD_COV_CACHE.get(key)
    if hit is not None:
        return hit
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0))
    if mask == 0:
        _HARD_COV_CACHE[key] = surf
        return surf
    if mask == 15:
        surf.fill((255, 255, 255, 255))
        _HARD_COV_CACHE[key] = surf
        return surf
    for poly in _unit_polygons(mask):
        pts = []
        for x, y in poly:
            px = 0 if x <= 0.0 else (size - 1 if x >= 1.0 else int(round(x * (size - 1))))
            py = 0 if y <= 0.0 else (size - 1 if y >= 1.0 else int(round(y * (size - 1))))
            pts.append((px, py))
        if len(pts) >= 3:
            pygame.draw.polygon(surf, (255, 255, 255, 255), pts)
    _HARD_COV_CACHE[key] = surf
    return surf


def _stamp_replace(
    dest: pygame.Surface,
    texture: pygame.Surface,
    coverage: pygame.Surface,
) -> None:
    """Opaque replace: texture RGB where coverage alpha is opaque.

    Copies coverage alpha onto the texture (RGB untouched) then blits — never
    multiplies RGB toward black (classic dark-rim bug).
    """
    stamped = texture.convert_alpha()
    try:
        import numpy as np
        from pygame import surfarray

        alpha = surfarray.pixels_alpha(stamped)
        alpha[:, :] = surfarray.array_alpha(coverage)
        del alpha
    except Exception:
        # Fallback without numpy: per-pixel (slow; rare).
        w, h = stamped.get_size()
        for y in range(h):
            for x in range(w):
                c = stamped.get_at((x, y))
                a = coverage.get_at((x, y))[3]
                stamped.set_at((x, y), (c[0], c[1], c[2], a))
    dest.blit(stamped, (0, 0))


def build_tile_from_corners(
    tl: TerrainType,
    tr: TerrainType,
    br: TerrainType,
    bl: TerrainType,
) -> tuple[pygame.Surface, pygame.Surface, int, TerrainType, TerrainType]:
    """MS composition from four shared corners (atlas / F6).

    Land↔land: soft bilinear coverage + opaque colour lerp.
    Water↔other: sharp. Fills from local-UV mottling.
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
    denom = max(1, TILE - 1)

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
        sharp = fg == TerrainType.WATER or bg == TerrainType.WATER
        for ly in range(TILE):
            v = ly / denom
            for lx in range(TILE):
                u = lx / denom
                field = _fg_field(tl, tr, br, bl, fg, u, v)
                if sharp:
                    if field < 0.5:
                        continue
                    t = 1.0
                else:
                    t = _smoothstep((field - 0.08) / 0.84)
                    if t <= 0.001:
                        continue
                base = rgb.get_at((lx, ly))[:3]
                fg_c = _opaque_fill(fg, lx, ly)
                rgb.set_at((lx, ly), _lerp_colour(base, fg_c, t))
                if fg == TerrainType.WATER:
                    water.set_at((lx, ly), (255, 255, 255, int(255 * t)))
                elif bg == TerrainType.WATER:
                    wa = water.get_at((lx, ly))[3]
                    water.set_at((lx, ly), (255, 255, 255, int(wa * (1.0 - t))))
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
        _HARD_COV_CACHE.clear()
        _COV_CACHE.clear()

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
        # Soft land blends benefit from smoothscale; water edges stay acceptable.
        out = (
            pygame.transform.smoothscale(native_rgb, (size, size)),
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


def cell_neighbourhood(
    terrain_at: Callable[[int, int], TerrainType], x: int, y: int
) -> tuple[TerrainType, TerrainType, TerrainType, TerrainType]:
    """This cell + east + south + south-east (diagnostics / legacy)."""
    return (
        hardscape_tile_group(terrain_at(x, y)),
        hardscape_tile_group(terrain_at(x + 1, y)),
        hardscape_tile_group(terrain_at(x, y + 1)),
        hardscape_tile_group(terrain_at(x + 1, y + 1)),
    )


def compose_cell_fills(
    tl: TerrainType,
    tr: TerrainType,
    br: TerrainType,
    bl: TerrainType,
    *,
    cell_x: int,
    cell_y: int,
    size: int,
) -> tuple[pygame.Surface, pygame.Surface, int, TerrainType, TerrainType]:
    """Soft land MS joins via opaque colour-lerp of world-UV mottling.

    Never alpha-blends onto black. Water edges stay hard-thresholded.
    """
    import numpy as np
    from pygame import surfarray

    from terrain_mottle import world_mottle_surface

    corners = (tl, tr, br, bl)
    present: list[TerrainType] = []
    for p in _PRIORITY:
        if p in corners and p not in present:
            present.append(p)
    for t in corners:
        if t not in present:
            present.append(t)

    bg = present[0]
    bg_surf = world_mottle_surface(bg, cell_x, cell_y, size)
    # surfarray layout: [x, y, channel]
    rgb = surfarray.array3d(bg_surf).astype(np.float32)
    water = pygame.Surface((size, size), pygame.SRCALPHA)
    water.fill((0, 0, 0, 0))
    water_a = np.zeros((size, size), dtype=np.float32)
    if bg == TerrainType.WATER:
        water_a[:, :] = 255.0

    primary_mask = 15 if len(present) == 1 else 0
    primary_fg = bg

    # u along x, v along y — match get_at((lx, ly)) / MS unit square.
    u = np.linspace(0.0, 1.0, size, dtype=np.float32)
    v = np.linspace(0.0, 1.0, size, dtype=np.float32)
    uu = np.broadcast_to(u[:, None], (size, size))
    vv = np.broadcast_to(v[None, :], (size, size))

    for fg in present[1:]:
        mask = mask_for_corners(tl, tr, br, bl, fg)
        if mask == 0:
            continue
        sharp = fg == TerrainType.WATER or bg == TerrainType.WATER
        c_tl = 1.0 if tl == fg else 0.0
        c_tr = 1.0 if tr == fg else 0.0
        c_br = 1.0 if br == fg else 0.0
        c_bl = 1.0 if bl == fg else 0.0
        top = c_tl + (c_tr - c_tl) * uu
        bot = c_bl + (c_br - c_bl) * uu
        field = top + (bot - top) * vv

        if sharp:
            t = (field >= 0.5).astype(np.float32)
        else:
            # Wide soft band across the MS contour (same as restore-tiling).
            t = (field - 0.08) / 0.84
            t = np.clip(t, 0.0, 1.0)
            t = t * t * (3.0 - 2.0 * t)

        fg_arr = surfarray.array3d(
            world_mottle_surface(fg, cell_x, cell_y, size)
        ).astype(np.float32)
        tw = t[:, :, None]
        rgb = rgb * (1.0 - tw) + fg_arr * tw

        if fg == TerrainType.WATER:
            water_a = np.maximum(water_a, t * 255.0)
        elif bg == TerrainType.WATER:
            water_a = water_a * (1.0 - t)

        primary_mask = mask
        primary_fg = fg

    out = pygame.Surface((size, size))
    surfarray.blit_array(out, np.clip(rgb, 0, 255).astype(np.uint8))

    if np.any(water_a > 0.5):
        wa = np.clip(np.rint(water_a), 0, 255).astype(np.uint8)
        buf = pygame.Surface((size, size), pygame.SRCALPHA)
        px = pygame.surfarray.pixels_alpha(buf)
        px[:, :] = wa
        del px
        rgb3 = pygame.surfarray.pixels3d(buf)
        rgb3[:, :, :] = 255
        del rgb3
        water = buf

    return out, water, primary_mask, primary_fg, bg


def paint_cell(
    layer: pygame.Surface,
    water_mask: pygame.Surface,
    x: int,
    y: int,
    *,
    terrain_at: Callable[[int, int], TerrainType],
    cell_size: int | None = None,
    grass_mask: pygame.Surface | None = None,
    soil_mask: pygame.Surface | None = None,
) -> tuple[int, TerrainType, TerrainType, tuple[TerrainType, TerrainType, TerrainType, TerrainType]]:
    """Blit soft MS + mottling. Returns (mask, fg, bg, corners)."""
    size = CELL_SIZE if cell_size is None else cell_size
    corners = cell_corners(terrain_at, x, y)
    tl, tr, br, bl = corners
    rgb, wmask, mask, fg, bg = compose_cell_fills(
        tl, tr, br, bl, cell_x=x, cell_y=y, size=size
    )
    # Alpha stamps (rocks/foliage/…) for this cell's terrain — after mottling.
    from terrain_overlays import stamp_cell_overlays

    stamp_cell_overlays(rgb, terrain_at(x, y), x, y)
    dest = (x * size, y * size)
    layer.blit(rgb, dest)
    water_mask.fill((0, 0, 0, 0), pygame.Rect(dest[0], dest[1], size, size))
    water_mask.blit(wmask, dest)
    if grass_mask is not None:
        _blit_type_coverage(grass_mask, dest, size, corners, _GRASS_MASK_TYPES)
    if soil_mask is not None:
        _blit_type_coverage(soil_mask, dest, size, corners, _SOIL_MASK_TYPES)
    return mask, fg, bg, corners


_GRASS_MASK_TYPES: frozenset[TerrainType] = frozenset(
    {TerrainType.GRASS, TerrainType.MEADOW}
)
_SOIL_MASK_TYPES: frozenset[TerrainType] = frozenset(
    {TerrainType.SOIL, TerrainType.FOREST_FLOOR}
)

_COV_CACHE: dict[
    tuple[tuple[TerrainType, ...], frozenset[TerrainType], int],
    pygame.Surface,
] = {}


def _blit_type_coverage(
    mask: pygame.Surface,
    dest: tuple[int, int],
    size: int,
    corners: tuple[TerrainType, TerrainType, TerrainType, TerrainType],
    types: frozenset[TerrainType],
) -> None:
    """Write hard white coverage for terrain types into a seasonal mask."""
    rect = pygame.Rect(dest[0], dest[1], size, size)
    mask.fill((0, 0, 0, 0), rect)
    tl, tr, br, bl = corners
    if not any(t in types for t in corners):
        return
    if all(t in types for t in corners):
        mask.fill((255, 255, 255, 255), rect)
        return
    key = (corners, types, size)
    hit = _COV_CACHE.get(key)
    if hit is None:
        hit = _hard_type_coverage_surface(tl, tr, br, bl, types, size)
        _COV_CACHE[key] = hit
    mask.blit(hit, dest)


def _hard_type_coverage_surface(
    tl: TerrainType,
    tr: TerrainType,
    br: TerrainType,
    bl: TerrainType,
    types: frozenset[TerrainType],
    size: int,
) -> pygame.Surface:
    """OR of hard MS masks for every corner type in ``types``."""
    out = pygame.Surface((size, size), pygame.SRCALPHA)
    out.fill((0, 0, 0, 0))
    for terr in types:
        m = mask_for_corners(tl, tr, br, bl, terr)
        if m:
            out.blit(_fg_coverage_mask(m, size), (0, 0), special_flags=pygame.BLEND_RGBA_MAX)
    return out


def describe_system() -> str:
    return (
        "convention=16-case marching-squares + world-UV procedural mottling\n"
        "bits: TL=1 TR=2 BR=4 BL=8\n"
        "dirs: N=(0,-1) E=(+1,0) S=(0,+1) W=(-1,0)\n"
        "corners: shared vertex grid; max-priority among 2x2 cells\n"
        "joins: land↔land soft bilinear coverage (opaque colour lerp); water sharp\n"
        "fills: palette + multi-scale noise (terrain_mottle; preview knobs)\n"
        "atlas: logical 4x4 of cases 0..15 for F6 diagnostics\n"
    )


def verify_shared_edges(
    terrain_at: Callable[[int, int], TerrainType],
    x: int, y: int,
) -> tuple[bool, bool]:
    """Check east/west and south/north corner agreement with neighbours."""
    tl, tr, br, bl = cell_corners(terrain_at, x, y)
    etl, etr, ebr, ebl = cell_corners(terrain_at, x + 1, y)
    east_ok = tr == etl and br == ebl
    stl, str_, sbr, sbl = cell_corners(terrain_at, x, y + 1)
    south_ok = bl == stl and br == str_
    return east_ok, south_ok
