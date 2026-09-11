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

try:
    from settings import WORLD_COLS, WORLD_ROWS
except Exception:  # pragma: no cover - headless fallback
    WORLD_COLS, WORLD_ROWS = 96, 72

if TYPE_CHECKING:
    from world import World

# ---------------------------------------------------------------------------
# Defaults — broad coherent regions with independent fertility / hydrology.
# ---------------------------------------------------------------------------
DEFAULT_WIDTH = WORLD_COLS
DEFAULT_HEIGHT = WORLD_ROWS
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
    """Experimental grids — not production Cell.fertility / EnvMaps moisture.

    Intermediate landscape structure:
        soil_texture, fertility_potential, hydrological_position

    Plant-facing preview environment (fed to wild_species niche scoring):
        soil_moisture ← moisture baseline (hydro + texture retention + …)
        fertility ← fertility_potential (pre-management site quality)
        temperature ← static niche-normalised preview (not live EnvMaps °C)
        disturbance ← virgin-map baseline
    """

    params: LandscapeFieldsParams
    soil_texture: list[list[float]] = field(default_factory=list)
    fertility_potential: list[list[float]] = field(default_factory=list)
    hydrological_position: list[list[float]] = field(default_factory=list)
    soil_moisture_baseline: list[list[float]] = field(default_factory=list)
    # Plant-facing mirrors / previews
    soil_moisture: list[list[float]] = field(default_factory=list)
    fertility: list[list[float]] = field(default_factory=list)
    temperature: list[list[float]] = field(default_factory=list)
    disturbance: list[list[float]] = field(default_factory=list)
    elevation: list[list[float]] = field(default_factory=list)
    water_mask: list[list[bool]] = field(default_factory=list)

    def at(self, x: int, y: int) -> dict[str, float | bool]:
        return {
            "x": x,
            "y": y,
            "soil_texture": round(self.soil_texture[y][x], 2),
            "fertility_potential": round(self.fertility_potential[y][x], 2),
            "hydrological_position": round(self.hydrological_position[y][x], 2),
            "soil_moisture": round(self.soil_moisture[y][x], 2),
            "fertility": round(self.fertility[y][x], 2),
            "temperature": round(self.temperature[y][x], 2),
            "disturbance": round(self.disturbance[y][x], 2),
            "elevation": round(self.elevation[y][x], 2),
            "water": bool(self.water_mask[y][x]),
        }

    def plant_env(self, x: int, y: int) -> dict[str, float]:
        """Values consumed by ``species_environment_suitability`` (temp already 0..1)."""
        return {
            "temperature": float(self.temperature[y][x]),
            "soil_moisture": float(self.soil_moisture[y][x]),
            "fertility": float(self.fertility[y][x]),
            "disturbance": float(self.disturbance[y][x]),
            "soil_texture": float(self.soil_texture[y][x]),
        }


def _spacing_from_scale(short: int, scale: float, *, lo: int, hi: int) -> int:
    """Map 0..1 region-scale knob to knot spacing (larger scale → broader)."""
    t = max(0.15, min(0.95, float(scale)))
    return max(lo, min(hi, int(round(short * t))))


