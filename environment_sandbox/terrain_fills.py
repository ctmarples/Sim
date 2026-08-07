"""Terrain fills: seamless PNG tiles for the game bake + colour-bucket preview tools.

Game paint path (``world_fill_surface``) samples ``assets/terrain/{stem}_N.png``
in continuous world UV (always variant 0) so adjacent cells share one field.

Colour-bucket helpers remain for ``preview_terrain_fills.py`` /
``generate_terrain_fills.py`` only — they are not used by Wang/MS joins.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

import pygame

from settings import (
    COLOUR_FOREST_FLOOR,
    COLOUR_GRASS,
    COLOUR_MEADOW,
    COLOUR_PATH,
    COLOUR_RIPARIAN,
    COLOUR_ROCK_TERRAIN,
    COLOUR_SOIL,
    COLOUR_URBAN,
    COLOUR_WATER,
    TERRAIN_SUBDIV,
)
from world import TerrainType

TILE = TERRAIN_SUBDIV
_TERRAIN_DIR = Path(__file__).resolve().parent / "assets" / "terrain"

FILL_RGB_NOISE: int = 0
FILL_VARIANT_TARGET: int = 8

_STEM: dict[TerrainType, str] = {
    TerrainType.SOIL: "soil",
    TerrainType.FOREST_FLOOR: "soil",
    TerrainType.GRASS: "grass",
    TerrainType.MEADOW: "meadow",
    TerrainType.RIPARIAN: "riparian",
    TerrainType.WATER: "water",
    TerrainType.RIVER: "water",
    TerrainType.ROCK: "rock",
    TerrainType.URBAN: "rock",
    TerrainType.PATH: "rock",
}

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

PREVIEW_TERRAINS: tuple[TerrainType, ...] = (
    TerrainType.GRASS,
    TerrainType.MEADOW,
    TerrainType.SOIL,
    TerrainType.RIPARIAN,
    TerrainType.ROCK,
    TerrainType.WATER,
)

Colour = tuple[int, int, int]
_PALETTE_CACHE: dict[str, tuple[list[Colour], list[int], list[int]]] = {}
_VARIANT_CACHE: dict[TerrainType, list[pygame.Surface]] = {}
_VARIANT_MTIME: dict[TerrainType, tuple[int, ...]] = {}
_SEAMLESS_CACHE: dict[TerrainType, list[pygame.Surface]] = {}
_SEAMLESS_MTIME: dict[TerrainType, tuple[int, ...]] = {}
_WORLD_FILL_CACHE: dict[tuple, pygame.Surface] = {}


def _hash01(x: int, y: int, salt: int = 0) -> float:
    n = (x * 374761393 + y * 668265263 + salt * 1274126177) & 0x7FFFFFFF
    return (n % 10007) / 10007.0


def _shift(colour: Colour, amount: float) -> Colour:
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


def procedural_fill(terrain: TerrainType, lx: int, ly: int) -> Colour:
    """Fallback mottling when no PNG exists yet."""
    base = _COLOURS[terrain]
    n1 = (_hash01(lx, ly, 11 + terrain.value * 17) - 0.5) * 0.16
    n2 = (_hash01(lx * 2, ly * 3, 40 + terrain.value) - 0.5) * 0.09
    return _shift(base, n1 + n2)


def variant_paths(terrain: TerrainType) -> list[Path]:
    stem = _STEM.get(terrain)
    if not stem:
        return []
    paths = sorted(_TERRAIN_DIR.glob(f"{stem}_*.png"))
    if not paths:
        single = _TERRAIN_DIR / f"{stem}.png"
        if single.is_file():
            paths = [single]
    return paths


def palette_path(stem: str) -> Path:
    return _TERRAIN_DIR / f"{stem}_palette.json"


def _make_seamless(surf: pygame.Surface, blend: int | None = None) -> pygame.Surface:
    """Crossfade opposite edges so the tile repeats without a hard seam."""
    w, h = surf.get_width(), surf.get_height()
    if w < 2 or h < 2:
        return surf
    ramp = blend if blend is not None else max(2, min(w, h) // 5)
    ramp = max(1, min(ramp, w // 2, h // 2))
    src = [[surf.get_at((x, y))[:3] for x in range(w)] for y in range(h)]

    def _mix(a: Colour, b: Colour, t: float) -> Colour:
        return (
            int(round(a[0] + (b[0] - a[0]) * t)),
            int(round(a[1] + (b[1] - a[1]) * t)),
            int(round(a[2] + (b[2] - a[2]) * t)),
        )

    def _wrap_axis(grid: list[list[Colour]], horizontal: bool) -> None:
        if horizontal:
            for y in range(h):
                for i in range(ramp):
                    t = 1.0 - i / ramp
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

    _wrap_axis(src, True)
    _wrap_axis(src, False)
    _wrap_axis(src, True)
    _wrap_axis(src, False)

    out = pygame.Surface((w, h))
    for y in range(h):
        for x in range(w):
            out.set_at((x, y), src[y][x])
    return out


def load_seamless_variants(terrain: TerrainType) -> list[pygame.Surface]:
    """PNG variants scaled to TILE×TILE and made seamless for world-UV paint."""
    paths = variant_paths(terrain)
    mtimes = tuple(p.stat().st_mtime_ns for p in paths) if paths else ()
    cached = _SEAMLESS_CACHE.get(terrain)
    if cached is not None and _SEAMLESS_MTIME.get(terrain) == mtimes:
        return cached
    surfs: list[pygame.Surface] = []
    for path in paths:
        raw = pygame.image.load(str(path))
        try:
            raw = raw.convert()
        except pygame.error:
            pass
        if raw.get_width() != TILE or raw.get_height() != TILE:
            raw = pygame.transform.scale(raw, (TILE, TILE))
        surfs.append(_make_seamless(raw))
    _SEAMLESS_CACHE[terrain] = surfs
    _SEAMLESS_MTIME[terrain] = mtimes
    return surfs


def sample_png_world(
    terrain: TerrainType,
    wx: int,
    wy: int,
    *,
    variant: int = 0,
) -> Colour:
    """Colour at world pixel from seamless PNG (fallback: procedural mottling)."""
    variants = load_seamless_variants(terrain)
    if not variants:
        return procedural_fill(terrain, wx, wy)
    surf = variants[variant % len(variants)]
    tw, th = surf.get_width(), surf.get_height()
    return surf.get_at((wx % tw, wy % th))[:3]


def _cdf_from_weights(weights: list[int]) -> list[int]:
    cdf: list[int] = []
    total = 0
    for w in weights:
        total += max(0, int(w))
        cdf.append(total)
    return cdf


def _store_palette(
    stem: str, colours: list[Colour], weights: list[int]
) -> tuple[list[Colour], list[int], list[int]]:
    if not colours:
        colours = [_COLOURS[TerrainType.GRASS]]
        weights = [1]
    cdf = _cdf_from_weights(weights)
    if cdf[-1] <= 0:
        weights = [1] * len(colours)
        cdf = _cdf_from_weights(weights)
    packed = (colours, weights, cdf)
    _PALETTE_CACHE[stem] = packed
    return packed


def extract_colour_bucket_from_surfaces(
    surfs: list[pygame.Surface],
) -> tuple[list[Colour], list[int]]:
    """Weighted RGB palette + densities from one or more tiles."""
    counts: Counter[Colour] = Counter()
    for surf in surfs:
        w, h = surf.get_width(), surf.get_height()
        for y in range(h):
            for x in range(w):
                counts[surf.get_at((x, y))[:3]] += 1
    if not counts:
        return [], []
    colours = list(counts.keys())
    weights = [counts[c] for c in colours]
    return colours, weights


def extract_colour_bucket(terrain: TerrainType) -> tuple[list[Colour], list[int]]:
    """Build palette from on-disk PNGs for this biome (or solid fallback)."""
    surfs: list[pygame.Surface] = []
    for path in variant_paths(terrain):
        raw = pygame.image.load(str(path))
        if raw.get_width() != TILE or raw.get_height() != TILE:
            raw = pygame.transform.scale(raw, (TILE, TILE))
        surfs.append(raw)
    if not surfs:
        return [_COLOURS[terrain]], [1]
    return extract_colour_bucket_from_surfaces(surfs)


def save_palette(stem: str, colours: list[Colour], weights: list[int]) -> Path:
    path = palette_path(stem)
    payload = {
        "colours": [list(c) for c in colours],
        "weights": list(weights),
        "unique": len(colours),
        "pixels": int(sum(weights)),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _store_palette(stem, colours, weights)
    return path


def load_palette_file(stem: str) -> tuple[list[Colour], list[int]] | None:
    path = palette_path(stem)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    colours = [tuple(int(x) for x in c) for c in data["colours"]]
    weights = [int(w) for w in data["weights"]]
    return colours, weights  # type: ignore[return-value]


def ensure_palette(
    terrain: TerrainType,
) -> tuple[list[Colour], list[int], list[int]]:
    """Return (colours, weights, cdf) for ``terrain``, loading or extracting."""
    stem = _STEM[terrain]
    hit = _PALETTE_CACHE.get(stem)
    if hit is not None:
        return hit
    loaded = load_palette_file(stem)
    if loaded is not None:
        colours, weights = loaded
        return _store_palette(stem, colours, weights)
    colours, weights = extract_colour_bucket(terrain)
    return _store_palette(stem, colours, weights)


def pick_from_bucket(
    colours: list[Colour],
    cdf: list[int],
    *,
    wx: int,
    wy: int,
    salt: int,
) -> Colour:
    """Deterministic weighted pick from the colour bucket at world pixel."""
    total = cdf[-1]
    slot = int(_hash01(wx, wy, salt) * total)
    if slot >= total:
        slot = total - 1
    lo, hi = 0, len(cdf) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if slot < cdf[mid]:
            hi = mid
        else:
            lo = mid + 1
    return colours[lo]


def sample_world(
    terrain: TerrainType,
    wx: int,
    wy: int,
    *,
    variant: int = 0,
) -> Colour:
    """Preview/tool colour-bucket sample (not used by Wang/MS paint)."""
    colours, _weights, cdf = ensure_palette(terrain)
    salt = 400 + terrain.value * 31 + int(variant) * 17
    return pick_from_bucket(colours, cdf, wx=wx, wy=wy, salt=salt)


def scatter_tile(
    terrain: TerrainType,
    *,
    seed: int,
    size: int | None = None,
) -> pygame.Surface:
    """One TILE×TILE (or ``size``) random draw from the biome colour bucket."""
    dim = TILE if size is None else size
    colours, weights, _cdf = ensure_palette(terrain)
    rng = random.Random(seed)
    surf = pygame.Surface((dim, dim))
    population = colours
    for y in range(dim):
        for x in range(dim):
            surf.set_at((x, y), rng.choices(population, weights=weights, k=1)[0])
    return surf


def load_variants(terrain: TerrainType) -> list[pygame.Surface]:
    """Load PNG variants for the preview strip (plain; no seamless wrap)."""
    paths = variant_paths(terrain)
    mtimes = tuple(p.stat().st_mtime_ns for p in paths) if paths else ()
    cached = _VARIANT_CACHE.get(terrain)
    if cached is not None and _VARIANT_MTIME.get(terrain) == mtimes:
        return cached
    surfs: list[pygame.Surface] = []
    for path in paths:
        raw = pygame.image.load(str(path))
        try:
            raw = raw.convert()
        except pygame.error:
            pass
        if raw.get_width() != TILE or raw.get_height() != TILE:
            raw = pygame.transform.scale(raw, (TILE, TILE))
        surfs.append(raw)
    if not surfs:
        for i in range(FILL_VARIANT_TARGET):
            surfs.append(scatter_tile(terrain, seed=terrain.value * 100 + i))
    _VARIANT_CACHE[terrain] = surfs
    _VARIANT_MTIME[terrain] = mtimes
    return surfs


def clear_fill_cache() -> None:
    _VARIANT_CACHE.clear()
    _VARIANT_MTIME.clear()
    _SEAMLESS_CACHE.clear()
    _SEAMLESS_MTIME.clear()
    _WORLD_FILL_CACHE.clear()
    _PROC_TILE_CACHE.clear()
    _PALETTE_CACHE.clear()


def variant_count(terrain: TerrainType) -> int:
    n = len(variant_paths(terrain))
    if n > 0:
        return n
    return FILL_VARIANT_TARGET


def has_png_fills(terrain: TerrainType) -> bool:
    return bool(variant_paths(terrain)) or palette_path(_STEM[terrain]).is_file()


def variant_index(terrain: TerrainType, cell_x: int, cell_y: int) -> int:
    """Preview helper — paint path always uses variant 0."""
    n = variant_count(terrain)
    if n <= 1:
        return 0
    return int(_hash01(cell_x, cell_y, 200) * 9973) % n


def world_fill_surface(
    terrain: TerrainType,
    cell_x: int,
    cell_y: int,
    size: int,
    *,
    variant: int | None = None,
) -> pygame.Surface:
    """``size``×``size`` seamless PNG fill in continuous world UV (variant 0).

    Built by blit-tiling the TILE×TILE source (not per-pixel Python sampling).
    Cached by texture phase so the full map rebake stays fast.
    """
    del variant
    v = 0
    src = _fill_source_tile(terrain, v)
    tw, th = src.get_width(), src.get_height()
    # Phase in texture space — adjacent cells share continuous UV.
    ox = (cell_x * size) % tw
    oy = (cell_y * size) % th
    key = (terrain, size, ox, oy, v, "png-blit")
    hit = _WORLD_FILL_CACHE.get(key)
    if hit is not None:
        return hit
    out = pygame.Surface((size, size))
    # Blit tiles so world (cell_x*size, cell_y*size) maps to texture (ox, oy).
    y = -oy
    while y < size:
        x = -ox
        while x < size:
            out.blit(src, (x, y))
            x += tw
        y += th
    _WORLD_FILL_CACHE[key] = out
    return out


_PROC_TILE_CACHE: dict[TerrainType, pygame.Surface] = {}


def _fill_source_tile(terrain: TerrainType, variant: int = 0) -> pygame.Surface:
    """TILE×TILE source for world-UV blit tiling (seamless PNG or procedural)."""
    variants = load_seamless_variants(terrain)
    if variants:
        return variants[variant % len(variants)]
    hit = _PROC_TILE_CACHE.get(terrain)
    if hit is not None:
        return hit
    surf = pygame.Surface((TILE, TILE))
    for ly in range(TILE):
        for lx in range(TILE):
            surf.set_at((lx, ly), procedural_fill(terrain, lx, ly))
    _PROC_TILE_CACHE[terrain] = surf
    return surf


def fill_inventory() -> list[tuple[TerrainType, str, int, list[Path]]]:
    rows: list[tuple[TerrainType, str, int, list[Path]]] = []
    for terrain in PREVIEW_TERRAINS:
        paths = variant_paths(terrain)
        rows.append((terrain, _STEM[terrain], len(paths), paths))
    return rows


def palette_summary(terrain: TerrainType) -> str:
    colours, weights, _cdf = ensure_palette(terrain)
    total = sum(weights)
    return f"{len(colours)} colours / {total} px"


def generate_variant_set(
    *,
    count: int | None = None,
    noise: int | None = None,
    stems: tuple[str, ...] | None = None,
) -> list[Path]:
    """Extract colour buckets from current tiles, then rewrite ``_1..N`` as scatter.

    Saves ``{stem}_palette.json`` so density survives regenerations.
    """
    del noise
    n = FILL_VARIANT_TARGET if count is None else max(1, int(count))
    wanted = set(stems) if stems is not None else None
    written: list[Path] = []
    seen_stems: set[str] = set()

    for terrain in PREVIEW_TERRAINS:
        stem = _STEM[terrain]
        if stem in seen_stems:
            continue
        if wanted is not None and stem not in wanted:
            continue
        seen_stems.add(stem)

        loaded = load_palette_file(stem)
        if loaded is not None:
            colours, weights = loaded
        else:
            colours, weights = extract_colour_bucket(terrain)
        save_palette(stem, colours, weights)

        for old in _TERRAIN_DIR.glob(f"{stem}_*.png"):
            old.unlink()
        for i in range(1, n + 1):
            tile = scatter_tile(terrain, seed=terrain.value * 1009 + i * 97)
            path = _TERRAIN_DIR / f"{stem}_{i}.png"
            pygame.image.save(tile, str(path))
            written.append(path)

    clear_fill_cache()
    return written
