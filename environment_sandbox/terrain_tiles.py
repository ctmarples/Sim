"""Soft-joined terrain tiling from PNG textures.

Each cell blends with its east / south / south-east neighbours so habitat
edges are gradual on both sides (no one-sided dark rim). Water shores stay
sharp. Corner priority helpers remain for F6 diagnostics.

Fills come from ``assets/terrain/{stem}_N.png``. PNGs are edge-crossfaded on
load, then sampled with continuous world-space UVs so the texture period is
the PNG size (not the cell size) — no per-cell grid/screen-door.
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

_VARIANT_CACHE: dict[TerrainType, list[pygame.Surface]] = {}
_VARIANT_MTIME: dict[TerrainType, tuple[int, ...]] = {}


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
    """Procedural fallback when no PNG variants exist."""
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


def _make_seamless(surf: pygame.Surface, blend: int | None = None) -> pygame.Surface:
    """Crossfade opposite edges so the tile repeats without a hard seam.

    Opposite edge pixels are forced equal (averaged), with a short ramp into
    the interior so non-tileable art does not leave a dark grid when repeated.
    """
    w, h = surf.get_width(), surf.get_height()
    if w < 2 or h < 2:
        return surf
    ramp = blend if blend is not None else max(2, min(w, h) // 5)
    ramp = max(1, min(ramp, w // 2, h // 2))
    src = [[surf.get_at((x, y))[:3] for x in range(w)] for y in range(h)]

    def _mix(
        a: tuple[int, int, int], b: tuple[int, int, int], t: float
    ) -> tuple[int, int, int]:
        return (
            int(round(a[0] + (b[0] - a[0]) * t)),
            int(round(a[1] + (b[1] - a[1]) * t)),
            int(round(a[2] + (b[2] - a[2]) * t)),
        )

    def _wrap_axis(grid: list[list[tuple[int, int, int]]], horizontal: bool):
        if horizontal:
            for y in range(h):
                for i in range(ramp):
                    t = 1.0 - i / ramp  # 1 at outer edge → 0 at ramp
                    left = grid[y][i]
                    right = grid[y][w - 1 - i]
                    mid = _mix(left, right, 0.5)
                    grid[y][i] = _mix(left, mid, t)
                    grid[y][w - 1 - i] = _mix(right, mid, t)
        else:
            for x in range(w):
                for i in range(ramp):
                    t = 1.0 - i / ramp
                    top = grid[i][x]
                    bot = grid[h - 1 - i][x]
                    mid = _mix(top, bot, 0.5)
                    grid[i][x] = _mix(top, mid, t)
                    grid[h - 1 - i][x] = _mix(bot, mid, t)

    # Horizontal then vertical; repeat once so corners stay consistent.
    _wrap_axis(src, True)
    _wrap_axis(src, False)
    _wrap_axis(src, True)
    _wrap_axis(src, False)

    out = pygame.Surface((w, h))
    for y in range(h):
        for x in range(w):
            out.set_at((x, y), src[y][x])
    return out


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
        surfs.append(_make_seamless(raw))
    _VARIANT_CACHE[terrain] = surfs
    _VARIANT_MTIME[terrain] = mtimes
    return surfs


def clear_texture_cache() -> None:
    _VARIANT_CACHE.clear()
    _VARIANT_MTIME.clear()
    _COVERAGE_CACHE.clear()
    _SOFT_COVERAGE_CACHE.clear()
    _WORLD_FILL_CACHE.clear()
    global _ATLAS
    _ATLAS = None


def variant_count(terrain: TerrainType) -> int:
    return max(1, len(_load_variants(terrain)))


def cell_variant_roll(cell_x: int, cell_y: int) -> int:
    return int(_hash01(cell_x, cell_y, 200) * 9973) % 9973


def variant_index(terrain: TerrainType, cell_x: int, cell_y: int) -> int:
    n = variant_count(terrain)
    if n <= 1:
        return 0
    return cell_variant_roll(cell_x, cell_y) % n


def _fill_tile(
    terrain: TerrainType,
    *,
    variant: int = 0,
) -> pygame.Surface:
    """TILE×TILE seamless fill (variant 0 by default)."""
    return _terrain_tile_surface(terrain, variant=variant)


def sample_world(
    terrain: TerrainType,
    wx: int,
    wy: int,
    *,
    variant: int = 0,
) -> tuple[int, int, int]:
    """Colour at continuous world pixel (seamless PNG or procedural)."""
    variants = _load_variants(terrain)
    if not variants:
        return _opaque_fill(terrain, wx, wy)
    surf = variants[variant % len(variants)]
    tw, th = surf.get_width(), surf.get_height()
    return surf.get_at((wx % tw, wy % th))[:3]


def sample_fill(
    terrain: TerrainType,
    lx: int,
    ly: int,
    *,
    cell_x: int = 0,
    cell_y: int = 0,
    variant: int | None = None,
    cell_size: int | None = None,
) -> tuple[int, int, int]:
    """Colour at local cell pixel using world-space UV (no per-cell restart)."""
    size = TILE if cell_size is None else cell_size
    v = 0 if variant is None else variant
    return sample_world(terrain, cell_x * size + lx, cell_y * size + ly, variant=v)


_WORLD_FILL_CACHE: dict[tuple, pygame.Surface] = {}


def world_fill_surface(
    terrain: TerrainType,
    cell_x: int,
    cell_y: int,
    size: int,
    *,
    variant: int = 0,
) -> pygame.Surface:
    """``size``×``size`` fill sampled with world UV so adjacent cells continue."""
    variants = _load_variants(terrain)
    if not variants:
        key = (terrain, cell_x, cell_y, size, "proc")
        hit = _WORLD_FILL_CACHE.get(key)
        if hit is not None:
            return hit
        surf = pygame.Surface((size, size))
        for ly in range(size):
            for lx in range(size):
                surf.set_at(
                    (lx, ly),
                    _opaque_fill(terrain, cell_x * size + lx, cell_y * size + ly),
                )
        _WORLD_FILL_CACHE[key] = surf
        return surf

    tex = variants[variant % len(variants)]
    tw, th = tex.get_width(), tex.get_height()
    ox = (cell_x * size) % tw
    oy = (cell_y * size) % th
    key = (terrain, variant, ox, oy, size, tw, th)
    hit = _WORLD_FILL_CACHE.get(key)
    if hit is not None:
        return hit

    pad_w = size + tw
    pad_h = size + th
    pad = pygame.Surface((pad_w, pad_h))
    for yy in range(0, pad_h, th):
        for xx in range(0, pad_w, tw):
            pad.blit(tex, (xx, yy))
    out = pad.subsurface((ox, oy, size, size)).convert()
    _WORLD_FILL_CACHE[key] = out
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
    """Shared vertex (vx, vy): highest-priority terrain among the 2×2 cells.

    Priority WATER > ROCK > SOIL > RIPARIAN > MEADOW > GRASS (no colour averaging).
    Adjacent cells read the same vertex, so shared edges cannot disagree.
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


