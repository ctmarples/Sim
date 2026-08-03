"""Main game loop: input, buildings, villagers, update, and render.

Player presses Enter/E on their cell. Toolbar handles build, tasks, speed,
and File save/load. Click selects villagers/buildings; drag draws task areas.
Esc clears selection / menus (does not quit).
"""

from __future__ import annotations

import random

import pygame

from crops import (
    CROP_BY_KEY,
    FARM_SEED_AMOUNTS,
    SEED_KEYS,
    SeasonPhase,
    growth_ticks_for,
    phase_allows_plough_plant,
    phase_for_crop,
)
from entities import (
    BUILDING_LABELS,
    DEFAULT_PRIORITIES_UNASSIGNED,
    PRIORITY_LABELS,
    RATION_LABELS,
    TASK_LABELS,
    WORK_MODE_LABELS,
    Building,
    BuildingKind,
    ConstructionSite,
    CropPlan,
    HomeStorage,
    Inventory,
    Player,
    RationMode,
    TaskArea,
    TaskType,
    Villager,
    VillagerState,
    WorkMode,
    WorkPriority,
)
from indicators import (
    BIODIVERSITY_SAMPLES_PER_YEAR,
    OVERLAY_LABELS,
    OverlayMode,
    average_grids,
    biodiversity_snapshot,
    build_overlay_grid,
    overlay_colour,
)
from settings import (
    BOAR_MEAT_YIELD,
    DEER_MEAT_YIELD,
    BUILDING_STORAGE_CAPACITY,
    CELL_SIZE,
    COLOUR_BOAR,
    COLOUR_DEER,
    COLOUR_BG,
    COLOUR_FISH,
    COLOUR_MEAT,
    COLOUR_PLAYER,
    COLOUR_SELECTED_ENTITY,
    COLOUR_TASK_AREA,
    COLOUR_TASK_CHOP,
    COLOUR_TASK_FISH,
    COLOUR_TASK_FARM,
    COLOUR_TASK_HUNT,
    COLOUR_TASK_FORAGE,
    COLOUR_TASK_MANAGE,
    COLOUR_TASK_PLANT,
    COLOUR_TASK_PREVIEW,
    COLOUR_TASK_ROCK,
    COLOUR_VILLAGER,
    DISTURBANCE_DECAY_PER_TICK,
    FARM_COST_ROCK,
    FARM_COST_WOOD,
    FARM_FIELD_RADIUS,
    FIELD_COST_ROCK,
    FIELD_COST_WOOD,
    FISHER_COST_ROCK,
    FISHER_COST_WOOD,
    FISH_YIELD,
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
    MASON_COST_ROCK,
    MASON_COST_WOOD,
    MAX_VILLAGERS,
    MINIMAP_HEIGHT,
    MINIMAP_WIDTH,
    OVERLAY_ALPHA,
    SAPLING_DROP_CHANCE,
    SIM_SPEEDS,
    STARTING_FOOD,
    STARTING_ROCK,
    STARTING_WOOD,
    STATUS_MESSAGE_FRAMES,
    VILLAGER_FOOD_KEYS,
    VILLAGER_MOVE_INTERVAL,
    VILLAGER_SATIATION_DECAY_PER_TICK,
    VILLAGER_WORK_INTERVAL,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    WORLD_COLS,
    ZOOM_STEP,
    MAP_OFFSET_Y,
    map_view_height,
    map_view_width,
)
from camera import Camera
from dialogs import FileDialog
from building_inspect_dialog import BuildingInspectDialog
from field_plan_dialog import FieldPlanDialog
from resource_inspect_dialog import ResourceInspectDialog
from villager_inspect_dialog import VillagerInspectDialog
from resource_bar import VIEW_LABELS, ResourceBar
from save_load import load_from_path, save_to_path
from seasons import (
    DAYS_PER_SEASON,
    TICKS_PER_DAY,
    YEAR_DAYS,
    Season,
    blend_colour,
    day_in_season,
    fishing_allowed,
    format_date,
    freeze_amount,
    season_for_day,
    seed_chance_multiplier,
    terrain_vibrancy,
    water_frozen,
)
from toolbar import Toolbar
from ui import UI, draw_feature
from terrain_tiles import (
    CASE_NAMES,
    atlas_row_col,
    describe_system,
    paint_cell,
    verify_shared_edges,
)
from wildlife import AnimalKind, FishManager, WildlifeManager
from world import FeatureType, PLANTABLE_LAND, TerrainType, World


TASK_COLOURS = {
    TaskType.CHOP_TREES: COLOUR_TASK_CHOP,
    TaskType.COLLECT_ROCKS: COLOUR_TASK_ROCK,
    TaskType.PLANT_SAPLINGS: COLOUR_TASK_PLANT,
    TaskType.FULL_MANAGE: COLOUR_TASK_MANAGE,
    TaskType.HUNT: COLOUR_TASK_HUNT,
    TaskType.FISH: COLOUR_TASK_FISH,
    TaskType.FORAGE_MUSHROOMS: COLOUR_TASK_FORAGE,
    TaskType.FORAGE_BERRIES: COLOUR_TASK_FORAGE,
    TaskType.FORAGE_HERBS: COLOUR_TASK_FORAGE,
    TaskType.PLANT_BERRY_SEEDS: COLOUR_TASK_PLANT,
    TaskType.PLANT_HERB_SEEDS: COLOUR_TASK_PLANT,
    TaskType.FULL_FORAGE: COLOUR_TASK_FORAGE,
    TaskType.FARM_FIELD: COLOUR_TASK_FARM,
}

FEATURE_FOR_BUILDING = {
    BuildingKind.FORESTER: FeatureType.FORESTER,
    BuildingKind.MASON: FeatureType.MASON,
    BuildingKind.HUNTER: FeatureType.HUNTER,
    BuildingKind.FORAGER: FeatureType.FORAGER,
    BuildingKind.FISHER: FeatureType.FISHER,
    BuildingKind.FARM: FeatureType.FARM,
    BuildingKind.FIELD: FeatureType.FIELD,
}

# Buildings that draw rectangular work areas via drag.
AREA_DRAW_KINDS = {
    BuildingKind.FORESTER,
    BuildingKind.MASON,
    BuildingKind.HUNTER,
    BuildingKind.FORAGER,
    BuildingKind.FISHER,
}


