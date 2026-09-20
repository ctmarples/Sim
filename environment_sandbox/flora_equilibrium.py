"""Equilibrium flora composition — shared by map estimates and live World.

Plant counts for a half-season = capacity × intensity share × activity × fill.

* Capacity: ``tiles × FLORA_TILE_CAP_<terrain> × max_per_cell`` (spawnable area)
* Intensity: ``spawn_peak × spawn_activity × FLORA_SPECIES_WEIGHT × soft_niche``
* Fill: establishment pass scale only (never scales up past capacity)
* Temporal: ``activity_profile`` sampled once per half-season

Species compete for the terrain's tile budget via relative intensity × activity.
Near-tree specialists share the same per-terrain capacity; they only place on
sites that satisfy ``near_feature``.

Live game: each half-season installs one stand atomically (clear + place).
Plants stay until the next half-season install or until picked.
"""

from __future__ import annotations

from wild_species import (
    WILD_PLANT_MAX_FRACTION,
    WildSpeciesDef,
    activity_at_day,
    spawn_probability,
)

# Matches ``subtile_layout`` wild_plant family max_per_cell.
MAX_WILD_PER_CELL: int = 3

# Default establishment effort for full rebuilds (map gen / Respawn flora).
FLORA_ESTABLISHMENT_PASSES: float = 32.0


def wild_plant_capacity(
    tiles: float, *, tile_fraction: float | None = None
) -> float:
    """Max expected wild plants on ``tiles`` given a spawnable-tile fraction."""
    fraction = (
        float(WILD_PLANT_MAX_FRACTION)
        if tile_fraction is None
        else max(0.0, min(1.0, float(tile_fraction)))
    )
    return float(tiles) * fraction * float(MAX_WILD_PER_CELL)


def composition_intensity(
    species: WildSpeciesDef,
    *,
    mean_suitability: float,
    species_weight: float = 1.0,
) -> float:
    """Relative intensity for share allocation (no terrain fill)."""
    if species.spawn_peak <= 0 or mean_suitability <= 0.0:
        return 0.0
    soft = 0.35 + 0.65 * spawn_probability(mean_suitability)
    return (
        float(species.spawn_peak)
        * float(species.spawn_activity)
        * max(0.0, float(species_weight))
        * soft
    )


def composition_weight(
    species: WildSpeciesDef,
    *,
    mean_suitability: float,
    day: float,
    species_weight: float = 1.0,
) -> tuple[float, float]:
    """Return ``(intensity, seasonal_activity)`` for capacity demand."""
    intensity = composition_intensity(
        species, mean_suitability=mean_suitability, species_weight=species_weight
    )
    if intensity <= 0.0:
        return 0.0, 0.0
    return intensity, max(0.0, activity_at_day(species, day))


def allocate_capacity(
    rows: list[tuple[WildSpeciesDef, float, float]],
    capacity: float,
    *,
    terrain_fill: float = 1.0,
) -> list[tuple[WildSpeciesDef, float]]:
    """Allocate plant counts from intensity shares × activity × terrain fill.

    ``rows`` entries are ``(species, intensity, seasonal_activity)``.
    If total demand exceeds capacity, scale down; never scale up.
    """
    if capacity <= 0.0:
        return [(s, 0.0) for s, _i, _a in rows]
    intensity_sum = sum(max(0.0, intensity) for _s, intensity, _a in rows)
    if intensity_sum <= 0.0:
        return [(s, 0.0) for s, _i, _a in rows]
    fill = max(0.0, float(terrain_fill))
    demands: list[tuple[WildSpeciesDef, float]] = []
    total_demand = 0.0
    for species, intensity, seasonal in rows:
        share = max(0.0, intensity) / intensity_sum
        demand = capacity * fill * share * max(0.0, seasonal)
        demands.append((species, demand))
        total_demand += demand
    if total_demand > capacity > 0.0:
        scale = capacity / total_demand
        return [(s, d * scale) for s, d in demands]
    return demands


def pass_fill_scale(passes: float | None = None) -> float:
    """Establishment-pass scale relative to the default 32-pass rebuild."""
    value = float(FLORA_ESTABLISHMENT_PASSES if passes is None else passes)
    return max(0.0, value) / float(FLORA_ESTABLISHMENT_PASSES)