def build_landscape_fields_map(params: LandscapeFieldsParams):
    """Full-size production-style map (usual terrain mix) for the lab.

    Uses ``generate_map`` so cover includes forest, grass, meadow, soil, rock,
    water, river, and riparian — not a miniature single-basin toy landform.
    Experimental landscape fields are layered afterward from water/elevation.
    """
    from random_map_generator import MapOptions, generate_map

    w = max(16, min(256, int(params.width) or DEFAULT_WIDTH))
    h = max(12, min(256, int(params.height) or DEFAULT_HEIGHT))
    options = MapOptions(
        width=w,
        height=h,
        seed=int(params.seed),
        composition="valley",
        climate="temperate",
        temperature=0.5,
        rainfall=0.55,
        roughness=0.45,
        generate_lake=True,
        generate_river=True,
    ).normalized()
    return generate_map(options)


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

    # --- 5. Plant-facing previews (explicit derivations; not live EnvMaps) ---
    # Fertility preview := fertility_potential (pre-management site quality).
    plant_fertility = [row[:] for row in fertility]
    # Moisture preview := moisture baseline (already hydro + texture + …).
    plant_moisture = [row[:] for row in moisture]

    # Temperature: niche-normalised 0..1 preview. Warm open rises, cooler wet hollows.
    # Not production temperature_grid / seasonal °C.
    temp_noise = value_noise_field(
        cols, rows, random.Random(seed ^ 0x7E400005), spacing=max(6, short // 4), persistence=0.45
    )
    temperature = [[0.0] * cols for _ in range(rows)]
    for y in range(rows):
        for x in range(cols):
            if water_mask[y][x]:
                temperature[y][x] = 0.42  # cool water bodies
                continue
            temperature[y][x] = clamp01(
                0.50
                + (1.0 - elev_norm[y][x]) * 0.10
                - hydrological[y][x] * 0.12
                + (temp_noise[y][x] - 0.5) * 0.08
            )

    # Disturbance: low virgin baseline with mild spatial noise (no traffic yet).
    dist_noise = value_noise_field(
        cols, rows, random.Random(seed ^ 0xD1570006), spacing=max(4, short // 6), persistence=0.40
    )
    disturbance = [[0.0] * cols for _ in range(rows)]
    for y in range(rows):
        for x in range(cols):
            if water_mask[y][x]:
                disturbance[y][x] = 0.0
                continue
            disturbance[y][x] = clamp01(0.08 + (dist_noise[y][x] - 0.5) * 0.10)

    return LandscapeFieldsState(
        params=p,
        soil_texture=soil_texture,
        fertility_potential=fertility,
        hydrological_position=hydrological,
        soil_moisture_baseline=moisture,
        soil_moisture=plant_moisture,
        fertility=plant_fertility,
        temperature=temperature,
        disturbance=disturbance,
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


# ---------------------------------------------------------------------------
# Ecology diagnostics — reuse wild_species niche scoring (no parallel model).
# ---------------------------------------------------------------------------

DOMINANT_SUITABILITY_FLOOR = 0.25
DEFAULT_PATCH_THRESHOLD = 0.50


@dataclass
class TileNicheResult:
    """One tile × species evaluation via production niche code + hard site filters."""

    suitability: Any  # PlantSuitability
    display_combined: float
    terrain_ok: bool
    establishment_ok: bool
    fail_reasons: tuple[str, ...]
    env: dict[str, float]
    spatial_combined: float = 0.0
    activity: float = 1.0
    current_combined: float = 0.0
    # Fallen wood uses appearance seasonality rather than biological activity.
    temporal_label: str = "Seasonal activity"


def hard_site_failure_reason(world: "World", x: int, y: int, species) -> str | None:
    """Explain World._species_can_occupy failure, or None if the site is allowed."""
    from world import FeatureType, TerrainType

    cell = world.get_cell(x, y)
    if cell is None:
        return "Terrain: invalid"
    if isinstance(species.terrains, str):
        allowed = {species.terrains}
    else:
        allowed = set(species.terrains)
    if cell.terrain.name not in allowed:
        return "Terrain: invalid"
    near_name = getattr(species, "near_feature", None)
    if near_name:
        try:
            required = FeatureType[near_name]
        except KeyError:
            return f"Near-feature: unknown {near_name}"
        if not any(
            (nx, ny) != (x, y) and world.cells[ny][nx].feature == required
            for ny, nx in world.neighbourhood(x, y, radius=1)
        ):
            return f"Near-feature: need {near_name}"
    edge_names = getattr(species, "edge_terrains", ()) or ()
    if isinstance(edge_names, str):
        edge_names = (edge_names,)
    if edge_names:
        edge = {TerrainType[n] for n in edge_names if n in TerrainType.__members__}
        if edge and not any(
            (nx, ny) != (x, y) and world.cells[ny][nx].terrain in edge
            for ny, nx in world.neighbourhood(x, y, radius=1)
        ):
            return "Edge terrain: required neighbour missing"
    if not world._species_can_occupy(x, y, species):
        return "Terrain: invalid"
    return None


def establishment_failure_reasons(species, suitability) -> tuple[str, ...]:
    """Hard establishment gates from wild_species (temp / moisture / texture)."""
    from wild_species import MIN_NICHE_RESPONSE_FOR_ESTABLISHMENT

    reasons: list[str] = []
    pairs = (
        ("Temperature", species.temperature_niche, suitability.temperature),
        ("Moisture", species.moisture_niche, suitability.moisture),
        ("Texture", species.texture_niche, suitability.soil_texture),
    )
    for label, niche, score in pairs:
        if niche is not None and score < MIN_NICHE_RESPONSE_FOR_ESTABLISHMENT:
            reasons.append(f"{label} establishment threshold failed")
    return tuple(reasons)


def evaluate_species_on_landscape(
    world: "World",
    state: LandscapeFieldsState,
    x: int,
    y: int,
    species,
    *,
    day: float = 42.0,
    suitability_mode: str = "spatial",
) -> TileNicheResult:
    """Score one tile using experimental plant-facing env + real niche evaluator.

    ``suitability_mode``:
      - ``spatial`` — habitat only (ignore season)
      - ``current`` — spatial × activity_at_day
    """
    from wild_species import (
        activity_at_day,
        environment_allows_establishment,
        species_environment_suitability,
    )

    env = state.plant_env(x, y)
    suitability = species_environment_suitability(
        species,
        temperature=env["temperature"],
        soil_moisture=env["soil_moisture"],
        fertility=env["fertility"],
        disturbance=env["disturbance"],
        soil_texture=env["soil_texture"],
    )
    site_fail = hard_site_failure_reason(world, x, y, species)
    terrain_ok = site_fail is None
    estab_reasons = establishment_failure_reasons(species, suitability)
    establishment_ok = environment_allows_establishment(species, suitability)
    fails: list[str] = []
    if site_fail:
        fails.append(site_fail)
    fails.extend(estab_reasons)
    spatial = float(suitability.combined) if terrain_ok and establishment_ok else 0.0
    activity = float(activity_at_day(species, day))
    current = spatial * activity
    display = current if suitability_mode == "current" else spatial
    temporal_label = (
        "Appearance seasonality"
        if getattr(species, "key", "") == "wood_bush"
        else "Seasonal activity"
    )
    return TileNicheResult(
        suitability=suitability,
        display_combined=display,
        terrain_ok=terrain_ok,
        establishment_ok=establishment_ok,
        fail_reasons=tuple(fails),
        env=env,
        spatial_combined=spatial,
        activity=activity,
        current_combined=current,
        temporal_label=temporal_label,
    )


def suitability_grid(
    world: "World",
    state: LandscapeFieldsState,
    species,
    *,
    day: float = 42.0,
    suitability_mode: str = "spatial",
) -> list[list[float]]:
    """Map-wide display suitability (0 where hard-invalid)."""
    rows, cols = world.rows, world.cols
    out = [[0.0] * cols for _ in range(rows)]
    for y in range(rows):
        for x in range(cols):
            out[y][x] = evaluate_species_on_landscape(
                world,
                state,
                x,
                y,
                species,
                day=day,
                suitability_mode=suitability_mode,
            ).display_combined
    return out


def suitability_summary(grid: list[list[float]], water_mask: list[list[bool]]) -> dict[str, float | int]:
    vals = [
        grid[y][x]
        for y, row in enumerate(grid)
        for x, _ in enumerate(row)
        if not water_mask[y][x]
    ]
    if not vals:
        return {
            "mean": 0.0, "max": 0.0,
            "pct_gt_025": 0.0, "pct_gt_050": 0.0, "pct_gt_075": 0.0,
            "n": 0,
        }
    n = len(vals)
    return {
        "mean": sum(vals) / n,
        "max": max(vals),
        "pct_gt_025": sum(1 for v in vals if v > 0.25) / n,
        "pct_gt_050": sum(1 for v in vals if v > 0.50) / n,
        "pct_gt_075": sum(1 for v in vals if v > 0.75) / n,
        "n": n,
    }


def high_suitability_patches(
    world: "World",
    grid: list[list[float]],
    *,
    threshold: float = DEFAULT_PATCH_THRESHOLD,
) -> dict[str, Any]:
    """Connected components where suitability >= threshold."""
    cells = {
        (x, y)
        for y, row in enumerate(grid)
        for x, value in enumerate(row)
        if value >= threshold
    }
    patches = world._connected_patches(cells) if cells else []
    patches.sort(key=len, reverse=True)
    centres = []
    for patch in patches[:8]:
        cx = sum(p[0] for p in patch) / len(patch)
        cy = sum(p[1] for p in patch) / len(patch)
        centres.append((round(cx, 1), round(cy, 1), len(patch)))
    return {
        "count": len(patches),
        "largest": len(patches[0]) if patches else 0,
        "centres": centres,
    }


def dominant_species_maps(
    world: "World",
    state: LandscapeFieldsState,
    species_list: list,
    *,
    floor: float = DOMINANT_SUITABILITY_FLOOR,
    day: float = 42.0,
    suitability_mode: str = "spatial",
) -> tuple[list[list[float]], list[list[str | None]], dict[str, tuple[int, int, int]]]:
    """Per-cell winner among catalogue species; categorical colour table."""
    rows, cols = world.rows, world.cols
    score_grid = [[0.0] * cols for _ in range(rows)]
    key_grid: list[list[str | None]] = [[None] * cols for _ in range(rows)]
    colours: dict[str, tuple[int, int, int]] = {}
    for species in species_list:
        colours[species.key] = _stable_species_colour(species.key)
    for y in range(rows):
        for x in range(cols):
            if state.water_mask[y][x]:
                continue
            best_key = None
            best = floor
            for species in species_list:
                result = evaluate_species_on_landscape(
                    world,
                    state,
                    x,
                    y,
                    species,
                    day=day,
                    suitability_mode=suitability_mode,
                )
                if result.display_combined > best:
                    best = result.display_combined
                    best_key = species.key
            if best_key is not None:
                key_grid[y][x] = best_key
                # Encode hue index as 0..1 for overlay fallback; colour drawn categorically.
                keys = list(colours.keys())
                score_grid[y][x] = (keys.index(best_key) + 0.5) / max(1, len(keys))
    return score_grid, key_grid, colours


def _stable_species_colour(key: str) -> tuple[int, int, int]:
    """Deterministic saturated colour from species key."""
    h = 0
    for ch in key:
        h = (h * 131 + ord(ch)) & 0xFFFFFFFF
    hue = (h % 360) / 360.0
    sat, val = 0.72, 0.88
    return _hsv_to_rgb(hue, sat, val)


def _hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    i = int(h * 6.0) % 6
    f = h * 6.0 - int(h * 6.0)
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)
    if i == 0:
        r, g, b = v, t, p
    elif i == 1:
        r, g, b = q, v, p
    elif i == 2:
        r, g, b = p, v, t
    elif i == 3:
        r, g, b = p, q, v
    elif i == 4:
        r, g, b = t, p, v
    else:
        r, g, b = v, p, q
    return int(r * 255), int(g * 255), int(b * 255)


def niche_bearing_species():
    """Wild flora that define at least one environmental niche axis."""
    from wild_species import WILD_SPECIES

    return [
        s
        for s in WILD_SPECIES
        if any(
            (
                s.temperature_niche,
                s.moisture_niche,
                s.fertility_niche,
                s.disturbance_niche,
                s.texture_niche,
            )
        )
    ]

