"""Cyclic environmental layers and production modifiers.

Overlay / ecology maps that affect gameplay are sampled on a fixed calendar
cadence (start + midpoint of each season → 8 updates per year). Between
samples the year-average grids stay stable so farms and other systems can
read a consistent modifier.

Live display overlays (habitat diversity, tree density, etc.) remain in
``indicators.py`` and recompute every tick while active. Sampled layers:
biodiversity, floral resources, pollination coverage, and derived pest control.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from collections import deque
import math
from typing import Iterable

from indicators import (
    BIODIVERSITY_SAMPLES_PER_YEAR,
    average_grids,
    biodiversity_snapshot,
    floral_resources_snapshot,
    pollination_coverage_grid,
)
from resource_balance import (
    POLLINATOR_BASE_RADIUS,
    POLLINATOR_BASE_STRENGTH,
    POLLINATOR_RADIUS_PER_LEVEL,
    POLLINATOR_STRENGTH_PER_LEVEL,
)
from seasons import DAYS_PER_SEASON, day_in_season
from settings import (
    CROP_HEALTH_MAX_DROP,
    CROP_HEALTH_MIN,
    PEST_CONTROL_MULT_HIGH,
    PEST_CONTROL_MULT_LOW,
    PEST_CONTROL_MULT_MID,
    PEST_CONTROL_RICHNESS_HIGH,
    PEST_CONTROL_RICHNESS_LOW,
    PEST_CONTROL_RICHNESS_MID,
    POLLINATION_YIELD_HIGH,
    POLLINATION_YIELD_LOW,
)
from world import World

ENV_SAMPLES_PER_YEAR: int = BIODIVERSITY_SAMPLES_PER_YEAR


class EnvLayer(Enum):
    """Stable cyclic layers used for production modifiers / overlays."""

    BIODIVERSITY = auto()
    PEST_CONTROL = auto()
    FLORAL_RESOURCES = auto()
    POLLINATION = auto()
    SOIL_MOISTURE = auto()
    TEMPERATURE = auto()
    RAINFALL = auto()


# Seasonal rainfall / evapotranspiration balance, indexed by Season.name.
# Spring and autumn recharge soil; summer drying and winter freeze reduce the
# amount available to plants.
SEASON_MOISTURE: dict[str, float] = {
    "SPRING": 0.16,
    "SUMMER": -0.18,
    "AUTUMN": 0.12,
    "WINTER": -0.04,
}

# Groundwater reach and peak boost (was 4 cells / +0.30).
WATER_MOISTURE_RADIUS: float = 8.0
WATER_MOISTURE_BOOST: float = 0.48
# Daily rain → soil recharge strength (was 0.34).
RAIN_TO_MOISTURE_GAIN: float = 0.55


def _moisture_cell_noise(seed: int, x: int, y: int) -> float:
    """Deterministic ±1 noise for within-terrain moisture mottling."""
    h = ((int(seed) ^ 0x50115A) + x * 374761393 + y * 668265263) & 0xFFFFFFFF
    u = (h / 0xFFFFFFFF) * 2.0 - 1.0
    h2 = ((int(seed) ^ 0xA11CE) + x * 83492791 + y * 19349663) & 0xFFFFFFFF
    v = (h2 / 0xFFFFFFFF) * 2.0 - 1.0
    return u * 0.65 + v * 0.35


def water_distance_grid(world: World) -> list[list[int]]:
    """4-neighbour BFS distance (in cells) to the nearest water/river tile.

    Reused by live soil-moisture sampling and the Landscape Fields prototype.
    Cells that are themselves water have distance 0. If the map has no water,
    every cell receives ``rows + cols`` (effectively unreachable).
    """
    from world import is_water_terrain

    cols, rows = world.cols, world.rows
    unreachable = rows + cols
    distances = [[unreachable] * cols for _ in range(rows)]
    queue: deque[tuple[int, int]] = deque()
    for y in range(rows):
        for x in range(cols):
            if is_water_terrain(world.cells[y][x].terrain):
                distances[y][x] = 0
                queue.append((x, y))
    while queue:
        x, y = queue.popleft()
        nd = distances[y][x] + 1
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < cols and 0 <= ny < rows and nd < distances[ny][nx]:
                distances[ny][nx] = nd
                queue.append((nx, ny))
    return distances


def soil_moisture_grid(world: World, calendar_day: int) -> list[list[float]]:
    """Build a 0–1 soil-moisture map from terrain, features, and climate.

    Distance to water is calculated across the grid (including rivers and
    lakes). Trees, saplings, reeds, and low vegetation locally retain water.
    The result is deterministic and intentionally sampled with the other
    environmental maps rather than fluctuating every simulation tick.
    """
    from seasons import season_for_day
    from world import FeatureType, TerrainType, is_water_terrain

    from developer_tools.terrain_editor import terrain_band
    bands = {terrain: terrain_band(terrain, "soil_moisture") for terrain in TerrainType}
    distances = water_distance_grid(world)

    retaining = {
        FeatureType.TREE: 0.10,
        FeatureType.SAPLING: 0.05,
        FeatureType.REED: 0.12,
        FeatureType.BERRY_BUSH: 0.05,
        FeatureType.WOOD_BUSH: 0.03,
        FeatureType.WILD_CROP: 0.03,
        FeatureType.CROP_HERB: 0.02,
    }
    climate = SEASON_MOISTURE.get(season_for_day(calendar_day).name, 0.0)
    seed = int(getattr(world, "seed", 0))
    out = _zero_grid(world.rows, world.cols)
    for y in range(world.rows):
        for x in range(world.cols):
            cell = world.cells[y][x]
            if is_water_terrain(cell.terrain):
                out[y][x] = 1.0
                continue
            centre, spread = bands.get(cell.terrain, (0.35, 0.10))
            # Groundwater influence fades across WATER_MOISTURE_RADIUS cells.
            water = max(
                0.0,
                (WATER_MOISTURE_RADIUS - float(distances[y][x])) / WATER_MOISTURE_RADIUS,
            ) * WATER_MOISTURE_BOOST
            feature = retaining.get(cell.feature, 0.0)
            mottling = _moisture_cell_noise(seed, x, y) * float(spread)
            # Clay holds a little more baseline water than sand (soil_texture 0→1).
            texture = float(getattr(cell, "soil_texture", -1.0))
            if texture < 0.0:
                texture = 0.45
            texture_term = (max(0.0, min(1.0, texture)) - 0.5) * 0.14
            out[y][x] = max(
                0.0,
                min(1.0, float(centre) + water + feature + climate + mottling + texture_term),
            )
    return out


def temperature_grid(world: World, calendar_day: int) -> list[list[float]]:
    """Build a local air-temperature map in degrees Celsius.

    Open grassland follows the ambient yearly ``-cos`` curve. Forest cover
    damps that curve (cooler summers, warmer winters), while nearby water has
    thermal inertia and increasingly dominates the microclimate when it forms
    a large local body. Terrain and vegetation add smaller local adjustments.
    """
    from seasons import TEMP_SUMMER_C, TEMP_WINTER_C, YEAR_DAYS, ambient_temperature_c
    from world import FeatureType, TerrainType, is_water_terrain

    ambient = ambient_temperature_c(calendar_day)
    midpoint = 0.5 * (TEMP_WINTER_C + TEMP_SUMMER_C)
    # Same annual -cosine, but water only swings 4 C around a cool mean.
    angle = 2.0 * math.pi * (float(calendar_day) - 42.0) / float(YEAR_DAYS)
    water_temperature = 9.0 + 4.0 * math.cos(angle)
    from developer_tools.terrain_editor import terrain_band
    terrain_bands = {terrain: terrain_band(terrain, "temperature_offset_c") for terrain in TerrainType}
    shade_features = {
        FeatureType.TREE: 1.0,
        FeatureType.SAPLING: 0.45,
        FeatureType.BERRY_BUSH: 0.25,
        FeatureType.REED: 0.20,
    }
    seed = int(getattr(world, "seed", 0))
    out = _zero_grid(world.rows, world.cols)
    for y in range(world.rows):
        for x in range(world.cols):
            cell = world.cells[y][x]
            if is_water_terrain(cell.terrain):
                out[y][x] = water_temperature
                continue

            water_count = 0
            forest_weight = 0.0
            local_count = 0
            for ny in range(max(0, y - 3), min(world.rows, y + 4)):
                for nx in range(max(0, x - 3), min(world.cols, x + 4)):
                    if (nx - x) ** 2 + (ny - y) ** 2 > 9:
                        continue
                    nearby = world.cells[ny][nx]
                    local_count += 1
                    if is_water_terrain(nearby.terrain):
                        water_count += 1
                    if nearby.terrain == TerrainType.FOREST_FLOOR:
                        forest_weight += 0.65
                    forest_weight += shade_features.get(nearby.feature, 0.0)

            water_share = water_count / max(1, local_count)
            forest_share = min(1.0, forest_weight / max(1, local_count * 0.55))
            # A lone tree has a small effect; a continuous forest canopy damps
            # up to 45% of the seasonal departure from the annual midpoint.
            forest_temp = midpoint + (ambient - midpoint) * (1.0 - 0.45 * forest_share)
            centre, spread = terrain_bands.get(cell.terrain, (0.0, 0.0))
            temp = forest_temp + float(centre) + _moisture_cell_noise(seed, x, y) * float(spread)
            # Large water bodies exert more influence than isolated water tiles.
            water_influence = min(0.75, water_share * 2.2)
            temp += (water_temperature - temp) * water_influence
            out[y][x] = temp
    return out


def rainfall_modifier_grid(world: World) -> list[list[float]]:
    """Static-ish local rainfall/throughfall modifier from nearby landscape."""
    from world import FeatureType, TerrainType, is_water_terrain

    out = _zero_grid(world.rows, world.cols)
    for y in range(world.rows):
        for x in range(world.cols):
            water = 0
            canopy = 0.0
            count = 0
            for ny in range(max(0, y - 2), min(world.rows, y + 3)):
                for nx in range(max(0, x - 2), min(world.cols, x + 3)):
                    if (nx - x) ** 2 + (ny - y) ** 2 > 4:
                        continue
                    nearby = world.cells[ny][nx]
                    count += 1
                    water += int(is_water_terrain(nearby.terrain))
                    if nearby.feature == FeatureType.TREE:
                        canopy += 1.0
                    elif nearby.feature == FeatureType.SAPLING:
                        canopy += 0.35
            water_share = water / max(1, count)
            canopy_share = canopy / max(1, count)
            cell = world.cells[y][x]
            modifier = 1.0 + min(0.16, water_share * 0.30)
            # Forest humidity raises local precipitation slightly, while the
            # canopy intercepts some rain before it reaches the ground.
            modifier += min(0.08, canopy_share * 0.12)
            if cell.feature == FeatureType.TREE:
                modifier *= 0.86
            elif cell.feature == FeatureType.SAPLING:
                modifier *= 0.94
            from developer_tools.terrain_editor import terrain_band
            centre, spread = terrain_band(cell.terrain, "rainfall_multiplier")
            rain_mult = float(centre) + _moisture_cell_noise(
                int(getattr(world, "seed", 0)) ^ 0x5A1A, x, y
            ) * float(spread)
            modifier *= max(0.05, rain_mult)
            out[y][x] = max(0.65, min(1.25, modifier))
    return out


def update_soil_moisture_from_rain(
    world: World,
    moisture: list[list[float]],
    rainfall: list[list[float]],
    temperature: list[list[float]],
    calendar_day: int,
) -> list[list[float]]:
    """Advance persistent soil water by one day of rain, drying, and recharge."""
    from world import FeatureType, TerrainType, is_water_terrain

    baseline = soil_moisture_grid(world, calendar_day)
    infiltration = {
        TerrainType.SOIL: 1.0,
        TerrainType.FOREST_FLOOR: 0.92,
        TerrainType.GRASS: 0.82,
        TerrainType.MEADOW: 0.86,
        TerrainType.RIPARIAN: 1.0,
        TerrainType.ROCK: 0.12,
        TerrainType.URBAN: 0.05,
        TerrainType.PATH: 0.25,
    }
    out = _zero_grid(world.rows, world.cols)
    valid = len(moisture) == world.rows and bool(moisture)
    for y in range(world.rows):
        for x in range(world.cols):
            cell = world.cells[y][x]
            if is_water_terrain(cell.terrain):
                out[y][x] = 1.0
                continue
            old = moisture[y][x] if valid and x < len(moisture[y]) else baseline[y][x]
            rain_gain = rainfall[y][x] * RAIN_TO_MOISTURE_GAIN * infiltration.get(cell.terrain, 0.65)
            temp = temperature[y][x] if temperature else 12.0
            heat = max(0.0, min(1.0, (temp + 5.0) / 40.0))
            evaporation = 0.012 + heat * 0.045
            if cell.feature in (FeatureType.TREE, FeatureType.SAPLING):
                evaporation *= 0.72
            # Modest texture effect: sandy soils dry a little faster, clay slower.
            texture = float(getattr(cell, "soil_texture", -1.0))
            if texture < 0.0:
                texture = 0.45
            texture = max(0.0, min(1.0, texture))
            evaporation *= 1.08 - 0.16 * texture
            # Pull toward the water-/terrain-aware baseline a bit faster so rain
            # and proximity reshapes local moisture more visibly.
            recharge = (baseline[y][x] - old) * 0.055
            out[y][x] = max(0.0, min(1.0, old + rain_gain - evaporation + recharge))
    return out


def is_env_sample_day(calendar_day: int) -> bool:
    """True on season start and midpoint (8 times per 112-day year)."""
    d = day_in_season(calendar_day)
    return d == 0 or d == DAYS_PER_SEASON // 2


def env_sample_period(calendar_day: int) -> int:
    """Half-season index 0..7 within the year."""
    from seasons import half_season_index

    return half_season_index(calendar_day)


def _bal_float(key: str, default: float) -> float:
    try:
        from balance_config import active_balance

        return float(active_balance().get_float(key))
    except Exception:
        return float(default)


def _bal_int(key: str, default: int) -> int:
    try:
        from balance_config import active_balance

        return int(active_balance().get_int(key))
    except Exception:
        return int(default)


def crop_health_min() -> float:
    return _bal_float("CROP_HEALTH_MIN", CROP_HEALTH_MIN)


def crop_health_max_drop() -> float:
    return _bal_float("CROP_HEALTH_MAX_DROP", CROP_HEALTH_MAX_DROP)


def pest_control_multiplier(richness: float) -> float:
    """Map neighbourhood species richness to a farm yield multiplier."""
    v = max(0.0, float(richness))
    lo = _bal_float("PEST_CONTROL_RICHNESS_LOW", PEST_CONTROL_RICHNESS_LOW)
    mid = _bal_float("PEST_CONTROL_RICHNESS_MID", PEST_CONTROL_RICHNESS_MID)
    hi = _bal_float("PEST_CONTROL_RICHNESS_HIGH", PEST_CONTROL_RICHNESS_HIGH)
    m_lo = _bal_float("PEST_CONTROL_MULT_LOW", PEST_CONTROL_MULT_LOW)
    m_mid = _bal_float("PEST_CONTROL_MULT_MID", PEST_CONTROL_MULT_MID)
    m_hi = _bal_float("PEST_CONTROL_MULT_HIGH", PEST_CONTROL_MULT_HIGH)
    if mid <= lo:
        mid = lo + 0.01
    if hi <= mid:
        hi = mid + 0.01
    if v <= lo:
        t = v / lo if lo > 0 else 1.0
        return m_lo * (0.85 + 0.15 * t)
    if v <= mid:
        t = (v - lo) / (mid - lo)
        return m_lo + (m_mid - m_lo) * t
    if v <= hi:
        t = (v - mid) / (hi - mid)
        return m_mid + (m_hi - m_mid) * t
    return m_hi


def crop_health_cap_from_pest_control(pest_control: float) -> float:
    """Environmental health target from pest-control pressure.

    Full health when pest control ≥ mid. Below that, scales gently down to
    the health floor at/under MULT_LOW — cleared fields stay usable.
    """
    m_lo = _bal_float("PEST_CONTROL_MULT_LOW", PEST_CONTROL_MULT_LOW)
    m_mid = _bal_float("PEST_CONTROL_MULT_MID", PEST_CONTROL_MULT_MID)
    hmin = crop_health_min()
    if pest_control >= m_mid:
        return 1.0
    if pest_control <= m_lo:
        return hmin
    span = m_mid - m_lo
    t = (pest_control - m_lo) / span if span > 0 else 1.0
    return hmin + (1.0 - hmin) * t


def pollination_yield_multiplier(coverage: float) -> float:
    """Map nest coverage 0–1 to a yield multiplier."""
    t = max(0.0, min(1.0, float(coverage)))
    lo = _bal_float("POLLINATION_YIELD_LOW", POLLINATION_YIELD_LOW)
    hi = _bal_float("POLLINATION_YIELD_HIGH", POLLINATION_YIELD_HIGH)
    return lo + (hi - lo) * t


def average_cells(
    grid: list[list[float]], cells: Iterable[tuple[int, int]]
) -> float:
    """Mean grid value over ``cells``; 0.0 if empty / out of bounds."""
    total = 0.0
    n = 0
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    for x, y in cells:
        if 0 <= y < rows and 0 <= x < cols:
            total += float(grid[y][x])
            n += 1
    if n <= 0:
        return 0.0
    return total / n


def _zero_grid(rows: int, cols: int) -> list[list[float]]:
    return [[0.0] * cols for _ in range(rows)]


def _trim_samples(samples: list, limit: int) -> None:
    while len(samples) > limit:
        samples.pop(0)


@dataclass
class EnvMaps:
    """Year-stable environmental grids updated on the 8×/year sample cadence."""

    rows: int
    cols: int
    biodiversity_samples: list[list[list[float]]] = field(default_factory=list)
    floral_samples: list[list[list[float]]] = field(default_factory=list)
    biodiversity: list[list[float]] = field(default_factory=list)
    pest_control: list[list[float]] = field(default_factory=list)
    floral_resources: list[list[float]] = field(default_factory=list)
    pollination: list[list[float]] = field(default_factory=list)
    erosion: list[list[float]] = field(default_factory=list)
    soil_moisture: list[list[float]] = field(default_factory=list)
    temperature: list[list[float]] = field(default_factory=list)
    rainfall_modifiers: list[list[float]] = field(default_factory=list)
    rainfall: list[list[float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.biodiversity:
            self.biodiversity = _zero_grid(self.rows, self.cols)
        if not self.pest_control:
            self.pest_control = _zero_grid(self.rows, self.cols)
        if not self.floral_resources:
            self.floral_resources = _zero_grid(self.rows, self.cols)
        if not self.pollination:
            self.pollination = _zero_grid(self.rows, self.cols)
        if not self.erosion:
            self.erosion = _zero_grid(self.rows, self.cols)
        if not self.soil_moisture:
            self.soil_moisture = _zero_grid(self.rows, self.cols)
        if not self.temperature:
            self.temperature = _zero_grid(self.rows, self.cols)
        if not self.rainfall_modifiers:
            self.rainfall_modifiers = _zero_grid(self.rows, self.cols)
        if not self.rainfall:
            self.rainfall = _zero_grid(self.rows, self.cols)

    @classmethod
    def blank(cls, rows: int, cols: int) -> EnvMaps:
        return cls(rows=rows, cols=cols)

    def resize(self, rows: int, cols: int) -> None:
        self.rows = rows
        self.cols = cols
        self.biodiversity_samples.clear()
        self.floral_samples.clear()
        self.biodiversity = _zero_grid(rows, cols)
        self.pest_control = _zero_grid(rows, cols)
        self.floral_resources = _zero_grid(rows, cols)
        self.pollination = _zero_grid(rows, cols)
        self.erosion = _zero_grid(rows, cols)
        self.soil_moisture = _zero_grid(rows, cols)
        self.temperature = _zero_grid(rows, cols)
        self.rainfall_modifiers = _zero_grid(rows, cols)
        self.rainfall = _zero_grid(rows, cols)

    def layer_grid(self, layer: EnvLayer) -> list[list[float]]:
        if layer == EnvLayer.BIODIVERSITY:
            return self.biodiversity
        if layer == EnvLayer.PEST_CONTROL:
            return self.pest_control
        if layer == EnvLayer.FLORAL_RESOURCES:
            return self.floral_resources
        if layer == EnvLayer.POLLINATION:
            return self.pollination
        if layer == EnvLayer.SOIL_MOISTURE:
            return self.soil_moisture
        if layer == EnvLayer.TEMPERATURE:
            return self.temperature
        if layer == EnvLayer.RAINFALL:
            return self.rainfall
        return self.biodiversity

    def value_at(self, layer: EnvLayer, x: int, y: int) -> float:
        grid = self.layer_grid(layer)
        if not (0 <= y < len(grid) and 0 <= x < len(grid[y])):
            return 0.0
        return float(grid[y][x])

    def average_over(
        self, layer: EnvLayer, cells: Iterable[tuple[int, int]]
    ) -> float:
        return average_cells(self.layer_grid(layer), cells)

    def _rebuild_pest_control(self) -> None:
        self.pest_control = [
            [pest_control_multiplier(v) for v in row] for row in self.biodiversity
        ]

    def sample(
        self,
        world: World,
        *,
        deer_positions: Iterable[tuple[int, int]],
        boar_positions: Iterable[tuple[int, int]],
        fish_positions: Iterable[tuple[int, int, str]],
        bee_positions: Iterable[tuple[int, int]] = (),
        rabbit_positions: Iterable[tuple[int, int]] = (),
        wolf_positions: Iterable[tuple[int, int]] = (),
        bee_nests: Iterable[tuple[int, int, int]] = (),
        calendar_day: int = 0,
    ) -> None:
        """Take cyclic snapshots and refresh stable production / overlay grids."""
        if world.rows != self.rows or world.cols != self.cols:
            self.resize(world.rows, world.cols)

        bio = biodiversity_snapshot(
            world,
            deer_positions=deer_positions,
            boar_positions=boar_positions,
            fish_positions=fish_positions,
            bee_positions=bee_positions,
            rabbit_positions=rabbit_positions,
            wolf_positions=wolf_positions,
        )
        self.biodiversity_samples.append(bio)
        _trim_samples(self.biodiversity_samples, ENV_SAMPLES_PER_YEAR)
        self.biodiversity = average_grids(
            self.biodiversity_samples, self.rows, self.cols
        )
        self._rebuild_pest_control()

        floral = floral_resources_snapshot(world)
        self.floral_samples.append(floral)
        _trim_samples(self.floral_samples, ENV_SAMPLES_PER_YEAR)
        self.floral_resources = average_grids(
            self.floral_samples, self.rows, self.cols
        )

        # Pollination is instantaneous from active nests (still refreshed 8×/year).
        self.pollination = pollination_coverage_grid(
            world,
            bee_nests,
            base_radius=POLLINATOR_BASE_RADIUS,
            radius_per_level=POLLINATOR_RADIUS_PER_LEVEL,
            base_strength=POLLINATOR_BASE_STRENGTH,
            strength_per_level=POLLINATOR_STRENGTH_PER_LEVEL,
        )
        if not any(any(float(v) > 0.0 for v in row) for row in self.soil_moisture):
            self.soil_moisture = soil_moisture_grid(world, calendar_day)
        self.temperature = temperature_grid(world, calendar_day)
        self.rainfall_modifiers = rainfall_modifier_grid(world)

    def update_weather(
        self,
        world: World,
        intensity: float,
        calendar_day: int,
        localisation: list[list[float]] | None = None,
    ) -> None:
        """Apply today's regional rain to local rainfall and soil moisture."""
        if not self.rainfall_modifiers or len(self.rainfall_modifiers) != self.rows:
            self.rainfall_modifiers = rainfall_modifier_grid(world)
        strength = max(0.0, min(1.0, float(intensity)))
        local = localisation or [[1.0] * self.cols for _ in range(self.rows)]
        self.rainfall = [
            [
                max(0.0, min(1.0, strength * modifier * local[y][x]))
                for x, modifier in enumerate(row)
            ]
            for y, row in enumerate(self.rainfall_modifiers)
        ]
        self.soil_moisture = update_soil_moisture_from_rain(
            world, self.soil_moisture, self.rainfall, self.temperature, calendar_day
        )

    def farm_pest_control(self, cells: Iterable[tuple[int, int]]) -> float:
        return self.average_over(EnvLayer.PEST_CONTROL, cells)

    def farm_biodiversity(self, cells: Iterable[tuple[int, int]]) -> float:
        return self.average_over(EnvLayer.BIODIVERSITY, cells)

    def farm_floral(self, cells: Iterable[tuple[int, int]]) -> float:
        return self.average_over(EnvLayer.FLORAL_RESOURCES, cells)

    def farm_pollination(self, cells: Iterable[tuple[int, int]]) -> float:
        return self.average_over(EnvLayer.POLLINATION, cells)

    def farm_soil_moisture(self, cells: Iterable[tuple[int, int]]) -> float:
        return self.average_over(EnvLayer.SOIL_MOISTURE, cells)

    def farm_temperature(self, cells: Iterable[tuple[int, int]]) -> float:
        return self.average_over(EnvLayer.TEMPERATURE, cells)

    def farm_rainfall(self, cells: Iterable[tuple[int, int]]) -> float:
        return self.average_over(EnvLayer.RAINFALL, cells)

    def to_save_dict(self) -> dict:
        from developer_tools.terrain_editor import ecology_signature
        return {
            "terrain_ecology_signature": ecology_signature(),
            "biodiversity_samples": self.biodiversity_samples,
            "biodiversity": self.biodiversity,
            "pest_control": self.pest_control,
            "floral_samples": self.floral_samples,
            "floral_resources": self.floral_resources,
            "pollination": self.pollination,
            "erosion": self.erosion,
            "soil_moisture": self.soil_moisture,
            "temperature": self.temperature,
            "rainfall_modifiers": self.rainfall_modifiers,
            "rainfall": self.rainfall,
        }

    def load_save_dict(self, data: dict | None) -> None:
        if not data:
            self._rebuild_pest_control()
            return
        samples = data.get("biodiversity_samples")
        if isinstance(samples, list) and samples:
            self.biodiversity_samples = samples[-ENV_SAMPLES_PER_YEAR:]
            self.biodiversity = average_grids(
                self.biodiversity_samples, self.rows, self.cols
            )
        elif isinstance(data.get("biodiversity"), list):
            self.biodiversity = data["biodiversity"]
            self.biodiversity_samples = [self.biodiversity]
        stored_pc = data.get("pest_control")
        if isinstance(stored_pc, list) and stored_pc:
            self.pest_control = stored_pc
        else:
            self._rebuild_pest_control()

        floral_s = data.get("floral_samples")
        if isinstance(floral_s, list) and floral_s:
            self.floral_samples = floral_s[-ENV_SAMPLES_PER_YEAR:]
            self.floral_resources = average_grids(
                self.floral_samples, self.rows, self.cols
            )
        elif isinstance(data.get("floral_resources"), list):
            self.floral_resources = data["floral_resources"]
            self.floral_samples = [self.floral_resources]

        if isinstance(data.get("pollination"), list):
            self.pollination = data["pollination"]
        moisture = data.get("soil_moisture")
        if (
            isinstance(moisture, list)
            and len(moisture) == self.rows
            and moisture
            and len(moisture[0]) == self.cols
        ):
            self.soil_moisture = moisture
        temperature = data.get("temperature")
        if (
            isinstance(temperature, list)
            and len(temperature) == self.rows
            and temperature
            and len(temperature[0]) == self.cols
        ):
            self.temperature = temperature
        for key in ("rainfall_modifiers", "rainfall"):
            grid = data.get(key)
            if (
                isinstance(grid, list)
                and len(grid) == self.rows
                and grid
                and len(grid[0]) == self.cols
            ):
                setattr(self, key, grid)
        erosion = data.get("erosion")
        if (
            isinstance(erosion, list)
            and len(erosion) == self.rows
            and erosion
            and len(erosion[0]) == self.cols
        ):
            self.erosion = erosion
