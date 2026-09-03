"""World grid: terrain, features, generation, and neighbourhood queries.

Interaction policy
------------------
The player interacts only with the cell they currently stand on (press E).
Mouse drag draws rectangular task areas for hired villagers.

Future extension points:
- habitat connectivity graphs
- GIS-derived terrain import

Soil fertility and weeds are per-cell. Soil moisture is a sampled environmental
grid. Erosion potential is a prebaked
slope grid on ``environment.EnvMaps``. Disturbance is a live per-cell field
(urban floors mixed with path-traffic wear).
"""

from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass, field
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
    berry_fruiting,
    growth_halted,
    herb_despawn_rate,
    herb_spawn_rate,
    local_day,
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
    BERRY_INITIAL_COUNT,
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
from wild_species import (
    WILD_BY_KEY,
    non_crop_on_terrain,
    resolve_species,
    spawn_group_leader,
    species_despawn_rate,
    species_spawn_rate,
    species_environment_suitability,
    environment_allows_establishment,
    environmental_mortality_rate,
    normalize_temperature_c,
    WILD_PROPAGULE_NEIGHBOUR_BONUS,
    WILD_PROPAGULE_MAX_MULTIPLIER,
    format_environment_debug,
    wild_crops_by_terrain,
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
    FOREST_FLOOR = auto()  # darker litter under mature trees (not saplings alone)
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
# Built from ``wild_species.WILD_SPECIES`` — edit that catalogue to add crops.
def _wild_crops_map() -> dict[TerrainType, tuple[str, ...]]:
    out: dict[TerrainType, tuple[str, ...]] = {}
    for terrain_name, crops in wild_crops_by_terrain().items():
        try:
            out[TerrainType[terrain_name]] = crops
        except KeyError:
            continue
    return out


WILD_CROPS_BY_TERRAIN: dict[TerrainType, tuple[str, ...]] = _wild_crops_map()


def refresh_wild_crops_by_terrain() -> None:
    """Rebuild the derived crop index after Developer Tools registry edits."""
    WILD_CROPS_BY_TERRAIN.clear()
    WILD_CROPS_BY_TERRAIN.update(_wild_crops_map())

# Terrains that accept planted saplings / natural sprouts.
PLANTABLE_LAND: tuple[TerrainType, ...] = (
    TerrainType.SOIL,
    TerrainType.FOREST_FLOOR,
    TerrainType.GRASS,
    TerrainType.MEADOW,
)

# Field plots may cover plantable land and packed paths (not urban paving).
FIELDABLE_LAND: tuple[TerrainType, ...] = (
    *PLANTABLE_LAND,
    TerrainType.PATH,
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
    COBBLER = auto()
    MARKET = auto()
    TENT = auto()
    HOUSE_SMALL = auto()
    HOUSE = auto()
    BARN = auto()
    COMPOST_HEAP = auto()
    PANTRY = auto()
    CELLAR = auto()
    DRYING_RACK = auto()
    CONSTRUCTION_SITE = auto()
    # Invisible reserved cells of a multi-cell building footprint (not the glyph cell).
    STRUCTURE_PAD = auto()
    MUSHROOM = auto()
    WOOD_BUSH = auto()
    BERRY_BUSH = auto()
    HERB = auto()  # legacy; migrated to WILD_CROP on load
    WILD_CROP = auto()  # wild crop patches (any CropDef key)
    CROP_HERB = auto()  # farmed crop (growth_ticks > 0 while growing)
    REED = auto()  # riparian reeds (forage; year-round, spread spring–summer)
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
        FeatureType.COBBLER,
        FeatureType.MARKET,
        FeatureType.TENT,
        FeatureType.HOUSE_SMALL,
        FeatureType.HOUSE,
        FeatureType.BARN,
        FeatureType.COMPOST_HEAP,
        FeatureType.PANTRY,
        FeatureType.CELLAR,
        FeatureType.DRYING_RACK,
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
    """Side-panel tools available while map/object edit mode (T) is active."""

    SELECT = "select"
    HEIGHT_SET = "height_set"
    HEIGHT_RAISE = "height_raise"
    HEIGHT_LOWER = "height_lower"
    TERRAIN_PAINT = "terrain_paint"
    SEED_FOREST = "seed_forest"
    PAINT_ROCKS = "paint_rocks"
    PAINT_BERRIES = "paint_berries"
    CROP_PAINT = "crop_paint"
    PLACE_BUILDING = "place_building"
    MOVE_BUILDING = "move_building"


@dataclass
class Cell:
    """Single grid cell. Indicators are derived elsewhere from live state."""

    terrain: TerrainType
    feature: FeatureType = FeatureType.NONE
    disturbance: float = 0.0
    growth_ticks: int = 0  # sapling maturity / berry regen countdown
    deposit: int = 0  # wood, rock, or berries remaining
    meat_deposit: int = 0
    meat_anchor_slot: int | None = None
    hide_deposit: int = 0
    hide_anchor_slot: int | None = None
    fur_deposit: int = 0
    fur_anchor_slot: int | None = None
    feather_deposit: int = 0
    feather_anchor_slot: int | None = None
    fish_deposit: int = 0
    fish_anchor_slot: int | None = None
    crop_kind: str | None = None  # CropDef / WildSpeciesDef key
    tree_species: str | None = None  # TreeDef key for TREE / SAPLING
    tree_age_years: int = 0  # mature-tree age; saplings begin at zero
    # 1-based icon variant (e.g. tree_round_2); rolled on first draw.
    icon_variant: int | None = None
    # Stable hard-anchor in the visual 3x3 subgrid. The object's visible
    # footprint grows around this slot and may overhang neighbouring cells.
    object_anchor_slot: int | None = None
    # Additional natural objects anchored in this ecology cell. The legacy
    # fields above remain the primary object for simulation compatibility.
    extra_objects: list["NaturalObject"] = field(default_factory=list)
    # Visual sub-patch within a terrain biome (seasonal masking / speckles).
    terrain_cluster: int = 0
    terrain_shade: float = 0.55  # 0..1 seasonal wash strength for this subcluster
    fertility: float = 0.8  # 0–1 soil fertility (harvests deplete)
    weeds: float = 0.0  # 0–1 weed cover on farm crops
    weed_appearances: int = 0  # weed waves started this season
    compost_cycle_applied: bool = False
    mineral_cycle_applied: bool = False
    weed_suppression: float = 0.0
    repellant_season: str | None = None
    # Worn trail overlay — does not replace underlying terrain.
    path_worn: bool = False

    def habitat_category(self) -> str:
        if self.feature == FeatureType.TREE:
            return f"tree_{self.tree_species or 'oak'}"
        if self.feature == FeatureType.SAPLING:
            return f"sapling_{self.tree_species or 'oak'}"
        if self.feature != FeatureType.NONE:
            return self.feature.name.lower()
        return self.terrain.name.lower()


@dataclass
class NaturalObject:
    """A second or later natural object sharing an ecology cell."""

    feature: FeatureType
    anchor_slot: int
    deposit: int = 0
    growth_ticks: int = 0
    crop_kind: str | None = None
    tree_species: str | None = None
    tree_age_years: int = 0
    icon_variant: int | None = None


def cell_has_path(cell: Cell) -> bool:
    """True when a worn path overlay (or legacy PATH terrain) is present."""
    return bool(getattr(cell, "path_worn", False)) or cell.terrain == TerrainType.PATH


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


def wildlife_ecology_multiplier(disturbance: float) -> float:
    """Breed/grow/spread effectiveness under disturbance (balance-sensitive)."""
    from balance_config import active_balance

    base = disturbance_activity_multiplier(disturbance)
    sens = active_balance().get_float("WILDLIFE_DISTURBANCE_SENSITIVITY")
    if sens <= 0.0:
        return 1.0
    return max(0.0, min(1.0, 1.0 - (1.0 - base) * sens))


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
        # Bound by Game after EnvMaps construction; worlds remain usable standalone.
        self.env_maps = None
        # (origin_x, origin_y, width, height) for completed non-field buildings.
        self.building_footprints: list[tuple[int, int, int, int]] = []
        self._building_by_cell: dict[
            tuple[int, int], tuple[int, int, int, int]
        ] = {}
        self._building_by_entrance: dict[
            tuple[int, int], tuple[int, int, int, int]
        ] = {}
        self._can_step_cache: dict[tuple[int, int, int, int], bool] = {}
        self._path_miss_cache: set[
            tuple[tuple[int, int], tuple[int, int], int | None, int | None]
        ] = set()
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
        self._growth_cells: list[tuple[int, int]] | None = None
        self._growth_index_age = 0
        self._water_patches_cache: list[list[tuple[int, int]]] | None = None
        self._water_patches_rev = -1
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
        bump_revision: bool = True,
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
                if clear_features and (cell.feature != FeatureType.NONE or cell.extra_objects):
                    cell.feature = FeatureType.NONE
                    cell.extra_objects.clear()
                    cell.deposit = 0
                    cell.growth_ticks = 0
                    cell.crop_kind = None
                    cell.tree_species = None
                    cell.icon_variant = None
                    changed = True
                if cell.terrain != terrain:
                    cell.terrain = terrain
                    from soil import apply_terrain_fertility

                    apply_terrain_fertility(cell, reset=True)
                    self.mark_terrain_dirty(x, y)
                    changed = True
        if changed and bump_revision:
            self.terrain_revision += 1
        return changed

    def seed_forest(
        self,
        cx: int,
        cy: int,
        radius: int,
        rng: random.Random | None = None,
        species: str | None = None,
        bump_revision: bool = True,
    ) -> bool:
        """Stamp forest floor and mature trees of one species, or a mixed forest."""
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
                if cell.feature == FeatureType.TREE:
                    if species is not None and cell.tree_species != species:
                        tree = resolve_tree(species)
                        cell.tree_species = tree.key
                        cell.deposit = tree.yield_amount
                        cell.icon_variant = None
                        changed = True
                    if cell.terrain != TerrainType.FOREST_FLOOR:
                        cell.terrain = TerrainType.FOREST_FLOOR
                        from soil import apply_terrain_fertility

                        apply_terrain_fertility(cell, reset=True)
                        self.mark_terrain_dirty(x, y)
                        changed = True
                    continue
                if cell.feature == FeatureType.SAPLING:
                    continue
                chance = 0.9 if dist <= 0 else 0.75 if dist <= 1 else 0.55 if dist <= 2 else 0.35
                if radius > 0 and dist == radius:
                    chance *= 0.7
                if rng.random() >= chance:
                    continue
                tree_species = species if species is not None else pick_tree_species(rng)
                tree = resolve_tree(tree_species)
                cell.feature = FeatureType.TREE
                cell.tree_species = tree.key
                cell.deposit = tree.yield_amount
                cell.growth_ticks = 0
                cell.icon_variant = None
                if cell.terrain != TerrainType.FOREST_FLOOR:
                    cell.terrain = TerrainType.FOREST_FLOOR
                    from soil import apply_terrain_fertility

                    apply_terrain_fertility(cell, reset=True)
                    self.mark_terrain_dirty(x, y)
                changed = True
        if changed:
            if bump_revision:
                self.terrain_revision += 1
            self.update_forest_floor(bump_revision=bump_revision)
        return changed

    def paint_rocks(
        self,
        cx: int,
        cy: int,
        radius: int,
        rng: random.Random | None = None,
        *,
        bump_revision: bool = True,
    ) -> bool:
        """Paint a natural-looking area containing mixed small and large rocks."""
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
                if cell.feature in STRUCTURE_FEATURES or is_water_terrain(cell.terrain):
                    continue
                chance = 0.90 if dist == 0 else 0.68 if dist <= 1 else 0.48
                if radius > 0 and dist == radius:
                    chance *= 0.65
                if rng.random() >= chance:
                    continue
                cell.feature = FeatureType.ROCK
                cell.extra_objects.clear()
                if rng.random() < 0.35:
                    cell.deposit = rng.randint(ROCK_LARGE_MIN, ROCK_LARGE_MAX)
                else:
                    cell.deposit = rng.randint(ROCK_SMALL_MIN, ROCK_SMALL_MAX)
                cell.growth_ticks = 0
                cell.crop_kind = None
                cell.tree_species = None
                cell.icon_variant = None
                changed = True
        if changed and bump_revision:
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
        self._water_patches_cache = None
        self._can_step_cache.clear()
        self._path_miss_cache.clear()

    def invalidate_movement_cache(self) -> None:
        """Discard cached edges after a hard obstacle changes."""
        self._can_step_cache.clear()
        self._path_miss_cache.clear()

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
        self._growth_cells = None
        self._growth_index_age = 0
        self._water_patches_cache = None
        self._water_patches_rev = -1
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
        self._seed_initial_reeds(rng)

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

        # Permanent berry bushes (fruit only in season; no natural spread).
        berry = WILD_BY_KEY["berry_bush"]
        berry_terrains = tuple(
            TerrainType[n] for n in berry.terrains if n in TerrainType.__members__
        )
        target_bushes = max(0, int(BERRY_INITIAL_COUNT))
        berry_sites = [
            (x, y)
            for y in range(self.rows)
            for x in range(self.cols)
            if self.cells[y][x].feature == FeatureType.NONE
            and self.cells[y][x].terrain in berry_terrains
        ]
        rng.shuffle(berry_sites)
        for x, y in berry_sites[:target_bushes]:
            cell = self.cells[y][x]
            cell.feature = FeatureType.BERRY_BUSH
            cell.crop_kind = berry.key
            cell.deposit = 0
            cell.growth_ticks = 0

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
        self.ensure_tree_ages(rng=rng)
        self.update_forest_floor()
        self._paint_terrain_subclusters(rng)
        self._build_valley_heightfield()
        self.init_fertility()
        self.bump_terrain()

    def init_fertility(self) -> None:
        """Set every cell's fertility from its terrain base (world gen / missing saves)."""
        from soil import init_cell_fertility

        for row in self.cells:
            for cell in row:
                init_cell_fertility(cell)

    def _seed_wood_near_trees(self, rng: random.Random) -> None:
        """Place fallen wood on empty tiles adjacent to trees (forest edges)."""
        wood = WILD_BY_KEY["wood_bush"]
        plantable = tuple(
            TerrainType[n] for n in wood.terrains if n in TerrainType.__members__
        )
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
                    cell.crop_kind = wood.key
                    cell.deposit = WOOD_BUSH_YIELD
                    cell.growth_ticks = self._fallen_wood_lifetime_ticks()

    @staticmethod
    def _fallen_wood_lifetime_ticks() -> int:
        """One complete in-game year using the active day length."""
        import seasons

        return max(1, int(seasons.TICKS_PER_DAY) * int(seasons.YEAR_DAYS))

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

    def update_forest_floor(self, *, bump_revision: bool = True) -> None:
        """Forest floor forms under mature trees only; saplings never create it.

        Mature trees convert soil / grass / meadow under them to forest floor.
        Bare forest floor (no tree and no sapling) reverts to soil.
        Saplings may sit on existing forest floor without forming new litter.
        Runs on the same ≤8/year cadence as biodiversity / habitat refresh.
        """
        form_from = (
            TerrainType.SOIL,
            TerrainType.GRASS,
            TerrainType.MEADOW,
        )
        changed = False
        for y in range(self.rows):
            for x in range(self.cols):
                cell = self.cells[y][x]
                if cell.terrain == TerrainType.URBAN:
                    continue
                if cell.feature == FeatureType.TREE and cell.terrain in form_from:
                    cell.terrain = TerrainType.FOREST_FLOOR
                    self.mark_terrain_dirty(x, y)
                    changed = True
                elif (
                    cell.feature not in (FeatureType.TREE, FeatureType.SAPLING)
                    and cell.terrain == TerrainType.FOREST_FLOOR
                ):
                    cell.terrain = TerrainType.SOIL
                    self.mark_terrain_dirty(x, y)
                    changed = True
        if changed and bump_revision:
            self.terrain_revision += 1

    def forest_floor_cells(self) -> list[tuple[int, int]]:
        """Tiles whose terrain is forest floor (deer/boar habitat core)."""
        return [
            (x, y)
            for y in range(self.rows)
            for x in range(self.cols)
            if self.cells[y][x].terrain == TerrainType.FOREST_FLOOR
        ]

    def forest_floor_patches(self) -> list[list[tuple[int, int]]]:
        """Connected forest-floor patches (8-connected)."""
        return self._connected_patches(set(self.forest_floor_cells()))

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

    def _species_can_occupy(self, x: int, y: int, species) -> bool:
        """True if terrain, edge, and required neighbouring feature all match."""
        cell = self.get_cell(x, y)
        if cell is None:
            return False
        if cell.terrain.name not in species.terrains:
            return False
        near_name = getattr(species, "near_feature", None)
        if near_name:
            try:
                required_feature = FeatureType[near_name]
            except KeyError:
                return False
            if not any(
                (nx, ny) != (x, y)
                and self.cells[ny][nx].feature == required_feature
                for ny, nx in self.neighbourhood(x, y, radius=1)
            ):
                return False
        if not species.edge_terrains:
            return True
        edge = {
            TerrainType[n]
            for n in species.edge_terrains
            if n in TerrainType.__members__
        }
        if not edge:
            return True
        for ny, nx in self.neighbourhood(x, y, radius=1):
            if (nx, ny) == (x, y):
                continue
            if self.cells[ny][nx].terrain in edge:
                return True
        return False

    def species_suitability_at(self, x: int, y: int, species):
        """Evaluate a species from authoritative cached grids and live cell state."""
        cell = self.get_cell(x, y)
        maps = self.env_maps
        if cell is None or maps is None:
            return species_environment_suitability(
                species, temperature=.5, rainfall=.5, soil_moisture=.5,
                fertility=float(getattr(cell, "fertility", .5)) if cell else .5,
                disturbance=effective_disturbance_at(self, x, y),
            )
        def grid_value(grid, default):
            return float(grid[y][x]) if 0 <= y < len(grid) and 0 <= x < len(grid[y]) else default
        cached_disturbance = getattr(self, "_wild_tick_disturbance", None)
        disturbance = (cached_disturbance[y][x] if cached_disturbance is not None
                       else effective_disturbance_at(self, x, y))
        return species_environment_suitability(
            species,
            temperature=normalize_temperature_c(grid_value(maps.temperature, 12.5)),
            rainfall=max(0.0, min(1.0, grid_value(maps.rainfall, .5))),
            soil_moisture=max(0.0, min(1.0, grid_value(maps.soil_moisture, .5))),
            fertility=max(0.0, min(1.0, float(cell.fertility))),
            disturbance=disturbance,
        )

    def _build_effective_disturbance_grid(self) -> list[list[float]]:
        """Exact neighborhood means via a summed-area table for flora ticks."""
        from balance_config import active_balance

        radius = active_balance().get_int("DISTURBANCE_RADIUS")
        if radius <= 0:
            return [[max(0.0, min(1.0, float(cell.disturbance))) for cell in row]
                    for row in self.cells]
        sums = [[0.0] * (self.cols + 1) for _ in range(self.rows + 1)]
        for y, row in enumerate(self.cells, 1):
            running = 0.0
            above = sums[y - 1]
            current = sums[y]
            for x, cell in enumerate(row, 1):
                running += float(cell.disturbance)
                current[x] = above[x] + running
        out = [[0.0] * self.cols for _ in range(self.rows)]
        for y in range(self.rows):
            y0, y1 = max(0, y - radius), min(self.rows - 1, y + radius)
            for x in range(self.cols):
                x0, x1 = max(0, x - radius), min(self.cols - 1, x + radius)
                total = sums[y1 + 1][x1 + 1] - sums[y0][x1 + 1] - sums[y1 + 1][x0] + sums[y0][x0]
                out[y][x] = max(0.0, min(1.0, total / ((x1 - x0 + 1) * (y1 - y0 + 1))))
        return out

    def species_can_establish_at(self, x: int, y: int, species) -> bool:
        return (self._species_can_occupy(x, y, species) and
                environment_allows_establishment(species, self.species_suitability_at(x, y, species)))

    def wild_species_debug_at(self, x: int, y: int, species, day: float) -> str:
        """Developer-facing cell report suitable for an inspector or log."""
        cell = self.get_cell(x, y)
        maps = self.env_maps
        def value(grid, default):
            return float(grid[y][x]) if grid and 0 <= y < len(grid) and 0 <= x < len(grid[y]) else default
        temp = normalize_temperature_c(value(getattr(maps, "temperature", None), 12.5))
        rain = max(0.0, min(1.0, value(getattr(maps, "rainfall", None), .5)))
        moisture = max(0.0, min(1.0, value(getattr(maps, "soil_moisture", None), .5)))
        fertility = float(cell.fertility) if cell else .5
        disturbance = effective_disturbance_at(self, x, y)
        score = species_environment_suitability(species, temperature=temp, rainfall=rain,
                                                soil_moisture=moisture, fertility=fertility,
                                                disturbance=disturbance)
        return format_environment_debug(species, score, temperature=temp, rainfall=rain,
                                        soil_moisture=moisture, fertility=fertility,
                                        disturbance=disturbance, day=local_day(day, x, y))

    def _seed_initial_reeds(self, rng: random.Random) -> None:
        """Place riparian plants from the wild-species catalogue."""
        riparian = sorted(
            non_crop_on_terrain("RIPARIAN"),
            key=lambda s: (0 if s.edge_terrains else 1, s.key),
        )
        for y in range(self.rows):
            for x in range(self.cols):
                cell = self.cells[y][x]
                if cell.feature != FeatureType.NONE or cell.terrain != TerrainType.RIPARIAN:
                    continue
                for species in riparian:
                    if species.initial_fraction <= 0:
                        continue
                    if not self._species_can_occupy(x, y, species):
                        continue
                    if rng.random() < species.initial_fraction:
                        try:
                            cell.feature = FeatureType[species.feature]
                        except KeyError:
                            continue
                        cell.crop_kind = species.key
                        break

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
                cell.object_anchor_slot = None
                cell.extra_objects.clear()
                self.mark_terrain_dirty(x, y)
        return cx, cy

    def clear_structure_footprint(
        self, origin_x: int, origin_y: int, plot_w: int, plot_h: int
    ) -> None:
        """Remove construction/building glyphs from a rectangular footprint."""
        w = max(1, plot_w)
        h = max(1, plot_h)
        for y in range(origin_y, origin_y + h):
            for x in range(origin_x, origin_x + w):
                cell = self.get_cell(x, y)
                if cell is None:
                    continue
                cell.feature = FeatureType.NONE
                cell.deposit = 0
                cell.growth_ticks = 0
                cell.crop_kind = None
                cell.tree_species = None
                cell.icon_variant = None
                cell.object_anchor_slot = None
                cell.extra_objects.clear()
                self.mark_terrain_dirty(x, y)

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
        """Whether an actor standing at the ecology-cell centre fits."""
        cell = self.get_cell(x, y)
        if cell is None:
            return False
        if is_water_terrain(cell.terrain):
            return False
        building = self._building_at_cell(x, y)
        if building is not None:
            return (building[2], building[3]) == (3, 2) or (
                (x, y) == self.building_entrance_cell(building)
            )
        return self.is_position_walkable(float(x), float(y))

    def set_building_footprints(
        self, footprints: list[tuple[int, int, int, int]]
    ) -> None:
        self.building_footprints = [
            (int(x), int(y), max(1, int(w)), max(1, int(h)))
            for x, y, w, h in footprints
        ]
        self._building_by_cell = {}
        self._building_by_entrance = {}
        for footprint in self.building_footprints:
            bx, by, bw, bh = footprint
            for cy in range(by, by + bh):
                for cx in range(bx, bx + bw):
                    self._building_by_cell[(cx, cy)] = footprint
            self._building_by_entrance[self.building_entrance_cell(footprint)] = footprint
        self._can_step_cache.clear()
        self._path_miss_cache.clear()

    @staticmethod
    def building_entrance_cell(
        footprint: tuple[int, int, int, int]
    ) -> tuple[int, int]:
        x, y, w, h = footprint
        return x + w // 2, y + h - 1

    @staticmethod
    def building_entrance_position(
        footprint: tuple[int, int, int, int]
    ) -> tuple[float, float]:
        ex, ey = World.building_entrance_cell(footprint)
        # Centre of the bottom-middle subcell within the doorway ecology cell.
        return float(ex), float(ey) + 1.0 / 3.0

    @staticmethod
    def building_navigation_position(
        footprint: tuple[int, int, int, int], cell_x: int, cell_y: int
    ) -> tuple[float, float]:
        """Precise halo/door point represented by a building footprint cell."""
        bx, by, bw, bh = footprint
        if (cell_x, cell_y) == World.building_entrance_cell(footprint):
            return World.building_entrance_position(footprint)
        if (bw, bh) != (3, 2):
            return float(cell_x), float(cell_y)
        px = float(cell_x)
        py = float(cell_y)
        if cell_x == bx:
            px -= 1.0 / 3.0
        elif cell_x == bx + bw - 1:
            px += 1.0 / 3.0
        if cell_y == by:
            py -= 1.0 / 3.0
        elif cell_y == by + bh - 1:
            py += 1.0 / 3.0
        return px, py

    def _building_at_cell(
        self, x: int, y: int
    ) -> tuple[int, int, int, int] | None:
        return self._building_by_cell.get((x, y))

    def building_footprint_for_entrance(
        self, x: int, y: int
    ) -> tuple[int, int, int, int] | None:
        return self._building_by_entrance.get((x, y))

    def _building_position_open(self, world_x: float, world_y: float) -> bool:
        """Subcell building collision: 3x2 halo or bottom-middle doorway."""
        cell_x = int(math.floor(float(world_x) + 0.5))
        cell_y = int(math.floor(float(world_y) + 0.5))
        footprint = self._building_at_cell(cell_x, cell_y)
        if footprint is None:
            return True
        bx, by, bw, bh = footprint
        left, top = bx - 0.5, by - 0.5
        right, bottom = bx + bw - 0.5, by + bh - 0.5
        door_x, door_y = self.building_entrance_position(footprint)
        eps = 1e-6
        in_door = (
            abs(world_x - door_x) < 1.0 / 6.0 + eps
            and abs(world_y - door_y) < 1.0 / 6.0 + eps
        )
        if in_door:
            return True
        if (bw, bh) == (3, 2):
            halo = 1.0 / 3.0
            return (
                world_x <= left + halo + eps
                or world_x >= right - halo - eps
                or world_y <= top + halo + eps
                or world_y >= bottom - halo - eps
            )
        # Single-square and other compact buildings have no walkable halo.
        return False

    @staticmethod
    def _object_has_hard_anchor(
        feature: FeatureType, *, tree_age_years: int = 0, deposit: int = 0
    ) -> bool:
        """Compatibility query backed by the central footprint definition."""
        from subtile_layout import object_footprint

        return bool(
            object_footprint(
                feature.name,
                0,
                0,
                tree_age_years=tree_age_years,
                deposit=deposit,
                anchor_slot=4,
            ).hard_slots
        )

    @staticmethod
    def _point_in_anchor(
        world_x: float, world_y: float, cell_x: int, cell_y: int, slot: int
    ) -> bool:
        """Test a world point against one hard 1/3-cell anchor square."""
        slot = max(0, min(8, int(slot)))
        left = cell_x - 0.5 + (slot % 3) / 3.0
        top = cell_y - 0.5 + (slot // 3) / 3.0
        eps = 1e-9
        return (
            left + eps < world_x < left + 1.0 / 3.0 - eps
            and top + eps < world_y < top + 1.0 / 3.0 - eps
        )

    def _primary_anchor_slot(self, x: int, y: int, cell: Cell) -> int:
        from subtile_layout import stable_anchor_slot

        if cell.object_anchor_slot is None:
            cell.object_anchor_slot = stable_anchor_slot(x, y, int(cell.icon_variant or 1))
        return cell.object_anchor_slot

    def _cell_has_hard_anchor(self, x: int, y: int) -> bool:
        cell = self.get_cell(x, y)
        if cell is None:
            return False
        if self._object_has_hard_anchor(
            cell.feature,
            tree_age_years=cell.tree_age_years,
            deposit=cell.deposit,
        ):
            return True
        return any(
            self._object_has_hard_anchor(
                obj.feature,
                tree_age_years=obj.tree_age_years,
                deposit=obj.deposit,
            )
            for obj in cell.extra_objects
        )

    def is_position_walkable(self, world_x: float, world_y: float) -> bool:
        """Point-accurate terrain and natural-object collision in the 3x3 grid."""
        x = int(math.floor(float(world_x) + 0.5))
        y = int(math.floor(float(world_y) + 0.5))
        cell = self.get_cell(x, y)
        if cell is None or is_water_terrain(cell.terrain):
            return False
        if not self._building_position_open(world_x, world_y):
            return False
        if self._object_has_hard_anchor(
            cell.feature,
            tree_age_years=cell.tree_age_years,
            deposit=cell.deposit,
        ) and self._point_in_anchor(
            world_x, world_y, x, y, self._primary_anchor_slot(x, y, cell)
        ):
            return False
        for obj in cell.extra_objects:
            if self._object_has_hard_anchor(
                obj.feature,
                tree_age_years=obj.tree_age_years,
                deposit=obj.deposit,
            ) and self._point_in_anchor(world_x, world_y, x, y, obj.anchor_slot):
                return False
        return True

    def add_natural_object(
        self,
        x: int,
        y: int,
        feature: FeatureType,
        *,
        anchor_slot: int | None = None,
        deposit: int = 0,
        growth_ticks: int = 0,
        crop_kind: str | None = None,
        tree_species: str | None = None,
        tree_age_years: int = 0,
        icon_variant: int | None = None,
    ) -> NaturalObject | None:
        """Add a secondary object using the shared subcell-capacity rules."""
        from subtile_layout import (
            first_available_anchor,
            object_footprint,
        )

        cell = self.get_cell(x, y)
        if cell is None or feature in STRUCTURE_FEATURES or feature == FeatureType.NONE:
            return None
        existing = []
        if cell.feature != FeatureType.NONE:
            existing.append(
                object_footprint(
                    cell.feature.name,
                    x,
                    y,
                    tree_age_years=cell.tree_age_years,
                    variant=int(cell.icon_variant or 1),
                    deposit=cell.deposit,
                    crop_kind=cell.crop_kind,
                    anchor_slot=self._primary_anchor_slot(x, y, cell),
                )
            )
        existing.extend(
            object_footprint(
                obj.feature.name,
                x,
                y,
                tree_age_years=obj.tree_age_years,
                variant=int(obj.icon_variant or 1),
                deposit=obj.deposit,
                crop_kind=obj.crop_kind,
                anchor_slot=obj.anchor_slot,
            )
            for obj in cell.extra_objects
        )
        placement = first_available_anchor(
            feature.name,
            x,
            y,
            existing,
            tree_age_years=tree_age_years,
            variant=int(icon_variant or 1),
            deposit=deposit,
            crop_kind=crop_kind,
            preferred=anchor_slot,
        )
        if placement is None:
            return None
        slot, _footprint = placement
        obj = NaturalObject(
            feature=feature,
            anchor_slot=slot,
            deposit=int(deposit),
            growth_ticks=int(growth_ticks),
            crop_kind=crop_kind,
            tree_species=tree_species,
            tree_age_years=int(tree_age_years),
            icon_variant=icon_variant,
        )
        cell.extra_objects.append(obj)
        # Soft plants/litter do not alter navigation. Clearing the global edge
        # cache for them caused a recurring AI hitch at ecology spawn intervals.
        if _footprint.hard_slots:
            self.invalidate_movement_cache()
        return obj

    def promote_natural_object(self, x: int, y: int, obj: NaturalObject) -> bool:
        """Swap a selected secondary object into legacy primary fields."""
        cell = self.get_cell(x, y)
        if cell is None or obj not in cell.extra_objects:
            return False
        prior = NaturalObject(
            feature=cell.feature,
            anchor_slot=self._primary_anchor_slot(x, y, cell),
            deposit=cell.deposit,
            growth_ticks=cell.growth_ticks,
            crop_kind=cell.crop_kind,
            tree_species=cell.tree_species,
            tree_age_years=cell.tree_age_years,
            icon_variant=cell.icon_variant,
        )
        cell.extra_objects.remove(obj)
        if prior.feature != FeatureType.NONE:
            cell.extra_objects.append(prior)
        cell.feature = obj.feature
        cell.object_anchor_slot = obj.anchor_slot
        cell.deposit = obj.deposit
        cell.growth_ticks = obj.growth_ticks
        cell.crop_kind = obj.crop_kind
        cell.tree_species = obj.tree_species
        cell.tree_age_years = obj.tree_age_years
        cell.icon_variant = obj.icon_variant
        return True

    def can_move_between_positions(
        self, start_x: float, start_y: float, end_x: float, end_y: float
    ) -> bool:
        """Continuous actor collision along its actual subcell path."""
        sx = int(math.floor(start_x + 0.5))
        sy = int(math.floor(start_y + 0.5))
        ex = int(math.floor(end_x + 0.5))
        ey = int(math.floor(end_y + 0.5))
        if not self.is_position_walkable(end_x, end_y):
            return False
        if (sx, sy) != (ex, ey):
            if abs(ex - sx) > 1 or abs(ey - sy) > 1:
                return False
            if self._edge_key(sx, sy, ex, ey) in getattr(
                self, "blocked_edges", set()
            ):
                return False
        distance = math.hypot(end_x - start_x, end_y - start_y)
        samples = max(1, int(math.ceil(distance * 24.0)))
        for index in range(1, samples + 1):
            t = index / samples
            if not self.is_position_walkable(
                start_x + (end_x - start_x) * t,
                start_y + (end_y - start_y) * t,
            ):
                return False
        return True

    def free_loose_object_anchor(self, x: int, y: int, kind: str) -> int | None:
        """Return the nearest free subcell for a ground drop such as meat or fish."""
        from subtile_layout import (
            first_available_anchor,
            object_footprint,
            stable_drop_slot,
        )

        cell = self.get_cell(x, y)
        if cell is None:
            return None
        existing = []
        if cell.feature != FeatureType.NONE:
            existing.append(
                object_footprint(
                    cell.feature.name,
                    x,
                    y,
                    tree_age_years=cell.tree_age_years,
                    variant=int(cell.icon_variant or 1),
                    deposit=cell.deposit,
                    crop_kind=cell.crop_kind,
                    anchor_slot=self._primary_anchor_slot(x, y, cell),
                )
            )
        existing.extend(
            object_footprint(
                obj.feature.name,
                x,
                y,
                tree_age_years=obj.tree_age_years,
                variant=int(obj.icon_variant or 1),
                deposit=obj.deposit,
                crop_kind=obj.crop_kind,
                anchor_slot=obj.anchor_slot,
            )
            for obj in cell.extra_objects
        )
        for deposit_kind, slot in (
            ("MEAT", cell.meat_anchor_slot),
            ("FISH", cell.fish_anchor_slot),
            ("HIDE", cell.hide_anchor_slot),
            ("FUR", cell.fur_anchor_slot),
            ("FEATHER", cell.feather_anchor_slot),
        ):
            if slot is not None:
                existing.append(
                    object_footprint(deposit_kind, x, y, anchor_slot=slot)
                )
        placement = first_available_anchor(
            kind, x, y, existing, preferred=stable_drop_slot(x, y, kind)
        )
        return placement[0] if placement is not None else None

    def set_blocked_edges(self, edges: set[tuple[int, int, int, int]]) -> None:
        self.blocked_edges = set(edges)
        self._can_step_cache.clear()
        self._path_miss_cache.clear()

    @staticmethod
    def _edge_key(ax: int, ay: int, bx: int, by: int) -> tuple[int, int, int, int]:
        return (ax, ay, bx, by) if (ax, ay) <= (bx, by) else (bx, by, ax, ay)

    def can_step(self, ax: int, ay: int, bx: int, by: int) -> bool:
        """Cached movement-edge query used heavily by breadth-first searches."""
        key = (ax, ay, bx, by)
        cached = self._can_step_cache.get(key)
        if cached is not None:
            return cached
        result = self._can_step_uncached(ax, ay, bx, by)
        self._can_step_cache[key] = result
        return result

    def _can_step_uncached(self, ax: int, ay: int, bx: int, by: int) -> bool:
        """Whether movement may cross from one cell to the next."""
        if not self.is_walkable(bx, by):
            return False
        dx, dy = bx - ax, by - ay
        if abs(dx) > 1 or abs(dy) > 1:
            return False
        entering = self._building_at_cell(bx, by)
        leaving = self._building_at_cell(ax, ay)
        start_x, start_y = (
            self.building_navigation_position(leaving, ax, ay)
            if leaving is not None
            else (float(ax), float(ay))
        )
        end_x, end_y = (
            self.building_navigation_position(entering, bx, by)
            if entering is not None
            else (float(bx), float(by))
        )
        # Most edges cross empty terrain and need no subcell work. Sample only
        # when the segment touches a hard natural anchor or a building doorway.
        if (
            entering is not None
            or leaving is not None
            or self._cell_has_hard_anchor(ax, ay)
            or self._cell_has_hard_anchor(bx, by)
        ):
            # Match continuous actor collision closely enough that a narrow
            # wall corner cannot fall between samples on a diagonal edge.
            for index in range(1, 25):
                t = index / 24.0
                px = start_x + (end_x - start_x) * t
                py = start_y + (end_y - start_y) * t
                if not self.is_position_walkable(px, py):
                    return False
        blocked = getattr(self, "blocked_edges", set())
        if dx and dy:
            if any(
                footprint is not None
                for footprint in (
                    entering,
                    leaving,
                    self._building_at_cell(bx, ay),
                    self._building_at_cell(ax, by),
                )
            ):
                # Follow cardinal halo segments around structures. A diagonal
                # between them can visually shave the hard wall corner even
                # when both endpoint cells themselves are walkable.
                return False
            # Do not squeeze diagonally between water or across fence corners.
            return (
                self.is_walkable(bx, ay)
                and self.is_walkable(ax, by)
                and self._edge_key(ax, ay, bx, ay) not in blocked
                and self._edge_key(ax, ay, ax, by) not in blocked
                and self._edge_key(bx, ay, bx, by) not in blocked
                and self._edge_key(ax, by, bx, by) not in blocked
            )
        return self._edge_key(ax, ay, bx, by) not in blocked

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
        reachable: set[tuple[int, int]] | None = None
        if origin is not None:
            # One flood-fill from the villager instead of BFS-per-candidate.
            reachable = set()
            ox, oy = origin
            if self.is_walkable(ox, oy):
                q: deque[tuple[int, int]] = deque([(ox, oy)])
                reachable.add((ox, oy))
                while q and len(reachable) < self.rows * self.cols + 8:
                    cx, cy = q.popleft()
                    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                        nx, ny = cx + dx, cy + dy
                        nxt = (nx, ny)
                        if nxt in reachable or not self.is_walkable(nx, ny):
                            continue
                        reachable.add(nxt)
                        q.append(nxt)
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
                    if reachable is not None and (nx, ny) not in reachable:
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
        cell.fish_anchor_slot = None
        target = self.cells[best[1]][best[0]]
        if target.fish_deposit <= 0:
            target.fish_anchor_slot = self.free_loose_object_anchor(
                best[0], best[1], "FISH"
            )
        target.fish_deposit += amount
        return best

    def next_step_toward(self, start: tuple[int, int], goal: tuple[int, int]) -> tuple[int, int] | None:
        """Return the next cell on a shortest walkable path (BFS), or None if unreachable."""
        path = self.find_path(start, goal)
        if not path:
            return None if start != goal else goal
        return path[0]

    def find_path(
        self,
        start: tuple[int, int],
        goal: tuple[int, int],
        *,
        max_nodes: int | None = None,
        max_len: int | None = None,
    ) -> list[tuple[int, int]] | None:
        """Shortest eight-direction path after start, including the goal."""
        if start == goal:
            return []
        if not self.is_walkable(*goal):
            return None
        miss_key = (start, goal, max_nodes, max_len)
        if miss_key in self._path_miss_cache:
            return None

        sx, sy = start
        gx, gy = goal
        # Default: search the whole land component. Tight caps reject valid river
        # detours and turn every miss into a max-cost flood (worse + stuck workers).
        node_cap = (
            max_nodes
            if max_nodes is not None
            else self.rows * self.cols + 8
        )
        queue: deque[tuple[int, int]] = deque([(sx, sy)])
        came_from: dict[tuple[int, int], tuple[int, int] | None] = {(sx, sy): None}
        dist: dict[tuple[int, int], int] | None = {(sx, sy): 0} if max_len is not None else None

        found = False
        while queue and len(came_from) < node_cap:
            cx, cy = queue.popleft()
            if (cx, cy) == (gx, gy):
                found = True
                break
            directions = [
                (-1, -1), (0, -1), (1, -1),
                (-1, 0),             (1, 0),
                (-1, 1),  (0, 1),   (1, 1),
            ]
            # Among equally short BFS routes, prefer steps closest to the
            # destination vector. This yields diagonal-first direct paths.
            directions.sort(
                key=lambda d: (
                    max(abs(gx - (cx + d[0])), abs(gy - (cy + d[1]))),
                    (gx - (cx + d[0])) ** 2 + (gy - (cy + d[1])) ** 2,
                )
            )
            for dx, dy in directions:
                nx, ny = cx + dx, cy + dy
                if (nx, ny) in came_from:
                    continue
                if not self.can_step(cx, cy, nx, ny):
                    continue
                if dist is not None:
                    nd = dist[(cx, cy)] + 1
                    if max_len is not None and nd > max_len:
                        continue
                    dist[(nx, ny)] = nd
                came_from[(nx, ny)] = (cx, cy)
                queue.append((nx, ny))

        if not found:
            self._path_miss_cache.add(miss_key)
            return None

        path: list[tuple[int, int]] = []
        cur: tuple[int, int] | None = (gx, gy)
        while cur is not None and cur != start:
            path.append(cur)
            cur = came_from[cur]
        path.reverse()
        return path

    def note_growth_cell(self, x: int, y: int) -> None:
        """Track a newly planted crop/sapling so tick_bulk need not rescan the map."""
        cells = getattr(self, "_growth_cells", None)
        if cells is not None:
            cells.append((x, y))

    def _rebuild_growth_index(self) -> None:
        cells: list[tuple[int, int]] = []
        for y in range(self.rows):
            row = self.cells[y]
            for x in range(self.cols):
                cell = row[x]
                feat = cell.feature
                if feat == FeatureType.CROP_HERB:
                    cells.append((x, y))
                elif feat == FeatureType.SAPLING:
                    cells.append((x, y))
                elif feat == FeatureType.BERRY_BUSH and cell.growth_ticks > 0:
                    cells.append((x, y))
                elif feat == FeatureType.WOOD_BUSH:
                    cells.append((x, y))
                elif any(
                    obj.feature in (FeatureType.SAPLING, FeatureType.WOOD_BUSH)
                    for obj in cell.extra_objects
                ):
                    cells.append((x, y))
        self._growth_cells = cells
        self._growth_index_age = 0

    # ------------------------------------------------------------------
    # Simulation ticks (growth, optional disturbance decay)
    # ------------------------------------------------------------------
    def tick(self, decay_per_tick: float = 0.0, day: float = 0.0) -> bool:
        """Advance growth and gradual seasonal ecology for the calendar day."""
        return self.tick_bulk(1, decay_per_tick=decay_per_tick, day=day)

    def _tick_terrain_floors(
        self,
        ticks: int,
        decay_per_tick: float,
        urban_level: float,
        path_level: float,
    ) -> None:
        """Urban/path floors and disturbance decay (full-map, infrequent)."""
        cells = self.cells
        for y in range(self.rows):
            row = cells[y]
            for x in range(self.cols):
                cell = row[x]
                terrain = cell.terrain
                if terrain == TerrainType.URBAN:
                    cell.disturbance = urban_level
                elif cell_has_path(cell):
                    if cell.disturbance < path_level:
                        cell.disturbance = path_level
                elif decay_per_tick > 0 and cell.disturbance > 0:
                    cell.disturbance = max(0.0, cell.disturbance - decay_per_tick * ticks)

    def tick_bulk(
        self,
        ticks: int,
        decay_per_tick: float = 0.0,
        day: float = 0.0,
        *,
        seasonal_crops: bool = False,
    ) -> bool:
        """Apply `ticks` ecology steps at once (for headless fast-forward).

        Returns True when a farm crop first becomes ready or weeds cross the
        hoe threshold — callers bump idle-park generation from that.
        """
        from balance_config import active_balance
        from seasons import season_for_day
        from soil import grow_weeds_on_cell

        if ticks <= 0:
            return False
        grow = trees_grow_factor(day)
        halt = growth_halted(day)
        grow_step = max(1, int(round(grow))) if grow > 0.05 else 0
        weed_thresh = active_balance().get_float("WEED_ACTION_THRESHOLD")
        urban_level = active_balance().get_float("DISTURBANCE_URBAN_LEVEL")
        path_level = active_balance().get_float("DISTURBANCE_PATH_LEVEL")
        season = season_for_day(int(day))
        woke = False

        age = getattr(self, "_growth_index_age", 0)
        growth_cells = getattr(self, "_growth_cells", None)
        # Decay/floors need a full scan; crops/saplings use a sparse index.
        full_pass = growth_cells is None or age + ticks >= 48 or ticks >= 8
        if full_pass:
            floor_ticks = ticks if growth_cells is None else age + ticks
            self._tick_terrain_floors(
                floor_ticks, decay_per_tick, urban_level, path_level
            )
            self._rebuild_growth_index()
            growth_cells = self._growth_cells
        else:
            self._growth_index_age = age + ticks

        still_growing: list[tuple[int, int]] = []
        hard_collision_changed = False
        for x, y in growth_cells or ():
            cell = self.cells[y][x]
            feat = cell.feature
            if feat == FeatureType.SAPLING:
                if grow_step > 0:
                    cell.growth_ticks -= grow_step * ticks
                    if cell.growth_ticks <= 0:
                        tree = resolve_tree(cell.tree_species)
                        cell.feature = FeatureType.TREE
                        cell.tree_species = tree.key
                        cell.tree_age_years = 0
                        cell.growth_ticks = 0
                        cell.deposit = tree.yield_amount
                        hard_collision_changed = True
                    else:
                        still_growing.append((x, y))
                else:
                    still_growing.append((x, y))
            elif feat == FeatureType.BERRY_BUSH and cell.growth_ticks > 0:
                if grow_step > 0:
                    cell.growth_ticks -= grow_step * ticks
                    if cell.growth_ticks <= 0:
                        if cell.deposit <= 0 and berry_fruiting(day, x, y):
                            species = resolve_species("BERRY_BUSH", cell.crop_kind)
                            cell.deposit = (
                                int(species.yield_amount)
                                if species is not None
                                else BERRY_BUSH_YIELD
                            )
                        cell.growth_ticks = 0
                    if cell.growth_ticks > 0:
                        still_growing.append((x, y))
                else:
                    still_growing.append((x, y))
            elif feat == FeatureType.CROP_HERB:
                if cell.growth_ticks > 0 and not seasonal_crops:
                    grow_mult = disturbance_activity_multiplier(cell.disturbance)
                    prev_gt = cell.growth_ticks
                    cell.growth_ticks = max(
                        0, cell.growth_ticks - max(0, int(round(ticks * grow_mult)))
                    )
                    if prev_gt > 0 and cell.growth_ticks <= 0:
                        woke = True
                prev_weeds = float(getattr(cell, "weeds", 0.0) or 0.0)
                grow_weeds_on_cell(cell, ticks, season=season)
                if prev_weeds < weed_thresh <= float(getattr(cell, "weeds", 0.0) or 0.0):
                    woke = True
                still_growing.append((x, y))
            elif feat == FeatureType.WOOD_BUSH:
                # Old saves did not persist a wood age. Give such piles a full
                # year when first encountered rather than clearing them.
                if cell.growth_ticks <= 0:
                    cell.growth_ticks = self._fallen_wood_lifetime_ticks()
                cell.growth_ticks = max(0, cell.growth_ticks - ticks)
                if cell.growth_ticks <= 0:
                    cell.feature = FeatureType.NONE
                    cell.deposit = 0
                    cell.crop_kind = None
                else:
                    still_growing.append((x, y))
            keep_cell = False
            for obj in list(cell.extra_objects):
                if obj.feature == FeatureType.SAPLING:
                    if grow_step > 0:
                        obj.growth_ticks -= grow_step * ticks
                        if obj.growth_ticks <= 0:
                            tree = resolve_tree(obj.tree_species)
                            obj.feature = FeatureType.TREE
                            obj.tree_species = tree.key
                            obj.tree_age_years = 0
                            obj.growth_ticks = 0
                            obj.deposit = tree.yield_amount
                            hard_collision_changed = True
                        else:
                            keep_cell = True
                    else:
                        keep_cell = True
                elif obj.feature == FeatureType.WOOD_BUSH:
                    if obj.growth_ticks <= 0:
                        obj.growth_ticks = self._fallen_wood_lifetime_ticks()
                    obj.growth_ticks = max(0, obj.growth_ticks - ticks)
                    if obj.growth_ticks <= 0:
                        cell.extra_objects.remove(obj)
                    else:
                        keep_cell = True
            if keep_cell and (x, y) not in still_growing:
                still_growing.append((x, y))
        self._growth_cells = still_growing
        if hard_collision_changed:
            self.invalidate_movement_cache()

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
            _drain_timer("_berry_spread_timer", BERRY_SPREAD_INTERVAL, self._tick_berry_fruit)
            return woke

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
        _drain_timer("_berry_spread_timer", BERRY_SPREAD_INTERVAL, self._tick_berry_fruit)
        _drain_timer("_herb_timer", HERB_TICK_INTERVAL, self._tick_herbs_seasonal)
        return woke

    def _tick_herbs_seasonal(self, day: float) -> None:
        """Wild crop patches on meadow / grass / soil by crop preference."""
        self._wild_tick_disturbance = self._build_effective_disturbance_grid()
        wild_n: dict[TerrainType, int] = {}
        total_n: dict[TerrainType, int] = {}
        catalogue_terrains = {
            TerrainType[name] for species in WILD_BY_KEY.values()
            for name in species.terrains if name in TerrainType.__members__
        }
        terrains = tuple(set(WILD_CROPS_BY_TERRAIN.keys()) | catalogue_terrains)
        # One map pass, rather than one full scan per catalogue terrain.
        wild_features = (FeatureType.WILD_CROP, FeatureType.HERB,
                         FeatureType.BERRY_BUSH, FeatureType.REED)
        terrain_set = set(terrains)
        for terrain in terrains:
            wild_n[terrain] = 0
            total_n[terrain] = 0
        for row in self.cells:
            for cell in row:
                if cell.terrain not in terrain_set:
                    continue
                total_n[cell.terrain] += 1
                if cell.feature in wild_features:
                    wild_n[cell.terrain] += 1

        herb_leader = spawn_group_leader("wild_crop")
        herb_activity = float(herb_leader.spawn_activity) if herb_leader else 0.55
        non_crop_species = {
            # Species tied to a neighbouring feature have dedicated spawn
            # passes below. Including them here spawned mushrooms/fallen wood
            # independently as well, bypassing proximity and doubling output.
            terrain: sorted(
                            (s for s in non_crop_on_terrain(terrain.name)
                             if not s.near_feature),
                            key=lambda s: (0 if s.edge_terrains else 1, s.key))
            for terrain in terrains
        }
        non_crop_peak = {
            terrain: max((species.spawn_peak * species.spawn_activity
                          for species in species_list), default=0.0)
            for terrain, species_list in non_crop_species.items()
        }
        crop_peak = (float(herb_leader.spawn_peak) * herb_activity
                     if herb_leader is not None else 0.0)

        def terrain_spawn_weight(terrain: TerrainType) -> float:
            from balance_config import active_balance

            return active_balance().get_float(f"FLORA_SPAWN_WEIGHT_{terrain.name}")

        def pick_crop_for_terrain(terrain: TerrainType, sample_day: float) -> str:
            """Use developer spawn chances as relative weights in this terrain."""
            keys = WILD_CROPS_BY_TERRAIN[terrain]
            weighted = [
                (
                    key,
                    max(
                        0.0,
                        species_spawn_rate(WILD_BY_KEY[key], sample_day)
                        * float(WILD_BY_KEY[key].spawn_activity),
                    ),
                )
                for key in keys
            ]
            total = sum(weight for _key, weight in weighted)
            if total <= 0.0:
                return self._forage_rng.choice(keys)
            pick = self._forage_rng.random() * total
            for key, weight in weighted:
                pick -= weight
                if pick <= 0.0:
                    return key
            return weighted[-1][0]

        def room(terrain: TerrainType) -> bool:
            tot = total_n.get(terrain, 0)
            if tot <= 0:
                return False
            return wild_n[terrain] < int(tot * WILD_PLANT_MAX_FRACTION)

        for y in range(self.rows):
            for x in range(self.cols):
                cell = self.cells[y][x]
                if cell.feature == FeatureType.REED:
                    species = resolve_species("REED", cell.crop_kind)
                    rate = (
                        species_despawn_rate(species, local_day(day, x, y))
                        if species is not None
                        else 0.0
                    )
                    if species is not None:
                        rate = min(1.0, rate + environmental_mortality_rate(
                            self.species_suitability_at(x, y, species).combined) / 8.0)
                    if self._forage_rng.random() < rate:
                        terrain = cell.terrain
                        cell.feature = FeatureType.NONE
                        cell.deposit = 0
                        cell.growth_ticks = 0
                        cell.crop_kind = None
                        if terrain in wild_n:
                            wild_n[terrain] = max(0, wild_n[terrain] - 1)
                    elif species is not None:
                        self._try_wild_species_spread(x, y, species, wild_n, total_n)
                elif cell.feature in (FeatureType.HERB, FeatureType.WILD_CROP):
                    if self._forage_rng.random() < herb_despawn_rate(day, x, y):
                        terrain = cell.terrain
                        cell.feature = FeatureType.NONE
                        cell.deposit = 0
                        cell.growth_ticks = 0
                        cell.crop_kind = None
                        if terrain in wild_n:
                            wild_n[terrain] = max(0, wild_n[terrain] - 1)
                    elif cell.feature == FeatureType.HERB:
                        species = resolve_species("HERB", cell.crop_kind)
                        if species is not None:
                            self._try_wild_species_spread(x, y, species, wild_n, total_n)
                elif (
                    cell.feature == FeatureType.NONE
                    and cell.terrain in non_crop_species
                    and room(cell.terrain)
                    and self._forage_rng.random()
                    < non_crop_peak[cell.terrain] * terrain_spawn_weight(cell.terrain)
                ):
                    local = local_day(day, x, y)
                    opportunities = [
                        (species, species_spawn_rate(species, local) * species.spawn_activity)
                        for species in non_crop_species[cell.terrain]
                        if species.spawn_peak > 0
                    ]
                    # These species share one empty-tile establishment opportunity;
                    # adding every chance made four flowers quadruple tick work and
                    # drove the terrain straight to its cap.
                    total_opportunity = sum(chance for _, chance in opportunities)
                    roll_chance = max((chance for _, chance in opportunities), default=0.0)
                    peak = non_crop_peak[cell.terrain]
                    if (opportunities and peak > 0
                            and self._forage_rng.random() < roll_chance / peak):
                        pick = self._forage_rng.random() * total_opportunity
                        species = opportunities[-1][0]
                        for candidate, chance in opportunities:
                            pick -= chance
                            if pick <= 0:
                                species = candidate
                                break
                        if self._species_can_occupy(x, y, species):
                            suitability = self.species_suitability_at(x, y, species)
                            if not environment_allows_establishment(species, suitability):
                                continue
                            if self._forage_rng.random() >= suitability.combined:
                                continue
                            try:
                                cell.feature = FeatureType[species.feature]
                            except KeyError:
                                pass
                            else:
                                cell.crop_kind = species.key
                                wild_n[cell.terrain] = wild_n.get(cell.terrain, 0) + 1
                # A vegetated ecology cell can hold up to three individually
                # selected plants. Each additional plant gets its own species
                # suitability roll and free subcell rather than cloning the
                # primary cell icon/anchor.
                for obj in list(cell.extra_objects):
                    if obj.feature not in (FeatureType.HERB, FeatureType.WILD_CROP):
                        continue
                    if self._forage_rng.random() < herb_despawn_rate(day, x, y):
                        cell.extra_objects.remove(obj)
                wild_here = int(cell.feature in (FeatureType.HERB, FeatureType.WILD_CROP)) + sum(
                    obj.feature in (FeatureType.HERB, FeatureType.WILD_CROP)
                    for obj in cell.extra_objects
                )
                if (
                    0 < wild_here < 3
                    and cell.terrain in WILD_CROPS_BY_TERRAIN
                    and crop_peak > 0
                    and self._forage_rng.random()
                    < crop_peak * 0.35 * terrain_spawn_weight(cell.terrain)
                ):
                    crop_key = pick_crop_for_terrain(
                        cell.terrain, local_day(day, x, y)
                    )
                    species = WILD_BY_KEY[crop_key]
                    score = self.species_suitability_at(x, y, species)
                    if (
                        environment_allows_establishment(species, score)
                        and self._forage_rng.random() < score.combined
                    ):
                        self.add_natural_object(
                            x,
                            y,
                            FeatureType.WILD_CROP,
                            crop_kind=crop_key,
                        )
                if (
                    cell.feature == FeatureType.NONE
                    and cell.terrain in WILD_CROPS_BY_TERRAIN
                    and room(cell.terrain)
                    and crop_peak > 0
                    and self._forage_rng.random()
                    < crop_peak * terrain_spawn_weight(cell.terrain)
                ):
                    base_chance = herb_spawn_rate(day, x, y) * herb_activity
                    if self._forage_rng.random() < base_chance / crop_peak:
                        crop_key = pick_crop_for_terrain(
                            cell.terrain, local_day(day, x, y)
                        )
                        species = WILD_BY_KEY[crop_key]
                        score = self.species_suitability_at(x, y, species)
                        if (environment_allows_establishment(species, score)
                                and self._forage_rng.random() < score.combined):
                            self._plant_wild_crop_patch(
                                x, y, crop_key, wild_n=wild_n, total_n=total_n,
                                environment_checked=True,
                            )
        self._wild_tick_disturbance = None

    def _try_wild_species_spread(self, x, y, species, wild_n, total_n) -> bool:
        """One modest propagule attempt; establishment is scored at the target."""
        if species.spread_chance <= 0:
            return False
        targets = [(nx, ny) for ny, nx in self.neighbourhood(x, y, radius=1)
                   if (nx, ny) != (x, y) and self.cells[ny][nx].feature == FeatureType.NONE]
        if not targets:
            return False
        nx, ny = self._forage_rng.choice(targets)
        target = self.cells[ny][nx]
        if not self._wild_plant_room(target.terrain, wild_n=wild_n, total_n=total_n):
            return False
        if not self.species_can_establish_at(nx, ny, species):
            return False
        neighbours = sum(1 for ay, ax in self.neighbourhood(nx, ny, radius=1)
                         if self.cells[ay][ax].crop_kind == species.key)
        pressure = min(WILD_PROPAGULE_MAX_MULTIPLIER,
                       1.0 + neighbours * WILD_PROPAGULE_NEIGHBOUR_BONUS)
        suitability = self.species_suitability_at(nx, ny, species).combined
        from balance_config import active_balance

        terrain_weight = active_balance().get_float(
            f"FLORA_SPAWN_WEIGHT_{target.terrain.name}"
        )
        if self._forage_rng.random() >= species.spread_chance * suitability * pressure * terrain_weight:
            return False
        target.feature = FeatureType[species.feature]
        target.crop_kind = species.key
        target.deposit = 0
        wild_n[target.terrain] = wild_n.get(target.terrain, 0) + 1
        return True

    def _plant_wild_crop_patch(
        self,
        x: int,
        y: int,
        crop_key: str,
        *,
        wild_n: dict[TerrainType, int] | None = None,
        total_n: dict[TerrainType, int] | None = None,
        environment_checked: bool = False,
    ) -> None:
        """Place a small contiguous wild-crop patch centred near (x, y)."""
        if not self.plant_wild_crop(x, y, crop_key, wild_n=wild_n, total_n=total_n,
                                    environment_checked=environment_checked):
            return
        species = WILD_BY_KEY.get(crop_key) or spawn_group_leader("wild_crop")
        lo, hi = (1, 4) if species is None else species.patch_extras
        extras = self._forage_rng.randint(int(lo), int(hi))
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

    def _tick_berry_fruit(self, day: float) -> None:
        """Refresh or clear berries on permanent bushes; never spawn/despawn bushes."""
        for y in range(self.rows):
            for x in range(self.cols):
                cell = self.cells[y][x]
                if cell.feature != FeatureType.BERRY_BUSH:
                    continue
                if berry_fruiting(day, x, y):
                    if cell.deposit <= 0 and cell.growth_ticks <= 0:
                        species = resolve_species("BERRY_BUSH", cell.crop_kind)
                        cell.deposit = (
                            int(species.yield_amount)
                            if species is not None
                            else BERRY_BUSH_YIELD
                        )
                        if not cell.crop_kind and species is not None:
                            cell.crop_kind = species.key
                else:
                    cell.deposit = 0
                    cell.growth_ticks = 0

    def _tick_mushrooms_seasonal(self, day: float) -> None:
        mushroom = WILD_BY_KEY["mushroom"]
        wood = WILD_BY_KEY["wood_bush"]
        mush_terrains = tuple(
            TerrainType[n] for n in mushroom.terrains if n in TerrainType.__members__
        )
        wood_terrains = tuple(
            TerrainType[n] for n in wood.terrains if n in TerrainType.__members__
        )
        # Winter clears mushrooms. Fallen wood ages independently for a year.
        if season_for_day(int(day)) == Season.WINTER:
            self.clear_mushrooms()
            return

        existing = [
            (x, y)
            for y in range(self.rows)
            for x in range(self.cols)
            if self.cells[y][x].feature == FeatureType.MUSHROOM
        ]
        for extra_y, row in enumerate(self.cells):
            for extra_x, cell in enumerate(row):
                for obj in list(cell.extra_objects):
                    if (
                        obj.feature == FeatureType.MUSHROOM
                        and self._forage_rng.random()
                        < mushroom_despawn_rate(day, extra_x, extra_y)
                    ):
                        cell.extra_objects.remove(obj)
        for mx, my in existing:
            if self._forage_rng.random() < mushroom_despawn_rate(day, mx, my):
                cell = self.cells[my][mx]
                cell.feature = FeatureType.NONE
                cell.deposit = 0
                cell.crop_kind = None
                continue
            # Seasonal spread while mushrooms are peaking.
            for ny, nx in self.neighbourhood(mx, my, radius=1):
                if (nx, ny) == (mx, my):
                    continue
                cell = self.cells[ny][nx]
                if (
                    cell.feature == FeatureType.NONE
                    and cell.terrain in mush_terrains
                    and self.species_can_establish_at(nx, ny, mushroom)
                    and self._forage_rng.random()
                    < MUSHROOM_SPREAD_CHANCE
                    * mushroom_spawn_rate(day, nx, ny)
                    * 20.0
                    * self.species_suitability_at(nx, ny, mushroom).combined
                ):
                    cell.feature = FeatureType.MUSHROOM
                    cell.crop_kind = mushroom.key

        for y in range(self.rows):
            for x in range(self.cols):
                if self.cells[y][x].feature != FeatureType.TREE:
                    continue
                if self._forage_rng.random() < mushroom_spawn_rate(day, x, y) * 0.35:
                    self.add_natural_object(
                        x,
                        y,
                        FeatureType.MUSHROOM,
                        crop_kind=mushroom.key,
                    )
                for ny, nx in self.neighbourhood(x, y, radius=1):
                    if (nx, ny) == (x, y):
                        continue
                    cell = self.cells[ny][nx]
                    if (
                        cell.feature == FeatureType.NONE
                        and cell.terrain in mush_terrains
                        and self.species_can_establish_at(nx, ny, mushroom)
                        and self._forage_rng.random()
                        < mushroom_spawn_rate(day, nx, ny)
                        * self.species_suitability_at(nx, ny, mushroom).combined
                    ):
                        cell.feature = FeatureType.MUSHROOM
                        cell.crop_kind = mushroom.key

        # Autumn fallen wood beside trees (independent of mushrooms). Build a
        # candidate set first so a tile gets one roll per seasonal tick, not one
        # roll for every adjacent tree in dense forest.
        wood_candidates: set[tuple[int, int]] = set()
        for y in range(self.rows):
            for x in range(self.cols):
                if self.cells[y][x].feature != FeatureType.TREE:
                    continue
                for ny, nx in self.neighbourhood(x, y, radius=1):
                    if (nx, ny) == (x, y):
                        continue
                    wood_candidates.add((nx, ny))
        for nx, ny in wood_candidates:
            cell = self.cells[ny][nx]
            if (
                cell.terrain in wood_terrains
                and self._forage_rng.random() < wood_bush_spawn_rate(day, nx, ny)
            ):
                if cell.feature == FeatureType.NONE:
                    cell.feature = FeatureType.WOOD_BUSH
                    cell.crop_kind = wood.key
                    cell.deposit = WOOD_BUSH_YIELD
                    cell.growth_ticks = self._fallen_wood_lifetime_ticks()
                else:
                    self.add_natural_object(
                        nx,
                        ny,
                        FeatureType.WOOD_BUSH,
                        crop_kind=wood.key,
                        deposit=WOOD_BUSH_YIELD,
                        growth_ticks=self._fallen_wood_lifetime_ticks(),
                    )

    def clear_mushrooms(self) -> None:
        """Remove seasonal mushrooms; fallen wood has its own lifetime."""
        for y in range(self.rows):
            for x in range(self.cols):
                cell = self.cells[y][x]
                if cell.feature == FeatureType.MUSHROOM:
                    cell.feature = FeatureType.NONE
                    cell.deposit = 0
                    cell.crop_kind = None
                cell.extra_objects = [
                    obj
                    for obj in cell.extra_objects
                    if obj.feature != FeatureType.MUSHROOM
                ]

    def respawn_flora(self, day: float, *, passes: int = 32) -> int:
        """Replace non-tree natural flora for the current season and ecology."""
        flora = {
            FeatureType.WILD_CROP,
            FeatureType.HERB,
            FeatureType.REED,
            FeatureType.MUSHROOM,
            FeatureType.BERRY_BUSH,
            FeatureType.WOOD_BUSH,
        }
        for row in self.cells:
            for cell in row:
                if cell.feature in flora:
                    cell.feature = FeatureType.NONE
                    cell.deposit = 0
                    cell.growth_ticks = 0
                    cell.crop_kind = None
                cell.extra_objects = [obj for obj in cell.extra_objects if obj.feature not in flora]

        # Permanent fruiting plants do not use the recurring spawn envelope,
        # so restore their configured initial population at the best live sites.
        for species in WILD_BY_KEY.values():
            if not species.fruiting or species.initial_count <= 0:
                continue
            try:
                feature = FeatureType[species.feature]
            except KeyError:
                continue
            sites = []
            for y, row in enumerate(self.cells):
                for x, cell in enumerate(row):
                    if cell.feature != FeatureType.NONE or not self._species_can_occupy(x, y, species):
                        continue
                    suitability = self.species_suitability_at(x, y, species)
                    if environment_allows_establishment(species, suitability):
                        sites.append((suitability.combined, self._forage_rng.random(), x, y))
            sites.sort(reverse=True)
            for _score, _tie, x, y in sites[:int(species.initial_count)]:
                cell = self.cells[y][x]
                cell.feature = feature
                cell.crop_kind = species.key
                cell.deposit = 0
                cell.growth_ticks = 0

        # Repeated canonical seasonal ticks build an established population,
        # while retaining the current day's spawn windows and live niche maps.
        for _ in range(max(1, int(passes))):
            self._tick_herbs_seasonal(day)
            self._tick_mushrooms_seasonal(day)
        self._tick_berry_fruit(day)

        return sum(
            int(cell.feature in flora)
            + sum(obj.feature in flora for obj in cell.extra_objects)
            for row in self.cells
            for cell in row
        )

    def reconcile_flora_with_catalogue(self) -> int:
        """Remove loaded wild flora whose authored terrain match is no longer valid."""
        flora = {FeatureType.WILD_CROP,FeatureType.HERB,FeatureType.REED,FeatureType.MUSHROOM,FeatureType.BERRY_BUSH,FeatureType.WOOD_BUSH}
        removed=0
        for row in self.cells:
            for cell in row:
                if cell.feature in flora:
                    species=resolve_species(cell.feature.name,cell.crop_kind)
                    if species is None or cell.terrain.name not in species.terrains:
                        cell.feature=FeatureType.NONE;cell.deposit=0;cell.growth_ticks=0;cell.crop_kind=None;removed+=1
                kept=[]
                for obj in cell.extra_objects:
                    if obj.feature in flora:
                        species=resolve_species(obj.feature.name,obj.crop_kind)
                        if species is None or cell.terrain.name not in species.terrains:
                            removed+=1;continue
                    kept.append(obj)
                cell.extra_objects=kept
        return removed

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

    def age_trees_one_year(self) -> int:
        """Age mature trees; old or heavily disturbed trees become fallen wood."""
        from balance_config import active_balance

        balance = active_balance()
        lifespan = max(4, balance.get_int("TREE_LIFESPAN_YEARS"))
        base_risk = balance.get_float("TREE_OLD_AGE_DEATH_CHANCE")
        fallen = 0
        for y, row in enumerate(self.cells):
            for x, cell in enumerate(row):
                if cell.feature != FeatureType.TREE:
                    continue
                cell.tree_age_years = max(0, int(cell.tree_age_years)) + 1
                if cell.tree_age_years < lifespan:
                    continue
                disturbance = effective_disturbance_at(self, x, y)
                age_factor = 1.0 + (cell.tree_age_years - lifespan) / max(1, lifespan)
                risk = min(0.95, base_risk * age_factor + disturbance * 0.20)
                if self._sprout_rng.random() >= risk:
                    continue
                cell.feature = FeatureType.WOOD_BUSH
                cell.tree_species = None
                cell.tree_age_years = 0
                cell.deposit = 1
                cell.growth_ticks = self._fallen_wood_lifetime_ticks()
                cell.crop_kind = "wood_bush"
                self.note_growth_cell(x, y)
                fallen += 1
        if fallen:
            self.update_forest_floor()
        return fallen

    def ensure_tree_ages(self, *, rng: random.Random | None = None) -> int:
        """Give pre-existing mature trees varied ages (generation/legacy saves)."""
        from balance_config import active_balance

        lifespan = max(3, active_balance().get_int("TREE_LIFESPAN_YEARS"))
        age_rng = rng or random.Random(self.seed ^ 0x7AEE)
        assigned = 0
        for row in self.cells:
            for cell in row:
                if cell.feature != FeatureType.TREE or cell.tree_age_years > 0:
                    continue
                # Established forest spans young through near-old trees, while
                # newly matured saplings retain age zero until the next year.
                cell.tree_age_years = age_rng.randint(1, max(1, lifespan - 1))
                assigned += 1
        return assigned

    def plant_sapling(self, x: int, y: int, species: str | None = None) -> bool:
        cell = self.get_cell(x, y)
        if cell is None:
            return False
        if cell.terrain not in PLANTABLE_LAND:
            return False
        tree = resolve_tree(species)
        if cell.feature != FeatureType.NONE:
            planted = self.add_natural_object(
                x,
                y,
                FeatureType.SAPLING,
                tree_species=tree.key,
                tree_age_years=0,
                growth_ticks=growth_ticks_for(tree),
            )
            if planted is None:
                return False
            self.note_growth_cell(x, y)
            return True
        cell.feature = FeatureType.SAPLING
        cell.tree_species = tree.key
        cell.tree_age_years = 0
        cell.growth_ticks = growth_ticks_for(tree)
        cell.deposit = 0
        self.note_growth_cell(x, y)
        return True

    def plant_berry_bush(self, x: int, y: int) -> bool:
        cell = self.get_cell(x, y)
        if cell is None or cell.feature != FeatureType.NONE:
            return False
        berry = WILD_BY_KEY["berry_bush"]
        berry_terrains = tuple(
            TerrainType[n] for n in berry.terrains if n in TerrainType.__members__
        )
        if cell.terrain not in berry_terrains:
            return False
        if not self._wild_plant_room(cell.terrain):
            return False
        cell.feature = FeatureType.BERRY_BUSH
        cell.crop_kind = berry.key
        # Fruit appears only during berry season; the bush itself is permanent.
        cell.deposit = 0
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
        environment_checked: bool = False,
    ) -> bool:
        cell = self.get_cell(x, y)
        if cell is None:
            return False
        allowed = WILD_CROPS_BY_TERRAIN.get(cell.terrain)
        if not allowed:
            return False
        if crop_key not in CROP_BY_KEY:
            crop_key = allowed[0]
        if crop_key not in allowed:
            return False
        if cell.feature != FeatureType.NONE:
            if not self._wild_plant_room(
                cell.terrain, wild_n=wild_n, total_n=total_n
            ):
                return False
            return self.add_natural_object(
                x,
                y,
                FeatureType.WILD_CROP,
                crop_kind=crop_key,
            ) is not None
        species = WILD_BY_KEY.get(crop_key)
        if species is not None and not environment_checked:
            if not self._species_can_occupy(x, y, species):
                return False
            suitability = self.species_suitability_at(x, y, species)
            if not environment_allows_establishment(species, suitability):
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
        cell.tree_species = None
        from soil import cap_fertility_for_soil

        cap_fertility_for_soil(cell)
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
        cell.weeds = 0.0
        self.note_growth_cell(x, y)
        return True

    def sow_herb_crop(self, x: int, y: int) -> bool:
        """Legacy: sow sage with default spring growth."""
        from seasons import TICKS_PER_DAY

        crop = CROP_BY_KEY["sage"]
        return self.sow_crop(x, y, crop.key, crop.growth_days * TICKS_PER_DAY)

    def crop_herb_ready(self, x: int, y: int) -> bool:
        cell = self.get_cell(x, y)
        if cell is None or cell.feature != FeatureType.CROP_HERB:
            return False
        return cell.growth_ticks <= 0 and cell.deposit >= 0

    def harvest_crop_herb(self, x: int, y: int) -> str | None:
        """Harvest a ready farm crop; returns crop_kind or None.

        Clears annual plants. Perennials remain dormant for spring regrowth.
        """
        cell = self.get_cell(x, y)
        if cell is None or cell.feature != FeatureType.CROP_HERB:
            return None
        if cell.growth_ticks > 0:
            return None
        kind = cell.crop_kind or "sage"
        crop = CROP_BY_KEY.get(kind)
        from soil import drop_fertility_on_harvest

        drop_fertility_on_harvest(cell)
        cell.compost_cycle_applied = False
        cell.mineral_cycle_applied = False
        cell.weed_suppression = 0.0
        if crop is not None and crop.perennial:
            cell.growth_ticks = 0
            cell.deposit = -1  # harvested/dormant perennial sentinel
            cell.weeds = 0.0
            return kind
        cell.feature = FeatureType.NONE
        cell.growth_ticks = 0
        cell.crop_kind = None
        cell.deposit = 0
        return kind

    def clear_weeds(self, x: int, y: int) -> bool:
        """Hoe weeds off a crop square. Does not harvest."""
        cell = self.get_cell(x, y)
        if cell is None or cell.feature != FeatureType.CROP_HERB:
            return False
        if float(getattr(cell, "weeds", 0.0)) <= 0.0:
            return False
        cell.weeds = 0.0
        return True

    def harvest_mushroom(self, x: int, y: int) -> bool:
        cell = self.get_cell(x, y)
        if cell is None or cell.feature != FeatureType.MUSHROOM:
            return False
        cell.feature = FeatureType.NONE
        cell.crop_kind = None
        return True

    def harvest_wood_bush(self, x: int, y: int) -> int:
        cell = self.get_cell(x, y)
        if cell is None or cell.feature != FeatureType.WOOD_BUSH or cell.deposit <= 0:
            return 0
        taken = min(1, cell.deposit)
        cell.deposit -= taken
        if cell.deposit <= 0:
            cell.feature = FeatureType.NONE
            cell.crop_kind = None
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
        """Harvest wild crop/herb/reed; returns wild species / crop key."""
        cell = self.get_cell(x, y)
        if cell is None:
            return None
        if cell.feature == FeatureType.REED:
            kind = cell.crop_kind or "reed"
            cell.feature = FeatureType.NONE
            cell.crop_kind = None
            return kind
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
        cell.crop_kind = None
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
        cell.tree_species = None
        cell.tree_age_years = 0
        self.invalidate_movement_cache()
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
            cell.tree_age_years = 0
            cell.icon_variant = None
            self.invalidate_movement_cache()
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
        self.invalidate_movement_cache()
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
        if cell.meat_deposit <= 0:
            cell.meat_anchor_slot = None
        return taken

    def add_meat_deposit(self, x: int, y: int, amount: int) -> None:
        cell = self.get_cell(x, y)
        if cell is None:
            return
        if cell.meat_deposit <= 0:
            cell.meat_anchor_slot = self.free_loose_object_anchor(x, y, "MEAT")
        cell.meat_deposit += amount

    def harvest_hide(self, x: int, y: int, amount: int = 1) -> int:
        cell = self.get_cell(x, y)
        if cell is None or cell.hide_deposit <= 0:
            return 0
        taken = min(amount, cell.hide_deposit)
        cell.hide_deposit -= taken
        if cell.hide_deposit <= 0:
            cell.hide_anchor_slot = None
        return taken

    def add_hide_deposit(self, x: int, y: int, amount: int) -> None:
        cell = self.get_cell(x, y)
        if cell is None:
            return
        if cell.hide_deposit <= 0:
            cell.hide_anchor_slot = self.free_loose_object_anchor(x, y, "HIDE")
        cell.hide_deposit += amount

    def harvest_fur(self, x: int, y: int, amount: int = 1) -> int:
        cell = self.get_cell(x, y)
        if cell is None or cell.fur_deposit <= 0:
            return 0
        taken = min(amount, cell.fur_deposit)
        cell.fur_deposit -= taken
        if cell.fur_deposit <= 0:
            cell.fur_anchor_slot = None
        return taken

    def add_fur_deposit(self, x: int, y: int, amount: int) -> None:
        cell = self.get_cell(x, y)
        if cell is None:
            return
        if cell.fur_deposit <= 0:
            cell.fur_anchor_slot = self.free_loose_object_anchor(x, y, "FUR")
        cell.fur_deposit += amount

    def harvest_feathers(self, x: int, y: int, amount: int = 1) -> int:
        cell = self.get_cell(x, y)
        if cell is None or cell.feather_deposit <= 0:
            return 0
        taken = min(amount, cell.feather_deposit)
        cell.feather_deposit -= taken
        if cell.feather_deposit <= 0:
            cell.feather_anchor_slot = None
        return taken

    def add_feather_deposit(self, x: int, y: int, amount: int) -> None:
        cell = self.get_cell(x, y)
        if cell is not None:
            if cell.feather_deposit <= 0:
                cell.feather_anchor_slot = self.free_loose_object_anchor(
                    x, y, "FEATHER"
                )
            cell.feather_deposit += amount

    def harvest_fish(self, x: int, y: int, amount: int = 1) -> int:
        cell = self.get_cell(x, y)
        if cell is None or cell.fish_deposit <= 0:
            return 0
        taken = min(amount, cell.fish_deposit)
        cell.fish_deposit -= taken
        if cell.fish_deposit <= 0:
            cell.fish_anchor_slot = None
        return taken

    def add_fish_deposit(self, x: int, y: int, amount: int) -> tuple[int, int] | None:
        """Leave caught fish on mainland shore (avoid mid-lake islets). Returns deposit tile."""
        shore = self.best_fish_shore(x, y)
        if shore is not None:
            sx, sy = shore
            if self.cells[sy][sx].fish_deposit <= 0:
                self.cells[sy][sx].fish_anchor_slot = self.free_loose_object_anchor(
                    sx, sy, "FISH"
                )
            self.cells[sy][sx].fish_deposit += amount
            return shore
        cell = self.get_cell(x, y)
        if cell is None:
            return None
        if cell.fish_deposit <= 0:
            cell.fish_anchor_slot = self.free_loose_object_anchor(x, y, "FISH")
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

    def grass_patches(self) -> list[list[tuple[int, int]]]:
        """Connected grass terrain patches (8-connected)."""
        cells = {
            (x, y)
            for y in range(self.rows)
            for x in range(self.cols)
            if self.cells[y][x].terrain == TerrainType.GRASS
        }
        return self._connected_patches(cells)

    def riparian_patches(self) -> list[list[tuple[int, int]]]:
        """Connected riparian terrain patches (8-connected)."""
        cells = {
            (x, y)
            for y in range(self.rows)
            for x in range(self.cols)
            if self.cells[y][x].terrain == TerrainType.RIPARIAN
        }
        return self._connected_patches(cells)

    def water_patches(self) -> list[list[tuple[int, int]]]:
        """Connected components of water cells."""
        rev = self.terrain_revision
        cache = getattr(self, "_water_patches_cache", None)
        if cache is not None and getattr(self, "_water_patches_rev", None) == rev:
            return cache
        cache = self._connected_patches(set(self.water_cells()))
        self._water_patches_cache = cache
        self._water_patches_rev = rev
        return cache

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

    def sync_hardscape_disturbance(
        self, traffic: dict[tuple[int, int], float] | None = None
    ) -> None:
        """Mix urban floors with path-traffic wear into the disturbance field."""
        from balance_config import active_balance

        bal = active_balance()
        urban = bal.get_float("DISTURBANCE_URBAN_LEVEL")
        path = bal.get_float("DISTURBANCE_PATH_LEVEL")
        cap = max(1e-6, bal.get_float("PATH_TRAFFIC_OVERLAY_MAX"))
        dmax = bal.get_float("DISTURBANCE_MAX")
        wear_map = traffic or {}
        for y in range(self.rows):
            for x in range(self.cols):
                cell = self.cells[y][x]
                wear_d = min(dmax, float(wear_map.get((x, y), 0.0)) / cap)
                if cell.terrain == TerrainType.URBAN:
                    cell.disturbance = max(urban, wear_d)
                elif cell_has_path(cell):
                    cell.disturbance = max(path, wear_d)
                elif wear_d > 0:
                    cell.disturbance = max(cell.disturbance, wear_d)

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
        if cell_has_path(cell):
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
            elif cell_has_path(ncell):
                ncell.disturbance = max(
                    ncell.disturbance, bal.get_float("DISTURBANCE_PATH_LEVEL")
                )
            else:
                ncell.disturbance = min(dmax, ncell.disturbance + amount)
