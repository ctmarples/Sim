"""Environmental indicator calculations and overlay colour mapping.

Most overlays are derived live from world state. Biodiversity is an exception:
it is sampled at the start and midpoint of each season, then averaged over the
past year (up to 8 samples).
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Iterable

from settings import (
    COLOUR_BIODIVERSITY_1,
    COLOUR_BIODIVERSITY_5,
    COLOUR_BIODIVERSITY_10,
    COLOUR_DISTURBANCE_HIGH,
    COLOUR_DISTURBANCE_LOW,
    COLOUR_DIVERSITY_HIGH,
    COLOUR_DIVERSITY_LOW,
    COLOUR_SPECIES_DIVERSITY_HIGH,
    COLOUR_SPECIES_DIVERSITY_LOW,
    COLOUR_TREE_DENSITY_HIGH,
    COLOUR_TREE_DENSITY_LOW,
    INDICATOR_RADIUS,
    Colour,
)
from trees import TREE_KEYS
from world import FeatureType, World

# Samples: start + mid of each of 4 seasons.
BIODIVERSITY_SAMPLES_PER_YEAR: int = 8

# Colour ramp anchors (species count in neighbourhood).
BIODIVERSITY_COLOUR_AT: tuple[float, float, float] = (1.0, 5.0, 10.0)


class OverlayMode(Enum):
    NONE = auto()
    HABITAT_DIVERSITY = auto()
    TREE_DENSITY = auto()
    SPECIES_DIVERSITY = auto()
    DISTURBANCE = auto()
    BIODIVERSITY = auto()


OVERLAY_LABELS: dict[OverlayMode, str] = {
    OverlayMode.NONE: "None",
    OverlayMode.HABITAT_DIVERSITY: "Habitat diversity",
    OverlayMode.TREE_DENSITY: "Tree density",
    OverlayMode.SPECIES_DIVERSITY: "Species diversity",
    OverlayMode.DISTURBANCE: "Disturbance",
    OverlayMode.BIODIVERSITY: "Biodiversity",
}


def lerp_colour(low: Colour, high: Colour, t: float) -> Colour:
    t = max(0.0, min(1.0, t))
    return (
        int(low[0] + (high[0] - low[0]) * t),
        int(low[1] + (high[1] - low[1]) * t),
        int(low[2] + (high[2] - low[2]) * t),
    )


def habitat_diversity(world: World, x: int, y: int, radius: int = INDICATOR_RADIUS) -> float:
    """Unique habitat/feature categories in the local neighbourhood, normalised 0–1."""
    categories: set[str] = set()
    count = 0
    for ny, nx in world.neighbourhood(x, y, radius):
        categories.add(world.cells[ny][nx].habitat_category())
        count += 1
    if count == 0:
        return 0.0
    max_categories = 16 + 2 * len(TREE_KEYS)
    return min(1.0, len(categories) / max_categories)


def tree_density(world: World, x: int, y: int, radius: int = INDICATOR_RADIUS) -> float:
    """Proportion of nearby cells that contain a tree or sapling."""
    total = 0
    trees = 0
    for ny, nx in world.neighbourhood(x, y, radius):
        total += 1
        feature = world.cells[ny][nx].feature
        if feature in (FeatureType.TREE, FeatureType.SAPLING):
            trees += 1
    if total == 0:
        return 0.0
    return trees / total


def species_diversity(world: World, x: int, y: int, radius: int = INDICATOR_RADIUS) -> float:
    """Unique tree species among nearby trees/saplings, normalised 0–1."""
    species: set[str] = set()
    for ny, nx in world.neighbourhood(x, y, radius):
        cell = world.cells[ny][nx]
        if cell.feature not in (FeatureType.TREE, FeatureType.SAPLING):
            continue
        if cell.tree_species:
            species.add(cell.tree_species)
        else:
            species.add("oak")
    if not species:
        return 0.0
    return min(1.0, len(species) / max(1, len(TREE_KEYS)))


def disturbance_value(world: World, x: int, y: int) -> float:
    cell = world.get_cell(x, y)
    if cell is None:
        return 0.0
    return max(0.0, min(1.0, cell.disturbance))


def species_on_cell(cell) -> set[str]:
    """Plant species ids present on a single cell (farm + wild share crop keys)."""
    found: set[str] = set()
    feature = cell.feature
    if feature == FeatureType.TREE:
        found.add(f"tree:{cell.tree_species or 'oak'}")
    elif feature == FeatureType.SAPLING:
        found.add(f"sapling:{cell.tree_species or 'oak'}")
    elif feature == FeatureType.BERRY_BUSH:
        found.add("plant:berry")
    elif feature == FeatureType.MUSHROOM:
        found.add("plant:mushroom")
    elif feature == FeatureType.REED:
        found.add("plant:reed")
    elif feature in (FeatureType.HERB, FeatureType.WILD_CROP, FeatureType.CROP_HERB):
        kind = cell.crop_kind or "sage"
        found.add(f"crop:{kind}")
    return found


def biodiversity_snapshot(
    world: World,
    *,
    deer_positions: Iterable[tuple[int, int]],
    boar_positions: Iterable[tuple[int, int]],
    fish_positions: Iterable[tuple[int, int]],
    radius: int = INDICATOR_RADIUS,
) -> list[list[float]]:
    """Spatial richness: species count per neighbourhood (not normalised).

    Wheat (farm) and wild wheat share one crop species id. Deer and boar are
    separate animal species; all fish count as one. Colour scale uses
    1=red, 5=yellow, 10=green.
    """
    rows, cols = world.rows, world.cols
    plant: list[list[set[str]]] = [[set() for _ in range(cols)] for _ in range(rows)]
    for y in range(rows):
        for x in range(cols):
            plant[y][x] = species_on_cell(world.cells[y][x])

    has_deer = [[False] * cols for _ in range(rows)]
    for ax, ay in deer_positions:
        if 0 <= ax < cols and 0 <= ay < rows:
            has_deer[ay][ax] = True
    has_boar = [[False] * cols for _ in range(rows)]
    for bx, by in boar_positions:
        if 0 <= bx < cols and 0 <= by < rows:
            has_boar[by][bx] = True
    has_fish = [[False] * cols for _ in range(rows)]
    for fx, fy in fish_positions:
        if 0 <= fx < cols and 0 <= fy < rows:
            has_fish[fy][fx] = True

    grid: list[list[float]] = [[0.0] * cols for _ in range(rows)]
    for y in range(rows):
        for x in range(cols):
            species: set[str] = set()
            for ny, nx in world.neighbourhood(x, y, radius):
                species |= plant[ny][nx]
                if has_deer[ny][nx]:
                    species.add("animal:deer")
                if has_boar[ny][nx]:
                    species.add("animal:boar")
                if has_fish[ny][nx]:
                    species.add("animal:fish")
            grid[y][x] = float(len(species))
    return grid


def average_grids(samples: list[list[list[float]]], rows: int, cols: int) -> list[list[float]]:
    """Mean of sample grids; empty samples → zeros."""
    if not samples:
        return [[0.0] * cols for _ in range(rows)]
    n = float(len(samples))
    out = [[0.0] * cols for _ in range(rows)]
    for sample in samples:
        for y in range(rows):
            row = sample[y] if y < len(sample) else []
            for x in range(cols):
                if x < len(row):
                    out[y][x] += float(row[x])
    for y in range(rows):
        for x in range(cols):
            out[y][x] /= n
    return out


def biodiversity_colour(species_count: float) -> Colour:
    """Map average species richness to red(1) → yellow(5) → green(10)."""
    v = max(0.0, float(species_count))
    lo, mid, hi = BIODIVERSITY_COLOUR_AT
    if v <= lo:
        # Fade from near-black at 0 up to red at 1.
        return lerp_colour((40, 10, 10), COLOUR_BIODIVERSITY_1, v / lo if lo > 0 else 1.0)
    if v <= mid:
        return lerp_colour(COLOUR_BIODIVERSITY_1, COLOUR_BIODIVERSITY_5, (v - lo) / (mid - lo))
    if v <= hi:
        return lerp_colour(COLOUR_BIODIVERSITY_5, COLOUR_BIODIVERSITY_10, (v - mid) / (hi - mid))
    return COLOUR_BIODIVERSITY_10


def indicator_value(world: World, mode: OverlayMode, x: int, y: int) -> float:
    if mode == OverlayMode.HABITAT_DIVERSITY:
        return habitat_diversity(world, x, y)
    if mode == OverlayMode.TREE_DENSITY:
        return tree_density(world, x, y)
    if mode == OverlayMode.SPECIES_DIVERSITY:
        return species_diversity(world, x, y)
    if mode == OverlayMode.DISTURBANCE:
        return disturbance_value(world, x, y)
    # Biodiversity is not live-computed; Game supplies the year average.
    return 0.0


def overlay_colour(mode: OverlayMode, value: float) -> Colour:
    if mode == OverlayMode.HABITAT_DIVERSITY:
        return lerp_colour(COLOUR_DIVERSITY_LOW, COLOUR_DIVERSITY_HIGH, value)
    if mode == OverlayMode.TREE_DENSITY:
        return lerp_colour(COLOUR_TREE_DENSITY_LOW, COLOUR_TREE_DENSITY_HIGH, value)
    if mode == OverlayMode.SPECIES_DIVERSITY:
        return lerp_colour(
            COLOUR_SPECIES_DIVERSITY_LOW, COLOUR_SPECIES_DIVERSITY_HIGH, value
        )
    if mode == OverlayMode.DISTURBANCE:
        return lerp_colour(COLOUR_DISTURBANCE_LOW, COLOUR_DISTURBANCE_HIGH, value)
    if mode == OverlayMode.BIODIVERSITY:
        return biodiversity_colour(value)
    return (0, 0, 0)


def build_overlay_grid(world: World, mode: OverlayMode) -> list[list[float]]:
    """Compute a full indicator grid for live overlay modes."""
    if mode == OverlayMode.NONE or mode == OverlayMode.BIODIVERSITY:
        return [[0.0] * world.cols for _ in range(world.rows)]
    return [
        [indicator_value(world, mode, x, y) for x in range(world.cols)]
        for y in range(world.rows)
    ]