_COVERAGE_CACHE: dict[tuple[int, int], pygame.Surface] = {}
_SOFT_COVERAGE_CACHE: dict[tuple[int, int], pygame.Surface] = {}


def _fg_coverage_mask(mask: int, size: int | None = None) -> pygame.Surface:
    """Hard (binary) MS coverage — water edges."""
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
    for poly in _unit_polygons(mask):
        pts = [(int(round(x * (size - 1))), int(round(y * (size - 1)))) for x, y in poly]
        if len(pts) >= 3:
            pygame.draw.polygon(surf, (255, 255, 255, 255), pts)
    _COVERAGE_CACHE[key] = surf
    return surf


def _fg_soft_coverage_mask(mask: int, size: int | None = None) -> pygame.Surface:
    """Soft bilinear MS coverage — land↔land."""
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


def _stamp_terrain(
    dest: pygame.Surface,
    texture: pygame.Surface,
    coverage: pygame.Surface,
) -> None:
    stamped = pygame.Surface(dest.get_size(), pygame.SRCALPHA)
    stamped.blit(texture.convert_alpha(), (0, 0))
    stamped.blit(coverage, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    dest.blit(stamped, (0, 0))


def _terrain_tile_surface(
    terrain: TerrainType,
    *,
    cell_x: int = 0,
    cell_y: int = 0,
    variant: int | None = None,
) -> pygame.Surface:
    """TILE×TILE fill surface for MS composition."""
    variants = _load_variants(terrain)
    if variants:
        idx = variant_index(terrain, cell_x, cell_y) if variant is None else variant
        return variants[idx % len(variants)]
    surf = pygame.Surface((TILE, TILE))
    for ly in range(TILE):
        for lx in range(TILE):
            surf.set_at((lx, ly), _opaque_fill(terrain, lx, ly))
    return surf


def build_tile_from_corners(
    tl: TerrainType,
    tr: TerrainType,
    br: TerrainType,
    bl: TerrainType,
    *,
    cell_x: int = 0,
    cell_y: int = 0,
    join_variant: bool = False,
) -> tuple[pygame.Surface, pygame.Surface, int, TerrainType, TerrainType]:
    """MS composition from four shared corners.

    Land↔land transitions are gradual (soft bilinear coverage).
    Water↔other stays sharp. Fills from PNG variants (or procedural fallback).

    When ``join_variant`` is True (transition tiles), always use variant 0 so
    neighbouring transition cells share the same fill textures.
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
    v = 0 if join_variant else None
    water = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
    water.fill((0, 0, 0, 0))

    rgb = _terrain_tile_surface(bg, cell_x=cell_x, cell_y=cell_y, variant=v).convert()
    if bg == TerrainType.WATER:
        water.fill((255, 255, 255, 255))

    primary_mask = 15 if len(present) == 1 else 0
    primary_fg = bg

    for fg in present[1:]:
        mask = mask_for_corners(tl, tr, br, bl, fg)
        if mask == 0:
            continue
        sharp = fg == TerrainType.WATER or bg == TerrainType.WATER
        coverage = (
            _fg_coverage_mask(mask) if sharp else _fg_soft_coverage_mask(mask)
        )
        tex = _terrain_tile_surface(fg, cell_x=cell_x, cell_y=cell_y, variant=v)
        _stamp_terrain(rgb, tex, coverage)
        if fg == TerrainType.WATER:
            water.blit(coverage, (0, 0))
        elif bg == TerrainType.WATER:
            inv = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
            inv.fill((255, 255, 255, 255))
            inv.blit(coverage, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
            water.blit(inv, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        primary_mask = mask
        primary_fg = fg

    return rgb, water, primary_mask, primary_fg, bg


def build_soft_neighbour_tile(
    t00: TerrainType,
    t10: TerrainType,
    t01: TerrainType,
    t11: TerrainType,
    *,
    cell_x: int = 0,
    cell_y: int = 0,
    size: int | None = None,
) -> tuple[pygame.Surface, pygame.Surface, int, TerrainType, TerrainType]:
    """Continuous soft land join using this cell + E/S/SE neighbours.

    Both sides of a shared edge blend the same way, so there is no dark MS rim.
    Water stays sharp (thresholded bilinear field). Fills use world-space UV.
    """
    size = CELL_SIZE if size is None else size
    corners = (t00, t10, t11, t01)
    present: list[TerrainType] = []
    for p in _PRIORITY:
        if p in corners and p not in present:
            present.append(p)
    bg = present[0]
    fg = present[-1]
    mask = mask_for_corners(t00, t10, t11, t01, fg)

    water = pygame.Surface((size, size), pygame.SRCALPHA)
    water.fill((0, 0, 0, 0))

    if t00 == t10 == t01 == t11:
        rgb = world_fill_surface(t00, cell_x, cell_y, size).convert()
        if t00 == TerrainType.WATER:
            water.fill((255, 255, 255, 255))
        return rgb, water, 15, t00, t00

    land_types = [t for t in present if t != TerrainType.WATER]
    has_water = TerrainType.WATER in present
    if not has_water and len(land_types) <= 2:
        rgb = world_fill_surface(bg, cell_x, cell_y, size).convert()
        for terr in land_types[1:]:
            m = mask_for_corners(t00, t10, t11, t01, terr)
            if m == 0:
                continue
            _stamp_terrain(
                rgb,
                world_fill_surface(terr, cell_x, cell_y, size),
                _fg_soft_coverage_mask(m, size),
            )
        return rgb, water, mask, fg, bg

    if has_water and len(land_types) == 1:
        land = land_types[0]
        rgb = world_fill_surface(land, cell_x, cell_y, size).convert()
        wmask = mask_for_corners(t00, t10, t11, t01, TerrainType.WATER)
        if wmask:
            cov = _fg_coverage_mask(wmask, size)
            _stamp_terrain(
                rgb, world_fill_surface(TerrainType.WATER, cell_x, cell_y, size), cov
            )
            water.blit(cov, (0, 0))
        return rgb, water, mask, fg, bg

    # General path (3+ types): per-pixel blend with world UV.
    rgb = pygame.Surface((size, size))
    denom = max(1, size)
    for ly in range(size):
        v = (ly + 0.5) / denom
        for lx in range(size):
            u = (lx + 0.5) / denom
            wfield = _bilinear(
                1.0 if t00 == TerrainType.WATER else 0.0,
                1.0 if t10 == TerrainType.WATER else 0.0,
                1.0 if t11 == TerrainType.WATER else 0.0,
                1.0 if t01 == TerrainType.WATER else 0.0,
                u,
                v,
            )
            if wfield >= 0.5:
                rgb.set_at(
                    (lx, ly),
                    sample_fill(
                        TerrainType.WATER,
                        lx,
                        ly,
                        cell_x=cell_x,
                        cell_y=cell_y,
                        variant=0,
                        cell_size=size,
                    ),
                )
                a = (
                    255
                    if wfield >= 0.55
                    else int(round(_smoothstep((wfield - 0.45) / 0.2) * 255))
                )
                water.set_at((lx, ly), (255, 255, 255, a))
                continue

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
                    land = next(
                        (
                            t
                            for t, _ in sorted(cells, key=lambda kv: -kv[1])
                            if t != TerrainType.WATER
                        ),
                        bg if bg != TerrainType.WATER else TerrainType.GRASS,
                    )
                    terr = land
                colours.append(
                    sample_fill(
                        terr,
                        lx,
                        ly,
                        cell_x=cell_x,
                        cell_y=cell_y,
                        variant=0,
                        cell_size=size,
                    )
                )
                weights.append(w)
            total = sum(weights) or 1.0
            r = g = b = 0.0
            inv = 1.0 / total
            for (cr, cg, cb), w in zip(colours, weights):
                w *= inv
                r += cr * w
                g += cg * w
                b += cb * w
            rgb.set_at((lx, ly), (int(r), int(g), int(b)))

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
        # Touch PNG cache so seamless variants are ready.
        for terrain in TerrainType:
            _load_variants(terrain)

    def tile_for_neighbourhood(
        self,
        t00: TerrainType,
        t10: TerrainType,
        t01: TerrainType,
        t11: TerrainType,
        *,
        cell_x: int = 0,
        cell_y: int = 0,
        force_join_variant: bool = False,
    ) -> tuple[pygame.Surface, pygame.Surface, int, TerrainType, TerrainType]:
        del force_join_variant
        self.ensure()
        size = self._cell_size
        # Phase so soft-join cache stays correct under world UV.
        variants = _load_variants(t00)
        tw = variants[0].get_width() if variants else TILE
        th = variants[0].get_height() if variants else TILE
        ox = (cell_x * size) % tw
        oy = (cell_y * size) % th

        if t00 == t10 == t01 == t11:
            rgb = world_fill_surface(t00, cell_x, cell_y, size)
            water = pygame.Surface((size, size), pygame.SRCALPHA)
            water.fill((0, 0, 0, 0))
            if t00 == TerrainType.WATER:
                water.fill((255, 255, 255, 255))
            return rgb, water, 15, t00, t00

        key = (t00, t10, t01, t11, ox, oy, size)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        out = build_soft_neighbour_tile(
            t00, t10, t01, t11, cell_x=cell_x, cell_y=cell_y, size=size
        )
        self._cache[key] = out
        return out

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
        """F6 / diagnostics: MS corner args mapped onto a soft neighbourhood."""
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
    """This cell + east + south + south-east."""
    return (
        terrain_at(x, y),
        terrain_at(x + 1, y),
        terrain_at(x, y + 1),
        terrain_at(x + 1, y + 1),
    )


def _cell_on_boundary(
    terrain_at: Callable[[int, int], TerrainType],
    x: int,
    y: int,
    terrain: TerrainType,
) -> bool:
    """True when any 8-neighbour differs — lock fill to variant 0 for seamless joins."""
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            if terrain_at(x + dx, y + dy) != terrain:
                return True
    return False


def paint_cell(
    layer: pygame.Surface,
    water_mask: pygame.Surface,
    x: int,
    y: int,
    *,
    terrain_at: Callable[[int, int], TerrainType],
    cell_size: int | None = None,
) -> tuple[int, TerrainType, TerrainType, tuple[TerrainType, TerrainType, TerrainType, TerrainType]]:
    """Blit soft-joined tile. Returns (mask, fg, bg, neighbourhood)."""
    size = CELL_SIZE if cell_size is None else cell_size
    atlas = get_atlas()
    atlas.ensure(size)
    neigh = cell_neighbourhood(terrain_at, x, y)
    on_boundary = neigh[0] == neigh[1] == neigh[2] == neigh[3] and _cell_on_boundary(
        terrain_at, x, y, neigh[0]
    )
    rgb, wmask, mask, fg, bg = atlas.tile_for_neighbourhood(
        *neigh, cell_x=x, cell_y=y, force_join_variant=on_boundary
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
        "convention=soft E/S neighbour joins + PNG fills in assets/terrain/\n"
        f"variants: {counts}\n"
        "joins: each cell blends with east/south/SE (no one-sided MS rim)\n"
        "water: sharp thresholded shore; land: gradual colour mix\n"
        "fills: seamless PNG world-UV (period=texture size, not cell)\n"
        "corners (F6): shared vertex grid WATER>ROCK>SOIL>RIPARIAN>MEADOW>GRASS\n"
    )


def verify_shared_edges(
    terrain_at: Callable[[int, int], TerrainType],
    x: int,
    y: int,
) -> tuple[bool, bool]:
    """Check east/west and south/north corner agreement with neighbours."""
    tl, tr, br, bl = cell_corners(terrain_at, x, y)
    etl, etr, ebr, ebl = cell_corners(terrain_at, x + 1, y)
    east_ok = tr == etl and br == ebl
    stl, str_, sbr, sbl = cell_corners(terrain_at, x, y + 1)
    south_ok = bl == stl and br == str_
    return east_ok, south_ok
