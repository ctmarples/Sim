"""Soil fertility, weed growth, and slope-based erosion potential."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from balance_config import active_balance
from settings import (
    EROSION_SLOPE_SCALE,
    FERTILITY_FOREST,
    FERTILITY_GRASS,
    FERTILITY_HARVEST_DROP,
    FERTILITY_MEADOW,
    FERTILITY_RIPARIAN,
    FERTILITY_ROCK,
    FERTILITY_SOIL,
    FERTILITY_WATER,
    WEED_GROWTH_RATE,
    WEED_HARVEST_PENALTY,
    WEED_MAX_APPEARANCES_PER_SEASON,
)

if TYPE_CHECKING:
    from world import Cell, TerrainType, World


def _bal(key: str, default: float) -> float:
    try:
        return float(active_balance().get_float(key))
    except Exception:
        return float(default)


def fertility_base_for(terrain: TerrainType) -> float:
    """Starting fertility 0–1 for a terrain type."""
    from world import TerrainType as T
    from developer_tools.terrain_editor import terrain_value

    authored = terrain_value(terrain, "fertility")

    return authored


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def overlay_fertility(cell: Cell) -> float:
    """Fertility shown on the overlay: urban / water / rock read as 0."""
    from world import TerrainType, is_water_terrain

    if is_water_terrain(cell.terrain) or cell.terrain == TerrainType.ROCK:
        return 0.0
    if cell.terrain == TerrainType.URBAN:
        return 0.0
    # Paths are overlays — show the underlying soil fertility.
    return clamp01(getattr(cell, "fertility", 0.0))


def init_cell_fertility(cell: Cell) -> None:
    cell.fertility = clamp01(fertility_base_for(cell.terrain))
    cell.weeds = 0.0


def apply_terrain_fertility(cell: Cell, *, reset: bool = True) -> None:
    """After a terrain paint. ``reset`` writes the new terrain's base."""
    base = fertility_base_for(cell.terrain)
    if reset or base <= 0.0:
        cell.fertility = clamp01(base)
    else:
        cell.fertility = clamp01(min(float(getattr(cell, "fertility", base)), base))
    if cell.feature.name != "CROP_HERB":
        cell.weeds = 0.0


def cap_fertility_for_soil(cell: Cell) -> None:
    """Ploughing converts to soil: keep depletion, never above soil base."""
    from world import TerrainType

    cap = fertility_base_for(TerrainType.SOIL)
    cell.fertility = clamp01(min(float(getattr(cell, "fertility", cap)), cap))
    cell.weeds = 0.0


def drop_fertility_on_harvest(cell: Cell) -> None:
    drop = _bal("FERTILITY_HARVEST_DROP", FERTILITY_HARVEST_DROP)
    cell.fertility = clamp01(float(getattr(cell, "fertility", 0.0)) - drop)
    cell.weeds = 0.0


def weed_yield_multiplier(weeds: float) -> float:
    """1.0 when clean; at full weeds yield is reduced by WEED_HARVEST_PENALTY."""
    pen = max(0.0, min(1.0, _bal("WEED_HARVEST_PENALTY", WEED_HARVEST_PENALTY)))
    return clamp01(1.0 - clamp01(weeds) * pen)


def grow_weeds_on_cell(cell: Cell, ticks: int, *, season=None) -> None:
    """Higher fertility → weeds fill in faster on a planted crop square.

    Winter: no new growth (existing cover stays until hoed).
    Each square may start a weed wave at most WEED_MAX_APPEARANCES_PER_SEASON
    times per season; after hoeing, weeds do not return until the next season.
    """
    from seasons import Season, TICKS_PER_DAY
    from world import FeatureType

    if ticks <= 0 or cell.feature != FeatureType.CROP_HERB:
        return
    if season == Season.WINTER:
        return
    max_app = max(
        0, int(_bal("WEED_MAX_APPEARANCES_PER_SEASON", WEED_MAX_APPEARANCES_PER_SEASON))
    )
    if max_app <= 0:
        return
    appearances = int(getattr(cell, "weed_appearances", 0) or 0)
    weeds = clamp01(float(getattr(cell, "weeds", 0.0)))
    if weeds <= 1e-6:
        if appearances >= max_app:
            return
        cell.weed_appearances = appearances + 1
    elif appearances <= 0:
        # Legacy / mid-wave cover: count as this season's appearance.
        cell.weed_appearances = 1
    rate = max(0.0, _bal("WEED_GROWTH_RATE", WEED_GROWTH_RATE))
    fert = clamp01(getattr(cell, "fertility", 0.0))
    day_frac = float(ticks) / float(max(1, TICKS_PER_DAY))
    suppression = clamp01(float(getattr(cell, "weed_suppression", 0.0) or 0.0))
    cell.weeds = clamp01(weeds + fert * rate * day_frac * (1.0 - suppression))


def reset_seasonal_weed_appearances(world: World) -> None:
    """Clear per-square appearance counters at season change (cover stays)."""
    for y in range(world.rows):
        for x in range(world.cols):
            cell = world.get_cell(x, y)
            if cell is not None:
                cell.weed_appearances = 0


def cell_slope(world: World, x: int, y: int) -> float:
    """Gradient magnitude from the four height corners of cell (x, y)."""
    world.ensure_height_corners()
    if not (0 <= x < world.cols and 0 <= y < world.rows):
        return 0.0
    c = world.height_corners
    nw, ne = c[y][x], c[y][x + 1]
    sw, se = c[y + 1][x], c[y + 1][x + 1]
    gx = ((ne + se) - (nw + sw)) * 0.5
    gy = ((sw + se) - (nw + ne)) * 0.5
    return math.hypot(gx, gy)


def bake_erosion_grid(world: World) -> list[list[float]]:
    """Prebake 0–1 erosion potential from height-map slope."""
    scale = max(0.01, _bal("EROSION_SLOPE_SCALE", EROSION_SLOPE_SCALE))
    return [
        [min(1.0, cell_slope(world, x, y) / scale) for x in range(world.cols)]
        for y in range(world.rows)
    ]
