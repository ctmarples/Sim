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
from world import World

ENV_SAMPLES_PER_YEAR: int = BIODIVERSITY_SAMPLES_PER_YEAR

# Biodiversity richness (species count) → pest-control quality / yield mult.
PEST_CONTROL_RICHNESS_LOW: float = 1.0
PEST_CONTROL_RICHNESS_MID: float = 5.0
PEST_CONTROL_RICHNESS_HIGH: float = 10.0
PEST_CONTROL_MULT_LOW: float = 0.75
PEST_CONTROL_MULT_MID: float = 1.0
PEST_CONTROL_MULT_HIGH: float = 1.15

# Pollination coverage (0–1) → farm yield multiplier.
POLLINATION_YIELD_LOW: float = 0.9
POLLINATION_YIELD_HIGH: float = 1.2

# Field crop health: floor + max drop per 8-cycle sample (only decreases).
CROP_HEALTH_MIN: float = 0.7
CROP_HEALTH_MAX_DROP: float = 0.05


class EnvLayer(Enum):
    """Stable cyclic layers used for production modifiers / overlays."""

    BIODIVERSITY = auto()
    PEST_CONTROL = auto()
    FLORAL_RESOURCES = auto()
    POLLINATION = auto()


def is_env_sample_day(calendar_day: int) -> bool:
    """True on season start and midpoint (8 times per 112-day year)."""
    d = day_in_season(calendar_day)
    return d == 0 or d == DAYS_PER_SEASON // 2


def env_sample_period(calendar_day: int) -> int:
    """Half-season index 0..7 within the year."""
    from seasons import YEAR_DAYS, season_for_day, SEASON_ORDER

    day = int(calendar_day) % YEAR_DAYS
    half = DAYS_PER_SEASON // 2
    si = SEASON_ORDER.index(season_for_day(day))
    return si * 2 + (0 if day_in_season(day) < half else 1)


def pest_control_multiplier(richness: float) -> float:
    """Map neighbourhood species richness to a farm yield multiplier."""
    v = max(0.0, float(richness))
    lo, mid, hi = (
        PEST_CONTROL_RICHNESS_LOW,
        PEST_CONTROL_RICHNESS_MID,
        PEST_CONTROL_RICHNESS_HIGH,
    )
    m_lo, m_mid, m_hi = (
        PEST_CONTROL_MULT_LOW,
        PEST_CONTROL_MULT_MID,
        PEST_CONTROL_MULT_HIGH,
    )
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
    """Environmental health target from pest-control pressure (0.7–1.0).

    Full health when pest control ≥ mid (bio ≈ 5). Below that, scales gently
    down to ``CROP_HEALTH_MIN`` at/under MULT_LOW — cleared fields stay usable.
    """
    if pest_control >= PEST_CONTROL_MULT_MID:
        return 1.0
    if pest_control <= PEST_CONTROL_MULT_LOW:
        return CROP_HEALTH_MIN
    span = PEST_CONTROL_MULT_MID - PEST_CONTROL_MULT_LOW
    t = (pest_control - PEST_CONTROL_MULT_LOW) / span
    return CROP_HEALTH_MIN + (1.0 - CROP_HEALTH_MIN) * t


def pollination_yield_multiplier(coverage: float) -> float:
    """Map nest coverage 0–1 to a yield multiplier."""
    t = max(0.0, min(1.0, float(coverage)))
    return POLLINATION_YIELD_LOW + (POLLINATION_YIELD_HIGH - POLLINATION_YIELD_LOW) * t


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

    def __post_init__(self) -> None:
        if not self.biodiversity:
            self.biodiversity = _zero_grid(self.rows, self.cols)
        if not self.pest_control:
            self.pest_control = _zero_grid(self.rows, self.cols)
        if not self.floral_resources:
            self.floral_resources = _zero_grid(self.rows, self.cols)
        if not self.pollination:
            self.pollination = _zero_grid(self.rows, self.cols)

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

    def layer_grid(self, layer: EnvLayer) -> list[list[float]]:
        if layer == EnvLayer.BIODIVERSITY:
            return self.biodiversity
        if layer == EnvLayer.PEST_CONTROL:
            return self.pest_control
        if layer == EnvLayer.FLORAL_RESOURCES:
            return self.floral_resources
        if layer == EnvLayer.POLLINATION:
            return self.pollination
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
        fish_positions: Iterable[tuple[int, int]],
        bee_positions: Iterable[tuple[int, int]] = (),
        rabbit_positions: Iterable[tuple[int, int]] = (),
        bee_nests: Iterable[tuple[int, int, int]] = (),
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

    def farm_pest_control(self, cells: Iterable[tuple[int, int]]) -> float:
        return self.average_over(EnvLayer.PEST_CONTROL, cells)

    def farm_biodiversity(self, cells: Iterable[tuple[int, int]]) -> float:
        return self.average_over(EnvLayer.BIODIVERSITY, cells)

    def farm_floral(self, cells: Iterable[tuple[int, int]]) -> float:
        return self.average_over(EnvLayer.FLORAL_RESOURCES, cells)

    def farm_pollination(self, cells: Iterable[tuple[int, int]]) -> float:
        return self.average_over(EnvLayer.POLLINATION, cells)

    def to_save_dict(self) -> dict:
        return {
            "biodiversity_samples": self.biodiversity_samples,
            "biodiversity": self.biodiversity,
            "pest_control": self.pest_control,
            "floral_samples": self.floral_samples,
            "floral_resources": self.floral_resources,
            "pollination": self.pollination,
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
