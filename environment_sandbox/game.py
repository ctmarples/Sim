"""Main game loop: input, buildings, villagers, update, and render.

Player presses E on their cell. Click selects villagers/buildings.
With a building selected, drag draws task areas; T cycles task mode.
Esc clears selection (then quits if nothing selected).

Future extension points:
- more building types / upgrades
- action costs and farm income
- seasonal tick systems
- save / load game state
"""

from __future__ import annotations

import random

import pygame

from entities import (
    BUILDING_LABELS,
    TASK_LABELS,
    Building,
    BuildingKind,
    HomeStorage,
    Inventory,
    Player,
    TaskArea,
    TaskType,
    Villager,
    VillagerState,
)
from indicators import (
    OVERLAY_LABELS,
    OverlayMode,
    build_overlay_grid,
    overlay_colour,
)
from settings import (
    ANIMAL_MEAT_YIELD,
    BUILDING_STORAGE_CAPACITY,
    CELL_SIZE,
    COLOUR_ANIMAL,
    COLOUR_BG,
    COLOUR_MEAT,
    COLOUR_PLAYER,
    COLOUR_SELECTED_ENTITY,
    COLOUR_TASK_AREA,
    COLOUR_TASK_CHOP,
    COLOUR_TASK_HUNT,
    COLOUR_TASK_FORAGE,
    COLOUR_TASK_MANAGE,
    COLOUR_TASK_PLANT,
    COLOUR_TASK_PREVIEW,
    COLOUR_TASK_ROCK,
    COLOUR_VILLAGER,
    DISTURBANCE_DECAY_PER_TICK,
    FORESTER_COST_ROCK,
    FORESTER_COST_WOOD,
    FORAGER_COST_ROCK,
    FORAGER_COST_WOOD,
    FPS,
    GRID_COLS,
    GRID_ROWS,
    HUNTER_COST_ROCK,
    HUNTER_COST_WOOD,
    BERRY_SEED_DROP_CHANCE,
    HERB_SEED_DROP_CHANCE,
    MASON_COST_ROCK,
    MASON_COST_WOOD,
    MAX_VILLAGERS,
    OVERLAY_ALPHA,
    SAPLING_DROP_CHANCE,
    STATUS_MESSAGE_FRAMES,
    VILLAGER_MOVE_INTERVAL,
    VILLAGER_WORK_INTERVAL,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)
from ui import UI, draw_feature, terrain_colour
from wildlife import WildlifeManager
from world import FeatureType, TerrainType, World


TASK_COLOURS = {
    TaskType.CHOP_TREES: COLOUR_TASK_CHOP,
    TaskType.COLLECT_ROCKS: COLOUR_TASK_ROCK,
    TaskType.PLANT_SAPLINGS: COLOUR_TASK_PLANT,
    TaskType.FULL_MANAGE: COLOUR_TASK_MANAGE,
    TaskType.HUNT: COLOUR_TASK_HUNT,
    TaskType.FORAGE_MUSHROOMS: COLOUR_TASK_FORAGE,
    TaskType.FORAGE_BERRIES: COLOUR_TASK_FORAGE,
    TaskType.FORAGE_HERBS: COLOUR_TASK_FORAGE,
    TaskType.PLANT_BERRY_SEEDS: COLOUR_TASK_PLANT,
    TaskType.PLANT_HERB_SEEDS: COLOUR_TASK_PLANT,
    TaskType.FULL_FORAGE: COLOUR_TASK_FORAGE,
}

FEATURE_FOR_BUILDING = {
    BuildingKind.FORESTER: FeatureType.FORESTER,
    BuildingKind.MASON: FeatureType.MASON,
    BuildingKind.HUNTER: FeatureType.HUNTER,
    BuildingKind.FORAGER: FeatureType.FORAGER,
}


