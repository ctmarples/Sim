"""Probability-based map resource estimates for forage / seasonality balance.

Balance model (same as live ``World.establish_flora_equilibrium``):

* **Seasonal probability** — ``activity_profile`` (via ``activity_at_day``)
* **Spatial probability** — terrain ecology × plant niches
* **Intensity** — ``spawn_peak × spawn_activity × FLORA_SPECIES_WEIGHT × soft niche``
* **Composition** — per-cell soft occupancy: each tile slot plants with
  probability ``FLORA_TILE_CAP``, then picks a species ∝ those weights × season
* **Capacity** — expected plants ≈ ``tiles × FLORA_TILE_CAP × MAX_WILD_PER_CELL``
  when eligible species exist (soft mottling, not a global dump into niches)

Live ``spawn_rise``/``spawn_fall`` envelopes are ignored here.

Usage::

    python -m map_resource_estimate
    python -m map_resource_estimate --climate arid --half 4
    from map_resource_estimate import estimate_map_resources, format_report
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass, field
from typing import Iterable

from random_map_generator import CLIMATES, MapOptions, TERRAINS
from seasons import (
    HALF_SEASON_DAYS,
    N_HALF_SEASONS,
    ambient_temperature_c,
    half_season_name,
)
from flora_equilibrium import (
    MAX_WILD_PER_CELL,
    FLORA_ESTABLISHMENT_PASSES,
    composition_weight,
    expected_plants_for_species,
    wild_plant_capacity,
)
from wild_species import (
    WILD_BY_KEY,
    WILD_PLANT_MAX_FRACTION,
    WILD_SPECIES,
    WildSpeciesDef,
    activity_at_day,
    environment_allows_seasonal_flora,
    normalize_temperature_c,
    spawn_probability,
    species_environment_suitability,
    species_fruiting,
    species_spawn_rate,
)

# ---------------------------------------------------------------------------
# Generator constants (mirror random_map_generator.apply_to_world)
# ---------------------------------------------------------------------------
FOREST_TREE_CHANCE: float = 0.68
ROCK_DEPOSIT_CHANCE: float = 0.30
ROCK_DEPOSIT_MEAN: float = 5.0  # midpoint of randint(2, 8)
TREE_COMPANION_CHANCE: float = 0.32
TREE_COMPANION_MUSHROOM_SHARE: float = 0.65
FOREST_FLOOR_NEAR_CHANCE: float = 0.08
FOREST_FLOOR_NEAR_MUSHROOM_SHARE: float = 0.70
STARTER_WOOD_BUSHES: float = 7.0
STARTER_SMALL_ROCKS: float = 6.0
# Mean saplings per tree cell: E[randint(0,2)] = 1.0
SAPLINGS_PER_TREE: float = 1.0

# Expected harvestable units per plant: mean of uniform [UNIT_YIELD_MIN, UNIT_YIELD_MAX].
# Catalogue ``yield_amount`` remains the authored deposit; balance estimates use this
# randint-style range unless a species override is supplied later.
UNIT_YIELD_MIN: int = 1
UNIT_YIELD_MAX: int = 3


def mean_unit_yield(lo: int = UNIT_YIELD_MIN, hi: int = UNIT_YIELD_MAX) -> float:
    a, b = sorted((int(lo), int(hi)))
    return (a + b) / 2.0


def patch_plant_multiplier(species) -> float:
    """Expected plants from one successful wild-crop seed (centre + patch extras)."""
    lo, hi = species.patch_extras
    if int(hi) <= 0:
        return 1.0
    # Neighbour extras roll randint(lo,hi) then each candidate succeeds ~55%.
    return 1.0 + 0.55 * mean_unit_yield(int(lo), int(hi))


# Default low-disturbance wild landscape (settlement footprint is tiny).
DEFAULT_DISTURBANCE: float = 0.12
DEFAULT_SOIL_TEXTURE: float = 0.45

# Terrain name as used in MapOptions.mix → World TerrainType / wild catalogue.
_MIX_TO_TERRAIN: dict[str, str] = {
    "water": "WATER",
    "grass": "GRASS",
    "meadow": "MEADOW",
    "soil": "SOIL",
    "forest": "FOREST_FLOOR",
    "rock": "ROCK",
    "riparian": "RIPARIAN",
}


@dataclass(frozen=True)
class TerrainCounts:
    """Expected tile counts after mix claim + riparian bank paint."""

    width: int
    height: int
    counts: dict[str, float]  # OUTPUT terrain keys: water, grass, …, riparian

    @property
    def total(self) -> int:
        return max(1, int(self.width) * int(self.height))


@dataclass(frozen=True)
class SpeciesHalfSeason:
    """One flora species at one half-season sample day."""

    species_key: str
    label: str
    resource_key: str
    feature: str
    half_season: int
    day: float
    activity: float
    spawn_envelope: float
    mean_suitability: float
    establishment_ok: bool
    expected_plants: float
    expected_stock: float  # forageable units (0 if not fruiting / no resource)
    notes: str = ""


@dataclass(frozen=True)
class StaticDeposits:
    """Non-seasonal generator deposits (trees, rocks, companions, starters)."""

    trees: float
    saplings: float
    logs_equiv: float  # expected mature tree wood deposits
    rock_cells: float
    rock_deposit: float
    companion_mushrooms: float
    companion_wood: float
    starter_wood: float
    starter_rock: float


@dataclass(frozen=True)
class WildlifeSeedEstimate:
    deer: float
    boar: float
    rabbit_sites: float
    vole_sites: float
    frog_sites: float
    bee_sites: float


@dataclass
class MapResourceEstimate:
    """Full theoretical map resource snapshot."""

    options: MapOptions
    terrain: TerrainCounts
    static: StaticDeposits
    wildlife: WildlifeSeedEstimate
    half_seasons: list[list[SpeciesHalfSeason]] = field(default_factory=list)

    def by_resource(self, half: int) -> dict[str, float]:
        """Sum expected forage stock by resource_key for one half-season."""
        h = max(0, min(N_HALF_SEASONS - 1, int(half)))
        totals: dict[str, float] = {}
        for row in self.half_seasons[h]:
            if not row.resource_key or row.expected_stock <= 0:
                continue
            totals[row.resource_key] = totals.get(row.resource_key, 0.0) + row.expected_stock
        # Static / companion wood & mushrooms available year-round-ish
        totals["wood"] = totals.get("wood", 0.0) + self.static.companion_wood + self.static.starter_wood
        totals["mushrooms"] = totals.get("mushrooms", 0.0) + (
            self.static.companion_mushrooms * 4.0  # mushroom yield_amount
        )
        totals["rock"] = totals.get("rock", 0.0) + self.static.rock_deposit + self.static.starter_rock
        totals["logs"] = totals.get("logs", 0.0) + self.static.logs_equiv
        return totals


def half_season_sample_day(half: int) -> float:
    """Midpoint day of half-season ``half`` (0..7)."""
    h = int(half) % N_HALF_SEASONS
    return h * HALF_SEASON_DAYS + HALF_SEASON_DAYS * 0.5


def estimate_terrain_counts(options: MapOptions | None = None) -> TerrainCounts:
    """Exact mix targets + approximate riparian bank conversion.

    Mix claim order matches ``_assign_by_mix``; riparian then consumes a bank
    fringe of grass/meadow/soil/forest around water (compact-lake + river heuristic).
    """
    opt = (options or MapOptions()).normalized()
    n = float(opt.width * opt.height)
    raw = {name: opt.terrain_mix[name] * n for name in TERRAINS}
    # Riparian fringe: ~perimeter of water clumps + river length term.
    water = raw["water"]
    bank = min(
        raw["grass"] + raw["meadow"] + raw["soil"] + raw["forest"],
        3.2 * math.sqrt(max(0.0, water)) + 0.18 * water,
    )
    convertible = ("grass", "meadow", "soil", "forest")
    convertible_total = sum(raw[name] for name in convertible)
    counts = {name: float(raw[name]) for name in TERRAINS}
    counts["riparian"] = 0.0
    if bank > 0 and convertible_total > 0:
        for name in convertible:
            take = bank * (raw[name] / convertible_total)
            counts[name] -= take
            counts["riparian"] += take
    return TerrainCounts(opt.width, opt.height, counts)


def _mean_tree_yield() -> float:
    from trees import TREE_BY_KEY, TREE_SPAWN_WEIGHTS

    total_w = sum(TREE_SPAWN_WEIGHTS.values()) or 1.0
    return sum(
        TREE_SPAWN_WEIGHTS[k] * float(TREE_BY_KEY[k].yield_amount)
        for k in TREE_SPAWN_WEIGHTS
    ) / total_w


def estimate_static_deposits(terrain: TerrainCounts) -> StaticDeposits:
    forest = terrain.counts.get("forest", 0.0)
    rock = terrain.counts.get("rock", 0.0)
    trees = forest * FOREST_TREE_CHANCE
    rock_cells = rock * ROCK_DEPOSIT_CHANCE
    companions = trees * TREE_COMPANION_CHANCE
    # Near-forest empty floor companions (order-of-magnitude: remaining forest tiles).
    floor_empty = max(0.0, forest - trees)
    near = floor_empty * FOREST_FLOOR_NEAR_CHANCE
    mush = companions * TREE_COMPANION_MUSHROOM_SHARE + near * FOREST_FLOOR_NEAR_MUSHROOM_SHARE
    wood = companions * (1.0 - TREE_COMPANION_MUSHROOM_SHARE) + near * (
        1.0 - FOREST_FLOOR_NEAR_MUSHROOM_SHARE
    )
    from resource_balance import WOOD_BUSH_YIELD

    return StaticDeposits(
        trees=trees,
        saplings=trees * SAPLINGS_PER_TREE,
        logs_equiv=trees * _mean_tree_yield(),
        rock_cells=rock_cells,
        rock_deposit=rock_cells * ROCK_DEPOSIT_MEAN,
        companion_mushrooms=mush,
        companion_wood=wood * float(WOOD_BUSH_YIELD),
        starter_wood=STARTER_WOOD_BUSHES * float(WOOD_BUSH_YIELD),
        starter_rock=STARTER_SMALL_ROCKS * 3.0,  # midpoint small rock deposit
    )


def estimate_wildlife_seed() -> WildlifeSeedEstimate:
    from resource_balance import (
        COLONY_SEED_GROUNDS,
        WILDLIFE_SEED_COUNT,
        WILDLIFE_SEED_GROUNDS,
        WILDLIFE_SEED_RABBIT_SITE_BONUS,
        WILDLIFE_SEED_VOLE_SITE_BONUS,
    )

    grounds = float(WILDLIFE_SEED_GROUNDS)
    animals = float(WILDLIFE_SEED_COUNT)
    base = float(COLONY_SEED_GROUNDS)
    return WildlifeSeedEstimate(
        deer=grounds * animals,
        boar=grounds * animals,
        rabbit_sites=base + float(WILDLIFE_SEED_RABBIT_SITE_BONUS),
        vole_sites=base + float(WILDLIFE_SEED_VOLE_SITE_BONUS),
        frog_sites=base,
        bee_sites=base,
    )


def _flora_tile_cap(terrain_key: str) -> float:
    """Fraction of terrain tiles allowed to hold wild flora."""
    from wild_species import WILD_PLANT_MAX_FRACTION

    try:
        from balance_config import active_balance

        return max(
            0.0,
            min(1.0, float(active_balance().get_float(f"FLORA_TILE_CAP_{terrain_key}"))),
        )
    except Exception:
        return float(WILD_PLANT_MAX_FRACTION)


def _flora_species_weight(species_key: str) -> float:
    """Manual pre-competition species weight from balance."""
    try:
        from balance_config import active_balance

        return max(
            0.0, float(active_balance().get_float(f"FLORA_SPECIES_WEIGHT_{species_key}"))
        )
    except Exception:
        return 1.0


def _ecology_centres(terrain_key: str) -> tuple[float, float, float, float]:
    """moisture, fertility, temperature_offset_c, rainfall_multiplier."""
    from developer_tools.terrain_editor import ecology_bands_for

    bands = ecology_bands_for(terrain_key)
    return (
        float(bands["soil_moisture"]["centre"]),
        float(bands["fertility"]["centre"]),
        float(bands["temperature_offset_c"]["centre"]),
        float(bands["rainfall_multiplier"]["centre"]),
    )


def _climate_rain_temp(options: MapOptions) -> tuple[float, float]:
    climate_rain, climate_temp = {
        "temperate": (0.55, 0.52),
        "arid": (0.18, 0.72),
        "tropical": (0.82, 0.82),
        "cold": (0.46, 0.20),
        "continental": (0.42, 0.45),
    }[options.climate]
    rain = max(0.0, min(1.0, (options.rainfall + climate_rain) * 0.5))
    temp = max(0.0, min(1.0, (options.temperature + climate_temp) * 0.5))
    return rain, temp


# °C shift at temperature-bias extremes (0 vs 1) — matches map heat blend strength.
_TEMP_BIAS_SPAN_C: float = 20.0


def _suitability_on_terrain(
    species: WildSpeciesDef,
    terrain_key: str,
    day: float,
    options: MapOptions,
) -> tuple[float, bool]:
    """Mean niche suitability for species on a typical tile of ``terrain_key``."""
    moisture, fertility, temp_off_c, rain_mult = _ecology_centres(terrain_key)
    rain, clim_temp = _climate_rain_temp(options)
    # Same orographic/climate blend idea as generate_map (mean elevation ≈ 0.45).
    elev = 0.45
    moisture = max(0.0, min(1.0, moisture * 0.65 + rain * rain_mult * 0.55 - elev * 0.16))
    ambient_c = (
        ambient_temperature_c(day)
        + temp_off_c
        + (clim_temp - 0.5) * _TEMP_BIAS_SPAN_C
    )
    temp01 = normalize_temperature_c(ambient_c)
    score = species_environment_suitability(
        species,
        temperature=temp01,
        soil_moisture=moisture,
        fertility=fertility,
        disturbance=DEFAULT_DISTURBANCE,
        soil_texture=DEFAULT_SOIL_TEXTURE,
    )
    ok = environment_allows_seasonal_flora(species, score)
    return float(score.combined), ok


def _species_on_terrain(terrain_key: str) -> list[WildSpeciesDef]:
    """Species that may place on this terrain, including near-feature specialists.

    Near-tree species share the terrain capacity (no bonus forest pool); the
    live world only places them on sites that satisfy ``near_feature``.
    """
    return [
        s
        for s in WILD_SPECIES
        if terrain_key in s.terrains and s.spawn_peak > 0
    ]


def _composition_weight(
    species: WildSpeciesDef,
    *,
    terrain_key: str,
    day: float,
    options: MapOptions,
    species_weight: float = 1.0,
) -> tuple[float, float, float, bool]:
    """Factors for capacity demand: intensity (relative) × activity (temporal)."""
    suit, ok = _suitability_on_terrain(species, terrain_key, day, options)
    intensity, seasonal = composition_weight(
        species,
        mean_suitability=suit,
        day=day,
        species_weight=species_weight,
    )
    return intensity, seasonal, suit, ok


def _allocate_capacity(
    rows: list[tuple[WildSpeciesDef, float, float, float, bool]],
    *,
    tiles: float,
    tile_cap: float,
    fill_scale: float,
) -> list[tuple[WildSpeciesDef, float, float, bool]]:
    """Expected plants under the per-cell soft-cap model."""
    weights = [
        (s, max(0.0, intensity) * max(0.0, seasonal), suit, ok)
        for s, intensity, seasonal, suit, ok in rows
    ]
    weight_sum = sum(w for _s, w, _su, _ok in weights)
    out: list[tuple[WildSpeciesDef, float, float, bool]] = []
    for species, weight, suit, ok in weights:
        plants = expected_plants_for_species(
            tiles=tiles,
            tile_cap=tile_cap,
            fill_scale=fill_scale,
            species_weight=weight,
            weight_sum=weight_sum,
        )
        out.append((species, plants, suit, ok))
    return out


def estimate_flora_year(
    terrain: TerrainCounts,
    options: MapOptions | None = None,
    *,
    passes: float | None = None,
) -> list[list[SpeciesHalfSeason]]:
    """Per half-season flora via per-cell soft occupancy expectations.

    * Soft fill: ``FLORA_TILE_CAP × passes/32`` chance per cell slot
    * Species odds: peak × activity × species weight × soft niche × season
    * Up to ``MAX_WILD_PER_CELL`` slots per cell
    """
    opt = (options or MapOptions()).normalized()
    pass_scale = float(FLORA_ESTABLISHMENT_PASSES if passes is None else passes) / float(
        FLORA_ESTABLISHMENT_PASSES
    )
    seasons: list[list[SpeciesHalfSeason]] = [[] for _ in range(N_HALF_SEASONS)]

    berries = [s for s in WILD_SPECIES if s.feature == "BERRY_BUSH" and s.initial_count > 0]
    plant_day = half_season_sample_day(0)

    for half in range(N_HALF_SEASONS):
        day = half_season_sample_day(half)
        rows: list[SpeciesHalfSeason] = []

        for species in berries:
            suit_plant, _ok_plant = _suitability_on_terrain(species, "GRASS", plant_day, opt)
            plants = float(species.initial_count) if suit_plant > 0.05 else 0.0
            suit, ok = _suitability_on_terrain(species, "GRASS", day, opt)
            rows.append(
                _species_row(
                    species,
                    half=half,
                    day=day,
                    suitability=suit if suit > 0 else suit_plant,
                    ok=ok,
                    plants=plants,
                    note="initial_berry",
                    forageable=True,
                )
            )

        for mix_name, tiles in terrain.counts.items():
            terrain_key = _MIX_TO_TERRAIN.get(mix_name)
            if terrain_key is None or tiles <= 0:
                continue
            if terrain_key in ("WATER", "RIVER", "ROCK", "URBAN", "PATH"):
                continue
            candidates = _species_on_terrain(terrain_key)
            if not candidates:
                continue
            tile_cap = _flora_tile_cap(terrain_key)
            claims: list[tuple[WildSpeciesDef, float, float, float, bool]] = []
            for species in candidates:
                intensity, seasonal_spatial, suit, ok = _composition_weight(
                    species,
                    terrain_key=terrain_key,
                    day=day,
                    options=opt,
                    species_weight=_flora_species_weight(species.key),
                )
                claims.append((species, intensity, seasonal_spatial, suit, ok))
            for species, plants, suit, ok in _allocate_capacity(
                claims,
                tiles=tiles,
                tile_cap=tile_cap,
                fill_scale=pass_scale,
            ):
                if plants < 1e-9:
                    continue
                rows.append(
                    _species_row(
                        species,
                        half=half,
                        day=day,
                        suitability=suit,
                        ok=ok,
                        plants=plants,
                        note=f"on {terrain_key}",
                        forageable=True,
                    )
                )

        seasons[half] = rows

    return seasons


def estimate_flora_half_season(
    terrain: TerrainCounts,
    half: int,
    options: MapOptions | None = None,
) -> list[SpeciesHalfSeason]:
    """Equilibrium stock for one half-season."""
    year = estimate_flora_year(terrain, options)
    return year[int(half) % N_HALF_SEASONS]


def _species_row(
    species: WildSpeciesDef,
    *,
    half: int,
    day: float,
    suitability: float,
    ok: bool,
    plants: float,
    note: str,
    forageable: bool = False,
    unit_lo: int | None = None,
    unit_hi: int | None = None,
) -> SpeciesHalfSeason:
    stock = 0.0
    resource = species.resource_key or ""
    plant_sites = float(plants)
    harvest_plants = plant_sites
    can_forage = forageable or ok
    if resource and harvest_plants > 0 and can_forage:
        lo = UNIT_YIELD_MIN if unit_lo is None else int(unit_lo)
        hi = UNIT_YIELD_MAX if unit_hi is None else int(unit_hi)
        unit_mean = mean_unit_yield(lo, hi)
        if species.fruiting:
            fruit_env = 0.0
            if species_fruiting(species, day):
                from wild_species import _envelope

                fruit_env = _envelope(day, species.fruit_rise, species.fruit_fall)
            stock = harvest_plants * unit_mean * fruit_env
        elif species.spawn_peak > 0 or species.initial_fraction > 0 or species.initial_count > 0:
            stock = harvest_plants * unit_mean
    env = (
        species_spawn_rate(species, day) / max(1e-9, species.spawn_peak)
        if species.spawn_peak > 0
        else 0.0
    )
    return SpeciesHalfSeason(
        species_key=species.key,
        label=species.label,
        resource_key=resource,
        feature=species.feature,
        half_season=half,
        day=day,
        activity=activity_at_day(species, day),
        spawn_envelope=env,
        mean_suitability=suitability,
        establishment_ok=ok,
        expected_plants=plant_sites,
        expected_stock=stock,
        notes=note,
    )


def estimate_map_resources(
    options: MapOptions | None = None,
    *,
    halves: Iterable[int] | None = None,
) -> MapResourceEstimate:
    """Compute static deposits + flora expectations for each half-season."""
    opt = (options or MapOptions()).normalized()
    terrain = estimate_terrain_counts(opt)
    static = estimate_static_deposits(terrain)
    wildlife = estimate_wildlife_seed()
    year = estimate_flora_year(terrain, opt)
    half_list = list(range(N_HALF_SEASONS) if halves is None else halves)
    seasons: list[list[SpeciesHalfSeason]] = [[] for _ in range(N_HALF_SEASONS)]
    for h in half_list:
        hi = int(h) % N_HALF_SEASONS
        seasons[hi] = year[hi]
    return MapResourceEstimate(
        options=opt,
        terrain=terrain,
        static=static,
        wildlife=wildlife,
        half_seasons=seasons,
    )


def format_report(
    estimate: MapResourceEstimate,
    *,
    half: int | None = None,
    top_n: int = 24,
) -> str:
    """Human-readable balance table."""
    opt = estimate.options
    lines: list[str] = []
    lines.append("=== Theoretical map resource estimate ===")
    lines.append(
        f"size {opt.width}×{opt.height}  climate={opt.climate}  "
        f"composition={opt.composition}  rain={opt.rainfall:.2f} temp={opt.temperature:.2f}"
    )
    lines.append("terrain mix (expected tiles):")
    for name in (*TERRAINS, "riparian"):
        n = estimate.terrain.counts.get(name, 0.0)
        lines.append(f"  {name:10} {n:8.1f}  ({100.0 * n / estimate.terrain.total:5.1f}%)")
    st = estimate.static
    lines.append(
        f"static: trees≈{st.trees:.0f}  saplings≈{st.saplings:.0f}  "
        f"logs≈{st.logs_equiv:.0f}  rock≈{st.rock_deposit:.0f}  "
        f"companion mush≈{st.companion_mushrooms:.0f} wood≈{st.companion_wood:.0f}"
    )
    w = estimate.wildlife
    lines.append(
        f"wildlife seed: deer≈{w.deer:.0f} boar≈{w.boar:.0f}  "
        f"colonies rabbit/vole/frog/bee "
        f"{w.rabbit_sites:.0f}/{w.vole_sites:.0f}/{w.frog_sites:.0f}/{w.bee_sites:.0f}"
    )

    halves = [half] if half is not None else list(range(N_HALF_SEASONS))
    for h in halves:
        hi = int(h) % N_HALF_SEASONS
        day = half_season_sample_day(hi)
        lines.append("")
        lines.append(
            f"--- {half_season_name(hi)} (day {day:.0f})  ambient {ambient_temperature_c(day):.1f}°C ---"
        )
        by_res = estimate.by_resource(hi)
        ranked = sorted(by_res.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]
        lines.append(f"{'resource':22} {'stock':>10}")
        for key, stock in ranked:
            if stock < 0.05:
                continue
            lines.append(f"{key:22} {stock:10.1f}")
        species_rows = sorted(
            estimate.half_seasons[hi],
            key=lambda r: (-r.expected_plants, r.species_key),
        )[:12]
        if species_rows:
            lines.append(f"{'species':18} {'plants':>8} {'stock':>8} {'act':>5} {'suit':>5}")
            for row in species_rows:
                if row.expected_plants < 0.05 and row.expected_stock < 0.05:
                    continue
                lines.append(
                    f"{row.species_key:18} {row.expected_plants:8.1f} "
                    f"{row.expected_stock:8.1f} {row.activity:5.2f} {row.mean_suitability:5.2f}"
                )
    return "\n".join(lines)


def resource_matrix(estimate: MapResourceEstimate) -> dict[str, list[float]]:
    """resource_key → stock for each of 8 half-seasons (for CSV / charts)."""
    keys: set[str] = set()
    per_half = [estimate.by_resource(h) for h in range(N_HALF_SEASONS)]
    for d in per_half:
        keys.update(d)
    return {key: [float(d.get(key, 0.0)) for d in per_half] for key in sorted(keys)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--width", type=int, default=96)
    parser.add_argument("--height", type=int, default=72)
    parser.add_argument("--climate", choices=CLIMATES, default="temperate")
    parser.add_argument("--composition", default="valley")
    parser.add_argument("--rainfall", type=float, default=0.55)
    parser.add_argument("--temperature", type=float, default=0.5)
    parser.add_argument(
        "--half",
        type=int,
        default=None,
        help="Show only this half-season 0..7 (default: all)",
    )
    parser.add_argument("--csv", action="store_true", help="Print resource×half-season CSV")
    args = parser.parse_args(argv)

    options = MapOptions(
        width=args.width,
        height=args.height,
        climate=args.climate,
        composition=args.composition,
        rainfall=args.rainfall,
        temperature=args.temperature,
    )
    estimate = estimate_map_resources(options)
    if args.csv:
        matrix = resource_matrix(estimate)
        header = ["resource", *[half_season_name(h).replace(" ", "_") for h in range(N_HALF_SEASONS)]]
        print(",".join(header))
        for key, values in matrix.items():
            print(",".join([key, *[f"{v:.2f}" for v in values]]))
    else:
        print(format_report(estimate, half=args.half))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
