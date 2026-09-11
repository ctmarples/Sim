"""Isolated prototype: persistent landscape environmental fields.

Developer-only. Does not replace production World.generate / generate_map.
Does not drive flora niches or trees. Fields live on LandscapeFieldsState and
optionally mirror soil_texture onto cells for the existing texture overlay.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from soil_texture import (
    TEXTURE_BASE,
    blur_field,
    clamp01,
    generate_soil_texture_field,
    value_noise_field,
)

if TYPE_CHECKING:
    from world import World

# ---------------------------------------------------------------------------
# Defaults — broad coherent regions with independent fertility / hydrology.
# ---------------------------------------------------------------------------
DEFAULT_WIDTH = 48
DEFAULT_HEIGHT = 36
DEFAULT_SEED = 4201

# Soil texture: very broad structure, weak meso, near-zero micro.
DEFAULT_SOIL_REGION_SCALE = 0.55  # larger → broader knots (0.2..0.9)
DEFAULT_SOIL_VARIATION = 1.05

# Fertility potential: slightly finer independent structure.
DEFAULT_FERTILITY_REGION_SCALE = 0.38
DEFAULT_FERTILITY_VARIATION = 0.88

# Hydrology / moisture coupling strengths (0..1.5-ish).
DEFAULT_HYDROLOGY_STRENGTH = 1.0
DEFAULT_TEXTURE_MOISTURE_RETENTION = 0.22

# Mild, non-collapsing correlations (keep sandy≠dry≠poor).
FERTILITY_WET_BOOST = 0.10
FERTILITY_DRY_PENALTY = 0.08
WATER_PROXIMITY_RADIUS = 10
# Keep moisture related to hydro without cloning it.
MOISTURE_HYDRO_WEIGHT = 0.50
MOISTURE_WATER_WEIGHT = 0.14
MOISTURE_INDEPENDENT_AMP = 0.18


@dataclass
class LandscapeFieldsParams:
    """Small tuning surface for the Landscape Fields lab."""

    seed: int = DEFAULT_SEED
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    soil_region_scale: float = DEFAULT_SOIL_REGION_SCALE
    soil_variation_strength: float = DEFAULT_SOIL_VARIATION
    fertility_region_scale: float = DEFAULT_FERTILITY_REGION_SCALE
    fertility_variation_strength: float = DEFAULT_FERTILITY_VARIATION
    hydrology_strength: float = DEFAULT_HYDROLOGY_STRENGTH
    texture_moisture_retention: float = DEFAULT_TEXTURE_MOISTURE_RETENTION


@dataclass
class LandscapeFieldsState:
    """Experimental grids — not production Cell.fertility / EnvMaps moisture."""

    params: LandscapeFieldsParams
    soil_texture: list[list[float]] = field(default_factory=list)
    fertility_potential: list[list[float]] = field(default_factory=list)
    hydrological_position: list[list[float]] = field(default_factory=list)
    soil_moisture_baseline: list[list[float]] = field(default_factory=list)
    elevation: list[list[float]] = field(default_factory=list)
    water_mask: list[list[bool]] = field(default_factory=list)

    def at(self, x: int, y: int) -> dict[str, float | bool]:
        return {
            "x": x,
            "y": y,
            "soil_texture": round(self.soil_texture[y][x], 2),
            "fertility_potential": round(self.fertility_potential[y][x], 2),
            "hydrological_position": round(self.hydrological_position[y][x], 2),
            "soil_moisture_baseline": round(self.soil_moisture_baseline[y][x], 2),
            "elevation": round(self.elevation[y][x], 2),
            "water": bool(self.water_mask[y][x]),
        }


def _spacing_from_scale(short: int, scale: float, *, lo: int, hi: int) -> int:
    """Map 0..1 region-scale knob to knot spacing (larger scale → broader)."""
    t = max(0.15, min(0.95, float(scale)))
    return max(lo, min(hi, int(round(short * t))))


def build_landscape_fields_map(params: LandscapeFieldsParams):
    """Deterministic test landform with lake + elevation for hydrology tests."""
    from random_map_generator import GeneratedMap, MapOptions

    w = max(16, min(96, int(params.width)))
    h = max(12, min(72, int(params.height)))
    seed = int(params.seed)
    rng = random.Random(seed ^ 0x14D05C4E)

    short = max(8, min(w, h))
    elev_noise = value_noise_field(
        w, h, random.Random(seed ^ 0xE1E70001), spacing=max(8, short // 3), persistence=0.52
    )
    ridge = value_noise_field(
        w, h, random.Random(seed ^ 0x51D60002), spacing=max(6, short // 5), persistence=0.48
    )

    # Offset lake centre slightly per seed so hydrology varies.
    lake_cx = w * (0.42 + 0.16 * ((seed * 0.618) % 1.0))
    lake_cy = h * (0.45 + 0.14 * (((seed * 1.414) % 1.0)))
    lake_rx = max(3.5, w * 0.11)
    lake_ry = max(2.8, h * 0.10)

    elevation = [[0.0] * w for _ in range(h)]
    terrain = [["grass"] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            nx = (x - (w - 1) * 0.5) / max(1.0, w * 0.5)
            ny = (y - (h - 1) * 0.5) / max(1.0, h * 0.5)
            rim = math.sqrt(nx * nx + ny * ny)  # 0 centre → ~1 corners
            # Bowl: higher at edges; noise breaks radial symmetry.
            elev = (
                0.28 * elev_noise[y][x]
                + 0.18 * ridge[y][x]
                + 0.54 * min(1.0, rim * 0.92)
            )
            # Extra local depression around the lake focus.
            dx = (x - lake_cx) / lake_rx
            dy = (y - lake_cy) / lake_ry
            basin = math.exp(-0.5 * (dx * dx + dy * dy))
            elev -= 0.22 * basin
            elevation[y][x] = max(0.02, min(0.98, elev))

    # Water from absolute lows + basin core.
    sorted_elev = sorted(v for row in elevation for v in row)
    water_cut = sorted_elev[max(0, int(len(sorted_elev) * 0.07))]
    for y in range(h):
        for x in range(w):
            dx = (x - lake_cx) / lake_rx
            dy = (y - lake_cy) / lake_ry
            in_core = (dx * dx + dy * dy) <= 1.0
            if elevation[y][x] <= water_cut or in_core and elevation[y][x] < water_cut + 0.06:
                terrain[y][x] = "water"
                elevation[y][x] = min(elevation[y][x], water_cut * 0.85)

    # Soft riparian ring + meadow/soil bands from elevation (cover only).
    for y in range(h):
        for x in range(w):
            if terrain[y][x] == "water":
                continue
            near_water = any(
                0 <= nx < w
                and 0 <= ny < h
                and terrain[ny][nx] == "water"
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1),
                               (x - 1, y - 1), (x + 1, y - 1), (x - 1, y + 1), (x + 1, y + 1))
            )
            if near_water:
                terrain[y][x] = "riparian"
            elif elevation[y][x] > 0.72 and rng.random() < 0.35:
                terrain[y][x] = "rock"
            elif elevation[y][x] > 0.58:
                terrain[y][x] = "meadow"
            elif elevation[y][x] < 0.38:
                terrain[y][x] = "soil"
            else:
                terrain[y][x] = "grass"

    start = (max(1, w // 2), max(1, min(h - 2, int(lake_cy) + int(lake_ry) + 3)))
    if terrain[start[1]][start[0]] == "water":
        start = (start[0], min(h - 2, start[1] + 2))
    terrain[start[1]][start[0]] = "grass"

    # Map generator elevation is roughly 0..1-ish centres; apply_to_world ×80.
    options = MapOptions(
        width=w,
        height=h,
        seed=seed,
        composition="valley",
        climate="temperate",
        temperature=0.5,
        rainfall=0.55,
        roughness=0.3,
        generate_lake=True,
        generate_river=False,
    ).normalized()
    moisture = [
        [0.9 if terrain[y][x] == "water" else 0.55 for x in range(w)]
        for y in range(h)
    ]
    return GeneratedMap(options, terrain, elevation, moisture, start)


def generate_landscape_fields(
    world: "World",
    params: LandscapeFieldsParams | None = None,
) -> LandscapeFieldsState:
    """Build experimental fields from world water/elevation + continuous noise."""
    from environment import water_distance_grid
    from world import is_water_terrain

    p = params or LandscapeFieldsParams(seed=int(getattr(world, "seed", DEFAULT_SEED)))
    cols, rows = world.cols, world.rows
    short = max(8, min(cols, rows))
    seed = int(p.seed)

    # --- elevation sample (cell centres from corner grid) ---
    elevation = [[0.0] * cols for _ in range(rows)]
    corners = getattr(world, "height_corners", None)
    if corners is not None and len(corners) >= rows + 1:
        for y in range(rows):
            for x in range(cols):
                elevation[y][x] = 0.25 * (
                    float(corners[y][x])
                    + float(corners[y][x + 1])
                    + float(corners[y + 1][x])
                    + float(corners[y + 1][x + 1])
                )
    else:
        elevation = [[0.5] * cols for _ in range(rows)]

    emin = min(v for row in elevation for v in row)
    emax = max(v for row in elevation for v in row)
    espan = max(1e-6, emax - emin)
    elev_norm = [[(elevation[y][x] - emin) / espan for x in range(cols)] for y in range(rows)]

    water_mask = [
        [is_water_terrain(world.cells[y][x].terrain) for x in range(cols)]
        for y in range(rows)
    ]
    distances = water_distance_grid(world)
    radius = max(4, min(WATER_PROXIMITY_RADIUS, short // 3))
    water_prox = [
        [
            0.0
            if water_mask[y][x]
            else clamp01(1.0 - float(distances[y][x]) / float(radius)) ** 1.35
            for x in range(cols)
        ]
        for y in range(rows)
    ]

    # --- 1. soil texture (broad, almost terrain-free) ---
    soil_sp = _spacing_from_scale(short, p.soil_region_scale, lo=10, hi=max(12, short // 2))
    mid_sp = max(4, soil_sp // 3)
    soil_var = max(0.2, min(1.4, float(p.soil_variation_strength)))
    soil_texture = generate_soil_texture_field(
        cols,
        rows,
        seed,
        base=TEXTURE_BASE,
        regional_amp=0.48 * soil_var,
        mid_amp=0.14 * soil_var,
        fine_amp=0.012 * soil_var,
        regional_spacing=soil_sp,
        mid_spacing=mid_sp,
        fine_spacing=3,
        blur_radius=1,
        seed_mixin=0x50117E87,
    )
    # Gentle contrast so sandy/clayey belts occupy meaningful map area.
    soil_texture = [
        [clamp01(0.5 + (v - 0.5) * 1.20) for v in row] for row in soil_texture
    ]

    # --- 2. hydrological position (structure-driven, not generic noise) ---
    hydro_str = max(0.2, min(1.5, float(p.hydrology_strength)))
    mild = value_noise_field(
        cols, rows, random.Random(seed ^ 0x87D90003), spacing=max(6, short // 4), persistence=0.45
    )
    hydrological = [[0.0] * cols for _ in range(rows)]
    for y in range(rows):
        for x in range(cols):
            if water_mask[y][x]:
                hydrological[y][x] = 1.0
                continue
            # Low elevation + water proximity dominate; tiny noise for soft edges.
            low = 1.0 - elev_norm[y][x]
            raw = (
                0.42 * low
                + 0.50 * water_prox[y][x]
                + 0.08 * mild[y][x]
            )
            hydrological[y][x] = clamp01(0.5 + (raw - 0.5) * hydro_str)

    hydrological = blur_field(hydrological, 1)
    hydrological = [
        [1.0 if water_mask[y][x] else clamp01(hydrological[y][x]) for x in range(cols)]
        for y in range(rows)
    ]

    # --- 3. fertility potential (independent field + mild hydro correlation) ---
    fert_sp = _spacing_from_scale(
        short, p.fertility_region_scale, lo=6, hi=max(8, short // 3)
    )
    fert_var = max(0.2, min(1.4, float(p.fertility_variation_strength)))
    fert_rng = random.Random(seed ^ 0xFE2711E5)
    fert_regional = value_noise_field(cols, rows, fert_rng, spacing=fert_sp, persistence=0.55)
    fert_meso = value_noise_field(
        cols, rows, fert_rng, spacing=max(3, fert_sp // 3), persistence=0.50
    )
    fertility = [[0.0] * cols for _ in range(rows)]
    for y in range(rows):
        for x in range(cols):
            base = (
                0.48
                + (fert_regional[y][x] - 0.5) * (2.0 * 0.30 * fert_var)
                + (fert_meso[y][x] - 0.5) * (2.0 * 0.16 * fert_var)
            )
            # Mild wet boost / dry reduction — must not erase sandy+fertile etc.
            wet = hydrological[y][x]
            base += (wet - 0.45) * FERTILITY_WET_BOOST
            dry_exposure = elev_norm[y][x] * (1.0 - water_prox[y][x])
            base -= dry_exposure * FERTILITY_DRY_PENALTY
            fertility[y][x] = clamp01(base)
    fertility = blur_field(fertility, 1)
    fertility = [[clamp01(v) for v in row] for row in fertility]

    # --- 4. moisture baseline (hydrology primary, texture + mild independent meso) ---
    retain = max(0.0, min(0.45, float(p.texture_moisture_retention)))
    moist_indep = value_noise_field(
        cols,
        rows,
        random.Random(seed ^ 0xA0157004),
        spacing=max(5, short // 5),
        persistence=0.50,
    )
    moisture = [[0.0] * cols for _ in range(rows)]
    for y in range(rows):
        for x in range(cols):
            if water_mask[y][x]:
                moisture[y][x] = 1.0
                continue
            # Coarse (low texture) retains less; fine retains more.
            texture_term = (soil_texture[y][x] - 0.5) * (2.0 * retain)
            raw = (
                MOISTURE_HYDRO_WEIGHT * hydrological[y][x]
                + MOISTURE_WATER_WEIGHT * water_prox[y][x]
                + texture_term
                + MOISTURE_INDEPENDENT_AMP * (moist_indep[y][x] - 0.5) * 2.0
                + 0.06
            )
            moisture[y][x] = clamp01(raw)
    moisture = blur_field(moisture, 1)
    moisture = [
        [1.0 if water_mask[y][x] else clamp01(moisture[y][x]) for x in range(cols)]
        for y in range(rows)
    ]

    return LandscapeFieldsState(
        params=p,
        soil_texture=soil_texture,
        fertility_potential=fertility,
        hydrological_position=hydrological,
        soil_moisture_baseline=moisture,
        elevation=elev_norm,
        water_mask=water_mask,
    )


def apply_landscape_texture_to_world(world: "World", state: LandscapeFieldsState) -> None:
    """Mirror experimental soil_texture onto cells for the production overlay."""
    for y in range(world.rows):
        for x in range(world.cols):
            world.cells[y][x].soil_texture = clamp01(state.soil_texture[y][x])


def field_correlations(state: LandscapeFieldsState) -> dict[str, float]:
    """Pearson correlations over non-water cells (validation helper)."""

    def flatten(grid: list[list[float]]) -> list[float]:
        out: list[float] = []
        for y, row in enumerate(grid):
            for x, value in enumerate(row):
                if not state.water_mask[y][x]:
                    out.append(float(value))
        return out

    def pearson(a: list[float], b: list[float]) -> float:
        n = len(a)
        if n < 3:
            return 0.0
        ma = sum(a) / n
        mb = sum(b) / n
        num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
        da = math.sqrt(sum((x - ma) ** 2 for x in a))
        db = math.sqrt(sum((y - mb) ** 2 for y in b))
        if da < 1e-9 or db < 1e-9:
            return 0.0
        return num / (da * db)

    tex = flatten(state.soil_texture)
    fert = flatten(state.fertility_potential)
    hydro = flatten(state.hydrological_position)
    moist = flatten(state.soil_moisture_baseline)
    return {
        "texture_vs_fertility": pearson(tex, fert),
        "texture_vs_moisture": pearson(tex, moist),
        "hydrology_vs_moisture": pearson(hydro, moist),
        "fertility_vs_moisture": pearson(fert, moist),
    }


def summarise_fields(state: LandscapeFieldsState) -> dict[str, Any]:
    """Compact stats for CLI / lab status."""
    corr = field_correlations(state)

    def band_share(grid: list[list[float]], lo: float, hi: float) -> float:
        vals = [
            v
            for y, row in enumerate(grid)
            for x, v in enumerate(row)
            if not state.water_mask[y][x]
        ]
        if not vals:
            return 0.0
        return sum(1 for v in vals if lo <= v < hi) / len(vals)

    return {
        "seed": state.params.seed,
        "size": (state.params.width, state.params.height),
        "sandy_share": band_share(state.soil_texture, 0.0, 0.35),
        "clayey_share": band_share(state.soil_texture, 0.65, 1.01),
        "correlations": corr,
    }