class Game:
    def __init__(self) -> None:
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Environmental Farming Sandbox")
        self.clock = pygame.time.Clock()
        self.ui = UI()

        self.world = World()
        self.player = Player(x=self.world.start_pos[0], y=self.world.start_pos[1])
        self.home_storage = HomeStorage()
        self.villagers: list[Villager] = []
        self.buildings: dict[int, Building] = {}
        self.wildlife = WildlifeManager()
        self.next_villager_id = 1
        self.next_building_id = 1

        # Selection / drawing
        self.selected_building_id: int | None = None
        self.selected_villager_id: int | None = None
        self.place_kind: BuildingKind | None = None  # B cycles build ghost
        self.drawing = False
        self.draw_start: tuple[int, int] | None = None
        self.draw_current: tuple[int, int] | None = None
        self._mouse_down_cell: tuple[int, int] | None = None

        self.overlay_mode = OverlayMode.NONE
        self.overlay_values: list[list[float]] = build_overlay_grid(self.world, self.overlay_mode)

        self.status_message = (
            "Hire at station. B cycles build. Click building to set areas; "
            "click villager then building/home to assign."
        )
        self.status_timer = STATUS_MESSAGE_FRAMES
        self.running = True
        self._drop_rng = random.Random(42)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def run(self) -> None:
        while self.running:
            self._handle_events()
            self._update()
            self._draw()
            self.clock.tick(FPS)
        pygame.quit()

    def reset(self) -> None:
        self.world.reset()
        self.player.reset(self.world.start_pos[0], self.world.start_pos[1])
        self.home_storage.reset()
        self.villagers.clear()
        self.buildings.clear()
        self.wildlife.reset()
        self.next_villager_id = 1
        self.next_building_id = 1
        self._clear_selection()
        self.place_kind = None
        self.drawing = False
        self.draw_start = None
        self.draw_current = None
        self._mouse_down_cell = None
        self.overlay_mode = OverlayMode.NONE
        self._refresh_indicators()
        self._set_status("World reset.")

    def _clear_selection(self) -> None:
        self.selected_building_id = None
        self.selected_villager_id = None
        self.drawing = False
        self.draw_start = None
        self.draw_current = None

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------
    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self._on_keydown(event.key)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._on_mouse_down(event.pos)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self._on_mouse_up(event.pos)
            elif event.type == pygame.MOUSEMOTION and self.drawing:
                self._on_mouse_drag(event.pos)
            elif event.type == pygame.MOUSEWHEEL:
                mx, my = pygame.mouse.get_pos()
                if mx >= GRID_COLS * CELL_SIZE:
                    self.ui.scroll(event.y * 28)

    def _on_keydown(self, key: int) -> None:
        if key == pygame.K_ESCAPE:
            if (
                self.selected_building_id is not None
                or self.selected_villager_id is not None
                or self.place_kind is not None
            ):
                self._clear_selection()
                self.place_kind = None
                self._set_status("Selection cleared.")
            else:
                self.running = False
        elif key == pygame.K_r:
            self.reset()
        elif key == pygame.K_e:
            self._interact_at_player()
        elif key == pygame.K_b:
            self._cycle_place_kind()
        elif key == pygame.K_t:
            self._cycle_selected_building_task()
        elif key == pygame.K_c:
            self._clear_selected_building_areas()
        elif key == pygame.K_1:
            self._set_overlay(OverlayMode.NONE)
        elif key == pygame.K_2:
            self._set_overlay(OverlayMode.HABITAT_DIVERSITY)
        elif key == pygame.K_3:
            self._set_overlay(OverlayMode.TREE_DENSITY)
        elif key == pygame.K_4:
            self._set_overlay(OverlayMode.DISTURBANCE)
        elif key in (pygame.K_w, pygame.K_UP):
            self._try_move(0, -1)
        elif key in (pygame.K_s, pygame.K_DOWN):
            self._try_move(0, 1)
        elif key in (pygame.K_a, pygame.K_LEFT):
            self._try_move(-1, 0)
        elif key in (pygame.K_d, pygame.K_RIGHT):
            self._try_move(1, 0)

    def _map_cell_from_pos(self, pos: tuple[int, int]) -> tuple[int, int] | None:
        mx, my = pos
        map_width = GRID_COLS * CELL_SIZE
        if mx < 0 or my < 0 or mx >= map_width or my >= GRID_ROWS * CELL_SIZE:
            return None
        gx = mx // CELL_SIZE
        gy = my // CELL_SIZE
        if not self.world.in_bounds(gx, gy):
            return None
        return gx, gy

    def _on_mouse_down(self, pos: tuple[int, int]) -> None:
        cell = self._map_cell_from_pos(pos)
        if cell is None:
            return
        self._mouse_down_cell = cell
        # Only start area drawing when a workplace building is selected.
        if self.selected_building_id is not None and self.selected_building_id in self.buildings:
            self.drawing = True
            self.draw_start = cell
            self.draw_current = cell

    def _on_mouse_drag(self, pos: tuple[int, int]) -> None:
        cell = self._map_cell_from_pos(pos)
        if cell is not None:
            self.draw_current = cell

    def _on_mouse_up(self, pos: tuple[int, int]) -> None:
        end = self._map_cell_from_pos(pos) or self.draw_current or self._mouse_down_cell
        start = self.draw_start or self._mouse_down_cell
        was_drawing = self.drawing
        self.drawing = False
        self.draw_start = None
        self.draw_current = None
        down = self._mouse_down_cell
        self._mouse_down_cell = None

        if end is None or start is None or down is None:
            return

        # Click (same cell): selection / assignment.
        if end == down:
            self._handle_click(end)
            return

        # Drag: create task area for selected building.
        if was_drawing and self.selected_building_id is not None:
            building = self.buildings.get(self.selected_building_id)
            if building is None:
                return
            area = TaskArea(
                x0=start[0],
                y0=start[1],
                x1=end[0],
                y1=end[1],
                task_type=building.draw_task_type,
                building_id=building.id,
            )
            building.areas.append(area)
            self._set_status(
                f"{BUILDING_LABELS[building.kind]}: added {TASK_LABELS[area.task_type]}"
            )
            self._wake_building_workers(building.id)

    def _handle_click(self, cell: tuple[int, int]) -> None:
        x, y = cell

        # If a villager is selected, clicking a workplace/home assigns them.
        if self.selected_villager_id is not None:
            if self._try_assign_selected_villager(x, y):
                return

        villager = self._villager_at(x, y)
        if villager is not None:
            self.selected_villager_id = villager.id
            self.selected_building_id = None
            label = self._villager_assignment_label(villager)
            self._set_status(f"Selected villager {villager.id} ({label}). Click building/home.")
            return

        building = self._building_at(x, y)
        if building is not None:
            self.selected_building_id = building.id
            self.selected_villager_id = None
            if building.draw_task_type not in TASK_LABELS:
                building.draw_task_type = building.default_draw_task()
            self._set_status(
                f"Selected {BUILDING_LABELS[building.kind]}. "
                f"T: {TASK_LABELS[building.draw_task_type]}. Drag to draw. Esc to hide."
            )
            return

        if (x, y) == self.world.home_pos:
            self.selected_building_id = None
            self._set_status("Home. Select a villager first to assign as hauler.")
            return

        # Single-cell task area when a building is already selected.
        if self.selected_building_id is not None:
            selected = self.buildings.get(self.selected_building_id)
            if selected is not None:
                area = TaskArea(
                    x0=x,
                    y0=y,
                    x1=x,
                    y1=y,
                    task_type=selected.draw_task_type,
                    building_id=selected.id,
                )
                selected.areas.append(area)
                self._set_status(
                    f"{BUILDING_LABELS[selected.kind]}: added {TASK_LABELS[area.task_type]}"
                )
                self._wake_building_workers(selected.id)
                return

        self._set_status("Click a villager or building to select.")

    def _try_assign_selected_villager(self, x: int, y: int) -> bool:
        assert self.selected_villager_id is not None
        if (x, y) == self.world.home_pos:
            self._assign_villager_to_home(self.selected_villager_id)
            return True
        building = self._building_at(x, y)
        if building is not None:
            self._assign_villager_to_building(self.selected_villager_id, building.id)
            return True
        return False

    def _assign_villager_to_building(self, villager_id: int, building_id: int) -> None:
        villager = self._get_villager(villager_id)
        building = self.buildings.get(building_id)
        if villager is None or building is None:
            return
        villager.clear_assignment()
        villager.building_id = building_id
        villager.state = VillagerState.IDLE
        self.selected_villager_id = None
        self.selected_building_id = building_id
        self._set_status(
            f"Villager {villager.id} → {BUILDING_LABELS[building.kind]}"
        )
        self._wake_building_workers(building_id)

    def _assign_villager_to_home(self, villager_id: int) -> None:
        villager = self._get_villager(villager_id)
        if villager is None:
            return
        villager.clear_assignment()
        villager.assigned_to_home = True
        villager.state = VillagerState.IDLE
        self.selected_villager_id = None
        self._set_status(f"Villager {villager.id} → Home (hauler)")

    def _cycle_place_kind(self) -> None:
        order: list[BuildingKind | None] = [
            BuildingKind.FORESTER,
            BuildingKind.MASON,
            BuildingKind.HUNTER,
            BuildingKind.FORAGER,
            None,
        ]
        if self.place_kind not in order:
            self.place_kind = BuildingKind.FORESTER
        else:
            idx = order.index(self.place_kind)
            self.place_kind = order[(idx + 1) % len(order)]
        costs = {
            BuildingKind.FORESTER: (FORESTER_COST_WOOD, FORESTER_COST_ROCK, "Forester"),
            BuildingKind.MASON: (MASON_COST_WOOD, MASON_COST_ROCK, "Mason"),
            BuildingKind.HUNTER: (HUNTER_COST_WOOD, HUNTER_COST_ROCK, "Hunter"),
            BuildingKind.FORAGER: (FORAGER_COST_WOOD, FORAGER_COST_ROCK, "Forager"),
        }
        if self.place_kind is None:
            self._set_status("Build mode off.")
        else:
            w, r, name = costs[self.place_kind]
            self._set_status(
                f"Build: {name} ({w}w {r}r). Stand on empty soil/grass and press E."
            )

    def _cycle_selected_building_task(self) -> None:
        if self.selected_building_id is None:
            self._set_status("Select a building first (click it).")
            return
        building = self.buildings.get(self.selected_building_id)
        if building is None:
            return
        mode = building.cycle_draw_task()
        self._set_status(f"{BUILDING_LABELS[building.kind]} draw mode: {TASK_LABELS[mode]}")

    def _clear_selected_building_areas(self) -> None:
        if self.selected_building_id is None:
            self._set_status("Select a building to clear its areas.")
            return
        building = self.buildings.get(self.selected_building_id)
        if building is None:
            return
        building.areas.clear()
        self._set_status(f"Cleared areas for {BUILDING_LABELS[building.kind]}.")

    def _try_move(self, dx: int, dy: int) -> None:
        nx = self.player.x + dx
        ny = self.player.y + dy
        if self.world.is_walkable(nx, ny):
            self.player.move_to(nx, ny)

    def _set_overlay(self, mode: OverlayMode) -> None:
        self.overlay_mode = mode
        self._refresh_indicators()
        self._set_status(f"Overlay: {OVERLAY_LABELS[mode]}")

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------
    def _villager_at(self, x: int, y: int) -> Villager | None:
        for villager in self.villagers:
            if villager.x == x and villager.y == y:
                return villager
        return None

    def _building_at(self, x: int, y: int) -> Building | None:
        for building in self.buildings.values():
            if building.x == x and building.y == y:
                return building
        return None

    def _get_villager(self, villager_id: int) -> Villager | None:
        for villager in self.villagers:
            if villager.id == villager_id:
                return villager
        return None

    def _villager_assignment_label(self, villager: Villager) -> str:
        if villager.assigned_to_home:
            return "home hauler"
        if villager.building_id is not None:
            building = self.buildings.get(villager.building_id)
            if building is not None:
                return BUILDING_LABELS[building.kind]
        return "unassigned"

    def _wake_building_workers(self, building_id: int) -> None:
        for villager in self.villagers:
            if villager.building_id == building_id and villager.state == VillagerState.IDLE:
                villager.state = VillagerState.WORKING

    # ------------------------------------------------------------------
    # Player interaction
    # ------------------------------------------------------------------
    def _interact_at_player(self) -> None:
        x, y = self.player.x, self.player.y
        cell = self.world.get_cell(x, y)
        if cell is None:
            self._set_status("Invalid cell.")
            return

        if cell.feature == FeatureType.WORKSTATION:
            self._hire_villager()
            return

        if cell.feature == FeatureType.HOME:
            self._deposit_home(self.player.inventory)
            return

        if cell.feature in (
            FeatureType.FORESTER,
            FeatureType.MASON,
            FeatureType.HUNTER,
            FeatureType.FORAGER,
        ):
            building = self._building_at(x, y)
            if building is not None:
                self.selected_building_id = building.id
                self.selected_villager_id = None
                self._set_status(
                    f"{BUILDING_LABELS[building.kind]} "
                    f"store {building.stored_total}/{building.capacity}. "
                    f"T: {TASK_LABELS[building.draw_task_type]}"
                )
            return

        # Collect meat on this cell first if present.
        if cell.meat_deposit > 0:
            self._collect_meat(x, y, self.player.inventory, status=True)
            return

        # Hunt adjacent animal (within 1 square, including this cell).
        prey = self._adjacent_animal(x, y)
        if prey is not None:
            self._player_hunt(prey)
            return

        if cell.feature == FeatureType.MUSHROOM:
            self._collect_mushroom(x, y, self.player.inventory, status=True)
            return

        if cell.feature == FeatureType.BERRY_BUSH:
            self._collect_berries(x, y, self.player.inventory, status=True)
            return

        if cell.feature == FeatureType.HERB:
            self._collect_herb(x, y, self.player.inventory, status=True)
            return

        if cell.feature == FeatureType.TREE:
            self._chop_tree(x, y, self.player.inventory, status=True)
            return

        if cell.feature == FeatureType.ROCK:
            self._collect_rock(x, y, self.player.inventory, status=True)
            return

        if cell.feature == FeatureType.NONE and cell.terrain in (
            TerrainType.SOIL,
            TerrainType.GRASS,
        ):
            if self.place_kind is not None:
                self._try_build(self.place_kind, x, y)
            else:
                self._plant_here(x, y, self.player.inventory, status=True)
            return

        if cell.feature == FeatureType.SAPLING:
            self._set_status("Sapling is already growing.")
            return

        if cell.terrain == TerrainType.WATER:
            self._set_status("Cannot interact with water.")
            return

        self._set_status("Nothing to do here.")

    def _resource_pool_wood(self) -> int:
        return self.home_storage.wood + self.player.inventory.wood

    def _resource_pool_rock(self) -> int:
        return self.home_storage.rock + self.player.inventory.rock

    def _spend_resources(self, wood: int, rock: int) -> bool:
        """Spend from home storage first, then player inventory."""
        if self._resource_pool_wood() < wood or self._resource_pool_rock() < rock:
            return False

        need_w, need_r = wood, rock
        take_w = min(self.home_storage.wood, need_w)
        self.home_storage.wood -= take_w
        need_w -= take_w
        take_r = min(self.home_storage.rock, need_r)
        self.home_storage.rock -= take_r
        need_r -= take_r
        self.player.inventory.wood -= need_w
        self.player.inventory.rock -= need_r
        return True

    def _try_build(self, kind: BuildingKind, x: int, y: int) -> None:
        cell = self.world.get_cell(x, y)
        if cell is None or cell.feature != FeatureType.NONE:
            self._set_status("Cannot build here.")
            return
        if cell.terrain not in (TerrainType.SOIL, TerrainType.GRASS):
            self._set_status("Build on soil or grass.")
            return

        if kind == BuildingKind.FORESTER:
            cost_w, cost_r = FORESTER_COST_WOOD, FORESTER_COST_ROCK
            default_task = TaskType.CHOP_TREES
        elif kind == BuildingKind.MASON:
            cost_w, cost_r = MASON_COST_WOOD, MASON_COST_ROCK
            default_task = TaskType.COLLECT_ROCKS
        elif kind == BuildingKind.HUNTER:
            cost_w, cost_r = HUNTER_COST_WOOD, HUNTER_COST_ROCK
            default_task = TaskType.HUNT
        else:
            cost_w, cost_r = FORAGER_COST_WOOD, FORAGER_COST_ROCK
            default_task = TaskType.FULL_FORAGE

        if not self._spend_resources(cost_w, cost_r):
            self._set_status(f"Need {cost_w} wood and {cost_r} rock to build.")
            return

        building = Building(
            id=self.next_building_id,
            kind=kind,
            x=x,
            y=y,
            capacity=BUILDING_STORAGE_CAPACITY,
            draw_task_type=default_task,
        )
        self.next_building_id += 1
        self.buildings[building.id] = building
        cell.feature = FEATURE_FOR_BUILDING[kind]
        self.world.apply_disturbance(x, y)
        self._refresh_indicators()
        self.selected_building_id = building.id
        self.place_kind = None
        self._set_status(
            f"Built {BUILDING_LABELS[kind]}. Drag areas; T cycles tasks; Esc hides."
        )

    def _hire_villager(self) -> None:
        if len(self.villagers) >= MAX_VILLAGERS:
            self._set_status(f"Work station full ({MAX_VILLAGERS} villagers).")
            return
        wx, wy = self.world.workstation_pos
        spawn = self.world.workstation_pos
        for ny, nx in self.world.neighbourhood(wx, wy, radius=1):
            if (nx, ny) == (wx, wy):
                continue
            if self.world.is_walkable(nx, ny):
                spawn = (nx, ny)
                break
        villager = Villager(id=self.next_villager_id, x=spawn[0], y=spawn[1])
        self.next_villager_id += 1
        self.villagers.append(villager)
        self._set_status(
            f"Hired villager {villager.id}. Click them, then a building or home."
        )

    def _chop_tree(self, x: int, y: int, inventory: Inventory, status: bool = False) -> bool:
        if inventory.is_full:
            if status:
                self._set_status("Inventory is full.")
            return False
        cell = self.world.get_cell(x, y)
        if cell is None or cell.feature != FeatureType.TREE:
            if status:
                self._set_status("No tree here.")
            return False
        taken = self.world.harvest_wood(x, y, amount=1)
        if taken <= 0:
            if status:
                self._set_status("No wood left.")
            return False
        inventory.add_wood(taken)
        sapling_msg = ""
        if self._drop_rng.random() < SAPLING_DROP_CHANCE and inventory.can_add(1):
            inventory.add_saplings(1)
            sapling_msg = " +1 sapling"
        self.world.apply_disturbance(x, y)
        self._refresh_indicators()
        if status:
            left = self.world.get_cell(x, y)
            remaining = left.deposit if left and left.feature == FeatureType.TREE else 0
            self._set_status(f"Collected {taken} wood ({remaining} left){sapling_msg}.")
        return True

    def _collect_rock(self, x: int, y: int, inventory: Inventory, status: bool = False) -> bool:
        if inventory.is_full:
            if status:
                self._set_status("Inventory is full.")
            return False
        cell = self.world.get_cell(x, y)
        if cell is None or cell.feature != FeatureType.ROCK:
            if status:
                self._set_status("No rock here.")
            return False
        taken = self.world.harvest_rock(x, y, amount=1)
        if taken <= 0:
            if status:
                self._set_status("No rock left.")
            return False
        inventory.add_rock(taken)
        self.world.apply_disturbance(x, y)
        self._refresh_indicators()
        if status:
            left = self.world.get_cell(x, y)
            remaining = left.deposit if left and left.feature == FeatureType.ROCK else 0
            self._set_status(f"Collected {taken} rock ({remaining} left in deposit).")
        return True

    def _plant(self, x: int, y: int, inventory: Inventory, status: bool = False) -> bool:
        if inventory.saplings <= 0:
            if status:
                self._set_status("Need a sapling item to plant.")
            return False
        if not self.world.plant_sapling(x, y):
            if status:
                self._set_status("Cannot plant here.")
            return False
        inventory.consume_sapling()
        self.world.apply_disturbance(x, y)
        self._refresh_indicators()
        if status:
            self._set_status(f"Planted a sapling ({inventory.saplings} left).")
        return True

    def _plant_here(self, x: int, y: int, inventory: Inventory, status: bool = False) -> bool:
        """Plant berry seed, herb seed, or sapling depending on inventory and terrain."""
        cell = self.world.get_cell(x, y)
        if cell is None:
            return False
        if cell.terrain == TerrainType.GRASS and inventory.berry_seeds > 0:
            return self._plant_berry_seed(x, y, inventory, status=status)
        if cell.terrain == TerrainType.GRASS and inventory.herb_seeds > 0:
            return self._plant_herb_seed(x, y, inventory, status=status)
        return self._plant(x, y, inventory, status=status)

    def _plant_berry_seed(self, x: int, y: int, inventory: Inventory, status: bool = False) -> bool:
        if inventory.berry_seeds <= 0:
            if status:
                self._set_status("Need berry seeds.")
            return False
        if not self.world.plant_berry_bush(x, y):
            if status:
                self._set_status("Berry bushes need empty grass.")
            return False
        inventory.consume_berry_seed()
        self.world.apply_disturbance(x, y)
        self._refresh_indicators()
        if status:
            self._set_status("Planted a berry bush.")
        return True

    def _plant_herb_seed(self, x: int, y: int, inventory: Inventory, status: bool = False) -> bool:
        if inventory.herb_seeds <= 0:
            if status:
                self._set_status("Need herb seeds.")
            return False
        if not self.world.plant_herb(x, y):
            if status:
                self._set_status("Herbs need empty grass.")
            return False
        inventory.consume_herb_seed()
        self.world.apply_disturbance(x, y)
        self._refresh_indicators()
        if status:
            self._set_status("Planted herbs.")
        return True

    def _collect_mushroom(self, x: int, y: int, inventory: Inventory, status: bool = False) -> bool:
        if inventory.is_full:
            if status:
                self._set_status("Inventory is full.")
            return False
        if not self.world.harvest_mushroom(x, y):
            if status:
                self._set_status("No mushroom here.")
            return False
        inventory.add_mushrooms(1)
        self.world.apply_disturbance(x, y)
        self._refresh_indicators()
        if status:
            self._set_status("Collected 1 mushroom.")
        return True

    def _collect_berries(self, x: int, y: int, inventory: Inventory, status: bool = False) -> bool:
        if inventory.is_full:
            if status:
                self._set_status("Inventory is full.")
            return False
        taken = self.world.harvest_berries(x, y, amount=1)
        if taken <= 0:
            if status:
                self._set_status("No berries ready.")
            return False
        inventory.add_berries(taken)
        seed_msg = ""
        if self._drop_rng.random() < BERRY_SEED_DROP_CHANCE and inventory.can_add(1):
            inventory.add_berry_seeds(1)
            seed_msg = " +1 berry seed"
        self.world.apply_disturbance(x, y)
        self._refresh_indicators()
        if status:
            left = self.world.get_cell(x, y)
            rem = left.deposit if left and left.feature == FeatureType.BERRY_BUSH else 0
            self._set_status(f"Collected {taken} berry ({rem} left){seed_msg}.")
        return True

    def _collect_herb(self, x: int, y: int, inventory: Inventory, status: bool = False) -> bool:
        if inventory.is_full:
            if status:
                self._set_status("Inventory is full.")
            return False
        if not self.world.harvest_herb(x, y):
            if status:
                self._set_status("No herbs here.")
            return False
        inventory.add_herbs(1)
        seed_msg = ""
        if self._drop_rng.random() < HERB_SEED_DROP_CHANCE and inventory.can_add(1):
            inventory.add_herb_seeds(1)
            seed_msg = " +1 herb seed"
        self.world.apply_disturbance(x, y)
        self._refresh_indicators()
        if status:
            self._set_status(f"Collected 1 herb{seed_msg}.")
        return True

    def _deposit_home(self, inventory: Inventory, status: bool = True) -> bool:
        items = inventory.clear()
        if sum(items.values()) == 0:
            if status:
                self._set_status("Nothing to deposit.")
            return False
        self.home_storage.deposit_dict(items)
        hx, hy = self.world.home_pos
        self.world.apply_disturbance(hx, hy)
        self._refresh_indicators()
        if status:
            self._set_status(
                f"Deposited {items['wood']}w {items['rock']}r {items['meat']}m "
                f"{items['saplings']}s {items['mushrooms']}mush "
                f"{items['berries']}b {items['herbs']}h."
            )
        return True

    def _collect_meat(self, x: int, y: int, inventory: Inventory, status: bool = False) -> bool:
        if inventory.is_full:
            if status:
                self._set_status("Inventory is full.")
            return False
        taken = self.world.harvest_meat(x, y, amount=1)
        if taken <= 0:
            if status:
                self._set_status("No meat here.")
            return False
        inventory.add_meat(taken)
        if status:
            left = self.world.get_cell(x, y)
            remaining = left.meat_deposit if left else 0
            self._set_status(f"Collected {taken} meat ({remaining} left).")
        return True

    def _adjacent_animal(self, x: int, y: int):
        """Animal on this cell or within Chebyshev distance 1."""
        best = None
        best_dist = 99
        for animal in self.wildlife.animals:
            dist = max(abs(animal.x - x), abs(animal.y - y))
            if dist <= 1 and dist < best_dist:
                best = animal
                best_dist = dist
        return best

    def _player_hunt(self, animal) -> None:
        pos = self.wildlife.kill_animal(animal.id)
        if pos is None:
            self._set_status("Animal got away.")
            return
        self.world.add_meat_deposit(pos[0], pos[1], ANIMAL_MEAT_YIELD)
        self.world.apply_disturbance(pos[0], pos[1])
        self._refresh_indicators()
        self._set_status(f"Hunted animal. {ANIMAL_MEAT_YIELD} meat on ({pos[0]}, {pos[1]}).")

    # ------------------------------------------------------------------
    # Villager AI
    # ------------------------------------------------------------------
    def _update_villagers(self) -> None:
        for villager in self.villagers:
            if villager.move_cooldown > 0:
                villager.move_cooldown -= 1
            if villager.work_cooldown > 0:
                villager.work_cooldown -= 1

            if villager.assigned_to_home:
                self._update_hauler(villager)
            elif villager.building_id is not None:
                self._update_workplace_worker(villager)
            else:
                villager.state = VillagerState.IDLE

    def _update_workplace_worker(self, villager: Villager) -> None:
        building = self.buildings.get(villager.building_id) if villager.building_id else None
        if building is None:
            villager.clear_assignment()
            return

        if building.kind == BuildingKind.HUNTER:
            self._update_hunter(villager, building)
            return

        # Full carry → deliver to building storage.
        if villager.inventory.is_full and villager.state != VillagerState.DELIVERING:
            if building.space_left > 0:
                villager.state = VillagerState.DELIVERING
                villager.target = (building.x, building.y)
            else:
                villager.state = VillagerState.IDLE
                return

        if villager.state == VillagerState.DELIVERING:
            if (villager.x, villager.y) == (building.x, building.y):
                building.deposit_from_inventory(villager.inventory)
                if villager.inventory.is_empty or building.space_left == 0:
                    villager.state = VillagerState.WORKING
                    villager.target = None
                return
            self._step_villager_toward(villager, (building.x, building.y))
            return

        if villager.state == VillagerState.IDLE:
            if not villager.inventory.is_empty and building.space_left > 0:
                villager.state = VillagerState.DELIVERING
                villager.target = (building.x, building.y)
                return
            if building.areas and self._find_work_in_building(villager, building) is not None:
                if building.space_left > 0 or villager.inventory.is_empty:
                    villager.state = VillagerState.WORKING
            return

        target = self._find_work_in_building(villager, building)
        if target is None:
            if not villager.inventory.is_empty and building.space_left > 0:
                villager.state = VillagerState.DELIVERING
                villager.target = (building.x, building.y)
            else:
                villager.state = VillagerState.IDLE
                villager.target = None
            return

        if villager.inventory.is_full:
            return

        if (villager.x, villager.y) == target:
            if villager.work_cooldown == 0:
                self._villager_perform(villager, building, target)
                villager.work_cooldown = VILLAGER_WORK_INTERVAL
        else:
            self._step_villager_toward(villager, target)

    def _update_hunter(self, villager: Villager, building: Building) -> None:
        """Hunt animals in hunt areas: approach within 1, kill, collect meat, deliver."""
        if villager.inventory.is_full and villager.state != VillagerState.DELIVERING:
            if building.space_left > 0:
                villager.state = VillagerState.DELIVERING
                villager.hunt_animal_id = None
            else:
                villager.state = VillagerState.IDLE
                return

        if villager.state == VillagerState.DELIVERING:
            if (villager.x, villager.y) == (building.x, building.y):
                building.deposit_from_inventory(villager.inventory)
                if villager.inventory.is_empty or building.space_left == 0:
                    villager.state = VillagerState.WORKING
                    villager.target = None
                return
            self._step_villager_toward(villager, (building.x, building.y))
            return

        if villager.state == VillagerState.IDLE:
            if not villager.inventory.is_empty and building.space_left > 0:
                villager.state = VillagerState.DELIVERING
                return
            if building.areas and (
                self._find_hunt_target(villager, building) is not None
                or self._find_meat_in_hunt_areas(building) is not None
            ):
                if building.space_left > 0:
                    villager.state = VillagerState.WORKING
            return

        # Collect meat if we already have a carcass tile, or any in our areas.
        meat_pos = villager.hunt_meat_pos
        if meat_pos is not None:
            cell = self.world.get_cell(*meat_pos)
            if cell is None or cell.meat_deposit <= 0:
                villager.hunt_meat_pos = None
                meat_pos = None
        if meat_pos is None:
            meat_pos = self._find_meat_in_hunt_areas(building)
            if meat_pos is not None:
                villager.hunt_meat_pos = meat_pos

        if meat_pos is not None and not villager.inventory.is_full:
            if (villager.x, villager.y) == meat_pos:
                if villager.work_cooldown == 0:
                    self._collect_meat(*meat_pos, villager.inventory, status=False)
                    villager.work_cooldown = VILLAGER_WORK_INTERVAL
                    cell = self.world.get_cell(*meat_pos)
                    if cell is None or cell.meat_deposit <= 0:
                        villager.hunt_meat_pos = None
            else:
                if self.world.is_walkable(*meat_pos):
                    self._step_villager_toward(villager, meat_pos)
                else:
                    # Stand adjacent and still collect only on same square — skip unreachable.
                    villager.hunt_meat_pos = None
            return

        if villager.inventory.is_full:
            return

        animal = self._resolve_hunt_animal(villager, building)
        if animal is None:
            if not villager.inventory.is_empty and building.space_left > 0:
                villager.state = VillagerState.DELIVERING
            else:
                villager.state = VillagerState.IDLE
            return

        dist = max(abs(animal.x - villager.x), abs(animal.y - villager.y))
        if dist <= 1:
            if villager.work_cooldown == 0:
                pos = self.wildlife.kill_animal(animal.id)
                villager.hunt_animal_id = None
                if pos is not None:
                    self.world.add_meat_deposit(pos[0], pos[1], ANIMAL_MEAT_YIELD)
                    self.world.apply_disturbance(pos[0], pos[1])
                    self._refresh_indicators()
                    villager.hunt_meat_pos = pos
                villager.work_cooldown = VILLAGER_WORK_INTERVAL
            return

        # Approach: step toward animal cell (or a walkable neighbour).
        approach = (animal.x, animal.y)
        if not self.world.is_walkable(*approach):
            for ny, nx in self.world.neighbourhood(animal.x, animal.y, radius=1):
                if self.world.is_walkable(nx, ny):
                    approach = (nx, ny)
                    break
        self._step_villager_toward(villager, approach)

    def _find_hunt_target(self, villager: Villager, building: Building):
        animals = []
        for area in building.areas:
            if area.task_type != TaskType.HUNT:
                continue
            animals.extend(self.wildlife.animals_in_area(area.contains))
        if not animals:
            return None
        return min(
            animals,
            key=lambda a: abs(a.x - villager.x) + abs(a.y - villager.y),
        )

    def _resolve_hunt_animal(self, villager: Villager, building: Building):
        if villager.hunt_animal_id is not None:
            for animal in self.wildlife.animals:
                if animal.id == villager.hunt_animal_id:
                    return animal
            villager.hunt_animal_id = None
        animal = self._find_hunt_target(villager, building)
        if animal is not None:
            villager.hunt_animal_id = animal.id
        return animal

    def _find_meat_in_hunt_areas(self, building: Building) -> tuple[int, int] | None:
        for area in building.areas:
            if area.task_type != TaskType.HUNT:
                continue
            for x, y in area.cells():
                cell = self.world.get_cell(x, y)
                if cell is not None and cell.meat_deposit > 0:
                    return (x, y)
        return None

    def _update_hauler(self, villager: Villager) -> None:
        home = self.world.home_pos

        # Carrying goods → go home.
        if not villager.inventory.is_empty and villager.state != VillagerState.DELIVERING:
            villager.state = VillagerState.DELIVERING
            villager.target = home

        if villager.state == VillagerState.DELIVERING:
            if (villager.x, villager.y) == home:
                self._deposit_home(villager.inventory, status=False)
                villager.haul_building_id = None
                villager.state = VillagerState.IDLE
                return
            self._step_villager_toward(villager, home)
            return

        # Need a workplace with stock.
        source = self._find_haul_source(villager)
        if source is None:
            villager.state = VillagerState.IDLE
            return

        villager.haul_building_id = source.id
        villager.state = VillagerState.HAULING
        if (villager.x, villager.y) == (source.x, source.y):
            if villager.work_cooldown == 0:
                source.withdraw_to_inventory(villager.inventory)
                villager.work_cooldown = VILLAGER_WORK_INTERVAL
                if not villager.inventory.is_empty:
                    villager.state = VillagerState.DELIVERING
                    villager.target = home
            return
        self._step_villager_toward(villager, (source.x, source.y))

    def _find_haul_source(self, villager: Villager) -> Building | None:
        stocked = [b for b in self.buildings.values() if b.stored_total > 0]
        if not stocked:
            return None
        return min(
            stocked,
            key=lambda b: abs(b.x - villager.x) + abs(b.y - villager.y),
        )

    def _find_work_in_building(
        self, villager: Villager, building: Building
    ) -> tuple[int, int] | None:
        can_plant_sapling = villager.inventory.saplings > 0 or (
            building.kind == BuildingKind.FORESTER and building.saplings > 0
        )
        can_plant_berry = villager.inventory.berry_seeds > 0 or (
            building.kind == BuildingKind.FORAGER and building.berry_seeds > 0
        )
        can_plant_herb = villager.inventory.herb_seeds > 0 or (
            building.kind == BuildingKind.FORAGER and building.herb_seeds > 0
        )
        candidates: list[tuple[int, int]] = []
        for area in building.areas:
            for x, y in area.cells():
                cell = self.world.get_cell(x, y)
                if cell is None or not self.world.is_walkable(x, y):
                    continue
                if self._cell_matches_task(
                    cell,
                    area.task_type,
                    can_plant_sapling=can_plant_sapling,
                    can_plant_berry=can_plant_berry,
                    can_plant_herb=can_plant_herb,
                ):
                    candidates.append((x, y))
        if not candidates:
            return None
        return min(candidates, key=lambda p: abs(p[0] - villager.x) + abs(p[1] - villager.y))

    def _cell_matches_task(
        self,
        cell,
        task_type: TaskType,
        can_plant_sapling: bool = True,
        can_plant_berry: bool = True,
        can_plant_herb: bool = True,
    ) -> bool:
        if task_type == TaskType.CHOP_TREES:
            return cell.feature == FeatureType.TREE
        if task_type == TaskType.COLLECT_ROCKS:
            return cell.feature == FeatureType.ROCK
        if task_type == TaskType.PLANT_SAPLINGS:
            return (
                can_plant_sapling
                and cell.feature == FeatureType.NONE
                and cell.terrain in (TerrainType.SOIL, TerrainType.GRASS)
            )
        if task_type == TaskType.FULL_MANAGE:
            if cell.feature == FeatureType.TREE:
                return True
            return (
                can_plant_sapling
                and cell.feature == FeatureType.NONE
                and cell.terrain in (TerrainType.SOIL, TerrainType.GRASS)
            )
        if task_type == TaskType.FORAGE_MUSHROOMS:
            return cell.feature == FeatureType.MUSHROOM
        if task_type == TaskType.FORAGE_BERRIES:
            return cell.feature == FeatureType.BERRY_BUSH and cell.deposit > 0
        if task_type == TaskType.FORAGE_HERBS:
            return cell.feature == FeatureType.HERB
        if task_type == TaskType.PLANT_BERRY_SEEDS:
            return (
                can_plant_berry
                and cell.feature == FeatureType.NONE
                and cell.terrain == TerrainType.GRASS
            )
        if task_type == TaskType.PLANT_HERB_SEEDS:
            return (
                can_plant_herb
                and cell.feature == FeatureType.NONE
                and cell.terrain == TerrainType.GRASS
            )
        if task_type == TaskType.FULL_FORAGE:
            if cell.feature == FeatureType.MUSHROOM:
                return True
            if cell.feature == FeatureType.BERRY_BUSH and cell.deposit > 0:
                return True
            if cell.feature == FeatureType.HERB:
                return True
            if (
                cell.feature == FeatureType.NONE
                and cell.terrain == TerrainType.GRASS
                and (can_plant_berry or can_plant_herb)
            ):
                return True
            return False
        return False

    def _villager_perform(
        self, villager: Villager, building: Building, pos: tuple[int, int]
    ) -> None:
        x, y = pos
        cell = self.world.get_cell(x, y)
        if cell is None:
            return
        tasks = {area.task_type for area in building.areas if area.contains(x, y)}
        inv = villager.inventory

        if cell.feature == FeatureType.TREE and (
            TaskType.CHOP_TREES in tasks or TaskType.FULL_MANAGE in tasks
        ):
            self._chop_tree(x, y, inv, status=False)
        elif cell.feature == FeatureType.ROCK and TaskType.COLLECT_ROCKS in tasks:
            self._collect_rock(x, y, inv, status=False)
        elif cell.feature == FeatureType.MUSHROOM and (
            TaskType.FORAGE_MUSHROOMS in tasks or TaskType.FULL_FORAGE in tasks
        ):
            self._collect_mushroom(x, y, inv, status=False)
        elif cell.feature == FeatureType.BERRY_BUSH and (
            TaskType.FORAGE_BERRIES in tasks or TaskType.FULL_FORAGE in tasks
        ):
            self._collect_berries(x, y, inv, status=False)
        elif cell.feature == FeatureType.HERB and (
            TaskType.FORAGE_HERBS in tasks or TaskType.FULL_FORAGE in tasks
        ):
            self._collect_herb(x, y, inv, status=False)
        elif cell.feature == FeatureType.NONE:
            if TaskType.PLANT_BERRY_SEEDS in tasks or (
                TaskType.FULL_FORAGE in tasks and cell.terrain == TerrainType.GRASS
            ):
                if inv.berry_seeds <= 0 and building.kind == BuildingKind.FORAGER:
                    building.give_item_to(inv, "berry_seeds")
                if inv.berry_seeds > 0 and cell.terrain == TerrainType.GRASS:
                    self._plant_berry_seed(x, y, inv, status=False)
                    return
            if TaskType.PLANT_HERB_SEEDS in tasks or TaskType.FULL_FORAGE in tasks:
                if inv.herb_seeds <= 0 and building.kind == BuildingKind.FORAGER:
                    building.give_item_to(inv, "herb_seeds")
                if inv.herb_seeds > 0 and cell.terrain == TerrainType.GRASS:
                    self._plant_herb_seed(x, y, inv, status=False)
                    return
            if TaskType.PLANT_SAPLINGS in tasks or TaskType.FULL_MANAGE in tasks:
                if inv.saplings <= 0 and building.kind == BuildingKind.FORESTER:
                    building.give_sapling_to(inv)
                self._plant(x, y, inv, status=False)

    def _step_villager_toward(self, villager: Villager, goal: tuple[int, int]) -> None:
        if villager.move_cooldown > 0:
            return
        step = self.world.next_step_toward((villager.x, villager.y), goal)
        if step is None:
            return
        villager.x, villager.y = step
        villager.move_cooldown = VILLAGER_MOVE_INTERVAL

    # ------------------------------------------------------------------
    # Update / indicators
    # ------------------------------------------------------------------
    def _set_status(self, message: str) -> None:
        self.status_message = message
        self.status_timer = STATUS_MESSAGE_FRAMES

    def _refresh_indicators(self) -> None:
        self.overlay_values = build_overlay_grid(self.world, self.overlay_mode)

    def _update(self) -> None:
        self.world.tick(decay_per_tick=DISTURBANCE_DECAY_PER_TICK)
        self._update_villagers()
        self.wildlife.tick(self.world)
        if self.overlay_mode != OverlayMode.NONE:
            self._refresh_indicators()
        if self.status_timer > 0:
            self.status_timer -= 1
            if self.status_timer == 0:
                self.status_message = ""

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def _draw(self) -> None:
        self.screen.fill(COLOUR_BG)
        self._draw_world()
        if self.overlay_mode != OverlayMode.NONE:
            self._draw_overlay()
        self._draw_task_areas()
        self._draw_animals()
        self._draw_villagers()
        self._draw_player()
        self._draw_selection_highlights()
        self.ui.draw_panel(
            self.screen,
            self.world,
            self.player,
            self.home_storage,
            self.villagers,
            self.buildings,
            self.wildlife,
            self.selected_building_id,
            self.selected_villager_id,
            self.place_kind,
            self.overlay_mode,
            self.status_message,
        )
        pygame.display.flip()

    def _draw_world(self) -> None:
        for y in range(self.world.rows):
            for x in range(self.world.cols):
                cell = self.world.cells[y][x]
                rect = pygame.Rect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE)
                pygame.draw.rect(self.screen, terrain_colour(cell.terrain), rect)
                pygame.draw.rect(self.screen, (0, 0, 0), rect, 1)
                cx = x * CELL_SIZE + CELL_SIZE // 2
                cy = y * CELL_SIZE + CELL_SIZE // 2
                draw_feature(self.screen, cell.feature, cx, cy, CELL_SIZE)
                if cell.meat_deposit > 0:
                    pygame.draw.circle(self.screen, COLOUR_MEAT, (cx + 8, cy + 8), 5)
                    pygame.draw.circle(self.screen, (80, 20, 20), (cx + 8, cy + 8), 5, 1)

    def _draw_overlay(self) -> None:
        overlay = pygame.Surface((GRID_COLS * CELL_SIZE, GRID_ROWS * CELL_SIZE), pygame.SRCALPHA)
        for y in range(self.world.rows):
            for x in range(self.world.cols):
                value = self.overlay_values[y][x]
                colour = overlay_colour(self.overlay_mode, value)
                rect = pygame.Rect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE)
                overlay.fill((*colour, OVERLAY_ALPHA), rect)
        self.screen.blit(overlay, (0, 0))

    def _draw_task_areas(self) -> None:
        # Areas only visible while their building is selected.
        if self.selected_building_id is None:
            building = None
        else:
            building = self.buildings.get(self.selected_building_id)

        tint = pygame.Surface((GRID_COLS * CELL_SIZE, GRID_ROWS * CELL_SIZE), pygame.SRCALPHA)
        if building is not None:
            for area in building.areas:
                colour = TASK_COLOURS.get(area.task_type, COLOUR_TASK_AREA)
                left, top, right, bottom = area.normalised()
                for y in range(top, bottom + 1):
                    for x in range(left, right + 1):
                        rect = pygame.Rect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE)
                        tint.fill((*colour, 55), rect)
                border = pygame.Rect(
                    left * CELL_SIZE,
                    top * CELL_SIZE,
                    (right - left + 1) * CELL_SIZE,
                    (bottom - top + 1) * CELL_SIZE,
                )
                pygame.draw.rect(self.screen, colour, border, 2)

        if self.drawing and self.draw_start and self.draw_current and building is not None:
            x0, y0 = self.draw_start
            x1, y1 = self.draw_current
            left, top = min(x0, x1), min(y0, y1)
            right, bottom = max(x0, x1), max(y0, y1)
            preview = TASK_COLOURS.get(building.draw_task_type, COLOUR_TASK_PREVIEW)
            for y in range(top, bottom + 1):
                for x in range(left, right + 1):
                    rect = pygame.Rect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE)
                    tint.fill((*preview, 70), rect)
            border = pygame.Rect(
                left * CELL_SIZE,
                top * CELL_SIZE,
                (right - left + 1) * CELL_SIZE,
                (bottom - top + 1) * CELL_SIZE,
            )
            pygame.draw.rect(self.screen, COLOUR_TASK_PREVIEW, border, 2)

        self.screen.blit(tint, (0, 0))

    def _draw_animals(self) -> None:
        for animal in self.wildlife.animals:
            cx = animal.x * CELL_SIZE + CELL_SIZE // 2
            cy = animal.y * CELL_SIZE + CELL_SIZE // 2 + 2
            pygame.draw.ellipse(
                self.screen,
                COLOUR_ANIMAL,
                pygame.Rect(
                    cx - CELL_SIZE // 5,
                    cy - CELL_SIZE // 8,
                    max(6, CELL_SIZE // 2),
                    max(4, CELL_SIZE // 4),
                ),
            )
            # Head
            pygame.draw.circle(self.screen, COLOUR_ANIMAL, (cx + CELL_SIZE // 6, cy - 2), max(2, CELL_SIZE // 10))

    def _draw_villagers(self) -> None:
        for villager in self.villagers:
            cx = villager.x * CELL_SIZE + CELL_SIZE // 2
            cy = villager.y * CELL_SIZE + CELL_SIZE // 2
            pygame.draw.circle(self.screen, COLOUR_VILLAGER, (cx, cy), CELL_SIZE // 4)
            pygame.draw.circle(self.screen, (40, 30, 10), (cx, cy), CELL_SIZE // 4, 2)

    def _draw_player(self) -> None:
        cx = self.player.x * CELL_SIZE + CELL_SIZE // 2
        cy = self.player.y * CELL_SIZE + CELL_SIZE // 2
        pygame.draw.circle(self.screen, COLOUR_PLAYER, (cx, cy), CELL_SIZE // 3)
        pygame.draw.circle(self.screen, (255, 255, 255), (cx, cy), CELL_SIZE // 3, 2)

    def _draw_selection_highlights(self) -> None:
        if self.selected_villager_id is not None:
            villager = self._get_villager(self.selected_villager_id)
            if villager is not None:
                rect = pygame.Rect(
                    villager.x * CELL_SIZE, villager.y * CELL_SIZE, CELL_SIZE, CELL_SIZE
                )
                pygame.draw.rect(self.screen, COLOUR_SELECTED_ENTITY, rect, 3)
        if self.selected_building_id is not None:
            building = self.buildings.get(self.selected_building_id)
            if building is not None:
                rect = pygame.Rect(
                    building.x * CELL_SIZE, building.y * CELL_SIZE, CELL_SIZE, CELL_SIZE
                )
                pygame.draw.rect(self.screen, COLOUR_SELECTED_ENTITY, rect, 3)
