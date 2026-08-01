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

from settings import (
    BERRY_BUSH_YIELD,
    BERRY_REGEN_TICKS,
    BERRY_SPREAD_CHANCE,
    BERRY_SPREAD_INTERVAL,
    DISTURBANCE_INTERACTION_BOOST,
    DISTURBANCE_MAX,
    DISTURBANCE_NEIGHBOUR_SPREAD,
    HERB_SPAWN_CHANCE,
    HERB_TICK_INTERVAL,
    MUSHROOM_SPAWN_CHANCE,
    MUSHROOM_SPREAD_CHANCE,
    MUSHROOM_TICK_INTERVAL,
    NATURAL_SPROUT_CHANCE,
    NATURAL_SPROUT_INTERVAL,
    NATURAL_SPROUT_MIN_PATCH,
    RANDOM_SEED,
    ROCK_DEPOSIT,
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
    MUSHROOM = auto()
    BERRY_BUSH = auto()
    HERB = auto()


@dataclass
class Cell:
    """Single grid cell. Indicators are derived elsewhere from live state."""

    terrain: TerrainType
    feature: FeatureType = FeatureType.NONE
    disturbance: float = 0.0
    growth_ticks: int = 0  # sapling maturity / berry regen countdown
    deposit: int = 0  # wood, rock, or berries remaining
    meat_deposit: int = 0

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
        self.generate()

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    def generate(self) -> None:
        rng = random.Random(self.seed)
        self.cells = [
            [Cell(terrain=TerrainType.SOIL) for _ in range(self.cols)]
            for _ in range(self.rows)
        ]

        # Base terrain: mostly soil and grass, with water patches.
        for y in range(self.rows):
            for x in range(self.cols):
                roll = rng.random()
                if roll < 0.55:
                    self.cells[y][x].terrain = TerrainType.GRASS
                elif roll < 0.88:
                    self.cells[y][x].terrain = TerrainType.SOIL
                elif roll < 0.95:
                    self.cells[y][x].terrain = TerrainType.ROCK
                else:
                    self.cells[y][x].terrain = TerrainType.WATER

        # Smooth water into small ponds.
        self._place_clusters(
            rng,
            count=3,
            radius=2,
            apply=lambda c: setattr(c, "terrain", TerrainType.WATER),
        )

        # Tree clusters on grass/soil (not water).
        for _ in range(6):
            cx = rng.randint(1, self.cols - 2)
            cy = rng.randint(1, self.rows - 2)
            for ny, nx in self.neighbourhood(cx, cy, radius=2):
                cell = self.cells[ny][nx]
                if cell.terrain in (TerrainType.GRASS, TerrainType.SOIL) and rng.random() < 0.55:
                    cell.feature = FeatureType.TREE
                    cell.deposit = TREE_WOOD_DEPOSIT

        # Scattered rock resources.
        placed_rocks = 0
        attempts = 0
        while placed_rocks < 12 and attempts < 200:
            attempts += 1
            x = rng.randint(0, self.cols - 1)
            y = rng.randint(0, self.rows - 1)
            cell = self.cells[y][x]
            if cell.feature == FeatureType.NONE and cell.terrain != TerrainType.WATER:
                cell.feature = FeatureType.ROCK
                cell.deposit = ROCK_DEPOSIT
                placed_rocks += 1

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
                    ):
                        cell.feature = FeatureType.NONE
                        cell.deposit = 0
                        cell.growth_ticks = 0
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

    def _place_clusters(
        self,
        rng: random.Random,
        count: int,
        radius: int,
        apply,
    ) -> None:
        for _ in range(count):
            cx = rng.randint(radius, self.cols - radius - 1)
            cy = rng.randint(radius, self.rows - radius - 1)
            for ny, nx in self.neighbourhood(cx, cy, radius=radius):
                if rng.random() < 0.65:
                    apply(self.cells[ny][nx])

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
        """Return the next cell on a shortest walkable path (BFS), or None if unreachable.

        Avoids greedy pathfinding getting stuck against water / map edges.
        """
        if start == goal:
            return goal
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
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    nx, ny = cx + dx, cy + dy
                    if (nx, ny) in came_from:
                        continue
                    if not self.is_walkable(nx, ny):
                        continue
                    came_from[(nx, ny)] = (cx, cy)
                    queue.append((nx, ny))

        if not found:
            return None

        # Walk backward from goal to the step after start.
        cur = (gx, gy)
        while came_from[cur] is not None and came_from[cur] != start:
            cur = came_from[cur]
        return cur

    # ------------------------------------------------------------------
    # Simulation ticks (growth, optional disturbance decay)
    # ------------------------------------------------------------------
    def tick(self, decay_per_tick: float = 0.0) -> None:
        """Advance growth, forage ecology, sprouting, and disturbance decay."""
        for y in range(self.rows):
            for x in range(self.cols):
                cell = self.cells[y][x]
                if cell.feature == FeatureType.SAPLING:
                    cell.growth_ticks -= 1
                    if cell.growth_ticks <= 0:
                        cell.feature = FeatureType.TREE
                        cell.growth_ticks = 0
                        cell.deposit = TREE_WOOD_DEPOSIT
                elif cell.feature == FeatureType.BERRY_BUSH and cell.growth_ticks > 0:
                    cell.growth_ticks -= 1
                    if cell.growth_ticks <= 0 and cell.deposit <= 0:
                        cell.deposit = BERRY_BUSH_YIELD
                if decay_per_tick > 0 and cell.disturbance > 0:
                    cell.disturbance = max(0.0, cell.disturbance - decay_per_tick)

        self._sprout_timer -= 1
        if self._sprout_timer <= 0:
            self._sprout_timer = NATURAL_SPROUT_INTERVAL
            self._try_natural_sprouts()

        self._mushroom_timer -= 1
        if self._mushroom_timer <= 0:
            self._mushroom_timer = MUSHROOM_TICK_INTERVAL
            self._tick_mushrooms()

        self._berry_spread_timer -= 1
        if self._berry_spread_timer <= 0:
            self._berry_spread_timer = BERRY_SPREAD_INTERVAL
            self._tick_berry_spread()

        self._herb_timer -= 1
        if self._herb_timer <= 0:
            self._herb_timer = HERB_TICK_INTERVAL
            self._tick_herbs()

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

    def _tick_mushrooms(self) -> None:
        """Spawn mushrooms on soil beside trees; spread into neighbouring soil."""
        # Spread existing mushrooms first (snapshot positions).
        existing = [
            (x, y)
            for y in range(self.rows)
            for x in range(self.cols)
            if self.cells[y][x].feature == FeatureType.MUSHROOM
        ]
        for mx, my in existing:
            for ny, nx in self.neighbourhood(mx, my, radius=1):
                if (nx, ny) == (mx, my):
                    continue
                cell = self.cells[ny][nx]
                if (
                    cell.feature == FeatureType.NONE
                    and cell.terrain == TerrainType.SOIL
                    and self._forage_rng.random() < MUSHROOM_SPREAD_CHANCE
                ):
                    cell.feature = FeatureType.MUSHROOM

        # Spawn near trees on soil.
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
                        and self._forage_rng.random() < MUSHROOM_SPAWN_CHANCE
                    ):
                        cell.feature = FeatureType.MUSHROOM

    def _tick_berry_spread(self) -> None:
        bushes = [
            (x, y)
            for y in range(self.rows)
            for x in range(self.cols)
            if self.cells[y][x].feature == FeatureType.BERRY_BUSH
        ]
        for bx, by in bushes:
            if self._forage_rng.random() > BERRY_SPREAD_CHANCE:
                continue
            neighbours = [
                (nx, ny)
                for ny, nx in self.neighbourhood(bx, by, radius=1)
                if (nx, ny) != (bx, by)
                and self.cells[ny][nx].feature == FeatureType.NONE
                and self.cells[ny][nx].terrain == TerrainType.GRASS
            ]
            if neighbours:
                nx, ny = self._forage_rng.choice(neighbours)
                self.plant_berry_bush(nx, ny)

    def _tick_herbs(self) -> None:
        for y in range(self.rows):
            for x in range(self.cols):
                cell = self.cells[y][x]
                if (
                    cell.feature == FeatureType.NONE
                    and cell.terrain == TerrainType.GRASS
                    and self._forage_rng.random() < HERB_SPAWN_CHANCE
                ):
                    cell.feature = FeatureType.HERB

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

    def plant_herb(self, x: int, y: int) -> bool:
        cell = self.get_cell(x, y)
        if cell is None or cell.feature != FeatureType.NONE:
            return False
        if cell.terrain != TerrainType.GRASS:
            return False
        cell.feature = FeatureType.HERB
        cell.deposit = 0
        cell.growth_ticks = 0
        return True

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

    def harvest_herb(self, x: int, y: int) -> bool:
        cell = self.get_cell(x, y)
        if cell is None or cell.feature != FeatureType.HERB:
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

    def tree_cells(self) -> list[tuple[int, int]]:
        return [
            (x, y)
            for y in range(self.rows)
            for x in range(self.cols)
            if self.cells[y][x].feature == FeatureType.TREE
        ]

    def tree_patches(self) -> list[list[tuple[int, int]]]:
        """Connected components of tree cells (8-connected / Chebyshev)."""
        trees = set(self.tree_cells())
        patches: list[list[tuple[int, int]]] = []
        seen: set[tuple[int, int]] = set()
        for start in trees:
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
                    if pos in trees and pos not in seen:
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