class Game:
    def __init__(self, *, headless: bool = False) -> None:
        self.headless = headless
        if headless:
            self.screen = pygame.Surface((max(1, WINDOW_WIDTH), max(1, WINDOW_HEIGHT)))
        else:
            self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
            pygame.display.set_caption("Environmental Farming Sandbox")
        self.clock = pygame.time.Clock()
        self.ui = UI()
        self.toolbar = Toolbar()
        self.resource_bar = ResourceBar()
        self.file_dialog = FileDialog()
        self.field_plan_dialog = FieldPlanDialog()
        self.building_inspect = BuildingInspectDialog()
        self.villager_inspect = VillagerInspectDialog()
        self.resource_inspect = ResourceInspectDialog()

        self.world = World()
        self.camera = Camera()
        self.player = Player(x=self.world.start_pos[0], y=self.world.start_pos[1])
        self.camera.center_on(self.player.x, self.player.y, self.world.cols, self.world.rows)
        self.home_storage = HomeStorage()
        self.villagers: list[Villager] = []
        self.buildings: dict[int, Building] = {}
        self.construction_sites: dict[int, ConstructionSite] = {}
        self.wildlife = WildlifeManager()
        self.fish = FishManager()
        self.next_villager_id = 1
        self.next_building_id = 1
        self.next_construction_id = 1
        self.sim_speed = 1
        self._speed_before_pause = 1
        self.calendar_day = 0
        self.day_tick = TICKS_PER_DAY
        self._pending_file_action: str | None = None

        # Selection / drawing
        self.selected_building_id: int | None = None
        self.selected_villager_id: int | None = None
        self.selected_habitat_kind: AnimalKind | None = None
        self.selected_habitat_id: int | None = None
        self.assign_workplace_mode = False
        self.place_kind: BuildingKind | None = None  # B cycles build ghost
        self.field_crop_kind: str = "sage"
        self.drawing = False
        self.draw_start: tuple[int, int] | None = None
        self.draw_current: tuple[int, int] | None = None
        self._mouse_down_cell: tuple[int, int] | None = None
        self._placing_field = False  # drag-to-size Field construction

        self.overlay_mode = OverlayMode.NONE
        self.overlay_values: list[list[float]] = build_overlay_grid(self.world, self.overlay_mode)
        # Biodiversity: season start/mid samples, averaged over past year (≤8).
        self._biodiversity_samples: list[list[list[float]]] = []
        self._biodiversity_average: list[list[float]] = [
            [0.0] * self.world.cols for _ in range(self.world.rows)
        ]

        self._give_starting_resources()
        self._ensure_core_buildings()
        self.wildlife.refresh_habitats(self.world)
        self.wildlife.seed_breeding_grounds(self.world)
        self._sample_biodiversity()
        self.status_message = (
            "Hire from Hiring hall popup. Toolbar builds place construction sites. "
            "Unassigned villagers build & transport by priority."
        )
        self.status_timer = STATUS_MESSAGE_FRAMES
        self.running = True
        self._drop_rng = random.Random(42)
        self._food_rng = random.Random(99)
        # Headless: no window present; AI still uses real cooldowns.
        self.fast_forward = bool(headless)
        # Season-neutral tiled map + water alpha mask; seasonal tint/ice at blit time.
        self._terrain_base: pygame.Surface | None = None
        self._terrain_base_key: tuple | None = None
        self._terrain_water_mask: pygame.Surface | None = None
        self._farm_cells_cached: set[tuple[int, int]] = set()
        self._season_mute: pygame.Surface | None = None
        self._season_mute_key: float | None = None
        self._ice_overlay: pygame.Surface | None = None
        self._ice_overlay_key: float | None = None
        # F6: deterministic autotile diagnostic scene + per-cell mask overlay.
        self.autotile_diag = False
        self._diag_cell_meta: dict[tuple[int, int], dict] = {}
        self._diag_backup_cells: list[list] | None = None

    def _give_starting_resources(self) -> None:
        self.home_storage.wood = STARTING_WOOD
        self.home_storage.rock = STARTING_ROCK
        self.home_storage.berries = STARTING_FOOD

    def _ensure_core_buildings(self) -> None:
        """Ensure HOME and WORKSTATION buildings exist at their world positions."""
        # Find or create HOME building
        home_building = None
        for b in self.buildings.values():
            if b.kind == BuildingKind.HOME:
                home_building = b
                break
        if home_building is None:
            home_building = Building(
                id=self.next_building_id,
                kind=BuildingKind.HOME,
                x=self.world.home_pos[0],
                y=self.world.home_pos[1],
                capacity=BUILDING_STORAGE_CAPACITY * 50,
            )
            self.buildings[home_building.id] = home_building
            self.next_building_id += 1
        else:
            # Sync position
            home_building.x = self.world.home_pos[0]
            home_building.y = self.world.home_pos[1]

        # Find or create WORKSTATION building
        workstation_building = None
        for b in self.buildings.values():
            if b.kind == BuildingKind.WORKSTATION:
                workstation_building = b
                break
        if workstation_building is None:
            workstation_building = Building(
                id=self.next_building_id,
                kind=BuildingKind.WORKSTATION,
                x=self.world.workstation_pos[0],
                y=self.world.workstation_pos[1],
                capacity=BUILDING_STORAGE_CAPACITY * 50,
            )
            self.buildings[workstation_building.id] = workstation_building
            self.next_building_id += 1
        else:
            # Sync position
            workstation_building.x = self.world.workstation_pos[0]
            workstation_building.y = self.world.workstation_pos[1]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def run(self) -> None:
        pygame.key.set_repeat(180, 40)
        while self.running:
            self._handle_events()
            if self.sim_speed > 0:
                for _ in range(self.sim_speed):
                    self._update_simulation()
            self._update_status_timer()
            self._draw()
            self.clock.tick(FPS)
        pygame.quit()

    def reset(self) -> None:
        self.world.reset()
        self.player.reset(self.world.start_pos[0], self.world.start_pos[1])
        self.camera.center_on(self.player.x, self.player.y, self.world.cols, self.world.rows)
        self.home_storage.reset()
        self.villagers.clear()
        self.buildings.clear()
        self.construction_sites.clear()
        self.wildlife.reset()
        self.fish.reset()
        self.next_villager_id = 1
        self.next_building_id = 1
        self.next_construction_id = 1
        self._clear_selection()
        self.place_kind = None
        self.field_crop_kind = "sage"
        self.calendar_day = 0
        self.day_tick = TICKS_PER_DAY
        self.file_dialog.close()
        self.field_plan_dialog.close()
        self.building_inspect.close()
        self.villager_inspect.close()
        self.resource_inspect.close()
        self.drawing = False
        self.draw_start = None
        self.draw_current = None
        self._mouse_down_cell = None
        self._placing_field = False
        self.overlay_mode = OverlayMode.NONE
        self._biodiversity_samples.clear()
        self._give_starting_resources()
        self._ensure_core_buildings()
        self._food_rng.seed(99)
        self.wildlife.refresh_habitats(self.world)
        self.wildlife.seed_breeding_grounds(self.world)
        self._sample_biodiversity()
        self._refresh_indicators()
        self._set_status("World reset.")

    def _clear_selection(self) -> None:
        self.selected_building_id = None
        self.selected_villager_id = None
        self.selected_habitat_kind = None
        self.selected_habitat_id = None
        self.assign_workplace_mode = False
        self.drawing = False
        self.draw_start = None
        self.draw_current = None
        self._placing_field = False
        self.field_plan_dialog.close()
        self.building_inspect.close()
        self.villager_inspect.close()
        self.resource_inspect.close()

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------
    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if self.file_dialog.open:
                    self.file_dialog.handle_keydown(event)
                    self._finish_file_dialog_if_needed()
                    continue
                if self.field_plan_dialog.open and self.field_plan_dialog.handle_keydown(
                    event
                ):
                    self._finish_field_plan_dialog()
                    continue
                if self.building_inspect.open and self.building_inspect.handle_keydown(
                    event
                ):
                    continue
                if self.villager_inspect.open and self.villager_inspect.handle_keydown(
                    event
                ):
                    continue
                if self.resource_inspect.open and self.resource_inspect.handle_keydown(
                    event
                ):
                    continue
                self._on_keydown(event.key)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.file_dialog.open:
                    self.file_dialog.handle_click(event.pos)
                    self._finish_file_dialog_if_needed()
                    continue
                # Floating field editor: only consume clicks on the panel itself.
                if self.field_plan_dialog.open and self.field_plan_dialog.contains(
                    event.pos
                ):
                    building = self._field_plan_building()
                    self.field_plan_dialog.handle_mousedown(event.pos, building)
                    self._apply_pending_field_plan()
                    self._finish_field_plan_dialog()
                    continue
                if self.building_inspect.open and self.building_inspect.contains(
                    event.pos
                ):
                    self.building_inspect.handle_mousedown(event.pos)
                    self._apply_building_inspect_action()
                    continue
                if self.villager_inspect.open and self.villager_inspect.contains(
                    event.pos
                ):
                    self.villager_inspect.handle_mousedown(event.pos)
                    self._apply_villager_inspect_action()
                    continue
                if self.resource_inspect.open and self.resource_inspect.contains(
                    event.pos
                ):
                    self.resource_inspect.handle_mousedown(event.pos)
                    continue
                mx, my = event.pos
                if mx >= map_view_width() and my >= MAP_OFFSET_Y:
                    if self._handle_panel_click(event.pos):
                        continue
                self._on_mouse_down(event.pos)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if self.file_dialog.open:
                    continue
                # Finish panel drag / window move without also treating as a map action.
                if self.field_plan_dialog.open and (
                    self.field_plan_dialog._moving
                    or self.field_plan_dialog._drag_start is not None
                ):
                    building = self._field_plan_building()
                    self.field_plan_dialog.handle_mouseup(event.pos, building)
                    self._apply_pending_field_plan()
                    self._finish_field_plan_dialog()
                    continue
                if self.building_inspect.open and self.building_inspect._moving:
                    self.building_inspect.handle_mouseup(event.pos)
                    continue
                if self.villager_inspect.open and self.villager_inspect._moving:
                    self.villager_inspect.handle_mouseup(event.pos)
                    continue
                if self.resource_inspect.open and self.resource_inspect._moving:
                    self.resource_inspect.handle_mouseup(event.pos)
                    continue
                self._on_mouse_up(event.pos)
            elif event.type == pygame.MOUSEMOTION:
                if self.file_dialog.open:
                    continue
                if self.field_plan_dialog.open and (
                    self.field_plan_dialog._moving
                    or self.field_plan_dialog._drag_start is not None
                ):
                    self.field_plan_dialog.handle_mousemotion(
                        event.pos, self._field_plan_building()
                    )
                    continue
                if self.building_inspect.open and self.building_inspect._moving:
                    self.building_inspect.handle_mousemotion(event.pos)
                    continue
                if self.villager_inspect.open and self.villager_inspect._moving:
                    self.villager_inspect.handle_mousemotion(event.pos)
                    continue
                if self.resource_inspect.open and self.resource_inspect._moving:
                    self.resource_inspect.handle_mousemotion(event.pos)
                    continue
                if self.building_inspect.open:
                    self.building_inspect.handle_mousemotion(event.pos)
                if self.villager_inspect.open:
                    self.villager_inspect.handle_mousemotion(event.pos)
                if self.resource_inspect.open:
                    self.resource_inspect.handle_mousemotion(event.pos)
                if self.drawing:
                    self._on_mouse_drag(event.pos)
            elif event.type == pygame.MOUSEWHEEL:
                if self.file_dialog.open:
                    continue
                if self.field_plan_dialog.open and self.field_plan_dialog.contains(
                    pygame.mouse.get_pos()
                ):
                    continue
                if self.building_inspect.open and self.building_inspect.contains(
                    pygame.mouse.get_pos()
                ):
                    continue
                if self.villager_inspect.open and self.villager_inspect.contains(
                    pygame.mouse.get_pos()
                ):
                    continue
                if self.resource_inspect.open and self.resource_inspect.contains(
                    pygame.mouse.get_pos()
                ):
                    continue
                mx, my = pygame.mouse.get_pos()
                if mx >= map_view_width() and my >= MAP_OFFSET_Y:
                    self.ui.scroll(event.y * 28)
                else:
                    # Zoom camera over map (not over minimap, not over dialogs)
                    if my >= MAP_OFFSET_Y and not self._minimap_rect().collidepoint((mx, my)):
                        factor = (1 + ZOOM_STEP) if event.y > 0 else (1 - ZOOM_STEP)
                        self.camera.zoom_at(factor, (mx, my), self.world.cols, self.world.rows)

    def _finish_file_dialog_if_needed(self) -> None:
        if self.file_dialog.open:
            return
        if self.file_dialog.cancelled:
            self._pending_file_action = None
            self._set_status("Cancelled.")
            return
        path = self.file_dialog.result_path
        if path is None:
            return
        action = self._pending_file_action
        self._pending_file_action = None
        if action == "save":
            try:
                save_to_path(self, path)
                self._set_status(f"Saved to {path.name}")
            except Exception as exc:
                self._set_status(f"Save failed: {exc}")
        elif action == "load":
            try:
                load_from_path(self, path)
                self._set_status(f"Loaded {path.name} (speed x{self.sim_speed})")
            except Exception as exc:
                self._set_status(f"Load failed: {exc}")

    def _on_keydown(self, key: int) -> None:
        if key == pygame.K_ESCAPE:
            if self.toolbar.file_menu_open:
                self.toolbar.file_menu_open = False
                return
            if self.field_plan_dialog.open:
                self.field_plan_dialog.close()
                return
            if self.building_inspect.open:
                self.building_inspect.close()
                return
            if self.villager_inspect.open:
                self.villager_inspect.close()
                return
            if self.resource_inspect.open:
                self.resource_inspect.close()
                return
            if (
                self.selected_building_id is not None
                or self.selected_villager_id is not None
                or self.place_kind is not None
                or self.assign_workplace_mode
            ):
                self._clear_selection()
                self.place_kind = None
                self._set_status("Selection cleared.")
            # Esc never quits the game.
        elif key == pygame.K_r:
            self.reset()
        elif key in (pygame.K_e, pygame.K_RETURN, pygame.K_KP_ENTER):
            self._interact_at_player()
        elif key == pygame.K_b:
            self._cycle_place_kind()
        elif key == pygame.K_t:
            self._cycle_selected_building_task()
        elif key == pygame.K_c:
            self._clear_selected_building_areas()
        elif key == pygame.K_SPACE:
            self._toggle_pause()
        elif key == pygame.K_1:
            self._set_overlay(OverlayMode.NONE)
        elif key == pygame.K_2:
            self._set_overlay(OverlayMode.HABITAT_DIVERSITY)
        elif key == pygame.K_3:
            self._set_overlay(OverlayMode.TREE_DENSITY)
        elif key == pygame.K_4:
            self._set_overlay(OverlayMode.SPECIES_DIVERSITY)
        elif key == pygame.K_5:
            self._set_overlay(OverlayMode.DISTURBANCE)
        elif key == pygame.K_6:
            self._set_overlay(OverlayMode.BIODIVERSITY)
        elif key == pygame.K_F6:
            self._toggle_autotile_diagnostic()
        elif key == pygame.K_w:
            self.camera.pan(0, -1, self.world.cols, self.world.rows)
        elif key == pygame.K_s:
            self.camera.pan(0, 1, self.world.cols, self.world.rows)
        elif key == pygame.K_a:
            self.camera.pan(-1, 0, self.world.cols, self.world.rows)
        elif key == pygame.K_d:
            self.camera.pan(1, 0, self.world.cols, self.world.rows)
        elif key == pygame.K_UP:
            self._try_move(0, -1)
        elif key == pygame.K_DOWN:
            self._try_move(0, 1)
        elif key == pygame.K_LEFT:
            self._try_move(-1, 0)
        elif key == pygame.K_RIGHT:
            self._try_move(1, 0)

    def _selected_building(self) -> Building | None:
        if self.selected_building_id is None:
            return None
        return self.buildings.get(self.selected_building_id)

    def _minimap_rect(self) -> pygame.Rect:
        """Return the minimap rectangle in screen coordinates."""
        margin = 8
        x = map_view_width() - MINIMAP_WIDTH - margin
        y = MAP_OFFSET_Y + map_view_height() - MINIMAP_HEIGHT - margin
        return pygame.Rect(x, y, MINIMAP_WIDTH, MINIMAP_HEIGHT)

    def _map_cell_from_pos(self, pos: tuple[int, int]) -> tuple[int, int] | None:
        """Convert screen position to world cell coordinates (None if over minimap or outside)."""
        mx, my = pos
        # Check if over minimap
        if self._minimap_rect().collidepoint(pos):
            return None
        # Use camera to convert screen to world
        return self.camera.screen_to_world(mx, my)

    def _cell_rect(self, x: int, y: int) -> pygame.Rect:
        """Return screen rect for given world cell coordinates."""
        return self.camera.cell_rect(x, y)

    def _cell_center(self, x: int, y: int) -> tuple[int, int]:
        """Return screen center point for given world cell coordinates."""
        rect = self.camera.cell_rect(x, y)
        return rect.centerx, rect.centery

    def _on_mouse_down(self, pos: tuple[int, int]) -> None:
        building = self._selected_building()
        if self.toolbar.contains(pos) or self.toolbar.file_menu_open:
            action = self.toolbar.hit_test(
                pos,
                building,
                place_kind=self.place_kind,
                field_crop=self.field_crop_kind,
            )
            if action is not None:
                self._handle_toolbar_action(action)
            elif self.toolbar.file_menu_open:
                self.toolbar.file_menu_open = False
            return
        if self.resource_bar.contains(pos):
            if self.resource_bar.handle_click(pos):
                self._set_status(f"Resources: {VIEW_LABELS[self.resource_bar.view_mode]}")
            return

        # Minimap click: center camera on clicked world position
        minimap_rect = self._minimap_rect()
        if minimap_rect.collidepoint(pos):
            mx, my = pos
            # Convert minimap click to world coordinates
            rel_x = (mx - minimap_rect.x) / minimap_rect.width
            rel_y = (my - minimap_rect.y) / minimap_rect.height
            world_x = rel_x * self.world.cols
            world_y = rel_y * self.world.rows
            self.camera.center_on(world_x, world_y, self.world.cols, self.world.rows)
            return

        cell = self._map_cell_from_pos(pos)
        if cell is None:
            return
        self._mouse_down_cell = cell
        # Field placement: drag to size the plot.
        if self.place_kind == BuildingKind.FIELD:
            self.drawing = True
            self._placing_field = True
            self.draw_start = cell
            self.draw_current = cell
            return
        if self.place_kind is not None:
            return
        # Only start area drawing for workplaces that own task areas.
        if self.selected_building_id is not None and self.selected_building_id in self.buildings:
            building = self.buildings[self.selected_building_id]
            if building.kind in AREA_DRAW_KINDS:
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
        placing_field = self._placing_field
        self.drawing = False
        self._placing_field = False
        self.draw_start = None
        self.draw_current = None
        down = self._mouse_down_cell
        self._mouse_down_cell = None

        if end is None or start is None or down is None:
            return

        if placing_field and self.place_kind == BuildingKind.FIELD:
            self._place_field_site(start, end)
            return

        # Click (same cell): selection / assignment.
        if end == down:
            self._handle_click(end)
            return

        # Drag: task areas for workplaces.
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

        # Build mode: click places a construction site (non-Field).
        if self.place_kind is not None:
            if self.place_kind == BuildingKind.FIELD:
                self._place_field_site((x, y), (x, y))
                return
            if self._place_construction_site(self.place_kind, x, y):
                return

        # Explicit assign-to-workplace mode (after Assign button).
        if self.assign_workplace_mode and self.selected_villager_id is not None:
            if self._try_assign_selected_villager(x, y):
                return
            self._set_status("Click a building or home to assign workplace.")
            return

        villager = self._villager_at(x, y)
        if villager is not None:
            self._open_villager_inspect(villager)
            return

        building = self._building_at(x, y)
        if building is not None:
            self._select_building(building)
            return

        resource = self._map_resource_at(x, y)
        if resource is not None:
            self.villager_inspect.close()
            title, quantity, unit, detail = resource
            self.resource_inspect.open_for(
                title=title,
                quantity=quantity,
                unit=unit,
                detail=detail,
                cell=(x, y),
                screen_xy=self.camera.world_to_screen(x, y),
            )
            self._set_status(f"{title}: {quantity} {unit}".strip())
            return

        # Single-cell task area when a building is already selected.
        if self.selected_building_id is not None:
            selected = self.buildings.get(self.selected_building_id)
            if selected is not None and selected.kind in AREA_DRAW_KINDS:
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

    def _handle_panel_click(self, pos: tuple[int, int]) -> bool:
        action = self.ui.hit_action(pos)
        if action is not None and action.startswith("prio:"):
            parts = action.split(":")
            if len(parts) == 3:
                vid, slot = int(parts[1]), int(parts[2])
                villager = self._get_villager(vid)
                if villager is not None:
                    mode = villager.cycle_priority_slot(slot)
                    self._set_status(
                        f"Villager {vid} priority {slot + 1}: {PRIORITY_LABELS[mode]}"
                    )
            return True
        if action is not None and action.startswith("ration:"):
            vid = int(action.split(":")[1])
            villager = self._get_villager(vid)
            if villager is not None:
                mode = villager.cycle_ration_mode()
                self._set_status(
                    f"Villager {vid} rations: {RATION_LABELS[mode]}"
                )
            return True
        if action == "assign_villager":
            self._assign_unassigned_to_selected_building()
            return True
        if action == "unassign_villager":
            self._unassign_worker_from_selected_building()
            return True
        if action == "open_field_plan":
            building = self._selected_building()
            if building is not None and building.kind == BuildingKind.FIELD:
                self._open_field_plan(building)
            return True
        if action == "cycle_work_mode":
            self._cycle_selected_building_work_mode()
            return True
        if action == "hire_villager":
            self._hire_villager()
            return True
        if action == "assign_workplace":
            if self.selected_villager_id is None:
                return True
            self.assign_workplace_mode = not self.assign_workplace_mode
            if self.assign_workplace_mode:
                self._set_status("Pick a workplace on the map or in the Buildings list.")
            else:
                self._set_status("Assign cancelled.")
            return True
        if action == "assign_home":
            if self.selected_villager_id is not None:
                self._assign_villager_to_home(self.selected_villager_id)
            return True

        hit = self.ui.hit_priority(pos)
        if hit is not None:
            vid, slot = hit
            villager = self._get_villager(vid)
            if villager is not None:
                mode = villager.cycle_priority_slot(slot)
                self._set_status(
                    f"Villager {vid} priority {slot + 1}: {PRIORITY_LABELS[mode]}"
                )
            return True

        list_hit = self.ui.hit_list(pos)
        if list_hit is None:
            return False
        kind, item_id = list_hit

        if self.assign_workplace_mode and self.selected_villager_id is not None:
            if kind == "building":
                self._assign_villager_to_building(self.selected_villager_id, item_id)
                return True
            if kind == "home":
                self._assign_villager_to_home(self.selected_villager_id)
                return True

        if kind == "building":
            building = self.buildings.get(item_id)
            if building is None:
                return True
            self._select_building(building)
            return True
        if kind == "villager":
            villager = self._get_villager(item_id)
            if villager is None:
                return True
            self._open_villager_inspect(villager)
            return True
        if kind == "home":
            self._set_status("Home storehouse. Select a villager, then Assign to home.")
            return True
        if kind == "deer_ground":
            self._select_habitat(AnimalKind.DEER, item_id)
            return True
        if kind == "boar_ground":
            self._select_habitat(AnimalKind.BOAR, item_id)
            return True
        return False

    def _select_habitat(self, kind: AnimalKind, patch_id: int) -> None:
        hab = self.wildlife.habitat(patch_id)
        if hab is None:
            return
        breed = (
            hab.deer_breeding if kind == AnimalKind.DEER else hab.boar_breeding
        )
        if not breed:
            return
        self.selected_building_id = None
        self.selected_villager_id = None
        self.selected_habitat_kind = kind
        self.selected_habitat_id = patch_id
        self.building_inspect.close()
        self.villager_inspect.close()
        self.resource_inspect.close()
        cx = sum(p[0] for p in breed) // len(breed)
        cy = sum(p[1] for p in breed) // len(breed)
        self.camera.center_on(cx, cy, self.world.cols, self.world.rows)
        label = "Deer" if kind == AnimalKind.DEER else "Boar"
        pop = self.wildlife.count_in_patch(kind, patch_id)
        cap = hab.deer_cap if kind == AnimalKind.DEER else hab.boar_cap
        self._set_status(f"{label} ground #{patch_id}: {pop}/{cap}")

    def _assign_unassigned_to_selected_building(self) -> None:
        if self.selected_building_id is None:
            return
        building = self.buildings.get(self.selected_building_id)
        if building is None:
            return
        # Special handling for HOME: assign as home hauler
        if building.kind == BuildingKind.HOME:
            free = next(
                (
                    v
                    for v in self.villagers
                    if v.building_id is None and not v.assigned_to_home
                ),
                None,
            )
            if free is None:
                self._set_status("No unassigned villagers available.")
                return
            self._assign_villager_to_home(free.id)
            return
        free = next(
            (
                v
                for v in self.villagers
                if v.building_id is None and not v.assigned_to_home
            ),
            None,
        )
        if free is None:
            self._set_status("No unassigned villagers available.")
            return
        self._assign_villager_to_building(free.id, building.id)

    def _unassign_worker_from_selected_building(self) -> None:
        building = self._selected_building()
        if building is None:
            self._set_status("Select a building first.")
            return
        # Special handling for HOME: unassign a home hauler
        if building.kind == BuildingKind.HOME:
            haulers = [v for v in self.villagers if v.assigned_to_home]
            if not haulers:
                self._set_status("No haulers assigned to home.")
                return
            hauler = None
            if self.selected_villager_id is not None:
                hauler = next(
                    (v for v in haulers if v.id == self.selected_villager_id), None
                )
            if hauler is None:
                hauler = max(haulers, key=lambda v: v.id)
            hauler.assigned_to_home = False
            hauler.set_default_priorities()
            self._set_status(f"Unassigned villager {hauler.id} from home haulers.")
            return
        workers = [v for v in self.villagers if v.building_id == building.id]
        if not workers:
            self._set_status(f"No workers assigned to {BUILDING_LABELS[building.kind]}.")
            return
        worker = None
        if self.selected_villager_id is not None:
            worker = next(
                (v for v in workers if v.id == self.selected_villager_id), None
            )
        if worker is None:
            worker = max(workers, key=lambda v: v.id)
        worker.clear_assignment()
        worker.set_default_priorities()
        self._set_status(
            f"Unassigned villager {worker.id} from {BUILDING_LABELS[building.kind]}."
        )

    def _cycle_selected_building_work_mode(self) -> None:
        building = self._selected_building()
        if building is None:
            self._set_status("Select a building first.")
            return
        if not building.allows_planting():
            building.set_work_mode(WorkMode.COLLECT)
            self._set_status(f"{BUILDING_LABELS[building.kind]} is collect-only.")
            return
        mode = building.cycle_work_mode()
        self._wake_building_workers(building.id)
        self._set_status(
            f"{BUILDING_LABELS[building.kind]} behaviour: {WORK_MODE_LABELS[mode]}."
        )

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
        building = self.buildings.get(building_id)
        if building is None:
            return
        if building.kind == BuildingKind.FIELD:
            self._set_status("Assign workers to a Farm — Fields only define crop areas.")
            return
        if building.kind == BuildingKind.HOME:
            self._assign_villager_to_home(villager_id)
            return
        if building.kind == BuildingKind.WORKSTATION:
            self._set_status("Hiring hall does not take workers — hire there, then assign elsewhere.")
            return
        villager = self._get_villager(villager_id)
        if villager is None:
            return
        villager.clear_assignment()
        villager.building_id = building_id
        villager.state = VillagerState.IDLE
        villager.set_default_priorities()
        self.assign_workplace_mode = False
        self.selected_villager_id = None
        self.selected_building_id = building_id
        self._open_building_inspect(building)
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
        villager.set_default_priorities()
        self.assign_workplace_mode = False
        self.selected_villager_id = None
        self.selected_building_id = None
        self._set_status(f"Villager {villager.id} → Home (hauler)")

    def _cycle_place_kind(self) -> None:
        order: list[BuildingKind | None] = [
            BuildingKind.FORESTER,
            BuildingKind.MASON,
            BuildingKind.HUNTER,
            BuildingKind.FORAGER,
            BuildingKind.FISHER,
            BuildingKind.FARM,
            BuildingKind.FIELD,
            None,
        ]
        if self.place_kind not in order:
            self.place_kind = BuildingKind.FORESTER
        else:
            idx = order.index(self.place_kind)
            self.place_kind = order[(idx + 1) % len(order)]
        self._announce_place_kind()

    def _set_place_kind(self, kind: BuildingKind | None) -> None:
        self.place_kind = kind
        self._announce_place_kind()

    def _announce_place_kind(self) -> None:
        costs = {
            BuildingKind.FORESTER: (FORESTER_COST_WOOD, FORESTER_COST_ROCK, "Forester"),
            BuildingKind.MASON: (MASON_COST_WOOD, MASON_COST_ROCK, "Mason"),
            BuildingKind.HUNTER: (HUNTER_COST_WOOD, HUNTER_COST_ROCK, "Hunter"),
            BuildingKind.FORAGER: (FORAGER_COST_WOOD, FORAGER_COST_ROCK, "Forager"),
            BuildingKind.FISHER: (FISHER_COST_WOOD, FISHER_COST_ROCK, "Fisher"),
            BuildingKind.FARM: (FARM_COST_WOOD, FARM_COST_ROCK, "Farm"),
            BuildingKind.FIELD: (FIELD_COST_WOOD, FIELD_COST_ROCK, "Field"),
        }
        if self.place_kind is None:
            self._set_status("Build mode off.")
        elif self.place_kind == BuildingKind.FIELD:
            w, r, name = costs[self.place_kind]
            self._set_status(
                f"Build: {name} ({w}w {r}r). Drag a rectangle on soil/grass to size the field."
            )
        else:
            w, r, name = costs[self.place_kind]
            self._set_status(
                f"Build: {name} ({w}w {r}r). Click empty soil/grass to place a site."
            )

    def _set_building_task(self, task: TaskType) -> None:
        building = self._selected_building()
        if building is None:
            self._set_status("Select a building first.")
            return
        building.draw_task_type = task
        building.work_mode = Building.work_mode_from_task(building.kind, task)
        self._wake_building_workers(building.id)
        self._set_status(
            f"{BUILDING_LABELS[building.kind]}: {WORK_MODE_LABELS[building.work_mode]} "
            f"({TASK_LABELS[task]})"
        )

    def _set_building_work_mode(self, mode: WorkMode) -> None:
        building = self._selected_building()
        if building is None:
            self._set_status("Select a building first.")
            return
        building.set_work_mode(mode)
        self._wake_building_workers(building.id)
        self._set_status(
            f"{BUILDING_LABELS[building.kind]} behaviour: {WORK_MODE_LABELS[mode]}."
        )

    @property
    def season(self) -> Season:
        return season_for_day(self.calendar_day)

    def _set_sim_speed(self, speed: int) -> None:
        if speed not in SIM_SPEEDS:
            return
        if speed > 0:
            self._speed_before_pause = speed
        self.sim_speed = speed
        if speed == 0:
            self._set_status("Paused.")
        else:
            self._set_status(f"Simulation speed x{speed}")

    def _toggle_pause(self) -> None:
        if self.sim_speed == 0:
            restore = getattr(self, "_speed_before_pause", 1) or 1
            if restore not in SIM_SPEEDS or restore == 0:
                restore = 1
            self._set_sim_speed(restore)
        else:
            self._speed_before_pause = self.sim_speed
            self._set_sim_speed(0)

    def _toggle_autotile_diagnostic(self) -> None:
        if self.autotile_diag:
            self.autotile_diag = False
            self._diag_cell_meta.clear()
            self.reset()
            self._set_status("Autotile diagnostic off — world reset.")
            return
        self.autotile_diag = True
        self._set_sim_speed(0)
        self._layout_autotile_diagnostic()
        print(describe_system(), flush=True)
        self._set_status(
            "Autotile diagnostic ON (F6 exit). Labels: xy · mask/case · atlas · tile_id"
        )

    def _layout_autotile_diagnostic(self) -> None:
        """Deterministic soil-on-grass shapes for MS verification (no gen changes)."""
        for y in range(self.world.rows):
            for x in range(self.world.cols):
                cell = self.world.cells[y][x]
                cell.terrain = TerrainType.GRASS
                cell.feature = FeatureType.NONE
                cell.deposit = 0
                cell.growth_ticks = 0
                cell.crop_kind = None

        def soil(x: int, y: int) -> None:
            if self.world.in_bounds(x, y):
                self.world.cells[y][x].terrain = TerrainType.SOIL

        soil(2, 2)  # isolated
        for dy in range(2):
            for dx in range(2):
                soil(5 + dx, 2 + dy)  # 2×2
        for dx in range(4):
            soil(9 + dx, 2)  # horizontal strip
        for dy in range(4):
            soil(2, 5 + dy)  # vertical strip
        soil(5, 5)
        soil(6, 5)
        soil(5, 6)
        soil(5, 7)  # L-shape
        for dy in range(3):
            for dx in range(3):
                if dx == 2 and dy == 0:
                    continue
                soil(9 + dx, 5 + dy)  # concave (missing NE)

        # All 16 MS cases: each mask shown on a GRASS cell whose shared corners
        # are forced by diagonal soil seeds (cell itself stays grass).
        for mask in range(16):
            bx = 1 + (mask % 8) * 3
            by = 11 + (mask // 8) * 3
            for dy in range(-1, 3):
                for dx in range(-1, 3):
                    if self.world.in_bounds(bx + dx, by + dy):
                        self.world.cells[by + dy][bx + dx].terrain = TerrainType.GRASS
            # Seeds affecting only the intended vertices of cell (bx, by).
            if mask & 1:  # TL
                soil(bx - 1, by - 1)
            if mask & 2:  # TR
                soil(bx + 1, by - 1)
            if mask & 4:  # BR
                soil(bx + 1, by + 1)
            if mask & 8:  # BL
                soil(bx - 1, by + 1)

        self.buildings.clear()
        self.villagers.clear()
        self.construction_sites.clear()
        self._clear_selection()
        self.world.bump_terrain()
        self._diag_cell_meta.clear()
        farm: set[tuple[int, int]] = set()
        self._ensure_terrain_base(farm)
        self._capture_diag_meta(farm)
        ok_e = ok_s = bad = 0
        total = (self.world.rows - 1) * (self.world.cols - 1)
        for y in range(self.world.rows - 1):
            for x in range(self.world.cols - 1):
                e, s = verify_shared_edges(
                    lambda tx, ty, f=farm: self._visual_terrain_at(tx, ty, f),
                    x,
                    y,
                )
                ok_e += int(e)
                ok_s += int(s)
                if not (e and s):
                    bad += 1
        print(
            f"shared-edge check: east_ok={ok_e}/{total} south_ok={ok_s}/{total} bad={bad}",
            flush=True,
        )

    def _capture_diag_meta(self, farm_cells: set[tuple[int, int]]) -> None:
        from terrain_tiles import cell_corners, mask_for_corners

        self._diag_cell_meta.clear()
        terrain_at = lambda tx, ty: self._visual_terrain_at(tx, ty, farm_cells)
        for y in range(self.world.rows):
            for x in range(self.world.cols):
                corners = cell_corners(terrain_at, x, y)
                tl, tr, br, bl = corners
                types = {tl, tr, br, bl}
                if len(types) == 1:
                    only = next(iter(types))
                    # Solid cell: canonical mask 15. Soil-FG empty on pure grass is 0.
                    mask = 0 if only == TerrainType.GRASS else 15
                    fg, bg = (
                        (TerrainType.SOIL, TerrainType.GRASS)
                        if only == TerrainType.GRASS
                        else (only, only)
                    )
                else:
                    bg = (
                        TerrainType.GRASS
                        if TerrainType.GRASS in types
                        else next(iter(types))
                    )
                    fg = (
                        TerrainType.SOIL
                        if TerrainType.SOIL in types
                        else next(t for t in types if t != bg)
                    )
                    mask = mask_for_corners(tl, tr, br, bl, fg)
                row, col = atlas_row_col(mask)
                if x < self.world.cols - 1 and y < self.world.rows - 1:
                    east_ok, south_ok = verify_shared_edges(terrain_at, x, y)
                else:
                    east_ok, south_ok = True, True
                self._diag_cell_meta[(x, y)] = {
                    "corners": corners,
                    "mask": mask,
                    "raw_mask": mask,
                    "canonical_mask": mask,
                    "fg": fg,
                    "bg": bg,
                    "case": CASE_NAMES.get(mask, "?"),
                    "atlas": (row, col),
                    "tile_id": f"ms{mask:02d}",
                    "east_ok": east_ok,
                    "south_ok": south_ok,
                    "centre": self.world.cells[y][x].terrain,
                }

    def _draw_autotile_diag_overlay(self) -> None:
        if not self.autotile_diag:
            return
        font = pygame.font.SysFont("menlo", 9)
        legend = font.render(
            "N=y-1 E=x+1 S=y+1 W=x-1 | bits TL=1 TR=2 BR=4 BL=8 | F6 exit",
            True,
            (240, 240, 240),
        )
        self.screen.blit(legend, (8, MAP_OFFSET_Y + 4))
        ox, oy = self._cell_center(0, 0)
        pygame.draw.line(self.screen, (255, 220, 80), (ox, oy), (ox, oy - 18), 2)
        self.screen.blit(font.render("N", True, (255, 220, 80)), (ox - 4, oy - 28))
        pygame.draw.line(self.screen, (255, 220, 80), (ox, oy), (ox + 18, oy), 2)
        self.screen.blit(font.render("E", True, (255, 220, 80)), (ox + 20, oy - 5))

        interesting = {
            (2, 2),
            (5, 2), (6, 2), (5, 3), (6, 3),
            (9, 2), (10, 2), (11, 2), (12, 2),
            (2, 5), (2, 6), (2, 7), (2, 8),
            (5, 5), (6, 5), (5, 6), (5, 7),
            (9, 5), (10, 5), (11, 5),
            (9, 6), (10, 6), (11, 6),
            (9, 7), (10, 7), (11, 7),
        }
        for mask in range(16):
            bx = 1 + (mask % 8) * 3
            by = 11 + (mask // 8) * 3
            interesting.add((bx, by))

        for (x, y), meta in self._diag_cell_meta.items():
            if (
                (x, y) not in interesting
                and meta["centre"] == TerrainType.GRASS
                and meta["mask"] in (0, 15)
            ):
                continue
            rect = self._cell_rect(x, y)
            colour = (
                (255, 80, 80)
                if not (meta["east_ok"] and meta["south_ok"])
                else (255, 255, 255)
            )
            yy = rect.y + 1
            for line in (
                f"{x},{y}",
                f"m{meta['mask']:02d}/{meta['case']}",
                f"a{meta['atlas'][0]},{meta['atlas'][1]} {meta['tile_id']}",
            ):
                self.screen.blit(font.render(line, True, colour), (rect.x + 1, yy))
                yy += 10
            dots = (
                (rect.x + 3, rect.y + 3, meta["corners"][0]),
                (rect.right - 4, rect.y + 3, meta["corners"][1]),
                (rect.right - 4, rect.bottom - 4, meta["corners"][2]),
                (rect.x + 3, rect.bottom - 4, meta["corners"][3]),
            )
            for dx, dy, corner in dots:
                c = (80, 200, 255) if corner == TerrainType.SOIL else (50, 50, 50)
                pygame.draw.circle(self.screen, c, (dx, dy), 2)

    def _advance_day(self) -> None:
        prev = self.season
        self.calendar_day = (self.calendar_day + 1) % YEAR_DAYS
        if self.season != prev:
            self._expire_unharvested_crops(prev)
            if self.season == Season.WINTER:
                self.world.clear_mushrooms()
            self.wildlife.on_season_change(self.world, self.season)
            self._set_status(f"{format_date(self.calendar_day)} begins.")
        # Biodiversity: sample at season start (day 0) and midpoint.
        if self._is_biodiversity_sample_day(self.calendar_day):
            self._sample_biodiversity()
            self._sync_habitat_selection()

    @staticmethod
    def _is_biodiversity_sample_day(calendar_day: int) -> bool:
        d = day_in_season(calendar_day)
        return d == 0 or d == DAYS_PER_SEASON // 2

    def _sample_biodiversity(self) -> None:
        """Record a spatial biodiversity snapshot; keep last year of samples.

        Also refreshes wildlife forest-patch habitats on the same cadence.
        """
        self.wildlife.refresh_habitats(self.world)
        snap = biodiversity_snapshot(
            self.world,
            deer_positions=((a.x, a.y) for a in self.wildlife.deer()),
            boar_positions=((a.x, a.y) for a in self.wildlife.boars()),
            fish_positions=((f.x, f.y) for f in self.fish.fish),
        )
        self._biodiversity_samples.append(snap)
        while len(self._biodiversity_samples) > BIODIVERSITY_SAMPLES_PER_YEAR:
            self._biodiversity_samples.pop(0)
        self._biodiversity_average = average_grids(
            self._biodiversity_samples, self.world.rows, self.world.cols
        )
        if self.overlay_mode == OverlayMode.BIODIVERSITY:
            self._refresh_indicators()

    def _sync_habitat_selection(self) -> None:
        """Drop habitat highlight if that breeding ground vanished on refresh."""
        if self.selected_habitat_id is None or self.selected_habitat_kind is None:
            return
        hab = self.wildlife.habitat(self.selected_habitat_id)
        if hab is None:
            self.selected_habitat_kind = None
            self.selected_habitat_id = None
            return
        breed = (
            hab.deer_breeding
            if self.selected_habitat_kind == AnimalKind.DEER
            else hab.boar_breeding
        )
        cap = (
            hab.deer_cap
            if self.selected_habitat_kind == AnimalKind.DEER
            else hab.boar_cap
        )
        if not breed or cap <= 0:
            self.selected_habitat_kind = None
            self.selected_habitat_id = None

    def _expire_unharvested_crops(self, ended_season: Season) -> None:
        """Clear crops that missed their harvest window so the tile can be replanted.

        Ripe leftovers clear when their harvest season ends. Crops still immature at
        the end of their harvest season also clear (except newly sown plantings in a
        harvest/plant season, e.g. autumn wheat re-sow).
        """
        cleared = False
        for y in range(self.world.rows):
            for x in range(self.world.cols):
                cell = self.world.cells[y][x]
                if cell.feature not in (
                    FeatureType.CROP_HERB,
                    FeatureType.WILD_CROP,
                    FeatureType.HERB,
                ):
                    continue
                crop = CROP_BY_KEY.get(cell.crop_kind or "sage")
                if crop is None:
                    continue

                newly_sown_in_ended = (
                    cell.feature == FeatureType.CROP_HERB
                    and cell.growth_ticks > 0
                    and crop.plant_season == ended_season
                )
                # Clear only when a harvest window ends without collection.
                # Ripe crops outside the calendar window stay until workers pick
                # them (or the next harvest season ends).
                missed_harvest = (
                    ended_season in crop.harvest_seasons and not newly_sown_in_ended
                )
                if not missed_harvest:
                    continue

                cell.feature = FeatureType.NONE
                cell.growth_ticks = 0
                cell.crop_kind = None
                cell.deposit = 0
                cleared = True

        if cleared:
            self._wake_all_farm_workers()
            self._refresh_indicators()

    def _seed_chance(self, base: float) -> float:
        return min(1.0, base * seed_chance_multiplier(self.calendar_day))

    def _handle_toolbar_action(self, action: str) -> None:
        if action == "file_toggle":
            self.toolbar.file_menu_open = not self.toolbar.file_menu_open
            return
        if action.startswith("file_"):
            self.toolbar.file_menu_open = False
        if action == "file_save":
            self._pending_file_action = "save"
            self.file_dialog.open_save("savegame")
        elif action == "file_load":
            self._pending_file_action = "load"
            self.file_dialog.open_load()
        elif action == "file_reset":
            self.reset()
        elif action == "file_quit":
            self.running = False
        elif action == "build_off":
            self._set_place_kind(None)
        elif action.startswith("build_"):
            name = action[len("build_") :].upper()
            self._set_place_kind(BuildingKind[name])
        elif action == "task_clear":
            self._clear_selected_building_areas()
        elif action.startswith("mode_"):
            self._set_building_work_mode(WorkMode[action[len("mode_") :]])
        elif action.startswith("task_"):
            self._set_building_task(TaskType[action[len("task_") :]])
        elif action.startswith("speed_"):
            self._set_sim_speed(int(action[len("speed_") :]))

    def _select_building(self, building: Building) -> None:
        """Select a building and open its inspection popup (closes any previous)."""
        self.selected_building_id = building.id
        self.selected_villager_id = None
        self.selected_habitat_kind = None
        self.selected_habitat_id = None
        self.assign_workplace_mode = False
        if building.draw_task_type not in TASK_LABELS:
            building.draw_task_type = building.default_draw_task()
        if building.kind == BuildingKind.FIELD:
            self._open_field_plan(building)
            return
        self._open_building_inspect(building)

    def _field_plan_building(self) -> Building | None:
        bid = self.field_plan_dialog.building_id
        if bid is None:
            return None
        building = self.buildings.get(bid)
        if building is None or building.kind != BuildingKind.FIELD:
            return None
        return building

    def _inspect_building(self) -> Building | None:
        bid = self.building_inspect.building_id
        if bid is None:
            return None
        building = self.buildings.get(bid)
        if building is None or building.kind == BuildingKind.FIELD:
            return None
        return building

    def _open_field_plan(self, building: Building) -> None:
        self.building_inspect.close()
        self.villager_inspect.close()
        self.resource_inspect.close()
        self.selected_building_id = building.id
        self.field_plan_dialog.open_for(building, season=self.season)
        self._set_status(
            f"Plan Field #{building.id} ({building.plot_size_label()}). "
            f"Select season & crop, drag to plant."
        )

    def _open_building_inspect(self, building: Building) -> None:
        self.field_plan_dialog.close()
        self.villager_inspect.close()
        self.resource_inspect.close()
        self.selected_building_id = building.id
        screen_xy = self.camera.world_to_screen(building.x, building.y)
        self.building_inspect.open_for(building, screen_xy=screen_xy)
        if building.kind == BuildingKind.HOME:
            haulers = sum(1 for v in self.villagers if v.assigned_to_home)
            self._set_status(
                f"Selected Storehouse. {haulers} hauler(s). Assign villagers to haul resources."
            )
        elif building.kind == BuildingKind.WORKSTATION:
            hired_count = len(self.villagers)
            self._set_status(
                f"Selected Hiring hall. {hired_count}/{MAX_VILLAGERS} hired. Click Hire button."
            )
        elif building.kind == BuildingKind.FARM:
            self._set_status(
                f"Selected Farm. Workers manage nearby Fields "
                f"(within {FARM_FIELD_RADIUS}). "
                f"{WORK_MODE_LABELS[building.work_mode]}."
            )
        else:
            self._set_status(
                f"Selected {BUILDING_LABELS[building.kind]}. "
                f"{WORK_MODE_LABELS[building.work_mode]}. Drag to draw. Esc to hide."
            )

    def _apply_building_inspect_action(self) -> None:
        action = self.building_inspect.take_action()
        if action is None:
            return
        if action.startswith("select_worker:"):
            vid = int(action.split(":")[1])
            villager = self._get_villager(vid)
            if villager is not None:
                self._open_villager_inspect(villager)
            return
        if action.startswith("mode_"):
            self._set_building_work_mode(WorkMode[action[len("mode_") :]])
            return
        if action == "task_clear":
            self._clear_selected_building_areas()
            return
        if action == "assign_villager":
            self._assign_unassigned_to_selected_building()
            return
        if action == "unassign_villager":
            self._unassign_worker_from_selected_building()
            return
        if action == "hire_villager":
            self._hire_villager()
            return

    def _open_villager_inspect(self, villager: Villager) -> None:
        self.selected_villager_id = villager.id
        self.selected_building_id = None
        self.selected_habitat_kind = None
        self.selected_habitat_id = None
        self.assign_workplace_mode = False
        self.field_plan_dialog.close()
        self.building_inspect.close()
        self.resource_inspect.close()
        screen_xy = self.camera.world_to_screen(villager.x, villager.y)
        self.villager_inspect.open_for(villager, screen_xy=screen_xy)
        label = self._villager_assignment_label(villager)
        self._set_status(
            f"Selected villager {villager.id} ({label}). "
            f"Set priorities & ration in the popup."
        )

    def _apply_villager_inspect_action(self) -> None:
        action = self.villager_inspect.take_action()
        if action is None:
            return
        villager = self._get_villager(self.villager_inspect.villager_id or -1)
        if villager is None:
            return
        if action.startswith("ration_"):
            from entities import RationMode

            try:
                villager.ration_mode = RationMode[action[len("ration_") :]]
            except KeyError:
                return
            self._set_status(
                f"Villager {villager.id} ration: {RATION_LABELS[villager.ration_mode]}"
            )
            return
        if action.startswith("prio:"):
            parts = action.split(":")
            if len(parts) == 3:
                slot = int(parts[1])
                try:
                    prio = WorkPriority[parts[2]]
                except KeyError:
                    return
                while len(villager.priorities) < 3:
                    villager.priorities.append(WorkPriority.NONE)
                villager.priorities[slot] = prio
                self._set_status(
                    f"Villager {villager.id} priority {slot + 1}: {PRIORITY_LABELS[prio]}"
                )
            return
        if action == "assign_workplace":
            self.assign_workplace_mode = True
            self._set_status(
                f"Assign villager {villager.id}: click a building or storehouse."
            )
            return
        if action == "unassign":
            self._unassign_villager(villager)
            return

    def _unassign_villager(self, villager: Villager) -> None:
        villager.clear_assignment()
        villager.set_default_priorities()
        self._set_status(f"Unassigned villager {villager.id}.")

    def _field_crop_counts(self, building: Building) -> dict[str, int]:
        counts: dict[str, int] = {}
        left, top, right, bottom = building.plot_bounds()
        for y in range(top, bottom + 1):
            for x in range(left, right + 1):
                cell = self.world.get_cell(x, y)
                if cell is None or cell.feature != FeatureType.CROP_HERB:
                    continue
                kind = cell.crop_kind or "sage"
                counts[kind] = counts.get(kind, 0) + 1
        return counts

    def _map_resource_at(
        self, x: int, y: int
    ) -> tuple[str, int, str, str] | None:
        """Return (title, quantity, unit, detail) for a harvestable map resource."""
        cell = self.world.get_cell(x, y)
        if cell is None:
            return None
        if cell.meat_deposit > 0:
            return ("Meat", cell.meat_deposit, "meat", "Ground deposit")
        if cell.fish_deposit > 0:
            return ("Fish", cell.fish_deposit, "fish", "Shore catch")
        if cell.feature == FeatureType.TREE:
            from trees import resolve_tree

            tree = resolve_tree(cell.tree_species)
            return (
                tree.label,
                max(1, cell.deposit),
                tree.yield_key,
                f"{tree.yield_amount} {tree.yield_key}",
            )
        if cell.feature == FeatureType.ROCK:
            return ("Rock", max(1, cell.deposit), "rock", "")
        if cell.feature == FeatureType.BERRY_BUSH:
            qty = cell.deposit
            detail = "Regrowing" if qty <= 0 else ""
            return ("Berry bush", max(0, qty), "berries", detail)
        if cell.feature == FeatureType.MUSHROOM:
            return ("Mushroom", 1, "mushrooms", "")
        if cell.feature in (FeatureType.HERB, FeatureType.WILD_CROP):
            kind = cell.crop_kind or "sage"
            crop = CROP_BY_KEY.get(kind)
            label = crop.label if crop else kind
            return (f"Wild {label}", 1, crop.produce_key if crop else kind, "")
        if cell.feature == FeatureType.REED:
            return ("Reeds", 1, "reeds", "")
        if cell.feature == FeatureType.CROP_HERB:
            kind = cell.crop_kind or "sage"
            crop = CROP_BY_KEY.get(kind)
            label = crop.label if crop else kind
            if cell.growth_ticks > 0:
                return (label, 1, crop.produce_key if crop else kind, "Growing")
            return (label, 1, crop.produce_key if crop else kind, "Ready to harvest")
        if cell.feature == FeatureType.SAPLING:
            from trees import resolve_tree

            tree = resolve_tree(cell.tree_species)
            return (f"{tree.label} sapling", 1, f"{tree.key}_saplings", "Growing")
        return None

    def _apply_pending_field_plan(self) -> None:
        pending = self.field_plan_dialog.take_pending_plan()
        if pending is None:
            return
        bid = self.field_plan_dialog.building_id
        building = self.buildings.get(bid) if bid is not None else None
        if building is None or building.kind != BuildingKind.FIELD:
            return
        x0, y0, x1, y1, crop_kind = pending

        def _planted(cx: int, cy: int, kind: str) -> bool:
            cell = self.world.get_cell(cx, cy)
            return (
                cell is not None
                and cell.feature == FeatureType.CROP_HERB
                and (cell.crop_kind or "") == kind
            )

        plan = building.add_field_plan(
            x0, y0, x1, y1, crop_kind, cell_planted=_planted
        )
        if plan is None:
            self._set_status("Plan must be inside the field.")
            return
        crop = CROP_BY_KEY.get(plan.crop_kind, CROP_BY_KEY["sage"])
        kinds = sorted({p.crop_kind for p in building.plans})
        self._set_status(
            f"Plan: {crop.label}. Field schedule: {', '.join(kinds)}."
        )
        self._wake_all_farm_workers()

    def _finish_field_plan_dialog(self) -> None:
        result = self.field_plan_dialog.take_result()
        if result is None:
            return
        if result == "cleared":
            bid = self.field_plan_dialog.building_id
            building = self.buildings.get(bid) if bid is not None else None
            if building is not None and building.kind == BuildingKind.FIELD:
                building.plans.clear()
                self._set_status(f"Cleared plans on Field #{building.id}.")
                self._wake_all_farm_workers()
            return
        if result == "deleted":
            bid = self.selected_building_id
            if bid is not None:
                self._delete_field_building(bid)
            return

    def _wake_all_farm_workers(self) -> None:
        for building in self.buildings.values():
            if building.kind == BuildingKind.FARM:
                self._wake_building_workers(building.id)

    def _delete_field_building(self, building_id: int) -> None:
        building = self.buildings.get(building_id)
        if building is None or building.kind != BuildingKind.FIELD:
            return
        # Clear any legacy FIELD feature markers inside the plot.
        for x, y in building.plot_cells():
            cell = self.world.get_cell(x, y)
            if cell is not None and cell.feature == FeatureType.FIELD:
                cell.feature = FeatureType.NONE
        del self.buildings[building_id]
        if self.selected_building_id == building_id:
            self.selected_building_id = None
        if self.field_plan_dialog.building_id == building_id:
            self.field_plan_dialog.close()
        if self.building_inspect.building_id == building_id:
            self.building_inspect.close()
        self._set_status(f"Deleted Field #{building_id}.")
        self._wake_all_farm_workers()
        self._refresh_indicators()

    def _save_game(self) -> None:
        self._pending_file_action = "save"
        self.file_dialog.open_save("savegame")

    def _load_game(self) -> None:
        self._pending_file_action = "load"
        self.file_dialog.open_load()

    def _cycle_selected_building_task(self) -> None:
        if self.selected_building_id is None:
            self._set_status("Select a building first (click it).")
            return
        building = self.buildings.get(self.selected_building_id)
        if building is None:
            return
        mode = building.cycle_work_mode()
        self._wake_building_workers(building.id)
        self._set_status(
            f"{BUILDING_LABELS[building.kind]} behaviour: {WORK_MODE_LABELS[mode]}."
        )

    def _clear_selected_building_areas(self) -> None:
        if self.selected_building_id is None:
            self._set_status("Select a building to clear its areas.")
            return
        building = self.buildings.get(self.selected_building_id)
        if building is None:
            return
        if building.kind == BuildingKind.FARM:
            self._set_status("Farm has no task areas — Fields are separate buildings.")
            return
        if building.kind == BuildingKind.FIELD:
            building.plans.clear()
            self._set_status(f"Cleared plans on Field #{building.id}.")
            self._wake_all_farm_workers()
            return
        building.areas.clear()
        self._set_status(f"Cleared areas for {BUILDING_LABELS[building.kind]}.")
        self._wake_building_workers(building.id)

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
        # Prefer Field plot hits (any cell of the plot).
        for building in self.buildings.values():
            if building.kind == BuildingKind.FIELD and building.contains_plot(x, y):
                return building
        for building in self.buildings.values():
            if building.x == x and building.y == y:
                return building
        return None

    def _construction_at(self, x: int, y: int) -> ConstructionSite | None:
        for site in self.construction_sites.values():
            if site.x == x and site.y == y:
                return site
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
            building = self._building_at(x, y)
            if building is not None:
                self._select_building(building)
            return

        if cell.feature == FeatureType.HOME:
            # Allow deposit but also could select building
            self._deposit_home(self.player.inventory)
            return

        if cell.feature in (
            FeatureType.FORESTER,
            FeatureType.MASON,
            FeatureType.HUNTER,
            FeatureType.FORAGER,
            FeatureType.FISHER,
            FeatureType.FARM,
            FeatureType.FIELD,
        ):
            building = self._building_at(x, y)
            if building is not None:
                self._select_building(building)
            return

        # Collect meat / fish on this cell first if present.
        if cell.meat_deposit > 0:
            self._collect_meat(x, y, self.player.inventory, status=True)
            return
        if cell.fish_deposit > 0:
            self._collect_fish(x, y, self.player.inventory, status=True)
            return

        # Hunt adjacent animal (within 1 square, including this cell).
        prey = self._adjacent_animal(x, y)
        if prey is not None:
            self._player_hunt(prey)
            return

        # Fish adjacent (on water within 1).
        catch = self._adjacent_fish(x, y)
        if catch is not None:
            if not fishing_allowed(self.calendar_day):
                self._set_status("Water is frozen — no fishing in winter.")
                return
            self._player_fish(catch)
            return

        if cell.feature == FeatureType.CONSTRUCTION_SITE:
            site = self._construction_at(x, y)
            if site is None:
                self._set_status("Broken construction site.")
                return
            delivered = False
            while site.wood_needed > 0 and self.player.inventory.wood > 0:
                self.player.inventory.wood -= 1
                site.have_wood += 1
                delivered = True
            while site.rock_needed > 0 and self.player.inventory.rock > 0:
                self.player.inventory.rock -= 1
                site.have_rock += 1
                delivered = True
            if delivered:
                self._set_status(
                    f"Delivered to site. Now {site.have_wood}/{site.need_wood}w "
                    f"{site.have_rock}/{site.need_rock}r."
                )
                return
            pct = 0
            if site.materials_ready:
                pct = int(100 * site.build_progress / max(1, site.build_required_ticks()))
            self._set_status(
                f"{BUILDING_LABELS[site.kind]} site: "
                f"{site.have_wood}/{site.need_wood}w {site.have_rock}/{site.need_rock}r"
                + (f" · build {pct}%" if site.materials_ready else "")
            )
            return

        if cell.feature == FeatureType.MUSHROOM:
            self._collect_mushroom(x, y, self.player.inventory, status=True)
            return

        if cell.feature == FeatureType.BERRY_BUSH:
            self._collect_berries(x, y, self.player.inventory, status=True)
            return

        if cell.feature in (FeatureType.HERB, FeatureType.WILD_CROP, FeatureType.REED):
            self._collect_herb(x, y, self.player.inventory, status=True)
            return

        if cell.feature == FeatureType.CROP_HERB:
            if self.world.crop_herb_ready(x, y):
                self._harvest_farm_herb(x, y, self.player.inventory, status=True)
            else:
                self._set_status("Crop still growing.")
            return

        if cell.feature == FeatureType.TREE:
            self._chop_tree(x, y, self.player.inventory, status=True)
            return

        if cell.feature == FeatureType.ROCK:
            self._collect_rock(x, y, self.player.inventory, status=True)
            return

        if cell.feature == FeatureType.NONE and cell.terrain in PLANTABLE_LAND:
            if self.place_kind is not None:
                self._try_build(self.place_kind, x, y)
            else:
                self._plant_here(x, y, self.player.inventory, status=True)
            return

        if cell.feature == FeatureType.SAPLING:
            self._set_status("Sapling is already growing.")
            return

        if cell.terrain == TerrainType.WATER:
            if water_frozen(self.calendar_day):
                self._set_status("Ice — fishing resumes in spring.")
            else:
                self._set_status("Water — stand on shore and catch fish with Enter.")
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

    def _building_cost(self, kind: BuildingKind) -> tuple[int, int, TaskType]:
        if kind == BuildingKind.FORESTER:
            return FORESTER_COST_WOOD, FORESTER_COST_ROCK, TaskType.FULL_MANAGE
        if kind == BuildingKind.MASON:
            return MASON_COST_WOOD, MASON_COST_ROCK, TaskType.COLLECT_ROCKS
        if kind == BuildingKind.HUNTER:
            return HUNTER_COST_WOOD, HUNTER_COST_ROCK, TaskType.HUNT
        if kind == BuildingKind.FISHER:
            return FISHER_COST_WOOD, FISHER_COST_ROCK, TaskType.FISH
        if kind == BuildingKind.FARM:
            return FARM_COST_WOOD, FARM_COST_ROCK, TaskType.FARM_FIELD
        if kind == BuildingKind.FIELD:
            return FIELD_COST_WOOD, FIELD_COST_ROCK, TaskType.FARM_FIELD
        return FORAGER_COST_WOOD, FORAGER_COST_ROCK, TaskType.FULL_FORAGE

    def _place_field_site(
        self, start: tuple[int, int], end: tuple[int, int]
    ) -> bool:
        """Place a Field construction site sized to the dragged rectangle."""
        x0, y0 = min(start[0], end[0]), min(start[1], end[1])
        x1, y1 = max(start[0], end[0]), max(start[1], end[1])
        plot_w = x1 - x0 + 1
        plot_h = y1 - y0 + 1
        blocked = (
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
        )
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                cell = self.world.get_cell(x, y)
                if cell is None or cell.terrain not in PLANTABLE_LAND:
                    self._set_status("Field must be entirely on soil, grass, or meadow.")
                    return False
                if cell.feature in blocked:
                    self._set_status("Field overlaps a building or construction site.")
                    return False
        # Construction marker on top-left; clear natural cover there if needed.
        origin = self.world.get_cell(x0, y0)
        assert origin is not None
        if origin.feature != FeatureType.NONE:
            origin.feature = FeatureType.NONE
            origin.deposit = 0
            origin.growth_ticks = 0
            origin.crop_kind = None
        cost_w, cost_r, _ = self._building_cost(BuildingKind.FIELD)
        site = ConstructionSite(
            id=self.next_construction_id,
            x=x0,
            y=y0,
            kind=BuildingKind.FIELD,
            need_wood=cost_w,
            need_rock=cost_r,
            plot_w=plot_w,
            plot_h=plot_h,
        )
        # No map feature marker — the plot is shown as an outline while building.
        # (Top-left stays walkable grass/soil; natural cover already cleared above.)
        self.next_construction_id += 1
        self.construction_sites[site.id] = site
        self.world.apply_disturbance(x0, y0)
        self._refresh_indicators()
        self.place_kind = None
        self._set_status(
            f"Field plot {plot_w}×{plot_h} marked "
            f"(needs {cost_w}w {cost_r}r to finish). "
            f"Outline shows the plot; plough each tile before sowing."
        )
        return True

    def _place_construction_site(self, kind: BuildingKind, x: int, y: int) -> bool:
        if kind == BuildingKind.FIELD:
            return self._place_field_site((x, y), (x, y))
        cell = self.world.get_cell(x, y)
        if cell is None or cell.feature != FeatureType.NONE:
            self._set_status("Cannot place construction site here.")
            return False
        if cell.terrain not in PLANTABLE_LAND:
            self._set_status("Build on soil, grass, or meadow.")
            return False
        cost_w, cost_r, _ = self._building_cost(kind)
        site = ConstructionSite(
            id=self.next_construction_id,
            x=x,
            y=y,
            kind=kind,
            need_wood=cost_w,
            need_rock=cost_r,
        )
        self.next_construction_id += 1
        self.construction_sites[site.id] = site
        cell.feature = FeatureType.CONSTRUCTION_SITE
        self.world.apply_disturbance(x, y)
        self._refresh_indicators()
        self.place_kind = None
        self._set_status(
            f"Construction site: {BUILDING_LABELS[kind]} "
            f"(needs {cost_w}w {cost_r}r). Villagers will deliver & build."
        )
        return True

    def _complete_construction(self, site: ConstructionSite) -> None:
        cell = self.world.get_cell(site.x, site.y)
        if cell is None:
            return
        _, _, default_task = self._building_cost(site.kind)
        building = Building(
            id=self.next_building_id,
            kind=site.kind,
            x=site.x,
            y=site.y,
            capacity=BUILDING_STORAGE_CAPACITY,
            draw_task_type=default_task,
            work_mode=Building.work_mode_from_task(site.kind, default_task),
            plot_w=max(1, site.plot_w) if site.kind == BuildingKind.FIELD else 1,
            plot_h=max(1, site.plot_h) if site.kind == BuildingKind.FIELD else 1,
        )
        building.sync_draw_task_from_mode()
        self.next_building_id += 1
        self.buildings[building.id] = building
        if site.kind == BuildingKind.FIELD:
            # Field is a plot outline only — no building glyph on the map.
            if cell.feature == FeatureType.CONSTRUCTION_SITE:
                cell.feature = FeatureType.NONE
        else:
            cell.feature = FEATURE_FOR_BUILDING[site.kind]
        del self.construction_sites[site.id]
        for villager in self.villagers:
            if villager.construction_id == site.id:
                villager.construction_id = None
                villager.state = VillagerState.IDLE
        if site.kind == BuildingKind.FIELD:
            self._set_status(
                f"Finished Field #{building.id} ({building.plot_size_label()}). "
                f"Plough tiles to soil, then sow. Click the plot to plan crops."
            )
            self._wake_all_farm_workers()
        else:
            self._set_status(f"Finished {BUILDING_LABELS[site.kind]} #{building.id}.")

    def _try_build(self, kind: BuildingKind, x: int, y: int) -> None:
        # Legacy Enter/E path also places a construction site.
        self._place_construction_site(kind, x, y)

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
        villager.priorities = list(DEFAULT_PRIORITIES_UNASSIGNED)
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
        from trees import resolve_tree

        tree = resolve_tree(cell.tree_species)
        yield_key = tree.yield_key
        taken = self.world.harvest_wood(x, y, amount=1)
        if taken <= 0:
            if status:
                self._set_status("No wood left.")
            return False
        inventory.add_item(yield_key, taken)
        sapling_msg = ""
        if self._drop_rng.random() < self._seed_chance(SAPLING_DROP_CHANCE):
            from trees import sapling_item_key

            skey = sapling_item_key(tree.key)
            if inventory.can_add(1, key=skey):
                inventory.add_saplings(1, species=tree.key)
                sapling_msg = f" +1 {tree.label.lower()} sapling"
        self.world.apply_disturbance(x, y)
        self._refresh_indicators()
        if status:
            left = self.world.get_cell(x, y)
            remaining = left.deposit if left and left.feature == FeatureType.TREE else 0
            label = tree.label
            self._set_status(
                f"Collected {taken} {yield_key} from {label} ({remaining} left){sapling_msg}."
            )
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
        from trees import resolve_tree, species_from_sapling_key

        key = inventory.first_sapling_key()
        if key is None:
            if status:
                self._set_status("Need a sapling item to plant.")
            return False
        species = species_from_sapling_key(key)
        if not self.world.plant_sapling(x, y, species=species):
            if status:
                self._set_status("Cannot plant here.")
            return False
        inventory.consume_item(key, 1)
        self.world.apply_disturbance(x, y)
        self._refresh_indicators()
        if status:
            label = resolve_tree(species).label
            self._set_status(f"Planted {label} sapling ({inventory.saplings} left).")
        return True

    def _local_tree_species(self, x: int, y: int) -> str | None:
        """Prefer a nearby tree species when planting; else weighted random."""
        from trees import pick_tree_species

        for ny, nx in self.world.neighbourhood(x, y, radius=3):
            cell = self.world.get_cell(nx, ny)
            if cell is None:
                continue
            if cell.feature in (FeatureType.TREE, FeatureType.SAPLING) and cell.tree_species:
                return cell.tree_species
        return pick_tree_species(self._drop_rng)

    def _plant_here(self, x: int, y: int, inventory: Inventory, status: bool = False) -> bool:
        """Plant berry seed or sapling depending on inventory and terrain."""
        cell = self.world.get_cell(x, y)
        if cell is None:
            return False
        if cell.terrain == TerrainType.GRASS and inventory.berry_seeds > 0:
            return self._plant_berry_seed(x, y, inventory, status=status)
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
        if self._drop_rng.random() < self._seed_chance(BERRY_SEED_DROP_CHANCE) and inventory.can_add(1, key="berry_seeds"):
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
        crop_key = self.world.harvest_herb(x, y)
        if crop_key is None:
            if status:
                self._set_status("No wild plants here.")
            return False
        if crop_key == "reeds":
            inventory.add_item("reeds", 1)
            self.world.apply_disturbance(x, y)
            self._refresh_indicators()
            if status:
                self._set_status("Collected 1 reed.")
            return True
        crop = CROP_BY_KEY.get(crop_key, CROP_BY_KEY["sage"])
        inventory.add_item(crop.produce_key, 1)
        seed_msg = ""
        # Forage: flat 1/3 chance of a single seed.
        if self._drop_rng.random() < crop.wild_seed_chance and inventory.can_add(1, key=crop.seed_key):
            inventory.add_item(crop.seed_key, 1)
            seed_msg = f" +1 {crop.label.lower()} seed"
        self.world.apply_disturbance(x, y)
        self._refresh_indicators()
        if status:
            self._set_status(f"Collected 1 {crop.label.lower()}{seed_msg}.")
        return True

    def _harvest_farm_herb(
        self, x: int, y: int, inventory: Inventory, status: bool = False
    ) -> bool:
        if inventory.is_full:
            if status:
                self._set_status("Inventory is full.")
            return False
        crop_key = self.world.harvest_crop_herb(x, y)
        if crop_key is None:
            if status:
                self._set_status("Crop not ready.")
            return False
        crop = CROP_BY_KEY.get(crop_key, CROP_BY_KEY["sage"])
        inventory.add_item(crop.produce_key, 1)
        seed_msg = ""
        # Farm: always 1, 2, or 3 seeds (capped by seed carry space).
        amounts = crop.farm_seed_amounts or FARM_SEED_AMOUNTS
        want = self._drop_rng.choice(amounts)
        got = 0
        for _ in range(want):
            if not inventory.can_add(1, key=crop.seed_key):
                break
            inventory.add_item(crop.seed_key, 1)
            got += 1
        if got > 0:
            seed_msg = f" +{got} {crop.label.lower()} seed{'s' if got != 1 else ''}"
        self.world.apply_disturbance(x, y)
        self._refresh_indicators()
        if status:
            self._set_status(f"Harvested farm {crop.label.lower()}{seed_msg}.")
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
            from resources import amounts_from_obj, format_grouped_counts

            class _Bag:
                pass

            bag = _Bag()
            for k, v in items.items():
                setattr(bag, k, v)
            lines = format_grouped_counts(amounts_from_obj(bag), skip_zero=True)
            self._set_status("Deposited. " + " · ".join(lines) if lines else "Deposited.")
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
        result = self.wildlife.kill_animal(animal.id)
        if result is None:
            self._set_status("Animal got away.")
            return
        x, y, kind = result
        meat = BOAR_MEAT_YIELD if kind == AnimalKind.BOAR else DEER_MEAT_YIELD
        label = "boar" if kind == AnimalKind.BOAR else "deer"
        self.world.add_meat_deposit(x, y, meat)
        self.world.apply_disturbance(x, y)
        self._refresh_indicators()
        self._set_status(f"Hunted {label}. {meat} meat on ({x}, {y}).")

    def _collect_fish(self, x: int, y: int, inventory: Inventory, status: bool = False) -> bool:
        if inventory.is_full:
            if status:
                self._set_status("Inventory is full.")
            return False
        taken = self.world.harvest_fish(x, y, amount=1)
        if taken <= 0:
            if status:
                self._set_status("No fish here.")
            return False
        inventory.add_fish(taken)
        if status:
            left = self.world.get_cell(x, y)
            remaining = left.fish_deposit if left else 0
            self._set_status(f"Collected {taken} fish ({remaining} left).")
        return True

    def _adjacent_fish(self, x: int, y: int):
        best = None
        best_dist = 99
        for item in self.fish.fish:
            dist = max(abs(item.x - x), abs(item.y - y))
            if dist <= 1 and dist < best_dist:
                best = item
                best_dist = dist
        return best

    def _player_fish(self, item) -> None:
        pos = self.fish.kill_fish(item.id)
        if pos is None:
            self._set_status("Fish got away.")
            return
        self.world.add_fish_deposit(pos[0], pos[1], FISH_YIELD)
        self.world.apply_disturbance(pos[0], pos[1])
        self._refresh_indicators()
        self._set_status(f"Caught fish. {FISH_YIELD} fish left on shore.")

    # ------------------------------------------------------------------
    # Villager AI
    # ------------------------------------------------------------------
    def _update_villagers(self) -> None:
        for villager in self.villagers:
            if villager.move_cooldown > 0:
                villager.move_cooldown -= 1
            if villager.work_cooldown > 0:
                villager.work_cooldown -= 1

            villager.satiation = max(
                0.0, villager.satiation - VILLAGER_SATIATION_DECAY_PER_TICK
            )

            # Both timers blocking — no move or work this tick.
            if villager.move_cooldown > 0 and villager.work_cooldown > 0:
                if not (villager.needs_food() or villager.seeking_food):
                    continue

            if villager.needs_food() or villager.seeking_food:
                # Don't abandon deliveries / hauling / building to snack — cargo
                # would sit on the home tile and look like a stuck worker.
                if villager.state in (
                    VillagerState.DELIVERING,
                    VillagerState.HAULING,
                    VillagerState.BUILDING,
                ):
                    villager.seeking_food = True
                else:
                    can_eat = (
                        self._food_count(villager.inventory) > 0
                        or self._find_nearest_food_store(villager) is not None
                    )
                    if can_eat:
                        self._update_seek_food(villager)
                        continue
                    villager.seeking_food = False

            acted = False
            for priority in villager.priorities:
                if priority == WorkPriority.NONE:
                    continue
                if priority == WorkPriority.WORKPLACE:
                    if villager.building_id is not None and self._workplace_has_work(villager):
                        self._update_workplace_worker(villager)
                        acted = True
                        break
                elif priority == WorkPriority.BUILD:
                    if self._construction_has_work(villager):
                        self._update_builder(villager)
                        acted = True
                        break
                elif priority == WorkPriority.TRANSPORT:
                    if self._transport_has_work(villager):
                        self._update_hauler(villager)
                        acted = True
                        break
            if not acted:
                # Finish delivering carried goods home if any.
                if not villager.inventory.is_empty and WorkPriority.TRANSPORT in villager.priorities:
                    self._update_hauler(villager)
                elif villager.state not in (VillagerState.DELIVERING, VillagerState.HAULING, VillagerState.BUILDING):
                    villager.state = VillagerState.IDLE
                    villager.target = None

    def _satiation_speed_factor(self, villager: Villager) -> float:
        """1.0 when full, down to 0.4 when starving — scales move/work pace."""
        s = max(0.0, min(1.0, villager.satiation))
        return 0.4 + 0.6 * s

    def _villager_move_interval(self, villager: Villager) -> int:
        factor = self._satiation_speed_factor(villager)
        return max(8, int(round(VILLAGER_MOVE_INTERVAL / factor)))

    def _villager_work_interval(self, villager: Villager) -> int:
        factor = self._satiation_speed_factor(villager)
        return max(12, int(round(VILLAGER_WORK_INTERVAL / factor)))

    def _food_count(self, storage) -> int:
        return sum(getattr(storage, key, 0) for key in VILLAGER_FOOD_KEYS)

    def _food_store_at(self, pos: tuple[int, int]):
        if pos == self.world.home_pos:
            return self.home_storage
        for building in self.buildings.values():
            if (building.x, building.y) == pos and building.kind in (
                BuildingKind.FORAGER,
                BuildingKind.HUNTER,
                BuildingKind.FISHER,
                BuildingKind.FARM,
            ):
                return building
        return None

    def _find_nearest_food_store(self, villager: Villager) -> tuple[int, int] | None:
        options: list[tuple[int, int]] = []
        if self._food_count(self.home_storage) > 0:
            options.append(self.world.home_pos)
        for building in self.buildings.values():
            if building.kind not in (
                BuildingKind.FORAGER,
                BuildingKind.HUNTER,
                BuildingKind.FISHER,
                BuildingKind.FARM,
            ):
                continue
            if self._food_count(building) > 0:
                options.append((building.x, building.y))
        if not options:
            return None
        return min(
            options,
            key=lambda p: abs(p[0] - villager.x) + abs(p[1] - villager.y),
        )

    def _eat_random_from(
        self, storage, amount: int, villager: Villager | None = None
    ) -> int:
        """Consume up to `amount` random food units. Returns how many eaten."""
        eaten = 0
        for _ in range(amount):
            choices = [
                key for key in VILLAGER_FOOD_KEYS if getattr(storage, key, 0) > 0
            ]
            if not choices:
                break
            key = self._food_rng.choice(choices)
            setattr(storage, key, getattr(storage, key) - 1)
            if villager is not None:
                villager.last_food = key
            eaten += 1
        return eaten

    def _update_seek_food(self, villager: Villager) -> None:
        """Walk to nearest food store and eat according to ration mode."""
        villager.seeking_food = True
        amount = villager.ration_food_amount()

        # Eat from carried food first.
        if self._food_count(villager.inventory) > 0:
            eaten = self._eat_random_from(villager.inventory, amount, villager)
            if eaten > 0:
                villager.satiation = villager.ration_refill()
                villager.seeking_food = False
                villager.work_cooldown = self._villager_work_interval(villager)
                villager.state = VillagerState.WORKING
            return

        dest = self._find_nearest_food_store(villager)
        if dest is None:
            # Nowhere to eat — keep seeking flag while below threshold so we retry.
            villager.seeking_food = villager.needs_food()
            if villager.state not in (
                VillagerState.DELIVERING,
                VillagerState.HAULING,
                VillagerState.BUILDING,
            ):
                villager.state = VillagerState.IDLE
            return

        villager.state = VillagerState.WORKING
        if (villager.x, villager.y) == dest:
            if villager.work_cooldown > 0:
                return
            storage = self._food_store_at(dest)
            if storage is None:
                villager.seeking_food = villager.needs_food()
                return
            eaten = self._eat_random_from(storage, amount, villager)
            if eaten > 0:
                villager.satiation = villager.ration_refill()
                villager.seeking_food = False
            else:
                villager.seeking_food = villager.needs_food()
            villager.work_cooldown = self._villager_work_interval(villager)
            return
        self._step_villager_toward(villager, dest)

    def _workplace_has_work(self, villager: Villager) -> bool:
        building = self.buildings.get(villager.building_id) if villager.building_id else None
        if building is None:
            return False
        # Already committed — do not re-scan the map.
        if villager.state == VillagerState.DELIVERING:
            return True
        if villager.target is not None:
            return True
        if villager.hunt_animal_id is not None or villager.hunt_meat_pos is not None:
            return True
        if villager.fish_target_id is not None or villager.fish_catch_pos is not None:
            # Off-season: keep the catch sticky for later, but don't block other work.
            if fishing_allowed(self.calendar_day):
                return True
        # Only treat cargo as workplace work if this building can store it.
        if building.can_accept_from(villager.inventory):
            return True
        # Wrong-type cargo should be cleared via home delivery, not workplace idle.
        if not villager.inventory.is_empty and not building.can_accept_from(villager.inventory):
            return True
        if building.kind == BuildingKind.HUNTER:
            return (
                self._find_hunt_target(villager, building) is not None
                or self._find_meat_in_hunt_areas(building) is not None
            )
        if building.kind == BuildingKind.FISHER:
            if not fishing_allowed(self.calendar_day):
                return False
            return (
                self._find_fish_target(villager, building) is not None
                or self._find_fish_in_fish_areas(building) is not None
            )
        if building.kind == BuildingKind.FARM:
            return self._find_farm_work(villager, building) is not None
        target = self._find_work_in_building(villager, building)
        if target is not None:
            villager.target = target
            return True
        return False

    def _work_target_valid(
        self, villager: Villager, building: Building, pos: tuple[int, int]
    ) -> bool:
        """True if a sticky gather/plant target is still worth walking to."""
        x, y = pos
        cell = self.world.get_cell(x, y)
        if cell is None or not self.world.is_walkable(x, y):
            return False
        can_plant_sapling, can_plant_berry, can_plant_herb = self._can_plant_from(
            villager, building
        )
        mode = building.work_mode
        allow_plant = mode in (WorkMode.PLANT, WorkMode.BOTH) and building.allows_planting()
        if not allow_plant:
            can_plant_sapling = can_plant_berry = can_plant_herb = False
        if building.areas:
            tasks = {a.task_type for a in building.areas if a.contains(x, y)}
            if not tasks:
                return False
            return any(
                self._cell_matches_task(
                    cell,
                    task,
                    can_plant_sapling=can_plant_sapling,
                    can_plant_berry=can_plant_berry,
                    can_plant_herb=can_plant_herb,
                )
                for task in tasks
            )
        task = building.draw_task_type
        if task not in TASK_LABELS:
            task = building.default_draw_task()
        if building.kind == BuildingKind.FORESTER and allow_plant and can_plant_sapling:
            if self._cell_matches_manage_plant(cell, can_plant_sapling=True):
                return True
            task = TaskType.CHOP_TREES
        if building.kind == BuildingKind.FORAGER:
            task = TaskType.FULL_FORAGE
        if building.kind == BuildingKind.MASON:
            task = TaskType.COLLECT_ROCKS
        return self._cell_matches_task(
            cell,
            task,
            can_plant_sapling=False,
            can_plant_berry=False,
            can_plant_herb=False,
        )

    def _delivery_destination(
        self, villager: Villager, building: Building
    ) -> tuple[int, int]:
        """Workplace if it can take cargo; otherwise home for the rest."""
        if building.can_accept_from(villager.inventory):
            return building.x, building.y
        return self.world.home_pos

    def _update_workplace_delivery(self, villager: Villager, building: Building) -> bool:
        """Handle DELIVERING for workplace workers. Returns True if delivery consumed the turn."""
        if villager.state != VillagerState.DELIVERING:
            return False
        # Reserved plant stock alone is not delivery cargo.
        # Farm stores crop seeds at the farmhouse (do not reserve them in-hand).
        keep = building.work_mode in (WorkMode.PLANT, WorkMode.BOTH)
        if building.kind == BuildingKind.FARM:
            keep = False
        if keep and building.holding_only_plantables(villager.inventory):
            villager.state = VillagerState.WORKING
            villager.target = None
            return False

        dest = self._delivery_destination(villager, building)
        villager.target = dest
        if (villager.x, villager.y) == dest:
            if dest == self.world.home_pos:
                self._deposit_home(villager.inventory, status=False)
            else:
                building.deposit_from_inventory(
                    villager.inventory, keep_plantables=keep
                )
                # Only plantables left (reserved) → resume planting/collecting.
                if keep and building.holding_only_plantables(villager.inventory):
                    villager.state = VillagerState.WORKING
                    villager.target = None
                    return True
                # Leftover wrong-type goods → send home next.
                if not villager.inventory.is_empty and not building.can_accept_from(
                    villager.inventory
                ):
                    villager.target = self.world.home_pos
                    return True
            if villager.inventory.is_empty or (
                dest != self.world.home_pos and building.space_left == 0
            ):
                villager.state = VillagerState.WORKING
                villager.target = None
            # Still holding only reserved plantables after a full storehouse.
            elif keep and building.holding_only_plantables(villager.inventory):
                villager.state = VillagerState.WORKING
                villager.target = None
            return True
        self._step_villager_toward(villager, dest)
        return True

    def _begin_workplace_delivery(self, villager: Villager, building: Building) -> None:
        if villager.inventory.is_empty:
            return
        if building.kind == BuildingKind.FARM:
            has_farm_cargo = (
                building.has_gather_cargo(villager.inventory)
                or any(getattr(villager.inventory, k, 0) > 0 for k in SEED_KEYS)
            )
            if not has_farm_cargo and building.can_accept_from(villager.inventory):
                return
            # has farm cargo, or wrong-type cargo that must go home
        elif building.work_mode in (WorkMode.PLANT, WorkMode.BOTH):
            if not building.has_gather_cargo(villager.inventory) and building.can_accept_from(
                villager.inventory
            ):
                return
        villager.state = VillagerState.DELIVERING
        villager.target = self._delivery_destination(villager, building)

    def _should_deliver_workplace(
        self, villager: Villager, building: Building
    ) -> bool:
        """True when carrying gather goods that should go to storage."""
        if villager.inventory.is_empty:
            return False
        if building.kind == BuildingKind.FARM:
            has_farm_cargo = (
                building.has_gather_cargo(villager.inventory)
                or any(getattr(villager.inventory, k, 0) > 0 for k in SEED_KEYS)
            )
            if not has_farm_cargo:
                # Wood/rock/etc. — clear via home; do not idle with a full wrong pack.
                return True
            return villager.inventory.is_full
        if building.work_mode in (WorkMode.PLANT, WorkMode.BOTH):
            if not building.has_gather_cargo(villager.inventory):
                return not building.can_accept_from(villager.inventory)
            # Deliver when pack is full, or when gather goods present and no work left.
            return villager.inventory.is_full
        return villager.inventory.is_full

    def _transport_has_work(self, villager: Villager) -> bool:
        if not villager.inventory.is_empty:
            return True
        return self._find_haul_source(villager) is not None

    def _construction_has_work(self, villager: Villager) -> bool:
        if not self.construction_sites:
            if villager.construction_id is not None:
                villager.construction_id = None
            return False

        # Carrying wood/rock only counts if some site still needs it.
        # Otherwise release the claim so transport can clear leftover cargo
        # (e.g. extra wood after a site's wood quota is already full).
        if villager.inventory.wood > 0 or villager.inventory.rock > 0:
            if self._find_site_needing_materials(villager) is not None:
                return True
            if villager.construction_id is not None:
                villager.construction_id = None
            return False

        if villager.construction_id is not None:
            site = self.construction_sites.get(villager.construction_id)
            if site is None or site.is_complete:
                villager.construction_id = None
            elif site.materials_ready:
                return True
            elif (site.wood_needed > 0 and self._material_available("wood")) or (
                site.rock_needed > 0 and self._material_available("rock")
            ):
                return True
            else:
                # Assigned to a half-built site with nothing left to fetch.
                villager.construction_id = None

        for site in self.construction_sites.values():
            if not site.materials_ready:
                if site.wood_needed > 0 and self._material_available("wood"):
                    return True
                if site.rock_needed > 0 and self._material_available("rock"):
                    return True
            elif not site.is_complete:
                return True
        return False

    def _material_available(self, key: str) -> bool:
        if getattr(self.home_storage, key, 0) > 0:
            return True
        for building in self.buildings.values():
            if getattr(building, key, 0) > 0:
                return True
        return False

    def _update_builder(self, villager: Villager) -> None:
        site = None
        if villager.construction_id is not None:
            site = self.construction_sites.get(villager.construction_id)
            if site is None or site.is_complete:
                villager.construction_id = None
                site = None

        carrying = villager.inventory.wood > 0 or villager.inventory.rock > 0

        # Deliver carried wood/rock to a needing site.
        if carrying:
            useful = self._find_site_needing_materials(villager)
            if useful is None:
                # Leftover mats no site needs — release claim so transport can haul home.
                villager.construction_id = None
                villager.state = VillagerState.IDLE
                return
            # Prefer current site only if it can still take what we carry.
            if site is None or not (
                (site.wood_needed > 0 and villager.inventory.wood > 0)
                or (site.rock_needed > 0 and villager.inventory.rock > 0)
            ):
                site = useful
                villager.construction_id = site.id
            if (villager.x, villager.y) == (site.x, site.y):
                if villager.work_cooldown == 0:
                    self._deposit_materials_at_site(villager, site)
                    villager.work_cooldown = self._villager_work_interval(villager)
                    if site.is_complete:
                        self._complete_construction(site)
                        villager.construction_id = None
                        villager.state = VillagerState.IDLE
                        return
                # After a partial drop, keep going (fetch remainder / other site)
                # instead of parking on the scaffold with useless leftover cargo.
                if villager.inventory.wood > 0 or villager.inventory.rock > 0:
                    if (site.wood_needed > 0 and villager.inventory.wood > 0) or (
                        site.rock_needed > 0 and villager.inventory.rock > 0
                    ):
                        return  # still depositing next tick (cooldown)
                    other = self._find_site_needing_materials(villager)
                    if other is not None:
                        villager.construction_id = other.id
                        self._step_villager_toward(villager, (other.x, other.y))
                        villager.state = VillagerState.DELIVERING
                        return
                    villager.construction_id = None
                    villager.state = VillagerState.IDLE
                    return
                # Empty hands — fall through to build or fetch more.
            else:
                self._step_villager_toward(villager, (site.x, site.y))
                villager.state = VillagerState.DELIVERING
                return

        # Pick / keep a site.
        if site is None:
            site = self._find_best_construction_site(villager)
            if site is None:
                villager.construction_id = None
                villager.state = VillagerState.IDLE
                return
            villager.construction_id = site.id

        # Build when materials ready.
        if site.materials_ready:
            if (villager.x, villager.y) != (site.x, site.y):
                self._step_villager_toward(villager, (site.x, site.y))
                villager.state = VillagerState.BUILDING
                return
            villager.state = VillagerState.BUILDING
            site.build_progress += 1
            if site.is_complete:
                self._complete_construction(site)
                villager.construction_id = None
                villager.state = VillagerState.IDLE
            return

        # Fetch materials from storage.
        need_wood = site.wood_needed
        need_rock = site.rock_needed
        source = self._find_material_source(villager, need_wood > 0, need_rock > 0)
        if source is None:
            villager.construction_id = None
            villager.state = VillagerState.IDLE
            return
        sx, sy, _kind = source
        if (villager.x, villager.y) != (sx, sy):
            self._step_villager_toward(villager, (sx, sy))
            villager.state = VillagerState.HAULING
            return
        if villager.work_cooldown == 0:
            self._withdraw_build_materials(villager, site, source)
            villager.work_cooldown = self._villager_work_interval(villager)
            villager.state = VillagerState.HAULING
            # Nothing withdrawn (empty stock race) — drop claim next tick via has_work.
            if villager.inventory.wood <= 0 and villager.inventory.rock <= 0:
                villager.construction_id = None
                villager.state = VillagerState.IDLE

    def _find_site_needing_materials(self, villager: Villager) -> ConstructionSite | None:
        candidates = [
            s
            for s in self.construction_sites.values()
            if (s.wood_needed > 0 and villager.inventory.wood > 0)
            or (s.rock_needed > 0 and villager.inventory.rock > 0)
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda s: abs(s.x - villager.x) + abs(s.y - villager.y),
        )

    def _find_best_construction_site(self, villager: Villager) -> ConstructionSite | None:
        ready = [s for s in self.construction_sites.values() if s.materials_ready and not s.is_complete]
        if ready:
            return min(ready, key=lambda s: abs(s.x - villager.x) + abs(s.y - villager.y))
        needing = [
            s
            for s in self.construction_sites.values()
            if not s.materials_ready
            and (
                (s.wood_needed > 0 and self._material_available("wood"))
                or (s.rock_needed > 0 and self._material_available("rock"))
            )
        ]
        if not needing:
            return None
        return min(needing, key=lambda s: abs(s.x - villager.x) + abs(s.y - villager.y))

    def _find_material_source(
        self, villager: Villager, want_wood: bool, want_rock: bool
    ) -> tuple[int, int, str] | None:
        """Return (x, y, 'home'|'bID') for nearest wood/rock stock."""
        options: list[tuple[int, int, str, int]] = []
        hx, hy = self.world.home_pos
        if (want_wood and self.home_storage.wood > 0) or (want_rock and self.home_storage.rock > 0):
            options.append((hx, hy, "home", abs(hx - villager.x) + abs(hy - villager.y)))
        for building in self.buildings.values():
            if (want_wood and building.wood > 0) or (want_rock and building.rock > 0):
                options.append(
                    (
                        building.x,
                        building.y,
                        f"b{building.id}",
                        abs(building.x - villager.x) + abs(building.y - villager.y),
                    )
                )
        if not options:
            return None
        options.sort(key=lambda o: o[3])
        x, y, kind, _ = options[0]
        return x, y, kind

    def _withdraw_build_materials(
        self, villager: Villager, site: ConstructionSite, source: tuple[int, int, str]
    ) -> None:
        _, _, kind = source
        take_wood = min(site.wood_needed, villager.inventory.capacity - villager.inventory.cargo_total)
        take_rock = min(site.rock_needed, villager.inventory.capacity - villager.inventory.cargo_total)

        def pull(storage, key: str, amount: int) -> int:
            got = 0
            while got < amount and getattr(storage, key) > 0 and villager.inventory.can_add(1, key=key):
                setattr(storage, key, getattr(storage, key) - 1)
                setattr(villager.inventory, key, getattr(villager.inventory, key) + 1)
                got += 1
            return got

        if kind == "home":
            if site.wood_needed > 0:
                pull(self.home_storage, "wood", take_wood)
            if site.rock_needed > 0:
                pull(
                    self.home_storage,
                    "rock",
                    min(take_rock, villager.inventory.capacity - villager.inventory.cargo_total),
                )
        elif kind.startswith("b"):
            bid = int(kind[1:])
            building = self.buildings.get(bid)
            if building is None:
                return
            if site.wood_needed > 0:
                pull(building, "wood", take_wood)
            if site.rock_needed > 0:
                pull(
                    building,
                    "rock",
                    min(take_rock, villager.inventory.capacity - villager.inventory.cargo_total),
                )
    def _deposit_materials_at_site(self, villager: Villager, site: ConstructionSite) -> None:
        while site.wood_needed > 0 and villager.inventory.wood > 0:
            villager.inventory.wood -= 1
            site.have_wood += 1
        while site.rock_needed > 0 and villager.inventory.rock > 0:
            villager.inventory.rock -= 1
            site.have_rock += 1

    def _update_workplace_worker(self, villager: Villager) -> None:
        building = self.buildings.get(villager.building_id) if villager.building_id else None
        if building is None:
            villager.clear_assignment()
            return

        if building.kind == BuildingKind.HUNTER:
            self._update_hunter(villager, building)
            return
        if building.kind == BuildingKind.FISHER:
            self._update_fisher(villager, building)
            return
        if building.kind == BuildingKind.FARM:
            self._update_farmer(villager, building)
            return

        # Full gather cargo → deliver to workplace or home.
        if (
            self._should_deliver_workplace(villager, building)
            and villager.state != VillagerState.DELIVERING
        ):
            villager.target = None
            self._begin_workplace_delivery(villager, building)

        if self._update_workplace_delivery(villager, building):
            return

        # Collect plant stock from workplace / home before planting.
        if self._update_plant_stock_withdraw(villager, building):
            return

        # Keep sticky target if still valid (avoids full-map scan every tick).
        if villager.target is not None and not self._work_target_valid(
            villager, building, villager.target
        ):
            villager.target = None
            villager._path_cache = None  # type: ignore[attr-defined]
            villager._path_goal = None  # type: ignore[attr-defined]

        target = villager.target
        if target is None:
            # Partial gather load with nowhere left to work → deliver acceptables.
            if building.has_gather_cargo(villager.inventory):
                if self._find_work_in_building(villager, building) is None:
                    self._begin_workplace_delivery(villager, building)
                    self._update_workplace_delivery(villager, building)
                    return

            target = self._find_work_in_building(villager, building)
            if target is None:
                if building.has_gather_cargo(villager.inventory):
                    self._begin_workplace_delivery(villager, building)
                    self._update_workplace_delivery(villager, building)
                else:
                    villager.state = VillagerState.IDLE
                    villager.target = None
                return
            villager.target = target

        villager.state = VillagerState.WORKING
        if villager.inventory.is_full and building.has_gather_cargo(villager.inventory):
            return

        if (villager.x, villager.y) == target:
            if villager.work_cooldown > 0:
                return
            self._villager_perform(villager, building, target)
            villager.work_cooldown = self._villager_work_interval(villager)
            # Resource may be gone — refresh next tick.
            if not self._work_target_valid(villager, building, target):
                villager.target = None
                villager._path_cache = None  # type: ignore[attr-defined]
                villager._path_goal = None  # type: ignore[attr-defined]
        else:
            if villager.move_cooldown > 0:
                return
            self._step_villager_toward(villager, target)

    def _update_farmer(self, villager: Villager, building: Building) -> None:
        """Plough, sow, and harvest according to each field plan's seasonal calendar."""
        if (
            self._should_deliver_workplace(villager, building)
            and villager.state != VillagerState.DELIVERING
        ):
            self._begin_workplace_delivery(villager, building)

        if self._update_workplace_delivery(villager, building):
            return

        if not self._fields_near_farm(building):
            if building.has_gather_cargo(villager.inventory):
                self._begin_workplace_delivery(villager, building)
                self._update_workplace_delivery(villager, building)
            else:
                villager.state = VillagerState.IDLE
                villager.target = None
            return

        # Harvest / plough before seed runs — never park at home for seeds while
        # field work is available (sowing can pull seeds from home remotely).
        harvest_first = self._find_farm_harvest(villager, building)
        plough_or_sow = None if harvest_first is not None else self._find_farm_plant_work(
            villager, building
        )
        if (
            harvest_first is None
            and plough_or_sow is None
            and self._update_plant_stock_withdraw(villager, building)
        ):
            return

        if building.has_gather_cargo(villager.inventory):
            if self._find_farm_work(villager, building) is None:
                self._begin_workplace_delivery(villager, building)
                self._update_workplace_delivery(villager, building)
                return

        target = harvest_first or plough_or_sow or self._find_farm_work(villager, building)
        if target is None:
            if (
                building.has_gather_cargo(villager.inventory)
                or (
                    not villager.inventory.is_empty
                    and not building.can_accept_from(villager.inventory)
                )
            ):
                self._begin_workplace_delivery(villager, building)
                self._update_workplace_delivery(villager, building)
            else:
                villager.state = VillagerState.IDLE
                villager.target = None
            return

        villager.state = VillagerState.WORKING
        villager.target = None
        if villager.inventory.is_full and building.has_gather_cargo(villager.inventory):
            self._begin_workplace_delivery(villager, building)
            self._update_workplace_delivery(villager, building)
            return

        if (villager.x, villager.y) == target:
            if villager.work_cooldown == 0:
                self._villager_perform_farm(villager, building, target)
                villager.work_cooldown = self._villager_work_interval(villager)
        else:
            self._step_villager_toward(villager, target)

    def _find_farm_harvest(
        self, villager: Villager, building: Building
    ) -> tuple[int, int] | None:
        """Closest ripe crop on a nearby field (ignores calendar phase)."""
        mode = building.work_mode
        if mode not in (WorkMode.COLLECT, WorkMode.BOTH):
            return None
        if villager.inventory.is_full:
            return None
        harvest: list[tuple[int, int]] = []
        for field_b in self._fields_near_farm(building):
            for x, y in field_b.plot_cells():
                if not self.world.is_walkable(x, y):
                    continue
                if self.world.crop_herb_ready(x, y):
                    harvest.append((x, y))
        return self._closest_of((villager.x, villager.y), harvest)

    def _find_farm_plant_work(
        self, villager: Villager, building: Building
    ) -> tuple[int, int] | None:
        """Closest plough or sow tile (no harvest)."""
        mode = building.work_mode
        if mode not in (WorkMode.PLANT, WorkMode.BOTH):
            return None
        plough: list[tuple[int, int]] = []
        sow: list[tuple[int, int]] = []
        season = self.season
        for field_b in self._fields_near_farm(building):
            for plan in field_b.plans:
                crop = CROP_BY_KEY.get(plan.crop_kind, CROP_BY_KEY["sage"])
                phase = phase_for_crop(crop, season)
                if not phase_allows_plough_plant(phase):
                    continue
                seed_key = crop.seed_key
                can_sow = (
                    getattr(villager.inventory, seed_key, 0) > 0
                    or self._plant_stock_at(building, seed_key) > 0
                    or getattr(self.home_storage, seed_key, 0) > 0
                )
                for x, y in plan.cells():
                    if not self.world.is_walkable(x, y):
                        continue
                    cell = self.world.get_cell(x, y)
                    if cell is None or cell.feature == FeatureType.CROP_HERB:
                        continue
                    if cell.terrain == TerrainType.SOIL and cell.feature == FeatureType.NONE:
                        if can_sow and (
                            getattr(villager.inventory, seed_key, 0) > 0
                            or villager.inventory.can_add(1, key=seed_key)
                        ):
                            sow.append((x, y))
                        continue
                    if cell.terrain not in (TerrainType.WATER, TerrainType.ROCK):
                        if cell.feature not in (
                            FeatureType.HOME,
                            FeatureType.WORKSTATION,
                            FeatureType.FORESTER,
                            FeatureType.MASON,
                            FeatureType.HUNTER,
                            FeatureType.FORAGER,
                            FeatureType.FISHER,
                            FeatureType.FARM,
                            FeatureType.CONSTRUCTION_SITE,
                        ):
                            plough.append((x, y))
        origin = (villager.x, villager.y)
        return self._closest_of(origin, plough) or self._closest_of(origin, sow)

    def _find_farm_work(
        self, villager: Villager, building: Building
    ) -> tuple[int, int] | None:
        """Priority: harvest → plough → sow on nearby Field buildings' plans."""
        found = self._find_farm_harvest(villager, building)
        if found is not None:
            return found
        return self._find_farm_plant_work(villager, building)

    def _fields_near_farm(self, farm: Building) -> list[Building]:
        """Field buildings whose plot is within Chebyshev radius of the farm."""
        nearby: list[Building] = []
        for building in self.buildings.values():
            if building.kind != BuildingKind.FIELD:
                continue
            left, top, right, bottom = building.plot_bounds()
            cx = min(max(farm.x, left), right)
            cy = min(max(farm.y, top), bottom)
            if max(abs(cx - farm.x), abs(cy - farm.y)) <= FARM_FIELD_RADIUS:
                nearby.append(building)
        return nearby

    def _field_building_at(self, x: int, y: int) -> Building | None:
        for building in self.buildings.values():
            if building.kind == BuildingKind.FIELD and building.contains_plot(x, y):
                return building
        return None

    def _field_buildings(self) -> list[Building]:
        return [b for b in self.buildings.values() if b.kind == BuildingKind.FIELD]

    def _plan_at_cell(
        self, building: Building, x: int, y: int
    ) -> CropPlan | None:
        # Farm workers: plan lives on the Field covering this cell.
        field_b: Building | None
        if building.kind == BuildingKind.FARM:
            field_b = self._field_building_at(x, y)
        elif building.kind == BuildingKind.FIELD:
            field_b = building
        else:
            hit = building.plan_at_cell(x, y)
            return hit[1] if hit else None
        if field_b is None:
            return None
        # Prefer a plan that wants planting this season (harvest crop may still be present).
        plant_plan: CropPlan | None = None
        any_plan: CropPlan | None = None
        for plan in field_b.plans:
            if not plan.contains(x, y):
                continue
            any_plan = plan
            crop = CROP_BY_KEY.get(plan.crop_kind, CROP_BY_KEY["sage"])
            if phase_allows_plough_plant(phase_for_crop(crop, self.season)):
                plant_plan = plan
        return plant_plan or any_plan

    def _villager_perform_farm(
        self, villager: Villager, building: Building, pos: tuple[int, int]
    ) -> None:
        x, y = pos
        inv = villager.inventory
        cell = self.world.get_cell(x, y)
        if cell is None:
            return
        mode = building.work_mode
        allow_harvest = mode in (WorkMode.COLLECT, WorkMode.BOTH)
        allow_plant = mode in (WorkMode.PLANT, WorkMode.BOTH)

        # Harvest uses the crop actually on the tile (ripe = harvestable any season).
        if self.world.crop_herb_ready(x, y):
            if not allow_harvest:
                return
            crop = CROP_BY_KEY.get(cell.crop_kind or "sage", CROP_BY_KEY["sage"])
            phase = phase_for_crop(crop, self.season)
            self._harvest_farm_herb(x, y, inv, status=False)
            if phase == SeasonPhase.HARVEST_PLOUGH_PLANT and allow_plant:
                self.world.plough_tile(x, y)
                self.world.apply_disturbance(x, y)
                self._refresh_indicators()
            return

        if not allow_plant:
            return
        if cell.feature == FeatureType.CROP_HERB:
            return
        plan = self._plan_at_cell(building, x, y)
        if plan is None:
            return
        crop = CROP_BY_KEY.get(plan.crop_kind, CROP_BY_KEY["sage"])
        phase = phase_for_crop(crop, self.season)
        if not phase_allows_plough_plant(phase):
            return
        if cell.terrain == TerrainType.SOIL and cell.feature == FeatureType.NONE:
            seed_key = crop.seed_key
            if getattr(inv, seed_key, 0) <= 0:
                if not building.give_item_to(inv, seed_key):
                    self.home_storage.withdraw_keys_to(inv, (seed_key,))
            if getattr(inv, seed_key, 0) > 0 and self.world.sow_crop(
                x, y, crop.key, growth_ticks_for(crop, TICKS_PER_DAY)
            ):
                setattr(inv, seed_key, getattr(inv, seed_key) - 1)
                self.world.apply_disturbance(x, y)
                self._refresh_indicators()
            return
        self.world.plough_tile(x, y)
        self.world.apply_disturbance(x, y)
        self._refresh_indicators()

    def _update_hunter(self, villager: Villager, building: Building) -> None:
        """Hunt in areas, or nearest animal if no area is drawn."""
        if villager.inventory.is_full and villager.state != VillagerState.DELIVERING:
            villager.hunt_animal_id = None
            self._begin_workplace_delivery(villager, building)

        if self._update_workplace_delivery(villager, building):
            return

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
            villager.state = VillagerState.WORKING
            if (villager.x, villager.y) == meat_pos:
                if villager.work_cooldown == 0:
                    self._collect_meat(*meat_pos, villager.inventory, status=False)
                    villager.work_cooldown = self._villager_work_interval(villager)
                    cell = self.world.get_cell(*meat_pos)
                    if cell is None or cell.meat_deposit <= 0:
                        villager.hunt_meat_pos = None
                return
            if not self.world.is_walkable(*meat_pos):
                villager.hunt_meat_pos = None
                self._clear_villager_path(villager)
                return
            if not self._step_villager_toward(villager, meat_pos):
                # Unreachable pile — drop sticky target so hunting can continue.
                villager.hunt_meat_pos = None
                self._clear_villager_path(villager)
            return

        if villager.inventory.is_full:
            return

        animal = self._resolve_hunt_animal(villager, building)
        if animal is None:
            if not villager.inventory.is_empty:
                self._begin_workplace_delivery(villager, building)
                self._update_workplace_delivery(villager, building)
            else:
                villager.state = VillagerState.IDLE
            return

        villager.state = VillagerState.WORKING
        dist = max(abs(animal.x - villager.x), abs(animal.y - villager.y))
        if dist <= 1:
            if villager.work_cooldown == 0:
                result = self.wildlife.kill_animal(animal.id)
                villager.hunt_animal_id = None
                if result is not None:
                    x, y, kind = result
                    meat = BOAR_MEAT_YIELD if kind == AnimalKind.BOAR else DEER_MEAT_YIELD
                    self.world.add_meat_deposit(x, y, meat)
                    self.world.apply_disturbance(x, y)
                    self._refresh_indicators()
                    villager.hunt_meat_pos = (x, y)
                villager.work_cooldown = self._villager_work_interval(villager)
            return

        approach = (animal.x, animal.y)
        if not self.world.is_walkable(*approach):
            for ny, nx in self.world.neighbourhood(animal.x, animal.y, radius=1):
                if self.world.is_walkable(nx, ny):
                    approach = (nx, ny)
                    break
        self._step_villager_toward(villager, approach)

    def _find_hunt_target(self, villager: Villager, building: Building):
        animals = []
        if building.areas:
            for area in building.areas:
                if area.task_type != TaskType.HUNT:
                    continue
                animals.extend(self.wildlife.animals_in_area(area.contains))
            ox, oy = villager.x, villager.y
        else:
            animals = list(self.wildlife.animals)
            ox, oy = building.x, building.y
        if not animals:
            return None
        return min(animals, key=lambda a: abs(a.x - ox) + abs(a.y - oy))

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
        if building.areas:
            for area in building.areas:
                if area.task_type != TaskType.HUNT:
                    continue
                for x, y in area.cells():
                    cell = self.world.get_cell(x, y)
                    if cell is not None and cell.meat_deposit > 0:
                        return (x, y)
            return None
        best: tuple[int, int] | None = None
        best_d = 10**9
        for y in range(self.world.rows):
            for x in range(self.world.cols):
                cell = self.world.cells[y][x]
                if cell.meat_deposit <= 0:
                    continue
                d = abs(x - building.x) + abs(y - building.y)
                if d < best_d:
                    best_d = d
                    best = (x, y)
        return best

    def _update_fisher(self, villager: Villager, building: Building) -> None:
        """Fish in areas, or nearest fish if no area is drawn."""
        if not fishing_allowed(self.calendar_day):
            if not villager.inventory.is_empty:
                self._begin_workplace_delivery(villager, building)
                self._update_workplace_delivery(villager, building)
            else:
                villager.state = VillagerState.IDLE
                villager.fish_target_id = None
            return

        if villager.inventory.is_full and villager.state != VillagerState.DELIVERING:
            villager.fish_target_id = None
            self._begin_workplace_delivery(villager, building)

        if self._update_workplace_delivery(villager, building):
            return

        catch_pos = villager.fish_catch_pos
        if catch_pos is not None:
            cell = self.world.get_cell(*catch_pos)
            if cell is None or cell.fish_deposit <= 0:
                villager.fish_catch_pos = None
                catch_pos = None
        if catch_pos is None:
            catch_pos = self._find_fish_in_fish_areas(building)
            if catch_pos is not None:
                villager.fish_catch_pos = catch_pos

        if catch_pos is not None and not villager.inventory.is_full:
            villager.state = VillagerState.WORKING
            if (villager.x, villager.y) == catch_pos:
                if villager.work_cooldown == 0:
                    self._collect_fish(*catch_pos, villager.inventory, status=False)
                    villager.work_cooldown = self._villager_work_interval(villager)
                    cell = self.world.get_cell(*catch_pos)
                    if cell is None or cell.fish_deposit <= 0:
                        villager.fish_catch_pos = None
                return
            if not self.world.is_walkable(*catch_pos):
                recovered = self._recover_fish_catch(villager, catch_pos)
                villager.fish_catch_pos = recovered
                return
            if not self._step_villager_toward(villager, catch_pos):
                recovered = self._recover_fish_catch(villager, catch_pos)
                villager.fish_catch_pos = recovered
            return

        if villager.inventory.is_full:
            return

        target = self._resolve_fish_target(villager, building)
        if target is None:
            if not villager.inventory.is_empty:
                self._begin_workplace_delivery(villager, building)
                self._update_workplace_delivery(villager, building)
            else:
                villager.state = VillagerState.IDLE
            return

        villager.state = VillagerState.WORKING
        approach = None
        for ny, nx in self.world.neighbourhood(target.x, target.y, radius=1):
            if self.world.is_walkable(nx, ny):
                if approach is None or abs(nx - villager.x) + abs(ny - villager.y) < abs(
                    approach[0] - villager.x
                ) + abs(approach[1] - villager.y):
                    approach = (nx, ny)
        if approach is None:
            villager.fish_target_id = None
            villager.state = VillagerState.IDLE
            return

        dist = max(abs(target.x - villager.x), abs(target.y - villager.y))
        if dist <= 1:
            if villager.work_cooldown == 0:
                pos = self.fish.kill_fish(target.id)
                villager.fish_target_id = None
                if pos is not None:
                    deposit_at = self.world.add_fish_deposit(pos[0], pos[1], FISH_YIELD)
                    shore = self._find_fish_in_fish_areas(building)
                    villager.fish_catch_pos = (
                        shore if shore is not None else deposit_at if deposit_at is not None else pos
                    )
                villager.work_cooldown = self._villager_work_interval(villager)
            return

        self._step_villager_toward(villager, approach)

    def _find_fish_target(self, villager: Villager, building: Building):
        found = []
        if building.areas:
            for area in building.areas:
                if area.task_type != TaskType.FISH:
                    continue
                found.extend(self.fish.fish_in_area(area.contains))
            ox, oy = villager.x, villager.y
        else:
            found = list(self.fish.fish)
            ox, oy = building.x, building.y
        if not found:
            return None
        return min(found, key=lambda f: abs(f.x - ox) + abs(f.y - oy))

    def _resolve_fish_target(self, villager: Villager, building: Building):
        if villager.fish_target_id is not None:
            for item in self.fish.fish:
                if item.id == villager.fish_target_id:
                    return item
            villager.fish_target_id = None
        item = self._find_fish_target(villager, building)
        if item is not None:
            villager.fish_target_id = item.id
        return item

    def _find_fish_in_fish_areas(self, building: Building) -> tuple[int, int] | None:
        if building.areas:
            for area in building.areas:
                if area.task_type != TaskType.FISH:
                    continue
                for x, y in area.cells():
                    cell = self.world.get_cell(x, y)
                    if cell is not None and cell.fish_deposit > 0:
                        return (x, y)
                for x, y in area.cells():
                    cell = self.world.get_cell(x, y)
                    if cell is None or cell.terrain != TerrainType.WATER:
                        continue
                    for ny, nx in self.world.neighbourhood(x, y, radius=1):
                        ncell = self.world.get_cell(nx, ny)
                        if ncell is not None and ncell.fish_deposit > 0:
                            return (nx, ny)
            return None
        best: tuple[int, int] | None = None
        best_d = 10**9
        for y in range(self.world.rows):
            for x in range(self.world.cols):
                cell = self.world.cells[y][x]
                if cell.fish_deposit <= 0:
                    continue
                d = abs(x - building.x) + abs(y - building.y)
                if d < best_d:
                    best_d = d
                    best = (x, y)
        return best

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
                villager.work_cooldown = self._villager_work_interval(villager)
                if not villager.inventory.is_empty:
                    villager.state = VillagerState.DELIVERING
                    villager.target = home
            return
        self._step_villager_toward(villager, (source.x, source.y))

    def _find_haul_source(self, villager: Villager) -> Building | None:
        stocked = [b for b in self.buildings.values() if b.haulable_total() > 0]
        if not stocked:
            return None
        return min(
            stocked,
            key=lambda b: abs(b.x - villager.x) + abs(b.y - villager.y),
        )

    def _plant_stock_in_inv(self, villager: Villager, building: Building) -> bool:
        return any(getattr(villager.inventory, key, 0) > 0 for key in building.plant_keys())

    def _plant_stock_at(self, building: Building, key: str) -> int:
        # Prefer farm stock; home seeds are still usable so planting can start.
        return getattr(building, key, 0) + getattr(self.home_storage, key, 0)

    def _can_plant_from(self, villager: Villager, building: Building) -> tuple[bool, bool, bool]:
        """Whether sapling / berry / crop-seed planting is currently possible."""
        from trees import SAPLING_ITEM_KEYS

        inv = villager.inventory
        can_sapling = inv.saplings > 0 or (
            building.kind == BuildingKind.FORESTER
            and any(self._plant_stock_at(building, k) > 0 for k in SAPLING_ITEM_KEYS)
            and any(inv.can_add(1, key=k) for k in SAPLING_ITEM_KEYS)
        )
        can_berry = False
        can_herb = False
        if building.kind == BuildingKind.FARM:
            can_herb = any(getattr(inv, k, 0) > 0 for k in SEED_KEYS) or (
                any(self._plant_stock_at(building, k) > 0 for k in SEED_KEYS)
                and any(inv.can_add(1, key=k) for k in SEED_KEYS)
            )
        return can_sapling, can_berry, can_herb

    def _plant_withdraw_destination(
        self, building: Building
    ) -> tuple[int, int] | None:
        """Prefer workplace stock; foresters may fall back to home storehouse.

        Farm workers do not walk home for seeds — sowing pulls from home remotely
        so they keep working fields instead of parking on the house tile.
        """
        if any(getattr(building, key, 0) > 0 for key in building.plant_keys()):
            return building.x, building.y
        if building.kind == BuildingKind.FARM:
            return None
        if any(getattr(self.home_storage, key, 0) > 0 for key in building.plant_keys()):
            return self.world.home_pos
        return None

    def _update_plant_stock_withdraw(
        self, villager: Villager, building: Building
    ) -> bool:
        """Walk to storage and pull saplings/seeds before planting. Consumes the turn."""
        if building.work_mode not in (WorkMode.PLANT, WorkMode.BOTH):
            return False
        if not building.allows_planting():
            return False
        if self._plant_stock_in_inv(villager, building):
            return False
        # Need room for at least one plantable of this workplace's type.
        plant_keys = building.plant_keys()
        if not any(villager.inventory.can_add(1, key=k) for k in plant_keys):
            return False
        dest = self._plant_withdraw_destination(building)
        if dest is None:
            return False
        # Only interrupt for withdraw when planting is part of upcoming work.
        can_sapling, can_berry, can_herb = self._can_plant_from(villager, building)
        if building.kind == BuildingKind.FORESTER and not can_sapling:
            return False
        if building.kind == BuildingKind.FARM and not can_herb:
            return False

        villager.state = VillagerState.WORKING
        if (villager.x, villager.y) == dest:
            if villager.work_cooldown > 0:
                return True
            taken = 0
            if dest == self.world.home_pos:
                for key in building.plant_keys():
                    while (
                        taken < 3
                        and getattr(self.home_storage, key, 0) > 0
                        and villager.inventory.can_add(1, key=key)
                        and (
                            Inventory.is_seed_key(key)
                            or villager.inventory.cargo_total < villager.inventory.capacity - 1
                        )
                    ):
                        setattr(self.home_storage, key, getattr(self.home_storage, key) - 1)
                        setattr(
                            villager.inventory,
                            key,
                            getattr(villager.inventory, key) + 1,
                        )
                        taken += 1
            else:
                taken = building.withdraw_plantables_to(villager.inventory, max_items=3)
            if taken <= 0:
                return False
            villager.work_cooldown = self._villager_work_interval(villager)
            return True
        self._step_villager_toward(villager, dest)
        return True

    def _cell_matches_forage_plant(
        self,
        cell,
        *,
        can_plant_berry: bool,
        can_plant_herb: bool,
    ) -> bool:
        return (
            cell.feature == FeatureType.NONE
            and cell.terrain == TerrainType.GRASS
            and (can_plant_berry or can_plant_herb)
        )

    def _cell_matches_manage_plant(self, cell, *, can_plant_sapling: bool) -> bool:
        return (
            can_plant_sapling
            and cell.feature == FeatureType.NONE
            and cell.terrain in PLANTABLE_LAND
        )

    def _closest_of(
        self, origin: tuple[int, int], cells: list[tuple[int, int]]
    ) -> tuple[int, int] | None:
        if not cells:
            return None
        ox, oy = origin
        return min(cells, key=lambda p: abs(p[0] - ox) + abs(p[1] - oy))

    def _find_work_in_building(
        self, villager: Villager, building: Building
    ) -> tuple[int, int] | None:
        can_plant_sapling, can_plant_berry, can_plant_herb = self._can_plant_from(
            villager, building
        )
        mode = building.work_mode
        allow_collect = mode in (WorkMode.COLLECT, WorkMode.BOTH)
        allow_plant = mode in (WorkMode.PLANT, WorkMode.BOTH) and building.allows_planting()
        if not allow_plant:
            can_plant_sapling = can_plant_berry = can_plant_herb = False
        origin = (villager.x, villager.y)

        def match(cell, task_type: TaskType, *, plant_ok: bool) -> bool:
            return self._cell_matches_task(
                cell,
                task_type,
                can_plant_sapling=can_plant_sapling if plant_ok else False,
                can_plant_berry=can_plant_berry if plant_ok else False,
                can_plant_herb=can_plant_herb if plant_ok else False,
            )

        if building.areas:
            gather: list[tuple[int, int]] = []
            plant: list[tuple[int, int]] = []
            for area in building.areas:
                for x, y in area.cells():
                    cell = self.world.get_cell(x, y)
                    if cell is None or not self.world.is_walkable(x, y):
                        continue
                    task = area.task_type
                    if task == TaskType.FULL_MANAGE:
                        if allow_collect and cell.feature == FeatureType.TREE and cell.deposit > 0:
                            gather.append((x, y))
                        elif allow_plant and self._cell_matches_manage_plant(
                            cell, can_plant_sapling=can_plant_sapling
                        ):
                            plant.append((x, y))
                    elif task == TaskType.FULL_FORAGE:
                        if allow_collect and match(cell, task, plant_ok=False):
                            gather.append((x, y))
                    elif match(cell, task, plant_ok=allow_plant):
                        if task in (
                            TaskType.PLANT_SAPLINGS,
                            TaskType.PLANT_BERRY_SEEDS,
                            TaskType.PLANT_HERB_SEEDS,
                        ):
                            if allow_plant:
                                plant.append((x, y))
                        elif allow_collect:
                            gather.append((x, y))
            if allow_plant and plant and (
                can_plant_sapling or can_plant_berry or can_plant_herb
            ):
                chosen = self._closest_of(origin, plant)
                if chosen is not None:
                    return chosen
            if allow_collect:
                return self._closest_of(origin, gather)
            return self._closest_of(origin, plant)

        # No areas: whole-map behaviour from work_mode.
        if building.kind == BuildingKind.FORESTER:
            if allow_plant and can_plant_sapling:
                planted = self._find_closest_manage_plant_cell(
                    building.x, building.y, can_plant_sapling=True
                )
                if planted is not None:
                    return planted
            if allow_collect:
                return self._find_closest_task_cell(
                    building.x,
                    building.y,
                    TaskType.CHOP_TREES,
                    can_plant_sapling=False,
                    can_plant_berry=False,
                    can_plant_herb=False,
                )
            return None

        if building.kind == BuildingKind.FORAGER:
            if allow_collect:
                return self._find_closest_task_cell(
                    building.x,
                    building.y,
                    TaskType.FULL_FORAGE,
                    can_plant_sapling=False,
                    can_plant_berry=False,
                    can_plant_herb=False,
                )
            return None

        if building.kind == BuildingKind.MASON:
            task = TaskType.COLLECT_ROCKS
        else:
            task = building.draw_task_type
            if task not in TASK_LABELS:
                task = building.default_draw_task()
        if not allow_collect:
            return None
        return self._find_closest_task_cell(
            building.x,
            building.y,
            task,
            can_plant_sapling=False,
            can_plant_berry=False,
            can_plant_herb=False,
        )

    def _find_closest_task_cell(
        self,
        ox: int,
        oy: int,
        task_type: TaskType,
        *,
        can_plant_sapling: bool,
        can_plant_berry: bool,
        can_plant_herb: bool,
    ) -> tuple[int, int] | None:
        best: tuple[int, int] | None = None
        best_d = 10**9
        cells = self.world.cells
        rows = self.world.rows
        cols = self.world.cols
        for y in range(rows):
            row = cells[y]
            for x in range(cols):
                cell = row[x]
                if cell.terrain == TerrainType.WATER:
                    continue
                if not self._cell_matches_task(
                    cell,
                    task_type,
                    can_plant_sapling=can_plant_sapling,
                    can_plant_berry=can_plant_berry,
                    can_plant_herb=can_plant_herb,
                ):
                    continue
                d = abs(x - ox) + abs(y - oy)
                if d < best_d:
                    best_d = d
                    best = (x, y)
                    if best_d == 0:
                        return best
        return best

    def _find_closest_forage_plant_cell(
        self,
        ox: int,
        oy: int,
        *,
        can_plant_berry: bool,
        can_plant_herb: bool,
    ) -> tuple[int, int] | None:
        best: tuple[int, int] | None = None
        best_d = 10**9
        cells = self.world.cells
        for y in range(self.world.rows):
            row = cells[y]
            for x in range(self.world.cols):
                cell = row[x]
                if cell.terrain == TerrainType.WATER:
                    continue
                if not self._cell_matches_forage_plant(
                    cell,
                    can_plant_berry=can_plant_berry,
                    can_plant_herb=can_plant_herb,
                ):
                    continue
                d = abs(x - ox) + abs(y - oy)
                if d < best_d:
                    best_d = d
                    best = (x, y)
        return best

    def _find_closest_manage_plant_cell(
        self,
        ox: int,
        oy: int,
        *,
        can_plant_sapling: bool,
    ) -> tuple[int, int] | None:
        best: tuple[int, int] | None = None
        best_d = 10**9
        cells = self.world.cells
        for y in range(self.world.rows):
            row = cells[y]
            for x in range(self.world.cols):
                cell = row[x]
                if cell.terrain == TerrainType.WATER:
                    continue
                if not self._cell_matches_manage_plant(
                    cell, can_plant_sapling=can_plant_sapling
                ):
                    continue
                d = abs(x - ox) + abs(y - oy)
                if d < best_d:
                    best_d = d
                    best = (x, y)
        return best

    def _cell_matches_task(
        self,
        cell,
        task_type: TaskType,
        can_plant_sapling: bool = True,
        can_plant_berry: bool = True,
        can_plant_herb: bool = True,
    ) -> bool:
        if task_type == TaskType.CHOP_TREES:
            return cell.feature == FeatureType.TREE and cell.deposit > 0
        if task_type == TaskType.COLLECT_ROCKS:
            return cell.feature == FeatureType.ROCK and cell.deposit > 0
        if task_type == TaskType.PLANT_SAPLINGS:
            return (
                can_plant_sapling
                and cell.feature == FeatureType.NONE
                and cell.terrain in PLANTABLE_LAND
            )
        if task_type == TaskType.FULL_MANAGE:
            if cell.feature == FeatureType.TREE and cell.deposit > 0:
                return True
            return (
                can_plant_sapling
                and cell.feature == FeatureType.NONE
                and cell.terrain in PLANTABLE_LAND
            )
        if task_type == TaskType.FORAGE_MUSHROOMS:
            return cell.feature == FeatureType.MUSHROOM
        if task_type == TaskType.FORAGE_BERRIES:
            return cell.feature == FeatureType.BERRY_BUSH and cell.deposit > 0
        if task_type == TaskType.FORAGE_HERBS:
            return cell.feature in (FeatureType.HERB, FeatureType.WILD_CROP, FeatureType.REED)
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
            if cell.feature in (FeatureType.HERB, FeatureType.WILD_CROP, FeatureType.REED):
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
        mode = building.work_mode
        allow_collect = mode in (WorkMode.COLLECT, WorkMode.BOTH)
        allow_plant = mode in (WorkMode.PLANT, WorkMode.BOTH) and building.allows_planting()
        tasks = {area.task_type for area in building.areas if area.contains(x, y)}
        if not tasks:
            task = building.draw_task_type
            if task not in TASK_LABELS:
                task = building.default_draw_task()
            tasks = {task}
        inv = villager.inventory

        if (
            allow_collect
            and cell.feature == FeatureType.TREE
            and (TaskType.CHOP_TREES in tasks or TaskType.FULL_MANAGE in tasks)
        ):
            self._chop_tree(x, y, inv, status=False)
        elif allow_collect and cell.feature == FeatureType.ROCK and TaskType.COLLECT_ROCKS in tasks:
            self._collect_rock(x, y, inv, status=False)
        elif (
            allow_collect
            and cell.feature == FeatureType.MUSHROOM
            and (TaskType.FORAGE_MUSHROOMS in tasks or TaskType.FULL_FORAGE in tasks)
        ):
            self._collect_mushroom(x, y, inv, status=False)
        elif (
            allow_collect
            and cell.feature == FeatureType.BERRY_BUSH
            and (TaskType.FORAGE_BERRIES in tasks or TaskType.FULL_FORAGE in tasks)
        ):
            self._collect_berries(x, y, inv, status=False)
        elif (
            allow_collect
            and cell.feature in (FeatureType.HERB, FeatureType.WILD_CROP, FeatureType.REED)
            and (TaskType.FORAGE_HERBS in tasks or TaskType.FULL_FORAGE in tasks)
        ):
            self._collect_herb(x, y, inv, status=False)
        elif allow_plant and cell.feature == FeatureType.NONE:
            # Prefer inventory stock (filled by storage withdraw). Fall back to remote pull.
            if building.kind == BuildingKind.FORESTER and (
                TaskType.PLANT_SAPLINGS in tasks or TaskType.FULL_MANAGE in tasks
            ):
                if inv.saplings <= 0:
                    if not building.give_sapling_to(inv):
                        from trees import SAPLING_ITEM_KEYS

                        self.home_storage.withdraw_keys_to(inv, SAPLING_ITEM_KEYS)
                self._plant(x, y, inv, status=False)

    def _step_villager_toward(self, villager: Villager, goal: tuple[int, int]) -> bool:
        """Step along a path toward goal. Returns False if the goal is unreachable."""
        if villager.move_cooldown > 0:
            return True
        if (villager.x, villager.y) == goal:
            return True
        cache_goal = getattr(villager, "_path_goal", None)
        cache: list[tuple[int, int]] | None = getattr(villager, "_path_cache", None)
        if cache_goal != goal or cache is None:
            path = self.world.find_path((villager.x, villager.y), goal)
            villager._path_cache = path if path is not None else []  # type: ignore[attr-defined]
            villager._path_goal = goal  # type: ignore[attr-defined]
            cache = villager._path_cache  # type: ignore[attr-defined]
        if not cache:
            # Unreachable or exhausted — clear and signal failure.
            villager._path_cache = None  # type: ignore[attr-defined]
            villager._path_goal = None  # type: ignore[attr-defined]
            return False
        step = cache.pop(0)
        villager.x, villager.y = step
        villager.move_cooldown = self._villager_move_interval(villager)
        return True

    def _clear_villager_path(self, villager: Villager) -> None:
        villager._path_cache = None  # type: ignore[attr-defined]
        villager._path_goal = None  # type: ignore[attr-defined]

    def _recover_fish_catch(
        self, villager: Villager, catch_pos: tuple[int, int]
    ) -> tuple[int, int] | None:
        """If a catch tile is unreachable, move the pile onto reachable shore."""
        relocated = self.world.relocate_fish_deposit(
            catch_pos[0],
            catch_pos[1],
            reachable_from=(villager.x, villager.y),
        )
        self._clear_villager_path(villager)
        if relocated is None:
            return None
        if self.world.find_path((villager.x, villager.y), relocated) is None:
            return None
        return relocated

    # ------------------------------------------------------------------
    # Update / indicators
    # ------------------------------------------------------------------
    def _set_status(self, message: str) -> None:
        self.status_message = message
        self.status_timer = STATUS_MESSAGE_FRAMES

    def _refresh_indicators(self) -> None:
        if self.overlay_mode == OverlayMode.BIODIVERSITY:
            # Year-average of season start/mid samples — not live.
            avg = self._biodiversity_average
            self.overlay_values = [row[:] for row in avg]
            return
        self.overlay_values = build_overlay_grid(self.world, self.overlay_mode)

    def _update_status_timer(self) -> None:
        if self.status_timer > 0:
            self.status_timer -= 1
            if self.status_timer == 0:
                self.status_message = ""

    def _update_simulation(self) -> None:
        self.day_tick -= 1
        if self.day_tick <= 0:
            self.day_tick = TICKS_PER_DAY
            self._advance_day()
        day = float(self.calendar_day) + (1.0 - self.day_tick / TICKS_PER_DAY)
        self.world.tick(decay_per_tick=DISTURBANCE_DECAY_PER_TICK, day=day)
        self._update_villagers()
        self.wildlife.tick(self.world, day)
        self.fish.tick(self.world, day)
        # Biodiversity is sample-based; skip live refresh for that mode.
        if self.overlay_mode not in (OverlayMode.NONE, OverlayMode.BIODIVERSITY):
            self._refresh_indicators()

    def _advance_sim_ticks(self, ticks: int) -> None:
        """Advance `ticks` simulation steps, batching idle waits and ecology."""
        remaining = ticks
        eco_pending = 0
        wildlife_pending = 0

        def flush_eco(day: float) -> None:
            nonlocal eco_pending
            if eco_pending <= 0:
                return
            self.world.tick_bulk(
                eco_pending,
                decay_per_tick=DISTURBANCE_DECAY_PER_TICK,
                day=day,
            )
            eco_pending = 0

        while remaining > 0:
            skip = self._idle_cooldown_skip(remaining)
            day = float(self.calendar_day) + (1.0 - self.day_tick / TICKS_PER_DAY)

            if skip > 1:
                flush_eco(day)
                for villager in self.villagers:
                    villager.move_cooldown = max(0, villager.move_cooldown - skip)
                    villager.work_cooldown = max(0, villager.work_cooldown - skip)
                    villager.satiation = max(
                        0.0,
                        villager.satiation - VILLAGER_SATIATION_DECAY_PER_TICK * skip,
                    )
                for animal in self.wildlife.animals:
                    animal.move_cooldown = max(0, animal.move_cooldown - skip)
                for item in self.fish.fish:
                    item.move_cooldown = max(0, item.move_cooldown - skip)

                eco_left = skip
                while eco_left > 0:
                    step = min(eco_left, self.day_tick)
                    self.day_tick -= step
                    eco_left -= step
                    if self.day_tick <= 0:
                        self.day_tick = TICKS_PER_DAY
                        self._advance_day()
                day = float(self.calendar_day)
                self.world.tick_bulk(
                    skip,
                    decay_per_tick=DISTURBANCE_DECAY_PER_TICK,
                    day=day,
                )
                self.wildlife.tick(self.world, day)
                self.fish.tick(self.world, day)
                wildlife_pending = 0
                remaining -= skip
                continue

            # Single active tick (someone can act).
            self.day_tick -= 1
            if self.day_tick <= 0:
                flush_eco(day)
                self.day_tick = TICKS_PER_DAY
                self._advance_day()
                day = float(self.calendar_day)
            else:
                day = float(self.calendar_day) + (1.0 - self.day_tick / TICKS_PER_DAY)

            eco_pending += 1
            wildlife_pending += 1
            if eco_pending >= 16:
                flush_eco(day)
            self._update_villagers()
            if wildlife_pending >= 4:
                self.wildlife.tick(self.world, day)
                self.fish.tick(self.world, day)
                wildlife_pending = 0
            remaining -= 1

        day = float(self.calendar_day) + (1.0 - self.day_tick / TICKS_PER_DAY)
        flush_eco(day)
        if wildlife_pending:
            self.wildlife.tick(self.world, day)
            self.fish.tick(self.world, day)

    def _idle_cooldown_skip(self, limit: int) -> int:
        """Largest N≤limit where every villager is blocked on move+work cooldowns."""
        if limit <= 1 or not self.villagers:
            return 1
        skip = limit
        for villager in self.villagers:
            if villager.needs_food() or villager.seeking_food:
                return 1
            if villager.move_cooldown <= 0 or villager.work_cooldown <= 0:
                return 1
            skip = min(skip, villager.move_cooldown, villager.work_cooldown)
        return max(1, skip)

    def simulate_fast_day(self) -> None:
        """One in-game day: same rules as live play, no rendering."""
        self.fast_forward = True
        self._advance_sim_ticks(TICKS_PER_DAY)

    def simulate_fast_days(self, days: int) -> None:
        self.fast_forward = True
        self._advance_sim_ticks(days * TICKS_PER_DAY)
        self.fast_forward = False

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
        self._draw_fish()
        self._draw_villagers()
        self._draw_player()
        self._draw_selection_highlights()
        self._draw_minimap()
        self._draw_autotile_diag_overlay()
        mouse = pygame.mouse.get_pos()
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
            sim_speed=self.sim_speed,
            fish_manager=self.fish,
            construction_sites=self.construction_sites,
            assign_workplace_mode=self.assign_workplace_mode,
            mouse_pos=mouse,
            season=self.season,
            calendar_day=self.calendar_day,
            selected_habitat_kind=self.selected_habitat_kind,
            selected_habitat_id=self.selected_habitat_id,
        )
        self.resource_bar.draw(
            self.screen,
            self.home_storage,
            self.player,
            self.buildings,
            self.villagers,
            mouse,
        )
        self.toolbar.draw(
            self.screen,
            self.place_kind,
            self._selected_building(),
            self.sim_speed,
            mouse,
            season_label=format_date(self.calendar_day),
            field_crop=self.field_crop_kind,
        )
        self.file_dialog.draw(self.screen)
        field_b = self._field_plan_building()
        self.field_plan_dialog.draw(
            self.screen,
            field_b,
            crop_counts=self._field_crop_counts(field_b) if field_b else None,
        )
        inspect_b = self._inspect_building()
        if inspect_b is None:
            inspect_workers: list = []
            storage_amounts = None
            hired_count = 0
        elif inspect_b.kind == BuildingKind.HOME:
            inspect_workers = [v for v in self.villagers if v.assigned_to_home]
            from resources import amounts_from_obj

            storage_amounts = amounts_from_obj(self.home_storage)
            hired_count = 0
        elif inspect_b.kind == BuildingKind.WORKSTATION:
            inspect_workers = []
            storage_amounts = None
            hired_count = len(self.villagers)
        else:
            inspect_workers = [v for v in self.villagers if v.building_id == inspect_b.id]
            storage_amounts = None
            hired_count = 0
        self.building_inspect.draw(
            self.screen,
            inspect_b,
            inspect_workers,
            selected_villager_id=self.selected_villager_id,
            mouse_pos=mouse,
            storage_amounts=storage_amounts,
            hired_count=hired_count,
        )
        inspect_v = self._get_villager(self.villager_inspect.villager_id or -1)
        self.villager_inspect.draw(
            self.screen,
            inspect_v,
            assignment_label=(
                self._villager_assignment_label(inspect_v) if inspect_v else "—"
            ),
            mouse_pos=mouse,
        )
        self.resource_inspect.draw(self.screen, mouse_pos=mouse)
        pygame.display.flip()

    def _farm_field_cells(self) -> set[tuple[int, int]]:
        """No fake soil: field plots stay grass until workers plough each tile."""
        return set()

    def _draw_field_plot_outline(
        self,
        left: int,
        top: int,
        right: int,
        bottom: int,
        *,
        colour: tuple[int, int, int],
        width: int = 2,
        fill_alpha: int = 0,
        tint: pygame.Surface | None = None,
    ) -> None:
        if fill_alpha > 0 and tint is not None:
            for y in range(top, bottom + 1):
                for x in range(left, right + 1):
                    rect = self._cell_rect(x, y)
                    # tint surface is map-local (0,0 = map top-left)
                    local = pygame.Rect(
                        rect.x, rect.y - MAP_OFFSET_Y, rect.w, rect.h
                    )
                    tint.fill((*colour, fill_alpha), local)
        tl = self.camera.world_to_screen(left, top)
        br = self.camera.world_to_screen(right + 1, bottom + 1)
        border = pygame.Rect(tl[0], tl[1], br[0] - tl[0], br[1] - tl[1])
        pygame.draw.rect(self.screen, colour, border, width)

    def _terrain_base_cache_key(self) -> tuple:
        return (
            self.world.cols,
            self.world.rows,
            CELL_SIZE,
            self.world.terrain_revision,
        )

    def _invalidate_terrain_layer(self) -> None:
        self._terrain_base = None
        self._terrain_base_key = None
        self._terrain_water_mask = None
        self._farm_cells_cached = set()
        self._season_mute = None
        self._season_mute_key = None
        self._ice_overlay = None
        self._ice_overlay_key = None

    def _visual_terrain_at(
        self, x: int, y: int, farm_cells: set[tuple[int, int]]
    ) -> TerrainType:
        """Terrain used for tiling; farm plots render as soil."""
        if not (0 <= x < self.world.cols and 0 <= y < self.world.rows):
            # Out of bounds matches nearest edge cell so borders stay solid.
            cx = min(max(0, x), self.world.cols - 1)
            cy = min(max(0, y), self.world.rows - 1)
            if (cx, cy) in farm_cells:
                return TerrainType.SOIL
            return self.world.cells[cy][cx].terrain
        if (x, y) in farm_cells:
            return TerrainType.SOIL
        return self.world.cells[y][x].terrain

    def _paint_terrain_cell(
        self,
        x: int,
        y: int,
        farm_cells: set[tuple[int, int]],
    ) -> None:
        assert self._terrain_base is not None and self._terrain_water_mask is not None
        paint_cell(
            self._terrain_base,
            self._terrain_water_mask,
            x,
            y,
            terrain_at=lambda tx, ty: self._visual_terrain_at(tx, ty, farm_cells),
        )

    def _sync_farm_terrain_dirty(
        self, farm_cells: set[tuple[int, int]]
    ) -> None:
        """When field layout changes, re-tile only affected cells + neighbours."""
        if farm_cells == self._farm_cells_cached:
            return
        changed = farm_cells.symmetric_difference(self._farm_cells_cached)
        self._farm_cells_cached = set(farm_cells)
        for x, y in changed:
            self.world.mark_terrain_dirty(x, y)

    def _ensure_terrain_base(
        self, farm_cells: set[tuple[int, int]]
    ) -> tuple[pygame.Surface, pygame.Surface]:
        """Stitch pre-rendered tiles; full rebuild on revision, else patch dirty."""
        key = self._terrain_base_cache_key()
        full_rebuild = (
            self._terrain_base is None
            or self._terrain_water_mask is None
            or self._terrain_base_key != key
        )
        self._sync_farm_terrain_dirty(farm_cells)

        if full_rebuild:
            size = (self.world.cols * CELL_SIZE, self.world.rows * CELL_SIZE)
            self._terrain_base = pygame.Surface(size)
            self._terrain_water_mask = pygame.Surface(size, pygame.SRCALPHA)
            self._terrain_water_mask.fill((0, 0, 0, 0))
            self._terrain_base_key = key
            self._farm_cells_cached = set(farm_cells)
            for y in range(self.world.rows):
                for x in range(self.world.cols):
                    self._paint_terrain_cell(x, y, farm_cells)
            self.world.terrain_dirty.clear()
            self._ice_overlay = None
            self._ice_overlay_key = None
            self._season_mute = None
            self._season_mute_key = None
            return self._terrain_base, self._terrain_water_mask

        dirty = self.world.terrain_dirty
        if dirty:
            # Copy before clear — paint may mark nothing new.
            cells = list(dirty)
            dirty.clear()
            for x, y in cells:
                self._paint_terrain_cell(x, y, farm_cells)
            # Ice mask geometry may have changed on patched water edges.
            self._ice_overlay = None
            self._ice_overlay_key = None

        return self._terrain_base, self._terrain_water_mask

    def _ensure_season_mute(self, vibrancy: float) -> pygame.Surface | None:
        """RGB multiply tint; lower vibrancy → cooler / duller map."""
        bucket = round(vibrancy, 2)
        if bucket >= 0.995:
            return None
        if self._season_mute is not None and self._season_mute_key == bucket:
            return self._season_mute
        t = bucket
        mute = pygame.Surface(
            (self.world.cols * CELL_SIZE, self.world.rows * CELL_SIZE)
        )
        mute.fill(
            (
                int(140 + 115 * t),
                int(148 + 107 * t),
                int(158 + 97 * t),
            )
        )
        self._season_mute = mute
        self._season_mute_key = bucket
        return mute

    def _ensure_ice_overlay(
        self, freeze: float, water_mask: pygame.Surface
    ) -> pygame.Surface | None:
        bucket = round(freeze, 2)
        if bucket < 0.02:
            return None
        if self._ice_overlay is not None and self._ice_overlay_key == bucket:
            return self._ice_overlay
        ice = pygame.Surface(water_mask.get_size(), pygame.SRCALPHA)
        ice.fill((210, 228, 240, int(min(1.0, bucket) * 200)))
        ice.blit(water_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        self._ice_overlay = ice
        self._ice_overlay_key = bucket
        return ice

    def _blit_camera_world_surface(
        self,
        surf: pygame.Surface,
        dest: tuple[int, int],
        *,
        special_flags: int = 0,
    ) -> None:
        """Blit the camera viewport of a CELL_SIZE-based world surface onto the map."""
        mw = map_view_width()
        mh = map_view_height()
        zoom = self.camera.view_cell() / CELL_SIZE
        sx = self.camera.x * CELL_SIZE
        sy = self.camera.y * CELL_SIZE
        sw = mw / max(1e-6, zoom)
        sh = mh / max(1e-6, zoom)
        ix = max(0, int(sx))
        iy = max(0, int(sy))
        src = pygame.Rect(ix, iy, int(sw) + 2, int(sh) + 2).clip(surf.get_rect())
        if src.w < 1 or src.h < 1:
            return
        piece = surf.subsurface(src)
        scaled = pygame.transform.scale(
            piece,
            (max(1, int(round(src.w * zoom))), max(1, int(round(src.h * zoom)))),
        )
        ox = dest[0] - int(round((sx - src.x) * zoom))
        oy = dest[1] - int(round((sy - src.y) * zoom))
        self.screen.blit(scaled, (ox, oy), special_flags=special_flags)

    def _draw_world(self) -> None:
        """Draw tiled terrain under camera, then features for visible cells."""
        day = float(self.calendar_day) + (1.0 - self.day_tick / TICKS_PER_DAY)
        freeze = freeze_amount(day)
        vibrancy = terrain_vibrancy(day)
        farm_cells = self._farm_field_cells()
        base, water_mask = self._ensure_terrain_base(farm_cells)

        map_clip = pygame.Rect(0, MAP_OFFSET_Y, map_view_width(), map_view_height())
        self.screen.set_clip(map_clip)

        origin = (0, MAP_OFFSET_Y)
        self._blit_camera_world_surface(base, origin)
        mute = self._ensure_season_mute(vibrancy)
        if mute is not None:
            self._blit_camera_world_surface(
                mute, origin, special_flags=pygame.BLEND_RGB_MULT
            )
        ice = self._ensure_ice_overlay(freeze, water_mask)
        if ice is not None:
            self._blit_camera_world_surface(ice, origin)

        x0, y0, x1, y1 = self.camera.visible_range(self.world.cols, self.world.rows)
        vc = self.camera.view_cell()
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if not self.world.in_bounds(x, y):
                    continue
                cell = self.world.cells[y][x]
                rect = self._cell_rect(x, y)
                cx, cy = self._cell_center(x, y)
                draw_feature(
                    self.screen,
                    cell.feature,
                    cx,
                    cy,
                    vc,
                    vibrancy=vibrancy,
                    crop_kind=cell.crop_kind,
                    tree_species=cell.tree_species,
                )
                if cell.feature == FeatureType.CONSTRUCTION_SITE:
                    site = self._construction_at(x, y)
                    if site is not None:
                        self._draw_construction_progress(site, rect)
                if cell.meat_deposit > 0:
                    pygame.draw.circle(self.screen, COLOUR_MEAT, (cx + 8, cy + 8), 5)
                    pygame.draw.circle(self.screen, (80, 20, 20), (cx + 8, cy + 8), 5, 1)
                if cell.fish_deposit > 0:
                    pygame.draw.circle(self.screen, COLOUR_FISH, (cx - 8, cy + 8), 5)
                    pygame.draw.circle(self.screen, (20, 60, 90), (cx - 8, cy + 8), 5, 1)

        self.screen.set_clip(None)

    def _draw_construction_progress(self, site: ConstructionSite, rect: pygame.Rect) -> None:
        bar = pygame.Rect(rect.x + 4, rect.bottom - 8, rect.w - 8, 4)
        pygame.draw.rect(self.screen, (40, 40, 45), bar)
        if site.materials_ready:
            frac = site.build_progress / max(1, site.build_required_ticks())
            colour = (80, 180, 100)
        else:
            delivered = site.have_wood + site.have_rock
            frac = delivered / max(1, site.total_items)
            colour = (220, 180, 60)
        fill = pygame.Rect(bar.x, bar.y, max(0, int(bar.w * min(1.0, frac))), bar.h)
        pygame.draw.rect(self.screen, colour, fill)

    def _draw_overlay(self) -> None:
        """Draw indicator overlay for the camera viewport (world-sized values)."""
        if self.overlay_mode == OverlayMode.NONE:
            return
        if not self.overlay_values or len(self.overlay_values) != self.world.rows:
            self._refresh_indicators()
        map_clip = pygame.Rect(0, MAP_OFFSET_Y, map_view_width(), map_view_height())
        self.screen.set_clip(map_clip)
        x0, y0, x1, y1 = self.camera.visible_range(self.world.cols, self.world.rows)
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if not self.world.in_bounds(x, y):
                    continue
                value = self.overlay_values[y][x]
                colour = overlay_colour(self.overlay_mode, value)
                rect = self._cell_rect(x, y)
                tint = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
                tint.fill((*colour, OVERLAY_ALPHA))
                self.screen.blit(tint, rect.topleft)
        self.screen.set_clip(None)

    def _draw_task_areas(self) -> None:
        building = self._selected_building()
        map_clip = pygame.Rect(0, MAP_OFFSET_Y, map_view_width(), map_view_height())
        self.screen.set_clip(map_clip)

        # Field plots: outline only (crop status lives in the plan popup).
        for field_b in self.buildings.values():
            if field_b.kind != BuildingKind.FIELD:
                continue
            self._draw_field_building(field_b)
        # Pending Field construction: full plot outline (no scaffold glyph).
        for site in self.construction_sites.values():
            if site.kind != BuildingKind.FIELD:
                continue
            left, top = site.x, site.y
            right = site.x + max(1, site.plot_w) - 1
            bottom = site.y + max(1, site.plot_h) - 1
            self._draw_field_plot_outline(
                left,
                top,
                right,
                bottom,
                colour=COLOUR_TASK_PREVIEW,
                width=2,
                fill_alpha=0,
            )

        if building is not None and building.kind not in (
            BuildingKind.FARM,
            BuildingKind.FIELD,
        ):
            for area in building.areas:
                colour = TASK_COLOURS.get(area.task_type, COLOUR_TASK_AREA)
                left, top, right, bottom = area.normalised()
                for y in range(top, bottom + 1):
                    for x in range(left, right + 1):
                        rect = self._cell_rect(x, y)
                        tint = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
                        tint.fill((*colour, 55))
                        self.screen.blit(tint, rect.topleft)
                self._draw_field_plot_outline(
                    left, top, right, bottom, colour=colour, width=2, fill_alpha=0
                )

        if self.drawing and self.draw_start and self.draw_current:
            x0, y0 = self.draw_start
            x1, y1 = self.draw_current
            left, top = min(x0, x1), min(y0, y1)
            right, bottom = max(x0, x1), max(y0, y1)
            if self._placing_field or self.place_kind == BuildingKind.FIELD:
                preview = COLOUR_TASK_FARM
            elif building is not None:
                preview = TASK_COLOURS.get(building.draw_task_type, COLOUR_TASK_PREVIEW)
            else:
                preview = COLOUR_TASK_PREVIEW
            for y in range(top, bottom + 1):
                for x in range(left, right + 1):
                    rect = self._cell_rect(x, y)
                    tint = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
                    tint.fill((*preview, 70))
                    self.screen.blit(tint, rect.topleft)
            self._draw_field_plot_outline(
                left,
                top,
                right,
                bottom,
                colour=COLOUR_TASK_PREVIEW,
                width=2,
                fill_alpha=0,
            )

        self.screen.set_clip(None)

    def _draw_field_building(self, building: Building) -> None:
        """Outline only when selected — otherwise soil/crops alone show the field."""
        if building.id != self.selected_building_id:
            return
        left, top, right, bottom = building.plot_bounds()
        self._draw_field_plot_outline(
            left,
            top,
            right,
            bottom,
            colour=COLOUR_SELECTED_ENTITY,
            width=3,
            fill_alpha=0,
        )

    def _draw_animals(self) -> None:
        for animal in self.wildlife.animals:
            cx, cy = self._cell_center(animal.x, animal.y)
            cy += 2
            colour = COLOUR_BOAR if animal.kind == AnimalKind.BOAR else COLOUR_DEER
            pygame.draw.ellipse(
                self.screen,
                colour,
                pygame.Rect(
                    cx - CELL_SIZE // 5,
                    cy - CELL_SIZE // 8,
                    max(6, CELL_SIZE // 2),
                    max(4, CELL_SIZE // 4),
                ),
            )
            # Head
            pygame.draw.circle(
                self.screen, colour, (cx + CELL_SIZE // 6, cy - 2), max(2, CELL_SIZE // 10)
            )

    def _draw_fish(self) -> None:
        freeze = freeze_amount(
            float(self.calendar_day) + (1.0 - self.day_tick / TICKS_PER_DAY)
        )
        colour = blend_colour(COLOUR_FISH, (150, 190, 210), freeze)
        for item in self.fish.fish:
            cx, cy = self._cell_center(item.x, item.y)
            body = pygame.Rect(cx - CELL_SIZE // 5, cy - 2, max(8, CELL_SIZE // 2), max(4, CELL_SIZE // 5))
            pygame.draw.ellipse(self.screen, colour, body)
            pygame.draw.polygon(
                self.screen,
                colour,
                [(cx + CELL_SIZE // 5, cy), (cx + CELL_SIZE // 3, cy - 4), (cx + CELL_SIZE // 3, cy + 4)],
            )

    def _draw_villagers(self) -> None:
        for villager in self.villagers:
            cx, cy = self._cell_center(villager.x, villager.y)
            pygame.draw.circle(self.screen, COLOUR_VILLAGER, (cx, cy), CELL_SIZE // 4)
            pygame.draw.circle(self.screen, (40, 30, 10), (cx, cy), CELL_SIZE // 4, 2)

    def _draw_player(self) -> None:
        cx, cy = self._cell_center(self.player.x, self.player.y)
        pygame.draw.circle(self.screen, COLOUR_PLAYER, (cx, cy), CELL_SIZE // 3)
        pygame.draw.circle(self.screen, (255, 255, 255), (cx, cy), CELL_SIZE // 3, 2)

    def _draw_selection_highlights(self) -> None:
        if self.selected_villager_id is not None:
            villager = self._get_villager(self.selected_villager_id)
            if villager is not None:
                rect = self._cell_rect(villager.x, villager.y)
                pygame.draw.rect(self.screen, COLOUR_SELECTED_ENTITY, rect, 3)
        if self.selected_building_id is not None:
            building = self.buildings.get(self.selected_building_id)
            if building is not None:
                rect = self._cell_rect(building.x, building.y)
                pygame.draw.rect(self.screen, COLOUR_SELECTED_ENTITY, rect, 3)
        if (
            self.selected_habitat_id is not None
            and self.selected_habitat_kind is not None
        ):
            hab = self.wildlife.habitat(self.selected_habitat_id)
            if hab is not None:
                tiles = set(
                    hab.deer_breeding
                    if self.selected_habitat_kind == AnimalKind.DEER
                    else hab.boar_breeding
                )
                roam = (
                    hab.deer_roam_cold
                    if self.selected_habitat_kind == AnimalKind.DEER
                    else hab.boar_roam_cold
                )
                for x, y in roam:
                    if (x, y) in tiles:
                        continue
                    rect = self._cell_rect(x, y)
                    pygame.draw.rect(self.screen, (120, 140, 80), rect, 1)
                for x, y in tiles:
                    rect = self._cell_rect(x, y)
                    pygame.draw.rect(self.screen, COLOUR_SELECTED_ENTITY, rect, 2)

    def _draw_minimap(self) -> None:
        """Draw minimap showing terrain, buildings, and camera viewport."""
        minimap_rect = self._minimap_rect()
        
        # Dark background
        pygame.draw.rect(self.screen, (20, 20, 25), minimap_rect)
        
        # Sample terrain colors (every N cells to fit in minimap)
        sample_step = max(1, max(self.world.cols // MINIMAP_WIDTH, self.world.rows // MINIMAP_HEIGHT))
        
        for wy in range(0, self.world.rows, sample_step):
            for wx in range(0, self.world.cols, sample_step):
                cell = self.world.get_cell(wx, wy)
                if cell is None:
                    continue
                
                # Map world coordinates to minimap pixel
                mini_x = minimap_rect.x + int(wx * MINIMAP_WIDTH / self.world.cols)
                mini_y = minimap_rect.y + int(wy * MINIMAP_HEIGHT / self.world.rows)
                pixel_w = max(1, int(sample_step * MINIMAP_WIDTH / self.world.cols))
                pixel_h = max(1, int(sample_step * MINIMAP_HEIGHT / self.world.rows))
                
                # Simple terrain colors
                from ui import terrain_colour
                colour = terrain_colour(cell.terrain)
                # Darken for minimap
                colour = (colour[0] // 3, colour[1] // 3, colour[2] // 3)
                pygame.draw.rect(self.screen, colour, pygame.Rect(mini_x, mini_y, pixel_w, pixel_h))
        
        # Draw buildings as dots
        for building in self.buildings.values():
            mini_x = minimap_rect.x + int(building.x * MINIMAP_WIDTH / self.world.cols)
            mini_y = minimap_rect.y + int(building.y * MINIMAP_HEIGHT / self.world.rows)
            
            # Color by building kind
            from settings import COLOUR_HOME, COLOUR_WORKSTATION, COLOUR_FORESTER, COLOUR_MASON, COLOUR_HUNTER, COLOUR_FORAGER, COLOUR_FISHER, COLOUR_FARM, COLOUR_FIELD
            colour_map = {
                BuildingKind.HOME: COLOUR_HOME,
                BuildingKind.WORKSTATION: COLOUR_WORKSTATION,
                BuildingKind.FORESTER: COLOUR_FORESTER,
                BuildingKind.MASON: COLOUR_MASON,
                BuildingKind.HUNTER: COLOUR_HUNTER,
                BuildingKind.FORAGER: COLOUR_FORAGER,
                BuildingKind.FISHER: COLOUR_FISHER,
                BuildingKind.FARM: COLOUR_FARM,
                BuildingKind.FIELD: COLOUR_FIELD,
            }
            colour = colour_map.get(building.kind, (200, 200, 200))
            pygame.draw.circle(self.screen, colour, (mini_x, mini_y), 2)
        
        # Draw player as a dot
        player_x = minimap_rect.x + int(self.player.x * MINIMAP_WIDTH / self.world.cols)
        player_y = minimap_rect.y + int(self.player.y * MINIMAP_HEIGHT / self.world.rows)
        pygame.draw.circle(self.screen, COLOUR_PLAYER, (player_x, player_y), 2)
        
        # Draw camera viewport rectangle
        x0, y0, x1, y1 = self.camera.visible_range(self.world.cols, self.world.rows)
        viewport_x = minimap_rect.x + int(x0 * MINIMAP_WIDTH / self.world.cols)
        viewport_y = minimap_rect.y + int(y0 * MINIMAP_HEIGHT / self.world.rows)
        viewport_w = int((x1 - x0) * MINIMAP_WIDTH / self.world.cols)
        viewport_h = int((y1 - y0) * MINIMAP_HEIGHT / self.world.rows)
        pygame.draw.rect(self.screen, (255, 255, 255), pygame.Rect(viewport_x, viewport_y, viewport_w, viewport_h), 1)
        
        # Border
        pygame.draw.rect(self.screen, (100, 100, 110), minimap_rect, 2)

