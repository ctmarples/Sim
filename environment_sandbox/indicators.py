"""Environmental indicator calculations and overlay colour mapping.

Most overlays are derived live from world state. Biodiversity is an exception:
it is sampled at the start and midpoint of each season (8×/year), then averaged
over the past year. Production modifiers (pest control, …) are derived from
those stable averages in ``environment.EnvMaps``.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Iterable

from balance_config import active_balance
from settings import (
    COLOUR_BIODIVERSITY_1,
    COLOUR_BIODIVERSITY_5,
    COLOUR_BIODIVERSITY_10,
    COLOUR_DISTURBANCE_HIGH,
    COLOUR_DISTURBANCE_LOW,
    COLOUR_DIVERSITY_HIGH,
    COLOUR_DIVERSITY_LOW,
    COLOUR_EROSION_HIGH,
    COLOUR_EROSION_LOW,
    COLOUR_FERTILITY_HIGH,
    COLOUR_FERTILITY_LOW,
    COLOUR_SPECIES_DIVERSITY_HIGH,
    COLOUR_SPECIES_DIVERSITY_LOW,
    COLOUR_TREE_DENSITY_HIGH,
    COLOUR_TREE_DENSITY_LOW,
    Colour,
)
from trees import TREE_KEYS
from world import FeatureType, World


def _indicator_radius() -> int:
    return active_balance().get_int("INDICATOR_RADIUS")

# Samples: start + mid of each of 4 seasons.
BIODIVERSITY_SAMPLES_PER_YEAR: int = 8

# Colour ramp anchors (species count in neighbourhood).
BIODIVERSITY_COLOUR_AT: tuple[float, float, float] = (0.0, 5.0, 10.0)


class OverlayMode(Enum):
    NONE = auto()
    HABITAT_DIVERSITY = auto()
    TREE_DENSITY = auto()
    SPECIES_DIVERSITY = auto()
    DISTURBANCE = auto()
    BIODIVERSITY = auto()
    FLORAL_RESOURCES = auto()
    POLLINATION = auto()
    EROSION = auto()
    FERTILITY = auto()
    FIELD_YIELD = auto()


OVERLAY_LABELS: dict[OverlayMode, str] = {
    OverlayMode.NONE: "None",
    OverlayMode.HABITAT_DIVERSITY: "Habitat diversity",
    OverlayMode.TREE_DENSITY: "Tree density",
    OverlayMode.SPECIES_DIVERSITY: "Species diversity",
    OverlayMode.DISTURBANCE: "Disturbance",
    OverlayMode.BIODIVERSITY: "Biodiversity",
    OverlayMode.FLORAL_RESOURCES: "Floral resources",
    OverlayMode.POLLINATION: "Pollination",
    OverlayMode.EROSION: "Soil erosion",
    OverlayMode.FERTILITY: "Soil fertility",
    OverlayMode.FIELD_YIELD: "Field yield",
}


def format_overlay_value(mode: OverlayMode, value: float) -> str:
    """Human-readable readout for the overlay HUD under the cursor."""
    if mode == OverlayMode.NONE:
        return "—"
    if mode == OverlayMode.BIODIVERSITY:
        return f"{value:.1f} species"
    if mode == OverlayMode.FIELD_YIELD:
        if value <= 0.0:
            return "—"
        return f"{value * 100:.0f}% of base"
    if mode == OverlayMode.FLORAL_RESOURCES:
        return f"{value:.2f}"
    # Most live overlays are 0–1 fractions mapped to the colour ramp.
    return f"{value * 100:.0f}%"


def lerp_colour(low: Colour, high: Colour, t: float) -> Colour:
    t = max(0.0, min(1.0, t))
    return (
        int(low[0] + (high[0] - low[0]) * t),
        int(low[1] + (high[1] - low[1]) * t),
        int(low[2] + (high[2] - low[2]) * t),
    )


def habitat_diversity(world: World, x: int, y: int, radius: int | None = None) -> float:
    """Unique habitat/feature categories in the local neighbourhood, normalised 0–1."""
    radius = _indicator_radius() if radius is None else radius
    categories: set[str] = set()
    count = 0
    for ny, nx in world.neighbourhood(x, y, radius):
        categories.add(world.cells[ny][nx].habitat_category())
        count += 1
    if count == 0:
        return 0.0
    max_categories = 16 + 2 * len(TREE_KEYS)
    return min(1.0, len(categories) / max_categories)


def tree_density(world: World, x: int, y: int, radius: int | None = None) -> float:
    """Proportion of nearby cells that contain a tree or sapling."""
    radius = _indicator_radius() if radius is None else radius
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


def species_diversity(world: World, x: int, y: int, radius: int | None = None) -> float:
    """Unique tree species among nearby trees/saplings, normalised 0–1."""
    radius = _indicator_radius() if radius is None else radius
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
    from world import effective_disturbance_at

    return effective_disturbance_at(world, x, y)


def fertility_value(world: World, x: int, y: int) -> float:
    from soil import overlay_fertility

    cell = world.get_cell(x, y)
    if cell is None:
        return 0.0
    return overlay_fertility(cell)


def species_on_cell(cell) -> set[str]:
    """Plant species ids present on a single cell (farm + wild share crop keys)."""
    found: set[str] = set()
    feature = cell.feature
    if feature == FeatureType.TREE:
        found.add(f"tree:{cell.tree_species or 'oak'}")
    elif feature == FeatureType.SAPLING:
        # Count as the same species as the adult tree for richness.
        found.add(f"tree:{cell.tree_species or 'oak'}")
    elif feature == FeatureType.BERRY_BUSH:
        found.add("plant:berry")
    elif feature == FeatureType.MUSHROOM:
        found.add("plant:mushroom")
    elif feature == FeatureType.REED:
        kind = getattr(cell, "crop_kind", None) or "reed"
        found.add(f"plant:{kind}")
    elif feature == FeatureType.WOOD_BUSH:
        found.add("plant:wood_bush")
    elif feature in (FeatureType.HERB, FeatureType.WILD_CROP, FeatureType.CROP_HERB):
        kind = cell.crop_kind or "sage"
        found.add(f"crop:{kind}")
    return found


def floral_score_on_cell(cell) -> float:
    """Local floral resource contribution of one cell (0–1 scale pieces)."""
    from world import TerrainType

    feature = cell.feature
    if feature == FeatureType.BERRY_BUSH and cell.deposit > 0:
        return 1.0
    if feature == FeatureType.BERRY_BUSH:
        return 0.35
    if feature in (FeatureType.HERB, FeatureType.WILD_CROP):
        return 0.85
    if feature == FeatureType.CROP_HERB:
        return 0.65
    if feature == FeatureType.REED:
        return 0.4
    if feature == FeatureType.WOOD_BUSH:
        return 0.15
    if feature == FeatureType.MUSHROOM:
        return 0.05
    if feature == FeatureType.NONE and cell.terrain == TerrainType.MEADOW:
        return 0.2
    return 0.0


def biodiversity_snapshot(
    world: World,
    *,
    deer_positions: Iterable[tuple[int, int]],
    boar_positions: Iterable[tuple[int, int]],
    fish_positions: Iterable[tuple[int, int, str]],
    bee_positions: Iterable[tuple[int, int]] = (),
    rabbit_positions: Iterable[tuple[int, int]] = (),
    wolf_positions: Iterable[tuple[int, int]] = (),
    radius: int | None = None,
) -> list[list[float]]:
    """Spatial richness: unique plant + animal species in each neighbourhood.

    ``fish_positions`` is ``(x, y, species_key)`` so carp/perch/pike/roach
    each count separately. Colour scale: 0=red → 5=yellow → 10+=bright green.
    """
    radius = _indicator_radius() if radius is None else radius
    rows, cols = world.rows, world.cols
    plant: list[list[set[str]]] = [[set() for _ in range(cols)] for _ in range(rows)]
    for y in range(rows):
        for x in range(cols):
            plant[y][x] = species_on_cell(world.cells[y][x])

    def _mark(positions: Iterable[tuple[int, int]]) -> list[list[bool]]:
        grid = [[False] * cols for _ in range(rows)]
        for ax, ay in positions:
            if 0 <= ax < cols and 0 <= ay < rows:
                grid[ay][ax] = True
        return grid

    has_deer = _mark(deer_positions)
    has_boar = _mark(boar_positions)
    has_bee = _mark(bee_positions)
    has_rabbit = _mark(rabbit_positions)
    has_wolf = _mark(wolf_positions)

    # Sparse fish marks — avoid allocating a set per map cell.
    fish_at: dict[tuple[int, int], set[str]] = {}
    for entry in fish_positions:
        if len(entry) < 2:
            continue
        ax, ay = int(entry[0]), int(entry[1])
        if not (0 <= ax < cols and 0 <= ay < rows):
            continue
        kind = str(entry[2]).lower() if len(entry) >= 3 else "fish"
        fish_at.setdefault((ax, ay), set()).add(f"animal:fish:{kind}")

    grid: list[list[float]] = [[0.0] * cols for _ in range(rows)]
    for y in range(rows):
        for x in range(cols):
            species: set[str] = set()
            for ny, nx in world.neighbourhood(x, y, radius):
                species |= plant[ny][nx]
                fish_here = fish_at.get((nx, ny))
                if fish_here:
                    species |= fish_here
                if has_deer[ny][nx]:
                    species.add("animal:deer")
                if has_boar[ny][nx]:
                    species.add("animal:boar")
                if has_bee[ny][nx]:
                    species.add("animal:bee")
                if has_rabbit[ny][nx]:
                    species.add("animal:rabbit")
                if has_wolf[ny][nx]:
                    species.add("animal:wolf")
            grid[y][x] = float(len(species))
    return grid


def floral_resources_snapshot(
    world: World, *, radius: int | None = None
) -> list[list[float]]:
    """Neighbourhood mean floral score (0–1-ish, can exceed 1 with dense flowers)."""
    radius = _indicator_radius() if radius is None else radius
    rows, cols = world.rows, world.cols
    local = [
        [floral_score_on_cell(world.cells[y][x]) for x in range(cols)]
        for y in range(rows)
    ]
    grid: list[list[float]] = [[0.0] * cols for _ in range(rows)]
    for y in range(rows):
        for x in range(cols):
            total = 0.0
            n = 0
            for ny, nx in world.neighbourhood(x, y, radius):
                total += local[ny][nx]
                n += 1
            grid[y][x] = total / n if n else 0.0
    return grid


def pollination_coverage_grid(
    world: World,
    nests: Iterable[tuple[int, int, int]],
    *,
    base_radius: int,
    radius_per_level: int,
    base_strength: float = 0.85,
    strength_per_level: float = 0.05,
) -> list[list[float]]:
    """0–1 pollination access from active bee nests; nest level widens reach.

    ``nests`` is ``(x, y, level)`` for each bee colony.
    """
    rows, cols = world.rows, world.cols
    grid: list[list[float]] = [[0.0] * cols for _ in range(rows)]
    for nx, ny, level in nests:
        level = max(1, int(level))
        reach = max(1, base_radius + (level - 1) * radius_per_level)
        strength = min(1.0, base_strength + strength_per_level * (level - 1))
        for y in range(max(0, ny - reach), min(rows, ny + reach + 1)):
            for x in range(max(0, nx - reach), min(cols, nx + reach + 1)):
                dist = max(abs(x - nx), abs(y - ny))
                if dist > reach:
                    continue
                # Gentler falloff so mid-range cells stay useful.
                falloff = 1.0 - 0.65 * (dist / float(reach))
                grid[y][x] = max(grid[y][x], strength * falloff)
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
    """Map richness to red(0) → yellow(5) → bright green(10+)."""
    v = max(0.0, float(species_count))
    lo, mid, hi = BIODIVERSITY_COLOUR_AT
    if v <= lo:
        return COLOUR_BIODIVERSITY_1
    if v <= mid:
        return lerp_colour(COLOUR_BIODIVERSITY_1, COLOUR_BIODIVERSITY_5, (v - lo) / (mid - lo))
    if v <= hi:
        return lerp_colour(COLOUR_BIODIVERSITY_5, COLOUR_BIODIVERSITY_10, (v - mid) / (hi - mid))
    return COLOUR_BIODIVERSITY_10


def floral_colour(value: float) -> Colour:
    """Floral density: dim magenta → bright pink/yellow."""
    t = max(0.0, min(1.0, float(value)))
    return lerp_colour((40, 20, 40), (255, 170, 90), t)


def pollination_colour(value: float) -> Colour:
    """Pollination access: dark → bright amber."""
    t = max(0.0, min(1.0, float(value)))
    return lerp_colour((25, 25, 20), (255, 210, 60), t)


def indicator_value(world: World, mode: OverlayMode, x: int, y: int) -> float:
    if mode == OverlayMode.HABITAT_DIVERSITY:
        return habitat_diversity(world, x, y)
    if mode == OverlayMode.TREE_DENSITY:
        return tree_density(world, x, y)
    if mode == OverlayMode.SPECIES_DIVERSITY:
        return species_diversity(world, x, y)
    if mode == OverlayMode.DISTURBANCE:
        return disturbance_value(world, x, y)
    if mode == OverlayMode.FERTILITY:
        return fertility_value(world, x, y)
    # Biodiversity / floral / pollination / erosion are supplied by Game.
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
    if mode == OverlayMode.FLORAL_RESOURCES:
        return floral_colour(value)
    if mode == OverlayMode.POLLINATION:
        return pollination_colour(value)
    if mode == OverlayMode.EROSION:
        return lerp_colour(COLOUR_EROSION_LOW, COLOUR_EROSION_HIGH, value)
    if mode == OverlayMode.FERTILITY:
        return lerp_colour(COLOUR_FERTILITY_LOW, COLOUR_FERTILITY_HIGH, value)
    if mode == OverlayMode.FIELD_YIELD:
        # Green good → red poor (value already normalised high=good)
        return lerp_colour(COLOUR_DISTURBANCE_HIGH, COLOUR_FERTILITY_HIGH, value)
    return (0, 0, 0)


def build_overlay_grid(world: World, mode: OverlayMode) -> list[list[float]]:
    """Compute a full indicator grid for live overlay modes."""
    if mode in (
        OverlayMode.NONE,
        OverlayMode.BIODIVERSITY,
        OverlayMode.FLORAL_RESOURCES,
        OverlayMode.POLLINATION,
        OverlayMode.EROSION,
        OverlayMode.FIELD_YIELD,
    ):
        return [[0.0] * world.cols for _ in range(world.rows)]
    return [
        [indicator_value(world, mode, x, y) for x in range(world.cols)]
        for y in range(world.rows)
    ]
