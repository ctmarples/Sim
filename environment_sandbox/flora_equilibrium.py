"""Equilibrium flora composition — shared by map estimates and live World.

Per-cell soft occupancy (live map):

* Hard filters: terrain list, near_feature, moisture/texture gates
* Soft fill: ``FLORA_TILE_CAP × pass_scale`` chance a cell slot plants
* Species odds: ``spawn_peak × spawn_activity × FLORA_SPECIES_WEIGHT ×
  suitability × activity_profile`` among eligible species
* Up to ``MAX_WILD_PER_CELL`` independent slot draws per cell

Expected plants per terrain tile ≈ ``tile_cap × pass_scale × MAX_WILD_PER_CELL``
when every cell has at least one eligible species.

Legacy helpers ``allocate_capacity`` / ``composition_*`` remain for approximate
map-resource estimates.
"""

from __future__ import annotations

import random
from typing import Sequence

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
    """Expected plant slots on ``tiles`` at a soft tile-cap fraction."""
    fraction = (
        float(WILD_PLANT_MAX_FRACTION)
        if tile_fraction is None
        else max(0.0, min(1.0, float(tile_fraction)))
    )
    return float(tiles) * fraction * float(MAX_WILD_PER_CELL)


def cell_species_weight(
    species: WildSpeciesDef,
    *,
    suitability: float,
    day: float,
    species_weight: float = 1.0,
) -> float:
    """Relative placement weight for one eligible species on one cell."""
    peak = float(species.spawn_peak)
    if peak <= 0.0 or suitability <= 0.0:
        return 0.0
    seasonal = max(0.0, activity_at_day(species, day))
    if seasonal <= 0.0:
        return 0.0
    return (
        peak
        * float(species.spawn_activity)
        * max(0.0, float(species_weight))
        * max(0.0, float(suitability))
        * seasonal
    )


def draw_cell_plants(
    weighted: Sequence[tuple[str, float]],
    *,
    tile_cap: float,
    fill_scale: float = 1.0,
    rng: random.Random | None = None,
    max_per_cell: int = MAX_WILD_PER_CELL,
) -> list[str]:
    """Soft-cap categorical draws: empty vs weighted species, up to max slots.

    Each slot independently:
    * with probability ``1 - p_occupy`` → nothing
    * else pick species ``i`` with probability proportional to its weight

    ``p_occupy = clamp(tile_cap × fill_scale, 0, 1)``.
    """
    if not weighted or max_per_cell <= 0:
        return []
    keys: list[str] = []
    weights: list[float] = []
    for key, weight in weighted:
        w = max(0.0, float(weight))
        if w <= 0.0:
            continue
        keys.append(str(key))
        weights.append(w)
    if not keys:
        return []
    occupy = max(0.0, min(1.0, float(tile_cap) * max(0.0, float(fill_scale))))
    if occupy <= 0.0:
        return []
    roller = rng if rng is not None else random
    picked: list[str] = []
    for _ in range(int(max_per_cell)):
        if roller.random() >= occupy:
            continue
        picked.append(roller.choices(keys, weights=weights, k=1)[0])
    return picked


def expected_plants_for_species(
    *,
    tiles: float,
    tile_cap: float,
    fill_scale: float,
    species_weight: float,
    weight_sum: float,
    max_per_cell: int = MAX_WILD_PER_CELL,
) -> float:
    """Expected plant count for one species under the per-cell soft model."""
    if tiles <= 0.0 or weight_sum <= 0.0 or species_weight <= 0.0:
        return 0.0
    occupy = max(0.0, min(1.0, float(tile_cap) * max(0.0, float(fill_scale))))
    share = max(0.0, float(species_weight)) / float(weight_sum)
    return float(tiles) * occupy * float(max_per_cell) * share


def composition_intensity(
    species: WildSpeciesDef,
    *,
    mean_suitability: float,
    species_weight: float = 1.0,
) -> float:
    """Relative intensity for share allocation / estimate weights."""
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
