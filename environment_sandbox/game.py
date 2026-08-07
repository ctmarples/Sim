"""Main game loop: input, buildings, villagers, update, and render.

Player presses Enter/E on their cell. Toolbar handles build, tasks, speed,
and File save/load. Click selects villagers/buildings; drag draws task areas.
Esc clears selection / menus (does not quit).
"""

from __future__ import annotations

import math
import random
import time

import pygame

from crops import (
    CROP_BY_KEY,
    SEED_KEYS,
    SeasonPhase,
    growth_ticks_for,
    phase_allows_plough_plant,
    phase_for_crop,
)
from resource_balance import (
    BERRY_SEED_DROP_CHANCE,
    BOAR_MEAT_YIELD,
    DEER_MEAT_YIELD,
    FARM_PRODUCE_YIELD,
    FARM_SEED_AMOUNTS,
    FISH_YIELD,
    FISH_POST_LOCAL_RADIUS,
    FISH_POST_MIN_FISH,
    FISH_POST_SCORE_RADIUS,
    FORAGER_PRIORITY_BAND,
    WORK_SEARCH_RADIUS,
    PATH_DETOUR_RATIO,
    PATH_DETOUR_SLACK,
    HONEY_PER_BEE_LEVEL,
    MAX_FOOD_TYPES_PER_MEAL,
    MUSHROOM_YIELD,
    POLLINATOR_BASE_RADIUS,
    POLLINATOR_BASE_STRENGTH,
    POLLINATOR_RADIUS_PER_LEVEL,
    POLLINATOR_STRENGTH_PER_LEVEL,
    FIELD_PEST_BOOST_MAX,
    INSECT_REPELLANT_PEST_BOOST,
    MINERAL_POWDER_PEST_BOOST,
    RABBIT_MEAT_PER_LEVEL,
    REED_YIELD,
    SAPLING_DROP_CHANCE,
    STARTING_FOOD,
    VILLAGER_FOOD_KEYS,
    VILLAGER_SATIATION_DECAY_PER_TICK,
    WILD_PRODUCE_YIELD,
    combine_meal_buffs,
    food_def,
    satiation_from_points,
)
from entities import (
    BUILDING_LABELS,
    DEFAULT_PRIORITIES_UNASSIGNED,
    PRIORITY_LABELS,
    RATION_LABELS,
    RECIPE_PRIORITY_MAX,
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
    TOOL_KEYS,
    WORKPLACE_TOOL,
    Villager,
    VillagerState,
    WorkMode,
    WorkPriority,
    arm_cell_step_visual,
    default_building_plot,
    default_item_mins,
    default_processor_capacities,
    entity_draw_xy,
    note_cell_step,
)
from indicators import (
    OVERLAY_LABELS,
    OverlayMode,
    build_overlay_grid,
    floral_resources_snapshot,
    overlay_colour,
    pollination_coverage_grid,
)
from environment import (
    EnvLayer,
    EnvMaps,
    PEST_CONTROL_MULT_HIGH,
    POLLINATION_YIELD_HIGH,
    crop_health_cap_from_pest_control,
    is_env_sample_day,
    pollination_yield_multiplier,
)
from settings import (
    BUILDING_STORAGE_CAPACITY,
    BUILDING_FOOTPRINT,
    CELL_SIZE,
    COLOUR_BOAR,
    COLOUR_DEER,
    COLOUR_BG,
    COLOUR_FISH,
    COLOUR_FARM,
    COLOUR_FISHER,
    COLOUR_FORAGER,
    COLOUR_FORESTER,
    COLOUR_HOME,
    COLOUR_HUNTER,
    COLOUR_KITCHEN,
    COLOUR_CRAFT_BENCH,
    COLOUR_ALCHEMIST,
    COLOUR_MASON,
    COLOUR_MEAT,
    COLOUR_MILL,
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
    FARM_COST_ROCK,
    FARM_COST_WOOD,
    FARM_FIELD_RADIUS,
    FIELD_COST_ROCK,
    FIELD_COST_WOOD,
    FISHER_COST_ROCK,
    FISHER_COST_WOOD,
    FORESTER_COST_ROCK,
    FORESTER_COST_WOOD,
    FORAGER_COST_ROCK,
    FORAGER_COST_WOOD,
    FPS,
    GRID_COLS,
    GRID_ROWS,
    HUNTER_COST_ROCK,
    HUNTER_COST_WOOD,
    INVENTORY_CAPACITY,
    KITCHEN_COST_ROCK,
    KITCHEN_COST_WOOD,
    KITCHEN_FUEL_CAPACITY,
    CRAFT_BENCH_COST_ROCK,
    ALCHEMIST_COST_WOOD,
    ALCHEMIST_COST_ROCK,
    CRAFT_BENCH_COST_WOOD,
    MASON_COST_ROCK,
    MASON_COST_WOOD,
    MAX_VILLAGERS,
    MILL_COST_ROCK,
    MILL_COST_WOOD,
    MINIMAP_HEIGHT,
    MINIMAP_WIDTH,
    OVERLAY_ALPHA,
    PLAYER_VIS_SPEED,
    SIM_SPEEDS,
    STARTING_ROCK,
    STARTING_WOOD,
    STATUS_MESSAGE_FRAMES,
    TICKS_PER_DAY_OPTIONS,
    REFERENCE_TICKS_PER_DAY,
    HEIGHT_SAMPLE_ENABLED_DEFAULT,
    HEIGHT_LIFT_PX,
    HEIGHT_EDIT_BRUSH_MIN,
    HEIGHT_EDIT_BRUSH_MAX,
    HEIGHT_EDIT_VALUE_MAX,
    HEIGHT_EDIT_VALUE_STEP,
    HEIGHT_EDIT_DELTA_DEFAULT,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    WORLD_COLS,
    ZOOM_STEP,
    MAP_OFFSET_Y,
    map_view_height,
    map_view_width,
)
from height_sample import (
    HeightSample,
    bake_height_sample_surface,
    generate_height_sample,
    screen_lift_px,
)
from balance_config import BalanceState, set_active_balance
from balance_dialog import BalanceDialog
from camera import Camera
from dialogs import FileDialog
from building_inspect_dialog import BuildingInspectDialog
from field_plan_dialog import FieldPlanDialog
from habitat_inspect_dialog import HabitatInspectDialog, HabitatInspectView
from resource_inspect_dialog import ResourceInspectDialog
from resource_tracker import ResourceHistory
from resource_tracker_dialog import ResourceTrackerDialog
from villager_inspect_dialog import VillagerInspectDialog
from resource_bar import VIEW_LABELS, ResourceBar
from recipes import (
    apply_recipe,
)
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
    set_ticks_per_day,
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
from world import (
    BUILDABLE_LAND,
    EDIT_PAINTABLE_TERRAIN,
    FeatureType,
    MapEditTool,
    PLANTABLE_LAND,
    SOIL_LIKE,
    TERRAIN_EDIT_LABELS,
    TerrainType,
    World,
    hardscape_paintable,
    is_bare_rock,
    is_water_terrain,
)


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
    TaskType.SPLIT_LOGS: COLOUR_TASK_CHOP,
}

FEATURE_FOR_BUILDING = {
    BuildingKind.HOME: FeatureType.HOME,
    BuildingKind.WORKSTATION: FeatureType.WORKSTATION,
    BuildingKind.FORESTER: FeatureType.FORESTER,
    BuildingKind.MASON: FeatureType.MASON,
    BuildingKind.HUNTER: FeatureType.HUNTER,
    BuildingKind.FORAGER: FeatureType.FORAGER,
    BuildingKind.FISHER: FeatureType.FISHER,
    BuildingKind.FARM: FeatureType.FARM,
    BuildingKind.FIELD: FeatureType.FIELD,
    BuildingKind.MILL: FeatureType.MILL,
    BuildingKind.KITCHEN: FeatureType.KITCHEN,
    BuildingKind.CRAFT_BENCH: FeatureType.CRAFT_BENCH,
    BuildingKind.ALCHEMIST: FeatureType.ALCHEMIST,
}

