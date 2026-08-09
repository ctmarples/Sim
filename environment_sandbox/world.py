"""World grid: terrain, features, generation, and neighbourhood queries.

Interaction policy
------------------
The player interacts only with the cell they currently stand on (press E).
Mouse drag draws rectangular task areas for hired villagers.

Future extension points:
- soil fertility / moisture fields (cyclic EnvMaps layers)
- crop / seasonal state per cell
- habitat connectivity graphs
- erosion risk maps
- GIS-derived terrain import

Production modifiers from cyclic layers live in ``environment.EnvMaps``
(sampled 8×/year with biodiversity). Disturbance remains a live per-cell field.
"""

from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
from typing import Iterator

from crops import CROP_BY_KEY
from trees import (
    DEFAULT_TREE_KEY,
    growth_ticks_for,
    pick_tree_species,
    resolve_tree,
)
from seasons import (
    berry_despawn_rate,
    berry_spawn_rate,
    growth_halted,
    herb_despawn_rate,
    herb_spawn_rate,
    mushroom_despawn_rate,
    mushroom_spawn_rate,
    Season,
    season_for_day,
    trees_grow_factor,
    trees_spread_factor,
    wood_bush_spawn_rate,
)
from resource_balance import (
    BERRY_BUSH_YIELD,
    BERRY_REGEN_TICKS,
    BERRY_SPREAD_INTERVAL,
    HERB_TICK_INTERVAL,
    MUSHROOM_SPREAD_CHANCE,
    MUSHROOM_TICK_INTERVAL,
    NATURAL_SPROUT_CHANCE,
    NATURAL_SPROUT_INTERVAL,
    NATURAL_SPROUT_MIN_PATCH,
    ROCK_LARGE_MAX,
    ROCK_LARGE_MIN,
    ROCK_SMALL_MAX,
    ROCK_SMALL_MIN,
    WILD_PLANT_MAX_FRACTION,
    WOOD_BUSH_SEED_CHANCE,
    WOOD_BUSH_YIELD,
)
from settings import (
    DISTURBANCE_INTERACTION_BOOST,
    DISTURBANCE_MAX,
    DISTURBANCE_NEIGHBOUR_SPREAD,
    HEIGHT_LAKE,
    HEIGHT_RIVER_HEAD,
    HEIGHT_VALLEY_RISE_MAX,
    HEIGHT_VALLEY_RISE_PER_CELL,
    RANDOM_SEED,
)


class TerrainType(Enum):
    SOIL = auto()
    FOREST_FLOOR = auto()  # darker soil on tiles that currently hold a tree/sapling
    GRASS = auto()
    MEADOW = auto()  # open meadow — slightly greener than grass
    RIPARIAN = auto()  # shoreline strip beside water
    WATER = auto()  # standing water / lakes (can freeze)
    RIVER = auto()  # flowing channel (does not freeze)
    ROCK = auto()  # bare rocky ground (distinct from rock resource feature)
    URBAN = auto()  # packed ground under contiguous building footprints
    PATH = auto()  # worn sandy tracks from villager journeys


# Open water bodies (impassable; fishing / riparian). Lake-only freeze uses WATER.
WATER_LIKE: tuple[TerrainType, ...] = (
    TerrainType.WATER,
    TerrainType.RIVER,
)


def is_water_terrain(terrain: TerrainType) -> bool:
    return terrain in WATER_LIKE


# Soil and forest floor share plough / sow / forage behaviour.
SOIL_LIKE: tuple[TerrainType, ...] = (
    TerrainType.SOIL,
    TerrainType.FOREST_FLOOR,
)

# Packed / paved ground — walkable, not plantable; URBAN≈PATH for tiling.
HARDSCAPE: tuple[TerrainType, ...] = (
    TerrainType.URBAN,
    TerrainType.PATH,
)

# Wild forage plants by preferred terrain (farm crops may still grow on fields).
WILD_CROPS_BY_TERRAIN: dict[TerrainType, tuple[str, ...]] = {
    TerrainType.MEADOW: ("flax", "hemp", "sage", "mint"),
    TerrainType.GRASS: ("wheat", "rye"),
    TerrainType.SOIL: ("onion", "cabbage", "carrot", "garlic"),
    TerrainType.FOREST_FLOOR: ("onion", "cabbage", "carrot", "garlic"),
}

# Terrains that accept planted saplings / natural sprouts.
PLANTABLE_LAND: tuple[TerrainType, ...] = (
    TerrainType.SOIL,
    TerrainType.FOREST_FLOOR,
    TerrainType.GRASS,
    TerrainType.MEADOW,
)

# Where new buildings may be placed (densify over urban/path).
BUILDABLE_LAND: tuple[TerrainType, ...] = (
    *PLANTABLE_LAND,
    TerrainType.URBAN,
    TerrainType.PATH,
)


def hardscape_tile_group(terrain: TerrainType) -> TerrainType:
    """Tile grouping: RIVER shares WATER visuals; PATH/URBAN stay distinct."""
    if terrain == TerrainType.RIVER:
        return TerrainType.WATER
    return terrain


class FeatureType(Enum):
    NONE = auto()
    TREE = auto()
    SAPLING = auto()
    ROCK = auto()
    HOME = auto()
    WORKSTATION = auto()
    FORESTER = auto()
    MASON = auto()
    HUNTER = auto()
    FORAGER = auto()
    FISHER = auto()
    FARM = auto()
    FIELD = auto()
    MILL = auto()
    KITCHEN = auto()
    CRAFT_BENCH = auto()
    ALCHEMIST = auto()
    TAILOR = auto()
    TENT = auto()
    HOUSE_SMALL = auto()
    HOUSE = auto()
    CONSTRUCTION_SITE = auto()
    # Invisible reserved cells of a multi-cell building footprint (not the glyph cell).
    STRUCTURE_PAD = auto()
    MUSHROOM = auto()
    WOOD_BUSH = auto()
    BERRY_BUSH = auto()
    HERB = auto()  # legacy; migrated to WILD_CROP on load
    WILD_CROP = auto()  # wild crop patches (any CropDef key)
    CROP_HERB = auto()  # farmed crop (growth_ticks > 0 while growing)
    REED = auto()  # riparian reeds (forage, no seeds)
    COMMUNITY = auto()  # map camp marker (decorative / clickable)


# Buildings / pads — map-edit brushes must not overwrite these.
STRUCTURE_FEATURES: frozenset[FeatureType] = frozenset(
    {
        FeatureType.HOME,
        FeatureType.WORKSTATION,
        FeatureType.FORESTER,
        FeatureType.MASON,
        FeatureType.HUNTER,
        FeatureType.FORAGER,
        FeatureType.FISHER,
        FeatureType.FARM,
        FeatureType.FIELD,
        FeatureType.MILL,
        FeatureType.KITCHEN,
        FeatureType.CRAFT_BENCH,
        FeatureType.ALCHEMIST,
        FeatureType.TAILOR,
        FeatureType.TENT,
        FeatureType.HOUSE_SMALL,
        FeatureType.HOUSE,
        FeatureType.CONSTRUCTION_SITE,
        FeatureType.STRUCTURE_PAD,
    }
)

# Terrains available in the map-edit paint tool.
EDIT_PAINTABLE_TERRAIN: tuple[TerrainType, ...] = (
    TerrainType.SOIL,
    TerrainType.FOREST_FLOOR,
    TerrainType.GRASS,
    TerrainType.MEADOW,
    TerrainType.RIPARIAN,
    TerrainType.WATER,
    TerrainType.RIVER,
    TerrainType.ROCK,
)

TERRAIN_EDIT_LABELS: dict[TerrainType, str] = {
    TerrainType.SOIL: "Soil",
    TerrainType.FOREST_FLOOR: "Floor",
    TerrainType.GRASS: "Grass",
    TerrainType.MEADOW: "Meadow",
    TerrainType.RIPARIAN: "Riparian",
    TerrainType.WATER: "Lake",
    TerrainType.RIVER: "River",
    TerrainType.ROCK: "Rock",
}


class MapEditTool(Enum):
    """Side-panel tools available while map-edit mode (Y) is active."""

    HEIGHT_SET = "height_set"
    HEIGHT_RAISE = "height_raise"
    HEIGHT_LOWER = "height_lower"
    TERRAIN_PAINT = "terrain_paint"
    SEED_FOREST = "seed_forest"


@dataclass
class Cell:
    """Single grid cell. Indicators are derived elsewhere from live state."""

    terrain: TerrainType
    feature: FeatureType = FeatureType.NONE
    disturbance: float = 0.0
    growth_ticks: int = 0  # sapling maturity / berry regen countdown
    deposit: int = 0  # wood, rock, or berries remaining
    meat_deposit: int = 0
    fish_deposit: int = 0
    crop_kind: str | None = None  # CropDef key for wild & farm crops
    tree_species: str | None = None  # TreeDef key for TREE / SAPLING
    # 1-based icon variant (e.g. tree_round_2); rolled on first draw.
    icon_variant: int | None = None
    # Visual sub-patch within a terrain biome (seasonal masking / speckles).
    terrain_cluster: int = 0
    terrain_shade: float = 0.55  # 0..1 seasonal wash strength for this subcluster

    def habitat_category(self) -> str:
        if self.feature == FeatureType.TREE:
            return f"tree_{self.tree_species or 'oak'}"
        if self.feature == FeatureType.SAPLING:
            return f"sapling_{self.tree_species or 'oak'}"
        if self.feature != FeatureType.NONE:
            return self.feature.name.lower()
        return self.terrain.name.lower()


def is_bare_rock(cell: Cell) -> bool:
    """Rock ground without a collectable rock deposit."""
    return cell.terrain == TerrainType.ROCK and cell.feature == FeatureType.NONE


def hardscape_paintable(cell: Cell) -> bool:
    """Cells that villager wear / urban may convert (not water, riparian, or deposits)."""
    if is_water_terrain(cell.terrain) or cell.terrain == TerrainType.RIPARIAN:
        return False
    if cell.feature == FeatureType.ROCK:
        return False
    return True


def disturbance_activity_multiplier(disturbance: float) -> float:
    """Ecology/farming effectiveness: 1.0 at zero disturbance, floor at max."""
    from balance_config import active_balance

    d = max(0.0, min(1.0, float(disturbance)))
    floor = active_balance().get_float("DISTURBANCE_ACTIVITY_FLOOR")
    return 1.0 - d * (1.0 - floor)


def effective_disturbance_at(world: "World", x: int, y: int) -> float:
    """Neighbourhood-mean disturbance (Chebyshev radius from balance)."""
    from balance_config import active_balance

    radius = active_balance().get_int("DISTURBANCE_RADIUS")
    if radius <= 0:
        cell = world.get_cell(x, y)
        return max(0.0, min(1.0, cell.disturbance)) if cell is not None else 0.0
    total = 0.0
    count = 0
    for ny, nx in world.neighbourhood(x, y, radius=radius):
        cell = world.get_cell(nx, ny)
        if cell is not None:
            total += cell.disturbance
            count += 1
    if count <= 0:
        return 0.0
    return max(0.0, min(1.0, total / count))


