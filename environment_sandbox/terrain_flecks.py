"""Seasonal speckle + cluster overlays (shared by game + previewer).

Density fields are seed-stable white-alpha maps; recipes tint and mask them
per calendar half-season (8 periods / year). Preview can tune strengths and
drop a synthetic forest patch in the field centre for halo flecks.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace

import pygame

from seasons import DAYS_PER_SEASON, YEAR_DAYS
from world import TerrainType

Colour = tuple[int, int, int]

COLOUR_WHITE: Colour = (235, 240, 245)
COLOUR_YELLOW: Colour = (210, 195, 55)
COLOUR_GREEN: Colour = (80, 175, 60)
COLOUR_BROWN: Colour = (160, 85, 40)
COLOUR_ORANGE: Colour = (210, 125, 40)

DENSITY_KEYS: tuple[str, ...] = (
    "speckle_light",
    "speckle_med",
    "speckle_heavy",
    "cluster_light",
    "cluster_med",
    "cluster_heavy",
)

_PERIOD_NAMES: tuple[str, ...] = (
    "spring early",
    "spring late",
    "summer early",
    "summer late",
    "autumn early",
    "autumn late",
    "winter early",
    "winter late",
)

# Mask tags → terrain types (recipes can target any land cover).
MASK_TYPES: dict[str, frozenset[TerrainType]] = {
    "grass": frozenset({TerrainType.GRASS}),
    "meadow": frozenset({TerrainType.MEADOW}),
    "soil": frozenset({TerrainType.SOIL}),
    "forest": frozenset({TerrainType.FOREST_FLOOR}),
    "rock": frozenset({TerrainType.ROCK}),
    "path": frozenset({TerrainType.PATH}),
    "riparian": frozenset({TerrainType.RIPARIAN}),
    "urban": frozenset({TerrainType.URBAN}),
    "water": frozenset({TerrainType.WATER, TerrainType.RIVER}),
    "grass_meadow": frozenset({TerrainType.GRASS, TerrainType.MEADOW}),
    "open": frozenset({TerrainType.SOIL, TerrainType.GRASS, TerrainType.MEADOW}),
    "all_land": frozenset(
        {
            TerrainType.SOIL,
            TerrainType.GRASS,
            TerrainType.MEADOW,
            TerrainType.FOREST_FLOOR,
            TerrainType.RIPARIAN,
            TerrainType.ROCK,
            TerrainType.URBAN,
            TerrainType.PATH,
        }
    ),
    "hard": frozenset(
        {
            TerrainType.FOREST_FLOOR,
            TerrainType.RIPARIAN,
            TerrainType.ROCK,
            TerrainType.URBAN,
            TerrainType.PATH,
        }
    ),
}

_DENSITY_CACHE: dict[tuple, dict[str, pygame.Surface]] = {}
_STAMP_CACHE: dict[tuple, pygame.Surface] = {}
_MASK_CACHE: dict[tuple, pygame.Surface] = {}


@dataclass
class FleckParams:
    """Tunable overlay strengths (per season period; preview + game)."""

    enabled: bool = True
    clusters_enabled: bool = True
    speckle_density: float = 1.0
    cluster_density: float = 1.0
    speckle_alpha: float = 1.0
    cluster_alpha: float = 1.0
    cluster_spread: float = 1.0
    seed: int = 0


FLECK_PARAMS = FleckParams()


def get_fleck_params() -> FleckParams:
    return FLECK_PARAMS


def set_fleck_params(params: FleckParams) -> None:
    global FLECK_PARAMS
    FLECK_PARAMS = params
    clear_fleck_cache()


def clear_fleck_cache() -> None:
    _DENSITY_CACHE.clear()
    _STAMP_CACHE.clear()
    _MASK_CACHE.clear()


def period_for_day(calendar_day: int) -> int:
    d = int(calendar_day) % YEAR_DAYS
    season_i = d // DAYS_PER_SEASON
    half = 0 if (d % DAYS_PER_SEASON) < (DAYS_PER_SEASON // 2) else 1
    return season_i * 2 + half


def period_name(period: int) -> str:
    return _PERIOD_NAMES[period & 7]


def scramble(i: int, salt: int) -> int:
    n = (i * 2654435761 + salt * 1597334677) & 0xFFFFFFFF
    n ^= n >> 16
    n = (n * 2246822519) & 0xFFFFFFFF
    n ^= n >> 13
    return n & 0x7FFFFFFF


def _fleck_params_key(p: FleckParams, w: int, h: int) -> tuple:
    return (
        w,
        h,
        int(p.seed),
        bool(p.clusters_enabled),
        round(p.speckle_density, 4),
        round(p.cluster_density, 4),
        round(p.speckle_alpha, 4),
        round(p.cluster_alpha, 4),
        round(p.cluster_spread, 4),
    )


def _cluster_stamp(
    *,
    salt: int,
    dots: int,
    spread: int,
    alpha_lo: int,
    alpha_hi: int,
) -> pygame.Surface:
    variant = salt % 24
    key = (dots, spread, alpha_lo, alpha_hi, variant)
    hit = _STAMP_CACHE.get(key)
    if hit is not None:
        return hit
    size = spread * 2 + 6
    stamp = pygame.Surface((size, size), pygame.SRCALPHA)
    cx = cy = size // 2
    for i in range(dots):
        ang = (scramble(variant + i, 10) / 0x7FFFFFFF) * math.tau
        dist = (scramble(variant + i, 40) / 0x7FFFFFFF) * spread
        px = cx + int(dist * math.cos(ang))
        py = cy + int(dist * math.sin(ang) * 0.85)
        alpha = alpha_lo + (
            scramble(variant + i, 130) % max(1, alpha_hi - alpha_lo + 1)
        )
        if i < 2:
            alpha = min(alpha_hi + 20, alpha + 15)
        radius = 1 if (scramble(variant + i, 160) % 10) < 7 else 2
        if 0 <= px < size and 0 <= py < size:
            pygame.draw.circle(stamp, (255, 255, 255, alpha), (px, py), radius)
    _STAMP_CACHE[key] = stamp
    return stamp


def _bake_speckle(
    surf: pygame.Surface,
    *,
    salt: int,
    frac: float,
    alpha_lo: int,
    alpha_hi: int,
) -> None:
    w, h = surf.get_size()
    n = max(0, int(round(w * h * frac)))
    for i in range(n):
        px = scramble(i, salt + 17) % w
        py = scramble(i, salt + 19) % h
        alpha = alpha_lo + (
            scramble(i, salt + 23) % max(1, alpha_hi - alpha_lo + 1)
        )
        surf.set_at((px, py), (255, 255, 255, alpha))


def _bake_cluster(
    surf: pygame.Surface,
    *,
    salt: int,
    frac: float,
    alpha_lo: int,
    alpha_hi: int,
    cluster_dots: int,
    cluster_spread: int,
) -> None:
    w, h = surf.get_size()
    n = max(0, int(round(w * h * frac)))
    for i in range(n):
        cx = scramble(i, salt + 41) % w
        cy = scramble(i, salt + 43) % h
        spread = max(2, cluster_spread + (scramble(i, salt + 47) % 3))
        stamp = _cluster_stamp(
            salt=salt + i * 47,
            dots=cluster_dots,
            spread=spread,
            alpha_lo=alpha_lo,
            alpha_hi=alpha_hi,
        )
        surf.blit(
            stamp,
            (cx - stamp.get_width() // 2, cy - stamp.get_height() // 2),
        )


def ensure_densities(
    width: int,
    height: int,
    params: FleckParams | None = None,
) -> dict[str, pygame.Surface]:
    p = FLECK_PARAMS if params is None else params
    key = _fleck_params_key(p, width, height)
    hit = _DENSITY_CACHE.get(key)
    if hit is not None:
        return hit

    sa = max(0.0, min(2.0, p.speckle_alpha))
    ca = max(0.0, min(2.0, p.cluster_alpha))
    sd = max(0.0, min(3.0, p.speckle_density))
    cd = max(0.0, min(3.0, p.cluster_density))
    spread_mul = max(0.5, min(2.0, p.cluster_spread))

    def _alpha(lo: int, hi: int, mul: float) -> tuple[int, int]:
        return (
            max(0, min(255, int(lo * mul))),
            max(0, min(255, int(hi * mul))),
        )

    specs: list[tuple[str, str, dict]] = [
        (
            "speckle_light",
            "speckle",
            dict(salt=11001 + p.seed, frac=0.0035 * sd, alpha_lo=55, alpha_hi=130),
        ),
        (
            "speckle_med",
            "speckle",
            dict(salt=11002 + p.seed, frac=0.010 * sd, alpha_lo=50, alpha_hi=125),
        ),
        (
            "speckle_heavy",
            "speckle",
            dict(salt=11003 + p.seed, frac=0.024 * sd, alpha_lo=45, alpha_hi=140),
        ),
        (
            "cluster_light",
            "cluster",
            dict(
                salt=22001 + p.seed,
                frac=0.00012 * cd,
                alpha_lo=50,
                alpha_hi=120,
                cluster_dots=14,
                cluster_spread=max(2, int(round(4 * spread_mul))),
            ),
        ),
        (
            "cluster_med",
            "cluster",
            dict(
                salt=22002 + p.seed,
                frac=0.00040 * cd,
                alpha_lo=45,
                alpha_hi=130,
                cluster_dots=22,
                cluster_spread=max(2, int(round(5 * spread_mul))),
            ),
        ),
        (
            "cluster_heavy",
            "cluster",
            dict(
                salt=22003 + p.seed,
                frac=0.0010 * cd,
                alpha_lo=40,
                alpha_hi=150,
                cluster_dots=30,
                cluster_spread=max(2, int(round(6 * spread_mul))),
            ),
        ),
    ]

    out: dict[str, pygame.Surface] = {}
    for name, kind, kwargs in specs:
        layer = pygame.Surface((width, height), pygame.SRCALPHA)
        layer.fill((0, 0, 0, 0))
        lo, hi = _alpha(kwargs["alpha_lo"], kwargs["alpha_hi"], sa if kind == "speckle" else ca)
        kwargs = {**kwargs, "alpha_lo": lo, "alpha_hi": hi}
        if kind == "speckle":
            _bake_speckle(layer, **kwargs)
        else:
            _bake_cluster(layer, **kwargs)
        out[name] = layer

    _DENSITY_CACHE[key] = out
    return out


def period_recipe(period: int) -> dict[str, tuple[Colour, str]]:
    """field_key → (rgb, mask_tag). Extended so every land cover gets flecks."""
    W, Y, G, B, O = (
        COLOUR_WHITE,
        COLOUR_YELLOW,
        COLOUR_GREEN,
        COLOUR_BROWN,
        COLOUR_ORANGE,
    )
    p = period & 7
    if p == 0:
        return {
            "speckle_light": (W, "open"),
            "speckle_med": (W, "forest"),
            "cluster_light": (W, "rock"),
        }
    if p == 1:
        return {
            "speckle_light": (W, "grass_meadow"),
            "speckle_med": (Y, "meadow"),
            "cluster_light": (G, "riparian"),
        }
    if p == 2:
        return {
            "speckle_med": (Y, "grass_meadow"),
            "speckle_heavy": (G, "soil"),
            "cluster_med": (G, "forest"),
        }
    if p == 3:
        return {
            "speckle_light": (Y, "soil"),
            "speckle_heavy": (Y, "grass_meadow"),
            "cluster_light": (G, "grass_meadow"),
            "cluster_med": (G, "meadow"),
            "speckle_med": (Y, "path"),
        }
    if p == 4:
        return {
            "speckle_light": (O, "halo"),
            "speckle_med": (Y, "halo"),
            "cluster_med": (B, "halo"),
            "speckle_heavy": (O, "all_land"),
            "cluster_light": (B, "forest"),
        }
    if p == 5:
        return {
            "speckle_med": (O, "halo"),
            "speckle_heavy": (Y, "halo"),
            "cluster_heavy": (B, "halo"),
            "cluster_med": (O, "all_land"),
            "speckle_light": (O, "rock"),
        }
    if p == 6:
        return {
            "speckle_med": (W, "open"),
            "cluster_med": (W, "open_water"),
            "speckle_light": (W, "hard"),
            "cluster_light": (W, "urban"),
        }
    return {
        "speckle_light": (W, "hard"),
        "speckle_heavy": (W, "open_water"),
        "cluster_light": (W, "open_water"),
        "cluster_med": (W, "water"),
        "cluster_heavy": (W, "all_land"),
    }


def halo_radius_for_period(period: int) -> int:
    if period == 4:
        return 5
    if period == 5:
        return 10
    return 5


def build_terrain_mask(
    terrain_grid: list[list[TerrainType]],
    cell_size: int,
    types: frozenset[TerrainType],
) -> pygame.Surface:
    rows = len(terrain_grid)
    cols = len(terrain_grid[0]) if rows else 0
    w, h = cols * cell_size, rows * cell_size
    key = (tuple(tuple(row) for row in terrain_grid), cell_size, types)
    hit = _MASK_CACHE.get(key)
    if hit is not None:
        return hit
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0))
    for y, row in enumerate(terrain_grid):
        for x, terr in enumerate(row):
            if terr in types:
                surf.fill(
                    (255, 255, 255, 255),
                    pygame.Rect(x * cell_size, y * cell_size, cell_size, cell_size),
                )
    _MASK_CACHE[key] = surf
    return surf


def build_halo_mask(
    width: int,
    height: int,
    *,
    center_px: tuple[int, int],
    radius_px: int,
) -> pygame.Surface:
    key = ("halo", width, height, center_px, radius_px)
    hit = _MASK_CACHE.get(key)
    if hit is not None:
        return hit
    surf = pygame.Surface((width, height), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0))
    pygame.draw.circle(surf, (255, 255, 255, 255), center_px, max(1, radius_px))
    _MASK_CACHE[key] = surf
    return surf


def build_open_water_mask(
    land_mask: pygame.Surface,
    water_mask: pygame.Surface,
) -> pygame.Surface:
    key = ("open_water", id(land_mask), id(water_mask), land_mask.get_size())
    hit = _MASK_CACHE.get(key)
    if hit is not None:
        return hit
    out = land_mask.copy()
    if water_mask.get_size() != out.get_size():
        wm = pygame.transform.scale(water_mask, out.get_size())
    else:
        wm = water_mask
    out.blit(wm, (0, 0), special_flags=pygame.BLEND_RGBA_MAX)
    _MASK_CACHE[key] = out
    return out


def resolve_mask(
    tag: str,
    terrain_grid: list[list[TerrainType]],
    cell_size: int,
    *,
    water_mask: pygame.Surface | None = None,
    halo_mask: pygame.Surface | None = None,
) -> pygame.Surface:
    if tag == "halo":
        if halo_mask is None:
            rows = len(terrain_grid)
            cols = len(terrain_grid[0]) if rows else 0
            return pygame.Surface((cols * cell_size, rows * cell_size), pygame.SRCALPHA)
        return halo_mask
    if tag == "open_water":
        open_m = build_terrain_mask(terrain_grid, cell_size, MASK_TYPES["open"])
        if water_mask is None:
            return open_m
        return build_open_water_mask(open_m, water_mask)
    types = MASK_TYPES.get(tag)
    if types is None:
        rows = len(terrain_grid)
        cols = len(terrain_grid[0]) if rows else 0
        return pygame.Surface((cols * cell_size, rows * cell_size), pygame.SRCALPHA)
    return build_terrain_mask(terrain_grid, cell_size, types)


def _tint_density(density: pygame.Surface, rgb: Colour) -> pygame.Surface:
    tinted = pygame.Surface(density.get_size(), pygame.SRCALPHA)
    tinted.fill((*rgb, 255))
    tinted.blit(density, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return tinted


def compose_overlay(
    width: int,
    height: int,
    *,
    period: int,
    terrain_grid: list[list[TerrainType]],
    cell_size: int,
    params: FleckParams | None = None,
    water_mask: pygame.Surface | None = None,
    forest_center: bool = False,
    halo_radius_cells: int = 6,
) -> pygame.Surface | None:
    p = FLECK_PARAMS if params is None else params
    if not p.enabled:
        return None

    densities = ensure_densities(width, height, p)
    recipe = period_recipe(period)
    halo = None
    if forest_center:
        cx = width // 2
        cy = height // 2
        halo = build_halo_mask(
            width,
            height,
            center_px=(cx, cy),
            radius_px=max(cell_size, halo_radius_cells * cell_size // 2),
        )

    overlay = pygame.Surface((width, height), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 0))
    halo_r = halo_radius_for_period(period)

    for field, (rgb, tag) in recipe.items():
        if field.startswith("cluster") and not p.clusters_enabled:
            continue
        if tag == "halo" and halo is None:
            continue
        density = densities.get(field)
        if density is None:
            continue
        layer = _tint_density(density, rgb)
        mask = resolve_mask(
            tag,
            terrain_grid,
            cell_size,
            water_mask=water_mask,
            halo_mask=halo if tag == "halo" else None,
        )
        if mask.get_size() != layer.get_size():
            mask = pygame.transform.scale(mask, layer.get_size())
        layer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        overlay.blit(layer, (0, 0))

    return overlay


def compose_crossfade(
    width: int,
    height: int,
    *,
    from_period: int | None,
    to_period: int,
    from_alpha: float,
    to_alpha: float,
    terrain_grid: list[list[TerrainType]],
    cell_size: int,
    from_params: FleckParams | None = None,
    to_params: FleckParams | None = None,
    water_mask: pygame.Surface | None = None,
    forest_center: bool = False,
    master_opacity: float = 1.0,
) -> pygame.Surface | None:
    """Blend outgoing + incoming period overlays (sim-style season transition)."""
    layers: list[tuple[pygame.Surface, float]] = []
    if from_period is not None and from_alpha > 0.001:
        src = compose_overlay(
            width,
            height,
            period=from_period,
            terrain_grid=terrain_grid,
            cell_size=cell_size,
            params=from_params,
            water_mask=water_mask,
            forest_center=forest_center,
        )
        if src is not None:
            layers.append((src, from_alpha))
    if to_alpha > 0.001:
        dst = compose_overlay(
            width,
            height,
            period=to_period,
            terrain_grid=terrain_grid,
            cell_size=cell_size,
            params=to_params,
            water_mask=water_mask,
            forest_center=forest_center,
        )
        if dst is not None:
            layers.append((dst, to_alpha))
    if not layers:
        return None
    out = pygame.Surface((width, height), pygame.SRCALPHA)
    out.fill((0, 0, 0, 0))
    mop = max(0.0, min(1.5, master_opacity))
    for surf, a in layers:
        alpha = max(0, min(255, int(255 * a * mop)))
        if alpha <= 0:
            continue
        if alpha < 255:
            s = surf.copy()
            s.set_alpha(alpha)
            out.blit(s, (0, 0))
        else:
            out.blit(surf, (0, 0))
    return out


def apply_flecks(
    dest: pygame.Surface,
    *,
    period: int,
    terrain_grid: list[list[TerrainType]],
    cell_size: int,
    params: FleckParams | None = None,
    water_mask: pygame.Surface | None = None,
    forest_center: bool = False,
) -> None:
    """Alpha-composite seasonal flecks onto an opaque RGB surface."""
    w, h = dest.get_size()
    overlay = compose_overlay(
        w,
        h,
        period=period,
        terrain_grid=terrain_grid,
        cell_size=cell_size,
        params=params,
        water_mask=water_mask,
        forest_center=forest_center,
    )
    if overlay is not None:
        dest.blit(overlay, (0, 0))


def apply_flecks_for_day(
    dest: pygame.Surface,
    *,
    day: float,
    terrain_grid: list[list[TerrainType]],
    cell_size: int,
    water_mask: pygame.Surface | None = None,
    forest_center: bool = False,
) -> tuple[int, int | None, float]:
    """Compose flecks for a continuous year-day (with crossfade). Uses terrain_settings."""
    from terrain_settings import (
        fade_alphas,
        get_anim_params,
        get_fleck,
        season_transition,
    )

    anim = get_anim_params()
    to_p, from_p, t = season_transition(day, anim=anim)
    from_a, to_a = fade_alphas(t, anim=anim)
    w, h = dest.get_size()
    overlay = compose_crossfade(
        w,
        h,
        from_period=from_p,
        to_period=to_p,
        from_alpha=from_a,
        to_alpha=to_a,
        terrain_grid=terrain_grid,
        cell_size=cell_size,
        from_params=get_fleck(from_p) if from_p is not None else None,
        to_params=get_fleck(to_p),
        water_mask=water_mask,
        forest_center=forest_center,
        master_opacity=anim.opacity,
    )
    if overlay is not None:
        dest.blit(overlay, (0, 0))
    return to_p, from_p, t


def preview_terrain_grid(
    biome: TerrainType,
    grid: int,
    *,
    forest_center: bool,
    forest_radius: int = 1,
) -> list[list[TerrainType]]:
    """Fill grid with ``biome``; optional FOREST_FLOOR patch in the middle."""
    rows = [[biome for _ in range(grid)] for _ in range(grid)]
    if not forest_center:
        return rows
    mid = grid // 2
    for y in range(max(0, mid - forest_radius), min(grid, mid + forest_radius + 1)):
        for x in range(max(0, mid - forest_radius), min(grid, mid + forest_radius + 1)):
            rows[y][x] = TerrainType.FOREST_FLOOR
    return rows


def fleck_params_as_dict() -> dict:
    return asdict(FLECK_PARAMS)