BUILDING_FEATURES = frozenset(FEATURE_FOR_BUILDING.values()) | {
    FeatureType.CONSTRUCTION_SITE,
    FeatureType.STRUCTURE_PAD,
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
        from icons import ALL_ICON_NAMES, preload

        preload(ALL_ICON_NAMES, sizes=(CELL_SIZE,))
        self.clock = pygame.time.Clock()
        self.ui = UI()
        self.toolbar = Toolbar()
        self.resource_bar = ResourceBar()
        self.file_dialog = FileDialog()
        self.field_plan_dialog = FieldPlanDialog()
        self.habitat_inspect = HabitatInspectDialog()
        self.building_inspect = BuildingInspectDialog()
        self.villager_inspect = VillagerInspectDialog()
        self.resource_inspect = ResourceInspectDialog()
        self.resource_tracker = ResourceTrackerDialog()
        self.balance_dialog = BalanceDialog()
        self.balance = BalanceState()
        set_active_balance(self.balance)
        self.resource_history = ResourceHistory()
        self.height_sample_enabled = HEIGHT_SAMPLE_ENABLED_DEFAULT
        self.height_sample: HeightSample | None = None
        self._height_sample_cache: pygame.Surface | None = None
        self._height_sample_cache_pad: int = 0
        self._height_sample_cache_key: tuple | None = None
        # Sticky baked cell bounds (x0,y0,x1,y1). Rebake only when camera leaves.
        self._height_cache_bounds: tuple[int, int, int, int] | None = None
        self.height_edit_mode = False
        self._height_warp_before_edit = HEIGHT_SAMPLE_ENABLED_DEFAULT
        self.map_edit_tool = MapEditTool.HEIGHT_SET
        self.map_edit_terrain = TerrainType.GRASS
        self.height_paint_value = 20.0
        self.height_delta_step = HEIGHT_EDIT_DELTA_DEFAULT
        self.height_brush_radius = 2
        self._height_painting = False
        self._height_paint_last: tuple[int, int] | None = None
        self._edit_paint_rng = random.Random(0xED17)

        self.world = World()
        self.camera = Camera()
        self.height_sample = generate_height_sample(
            self.world.cols,
            self.world.rows,
            seed=self.world.seed,
            corners=self.world.height_corners,
        )
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
        self.ticks_per_day = TICKS_PER_DAY
        set_ticks_per_day(self.ticks_per_day)
        self.calendar_day = 0
        self.day_tick = self.ticks_per_day
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
        # Cyclic env layers (8×/year): biodiversity → pest-control modifiers.
        self.env_maps = EnvMaps.blank(self.world.rows, self.world.cols)
        # Compat aliases used by overlay draw / older diagnostics.
        self._biodiversity_samples = self.env_maps.biodiversity_samples
        self._biodiversity_average = self.env_maps.biodiversity
        # Rebuilt at most once per sim tick; avoids full-map forage scans per villager.
        self._forage_cell_index: dict[str, list[tuple[int, int]]] | None = None
        self._minimap_terrain: pygame.Surface | None = None
        self._minimap_terrain_key: tuple[int, int, int] | None = None
        # Villager wear map: cell → cumulative traffic (decayed on env sample).
        self._path_traffic: dict[tuple[int, int], float] = {}

        self._give_starting_resources()
        self._ensure_core_buildings()
        self.wildlife.refresh_habitats(self.world)
        self.wildlife.seed_breeding_grounds(self.world)
        self._sample_environment()
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
        # Season-neutral tiled map + water/grass/soil alpha masks; seasonal tint at blit.
        self._terrain_base: pygame.Surface | None = None
        self._terrain_base_key: tuple | None = None
        self._terrain_water_mask: pygame.Surface | None = None
        self._terrain_grass_mask: pygame.Surface | None = None
        self._terrain_soil_mask: pygame.Surface | None = None
        self._farm_cells_cached: set[tuple[int, int]] = set()
        self._season_mute: pygame.Surface | None = None
        self._season_mute_key: float | None = None
        self._ice_overlay: pygame.Surface | None = None
        self._ice_overlay_key: float | None = None
        self._lake_ice_mask: pygame.Surface | None = None
        self._lake_ice_mask_key: int | None = None
        self._season_period_overlay: pygame.Surface | None = None
        self._season_mask_period_key: tuple | None = None
        # Six seed-stable density fields; cycle tints/masks + crossfade.
        self._season_densities: dict[str, pygame.Surface | None] = {
            k: None
            for k in (
                "speckle_light",
                "speckle_med",
                "speckle_heavy",
                "cluster_light",
                "cluster_med",
                "cluster_heavy",
            )
        }
        self._season_density_key: tuple | None = None
        self._season_density_gen = None
        self._season_density_bake_step = 0
        self._season_density_baking: pygame.Surface | None = None
        self._season_cluster_stamps: dict = {}
        self._season_type_masks: dict = {}
        self._season_fade_from: int | None = None
        self._season_fade_to: int | None = None
        self._season_fade_tick = 0
        self._season_fade_from_only: pygame.Surface | None = None
        self._season_fade_to_only: pygame.Surface | None = None
        self._season_fade_shared: pygame.Surface | None = None
        self._season_fade_shared_bucket = -1
        self._season_fade_present_bucket = -1
        self._season_tree_halo: pygame.Surface | None = None
        self._season_tree_halo_key: tuple | None = None
        self._season_tree_sig: int | None = None
        self._season_check_trees = False
        # F6: deterministic autotile diagnostic scene + per-cell mask overlay.
        self.autotile_diag = False
        self._diag_cell_meta: dict[tuple[int, int], dict] = {}
        self._diag_backup_cells: list[list] | None = None

    def _give_starting_resources(self) -> None:
        self.home_storage.logs = STARTING_WOOD
        self.home_storage.rock = STARTING_ROCK
        self.home_storage.berries = STARTING_FOOD

    def _ensure_core_buildings(self) -> None:
        """Ensure HOME and WORKSTATION buildings exist at their world positions."""
        pw, ph = default_building_plot(BuildingKind.HOME)
        half_w, half_h = pw // 2, ph // 2

        def _sync_core(kind: BuildingKind, centre: tuple[int, int]) -> Building:
            building = next((b for b in self.buildings.values() if b.kind == kind), None)
            cx, cy = centre
            ox, oy = cx - half_w, cy - half_h
            if building is None:
                building = Building(
                    id=self.next_building_id,
                    kind=kind,
                    x=ox,
                    y=oy,
                    plot_w=pw,
                    plot_h=ph,
                )
                from entities import apply_building_storage

                apply_building_storage(building)
                self.buildings[building.id] = building
                self.next_building_id += 1
            else:
                building.x, building.y = ox, oy
                building.plot_w, building.plot_h = pw, ph
            feature = FEATURE_FOR_BUILDING[kind]
            self.world.claim_structure_footprint(ox, oy, pw, ph, feature)
            return building

        # Keep hiring hall clear of the storehouse footprint on legacy saves.
        hx, hy = self.world.home_pos
        sx, sy = self.world.workstation_pos
        if max(abs(sx - hx), abs(sy - hy)) < pw:
            sx = hx + pw
            if sx + half_w >= self.world.cols:
                sx = hx - pw
            sy = hy
            self.world.workstation_pos = (sx, sy)

        _sync_core(BuildingKind.HOME, self.world.home_pos)
        _sync_core(BuildingKind.WORKSTATION, self.world.workstation_pos)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def run(self) -> None:
        pygame.key.set_repeat(180, 40)
        while self.running:
            dt = self.clock.get_time() / 1000.0
            self._handle_events()
            self._sync_camera_height_overscan()
            self._update_camera_input(dt)
            self.camera.update(dt, self.world.cols, self.world.rows)
            self.player.update_visual(dt, PLAYER_VIS_SPEED)
            if self.sim_speed > 0:
                for _ in range(self.sim_speed):
                    self._update_simulation()
            self._update_status_timer()
            self._draw()
            self.clock.tick(FPS)
        pygame.quit()

    def _update_camera_input(self, dt: float) -> None:
        """Continuous WASD panning (smooth, not cell-stepped)."""
        if self.headless:
            return
        if (
            self.file_dialog.open
            or self.field_plan_dialog.open
            or self.building_inspect.open
            or self.villager_inspect.open
            or self.resource_inspect.open
            or self.resource_tracker.open
            or self.balance_dialog.open
            or self.habitat_inspect.open
        ):
            return
        keys = pygame.key.get_pressed()
        dx = float(keys[pygame.K_d]) - float(keys[pygame.K_a])
        dy = float(keys[pygame.K_s]) - float(keys[pygame.K_w])
        if dx or dy:
            self.camera.pan_continuous(dx, dy, dt, self.world.cols, self.world.rows)

    def reset(self) -> None:
        self.world.reset()
        self.height_sample = generate_height_sample(
            self.world.cols,
            self.world.rows,
            seed=self.world.seed,
            corners=self.world.height_corners,
        )
        self._invalidate_height_sample_cache()
        self.height_edit_mode = False
        self._height_painting = False
        self._height_paint_last = None
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
        self.day_tick = self.ticks_per_day
        set_ticks_per_day(self.ticks_per_day)
        self.resource_history.reset()
        self.file_dialog.close()
        self.field_plan_dialog.close()
        self.building_inspect.close()
        self.villager_inspect.close()
        self.resource_inspect.close()
        self.resource_tracker.close()
        self.balance_dialog.close()
        self.habitat_inspect.close()
        self.drawing = False
        self.draw_start = None
        self.draw_current = None
        self._mouse_down_cell = None
        self._placing_field = False
        self.overlay_mode = OverlayMode.NONE
        self.env_maps.resize(self.world.rows, self.world.cols)
        self._biodiversity_samples = self.env_maps.biodiversity_samples
        self._biodiversity_average = self.env_maps.biodiversity
        self._give_starting_resources()
        self._ensure_core_buildings()
        self._food_rng.seed(99)
        self.wildlife.refresh_habitats(self.world)
        self.wildlife.seed_breeding_grounds(self.world)
        self._sample_environment()
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
        self.resource_tracker.close()
        self.habitat_inspect.close()

    def record_produced(self, key: str, amount: int = 1) -> None:
        self.resource_history.record_produced(key, amount)

    def record_consumed(self, key: str, amount: int = 1) -> None:
        self.resource_history.record_consumed(key, amount)

    def _village_stock_amounts(self) -> dict[str, int]:
        """Storehouse + building storage totals (same scope as resource bar Total)."""
        from resources import amounts_from_obj, merge_amounts

        parts = [amounts_from_obj(self.home_storage)]
        parts.extend(amounts_from_obj(b) for b in self.buildings.values())
        return merge_amounts(*parts)

    def _apply_recipe_tracked(
        self, storage: object, recipe, *, fuel_wood: int = 0
    ) -> None:
        apply_recipe(storage, recipe)
        for key, n in recipe.inputs.items():
            self.record_consumed(key, n)
        for key, n in recipe.outputs.items():
            self.record_produced(key, n)
        if fuel_wood > 0:
            self.record_consumed("wood", fuel_wood)

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
                if self.resource_tracker.open and self.resource_tracker.handle_keydown(
                    event
                ):
                    continue
                if self.balance_dialog.open and self.balance_dialog.handle_keydown(
                    event
                ):
                    continue
                if self.habitat_inspect.open and self.habitat_inspect.handle_keydown(
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
                if self.resource_tracker.open and self.resource_tracker.contains(
                    event.pos
                ):
                    self.resource_tracker.handle_mousedown(event.pos)
                    continue
                if self.balance_dialog.open and self.balance_dialog.contains(
                    event.pos
                ):
                    self.balance_dialog.handle_mousedown(event.pos)
                    continue
                if self.habitat_inspect.open and self.habitat_inspect.contains(
                    event.pos
                ):
                    self.habitat_inspect.handle_mousedown(event.pos)
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
                if self.resource_tracker.open and self.resource_tracker._moving:
                    self.resource_tracker.handle_mouseup(event.pos)
                    continue
                if self.balance_dialog.open:
                    self.balance_dialog.handle_mouseup(event.pos, self.balance)
                    continue
                if self.habitat_inspect.open and self.habitat_inspect._moving:
                    self.habitat_inspect.handle_mouseup(event.pos)
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
                if self.resource_tracker.open and self.resource_tracker._moving:
                    self.resource_tracker.handle_mousemotion(event.pos)
                    continue
                if self.balance_dialog.open and self.balance_dialog._moving:
                    self.balance_dialog.handle_mousemotion(event.pos)
                    continue
                if self.habitat_inspect.open and self.habitat_inspect._moving:
                    self.habitat_inspect.handle_mousemotion(event.pos)
                    continue
                if self.building_inspect.open:
                    self.building_inspect.handle_mousemotion(event.pos)
                if self.villager_inspect.open:
                    self.villager_inspect.handle_mousemotion(event.pos)
                if self.resource_inspect.open:
                    self.resource_inspect.handle_mousemotion(event.pos)
                if self.resource_tracker.open:
                    self.resource_tracker.handle_mousemotion(event.pos)
                if self.drawing or self._height_painting:
                    self._on_mouse_drag(event.pos)
            elif event.type == pygame.MOUSEWHEEL:
                if self.file_dialog.open:
                    self.file_dialog.handle_mousewheel(event.y)
                    continue
                if self.field_plan_dialog.open and self.field_plan_dialog.contains(
                    pygame.mouse.get_pos()
                ):
                    continue
                if self.building_inspect.open and self.building_inspect.contains(
                    pygame.mouse.get_pos()
                ):
                    self.building_inspect.handle_mousewheel(
                        event.y, pygame.mouse.get_pos()
                    )
                    continue
                if self.villager_inspect.open and self.villager_inspect.contains(
                    pygame.mouse.get_pos()
                ):
                    continue
                if self.resource_inspect.open and self.resource_inspect.contains(
                    pygame.mouse.get_pos()
                ):
                    continue
                if self.resource_tracker.open and self.resource_tracker.handle_mousewheel(
                    event.y, pygame.mouse.get_pos()
                ):
                    continue
                if self.balance_dialog.open and self.balance_dialog.handle_mousewheel(
                    event.y
                ):
                    continue
                mx, my = pygame.mouse.get_pos()
                if mx >= map_view_width() and my >= MAP_OFFSET_Y:
                    self.ui.scroll(event.y * 28)
                else:
                    # Zoom camera over map (not over minimap, not over dialogs).
                    # Height-edit still zooms; brush/value use [ ] and +/-.
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
                self._invalidate_forage_index()
                self._minimap_terrain = None
                self._minimap_terrain_key = None
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
            if self.resource_tracker.open:
                self.resource_tracker.close()
            if self.balance_dialog.open:
                self.balance_dialog.close()
                return
            if self.habitat_inspect.open:
                self.habitat_inspect.close()
                return
            if self.height_edit_mode:
                self._toggle_height_edit()
                return
            if (
                self.selected_building_id is not None
                or self.selected_villager_id is not None
                or self.selected_habitat_id is not None
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
        elif key == pygame.K_h:
            if self.height_edit_mode:
                self._set_status("Exit map edit (Y) before toggling warp (H).")
            else:
                self._toggle_height_sample()
        elif key == pygame.K_y:
            self._toggle_height_edit()
        elif self.height_edit_mode and key in (
            pygame.K_EQUALS,
            pygame.K_PLUS,
            pygame.K_KP_PLUS,
        ):
            if self.map_edit_tool in (
                MapEditTool.HEIGHT_RAISE,
                MapEditTool.HEIGHT_LOWER,
            ):
                self._adjust_height_delta_step(HEIGHT_EDIT_VALUE_STEP)
            else:
                self._adjust_height_paint_value(HEIGHT_EDIT_VALUE_STEP)
        elif self.height_edit_mode and key in (
            pygame.K_MINUS,
            pygame.K_KP_MINUS,
        ):
            if self.map_edit_tool in (
                MapEditTool.HEIGHT_RAISE,
                MapEditTool.HEIGHT_LOWER,
            ):
                self._adjust_height_delta_step(-HEIGHT_EDIT_VALUE_STEP)
            else:
                self._adjust_height_paint_value(-HEIGHT_EDIT_VALUE_STEP)
        elif self.height_edit_mode and key == pygame.K_0:
            self.height_paint_value = 0.0
            self._set_status(self._height_edit_status())
        elif self.height_edit_mode and key == pygame.K_LEFTBRACKET:
            self._adjust_height_brush(-1)
        elif self.height_edit_mode and key == pygame.K_RIGHTBRACKET:
            self._adjust_height_brush(1)
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
        elif key == pygame.K_7:
            self._set_overlay(OverlayMode.FLORAL_RESOURCES)
        elif key == pygame.K_8:
            self._set_overlay(OverlayMode.POLLINATION)
        elif key == pygame.K_9:
            self._set_overlay(OverlayMode.PATH_TRAFFIC)
        elif key in (pygame.K_LEFTBRACKET, pygame.K_COMMA):
            self._cycle_ticks_per_day(-1)
        elif key in (pygame.K_RIGHTBRACKET, pygame.K_PERIOD):
            self._cycle_ticks_per_day(1)
        elif key == pygame.K_F6:
            self._toggle_autotile_diagnostic()
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
        if self._minimap_rect().collidepoint(pos):
            return None
        flat = self.camera.screen_to_world_float(mx, my)
        if flat is None:
            return None
        fx, fy = flat
        ix, iy = int(fx), int(fy)
        # Height-edit forces warp off; keep flat picking there.
        if (
            not self.height_sample_enabled
            or self.height_sample is None
            or self.height_edit_mode
        ):
            if not self.world.in_bounds(ix, iy):
                return None
            return ix, iy
        return self._map_cell_from_pos_height(mx, my, fx, fy)

    @staticmethod
    def _point_in_convex_quad(
        px: float, py: float, pts: list[tuple[int, int]]
    ) -> bool:
        """True if (px, py) is inside a convex quad (screen space)."""
        sign = 0
        n = len(pts)
        for i in range(n):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % n]
            cross = (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)
            if cross == 0:
                continue
            s = 1 if cross > 0 else -1
            if sign == 0:
                sign = s
            elif s != sign:
                return False
        return True

    def _map_cell_from_pos_height(
        self,
        mx: int,
        my: int,
        fx: float,
        fy: float,
    ) -> tuple[int, int] | None:
        """Pick the height-warped cell under the cursor (flat pick is biased north)."""
        peak = self.height_sample.max_height if self.height_sample is not None else 0.0
        search = max(3, int(math.ceil(peak * HEIGHT_LIFT_PX / CELL_SIZE)) + 2)
        x_mid = int(fx)
        y_mid = int(fy)
        best: tuple[int, int] | None = None
        best_y = -10**9
        # Prefer southern hits — drawn later / in front on slopes.
        for dy in range(-1, search + 1):
            for dx in range(-2, 3):
                x = x_mid + dx
                y = y_mid + dy
                if not self.world.in_bounds(x, y):
                    continue
                pts = self._cell_quad_points(x, y)
                if self._point_in_convex_quad(mx, my, pts) and y >= best_y:
                    best = (x, y)
                    best_y = y
        if best is not None:
            return best
        if self.world.in_bounds(x_mid, y_mid):
            return x_mid, y_mid
        return None

    def _sync_camera_height_overscan(self) -> None:
        """Allow scrolling north so lifted peaks are not clipped under the toolbar."""
        if self.height_sample_enabled and self.height_sample is not None:
            peak = max(0.0, float(self.height_sample.max_height))
            self.camera.y_overscan = peak * HEIGHT_LIFT_PX / float(CELL_SIZE) + 0.75
        else:
            self.camera.y_overscan = 0.0
            if self.camera.y < 0.0:
                self.camera.y = 0.0
                self.camera.clamp(self.world.cols, self.world.rows)

    def _cell_rect(self, x: int, y: int) -> pygame.Rect:
        """Return screen rect for given world cell coordinates."""
        rect = self.camera.cell_rect(x, y)
        dy = self._height_screen_lift(float(x) + 0.5, float(y) + 0.5)
        if dy:
            rect = rect.move(0, -int(round(dy)))
        return rect

    def _cell_center(self, x: float, y: float) -> tuple[int, int]:
        """Return screen center point for given world cell coordinates (may be fractional)."""
        cx, cy = self.camera.world_to_screen(float(x) + 0.5, float(y) + 0.5)
        dy = self._height_screen_lift(float(x) + 0.5, float(y) + 0.5)
        return cx, cy - int(round(dy))

    def _toggle_height_sample(self) -> None:
        self.height_sample_enabled = not self.height_sample_enabled
        self._sync_camera_height_overscan()
        if self.height_sample_enabled:
            self.height_sample = generate_height_sample(
                self.world.cols,
                self.world.rows,
                seed=self.world.seed,
                corners=self.world.height_corners,
            )
            self._invalidate_height_sample_cache()
            self._set_status(
                f"Height warp ON (full map, head={int(self.height_sample.max_height)}) — H to toggle"
            )
        else:
            self._invalidate_height_sample_cache()
            self._set_status("Height warp OFF — H to toggle")

    def _height_edit_status(self) -> str:
        tool = self.map_edit_tool
        brush = self.height_brush_radius
        if tool == MapEditTool.HEIGHT_SET:
            return (
                f"Set height={self.height_paint_value:.0f}  brush={brush}  "
                f"(drag paint · panel tools · Y exit)"
            )
        if tool == MapEditTool.HEIGHT_RAISE:
            return (
                f"Raise +{self.height_delta_step:.0f}  brush={brush}  "
                f"(drag · panel tools · Y exit)"
            )
        if tool == MapEditTool.HEIGHT_LOWER:
            return (
                f"Lower -{self.height_delta_step:.0f}  brush={brush}  "
                f"(drag · panel tools · Y exit)"
            )
        if tool == MapEditTool.TERRAIN_PAINT:
            label = TERRAIN_EDIT_LABELS.get(
                self.map_edit_terrain, self.map_edit_terrain.name.title()
            )
            return f"Paint {label}  brush={brush}  (drag · panel tools · Y exit)"
        return f"Seed forest  brush={brush}  (drag · panel tools · Y exit)"

    @staticmethod
    def _height_heatmap_colour(t: float) -> tuple[int, int, int]:
        """Blue → cyan → green → yellow → red for t in 0..1."""
        t = max(0.0, min(1.0, t))
        stops = (
            (0.0, (40, 80, 200)),
            (0.25, (40, 180, 200)),
            (0.5, (60, 190, 70)),
            (0.75, (230, 200, 40)),
            (1.0, (220, 60, 40)),
        )
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t <= t1 or i == len(stops) - 2:
                u = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)
                u = max(0.0, min(1.0, u))
                return (
                    int(c0[0] + (c1[0] - c0[0]) * u),
                    int(c0[1] + (c1[1] - c0[1]) * u),
                    int(c0[2] + (c1[2] - c0[2]) * u),
                )
        return stops[-1][1]

    def _toggle_height_edit(self) -> None:
        self.height_edit_mode = not self.height_edit_mode
        if self.height_edit_mode:
            self._height_warp_before_edit = self.height_sample_enabled
            self.height_sample_enabled = False
            self._invalidate_height_sample_cache()
            self.place_kind = None
            self._clear_selection()
            self.world.ensure_height_corners()
            self._set_status(self._height_edit_status())
        else:
            self._height_painting = False
            self._sync_height_sample_from_world()
            self.height_sample_enabled = self._height_warp_before_edit
            if self.height_sample_enabled:
                self._invalidate_height_sample_cache()
                self._set_status("Map edit OFF — warp restored (H to toggle)")
            else:
                self._set_status("Map edit OFF — Y to edit, H for warp")

    def _set_map_edit_tool(self, tool: MapEditTool) -> None:
        self.map_edit_tool = tool
        self._set_status(self._height_edit_status())

    def _adjust_height_paint_value(self, delta: float) -> None:
        self.height_paint_value = max(
            0.0,
            min(HEIGHT_EDIT_VALUE_MAX, self.height_paint_value + delta),
        )
        self._set_status(self._height_edit_status())

    def _adjust_height_delta_step(self, delta: float) -> None:
        self.height_delta_step = max(
            1.0,
            min(HEIGHT_EDIT_VALUE_MAX, self.height_delta_step + delta),
        )
        self._set_status(self._height_edit_status())

    def _adjust_height_brush(self, delta: int) -> None:
        self.height_brush_radius = max(
            HEIGHT_EDIT_BRUSH_MIN,
            min(HEIGHT_EDIT_BRUSH_MAX, self.height_brush_radius + delta),
        )
        self._set_status(self._height_edit_status())

    def _sync_height_sample_from_world(self) -> None:
        self.world.ensure_height_corners()
        self.height_sample = generate_height_sample(
            self.world.cols,
            self.world.rows,
            seed=self.world.seed,
            corners=self.world.height_corners,
        )
        self._invalidate_height_sample_cache()

    def _paint_height_at(self, x: int, y: int) -> None:
        """Dispatch the active map-edit brush stamp at cell (x, y)."""
        if not self.world.in_bounds(x, y):
            return
        if self._height_paint_last == (x, y):
            return
        self._height_paint_last = (x, y)
        tool = self.map_edit_tool
        r = self.height_brush_radius
        if tool == MapEditTool.HEIGHT_SET:
            self.world.paint_height(x, y, self.height_paint_value, r)
            self._sync_height_corners_peak()
        elif tool == MapEditTool.HEIGHT_RAISE:
            self.world.paint_height_delta(
                x,
                y,
                self.height_delta_step,
                r,
                max_h=HEIGHT_EDIT_VALUE_MAX,
            )
            self._sync_height_corners_peak()
        elif tool == MapEditTool.HEIGHT_LOWER:
            self.world.paint_height_delta(
                x,
                y,
                -self.height_delta_step,
                r,
                max_h=HEIGHT_EDIT_VALUE_MAX,
            )
            self._sync_height_corners_peak()
        elif tool == MapEditTool.TERRAIN_PAINT:
            self.world.paint_terrain(x, y, self.map_edit_terrain, r)
        elif tool == MapEditTool.SEED_FOREST:
            self.world.seed_forest(x, y, r, self._edit_paint_rng)

    def _sync_height_corners_peak(self) -> None:
        if self.height_sample is not None:
            self.height_sample.corners = self.world.height_corners
            peak = 0.0
            for row in self.world.height_corners:
                for v in row:
                    if v > peak:
                        peak = v
            self.height_sample.max_height = peak
        self._invalidate_height_sample_cache()

    def _invalidate_height_sample_cache(self) -> None:
        self._height_sample_cache = None
        self._height_sample_cache_key = None
        self._height_cache_bounds = None

    def _ensure_height_sample_cache(
        self,
        ground: pygame.Surface,
        *,
        region: HeightSample,
    ) -> None:
        if not self.height_sample_enabled or self.height_sample is None:
            return
        # Height is static; do NOT key on terrain_revision (paths bump that daily).
        key = (
            CELL_SIZE,
            region.x0,
            region.y0,
            region.width,
            region.height,
            id(self.height_sample),
            round(self.height_sample.max_height, 2),
        )
        if self._height_sample_cache is not None and self._height_sample_cache_key == key:
            return
        surf, pad = bake_height_sample_surface(
            region, ground, cell_size=CELL_SIZE
        )
        self._height_sample_cache = surf
        self._height_sample_cache_pad = pad
        self._height_sample_cache_key = key
        self._height_cache_bounds = (
            region.x0,
            region.y0,
            region.x1,
            region.y1,
        )

    def _patch_height_warp_cells(self, cells: list[tuple[int, int]]) -> None:
        """Terrain pixels changed under an existing height warp.

        Intentionally a no-op: invalidating here forced a full-map height rebake
        (~700ms) on env-sample dirties and path reverts — catastrophic at low
        ticks/day. Warp geometry is static; colour can lag until the next height
        edit or H toggle.
        """
        return

    def _height_sample_ground_composite(
        self,
        base: pygame.Surface,
        *,
        region: HeightSample,
    ) -> pygame.Surface:
        """Region footprint for warp bake: terrain base only.

        Season flecks, ice, and mute are applied after the warp blit so calendar
        drift does not force expensive height rebakes.
        """
        area = pygame.Rect(
            region.x0 * CELL_SIZE,
            region.y0 * CELL_SIZE,
            region.width * CELL_SIZE,
            region.height * CELL_SIZE,
        ).clip(base.get_rect())
        ground = pygame.Surface(
            (region.width * CELL_SIZE, region.height * CELL_SIZE), depth=24
        )
        ground.fill((40, 55, 35))
        if area.w > 0 and area.h > 0:
            dest = (area.x - region.x0 * CELL_SIZE, area.y - region.y0 * CELL_SIZE)
            ground.blit(base.subsurface(area), dest)
        return ground

    def _height_view_region(self) -> HeightSample | None:
        """Full-map sample — bake once; pan/zoom only re-blits."""
        return self.height_sample

    def _height_screen_lift(self, wx: float, wy: float) -> float:
        if not self.height_sample_enabled or self.height_sample is None:
            return 0.0
        h = self.height_sample.height_world(wx, wy)
        if h <= 0.0:
            return 0.0
        return screen_lift_px(h, self.camera.view_cell(), float(CELL_SIZE))

    def _screen_world_point(self, wx: float, wy: float) -> tuple[int, int]:
        """Screen pixel for a continuous world cell corner/point, with height lift."""
        sx, sy = self.camera.world_to_screen(wx, wy)
        dy = self._height_screen_lift(wx, wy)
        return sx, sy - int(round(dy))

    def _cell_quad_points(self, x: int, y: int) -> list[tuple[int, int]]:
        return [
            self._screen_world_point(x, y),
            self._screen_world_point(x + 1, y),
            self._screen_world_point(x + 1, y + 1),
            self._screen_world_point(x, y + 1),
        ]

    def _draw_height_quad(
        self,
        x: int,
        y: int,
        colour: tuple[int, int, int],
        alpha: int,
    ) -> None:
        """Fill a cell as a height-warped quad (for overlays / placement tints)."""
        pts = self._cell_quad_points(x, y)
        min_x = min(p[0] for p in pts)
        min_y = min(p[1] for p in pts)
        max_x = max(p[0] for p in pts)
        max_y = max(p[1] for p in pts)
        w = max(1, max_x - min_x + 1)
        h = max(1, max_y - min_y + 1)
        local = [(p[0] - min_x, p[1] - min_y) for p in pts]
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.polygon(surf, (*colour, alpha), local)
        self.screen.blit(surf, (min_x, min_y))

    def _plot_outline_points(
        self, left: int, top: int, right: int, bottom: int
    ) -> list[tuple[int, int]]:
        """Perimeter polyline following terrain height along cell edges."""
        pts: list[tuple[int, int]] = []
        for x in range(left, right + 1):
            pts.append(self._screen_world_point(x, top))
        pts.append(self._screen_world_point(right + 1, top))
        for y in range(top + 1, bottom + 1):
            pts.append(self._screen_world_point(right + 1, y))
        pts.append(self._screen_world_point(right + 1, bottom + 1))
        for x in range(right, left - 1, -1):
            pts.append(self._screen_world_point(x, bottom + 1))
        pts.append(self._screen_world_point(left, bottom + 1))
        for y in range(bottom, top, -1):
            pts.append(self._screen_world_point(left, y))
        return pts

    def _flat_cell_rect(self, x: int, y: int) -> pygame.Rect:
        """Screen rect without height lift (for covering baked terrain)."""
        return self.camera.cell_rect(x, y)

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
        if self.height_edit_mode:
            self._height_painting = True
            self._height_paint_last = None
            self._paint_height_at(cell[0], cell[1])
            return
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
            if self.height_edit_mode and self._height_painting:
                self._paint_height_at(cell[0], cell[1])

    def _on_mouse_up(self, pos: tuple[int, int]) -> None:
        end = self._map_cell_from_pos(pos) or self.draw_current or self._mouse_down_cell
        start = self.draw_start or self._mouse_down_cell
        was_drawing = self.drawing
        was_height_painting = self._height_painting
        placing_field = self._placing_field
        self.drawing = False
        self._placing_field = False
        self._height_painting = False
        self._height_paint_last = None
        self.draw_start = None
        self.draw_current = None
        down = self._mouse_down_cell
        self._mouse_down_cell = None

        if was_height_painting:
            return

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
        if action is not None and action.startswith("edit_tool:"):
            key = action.split(":", 1)[1]
            try:
                self._set_map_edit_tool(MapEditTool(key))
            except ValueError:
                pass
            return True
        if action is not None and action.startswith("edit_terrain:"):
            name = action.split(":", 1)[1]
            try:
                terrain = TerrainType[name]
            except KeyError:
                return True
            if terrain in EDIT_PAINTABLE_TERRAIN:
                self.map_edit_terrain = terrain
                self.map_edit_tool = MapEditTool.TERRAIN_PAINT
                self._set_status(self._height_edit_status())
            return True
        if action is not None and action.startswith("edit_value:"):
            raw = action.split(":", 1)[1]
            if raw == "0":
                self.height_paint_value = 0.0
                self._set_status(self._height_edit_status())
            else:
                self._adjust_height_paint_value(float(raw))
            return True
        if action is not None and action.startswith("edit_delta:"):
            self._adjust_height_delta_step(float(action.split(":", 1)[1]))
            return True
        if action is not None and action.startswith("edit_brush:"):
            self._adjust_height_brush(int(action.split(":", 1)[1]))
            return True
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
        if kind == "bee_ground":
            self._select_habitat(AnimalKind.BEE, item_id)
            return True
        if kind == "rabbit_ground":
            self._select_habitat(AnimalKind.RABBIT, item_id)
            return True
        return False

    def _select_habitat(self, kind: AnimalKind, patch_id: int) -> None:
        hab = self.wildlife.habitat(patch_id, kind)
        if hab is None:
            return
        breed = self.wildlife._breeding_for(kind, hab)
        if not breed:
            return
        self.selected_building_id = None
        self.selected_villager_id = None
        self.selected_habitat_kind = kind
        self.selected_habitat_id = patch_id
        self.building_inspect.close()
        self.villager_inspect.close()
        self.resource_inspect.close()
        self.field_plan_dialog.close()
        cx = sum(p[0] for p in breed) // len(breed)
        cy = sum(p[1] for p in breed) // len(breed)
        self.camera.center_on(cx, cy, self.world.cols, self.world.rows)
        screen_xy = self.camera.world_to_screen(cx, cy)
        self.habitat_inspect.open_for(kind, patch_id, screen_xy=screen_xy)

    def _habitat_inspect_view(self) -> HabitatInspectView | None:
        if self.selected_habitat_id is None or self.selected_habitat_kind is None:
            return None
        kind = self.selected_habitat_kind
        patch_id = self.selected_habitat_id
        hab = self.wildlife.habitat(patch_id, kind)
        if hab is None:
            return None
        from resource_balance import (
            ANIMAL_BREED_CHANCE,
            COLONY_GROW_CHANCE,
            COLONY_LEVEL_MAX,
        )
        from wildlife import COLONY_KINDS, OpenHabitat
        from world import disturbance_activity_multiplier, effective_disturbance_at

        label = {
            AnimalKind.DEER: "Deer breeding ground",
            AnimalKind.BOAR: "Boar breeding ground",
            AnimalKind.BEE: "Bee nest",
            AnimalKind.RABBIT: "Rabbit warren",
        }.get(kind, kind.name.title())
        breed = self.wildlife._breeding_for(kind, hab)
        roam = self.wildlife._cold_roaming_for(kind, hab)
        breed_set = set(breed)
        roam_only = roam - breed_set
        sample_cells = list(breed_set | roam)
        if not sample_cells:
            return None

        dist_values = [
            effective_disturbance_at(self.world, x, y) for x, y in sample_cells
        ]
        avg_dist = sum(dist_values) / len(dist_values)
        max_dist = max(dist_values)
        ecology = disturbance_activity_multiplier(avg_dist)

        bio = self.env_maps.farm_biodiversity(sample_cells)
        floral = self.env_maps.farm_floral(sample_cells)
        poll = self.env_maps.farm_pollination(sample_cells)
        benefits: list[tuple[str, str]] = [
            ("Biodiversity", f"{bio * 100:.0f}%"),
            ("Floral resources", f"{floral * 100:.0f}%"),
        ]
        if kind == AnimalKind.BEE:
            benefits.append(("Pollination (nest)", f"{poll * 100:.0f}%"))
        elif isinstance(hab, OpenHabitat):
            benefits.append(("Forage tiles", str(len(hab.forage_tiles))))
        else:
            benefits.append(("Forest patch", f"{len(hab.forest_tiles)} cells"))

        cap = self.wildlife._cap_for(kind, hab)
        if kind in COLONY_KINDS:
            colony = self.wildlife._colony_on_habitat(kind, patch_id)
            if colony is None:
                population = "Empty nest"
                pop_factor = 0.35
            else:
                population = (
                    f"Level {colony.level}/{COLONY_LEVEL_MAX} · "
                    f"{colony.target_members()} visible"
                )
                pop_factor = colony.level / float(COLONY_LEVEL_MAX)
            base_breed = COLONY_GROW_CHANCE
            subtitle = f"Nest #{patch_id} · open habitat"
        else:
            _present, migrating, total, pairs = self.wildlife.patch_occupancy(
                kind, patch_id
            )
            pair_txt = f"{pairs} pair" if pairs == 1 else f"{pairs} pairs"
            if migrating:
                population = f"{total}/{cap} · {pair_txt} · {migrating} migrating"
            else:
                population = f"{total}/{cap} · {pair_txt}"
            pop_factor = min(1.0, total / cap) if cap > 0 else 0.0
            base_breed = ANIMAL_BREED_CHANCE
            subtitle = f"Ground #{patch_id} · forest patch"

        benefit_factor = 0.55 + 0.45 * min(1.0, bio)
        health = max(0.0, min(100.0, 100.0 * ecology * pop_factor * benefit_factor))
        breed_pct = base_breed * ecology * 100.0

        return HabitatInspectView(
            title=label,
            subtitle=subtitle,
            population=population,
            breeding_tiles=len(breed_set),
            roam_tiles=len(roam_only),
            avg_disturbance=avg_dist,
            max_disturbance=max_dist,
            ecology_mult=ecology,
            breed_chance_pct=breed_pct,
            health_pct=health,
            benefits=benefits,
        )

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
            BuildingKind.MILL,
            BuildingKind.KITCHEN,
            BuildingKind.CRAFT_BENCH,
            BuildingKind.ALCHEMIST,
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
            BuildingKind.MILL: (MILL_COST_WOOD, MILL_COST_ROCK, "Mill"),
            BuildingKind.KITCHEN: (KITCHEN_COST_WOOD, KITCHEN_COST_ROCK, "Kitchen"),
            BuildingKind.CRAFT_BENCH: (
                CRAFT_BENCH_COST_WOOD,
                CRAFT_BENCH_COST_ROCK,
                "Craft bench",
            ),
            BuildingKind.ALCHEMIST: (
                ALCHEMIST_COST_WOOD,
                ALCHEMIST_COST_ROCK,
                "Alchemist",
            ),
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

    def _set_ticks_per_day(self, ticks: int) -> None:
        if ticks not in TICKS_PER_DAY_OPTIONS:
            return
        old = max(1, self.ticks_per_day)
        day_frac = 1.0 - (self.day_tick / old)
        self.ticks_per_day = set_ticks_per_day(ticks)
        self.day_tick = max(
            1, min(self.ticks_per_day, int(round(day_frac * self.ticks_per_day)))
        )
        secs = self.ticks_per_day / max(1, FPS)
        self._set_status(
            f"Day length: {self.ticks_per_day} ticks (~{secs:.1f}s at ×1) — "
            f"lower = faster calendar for path testing"
        )

    def _day_length_scale(self) -> float:
        """Scale tick-based intervals so villager moves/day stay ~constant."""
        return self.ticks_per_day / max(1, REFERENCE_TICKS_PER_DAY)

    def _cycle_ticks_per_day(self, delta: int) -> None:
        opts = TICKS_PER_DAY_OPTIONS
        try:
            idx = opts.index(self.ticks_per_day)
        except ValueError:
            idx = min(range(len(opts)), key=lambda i: abs(opts[i] - self.ticks_per_day))
        self._set_ticks_per_day(opts[(idx + delta) % len(opts)])

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
        self.resource_history.record_stock(self._village_stock_amounts())
        self.resource_history.advance_day()
        if self.season != prev:
            self._expire_unharvested_crops(prev)
            self._ripen_crops_for_harvest_season()
            if self.season == Season.WINTER:
                self.world.clear_mushrooms()
            self.wildlife.on_season_change(self.world, self.season)
            self._set_status(f"{format_date(self.calendar_day)} begins.")
        # Environmental layers: sample at season start (day 0) and midpoint.
        if is_env_sample_day(self.calendar_day):
            self._sample_environment()
            self._sync_habitat_selection()
        else:
            # Paint worn paths every in-game day; decay stays on the 8×/year env sample.
            self._update_path_terrain(decay_traffic=False)

    def _sample_environment(self) -> None:
        """8×/year: refresh habitats/forest floor and stable env production grids."""
        from wildlife import AnimalKind

        self.wildlife.refresh_habitats(self.world)
        self.world.update_forest_floor()
        self._refresh_hardscape_terrain(decay_traffic=True)
        # Seasonal overlays follow the same ≤8/year cadence (not daily).
        self._season_mask_period_key = None
        self._season_check_trees = True

        bee_nests = self._bee_nest_sites()
        bee_pos: list[tuple[int, int]] = []
        rabbit_pos: list[tuple[int, int]] = []
        for colony in self.wildlife.colonies:
            if colony.kind == AnimalKind.BEE:
                bee_pos.append((colony.x, colony.y))
                for m in colony.members:
                    bee_pos.append((m.x, m.y))
            elif colony.kind == AnimalKind.RABBIT:
                rabbit_pos.append((colony.x, colony.y))
                for m in colony.members:
                    rabbit_pos.append((m.x, m.y))

        self.env_maps.sample(
            self.world,
            deer_positions=((a.x, a.y) for a in self.wildlife.deer()),
            boar_positions=((a.x, a.y) for a in self.wildlife.boars()),
            fish_positions=((f.x, f.y) for f in self.fish.fish),
            bee_positions=bee_pos,
            rabbit_positions=rabbit_pos,
            bee_nests=bee_nests,
        )
        self._biodiversity_samples = self.env_maps.biodiversity_samples
        self._biodiversity_average = self.env_maps.biodiversity
        self._update_field_crop_health()
        if self.overlay_mode in (
            OverlayMode.BIODIVERSITY,
            OverlayMode.FLORAL_RESOURCES,
            OverlayMode.POLLINATION,
        ):
            self._refresh_indicators()

    def _update_field_crop_health(self) -> None:
        """Ratchet each Field's crop_health down toward the pest-control target.

        Health only decreases (sticky), at most CROP_HEALTH_MAX_DROP per sample,
        and never below CROP_HEALTH_MIN. Values crushed by the old harsh curve
        are lifted to the new floor.
        """
        from environment import CROP_HEALTH_MAX_DROP, CROP_HEALTH_MIN

        for building in self.buildings.values():
            if building.kind != BuildingKind.FIELD:
                continue
            cells = building.plot_cells()
            if not cells:
                continue
            pc = self.env_maps.farm_pest_control(cells)
            target = crop_health_cap_from_pest_control(pc)
            current = float(getattr(building, "crop_health", 1.0))
            # Lift out of the obsolete sub-floor range from the old formula.
            current = max(current, CROP_HEALTH_MIN)
            if current > target:
                current = max(target, current - CROP_HEALTH_MAX_DROP)
            building.crop_health = max(CROP_HEALTH_MIN, min(1.0, current))

    def _field_crop_health(self, field: Building) -> float:
        from environment import CROP_HEALTH_MIN

        return max(CROP_HEALTH_MIN, min(1.0, float(getattr(field, "crop_health", 1.0))))

    def _record_path_traffic(self, x: int, y: int) -> None:
        """Accumulate villager wear on a cell (every logical step)."""
        cell = self.world.get_cell(x, y)
        if cell is None or not hardscape_paintable(cell):
            return
        if cell.feature in BUILDING_FEATURES:
            return
        key = (x, y)
        step = self.balance.get_float("PATH_TRAFFIC_STEP")
        self._path_traffic[key] = float(self._path_traffic.get(key, 0.0)) + step

    @staticmethod
    def _cell_buildable(cell) -> bool:
        """Terrain may host a structure footprint (bare rock ground, not rock deposits)."""
        if cell.terrain in BUILDABLE_LAND:
            return True
        if is_bare_rock(cell):
            return True
        return False

    def _field_plot_cells(self) -> set[tuple[int, int]]:
        cells: set[tuple[int, int]] = set()
        for building in self.buildings.values():
            if building.kind == BuildingKind.FIELD:
                cells.update(building.plot_cells())
        for site in self.construction_sites.values():
            if site.kind == BuildingKind.FIELD:
                cells.update(site.plot_cells())
        return cells

    def _non_field_footprints(self) -> list[tuple[int, object]]:
        """Stable id + building/construction for urban clustering."""
        items: list[tuple[int, object]] = []
        for building in self.buildings.values():
            if building.kind != BuildingKind.FIELD:
                items.append((building.id, building))
        for site in self.construction_sites.values():
            if site.kind != BuildingKind.FIELD:
                items.append((1_000_000 + site.id, site))
        return items

    @staticmethod
    def _footprint_sets_touch(a: set[tuple[int, int]], b: set[tuple[int, int]]) -> bool:
        """Orthogonal adjacency only — diagonal gaps stay separate clusters."""
        for x, y in a:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if (x + dx, y + dy) in b:
                    return True
        return False

    @staticmethod
    def _cardinally_adjacent_to(
        x: int, y: int, cells: set[tuple[int, int]]
    ) -> bool:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if (x + dx, y + dy) in cells:
                return True
        return False

    def _hardscape_candidate(self, x: int, y: int) -> bool:
        if not self.world.in_bounds(x, y):
            return False
        if (x, y) in self._field_plot_cells():
            return False
        return hardscape_paintable(self.world.cells[y][x])

    def _revert_hardscape_terrain(self, x: int, y: int) -> TerrainType:
        if (x, y) in self._field_plot_cells():
            return TerrainType.SOIL
        cell = self.world.cells[y][x]
        if cell.terrain_shade < 0.0:
            cell.terrain_shade = 0.55
            return TerrainType.ROCK
        return TerrainType.GRASS

    def _set_hardscape_terrain(self, x: int, y: int, terrain: TerrainType) -> None:
        cell = self.world.cells[y][x]
        if not hardscape_paintable(cell):
            return
        if is_bare_rock(cell):
            cell.terrain_shade = -1.0
        cell.terrain = terrain
        self.world.mark_terrain_dirty(x, y)

    def _compute_urban_layout(self) -> set[tuple[int, int]]:
        """Urban cores (3+ building clusters); 1-cell gaps between clusters fill in."""
        field_cells = self._field_plot_cells()
        structures = self._non_field_footprints()
        if not structures:
            return set()

        cell_sets = [(sid, set(obj.plot_cells())) for sid, obj in structures]
        n = len(cell_sets)
        parent = list(range(n))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i: int, j: int) -> None:
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[rj] = ri

        for i in range(n):
            for j in range(i + 1, n):
                if self._footprint_sets_touch(cell_sets[i][1], cell_sets[j][1]):
                    union(i, j)

        clusters: dict[int, list[int]] = {}
        for i in range(n):
            clusters.setdefault(find(i), []).append(i)

        urban_cells: set[tuple[int, int]] = set()
        cluster_cores: list[tuple[int, set[tuple[int, int]]]] = []

        for members in clusters.values():
            if len(members) < self.balance.get_int("URBAN_MIN_BUILDINGS"):
                continue
            core: set[tuple[int, int]] = set()
            cluster_id = min(members)
            for idx in members:
                core |= cell_sets[idx][1]
            core -= field_cells
            if not core:
                continue
            urban_cells |= core
            cluster_cores.append((cluster_id, core))

        if len(cluster_cores) >= 2:
            for y in range(self.world.rows):
                for x in range(self.world.cols):
                    if (x, y) in urban_cells or (x, y) in field_cells:
                        continue
                    if not self._hardscape_candidate(x, y):
                        continue
                    touching: set[int] = set()
                    for cluster_id, core in cluster_cores:
                        if self._cardinally_adjacent_to(x, y, core):
                            touching.add(cluster_id)
                    if len(touching) >= 2:
                        urban_cells.add((x, y))

        return urban_cells

    def _refresh_hardscape_terrain(self, *, decay_traffic: bool = False) -> None:
        """Recompute urban patches and worn paths."""
        self._update_urban_terrain()
        self._update_path_terrain(decay_traffic=decay_traffic)
        self.world.sync_hardscape_disturbance()

    def _update_urban_terrain(self) -> None:
        """Paint URBAN for 3+ building clusters; merge 1-cell gaps; protect fields."""
        urban_cells = self._compute_urban_layout()
        field_cells = self._field_plot_cells()
        changed = False

        for x, y in urban_cells:
            cell = self.world.cells[y][x]
            if cell.terrain == TerrainType.URBAN:
                continue
            if (x, y) in field_cells or not hardscape_paintable(cell):
                continue
            self._set_hardscape_terrain(x, y, TerrainType.URBAN)
            changed = True

        for x, y in field_cells:
            cell = self.world.cells[y][x]
            if cell.terrain in (TerrainType.URBAN, TerrainType.PATH):
                cell.terrain = TerrainType.SOIL
                self.world.mark_terrain_dirty(x, y)
                changed = True

        for y in range(self.world.rows):
            for x in range(self.world.cols):
                if (x, y) in field_cells:
                    continue
                cell = self.world.cells[y][x]
                if cell.terrain == TerrainType.URBAN and (x, y) not in urban_cells:
                    wear = float(self._path_traffic.get((x, y), 0.0))
                    cell.terrain = (
                        TerrainType.PATH
                        if wear >= self.balance.get_float("PATH_TRAFFIC_THRESHOLD")
                        else self._revert_hardscape_terrain(x, y)
                    )
                    self.world.mark_terrain_dirty(x, y)
                    changed = True

        if changed:
            self.world.terrain_revision += 1

    def _update_path_terrain(self, *, decay_traffic: bool = False) -> None:
        """Paint PATH from villager wear; sticky until wear drops below KEEP."""
        urban_cells = self._compute_urban_layout()
        field_cells = self._field_plot_cells()

        if decay_traffic:
            decayed: dict[tuple[int, int], float] = {}
            decay = self.balance.get_float("PATH_TRAFFIC_DECAY")
            for key, wear in self._path_traffic.items():
                nxt = float(wear) * decay
                if nxt >= 0.2:
                    decayed[key] = nxt
            self._path_traffic = decayed

        threshold = self.balance.get_float("PATH_TRAFFIC_THRESHOLD")
        keep = self.balance.get_float("PATH_TRAFFIC_KEEP")
        # Local dirty only — bumping terrain_revision here forced a full-map
        # terrain stitch + height rebake every in-game day.
        for (x, y), wear in self._path_traffic.items():
            if (x, y) in urban_cells or (x, y) in field_cells:
                continue
            cell = self.world.get_cell(x, y)
            if cell is None or not hardscape_paintable(cell):
                continue
            if cell.terrain == TerrainType.URBAN:
                continue
            if wear >= threshold and cell.terrain != TerrainType.PATH:
                self._set_hardscape_terrain(x, y, TerrainType.PATH)

        for y in range(self.world.rows):
            for x in range(self.world.cols):
                if (x, y) in field_cells or (x, y) in urban_cells:
                    continue
                cell = self.world.cells[y][x]
                if cell.terrain != TerrainType.PATH:
                    continue
                wear = float(self._path_traffic.get((x, y), 0.0))
                if wear < keep:
                    cell.terrain = self._revert_hardscape_terrain(x, y)
                    self.world.mark_terrain_dirty(x, y)

    def _path_traffic_overlay_grid(self) -> list[list[float]]:
        cap = max(1.0, self.balance.get_float("PATH_TRAFFIC_OVERLAY_MAX"))
        grid = [[0.0] * self.world.cols for _ in range(self.world.rows)]
        for (x, y), wear in self._path_traffic.items():
            if self.world.in_bounds(x, y):
                grid[y][x] = min(1.0, float(wear) / cap)
        return grid

    def _bee_nest_sites(self) -> list[tuple[int, int, int]]:
        """Active bee nests as (x, y, level) for pollination coverage."""
        from wildlife import AnimalKind

        nests: list[tuple[int, int, int]] = []
        for colony in self.wildlife.colonies:
            if colony.kind == AnimalKind.BEE and colony.level >= 1:
                nests.append((colony.x, colony.y, colony.level))
        return nests

    def _backfill_env_overlays(self) -> None:
        """Fill floral if missing; always rebuild pollination from current nests."""
        if not self.env_maps.floral_samples:
            floral = floral_resources_snapshot(self.world)
            self.env_maps.floral_samples = [floral]
            self.env_maps.floral_resources = [row[:] for row in floral]
        # Pollination is nest-derived (not a year average) — refresh so range
        # / strength balance changes apply immediately on load.
        self.env_maps.pollination = pollination_coverage_grid(
            self.world,
            self._bee_nest_sites(),
            base_radius=POLLINATOR_BASE_RADIUS,
            radius_per_level=POLLINATOR_RADIUS_PER_LEVEL,
            base_strength=POLLINATOR_BASE_STRENGTH,
            strength_per_level=POLLINATOR_STRENGTH_PER_LEVEL,
        )

    # Back-compat alias for save_load / diagnostics.
    def _sample_biodiversity(self) -> None:
        self._sample_environment()

    def _is_biodiversity_sample_day(self, calendar_day: int) -> bool:
        return is_env_sample_day(calendar_day)

    def _field_env_cells(self, field: Building) -> list[tuple[int, int]]:
        return field.plot_cells()

    def _farm_pest_control_at(self, x: int, y: int) -> float:
        """Pest-control multiplier for the Field covering (x, y), else cell value.

        Includes alchemist ``pest_boost`` on fields (insect repellant / mineral powder).
        """
        field_b = self._field_building_at(x, y)
        if field_b is not None:
            base = self.env_maps.farm_pest_control(field_b.plot_cells())
            boost = max(0.0, float(getattr(field_b, "pest_boost", 0.0)))
            return base + boost
        return self.env_maps.value_at(EnvLayer.PEST_CONTROL, x, y)

    def _apply_field_pest_boost(self, field: Building, amount: float) -> float:
        """Add pest boost to a field; returns the applied amount (after cap)."""
        before = max(0.0, float(getattr(field, "pest_boost", 0.0)))
        after = min(FIELD_PEST_BOOST_MAX, before + max(0.0, amount))
        field.pest_boost = after
        return after - before

    def _try_apply_alchemist_treatment(self, x: int, y: int) -> bool:
        """Apply insect repellant / mineral powder from player inventory. True if used."""
        from world import PLANTABLE_LAND, TerrainType

        inv = self.player.inventory
        cell = self.world.get_cell(x, y)
        if cell is None:
            return False
        field_b = self._field_building_at(x, y)

        # Insect repellant: field tiles only.
        if int(getattr(inv, "insect_repellant", 0)) > 0 and field_b is not None:
            if not inv.consume_item("insect_repellant", 1):
                return False
            added = self._apply_field_pest_boost(field_b, INSECT_REPELLANT_PEST_BOOST)
            self.world.apply_disturbance(x, y)
            self.record_consumed("insect_repellant", 1)
            self._set_status(
                f"Applied insect repellant (+{added:.2f} pest control, "
                f"field now +{field_b.pest_boost:.2f})."
            )
            return True

        # Mineral powder: convert grass/meadow → soil; small field pest boost.
        if int(getattr(inv, "mineral_powder", 0)) > 0:
            changed_soil = False
            if cell.terrain in (TerrainType.GRASS, TerrainType.MEADOW):
                cell.terrain = TerrainType.SOIL
                self.world.mark_terrain_dirty(x, y)
                changed_soil = True
            elif cell.terrain not in PLANTABLE_LAND and field_b is None:
                return False
            if not inv.consume_item("mineral_powder", 1):
                return False
            added = 0.0
            if field_b is not None:
                added = self._apply_field_pest_boost(field_b, MINERAL_POWDER_PEST_BOOST)
            self.world.apply_disturbance(x, y)
            self.record_consumed("mineral_powder", 1)
            bits = []
            if changed_soil:
                bits.append("soil amended")
            if added > 0:
                bits.append(f"+{added:.2f} pest control")
            if not bits:
                bits.append("minerals worked in")
            self._set_status(f"Applied mineral powder ({', '.join(bits)}).")
            return True

        return False

    def _farm_pollination_at(self, x: int, y: int) -> float:
        """Mean pollination coverage for the Field covering (x, y), else cell value."""
        field_b = self._field_building_at(x, y)
        if field_b is not None:
            return self.env_maps.farm_pollination(field_b.plot_cells())
        return self.env_maps.value_at(EnvLayer.POLLINATION, x, y)

    def _farm_produce_yield_at(self, x: int, y: int) -> int:
        """Farmed produce after pest × health × pollination (min 1)."""
        pest = self._farm_pest_control_at(x, y)
        poll = pollination_yield_multiplier(self._farm_pollination_at(x, y))
        field_b = self._field_building_at(x, y)
        health = self._field_crop_health(field_b) if field_b is not None else 1.0
        from world import disturbance_activity_multiplier, effective_disturbance_at

        cell = self.world.get_cell(x, y)
        ecology = (
            disturbance_activity_multiplier(effective_disturbance_at(self.world, x, y))
            if cell is not None
            else 1.0
        )
        return max(
            1,
            int(round(FARM_PRODUCE_YIELD * pest * health * poll * ecology)),
        )

    def _farm_produce_yield_budget(self) -> int:
        """Conservative cargo budget for next farm harvest (best-case mults)."""
        return max(
            1,
            int(
                round(
                    FARM_PRODUCE_YIELD
                    * PEST_CONTROL_MULT_HIGH
                    * POLLINATION_YIELD_HIGH
                )
            ),
        )

    def _sync_habitat_selection(self) -> None:
        """Drop habitat highlight if that breeding ground vanished on refresh."""
        if self.selected_habitat_id is None or self.selected_habitat_kind is None:
            return
        kind = self.selected_habitat_kind
        hab = self.wildlife.habitat(self.selected_habitat_id, kind)
        if hab is None:
            self.selected_habitat_kind = None
            self.selected_habitat_id = None
            self.habitat_inspect.close()
            return
        breed = self.wildlife._breeding_for(kind, hab)
        cap = self.wildlife._cap_for(kind, hab)
        if not breed or cap <= 0:
            self.selected_habitat_kind = None
            self.selected_habitat_id = None
            self.habitat_inspect.close()

    def _expire_unharvested_crops(self, ended_season: Season) -> None:
        """Clear ripe crops that missed their harvest window so the tile can be replanted.

        Only ripe (``growth_ticks <= 0``) leftovers are cleared. Still-growing
        plantings are left alone so a late crop can finish and be picked after
        the calendar harvest window (farm harvest ignores phase).
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
                if ended_season not in crop.harvest_seasons:
                    continue
                # Still growing — keep it; workers can pick once ripe.
                if cell.feature == FeatureType.CROP_HERB and cell.growth_ticks > 0:
                    continue

                cell.feature = FeatureType.NONE
                cell.growth_ticks = 0
                cell.crop_kind = None
                cell.deposit = 0
                cleared = True

        if cleared:
            self._wake_all_farm_workers()
            self._refresh_indicators()

    def _ripen_crops_for_harvest_season(self) -> None:
        """At season start, snap in-season farm crops to harvestable.

        Lets workers collect during the harvest window even if growth ticks
        (e.g. after changing ``TICKS_PER_DAY``) would otherwise finish late.
        """
        ripened = False
        season = self.season
        for y in range(self.world.rows):
            for x in range(self.world.cols):
                cell = self.world.cells[y][x]
                if cell.feature != FeatureType.CROP_HERB or cell.growth_ticks <= 0:
                    continue
                crop = CROP_BY_KEY.get(cell.crop_kind or "sage")
                if crop is None or season not in crop.harvest_seasons:
                    continue
                cell.growth_ticks = 0
                ripened = True
        if ripened:
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
        elif action == "file_tracker":
            self.resource_tracker.toggle(self.resource_history)
        elif action == "file_balance":
            self.balance_dialog.toggle()
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
        elif action == "day_slower":
            self._cycle_ticks_per_day(-1)
        elif action == "day_faster":
            self._cycle_ticks_per_day(1)

    def _select_building(
        self, building: Building, *, show_player: bool = False
    ) -> None:
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
        self._open_building_inspect(building, show_player=show_player)

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

    def _open_building_inspect(
        self, building: Building, *, show_player: bool = False
    ) -> None:
        self.field_plan_dialog.close()
        self.villager_inspect.close()
        self.resource_inspect.close()
        self.selected_building_id = building.id
        screen_xy = self.camera.world_to_screen(*building.center_cell())
        self.building_inspect.open_for(
            building, screen_xy=screen_xy, show_player=show_player
        )
        if building.kind == BuildingKind.HOME:
            haulers = sum(1 for v in self.villagers if v.assigned_to_home)
            if show_player:
                self._set_status(
                    f"Storehouse open. Click items to transfer one. {haulers} hauler(s)."
                )
            else:
                self._set_status(
                    f"Selected Storehouse. {haulers} hauler(s). Assign villagers to haul."
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
        if action.startswith("xfer_to_player:"):
            self._transfer_inspect_to_player(action.split(":", 1)[1])
            return
        if action.startswith("xfer_to_storage:"):
            self._transfer_inspect_to_storage(action.split(":", 1)[1])
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
        if action.startswith("toggle_recipe:"):
            building = self._inspect_building()
            if building is None or not (building.has_recipes() or building.split_recipes()):
                return
            name = action.split(":", 1)[1]
            enabled = building.toggle_recipe(name)
            from recipes import RECIPE_LABELS, recipe_label

            label = RECIPE_LABELS.get(name)
            if label is None:
                for recipe in building.known_recipes():
                    if recipe.name == name:
                        label = recipe_label(recipe)
                        break
                else:
                    for recipe in building.split_recipes():
                        if recipe.name == name:
                            label = recipe_label(recipe)
                            break
                    else:
                        label = name
            state = "on" if enabled else "off"
            self._wake_building_workers(building.id)
            self._set_status(f"{BUILDING_LABELS[building.kind]}: {label} {state}.")
            return
        if action.startswith("cycle_recipe_priority:"):
            building = self._inspect_building()
            if building is None or not (building.has_recipes() or building.split_recipes()):
                return
            name = action.split(":", 1)[1]
            priority = building.cycle_recipe_priority(name)
            from recipes import RECIPE_LABELS, recipe_label

            label = RECIPE_LABELS.get(name)
            if label is None:
                for recipe in (*building.known_recipes(), *building.split_recipes()):
                    if recipe.name == name:
                        label = recipe_label(recipe)
                        break
                else:
                    label = name
            self._wake_building_workers(building.id)
            self._set_status(
                f"{BUILDING_LABELS[building.kind]}: {label} priority {priority}."
            )
            return
        if action == "toggle_caps":
            self.building_inspect.caps_expanded = not self.building_inspect.caps_expanded
            return
        if action == "toggle_mins":
            self.building_inspect.mins_expanded = not self.building_inspect.mins_expanded
            return
        if action.startswith("select_cap:"):
            key = action.split(":", 1)[1]
            building = self._inspect_building()
            if building is None:
                return
            if key not in building.depositable_keys():
                return
            self.building_inspect.selected_cap_key = key
            from resources import resource_label

            cap = building.item_cap(key)
            tip = "unlimited" if cap is None else f"max {cap}"
            self._set_status(f"{resource_label(key)} selected ({tip}). Use + / −.")
            return
        if action in ("cap_inc", "cap_dec", "cap_clear"):
            building = self._inspect_building()
            key = self.building_inspect.selected_cap_key
            if building is None or key is None:
                return
            from resources import resource_label

            label = resource_label(key)
            if action == "cap_clear":
                building.set_item_cap(key, None)
                self._set_status(f"{label} cap cleared (unlimited).")
                return
            delta = 1 if action == "cap_inc" else -1
            new_cap = building.adjust_item_cap(key, delta)
            if new_cap is None:
                self._set_status(f"{label} cap cleared (unlimited).")
            else:
                self._set_status(f"{label} cap: {new_cap}.")
            return
        if action.startswith("select_min:"):
            key = action.split(":", 1)[1]
            building = self._inspect_building()
            if building is None:
                return
            if key not in building.depositable_keys():
                return
            self.building_inspect.selected_min_key = key
            from resources import resource_label

            reserve = building.item_min(key)
            tip = "none" if reserve is None else f"min {reserve}"
            self._set_status(f"{resource_label(key)} min selected ({tip}). Use + / −.")
            return
        if action in ("min_inc", "min_dec", "min_clear"):
            building = self._inspect_building()
            key = self.building_inspect.selected_min_key
            if building is None or key is None:
                return
            from resources import resource_label

            label = resource_label(key)
            if action == "min_clear":
                building.set_item_min(key, None)
                self._set_status(f"{label} min reserve cleared.")
                return
            delta = 1 if action == "min_inc" else -1
            new_min = building.adjust_item_min(key, delta)
            if new_min is None:
                self._set_status(f"{label} min reserve cleared.")
            else:
                self._set_status(f"{label} min reserve: {new_min}.")
            return

    def _transfer_inspect_to_player(self, key: str) -> None:
        if not self.building_inspect.show_player:
            return
        building = self._inspect_building()
        if building is None:
            return
        inv = self.player.inventory
        from resources import resource_label

        label = resource_label(key)
        if building.kind == BuildingKind.HOME:
            if int(getattr(self.home_storage, key, 0)) <= 0:
                self._set_status(f"No {label} in storehouse.")
                return
            ok = self.home_storage.withdraw_one_to(inv, key)
        else:
            if int(getattr(building, key, 0)) <= 0:
                self._set_status(f"No {label} in storage.")
                return
            ok = building.give_item_to(inv, key)
        if not ok:
            self._set_status("Inventory is full.")
            return
        self._refresh_indicators()
        self._set_status(f"Took 1 {label}.")

    def _transfer_inspect_to_storage(self, key: str) -> None:
        if not self.building_inspect.show_player:
            return
        building = self._inspect_building()
        if building is None:
            return
        inv = self.player.inventory
        from resources import resource_label

        label = resource_label(key)
        if int(getattr(inv, key, 0)) <= 0:
            self._set_status(f"You have no {label}.")
            return
        if key not in building.depositable_keys():
            self._set_status(f"{BUILDING_LABELS[building.kind]} cannot store {label}.")
            return
        if building.kind == BuildingKind.HOME:
            ok = self.home_storage.deposit_one_from(inv, key)
            hx, hy = self.world.home_pos
            self.world.apply_disturbance(hx, hy)
        else:
            if building.space_for_key(key) <= 0:
                cap = building.item_cap(key)
                if cap is not None and int(getattr(building, key, 0)) >= cap:
                    self._set_status(f"{label} cap reached ({cap}).")
                else:
                    self._set_status("Building storage is full.")
                return
            ok = building.deposit_one_from(inv, key)
        if not ok:
            self._set_status("Could not deposit.")
            return
        self._refresh_indicators()
        self._set_status(f"Deposited 1 {label}.")

    def _open_villager_inspect(
        self, villager: Villager, *, show_player: bool = False
    ) -> None:
        self.selected_villager_id = villager.id
        self.selected_building_id = None
        self.selected_habitat_kind = None
        self.selected_habitat_id = None
        self.assign_workplace_mode = False
        self.field_plan_dialog.close()
        self.building_inspect.close()
        self.resource_inspect.close()
        screen_xy = self.camera.world_to_screen(villager.x, villager.y)
        self.villager_inspect.open_for(
            villager, screen_xy=screen_xy, show_player=show_player
        )
        label = self._villager_assignment_label(villager)
        if show_player:
            self._set_status(
                f"Villager {villager.id} ({label}). Click items to transfer one."
            )
        else:
            self._set_status(
                f"Selected villager {villager.id} ({label}). "
                f"Set priorities & ration in the popup."
            )

    def _apply_villager_inspect_action(self) -> None:
        action = self.villager_inspect.take_action()
        if action is None:
            return
        if action.startswith("xfer_to_player:"):
            self._transfer_villager_to_player(action.split(":", 1)[1])
            return
        if action.startswith("xfer_to_villager:"):
            self._transfer_player_to_villager(action.split(":", 1)[1])
            return
        if action == "tool_equip":
            self._villager_equip_tool()
            return
        if action == "tool_unequip":
            self._villager_unequip_tool()
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

    def _villager_equip_tool(self) -> None:
        villager = self._get_villager(self.villager_inspect.villager_id or -1)
        if villager is None:
            return
        inv = villager.inventory
        if inv.equipped_tool is not None:
            return
        for key in TOOL_KEYS:
            if inv.equip_tool(key):
                from resources import resource_label

                self._set_status(
                    f"Villager {villager.id} equipped {resource_label(key)}."
                )
                return
        if self.villager_inspect.show_player:
            for key in TOOL_KEYS:
                if int(getattr(self.player.inventory, key, 0)) <= 0:
                    continue
                if not self.player.inventory.consume_item(key, 1):
                    continue
                if inv.equip_tool_from_transfer(key):
                    from resources import resource_label

                    self._set_status(
                        f"Villager {villager.id} equipped {resource_label(key)}."
                    )
                    return
                self.player.inventory.add_item(key, 1)
        self._set_status("No tool to equip.")

    def _villager_unequip_tool(self) -> None:
        villager = self._get_villager(self.villager_inspect.villager_id or -1)
        if villager is None:
            return
        inv = villager.inventory
        if inv.equipped_tool is None:
            return
        from resources import resource_label

        label = resource_label(inv.equipped_tool)
        if (
            self.villager_inspect.show_player
            and inv.transfer_equipped_tool_to(self.player.inventory)
        ):
            self._set_status(f"Gave {label} to player.")
            return
        if inv.unequip_tool():
            self._set_status(f"Villager {villager.id} unequipped {label}.")
            return
        self._set_status("Cargo full — cannot unequip tool.")

    def _transfer_villager_to_player(self, key: str) -> None:
        if not self.villager_inspect.show_player:
            return
        villager = self._get_villager(self.villager_inspect.villager_id or -1)
        if villager is None:
            return
        from resources import resource_label

        label = resource_label(key)
        if int(getattr(villager.inventory, key, 0)) <= 0:
            self._set_status(f"Villager has no {label}.")
            return
        if not self.player.inventory.can_add(1, key=key):
            self._set_status("Inventory is full.")
            return
        villager.inventory.consume_item(key, 1)
        self.player.inventory.add_item(key, 1)
        self._refresh_indicators()
        self._set_status(f"Took 1 {label}.")

    def _transfer_player_to_villager(self, key: str) -> None:
        if not self.villager_inspect.show_player:
            return
        villager = self._get_villager(self.villager_inspect.villager_id or -1)
        if villager is None:
            return
        from resources import resource_label

        label = resource_label(key)
        if int(getattr(self.player.inventory, key, 0)) <= 0:
            self._set_status(f"You have no {label}.")
            return
        if not villager.inventory.can_add(1, key=key):
            self._set_status("Villager inventory is full.")
            return
        self.player.inventory.consume_item(key, 1)
        villager.inventory.add_item(key, 1)
        self._refresh_indicators()
        self._set_status(f"Gave 1 {label}.")

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
            self._ensure_player_in_view()

    def _ensure_player_in_view(self, *, margin: float = 2.5) -> None:
        """Pan the camera when the player reaches the edge of the viewport."""
        vis_w, vis_h = self.camera.visible_cells()
        px = self.player.x + 0.5
        py = self.player.y + 0.5
        m = max(1.0, float(margin))
        if px < self.camera.x + m:
            self.camera.x = px - m
        elif px > self.camera.x + vis_w - m:
            self.camera.x = px - (vis_w - m)
        if py < self.camera.y + m:
            self.camera.y = py - m
        elif py > self.camera.y + vis_h - m:
            self.camera.y = py - (vis_h - m)
        self.camera.clamp(self.world.cols, self.world.rows)

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

    def _adjacent_villager(self, x: int, y: int) -> Villager | None:
        """Nearest villager at Chebyshev distance 1."""
        best: Villager | None = None
        best_dist = 99
        for villager in self.villagers:
            dist = max(abs(villager.x - x), abs(villager.y - y))
            if dist == 1 and dist < best_dist:
                best = villager
                best_dist = dist
        return best

    def _building_at(self, x: int, y: int) -> Building | None:
        for building in self.buildings.values():
            if building.contains_plot(x, y):
                return building
        return None

    def _construction_at(self, x: int, y: int) -> ConstructionSite | None:
        for site in self.construction_sites.values():
            if site.contains_plot(x, y):
                return site
        return None

    def _footprint_blocked(self, cells: list[tuple[int, int]], *, ignore_site_id: int | None = None) -> str | None:
        """Return a status reason if any cell cannot host a structure footprint."""
        # Herbs/crops are cleared when the footprint is claimed; trees/rocks stay blockers.
        clearable = {
            FeatureType.HERB,
            FeatureType.WILD_CROP,
            FeatureType.CROP_HERB,
            FeatureType.REED,
            FeatureType.MUSHROOM,
        }
        for x, y in cells:
            cell = self.world.get_cell(x, y)
            if cell is None:
                return "Footprint leaves the map."
            if not self._cell_buildable(cell):
                return "Build on soil, grass, meadow, bare rock, urban, or path."
            if cell.feature != FeatureType.NONE and cell.feature not in clearable:
                return "Cannot place construction site here."
            for building in self.buildings.values():
                if building.contains_plot(x, y):
                    return "Overlaps an existing building."
            for site in self.construction_sites.values():
                if ignore_site_id is not None and site.id == ignore_site_id:
                    continue
                if site.contains_plot(x, y):
                    return "Overlaps a construction site."
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

    def _villager_job_colour(self, villager: Villager) -> tuple[int, int, int]:
        if villager.assigned_to_home:
            return COLOUR_HOME
        if villager.building_id is not None:
            building = self.buildings.get(villager.building_id)
            if building is not None:
                return {
                    BuildingKind.FORESTER: COLOUR_FORESTER,
                    BuildingKind.MASON: COLOUR_MASON,
                    BuildingKind.HUNTER: COLOUR_HUNTER,
                    BuildingKind.FORAGER: COLOUR_FORAGER,
                    BuildingKind.FISHER: COLOUR_FISHER,
                    BuildingKind.FARM: COLOUR_FARM,
                    BuildingKind.FIELD: COLOUR_FARM,
                    BuildingKind.MILL: COLOUR_MILL,
                    BuildingKind.KITCHEN: COLOUR_KITCHEN,
                    BuildingKind.CRAFT_BENCH: COLOUR_CRAFT_BENCH,
                    BuildingKind.ALCHEMIST: COLOUR_ALCHEMIST,
                }.get(building.kind, COLOUR_VILLAGER)
        return COLOUR_VILLAGER

    def _wake_building_workers(self, building_id: int) -> None:
        for villager in self.villagers:
            if villager.building_id != building_id:
                continue
            villager.target = None
            villager._path_cache = None  # type: ignore[attr-defined]
            villager._path_goal = None  # type: ignore[attr-defined]
            if villager.state == VillagerState.IDLE:
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
                self._select_building(building, show_player=True)
            return

        if cell.feature == FeatureType.HOME:
            building = self._building_at(x, y)
            if building is not None:
                self._select_building(building, show_player=True)
            return

        if cell.feature in (
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
            FeatureType.WORKSTATION,
            FeatureType.STRUCTURE_PAD,
        ):
            # Alchemist treatments on field tiles before opening the inspect panel.
            if (
                cell.feature in (FeatureType.FIELD, FeatureType.STRUCTURE_PAD)
                or self._field_building_at(x, y) is not None
            ) and self._try_apply_alchemist_treatment(x, y):
                return
            building = self._building_at(x, y)
            if building is not None:
                self._select_building(building, show_player=True)
            return

        # Talk / trade with a villager on this cell (or adjacent).
        villager = self._villager_at(x, y) or self._adjacent_villager(x, y)
        if villager is not None:
            self._open_villager_inspect(villager, show_player=True)
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
            while site.wood_needed > 0 and self.player.inventory.logs > 0:
                self.player.inventory.logs -= 1
                site.have_wood += 1
                self.record_consumed("logs", 1)
                delivered = True
            while site.rock_needed > 0 and self.player.inventory.rock > 0:
                self.player.inventory.rock -= 1
                site.have_rock += 1
                self.record_consumed("rock", 1)
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

        if cell.feature == FeatureType.WOOD_BUSH:
            self._collect_wood_bush(x, y, self.player.inventory, status=True)
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
            elif self._try_apply_alchemist_treatment(x, y):
                return
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
            if self._try_apply_alchemist_treatment(x, y):
                return
            if self.place_kind is not None:
                self._try_build(self.place_kind, x, y)
            else:
                self._plant_here(x, y, self.player.inventory, status=True)
            return

        if cell.feature == FeatureType.SAPLING:
            self._set_status("Sapling is already growing.")
            return

        if is_water_terrain(cell.terrain):
            if water_frozen(self.calendar_day):
                self._set_status("Ice — fishing resumes in spring.")
            else:
                self._set_status("Water — stand on shore and catch fish with Enter.")
            return

        self._set_status("Nothing to do here.")

    def _resource_pool_wood(self) -> int:
        return self.home_storage.logs + self.player.inventory.logs

    def _resource_pool_rock(self) -> int:
        return self.home_storage.rock + self.player.inventory.rock

    def _spend_resources(self, wood: int, rock: int) -> bool:
        """Spend from home storage first, then player inventory."""
        if self._resource_pool_wood() < wood or self._resource_pool_rock() < rock:
            return False

        need_w, need_r = wood, rock
        take_w = min(self.home_storage.logs, need_w)
        self.home_storage.logs -= take_w
        need_w -= take_w
        take_r = min(self.home_storage.rock, need_r)
        self.home_storage.rock -= take_r
        need_r -= take_r
        self.player.inventory.logs -= need_w
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
        if kind == BuildingKind.MILL:
            return MILL_COST_WOOD, MILL_COST_ROCK, TaskType.FULL_FORAGE
        if kind == BuildingKind.KITCHEN:
            return KITCHEN_COST_WOOD, KITCHEN_COST_ROCK, TaskType.FULL_FORAGE
        if kind == BuildingKind.CRAFT_BENCH:
            return CRAFT_BENCH_COST_WOOD, CRAFT_BENCH_COST_ROCK, TaskType.FULL_FORAGE
        if kind == BuildingKind.ALCHEMIST:
            return ALCHEMIST_COST_WOOD, ALCHEMIST_COST_ROCK, TaskType.FULL_FORAGE
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
            FeatureType.MILL,
            FeatureType.KITCHEN,
            FeatureType.CRAFT_BENCH,
            FeatureType.ALCHEMIST,
            FeatureType.CONSTRUCTION_SITE,
            FeatureType.STRUCTURE_PAD,
            FeatureType.TREE,
            FeatureType.SAPLING,
            FeatureType.BERRY_BUSH,
            FeatureType.ROCK,
        )
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                cell = self.world.get_cell(x, y)
                if cell is None or cell.terrain not in PLANTABLE_LAND:
                    self._set_status("Field must be entirely on soil, grass, or meadow.")
                    return False
                if cell.feature in blocked:
                    self._set_status("Field overlaps a building, tree, or rock.")
                    return False
                if self._building_at(x, y) is not None or self._construction_at(x, y) is not None:
                    self._set_status("Field overlaps a building or construction site.")
                    return False
                if self._field_plot_covers(x, y):
                    self._set_status("Field overlaps another field.")
                    return False
        # Clear herbs/crops on the plot (trees already blocked above).
        clearable = {
            FeatureType.HERB,
            FeatureType.WILD_CROP,
            FeatureType.CROP_HERB,
            FeatureType.REED,
            FeatureType.MUSHROOM,
        }
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                cell = self.world.get_cell(x, y)
                if cell is not None and cell.feature in clearable:
                    cell.feature = FeatureType.NONE
                    cell.deposit = 0
                    cell.growth_ticks = 0
                    cell.crop_kind = None
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

    def _field_plot_covers(self, x: int, y: int) -> bool:
        """True if an existing Field building or Field construction covers the cell."""
        for building in self.buildings.values():
            if building.kind == BuildingKind.FIELD and building.contains_plot(x, y):
                return True
        for site in self.construction_sites.values():
            if site.kind == BuildingKind.FIELD and site.contains_plot(x, y):
                return True
        return False

    def _field_drag_overlaps(self, left: int, top: int, right: int, bottom: int) -> bool:
        for y in range(top, bottom + 1):
            for x in range(left, right + 1):
                if self._field_plot_covers(x, y):
                    return True
        return False

    def _place_construction_site(self, kind: BuildingKind, x: int, y: int) -> bool:
        if kind == BuildingKind.FIELD:
            return self._place_field_site((x, y), (x, y))
        plot_w, plot_h = default_building_plot(kind)
        # Click cell is the centre of the footprint.
        ox = x - plot_w // 2
        oy = y - plot_h // 2
        cells = [
            (px, py)
            for py in range(oy, oy + plot_h)
            for px in range(ox, ox + plot_w)
        ]
        reason = self._footprint_blocked(cells)
        if reason is not None:
            self._set_status(reason)
            return False
        cost_w, cost_r, _ = self._building_cost(kind)
        site = ConstructionSite(
            id=self.next_construction_id,
            x=ox,
            y=oy,
            kind=kind,
            need_wood=cost_w,
            need_rock=cost_r,
            plot_w=plot_w,
            plot_h=plot_h,
        )
        self.next_construction_id += 1
        self.construction_sites[site.id] = site
        self.world.claim_structure_footprint(
            ox, oy, plot_w, plot_h, FeatureType.CONSTRUCTION_SITE
        )
        self._refresh_hardscape_terrain()
        self.world.apply_disturbance(x, y)
        self._refresh_indicators()
        self.place_kind = None
        self._set_status(
            f"Construction site: {BUILDING_LABELS[kind]} "
            f"(needs {cost_w}w {cost_r}r). Villagers will deliver & build."
        )
        return True

    def _complete_construction(self, site: ConstructionSite) -> None:
        cx, cy = site.center_cell()
        cell = self.world.get_cell(cx, cy)
        if cell is None:
            return
        _, _, default_task = self._building_cost(site.kind)
        plot_w = max(1, site.plot_w)
        plot_h = max(1, site.plot_h)
        if site.kind != BuildingKind.FIELD:
            pw, ph = default_building_plot(site.kind)
            plot_w, plot_h = pw, ph
        cap, in_cap, out_cap = default_processor_capacities(site.kind)
        building = Building(
            id=self.next_building_id,
            kind=site.kind,
            x=site.x,
            y=site.y,
            capacity=cap,
            input_capacity=in_cap,
            output_capacity=out_cap,
            draw_task_type=default_task,
            work_mode=Building.work_mode_from_task(site.kind, default_task),
            plot_w=plot_w,
            plot_h=plot_h,
        )
        from entities import apply_building_storage

        apply_building_storage(building)
        building.sync_draw_task_from_mode()
        if site.kind == BuildingKind.FORESTER:
            building.item_mins = dict(default_item_mins(BuildingKind.FORESTER))
        self.next_building_id += 1
        self.buildings[building.id] = building
        if site.kind == BuildingKind.FIELD:
            # Field is a plot outline only — no building glyph on the map.
            for px, py in site.plot_cells():
                pad = self.world.get_cell(px, py)
                if pad is not None and pad.feature in (
                    FeatureType.CONSTRUCTION_SITE,
                    FeatureType.STRUCTURE_PAD,
                ):
                    pad.feature = FeatureType.NONE
        else:
            self.world.claim_structure_footprint(
                building.x,
                building.y,
                building.plot_w,
                building.plot_h,
                FEATURE_FOR_BUILDING[site.kind],
            )
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
        self._refresh_hardscape_terrain()

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

    def _chop_tree(
        self,
        x: int,
        y: int,
        inventory: Inventory,
        status: bool = False,
        *,
        require_axe: bool = False,
    ) -> bool:
        if require_axe and not inventory.has_equipped_tool("axe"):
            if status:
                self._set_status("Forester needs an axe in the tool slot.")
            return False
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
        self.record_produced(yield_key, taken)
        sapling_msg = ""
        if self._drop_rng.random() < self._seed_chance(SAPLING_DROP_CHANCE):
            from trees import sapling_item_key

            skey = sapling_item_key(tree.key)
            if inventory.can_add(1, key=skey):
                inventory.add_saplings(1, species=tree.key)
                self.record_produced(skey, 1)
                sapling_msg = f" +1 {tree.label.lower()} sapling"
        self.world.apply_extraction_disturbance(x, y)
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
        self.record_produced("rock", taken)
        self.world.apply_extraction_disturbance(x, y)
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
        self.record_consumed(key, 1)
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
        self.record_consumed("berry_seeds", 1)
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
        if not inventory.can_add(MUSHROOM_YIELD, key="mushrooms"):
            if status:
                self._set_status(
                    f"Need {MUSHROOM_YIELD} free cargo slots for mushrooms."
                )
            return False
        if not self.world.harvest_mushroom(x, y):
            if status:
                self._set_status("No mushroom here.")
            return False
        inventory.add_mushrooms(MUSHROOM_YIELD)
        self.record_produced("mushrooms", MUSHROOM_YIELD)
        self.world.apply_extraction_disturbance(x, y)
        self._refresh_indicators()
        if status:
            self._set_status(
                f"Collected {MUSHROOM_YIELD} mushroom"
                f"{'' if MUSHROOM_YIELD == 1 else 's'}."
            )
        return True

    def _collect_wood_bush(
        self, x: int, y: int, inventory: Inventory, status: bool = False
    ) -> bool:
        if inventory.is_full:
            if status:
                self._set_status("Inventory is full.")
            return False
        taken = self.world.harvest_wood_bush(x, y)
        if taken <= 0:
            if status:
                self._set_status("No wood left.")
            return False
        inventory.add_item("wood", taken)
        self.record_produced("wood", taken)
        self.world.apply_extraction_disturbance(x, y)
        self._refresh_indicators()
        if status:
            self._set_status(f"Collected {taken} wood.")
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
        self.record_produced("berries", taken)
        seed_msg = ""
        if self._drop_rng.random() < self._seed_chance(BERRY_SEED_DROP_CHANCE) and inventory.can_add(1, key="berry_seeds"):
            inventory.add_berry_seeds(1)
            self.record_produced("berry_seeds", 1)
            seed_msg = " +1 berry seed"
        self.world.apply_extraction_disturbance(x, y)
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
        cell = self.world.get_cell(x, y)
        if cell is None:
            if status:
                self._set_status("No wild plants here.")
            return False
        # Check cargo room before clearing the tile (seeds use a separate bag).
        if cell.feature == FeatureType.REED:
            produce_key, need = "reeds", REED_YIELD
        elif cell.feature == FeatureType.HERB:
            crop = CROP_BY_KEY["sage"]
            produce_key, need = crop.produce_key, WILD_PRODUCE_YIELD
        elif cell.feature == FeatureType.WILD_CROP:
            crop = CROP_BY_KEY.get(cell.crop_kind or "sage", CROP_BY_KEY["sage"])
            produce_key, need = crop.produce_key, WILD_PRODUCE_YIELD
        else:
            if status:
                self._set_status("No wild plants here.")
            return False
        if not inventory.can_add(need, key=produce_key):
            if status:
                self._set_status(
                    f"Need {need} free cargo slots to harvest {produce_key.replace('_', ' ')}."
                )
            return False

        crop_key = self.world.harvest_herb(x, y)
        if crop_key is None:
            if status:
                self._set_status("No wild plants here.")
            return False
        if crop_key == "reeds":
            inventory.add_item("reeds", REED_YIELD)
            self.record_produced("reeds", REED_YIELD)
            self.world.apply_extraction_disturbance(x, y)
            self._refresh_indicators()
            if status:
                self._set_status(
                    f"Collected {REED_YIELD} reed{'' if REED_YIELD == 1 else 's'}."
                )
            return True
        crop = CROP_BY_KEY.get(crop_key, CROP_BY_KEY["sage"])
        inventory.add_item(crop.produce_key, WILD_PRODUCE_YIELD)
        self.record_produced(crop.produce_key, WILD_PRODUCE_YIELD)
        seed_msg = ""
        # Forage: flat chance of a single seed (see resource_balance.WILD_SEED_CHANCE).
        if self._drop_rng.random() < crop.wild_seed_chance and inventory.can_add(
            1, key=crop.seed_key
        ):
            inventory.add_item(crop.seed_key, 1)
            self.record_produced(crop.seed_key, 1)
            seed_msg = f" +1 {crop.label.lower()} seed"
        self.world.apply_extraction_disturbance(x, y)
        self._refresh_indicators()
        if status:
            self._set_status(
                f"Collected {WILD_PRODUCE_YIELD} {crop.label.lower()}{seed_msg}."
            )
        return True

    def _harvest_farm_herb(
        self, x: int, y: int, inventory: Inventory, status: bool = False
    ) -> bool:
        if inventory.is_full:
            if status:
                self._set_status("Inventory is full.")
            return False
        cell = self.world.get_cell(x, y)
        if (
            cell is None
            or cell.feature != FeatureType.CROP_HERB
            or cell.growth_ticks > 0
        ):
            if status:
                self._set_status("Crop not ready.")
            return False
        crop = CROP_BY_KEY.get(cell.crop_kind or "sage", CROP_BY_KEY["sage"])
        yield_n = self._farm_produce_yield_at(x, y)
        # Must fit the full harvest before clearing the tile.
        if not inventory.can_add(yield_n, key=crop.produce_key):
            if status:
                self._set_status(
                    f"Need {yield_n} free cargo slots to harvest "
                    f"{crop.label.lower()}."
                )
            return False
        crop_key = self.world.harvest_crop_herb(x, y)
        if crop_key is None:
            if status:
                self._set_status("Crop not ready.")
            return False
        crop = CROP_BY_KEY.get(crop_key, CROP_BY_KEY["sage"])
        if not inventory.add_item(crop.produce_key, yield_n):
            if status:
                self._set_status("Could not store harvest.")
            return False
        self.record_produced(crop.produce_key, yield_n)
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
            self.record_produced(crop.seed_key, got)
            seed_msg = f" +{got} {crop.label.lower()} seed{'s' if got != 1 else ''}"
        self.world.apply_extraction_disturbance(x, y)
        self._refresh_indicators()
        if status:
            qty = f" ×{yield_n}" if yield_n != 1 else ""
            self._set_status(f"Harvested farm {crop.label.lower()}{qty}{seed_msg}.")
        return True

    def _forester_needs_axe(self, building: Building) -> bool:
        return building.work_mode in (WorkMode.COLLECT, WorkMode.ALL, WorkMode.SPLIT)

    def _tool_fetchable(self, villager: Villager, tool_key: str) -> bool:
        """True if the tool is equipped, in cargo, or stocked at home."""
        inv = villager.inventory
        if inv.has_equipped_tool(tool_key):
            return True
        if inv.can_equip_tool(tool_key) or int(getattr(inv, tool_key, 0)) > 0:
            return True
        return int(getattr(self.home_storage, tool_key, 0)) > 0

    def _ensure_work_tool(self, villager: Villager, tool_key: str) -> bool:
        """Fetch and equip a workplace tool from cargo or home storage."""
        inv = villager.inventory
        if inv.has_equipped_tool(tool_key):
            return True
        if inv.can_equip_tool(tool_key):
            inv.equip_tool(tool_key)
            return True
        if int(getattr(self.home_storage, tool_key, 0)) <= 0:
            # Don't leave WORKING+target=home as a fake sticky primary.
            if villager.target == self.world.home_pos:
                villager.target = None
                self._clear_villager_path(villager)
            return False
        home = self.world.home_pos
        if (villager.x, villager.y) != home:
            villager.state = VillagerState.WORKING
            villager.target = home
            if villager.move_cooldown == 0:
                self._step_villager_toward(villager, home)
            return False
        if inv.equipped_tool is None:
            setattr(self.home_storage, tool_key, getattr(self.home_storage, tool_key) - 1)
            inv.equip_tool_from_transfer(tool_key)
            villager.target = None
        return inv.has_equipped_tool(tool_key)

    def _is_station_or_home_cell(self, pos: tuple[int, int]) -> bool:
        """True for home or any building centre (not field gather cells)."""
        stations = getattr(self, "_tick_claim_stations", None)
        if stations is not None:
            return pos in stations
        if pos == self.world.home_pos:
            return True
        return any(b.center_cell() == pos for b in self.buildings.values())

    def _step_or_clear_field_target(
        self, villager: Villager, goal: tuple[int, int]
    ) -> bool:
        """Walk to a field work cell; clear sticky target if unreachable."""
        if self._step_villager_toward(villager, goal):
            return True
        if villager.target == goal:
            villager.target = None
        self._clear_villager_path(villager)
        return False

    def _ensure_forester_axe(self, villager: Villager, building: Building) -> bool:
        """Fetch and equip an axe when chopping or splitting. Returns True when ready."""
        if building.kind != BuildingKind.FORESTER or not self._forester_needs_axe(building):
            return True
        return self._ensure_work_tool(villager, "axe")

    def _forester_try_split(self, villager: Villager, building: Building) -> bool:
        """One split work tick at the forester. Returns True if work was done."""
        if not villager.inventory.has_equipped_tool("axe"):
            return False
        recipe = building.craftable_split_recipe()
        if recipe is None or villager.work_cooldown > 0:
            return False
        if building.advance_recipe_progress(recipe, split=True):
            self._apply_recipe_tracked(building, recipe)
        villager.work_cooldown = self._villager_work_interval(villager)
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
        self.record_produced("meat", taken)
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
        self.world.apply_extraction_disturbance(x, y)
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
        self.record_produced("fish", taken)
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
        self.world.apply_extraction_disturbance(pos[0], pos[1])
        self._refresh_indicators()
        self._set_status(f"Caught fish. {FISH_YIELD} fish left on shore.")

    # ------------------------------------------------------------------
    # Villager AI
    # ------------------------------------------------------------------
    def _update_villagers(self) -> None:
        # One claim snapshot per tick — avoids rebuilding station sets / scans per villager.
        self._tick_claim_stations = {b.center_cell() for b in self.buildings.values()}
        self._tick_claim_stations.add(self.world.home_pos)
        self._tick_claim_cells: set[tuple[int, int]] = set()
        self._tick_claim_animals: set[int] = set()
        self._tick_claim_colonies: set[int] = set()
        self._tick_claim_fish: set[int] = set()
        self._tick_claim_by_villager: dict[int, set[tuple[int, int]]] = {}
        self._tick_has_general_hauler = False
        for other in self.villagers:
            if other.building_id is None:
                self._tick_has_general_hauler = True
            cells: set[tuple[int, int]] = set()
            if (
                other.target is not None
                and other.state == VillagerState.WORKING
                and other.target not in self._tick_claim_stations
            ):
                cells.add(other.target)
            if other.hunt_meat_pos is not None:
                cells.add(other.hunt_meat_pos)
            if other.fish_catch_pos is not None:
                cells.add(other.fish_catch_pos)
            if other.fish_post_pos is not None:
                cells.add(other.fish_post_pos)
            if cells:
                self._tick_claim_by_villager[other.id] = cells
                self._tick_claim_cells |= cells
            if other.hunt_animal_id is not None:
                self._tick_claim_animals.add(other.hunt_animal_id)
            if other.hunt_colony_id is not None:
                self._tick_claim_colonies.add(other.hunt_colony_id)
            if other.forage_colony_id is not None:
                self._tick_claim_colonies.add(other.forage_colony_id)
            if other.fish_target_id is not None:
                self._tick_claim_fish.add(other.fish_target_id)

        for villager in self.villagers:
            if villager.move_cooldown > 0:
                villager.move_cooldown -= 1
            if villager.work_cooldown > 0:
                villager.work_cooldown -= 1

            villager.satiation = max(
                0.0,
                villager.satiation
                - VILLAGER_SATIATION_DECAY_PER_TICK * villager.food_hunger_mult,
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
            # Mid-build / carrying mats always finishes. Otherwise only preempt the
            # priority loop when BUILD is actually on this villager's list (S7).
            if self._construction_delivery_active(villager):
                if (
                    self._carrying_build_mats(villager)
                    or villager.state == VillagerState.BUILDING
                    or WorkPriority.BUILD in villager.priorities
                ):
                    self._update_builder(villager)
                    continue
                villager.construction_id = None
            # Finish leftover construction mats (no site needs them anymore).
            if (
                villager.state == VillagerState.DELIVERING
                and villager.haul_building_id is None
                and villager.construction_id is None
                and self._leftover_build_mats_need_home(villager)
            ):
                self._update_leftover_build_mats(villager)
                continue
            # Finish an in-progress haul (general haulers, or workplace helpers).
            if (
                villager.state == VillagerState.HAULING
                or (
                    villager.state == VillagerState.DELIVERING
                    and villager.haul_building_id is not None
                )
            ):
                if self._uses_general_haul_update(villager):
                    self._update_hauler(villager)
                else:
                    building = self.buildings.get(villager.building_id)
                    if building is not None:
                        self._update_assigned_transport(villager, building)
                    else:
                        villager.haul_building_id = None
                        villager.state = VillagerState.IDLE
                continue
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
                    if self._is_general_hauler(villager):
                        if self._transport_has_work(villager):
                            self._update_hauler(villager)
                            acted = True
                            break
                    else:
                        building = (
                            self.buildings.get(villager.building_id)
                            if villager.building_id
                            else None
                        )
                        if (
                            building is not None
                            and self._assigned_transport_has_work(villager, building)
                        ):
                            self._update_assigned_transport(villager, building)
                            acted = True
                            break
                        # Workplace quiet (e.g. frozen lake): help village haul.
                        if self._transport_has_work(villager):
                            self._update_hauler(villager)
                            acted = True
                            break
            if self._is_general_hauler(villager) and self._try_idle_transport(villager):
                acted = True
            elif not acted:
                if self._construction_delivery_active(villager) and (
                    self._carrying_build_mats(villager)
                    or WorkPriority.BUILD in villager.priorities
                ):
                    self._update_builder(villager)
                elif self._leftover_build_mats_need_home(villager):
                    self._update_leftover_build_mats(villager)
                elif not villager.inventory.is_empty and self._is_general_hauler(
                    villager
                ):
                    self._update_hauler(villager)
                elif villager.building_id is not None:
                    if self._workplace_has_work(villager):
                        self._update_workplace_worker(villager)
                        acted = True
                    else:
                        self._set_workplace_idle(villager)
                elif villager.state not in (VillagerState.DELIVERING, VillagerState.HAULING, VillagerState.BUILDING):
                    villager.state = VillagerState.IDLE
                    villager.target = None

    def _satiation_speed_factor(self, villager: Villager) -> float:
        """1.0 when full, down to 0.4 when starving — scales move/work pace."""
        s = max(0.0, min(1.0, villager.satiation))
        return 0.4 + 0.6 * s

    def _villager_move_interval(self, villager: Villager) -> int:
        factor = self._satiation_speed_factor(villager) * max(
            0.1, villager.food_walk_mult
        )
        scaled = self.balance.get_int("VILLAGER_MOVE_INTERVAL") * self._day_length_scale()
        return max(4, int(round(scaled / factor)))

    def _villager_work_interval(self, villager: Villager) -> int:
        factor = self._satiation_speed_factor(villager) * max(
            0.1, villager.food_work_mult
        )
        scaled = self.balance.get_int("VILLAGER_WORK_INTERVAL") * self._day_length_scale()
        return max(6, int(round(scaled / factor)))

    def _food_count(self, storage) -> int:
        return sum(getattr(storage, key, 0) for key in VILLAGER_FOOD_KEYS)

    def _food_store_at(self, pos: tuple[int, int]):
        if pos == self.world.home_pos:
            return self.home_storage
        for building in self.buildings.values():
            if building.center_cell() == pos and building.kind in (
                BuildingKind.FORAGER,
                BuildingKind.HUNTER,
                BuildingKind.FISHER,
                BuildingKind.FARM,
                BuildingKind.KITCHEN,
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
                BuildingKind.KITCHEN,
            ):
                continue
            if self._food_count(building) > 0:
                options.append(building.center_cell())
        if not options:
            return None
        return min(
            options,
            key=lambda p: abs(p[0] - villager.x) + abs(p[1] - villager.y),
        )

    def _eat_random_from(
        self, storage, villager: Villager | None = None
    ) -> int:
        """Consume food toward a meal. Returns how many items eaten.

        One unit of each food type, up to ``MAX_FOOD_TYPES_PER_MEAL`` types,
        preferring highest-satiation foods first. Stops early once the villager
        reaches their ration refill target (or a full meal for non-villager calls).
        """
        target = (
            villager.ration_refill()
            if villager is not None
            else 0.75
        )
        available = [
            key for key in VILLAGER_FOOD_KEYS if getattr(storage, key, 0) > 0
        ]
        # Highest satiation first; prefer stronger walk buff (cooked over raw).
        available.sort(
            key=lambda k: (
                -food_def(k).satiation,
                -food_def(k).walk_speed,
                k,
            ),
        )
        eaten_keys: list[str] = []
        points = 0.0
        for key in available:
            if len(eaten_keys) >= MAX_FOOD_TYPES_PER_MEAL:
                break
            if villager is not None and villager.satiation >= target and eaten_keys:
                break
            if villager is None and points >= 5.0 and eaten_keys:
                break
            setattr(storage, key, getattr(storage, key) - 1)
            self.record_consumed(key, 1)
            fx = food_def(key)
            points += fx.satiation
            eaten_keys.append(key)
            if villager is not None:
                villager.satiation = min(
                    1.0, villager.satiation + satiation_from_points(fx.satiation)
                )
                if villager.satiation >= target:
                    break
            elif points >= 5.0:
                break
        if villager is not None and eaten_keys:
            villager.last_meal = list(eaten_keys)
            walk, work, hunger = combine_meal_buffs(eaten_keys)
            villager.apply_food_buffs(walk, work, hunger)
        return len(eaten_keys)

    def _update_seek_food(self, villager: Villager) -> None:
        """Walk to nearest food store and eat according to ration mode."""
        villager.seeking_food = True

        # Eat from carried food first.
        if self._food_count(villager.inventory) > 0:
            eaten = self._eat_random_from(villager.inventory, villager)
            if eaten > 0:
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
            eaten = self._eat_random_from(storage, villager)
            if eaten > 0:
                villager.seeking_food = False
            else:
                villager.seeking_food = villager.needs_food()
            villager.work_cooldown = self._villager_work_interval(villager)
            return
        self._step_villager_toward(villager, dest)

    def _try_idle_transport(self, villager: Villager) -> bool:
        """Run transport when a higher priority left the worker idle but haul work exists."""
        if not self._is_general_hauler(villager):
            return False
        if WorkPriority.TRANSPORT not in villager.priorities:
            return False
        if villager.state != VillagerState.IDLE:
            return False
        if not self._transport_has_work(villager):
            return False
        self._update_hauler(villager)
        return True

    def _is_general_hauler(self, villager: Villager) -> bool:
        """Unassigned / home haulers — handle all village transport."""
        return villager.building_id is None

    def _uses_general_haul_update(self, villager: Villager) -> bool:
        """True when mid-haul should use the village hauler state machine."""
        if self._is_general_hauler(villager):
            return True
        # Workplace helper hauling a foreign building (not own assigned transport).
        hid = villager.haul_building_id
        return hid is not None and hid != villager.building_id

    def _building_can_produce(self, building: Building) -> bool:
        """True while the station can still run a recipe from current stock."""
        if building.is_processor():
            return building.craftable_recipe() is not None
        if building.is_splitter() or (
            building.kind == BuildingKind.FORESTER
            and building.work_mode == WorkMode.ALL
        ):
            return building.craftable_split_recipe() is not None
        return False

    def _claimed_haul_targets(self, exclude_id: int) -> set[int]:
        """Buildings already reserved by another hauler / assigned transporter."""
        claimed: set[int] = set()
        for other in self.villagers:
            if other.id == exclude_id:
                continue
            if other.haul_building_id is not None:
                claimed.add(other.haul_building_id)
        return claimed

    def _owns_haul_claim(self, villager: Villager, building_id: int) -> bool:
        """True if this villager may keep/take the haul claim.

        Lowest id among *active* haulers (HAULING/DELIVERING) wins. Idle or
        working-elsewhere claims are treated as stale so coworkers can take over (S8).
        """
        for other in self.villagers:
            if other.id == villager.id:
                continue
            if other.haul_building_id != building_id:
                continue
            if other.state not in (VillagerState.HAULING, VillagerState.DELIVERING):
                continue
            if other.id < villager.id:
                return False
        return True

    def _register_field_claim(
        self, villager: Villager, cell: tuple[int, int] | None
    ) -> None:
        """Add a field work cell to this tick's live claim set (S12)."""
        if cell is None:
            return
        tick_cells = getattr(self, "_tick_claim_cells", None)
        if tick_cells is None:
            return
        if self._is_station_or_home_cell(cell):
            return
        by_v = getattr(self, "_tick_claim_by_villager", None)
        if by_v is None:
            return
        cells = by_v.setdefault(villager.id, set())
        cells.add(cell)
        tick_cells.add(cell)

    def _register_animal_claim(self, animal_id: int | None) -> None:
        if animal_id is None:
            return
        claimed = getattr(self, "_tick_claim_animals", None)
        if claimed is not None:
            claimed.add(animal_id)

    def _register_colony_claim(self, colony_id: int | None) -> None:
        if colony_id is None:
            return
        claimed = getattr(self, "_tick_claim_colonies", None)
        if claimed is not None:
            claimed.add(colony_id)

    def _register_fish_claim(self, fish_id: int | None) -> None:
        if fish_id is None:
            return
        claimed = getattr(self, "_tick_claim_fish", None)
        if claimed is not None:
            claimed.add(fish_id)

    def _claimed_work_cells(self, exclude_id: int) -> set[tuple[int, int]]:
        """Map cells already targeted by another villager's primary work."""
        claimed = getattr(self, "_tick_claim_cells", None)
        if claimed is None:
            # Fallback outside the villager tick (diagnostics).
            stations = {b.center_cell() for b in self.buildings.values()}
            stations.add(self.world.home_pos)
            out: set[tuple[int, int]] = set()
            for other in self.villagers:
                if other.id == exclude_id:
                    continue
                if (
                    other.target is not None
                    and other.state == VillagerState.WORKING
                    and other.target not in stations
                ):
                    out.add(other.target)
                if other.hunt_meat_pos is not None:
                    out.add(other.hunt_meat_pos)
                if other.fish_catch_pos is not None:
                    out.add(other.fish_catch_pos)
                if other.fish_post_pos is not None:
                    out.add(other.fish_post_pos)
            return out
        mine = self._tick_claim_by_villager.get(exclude_id)
        if not mine:
            return claimed
        return claimed - mine

    def _claimed_animal_ids(self, exclude_id: int) -> set[int]:
        claimed = getattr(self, "_tick_claim_animals", None)
        if claimed is None:
            return {
                other.hunt_animal_id
                for other in self.villagers
                if other.id != exclude_id and other.hunt_animal_id is not None
            }
        out = set(claimed)
        v = next((x for x in self.villagers if x.id == exclude_id), None)
        if v is not None and v.hunt_animal_id is not None:
            out.discard(v.hunt_animal_id)
        return out

    def _claimed_colony_ids(self, exclude_id: int) -> set[int]:
        claimed = getattr(self, "_tick_claim_colonies", None)
        if claimed is None:
            ids: set[int] = set()
            for other in self.villagers:
                if other.id == exclude_id:
                    continue
                if other.hunt_colony_id is not None:
                    ids.add(other.hunt_colony_id)
                if other.forage_colony_id is not None:
                    ids.add(other.forage_colony_id)
            return ids
        out = set(claimed)
        v = next((x for x in self.villagers if x.id == exclude_id), None)
        if v is not None:
            if v.hunt_colony_id is not None:
                out.discard(v.hunt_colony_id)
            if v.forage_colony_id is not None:
                out.discard(v.forage_colony_id)
        return out

    def _claimed_fish_ids(self, exclude_id: int) -> set[int]:
        claimed = getattr(self, "_tick_claim_fish", None)
        if claimed is None:
            return {
                other.fish_target_id
                for other in self.villagers
                if other.id != exclude_id and other.fish_target_id is not None
            }
        out = set(claimed)
        v = next((x for x in self.villagers if x.id == exclude_id), None)
        if v is not None and v.fish_target_id is not None:
            out.discard(v.fish_target_id)
        return out

    def _workplace_recipe_keys(self, building: Building) -> frozenset[str]:
        """Resource keys tied to this workplace's recipes and gather outputs."""
        from recipes import KITCHEN_FUEL_KEY

        keys: set[str] = set()
        if building.is_processor():
            keys.update(building.processor_input_keys())
            keys.update(building.processor_output_keys())
            if building.kind == BuildingKind.KITCHEN:
                keys.add(KITCHEN_FUEL_KEY)
        elif building.is_splitter():
            keys.update(("logs", "hardwood_logs", "wood"))
        elif building.kind == BuildingKind.FARM:
            keys.update(building.gather_deposit_keys())
            keys.update(SEED_KEYS)
        elif building.kind == BuildingKind.HUNTER:
            keys.add("meat")
        elif building.kind == BuildingKind.FISHER:
            keys.add("fish")
        elif building.kind == BuildingKind.FORAGER:
            keys.update(building.gather_deposit_keys())
        elif building.kind == BuildingKind.FORESTER:
            keys.update(building.gather_deposit_keys())
        return frozenset(keys)

    def _inventory_has_workplace_keys(
        self, inventory: Inventory, building: Building
    ) -> bool:
        return any(
            int(getattr(inventory, key, 0)) > 0
            for key in self._workplace_recipe_keys(building)
        )

    def _workplace_recipe_haulable(self, building: Building) -> int:
        recipe_keys = self._workplace_recipe_keys(building)
        return sum(
            building.haulable_amount(key)
            for key in building.haul_keys()
            if key in recipe_keys
        )

    def _workplace_needs_home_supply(self, building: Building) -> bool:
        if not building.needs_supplied():
            return False
        demand = building.supply_demand()
        if not demand:
            return False
        return any(int(getattr(self.home_storage, key, 0)) > 0 for key in demand)

    def _gather_cargo_needs_delivery(
        self, villager: Villager, building: Building
    ) -> bool:
        """True when the worker should stop gathering and deposit cargo."""
        inv = villager.inventory
        if inv.is_empty:
            return False
        if inv.is_full or not inv.can_add(1):
            return True
        # Farm / forager: deliver whenever the next enabled yield won't fit —
        # even if cargo is "wrong" (e.g. leftover wood), so space frees up.
        if building.kind == BuildingKind.FARM:
            return not inv.can_add(self._farm_produce_yield_budget())
        if building.kind == BuildingKind.FORAGER:
            for recipe in building.enabled_recipes():
                need = self._forage_yield_amount(recipe.name)
                key = "wood" if recipe.name == "wood" else recipe.name
                if inv.can_add(need, key=key):
                    return False
            return True
        return False

    def _forage_yield_amount(self, key: str) -> int:
        """Cargo units one collect of this forager recipe needs."""
        if key == "mushrooms":
            return MUSHROOM_YIELD
        if key == "honey":
            return HONEY_PER_BEE_LEVEL
        if key == "reeds":
            return REED_YIELD
        if key == "berries":
            return 1
        if key == "wood":
            return 1
        return WILD_PRODUCE_YIELD

    def _clear_gather_stickies(self, villager: Villager) -> None:
        """Drop mid-task sticky targets so full inventory can deliver."""
        villager.target = None
        villager.hunt_animal_id = None
        villager.hunt_colony_id = None
        villager.hunt_meat_pos = None
        villager.fish_target_id = None
        villager.fish_catch_pos = None
        villager.fish_post_pos = None
        villager.forage_colony_id = None
        self._clear_villager_path(villager)

    def _force_assigned_delivery(
        self, villager: Villager, building: Building
    ) -> bool:
        """Clear stickies and run assigned transport (deposit / haul)."""
        self._clear_gather_stickies(villager)
        return self._maybe_assigned_transport(villager, building)

    def _workplace_primary_available(
        self, villager: Villager, building: Building
    ) -> bool:
        """True when the worker can perform their main job this tick (not transport)."""
        if building.kind in (
            BuildingKind.MILL,
            BuildingKind.KITCHEN,
            BuildingKind.CRAFT_BENCH,
            BuildingKind.ALCHEMIST,
        ):
            tool = WORKPLACE_TOOL.get(building.kind)
            if tool and not villager.inventory.has_equipped_tool(tool):
                return self._tool_fetchable(villager, tool)
            # Stay on craft cooldown / keep crafting — never bounce to home mid-cycle.
            if villager.work_cooldown > 0:
                return True
            if building.craftable_recipe() is not None:
                return True
            # Carrying inputs the station needs — walk back and deposit (not home haul).
            if building.can_accept_from(villager.inventory):
                return True
            return False

        if building.kind == BuildingKind.FORESTER and building.work_mode == WorkMode.SPLIT:
            if not villager.inventory.has_equipped_tool("axe"):
                return self._tool_fetchable(villager, "axe")
            if villager.work_cooldown > 0:
                return True
            if building.craftable_split_recipe() is not None:
                return True
            if building.can_accept_from(villager.inventory):
                return True
            return False

        # Full / harvest-blocked cargo must deliver — sticky targets must not block that.
        if self._gather_cargo_needs_delivery(villager, building):
            return False

        # Sticky field targets only — home/station centres are tool-fetch or craft walks,
        # not primary gather work (those must not block delivery / idle).
        if (
            villager.target is not None
            and villager.state == VillagerState.WORKING
            and not self._is_station_or_home_cell(villager.target)
        ):
            return True
        if villager.hunt_animal_id is not None or villager.hunt_meat_pos is not None:
            return True
        if villager.hunt_colony_id is not None:
            return True
        if villager.forage_colony_id is not None:
            return True
        if (
            villager.fish_target_id is not None
            or villager.fish_catch_pos is not None
            or villager.fish_post_pos is not None
        ):
            if fishing_allowed(self.calendar_day):
                return True

        if building.kind == BuildingKind.FORESTER:
            if self._forester_needs_axe(building) and not villager.inventory.has_equipped_tool(
                "axe"
            ):
                return self._tool_fetchable(villager, "axe")
            if (
                villager.inventory.is_full
                and building.has_gather_cargo(villager.inventory)
            ):
                return False
            if building.work_mode == WorkMode.ALL:
                return self._pick_forester_all_work(villager, building) is not None
            if building.work_mode == WorkMode.SPLIT:
                return building.craftable_split_recipe() is not None
            return self._find_work_in_building(villager, building) is not None

        if building.kind == BuildingKind.HUNTER:
            if not villager.inventory.has_equipped_tool("spear"):
                return self._tool_fetchable(villager, "spear")
            if villager.inventory.is_full:
                return False
            # Cheap: stickies or any prey/meat in search radius (no pathfinding).
            if (
                villager.hunt_animal_id is not None
                or villager.hunt_colony_id is not None
                or villager.hunt_meat_pos is not None
            ):
                return True
            origin = (villager.x, villager.y)
            if any(
                building.allows_hunt_kind(a.kind.name)
                and self._within_work_search(origin, (a.x, a.y))
                for a in self.wildlife.animals
            ):
                return True
            from wildlife import AnimalKind

            if building.allows_hunt_kind("rabbit") and any(
                c.kind == AnimalKind.RABBIT
                and c.can_harvest()
                and self._within_work_search(origin, (c.x, c.y))
                for c in self.wildlife.colonies
            ):
                return True
            return self._meat_deposit_available(building, villager.id)

        if building.kind == BuildingKind.FISHER:
            if not fishing_allowed(self.calendar_day):
                return False
            if not villager.inventory.has_equipped_tool("fishing_rod"):
                return self._tool_fetchable(villager, "fishing_rod")
            if villager.inventory.is_full:
                return False
            # Cheap availability only — full shore pathfinding runs in update.
            if villager.fish_post_pos is not None or villager.fish_catch_pos is not None:
                return True
            if self._fisher_candidate_fish(villager, building):
                return True
            return self._fish_deposit_available(building, villager.id)

        if building.kind == BuildingKind.FARM:
            if not villager.inventory.has_equipped_tool("hoe"):
                return self._tool_fetchable(villager, "hoe")
            if self._gather_cargo_needs_delivery(villager, building):
                return False
            return self._find_farm_work(villager, building) is not None

        if building.kind == BuildingKind.FORAGER:
            if (
                villager.inventory.is_full
                and building.has_gather_cargo(villager.inventory)
            ):
                return False
            return self._find_work_in_building(villager, building) is not None

        return self._find_work_in_building(villager, building) is not None

    def _assigned_transport_has_work(
        self, villager: Villager, building: Building
    ) -> bool:
        """Recipe-related supply/pickup for an assigned worker when primary work is blocked."""
        if self._workplace_primary_available(villager, building):
            return False
        if not villager.inventory.is_empty:
            return True
        # Only one coworker handles shared supply / output pickup.
        if not self._owns_haul_claim(villager, building.id):
            return False
        if self._workplace_needs_home_supply(building):
            return True
        # Leave produce for general haulers unless none exist, none are serving
        # this building, or the output bay is backing up (S9).
        if self._workplace_recipe_haulable(building) > 0 and (
            not self._has_general_hauler()
            or self._workplace_output_backed_up(building)
            or not self._general_hauler_serving(building.id)
        ):
            return True
        return False

    def _general_hauler_serving(self, building_id: int) -> bool:
        return any(
            self._is_general_hauler(v)
            and v.haul_building_id == building_id
            and v.state in (VillagerState.HAULING, VillagerState.DELIVERING)
            for v in self.villagers
        )

    def _workplace_output_backed_up(self, building: Building) -> bool:
        """True when output stock is high enough that assigned workers should clear it."""
        haulable = self._workplace_recipe_haulable(building)
        if haulable <= 0:
            return False
        if building.output_capacity > 0:
            return building.output_stored_total() >= max(
                1, (building.output_capacity * 3) // 4
            )
        return haulable >= max(4, INVENTORY_CAPACITY // 2)

    def _has_general_hauler(self) -> bool:
        cached = getattr(self, "_tick_has_general_hauler", None)
        if cached is not None:
            return cached
        return any(self._is_general_hauler(v) for v in self.villagers)

    def _assigned_transport_destination(
        self, villager: Villager, building: Building
    ) -> tuple[int, int]:
        """Where an assigned worker should drop personal cargo.

        Processors/splitters take inputs at the station. Gather workplaces must
        not take their own outputs back (withdraw → redeposit loops); those
        go to the storehouse. Plant stock still returns to the workplace.
        """
        home = self.world.home_pos
        inv = villager.inventory
        if building.is_processor() or building.is_splitter():
            if building.can_accept_from(inv):
                return building.center_cell()
            return home
        if (
            building.kind == BuildingKind.FORESTER
            and building.work_mode == WorkMode.SPLIT
            and building.can_accept_from(inv)
        ):
            return building.center_cell()
        if building.allows_planting() and building.holding_only_plantables(inv):
            return building.center_cell()
        return home

    def _withdraw_workplace_recipe_output(
        self, villager: Villager, building: Building
    ) -> None:
        recipe_keys = self._workplace_recipe_keys(building)
        for key in building.haul_keys():
            if key not in recipe_keys:
                continue
            while (
                building.haulable_amount(key) > 0
                and villager.inventory.can_add(1, key=key)
            ):
                setattr(building, key, int(getattr(building, key)) - 1)
                setattr(
                    villager.inventory,
                    key,
                    int(getattr(villager.inventory, key)) + 1,
                )

    def _set_workplace_idle(self, villager: Villager) -> None:
        """Clear stickies / haul claim and park the worker as IDLE."""
        self._clear_gather_stickies(villager)
        villager.haul_building_id = None
        villager.state = VillagerState.IDLE
        villager.target = None

    def _update_assigned_transport(
        self, villager: Villager, building: Building
    ) -> bool:
        """Supply own workplace or clear recipe output when primary task is blocked."""
        if not self._assigned_transport_has_work(villager, building):
            villager.haul_building_id = None
            if villager.state in (VillagerState.HAULING, VillagerState.DELIVERING):
                villager.state = VillagerState.IDLE
                villager.target = None
            return False

        home = self.world.home_pos
        station = building.center_cell()

        if not villager.inventory.is_empty:
            # Personal cargo — no exclusive building claim (coworkers may also deliver).
            villager.haul_building_id = None
            dest = self._assigned_transport_destination(villager, building)
            villager.state = VillagerState.DELIVERING
            villager.target = dest
            if (villager.x, villager.y) == dest:
                if villager.work_cooldown == 0:
                    if dest == home:
                        self._deposit_home(villager.inventory, status=False)
                    else:
                        building.deposit_from_inventory(villager.inventory)
                    villager.work_cooldown = self._villager_work_interval(villager)
                    villager.state = VillagerState.IDLE
                    villager.target = None
                return True
            self._step_villager_toward(villager, dest)
            return True

        villager.haul_building_id = building.id

        if self._workplace_needs_home_supply(building):
            if not self._owns_haul_claim(villager, building.id):
                villager.haul_building_id = None
                return False
            villager.state = VillagerState.HAULING
            villager.target = home
            if (villager.x, villager.y) != home:
                self._step_villager_toward(villager, home)
                return True
            if villager.work_cooldown > 0:
                return True
            taken = self._withdraw_processor_supply(villager, building)
            villager.work_cooldown = self._villager_work_interval(villager)
            if taken <= 0:
                villager.haul_building_id = None
                villager.state = VillagerState.IDLE
                villager.target = None
            return True

        if self._workplace_recipe_haulable(building) > 0 and (
            not self._has_general_hauler()
            or self._workplace_output_backed_up(building)
            or not self._general_hauler_serving(building.id)
        ):
            if not self._owns_haul_claim(villager, building.id):
                villager.haul_building_id = None
                return False
            villager.state = VillagerState.HAULING
            villager.target = station
            if (villager.x, villager.y) != station:
                self._step_villager_toward(villager, station)
                return True
            if villager.work_cooldown > 0:
                return True
            self._withdraw_workplace_recipe_output(villager, building)
            villager.work_cooldown = self._villager_work_interval(villager)
            if not villager.inventory.is_empty:
                villager.state = VillagerState.DELIVERING
                villager.target = home
            else:
                villager.haul_building_id = None
                villager.state = VillagerState.IDLE
                villager.target = None
            return True

        villager.haul_building_id = None
        return False

    def _maybe_assigned_transport(
        self, villager: Villager, building: Building
    ) -> bool:
        """When primary work is blocked, run recipe-related transport only.

        Returns True when the tick is handled (transport ran, or worker idled).
        Returns False when primary work is still available.
        """
        if self._workplace_primary_available(villager, building):
            return False
        if self._update_assigned_transport(villager, building):
            return True
        self._set_workplace_idle(villager)
        return True

    def _hauler_pickup_from_building(
        self, villager: Villager, building: Building
    ) -> bool:
        """Withdraw haulable goods from a workplace. Returns True if carrying cargo."""
        if building.haulable_total() <= 0:
            return False
        if villager.work_cooldown > 0:
            return not villager.inventory.is_empty
        building.withdraw_to_inventory(villager.inventory)
        villager.work_cooldown = self._villager_work_interval(villager)
        return not villager.inventory.is_empty

    def _hauler_exchange_at_processor(
        self, villager: Villager, building: Building
    ) -> None:
        """One work tick: drop off inputs, then fill remaining space with produce."""
        building.deposit_supply_from(villager.inventory)
        # Only outputs (not excess ingredients we may have just stocked).
        out_keys = building.processor_output_keys()
        if out_keys and not villager.inventory.is_full:
            if any(building.haulable_amount(k) > 0 for k in out_keys):
                building.withdraw_to_inventory(villager.inventory, keys=out_keys)
        villager.work_cooldown = self._villager_work_interval(villager)

    def _workplace_has_work(self, villager: Villager) -> bool:
        building = self.buildings.get(villager.building_id) if villager.building_id else None
        if building is None:
            return False
        if (
            villager.haul_building_id == building.id
            and villager.state in (VillagerState.HAULING, VillagerState.DELIVERING)
        ):
            return True
        if self._workplace_primary_available(villager, building):
            return True
        return self._assigned_transport_has_work(villager, building)

    def _processor_has_work(self, villager: Villager, building: Building) -> bool:
        return self._workplace_has_work(villager)

    def _forester_split_has_work(self, villager: Villager, building: Building) -> bool:
        return self._workplace_has_work(villager)

    def _update_forester_split(self, villager: Villager, building: Building) -> None:
        """Forester split mode: stay on-site and process logs into wood."""
        # Deposit / haul before tool fetch so full packs aren't stuck without an axe.
        if not villager.inventory.is_empty and not building.can_accept_from(
            villager.inventory
        ):
            if self._force_assigned_delivery(villager, building):
                return
        if not self._ensure_forester_axe(villager, building):
            if self._maybe_assigned_transport(villager, building):
                return
            return
        if self._maybe_assigned_transport(villager, building):
            return

        bx, by = building.center_cell()
        villager.target = (bx, by)
        villager.state = VillagerState.WORKING

        if (villager.x, villager.y) != (bx, by):
            if villager.move_cooldown > 0:
                return
            if not self._step_villager_toward(villager, (bx, by)):
                self._clear_villager_path(villager)
            return

        building.deposit_from_inventory(villager.inventory)

        if not villager.inventory.has_equipped_tool("axe"):
            return

        self._forester_try_split(villager, building)

    def _work_target_valid(
        self, villager: Villager, building: Building, pos: tuple[int, int]
    ) -> bool:
        """True if a sticky gather/plant target is still worth walking to."""
        x, y = pos
        cell = self.world.get_cell(x, y)
        if cell is None or not self.world.is_walkable(x, y):
            return False
        if building.kind == BuildingKind.FORAGER and building.allows_forage_key("honey"):
            from wildlife import AnimalKind

            colony = self.wildlife.colony_at(x, y)
            if (
                colony is not None
                and colony.kind == AnimalKind.BEE
                and colony.can_harvest()
                and colony.id not in self._claimed_colony_ids(villager.id)
            ):
                return True
        can_plant_sapling, can_plant_berry, can_plant_herb = self._can_plant_from(
            villager, building
        )
        mode = building.work_mode
        allow_plant = mode in (WorkMode.PLANT, WorkMode.ALL) and building.allows_planting()
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
                and self._building_allows_cell(building, cell)
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
        ) and self._building_allows_cell(building, cell)

    def _transport_has_work(self, villager: Villager) -> bool:
        if not villager.inventory.is_empty:
            return True
        if self._find_haul_source(villager) is not None:
            return True
        return self._find_processor_needing_supply_for(villager) is not None

    def _construction_delivery_active(self, villager: Villager) -> bool:
        """True while this villager should fetch/deliver construction materials."""
        if villager.construction_id is None:
            return False
        return self._construction_has_work(villager)

    def _construction_has_work(self, villager: Villager) -> bool:
        if not self.construction_sites:
            if villager.construction_id is not None:
                villager.construction_id = None
            return False

        # Carrying wood/rock only counts if some site still needs it.
        # Otherwise release the claim so transport can clear leftover cargo
        # (e.g. extra wood after a site's wood quota is already full).
        if villager.inventory.logs > 0 or villager.inventory.rock > 0:
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
            elif (site.wood_needed > 0 and self._material_available("logs")) or (
                site.rock_needed > 0 and self._material_available("rock")
            ):
                return True
            else:
                # Assigned to a half-built site with nothing left to fetch.
                villager.construction_id = None

        for site in self.construction_sites.values():
            if not site.materials_ready:
                if site.wood_needed > 0 and self._material_available("logs"):
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

    def _carrying_build_mats(self, villager: Villager) -> bool:
        return villager.inventory.logs > 0 or villager.inventory.rock > 0

    def _leftover_build_mats_need_home(self, villager: Villager) -> bool:
        """True when carrying construction mats no site can still accept."""
        if not self._carrying_build_mats(villager):
            return False
        return self._find_site_needing_materials(villager) is None

    def _update_leftover_build_mats(self, villager: Villager) -> None:
        """Deposit leftover wood/rock at workplace (if accepted) or home."""
        if not self._leftover_build_mats_need_home(villager):
            return
        villager.construction_id = None
        villager.haul_building_id = None
        dest = self.world.home_pos
        building = (
            self.buildings.get(villager.building_id) if villager.building_id else None
        )
        if building is not None and building.can_accept_from(villager.inventory):
            dest = building.center_cell()
        villager.state = VillagerState.DELIVERING
        villager.target = dest
        if (villager.x, villager.y) == dest:
            if villager.work_cooldown > 0:
                return
            if dest == self.world.home_pos:
                self._deposit_home(villager.inventory, status=False)
            elif building is not None:
                building.deposit_from_inventory(villager.inventory)
            villager.work_cooldown = self._villager_work_interval(villager)
            villager.state = VillagerState.IDLE
            villager.target = None
            return
        self._step_villager_toward(villager, dest)

    def _update_builder(self, villager: Villager) -> None:
        site = None
        if villager.construction_id is not None:
            site = self.construction_sites.get(villager.construction_id)
            if site is None or site.is_complete:
                villager.construction_id = None
                site = None

        carrying = self._carrying_build_mats(villager)

        # Deliver carried wood/rock to a needing site.
        if carrying:
            useful = self._find_site_needing_materials(villager)
            if useful is None:
                # Leftover mats no site needs — send to workplace/home.
                self._update_leftover_build_mats(villager)
                return
            # Prefer current site only if it can still take what we carry.
            if site is None or not (
                (site.wood_needed > 0 and villager.inventory.logs > 0)
                or (site.rock_needed > 0 and villager.inventory.rock > 0)
            ):
                site = useful
                villager.construction_id = site.id
            if (villager.x, villager.y) == site.center_cell():
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
                if self._carrying_build_mats(villager):
                    if (site.wood_needed > 0 and villager.inventory.logs > 0) or (
                        site.rock_needed > 0 and villager.inventory.rock > 0
                    ):
                        return  # still depositing next tick (cooldown)
                    other = self._find_site_needing_materials(villager)
                    if other is not None:
                        villager.construction_id = other.id
                        self._step_villager_toward(villager, other.center_cell())
                        villager.state = VillagerState.DELIVERING
                        return
                    self._update_leftover_build_mats(villager)
                    return
                # Empty hands — fall through to build or fetch more.
            else:
                self._step_villager_toward(villager, site.center_cell())
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
            if (villager.x, villager.y) != site.center_cell():
                self._step_villager_toward(villager, site.center_cell())
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
            villager.state = VillagerState.BUILDING
            return
        self._withdraw_build_materials(villager, site, source)
        if villager.inventory.logs > 0 or villager.inventory.rock > 0:
            villager.state = VillagerState.DELIVERING
            villager.target = site.center_cell()
        else:
            villager.construction_id = None
            villager.state = VillagerState.IDLE

    def _find_site_needing_materials(self, villager: Villager) -> ConstructionSite | None:
        candidates = [
            s
            for s in self.construction_sites.values()
            if (s.wood_needed > 0 and villager.inventory.logs > 0)
            or (s.rock_needed > 0 and villager.inventory.rock > 0)
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda s: abs(s.center_cell()[0] - villager.x)
            + abs(s.center_cell()[1] - villager.y),
        )

    def _find_best_construction_site(self, villager: Villager) -> ConstructionSite | None:
        ready = [s for s in self.construction_sites.values() if s.materials_ready and not s.is_complete]
        if ready:
            return min(
                ready,
                key=lambda s: abs(s.center_cell()[0] - villager.x)
                + abs(s.center_cell()[1] - villager.y),
            )
        needing = [
            s
            for s in self.construction_sites.values()
            if not s.materials_ready
            and (
                (s.wood_needed > 0 and self._material_available("logs"))
                or (s.rock_needed > 0 and self._material_available("rock"))
            )
        ]
        if not needing:
            return None
        return min(
            needing,
            key=lambda s: abs(s.center_cell()[0] - villager.x)
            + abs(s.center_cell()[1] - villager.y),
        )

    def _find_material_source(
        self, villager: Villager, want_wood: bool, want_rock: bool
    ) -> tuple[int, int, str] | None:
        """Return (x, y, 'home'|'bID') for nearest wood/rock stock."""
        options: list[tuple[int, int, str, int]] = []
        hx, hy = self.world.home_pos
        if (want_wood and self.home_storage.logs > 0) or (want_rock and self.home_storage.rock > 0):
            options.append((hx, hy, "home", abs(hx - villager.x) + abs(hy - villager.y)))
        for building in self.buildings.values():
            if (want_wood and building.logs > 0) or (want_rock and building.rock > 0):
                cx, cy = building.center_cell()
                options.append(
                    (
                        cx,
                        cy,
                        f"b{building.id}",
                        abs(cx - villager.x) + abs(cy - villager.y),
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
                pull(self.home_storage, "logs", take_wood)
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
                pull(building, "logs", take_wood)
            if site.rock_needed > 0:
                pull(
                    building,
                    "rock",
                    min(take_rock, villager.inventory.capacity - villager.inventory.cargo_total),
                )
    def _deposit_materials_at_site(self, villager: Villager, site: ConstructionSite) -> None:
        while site.wood_needed > 0 and villager.inventory.logs > 0:
            villager.inventory.logs -= 1
            site.have_wood += 1
            self.record_consumed("logs", 1)
        while site.rock_needed > 0 and villager.inventory.rock > 0:
            villager.inventory.rock -= 1
            site.have_rock += 1
            self.record_consumed("rock", 1)

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
        if building.kind == BuildingKind.FORESTER and building.work_mode == WorkMode.SPLIT:
            self._update_forester_split(villager, building)
            return
        if building.kind == BuildingKind.FORESTER and building.work_mode == WorkMode.ALL:
            self._update_forester_all(villager, building)
            return
        if building.kind == BuildingKind.FORESTER and self._forester_needs_axe(building):
            if self._gather_cargo_needs_delivery(villager, building):
                self._force_assigned_delivery(villager, building)
                return
            if not self._ensure_forester_axe(villager, building):
                self._maybe_assigned_transport(villager, building)
                return
        if building.kind in (
            BuildingKind.MILL,
            BuildingKind.KITCHEN,
            BuildingKind.CRAFT_BENCH,
            BuildingKind.ALCHEMIST,
        ):
            self._update_processor(villager, building)
            return

        if self._maybe_assigned_transport(villager, building):
            return

        # Collect plant stock from workplace / home before planting.
        if self._update_plant_stock_withdraw(villager, building):
            return

        # Keep sticky target if still valid (avoids full-map scan every tick).
        if villager.target is not None and not self._work_target_valid(
            villager, building, villager.target
        ):
            villager.target = None
            villager.forage_colony_id = None
            villager._path_cache = None  # type: ignore[attr-defined]
            villager._path_goal = None  # type: ignore[attr-defined]

        target = villager.target
        if target is None:
            target = self._find_work_in_building(villager, building)
            if target is None:
                self._maybe_assigned_transport(villager, building)
                return
            villager.target = target
            self._register_field_claim(villager, target)

        villager.state = VillagerState.WORKING
        if self._gather_cargo_needs_delivery(villager, building):
            self._force_assigned_delivery(villager, building)
            return

        if (villager.x, villager.y) == target:
            if villager.work_cooldown > 0:
                return
            self._villager_perform(villager, building, target)
            villager.work_cooldown = self._villager_work_interval(villager)
            if getattr(villager, "_return_after_harvest", False):
                villager._return_after_harvest = False  # type: ignore[attr-defined]
                self._force_assigned_delivery(villager, building)
                return
            # Became full / next yield won't fit — don't keep sticky standing.
            if self._gather_cargo_needs_delivery(villager, building):
                self._force_assigned_delivery(villager, building)
                return
            # Resource may be gone — refresh next tick.
            if not self._work_target_valid(villager, building, target):
                villager.target = None
                villager._path_cache = None  # type: ignore[attr-defined]
                villager._path_goal = None  # type: ignore[attr-defined]
        else:
            if villager.move_cooldown > 0:
                return
            self._step_or_clear_field_target(villager, target)

    def _update_forester_all(self, villager: Villager, building: Building) -> None:
        """ALL mode: choose collect / split / plant by recipe priority (1 highest)."""
        if self._gather_cargo_needs_delivery(villager, building):
            self._force_assigned_delivery(villager, building)
            return
        if self._forester_needs_axe(building) and not self._ensure_forester_axe(
            villager, building
        ):
            self._maybe_assigned_transport(villager, building)
            return
        if self._maybe_assigned_transport(villager, building):
            return
        if self._update_plant_stock_withdraw(villager, building):
            return

        pick = self._pick_forester_all_work(villager, building)
        if pick is None:
            self._maybe_assigned_transport(villager, building)
            return
        target, kind = pick

        # Drop sticky collect/plant targets when a higher-priority task wins.
        if villager.target is not None and villager.target != target:
            villager.target = None
            self._clear_villager_path(villager)
        villager.target = target
        villager.state = VillagerState.WORKING
        if kind != "split":
            self._register_field_claim(villager, target)

        if (villager.x, villager.y) == target:
            if villager.work_cooldown > 0:
                return
            if kind == "split":
                building.deposit_from_inventory(villager.inventory)
                if self._forester_try_split(villager, building):
                    return
                # Split became unavailable mid-tick — clear and re-pick next tick.
                villager.target = None
                return
            self._villager_perform(villager, building, target)
            villager.work_cooldown = self._villager_work_interval(villager)
            if self._gather_cargo_needs_delivery(villager, building):
                self._force_assigned_delivery(villager, building)
                return
            if not self._work_target_valid(villager, building, target):
                villager.target = None
                self._clear_villager_path(villager)
        else:
            if villager.move_cooldown > 0:
                return
            self._step_or_clear_field_target(villager, target)

    def _pick_forester_all_work(
        self, villager: Villager, building: Building
    ) -> tuple[tuple[int, int], str] | None:
        """Return (target, kind) for ALL mode using recipe priorities.

        ``kind`` is ``split``, ``collect``, or ``plant``. Lower priority number
        wins; ties prefer split, then collect, then plant.
        """
        candidates: list[tuple[int, int, tuple[int, int], str]] = []

        split_recipe = building.craftable_split_recipe()
        if split_recipe is not None:
            candidates.append(
                (
                    building.get_recipe_priority(split_recipe.name),
                    0,
                    building.center_cell(),
                    "split",
                )
            )

        collect = self._find_forester_collect_by_priority(villager, building)
        if collect is not None:
            target, prio = collect
            candidates.append((prio, 1, target, "collect"))

        can_plant_sapling, _, _ = self._can_plant_from(villager, building)
        if can_plant_sapling and building.allows_planting():
            claimed = self._claimed_work_cells(villager.id)
            plant = self._find_forester_plant_target(villager, building, claimed)
            if plant is not None:
                # Planting has no recipe chip — treat as lowest urgency in ALL.
                candidates.append((RECIPE_PRIORITY_MAX, 2, plant, "plant"))

        if not candidates:
            return None
        candidates.sort()
        _prio, _tie, target, kind = candidates[0]
        return target, kind

    def _find_forester_collect_by_priority(
        self, villager: Villager, building: Building
    ) -> tuple[tuple[int, int], int] | None:
        """Closest tree for the best-priority enabled collect recipe that has work."""
        claimed = self._claimed_work_cells(villager.id)
        for recipe in building.enabled_recipes():
            target = self._find_forester_tree_target(
                villager, building, recipe.name, claimed
            )
            if target is not None:
                return target, building.get_recipe_priority(recipe.name)
        return None

    def _find_forester_tree_target(
        self,
        villager: Villager,
        building: Building,
        yield_key: str,
        claimed: set[tuple[int, int]],
    ) -> tuple[int, int] | None:
        """Closest walkable tree whose species yields ``yield_key``."""
        from trees import resolve_tree

        origin = (villager.x, villager.y)
        cells: list[tuple[int, int]] = []

        def consider(x: int, y: int) -> None:
            if (x, y) in claimed:
                return
            cell = self.world.get_cell(x, y)
            if cell is None or cell.feature != FeatureType.TREE or cell.deposit <= 0:
                return
            if not self.world.is_walkable(x, y):
                return
            if resolve_tree(cell.tree_species).yield_key != yield_key:
                return
            cells.append((x, y))

        if building.areas:
            for area in building.areas:
                if area.task_type in (
                    TaskType.PLANT_SAPLINGS,
                    TaskType.PLANT_BERRY_SEEDS,
                    TaskType.PLANT_HERB_SEEDS,
                ):
                    continue
                if area.task_type not in (
                    TaskType.CHOP_TREES,
                    TaskType.FULL_MANAGE,
                    TaskType.FULL_FORAGE,
                ):
                    continue
                for x, y in area.cells():
                    consider(x, y)
            return self._closest_of(origin, cells)

        ox, oy = building.center_cell()
        best: tuple[int, int] | None = None
        best_d = 10**9
        for y in range(self.world.rows):
            row = self.world.cells[y]
            for x in range(self.world.cols):
                if (x, y) in claimed:
                    continue
                cell = row[x]
                if cell.feature != FeatureType.TREE or cell.deposit <= 0:
                    continue
                if not self.world.is_walkable(x, y):
                    continue
                if resolve_tree(cell.tree_species).yield_key != yield_key:
                    continue
                d = abs(x - ox) + abs(y - oy)
                if d < best_d:
                    best_d = d
                    best = (x, y)
                    if best_d == 0:
                        return best
        return best

    def _find_forester_plant_target(
        self,
        villager: Villager,
        building: Building,
        claimed: set[tuple[int, int]],
    ) -> tuple[int, int] | None:
        can_plant_sapling, _, _ = self._can_plant_from(villager, building)
        if not can_plant_sapling:
            return None
        origin = (villager.x, villager.y)
        if building.areas:
            plant: list[tuple[int, int]] = []
            for area in building.areas:
                if area.task_type not in (
                    TaskType.PLANT_SAPLINGS,
                    TaskType.FULL_MANAGE,
                ):
                    continue
                for x, y in area.cells():
                    if (x, y) in claimed:
                        continue
                    cell = self.world.get_cell(x, y)
                    if cell is None or not self.world.is_walkable(x, y):
                        continue
                    if self._cell_matches_manage_plant(
                        cell, can_plant_sapling=True
                    ):
                        plant.append((x, y))
            return self._closest_of(origin, plant)
        ox, oy = building.center_cell()
        return self._find_closest_manage_plant_cell(
            ox, oy, can_plant_sapling=True, exclude_cells=claimed
        )

    def _update_farmer(self, villager: Villager, building: Building) -> None:
        """Plough, sow, and harvest according to each field plan's seasonal calendar."""
        if self._gather_cargo_needs_delivery(villager, building):
            self._force_assigned_delivery(villager, building)
            return

        if not self._ensure_work_tool(villager, "hoe"):
            self._maybe_assigned_transport(villager, building)
            return

        if self._maybe_assigned_transport(villager, building):
            return

        if not self._fields_near_farm(building):
            villager.state = VillagerState.IDLE
            villager.target = None
            return

        # Keep sticky field target so coworkers don't all pile onto the same tile.
        if villager.target is not None:
            claimed = self._claimed_work_cells(villager.id)
            if (
                villager.target in claimed
                or not self._farm_target_still_valid(villager, building, villager.target)
            ):
                villager.target = None
                self._clear_villager_path(villager)

        if villager.target is None:
            harvest_first = self._find_farm_harvest(villager, building)
            plough_or_sow = (
                None
                if harvest_first is not None
                else self._find_farm_plant_work(villager, building)
            )
            if (
                harvest_first is None
                and plough_or_sow is None
                and self._update_plant_stock_withdraw(villager, building)
            ):
                return
            target = harvest_first or plough_or_sow or self._find_farm_work(
                villager, building
            )
            if target is None:
                self._maybe_assigned_transport(villager, building)
                return
            villager.target = target
            self._register_field_claim(villager, target)

        target = villager.target
        villager.state = VillagerState.WORKING

        if (villager.x, villager.y) == target:
            if villager.work_cooldown == 0:
                self._villager_perform_farm(villager, building, target)
                villager.work_cooldown = self._villager_work_interval(villager)
                villager.target = None
                self._clear_villager_path(villager)
                if self._gather_cargo_needs_delivery(villager, building):
                    self._force_assigned_delivery(villager, building)
        else:
            self._step_or_clear_field_target(villager, target)

    def _update_processor(self, villager: Villager, building: Building) -> None:
        """Mill / Kitchen / Craft bench: stay on-site and craft from building stock."""
        # Cargo the station won't take must deliver before tool-fetch can strand the worker.
        if not villager.inventory.is_empty and not building.can_accept_from(
            villager.inventory
        ):
            if self._force_assigned_delivery(villager, building):
                return
        required = WORKPLACE_TOOL.get(building.kind)
        if required is not None and not self._ensure_work_tool(villager, required):
            if self._maybe_assigned_transport(villager, building):
                return
            return
        if self._maybe_assigned_transport(villager, building):
            return

        bx, by = building.center_cell()
        villager.target = (bx, by)
        villager.state = VillagerState.WORKING

        if (villager.x, villager.y) != (bx, by):
            if villager.move_cooldown > 0:
                return
            if not self._step_villager_toward(villager, (bx, by)):
                self._clear_villager_path(villager)
            return

        building.deposit_from_inventory(villager.inventory)

        recipe = building.craftable_recipe()
        if recipe is None or villager.work_cooldown > 0:
            return
        if building.advance_recipe_progress(recipe):
            fuel = 1 if building.kind == BuildingKind.KITCHEN else 0
            self._apply_recipe_tracked(building, recipe, fuel_wood=fuel)
            if fuel:
                building.fuel_wood = max(0, building.fuel_wood - 1)
        villager.work_cooldown = self._villager_work_interval(villager)

    def _find_farm_harvest(
        self, villager: Villager, building: Building
    ) -> tuple[int, int] | None:
        """Closest ripe crop on a nearby field (ignores calendar phase)."""
        mode = building.work_mode
        if mode not in (WorkMode.COLLECT, WorkMode.ALL):
            return None
        if not villager.inventory.can_add(self._farm_produce_yield_budget()):
            return None
        claimed = self._claimed_work_cells(villager.id)
        harvest: list[tuple[int, int]] = []
        for field_b in self._fields_near_farm(building):
            for x, y in field_b.plot_cells():
                if (x, y) in claimed:
                    continue
                if not self.world.is_walkable(x, y):
                    continue
                if self.world.crop_herb_ready(x, y):
                    need = self._farm_produce_yield_at(x, y)
                    if villager.inventory.can_add(need):
                        harvest.append((x, y))
        return self._closest_of((villager.x, villager.y), harvest)

    def _farm_target_still_valid(
        self, villager: Villager, building: Building, pos: tuple[int, int]
    ) -> bool:
        """True if a sticky farm tile is still worth working."""
        x, y = pos
        if not self.world.is_walkable(x, y):
            return False
        if self.world.crop_herb_ready(x, y):
            return (
                building.work_mode in (WorkMode.COLLECT, WorkMode.ALL)
                and villager.inventory.can_add(self._farm_produce_yield_at(x, y))
            )
        if building.work_mode not in (WorkMode.PLANT, WorkMode.ALL):
            return False
        cell = self.world.get_cell(x, y)
        if cell is None or cell.feature == FeatureType.CROP_HERB:
            return False
        plan = self._plan_at_cell(building, x, y)
        if plan is None:
            return False
        crop = CROP_BY_KEY.get(plan.crop_kind, CROP_BY_KEY["sage"])
        phase = phase_for_crop(crop, self.season)
        if not phase_allows_plough_plant(phase):
            return False
        if cell.terrain in SOIL_LIKE and cell.feature == FeatureType.NONE:
            return True
        if not is_water_terrain(cell.terrain) and cell.terrain != TerrainType.ROCK:
            return True
        return False

    def _find_farm_plant_work(
        self, villager: Villager, building: Building
    ) -> tuple[int, int] | None:
        """Closest plough or sow tile (no harvest)."""
        mode = building.work_mode
        if mode not in (WorkMode.PLANT, WorkMode.ALL):
            return None
        claimed = self._claimed_work_cells(villager.id)
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
                    if (x, y) in claimed:
                        continue
                    if not self.world.is_walkable(x, y):
                        continue
                    cell = self.world.get_cell(x, y)
                    if cell is None or cell.feature == FeatureType.CROP_HERB:
                        continue
                    if cell.terrain in SOIL_LIKE and cell.feature == FeatureType.NONE:
                        if can_sow and (
                            getattr(villager.inventory, seed_key, 0) > 0
                            or villager.inventory.can_add(1, key=seed_key)
                        ):
                            sow.append((x, y))
                        continue
                    if not is_water_terrain(cell.terrain) and cell.terrain != TerrainType.ROCK:
                        if cell.feature not in (
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
                            FeatureType.CONSTRUCTION_SITE,
                            FeatureType.STRUCTURE_PAD,
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
            fcx, fcy = farm.center_cell()
            cx = min(max(fcx, left), right)
            cy = min(max(fcy, top), bottom)
            if max(abs(cx - fcx), abs(cy - fcy)) <= FARM_FIELD_RADIUS:
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
        allow_harvest = mode in (WorkMode.COLLECT, WorkMode.ALL)
        allow_plant = mode in (WorkMode.PLANT, WorkMode.ALL)

        # Harvest uses the crop actually on the tile (ripe = harvestable any season).
        if self.world.crop_herb_ready(x, y):
            if not allow_harvest:
                return
            crop = CROP_BY_KEY.get(cell.crop_kind or "sage", CROP_BY_KEY["sage"])
            phase = phase_for_crop(crop, self.season)
            self._harvest_farm_herb(x, y, inv, status=False)
            if phase == SeasonPhase.HARVEST_PLOUGH_PLANT and allow_plant:
                self.world.plough_tile(x, y)
                self.world.apply_extraction_disturbance(x, y)
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
        if cell.terrain in SOIL_LIKE and cell.feature == FeatureType.NONE:
            seed_key = crop.seed_key
            if getattr(inv, seed_key, 0) <= 0:
                if not building.give_item_to(inv, seed_key):
                    self.home_storage.withdraw_keys_to(inv, (seed_key,))
            if getattr(inv, seed_key, 0) > 0 and self.world.sow_crop(
                x, y, crop.key, growth_ticks_for(crop, self.ticks_per_day)
            ):
                setattr(inv, seed_key, getattr(inv, seed_key) - 1)
                self.record_consumed(seed_key, 1)
                self.world.apply_disturbance(x, y)
                self._refresh_indicators()
            return
        self.world.plough_tile(x, y)
        self.world.apply_extraction_disturbance(x, y)
        self._refresh_indicators()

    def _update_hunter(self, villager: Villager, building: Building) -> None:
        """Hunt in areas, or nearest animal if no area is drawn."""
        if villager.inventory.is_full or self._gather_cargo_needs_delivery(
            villager, building
        ):
            self._force_assigned_delivery(villager, building)
            return
        if not self._ensure_work_tool(villager, "spear"):
            self._maybe_assigned_transport(villager, building)
            return
        if self._maybe_assigned_transport(villager, building):
            return

        meat_pos = villager.hunt_meat_pos
        if meat_pos is not None:
            cell = self.world.get_cell(*meat_pos)
            if cell is None or cell.meat_deposit <= 0:
                villager.hunt_meat_pos = None
                meat_pos = None
        if meat_pos is None:
            meat_pos = self._find_meat_in_hunt_areas(building, villager.id)
            if meat_pos is not None:
                villager.hunt_meat_pos = meat_pos
                self._register_field_claim(villager, meat_pos)

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

        # Rabbit colony vs free animal: chase whichever is nearer to the hunter.
        colony = self._resolve_hunt_colony(villager, building)
        animal = self._resolve_hunt_animal(villager, building)
        if colony is not None and animal is not None:
            dc = abs(colony.x - villager.x) + abs(colony.y - villager.y)
            da = abs(animal.x - villager.x) + abs(animal.y - villager.y)
            if da < dc:
                villager.hunt_colony_id = None
                colony = None
            else:
                villager.hunt_animal_id = None
                animal = None

        if colony is not None:
            villager.state = VillagerState.WORKING
            dist = max(abs(colony.x - villager.x), abs(colony.y - villager.y))
            if dist <= 1:
                if villager.work_cooldown == 0:
                    if not villager.inventory.can_add(RABBIT_MEAT_PER_LEVEL, key="meat"):
                        villager.hunt_colony_id = None
                        self._force_assigned_delivery(villager, building)
                        return
                    result = self.wildlife.harvest_colony(
                        colony.id, kind=colony.kind
                    )
                    villager.hunt_colony_id = None
                    if result is not None:
                        _kind, amount = result
                        villager.inventory.add_item("meat", amount)
                        self.record_produced("meat", amount)
                        self.world.apply_extraction_disturbance(colony.x, colony.y)
                        self._refresh_indicators()
                        villager.work_cooldown = self._villager_work_interval(villager)
                        self._force_assigned_delivery(villager, building)
                        return
                    villager.work_cooldown = self._villager_work_interval(villager)
                return
            approach = (colony.x, colony.y)
            if not self.world.is_walkable(*approach):
                for ny, nx in self.world.neighbourhood(colony.x, colony.y, radius=1):
                    if self.world.is_walkable(nx, ny):
                        approach = (nx, ny)
                        break
            if not self._step_villager_toward(villager, approach):
                villager.hunt_colony_id = None
                self._clear_villager_path(villager)
            return

        if animal is None:
            self._maybe_assigned_transport(villager, building)
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
                    self.world.apply_extraction_disturbance(x, y)
                    self._refresh_indicators()
                    villager.hunt_meat_pos = (x, y)
                    self._register_field_claim(villager, (x, y))
                villager.work_cooldown = self._villager_work_interval(villager)
            return

        approach = (animal.x, animal.y)
        if not self.world.is_walkable(*approach):
            for ny, nx in self.world.neighbourhood(animal.x, animal.y, radius=1):
                if self.world.is_walkable(nx, ny):
                    approach = (nx, ny)
                    break
        if not self._step_villager_toward(villager, approach):
            villager.hunt_animal_id = None
            self._clear_villager_path(villager)

    def _within_work_search(
        self, origin: tuple[int, int], pos: tuple[int, int]
    ) -> bool:
        ox, oy = origin
        px, py = pos
        return abs(px - ox) + abs(py - oy) <= WORK_SEARCH_RADIUS

    def _find_hunt_colony(self, villager: Villager, building: Building):
        from wildlife import AnimalKind

        if not building.allows_hunt_kind("rabbit"):
            return None
        if not villager.inventory.can_add(RABBIT_MEAT_PER_LEVEL, key="meat"):
            return None
        taken = self._claimed_colony_ids(villager.id)
        colonies = [
            c
            for c in self.wildlife.colonies
            if c.kind == AnimalKind.RABBIT
            and c.can_harvest()
            and c.id not in taken
        ]
        if building.areas:
            filtered = []
            for area in building.areas:
                if area.task_type != TaskType.HUNT:
                    continue
                for c in colonies:
                    if area.contains(c.x, c.y):
                        filtered.append(c)
            colonies = filtered
        origin = (villager.x, villager.y)
        return self._pick_nearest_reachable(
            origin,
            colonies,
            pos_fn=lambda c: (c.x, c.y),
            prefer_adjacent=True,
            villager=villager,
        )

    def _resolve_hunt_colony(self, villager: Villager, building: Building):
        if villager.hunt_colony_id is not None:
            colony = self.wildlife.colony_by_id(villager.hunt_colony_id)
            if (
                colony is not None
                and colony.can_harvest()
                and self._within_work_search(
                    (villager.x, villager.y), (colony.x, colony.y)
                )
            ):
                return colony
            villager.hunt_colony_id = None
        colony = self._find_hunt_colony(villager, building)
        if colony is not None:
            villager.hunt_colony_id = colony.id
            self._register_colony_claim(colony.id)
        return colony

    def _find_hunt_target(self, villager: Villager, building: Building):
        animals = []
        if building.areas:
            for area in building.areas:
                if area.task_type != TaskType.HUNT:
                    continue
                animals.extend(self.wildlife.animals_in_area(area.contains))
        else:
            animals = list(self.wildlife.animals)
        taken = self._claimed_animal_ids(villager.id)
        animals = [
            a
            for a in animals
            if building.allows_hunt_kind(a.kind.name) and a.id not in taken
        ]
        origin = (villager.x, villager.y)
        return self._pick_nearest_reachable(
            origin,
            animals,
            pos_fn=lambda a: (a.x, a.y),
            prefer_adjacent=True,
            villager=villager,
        )

    def _resolve_hunt_animal(self, villager: Villager, building: Building):
        if villager.hunt_animal_id is not None:
            for animal in self.wildlife.animals:
                if animal.id == villager.hunt_animal_id:
                    if self._within_work_search(
                        (villager.x, villager.y), (animal.x, animal.y)
                    ):
                        return animal
                    break
            villager.hunt_animal_id = None
        animal = self._find_hunt_target(villager, building)
        if animal is not None:
            villager.hunt_animal_id = animal.id
            self._register_animal_claim(animal.id)
        return animal

    def _find_meat_in_hunt_areas(
        self, building: Building, exclude_villager_id: int = -1
    ) -> tuple[int, int] | None:
        claimed = self._claimed_work_cells(exclude_villager_id)
        cells: list[tuple[int, int]] = []
        if building.areas:
            for area in building.areas:
                if area.task_type != TaskType.HUNT:
                    continue
                for x, y in area.cells():
                    if (x, y) in claimed:
                        continue
                    cell = self.world.get_cell(x, y)
                    if cell is not None and cell.meat_deposit > 0:
                        cells.append((x, y))
            origin = building.center_cell()
            # Prefer nearest to a hunter currently looking — use building centre.
        else:
            for y in range(self.world.rows):
                for x in range(self.world.cols):
                    if (x, y) in claimed:
                        continue
                    if self.world.cells[y][x].meat_deposit > 0:
                        cells.append((x, y))
            origin = building.center_cell()
        villager = self._get_villager(exclude_villager_id)
        if villager is not None:
            origin = (villager.x, villager.y)
        return self._pick_nearest_reachable(
            origin,
            cells,
            pos_fn=lambda p: p,
            prefer_adjacent=False,
            villager=villager,
        )

    def _meat_deposit_available(
        self, building: Building, exclude_villager_id: int = -1
    ) -> bool:
        """True if any unclaimed meat pile exists (no pathfinding)."""
        claimed = self._claimed_work_cells(exclude_villager_id)
        if building.areas:
            for area in building.areas:
                if area.task_type != TaskType.HUNT:
                    continue
                for x, y in area.cells():
                    if (x, y) in claimed:
                        continue
                    cell = self.world.get_cell(x, y)
                    if cell is not None and cell.meat_deposit > 0:
                        return True
            return False
        villager = self._get_villager(exclude_villager_id)
        origin = (
            (villager.x, villager.y)
            if villager is not None
            else building.center_cell()
        )
        for y in range(self.world.rows):
            for x in range(self.world.cols):
                if (x, y) in claimed:
                    continue
                if self.world.cells[y][x].meat_deposit <= 0:
                    continue
                if self._within_work_search(origin, (x, y)):
                    return True
        return False

    def _update_fisher(self, villager: Villager, building: Building) -> None:
        """Collect shore deposits, else stand at a dense shoreline and wait for fish."""
        if not fishing_allowed(self.calendar_day):
            self._maybe_assigned_transport(villager, building)
            villager.fish_target_id = None
            villager.fish_post_pos = None
            return

        if villager.inventory.is_full or self._gather_cargo_needs_delivery(
            villager, building
        ):
            self._force_assigned_delivery(villager, building)
            return

        if not self._ensure_work_tool(villager, "fishing_rod"):
            self._maybe_assigned_transport(villager, building)
            return
        if self._maybe_assigned_transport(villager, building):
            return

        # Never chase swimming fish — clear any legacy sticky target.
        villager.fish_target_id = None

        catch_pos = villager.fish_catch_pos
        if catch_pos is not None:
            cell = self.world.get_cell(*catch_pos)
            if cell is None or cell.fish_deposit <= 0:
                villager.fish_catch_pos = None
                catch_pos = None
        if catch_pos is None:
            catch_pos = self._find_fish_in_fish_areas(building, villager.id)
            if catch_pos is not None:
                villager.fish_catch_pos = catch_pos
                self._register_field_claim(villager, catch_pos)

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

        post = self._resolve_fish_post(villager, building)
        if post is None:
            self._maybe_assigned_transport(villager, building)
            return

        villager.state = VillagerState.WORKING
        if (villager.x, villager.y) != post:
            if not self._step_villager_toward(villager, post):
                villager.fish_post_pos = None
                self._clear_villager_path(villager)
            return

        # At the post: catch any fish that swim within Chebyshev range 1.
        # Fish go straight into inventory (no shore drop → pick-up loop).
        if villager.work_cooldown != 0:
            return
        if not villager.inventory.can_add(FISH_YIELD, key="fish"):
            self._force_assigned_delivery(villager, building)
            return
        taken = self._claimed_fish_ids(villager.id)
        catchable = [
            f
            for f in self._fisher_candidate_fish(villager, building)
            if f.id not in taken
            and self.world.is_adjacent_chebyshev(
                villager.x, villager.y, f.x, f.y, radius=1
            )
        ]
        if not catchable:
            return
        target = min(
            catchable,
            key=lambda f: abs(f.x - villager.x) + abs(f.y - villager.y),
        )
        pos = self.fish.kill_fish(target.id)
        if pos is None:
            return
        villager.inventory.add_fish(FISH_YIELD)
        self.record_produced("fish", FISH_YIELD)
        self.world.apply_extraction_disturbance(pos[0], pos[1])
        self._refresh_indicators()
        villager.work_cooldown = self._villager_work_interval(villager)
        if villager.inventory.is_full or self._gather_cargo_needs_delivery(
            villager, building
        ):
            self._force_assigned_delivery(villager, building)

    def _is_fishing_shore(self, x: int, y: int) -> bool:
        """Walkable land tile that touches water (a place to stand and fish)."""
        if not self.world.is_walkable(x, y):
            return False
        for ny, nx in self.world.neighbourhood(x, y, radius=1):
            if (nx, ny) == (x, y):
                continue
            cell = self.world.get_cell(nx, ny)
            if cell is not None and is_water_terrain(cell.terrain):
                return True
        return False

    def _fisher_candidate_fish(self, villager: Villager, building: Building):
        """Fish the workplace may target (area filter + search radius from villager)."""
        if building.areas:
            found = []
            for area in building.areas:
                if area.task_type != TaskType.FISH:
                    continue
                found.extend(self.fish.fish_in_area(area.contains))
        else:
            found = list(self.fish.fish)
        origin = (villager.x, villager.y)
        return [
            f
            for f in found
            if self._within_work_search(origin, (f.x, f.y))
        ]

    def _fish_deposit_available(
        self, building: Building, exclude_villager_id: int = -1
    ) -> bool:
        """True if any unclaimed shore fish pile exists (no pathfinding)."""
        claimed = self._claimed_work_cells(exclude_villager_id)
        if building.areas:
            for area in building.areas:
                if area.task_type != TaskType.FISH:
                    continue
                for x, y in area.cells():
                    if (x, y) in claimed:
                        continue
                    cell = self.world.get_cell(x, y)
                    if cell is not None and cell.fish_deposit > 0:
                        return True
                    if cell is None or not is_water_terrain(cell.terrain):
                        continue
                    for ny, nx in self.world.neighbourhood(x, y, radius=1):
                        if (nx, ny) in claimed:
                            continue
                        ncell = self.world.get_cell(nx, ny)
                        if ncell is not None and ncell.fish_deposit > 0:
                            return True
            return False
        for y in range(self.world.rows):
            for x in range(self.world.cols):
                if (x, y) in claimed:
                    continue
                if self.world.cells[y][x].fish_deposit > 0:
                    return True
        return False

    def _fish_post_density(
        self, shore: tuple[int, int], fish_list: list
    ) -> int:
        sx, sy = shore
        r = FISH_POST_SCORE_RADIUS
        return sum(
            1
            for f in fish_list
            if max(abs(f.x - sx), abs(f.y - sy)) <= r
        )

    def _find_fish_post(
        self, villager: Villager, building: Building
    ) -> tuple[int, int] | None:
        """Best walkable shore near a concentration of fish."""
        fish_list = self._fisher_candidate_fish(villager, building)
        if not fish_list:
            return None
        origin = (villager.x, villager.y)
        claimed = self._claimed_work_cells(villager.id)
        shore_scores: dict[tuple[int, int], int] = {}
        r = FISH_POST_SCORE_RADIUS
        for item in fish_list:
            for ny, nx in self.world.neighbourhood(item.x, item.y, radius=r):
                shore = (nx, ny)
                if shore in claimed or shore in shore_scores:
                    continue
                if not self._within_work_search(origin, shore):
                    continue
                if not self._is_fishing_shore(nx, ny):
                    continue
                dens = self._fish_post_density(shore, fish_list)
                if dens >= FISH_POST_MIN_FISH:
                    shore_scores[shore] = dens
        if not shore_scores:
            # Fallback: any shore adjacent to a single fish.
            for item in fish_list:
                for ny, nx in self.world.neighbourhood(item.x, item.y, radius=1):
                    shore = (nx, ny)
                    if shore in claimed:
                        continue
                    if not self._is_fishing_shore(nx, ny):
                        continue
                    if not self._within_work_search(origin, shore):
                        continue
                    shore_scores[shore] = max(shore_scores.get(shore, 0), 1)
        if not shore_scores:
            return None

        def pick_from(cands: dict[tuple[int, int], int]):
            best_dens = max(cands.values())
            top = [s for s, d in cands.items() if d >= best_dens - 1]
            return self._pick_nearest_reachable(
                origin,
                top,
                pos_fn=lambda p: p,
                prefer_adjacent=False,
                villager=villager,
            )

        local = {
            s: d
            for s, d in shore_scores.items()
            if abs(s[0] - origin[0]) + abs(s[1] - origin[1]) <= FISH_POST_LOCAL_RADIUS
        }
        if local:
            chosen = pick_from(local)
            if chosen is not None:
                return chosen
        return pick_from(shore_scores)

    def _resolve_fish_post(
        self, villager: Villager, building: Building
    ) -> tuple[int, int] | None:
        """Keep a shore post while fish still concentrate nearby; else re-pick."""
        post = villager.fish_post_pos
        if post is not None:
            if (
                self._is_fishing_shore(*post)
                and self._within_work_search((villager.x, villager.y), post)
            ):
                fish_list = self._fisher_candidate_fish(villager, building)
                if self._fish_post_density(post, fish_list) >= FISH_POST_MIN_FISH:
                    return post
            villager.fish_post_pos = None
            self._clear_villager_path(villager)
        post = self._find_fish_post(villager, building)
        if post is not None:
            villager.fish_post_pos = post
            self._register_field_claim(villager, post)
        return post

    def _find_fish_target(self, villager: Villager, building: Building):
        """Legacy helper: nearest fish (availability / debug). Prefer shore posts."""
        found = self._fisher_candidate_fish(villager, building)
        taken = self._claimed_fish_ids(villager.id)
        found = [f for f in found if f.id not in taken]
        return self._pick_nearest_reachable(
            (villager.x, villager.y),
            found,
            pos_fn=lambda f: (f.x, f.y),
            prefer_adjacent=True,
            villager=None,
        )

    def _resolve_fish_target(self, villager: Villager, building: Building):
        """Unused by shore-post fishing; kept for save compatibility / tools."""
        villager.fish_target_id = None
        return None

    def _find_fish_in_fish_areas(
        self, building: Building, exclude_villager_id: int = -1
    ) -> tuple[int, int] | None:
        claimed = self._claimed_work_cells(exclude_villager_id)
        cells: list[tuple[int, int]] = []
        if building.areas:
            for area in building.areas:
                if area.task_type != TaskType.FISH:
                    continue
                for x, y in area.cells():
                    if (x, y) in claimed:
                        continue
                    cell = self.world.get_cell(x, y)
                    if cell is not None and cell.fish_deposit > 0:
                        cells.append((x, y))
                for x, y in area.cells():
                    cell = self.world.get_cell(x, y)
                    if cell is None or not is_water_terrain(cell.terrain):
                        continue
                    for ny, nx in self.world.neighbourhood(x, y, radius=1):
                        if (nx, ny) in claimed or (nx, ny) in cells:
                            continue
                        ncell = self.world.get_cell(nx, ny)
                        if ncell is not None and ncell.fish_deposit > 0:
                            cells.append((nx, ny))
        else:
            for y in range(self.world.rows):
                for x in range(self.world.cols):
                    if (x, y) in claimed:
                        continue
                    if self.world.cells[y][x].fish_deposit > 0:
                        cells.append((x, y))
        origin = building.center_cell()
        villager = self._get_villager(exclude_villager_id)
        if villager is not None:
            origin = (villager.x, villager.y)
        return self._pick_nearest_reachable(
            origin,
            cells,
            pos_fn=lambda p: p,
            prefer_adjacent=False,
            villager=villager,
        )

    def _update_hauler(self, villager: Villager) -> None:
        if self._construction_delivery_active(villager):
            self._update_builder(villager)
            return

        home = self.world.home_pos

        # Carrying goods → processor input delivery, else home.
        if not villager.inventory.is_empty and villager.state != VillagerState.DELIVERING:
            sink = self._find_processor_input_sink(villager)
            if sink is not None:
                villager.haul_building_id = sink.id
                villager.state = VillagerState.HAULING
            else:
                villager.state = VillagerState.DELIVERING
                villager.target = home

        if villager.state == VillagerState.DELIVERING:
            if villager.inventory.is_empty:
                villager.haul_building_id = None
                villager.state = VillagerState.IDLE
                return
            if (villager.x, villager.y) == home:
                self._deposit_home(villager.inventory, status=False)
                villager.haul_building_id = None
                villager.state = VillagerState.IDLE
                return
            self._step_villager_toward(villager, home)
            return

        if villager.state == VillagerState.HAULING and villager.haul_building_id is not None:
            claimed = self.buildings.get(villager.haul_building_id)
            if claimed is not None and claimed.needs_supplied():
                # Deliver ingredients the processor / forester splitter still needs.
                if (
                    not villager.inventory.is_empty
                    and claimed.can_accept_from(villager.inventory)
                ):
                    dest = claimed.center_cell()
                    villager.target = dest
                    if (villager.x, villager.y) == dest:
                        if villager.work_cooldown == 0:
                            self._hauler_exchange_at_processor(villager, claimed)
                            if not villager.inventory.is_empty:
                                # Leftover inputs and/or picked-up produce → home.
                                villager.haul_building_id = None
                                villager.state = VillagerState.DELIVERING
                                villager.target = home
                            # else empty: keep claim so sticky supply can fetch more,
                            # or fall through next tick to clear/idle.
                        return
                    self._step_villager_toward(villager, dest)
                    return
                if not villager.inventory.is_empty:
                    # Cargo left that this sink will not take — grab produce first
                    # if standing at the station, then return home.
                    dest = claimed.center_cell()
                    out_keys = claimed.processor_output_keys()
                    if (
                        (villager.x, villager.y) == dest
                        and villager.work_cooldown == 0
                        and out_keys
                        and not villager.inventory.is_full
                        and any(claimed.haulable_amount(k) > 0 for k in out_keys)
                    ):
                        claimed.withdraw_to_inventory(villager.inventory, keys=out_keys)
                        villager.work_cooldown = self._villager_work_interval(villager)
                    villager.haul_building_id = None
                    villager.state = VillagerState.DELIVERING
                    villager.target = home
                    return
                # Sticky supply trip: keep fetching for this processor (don't divert
                # to farm clearing mid-walk).
                if self._processor_can_be_supplied(claimed) and self._owns_haul_claim(
                    villager, claimed.id
                ):
                    if (villager.x, villager.y) != home:
                        self._step_villager_toward(villager, home)
                        return
                    taken = self._withdraw_processor_supply(villager, claimed)
                    if taken <= 0:
                        villager.haul_building_id = None
                        villager.state = VillagerState.IDLE
                    return
                villager.haul_building_id = None
            elif claimed is not None and villager.inventory.is_empty:
                # Drop duplicate empty claims so only one hauler walks to each source.
                if not self._owns_haul_claim(villager, claimed.id):
                    villager.haul_building_id = None
                else:
                    # Clearing a stocked workplace → withdraw then deliver home.
                    dest = claimed.center_cell()
                    if (villager.x, villager.y) == dest:
                        if villager.work_cooldown == 0:
                            claimed.withdraw_to_inventory(villager.inventory)
                            villager.work_cooldown = self._villager_work_interval(
                                villager
                            )
                            if not villager.inventory.is_empty:
                                villager.state = VillagerState.DELIVERING
                                villager.target = home
                            else:
                                # Race / emptied by another hauler — abort empty walk.
                                villager.haul_building_id = None
                                villager.state = VillagerState.IDLE
                        return
                    self._step_villager_toward(villager, dest)
                    return
            else:
                villager.haul_building_id = None

        # Prefer clearing processor outputs / farm produce, then supplying inputs.
        source = self._find_haul_source(villager)
        if source is not None:
            villager.haul_building_id = source.id
            villager.state = VillagerState.HAULING
            if (villager.x, villager.y) == source.center_cell():
                if villager.work_cooldown == 0:
                    source.withdraw_to_inventory(villager.inventory)
                    villager.work_cooldown = self._villager_work_interval(villager)
                    if not villager.inventory.is_empty:
                        villager.state = VillagerState.DELIVERING
                        villager.target = home
                    else:
                        villager.haul_building_id = None
                        villager.state = VillagerState.IDLE
                return
            self._step_villager_toward(villager, source.center_cell())
            return

        sink = self._find_processor_needing_supply_for(villager)
        if sink is not None:
            villager.haul_building_id = sink.id
            villager.state = VillagerState.HAULING
            if (villager.x, villager.y) != home:
                self._step_villager_toward(villager, home)
                return
            taken = self._withdraw_processor_supply(villager, sink)
            if taken <= 0:
                villager.haul_building_id = None
                villager.state = VillagerState.IDLE
            return

        villager.haul_building_id = None
        villager.state = VillagerState.IDLE

    def _processor_can_be_supplied(self, building: Building) -> bool:
        demand = building.supply_demand()
        if not demand:
            return False
        return any(getattr(self.home_storage, key, 0) > 0 for key in demand)

    def _withdraw_processor_supply(self, villager: Villager, sink: Building) -> int:
        """Pack ingredients for a processor; fill remaining cargo when the sink has room."""
        demand = sink.supply_demand()
        if not demand:
            return 0
        amounts: dict[str, int] = {}
        room_left = villager.inventory.capacity - villager.inventory.cargo_total

        def _take_key(key: str, want: int) -> None:
            nonlocal room_left
            if room_left <= 0 or want <= 0:
                return
            already = amounts.get(key, 0)
            have = int(getattr(self.home_storage, key, 0)) - already
            room = sink.space_for_key(key) - already
            n = min(want, have, room, room_left)
            if n > 0:
                amounts[key] = already + n
                room_left -= n

        # Pass 1: recipe gaps + reserve targets from supply_demand.
        for key, want in demand.items():
            _take_key(key, want)

        # Pass 2: fill remaining pack space with the same supply keys (stockpile
        # up to building room / caps), round-robin so one input doesn't starve others.
        if room_left > 0:
            fill_keys = list(demand.keys())
            progressed = True
            while room_left > 0 and progressed:
                progressed = False
                for key in fill_keys:
                    before = room_left
                    _take_key(key, 1)
                    if room_left < before:
                        progressed = True
                    if room_left <= 0:
                        break

        if not amounts:
            return 0
        return self.home_storage.withdraw_amounts_to(villager.inventory, amounts)

    def _find_haul_source(self, villager: Villager) -> Building | None:
        claimed = self._claimed_haul_targets(villager.id)
        stocked = [
            b
            for b in self.buildings.values()
            if b.haulable_total() > 0
            and b.id not in claimed
            and not (
                villager.building_id == b.id
                and self._building_can_produce(b)
            )
        ]
        if not stocked:
            return None
        return min(
            stocked,
            key=lambda b: abs(b.center_cell()[0] - villager.x)
            + abs(b.center_cell()[1] - villager.y),
        )

    def _find_processor_needing_supply(self) -> Building | None:
        return self._find_processor_needing_supply_for(None)

    def _find_processor_needing_supply_for(
        self, villager: Villager | None
    ) -> Building | None:
        claimed = (
            self._claimed_haul_targets(villager.id) if villager is not None else set()
        )
        needy: list[Building] = []
        for building in self.buildings.values():
            if not building.needs_supplied():
                continue
            if villager is not None and building.id in claimed:
                continue
            if not self._processor_can_be_supplied(building):
                continue
            needy.append(building)
        if not needy:
            return None
        return min(
            needy,
            key=lambda b: abs(b.center_cell()[0] - self.world.home_pos[0])
            + abs(b.center_cell()[1] - self.world.home_pos[1]),
        )

    def _find_processor_input_sink(self, villager: Villager) -> Building | None:
        sinks = [
            b
            for b in self.buildings.values()
            if b.needs_supplied() and b.can_accept_from(villager.inventory)
        ]
        if not sinks:
            return None
        return min(
            sinks,
            key=lambda b: abs(b.center_cell()[0] - villager.x)
            + abs(b.center_cell()[1] - villager.y),
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
            return building.center_cell()
        if building.kind == BuildingKind.FARM:
            return None
        if any(getattr(self.home_storage, key, 0) > 0 for key in building.plant_keys()):
            return self.world.home_pos
        return None

    def _update_plant_stock_withdraw(
        self, villager: Villager, building: Building
    ) -> bool:
        """Walk to storage and pull saplings/seeds before planting. Consumes the turn."""
        if building.work_mode not in (WorkMode.PLANT, WorkMode.ALL):
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

    @staticmethod
    def _path_detour_ok(straight: int, path_len: int) -> bool:
        """True if BFS path length is not an extreme detour vs Manhattan."""
        limit = max(
            int(straight * PATH_DETOUR_RATIO),
            straight + PATH_DETOUR_SLACK,
        )
        return path_len <= limit

    def _walk_goal_for_target(
        self,
        tx: int,
        ty: int,
        *,
        prefer_adjacent: bool = False,
        from_pos: tuple[int, int] | None = None,
    ) -> tuple[int, int] | None:
        """Walkable cell to path to for a target (cell itself or best neighbour)."""
        if not prefer_adjacent and self.world.is_walkable(tx, ty):
            return (tx, ty)
        ox, oy = from_pos if from_pos is not None else (tx, ty)
        best: tuple[int, int] | None = None
        best_d = 10**9
        for ny, nx in self.world.neighbourhood(tx, ty, radius=1):
            if not self.world.is_walkable(nx, ny):
                continue
            d = abs(nx - ox) + abs(ny - oy)
            if d < best_d:
                best_d = d
                best = (nx, ny)
        if best is not None:
            return best
        if self.world.is_walkable(tx, ty):
            return (tx, ty)
        return None

    def _pick_nearest_reachable(
        self,
        origin: tuple[int, int],
        candidates: list,
        *,
        pos_fn,
        prefer_adjacent: bool = False,
        max_radius: int | None = None,
        villager: Villager | None = None,
    ):
        """Nearest candidate by Manhattan rings with path-detour rejection.

        Searches expanding Manhattan distance up to ``max_radius``. Within each
        ring, prefers the shortest acceptable BFS path. Optionally seeds the
        villager path cache for the chosen approach goal.
        """
        if not candidates:
            return None
        ox, oy = origin
        r_max = WORK_SEARCH_RADIUS if max_radius is None else max(0, int(max_radius))
        by_dist: dict[int, list] = {}
        for item in candidates:
            px, py = pos_fn(item)
            d = abs(px - ox) + abs(py - oy)
            if d > r_max:
                continue
            by_dist.setdefault(d, []).append(item)

        for d in sorted(by_dist):
            best_item = None
            best_len = 10**9
            best_goal: tuple[int, int] | None = None
            best_path: list[tuple[int, int]] | None = None
            for item in by_dist[d]:
                px, py = pos_fn(item)
                goal = self._walk_goal_for_target(
                    px, py, prefer_adjacent=prefer_adjacent, from_pos=origin
                )
                if goal is None:
                    continue
                path = self.world.find_path(origin, goal)
                if path is None:
                    continue
                plen = len(path)
                straight = abs(goal[0] - ox) + abs(goal[1] - oy)
                if not self._path_detour_ok(straight, plen):
                    continue
                if plen < best_len:
                    best_len = plen
                    best_item = item
                    best_goal = goal
                    best_path = path
            if best_item is not None:
                if (
                    villager is not None
                    and best_goal is not None
                    and best_path is not None
                ):
                    villager._path_cache = list(best_path)  # type: ignore[attr-defined]
                    villager._path_goal = best_goal  # type: ignore[attr-defined]
                return best_item
        return None

    def _find_work_in_building(
        self, villager: Villager, building: Building
    ) -> tuple[int, int] | None:
        can_plant_sapling, can_plant_berry, can_plant_herb = self._can_plant_from(
            villager, building
        )
        mode = building.work_mode
        if building.kind == BuildingKind.FORESTER and mode == WorkMode.SPLIT:
            return None
        allow_collect = mode in (WorkMode.COLLECT, WorkMode.ALL)
        allow_plant = mode in (WorkMode.PLANT, WorkMode.ALL) and building.allows_planting()
        if not allow_plant:
            can_plant_sapling = can_plant_berry = can_plant_herb = False
        origin = (villager.x, villager.y)
        claimed = self._claimed_work_cells(villager.id)

        def match(cell, task_type: TaskType, *, plant_ok: bool) -> bool:
            if not self._cell_matches_task(
                cell,
                task_type,
                can_plant_sapling=can_plant_sapling if plant_ok else False,
                can_plant_berry=can_plant_berry if plant_ok else False,
                can_plant_herb=can_plant_herb if plant_ok else False,
            ):
                return False
            return self._building_allows_cell(building, cell)

        if building.areas:
            gather: list[tuple[int, int]] = []
            plant: list[tuple[int, int]] = []
            for area in building.areas:
                for x, y in area.cells():
                    if (x, y) in claimed:
                        continue
                    cell = self.world.get_cell(x, y)
                    if cell is None or not self.world.is_walkable(x, y):
                        continue
                    task = area.task_type
                    if task == TaskType.FULL_MANAGE:
                        if (
                            allow_collect
                            and cell.feature == FeatureType.TREE
                            and cell.deposit > 0
                            and self._building_allows_cell(building, cell)
                        ):
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
            if allow_collect and building.kind == BuildingKind.FORAGER:
                return self._pick_forager_target(
                    villager,
                    building,
                    origin=origin,
                    claimed=claimed,
                    areas=building.areas,
                )
            if allow_collect:
                return self._closest_of(origin, gather)
            return self._closest_of(origin, plant)

        # No areas: whole-map behaviour from work_mode.
        ox, oy = building.center_cell()
        if building.kind == BuildingKind.FORESTER:
            if building.work_mode == WorkMode.SPLIT:
                return None
            if allow_plant and can_plant_sapling:
                planted = self._find_closest_manage_plant_cell(
                    ox, oy, can_plant_sapling=True, exclude_cells=claimed
                )
                if planted is not None:
                    return planted
            if allow_collect:
                return self._find_closest_task_cell(
                    ox,
                    oy,
                    TaskType.CHOP_TREES,
                    can_plant_sapling=False,
                    can_plant_berry=False,
                    can_plant_herb=False,
                    building=building,
                    exclude_cells=claimed,
                )
            return None

        if building.kind == BuildingKind.FORAGER:
            if allow_collect:
                claimed = self._claimed_work_cells(villager.id)
                return self._pick_forager_target(
                    villager,
                    building,
                    origin=(villager.x, villager.y),
                    claimed=claimed,
                    areas=building.areas,
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
            ox,
            oy,
            task,
            can_plant_sapling=False,
            can_plant_berry=False,
            can_plant_herb=False,
            building=building,
            exclude_cells=claimed,
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
        building: Building | None = None,
        exclude_cells: set[tuple[int, int]] | None = None,
    ) -> tuple[int, int] | None:
        best: tuple[int, int] | None = None
        best_d = 10**9
        cells = self.world.cells
        rows = self.world.rows
        cols = self.world.cols
        for y in range(rows):
            row = cells[y]
            for x in range(cols):
                if exclude_cells and (x, y) in exclude_cells:
                    continue
                cell = row[x]
                if is_water_terrain(cell.terrain):
                    continue
                if not self._cell_matches_task(
                    cell,
                    task_type,
                    can_plant_sapling=can_plant_sapling,
                    can_plant_berry=can_plant_berry,
                    can_plant_herb=can_plant_herb,
                ):
                    continue
                if building is not None and not self._building_allows_cell(building, cell):
                    continue
                d = abs(x - ox) + abs(y - oy)
                if d < best_d:
                    best_d = d
                    best = (x, y)
                    if best_d == 0:
                        return best
        return best

    def _find_closest_forage_key(
        self,
        ox: int,
        oy: int,
        key: str,
        *,
        building: Building,
        exclude_cells: set[tuple[int, int]] | None = None,
        areas: list | None = None,
        villager: Villager | None = None,
    ) -> tuple[int, int] | None:
        """Closest reachable forage ``key`` cell (radius + path-detour gate)."""
        if key == "honey":
            return None
        cells: list[tuple[int, int]] = []

        def consider(x: int, y: int) -> None:
            if exclude_cells and (x, y) in exclude_cells:
                return
            cell = self.world.get_cell(x, y)
            if cell is None or not self.world.is_walkable(x, y):
                return
            if self._forage_key_for_cell(cell) != key:
                return
            if not self._building_allows_cell(building, cell):
                return
            cells.append((x, y))

        if areas:
            for area in areas:
                if area.task_type not in (
                    TaskType.FULL_FORAGE,
                    TaskType.FORAGE_BERRIES,
                    TaskType.FORAGE_MUSHROOMS,
                    TaskType.FORAGE_HERBS,
                ):
                    continue
                for x, y in area.cells():
                    consider(x, y)
        else:
            for x, y in self._forage_cells_for_key(key):
                if exclude_cells and (x, y) in exclude_cells:
                    continue
                cell = self.world.cells[y][x]
                if not self.world.is_walkable(x, y):
                    continue
                if not self._building_allows_cell(building, cell):
                    continue
                cells.append((x, y))

        return self._pick_nearest_reachable(
            (ox, oy),
            cells,
            pos_fn=lambda p: p,
            prefer_adjacent=False,
            villager=villager,
        )

    def _pick_forager_target(
        self,
        villager: Villager,
        building: Building,
        *,
        origin: tuple[int, int],
        claimed: set[tuple[int, int]],
        areas: list | None,
    ) -> tuple[int, int] | None:
        """Pick forage work: nearby first, then priority within each distance band.

        For each enabled recipe, find the closest matching cell (or honey colony).
        Sort by distance band → recipe priority (1 best) → exact distance, so a
        forager clears local forage before crossing the map for a higher priority.
        """
        ox, oy = origin
        band = max(1, int(FORAGER_PRIORITY_BAND))
        # (band, priority, distance, target, colony_id|None)
        candidates: list[tuple[int, int, int, tuple[int, int], int | None]] = []

        for recipe in building.enabled_recipes():
            priority = building.get_recipe_priority(recipe.name)
            need = self._forage_yield_amount(recipe.name)
            cargo_key = "wood" if recipe.name == "wood" else recipe.name
            # Produce recipes output the produce key (same as recipe name for forager).
            if recipe.outputs:
                cargo_key = next(iter(recipe.outputs))
            if not villager.inventory.can_add(need, key=cargo_key):
                continue
            if recipe.name == "honey":
                colony = self._find_honey_colony(
                    villager, building, origin=origin
                )
                if colony is None:
                    continue
                target = (colony.x, colony.y)
                dist = abs(colony.x - ox) + abs(colony.y - oy)
                candidates.append(
                    (dist // band, priority, dist, target, colony.id)
                )
                continue
            target = self._find_closest_forage_key(
                ox,
                oy,
                recipe.name,
                building=building,
                exclude_cells=claimed,
                areas=areas,
            )
            if target is None:
                continue
            dist = abs(target[0] - ox) + abs(target[1] - oy)
            candidates.append((dist // band, priority, dist, target, None))

        if not candidates:
            villager.forage_colony_id = None
            return None
        # Sort by band → priority → distance → cell; omit colony_id (None vs int
        # breaks ordering when a plant and honey target tie on the other keys).
        candidates.sort(key=lambda c: (c[0], c[1], c[2], c[3]))
        _band, _prio, _dist, target, colony_id = candidates[0]
        villager.forage_colony_id = colony_id
        self._register_colony_claim(colony_id)
        self._register_field_claim(villager, target)
        return target

    def _find_honey_colony(
        self,
        villager: Villager,
        building: Building,
        *,
        origin: tuple[int, int] | None = None,
    ):
        from wildlife import AnimalKind

        if not building.allows_forage_key("honey"):
            return None
        if not villager.inventory.can_add(HONEY_PER_BEE_LEVEL, key="honey"):
            return None
        taken = self._claimed_colony_ids(villager.id)
        colonies = [
            c
            for c in self.wildlife.colonies
            if c.kind == AnimalKind.BEE and c.can_harvest() and c.id not in taken
        ]
        if building.areas:
            filtered = []
            for area in building.areas:
                if area.task_type not in (
                    TaskType.FULL_FORAGE,
                    TaskType.FORAGE_BERRIES,
                    TaskType.FORAGE_MUSHROOMS,
                    TaskType.FORAGE_HERBS,
                ):
                    continue
                for c in colonies:
                    if area.contains(c.x, c.y):
                        filtered.append(c)
            colonies = filtered
        if not colonies:
            return None
        ox, oy = origin if origin is not None else (villager.x, villager.y)
        # Do not seed path cache here: forager may compare several recipes first.
        return self._pick_nearest_reachable(
            (ox, oy),
            colonies,
            pos_fn=lambda c: (c.x, c.y),
            prefer_adjacent=True,
            villager=None,
        )

    def _invalidate_forage_index(self) -> None:
        self._forage_cell_index = None

    def _forage_cells_for_key(self, key: str) -> list[tuple[int, int]]:
        return self._ensure_forage_cell_index().get(key, [])

    def _ensure_forage_cell_index(self) -> dict[str, list[tuple[int, int]]]:
        """Map forage inventory key → cells (one full scan per sim tick)."""
        if self._forage_cell_index is not None:
            return self._forage_cell_index
        index: dict[str, list[tuple[int, int]]] = {}
        cells = self.world.cells
        for y in range(self.world.rows):
            row = cells[y]
            for x in range(self.world.cols):
                cell = row[x]
                if is_water_terrain(cell.terrain):
                    continue
                key = self._forage_key_for_cell(cell)
                if key is None:
                    continue
                bucket = index.get(key)
                if bucket is None:
                    index[key] = [(x, y)]
                else:
                    bucket.append((x, y))
        self._forage_cell_index = index
        return index

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
                if is_water_terrain(cell.terrain):
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
        exclude_cells: set[tuple[int, int]] | None = None,
    ) -> tuple[int, int] | None:
        if not can_plant_sapling:
            return None
        cells = self.world.cells
        rows = self.world.rows
        cols = self.world.cols
        max_d = max(ox + oy, ox + (rows - 1 - oy), (cols - 1 - ox) + oy, (cols - 1 - ox) + (rows - 1 - oy))
        for dist in range(0, max_d + 1):
            for dx in range(-dist, dist + 1):
                dy = dist - abs(dx)
                for sy in ((oy - dy, oy + dy) if dy else (oy,)):
                    x = ox + dx
                    y = sy
                    if not (0 <= x < cols and 0 <= y < rows):
                        continue
                    if exclude_cells and (x, y) in exclude_cells:
                        continue
                    cell = cells[y][x]
                    if is_water_terrain(cell.terrain):
                        continue
                    if self._cell_matches_manage_plant(
                        cell, can_plant_sapling=True
                    ):
                        return (x, y)
        return None

    def _forage_key_for_cell(self, cell) -> str | None:
        """Inventory key a forager would collect from this cell, if any."""
        if cell.feature == FeatureType.MUSHROOM:
            return "mushrooms"
        if cell.feature == FeatureType.WOOD_BUSH and cell.deposit > 0:
            return "wood"
        if cell.feature == FeatureType.BERRY_BUSH and cell.deposit > 0:
            return "berries"
        if cell.feature == FeatureType.REED:
            return "reeds"
        if cell.feature in (FeatureType.HERB, FeatureType.WILD_CROP):
            crop = CROP_BY_KEY.get(cell.crop_kind or "sage", CROP_BY_KEY["sage"])
            return crop.produce_key
        if cell.feature == FeatureType.TREE and cell.deposit > 0:
            from trees import resolve_tree

            return resolve_tree(cell.tree_species).yield_key
        return None

    def _building_allows_cell(self, building: Building, cell) -> bool:
        """Respect gather-recipe toggles for forester / forager cells."""
        if building.kind == BuildingKind.FORESTER:
            if cell.feature == FeatureType.TREE and cell.deposit > 0:
                from trees import resolve_tree

                return building.allows_tree_yield(
                    resolve_tree(cell.tree_species).yield_key
                )
            return True
        if building.kind == BuildingKind.FORAGER:
            key = self._forage_key_for_cell(cell)
            if key is None:
                return True
            # Reeds have no recipe toggle — leave them for manual collection.
            if key == "reeds":
                return False
            return building.allows_forage_key(key)
        return True

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
            if cell.feature == FeatureType.WOOD_BUSH and cell.deposit > 0:
                return True
            if cell.feature == FeatureType.BERRY_BUSH and cell.deposit > 0:
                return True
            if cell.feature in (FeatureType.HERB, FeatureType.WILD_CROP, FeatureType.REED):
                return True
            if cell.feature == FeatureType.TREE and cell.deposit > 0:
                from trees import resolve_tree

                # Softwood only when forager wood recipe is used.
                return resolve_tree(cell.tree_species).yield_key == "logs"
            return False
        if task_type == TaskType.SPLIT_LOGS:
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
        allow_collect = mode in (WorkMode.COLLECT, WorkMode.ALL)
        allow_plant = mode in (WorkMode.PLANT, WorkMode.ALL) and building.allows_planting()
        tasks = {area.task_type for area in building.areas if area.contains(x, y)}
        if not tasks:
            task = building.draw_task_type
            if task not in TASK_LABELS:
                task = building.default_draw_task()
            tasks = {task}
        inv = villager.inventory
        require_axe = building.kind == BuildingKind.FORESTER

        if (
            allow_collect
            and building.kind == BuildingKind.FORAGER
            and building.allows_forage_key("honey")
        ):
            from wildlife import AnimalKind

            colony = None
            if villager.forage_colony_id is not None:
                colony = self.wildlife.colony_by_id(villager.forage_colony_id)
            if colony is None:
                colony = self.wildlife.colony_at(x, y)
            if (
                colony is not None
                and colony.kind == AnimalKind.BEE
                and colony.x == x
                and colony.y == y
                and colony.can_harvest()
            ):
                if not inv.can_add(HONEY_PER_BEE_LEVEL, key="honey"):
                    villager.forage_colony_id = None
                    return
                result = self.wildlife.harvest_colony(colony.id, kind=AnimalKind.BEE)
                villager.forage_colony_id = None
                if result is not None:
                    inv.add_item("honey", result[1])
                    self.record_produced("honey", result[1])
                    self.world.apply_extraction_disturbance(x, y)
                    villager._return_after_harvest = True  # type: ignore[attr-defined]
                return

        if (
            allow_collect
            and cell.feature == FeatureType.TREE
            and (TaskType.CHOP_TREES in tasks or TaskType.FULL_MANAGE in tasks)
            and self._building_allows_cell(building, cell)
        ):
            self._chop_tree(x, y, inv, status=False, require_axe=require_axe)
        elif allow_collect and cell.feature == FeatureType.ROCK and TaskType.COLLECT_ROCKS in tasks:
            self._collect_rock(x, y, inv, status=False)
        elif (
            allow_collect
            and cell.feature == FeatureType.MUSHROOM
            and (TaskType.FORAGE_MUSHROOMS in tasks or TaskType.FULL_FORAGE in tasks)
            and self._building_allows_cell(building, cell)
        ):
            self._collect_mushroom(x, y, inv, status=False)
        elif (
            allow_collect
            and cell.feature == FeatureType.WOOD_BUSH
            and TaskType.FULL_FORAGE in tasks
            and self._building_allows_cell(building, cell)
        ):
            self._collect_wood_bush(x, y, inv, status=False)
        elif (
            allow_collect
            and cell.feature == FeatureType.BERRY_BUSH
            and (TaskType.FORAGE_BERRIES in tasks or TaskType.FULL_FORAGE in tasks)
            and self._building_allows_cell(building, cell)
        ):
            self._collect_berries(x, y, inv, status=False)
        elif (
            allow_collect
            and cell.feature in (FeatureType.HERB, FeatureType.WILD_CROP, FeatureType.REED)
            and (TaskType.FORAGE_HERBS in tasks or TaskType.FULL_FORAGE in tasks)
            and self._building_allows_cell(building, cell)
        ):
            self._collect_herb(x, y, inv, status=False)
        elif (
            allow_collect
            and cell.feature == FeatureType.TREE
            and TaskType.FULL_FORAGE in tasks
            and self._building_allows_cell(building, cell)
        ):
            self._chop_tree(x, y, inv, status=False, require_axe=require_axe)
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
        interval = self._villager_move_interval(villager)
        note_cell_step(villager, step[0], step[1])
        self._record_path_traffic(step[0], step[1])
        villager.move_cooldown = interval
        arm_cell_step_visual(villager, interval)
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
            avg = self.env_maps.biodiversity
            self.overlay_values = [row[:] for row in avg]
            return
        if self.overlay_mode == OverlayMode.FLORAL_RESOURCES:
            self.overlay_values = [row[:] for row in self.env_maps.floral_resources]
            return
        if self.overlay_mode == OverlayMode.POLLINATION:
            self.overlay_values = [row[:] for row in self.env_maps.pollination]
            return
        if self.overlay_mode == OverlayMode.PATH_TRAFFIC:
            self.overlay_values = self._path_traffic_overlay_grid()
            return
        self.overlay_values = build_overlay_grid(self.world, self.overlay_mode)

    def _update_status_timer(self) -> None:
        if self.status_timer > 0:
            self.status_timer -= 1
            if self.status_timer == 0:
                self.status_message = ""

    def _update_simulation(self) -> None:
        self._invalidate_forage_index()
        self.day_tick -= 1
        if self.day_tick <= 0:
            self.day_tick = self.ticks_per_day
            self._advance_day()
        day = float(self.calendar_day) + (1.0 - self.day_tick / self.ticks_per_day)
        self.world.tick(
            decay_per_tick=self.balance.get_float("DISTURBANCE_DECAY_PER_TICK"), day=day
        )
        self._update_villagers()
        self.wildlife.tick(self.world, day)
        self.fish.tick(self.world, day)
        # Biodiversity is sample-based; skip live refresh for sampled modes.
        if self.overlay_mode not in (
            OverlayMode.NONE,
            OverlayMode.BIODIVERSITY,
            OverlayMode.FLORAL_RESOURCES,
            OverlayMode.POLLINATION,
            OverlayMode.PATH_TRAFFIC,
        ):
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
                decay_per_tick=self.balance.get_float("DISTURBANCE_DECAY_PER_TICK"),
                day=day,
            )
            eco_pending = 0

        while remaining > 0:
            skip = self._idle_cooldown_skip(remaining)
            day = float(self.calendar_day) + (1.0 - self.day_tick / self.ticks_per_day)

            if skip > 1:
                flush_eco(day)
                for villager in self.villagers:
                    villager.move_cooldown = max(0, villager.move_cooldown - skip)
                    villager.work_cooldown = max(0, villager.work_cooldown - skip)
                    villager.satiation = max(
                        0.0,
                        villager.satiation
                        - VILLAGER_SATIATION_DECAY_PER_TICK
                        * villager.food_hunger_mult
                        * skip,
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
                        self.day_tick = self.ticks_per_day
                        self._advance_day()
                day = float(self.calendar_day)
                self.world.tick_bulk(
                    skip,
                    decay_per_tick=self.balance.get_float("DISTURBANCE_DECAY_PER_TICK"),
                    day=day,
                )
                self.wildlife.tick(self.world, day)
                self.fish.tick(self.world, day)
                wildlife_pending = 0
                remaining -= skip
                continue

            # Single active tick (someone can act).
            self._invalidate_forage_index()
            self.day_tick -= 1
            if self.day_tick <= 0:
                flush_eco(day)
                self.day_tick = self.ticks_per_day
                self._advance_day()
                day = float(self.calendar_day)
            else:
                day = float(self.calendar_day) + (1.0 - self.day_tick / self.ticks_per_day)

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

        day = float(self.calendar_day) + (1.0 - self.day_tick / self.ticks_per_day)
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
        self._advance_sim_ticks(self.ticks_per_day)

    def simulate_fast_days(self, days: int) -> None:
        self.fast_forward = True
        self._advance_sim_ticks(days * self.ticks_per_day)
        self.fast_forward = False

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def _draw(self) -> None:
        self.screen.fill(COLOUR_BG)
        self._draw_world()
        if self.height_edit_mode:
            self._draw_height_edit_overlay()
        elif self.overlay_mode != OverlayMode.NONE:
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
            ticks_per_day=self.ticks_per_day,
            fish_manager=self.fish,
            construction_sites=self.construction_sites,
            assign_workplace_mode=self.assign_workplace_mode,
            mouse_pos=mouse,
            season=self.season,
            calendar_day=self.calendar_day,
            selected_habitat_kind=self.selected_habitat_kind,
            selected_habitat_id=self.selected_habitat_id,
            map_edit_mode=self.height_edit_mode,
            map_edit_tool=self.map_edit_tool,
            map_edit_terrain=self.map_edit_terrain,
            height_paint_value=self.height_paint_value,
            height_delta_step=self.height_delta_step,
            height_brush_radius=self.height_brush_radius,
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
        field_pc = None
        field_bio = None
        field_health = None
        field_poll = None
        field_harvest = None
        if field_b is not None:
            cells = field_b.plot_cells()
            boost = max(0.0, float(getattr(field_b, "pest_boost", 0.0)))
            field_pc = self.env_maps.farm_pest_control(cells) + boost
            field_bio = self.env_maps.farm_biodiversity(cells)
            field_health = self._field_crop_health(field_b)
            field_poll = self.env_maps.farm_pollination(cells)
            field_harvest = max(
                1,
                int(
                    round(
                        FARM_PRODUCE_YIELD
                        * field_pc
                        * field_health
                        * pollination_yield_multiplier(field_poll)
                    )
                ),
            )
        self.field_plan_dialog.draw(
            self.screen,
            field_b,
            crop_counts=self._field_crop_counts(field_b) if field_b else None,
            pest_control=field_pc,
            biodiversity=field_bio,
            crop_health=field_health,
            pollination=field_poll,
            base_yield=FARM_PRODUCE_YIELD if field_b else None,
            harvest_yield=field_harvest,
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
            player_inventory=self.player.inventory,
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
            player_inventory=self.player.inventory,
        )
        self.resource_inspect.draw(self.screen, mouse_pos=mouse)
        self.resource_tracker.draw(
            self.screen,
            self.resource_history,
            stock_now=self._village_stock_amounts(),
            mouse_pos=mouse,
        )
        self.balance_dialog.draw(self.screen, self.balance, mouse_pos=mouse)
        self.habitat_inspect.draw(
            self.screen,
            self._habitat_inspect_view(),
            mouse_pos=mouse,
        )
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
        if fill_alpha > 0:
            for y in range(top, bottom + 1):
                for x in range(left, right + 1):
                    if tint is not None:
                        rect = self._cell_rect(x, y)
                        local = pygame.Rect(
                            rect.x, rect.y - MAP_OFFSET_Y, rect.w, rect.h
                        )
                        tint.fill((*colour, fill_alpha), local)
                    else:
                        self._draw_height_quad(x, y, colour, fill_alpha)
        pts = self._plot_outline_points(left, top, right, bottom)
        if len(pts) >= 2:
            pygame.draw.lines(self.screen, colour, True, pts, width)

    def _terrain_base_cache_key(self) -> tuple:
        from terrain_tiles import active_fill_mode

        return (
            self.world.cols,
            self.world.rows,
            CELL_SIZE,
            self.world.terrain_revision,
            active_fill_mode(),
        )

    def _invalidate_terrain_layer(self) -> None:
        self._terrain_base = None
        self._terrain_base_key = None
        self._terrain_water_mask = None
        self._terrain_grass_mask = None
        self._terrain_soil_mask = None
        self._farm_cells_cached = set()
        self._season_mute = None
        self._season_mute_key = None
        self._ice_overlay = None
        self._ice_overlay_key = None
        self._lake_ice_mask = None
        self._lake_ice_mask_key = None
        self._season_period_overlay = None
        self._season_mask_period_key = None
        self._season_compose_source = None
        self._season_compose_source_key = None
        self._season_reveal_period = None
        # Density fields are seed-stable; terrain paint only needs remask.

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
        assert (
            self._terrain_base is not None
            and self._terrain_water_mask is not None
            and self._terrain_grass_mask is not None
            and self._terrain_soil_mask is not None
        )
        paint_cell(
            self._terrain_base,
            self._terrain_water_mask,
            x,
            y,
            terrain_at=lambda tx, ty: self._visual_terrain_at(tx, ty, farm_cells),
            grass_mask=self._terrain_grass_mask,
            soil_mask=self._terrain_soil_mask,
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
    ) -> tuple[pygame.Surface, pygame.Surface, pygame.Surface, pygame.Surface]:
        """Stitch pre-rendered tiles; full rebuild on revision, else patch dirty."""
        key = self._terrain_base_cache_key()
        full_rebuild = (
            self._terrain_base is None
            or self._terrain_water_mask is None
            or self._terrain_grass_mask is None
            or self._terrain_soil_mask is None
            or self._terrain_base_key != key
        )
        self._sync_farm_terrain_dirty(farm_cells)

        if full_rebuild:
            size = (self.world.cols * CELL_SIZE, self.world.rows * CELL_SIZE)
            self._terrain_base = pygame.Surface(size)
            self._terrain_water_mask = pygame.Surface(size, pygame.SRCALPHA)
            self._terrain_water_mask.fill((0, 0, 0, 0))
            self._terrain_grass_mask = pygame.Surface(size, pygame.SRCALPHA)
            self._terrain_grass_mask.fill((0, 0, 0, 0))
            self._terrain_soil_mask = pygame.Surface(size, pygame.SRCALPHA)
            self._terrain_soil_mask.fill((0, 0, 0, 0))
            self._terrain_base_key = key
            self._farm_cells_cached = set(farm_cells)
            for y in range(self.world.rows):
                for x in range(self.world.cols):
                    self._paint_terrain_cell(x, y, farm_cells)
            self.world.terrain_dirty.clear()
            self._ice_overlay = None
            self._ice_overlay_key = None
            self._lake_ice_mask = None
            self._lake_ice_mask_key = None
            self._season_mute = None
            self._season_mute_key = None
            self._season_period_overlay = None
            self._season_mask_period_key = None
            # Flat terrain rebuilt. Keep the height warp cache: a full rebake here
            # (~700ms) fires on every env-sample day and is brutal at low ticks/day.
            # Warp colours may lag forest-floor/hardscape until the next height edit
            # or H toggle; geometry is unchanged.
            return (
                self._terrain_base,
                self._terrain_water_mask,
                self._terrain_grass_mask,
                self._terrain_soil_mask,
            )

        dirty = self.world.terrain_dirty
        if dirty:
            # Copy before clear — paint may mark nothing new.
            cells = list(dirty)
            dirty.clear()
            for x, y in cells:
                self._paint_terrain_cell(x, y, farm_cells)
            # Only drop ice/fleck caches when non-hardscape terrain changed.
            # Path dirties every day — wiping flecks forced a full remask hitch.
            hardscape = (TerrainType.PATH, TerrainType.URBAN)
            if any(
                self.world.in_bounds(x, y)
                and self.world.cells[y][x].terrain not in hardscape
                for x, y in cells
            ):
                self._ice_overlay = None
                self._ice_overlay_key = None
                self._lake_ice_mask = None
                self._lake_ice_mask_key = None
                self._season_period_overlay = None
                self._season_mask_period_key = None
            self._patch_height_warp_cells(cells)
        assert (
            self._terrain_base is not None
            and self._terrain_water_mask is not None
            and self._terrain_grass_mask is not None
            and self._terrain_soil_mask is not None
        )
        return (
            self._terrain_base,
            self._terrain_water_mask,
            self._terrain_grass_mask,
            self._terrain_soil_mask,
        )
    def _ensure_season_mute(self, vibrancy: float) -> tuple[int, int, int] | None:
        """Uniform RGB multiply tint colour, or None when vibrancy is full."""
        bucket = round(vibrancy, 1)
        if bucket >= 0.95:
            return None
        t = bucket
        return (
            int(140 + 115 * t),
            int(148 + 107 * t),
            int(158 + 97 * t),
        )

    def _ensure_lake_ice_mask(self) -> pygame.Surface:
        """Full-res alpha mask of standing WATER only (rivers excluded). Cached."""
        rev = self.world.terrain_revision
        if self._lake_ice_mask is not None and self._lake_ice_mask_key == rev:
            return self._lake_ice_mask
        size = (self.world.cols * CELL_SIZE, self.world.rows * CELL_SIZE)
        mask = pygame.Surface(size, pygame.SRCALPHA)
        mask.fill((0, 0, 0, 0))
        for y in range(self.world.rows):
            for x in range(self.world.cols):
                if self.world.cells[y][x].terrain == TerrainType.WATER:
                    mask.fill(
                        (255, 255, 255, 255),
                        pygame.Rect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE),
                    )
        self._lake_ice_mask = mask
        self._lake_ice_mask_key = rev
        return mask

    def _ensure_ice_overlay(
        self, freeze: float, water_mask: pygame.Surface
    ) -> pygame.Surface | None:
        """Ice only on standing WATER (lakes). Rivers stay open."""
        del water_mask  # lake mask is authoritative; water_mask includes rivers
        # Coarse bucket — freeze ramps slowly; avoid rebuilds every 0.1 change.
        bucket = round(freeze * 5.0) / 5.0
        if bucket < 0.05:
            return None
        if self._ice_overlay is not None and self._ice_overlay_key == bucket:
            return self._ice_overlay
        lake = self._ensure_lake_ice_mask()
        ice = pygame.Surface(lake.get_size(), pygame.SRCALPHA)
        ice.fill((210, 228, 240, int(min(1.0, bucket) * 200)))
        ice.blit(lake, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        self._ice_overlay = ice
        self._ice_overlay_key = bucket
        return ice

    @staticmethod
    def _hash01(x: int, y: int, salt: int = 0) -> float:
        n = (x * 374761393 + y * 668265263 + salt * 1274126177) & 0x7FFFFFFF
        return (n % 10007) / 10007.0

    @staticmethod
    def _season_mask_period(calendar_day: int) -> int:
        """0..7: spring1/2, summer1/2, autumn1/2, winter1/2."""
        d = int(calendar_day) % YEAR_DAYS
        season_i = d // DAYS_PER_SEASON
        half = 0 if (d % DAYS_PER_SEASON) < (DAYS_PER_SEASON // 2) else 1
        return season_i * 2 + half

    _COLOUR_WHITE: tuple[int, int, int] = (235, 240, 245)
    _COLOUR_YELLOW: tuple[int, int, int] = (210, 195, 55)
    _COLOUR_GREEN: tuple[int, int, int] = (80, 175, 60)
    _COLOUR_BROWN: tuple[int, int, int] = (160, 85, 40)
    _COLOUR_ORANGE: tuple[int, int, int] = (210, 125, 40)

    _DENSITY_KEYS: tuple[str, ...] = (
        "speckle_light",
        "speckle_med",
        "speckle_heavy",
        "cluster_light",
        "cluster_med",
        "cluster_heavy",
    )
    _SEASON_FLECK_SCALE: int = 2
    # Crossfade / colour-lerp duration in in-game days (scales with sim_speed).
    _SEASON_FADE_DAYS: float = 2.5

    @staticmethod
    def _scramble(i: int, salt: int) -> int:
        n = (i * 2654435761 + salt * 1597334677) & 0xFFFFFFFF
        n ^= (n >> 16)
        n = (n * 2246822519) & 0xFFFFFFFF
        n ^= (n >> 13)
        return n & 0x7FFFFFFF

    def _fleck_size(self) -> tuple[int, int]:
        s = self._SEASON_FLECK_SCALE
        return (
            max(1, (self.world.cols * CELL_SIZE) // s),
            max(1, (self.world.rows * CELL_SIZE) // s),
        )

    def _cluster_stamp_alpha(
        self,
        *,
        salt: int,
        dots: int,
        spread: int,
        alpha_lo: int,
        alpha_hi: int,
    ) -> pygame.Surface:
        variant = salt % 24
        key = (dots, spread, alpha_lo, alpha_hi, variant)
        cached = self._season_cluster_stamps.get(key)
        if cached is not None:
            return cached
        size = spread * 2 + 6
        stamp = pygame.Surface((size, size), pygame.SRCALPHA)
        cx = cy = size // 2
        for i in range(dots):
            ang = (self._scramble(variant + i, 10) / 0x7FFFFFFF) * math.tau
            dist = (self._scramble(variant + i, 40) / 0x7FFFFFFF) * spread
            px = cx + int(dist * math.cos(ang))
            py = cy + int(dist * math.sin(ang) * 0.85)
            alpha = alpha_lo + (
                self._scramble(variant + i, 130) % max(1, alpha_hi - alpha_lo + 1)
            )
            if i < 2:
                alpha = min(alpha_hi + 20, alpha + 15)
            radius = 1 if (self._scramble(variant + i, 160) % 10) < 7 else 2
            if 0 <= px < size and 0 <= py < size:
                pygame.draw.circle(stamp, (255, 255, 255, alpha), (px, py), radius)
        self._season_cluster_stamps[key] = stamp
        return stamp

    def _round_tree_cells(self) -> list[tuple[int, int]]:
        from trees import resolve_tree

        out: list[tuple[int, int]] = []
        for y in range(self.world.rows):
            for x in range(self.world.cols):
                cell = self.world.cells[y][x]
                if cell.feature != FeatureType.TREE:
                    continue
                if resolve_tree(cell.tree_species).shape == "round":
                    out.append((x, y))
        return out

    def _round_tree_signature(self) -> int:
        sig = 0
        for x, y in self._round_tree_cells():
            sig = (sig * 1315423911 + x * 73856093 + y * 19349663) & 0xFFFFFFFF
        return sig

    def _density_key(self) -> tuple:
        return (
            self.world.seed,
            self.world.cols,
            self.world.rows,
            CELL_SIZE,
            self._SEASON_FLECK_SCALE,
        )

    def _invalidate_season_density_fields(self) -> None:
        self._season_densities = {k: None for k in self._DENSITY_KEYS}
        self._season_density_key = None
        self._season_density_gen = None
        self._season_density_bake_step = 0
        self._season_density_baking = None
        self._season_type_masks = {}
        self._season_period_overlay = None
        self._season_mask_period_key = None
        self._season_fade_from = None
        self._season_fade_to = None
        self._season_fade_tick = 0
        self._season_fade_from_only = None
        self._season_fade_to_only = None
        self._season_fade_shared = None
        self._season_fade_shared_bucket = -1
        self._season_fade_present_bucket = -1
        self._season_tree_halo = None
        self._season_tree_halo_key = None
        self._season_tree_sig = None
        self._season_check_trees = True

    def _iter_bake_speckle_field(
        self,
        surf: pygame.Surface,
        *,
        salt: int,
        frac: float,
        alpha_lo: int,
        alpha_hi: int,
        yield_every: int = 2048,
    ):
        w, h = surf.get_size()
        n = max(0, int(round(w * h * frac)))
        for i in range(n):
            px = self._scramble(i, salt + 17) % w
            py = self._scramble(i, salt + 19) % h
            alpha = alpha_lo + (
                self._scramble(i, salt + 23) % max(1, alpha_hi - alpha_lo + 1)
            )
            surf.set_at((px, py), (255, 255, 255, alpha))
            if (i + 1) % yield_every == 0:
                yield

    def _iter_bake_cluster_field(
        self,
        surf: pygame.Surface,
        *,
        salt: int,
        frac: float,
        alpha_lo: int,
        alpha_hi: int,
        cluster_dots: int,
        cluster_spread: int,
        yield_every: int = 256,
    ):
        w, h = surf.get_size()
        n = max(0, int(round(w * h * frac)))
        for i in range(n):
            cx = self._scramble(i, salt + 41) % w
            cy = self._scramble(i, salt + 43) % h
            spread = max(2, cluster_spread + (self._scramble(i, salt + 47) % 3))
            stamp = self._cluster_stamp_alpha(
                salt=salt + i * 47,
                dots=cluster_dots,
                spread=spread,
                alpha_lo=alpha_lo,
                alpha_hi=alpha_hi,
            )
            surf.blit(
                stamp,
                (cx - stamp.get_width() // 2, cy - stamp.get_height() // 2),
            )
            if (i + 1) % yield_every == 0:
                yield

    def _advance_density_bake(self, *, budget_s: float = 0.008) -> bool:
        """Bake 6 density fields once per map. Returns True when ready."""
        key = self._density_key()
        if self._season_density_key != key:
            self._invalidate_season_density_fields()
            self._season_density_key = key
            self._season_tree_sig = self._round_tree_signature()
            self._season_check_trees = False
        if (
            all(self._season_densities[k] is not None for k in self._DENSITY_KEYS)
            and self._season_density_gen is None
            and self._season_density_bake_step >= len(self._DENSITY_KEYS)
        ):
            return True

        # Speckles = individuals only; clusters = stamp clusters only.
        specs: list[tuple[str, str, dict]] = [
            (
                "speckle_light",
                "speckle",
                dict(salt=11001, frac=0.0035, alpha_lo=55, alpha_hi=130),
            ),
            (
                "speckle_med",
                "speckle",
                dict(salt=11002, frac=0.010, alpha_lo=50, alpha_hi=125),
            ),
            (
                "speckle_heavy",
                "speckle",
                dict(salt=11003, frac=0.024, alpha_lo=45, alpha_hi=140),
            ),
            (
                "cluster_light",
                "cluster",
                dict(
                    salt=22001,
                    frac=0.00012,
                    alpha_lo=50,
                    alpha_hi=120,
                    cluster_dots=14,
                    cluster_spread=4,
                ),
            ),
            (
                "cluster_med",
                "cluster",
                dict(
                    salt=22002,
                    frac=0.00040,
                    alpha_lo=45,
                    alpha_hi=130,
                    cluster_dots=22,
                    cluster_spread=5,
                ),
            ),
            (
                "cluster_heavy",
                "cluster",
                dict(
                    salt=22003,
                    frac=0.0010,
                    alpha_lo=40,
                    alpha_hi=150,
                    cluster_dots=30,
                    cluster_spread=6,
                ),
            ),
        ]

        if self._season_density_gen is None:
            step = self._season_density_bake_step
            while step < len(specs) and self._season_densities[specs[step][0]] is not None:
                step += 1
            self._season_density_bake_step = step
            if step >= len(specs):
                return True
            name, kind, kwargs = specs[step]
            layer = pygame.Surface(self._fleck_size(), pygame.SRCALPHA)
            layer.fill((0, 0, 0, 0))
            self._season_density_baking = layer
            if kind == "speckle":
                self._season_density_gen = self._iter_bake_speckle_field(layer, **kwargs)
            else:
                self._season_density_gen = self._iter_bake_cluster_field(layer, **kwargs)

        deadline = time.perf_counter() + budget_s
        try:
            while time.perf_counter() < deadline:
                next(self._season_density_gen)
        except StopIteration:
            step = self._season_density_bake_step
            name = self._DENSITY_KEYS[step]
            self._season_densities[name] = self._season_density_baking
            self._season_density_baking = None
            self._season_density_gen = None
            self._season_density_bake_step = step + 1
            self._season_mask_period_key = None

        return (
            all(self._season_densities[k] is not None for k in self._DENSITY_KEYS)
            and self._season_density_gen is None
            and self._season_density_bake_step >= len(self._DENSITY_KEYS)
        )

    def _refresh_tree_sig(self) -> None:
        if not getattr(self, "_season_check_trees", False):
            return
        self._season_check_trees = False
        tree_sig = self._round_tree_signature()
        if self._season_tree_sig != tree_sig:
            self._season_tree_sig = tree_sig
            self._season_tree_halo = None
            self._season_tree_halo_key = None
            self._season_mask_period_key = None
            self._season_type_masks = {}

    def _tree_halo_mask(self, *, radius: int) -> pygame.Surface:
        tree_sig = self._season_tree_sig
        if tree_sig is None:
            tree_sig = self._round_tree_signature()
            self._season_tree_sig = tree_sig
        key = (radius, tree_sig, self._fleck_size())
        if self._season_tree_halo is not None and self._season_tree_halo_key == key:
            return self._season_tree_halo
        halo = pygame.Surface(self._fleck_size(), pygame.SRCALPHA)
        halo.fill((0, 0, 0, 0))
        scale = self._SEASON_FLECK_SCALE
        r_px = max(1, (radius * CELL_SIZE) // scale)
        for tx, ty in self._round_tree_cells():
            cx = (tx * CELL_SIZE + CELL_SIZE // 2) // scale
            cy = (ty * CELL_SIZE + CELL_SIZE // 2) // scale
            pygame.draw.circle(halo, (255, 255, 255, 255), (cx, cy), r_px)
        self._season_tree_halo = halo
        self._season_tree_halo_key = key
        return halo

    def _types_mask(self, types: frozenset[TerrainType]) -> pygame.Surface:
        """Half-res coverage for exact terrain types (cached on terrain_revision)."""
        key = (self.world.terrain_revision, types, self._fleck_size())
        cached = self._season_type_masks.get(key)
        if cached is not None:
            return cached
        size = self._fleck_size()
        surf = pygame.Surface(size, pygame.SRCALPHA)
        surf.fill((0, 0, 0, 0))
        scale = self._SEASON_FLECK_SCALE
        cs = max(1, CELL_SIZE // scale)
        for y in range(self.world.rows):
            for x in range(self.world.cols):
                if self.world.cells[y][x].terrain in types:
                    surf.fill(
                        (255, 255, 255, 255),
                        pygame.Rect(x * cs, y * cs, cs, cs),
                    )
        self._season_type_masks[key] = surf
        return surf

    def _mask_for(
        self,
        tag: str,
        water_mask: pygame.Surface,
        *,
        halo_radius: int,
    ) -> pygame.Surface:
        """Resolve a recipe mask tag to a half-res alpha mask."""
        if tag == "halo":
            return self._tree_halo_mask(radius=halo_radius)
        if tag == "grass":
            return self._types_mask(frozenset({TerrainType.GRASS, TerrainType.MEADOW}))
        if tag == "soil":
            return self._types_mask(frozenset({TerrainType.SOIL}))
        if tag == "open":
            return self._types_mask(
                frozenset(
                    {TerrainType.SOIL, TerrainType.GRASS, TerrainType.MEADOW}
                )
            )
        if tag == "open_water":
            land = self._types_mask(
                frozenset(
                    {TerrainType.SOIL, TerrainType.GRASS, TerrainType.MEADOW}
                )
            ).copy()
            land.blit(
                pygame.transform.scale(water_mask, self._fleck_size()),
                (0, 0),
                special_flags=pygame.BLEND_RGBA_MAX,
            )
            return land
        if tag == "hard":
            return self._types_mask(
                frozenset(
                    {
                        TerrainType.FOREST_FLOOR,
                        TerrainType.RIPARIAN,
                        TerrainType.ROCK,
                        TerrainType.URBAN,
                        TerrainType.PATH,
                    }
                )
            )
        return self._types_mask(frozenset())

    @staticmethod
    def _lerp_rgb(
        a: tuple[int, int, int], b: tuple[int, int, int], t: float
    ) -> tuple[int, int, int]:
        t = max(0.0, min(1.0, t))
        return (
            int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t),
        )

    def _period_recipe(
        self, period: int
    ) -> dict[str, tuple[tuple[int, int, int], str]]:
        """field_key -> (rgb, mask_tag) for one of the 8 year halves."""
        W, Y, G, B, O = (
            self._COLOUR_WHITE,
            self._COLOUR_YELLOW,
            self._COLOUR_GREEN,
            self._COLOUR_BROWN,
            self._COLOUR_ORANGE,
        )
        # Columns: speckle L/M/H, cluster L/M/H
        if period == 0:
            return {"speckle_light": (W, "open")}
        if period == 1:
            return {"speckle_light": (W, "grass")}
        if period == 2:
            return {"speckle_med": (Y, "grass")}
        if period == 3:
            return {
                "speckle_light": (Y, "soil"),
                "speckle_heavy": (Y, "grass"),
                "cluster_light": (G, "grass"),
            }
        if period == 4:
            return {
                "speckle_light": (O, "halo"),
                "speckle_med": (Y, "halo"),
                "cluster_med": (B, "halo"),
            }
        if period == 5:
            return {
                "speckle_med": (O, "halo"),
                "speckle_heavy": (Y, "halo"),
                "cluster_heavy": (B, "halo"),
            }
        if period == 6:
            return {
                "speckle_med": (W, "open"),
                "cluster_med": (W, "open_water"),
            }
        # period 7
        return {
            "speckle_light": (W, "hard"),
            "speckle_heavy": (W, "open_water"),
            "cluster_light": (W, "open_water"),
            "cluster_med": (W, "open_water"),
            "cluster_heavy": (W, "open_water"),
        }

    def _halo_radius_for_period(self, period: int) -> int:
        if period == 4:
            return 5
        if period == 5:
            return 10
        return 5

    def _tint_density(
        self, density: pygame.Surface, rgb: tuple[int, int, int]
    ) -> pygame.Surface:
        tinted = pygame.Surface(density.get_size(), pygame.SRCALPHA)
        tinted.fill((*rgb, 255))
        tinted.blit(density, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return tinted

    def _compose_recipe(
        self,
        recipe: dict[str, tuple[tuple[int, int, int], str]],
        water_mask: pygame.Surface,
        *,
        halo_radius: int,
        exclude: set[str] | None = None,
        alpha_scale: float = 1.0,
    ) -> pygame.Surface | None:
        """Compose selected density channels (half-res) for a recipe."""
        if any(self._season_densities[k] is None for k in self._DENSITY_KEYS):
            return None
        size = self._fleck_size()
        overlay = pygame.Surface(size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 0))
        skip = exclude or set()
        for field, (rgb, tag) in recipe.items():
            if field in skip:
                continue
            density = self._season_densities[field]
            if density is None:
                continue
            layer = self._tint_density(density, rgb)
            mask = self._mask_for(tag, water_mask, halo_radius=halo_radius)
            layer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            if alpha_scale < 0.999:
                layer.set_alpha(max(0, min(255, int(255 * alpha_scale))))
            overlay.blit(layer, (0, 0))
        return overlay

    def _compose_shared_lerp(
        self,
        from_recipe: dict[str, tuple[tuple[int, int, int], str]],
        to_recipe: dict[str, tuple[tuple[int, int, int], str]],
        shared: set[str],
        water_mask: pygame.Surface,
        *,
        t: float,
        to_period: int,
    ) -> pygame.Surface | None:
        """Shared density channels keep coverage; colour lerps old→new."""
        if not shared:
            return None
        size = self._fleck_size()
        overlay = pygame.Surface(size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 0))
        halo_r = self._halo_radius_for_period(to_period)
        for field in shared:
            rgb0, _tag0 = from_recipe[field]
            rgb1, tag1 = to_recipe[field]
            rgb = self._lerp_rgb(rgb0, rgb1, t)
            density = self._season_densities[field]
            if density is None:
                continue
            layer = self._tint_density(density, rgb)
            # Destination mask (end-of-transition terrain / halo).
            mask = self._mask_for(tag1, water_mask, halo_radius=halo_r)
            layer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            overlay.blit(layer, (0, 0))
        return overlay

    def _upscale_fleck(self, half: pygame.Surface) -> pygame.Surface:
        full = (self.world.cols * CELL_SIZE, self.world.rows * CELL_SIZE)
        if half.get_size() == full:
            return half
        return pygame.transform.scale(half, full)

    def _start_season_fade(
        self,
        from_period: int | None,
        to_period: int,
        water_mask: pygame.Surface,
    ) -> None:
        """Begin crossfade; shared density keys colour-lerp instead of fading."""
        self._season_fade_from = from_period
        self._season_fade_to = to_period
        self._season_fade_tick = 0
        self._season_fade_shared_bucket = -1
        self._season_fade_present_bucket = -1
        to_recipe = self._period_recipe(to_period)
        if from_period is None:
            self._season_fade_from_only = None
            self._season_fade_to_only = self._compose_recipe(
                to_recipe,
                water_mask,
                halo_radius=self._halo_radius_for_period(to_period),
            )
            self._season_fade_shared = None
            return
        from_recipe = self._period_recipe(from_period)
        shared = set(from_recipe) & set(to_recipe)
        self._season_fade_from_only = self._compose_recipe(
            from_recipe,
            water_mask,
            halo_radius=self._halo_radius_for_period(from_period),
            exclude=shared,
        )
        self._season_fade_to_only = self._compose_recipe(
            to_recipe,
            water_mask,
            halo_radius=self._halo_radius_for_period(to_period),
            exclude=shared,
        )
        self._season_fade_shared = self._compose_shared_lerp(
            from_recipe,
            to_recipe,
            shared,
            water_mask,
            t=0.0,
            to_period=to_period,
        )

    def _advance_season_fade(self, water_mask: pygame.Surface) -> bool:
        """Advance crossfade; returns True when finished."""
        to_period = self._season_fade_to
        if to_period is None:
            return True
        speed = max(0, int(self.sim_speed))
        if speed <= 0:
            return False
        total = max(1, int(self.ticks_per_day * self._SEASON_FADE_DAYS))
        self._season_fade_tick += speed
        t = min(1.0, self._season_fade_tick / total)
        present = int(t * 20)
        if (
            present == self._season_fade_present_bucket
            and t < 1.0
            and self._season_period_overlay is not None
        ):
            return False

        from_period = self._season_fade_from
        if from_period is not None:
            from_recipe = self._period_recipe(from_period)
            to_recipe = self._period_recipe(to_period)
            shared = set(from_recipe) & set(to_recipe)
            if present != self._season_fade_shared_bucket:
                self._season_fade_shared_bucket = present
                self._season_fade_shared = self._compose_shared_lerp(
                    from_recipe,
                    to_recipe,
                    shared,
                    water_mask,
                    t=t,
                    to_period=to_period,
                )

        size = self._fleck_size()
        half = pygame.Surface(size, pygame.SRCALPHA)
        half.fill((0, 0, 0, 0))
        if self._season_fade_from_only is not None and t < 1.0:
            a = max(0, min(255, int(255 * (1.0 - t))))
            if a > 0:
                self._season_fade_from_only.set_alpha(a)
                half.blit(self._season_fade_from_only, (0, 0))
                self._season_fade_from_only.set_alpha(255)
        if self._season_fade_to_only is not None and t > 0.0:
            a = max(0, min(255, int(255 * t)))
            if a > 0:
                self._season_fade_to_only.set_alpha(a)
                half.blit(self._season_fade_to_only, (0, 0))
                self._season_fade_to_only.set_alpha(255)
        if self._season_fade_shared is not None:
            half.blit(self._season_fade_shared, (0, 0))
        self._season_fade_present_bucket = present
        self._season_period_overlay = self._upscale_fleck(half)
        return t >= 1.0

    def _refresh_season_masks(
        self,
        grass_mask: pygame.Surface,
        soil_mask: pygame.Surface,
        water_mask: pygame.Surface,
        *,
        force: bool = False,
    ) -> None:
        """Density fields stay; 8-cycle remasks with crossfade / colour lerp."""
        del grass_mask, soil_mask  # recipes build type masks from the world grid
        if force:
            self._invalidate_season_density_fields()
        self._refresh_tree_sig()
        if not self._advance_density_bake():
            return
        period = self._season_mask_period(self.calendar_day)
        tree_sig = self._season_tree_sig
        key = (period, self.world.terrain_revision, CELL_SIZE, tree_sig)
        total = max(1, int(self.ticks_per_day * self._SEASON_FADE_DAYS))
        fading = (
            self._season_fade_to == period
            and self._season_fade_tick < total
        )
        if not force and self._season_mask_period_key == key and not fading:
            return

        if self._season_fade_to != period or force:
            prev = self._season_fade_to
            if prev is None and self._season_mask_period_key is not None:
                prev = int(self._season_mask_period_key[0])
            # Terrain-only remask of the active period: rebuild without a fade.
            if prev == period and not force:
                final = self._compose_recipe(
                    self._period_recipe(period),
                    water_mask,
                    halo_radius=self._halo_radius_for_period(period),
                )
                if final is not None:
                    self._season_period_overlay = self._upscale_fleck(final)
                self._season_mask_period_key = key
                return
            self._start_season_fade(
                prev if prev != period else None, period, water_mask
            )

        done = self._advance_season_fade(water_mask)
        if done:
            # Snap to final recipe compose (full opacity, destination masks).
            final = self._compose_recipe(
                self._period_recipe(period),
                water_mask,
                halo_radius=self._halo_radius_for_period(period),
            )
            if final is not None:
                self._season_period_overlay = self._upscale_fleck(final)
            self._season_mask_period_key = key
            self._season_fade_tick = total

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
        day = float(self.calendar_day) + (1.0 - self.day_tick / self.ticks_per_day)
        freeze = freeze_amount(day)
        vibrancy = terrain_vibrancy(day)
        farm_cells = self._farm_field_cells()
        base, water_mask, grass_mask, soil_mask = self._ensure_terrain_base(farm_cells)

        map_clip = pygame.Rect(0, MAP_OFFSET_Y, map_view_width(), map_view_height())
        self.screen.set_clip(map_clip)

        origin = (0, MAP_OFFSET_Y)
        mute = self._ensure_season_mute(vibrancy)

        if self.height_sample_enabled and self.height_sample is not None:
            # Warp path: do not run season fleck fade / ice (expensive, and we do not
            # blit them under warp). Day-length fade rebuilds were the low-ticks hitch.
            self.screen.fill(COLOUR_BG, map_clip)
            self._draw_height_sample(base)
            if mute is not None:
                tint = pygame.Surface((map_clip.w, map_clip.h))
                tint.fill(mute)
                self.screen.blit(
                    tint, map_clip.topleft, special_flags=pygame.BLEND_RGB_MULT
                )
        else:
            self._refresh_season_masks(grass_mask, soil_mask, water_mask)
            ice = self._ensure_ice_overlay(freeze, water_mask)
            self._blit_camera_world_surface(base, origin)
            if mute is not None:
                tint = pygame.Surface((map_clip.w, map_clip.h))
                tint.fill(mute)
                self.screen.blit(
                    tint, map_clip.topleft, special_flags=pygame.BLEND_RGB_MULT
                )
            if self._season_period_overlay is not None:
                self._blit_camera_world_surface(self._season_period_overlay, origin)
            if ice is not None:
                self._blit_camera_world_surface(ice, origin)

        x0, y0, x1, y1 = self.camera.visible_range(self.world.cols, self.world.rows)
        vc = self.camera.view_cell_px()
        # Tall / overhanging icons (trees, buildings) must paint after ground
        # features and in north→south order, or neighbour cells square-cut them.
        overhang = BUILDING_FEATURES | {
            FeatureType.TREE,
            FeatureType.SAPLING,
        }
        ground_cells: list[tuple[int, int]] = []
        tall_cells: list[tuple[int, int]] = []
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if not self.world.in_bounds(x, y):
                    continue
                cell = self.world.cells[y][x]
                if cell.feature in overhang and cell.feature != FeatureType.STRUCTURE_PAD:
                    tall_cells.append((x, y))
                else:
                    ground_cells.append((x, y))
        # Include one-cell halo so off-screen tree canopies still overhang in.
        for y in range(max(0, y0 - 1), min(self.world.rows, y1 + 2)):
            for x in range(max(0, x0 - 1), min(self.world.cols, x1 + 2)):
                if y0 <= y <= y1 and x0 <= x <= x1:
                    continue
                cell = self.world.cells[y][x]
                if cell.feature in overhang and cell.feature != FeatureType.STRUCTURE_PAD:
                    tall_cells.append((x, y))
        tall_cells.sort(key=lambda p: (p[1], p[0]))

        def _draw_cell_feature(x: int, y: int) -> None:
            cell = self.world.cells[y][x]
            cx, cy = self._cell_center(x, y)
            if cell.feature != FeatureType.NONE:
                from icons import ensure_icon_variant, icon_base_for_feature

                base = icon_base_for_feature(
                    cell.feature,
                    tree_species=cell.tree_species,
                    crop_kind=cell.crop_kind,
                    deposit=cell.deposit,
                    growth_ticks=cell.growth_ticks,
                )
                if base is not None:
                    cell.icon_variant = ensure_icon_variant(
                        base, cell.icon_variant, self._drop_rng
                    )
            draw_size = vc
            if (
                cell.feature in BUILDING_FEATURES
                and cell.feature != FeatureType.STRUCTURE_PAD
            ):
                draw_size = vc * max(1, BUILDING_FOOTPRINT)
            draw_feature(
                self.screen,
                cell.feature,
                cx,
                cy,
                draw_size,
                vibrancy=vibrancy,
                crop_kind=cell.crop_kind,
                tree_species=cell.tree_species,
                icon_variant=cell.icon_variant,
                deposit=cell.deposit,
                growth_ticks=cell.growth_ticks,
            )
            if cell.feature == FeatureType.CONSTRUCTION_SITE:
                site = self._construction_at(x, y)
                if site is not None and site.center_cell() == (x, y):
                    left, top, right, bottom = site.plot_bounds()
                    footprint = self._cell_rect(left, top).union(
                        self._cell_rect(right, bottom)
                    )
                    self._draw_construction_progress(site, footprint)

        for x, y in ground_cells:
            cell = self.world.cells[y][x]
            cx, cy = self._cell_center(x, y)
            _draw_cell_feature(x, y)
            if cell.meat_deposit > 0:
                from icons import ICON_MEAT_MARKER, blit_icon

                blit_icon(
                    self.screen,
                    ICON_MEAT_MARKER,
                    cx + max(4, vc // 5),
                    cy + max(4, vc // 5),
                    max(10, vc // 2),
                    recolour={"body": COLOUR_MEAT},
                )
            if cell.fish_deposit > 0:
                from icons import ICON_FISH_MARKER, blit_icon

                blit_icon(
                    self.screen,
                    ICON_FISH_MARKER,
                    cx - max(4, vc // 5),
                    cy + max(4, vc // 5),
                    max(10, vc // 2),
                    recolour={"body": COLOUR_FISH},
                )
        for x, y in tall_cells:
            _draw_cell_feature(x, y)

        self.screen.set_clip(None)

    def _draw_height_sample(
        self,
        base: pygame.Surface,
    ) -> None:
        """Blit a cached full-map height warp of the terrain base."""
        if not self.height_sample_enabled or self.height_sample is None:
            return
        region = self._height_view_region()
        if region is None or region.width <= 0 or region.height <= 0:
            return

        cache_key = (
            CELL_SIZE,
            region.x0,
            region.y0,
            region.width,
            region.height,
            id(self.height_sample),
            round(self.height_sample.max_height, 2),
        )
        if (
            self._height_sample_cache is None
            or self._height_sample_cache_key != cache_key
        ):
            ground = self._height_sample_ground_composite(base, region=region)
            self._ensure_height_sample_cache(ground, region=region)

        cache = self._height_sample_cache
        if cache is None:
            return
        pad = self._height_sample_cache_pad
        zoom = self.camera.view_cell() / CELL_SIZE

        # Wipe the visible flat footprint so warped terrain replaces it.
        vx0, vy0, vx1, vy1 = self.camera.visible_range(
            self.world.cols, self.world.rows
        )
        tl = self.camera.world_to_screen(vx0, vy0)
        br = self.camera.world_to_screen(vx1 + 1, vy1 + 1)
        wipe = pygame.Rect(
            tl[0],
            tl[1],
            max(1, br[0] - tl[0]),
            max(1, br[1] - tl[1]),
        )
        wipe.y = min(wipe.y, MAP_OFFSET_Y)
        wipe.height = max(wipe.height, MAP_OFFSET_Y + map_view_height() - wipe.y)
        wipe = wipe.clip(pygame.Rect(0, MAP_OFFSET_Y, map_view_width(), map_view_height()))
        if wipe.w > 0 and wipe.h > 0:
            self.screen.fill(COLOUR_BG, wipe)

        # Cache (0, pad) == world (region.x0 * CELL_SIZE, region.y0 * CELL_SIZE).
        world_ox = region.x0 * CELL_SIZE
        world_oy = region.y0 * CELL_SIZE - pad
        mw = map_view_width()
        mh = map_view_height()
        sx = self.camera.x * CELL_SIZE - world_ox
        sy = self.camera.y * CELL_SIZE - world_oy
        sw = mw / max(1e-6, zoom)
        sh = mh / max(1e-6, zoom)
        ix = max(0, int(math.floor(sx)))
        iy = max(0, int(math.floor(sy)))
        src = pygame.Rect(ix, iy, int(sw) + 2, int(sh) + 2).clip(cache.get_rect())
        if src.w <= 0 or src.h <= 0:
            return
        scaled = pygame.transform.scale(
            cache.subsurface(src),
            (max(1, int(round(src.w * zoom))), max(1, int(round(src.h * zoom)))),
        )
        if scaled.get_bitsize() != 24 and scaled.get_flags() & pygame.SRCALPHA:
            opaque = pygame.Surface(scaled.get_size(), depth=24)
            opaque.blit(scaled, (0, 0))
            scaled = opaque
        dest_x = int(round((ix - sx) * zoom))
        dest_y = MAP_OFFSET_Y + int(round((iy - sy) * zoom))
        self.screen.blit(scaled, (dest_x, dest_y))

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

    def _draw_height_edit_overlay(self) -> None:
        """Edit-mode overlay: height heatmap for height tools; brush for all tools."""
        map_clip = pygame.Rect(0, MAP_OFFSET_Y, map_view_width(), map_view_height())
        self.screen.set_clip(map_clip)
        x0, y0, x1, y1 = self.camera.visible_range(self.world.cols, self.world.rows)
        vc = self.camera.view_cell_px()
        show_numbers = vc >= 18
        font = self.ui.font_small if vc >= 28 else self.ui.font_icon
        tool = self.map_edit_tool
        show_height = tool in (
            MapEditTool.HEIGHT_SET,
            MapEditTool.HEIGHT_RAISE,
            MapEditTool.HEIGHT_LOWER,
        )

        hover = self._map_cell_from_pos(pygame.mouse.get_pos())
        if show_height:
            peak = max(1.0, HEIGHT_EDIT_VALUE_MAX * 0.5)
            if self.height_sample is not None and self.height_sample.max_height > peak:
                peak = self.height_sample.max_height
            # Also include paint value so the scale stays readable while editing high.
            peak = max(peak, self.height_paint_value, 1.0)
            for y in range(y0, y1 + 1):
                for x in range(x0, x1 + 1):
                    if not self.world.in_bounds(x, y):
                        continue
                    h = self.world.height_at_cell(x, y)
                    rect = self.camera.cell_rect(x, y)
                    t = max(0.0, min(1.0, h / peak))
                    heat = self._height_heatmap_colour(t)
                    tint = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
                    tint.fill((*heat, 125))
                    self.screen.blit(tint, rect.topleft)
                    if show_numbers and (hover is None or (x, y) != hover):
                        # Dark text on bright yellows; light text on deep blues.
                        lum = 0.299 * heat[0] + 0.587 * heat[1] + 0.114 * heat[2]
                        ink = (20, 20, 24) if lum > 140 else (245, 245, 240)
                        label = f"{h:.0f}"
                        text = font.render(label, True, ink)
                        tw, th = text.get_size()
                        self.screen.blit(
                            text,
                            (rect.centerx - tw // 2, rect.centery - th // 2),
                        )

        # Brush preview: ring + centre shows tool target / current.
        if hover is not None:
            hx, hy = hover
            r = self.height_brush_radius
            for y in range(hy - r, hy + r + 1):
                for x in range(hx - r, hx + r + 1):
                    if not self.world.in_bounds(x, y):
                        continue
                    if max(abs(x - hx), abs(y - hy)) > r:
                        continue
                    if (x, y) == (hx, hy):
                        continue
                    rect = self.camera.cell_rect(x, y)
                    edge = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
                    edge.fill((255, 255, 255, 40))
                    self.screen.blit(edge, rect.topleft)
            core = self.camera.cell_rect(hx, hy)
            pygame.draw.rect(self.screen, (255, 255, 255), core, 2)
            cur = self.world.height_at_cell(hx, hy)
            if tool == MapEditTool.HEIGHT_SET:
                top = f"→{self.height_paint_value:.0f}"
                bot = f"{cur:.0f}"
            elif tool == MapEditTool.HEIGHT_RAISE:
                top = f"↑{self.height_delta_step:.0f}"
                bot = f"{cur:.0f}"
            elif tool == MapEditTool.HEIGHT_LOWER:
                top = f"↓{self.height_delta_step:.0f}"
                bot = f"{cur:.0f}"
            elif tool == MapEditTool.TERRAIN_PAINT:
                top = TERRAIN_EDIT_LABELS.get(
                    self.map_edit_terrain, self.map_edit_terrain.name.title()
                )
                bot = TERRAIN_EDIT_LABELS.get(
                    self.world.cells[hy][hx].terrain,
                    self.world.cells[hy][hx].terrain.name.title(),
                )
            else:
                top = "Forest"
                bot = TERRAIN_EDIT_LABELS.get(
                    self.world.cells[hy][hx].terrain,
                    self.world.cells[hy][hx].terrain.name.title(),
                )
            if vc >= 22:
                line1 = font.render(top, True, (255, 255, 255))
                line2 = font.render(bot, True, (230, 230, 235))
                gap = 1 if vc < 32 else 2
                total_h = line1.get_height() + line2.get_height() + gap
                ty = core.centery - total_h // 2
                self.screen.blit(line1, (core.centerx - line1.get_width() // 2, ty))
                self.screen.blit(
                    line2,
                    (core.centerx - line2.get_width() // 2, ty + line1.get_height() + gap),
                )
            else:
                label = font.render(f"{top}/{bot}", True, (255, 255, 255))
                self.screen.blit(
                    label,
                    (
                        core.centerx - label.get_width() // 2,
                        core.centery - label.get_height() // 2,
                    ),
                )
        self.screen.set_clip(None)

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
                self._draw_height_quad(x, y, colour, OVERLAY_ALPHA)
        self.screen.set_clip(None)

    def _draw_task_areas(self) -> None:
        building = self._selected_building()
        map_clip = pygame.Rect(0, MAP_OFFSET_Y, map_view_width(), map_view_height())
        self.screen.set_clip(map_clip)

        # Field plots: always outline unploughed fields; selected fields too.
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

        # While placing a field, show every existing field outline for alignment.
        if self.place_kind == BuildingKind.FIELD or self._placing_field:
            for field_b in self.buildings.values():
                if field_b.kind != BuildingKind.FIELD:
                    continue
                left, top, right, bottom = field_b.plot_bounds()
                self._draw_field_plot_outline(
                    left,
                    top,
                    right,
                    bottom,
                    colour=COLOUR_FARM,
                    width=2,
                    fill_alpha=18,
                )
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
                    fill_alpha=18,
                )

        # Non-field build ghost: 3×3 footprint centred on the hovered cell.
        if (
            self.place_kind is not None
            and self.place_kind != BuildingKind.FIELD
            and not self.drawing
        ):
            mouse = pygame.mouse.get_pos()
            hover = self._map_cell_from_pos(mouse)
            if hover is not None:
                plot_w, plot_h = default_building_plot(self.place_kind)
                ox = hover[0] - plot_w // 2
                oy = hover[1] - plot_h // 2
                cells = [
                    (px, py)
                    for py in range(oy, oy + plot_h)
                    for px in range(ox, ox + plot_w)
                ]
                blocked = self._footprint_blocked(cells) is not None
                colour = (180, 70, 70) if blocked else COLOUR_TASK_PREVIEW
                for px, py in cells:
                    self._draw_height_quad(px, py, colour, 55)
                self._draw_field_plot_outline(
                    ox,
                    oy,
                    ox + plot_w - 1,
                    oy + plot_h - 1,
                    colour=colour,
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
                        self._draw_height_quad(x, y, colour, 55)
                self._draw_field_plot_outline(
                    left, top, right, bottom, colour=colour, width=2, fill_alpha=0
                )

        if self.drawing and self.draw_start and self.draw_current:
            x0, y0 = self.draw_start
            x1, y1 = self.draw_current
            left, top = min(x0, x1), min(y0, y1)
            right, bottom = max(x0, x1), max(y0, y1)
            placing_field = self._placing_field or self.place_kind == BuildingKind.FIELD
            if placing_field:
                overlap = self._field_drag_overlaps(left, top, right, bottom)
                preview = (180, 70, 70) if overlap else COLOUR_TASK_FARM
            elif building is not None:
                preview = TASK_COLOURS.get(building.draw_task_type, COLOUR_TASK_PREVIEW)
            else:
                preview = COLOUR_TASK_PREVIEW
            for y in range(top, bottom + 1):
                for x in range(left, right + 1):
                    self._draw_height_quad(x, y, preview, 70)
            self._draw_field_plot_outline(
                left,
                top,
                right,
                bottom,
                colour=COLOUR_TASK_PREVIEW if not placing_field else preview,
                width=2,
                fill_alpha=0,
            )

        self.screen.set_clip(None)

    def _field_needs_plough(self, building: Building) -> bool:
        """True if any plot tile is still unploughed grass/meadow."""
        for x, y in building.plot_cells():
            cell = self.world.get_cell(x, y)
            if cell is None:
                continue
            if cell.terrain not in SOIL_LIKE:
                return True
        return False

    def _draw_field_building(self, building: Building) -> None:
        """Outline selected fields, and any field that still needs ploughing."""
        selected = building.id == self.selected_building_id
        needs_plough = self._field_needs_plough(building)
        if not selected and not needs_plough:
            return
        left, top, right, bottom = building.plot_bounds()
        self._draw_field_plot_outline(
            left,
            top,
            right,
            bottom,
            colour=COLOUR_SELECTED_ENTITY if selected else COLOUR_FARM,
            width=3 if selected else 2,
            fill_alpha=0,
        )

    def _draw_animals(self) -> None:
        from wildlife import AnimalKind, AnimalSex
        from icons import (
            ICON_BEE,
            ICON_BEE_HIVE,
            ICON_BOAR_FEMALE,
            ICON_BOAR_MALE,
            ICON_BURROW,
            ICON_DEER_FEMALE,
            ICON_DEER_MALE,
            ICON_RABBIT,
            blit_icon,
        )
        from settings import COLOUR_BOAR, COLOUR_DEER

        size = self.camera.view_cell_px()
        for animal in self.wildlife.animals:
            if animal.kind not in (AnimalKind.DEER, AnimalKind.BOAR):
                continue
            ax, ay = entity_draw_xy(animal)
            cx, cy = self._cell_center(ax, ay)
            cy += max(1, size // 20)
            if animal.kind == AnimalKind.BOAR:
                colour = COLOUR_BOAR
                name = (
                    ICON_BOAR_FEMALE
                    if animal.sex == AnimalSex.FEMALE
                    else ICON_BOAR_MALE
                )
            else:
                colour = COLOUR_DEER
                name = (
                    ICON_DEER_FEMALE
                    if animal.sex == AnimalSex.FEMALE
                    else ICON_DEER_MALE
                )
            if animal.sex == AnimalSex.FEMALE:
                colour = (
                    min(255, colour[0] + 28),
                    min(255, colour[1] + 18),
                    min(255, colour[2] + 22),
                )
            blit_icon(self.screen, name, cx, cy, size, recolour={"body": colour})

        # Colony nests + members — use SVG colours (no body wash).
        member_size = max(8, size * 2 // 3)
        for colony in self.wildlife.colonies:
            nest_name = (
                ICON_BEE_HIVE if colony.kind == AnimalKind.BEE else ICON_BURROW
            )
            member_name = ICON_BEE if colony.kind == AnimalKind.BEE else ICON_RABBIT
            nx, ny = entity_draw_xy(colony)
            cx, cy = self._cell_center(nx, ny)
            blit_icon(self.screen, nest_name, cx, cy, size)
            for member in colony.members:
                mx, my = entity_draw_xy(member)
                cx, cy = self._cell_center(mx, my)
                cy += max(1, size // 20)
                blit_icon(self.screen, member_name, cx, cy, member_size)

    def _draw_fish(self) -> None:
        from icons import ICON_FISH, blit_icon

        freeze = freeze_amount(
            float(self.calendar_day) + (1.0 - self.day_tick / self.ticks_per_day)
        )
        colour = blend_colour(COLOUR_FISH, (150, 190, 210), freeze)
        size = self.camera.view_cell_px()
        for item in self.fish.fish:
            fx, fy = entity_draw_xy(item)
            cx, cy = self._cell_center(fx, fy)
            blit_icon(self.screen, ICON_FISH, cx, cy, size, recolour={"body": colour})

    def _draw_villagers(self) -> None:
        from icons import ICON_VILLAGER, blit_icon

        size = self.camera.view_cell_px()
        for villager in self.villagers:
            vx, vy = entity_draw_xy(villager)
            cx, cy = self._cell_center(vx, vy)
            job_colour = self._villager_job_colour(villager)
            blit_icon(
                self.screen,
                ICON_VILLAGER,
                cx,
                cy,
                size,
                recolour={"shirt": job_colour, "hat": job_colour},
            )

    def _draw_player(self) -> None:
        from icons import ICON_PLAYER, blit_icon

        cx, cy = self._cell_center(self.player.vis_x, self.player.vis_y)
        blit_icon(
            self.screen,
            ICON_PLAYER,
            cx,
            cy,
            self.camera.view_cell_px(),
            recolour={"body": COLOUR_PLAYER},
        )

    def _draw_cell_set_outline(
        self,
        cells: set[tuple[int, int]],
        *,
        colour: tuple[int, int, int],
        width: int = 2,
    ) -> None:
        """Draw only the outer border of a cell region (no internal grid lines)."""
        for x, y in cells:
            pts = self._cell_quad_points(x, y)
            nw, ne, se, sw = pts
            if (x, y - 1) not in cells:
                pygame.draw.line(self.screen, colour, nw, ne, width)
            if (x, y + 1) not in cells:
                pygame.draw.line(self.screen, colour, sw, se, width)
            if (x - 1, y) not in cells:
                pygame.draw.line(self.screen, colour, nw, sw, width)
            if (x + 1, y) not in cells:
                pygame.draw.line(self.screen, colour, ne, se, width)

    def _draw_selection_highlights(self) -> None:
        if self.selected_villager_id is not None:
            villager = self._get_villager(self.selected_villager_id)
            if villager is not None:
                pts = self._cell_quad_points(villager.x, villager.y)
                pygame.draw.lines(self.screen, COLOUR_SELECTED_ENTITY, True, pts, 3)
        if self.selected_building_id is not None:
            building = self.buildings.get(self.selected_building_id)
            if building is not None:
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
        if (
            self.selected_habitat_id is not None
            and self.selected_habitat_kind is not None
        ):
            kind = self.selected_habitat_kind
            hab = self.wildlife.habitat(self.selected_habitat_id, kind)
            if hab is not None:
                tiles = set(self.wildlife._breeding_for(kind, hab))
                roam = self.wildlife._cold_roaming_for(kind, hab)
                roam_only = roam - tiles
                if roam_only:
                    self._draw_cell_set_outline(
                        roam_only,
                        colour=(120, 140, 80),
                        width=1,
                    )
                if tiles:
                    self._draw_cell_set_outline(
                        tiles,
                        colour=COLOUR_SELECTED_ENTITY,
                        width=2,
                    )

    def _draw_minimap(self) -> None:
        """Draw minimap showing terrain, buildings, and camera viewport."""
        minimap_rect = self._minimap_rect()
        pygame.draw.rect(self.screen, (20, 20, 25), minimap_rect)

        sample_step = max(
            1, max(self.world.cols // MINIMAP_WIDTH, self.world.rows // MINIMAP_HEIGHT)
        )
        terrain_key = (self.world.cols, self.world.rows, sample_step)
        if (
            self._minimap_terrain is None
            or self._minimap_terrain_key != terrain_key
            or self._minimap_terrain.get_size() != (MINIMAP_WIDTH, MINIMAP_HEIGHT)
        ):
            from ui import terrain_colour

            surf = pygame.Surface((MINIMAP_WIDTH, MINIMAP_HEIGHT))
            surf.fill((20, 20, 25))
            for wy in range(0, self.world.rows, sample_step):
                row = self.world.cells[wy]
                for wx in range(0, self.world.cols, sample_step):
                    cell = row[wx]
                    mini_x = int(wx * MINIMAP_WIDTH / self.world.cols)
                    mini_y = int(wy * MINIMAP_HEIGHT / self.world.rows)
                    pixel_w = max(1, int(sample_step * MINIMAP_WIDTH / self.world.cols))
                    pixel_h = max(1, int(sample_step * MINIMAP_HEIGHT / self.world.rows))
                    colour = terrain_colour(cell.terrain)
                    colour = (colour[0] // 3, colour[1] // 3, colour[2] // 3)
                    surf.fill(colour, pygame.Rect(mini_x, mini_y, pixel_w, pixel_h))
            self._minimap_terrain = surf
            self._minimap_terrain_key = terrain_key

        self.screen.blit(self._minimap_terrain, minimap_rect.topleft)

        from settings import (
            COLOUR_CRAFT_BENCH,
            COLOUR_ALCHEMIST,
            COLOUR_FARM,
            COLOUR_FIELD,
            COLOUR_FISHER,
            COLOUR_FORAGER,
            COLOUR_FORESTER,
            COLOUR_HOME,
            COLOUR_HUNTER,
            COLOUR_KITCHEN,
            COLOUR_MASON,
            COLOUR_MILL,
            COLOUR_WORKSTATION,
        )

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
            BuildingKind.MILL: COLOUR_MILL,
            BuildingKind.KITCHEN: COLOUR_KITCHEN,
            BuildingKind.CRAFT_BENCH: COLOUR_CRAFT_BENCH,
            BuildingKind.ALCHEMIST: COLOUR_ALCHEMIST,
        }
        for building in self.buildings.values():
            cx, cy = building.center_cell()
            mini_x = minimap_rect.x + int(cx * MINIMAP_WIDTH / self.world.cols)
            mini_y = minimap_rect.y + int(cy * MINIMAP_HEIGHT / self.world.rows)
            colour = colour_map.get(building.kind, (200, 200, 200))
            pygame.draw.circle(self.screen, colour, (mini_x, mini_y), 2)

        player_x = minimap_rect.x + int(self.player.x * MINIMAP_WIDTH / self.world.cols)
        player_y = minimap_rect.y + int(self.player.y * MINIMAP_HEIGHT / self.world.rows)
        pygame.draw.circle(self.screen, COLOUR_PLAYER, (player_x, player_y), 2)

        x0, y0, x1, y1 = self.camera.visible_range(self.world.cols, self.world.rows)
        viewport_x = minimap_rect.x + int(x0 * MINIMAP_WIDTH / self.world.cols)
        viewport_y = minimap_rect.y + int(y0 * MINIMAP_HEIGHT / self.world.rows)
        viewport_w = max(1, int((x1 - x0) * MINIMAP_WIDTH / self.world.cols))
        viewport_h = max(1, int((y1 - y0) * MINIMAP_HEIGHT / self.world.rows))
        pygame.draw.rect(
            self.screen,
            (255, 255, 255),
            pygame.Rect(viewport_x, viewport_y, viewport_w, viewport_h),
            1,
        )
        pygame.draw.rect(self.screen, (100, 100, 110), minimap_rect, 2)