class World:
    """Grid landscape with generation and local queries."""

    def __init__(self, cols: int | None = None, rows: int | None = None, seed: int = RANDOM_SEED) -> None:
        # Resolve at construction time so configure_for_display() can resize the grid.
        import settings as cfg

        self.cols = cfg.WORLD_COLS if cols is None else cols
        self.rows = cfg.WORLD_ROWS if rows is None else rows
        self.seed = seed
        self.cells: list[list[Cell]] = []
        self.home_pos: tuple[int, int] = (0, 0)
        self.workstation_pos: tuple[int, int] = (0, 0)
        self.start_pos: tuple[int, int] = (0, 0)
        self._sprout_timer = NATURAL_SPROUT_INTERVAL
        self._sprout_rng = random.Random(seed + 99)
        self._mushroom_timer = MUSHROOM_TICK_INTERVAL
        self._berry_spread_timer = BERRY_SPREAD_INTERVAL
        self._herb_timer = HERB_TICK_INTERVAL
        self._forage_rng = random.Random(seed + 123)
        self.terrain_revision = 0
        self.terrain_dirty: set[tuple[int, int]] = set()
        # Valley hydrology / heightfield (filled during generate).
        self.valley_path: list[tuple[float, float]] = []
        self.lake_cx = 0.0
        self.lake_cy = 0.0
        self.lake_rx = 1.0
        self.lake_ry = 1.0
        self.height_corners: list[list[float]] = []
        self.generate()

    def ensure_height_corners(self) -> None:
        """Guarantee a full corner grid exists (rows+1 × cols+1)."""
        need_h = self.rows + 1
        need_w = self.cols + 1
        if (
            len(self.height_corners) == need_h
            and self.height_corners
            and len(self.height_corners[0]) == need_w
        ):
            return
        self.height_corners = [[0.0] * need_w for _ in range(need_h)]

    def height_at_cell(self, x: int, y: int) -> float:
        """Mean of the four corners for cell (x, y)."""
        self.ensure_height_corners()
        if not (0 <= x < self.cols and 0 <= y < self.rows):
            return 0.0
        c = self.height_corners
        return (c[y][x] + c[y][x + 1] + c[y + 1][x] + c[y + 1][x + 1]) * 0.25

    def paint_height(
        self,
        cx: int,
        cy: int,
        value: float,
        radius: int,
    ) -> None:
        """Soft-brush paint toward ``value`` at cell (cx, cy), then smooth edges.

        ``radius`` is Chebyshev brush size in cells (0 = single cell). Corners
        within the brush are blended with a smooth falloff so the stamp does not
        leave vertical cliffs; a short Laplacian pass finishes the edges.
        """
        self.ensure_height_corners()
        value = float(value)
        radius = max(0, int(radius))
        # Affect corners covering cells within radius, plus a 1-cell feather.
        feather = radius + 1.5
        cx_f = float(cx) + 0.5
        cy_f = float(cy) + 0.5
        lx0 = max(0, cx - radius - 1)
        ly0 = max(0, cy - radius - 1)
        lx1 = min(self.cols, cx + radius + 2)
        ly1 = min(self.rows, cy + radius + 2)
        for ly in range(ly0, ly1 + 1):
            for lx in range(lx0, lx1 + 1):
                # Distance from brush centre to this corner.
                dist = math.hypot(float(lx) - cx_f, float(ly) - cy_f)
                if dist > feather:
                    continue
                t = 1.0 - dist / feather
                t = t * t * (3.0 - 2.0 * t)  # smoothstep
                old = self.height_corners[ly][lx]
                self.height_corners[ly][lx] = old + (value - old) * t
        self._smooth_height_region(lx0, ly0, lx1, ly1, passes=2)

    def paint_height_delta(
        self,
        cx: int,
        cy: int,
        delta: float,
        radius: int,
        *,
        min_h: float = 0.0,
        max_h: float = 80.0,
    ) -> None:
        """Soft-brush raise/lower: add ``delta`` (signed) with falloff, then smooth."""
        self.ensure_height_corners()
        delta = float(delta)
        if abs(delta) < 1e-9:
            return
        radius = max(0, int(radius))
        feather = radius + 1.5
        cx_f = float(cx) + 0.5
        cy_f = float(cy) + 0.5
        lx0 = max(0, cx - radius - 1)
        ly0 = max(0, cy - radius - 1)
        lx1 = min(self.cols, cx + radius + 2)
        ly1 = min(self.rows, cy + radius + 2)
        for ly in range(ly0, ly1 + 1):
            for lx in range(lx0, lx1 + 1):
                dist = math.hypot(float(lx) - cx_f, float(ly) - cy_f)
                if dist > feather:
                    continue
                t = 1.0 - dist / feather
                t = t * t * (3.0 - 2.0 * t)
                old = self.height_corners[ly][lx]
                self.height_corners[ly][lx] = max(
                    min_h, min(max_h, old + delta * t)
                )
        self._smooth_height_region(lx0, ly0, lx1, ly1, passes=2)

    def paint_terrain(
        self,
        cx: int,
        cy: int,
        terrain: TerrainType,
        radius: int,
        *,
        clear_features: bool = True,
    ) -> bool:
        """Paint ``terrain`` in a Chebyshev brush. Skips structure footprints.

        Returns True if any cell changed.
        """
        radius = max(0, int(radius))
        changed = False
        for y in range(cy - radius, cy + radius + 1):
            for x in range(cx - radius, cx + radius + 1):
                if not self.in_bounds(x, y):
                    continue
                if max(abs(x - cx), abs(y - cy)) > radius:
                    continue
                cell = self.cells[y][x]
                if cell.feature in STRUCTURE_FEATURES:
                    continue
                if clear_features and cell.feature != FeatureType.NONE:
                    cell.feature = FeatureType.NONE
                    cell.deposit = 0
                    cell.growth_ticks = 0
                    cell.crop_kind = None
                    cell.tree_species = None
                    cell.icon_variant = None
                    changed = True
                if cell.terrain != terrain:
                    cell.terrain = terrain
                    self.mark_terrain_dirty(x, y)
                    changed = True
        if changed:
            self.terrain_revision += 1
        return changed

    def seed_forest(
        self,
        cx: int,
        cy: int,
        radius: int,
        rng: random.Random | None = None,
    ) -> bool:
        """Stamp a mixed forest: forest floor + mature trees (density by distance)."""
        rng = rng or random.Random()
        radius = max(0, int(radius))
        changed = False
        for y in range(cy - radius, cy + radius + 1):
            for x in range(cx - radius, cx + radius + 1):
                if not self.in_bounds(x, y):
                    continue
                dist = max(abs(x - cx), abs(y - cy))
                if dist > radius:
                    continue
                cell = self.cells[y][x]
                if cell.feature in STRUCTURE_FEATURES:
                    continue
                if is_water_terrain(cell.terrain):
                    continue
                # Clear light vegetation; keep existing trees.
                if cell.feature not in (
                    FeatureType.NONE,
                    FeatureType.TREE,
                    FeatureType.SAPLING,
                ):
                    cell.feature = FeatureType.NONE
                    cell.deposit = 0
                    cell.growth_ticks = 0
                    cell.crop_kind = None
                    cell.tree_species = None
                    cell.icon_variant = None
                    changed = True
                if cell.terrain != TerrainType.FOREST_FLOOR:
                    cell.terrain = TerrainType.FOREST_FLOOR
                    self.mark_terrain_dirty(x, y)
                    changed = True
                if cell.feature in (FeatureType.TREE, FeatureType.SAPLING):
                    continue
                chance = 0.9 if dist <= 0 else 0.75 if dist <= 1 else 0.55 if dist <= 2 else 0.35
                if radius > 0 and dist == radius:
                    chance *= 0.7
                if rng.random() >= chance:
                    continue
                species = pick_tree_species(rng)
                tree = resolve_tree(species)
                cell.feature = FeatureType.TREE
                cell.tree_species = species
                cell.deposit = tree.yield_amount
                cell.growth_ticks = 0
                cell.icon_variant = None
                changed = True
        if changed:
            self.terrain_revision += 1
        return changed

    def _smooth_height_region(
        self,
        lx0: int,
        ly0: int,
        lx1: int,
        ly1: int,
        *,
        passes: int = 2,
    ) -> None:
        """Laplacian smooth on a corner rectangle (inclusive)."""
        self.ensure_height_corners()
        for _ in range(max(1, passes)):
            nxt = [row[:] for row in self.height_corners]
            for ly in range(ly0, ly1 + 1):
                for lx in range(lx0, lx1 + 1):
                    total = self.height_corners[ly][lx]
                    n = 1
                    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        nx, ny = lx + dx, ly + dy
                        if 0 <= nx <= self.cols and 0 <= ny <= self.rows:
                            total += self.height_corners[ny][nx]
                            n += 1
                    # Blend toward neighbourhood mean (keeps centre bias of paint).
                    mean = total / n
                    cur = self.height_corners[ly][lx]
                    nxt[ly][lx] = cur * 0.35 + mean * 0.65
            for ly in range(ly0, ly1 + 1):
                for lx in range(lx0, lx1 + 1):
                    self.height_corners[ly][lx] = nxt[ly][lx]

    def bump_terrain(self) -> None:
        """Force a full terrain layer rebuild (generation / load)."""
        self.terrain_revision += 1
        self.terrain_dirty.clear()

    def mark_terrain_dirty(self, x: int, y: int, radius: int = 1) -> None:
        """Mark a cell and neighbours for incremental tile re-stitch."""
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                nx, ny = x + dx, y + dy
                if 0 <= nx < self.cols and 0 <= ny < self.rows:
                    self.terrain_dirty.add((nx, ny))

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    def generate(self) -> None:
        rng = random.Random(self.seed)
        self.cells = [
            [Cell(terrain=TerrainType.SOIL) for _ in range(self.cols)]
            for _ in range(self.rows)
        ]

        # Base terrain: coherent grass with soil pockets (value-noise blobs).
        self._paint_base_grass_soil(rng)

        # Valley floor / ridge layout, then a corner lake + meandering river.
        self._paint_valley_basin_landform(rng)
        self._paint_valley_lake_and_river(rng)

        # Compact grey rock outcrops (prefer high ground; never overwrite water).
        def _paint_rock(cell: Cell) -> None:
            if not is_water_terrain(cell.terrain):
                cell.terrain = TerrainType.ROCK

        self._place_clusters(
            rng,
            count=max(2, self.cols // 22),
            radius=3,
            density=0.65,
            apply=_paint_rock,
        )
        self._expand_terrain_patches(rng, TerrainType.ROCK, passes=2, chance=0.5)
        self._cull_isolated_terrain(TerrainType.ROCK, min_neighbours=2)
        self._cull_small_patches(TerrainType.ROCK, min_size=4)

        # Larger forest clearings: soil patches, then dense tree cover on them.
        forest_centres: list[tuple[int, int]] = []
        for _ in range(max(3, self.cols // 10)):
            cx = rng.randint(2, self.cols - 3)
            cy = rng.randint(2, self.rows - 3)
            forest_centres.append((cx, cy))
            for ny, nx in self.neighbourhood(cx, cy, radius=3):
                cell = self.cells[ny][nx]
                if is_water_terrain(cell.terrain):
                    continue
                # Soil under the canopy; keep rock outcrops if already placed.
                if cell.terrain != TerrainType.ROCK and rng.random() < 0.85:
                    cell.terrain = TerrainType.SOIL

        # Grow soil under forests into coherent clearings; smooth grass/meadow/soil.
        # Keep land cull gentle — aggressive grass absorption removes forest-edge
        # grass that deer breeding grounds require.
        self._expand_terrain_patches(rng, TerrainType.SOIL, passes=2, chance=0.5)
        self._expand_terrain_patches(rng, TerrainType.MEADOW, passes=1, chance=0.4)
        self._expand_terrain_patches(rng, TerrainType.GRASS, passes=1, chance=0.45)
        self._cull_isolated_terrain(TerrainType.SOIL, min_neighbours=1)
        self._cull_isolated_terrain(TerrainType.MEADOW, min_neighbours=1)
        self._cull_isolated_terrain(TerrainType.GRASS, min_neighbours=1)

        # Thin riparian strips on ~50% of land cells touching water.
        self._paint_riparian_strips(rng)

        for cx, cy in forest_centres:
            for ny, nx in self.neighbourhood(cx, cy, radius=3):
                cell = self.cells[ny][nx]
                if cell.terrain != TerrainType.SOIL:
                    continue
                if cell.feature != FeatureType.NONE:
                    continue
                # Dense core, thinner fringe.
                dist = max(abs(nx - cx), abs(ny - cy))
                chance = 0.9 if dist <= 1 else 0.7 if dist <= 2 else 0.45
                if rng.random() < chance:
                    species = pick_tree_species(rng)
                    tree = resolve_tree(species)
                    cell.feature = FeatureType.TREE
                    cell.tree_species = species
                    cell.deposit = tree.yield_amount

        # A few smaller mixed tree clumps on remaining plantable land.
        for _ in range(3):
            cx = rng.randint(1, self.cols - 2)
            cy = rng.randint(1, self.rows - 2)
            for ny, nx in self.neighbourhood(cx, cy, radius=1):
                cell = self.cells[ny][nx]
                if (
                    cell.feature == FeatureType.NONE
                    and cell.terrain in PLANTABLE_LAND
                    and rng.random() < 0.5
                ):
                    species = pick_tree_species(rng)
                    tree = resolve_tree(species)
                    cell.feature = FeatureType.TREE
                    cell.tree_species = species
                    cell.deposit = tree.yield_amount

        # Fallen wood on empty tiles beside trees (forest floor litter).
        self._seed_wood_near_trees(rng)

        # More scattered small rock deposits on soil/grass/meadow.
        placed_small = 0
        attempts = 0
        target_small = max(20, (self.cols * self.rows) // 320)
        while placed_small < target_small and attempts < 500:
            attempts += 1
            x = rng.randint(0, self.cols - 1)
            y = rng.randint(0, self.rows - 1)
            cell = self.cells[y][x]
            if (
                cell.feature == FeatureType.NONE
                and cell.terrain in PLANTABLE_LAND
            ):
                cell.feature = FeatureType.ROCK
                cell.deposit = rng.randint(ROCK_SMALL_MIN, ROCK_SMALL_MAX)
                placed_small += 1

        # Rock-terrain clusters mix mostly small deposits with some big ones.
        rock_tiles = [
            (x, y)
            for y in range(self.rows)
            for x in range(self.cols)
            if self.cells[y][x].terrain == TerrainType.ROCK
            and self.cells[y][x].feature == FeatureType.NONE
        ]
        rng.shuffle(rock_tiles)
        cluster_count = min(len(rock_tiles), max(6, int(round(len(rock_tiles) * 0.5))))
        big_count = int(round(cluster_count * 0.4))
        for i, (x, y) in enumerate(rock_tiles[:cluster_count]):
            cell = self.cells[y][x]
            cell.feature = FeatureType.ROCK
            if i < big_count:
                cell.deposit = rng.randint(ROCK_LARGE_MIN, ROCK_LARGE_MAX)
            else:
                cell.deposit = rng.randint(ROCK_SMALL_MIN, ROCK_SMALL_MAX)

        # A few starter berry bushes on grass.
        placed_bushes = 0
        attempts = 0
        while placed_bushes < 8 and attempts < 200:
            attempts += 1
            x = rng.randint(0, self.cols - 1)
            y = rng.randint(0, self.rows - 1)
            cell = self.cells[y][x]
            if cell.feature == FeatureType.NONE and cell.terrain == TerrainType.GRASS:
                cell.feature = FeatureType.BERRY_BUSH
                cell.deposit = BERRY_BUSH_YIELD
                placed_bushes += 1

        # Home near the centre-left so the starting area is clear.
        # Buildings occupy a square footprint; home_pos is the centre (glyph) cell.
        from settings import BUILDING_FOOTPRINT

        fp = max(1, int(BUILDING_FOOTPRINT))
        half = fp // 2
        home_cx = max(half, self.cols // 4)
        home_cy = min(max(half, self.rows // 2), self.rows - 1 - half)
        self.claim_structure_footprint(
            home_cx - half,
            home_cy - half,
            fp,
            fp,
            FeatureType.HOME,
        )
        self.home_pos = (home_cx, home_cy)

        # Hiring hall immediately to the right of the storehouse footprint.
        station_cx = home_cx + fp
        station_cy = home_cy
        if station_cx + half >= self.cols:
            station_cx = home_cx - fp
        self.claim_structure_footprint(
            station_cx - half,
            station_cy - half,
            fp,
            fp,
            FeatureType.WORKSTATION,
        )
        self.workstation_pos = (station_cx, station_cy)

        # Clear a small yard around home/workstation and choose a free start cell.
        clear_centres = [self.home_pos, self.workstation_pos]
        protected = {
            FeatureType.HOME,
            FeatureType.WORKSTATION,
            FeatureType.STRUCTURE_PAD,
        }
        for cx, cy in clear_centres:
            for ny, nx in self.neighbourhood(cx, cy, radius=half + 1):
                cell = self.cells[ny][nx]
                if cell.feature not in protected:
                    if cell.feature in (
                        FeatureType.TREE,
                        FeatureType.ROCK,
                        FeatureType.SAPLING,
                        FeatureType.MUSHROOM,
                        FeatureType.WOOD_BUSH,
                        FeatureType.BERRY_BUSH,
                        FeatureType.HERB,
                        FeatureType.WILD_CROP,
                        FeatureType.REED,
                    ):
                        cell.feature = FeatureType.NONE
                        cell.deposit = 0
                        cell.growth_ticks = 0
                        cell.crop_kind = None
                    if is_water_terrain(cell.terrain):
                        cell.terrain = TerrainType.GRASS
                    elif cell.terrain == TerrainType.RIPARIAN:
                        cell.terrain = TerrainType.GRASS

        start_candidates = [
            (nx, ny)
            for ny, nx in self.neighbourhood(home_cx, home_cy, radius=half + 1)
            if (nx, ny) not in (self.home_pos, self.workstation_pos)
            and self.cells[ny][nx].feature == FeatureType.NONE
            and not is_water_terrain(self.cells[ny][nx].terrain)
        ]
        if start_candidates:
            self.start_pos = start_candidates[0]
        else:
            self.start_pos = (home_cx, home_cy - half - 1 if home_cy > half else home_cy + half + 1)

        # Ensure start cell is walkable / empty.
        sx, sy = self.start_pos
        if self.in_bounds(sx, sy):
            self.cells[sy][sx].feature = FeatureType.NONE
            if is_water_terrain(self.cells[sy][sx].terrain):
                self.cells[sy][sx].terrain = TerrainType.GRASS
        self.update_forest_floor()
        self._paint_terrain_subclusters(rng)
        self._build_valley_heightfield()
        self.bump_terrain()

    def _seed_wood_near_trees(self, rng: random.Random) -> None:
        """Place fallen wood on empty tiles adjacent to trees (forest edges)."""
        plantable = SOIL_LIKE + (TerrainType.GRASS, TerrainType.MEADOW)
        tree_tiles = [
            (x, y)
            for y in range(self.rows)
            for x in range(self.cols)
            if self.cells[y][x].feature == FeatureType.TREE
        ]
        for tx, ty in tree_tiles:
            for ny, nx in self.neighbourhood(tx, ty, radius=1):
                if (nx, ny) == (tx, ty):
                    continue
                cell = self.cells[ny][nx]
                if (
                    cell.feature == FeatureType.NONE
                    and cell.terrain in plantable
                    and rng.random() < WOOD_BUSH_SEED_CHANCE
                ):
                    cell.feature = FeatureType.WOOD_BUSH
                    cell.deposit = WOOD_BUSH_YIELD

    def _paint_terrain_subclusters(self, rng: random.Random) -> None:
        """Carve small shade clusters inside each grass / meadow / soil patch.

        Gives seasonal washes and speckles non-uniform coverage instead of
        one flat mask per biome.
        """
        land = (
            TerrainType.GRASS,
            TerrainType.MEADOW,
            TerrainType.SOIL,
            TerrainType.FOREST_FLOOR,
        )
        next_id = 1
        for terrain in land:
            cells = {
                (x, y)
                for y in range(self.rows)
                for x in range(self.cols)
                if self.cells[y][x].terrain == terrain
            }
            for patch in self._connected_patches(cells):
                remaining = set(patch)
                while remaining:
                    sx, sy = remaining.pop()
                    target = rng.randint(2, 12)
                    cluster: list[tuple[int, int]] = [(sx, sy)]
                    frontier = [(sx, sy)]
                    while frontier and len(cluster) < target:
                        cx, cy = frontier.pop(rng.randrange(len(frontier)))
                        neighbours = [
                            (nx, ny)
                            for dx, dy in (
                                (0, -1),
                                (0, 1),
                                (-1, 0),
                                (1, 0),
                                (-1, -1),
                                (1, -1),
                                (-1, 1),
                                (1, 1),
                            )
                            for nx, ny in ((cx + dx, cy + dy),)
                            if (nx, ny) in remaining
                        ]
                        rng.shuffle(neighbours)
                        for nx, ny in neighbours[: rng.randint(1, 3)]:
                            if (nx, ny) not in remaining:
                                continue
                            remaining.discard((nx, ny))
                            cluster.append((nx, ny))
                            frontier.append((nx, ny))
                            if len(cluster) >= target:
                                break
                    shade = rng.uniform(0.28, 1.0)
                    # Bias a few clusters very light / very heavy for variety.
                    if rng.random() < 0.18:
                        shade = rng.uniform(0.15, 0.35)
                    elif rng.random() < 0.18:
                        shade = rng.uniform(0.82, 1.0)
                    for x, y in cluster:
                        cell = self.cells[y][x]
                        cell.terrain_cluster = next_id
                        cell.terrain_shade = shade
                    next_id += 1

    def update_forest_floor(self) -> None:
        """Mark only tree/sapling tiles as forest floor; clear bare litter.

        Runs on the same ≤8/year cadence as biodiversity / habitat refresh.
        Forest floor never spreads onto empty soil between trees.
        """
        changed = False
        for y in range(self.rows):
            for x in range(self.cols):
                cell = self.cells[y][x]
                has_tree = cell.feature in (FeatureType.TREE, FeatureType.SAPLING)
                if has_tree and cell.terrain == TerrainType.SOIL:
                    cell.terrain = TerrainType.FOREST_FLOOR
                    self.mark_terrain_dirty(x, y)
                    changed = True
                elif (
                    not has_tree
                    and cell.terrain == TerrainType.FOREST_FLOOR
                ):
                    cell.terrain = TerrainType.SOIL
                    self.mark_terrain_dirty(x, y)
                    changed = True
        if changed:
            self.terrain_revision += 1

    def _valley_axis_v(self, u: float) -> float:
        """Normalised valley centerline v for normalised u (SW lake → NE head)."""
        return 0.92 - u * 0.72 + math.sin(u * math.pi * 2.4) * 0.07

    def _valley_river_path(self) -> list[tuple[float, float]]:
        """Polyline from lake (t=0) to upstream head (t=1), in cell coordinates."""
        cols, rows = self.cols, self.rows
        steps = max(cols, rows) * 2
        path: list[tuple[float, float]] = []
        for i in range(steps + 1):
            t = i / steps
            u = 0.10 + t * 0.82
            v = 0.90 - t * 0.70 + math.sin(t * math.pi * 2.6) * 0.08
            v += math.sin(t * math.pi * 5.1 + 0.4) * 0.03
            path.append((u * (cols - 1), v * (rows - 1)))
        return path

    def _valley_lake_params(self) -> tuple[float, float, float, float]:
        cols, rows = self.cols, self.rows
        return (
            cols * 0.11,
            rows * 0.88,
            max(6.0, cols * 0.15),
            max(6.0, rows * 0.17),
        )

    def _nearest_on_valley_path(
        self, x: float, y: float
    ) -> tuple[float, float]:
        """Return (distance, t) for nearest point on ``valley_path`` (t: 0 lake → 1 head)."""
        path = self.valley_path
        if len(path) < 2:
            return 1e9, 0.0
        best = 1e9
        best_t = 0.0
        nseg = len(path) - 1
        for i in range(nseg):
            x0, y0 = path[i]
            x1, y1 = path[i + 1]
            seg_dx = x1 - x0
            seg_dy = y1 - y0
            seg_len2 = seg_dx * seg_dx + seg_dy * seg_dy
            if seg_len2 < 1e-6:
                continue
            tt = ((x - x0) * seg_dx + (y - y0) * seg_dy) / seg_len2
            tt = max(0.0, min(1.0, tt))
            px = x0 + seg_dx * tt
            py = y0 + seg_dy * tt
            d = math.hypot(x - px, y - py)
            if d < best:
                best = d
                best_t = (i + tt) / nseg
        return best, best_t

    def _in_lake(self, x: float, y: float, *, shore_scale: float = 1.0) -> bool:
        dx = (x - self.lake_cx) / max(1e-6, self.lake_rx * shore_scale)
        dy = (y - self.lake_cy) / max(1e-6, self.lake_ry * shore_scale)
        return math.hypot(dx, dy) <= 1.0

    def _channel_height(self, t: float, *, in_lake: bool) -> float:
        if in_lake:
            return float(HEIGHT_LAKE)
        return float(HEIGHT_LAKE) + (
            float(HEIGHT_RIVER_HEAD) - float(HEIGHT_LAKE)
        ) * max(0.0, min(1.0, t))

    def _valley_wall_rise(self, dist: float) -> float:
        """Height above the local channel from perpendicular distance (cells)."""
        # Keep the channel itself flat; start rising just outside the banks.
        d = max(0.0, dist - 0.85)
        rise = d * float(HEIGHT_VALLEY_RISE_PER_CELL)
        return min(float(HEIGHT_VALLEY_RISE_MAX), rise)

    def _build_valley_heightfield(self) -> None:
        """Corner heights: lake=0, river head=40→0 downstream, walls slope into channel."""
        cols, rows = self.cols, self.rows
        if not self.valley_path:
            self.valley_path = self._valley_river_path()
            self.lake_cx, self.lake_cy, self.lake_rx, self.lake_ry = self._valley_lake_params()

        corners = [[0.0] * (cols + 1) for _ in range(rows + 1)]
        for ly in range(rows + 1):
            for lx in range(cols + 1):
                wx = float(lx)
                wy = float(ly)
                in_lake = self._in_lake(wx, wy, shore_scale=1.05)
                dist, t = self._nearest_on_valley_path(wx, wy)
                base = self._channel_height(t, in_lake=in_lake)
                # Inside the lake bowl, stay at lake level.
                if in_lake:
                    corners[ly][lx] = base
                    continue
                # On/near the painted water channel: stay on the thalweg gradient.
                near_channel = dist <= 2.2
                if near_channel:
                    # Peek neighbouring cells — if mostly water, flatten to channel.
                    cx = min(cols - 1, max(0, int(math.floor(wx - 1e-6))))
                    cy = min(rows - 1, max(0, int(math.floor(wy - 1e-6))))
                    waterish = 0
                    for dy in (-1, 0):
                        for dx in (-1, 0):
                            nx, ny = cx + dx, cy + dy
                            if 0 <= nx < cols and 0 <= ny < rows:
                                if is_water_terrain(self.cells[ny][nx].terrain):
                                    waterish += 1
                    if waterish >= 2 or dist <= 1.35:
                        corners[ly][lx] = base
                        continue
                corners[ly][lx] = base + self._valley_wall_rise(dist)

        # Flatten water cells so lake/river surfaces read as level at local stage.
        for y in range(rows):
            for x in range(cols):
                if not is_water_terrain(self.cells[y][x].terrain):
                    continue
                in_lake = self.cells[y][x].terrain == TerrainType.WATER or self._in_lake(
                    x + 0.5, y + 0.5, shore_scale=1.08
                )
                _, t = self._nearest_on_valley_path(x + 0.5, y + 0.5)
                h = self._channel_height(t, in_lake=in_lake)
                for cy in (y, y + 1):
                    for cx in (x, x + 1):
                        corners[cy][cx] = h

        self.height_corners = corners

    def _paint_valley_basin_landform(self, rng: random.Random) -> None:
        """Bias land into a SW→NE river valley: soft floor, grassier ridges."""
        del rng  # deterministic from seed + coords
        cols, rows = self.cols, self.rows
        self.lake_cx, self.lake_cy, self.lake_rx, self.lake_ry = self._valley_lake_params()
        self.valley_path = self._valley_river_path()

        def _n(x: int, y: int, salt: int) -> float:
            n = (x * 374761393 + y * 668265263 + salt * 1274126177 + self.seed) & 0x7FFFFFFF
            return (n % 10007) / 10007.0

        for y in range(rows):
            for x in range(cols):
                u = x / max(1, cols - 1)
                v = y / max(1, rows - 1)
                axis_v = self._valley_axis_v(u)
                dist = abs(v - axis_v) / 0.20
                basin = math.hypot(u / 0.28, (1.0 - v) / 0.30)
                cell = self.cells[y][x]
                roll = _n(x, y, 3)
                if basin < 0.9:
                    cell.terrain = (
                        TerrainType.MEADOW if roll < 0.55 else TerrainType.SOIL
                    )
                elif dist < 0.65:
                    cell.terrain = (
                        TerrainType.SOIL if roll < 0.45 else TerrainType.MEADOW
                    )
                elif dist < 1.15:
                    if cell.terrain == TerrainType.SOIL and roll < 0.55:
                        cell.terrain = TerrainType.GRASS
                else:
                    if roll < 0.35:
                        cell.terrain = TerrainType.GRASS
                    elif roll > 0.92:
                        cell.terrain = TerrainType.ROCK

    def _paint_valley_lake_and_river(self, rng: random.Random) -> None:
        """Corner lake (WATER, freezes) + meandering river (RIVER, no freeze)."""
        cols, rows = self.cols, self.rows
        self.lake_cx, self.lake_cy, self.lake_rx, self.lake_ry = self._valley_lake_params()
        self.valley_path = self._valley_river_path()

        def _n(x: int, y: int, salt: int) -> float:
            n = (x * 374761393 + y * 668265263 + salt * 1274126177 + self.seed) & 0x7FFFFFFF
            return (n % 10007) / 10007.0

        # Lake body with noisy shore.
        for y in range(rows):
            for x in range(cols):
                dx = (x + 0.5 - self.lake_cx) / self.lake_rx
                dy = (y + 0.5 - self.lake_cy) / self.lake_ry
                r = math.hypot(dx, dy)
                shore = 0.82 + (_n(x, y, 9) - 0.5) * 0.28
                if r <= shore:
                    self.cells[y][x].terrain = TerrainType.WATER

        # Paint river channel (does not overwrite the lake).
        for y in range(rows):
            for x in range(cols):
                if self.cells[y][x].terrain == TerrainType.WATER:
                    continue
                best, best_t = self._nearest_on_valley_path(float(x), float(y))
                half_w = 1.15 + (1.0 - best_t) * 1.35 + (_n(x, y, 11) - 0.5) * 0.45
                if best <= half_w:
                    self.cells[y][x].terrain = TerrainType.RIVER

        self._expand_terrain_patches(rng, TerrainType.RIVER, passes=1, chance=0.35)
        # Keep lake cells as WATER if expansion spilled.
        for y in range(rows):
            for x in range(cols):
                if self.cells[y][x].terrain != TerrainType.RIVER:
                    continue
                if self._in_lake(x + 0.5, y + 0.5, shore_scale=0.95):
                    self.cells[y][x].terrain = TerrainType.WATER
        self._cull_isolated_terrain(TerrainType.RIVER, min_neighbours=2)
        self._cull_isolated_terrain(TerrainType.WATER, min_neighbours=2)
        self._cull_small_patches(TerrainType.RIVER, min_size=8)
        self._cull_small_patches(TerrainType.WATER, min_size=8)

    def _paint_base_grass_soil(self, rng: random.Random) -> None:
        """Fill the map with large grass / meadow / soil regions via coarse value noise."""
        # A few random influence points → smooth-ish regions without per-cell coin flips.
        blobs: list[tuple[float, float, float, TerrainType]] = []
        n_blobs = max(6, (self.cols * self.rows) // 40)
        for _ in range(n_blobs):
            bx = rng.uniform(0, self.cols)
            by = rng.uniform(0, self.rows)
            br = rng.uniform(2.5, 6.5)
            roll = rng.random()
            if roll < 0.30:
                kind = TerrainType.SOIL
            elif roll < 0.62:
                kind = TerrainType.MEADOW
            else:
                kind = TerrainType.GRASS
            blobs.append((bx, by, br, kind))

        for y in range(self.rows):
            for x in range(self.cols):
                soil_w = 0.0
                grass_w = 0.10
                meadow_w = 0.10
                for bx, by, br, kind in blobs:
                    d = ((x + 0.5 - bx) ** 2 + (y + 0.5 - by) ** 2) ** 0.5
                    if d >= br:
                        continue
                    w = (1.0 - d / br) ** 2
                    if kind == TerrainType.SOIL:
                        soil_w += w
                    elif kind == TerrainType.MEADOW:
                        meadow_w += w
                    else:
                        grass_w += w
                if soil_w >= grass_w and soil_w >= meadow_w:
                    self.cells[y][x].terrain = TerrainType.SOIL
                elif meadow_w >= grass_w:
                    self.cells[y][x].terrain = TerrainType.MEADOW
                else:
                    self.cells[y][x].terrain = TerrainType.GRASS

    def _paint_riparian_strips(self, rng: random.Random) -> None:
        """Convert ~50% of land cells that touch water into riparian strips."""
        shore_ok = (TerrainType.GRASS, TerrainType.MEADOW, TerrainType.SOIL, TerrainType.FOREST_FLOOR)
        to_paint: list[tuple[int, int]] = []
        for y in range(self.rows):
            for x in range(self.cols):
                cell = self.cells[y][x]
                if cell.terrain not in shore_ok:
                    continue
                touches_water = False
                for ny, nx in self.neighbourhood(x, y, radius=1):
                    if (nx, ny) == (x, y):
                        continue
                    if is_water_terrain(self.cells[ny][nx].terrain):
                        touches_water = True
                        break
                if touches_water and rng.random() < 0.5:
                    to_paint.append((x, y))
        for x, y in to_paint:
            self.cells[y][x].terrain = TerrainType.RIPARIAN

    def _place_clusters(
        self,
        rng: random.Random,
        count: int,
        radius: int,
        apply,
        density: float = 0.65,
    ) -> None:
        for _ in range(count):
            cx = rng.randint(radius, max(radius, self.cols - radius - 1))
            cy = rng.randint(radius, max(radius, self.rows - radius - 1))
            for ny, nx in self.neighbourhood(cx, cy, radius=radius):
                if rng.random() < density:
                    apply(self.cells[ny][nx])

    def _expand_terrain_patches(
        self,
        rng: random.Random,
        terrain: TerrainType,
        passes: int = 1,
        chance: float = 0.4,
    ) -> None:
        for _ in range(passes):
            to_paint: list[tuple[int, int]] = []
            for y in range(self.rows):
                for x in range(self.cols):
                    if self.cells[y][x].terrain == terrain:
                        continue
                    if terrain == TerrainType.ROCK and is_water_terrain(
                        self.cells[y][x].terrain
                    ):
                        continue
                    if is_water_terrain(terrain):
                        pass
                    elif is_water_terrain(self.cells[y][x].terrain):
                        continue
                    neighbours = list(self.neighbourhood(x, y, radius=1))
                    matching = sum(
                        1
                        for ny, nx in neighbours
                        if self.cells[ny][nx].terrain == terrain
                    )
                    if matching >= 3 and rng.random() < chance:
                        to_paint.append((x, y))
            for x, y in to_paint:
                self.cells[y][x].terrain = terrain

    def _cull_isolated_terrain(
        self, terrain: TerrainType, *, min_neighbours: int = 1
    ) -> None:
        """Remove 1-cell speckles of `terrain` that lack enough same-type neighbours."""
        fallback = {
            TerrainType.WATER: TerrainType.GRASS,
            TerrainType.RIVER: TerrainType.GRASS,
            TerrainType.ROCK: TerrainType.GRASS,
            TerrainType.SOIL: TerrainType.GRASS,
            TerrainType.MEADOW: TerrainType.GRASS,
            TerrainType.RIPARIAN: TerrainType.GRASS,
            TerrainType.GRASS: TerrainType.MEADOW,
        }[terrain]
        to_clear: list[tuple[int, int]] = []
        for y in range(self.rows):
            for x in range(self.cols):
                if self.cells[y][x].terrain != terrain:
                    continue
                matching = 0
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nx, ny = x + dx, y + dy
                    if self.in_bounds(nx, ny) and self.cells[ny][nx].terrain == terrain:
                        matching += 1
                if matching < min_neighbours:
                    to_clear.append((x, y))
        for x, y in to_clear:
            self.cells[y][x].terrain = self._majority_neighbour_terrain(
                x, y, exclude=terrain, fallback=fallback
            )

    def _majority_neighbour_terrain(
        self,
        x: int,
        y: int,
        *,
        exclude: TerrainType | None = None,
        fallback: TerrainType,
    ) -> TerrainType:
        """Pick the most common cardinal-neighbour terrain (for island fill-in)."""
        counts: dict[TerrainType, int] = {}
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nx, ny = x + dx, y + dy
            if not self.in_bounds(nx, ny):
                continue
            t = self.cells[ny][nx].terrain
            if exclude is not None and t == exclude:
                continue
            counts[t] = counts.get(t, 0) + 1
        if not counts:
            return fallback
        return max(counts.items(), key=lambda kv: kv[1])[0]

    def _cull_small_patches(self, terrain: TerrainType, *, min_size: int = 4) -> None:
        """Absorb connected components of ``terrain`` smaller than ``min_size``."""
        seen = [[False] * self.cols for _ in range(self.rows)]
        for y in range(self.rows):
            for x in range(self.cols):
                if seen[y][x] or self.cells[y][x].terrain != terrain:
                    continue
                # Flood-fill component.
                stack = [(x, y)]
                seen[y][x] = True
                patch: list[tuple[int, int]] = []
                while stack:
                    cx, cy = stack.pop()
                    patch.append((cx, cy))
                    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        nx, ny = cx + dx, cy + dy
                        if not self.in_bounds(nx, ny) or seen[ny][nx]:
                            continue
                        if self.cells[ny][nx].terrain != terrain:
                            continue
                        seen[ny][nx] = True
                        stack.append((nx, ny))
                if len(patch) >= min_size:
                    continue
                patch_set = set(patch)
                replacements: dict[tuple[int, int], TerrainType] = {}
                fallback = (
                    TerrainType.GRASS
                    if terrain != TerrainType.GRASS
                    else TerrainType.MEADOW
                )
                for px, py in patch:
                    counts: dict[TerrainType, int] = {}
                    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        nx, ny = px + dx, py + dy
                        if not self.in_bounds(nx, ny) or (nx, ny) in patch_set:
                            continue
                        t = self.cells[ny][nx].terrain
                        counts[t] = counts.get(t, 0) + 1
                    if counts:
                        replacements[(px, py)] = max(
                            counts.items(), key=lambda kv: kv[1]
                        )[0]
                    else:
                        replacements[(px, py)] = fallback
                for (px, py), t in replacements.items():
                    self.cells[py][px].terrain = t

    def reset(self) -> None:
        self._sprout_timer = NATURAL_SPROUT_INTERVAL
        self._sprout_rng.seed(self.seed + 99)
        self._mushroom_timer = MUSHROOM_TICK_INTERVAL
        self._berry_spread_timer = BERRY_SPREAD_INTERVAL
        self._herb_timer = HERB_TICK_INTERVAL
        self._forage_rng.seed(self.seed + 123)
        self.generate()

    # ------------------------------------------------------------------
    # Accessors & queries
    # ------------------------------------------------------------------
    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.cols and 0 <= y < self.rows

    def get_cell(self, x: int, y: int) -> Cell | None:
        if not self.in_bounds(x, y):
            return None
        return self.cells[y][x]

    def claim_structure_footprint(
        self,
        origin_x: int,
        origin_y: int,
        plot_w: int,
        plot_h: int,
        centre_feature: FeatureType,
    ) -> tuple[int, int]:
        """Clear a rectangular footprint; put glyph on centre, pads on the rest.

        Returns the centre cell coordinates.
        """
        w = max(1, plot_w)
        h = max(1, plot_h)
        cx = origin_x + w // 2
        cy = origin_y + h // 2
        for y in range(origin_y, origin_y + h):
            for x in range(origin_x, origin_x + w):
                cell = self.get_cell(x, y)
                if cell is None:
                    continue
                cell.feature = (
                    centre_feature
                    if (x, y) == (cx, cy)
                    else FeatureType.STRUCTURE_PAD
                )
                cell.deposit = 0
                cell.growth_ticks = 0
                cell.crop_kind = None
                cell.tree_species = None
                cell.icon_variant = None
                self.mark_terrain_dirty(x, y)
        return cx, cy

    def neighbourhood(self, x: int, y: int, radius: int) -> Iterator[tuple[int, int]]:
        """Yield (y, x) cells within Chebyshev distance `radius`, including centre."""
        for ny in range(y - radius, y + radius + 1):
            for nx in range(x - radius, x + radius + 1):
                if self.in_bounds(nx, ny):
                    yield ny, nx

    def is_adjacent_chebyshev(self, ax: int, ay: int, bx: int, by: int, radius: int = 1) -> bool:
        """True if cells are within Chebyshev (8-direction) distance `radius`."""
        return max(abs(ax - bx), abs(ay - by)) <= radius

    def is_walkable(self, x: int, y: int) -> bool:
        """Water/river is impassable; features never block movement in this prototype."""
        cell = self.get_cell(x, y)
        if cell is None:
            return False
        return not is_water_terrain(cell.terrain)

    def land_component_size(self, x: int, y: int, *, limit: int = 24) -> int:
        """How many walkable tiles are cardinally connected (capped). Isolates score 1."""
        if not self.is_walkable(x, y):
            return 0
        seen: set[tuple[int, int]] = {(x, y)}
        queue: deque[tuple[int, int]] = deque([(x, y)])
        while queue and len(seen) < limit:
            cx, cy = queue.popleft()
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                nx, ny = cx + dx, cy + dy
                if (nx, ny) in seen or not self.is_walkable(nx, ny):
                    continue
                seen.add((nx, ny))
                queue.append((nx, ny))
        return len(seen)

    def best_fish_shore(
        self, x: int, y: int, *, max_radius: int = 10
    ) -> tuple[int, int] | None:
        """Prefer mainland shore over tiny mid-water islets when leaving a catch."""
        best: tuple[int, int] | None = None
        best_key: tuple[int, int, int] | None = None  # (-size, radius, manhattan)
        for radius in range(0, max_radius + 1):
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    if max(abs(dx), abs(dy)) != radius:
                        continue
                    nx, ny = x + dx, y + dy
                    if not self.is_walkable(nx, ny):
                        continue
                    size = self.land_component_size(nx, ny)
                    key = (-size, radius, abs(dx) + abs(dy))
                    if best_key is None or key < best_key:
                        best_key = key
                        best = (nx, ny)
            # Early out once we found a large connected shore at this radius.
            if best is not None and best_key is not None and best_key[0] <= -24:
                return best
        return best

    def relocate_fish_deposit(
        self, x: int, y: int, *, reachable_from: tuple[int, int] | None = None
    ) -> tuple[int, int] | None:
        """Move a fish pile onto a better shore; prefer tiles reachable from `reachable_from`."""
        cell = self.get_cell(x, y)
        if cell is None or cell.fish_deposit <= 0:
            return None
        amount = cell.fish_deposit
        origin = reachable_from
        best: tuple[int, int] | None = None
        best_key: tuple[int, int, int] | None = None
        for radius in range(0, 12):
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    if max(abs(dx), abs(dy)) != radius:
                        continue
                    nx, ny = x + dx, y + dy
                    if not self.is_walkable(nx, ny):
                        continue
                    if origin is not None and self.find_path(origin, (nx, ny)) is None:
                        continue
                    size = self.land_component_size(nx, ny)
                    key = (-size, radius, abs(dx) + abs(dy))
                    if best_key is None or key < best_key:
                        best_key = key
                        best = (nx, ny)
            if best is not None and best_key is not None and best_key[0] <= -24:
                break
        if best is None:
            return None
        if best == (x, y):
            return best
        cell.fish_deposit = 0
        self.cells[best[1]][best[0]].fish_deposit += amount
        return best

    def next_step_toward(self, start: tuple[int, int], goal: tuple[int, int]) -> tuple[int, int] | None:
        """Return the next cell on a shortest walkable path (BFS), or None if unreachable."""
        path = self.find_path(start, goal)
        if not path:
            return None if start != goal else goal
        return path[0]

    def find_path(
        self, start: tuple[int, int], goal: tuple[int, int]
    ) -> list[tuple[int, int]] | None:
        """Shortest cardinal path from start→goal as cells after start (includes goal)."""
        if start == goal:
            return []
        if not self.is_walkable(*goal):
            return None

        sx, sy = start
        gx, gy = goal
        queue: deque[tuple[int, int]] = deque([(sx, sy)])
        came_from: dict[tuple[int, int], tuple[int, int] | None] = {(sx, sy): None}

        found = False
        while queue:
            cx, cy = queue.popleft()
            if (cx, cy) == (gx, gy):
                found = True
                break
            local: list[tuple[int, int]] = []
            rest: list[tuple[int, int]] = []
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                if abs(gx - cx) >= abs(gy - cy):
                    (local if dx != 0 else rest).append((dx, dy))
                else:
                    (local if dy != 0 else rest).append((dx, dy))
            for dx, dy in local + rest:
                nx, ny = cx + dx, cy + dy
                if (nx, ny) in came_from:
                    continue
                if not self.is_walkable(nx, ny):
                    continue
                came_from[(nx, ny)] = (cx, cy)
                queue.append((nx, ny))

        if not found:
            return None

        path: list[tuple[int, int]] = []
        cur: tuple[int, int] | None = (gx, gy)
        while cur is not None and cur != start:
            path.append(cur)
            cur = came_from[cur]
        path.reverse()
        return path

    # ------------------------------------------------------------------
    # Simulation ticks (growth, optional disturbance decay)
    # ------------------------------------------------------------------
    def tick(self, decay_per_tick: float = 0.0, day: float = 0.0) -> None:
        """Advance growth and gradual seasonal ecology for the calendar day."""
        self.tick_bulk(1, decay_per_tick=decay_per_tick, day=day)

    def tick_bulk(self, ticks: int, decay_per_tick: float = 0.0, day: float = 0.0) -> None:
        """Apply `ticks` ecology steps at once (for headless fast-forward)."""
        from balance_config import active_balance

        if ticks <= 0:
            return
        grow = trees_grow_factor(day)
        halt = growth_halted(day)
        grow_step = max(1, int(round(grow))) if grow > 0.05 else 0

        for y in range(self.rows):
            for x in range(self.cols):
                cell = self.cells[y][x]
                if grow_step > 0 and cell.feature == FeatureType.SAPLING:
                    cell.growth_ticks -= grow_step * ticks
                    if cell.growth_ticks <= 0:
                        tree = resolve_tree(cell.tree_species)
                        cell.feature = FeatureType.TREE
                        cell.tree_species = tree.key
                        cell.growth_ticks = 0
                        cell.deposit = tree.yield_amount
                elif grow_step > 0 and cell.feature == FeatureType.BERRY_BUSH and cell.growth_ticks > 0:
                    cell.growth_ticks -= grow_step * ticks
                    if cell.growth_ticks <= 0 and cell.deposit <= 0:
                        cell.deposit = BERRY_BUSH_YIELD
                        cell.growth_ticks = 0
                elif cell.feature == FeatureType.CROP_HERB and cell.growth_ticks > 0:
                    # Farm crops follow the calendar (growth_days), not ecology
                    # grow/freeze envelopes — otherwise they mature outside harvest.
                    grow_mult = disturbance_activity_multiplier(
                        effective_disturbance_at(self, x, y)
                    )
                    cell.growth_ticks = max(
                        0, cell.growth_ticks - max(0, int(round(ticks * grow_mult)))
                    )
                if cell.terrain == TerrainType.URBAN:
                    cell.disturbance = active_balance().get_float("DISTURBANCE_URBAN_LEVEL")
                elif cell.terrain == TerrainType.PATH:
                    cell.disturbance = active_balance().get_float("DISTURBANCE_PATH_LEVEL")
                elif decay_per_tick > 0 and cell.disturbance > 0:
                    cell.disturbance = max(0.0, cell.disturbance - decay_per_tick * ticks)

        # Seasonal spawn/despawn timers: fire the same number of times as real ticks.
        def _drain_timer(attr: str, interval: int, callback) -> None:
            remaining = ticks
            interval = max(1, interval)
            while remaining > 0:
                left = max(0, int(getattr(self, attr)))
                if left <= 0:
                    setattr(self, attr, interval)
                    callback(day)
                    remaining -= 1
                    continue
                if left > remaining:
                    setattr(self, attr, left - remaining)
                    return
                remaining -= left
                setattr(self, attr, interval)
                callback(day)

        if halt:
            _drain_timer("_mushroom_timer", MUSHROOM_TICK_INTERVAL, self._tick_mushrooms_seasonal)
            _drain_timer("_herb_timer", HERB_TICK_INTERVAL, self._tick_herbs_seasonal)
            _drain_timer("_berry_spread_timer", BERRY_SPREAD_INTERVAL, self._tick_berries_seasonal)
            return

        spread = trees_spread_factor(day)
        if spread > 0.05:
            sprout_interval = max(30, int(NATURAL_SPROUT_INTERVAL / max(0.2, spread)))

            def _sprout(_day: float) -> None:
                if self._sprout_rng.random() < spread:
                    self._try_natural_sprouts()

            _drain_timer("_sprout_timer", sprout_interval, _sprout)
        else:
            self._sprout_timer = max(0, self._sprout_timer - ticks)

        _drain_timer("_mushroom_timer", MUSHROOM_TICK_INTERVAL, self._tick_mushrooms_seasonal)
        _drain_timer("_berry_spread_timer", BERRY_SPREAD_INTERVAL, self._tick_berries_seasonal)
        _drain_timer("_herb_timer", HERB_TICK_INTERVAL, self._tick_herbs_seasonal)

    def _tick_herbs_seasonal(self, day: float) -> None:
        """Wild crop patches on meadow / grass / soil by crop preference."""
        wild_n: dict[TerrainType, int] = {}
        total_n: dict[TerrainType, int] = {}
        terrains = tuple(WILD_CROPS_BY_TERRAIN.keys()) + (TerrainType.RIPARIAN,)
        for terrain in terrains:
            w, t = self._wild_plant_counts(terrain)
            wild_n[terrain] = w
            total_n[terrain] = t

        def room(terrain: TerrainType) -> bool:
            tot = total_n.get(terrain, 0)
            if tot <= 0:
                return False
            return wild_n[terrain] < int(tot * WILD_PLANT_MAX_FRACTION)

        for y in range(self.rows):
            for x in range(self.cols):
                cell = self.cells[y][x]
                if cell.feature in (FeatureType.HERB, FeatureType.WILD_CROP, FeatureType.REED):
                    if self._forage_rng.random() < herb_despawn_rate(day, x, y):
                        terrain = cell.terrain
                        cell.feature = FeatureType.NONE
                        cell.deposit = 0
                        cell.growth_ticks = 0
                        cell.crop_kind = None
                        if terrain in wild_n:
                            wild_n[terrain] = max(0, wild_n[terrain] - 1)
                elif (
                    cell.feature == FeatureType.NONE
                    and cell.terrain == TerrainType.RIPARIAN
                    and room(TerrainType.RIPARIAN)
                    and self._forage_rng.random()
                    < herb_spawn_rate(day, x, y)
                    * 0.55
                    * disturbance_activity_multiplier(
                        effective_disturbance_at(self, x, y)
                    )
                ):
                    cell.feature = FeatureType.REED
                    wild_n[TerrainType.RIPARIAN] = wild_n.get(TerrainType.RIPARIAN, 0) + 1
                elif (
                    cell.feature == FeatureType.NONE
                    and cell.terrain in WILD_CROPS_BY_TERRAIN
                    and room(cell.terrain)
                    and self._forage_rng.random()
                    < herb_spawn_rate(day, x, y)
                    * 0.55
                    * disturbance_activity_multiplier(
                        effective_disturbance_at(self, x, y)
                    )
                ):
                    crops = WILD_CROPS_BY_TERRAIN[cell.terrain]
                    crop_key = self._forage_rng.choice(crops)
                    self._plant_wild_crop_patch(
                        x, y, crop_key, wild_n=wild_n, total_n=total_n
                    )

    def _plant_wild_crop_patch(
        self,
        x: int,
        y: int,
        crop_key: str,
        *,
        wild_n: dict[TerrainType, int] | None = None,
        total_n: dict[TerrainType, int] | None = None,
    ) -> None:
        """Place a small contiguous wild-crop patch centred near (x, y)."""
        if not self.plant_wild_crop(x, y, crop_key, wild_n=wild_n, total_n=total_n):
            return
        extras = self._forage_rng.randint(1, 4)
        placed = 0
        candidates = [
            (nx, ny)
            for ny, nx in self.neighbourhood(x, y, radius=2)
            if (nx, ny) != (x, y)
        ]
        self._forage_rng.shuffle(candidates)
        for nx, ny in candidates:
            if placed >= extras:
                break
            if self._forage_rng.random() > 0.55:
                continue
            if self.plant_wild_crop(nx, ny, crop_key, wild_n=wild_n, total_n=total_n):
                placed += 1

    def _tick_berries_seasonal(self, day: float) -> None:
        # Despawn existing bushes gradually.
        bushes = [
            (x, y)
            for y in range(self.rows)
            for x in range(self.cols)
            if self.cells[y][x].feature == FeatureType.BERRY_BUSH
        ]
        for bx, by in bushes:
            if self._forage_rng.random() < berry_despawn_rate(day, bx, by):
                cell = self.cells[by][bx]
                cell.feature = FeatureType.NONE
                cell.deposit = 0
                cell.growth_ticks = 0

        wild, total = self._wild_plant_counts(TerrainType.GRASS)
        limit = int(total * WILD_PLANT_MAX_FRACTION)
        if total <= 0 or wild >= limit:
            return
        for y in range(self.rows):
            for x in range(self.cols):
                if wild >= limit:
                    return
                cell = self.cells[y][x]
                if (
                    cell.feature == FeatureType.NONE
                    and cell.terrain == TerrainType.GRASS
                    and self._forage_rng.random()
                    < berry_spawn_rate(day, x, y)
                    * disturbance_activity_multiplier(
                        effective_disturbance_at(self, x, y)
                    )
                ):
                    cell.feature = FeatureType.BERRY_BUSH
                    cell.deposit = BERRY_BUSH_YIELD
                    cell.growth_ticks = 0
                    wild += 1

    def _tick_mushrooms_seasonal(self, day: float) -> None:
        # Winter: wipe immediately (also covers any leftovers mid-tick).
        if season_for_day(int(day)) == Season.WINTER:
            self.clear_mushrooms()
            return

        existing = [
            (x, y)
            for y in range(self.rows)
            for x in range(self.cols)
            if self.cells[y][x].feature == FeatureType.MUSHROOM
        ]
        for mx, my in existing:
            if self._forage_rng.random() < mushroom_despawn_rate(day, mx, my):
                cell = self.cells[my][mx]
                cell.feature = FeatureType.NONE
                cell.deposit = 0
                continue
            # Seasonal spread while mushrooms are peaking.
            for ny, nx in self.neighbourhood(mx, my, radius=1):
                if (nx, ny) == (mx, my):
                    continue
                cell = self.cells[ny][nx]
                if (
                    cell.feature == FeatureType.NONE
                    and cell.terrain in SOIL_LIKE
                    and self._forage_rng.random()
                    < MUSHROOM_SPREAD_CHANCE
                    * mushroom_spawn_rate(day, nx, ny)
                    * 20.0
                    * disturbance_activity_multiplier(
                        effective_disturbance_at(self, nx, ny)
                    )
                ):
                    cell.feature = FeatureType.MUSHROOM

        for y in range(self.rows):
            for x in range(self.cols):
                if self.cells[y][x].feature != FeatureType.TREE:
                    continue
                for ny, nx in self.neighbourhood(x, y, radius=1):
                    if (nx, ny) == (x, y):
                        continue
                    cell = self.cells[ny][nx]
                    if (
                        cell.feature == FeatureType.NONE
                        and cell.terrain in SOIL_LIKE
                        and self._forage_rng.random()
                        < mushroom_spawn_rate(day, nx, ny)
                        * disturbance_activity_multiplier(
                            effective_disturbance_at(self, nx, ny)
                        )
                    ):
                        cell.feature = FeatureType.MUSHROOM

        # Autumn fallen wood beside trees (independent of mushrooms).
        for y in range(self.rows):
            for x in range(self.cols):
                if self.cells[y][x].feature != FeatureType.TREE:
                    continue
                for ny, nx in self.neighbourhood(x, y, radius=1):
                    if (nx, ny) == (x, y):
                        continue
                    cell = self.cells[ny][nx]
                    if (
                        cell.feature == FeatureType.NONE
                        and cell.terrain in SOIL_LIKE
                        and self._forage_rng.random() < wood_bush_spawn_rate(day, nx, ny)
                    ):
                        cell.feature = FeatureType.WOOD_BUSH
                        cell.deposit = WOOD_BUSH_YIELD

    def clear_mushrooms(self) -> None:
        """Remove mushrooms and fallen wood (called at winter onset)."""
        for y in range(self.rows):
            for x in range(self.cols):
                cell = self.cells[y][x]
                if cell.feature in (FeatureType.MUSHROOM, FeatureType.WOOD_BUSH):
                    cell.feature = FeatureType.NONE
                    cell.deposit = 0

    def _wild_plant_counts(self, terrain: TerrainType) -> tuple[int, int]:
        """Return (wild plant tiles, total tiles) for a terrain type."""
        total = 0
        wild = 0
        for y in range(self.rows):
            for x in range(self.cols):
                cell = self.cells[y][x]
                if cell.terrain != terrain:
                    continue
                total += 1
                if cell.feature in (
                    FeatureType.WILD_CROP,
                    FeatureType.HERB,
                    FeatureType.BERRY_BUSH,
                    FeatureType.REED,
                ):
                    wild += 1
        return wild, total

    def _wild_plant_room(
        self,
        terrain: TerrainType,
        *,
        wild_n: dict[TerrainType, int] | None = None,
        total_n: dict[TerrainType, int] | None = None,
    ) -> bool:
        """True while wild plants cover less than WILD_PLANT_MAX_FRACTION of terrain."""
        if wild_n is not None and total_n is not None:
            tot = total_n.get(terrain, 0)
            return tot > 0 and wild_n.get(terrain, 0) < int(tot * WILD_PLANT_MAX_FRACTION)
        wild, total = self._wild_plant_counts(terrain)
        if total <= 0:
            return False
        return wild < int(total * WILD_PLANT_MAX_FRACTION)

    def _try_natural_sprouts(self) -> None:
        """Patches of 4+ trees have a 1/8 chance to sprout a sapling on an adjacent empty cell."""
        for patch in self.tree_patches():
            if len(patch) < NATURAL_SPROUT_MIN_PATCH:
                continue
            if self._sprout_rng.random() > NATURAL_SPROUT_CHANCE:
                continue
            candidates: list[tuple[int, int]] = []
            patch_set = set(patch)
            for tx, ty in patch:
                for ny, nx in self.neighbourhood(tx, ty, radius=1):
                    if (nx, ny) in patch_set:
                        continue
                    cell = self.cells[ny][nx]
                    if cell.feature == FeatureType.NONE and cell.terrain in PLANTABLE_LAND:
                        candidates.append((nx, ny))
            if not candidates:
                continue
            sx, sy = self._sprout_rng.choice(candidates)
            if self._sprout_rng.random() > disturbance_activity_multiplier(
                effective_disturbance_at(self, sx, sy)
            ):
                continue
            # Inherit a species from the patch when possible.
            species = None
            for ny, nx in self.neighbourhood(sx, sy, radius=2):
                ncell = self.cells[ny][nx]
                if ncell.feature in (FeatureType.TREE, FeatureType.SAPLING) and ncell.tree_species:
                    species = ncell.tree_species
                    break
            self.plant_sapling(sx, sy, species=species)

    def plant_sapling(self, x: int, y: int, species: str | None = None) -> bool:
        cell = self.get_cell(x, y)
        if cell is None:
            return False
        if cell.feature != FeatureType.NONE:
            return False
        if cell.terrain not in PLANTABLE_LAND:
            return False
        tree = resolve_tree(species)
        cell.feature = FeatureType.SAPLING
        cell.tree_species = tree.key
        cell.growth_ticks = growth_ticks_for(tree)
        cell.deposit = 0
        return True

    def plant_berry_bush(self, x: int, y: int) -> bool:
        cell = self.get_cell(x, y)
        if cell is None or cell.feature != FeatureType.NONE:
            return False
        if cell.terrain != TerrainType.GRASS:
            return False
        if not self._wild_plant_room(TerrainType.GRASS):
            return False
        cell.feature = FeatureType.BERRY_BUSH
        cell.deposit = BERRY_BUSH_YIELD
        cell.growth_ticks = 0
        return True

    def plant_herb(self, x: int, y: int, crop_key: str = "sage") -> bool:
        """Legacy alias for planting a single wild crop plant."""
        return self.plant_wild_crop(x, y, crop_key)

    def plant_wild_crop(
        self,
        x: int,
        y: int,
        crop_key: str,
        *,
        wild_n: dict[TerrainType, int] | None = None,
        total_n: dict[TerrainType, int] | None = None,
    ) -> bool:
        cell = self.get_cell(x, y)
        if cell is None or cell.feature != FeatureType.NONE:
            return False
        allowed = WILD_CROPS_BY_TERRAIN.get(cell.terrain)
        if not allowed:
            return False
        if crop_key not in CROP_BY_KEY:
            crop_key = allowed[0]
        if crop_key not in allowed:
            return False
        if not self._wild_plant_room(cell.terrain, wild_n=wild_n, total_n=total_n):
            return False
        cell.feature = FeatureType.WILD_CROP
        cell.crop_kind = crop_key
        cell.deposit = 0
        cell.growth_ticks = 0
        if wild_n is not None:
            wild_n[cell.terrain] = wild_n.get(cell.terrain, 0) + 1
        return True

    def plough_tile(self, x: int, y: int) -> bool:
        """Turn a field tile into bare soil ready for sowing."""
        cell = self.get_cell(x, y)
        if cell is None:
            return False
        if is_water_terrain(cell.terrain) or cell.terrain == TerrainType.ROCK:
            return False
        if cell.feature in (
            FeatureType.HOME,
            FeatureType.WORKSTATION,
            FeatureType.FORESTER,
            FeatureType.MASON,
            FeatureType.HUNTER,
            FeatureType.FORAGER,
            FeatureType.FISHER,
            FeatureType.FARM,
            FeatureType.CONSTRUCTION_SITE,
            FeatureType.STRUCTURE_PAD,
        ):
            return False
        # Legacy Field marker on origin: clear it when ploughing that tile.
        if cell.terrain in SOIL_LIKE and cell.feature in (
            FeatureType.NONE,
            FeatureType.FIELD,
        ):
            if cell.feature == FeatureType.FIELD:
                cell.feature = FeatureType.NONE
                cell.deposit = 0
                cell.growth_ticks = 0
                cell.crop_kind = None
                return True
            return False
        cell.terrain = TerrainType.SOIL
        cell.feature = FeatureType.NONE
        cell.growth_ticks = 0
        cell.deposit = 0
        cell.crop_kind = None
        self.mark_terrain_dirty(x, y)
        return True

    def sow_crop(self, x: int, y: int, crop_key: str, growth_ticks: int) -> bool:
        """Sow crop seeds on ploughed soil."""
        cell = self.get_cell(x, y)
        if cell is None or cell.feature != FeatureType.NONE:
            return False
        if cell.terrain not in SOIL_LIKE:
            return False
        if crop_key not in CROP_BY_KEY:
            return False
        cell.feature = FeatureType.CROP_HERB
        cell.crop_kind = crop_key
        cell.growth_ticks = max(1, growth_ticks)
        cell.deposit = 0
        return True

    def sow_herb_crop(self, x: int, y: int) -> bool:
        """Legacy: sow sage with default spring growth."""
        from seasons import TICKS_PER_DAY

        crop = CROP_BY_KEY["sage"]
        return self.sow_crop(x, y, crop.key, crop.growth_days * TICKS_PER_DAY)

    def crop_herb_ready(self, x: int, y: int) -> bool:
        cell = self.get_cell(x, y)
        return (
            cell is not None
            and cell.feature == FeatureType.CROP_HERB
            and cell.growth_ticks <= 0
        )

    def harvest_crop_herb(self, x: int, y: int) -> str | None:
        """Harvest a ready farm crop; returns crop_kind or None."""
        cell = self.get_cell(x, y)
        if cell is None or cell.feature != FeatureType.CROP_HERB:
            return None
        if cell.growth_ticks > 0:
            return None
        kind = cell.crop_kind or "sage"
        cell.feature = FeatureType.NONE
        cell.growth_ticks = 0
        cell.crop_kind = None
        return kind

    def harvest_mushroom(self, x: int, y: int) -> bool:
        cell = self.get_cell(x, y)
        if cell is None or cell.feature != FeatureType.MUSHROOM:
            return False
        cell.feature = FeatureType.NONE
        return True

    def harvest_wood_bush(self, x: int, y: int) -> int:
        cell = self.get_cell(x, y)
        if cell is None or cell.feature != FeatureType.WOOD_BUSH or cell.deposit <= 0:
            return 0
        taken = min(1, cell.deposit)
        cell.deposit -= taken
        if cell.deposit <= 0:
            cell.feature = FeatureType.NONE
        return taken

    def harvest_berries(self, x: int, y: int, amount: int = 1) -> int:
        cell = self.get_cell(x, y)
        if cell is None or cell.feature != FeatureType.BERRY_BUSH or cell.deposit <= 0:
            return 0
        taken = min(amount, cell.deposit)
        cell.deposit -= taken
        if cell.deposit <= 0:
            cell.growth_ticks = BERRY_REGEN_TICKS
        return taken

    def harvest_herb(self, x: int, y: int) -> str | None:
        """Harvest wild crop/herb/reed; returns produce key or crop kind."""
        cell = self.get_cell(x, y)
        if cell is None:
            return None
        if cell.feature == FeatureType.REED:
            cell.feature = FeatureType.NONE
            return "reeds"
        if cell.feature == FeatureType.HERB:
            cell.feature = FeatureType.NONE
            cell.crop_kind = None
            return "sage"
        if cell.feature != FeatureType.WILD_CROP:
            return None
        kind = cell.crop_kind or "sage"
        cell.feature = FeatureType.NONE
        cell.crop_kind = None
        return kind

    def harvest_reed(self, x: int, y: int) -> bool:
        cell = self.get_cell(x, y)
        if cell is None or cell.feature != FeatureType.REED:
            return False
        cell.feature = FeatureType.NONE
        return True

    def remove_feature(self, x: int, y: int) -> FeatureType | None:
        cell = self.get_cell(x, y)
        if cell is None or cell.feature == FeatureType.NONE:
            return None
        removed = cell.feature
        cell.feature = FeatureType.NONE
        cell.growth_ticks = 0
        cell.deposit = 0
        cell.crop_kind = None
        return removed

    def harvest_wood(self, x: int, y: int, amount: int = 1) -> int:
        """Take up to `amount` from a tree deposit. Removes tree when empty."""
        cell = self.get_cell(x, y)
        if cell is None or cell.feature != FeatureType.TREE or cell.deposit <= 0:
            return 0
        taken = min(amount, cell.deposit)
        cell.deposit -= taken
        if cell.deposit <= 0:
            cell.feature = FeatureType.NONE
            cell.deposit = 0
            cell.growth_ticks = 0
            cell.tree_species = None
            cell.icon_variant = None
        return taken

    def tree_yield_key(self, x: int, y: int) -> str:
        cell = self.get_cell(x, y)
        if cell is None:
            return "wood"
        return resolve_tree(cell.tree_species).yield_key

    def harvest_rock(self, x: int, y: int, amount: int = 1) -> int:
        """Take up to `amount` rock from a rock deposit. Removes feature when empty."""
        cell = self.get_cell(x, y)
        if cell is None or cell.feature != FeatureType.ROCK or cell.deposit <= 0:
            return 0
        taken = min(amount, cell.deposit)
        cell.deposit -= taken
        if cell.deposit <= 0:
            cell.feature = FeatureType.NONE
            cell.deposit = 0
            cell.growth_ticks = 0
        return taken

    def harvest_meat(self, x: int, y: int, amount: int = 1) -> int:
        """Take meat left on a cell after hunting."""
        cell = self.get_cell(x, y)
        if cell is None or cell.meat_deposit <= 0:
            return 0
        taken = min(amount, cell.meat_deposit)
        cell.meat_deposit -= taken
        return taken

    def add_meat_deposit(self, x: int, y: int, amount: int) -> None:
        cell = self.get_cell(x, y)
        if cell is None:
            return
        cell.meat_deposit += amount

    def harvest_fish(self, x: int, y: int, amount: int = 1) -> int:
        cell = self.get_cell(x, y)
        if cell is None or cell.fish_deposit <= 0:
            return 0
        taken = min(amount, cell.fish_deposit)
        cell.fish_deposit -= taken
        return taken

    def add_fish_deposit(self, x: int, y: int, amount: int) -> tuple[int, int] | None:
        """Leave caught fish on mainland shore (avoid mid-lake islets). Returns deposit tile."""
        shore = self.best_fish_shore(x, y)
        if shore is not None:
            sx, sy = shore
            self.cells[sy][sx].fish_deposit += amount
            return shore
        cell = self.get_cell(x, y)
        if cell is None:
            return None
        cell.fish_deposit += amount
        return (x, y)

    def tree_cells(self) -> list[tuple[int, int]]:
        return [
            (x, y)
            for y in range(self.rows)
            for x in range(self.cols)
            if self.cells[y][x].feature == FeatureType.TREE
        ]

    def forest_cells(self) -> list[tuple[int, int]]:
        """Tiles with a mature tree or sapling (wildlife forest patches)."""
        return [
            (x, y)
            for y in range(self.rows)
            for x in range(self.cols)
            if self.cells[y][x].feature in (FeatureType.TREE, FeatureType.SAPLING)
        ]

    def water_cells(self) -> list[tuple[int, int]]:
        return [
            (x, y)
            for y in range(self.rows)
            for x in range(self.cols)
            if is_water_terrain(self.cells[y][x].terrain)
        ]

    def tree_patches(self) -> list[list[tuple[int, int]]]:
        """Connected components of mature trees (8-connected / Chebyshev)."""
        return self._connected_patches(set(self.tree_cells()))

    def forest_patches(self) -> list[list[tuple[int, int]]]:
        """Connected forest: tree or sapling tiles (8-connected)."""
        return self._connected_patches(set(self.forest_cells()))

    def meadow_patches(self) -> list[list[tuple[int, int]]]:
        """Connected meadow terrain patches (8-connected)."""
        cells = {
            (x, y)
            for y in range(self.rows)
            for x in range(self.cols)
            if self.cells[y][x].terrain == TerrainType.MEADOW
        }
        return self._connected_patches(cells)

    def water_patches(self) -> list[list[tuple[int, int]]]:
        """Connected components of water cells."""
        return self._connected_patches(set(self.water_cells()))

    def _connected_patches(
        self, cells: set[tuple[int, int]]
    ) -> list[list[tuple[int, int]]]:
        patches: list[list[tuple[int, int]]] = []
        seen: set[tuple[int, int]] = set()
        for start in cells:
            if start in seen:
                continue
            stack = [start]
            seen.add(start)
            patch: list[tuple[int, int]] = []
            while stack:
                cx, cy = stack.pop()
                patch.append((cx, cy))
                for ny, nx in self.neighbourhood(cx, cy, radius=1):
                    pos = (nx, ny)
                    if pos in cells and pos not in seen:
                        seen.add(pos)
                        stack.append(pos)
            patches.append(patch)
        return patches

    def habitat_cells_near_trees(self) -> list[tuple[int, int]]:
        """Walkable cells within 1 square of at least one tree."""
        habitat: set[tuple[int, int]] = set()
        for tx, ty in self.tree_cells():
            for ny, nx in self.neighbourhood(tx, ty, radius=1):
                if self.is_walkable(nx, ny):
                    habitat.add((nx, ny))
        return list(habitat)

    def apply_disturbance(self, x: int, y: int) -> None:
        """Raise disturbance at the target cell and lightly on neighbours."""
        self._apply_disturbance_at(
            x,
            y,
            boost_key="DISTURBANCE_INTERACTION_BOOST",
            spread_key="DISTURBANCE_NEIGHBOUR_SPREAD",
        )

    def apply_extraction_disturbance(self, x: int, y: int) -> None:
        """Stronger, longer-lasting disturbance from harvest/hunt/farm work."""
        self._apply_disturbance_at(
            x,
            y,
            boost_key="DISTURBANCE_EXTRACTION_BOOST",
            spread_key="DISTURBANCE_EXTRACTION_SPREAD",
        )

    def sync_hardscape_disturbance(self) -> None:
        """Apply constant urban/path disturbance floors immediately after terrain paint."""
        from balance_config import active_balance

        bal = active_balance()
        urban = bal.get_float("DISTURBANCE_URBAN_LEVEL")
        path = bal.get_float("DISTURBANCE_PATH_LEVEL")
        for y in range(self.rows):
            for x in range(self.cols):
                cell = self.cells[y][x]
                if cell.terrain == TerrainType.URBAN:
                    cell.disturbance = urban
                elif cell.terrain == TerrainType.PATH:
                    cell.disturbance = path

    def _apply_disturbance_at(
        self,
        x: int,
        y: int,
        *,
        boost_key: str,
        spread_key: str,
    ) -> None:
        from balance_config import active_balance

        bal = active_balance()
        dmax = bal.get_float("DISTURBANCE_MAX")
        boost = bal.get_float(boost_key)
        spread = bal.get_float(spread_key)
        cell = self.get_cell(x, y)
        if cell is None:
            return
        if cell.terrain == TerrainType.URBAN:
            cell.disturbance = max(cell.disturbance, bal.get_float("DISTURBANCE_URBAN_LEVEL"))
            return
        if cell.terrain == TerrainType.PATH:
            cell.disturbance = max(cell.disturbance, bal.get_float("DISTURBANCE_PATH_LEVEL"))
            return
        cell.disturbance = min(dmax, cell.disturbance + boost)
        spread_radius = max(1, bal.get_int("DISTURBANCE_RADIUS"))
        for ny, nx in self.neighbourhood(x, y, radius=spread_radius):
            if (nx, ny) == (x, y):
                continue
            dist = max(abs(nx - x), abs(ny - y))
            amount = spread / float(dist)
            ncell = self.cells[ny][nx]
            if ncell.terrain == TerrainType.URBAN:
                ncell.disturbance = max(
                    ncell.disturbance, bal.get_float("DISTURBANCE_URBAN_LEVEL")
                )
            elif ncell.terrain == TerrainType.PATH:
                ncell.disturbance = max(
                    ncell.disturbance, bal.get_float("DISTURBANCE_PATH_LEVEL")
                )
            else:
                ncell.disturbance = min(dmax, ncell.disturbance + amount)
