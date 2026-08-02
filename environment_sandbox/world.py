"""World grid: terrain, features, generation, and neighbourhood queries.

Interaction policy
------------------
The player interacts only with the cell they currently stand on (press E).
Mouse drag draws rectangular task areas for hired villagers.

Future extension points:
- soil fertility / moisture fields
- crop / seasonal state per cell
- habitat connectivity graphs
- erosion risk maps
- GIS-derived terrain import
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
from typing import Iterator

from crops import CROP_BY_KEY, CROP_KEYS
from seasons import (
    berry_despawn_rate,
    berry_spawn_rate,
    growth_halted,
    herb_despawn_rate,
    herb_spawn_rate,
    mushroom_despawn_rate,
    mushroom_spawn_rate,
    trees_grow_factor,
    trees_spread_factor,
)
from settings import (
    BERRY_BUSH_YIELD,
    BERRY_REGEN_TICKS,
    BERRY_SPREAD_INTERVAL,
    DISTURBANCE_INTERACTION_BOOST,
    DISTURBANCE_MAX,
    DISTURBANCE_NEIGHBOUR_SPREAD,
    HERB_TICK_INTERVAL,
    MUSHROOM_SPREAD_CHANCE,
    MUSHROOM_TICK_INTERVAL,
    NATURAL_SPROUT_CHANCE,
    NATURAL_SPROUT_INTERVAL,
    NATURAL_SPROUT_MIN_PATCH,
    RANDOM_SEED,
    ROCK_LARGE_MAX,
    ROCK_LARGE_MIN,
    ROCK_SMALL_MAX,
    ROCK_SMALL_MIN,
    SAPLING_GROWTH_TICKS,
    TREE_WOOD_DEPOSIT,
)


class TerrainType(Enum):
    SOIL = auto()
    GRASS = auto()
    WATER = auto()
    ROCK = auto()  # bare rocky ground (distinct from rock resource feature)


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
    CONSTRUCTION_SITE = auto()
    MUSHROOM = auto()
    BERRY_BUSH = auto()
    HERB = auto()  # legacy; migrated to WILD_CROP on load
    WILD_CROP = auto()  # wild crop patches (any CropDef key)
    CROP_HERB = auto()  # farmed crop (growth_ticks > 0 while growing)


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

    def habitat_category(self) -> str:
        if self.feature != FeatureType.NONE:
            return self.feature.name.lower()
        return self.terrain.name.lower()


class World:
    """Grid landscape with generation and local queries."""

    def __init__(self, cols: int | None = None, rows: int | None = None, seed: int = RANDOM_SEED) -> None:
        # Resolve at construction time so configure_for_display() can resize the grid.
        import settings as cfg

        self.cols = cfg.GRID_COLS if cols is None else cols
        self.rows = cfg.GRID_ROWS if rows is None else rows
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
        self.generate()

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

        # Compact water ponds (not map-spanning lakes).
        self._place_clusters(
            rng,
            count=max(2, self.cols // 20),
            radius=3,
            density=0.72,
            apply=lambda c: setattr(c, "terrain", TerrainType.WATER),
        )
        self._expand_terrain_patches(rng, TerrainType.WATER, passes=2, chance=0.55)
        self._cull_isolated_terrain(TerrainType.WATER, min_neighbours=1)

        # Compact grey rock outcrops.
        def _paint_rock(cell: Cell) -> None:
            if cell.terrain != TerrainType.WATER:
                cell.terrain = TerrainType.ROCK

        self._place_clusters(
            rng,
            count=max(2, self.cols // 22),
            radius=3,
            density=0.65,
            apply=_paint_rock,
        )
        self._expand_terrain_patches(rng, TerrainType.ROCK, passes=2, chance=0.5)
        self._cull_isolated_terrain(TerrainType.ROCK, min_neighbours=1)

        # Larger forest clearings: soil patches, then dense tree cover on them.
        forest_centres: list[tuple[int, int]] = []
        for _ in range(max(3, self.cols // 10)):
            cx = rng.randint(2, self.cols - 3)
            cy = rng.randint(2, self.rows - 3)
            forest_centres.append((cx, cy))
            for ny, nx in self.neighbourhood(cx, cy, radius=3):
                cell = self.cells[ny][nx]
                if cell.terrain == TerrainType.WATER:
                    continue
                # Soil under the canopy; keep rock outcrops if already placed.
                if cell.terrain != TerrainType.ROCK and rng.random() < 0.85:
                    cell.terrain = TerrainType.SOIL

        # Grow soil under forests into coherent clearings; smooth grass/soil noise.
        self._expand_terrain_patches(rng, TerrainType.SOIL, passes=2, chance=0.5)
        self._expand_terrain_patches(rng, TerrainType.GRASS, passes=1, chance=0.45)
        self._cull_isolated_terrain(TerrainType.SOIL, min_neighbours=1)
        self._cull_isolated_terrain(TerrainType.GRASS, min_neighbours=1)

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
                    cell.feature = FeatureType.TREE
                    cell.deposit = TREE_WOOD_DEPOSIT

        # A few smaller mixed tree clumps on remaining soil/grass.
        for _ in range(3):
            cx = rng.randint(1, self.cols - 2)
            cy = rng.randint(1, self.rows - 2)
            for ny, nx in self.neighbourhood(cx, cy, radius=1):
                cell = self.cells[ny][nx]
                if (
                    cell.feature == FeatureType.NONE
                    and cell.terrain in (TerrainType.GRASS, TerrainType.SOIL)
                    and rng.random() < 0.5
                ):
                    cell.feature = FeatureType.TREE
                    cell.deposit = TREE_WOOD_DEPOSIT

        # Small rock deposits on soil/grass.
        placed_small = 0
        attempts = 0
        while placed_small < 14 and attempts < 300:
            attempts += 1
            x = rng.randint(0, self.cols - 1)
            y = rng.randint(0, self.rows - 1)
            cell = self.cells[y][x]
            if (
                cell.feature == FeatureType.NONE
                and cell.terrain in (TerrainType.GRASS, TerrainType.SOIL)
            ):
                cell.feature = FeatureType.ROCK
                cell.deposit = rng.randint(ROCK_SMALL_MIN, ROCK_SMALL_MAX)
                placed_small += 1

        # Large rock deposits (20+) only on grey rock terrain patches.
        rock_tiles = [
            (x, y)
            for y in range(self.rows)
            for x in range(self.cols)
            if self.cells[y][x].terrain == TerrainType.ROCK
            and self.cells[y][x].feature == FeatureType.NONE
        ]
        rng.shuffle(rock_tiles)
        large_count = min(len(rock_tiles), max(3, len(rock_tiles) // 2))
        for x, y in rock_tiles[:large_count]:
            cell = self.cells[y][x]
            cell.feature = FeatureType.ROCK
            cell.deposit = rng.randint(ROCK_LARGE_MIN, ROCK_LARGE_MAX)

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
        home_x = max(1, self.cols // 4)
        home_y = self.rows // 2
        self.cells[home_y][home_x].terrain = TerrainType.SOIL
        self.cells[home_y][home_x].feature = FeatureType.HOME
        self.home_pos = (home_x, home_y)

        # Work station beside home — stand here and press E to hire villagers.
        station_x = home_x + 1
        station_y = home_y
        if not self.in_bounds(station_x, station_y):
            station_x = home_x - 1
        self.cells[station_y][station_x].terrain = TerrainType.SOIL
        self.cells[station_y][station_x].feature = FeatureType.WORKSTATION
        self.workstation_pos = (station_x, station_y)

        # Clear a small yard around home/workstation and choose a free start cell.
        clear_centres = [self.home_pos, self.workstation_pos]
        protected = {FeatureType.HOME, FeatureType.WORKSTATION}
        for cx, cy in clear_centres:
            for ny, nx in self.neighbourhood(cx, cy, radius=1):
                cell = self.cells[ny][nx]
                if cell.feature not in protected:
                    if cell.feature in (
                        FeatureType.TREE,
                        FeatureType.ROCK,
                        FeatureType.SAPLING,
                        FeatureType.MUSHROOM,
                        FeatureType.BERRY_BUSH,
                        FeatureType.HERB,
                        FeatureType.WILD_CROP,
                    ):
                        cell.feature = FeatureType.NONE
                        cell.deposit = 0
                        cell.growth_ticks = 0
                        cell.crop_kind = None
                    if cell.terrain == TerrainType.WATER:
                        cell.terrain = TerrainType.GRASS

        start_candidates = [
            (nx, ny)
            for ny, nx in self.neighbourhood(home_x, home_y, radius=1)
            if (nx, ny) not in (self.home_pos, self.workstation_pos)
            and self.cells[ny][nx].feature == FeatureType.NONE
            and self.cells[ny][nx].terrain != TerrainType.WATER
        ]
        if start_candidates:
            self.start_pos = start_candidates[0]
        else:
            self.start_pos = (home_x, home_y - 1 if home_y > 0 else home_y + 1)

        # Ensure start cell is walkable / empty.
        sx, sy = self.start_pos
        if self.in_bounds(sx, sy):
            self.cells[sy][sx].feature = FeatureType.NONE
            if self.cells[sy][sx].terrain == TerrainType.WATER:
                self.cells[sy][sx].terrain = TerrainType.GRASS
        self.bump_terrain()

    def _paint_base_grass_soil(self, rng: random.Random) -> None:
        """Fill the map with large grass/soil regions via coarse value noise."""
        # A few random influence points → smooth-ish regions without per-cell coin flips.
        blobs: list[tuple[float, float, float, TerrainType]] = []
        n_blobs = max(6, (self.cols * self.rows) // 40)
        for _ in range(n_blobs):
            bx = rng.uniform(0, self.cols)
            by = rng.uniform(0, self.rows)
            br = rng.uniform(2.5, 6.5)
            kind = TerrainType.SOIL if rng.random() < 0.38 else TerrainType.GRASS
            blobs.append((bx, by, br, kind))

        for y in range(self.rows):
            for x in range(self.cols):
                # Default grass; soil wins when inside a soil blob more than grass.
                soil_w = 0.0
                grass_w = 0.15  # slight grass bias
                for bx, by, br, kind in blobs:
                    d = ((x + 0.5 - bx) ** 2 + (y + 0.5 - by) ** 2) ** 0.5
                    if d >= br:
                        continue
                    w = (1.0 - d / br) ** 2
                    if kind == TerrainType.SOIL:
                        soil_w += w
                    else:
                        grass_w += w
                self.cells[y][x].terrain = (
                    TerrainType.SOIL if soil_w > grass_w else TerrainType.GRASS
                )

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
                    if terrain == TerrainType.ROCK and self.cells[y][x].terrain == TerrainType.WATER:
                        continue
                    if terrain == TerrainType.WATER:
                        pass
                    elif self.cells[y][x].terrain == TerrainType.WATER:
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
            TerrainType.ROCK: TerrainType.GRASS,
            TerrainType.SOIL: TerrainType.GRASS,
            TerrainType.GRASS: TerrainType.SOIL,
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
            self.cells[y][x].terrain = fallback

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
        """Water is impassable; features never block movement in this prototype."""
        cell = self.get_cell(x, y)
        if cell is None:
            return False
        return cell.terrain != TerrainType.WATER

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
                        cell.feature = FeatureType.TREE
                        cell.growth_ticks = 0
                        cell.deposit = TREE_WOOD_DEPOSIT
                elif grow_step > 0 and cell.feature == FeatureType.BERRY_BUSH and cell.growth_ticks > 0:
                    cell.growth_ticks -= grow_step * ticks
                    if cell.growth_ticks <= 0 and cell.deposit <= 0:
                        cell.deposit = BERRY_BUSH_YIELD
                        cell.growth_ticks = 0
                elif grow_step > 0 and cell.feature == FeatureType.CROP_HERB and cell.growth_ticks > 0:
                    cell.growth_ticks -= grow_step * ticks
                    if cell.growth_ticks < 0:
                        cell.growth_ticks = 0
                if decay_per_tick > 0 and cell.disturbance > 0:
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
        """Wild crop patches on grass (replaces generic herbs)."""
        for y in range(self.rows):
            for x in range(self.cols):
                cell = self.cells[y][x]
                if cell.feature in (FeatureType.HERB, FeatureType.WILD_CROP):
                    if self._forage_rng.random() < herb_despawn_rate(day, x, y):
                        cell.feature = FeatureType.NONE
                        cell.deposit = 0
                        cell.growth_ticks = 0
                        cell.crop_kind = None
                elif (
                    cell.feature == FeatureType.NONE
                    and cell.terrain == TerrainType.GRASS
                    and self._forage_rng.random() < herb_spawn_rate(day, x, y) * 0.55
                ):
                    crop_key = self._forage_rng.choice(CROP_KEYS)
                    self._plant_wild_crop_patch(x, y, crop_key)

    def _plant_wild_crop_patch(self, x: int, y: int, crop_key: str) -> None:
        """Place a small contiguous wild-crop patch centred near (x, y)."""
        if not self.plant_wild_crop(x, y, crop_key):
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
            if self.plant_wild_crop(nx, ny, crop_key):
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

        # Spread / appear onto empty grass.
        for y in range(self.rows):
            for x in range(self.cols):
                cell = self.cells[y][x]
                if (
                    cell.feature == FeatureType.NONE
                    and cell.terrain == TerrainType.GRASS
                    and self._forage_rng.random() < berry_spawn_rate(day, x, y)
                ):
                    self.plant_berry_bush(x, y)

    def _tick_mushrooms_seasonal(self, day: float) -> None:
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
                    and cell.terrain == TerrainType.SOIL
                    and self._forage_rng.random()
                    < MUSHROOM_SPREAD_CHANCE * mushroom_spawn_rate(day, nx, ny) * 20.0
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
                        and cell.terrain == TerrainType.SOIL
                        and self._forage_rng.random() < mushroom_spawn_rate(day, nx, ny)
                    ):
                        cell.feature = FeatureType.MUSHROOM

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
                    if cell.feature == FeatureType.NONE and cell.terrain in (
                        TerrainType.SOIL,
                        TerrainType.GRASS,
                    ):
                        candidates.append((nx, ny))
            if not candidates:
                continue
            sx, sy = self._sprout_rng.choice(candidates)
            self.plant_sapling(sx, sy)

    def plant_sapling(self, x: int, y: int) -> bool:
        cell = self.get_cell(x, y)
        if cell is None:
            return False
        if cell.feature != FeatureType.NONE:
            return False
        if cell.terrain not in (TerrainType.SOIL, TerrainType.GRASS):
            return False
        cell.feature = FeatureType.SAPLING
        cell.growth_ticks = SAPLING_GROWTH_TICKS
        cell.deposit = 0
        return True

    def plant_berry_bush(self, x: int, y: int) -> bool:
        cell = self.get_cell(x, y)
        if cell is None or cell.feature != FeatureType.NONE:
            return False
        if cell.terrain != TerrainType.GRASS:
            return False
        cell.feature = FeatureType.BERRY_BUSH
        cell.deposit = BERRY_BUSH_YIELD
        cell.growth_ticks = 0
        return True

    def plant_herb(self, x: int, y: int, crop_key: str = "sage") -> bool:
        """Legacy alias for planting a single wild crop plant."""
        return self.plant_wild_crop(x, y, crop_key)

    def plant_wild_crop(self, x: int, y: int, crop_key: str) -> bool:
        cell = self.get_cell(x, y)
        if cell is None or cell.feature != FeatureType.NONE:
            return False
        if cell.terrain != TerrainType.GRASS:
            return False
        if crop_key not in CROP_BY_KEY:
            crop_key = "sage"
        cell.feature = FeatureType.WILD_CROP
        cell.crop_kind = crop_key
        cell.deposit = 0
        cell.growth_ticks = 0
        return True

    def plough_tile(self, x: int, y: int) -> bool:
        """Turn a field tile into bare soil ready for sowing."""
        cell = self.get_cell(x, y)
        if cell is None:
            return False
        if cell.terrain == TerrainType.WATER or cell.terrain == TerrainType.ROCK:
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
            FeatureType.FIELD,
            FeatureType.CONSTRUCTION_SITE,
        ):
            return False
        if cell.terrain == TerrainType.SOIL and cell.feature == FeatureType.NONE:
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
        if cell.terrain != TerrainType.SOIL:
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
        """Harvest wild crop/herb; returns crop_kind or None."""
        cell = self.get_cell(x, y)
        if cell is None:
            return None
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
        """Take up to `amount` wood from a tree deposit. Removes tree when empty."""
        cell = self.get_cell(x, y)
        if cell is None or cell.feature != FeatureType.TREE or cell.deposit <= 0:
            return 0
        taken = min(amount, cell.deposit)
        cell.deposit -= taken
        if cell.deposit <= 0:
            cell.feature = FeatureType.NONE
            cell.deposit = 0
            cell.growth_ticks = 0
        return taken

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

    def add_fish_deposit(self, x: int, y: int, amount: int) -> None:
        """Leave caught fish on a walkable shore cell near water."""
        cell = self.get_cell(x, y)
        if cell is None:
            return
        if cell.terrain == TerrainType.WATER:
            # Prefer depositing on an adjacent shore tile.
            for ny, nx in self.neighbourhood(x, y, radius=1):
                if self.is_walkable(nx, ny):
                    self.cells[ny][nx].fish_deposit += amount
                    return
        cell.fish_deposit += amount

    def tree_cells(self) -> list[tuple[int, int]]:
        return [
            (x, y)
            for y in range(self.rows)
            for x in range(self.cols)
            if self.cells[y][x].feature == FeatureType.TREE
        ]

    def water_cells(self) -> list[tuple[int, int]]:
        return [
            (x, y)
            for y in range(self.rows)
            for x in range(self.cols)
            if self.cells[y][x].terrain == TerrainType.WATER
        ]

    def tree_patches(self) -> list[list[tuple[int, int]]]:
        """Connected components of tree cells (8-connected / Chebyshev)."""
        return self._connected_patches(set(self.tree_cells()))

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
        cell = self.get_cell(x, y)
        if cell is None:
            return
        cell.disturbance = min(DISTURBANCE_MAX, cell.disturbance + DISTURBANCE_INTERACTION_BOOST)
        for ny, nx in self.neighbourhood(x, y, radius=1):
            if (nx, ny) == (x, y):
                continue
            ncell = self.cells[ny][nx]
            ncell.disturbance = min(
                DISTURBANCE_MAX,
                ncell.disturbance + DISTURBANCE_NEIGHBOUR_SPREAD,
            )
