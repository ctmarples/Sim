"""Environmental indicator calculations and overlay colour mapping.

Indicators are derived from the live world state each frame (or after actions),
not baked in at generation time.

Future extension points:
- biodiversity species richness
- habitat connectivity / fragmentation metrics
- soil fertility and water availability overlays
- pollination / erosion risk layers
- scenario comparison side-by-side views
"""

from __future__ import annotations

from enum import Enum, auto

from settings import (
    COLOUR_DISTURBANCE_HIGH,
    COLOUR_DISTURBANCE_LOW,
    COLOUR_DIVERSITY_HIGH,
    COLOUR_DIVERSITY_LOW,
    COLOUR_TREE_DENSITY_HIGH,
    COLOUR_TREE_DENSITY_LOW,
    INDICATOR_RADIUS,
    Colour,
)
from world import FeatureType, World


class OverlayMode(Enum):
    NONE = auto()
    HABITAT_DIVERSITY = auto()
    TREE_DENSITY = auto()
    DISTURBANCE = auto()


OVERLAY_LABELS: dict[OverlayMode, str] = {
    OverlayMode.NONE: "None",
    OverlayMode.HABITAT_DIVERSITY: "Habitat diversity",
    OverlayMode.TREE_DENSITY: "Tree density",
    OverlayMode.DISTURBANCE: "Disturbance",
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
    # Theoretical max categories in this prototype.
    max_categories = 11  # terrain + features including hunter
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


def disturbance_value(world: World, x: int, y: int) -> float:
    cell = world.get_cell(x, y)
    if cell is None:
        return 0.0
    return max(0.0, min(1.0, cell.disturbance))


def indicator_value(world: World, mode: OverlayMode, x: int, y: int) -> float:
    if mode == OverlayMode.HABITAT_DIVERSITY:
        return habitat_diversity(world, x, y)
    if mode == OverlayMode.TREE_DENSITY:
        return tree_density(world, x, y)
    if mode == OverlayMode.DISTURBANCE:
        return disturbance_value(world, x, y)
    return 0.0


def overlay_colour(mode: OverlayMode, value: float) -> Colour:
    if mode == OverlayMode.HABITAT_DIVERSITY:
        return lerp_colour(COLOUR_DIVERSITY_LOW, COLOUR_DIVERSITY_HIGH, value)
    if mode == OverlayMode.TREE_DENSITY:
        return lerp_colour(COLOUR_TREE_DENSITY_LOW, COLOUR_TREE_DENSITY_HIGH, value)
    if mode == OverlayMode.DISTURBANCE:
        return lerp_colour(COLOUR_DISTURBANCE_LOW, COLOUR_DISTURBANCE_HIGH, value)
    return (0, 0, 0)


def build_overlay_grid(world: World, mode: OverlayMode) -> list[list[float]]:
    """Compute a full indicator grid for the active overlay mode."""
    if mode == OverlayMode.NONE:
        return [[0.0] * world.cols for _ in range(world.rows)]
    return [
        [indicator_value(world, mode, x, y) for x in range(world.cols)]
        for y in range(world.rows)
    ]
