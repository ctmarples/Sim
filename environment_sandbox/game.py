"""Main game loop: input, buildings, villagers, update, and render.

Player presses Enter/E on their cell (needs equipped tools for chop/hunt/fish).
F eats the highlighted inventory food (select or hover); right-click food also eats.
Q equips/unequips tools; I opens inventory (drag tools to equip). On a stocked
construction site, E builds (pads or centre). Arrow keys move the player; WASD
pans the camera — both work at the same time. Opening a workplace via E shows
Craft on recipes. Movement/work use villager satiation pacing. Toolbar handles
build, tasks, speed, and File save/load. Esc clears selection / menus (does not quit).
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
    phase_allows_harvest,
    phase_allows_plough_plant,
    phase_for_crop,
)
from resource_balance import (
    BERRY_SEED_DROP_CHANCE,
    farm_produce_yield,
    FARM_SEED_AMOUNTS,
    FISH_YIELD,
    FISH_POST_LOCAL_RADIUS,
    FISH_POST_MIN_FISH,
    FISH_POST_SCORE_RADIUS,
    FORAGER_PRIORITY_BAND,
    WORK_SEARCH_RADIUS,
    PATH_DETOUR_RATIO,
    PATH_DETOUR_SLACK,
    PATH_PICK_MAX_PER_RING,
    HONEY_PER_BEE_LEVEL,
    MAX_FOOD_TYPES_PER_MEAL,
    MUSHROOM_YIELD,
    POLLINATOR_BASE_RADIUS,
    POLLINATOR_BASE_STRENGTH,
    POLLINATOR_RADIUS_PER_LEVEL,
    POLLINATOR_STRENGTH_PER_LEVEL,
    FIELD_PEST_BOOST_MAX,
    MINERAL_POWDER_PEST_BOOST,
    REED_YIELD,
    SAPLING_DROP_CHANCE,
    STARTING_FOOD,
    VILLAGER_FOOD_KEYS,
    satiation_decay_per_tick,
    WILD_PRODUCE_YIELD,
    combine_meal_buffs,
    food_def,
    food_is_sweet,
    food_preference_key,
    format_buff_mult,
    meal_covers_any_requirement,
    meal_includes_meat,
    satiation_from_points,
    storage_meal_score,
)
from entities import (
    BUILDING_LABELS,
    DEFAULT_PRIORITIES_UNASSIGNED,
    PRIORITY_LABELS,
    RATION_LABELS,
    RECIPE_PRIORITY_MAX,
    SITE_PHASE_BUILD,
    SITE_PHASE_DECONSTRUCT,
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
    WORKPLACE_EXTRA_TOOLS,
    WORKPLACE_ALSO_REQUIRES,
    WORKPLACE_TOOL,
    HUNTER_BOW_HIT_CHANCE,
    HUNTER_BOW_MIN_SKILL,
    HUNTER_BOW_RANGE,
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
    preferred_clothing_for_temp,
    snap_entity_visual,
)
from indicators import (
    OVERLAY_LABELS,
    OverlayMode,
    build_overlay_grid,
    floral_resources_snapshot,
    format_overlay_value,
    overlay_colour,
    pollination_coverage_grid,
)
from environment import (
    EnvLayer,
    EnvMaps,
    crop_health_cap_from_pest_control,
    crop_health_max_drop,
    crop_health_min,
    is_env_sample_day,
    pollination_yield_multiplier,
    soil_moisture_grid,
    temperature_grid,
)
from farm_pipeline import (
    FarmJob,
    FarmJobKind,
    barn_sheaf_keep_amount,
    barn_sheaf_keys,
)
from settings import (
    BUILDING_STORAGE_CAPACITY,
    BUILDING_FOOTPRINT,
    CELL_SIZE,
    COLOUR_BOAR,
    COLOUR_DEER,
    COLOUR_BG,
    COLOUR_GRASS,
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
    COLOUR_TAILOR,
    COLOUR_COBBLER,
    COLOUR_MARKET,
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
    COLOUR_TEXT,
    COLOUR_TEXT_DIM,
    COLOUR_TOOLBAR_BORDER,
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
    TAILOR_COST_WOOD,
    TAILOR_COST_ROCK,
    CRAFT_BENCH_COST_WOOD,
    MASON_COST_ROCK,
    MASON_COST_WOOD,
    MAX_VILLAGERS,
    MILL_COST_ROCK,
    MILL_COST_WOOD,
    MINIMAP_HEIGHT,
    MINIMAP_WIDTH,
    OVERLAY_ALPHA,
    SIM_SPEEDS,
    DAY_SECONDS_OPTIONS,
    seconds_to_ticks,
    ticks_to_seconds,
    STARTING_ROCK,
    STARTING_WOOD,
    STARTING_TWINE,
    STARTING_VILLAGERS,
    AUTOLOAD_SAVE,
    STATUS_MESSAGE_FRAMES,
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
    toggle_panel_collapsed,
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
from number_input_dialog import NumberInputDialog
from assign_picker_dialog import AssignPickerDialog
from building_inspect_dialog import BuildingInspectDialog
from field_plan_dialog import FieldPlanDialog
from habitat_inspect_dialog import HabitatInspectDialog, HabitatInspectView
from management_window import ManagementWindow, MgmtTab
from player_inventory_dialog import PlayerInventoryDialog
from resource_inspect_dialog import ResourceInspectDialog
from resource_tracker import ResourceHistory
from resource_tracker_dialog import ResourceTrackerDialog
from villager_inspect_dialog import VillagerInspectDialog
from resource_bar import VIEW_LABELS, ResourceBar
from recipes import (
    apply_recipe,
    apply_recipe_outputs,
    hunt_recipe,
    recipe_outputs_fit,
)
from bug_log import BugLog
from save_load import load_from_path, save_to_path
from seasons import (
    DAYS_PER_SEASON,
    TICKS_PER_DAY,
    YEAR_DAYS,
    Season,
    ambient_temperature_c,
    blend_colour,
    day_in_season,
    fishing_allowed,
    format_date,
    freeze_amount,
    season_for_day,
    seed_chance_multiplier,
    set_ticks_per_day,
    temperature_impact,
    terrain_vibrancy,
    water_frozen,
)
from toolbar import Toolbar
from building_unlock import (
    building_cost as unlock_building_cost,
    built_kinds as unlock_built_kinds,
    visible_build_order,
)
from society import (
    Community,
    HireCandidate,
    SkillType,
    ENERGY_MOVE_DRAIN,
    ENERGY_SLEEP_GAIN,
    ENERGY_SLEEP_THRESHOLD,
    ENERGY_WORK_DRAIN,
    HAPPINESS_FAVOURITE_MISS_PENALTY,
    HAPPINESS_FOOD_VARIETY_BONUS,
    HAPPINESS_HOUSING_BONUS_PER_LEVEL,
    HAPPINESS_LEAVE_SEASONS,
    HAPPINESS_LEAVE_THRESHOLD,
    HAPPINESS_MISSING_REQ_PENALTY,
    MAX_TRAVELLERS,
    SEASON_MISSING_REQ_PAY_COINS,
    candidate_requirement_rows,
    free_housing_beds,
    gain_skill,
    generate_communities,
    hire_unmet_requirements,
    housed_count,
    housing_beds_of,
    housing_level_of,
    is_housing_kind,
    max_housing_level,
    push_happiness_event,
    requirement_label,
    season_pay_coins,
    skill_efficiency,
    skill_for_building,
    skills_from_dict,
    skills_to_dict,
    spawn_travellers_from_templates,
    staple_food_available,
    tick_skill_decay,
    total_housing_beds,
    villager_meets_skill,
    villager_requirement_rows,
    villager_skill_level,
    villager_unmet_requirements,
    apply_happiness_points,
)
from villager_roster import (
    VillagerRosterDialog,
    entry_from_candidate,
    entry_from_villager,
    villager_job_colour,
)
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
    FIELDABLE_LAND,
    PLANTABLE_LAND,
    SOIL_LIKE,
    TERRAIN_EDIT_LABELS,
    TerrainType,
    World,
    cell_has_path,
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
    BuildingKind.TAILOR: FeatureType.TAILOR,
    BuildingKind.COBBLER: FeatureType.COBBLER,
    BuildingKind.MARKET: FeatureType.MARKET,
    BuildingKind.TENT: FeatureType.TENT,
    BuildingKind.HOUSE_SMALL: FeatureType.HOUSE_SMALL,
    BuildingKind.HOUSE: FeatureType.HOUSE,
    BuildingKind.BARN: FeatureType.BARN,
    BuildingKind.PANTRY: FeatureType.PANTRY,
    BuildingKind.DRYING_RACK: FeatureType.DRYING_RACK,
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
        try:
            from terrain_settings import load_settings

            load_settings()
        except Exception:
            pass
        if headless:
            self.screen = pygame.Surface((max(1, WINDOW_WIDTH), max(1, WINDOW_HEIGHT)))
        else:
            self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
            pygame.display.set_caption("Environmental Farming Sandbox")
        from icons import ALL_ICON_NAMES, preload, preload_building_stipple

        preload(ALL_ICON_NAMES, sizes=(CELL_SIZE,))
        preload_building_stipple()
        self.clock = pygame.time.Clock()
        self.ui = UI()
        self.toolbar = Toolbar()
        self.resource_bar = ResourceBar()
        self.file_dialog = FileDialog()
        self.number_input = NumberInputDialog()
        self.field_plan_dialog = FieldPlanDialog()
        self.habitat_inspect = HabitatInspectDialog()
        self.building_inspect = BuildingInspectDialog()
        self.villager_inspect = VillagerInspectDialog()
        self.villager_roster = VillagerRosterDialog()
        self.management = ManagementWindow()
        self.assign_picker = AssignPickerDialog()
        self.player_inventory = PlayerInventoryDialog()
        self.relocate_building_id: int | None = None
        self.selected_construction_id: int | None = None
        self._player_hud_tool_hits: list[tuple[pygame.Rect, str]] = []
        self.resource_inspect = ResourceInspectDialog()
        self.resource_tracker = ResourceTrackerDialog()
        self.balance_dialog = BalanceDialog()
        self.balance = BalanceState()
        set_active_balance(self.balance)
        from save_load import saves_dir

        self.balance.enable_autosave(saves_dir() / "balance_prefs.json")
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
        self._fishing_shore_cache: set[tuple[int, int]] | None = None
        self._fishing_shore_revision: int = -1
        self.camera = Camera()
        self.height_sample = generate_height_sample(
            self.world.cols,
            self.world.rows,
            seed=self.world.seed,
            corners=self.world.height_corners,
        )
        self.player = Player(x=self.world.start_pos[0], y=self.world.start_pos[1])
        self.player_craft_building_id: int | None = None
        self.player_craft_recipe: str | None = None
        self.player_craft_split: bool = False
        self.player_build_site_id: int | None = None
        self.camera.center_on(self.player.x, self.player.y, self.world.cols, self.world.rows)
        self.home_storage = HomeStorage()
        self.regional_wealth: int = 0
        self.villagers: list[Villager] = []
        self.communities: list[Community] = []
        self.hire_candidates: list[HireCandidate] = []
        self.next_hire_id = 1
        self.next_community_id = 1
        self._last_season_for_hire_reqs: object | None = None
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
        self._last_save_path = None  # Path | None — last successful save/load
        self._loaded_save_name: str | None = None
        self.bug_log = BugLog(enabled=False)
        # Bumped when stock/jobs change so sticky-IDLE workers wake early.
        self._work_gen: int = 0
        self._idle_skip_events: int = 0
        self._idle_skip_ticks: int = 0
        self._travel_skip_steps: int = 0
        # Headless only: jump idle/cooldown waits. Live play ignores this path.
        self._cooldown_skip_enabled: bool = True

        # Selection / drawing
        self.selected_building_id: int | None = None
        self.selected_villager_id: int | None = None
        self.selected_habitat_kind: AnimalKind | None = None
        self.selected_habitat_id: int | None = None
        # H toggles map-wide wildlife habitat outlines (hover + click to select).
        self.habitat_view_mode: bool = False
        self._habitat_hover: tuple[AnimalKind, int] | None = None
        self.assign_workplace_mode = False
        self.assign_workplace_picking = False
        self.assign_workplace_slot: int = 0
        self.assign_workplace_season: str | None = None
        self.area_draw_task: TaskType | None = None
        self.place_kind: BuildingKind | None = None  # B cycles build ghost
        self.extension_parent_id: int | None = None  # parent for extension placement
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
        self._bake_erosion()
        # Rebuilt at most once per sim tick; avoids full-map forage scans per villager.
        self._forage_cell_index: dict[str, list[tuple[int, int]]] | None = None
        self._forage_index_age = 0
        self._eco_pending = 0
        self._wildlife_pending = 0
        self._minimap_terrain: pygame.Surface | None = None
        self._minimap_terrain_key: tuple[int, int, int] | None = None
        # Active bow-shot visuals: (x0, y0, x1, y1, age, duration, hit).
        self._arrow_shots: list[tuple[float, float, float, float, int, int, bool]] = []
        # Villager wear map: cell → cumulative traffic (decayed on env sample).
        self._path_traffic: dict[tuple[int, int], float] = {}
        self._drop_rng = random.Random(42)
        self._food_rng = random.Random(99)

        self._boot_game()
        if not getattr(self, "status_message", None):
            self.status_message = (
                "Valley ready. Build a Forager first — hover build icons for costs. "
                "Hiring hall unlocks later."
            )
            self.status_timer = STATUS_MESSAGE_FRAMES
        self.running = True
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
        self.home_storage.wood = STARTING_WOOD
        self.home_storage.rock = STARTING_ROCK
        self.home_storage.twine = STARTING_TWINE
        self.home_storage.berries = STARTING_FOOD
        # Pocket snacks so the player can eat for walk speed before the first forage.
        if self.player.inventory.berries <= 0:
            self.player.inventory.add_item("berries", min(4, STARTING_FOOD))

    def _most_recent_save_path(self):
        """Newest world ``*.json`` in the saves folder, or None."""
        from save_load import iter_save_paths

        files = iter_save_paths()
        if not files:
            return None
        return max(files, key=lambda p: p.stat().st_mtime)

    def _autoload_save_path(self):
        """Template map used when starting a stripped new game."""
        from pathlib import Path

        name = AUTOLOAD_SAVE
        candidates = (
            Path(__file__).resolve().parents[1] / "saves" / name,
            Path(__file__).resolve().parent / "data" / name,
            Path(__file__).resolve().parent / "saves" / name,
        )
        for path in candidates:
            if path.is_file():
                return path
        return self._most_recent_save_path()

    def _boot_game(self) -> None:
        """On launch: load the most recent save, else start a fresh game."""
        path = self._most_recent_save_path()
        if path is not None:
            load_from_path(self, str(path))
            self._last_save_path = path
            self._loaded_save_name = path.name
            self._sync_time_knobs_from_clock()
            self.status_message = f"Loaded {path.name}"
            self.status_timer = STATUS_MESSAGE_FRAMES
            return
        self._start_fresh_game()

    def _spawn_starting_villagers(self, count: int | None = None) -> None:
        n = STARTING_VILLAGERS if count is None else max(0, int(count))
        hx, hy = self.world.home_pos
        spots = [(hx, hy)]
        spots.extend(
            (nx, ny) for ny, nx in self.world.neighbourhood(hx, hy, radius=2)
            if (nx, ny) != (hx, hy)
        )
        for i in range(n):
            sx, sy = spots[i % len(spots)]
            villager = Villager(id=self.next_villager_id, x=sx, y=sy)
            villager.priorities = list(DEFAULT_PRIORITIES_UNASSIGNED)
            self.villagers.append(villager)
            self.next_villager_id += 1

    def _apply_new_game_strip(self) -> None:
        """Keep valley terrain/wildlife; storehouse only; clear paths; 3 villagers."""
        home = next(
            (b for b in self.buildings.values() if b.kind == BuildingKind.HOME), None
        )
        keep_id = home.id if home is not None else None
        for bid in list(self.buildings.keys()):
            if bid != keep_id:
                del self.buildings[bid]
        self.construction_sites.clear()

        home_cells: set[tuple[int, int]] = set()
        if home is not None:
            home_cells = set(home.plot_cells())
            self.world.home_pos = home.center_cell()

        clear_features = BUILDING_FEATURES | {
            FeatureType.STRUCTURE_PAD,
            FeatureType.CONSTRUCTION_SITE,
        }
        for y in range(self.world.rows):
            for x in range(self.world.cols):
                cell = self.world.cells[y][x]
                if cell.terrain == TerrainType.PATH:
                    cell.terrain = TerrainType.GRASS
                    cell.path_worn = False
                if (x, y) in home_cells:
                    continue
                if cell.feature in clear_features:
                    cell.feature = FeatureType.NONE
                    cell.deposit = 0

        if home is not None:
            self.world.claim_structure_footprint(
                home.x, home.y, home.plot_w, home.plot_h, FeatureType.HOME
            )
            cx, cy = home.center_cell()
            # Placeholder until a hiring hall is built.
            self.world.workstation_pos = (
                min(self.world.cols - 1, cx + max(3, home.plot_w)),
                cy,
            )

        self.villagers.clear()
        self.next_villager_id = 1
        if self.buildings:
            self.next_building_id = max(b.id for b in self.buildings.values()) + 1
        else:
            self.next_building_id = 1
        self.next_construction_id = 1
        self.calendar_day = 0
        self.day_tick = self.ticks_per_day
        set_ticks_per_day(self.ticks_per_day)
        self.home_storage.reset()
        self.regional_wealth = 0
        self._give_starting_resources()
        self._spawn_starting_villagers()
        self._clear_selection()
        self.place_kind = None
        self._path_traffic.clear()
        self.player.reset(self.world.start_pos[0], self.world.start_pos[1])
        self.camera.center_on(
            self.player.x, self.player.y, self.world.cols, self.world.rows
        )
        self._refresh_hardscape_terrain()
        self._invalidate_height_sample_cache()
        # Fallen wood beside trees so foragers have something to gather at start.
        self.world._seed_wood_near_trees(random.Random(int(self.world.seed) ^ 0xA70D))
        self._seed_map_communities()
        self._refresh_indicators()
        self._apply_time_balance()
        self.day_tick = self.ticks_per_day

    def _start_fresh_game(self) -> None:
        path = self._autoload_save_path()
        if path is not None:
            from save_load import load_from_path

            load_from_path(self, str(path))
            self._apply_new_game_strip()
            return
        self._give_starting_resources()
        self._ensure_core_buildings()
        self._spawn_starting_villagers()
        self.wildlife.refresh_habitats(self.world)
        self.wildlife.seed_breeding_grounds(self.world)
        self._sample_environment()

    def _ensure_core_buildings(self) -> None:
        """Ensure the storehouse exists at the world home position."""
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

        _sync_core(BuildingKind.HOME, self.world.home_pos)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def run(self) -> None:
        pygame.key.set_repeat(180, 40)
        while self.running:
            dt = self.clock.get_time() / 1000.0
            self._handle_events()
            self._sync_camera_height_overscan()
            # Sim first so cooldowns expire this frame; then arrows can step (matches time demo).
            # WASD pans after walk so edge-follow does not undo an active pan.
            self._step_sim()
            self._update_player_move_input(dt)
            self._update_camera_input(dt)
            self.camera.update(dt, self.world.cols, self.world.rows)
            self._update_status_timer()
            self._draw()
            self.clock.tick(FPS)
        pygame.quit()

    def _dialogs_block_world_input(self) -> bool:
        return (
            self.file_dialog.open
            or self.number_input.open
            or self.field_plan_dialog.open
            or self.building_inspect.open
            or self.villager_inspect.open
            or self.resource_inspect.open
            or self.resource_tracker.open
            or self.balance_dialog.open
            or self.habitat_inspect.open
            or self.player_inventory.open
            or self.assign_picker.open
            or self.management.open
            or self.villager_roster.open
        )

    def _update_player_move_input(self, dt: float) -> None:
        """Continuous arrow-key player movement (WASD is camera pan only)."""
        del dt
        if self.headless or self._dialogs_block_world_input():
            return
        mods = pygame.key.get_mods()
        if mods & (pygame.KMOD_META | pygame.KMOD_CTRL | pygame.KMOD_ALT):
            return
        keys = pygame.key.get_pressed()
        dx = int(keys[pygame.K_RIGHT]) - int(keys[pygame.K_LEFT])
        dy = int(keys[pygame.K_DOWN]) - int(keys[pygame.K_UP])
        if not dx and not dy:
            return
        # While WASD is panning, skip edge-follow so pan and walk can coexist.
        panning = bool(
            keys[pygame.K_w] or keys[pygame.K_a] or keys[pygame.K_s] or keys[pygame.K_d]
        )
        if dx and dy:
            if self.world.is_walkable(self.player.x + dx, self.player.y + dy):
                self._try_move(dx, dy, follow_camera=not panning)
            elif self.world.is_walkable(self.player.x + dx, self.player.y):
                self._try_move(dx, 0, follow_camera=not panning)
            elif self.world.is_walkable(self.player.x, self.player.y + dy):
                self._try_move(0, dy, follow_camera=not panning)
        else:
            self._try_move(dx, dy, follow_camera=not panning)

    def _update_camera_input(self, dt: float) -> None:
        """Continuous WASD camera panning (arrows move the player separately)."""
        if self.headless or self._dialogs_block_world_input():
            return
        mods = pygame.key.get_mods()
        if mods & (pygame.KMOD_META | pygame.KMOD_CTRL | pygame.KMOD_ALT):
            return
        keys = pygame.key.get_pressed()
        dx = float(keys[pygame.K_d]) - float(keys[pygame.K_a])
        dy = float(keys[pygame.K_s]) - float(keys[pygame.K_w])
        if dx or dy:
            self.camera.pan_continuous(dx, dy, dt, self.world.cols, self.world.rows)

    def reset(self) -> None:
        self.file_dialog.close()
        self.field_plan_dialog.close()
        self.building_inspect.close()
        self.villager_inspect.close()
        self.resource_inspect.close()
        self.resource_tracker.close()
        self.balance_dialog.close()
        self.habitat_inspect.close()
        self.player_inventory.close()
        self._clear_player_craft()
        self._clear_player_build()
        self.drawing = False
        self.draw_start = None
        self.draw_current = None
        self._mouse_down_cell = None
        self._placing_field = False
        self.overlay_mode = OverlayMode.NONE
        self.resource_history.reset()
        self.height_edit_mode = False
        self._height_painting = False
        self._height_paint_last = None
        self._food_rng.seed(99)
        self._start_fresh_game()
        self.height_sample = generate_height_sample(
            self.world.cols,
            self.world.rows,
            seed=self.world.seed,
            corners=self.world.height_corners,
        )
        self._invalidate_height_sample_cache()
        self.env_maps.resize(self.world.rows, self.world.cols)
        self._biodiversity_samples = self.env_maps.biodiversity_samples
        self._biodiversity_average = self.env_maps.biodiversity
        self._bake_erosion()
        self._sample_environment()
        self._set_status("World reset to valley start.")

    def _clear_selection(self) -> None:
        self.selected_building_id = None
        self.selected_villager_id = None
        self.selected_habitat_kind = None
        self.selected_habitat_id = None
        self.assign_workplace_mode = False
        self.area_draw_task: TaskType | None = None
        self.relocate_building_id = None
        self.selected_construction_id = None
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
        self.management.close()
        self.assign_picker.close()
        self.player_inventory.close()

    def record_produced(self, key: str, amount: int = 1) -> None:
        self.resource_history.record_produced(key, amount)
        if amount > 0:
            self._tick_village_stock = None
            self._bump_work_gen()

    def record_consumed(self, key: str, amount: int = 1) -> None:
        self.resource_history.record_consumed(key, amount)
        if amount > 0:
            self._tick_village_stock = None
            self._bump_work_gen()

    def _bump_work_gen(self) -> None:
        self._work_gen += 1

    def _tick_world_ecology(self, ticks: int, *, day: float) -> None:
        """Advance world growth and wake idle workers when a field changes phase."""
        if ticks <= 0:
            return
        woke = self.world.tick_bulk(
            ticks,
            decay_per_tick=self.balance.get_float("DISTURBANCE_DECAY_PER_TICK"),
            day=day,
        )
        if woke:
            self._bump_work_gen()

    def _decision_slot_ticks(self) -> int:
        """Max delay between IDLE replans (~4 slots per in-game day)."""
        return max(1, self.ticks_per_day // 4)

    def _park_idle_decision(self, villager: Villager) -> None:
        """Stop re-probing workplace work until the next day-slot or a stock/job change."""
        if not villager.inventory.is_empty:
            villager.decision_cooldown = 0
            return
        villager.decision_cooldown = self._decision_slot_ticks()
        villager.idle_work_gen = self._work_gen

    def _idle_decision_pending(self, villager: Villager) -> bool:
        return (
            not villager.job_change_deposit
            and villager.decision_cooldown > 0
            and villager.idle_work_gen == self._work_gen
            and not villager.needs_food()
            and villager.inventory.is_empty
        )

    def _villager_needs_ai_pass(self, villager: Villager) -> bool:
        """Whether this villager will run food/work selection this tick."""
        if villager.state == VillagerState.SLEEPING:
            return False
        if villager.job_change_deposit:
            return True
        if villager.needs_food() or villager.seeking_food:
            return True
        if self._idle_decision_pending(villager):
            return False
        if villager.move_cooldown > 0 and villager.work_cooldown > 0:
            return False
        return True

    def _reset_tick_claims(self) -> None:
        self._tick_claim_stations = set()
        self._tick_claim_cells = set()
        self._tick_claim_animals = set()
        self._tick_claim_colonies = set()
        self._tick_claim_fish = set()
        self._tick_claim_by_villager = {}
        self._tick_has_general_hauler = False
        self._tick_supply_demand = {}
        self._tick_farm_unsown = {}
        self._tick_fields_near = {}
        self._tick_farm_harvest = {}
        self._tick_farm_weed = {}
        self._tick_farm_sow = {}
        self._tick_village_stock = None

    def _rebuild_villager_claim_snapshot(self) -> None:
        # One claim snapshot per tick — avoids rebuilding station sets / scans per villager.
        self._tick_claim_stations = {b.center_cell() for b in self.buildings.values()}
        self._tick_claim_stations.add(self.world.home_pos)
        self._tick_claim_cells = set()
        self._tick_claim_animals = set()
        self._tick_claim_colonies = set()
        self._tick_claim_fish = set()
        self._tick_claim_by_villager = {}
        self._tick_has_general_hauler = False
        self._tick_supply_demand = {}
        self._tick_farm_unsown = {}
        self._tick_fields_near = {}
        self._tick_farm_harvest = {}
        self._tick_farm_weed = {}
        self._tick_farm_sow = {}
        self._tick_village_stock = None
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

    def _village_stock_amounts(self) -> dict[str, int]:
        """Storehouse + building storage totals (same scope as resource bar Total)."""
        cached = getattr(self, "_tick_village_stock", None)
        if cached is not None:
            return cached
        from recipes import PROCESSED_KEYS
        from resources import RESOURCE_KEYS, amounts_from_obj, merge_amounts

        parts = [amounts_from_obj(self.home_storage)]
        parts.extend(amounts_from_obj(b) for b in self.buildings.values())
        totals = merge_amounts(*parts)
        # Recipe outputs registered after RESOURCES init must still count.
        for key in PROCESSED_KEYS:
            if key in RESOURCE_KEYS:
                continue
            totals[key] = int(getattr(self.home_storage, key, 0)) + sum(
                int(getattr(b, key, 0)) for b in self.buildings.values()
            )
        self._tick_village_stock = totals
        return totals

    def _under_production_max(self, building: Building, key: str) -> bool:
        """True when village stock is still below this building's Max for ``key``."""
        cap = building.item_cap(key)
        if cap is None:
            return True
        return int(self._village_stock_amounts().get(key, 0)) < int(cap)

    def _craftable_recipe(self, building: Building, **kwargs):
        """``Building.craftable_recipe`` with village-wide Max stock enforcement."""
        kwargs.setdefault("stock_amounts", self._village_stock_amounts())
        return building.craftable_recipe(**kwargs)

    def _craftable_split_recipe(self, building: Building, **kwargs):
        """``Building.craftable_split_recipe`` with village-wide Max enforcement."""
        kwargs.setdefault("stock_amounts", self._village_stock_amounts())
        return building.craftable_split_recipe(**kwargs)

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
            elif (
                self.management.open
                # MOUSEBUTTONDOWN / MOUSEWHEEL are handled below so detail-pane
                # clicks and scroll can reach the embedded inspect first.
                and event.type
                not in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEWHEEL)
                and self.management.handle_event(event)
            ):
                self._apply_management_action()
                continue
            elif self.villager_roster.open and self.villager_roster.handle_event(event):
                self._apply_roster_action()
                continue
            elif event.type == pygame.KEYDOWN:
                # Cmd+S / Ctrl+S quick-save (before dialogs swallow the key).
                if event.key == pygame.K_s and (
                    event.mod & (pygame.KMOD_META | pygame.KMOD_CTRL)
                ):
                    if not self.file_dialog.open and not self.number_input.open:
                        self._quick_save()
                    continue
                if self.number_input.open:
                    self.number_input.handle_keydown(event)
                    self._finish_number_input_if_needed()
                    continue
                if self.file_dialog.open:
                    self.file_dialog.handle_keydown(event)
                    self._finish_file_dialog_if_needed()
                    continue
                if self.assign_picker.open and self.assign_picker.handle_keydown(event):
                    continue
                if self.player_inventory.open and self.player_inventory.handle_keydown(
                    event
                ):
                    continue
                if self.management.open and self.management.handle_keydown(event):
                    if not self.management.open:
                        self.selected_construction_id = None
                    continue
                if self.field_plan_dialog.open and self.field_plan_dialog.handle_keydown(
                    event
                ):
                    self._finish_field_plan_dialog()
                    continue
                if (
                    not self.management.open
                    and self.building_inspect.open
                    and self.building_inspect.handle_keydown(event)
                ):
                    continue
                if (
                    not self.management.open
                    and self.villager_inspect.open
                    and self.villager_inspect.handle_keydown(event)
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
                if self.number_input.open:
                    self.number_input.handle_click(event.pos)
                    self._finish_number_input_if_needed()
                    continue
                if self.file_dialog.open:
                    self.file_dialog.handle_click(event.pos)
                    self._finish_file_dialog_if_needed()
                    continue
                if self.assign_picker.open:
                    if self.assign_picker.contains(event.pos):
                        self.assign_picker.handle_mousedown(event.pos)
                        self._apply_assign_picker_action()
                    else:
                        # Click outside dismisses without assigning.
                        self.assign_picker.close()
                    continue
                if self.player_inventory.open:
                    if self.player_inventory.contains(event.pos):
                        self.player_inventory.handle_mousedown(event.pos, button=1)
                        self._apply_player_inventory_action()
                    continue
                if self.management.open and self.management.contains(event.pos):
                    # Forward to embedded inspect panes when clicking detail.
                    detail = self.management.detail_rect()
                    if detail.w > 0 and detail.collidepoint(event.pos):
                        if (
                            self.management.tab == MgmtTab.BUILDINGS
                            and self.field_plan_dialog.open
                            and self.management.selected_construction_id is None
                        ):
                            building = self._field_plan_building()
                            self.field_plan_dialog.handle_mousedown(
                                event.pos, building
                            )
                            self._apply_pending_field_plan()
                            self._finish_field_plan_dialog()
                        elif (
                            self.management.tab == MgmtTab.BUILDINGS
                            and self.building_inspect.open
                            and self.management.selected_construction_id is None
                        ):
                            self.building_inspect.handle_mousedown(event.pos)
                            self._apply_building_inspect_action()
                        elif (
                            self.management.tab == MgmtTab.PEOPLE
                            and self.villager_inspect.open
                        ):
                            self.villager_inspect.handle_mousedown(event.pos)
                            self._apply_villager_inspect_action()
                    if self.management.handle_mousedown(event.pos):
                        self._apply_management_action()
                    continue
                # Floating field editor: only consume clicks on the panel itself.
                if (
                    self.field_plan_dialog.open
                    and not self.field_plan_dialog.embedded
                    and self.field_plan_dialog.contains(event.pos)
                ):
                    building = self._field_plan_building()
                    self.field_plan_dialog.handle_mousedown(event.pos, building)
                    self._apply_pending_field_plan()
                    self._finish_field_plan_dialog()
                    continue
                if (
                    not self.management.open
                    and self.building_inspect.open
                    and self.building_inspect.contains(event.pos)
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
                if self._handle_player_hud_click(event.pos):
                    continue
                if self.ui.hit_action(event.pos) == "toggle_panel":
                    collapsed = toggle_panel_collapsed()
                    self._set_status(
                        "Sidebar hidden (Tab)." if collapsed else "Sidebar shown (Tab)."
                    )
                    continue
                mx, my = event.pos
                if mx >= map_view_width() and my >= MAP_OFFSET_Y:
                    if self._handle_panel_click(event.pos):
                        continue
                self._on_mouse_down(event.pos)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                if self.player_inventory.open and self.player_inventory.contains(
                    event.pos
                ):
                    self.player_inventory.handle_mousedown(event.pos, button=3)
                    self._apply_player_inventory_action()
                    continue
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if self.file_dialog.open:
                    continue
                if self.assign_picker.open and self.assign_picker._moving:
                    self.assign_picker.handle_mouseup(event.pos)
                    continue
                if self.player_inventory.open and (
                    self.player_inventory._moving or self.player_inventory._drag_active
                ):
                    self.player_inventory.handle_mouseup(event.pos)
                    self._apply_player_inventory_action()
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
                    self._apply_time_balance()
                    self._refresh_active_meal_buffs()
                    status = self.balance_dialog.pending_status
                    if status:
                        self._set_status(status)
                        self.balance_dialog.pending_status = None
                    continue
                if self.habitat_inspect.open and self.habitat_inspect._moving:
                    self.habitat_inspect.handle_mouseup(event.pos)
                    continue
                self._on_mouse_up(event.pos)
            elif event.type == pygame.MOUSEMOTION:
                if self.file_dialog.open:
                    continue
                if self.assign_picker.open and self.assign_picker._moving:
                    self.assign_picker.handle_mousemotion(event.pos)
                    continue
                if self.player_inventory.open and (
                    self.player_inventory._moving or self.player_inventory._drag_active
                ):
                    self.player_inventory.handle_mousemotion(event.pos)
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
                if self.player_inventory.open:
                    self.player_inventory.handle_mousemotion(event.pos)
                if self.resource_inspect.open:
                    self.resource_inspect.handle_mousemotion(event.pos)
                if self.resource_tracker.open:
                    self.resource_tracker.handle_mousemotion(event.pos)
                if self.drawing or self._height_painting:
                    self._on_mouse_drag(event.pos)
                elif self.habitat_view_mode:
                    self._update_habitat_hover(event.pos)
            elif event.type == pygame.MOUSEWHEEL:
                if self.file_dialog.open:
                    self.file_dialog.handle_mousewheel(event.y)
                    continue
                mouse = pygame.mouse.get_pos()
                if self.assign_picker.open and self.assign_picker.handle_mousewheel(
                    event.y, mouse
                ):
                    continue
                if self.management.open and self.management.contains(mouse):
                    detail = self.management.detail_rect()
                    if detail.w > 0 and detail.collidepoint(mouse):
                        if (
                            self.management.tab == MgmtTab.BUILDINGS
                            and self.field_plan_dialog.open
                            and self.management.selected_construction_id is None
                        ):
                            self.field_plan_dialog.handle_scroll(mouse, event.y)
                            continue
                        if (
                            self.management.tab == MgmtTab.BUILDINGS
                            and self.building_inspect.open
                            and self.management.selected_construction_id is None
                        ):
                            self.building_inspect.handle_mousewheel(event.y, mouse)
                        elif (
                            self.management.tab == MgmtTab.PEOPLE
                            and self.villager_inspect.open
                        ):
                            self.villager_inspect.handle_mousewheel(event.y, mouse)
                        continue
                    if self.management.handle_event(event):
                        continue
                    continue
                if self.field_plan_dialog.open and self.field_plan_dialog.contains(mouse):
                    self.field_plan_dialog.handle_scroll(mouse, event.y)
                    continue
                if self.building_inspect.open and self.building_inspect.contains(mouse):
                    self.building_inspect.handle_mousewheel(event.y, mouse)
                    continue
                if self.villager_inspect.open and self.villager_inspect.contains(mouse):
                    self.villager_inspect.handle_mousewheel(event.y, mouse)
                    continue
                if self.resource_inspect.open and self.resource_inspect.contains(mouse):
                    continue
                if self.resource_tracker.open and self.resource_tracker.handle_mousewheel(
                    event.y, mouse
                ):
                    continue
                if self.balance_dialog.open and self.balance_dialog.handle_mousewheel(
                    event.y
                ):
                    continue
                mx, my = mouse
                if mx >= map_view_width() and my >= MAP_OFFSET_Y:
                    self.ui.scroll(event.y * 28)
                else:
                    # Zoom camera over map (not over minimap, not over dialogs).
                    # Height-edit still zooms; brush/value use [ ] and +/-.
                    if my >= MAP_OFFSET_Y and not self._minimap_rect().collidepoint(
                        (mx, my)
                    ):
                        factor = (1 + ZOOM_STEP) if event.y > 0 else (1 - ZOOM_STEP)
                        self.camera.zoom_at(
                            factor, (mx, my), self.world.cols, self.world.rows
                        )

    def _finish_number_input_if_needed(self) -> None:
        if self.number_input.open:
            return
        if self.number_input.cancelled or self.number_input.result is None:
            return
        ctx = self.number_input.context or ""
        value = int(self.number_input.result)
        building = self._inspect_building()
        if building is None:
            return
        if ctx.startswith("market_reserve:"):
            if not building.is_market():
                return
            key = ctx.split(":", 1)[1]
            building.set_market_supply_min(key, value)
            self.building_inspect.selected_market_supply_key = key
            from resources import resource_label

            self._set_status(
                f"Market reserve {resource_label(key)}: {building.market_supply_min(key)}"
            )
            return
        if ctx.startswith("recipe_max:"):
            key = ctx.split(":", 1)[1]
            from resources import resource_label

            if key not in building.depositable_keys():
                return
            # 0 → unlimited (∞).
            building.set_item_cap(key, None if value <= 0 else value)
            cap = building.item_cap(key)
            tip = "∞" if cap is None else str(cap)
            self._set_status(f"{resource_label(key)} max: {tip}")
            return

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
                self._last_save_path = path
                self._loaded_save_name = path.name
                self._set_status(f"Saved to {path.name}")
            except Exception as exc:
                self._set_status(f"Save failed: {exc}")
        elif action == "load":
            try:
                load_from_path(self, path)
                self._last_save_path = path
                self._loaded_save_name = path.name
                self._sync_time_knobs_from_clock()
                self._invalidate_forage_index()
                self._minimap_terrain = None
                self._minimap_terrain_key = None
                self._set_status(f"Loaded {path.name} (speed x{self.sim_speed})")
            except Exception as exc:
                self._set_status(f"Load failed: {exc}")

    def _quick_save(self) -> None:
        """Overwrite the last save path, else newest save, else quicksave.json."""
        from pathlib import Path

        from save_load import save_to_path, saves_dir

        path = self._last_save_path
        if path is None or not Path(path).parent.is_dir():
            path = self._most_recent_save_path()
        if path is None:
            path = saves_dir() / "quicksave.json"
        else:
            path = Path(path)
        try:
            save_to_path(self, path)
            self._last_save_path = path
            self._loaded_save_name = path.name
            self._set_status(f"Quick-saved to {path.name}")
        except Exception as exc:
            self._set_status(f"Save failed: {exc}")

    def _on_keydown(self, key: int) -> None:
        if key == pygame.K_ESCAPE:
            if self.toolbar.file_menu_open:
                self.toolbar.file_menu_open = False
                return
            if self.assign_picker.open:
                self.assign_picker.close()
                return
            if self.player_inventory.open:
                self.player_inventory.close()
                return
            if self.management.open:
                self.management.close()
                self.building_inspect.close()
                self.villager_inspect.close()
                self.selected_construction_id = None
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
            if self.habitat_view_mode:
                self.habitat_view_mode = False
                self._habitat_hover = None
                self._set_status("Habitat view OFF.")
                return
            if self.height_edit_mode:
                self._toggle_height_edit()
                return
            if (
                self.selected_building_id is not None
                or self.selected_villager_id is not None
                or self.selected_habitat_id is not None
                or self.selected_construction_id is not None
                or self.place_kind is not None
                or self.assign_workplace_mode
                or self.relocate_building_id is not None
            ):
                self._clear_selection()
                self.place_kind = None
                self.relocate_building_id = None
                self._set_status("Selection cleared.")
            # Esc never quits the game.
        elif key == pygame.K_r:
            self.reset()
        elif key in (pygame.K_e, pygame.K_RETURN, pygame.K_KP_ENTER):
            self._interact_at_player()
        elif key == pygame.K_f:
            self._player_eat(manual=True)
        elif key == pygame.K_q:
            self._player_cycle_tool()
        elif key == pygame.K_i:
            self.player_inventory.toggle()
        elif key == pygame.K_v:
            self._open_management_people_list()
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
                self._set_status("Exit map edit (Y) before toggling habitat view (H).")
            else:
                self._toggle_habitat_view()
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
            self._set_overlay(OverlayMode.EROSION)
        elif key == pygame.K_0 and not self.height_edit_mode:
            self._set_overlay(OverlayMode.FERTILITY)
        elif key == pygame.K_F10:
            self._set_overlay(OverlayMode.SOIL_MOISTURE)
        elif key == pygame.K_F11:
            self._set_overlay(OverlayMode.TEMPERATURE)
        elif key in (pygame.K_LEFTBRACKET, pygame.K_COMMA):
            self._cycle_ticks_per_day(-1)
        elif key in (pygame.K_RIGHTBRACKET, pygame.K_PERIOD):
            self._cycle_ticks_per_day(1)
        elif key == pygame.K_F6:
            self._toggle_autotile_diagnostic()
        elif key == pygame.K_F8:
            self.bug_log.enabled = not self.bug_log.enabled
            state = "ON" if self.bug_log.enabled else "OFF"
            self._set_status(f"Bug log {state} (writes saves/bug_log.jsonl)")
        elif key == pygame.K_TAB:
            collapsed = toggle_panel_collapsed()
            self._set_status(
                "Sidebar hidden (Tab)." if collapsed else "Sidebar shown (Tab)."
            )
        # Arrows: continuous move via ``_update_player_move_input``.
        # WASD: continuous pan via ``_update_camera_input``.

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
        cache = getattr(self, "_center_cache", None)
        if cache is not None and x == int(x) and y == int(y):
            key = (int(x), int(y))
            hit = cache.get(key)
            if hit is not None:
                return hit
            cx, cy = self.camera.world_to_screen(float(x) + 0.5, float(y) + 0.5)
            dy = self._height_screen_lift(float(x) + 0.5, float(y) + 0.5)
            result = (cx, cy - int(round(dy)))
            cache[key] = result
            return result
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
        self._bake_erosion()

    def _bake_erosion(self) -> None:
        from soil import bake_erosion_grid

        self.env_maps.erosion = bake_erosion_grid(self.world)
        if getattr(self, "overlay_mode", OverlayMode.NONE) == OverlayMode.EROSION:
            self._refresh_indicators()

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
            self._invalidate_fishing_shore_cache()
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
        self._bake_erosion()

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
        # Must match terrain — dark olive here shows through warp seams as
        # fake "black biome borders" (especially along height breaks).
        ground.fill(COLOUR_GRASS)
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
        if self.resource_bar.layers_open and not self.resource_bar.contains(pos):
            self.resource_bar.layers_open = False
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
            previous_view = self.resource_bar.view_mode
            handled, layer = self.resource_bar.handle_click(pos, self.overlay_mode)
            if layer is not None:
                self._set_overlay(layer)
            elif handled and self.resource_bar.view_mode != previous_view:
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
        # Only start area drawing when the area tool is explicitly enabled.
        if (
            self.area_draw_task is not None
            and self.selected_building_id is not None
            and self.selected_building_id in self.buildings
        ):
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

        # Drag: task areas only while area tool is on.
        if (
            was_drawing
            and self.area_draw_task is not None
            and self.selected_building_id is not None
        ):
            building = self.buildings.get(self.selected_building_id)
            if building is None or building.kind not in AREA_DRAW_KINDS:
                return
            area = TaskArea(
                x0=start[0],
                y0=start[1],
                x1=end[0],
                y1=end[1],
                task_type=self.area_draw_task,
                building_id=building.id,
            )
            building.areas.append(area)
            self._set_status(
                f"{BUILDING_LABELS[building.kind]}: added {TASK_LABELS[area.task_type]}"
            )
            self._wake_building_workers(building.id)

    def _handle_click(self, cell: tuple[int, int]) -> None:
        x, y = cell

        # Relocate / build mode: click places a construction site (non-Field).
        if self.place_kind is not None:
            if self.relocate_building_id is not None:
                self._finalize_relocate(x, y)
                return
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

        if self.habitat_view_mode:
            hit = self._habitat_at_cell(x, y)
            if hit is not None:
                kind, hid = hit
                self._select_habitat(kind, hid)
                return

        villager = self._villager_at(x, y)
        if villager is not None:
            self._open_villager_inspect(villager, detail_only=True)
            return

        building = self._building_at(x, y)
        if building is not None:
            self._select_building(building, detail_only=True)
            return

        site = self._construction_at(x, y)
        if site is not None:
            self._select_construction(site, detail_only=True)
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

        # Single-cell task area only while area tool is on.
        if self.area_draw_task is not None and self.selected_building_id is not None:
            selected = self.buildings.get(self.selected_building_id)
            if selected is not None and selected.kind in AREA_DRAW_KINDS:
                area = TaskArea(
                    x0=x,
                    y0=y,
                    x1=x,
                    y1=y,
                    task_type=self.area_draw_task,
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
                    season_name = (
                        self.season.name if villager.seasonal_priorities else None
                    )
                    self._open_assign_workplace_picker(
                        villager, slot=slot, season_name=season_name
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
            self.management.open_window(MgmtTab.PEOPLE, people_mode="hire")
            self._mgmt_auto_select_people()
            return True
        if action == "open_villager_roster":
            self.management.open_people_list()
            self._mgmt_auto_select_people()
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
        if action == "toggle_panel":
            collapsed = toggle_panel_collapsed()
            self._set_status(
                "Sidebar hidden (Tab)." if collapsed else "Sidebar shown (Tab)."
            )
            return True

        hit = self.ui.hit_priority(pos)
        if hit is not None:
            vid, slot = hit
            villager = self._get_villager(vid)
            if villager is not None:
                season_name = (
                    self.season.name if villager.seasonal_priorities else None
                )
                self._open_assign_workplace_picker(
                    villager, slot=slot, season_name=season_name
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
            self._select_building(building, detail_only=True)
            return True
        if kind == "villager":
            villager = self._get_villager(item_id)
            if villager is None:
                return True
            self._open_villager_inspect(villager, detail_only=True)
            return True
        if kind == "construction":
            site = self.construction_sites.get(item_id)
            if site is not None:
                self._select_construction(site, detail_only=True)
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
        """Select a wildlife unit into the management Wildlife inspect pane.

        Floating habitat inspect is not used (avoids duplicate deer/pack popups).
        """
        if kind in (AnimalKind.WOLF, AnimalKind.FOX):
            pack = next(
                (p for p in self.wildlife.wolf_packs if p.id == patch_id), None
            )
            if pack is None or pack.size() <= 0:
                return
            self.selected_building_id = None
            self.selected_villager_id = None
            self.selected_habitat_kind = kind
            self.selected_habitat_id = patch_id
            self.building_inspect.close()
            self.villager_inspect.close()
            self.resource_inspect.close()
            self.field_plan_dialog.close()
            self.habitat_inspect.close()
            self.camera.center_on(pack.x, pack.y, self.world.cols, self.world.rows)
            self.management.select_habitat(kind, patch_id)
            return

        if kind in (AnimalKind.OWL, AnimalKind.HAWK):
            bird = next(
                (
                    a
                    for a in self.wildlife.animals
                    if a.id == patch_id and a.kind == kind
                ),
                None,
            )
            if bird is None:
                return
            self.selected_building_id = None
            self.selected_villager_id = None
            self.selected_habitat_kind = kind
            self.selected_habitat_id = patch_id
            self.building_inspect.close()
            self.villager_inspect.close()
            self.resource_inspect.close()
            self.field_plan_dialog.close()
            self.habitat_inspect.close()
            self.camera.center_on(bird.x, bird.y, self.world.cols, self.world.rows)
            self.management.select_habitat(kind, patch_id)
            return

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
        self.habitat_inspect.close()
        cx = sum(p[0] for p in breed) // len(breed)
        cy = sum(p[1] for p in breed) // len(breed)
        self.camera.center_on(cx, cy, self.world.cols, self.world.rows)
        self.management.select_habitat(kind, patch_id)

    def _toggle_habitat_view(self) -> None:
        self.habitat_view_mode = not self.habitat_view_mode
        if self.habitat_view_mode:
            self._update_habitat_hover(pygame.mouse.get_pos())
            self._set_status(
                "Habitat view ON. Hover wildlife grounds, click to inspect."
            )
        else:
            self._habitat_hover = None
            self._set_status("Habitat view OFF.")

    def _update_habitat_hover(self, pos: tuple[int, int]) -> None:
        if not self.habitat_view_mode:
            self._habitat_hover = None
            return
        mx, my = pos
        if mx >= map_view_width() or my < MAP_OFFSET_Y:
            self._habitat_hover = None
            return
        cell = self._map_cell_from_pos(pos)
        self._habitat_hover = self._habitat_at_cell(*cell) if cell is not None else None

    def _habitat_at_cell(self, x: int, y: int) -> tuple[AnimalKind, int] | None:
        if not self.world.in_bounds(x, y):
            return None

        def _hit_for_kind(kind: AnimalKind) -> tuple[AnimalKind, int] | None:
            if kind in (
                AnimalKind.WOLF,
                AnimalKind.FOX,
                AnimalKind.OWL,
                AnimalKind.HAWK,
            ):
                return None
            for hab in self.wildlife.breeding_grounds(kind):
                if (x, y) in self.wildlife._breeding_for(kind, hab):
                    return kind, hab.id
            return None

        preferred = self.selected_habitat_kind
        if preferred is not None:
            hit = _hit_for_kind(preferred)
            if hit is not None:
                return hit

        for kind in (
            AnimalKind.DEER,
            AnimalKind.BOAR,
            AnimalKind.BEE,
            AnimalKind.RABBIT,
            AnimalKind.FROG,
            AnimalKind.VOLE,
        ):
            if kind == preferred:
                continue
            hit = _hit_for_kind(kind)
            if hit is not None:
                return hit
        return None

    def _wolf_pack_by_id(self, pack_id: int):
        return next(
            (p for p in self.wildlife.wolf_packs if p.id == pack_id), None
        )

    def _habitat_inspect_view(self) -> HabitatInspectView | None:
        if self.selected_habitat_id is None or self.selected_habitat_kind is None:
            return None
        kind = self.selected_habitat_kind
        patch_id = self.selected_habitat_id
        if kind in (AnimalKind.WOLF, AnimalKind.FOX):
            return self._wolf_inspect_view(patch_id)
        if kind in (AnimalKind.OWL, AnimalKind.HAWK):
            return self._bird_inspect_view(kind, patch_id)
        hab = self.wildlife.habitat(patch_id, kind)
        if hab is None:
            return None
        from balance_config import active_balance
        from wildlife import COLONY_KINDS, OpenHabitat
        from world import wildlife_ecology_multiplier, effective_disturbance_at

        label = {
            AnimalKind.DEER: "Deer breeding ground",
            AnimalKind.BOAR: "Boar breeding ground",
            AnimalKind.BEE: "Bee nest",
            AnimalKind.RABBIT: "Rabbit warren",
            AnimalKind.FROG: "Frog pond",
            AnimalKind.VOLE: "Vole burrow",
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
        ecology = wildlife_ecology_multiplier(avg_dist)

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

        bal = active_balance()
        cap = self.wildlife._cap_for(kind, hab)
        if kind in COLONY_KINDS:
            from resource_balance import COLONY_LEVEL_MAX

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
            base_breed = bal.get_float("WILDLIFE_COLONY_GROW_CHANCE")
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
            base_breed = bal.get_float("WILDLIFE_BREED_CHANCE")
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

    def _wolf_inspect_view(self, pack_id: int) -> HabitatInspectView | None:
        pack = self._wolf_pack_by_id(pack_id)
        if pack is None:
            return None
        from balance_config import active_balance
        from world import effective_disturbance_at, wildlife_ecology_multiplier

        day = float(self.calendar_day)
        is_fox = pack.kind == AnimalKind.FOX
        unit = "foxes" if is_fox else "wolves"
        title_kind = "Fox" if is_fox else "Wolf"
        males = sum(1 for m in pack.members if m.sex.name == "MALE")
        females = pack.size() - males
        population = f"{pack.size()} {unit} · {males}♂ {females}♀"
        left = pack.food_days_left(day)
        if left > 0.05:
            food_status = f"{left:.1f} days of food left"
            until_day = int(day + left) % YEAR_DAYS
            fed_until = format_date(until_day)
        else:
            food_status = "Hungry — needs a kill"
            fed_until = "—"
        if pack.last_prey and pack.last_meal_day >= 0:
            last_meal = (
                f"{pack.last_prey} on {format_date(int(pack.last_meal_day))}"
            )
        else:
            last_meal = "None yet"

        if is_fox:
            prey_opts = ("rabbit", "frog", "vole")
        else:
            prey_opts = ("boar", "deer", "fox", "rabbit")
        can = [
            prey
            for prey in prey_opts
            if self.wildlife._wolf_can_hunt(pack, prey)
        ]
        if "rabbit" in can:
            inhabited_rabbits = any(
                c.can_harvest()
                for c in self.wildlife.colonies
                if c.kind == AnimalKind.RABBIT
            )
            if not inhabited_rabbits:
                can = [
                    ("rabbit (none inhabited)" if p == "rabbit" else p) for p in can
                ]
        hunt = ", ".join(can) if can else "too small to hunt"

        sample = [(pack.x, pack.y)] + [(m.x, m.y) for m in pack.members]
        dist_values = [
            effective_disturbance_at(self.world, x, y) for x, y in sample
        ]
        avg_dist = sum(dist_values) / max(1, len(dist_values))
        max_dist = max(dist_values) if dist_values else 0.0
        ecology = wildlife_ecology_multiplier(avg_dist)
        bio = self.env_maps.farm_biodiversity(sample)
        bal = active_balance()
        breed_key = "FOX_BREED_CHANCE" if is_fox else "WOLF_BREED_CHANCE"
        cap_key = "FOX_MAX_POPULATION" if is_fox else "WOLF_MAX_POPULATION"
        base_breed = bal.get_float(breed_key)
        pop_cap = max(1, bal.get_int(cap_key))
        landscape = self.wildlife.pack_count(pack.kind)
        pop_factor = min(1.0, landscape / float(pop_cap))
        health = max(
            0.0,
            min(
                100.0,
                100.0 * ecology * (0.45 + 0.55 * min(1.0, pack.size() / 4.0))
                * (0.7 + 0.3 * (1.0 if left > 0 else 0.5)),
            ),
        )
        breed_pct = (
            base_breed * ecology * 100.0 if pack.has_pair() else 0.0
        )
        benefits = [
            ("Can hunt", hunt),
            ("Location", f"({pack.x}, {pack.y})"),
            ("Biodiversity", f"{bio * 100:.0f}%"),
            (f"Landscape {unit}", f"{landscape}/{pop_cap}"),
            ("Disturbance", f"{avg_dist:.2f}"),
        ]
        return HabitatInspectView(
            title=f"{title_kind} pack #{pack.id}",
            subtitle=pack.activity or "Roaming",
            population=population,
            breeding_tiles=0,
            roam_tiles=0,
            avg_disturbance=avg_dist,
            max_disturbance=max_dist,
            ecology_mult=ecology,
            breed_chance_pct=breed_pct,
            health_pct=health,
            benefits=benefits,
            panel_kind="wolf",
            activity=pack.activity or "Roaming",
            last_meal=last_meal,
            food_status=food_status,
            fed_until=fed_until,
        )

    def _bird_inspect_view(
        self, kind: AnimalKind, bird_id: int
    ) -> HabitatInspectView | None:
        bird = next(
            (a for a in self.wildlife.animals if a.id == bird_id and a.kind == kind),
            None,
        )
        if bird is None:
            return None
        from world import effective_disturbance_at, wildlife_ecology_multiplier

        label = "Hawk" if kind == AnimalKind.HAWK else "Owl"
        prey = self.wildlife._bird_prey_kinds(kind)
        prey_txt = ", ".join(k.name.lower() for k in prey) if prey else "—"
        nest = bird.retreat_target
        nest_txt = f"({nest[0]}, {nest[1]})" if nest else "—"
        dist = effective_disturbance_at(self.world, bird.x, bird.y)
        ecology = wildlife_ecology_multiplier(dist)
        bio = self.env_maps.farm_biodiversity([(bird.x, bird.y)])
        activity = bird.activity or "Soaring"
        benefits = [
            ("Activity", activity),
            ("Preys on", prey_txt),
            ("Nest", nest_txt),
            ("Location", f"({bird.x}, {bird.y})"),
            ("Biodiversity", f"{bio * 100:.0f}%"),
            ("Disturbance", f"{dist:.2f}"),
        ]
        return HabitatInspectView(
            title=f"{label} #{bird.id}",
            subtitle=activity,
            population="1 solo bird",
            breeding_tiles=0,
            roam_tiles=0,
            avg_disturbance=dist,
            max_disturbance=dist,
            ecology_mult=ecology,
            breed_chance_pct=0.0,
            health_pct=max(0.0, min(100.0, 100.0 * ecology)),
            benefits=benefits,
            panel_kind="bird",
            activity=activity,
            last_meal="—",
            food_status="Hunts colonies on contact",
            fed_until="—",
        )

    def _assign_unassigned_to_selected_building(self) -> None:
        if self.selected_building_id is None:
            return
        building = self.buildings.get(self.selected_building_id)
        if building is None:
            return
        if building.kind == BuildingKind.WORKSTATION:
            self.management.open_window(MgmtTab.PEOPLE, people_mode="hire")
            self._mgmt_auto_select_people()
            return
        if is_housing_kind(building.kind):
            beds = housing_beds_of(building.kind)
            used = sum(
                1 for v in self.villagers if v.housed and v.housing_id == building.id
            )
            self.assign_picker.open_villagers(
                building.id,
                title=(
                    f"House in {BUILDING_LABELS[building.kind]} #{building.id} "
                    f"({used}/{beds} beds)"
                ),
            )
            self._set_status(
                f"Pick a villager to house in {BUILDING_LABELS[building.kind]} #{building.id}."
            )
            return
        if building.kind == BuildingKind.FIELD:
            self._set_status("Assign workers to a Farm — Fields only define crop areas.")
            return
        self.assign_picker.open_villagers(
            building.id,
            title=f"Assign to {BUILDING_LABELS[building.kind]} #{building.id}",
        )
        self._set_status(
            f"Pick a villager to assign to {BUILDING_LABELS[building.kind]} #{building.id}."
        )

    def _open_assign_workplace_picker(
        self,
        villager: Villager,
        *,
        slot: int = 0,
        season_name: str | None = None,
    ) -> None:
        self.assign_workplace_mode = False
        self.assign_workplace_picking = True
        self.assign_workplace_slot = slot
        self.assign_workplace_season = season_name
        label = f"Priority {slot + 1}"
        if season_name is not None:
            from seasons import SEASON_LABELS, Season

            try:
                label = f"{SEASON_LABELS[Season[season_name]]} {label}"
            except KeyError:
                label = f"{season_name} {label}"
        self.assign_picker.open_buildings(
            villager.id,
            title=f"{label} — {villager.name or f'Villager #{villager.id}'}",
        )
        self._set_status(
            f"Pick a workplace for {villager.name or f'Villager #{villager.id}'} ({label}). "
            "Storehouse = labourer."
        )

    def _open_assign_housing_picker(self, villager: Villager) -> None:
        """Open a picker of housing buildings for this villager."""
        self.assign_workplace_mode = False
        self.assign_workplace_slot = 0
        self.assign_workplace_season = None
        need = int(villager.housing_need)
        self.assign_picker.open_housing(
            villager.id,
            title=(
                f"House {villager.name or f'Villager #{villager.id}'} "
                f"(needs ≥{need})"
            ),
        )
        self._set_status(
            f"Pick housing for {villager.name or f'Villager #{villager.id}'} "
            f"(needs level ≥{need})."
        )

    def _apply_workplace_slot(
        self,
        villager: Villager,
        slot: int,
        building_id: int,
        *,
        season_name: str | None = None,
    ) -> None:
        building = self.buildings.get(building_id)
        if building is None:
            return
        from seasons import Season

        season = None
        if season_name is not None:
            try:
                season = Season[season_name]
            except KeyError:
                season = None
        label = BUILDING_LABELS[building.kind]
        is_storehouse = building.kind == BuildingKind.HOME
        if is_storehouse:
            villager.set_workplace_slot(
                slot,
                kind=WorkPriority.LABOURER,
                building_id=building_id,
                is_storehouse=True,
                season=season,
            )
            # P1 storehouse → home hauler when no workplace buildings remain.
            plan = villager.active_workplace_plan(
                season if villager.seasonal_priorities else None
            )
            has_workplace = any(
                s.kind == WorkPriority.WORKPLACE and s.building_id is not None
                for s in plan
            )
            if slot == 0 and not has_workplace and season_name is None:
                villager.building_id = None
                villager.assigned_to_home = True
                villager.clear_work_stickies()
                villager.state = VillagerState.IDLE
                villager.set_workplace_slot(
                    0,
                    kind=WorkPriority.LABOURER,
                    building_id=building_id,
                    is_storehouse=True,
                )
                # Keep P2/P3 from the plan; defaults only fill empties if needed.
                self._begin_job_change_deposit(villager)
                self._bump_work_gen()
                self._set_status(f"{villager.name} → Labourer (storehouse P1)")
                return
            self._begin_job_change_deposit(villager)
            tag = f"{season_name} P{slot + 1}" if season_name else f"P{slot + 1}"
            self._set_status(f"{villager.name} → Labourer ({tag})")
            return
        villager.set_workplace_slot(
            slot,
            kind=WorkPriority.WORKPLACE,
            building_id=building_id,
            season=season,
        )
        if slot == 0 and (
            season_name is None
            or (season is not None and self.season == season)
        ):
            self._set_primary_workplace(villager, building_id, slot=0)
            tag = f"{season_name} P1" if season_name else "P1"
            self._set_status(f"{villager.name} → {label} ({tag})")
        else:
            self._begin_job_change_deposit(villager)
            tag = f"{season_name} P{slot + 1}" if season_name else f"P{slot + 1}"
            self._set_status(f"{villager.name} → {label} ({tag})")
        self._wake_building_workers(building_id)

    def _set_primary_workplace(
        self, villager: Villager, building_id: int, *, slot: int = 0
    ) -> None:
        """Set P1 / building_id without clearing other slots or labourer ranks."""
        building = self.buildings.get(building_id)
        if building is None:
            return
        villager.ensure_workplace_plan()
        was_home = villager.assigned_to_home
        was_unassigned = (
            villager.building_id is None
            and not villager.assigned_to_home
            and not any(
                s.kind == WorkPriority.WORKPLACE and s.building_id is not None
                for s in villager.workplace_plan
            )
        )
        villager.set_workplace_slot(
            slot, kind=WorkPriority.WORKPLACE, building_id=building_id
        )
        villager.clear_work_stickies()
        villager.assigned_to_home = False
        villager.building_id = building_id
        villager.state = VillagerState.IDLE
        if was_unassigned or was_home:
            villager.set_default_priorities()
            # Keep the just-assigned workplace on P1 after defaults.
            villager.set_workplace_slot(
                slot, kind=WorkPriority.WORKPLACE, building_id=building_id
            )
        self._begin_job_change_deposit(villager)

    def _apply_assign_picker_action(self) -> None:
        action = self.assign_picker.take_action()
        if action is None:
            return
        if action.startswith("pick_villager:"):
            vid = int(action.split(":")[1])
            bid = self.assign_picker.target_building_id
            self.assign_picker.close()
            if bid is None:
                return
            building = self.buildings.get(bid)
            if building is None:
                return
            if building.kind == BuildingKind.HOME:
                self._assign_villager_to_home(vid)
            else:
                self._assign_villager_to_building(vid, bid)
            return
        if action.startswith("pick_building:"):
            bid = int(action.split(":")[1])
            vid = self.assign_picker.target_villager_id
            housing_pick = getattr(self.assign_picker, "housing_only", False)
            workplace_pick = bool(getattr(self, "assign_workplace_picking", False))
            slot = int(getattr(self, "assign_workplace_slot", 0) or 0)
            season_name = getattr(self, "assign_workplace_season", None)
            self.assign_picker.close()
            self.assign_workplace_picking = False
            if vid is None:
                return
            building = self.buildings.get(bid)
            if building is None:
                return
            villager = self._get_villager(vid)
            if villager is None:
                return
            if housing_pick or is_housing_kind(building.kind):
                self._assign_villager_to_housing(vid, bid)
                return
            if workplace_pick:
                self._apply_workplace_slot(
                    villager,
                    slot,
                    bid,
                    season_name=season_name,
                )
                self.assign_workplace_slot = 0
                self.assign_workplace_season = None
                return
            if building.kind == BuildingKind.HOME:
                self._assign_villager_to_home(vid)
            else:
                self._apply_workplace_slot(
                    villager,
                    self.assign_workplace_slot,
                    bid,
                    season_name=self.assign_workplace_season,
                )
            self.assign_workplace_slot = 0
            self.assign_workplace_season = None
            return

    def _roster_entries_for_villagers(self) -> list:
        foods = self._village_food_amounts()
        entries = []
        for v in self.villagers:
            if v.assigned_to_home:
                job = "hauler"
            elif v.building_id and v.building_id in self.buildings:
                job = BUILDING_LABELS[self.buildings[v.building_id].kind]
            else:
                job = "free"
            entries.append(
                entry_from_villager(
                    v,
                    job=job,
                    status=self._villager_activity_label(v),
                    job_colour=villager_job_colour(v, self.buildings),
                    requirement_rows=villager_requirement_rows(
                        v,
                        self.buildings,
                        foods,
                        housing_icon=self._villager_housing_icon(v),
                    ),
                )
            )
        return entries

    def _hire_roster_entries(self) -> list:
        foods = self._village_food_amounts()
        beds = free_housing_beds(self.buildings, self.villagers)
        lvl = max_housing_level(self.buildings)
        entries = []
        for c in self.hire_candidates:
            unmet = hire_unmet_requirements(
                housing_need=c.housing_need,
                required_foods=list(c.required_foods),
                foods=foods,
                free_beds=beds,
                max_housing_level=lvl,
            )
            entries.append(
                entry_from_candidate(
                    c,
                    season_pay=season_pay_coins(unmet),
                    requirement_rows=candidate_requirement_rows(
                        housing_need=c.housing_need,
                        required_foods=list(c.required_foods),
                        foods=foods,
                        free_beds=beds,
                        max_housing_level=lvl,
                    ),
                )
            )
        return entries

    def _apply_roster_action(self) -> None:
        action = self.villager_roster.take_action()
        if action is None:
            return
        if action.startswith("assign_pick:"):
            vid = int(action.split(":")[1])
            bid = self.villager_roster.assign_building_id
            if bid is None:
                return
            building = self.buildings.get(bid)
            if building is None:
                return
            if building.kind == BuildingKind.HOME:
                self._assign_villager_to_home(vid)
            else:
                self._assign_villager_to_building(vid, bid)
            self.villager_roster.close()
            return
        if action.startswith("select_villager:"):
            vid = int(action.split(":")[1])
            villager = self._get_villager(vid)
            if villager is not None:
                self._open_villager_inspect(villager)
            return
        if action.startswith("hire_cand:"):
            self._hire_candidate(int(action.split(":")[1]))
            return
        if action.startswith("pay_cand:"):
            self._hire_candidate(int(action.split(":")[1]), pay=True)
            return

    def _handle_people_list_action(self, action: str) -> None:
        if action.startswith("assign_pick:"):
            vid = int(action.split(":")[1])
            bid = self.management.assign_building_id
            if bid is None:
                bid = self.villager_roster.assign_building_id
            if bid is None:
                return
            building = self.buildings.get(bid)
            if building is None:
                return
            if building.kind == BuildingKind.HOME:
                self._assign_villager_to_home(vid)
            else:
                self._assign_villager_to_building(vid, bid)
            self.management.people_mode = "roster"
            self.management.assign_building_id = None
            self.villager_roster.close()
            return
        if action.startswith("select_villager:"):
            vid = int(action.split(":")[1])
            villager = self._get_villager(vid)
            if villager is not None:
                self._open_villager_inspect(villager)
            return
        if action.startswith("hire_cand:"):
            self._hire_candidate(int(action.split(":")[1]))
            return
        if action.startswith("pay_cand:"):
            self._hire_candidate(int(action.split(":")[1]), pay=True)
            return

    def _apply_management_action(self) -> None:
        action = self.management.take_action()
        if action is None:
            return
        if action == "mgmt_closed":
            self.building_inspect.close()
            self.villager_inspect.close()
            self.field_plan_dialog.close()
            self.selected_construction_id = None
            return
        if action == "tab_people":
            self.management.tab = MgmtTab.PEOPLE
            self.management._layout_panel()
            self.field_plan_dialog.close()
            self._mgmt_auto_select_people()
            return
        if action == "tab_buildings":
            self.management.tab = MgmtTab.BUILDINGS
            self.management._layout_panel()
            self._mgmt_auto_select_building()
            return
        if action == "tab_wildlife":
            self.management.tab = MgmtTab.WILDLIFE
            self.management._layout_panel()
            self.field_plan_dialog.close()
            self._mgmt_auto_select_wildlife()
            return
        if action == "toggle_detail":
            if self.management.show_detail and not self.management.show_list:
                return
            self.management.show_detail = not self.management.show_detail
            self.management._layout_panel()
            return
        if action == "toggle_list":
            if self.management.show_list and not self.management.show_detail:
                return
            self.management.show_list = not self.management.show_list
            self.management._layout_panel()
            return
        if action.startswith("select_villager:"):
            vid = int(action.split(":")[1])
            v = self._get_villager(vid)
            if v is not None:
                self._open_villager_inspect(v)
            return
        if action.startswith("select_building:"):
            bid = int(action.split(":")[1])
            b = self.buildings.get(bid)
            if b is not None:
                self._select_building(b)
            return
        if action.startswith("select_construction:"):
            sid = int(action.split(":")[1])
            site = self.construction_sites.get(sid)
            if site is not None:
                self._select_construction(site)
            return
        if action.startswith("select_habitat:"):
            raw = action.split(":", 1)[1]
            name, pid_s = raw.split(":")
            try:
                kind = AnimalKind[name]
            except KeyError:
                return
            pid = int(pid_s)
            self._select_habitat(kind, pid)
            self.management.select_habitat(kind, pid)
            return
        if (
            action.startswith("hire_cand:")
            or action.startswith("pay_cand:")
            or action.startswith("assign_pick:")
        ):
            self._handle_people_list_action(action)

    def _open_management_people_list(self) -> None:
        self.management.open_people_list()
        self._mgmt_auto_select_people()
        self._set_status("People — villager list (V).")

    def _mgmt_auto_select_people(self) -> None:
        if self.management.people_mode == "hire":
            if self.hire_candidates:
                # Keep list-focused; no villager inspect for travellers.
                self.management.selected_villager_id = None
                self.villager_inspect.close()
            return
        if self.villagers:
            self._open_villager_inspect(self.villagers[0])
        else:
            self.management.selected_villager_id = None
            self.villager_inspect.close()

    def _mgmt_auto_select_building(self) -> None:
        if self.construction_sites:
            site = next(iter(self.construction_sites.values()))
            self._select_construction(site)
            return
        for b in self.buildings.values():
            if b.kind != BuildingKind.FIELD:
                self._select_building(b)
                return
        self.management.selected_building_id = None
        self.management.selected_construction_id = None
        self.building_inspect.close()

    def _mgmt_auto_select_wildlife(self) -> None:
        rows = self._wildlife_management_rows()
        if not rows:
            self.management.selected_habitat = None
            return
        kind, patch_id, _title, _sub, _inhabited = rows[0]
        self._select_habitat(kind, patch_id)
        self.management.select_habitat(kind, patch_id)

    def _wildlife_management_rows(self) -> list[tuple]:
        """List rows: (kind, id, title, subtitle, inhabited)."""
        rows: list[tuple] = []
        for kind, label in (
            (AnimalKind.DEER, "Deer ground"),
            (AnimalKind.BOAR, "Boar ground"),
            (AnimalKind.BEE, "Bee nest"),
            (AnimalKind.RABBIT, "Rabbit warren"),
            (AnimalKind.FROG, "Frog pond"),
            (AnimalKind.VOLE, "Vole burrow"),
        ):
            for hab in self.wildlife.breeding_grounds(kind):
                hid = int(hab.id)
                if kind in (
                    AnimalKind.BEE,
                    AnimalKind.RABBIT,
                    AnimalKind.FROG,
                    AnimalKind.VOLE,
                ):
                    colony = self.wildlife._colony_on_habitat(kind, hid)
                    inhabited = colony is not None and colony.level >= 1
                    if colony is not None and inhabited:
                        subtitle = f"Level {colony.level}"
                    else:
                        subtitle = "Empty"
                else:
                    _present, _mig, total, _pairs = self.wildlife.patch_occupancy(
                        kind, hid
                    )
                    inhabited = total > 0
                    subtitle = "" if inhabited else "Empty"
                rows.append(
                    (kind, hid, f"{label} #{hid}", subtitle, inhabited)
                )
        for pack in self.wildlife.wolf_packs:
            is_fox = pack.kind == AnimalKind.FOX
            title = f"{'Fox' if is_fox else 'Wolf'} pack #{pack.id}"
            males = sum(1 for m in pack.members if m.sex.name == "MALE")
            females = pack.size() - males
            sex_bits = []
            if males:
                sex_bits.append(f"{males}♂")
            if females:
                sex_bits.append(f"{females}♀")
            subtitle = " · ".join(sex_bits) if sex_bits else "Empty"
            if pack.activity:
                subtitle = f"{subtitle} · {pack.activity}" if subtitle else pack.activity
            rows.append(
                (
                    pack.kind,
                    int(pack.id),
                    title,
                    subtitle,
                    pack.size() > 0,
                )
            )
        for bird in self.wildlife.animals:
            if bird.kind not in (AnimalKind.OWL, AnimalKind.HAWK):
                continue
            label = "Hawk" if bird.kind == AnimalKind.HAWK else "Owl"
            subtitle = bird.activity or "Soaring"
            rows.append(
                (
                    bird.kind,
                    int(bird.id),
                    f"{label} #{bird.id}",
                    subtitle,
                    True,
                )
            )
        return rows

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
        if is_housing_kind(building.kind):
            residents = [
                v for v in self.villagers if v.housed and v.housing_id == building.id
            ]
            if not residents:
                self._set_status(
                    f"No one lives in {BUILDING_LABELS[building.kind]} #{building.id}."
                )
                return
            resident = None
            if self.selected_villager_id is not None:
                resident = next(
                    (v for v in residents if v.id == self.selected_villager_id), None
                )
            if resident is None:
                resident = max(residents, key=lambda v: v.id)
            resident.housed = False
            resident.housing_id = None
            self._set_status(
                f"{resident.name or f'Villager {resident.id}'} left "
                f"{BUILDING_LABELS[building.kind]} #{building.id}."
            )
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
        if is_housing_kind(building.kind):
            self._assign_villager_to_housing(villager_id, building_id)
            return
        villager = self._get_villager(villager_id)
        if villager is None:
            return
        secondary = list(villager.workplace_slots[1:3])
        while len(secondary) < 2:
            secondary.append(None)
        was_home = villager.assigned_to_home
        was_unassigned = villager.building_id is None and not villager.assigned_to_home
        villager.clear_work_stickies()
        villager.assigned_to_home = False
        villager.building_id = building_id
        villager.ensure_workplace_slots()
        villager.workplace_slots[0] = building_id
        villager.workplace_slots[1] = secondary[0]
        villager.workplace_slots[2] = secondary[1]
        villager.state = VillagerState.IDLE
        if was_unassigned or was_home:
            villager.set_default_priorities()
        self._begin_job_change_deposit(villager)
        self.assign_workplace_mode = False
        self.selected_villager_id = None
        self.selected_building_id = building_id
        self._open_building_inspect(building)
        self._set_status(
            f"{villager.name} → {BUILDING_LABELS[building.kind]}"
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
        self._begin_job_change_deposit(villager)
        self._bump_work_gen()
        self.assign_workplace_mode = False
        self.selected_villager_id = None
        self.selected_building_id = None
        self._set_status(f"Villager {villager.id} → Home (hauler)")

    def _cycle_place_kind(self) -> None:
        order = visible_build_order(unlock_built_kinds(self.buildings))
        if self.place_kind not in order:
            self.place_kind = order[0] if order else None
        else:
            idx = order.index(self.place_kind)
            self.place_kind = order[(idx + 1) % len(order)]
        self._announce_place_kind()

    def _set_place_kind(self, kind: BuildingKind | None) -> None:
        self.extension_parent_id = None
        if kind is not None:
            allowed = unlock_built_kinds(self.buildings)
            from building_unlock import unlocked_kinds
            from extensions import is_extension_kind

            if not is_extension_kind(kind) and kind not in unlocked_kinds(allowed):
                self._set_status(f"{BUILDING_LABELS[kind]} is still locked.")
                return
        self.place_kind = kind
        self._announce_place_kind()

    def _begin_place_extension(self, parent: Building, ext_kind: BuildingKind) -> None:
        from extensions import (
            EXTENSION_PARENT,
            extension_or_site_claimed,
            is_extension_kind,
        )

        if not is_extension_kind(ext_kind):
            return
        if EXTENSION_PARENT.get(ext_kind) != parent.kind:
            self._set_status("That extension does not belong on this building.")
            return
        if extension_or_site_claimed(
            parent.id, ext_kind, self.buildings, self.construction_sites
        ):
            self._set_status(
                f"{BUILDING_LABELS[ext_kind]} already built or under construction here."
            )
            return
        self.relocate_building_id = None
        self.place_kind = ext_kind
        self.extension_parent_id = parent.id
        self.area_draw_task = None
        cost = unlock_building_cost(ext_kind)
        bits = ", ".join(cost.summary_bits()) if cost.summary_bits() else "free"
        self._set_status(
            f"Place {BUILDING_LABELS[ext_kind]} adjacent to "
            f"{BUILDING_LABELS[parent.kind]} #{parent.id} ({bits})."
        )

    def _announce_place_kind(self) -> None:
        if self.place_kind is None:
            self._set_status("Build mode off.")
            return
        cost = unlock_building_cost(self.place_kind)
        name = BUILDING_LABELS[self.place_kind]
        bits = cost.summary_bits()
        cost_txt = ", ".join(bits) if bits else "free"
        if self.place_kind == BuildingKind.FIELD:
            self._set_status(
                f"Build: {name} ({cost_txt}). Drag a rectangle on soil/grass to size the field."
            )
        else:
            self._set_status(
                f"Build: {name} ({cost_txt}). Click empty soil/grass to place a site."
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

    def _open_time_demo(self) -> None:
        """Open the ticks/cooldown demo in a second process."""
        import subprocess
        import sys
        from pathlib import Path

        script = Path(__file__).resolve().parent / "time_demo.py"
        subprocess.Popen(
            [sys.executable, str(script)],
            cwd=str(script.parent),
            start_new_session=True,
        )
        self._set_status("Opened time demo window.")

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

    def _playback_ticks(self) -> int:
        """Sim ticks ×1 burns each frame."""
        try:
            return max(1, self.balance.get_int("PLAYBACK_TICKS_AT_X1"))
        except Exception:
            from settings import PLAYBACK_TICKS_AT_X1

            return max(1, PLAYBACK_TICKS_AT_X1)

    def _satiation_decay(self) -> float:
        return satiation_decay_per_tick(self._playback_ticks())

    def _legacy_per_tick(self, amount: float) -> float:
        """Rates authored at 1 sim tick per frame."""
        return float(amount) / self._playback_ticks()

    def _sync_time_knobs_from_clock(self) -> None:
        """Keep Balance day-seconds honest after loading a save's tick count."""
        try:
            self.balance.set(
                "DAY_SECONDS_AT_X1",
                ticks_to_seconds(self.ticks_per_day, self._playback_ticks()),
            )
        except Exception:
            pass

    def _walk_seconds(self) -> float:
        try:
            return float(self.balance.get_float("WALK_SECONDS_AT_X1"))
        except Exception:
            from settings import WALK_SECONDS_AT_X1

            return WALK_SECONDS_AT_X1

    def _work_seconds(self) -> float:
        try:
            return float(self.balance.get_float("WORK_SECONDS_AT_X1"))
        except Exception:
            from settings import WORK_SECONDS_AT_X1

            return WORK_SECONDS_AT_X1

    def _walk_interval_ticks(self) -> int:
        return max(4, seconds_to_ticks(self._walk_seconds(), self._playback_ticks()))

    def _work_interval_ticks(self) -> int:
        return max(6, seconds_to_ticks(self._work_seconds(), self._playback_ticks()))

    def _step_sim(self) -> int:
        """Advance exactly speed × playback ticks this displayed frame."""
        n = 0 if self.sim_speed <= 0 else self.sim_speed * self._playback_ticks()
        if n:
            self._advance_sim_ticks(n, flush=False)
            if self.overlay_mode not in (
                OverlayMode.NONE,
                OverlayMode.BIODIVERSITY,
                OverlayMode.FLORAL_RESOURCES,
                OverlayMode.POLLINATION,
                OverlayMode.EROSION,
                OverlayMode.SOIL_MOISTURE,
                OverlayMode.TEMPERATURE,
                OverlayMode.FIELD_YIELD,
            ):
                self._refresh_indicators()
            try:
                if self.bug_log.enabled:
                    self.bug_log.scan(self)
            except Exception:
                pass
        return n

    def _apply_time_balance(self) -> None:
        """Keep calendar ticks in sync with day length in real seconds at ×1."""
        day_s = self.balance.get_float("DAY_SECONDS_AT_X1")
        target = seconds_to_ticks(day_s, self._playback_ticks())
        if target != self.ticks_per_day:
            self._set_ticks_per_day(target)

    def _combine_eater_meal_buffs(
        self, eater: object, food_keys: list[str]
    ) -> tuple[float, float, float]:
        walk, work, hunger = combine_meal_buffs(food_keys)
        if (
            isinstance(eater, Villager)
            and eater.favourite_is_junk
            and any(f in food_keys for f in eater.favourite_foods)
        ):
            work = round(work * 0.85, 1)
        return walk, work, hunger

    def _refresh_active_meal_buffs(self) -> None:
        """Re-scale current meals when File → Balance buff strength changes."""
        eaters: list[object] = [self.player, *self.villagers]
        for eater in eaters:
            keys = list(getattr(eater, "last_meal", None) or [])
            if not keys:
                continue
            walk, work, hunger = self._combine_eater_meal_buffs(eater, keys)
            apply = getattr(eater, "apply_food_buffs", None)
            if apply is not None:
                apply(walk, work, hunger)

    def _set_ticks_per_day(self, ticks: int) -> None:
        ticks = max(1, int(ticks))
        old = max(1, self.ticks_per_day)
        day_frac = 1.0 - (self.day_tick / old)
        self.ticks_per_day = set_ticks_per_day(ticks)
        self.day_tick = max(
            1, min(self.ticks_per_day, int(round(day_frac * self.ticks_per_day)))
        )
        pb = self._playback_ticks()
        secs = ticks_to_seconds(self.ticks_per_day, pb)
        walk = ticks_to_seconds(self._walk_interval_ticks(), pb)
        tiles = self.ticks_per_day / max(1, self._walk_interval_ticks())
        try:
            self.balance.set("DAY_SECONDS_AT_X1", secs)
        except Exception:
            pass
        self._set_status(
            f"Day {secs:g}s at ×1  ·  walk {walk:.2f}s/tile  ·  ~{tiles:.0f} tiles/day"
        )

    def _cycle_ticks_per_day(self, delta: int) -> None:
        current = ticks_to_seconds(self.ticks_per_day, self._playback_ticks())
        opts = DAY_SECONDS_OPTIONS
        idx = min(range(len(opts)), key=lambda i: abs(opts[i] - current))
        self.balance.set("DAY_SECONDS_AT_X1", opts[(idx + delta) % len(opts)])
        self._apply_time_balance()

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

    def _tick_food_spoilage(self, steps: int = 1) -> None:
        from food_spoilage import tick_storage_spoilage

        if steps <= 0:
            return
        day_frac = float(steps) / max(1, self.ticks_per_day)
        days = self.balance.get_float("FOOD_SPOILAGE_DAYS")
        tick_storage_spoilage(self.home_storage, day_frac, days)
        tick_storage_spoilage(self.player.inventory, day_frac, days)
        for villager in self.villagers:
            tick_storage_spoilage(villager.inventory, day_frac, days)
        for building in self.buildings.values():
            tick_storage_spoilage(building, day_frac, days)

    def _advance_day(self) -> None:
        prev = self.season
        self.calendar_day = (self.calendar_day + 1) % YEAR_DAYS
        self._bump_work_gen()
        self.resource_history.record_stock(self._village_stock_amounts())
        self.resource_history.advance_day()
        if self.season != prev:
            self._expire_unharvested_crops(prev)
            self._ripen_crops_for_harvest_season()
            from soil import reset_seasonal_weed_appearances

            reset_seasonal_weed_appearances(self.world)
            if self.season == Season.WINTER:
                self.world.clear_mushrooms()
            self.wildlife.on_season_change(self.world, self.season)
            self._apply_seasonal_hire_requirement_fees()
            self._check_seasonal_happiness_leaves()
            self._top_up_hire_candidates()
            self._refresh_market_demands()
            self._set_status(f"{format_date(self.calendar_day)} begins.")
            self._apply_path_fertility_drain()
        # Temperature follows the annual cosine each day; slower ecological
        # layers (habitats, forest floor, paths, urban) remain at ≤8×/year.
        sample_day = is_env_sample_day(self.calendar_day)
        if not sample_day:
            self.env_maps.temperature = temperature_grid(
                self.world, self.calendar_day
            )
            if self.overlay_mode == OverlayMode.TEMPERATURE:
                self._refresh_indicators()
        if sample_day:
            self._sample_environment()
            self._sync_habitat_selection()

    def _apply_path_fertility_drain(self) -> None:
        """Each season a path remains, drain fertility on soft land (floor 0.3)."""
        from soil import clamp01

        drain = 0.05
        floor = 0.3
        soft = (
            TerrainType.SOIL,
            TerrainType.GRASS,
            TerrainType.MEADOW,
            TerrainType.RIPARIAN,
        )
        for y in range(self.world.rows):
            for x in range(self.world.cols):
                cell = self.world.cells[y][x]
                if not cell.path_worn:
                    continue
                if cell.terrain not in soft:
                    continue
                cell.fertility = clamp01(max(floor, float(cell.fertility) - drain))

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
            fish_positions=(
                (f.x, f.y, f.kind.name.lower()) for f in self.fish.fish
            ),
            bee_positions=bee_pos,
            rabbit_positions=rabbit_pos,
            wolf_positions=self.wildlife.wolf_positions(),
            bee_nests=bee_nests,
            calendar_day=self.calendar_day,
        )
        self._biodiversity_samples = self.env_maps.biodiversity_samples
        self._biodiversity_average = self.env_maps.biodiversity
        self._update_field_crop_health()
        if self.overlay_mode in (
            OverlayMode.BIODIVERSITY,
            OverlayMode.FLORAL_RESOURCES,
            OverlayMode.POLLINATION,
            OverlayMode.SOIL_MOISTURE,
            OverlayMode.TEMPERATURE,
        ):
            self._refresh_indicators()

    def _update_field_crop_health(self) -> None:
        """Ratchet each Field's crop_health down toward the pest-control target.

        Health only decreases (sticky), at most CROP_HEALTH_MAX_DROP per sample,
        and never below CROP_HEALTH_MIN. Values crushed by the old harsh curve
        are lifted to the new floor.
        """
        hmin = crop_health_min()
        drop = crop_health_max_drop()
        for building in self.buildings.values():
            if building.kind != BuildingKind.FIELD:
                continue
            cells = building.plot_cells()
            if not cells:
                continue
            pc = self.env_maps.farm_pest_control(cells)
            boost = max(0.0, float(getattr(building, "pest_boost", 0.0)))
            # Treatments raise the health cap (pest no longer multiplies harvest).
            target = crop_health_cap_from_pest_control(pc + boost)
            current = float(getattr(building, "crop_health", 1.0))
            current = max(current, hmin)
            if current > target:
                current = max(target, current - drop)
            building.crop_health = max(hmin, min(1.0, current))

    def _field_crop_health(self, field: Building) -> float:
        hmin = crop_health_min()
        return max(hmin, min(1.0, float(getattr(field, "crop_health", 1.0))))

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
        self._apply_traffic_disturbance_at(x, y)

    def _apply_traffic_disturbance_at(self, x: int, y: int) -> None:
        """Fold current wear on (x, y) into the disturbance field."""
        cell = self.world.get_cell(x, y)
        if cell is None:
            return
        cap = max(1e-6, self.balance.get_float("PATH_TRAFFIC_OVERLAY_MAX"))
        dmax = self.balance.get_float("DISTURBANCE_MAX")
        wear_d = min(dmax, float(self._path_traffic.get((x, y), 0.0)) / cap)
        if cell.terrain == TerrainType.URBAN:
            cell.disturbance = max(
                self.balance.get_float("DISTURBANCE_URBAN_LEVEL"), wear_d
            )
        elif cell_has_path(cell):
            cell.disturbance = max(
                self.balance.get_float("DISTURBANCE_PATH_LEVEL"), wear_d
            )
        else:
            cell.disturbance = max(cell.disturbance, wear_d)

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
        self.world.sync_hardscape_disturbance(self._path_traffic)

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
            if cell.terrain == TerrainType.URBAN:
                cell.terrain = TerrainType.SOIL
                self.world.mark_terrain_dirty(x, y)
                changed = True
            if cell.terrain == TerrainType.PATH:
                cell.terrain = TerrainType.SOIL
                cell.path_worn = False
                self.world.mark_terrain_dirty(x, y)
                changed = True
            elif cell.path_worn:
                cell.path_worn = False
                self.world.mark_terrain_dirty(x, y)
                changed = True

        path_visual = False
        for y in range(self.world.rows):
            for x in range(self.world.cols):
                if (x, y) in field_cells:
                    continue
                cell = self.world.cells[y][x]
                if cell.terrain == TerrainType.URBAN and (x, y) not in urban_cells:
                    wear = float(self._path_traffic.get((x, y), 0.0))
                    cell.terrain = self._revert_hardscape_terrain(x, y)
                    worn = wear >= self.balance.get_float("PATH_TRAFFIC_THRESHOLD")
                    if cell.path_worn != worn:
                        path_visual = True
                    cell.path_worn = worn
                    self.world.mark_terrain_dirty(x, y)
                    changed = True

        if changed:
            self.world.terrain_revision += 1
            self._note_path_visual_change()
        elif path_visual:
            self._note_path_visual_change()

    def _update_path_terrain(self, *, decay_traffic: bool = False) -> None:
        """Toggle path overlay from villager wear; underlying terrain stays put."""
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
        visual_changed = False
        # Local dirty only — bumping terrain_revision here forced a full-map
        # terrain stitch + height rebake every in-game day.
        for (x, y), wear in list(self._path_traffic.items()):
            if (x, y) in urban_cells or (x, y) in field_cells:
                continue
            cell = self.world.get_cell(x, y)
            if cell is None or not hardscape_paintable(cell):
                continue
            if cell.terrain == TerrainType.URBAN:
                continue
            # Migrate legacy PATH terrain into overlay on the restored base.
            if cell.terrain == TerrainType.PATH:
                cell.terrain = self._revert_hardscape_terrain(x, y)
                cell.path_worn = True
                self.world.mark_terrain_dirty(x, y)
                visual_changed = True
            if wear >= threshold and not cell.path_worn:
                cell.path_worn = True
                self.world.mark_terrain_dirty(x, y)
                visual_changed = True

        for y in range(self.world.rows):
            for x in range(self.world.cols):
                if (x, y) in field_cells or (x, y) in urban_cells:
                    continue
                cell = self.world.cells[y][x]
                if cell.terrain == TerrainType.PATH:
                    cell.terrain = self._revert_hardscape_terrain(x, y)
                    wear = float(self._path_traffic.get((x, y), 0.0))
                    cell.path_worn = wear >= keep
                    self.world.mark_terrain_dirty(x, y)
                    visual_changed = True
                    continue
                if not cell.path_worn:
                    continue
                wear = float(self._path_traffic.get((x, y), 0.0))
                if wear < keep:
                    cell.path_worn = False
                    self.world.mark_terrain_dirty(x, y)
                    visual_changed = True

        if visual_changed:
            self._note_path_visual_change()

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
        """Fill missing derived layers and refresh instantaneous overlays."""
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
        # Older saves predate soil moisture; a zero grid is not a useful
        # fallback because it would show the whole landscape as bone dry.
        has_moisture = any(
            any(float(v) > 0.0 for v in row)
            for row in self.env_maps.soil_moisture
        )
        if not has_moisture:
            self.env_maps.soil_moisture = soil_moisture_grid(
                self.world, self.calendar_day
            )
        # Zero can be a legitimate temperature, so detect the pre-layer save
        # by checking whether every value retained the blank-map default.
        has_temperature = any(
            any(float(v) != 0.0 for v in row)
            for row in self.env_maps.temperature
        )
        if not has_temperature:
            self.env_maps.temperature = temperature_grid(
                self.world, self.calendar_day
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
            added = self._apply_field_pest_boost(
                field_b,
                float(self.balance.get_float("INSECT_REPELLANT_PEST_BOOST")),
            )
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
        """Farmed produce after pest × health × pollination × … (min 1)."""
        return self._farm_produce_breakdown_at(x, y).final_rounded

    def _farm_produce_breakdown_at(self, x: int, y: int):
        """Shared yield factors for harvest + UI (same product)."""
        from field_yield import calculate_tile_yield_breakdown
        from world import disturbance_activity_multiplier, effective_disturbance_at
        from soil import overlay_fertility, weed_yield_multiplier

        pest = self._farm_pest_control_at(x, y)
        poll = pollination_yield_multiplier(self._farm_pollination_at(x, y))
        field_b = self._field_building_at(x, y)
        health = self._field_crop_health(field_b) if field_b is not None else 1.0
        cell = self.world.get_cell(x, y)
        ecology = (
            disturbance_activity_multiplier(effective_disturbance_at(self.world, x, y))
            if cell is not None
            else 1.0
        )
        fert = overlay_fertility(cell) if cell is not None else 1.0
        weeds = float(getattr(cell, "weeds", 0.0)) if cell is not None else 0.0
        weed_mult = weed_yield_multiplier(weeds)
        return calculate_tile_yield_breakdown(
            base=farm_produce_yield(),
            pest_control=pest,
            crop_health=health,
            pollination=poll,
            ecology=ecology,
            fertility=fert,
            weed_penalty=weed_mult,
            weeds=weeds,
        )

    def _farm_produce_yield_budget(self) -> int:
        """Conservative cargo budget for next farm harvest (best-case mults)."""
        return max(
            1,
            int(
                round(
                    farm_produce_yield()
                    * self.balance.get_float("POLLINATION_YIELD_HIGH")
                )
            ),
        )

    def _sync_habitat_selection(self) -> None:
        """Drop habitat highlight if that breeding ground vanished on refresh."""
        if self.selected_habitat_id is None or self.selected_habitat_kind is None:
            return
        kind = self.selected_habitat_kind
        if kind in (AnimalKind.WOLF, AnimalKind.FOX):
            pack = self._wolf_pack_by_id(self.selected_habitat_id)
            if pack is None or pack.size() <= 0 or pack.kind != kind:
                self.selected_habitat_kind = None
                self.selected_habitat_id = None
                self.habitat_inspect.close()
            return
        if kind in (AnimalKind.OWL, AnimalKind.HAWK):
            bird = next(
                (
                    a
                    for a in self.wildlife.animals
                    if a.id == self.selected_habitat_id and a.kind == kind
                ),
                None,
            )
            if bird is None:
                self.selected_habitat_kind = None
                self.selected_habitat_id = None
                self.habitat_inspect.close()
            return
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
                cell.weeds = 0.0
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
            if self.balance_dialog.open:
                self.balance.set(
                    "DAY_SECONDS_AT_X1",
                    ticks_to_seconds(self.ticks_per_day, self._playback_ticks()),
                )
        elif action == "file_reset":
            self.reset()
        elif action == "file_time_demo":
            self._open_time_demo()
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
        self, building: Building, *, show_player: bool = False, detail_only: bool = False
    ) -> None:
        """Select a building and open management (or field plan)."""
        self.selected_building_id = building.id
        self.selected_villager_id = None
        self.selected_habitat_kind = None
        self.selected_habitat_id = None
        self.selected_construction_id = None
        self.assign_workplace_mode = False
        self.area_draw_task: TaskType | None = None
        if building.draw_task_type not in TASK_LABELS:
            building.draw_task_type = building.default_draw_task()
        if building.kind == BuildingKind.FIELD:
            self._open_field_plan(
                building, show_player=show_player, detail_only=detail_only
            )
            return
        self._open_building_inspect(
            building, show_player=show_player, detail_only=detail_only
        )

    def _select_construction(
        self, site: ConstructionSite, *, detail_only: bool = False
    ) -> None:
        self.selected_construction_id = site.id
        self.selected_building_id = None
        self.selected_villager_id = None
        self.selected_habitat_kind = None
        self.selected_habitat_id = None
        self.assign_workplace_mode = False
        self.area_draw_task: TaskType | None = None
        self.field_plan_dialog.close()
        self.building_inspect.close()
        self.villager_inspect.close()
        self.resource_inspect.close()
        self.management.select_construction(site.id, detail_only=detail_only)
        cx, cy = site.center_cell()
        self.camera.center_on(cx, cy, self.world.cols, self.world.rows)
        self._set_status(
            f"{site.phase_label()}: {BUILDING_LABELS[site.kind]}. "
            f"See materials & progress in Management."
        )

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

    def _open_field_plan(
        self,
        building: Building,
        *,
        show_player: bool = False,
        detail_only: bool = False,
    ) -> None:
        self.building_inspect.close()
        self.villager_inspect.close()
        self.resource_inspect.close()
        self.selected_building_id = building.id
        self.selected_construction_id = None
        self.field_plan_dialog.open_for(building, season=self.season)
        self.management.select_building(
            building.id, show_player=show_player, detail_only=detail_only
        )
        self._set_status(
            f"Plan Field #{building.id} ({building.plot_size_label()}). "
            f"Select season & crop, drag to plant."
        )

    def _open_building_inspect(
        self,
        building: Building,
        *,
        show_player: bool = False,
        detail_only: bool = False,
    ) -> None:
        self.field_plan_dialog.close()
        self.villager_inspect.close()
        self.resource_inspect.close()
        self.selected_building_id = building.id
        self.selected_construction_id = None
        self.building_inspect.open_for(building, show_player=show_player)
        if building.is_market():
            self._ensure_market_demand(building)
        self.management.select_building(
            building.id, show_player=show_player, detail_only=detail_only
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
        elif building.kind in AREA_DRAW_KINDS:
            self._set_status(
                f"Selected {BUILDING_LABELS[building.kind]}. "
                f"Set recipe priorities and use Draw areas in the inspect window."
            )
        else:
            self._set_status(
                f"Selected {BUILDING_LABELS[building.kind]}. "
                f"{WORK_MODE_LABELS[building.work_mode]}."
            )

    def _apply_building_inspect_action(self) -> None:
        action = self.building_inspect.take_action()
        if action is None:
            return
        if action == "hire_villager":
            self.management.open_window(MgmtTab.PEOPLE, people_mode="hire")
            return
        if action.startswith("hire_cand:"):
            self._hire_candidate(int(action.split(":")[1]))
            return
        if action.startswith("pay_cand:"):
            self._hire_candidate(int(action.split(":")[1]), pay=True)
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
        if action == "clear_plant_areas":
            self._clear_building_areas(
                {TaskType.PLANT_SAPLINGS, TaskType.FULL_MANAGE},
                label="plant",
            )
            return
        if action == "clear_collect_areas":
            self._clear_building_areas(
                {TaskType.CHOP_TREES, TaskType.FULL_MANAGE},
                label="collect",
            )
            return
        if action == "toggle_draw_plant":
            self._toggle_area_draw_task(TaskType.PLANT_SAPLINGS)
            return
        if action == "toggle_draw_collect":
            self._toggle_area_draw_task(TaskType.CHOP_TREES)
            return
        if action == "toggle_area_draw":
            building = self._inspect_building()
            if building is None or building.kind not in AREA_DRAW_KINDS:
                return
            self._toggle_area_draw_task(building.default_draw_task())
            return
        if action == "relocate_building":
            building = self._inspect_building()
            if building is None:
                return
            self._begin_relocate(building)
            return
        if action.startswith("place_extension:"):
            building = self._inspect_building()
            if building is None:
                return
            name = action.split(":", 1)[1]
            try:
                ext_kind = BuildingKind[name]
            except KeyError:
                return
            self._begin_place_extension(building, ext_kind)
            return
        if action == "assign_villager":
            # Prefer the inspected building so Assign from the floating window works.
            inspect_b = self._inspect_building()
            if inspect_b is not None:
                self.selected_building_id = inspect_b.id
            self._assign_unassigned_to_selected_building()
            return
        if action == "unassign_villager":
            inspect_b = self._inspect_building()
            if inspect_b is not None:
                self.selected_building_id = inspect_b.id
            self._unassign_worker_from_selected_building()
            return
        if action.startswith("craft_recipe:"):
            self._player_craft_recipe(action.split(":", 1)[1])
            return
        if action.startswith("toggle_recipe:"):
            building = self._inspect_building()
            if building is None or not (
                building.has_recipes()
                or building.addon_craft_recipes()
                or building.split_recipes()
                or building.plant_recipes()
            ):
                return
            name = action.split(":", 1)[1]
            enabled = building.toggle_recipe(name)
            from recipes import RECIPE_LABELS, recipe_label

            label = RECIPE_LABELS.get(name)
            if label is None:
                for recipe in (
                    *building.known_recipes(),
                    *building.addon_craft_recipes(),
                ):
                    if recipe.name == name:
                        label = recipe_label(recipe)
                        break
                else:
                    for recipe in building.split_recipes():
                        if recipe.name == name:
                            label = recipe_label(recipe)
                            break
                    else:
                        for recipe in building.plant_recipes():
                            if recipe.name == name:
                                label = recipe_label(recipe)
                                break
                        else:
                            label = name
            state = "on" if enabled else "off"
            self._wake_building_workers(building.id)
            # Enabled recipes default to unlimited (∞) production max.
            if enabled:
                out_key = None
                for group in (
                    building.known_recipes(),
                    building.split_recipes(),
                    building.plant_recipes(),
                ):
                    for recipe in group:
                        if recipe.name == name:
                            if recipe.outputs:
                                out_key = next(iter(recipe.outputs))
                            break
                    if out_key is not None:
                        break
                if out_key is not None and out_key in building.depositable_keys():
                    # Only seed ∞ when no cap was ever set for this output.
                    if out_key not in building.item_caps:
                        building.set_item_cap(out_key, None)
            self._set_status(f"{BUILDING_LABELS[building.kind]}: {label} {state}.")
            return
        if action.startswith("edit_recipe_max:"):
            building = self._inspect_building()
            if building is None:
                return
            key = action.split(":", 1)[1]
            from resources import resource_label

            if key not in building.depositable_keys():
                return
            cap = building.item_cap(key)
            self.number_input.begin(
                title=f"Max — {resource_label(key)} (0 = ∞)",
                initial=0 if cap is None else int(cap),
                context=f"recipe_max:{key}",
                max_value=building.max_item_cap(key),
                anchor=self.building_inspect.panel_rect(),
            )
            return
        if action.startswith("cycle_recipe_priority:"):
            building = self._inspect_building()
            if building is None or not (
                building.has_recipes()
                or building.split_recipes()
                or building.plant_recipes()
            ):
                return
            name = action.split(":", 1)[1]
            priority = building.cycle_recipe_priority(name)
            from recipes import RECIPE_LABELS, recipe_label

            label = RECIPE_LABELS.get(name)
            if label is None:
                for recipe in (
                    *building.known_recipes(),
                    *building.split_recipes(),
                    *building.plant_recipes(),
                ):
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
        if action == "toggle_market_demand":
            self.building_inspect.market_demand_expanded = (
                not self.building_inspect.market_demand_expanded
            )
            return
        if action == "toggle_market_supply":
            self.building_inspect.market_supply_expanded = (
                not self.building_inspect.market_supply_expanded
            )
            return
        if action.startswith("market_supply_group:"):
            group = action.split(":", 1)[1]
            if group in ("food", "wares", "agriculture"):
                self.building_inspect.market_supply_group = group
            return
        if action.startswith("recipe_category:"):
            raw = action.split(":", 1)[1]
            self.building_inspect.recipe_category_tab = raw or None
            # Reset scroll so switching tabs doesn't leave a blank view.
            self.building_inspect._scroll.pop("craft_recipes", None)
            return
        if action.startswith("toggle_market_supply_key:"):
            building = self._inspect_building()
            if building is None or not building.is_market():
                return
            key = action.split(":", 1)[1]
            from market_economy import market_supply_resource_keys

            if key not in market_supply_resource_keys():
                return
            enabled = not building.market_supply_enabled(key)
            building.set_market_supply_enabled(key, enabled)
            self.building_inspect.selected_market_supply_key = key
            from resources import resource_label

            state = "on" if enabled else "off"
            self._set_status(
                f"Market supply {resource_label(key)}: {state}"
                + (
                    f" (reserve {building.market_supply_min(key)})"
                    if enabled
                    else ""
                )
            )
            return
        if action.startswith("edit_market_reserve:"):
            building = self._inspect_building()
            if building is None or not building.is_market():
                return
            key = action.split(":", 1)[1]
            from market_economy import market_supply_resource_keys
            from resources import resource_label

            if key not in market_supply_resource_keys():
                return
            if not building.market_supply_enabled(key):
                building.set_market_supply_enabled(key, True)
            self.building_inspect.selected_market_supply_key = key
            self.number_input.begin(
                title=f"Reserve — {resource_label(key)}",
                initial=building.market_supply_min(key),
                context=f"market_reserve:{key}",
                anchor=self.building_inspect.panel_rect(),
            )
            return
        if action in (
            "market_supply_min_inc",
            "market_supply_min_dec",
            "market_supply_min_clear",
        ):
            # Legacy +/- kept for safety; prefer typed reserve editor.
            building = self._inspect_building()
            if building is None or not building.is_market():
                return
            key = self.building_inspect.selected_market_supply_key
            if key is None:
                return
            if not building.market_supply_enabled(key):
                building.set_market_supply_enabled(key, True)
            if action == "market_supply_min_inc":
                building.adjust_market_supply_min(key, 1)
            elif action == "market_supply_min_dec":
                building.adjust_market_supply_min(key, -1)
            else:
                building.set_market_supply_min(key, 0)
            from resources import resource_label

            self._set_status(
                f"Market reserve {resource_label(key)}: "
                f"{building.market_supply_min(key)}"
            )
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
        self,
        villager: Villager,
        *,
        show_player: bool = False,
        detail_only: bool = False,
    ) -> None:
        self.selected_villager_id = villager.id
        self.selected_building_id = None
        self.selected_construction_id = None
        self.selected_habitat_kind = None
        self.selected_habitat_id = None
        self.assign_workplace_mode = False
        self.field_plan_dialog.close()
        self.building_inspect.close()
        self.resource_inspect.close()
        self.camera.center_on(villager.x, villager.y, self.world.cols, self.world.rows)
        self.villager_inspect.open_for(villager, show_player=show_player)
        self.management.select_villager(
            villager.id, show_player=show_player, detail_only=detail_only
        )
        label = self._villager_assignment_label(villager)
        if show_player:
            self._set_status(
                f"Villager {villager.id} ({label}). Click items to transfer one."
            )
        else:
            self._set_status(
                f"Selected villager {villager.id} ({label}). "
                f"Set priorities & ration in Management."
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
        if action.startswith("tool_unequip"):
            key = None
            if ":" in action:
                key = action.split(":", 1)[1]
            self._villager_unequip_tool(key)
            return
        if action.startswith("clothing_equip:"):
            self._villager_equip_clothing(action.split(":", 1)[1])
            return
        if action.startswith("clothing_unequip:"):
            self._villager_unequip_clothing(action.split(":", 1)[1])
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
        if action.startswith("prio_kind:"):
            # Kind cycling removed — Workplace slots are building picks only.
            return
        if action.startswith("assign_workplace:"):
            parts = action.split(":")
            slot = int(parts[1])
            season_name = parts[2] if len(parts) > 2 else None
            self._open_assign_workplace_picker(
                villager, slot=slot, season_name=season_name
            )
            return
        if action == "assign_workplace":
            self._open_assign_workplace_picker(villager, slot=0)
            return
        if action == "assign_housing":
            self._open_assign_housing_picker(villager)
            return
        if action == "seasonal_toggle":
            villager.seasonal_priorities = not villager.seasonal_priorities
            if villager.seasonal_priorities:
                villager.ensure_season_workplace_plan(
                    copy_from=villager.ensure_workplace_plan()
                )
            state = "on" if villager.seasonal_priorities else "off"
            self._set_status(f"Villager {villager.id} seasonal workplace: {state}")
            return
        if action == "unassign":
            self._unassign_villager(villager)
            return

    def _villager_activity_label(self, villager: Villager) -> str:
        """Human-readable current work: what, from where, to where."""
        if villager.seeking_food:
            return "Seeking food"

        def _bname(bid: int | None) -> str:
            if bid is None:
                return "storehouse"
            building = self.buildings.get(bid)
            if building is None:
                return f"#{bid}"
            return f"{BUILDING_LABELS[building.kind]} #{building.id}"

        def _cargo_summary(inv) -> str:
            from resources import amounts_from_obj, resource_label

            amounts = amounts_from_obj(inv)
            parts = [
                f"{resource_label(k)}×{n}"
                for k, n in sorted(amounts.items(), key=lambda kv: (-kv[1], kv[0]))
                if n > 0
            ]
            if not parts:
                return "goods"
            if len(parts) <= 2:
                return ", ".join(parts)
            return f"{parts[0]}, {parts[1]}…"

        state = villager.state
        if state == VillagerState.HAULING:
            dest = _bname(villager.haul_building_id)
            if villager.inventory.is_empty:
                return f"Fetching supplies for {dest} from storehouse"
            what = _cargo_summary(villager.inventory)
            return f"Hauling {what} to {dest}"
        if state == VillagerState.DELIVERING:
            if villager.construction_id is not None:
                site = self.construction_sites.get(villager.construction_id)
                what = _cargo_summary(villager.inventory)
                if site is not None:
                    return f"Delivering {what} to construction ({BUILDING_LABELS.get(site.kind, site.kind)})"
                return f"Delivering {what} to construction site"
            if villager.haul_building_id is not None:
                what = _cargo_summary(villager.inventory)
                return f"Delivering {what} to {_bname(villager.haul_building_id)}"
            what = (
                _cargo_summary(villager.inventory)
                if not villager.inventory.is_empty
                else "goods"
            )
            home = self.world.home_pos
            building = (
                self.buildings.get(villager.building_id)
                if villager.building_id is not None
                else None
            )
            if (
                building is not None
                and villager.target is not None
                and villager.target == building.center_cell()
            ):
                return f"Delivering {what} to {_bname(villager.building_id)}"
            if villager.target == home or villager.target is None:
                return f"Delivering {what} to storehouse"
            return f"Delivering {what} to storehouse"
        if state == VillagerState.BUILDING:
            cid = villager.construction_id
            site = self.construction_sites.get(cid) if cid is not None else None
            if site is not None:
                return f"Building {BUILDING_LABELS.get(site.kind, site.kind)}"
            return "Building"
        if state == VillagerState.WORKING:
            bid = villager.building_id
            building = self.buildings.get(bid) if bid is not None else None
            recipe = getattr(villager, "craft_recipe_name", None)
            if building is not None and recipe:
                return f"Crafting {recipe} at {BUILDING_LABELS[building.kind]} #{building.id}"
            if building is not None:
                detail = self._workplace_work_detail(villager, building)
                if detail:
                    return detail
                return f"Working at {BUILDING_LABELS[building.kind]} #{building.id}"
            if villager.target is not None:
                return f"Working at ({villager.target[0]}, {villager.target[1]})"
            return "Working"
        if state == VillagerState.SLEEPING:
            return "Sleeping"
        if state == VillagerState.IDLE:
            if villager.assigned_to_home:
                return "Idle (labourer)"
            if villager.building_id is not None:
                return f"Idle at {_bname(villager.building_id)}"
            return "Idle"
        return state.name.replace("_", " ").title()

    def _workplace_work_detail(self, villager: Villager, building) -> str | None:
        """Extra WORKING detail when we can infer the task."""
        label = f"{BUILDING_LABELS[building.kind]} #{building.id}"
        if villager.hunt_animal_id is not None or villager.hunt_colony_id is not None:
            return f"Hunting for {label}"
        if villager.fish_target_id is not None:
            return f"Fishing for {label}"
        if villager.forage_colony_id is not None:
            return f"Foraging for {label}"
        if building.kind == BuildingKind.FARM and villager.target is not None:
            cell = self.world.get_cell(*villager.target)
            if cell is not None and getattr(cell, "crop_kind", None):
                crop = str(cell.crop_kind)
                if getattr(cell, "growth_ticks", 0) <= 0:
                    return f"Harvesting {crop} for {label}"
                return f"Tending {crop} at {label}"
            return f"Farming at {label}"
        if building.kind == BuildingKind.FARM:
            job = getattr(villager, "farm_job_kind", None)
            if job == "THRESH":
                return f"Threshing at {label}"
            if job == "SEED_FETCH":
                return f"Fetching seeds for {label}"
            if job == "SHEAF_FETCH":
                return f"Fetching sheaves for {label}"
            if job == "EXPORT":
                return f"Exporting from {label}"
            if job == "WEED":
                return f"Weeding at {label}"
            if job == "PLOUGH":
                return f"Ploughing at {label}"
            if job == "SOW":
                return f"Sowing at {label}"
            if job == "HARVEST":
                return f"Harvesting for {label}"
        return None

    def _villager_equip_tool(self) -> None:
        villager = self._get_villager(self.villager_inspect.villager_id or -1)
        if villager is None:
            return
        inv = villager.inventory
        if inv.tool_slots_free() <= 0:
            self._set_status("All tool slots full.")
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
                if key in inv.equipped_tools:
                    continue
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

    def _villager_unequip_tool(self, tool_key: str | None = None) -> None:
        villager = self._get_villager(self.villager_inspect.villager_id or -1)
        if villager is None:
            return
        inv = villager.inventory
        if not inv.equipped_tools:
            return
        from resources import resource_label

        key = tool_key if tool_key in inv.equipped_tools else inv.equipped_tools[-1]
        label = resource_label(key)
        if (
            self.villager_inspect.show_player
            and inv.transfer_equipped_tool_to(self.player.inventory, key)
        ):
            self._set_status(f"Gave {label} to player.")
            return
        if inv.unequip_tool(key):
            self._set_status(f"Villager {villager.id} unequipped {label}.")
            return
        self._set_status("Cargo full — cannot unequip tool.")

    def _villager_equip_clothing(self, slot: str) -> None:
        from entities import CLOTHING_ITEM_SLOT
        from resources import resource_label

        villager = self._get_villager(self.villager_inspect.villager_id or -1)
        if villager is None:
            return
        inv = villager.inventory
        for key, item_slot in CLOTHING_ITEM_SLOT.items():
            if item_slot != slot:
                continue
            if inv.equip_clothing(key):
                self._set_status(
                    f"Villager {villager.id} equipped {resource_label(key)}."
                )
                return
            if self.villager_inspect.show_player and int(
                getattr(self.player.inventory, key, 0)
            ) > 0:
                if not self.player.inventory.consume_item(key, 1):
                    continue
                if not inv.add_item(key, 1):
                    self.player.inventory.add_item(key, 1)
                    continue
                if inv.equip_clothing(key):
                    self._set_status(
                        f"Villager {villager.id} equipped {resource_label(key)}."
                    )
                    return
                inv.consume_item(key, 1)
                self.player.inventory.add_item(key, 1)
        self._set_status("No clothing for that slot.")

    def _villager_unequip_clothing(self, slot: str) -> None:
        from resources import resource_label

        villager = self._get_villager(self.villager_inspect.villager_id or -1)
        if villager is None:
            return
        inv = villager.inventory
        key = inv.equipped_in_slot(slot)
        if key is None:
            return
        label = resource_label(key)
        if not inv.unequip_clothing(slot):
            self._set_status("Cargo full — cannot unequip clothing.")
            return
        if (
            self.villager_inspect.show_player
            and self.player.inventory.can_add(1, key=key)
            and inv.consume_item(key, 1)
        ):
            self.player.inventory.add_item(key, 1)
            self._set_status(f"Gave {label} to player.")
            return
        self._set_status(f"Villager {villager.id} unequipped {label}.")

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
        self._begin_job_change_deposit(villager)
        self._bump_work_gen()
        self._set_status(f"Unassigned villager {villager.id}.")

    def _map_resource_at(
        self, x: int, y: int
    ) -> tuple[str, int, str, str] | None:
        """Return (title, quantity, unit, detail) for a harvestable map resource."""
        cell = self.world.get_cell(x, y)
        if cell is None:
            return None
        if cell.meat_deposit > 0:
            return ("Meat", cell.meat_deposit, "meat", "Ground deposit")
        if cell.hide_deposit > 0:
            return ("Hide", cell.hide_deposit, "hide", "Ground deposit")
        if cell.fur_deposit > 0:
            return ("Fur", cell.fur_deposit, "fur", "Ground deposit")
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
            from wild_species import is_harvestable, resolve_species

            species = resolve_species("REED", cell.crop_kind)
            label = species.label if species is not None else "Reeds"
            if not is_harvestable(species):
                return (label, 0, "", "")
            key = (species.resource_key if species is not None else "reeds") or "reeds"
            return (label, 1, key, "")
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
        self._apply_field_plan_ui_requests()
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

    def _apply_field_plan_ui_requests(self) -> None:
        """Overlay / yield-map actions queued by the field Status panel."""
        key = self.field_plan_dialog.take_pending_overlay()
        if key:
            try:
                mode = OverlayMode[key]
            except KeyError:
                mode = None
            if mode is not None:
                self._set_overlay(mode)
        if self.field_plan_dialog.take_yield_map_request():
            if self.overlay_mode == OverlayMode.FIELD_YIELD:
                self._set_overlay(OverlayMode.NONE)
            else:
                self._set_overlay(OverlayMode.FIELD_YIELD)

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
        left, top, right, bottom = building.plot_bounds()
        if self.selected_building_id == building_id:
            self.selected_building_id = None
        if self.field_plan_dialog.building_id == building_id:
            self.field_plan_dialog.close()
        if self.building_inspect.building_id == building_id:
            self.building_inspect.close()
        self._set_status(f"Deleted Field #{building_id}.")
        self._wake_all_farm_workers()
        self._refresh_indicators()
        nearest: Building | None = None
        best = FARM_FIELD_RADIUS + 1
        for farm in self.buildings.values():
            if farm.kind != BuildingKind.FARM:
                continue
            fcx, fcy = farm.center_cell()
            cx = min(max(fcx, left), right)
            cy = min(max(fcy, top), bottom)
            d = max(abs(cx - fcx), abs(cy - fcy))
            if d < best:
                nearest = farm
                best = d
        if nearest is not None and best <= FARM_FIELD_RADIUS:
            self._select_building(nearest)
        elif self.management.open:
            self._mgmt_auto_select_building()

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

    def _clear_building_areas(
        self, task_types: set[TaskType], *, label: str
    ) -> None:
        building = self._inspect_building()
        if building is None:
            if self.selected_building_id is not None:
                building = self.buildings.get(self.selected_building_id)
        if building is None:
            self._set_status("Select a building to clear its areas.")
            return
        before = len(building.areas)
        building.areas = [a for a in building.areas if a.task_type not in task_types]
        removed = before - len(building.areas)
        if removed <= 0:
            self._set_status(f"No {label} areas to clear.")
            return
        self._set_status(
            f"Cleared {removed} {label} area(s) for {BUILDING_LABELS[building.kind]}."
        )
        self._wake_building_workers(building.id)

    def _toggle_area_draw_task(self, task: TaskType) -> None:
        building = self._inspect_building()
        if building is None or building.kind not in AREA_DRAW_KINDS:
            return
        if self.area_draw_task == task:
            self.area_draw_task = None
            self._set_status("Area tool off.")
            return
        self.area_draw_task = task
        self.selected_building_id = building.id
        self._set_status(
            f"Area tool on — click or drag to paint "
            f"{TASK_LABELS.get(task, 'work')} zones. Toggle off when done."
        )

    def _try_move(self, dx: int, dy: int, *, follow_camera: bool = True) -> None:
        if self.sim_speed <= 0:
            self._set_status("Unpause (Space) to move.")
            return
        if self.player.move_cooldown > 0:
            return
        nx = self.player.x + dx
        ny = self.player.y + dy
        if not self.world.is_walkable(nx, ny):
            return
        note_cell_step(self.player, nx, ny)
        interval = self._player_move_interval()
        self.player.move_cooldown = interval
        arm_cell_step_visual(self.player, interval)
        self.player.energy = max(
            0.0,
            self.player.energy
            - ENERGY_MOVE_DRAIN * self._temp_energy_mult(self.player.inventory),
        )
        if follow_camera:
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

    def _player_interact_workplace(self, building: Building) -> Building:
        """Map an extension tile (barn / drying rack / …) to its parent workplace."""
        from extensions import is_extension_kind

        if not is_extension_kind(building.kind):
            return building
        parent_id = getattr(building, "parent_building_id", None)
        if parent_id is None:
            return building
        parent = self.buildings.get(parent_id)
        return parent if parent is not None else building

    def _player_at_craft_site(self, building: Building) -> bool:
        """True when the player stands on the workplace or a linked extension."""
        from extensions import is_extension_kind, linked_extensions

        px, py = self.player.x, self.player.y
        if building.contains_plot(px, py):
            return True
        # Standing on barn / drying rack / pantry counts for parent crafts.
        if not is_extension_kind(building.kind):
            for ext in linked_extensions(building, self.buildings):
                if ext.contains_plot(px, py):
                    return True
        else:
            # If somehow crafting against an extension id, accept its tile.
            parent = self._player_interact_workplace(building)
            if parent is not building and parent.contains_plot(px, py):
                return True
        return False

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

    def _building_icon_for_id(self, building_id: int | None) -> str | None:
        if building_id is None:
            return None
        building = self.buildings.get(building_id)
        if building is None:
            return None
        from management_window import _BUILD_ICON

        return _BUILD_ICON.get(building.kind, "forager")

    def _villager_housing_icon(self, villager: Villager) -> str:
        if villager.housed and villager.housing_id is not None:
            building = self.buildings.get(villager.housing_id)
            if building is not None:
                from management_window import _BUILD_ICON

                return _BUILD_ICON.get(building.kind, "tent")
        return "tent"

    def _villager_workplace_icon(self, villager: Villager) -> str | None:
        if villager.assigned_to_home:
            return "storehouse"
        if villager.building_id is not None:
            building = self.buildings.get(villager.building_id)
            if building is not None:
                from management_window import _BUILD_ICON

                return _BUILD_ICON.get(building.kind, "forager")
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
        return villager_job_colour(villager, self.buildings)

    def _wake_building_workers(self, building_id: int) -> None:
        for villager in self.villagers:
            if villager.building_id != building_id:
                continue
            villager.target = None
            villager.decision_cooldown = 0
            villager._path_cache = None  # type: ignore[attr-defined]
            villager._path_goal = None  # type: ignore[attr-defined]
            if villager.state == VillagerState.IDLE:
                villager.state = VillagerState.WORKING

    # ------------------------------------------------------------------
    # Player interaction
    # ------------------------------------------------------------------
    def _interact_at_player(self) -> None:
        if self.sim_speed <= 0:
            self._set_status("Unpause (Space) to act.")
            return
        x, y = self.player.x, self.player.y
        cell = self.world.get_cell(x, y)
        if cell is None:
            self._set_status("Invalid cell.")
            return

        if cell.feature == FeatureType.WORKSTATION:
            building = self._building_at(x, y)
            if building is not None:
                self._select_building(building, show_player=True, detail_only=True)
            return

        if cell.feature == FeatureType.HOME:
            building = self._building_at(x, y)
            if building is not None:
                self._select_building(building, show_player=True, detail_only=True)
            return

        # Construction pads / centre glyph — deposit & build before other interacts.
        site = self._construction_at(x, y)
        if site is not None and (
            cell.feature
            in (FeatureType.CONSTRUCTION_SITE, FeatureType.STRUCTURE_PAD)
            or site.contains_plot(x, y)
        ):
            self._player_work_construction(site)
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
            FeatureType.TAILOR,
            FeatureType.COBBLER,
            FeatureType.MARKET,
            FeatureType.WORKSTATION,
            FeatureType.STRUCTURE_PAD,
            FeatureType.BARN,
            FeatureType.PANTRY,
            FeatureType.DRYING_RACK,
        ):
            # Alchemist treatments on field tiles before opening the inspect panel.
            if (
                cell.feature in (FeatureType.FIELD, FeatureType.STRUCTURE_PAD)
                or self._field_building_at(x, y) is not None
            ) and self._try_apply_alchemist_treatment(x, y):
                return
            building = self._building_at(x, y)
            if building is not None:
                building = self._player_interact_workplace(building)
                self._select_building(building, show_player=True, detail_only=True)
            return

        if self.player.work_cooldown > 0:
            self._set_status("Still working…")
            return

        # Collect meat / fish on this cell first if present.
        if cell.meat_deposit > 0:
            if self._collect_meat(x, y, self.player.inventory, status=True):
                self._finish_player_work()
            return
        if cell.fish_deposit > 0:
            if self._collect_fish(x, y, self.player.inventory, status=True):
                self._finish_player_work()
            return

        # Honey from an adjacent bee nest (same as foragers).
        bee = self._adjacent_colony(x, y, kind=AnimalKind.BEE)
        if bee is not None and bee.can_harvest():
            self._player_harvest_honey(bee)
            return

        # Hunt adjacent deer/boar (spear or bow+arrows).
        prey = self._adjacent_animal(x, y)
        if prey is not None:
            self._player_hunt(prey)
            return

        # Rabbit warren: spear hunt within 1 tile.
        warren = self._adjacent_colony(x, y, kind=AnimalKind.RABBIT)
        if warren is not None and warren.can_harvest():
            self._player_hunt_warren(warren)
            return

        # Fish adjacent (on water within 1).
        catch = self._adjacent_fish(x, y)
        if catch is not None:
            if not fishing_allowed(self.calendar_day):
                self._set_status("Cannot fish right now.")
                return
            self._player_fish(catch)
            return

        # Talk / trade with a villager on this cell (or adjacent).
        villager = self._villager_at(x, y) or self._adjacent_villager(x, y)
        if villager is not None:
            self._open_villager_inspect(villager, show_player=True, detail_only=True)
            return

        if cell.feature == FeatureType.MUSHROOM:
            if self._collect_mushroom(x, y, self.player.inventory, status=True):
                self._finish_player_work()
            return

        if cell.feature == FeatureType.WOOD_BUSH:
            if self._collect_wood_bush(x, y, self.player.inventory, status=True):
                self._finish_player_work()
            return

        if cell.feature == FeatureType.BERRY_BUSH:
            if self._collect_berries(x, y, self.player.inventory, status=True):
                self._finish_player_work()
            return

        if cell.feature in (FeatureType.HERB, FeatureType.WILD_CROP, FeatureType.REED):
            if self._collect_herb(x, y, self.player.inventory, status=True):
                self._finish_player_work()
            return

        if cell.feature == FeatureType.CROP_HERB:
            weeds = float(getattr(cell, "weeds", 0.0))
            hoe = self.player.inventory.has_equipped_tool("hoe")
            if weeds > 0.05 and hoe:
                if self.world.clear_weeds(x, y):
                    self.world.apply_disturbance(x, y)
                    self._finish_player_work()
                    self._set_status("Pulled weeds.")
                return
            if self.world.crop_herb_ready(x, y):
                if self._harvest_farm_herb(x, y, self.player.inventory, status=True):
                    self._finish_player_work()
            elif self._try_apply_alchemist_treatment(x, y):
                return
            elif weeds > 0.05 and not hoe:
                self._set_status("Equip a hoe (Q) to pull weeds.")
            else:
                self._set_status("Crop still growing.")
            return

        if cell.feature == FeatureType.TREE:
            if not self.player.inventory.has_equipped_tool("axe"):
                self._set_status("Equip an axe (Q) to chop trees.")
                return
            if self._chop_tree(
                x, y, self.player.inventory, status=True, require_axe=True
            ):
                self._finish_player_work()
            return

        if cell.feature == FeatureType.ROCK:
            if self._collect_rock(x, y, self.player.inventory, status=True):
                self._finish_player_work()
            return

        if cell.feature == FeatureType.NONE and cell.terrain in PLANTABLE_LAND:
            if self._try_apply_alchemist_treatment(x, y):
                return
            if self.place_kind is not None:
                self._try_build(self.place_kind, x, y)
            else:
                if self._plant_here(x, y, self.player.inventory, status=True):
                    self._finish_player_work()
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

    def _building_cost(self, kind: BuildingKind):
        cost = unlock_building_cost(kind)
        return cost.wood, cost.rock, cost.logs, cost.hardwood, cost.task

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
            FeatureType.TAILOR,
            FeatureType.MARKET,
            FeatureType.CONSTRUCTION_SITE,
            FeatureType.STRUCTURE_PAD,
            FeatureType.TREE,
            FeatureType.BERRY_BUSH,
            FeatureType.ROCK,
        )
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                cell = self.world.get_cell(x, y)
                if cell is None or cell.terrain not in FIELDABLE_LAND:
                    self._set_status(
                        "Field must be entirely on soil, grass, meadow, or path."
                    )
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
        # Keep saplings and wild crops on the plot until plough:
        # plough destroys saplings; wild crops are harvested then cleared.
        # Only strip mushrooms / reeds that are not part of field work.
        clearable = {
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
                    cell.tree_species = None
                    cell.icon_variant = None
        cost_w, cost_r, cost_l, cost_h, _ = self._building_cost(BuildingKind.FIELD)
        site = ConstructionSite(
            id=self.next_construction_id,
            x=x0,
            y=y0,
            kind=BuildingKind.FIELD,
            need_wood=cost_w,
            need_rock=cost_r,
            need_logs=cost_l,
            need_hardwood=cost_h,
            plot_w=plot_w,
            plot_h=plot_h,
        )
        # No map feature marker — the plot is shown as an outline while building.
        self.next_construction_id += 1
        self.construction_sites[site.id] = site
        self._bump_work_gen()
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
        from extensions import (
            EXTENSION_PARENT,
            footprints_orthogonally_adjacent,
            is_extension_kind,
        )

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
        parent_id: int | None = None
        if is_extension_kind(kind):
            parent_id = self.extension_parent_id
            parent = self.buildings.get(parent_id) if parent_id is not None else None
            need_parent = EXTENSION_PARENT.get(kind)
            if parent is None or parent.kind != need_parent:
                self._set_status(
                    f"Select {BUILDING_LABELS.get(need_parent, 'parent')} "
                    f"and use Add {BUILDING_LABELS[kind]} first."
                )
                return False
            parent_cells = set(parent.plot_cells())
            if not footprints_orthogonally_adjacent(set(cells), parent_cells):
                self._set_status(
                    f"{BUILDING_LABELS[kind]} must touch "
                    f"{BUILDING_LABELS[parent.kind]} #{parent.id} (edge, not corner)."
                )
                return False
        reason = self._footprint_blocked(cells)
        if reason is not None:
            self._set_status(reason)
            return False
        cost_w, cost_r, cost_l, cost_h, _ = self._building_cost(kind)
        site = ConstructionSite(
            id=self.next_construction_id,
            x=ox,
            y=oy,
            kind=kind,
            need_wood=cost_w,
            need_rock=cost_r,
            need_logs=cost_l,
            need_hardwood=cost_h,
            plot_w=plot_w,
            plot_h=plot_h,
            parent_building_id=parent_id,
        )
        self.next_construction_id += 1
        self.construction_sites[site.id] = site
        self._bump_work_gen()
        self.world.claim_structure_footprint(
            ox, oy, plot_w, plot_h, FeatureType.CONSTRUCTION_SITE
        )
        self._refresh_hardscape_terrain()
        self.world.apply_disturbance(x, y)
        self._refresh_indicators()
        self.place_kind = None
        self.extension_parent_id = None
        bits = unlock_building_cost(kind).summary_bits()
        need_txt = ", ".join(bits) if bits else "no materials"
        self._set_status(
            f"Construction site: {BUILDING_LABELS[kind]} "
            f"(needs {need_txt}). Villagers will deliver & build."
        )
        return True

    def _building_blocks_relocate(self, building: Building) -> bool:
        return int(building.stored_total) + int(building.fuel_wood) > 0

    def _begin_relocate(self, building: Building) -> None:
        if self._building_blocks_relocate(building):
            self._set_status(
                f"Empty {BUILDING_LABELS[building.kind]} storage (and fuel) before relocating."
            )
            return
        self.relocate_building_id = building.id
        self.place_kind = building.kind
        self.area_draw_task: TaskType | None = None
        self._set_status(
            f"Relocate {BUILDING_LABELS[building.kind]} #{building.id}: "
            f"click a free spot for the new site."
        )

    def _finalize_relocate(self, x: int, y: int) -> None:
        bid = self.relocate_building_id
        building = self.buildings.get(bid) if bid is not None else None
        if building is None:
            self.relocate_building_id = None
            self.place_kind = None
            self._set_status("Relocate cancelled — building gone.")
            return
        if self._building_blocks_relocate(building):
            self._set_status("Empty storage before relocating.")
            return
        kind = building.kind
        if kind == BuildingKind.FIELD:
            plot_w, plot_h = max(1, building.plot_w), max(1, building.plot_h)
            ox, oy = x - plot_w // 2, y - plot_h // 2
        else:
            plot_w, plot_h = default_building_plot(kind)
            ox, oy = x - plot_w // 2, y - plot_h // 2
        cells = [
            (px, py)
            for py in range(oy, oy + plot_h)
            for px in range(ox, ox + plot_w)
        ]
        # Temporarily remove building so footprint check ignores it.
        del self.buildings[building.id]
        reason = self._footprint_blocked(cells)
        if reason is not None:
            self.buildings[building.id] = building
            self._set_status(reason)
            return

        cost_w, cost_r, cost_l, cost_h, _ = self._building_cost(kind)
        old_x, old_y = building.x, building.y
        old_w, old_h = max(1, building.plot_w), max(1, building.plot_h)

        # Unassign workers / housing refs.
        for v in self.villagers:
            if v.building_id == building.id:
                v.building_id = None
                v.state = VillagerState.IDLE
                v.target = None
            if building.kind == BuildingKind.HOME and v.assigned_to_home:
                v.assigned_to_home = False

        # Clear old map glyphs (building already removed from dict).
        self.world.clear_structure_footprint(old_x, old_y, old_w, old_h)

        decon_id = self.next_construction_id
        self.next_construction_id += 1
        build_id = self.next_construction_id
        self.next_construction_id += 1

        decon = ConstructionSite(
            id=decon_id,
            x=old_x,
            y=old_y,
            kind=kind,
            need_wood=cost_w,
            need_rock=cost_r,
            need_logs=cost_l,
            need_hardwood=cost_h,
            have_wood=cost_w,
            have_rock=cost_r,
            have_logs=cost_l,
            have_hardwood=cost_h,
            plot_w=old_w,
            plot_h=old_h,
            phase=SITE_PHASE_DECONSTRUCT,
            relocate_pair_id=build_id,
            relocate_from_building_id=bid,
            source_building_id=bid,
        )
        new_site = ConstructionSite(
            id=build_id,
            x=ox,
            y=oy,
            kind=kind,
            need_wood=cost_w,
            need_rock=cost_r,
            need_logs=cost_l,
            need_hardwood=cost_h,
            plot_w=plot_w,
            plot_h=plot_h,
            phase=SITE_PHASE_BUILD,
            relocate_pair_id=decon_id,
            relocate_from_building_id=bid,
        )
        self.construction_sites[decon.id] = decon
        self.construction_sites[new_site.id] = new_site
        self._bump_work_gen()
        self.world.claim_structure_footprint(
            old_x, old_y, old_w, old_h, FeatureType.CONSTRUCTION_SITE
        )
        self.world.claim_structure_footprint(
            ox, oy, plot_w, plot_h, FeatureType.CONSTRUCTION_SITE
        )
        self._refresh_hardscape_terrain()
        self._refresh_indicators()
        self.place_kind = None
        self.relocate_building_id = None
        self.selected_building_id = None
        self._select_construction(new_site)
        if is_housing_kind(kind):
            self._rehouse_villagers()
        self.toolbar.set_built_kinds(unlock_built_kinds(self.buildings))
        self._set_status(
            f"Relocating {BUILDING_LABELS[kind]}: deconstruct old site, "
            f"build at new site. Recovered materials feed the new site when deconstruction finishes."
        )

    def _complete_deconstruction(self, site: ConstructionSite) -> None:
        pair = (
            self.construction_sites.get(site.relocate_pair_id)
            if site.relocate_pair_id is not None
            else None
        )
        if pair is not None and not pair.is_deconstruct:
            pair.have_wood = min(pair.need_wood, pair.have_wood + site.have_wood)
            pair.have_rock = min(pair.need_rock, pair.have_rock + site.have_rock)
            pair.have_logs = min(pair.need_logs, pair.have_logs + site.have_logs)
            pair.have_hardwood = min(
                pair.need_hardwood, pair.have_hardwood + site.have_hardwood
            )
        else:
            # No pair — dump recovered mats into storehouse.
            self.home_storage.wood += site.have_wood
            self.home_storage.rock += site.have_rock
            self.home_storage.logs += site.have_logs
            self.home_storage.hardwood_logs += site.have_hardwood
        self.world.clear_structure_footprint(
            site.x, site.y, max(1, site.plot_w), max(1, site.plot_h)
        )
        sid = site.id
        del self.construction_sites[sid]
        self._bump_work_gen()
        for villager in self.villagers:
            if villager.construction_id == sid:
                villager.construction_id = None
                villager.state = VillagerState.IDLE
        self._refresh_hardscape_terrain()
        self._refresh_indicators()
        if self.selected_construction_id == sid:
            self.selected_construction_id = None
            if pair is not None:
                self._select_construction(pair)
        self._set_status(
            f"Deconstructed {BUILDING_LABELS[site.kind]} site. Materials transferred."
        )

    def _complete_construction(self, site: ConstructionSite) -> None:
        if site.is_deconstruct:
            self._complete_deconstruction(site)
            return
        cx, cy = site.center_cell()
        cell = self.world.get_cell(cx, cy)
        if cell is None:
            return
        _, _, _, _, default_task = self._building_cost(site.kind)
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
            parent_building_id=site.parent_building_id,
        )
        from entities import apply_building_storage
        from extensions import apply_extension_storage_boosts, is_extension_kind

        apply_building_storage(building)
        building.sync_draw_task_from_mode()
        if site.kind == BuildingKind.FORESTER:
            building.item_mins = dict(default_item_mins(BuildingKind.FORESTER))
        if site.kind == BuildingKind.MARKET:
            self._ensure_market_demand(building)
        self.next_building_id += 1
        self.buildings[building.id] = building
        if is_extension_kind(site.kind):
            apply_extension_storage_boosts(self.buildings)
            parent = (
                self.buildings.get(site.parent_building_id)
                if site.parent_building_id is not None
                else None
            )
            if parent is not None:
                parent.ensure_recipe_state()
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
        self._bump_work_gen()
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
            if site.kind == BuildingKind.WORKSTATION:
                self.world.workstation_pos = building.center_cell()
            if is_housing_kind(site.kind):
                self._rehouse_villagers()
            self._set_status(f"Finished {BUILDING_LABELS[site.kind]} #{building.id}.")
        self._refresh_hardscape_terrain()
        # Rebuild toolbar unlocks when a new building completes.
        self.toolbar.set_built_kinds(unlock_built_kinds(self.buildings))
        if self.selected_construction_id == site.id:
            self.selected_construction_id = None
            self._select_building(building)

    def _try_build(self, kind: BuildingKind, x: int, y: int) -> None:
        # Legacy Enter/E path also places a construction site.
        self._place_construction_site(kind, x, y)

    def _seed_map_communities(self) -> None:
        """Place hireable camps around the valley."""
        rng = random.Random(int(getattr(self.world, "seed", 0) or 0) ^ 0xC0A1)
        communities, candidates = generate_communities(
            self.world,
            rng,
            count=3,
            candidates_per=(2, 4),
            avoid=self.world.start_pos,
        )
        self.communities = communities
        self.hire_candidates = candidates
        self.next_community_id = max((c.id for c in communities), default=0) + 1
        self.next_hire_id = max((c.id for c in candidates), default=0) + 1
        for camp in communities:
            cell = self.world.get_cell(camp.x, camp.y)
            if cell is not None and cell.feature == FeatureType.NONE:
                cell.feature = FeatureType.COMMUNITY

    def _village_food_amounts(self) -> dict[str, int]:
        from resources import amounts_from_obj, merge_amounts

        parts = [amounts_from_obj(self.home_storage)]
        parts.extend(amounts_from_obj(b) for b in self.buildings.values())
        return merge_amounts(*parts)

    def _candidate_unmet_requirements(self, cand: HireCandidate) -> list[str]:
        return hire_unmet_requirements(
            housing_need=cand.housing_need,
            required_foods=list(cand.required_foods),
            foods=self._village_food_amounts(),
            free_beds=free_housing_beds(self.buildings, self.villagers),
            max_housing_level=max_housing_level(self.buildings),
        )

    def _hire_requirements_met(
        self, cand: HireCandidate, *, allow_pay: bool = False
    ) -> tuple[bool, str]:
        missing = self._candidate_unmet_requirements(cand)
        if not missing:
            return True, "ok"
        labels = [requirement_label(k) for k in missing]
        if allow_pay:
            pay = season_pay_coins(missing)
            return (
                True,
                f"unmet ({pay} coins/season): " + ", ".join(labels),
            )
        return False, "Needs " + ", ".join(labels) + "."

    def _refresh_villager_season_pay(self, villager: Villager) -> int:
        unmet = villager_unmet_requirements(
            villager, self.buildings, self._village_food_amounts()
        )
        due = season_pay_coins(unmet)
        villager.season_pay_due = due
        return due

    def _house_bed_count(self, house_id: int) -> tuple[int, int]:
        """Return (used, capacity) for a housing building."""
        house = self.buildings.get(house_id)
        if house is None or not is_housing_kind(house.kind):
            return 0, 0
        beds = housing_beds_of(house.kind)
        used = sum(
            1 for v in self.villagers if v.housed and v.housing_id == house_id
        )
        return used, beds

    def _assign_villager_to_housing(self, villager_id: int, house_id: int) -> None:
        """Move a villager into a specific house bed (manual housing assignment)."""
        villager = self._get_villager(villager_id)
        house = self.buildings.get(house_id)
        if villager is None or house is None or not is_housing_kind(house.kind):
            return
        used, beds = self._house_bed_count(house_id)
        already_here = villager.housed and villager.housing_id == house_id
        if not already_here and used >= beds:
            self._set_status(
                f"{BUILDING_LABELS[house.kind]} #{house_id} is full ({used}/{beds})."
            )
            return
        lvl = housing_level_of(house.kind)
        villager.housed = True
        villager.housing_id = house_id
        note = ""
        if lvl < int(villager.housing_need):
            note = f" (needs ≥{villager.housing_need}, house is lvl {lvl})"
        self.selected_building_id = house_id
        self._open_building_inspect(house)
        self._set_status(
            f"{villager.name or f'Villager {villager.id}'} housed in "
            f"{BUILDING_LABELS[house.kind]} #{house_id}{note}."
        )

    def _assign_housing(self, villager: Villager) -> bool:
        """Claim a free bed, preferring houses that meet the villager's need."""
        houses = sorted(
            (
                b
                for b in self.buildings.values()
                if is_housing_kind(b.kind)
                and housing_level_of(b.kind) >= villager.housing_need
            ),
            key=lambda b: (-housing_level_of(b.kind), b.id),
        )
        for house in houses:
            used, beds = self._house_bed_count(house.id)
            if villager.housed and villager.housing_id == house.id:
                used = max(0, used - 1)
            if used < beds:
                villager.housed = True
                villager.housing_id = house.id
                return True
        # Fallback: any free bed regardless of preference level.
        for house in sorted(
            (b for b in self.buildings.values() if is_housing_kind(b.kind)),
            key=lambda b: (-housing_level_of(b.kind), b.id),
        ):
            used, beds = self._house_bed_count(house.id)
            if villager.housed and villager.housing_id == house.id:
                used = max(0, used - 1)
            if used < beds:
                villager.housed = True
                villager.housing_id = house.id
                return True
        villager.housed = False
        villager.housing_id = None
        return False

    def _rehouse_villagers(self) -> None:
        """Keep valid placements; only auto-fill empty beds for the unhoused."""
        for v in self.villagers:
            if not v.housed or v.housing_id is None:
                v.housed = False
                v.housing_id = None
                continue
            house = self.buildings.get(v.housing_id)
            if house is None or not is_housing_kind(house.kind):
                v.housed = False
                v.housing_id = None
        for house in self.buildings.values():
            if not is_housing_kind(house.kind):
                continue
            beds = housing_beds_of(house.kind)
            residents = sorted(
                (
                    v
                    for v in self.villagers
                    if v.housed and v.housing_id == house.id
                ),
                key=lambda x: (-int(x.housing_need), x.id),
            )
            for extra in residents[beds:]:
                extra.housed = False
                extra.housing_id = None
        for v in sorted(self.villagers, key=lambda x: (-x.housing_need, x.id)):
            if not v.housed:
                self._assign_housing(v)

    def _hire_candidate(self, candidate_id: int, *, pay: bool = False) -> None:
        if not any(b.kind == BuildingKind.WORKSTATION for b in self.buildings.values()):
            self._set_status("Build a Hiring hall before hiring villagers.")
            return
        if len(self.villagers) >= MAX_VILLAGERS:
            self._set_status(f"Village full ({MAX_VILLAGERS} villagers).")
            return
        cand = next((c for c in self.hire_candidates if c.id == candidate_id), None)
        if cand is None:
            self._set_status("That traveller is no longer available.")
            return
        unmet = self._candidate_unmet_requirements(cand)
        ok, reason = self._hire_requirements_met(cand, allow_pay=pay)
        if not ok:
            due = season_pay_coins(unmet)
            self._set_status(
                f"Cannot hire {cand.name}: {reason} "
                f"Use Pay to hire anyway ({due} coins/season while unmet)."
            )
            return

        wx, wy = self.world.workstation_pos
        spawn = (wx, wy)
        for ny, nx in self.world.neighbourhood(wx, wy, radius=1):
            if (nx, ny) != (wx, wy) and self.world.is_walkable(nx, ny):
                spawn = (nx, ny)
                break
        villager = Villager(
            id=self.next_villager_id,
            x=spawn[0],
            y=spawn[1],
            name=cand.name,
            skills=dict(cand.skills),
            housing_need=cand.housing_need,
            required_foods=list(cand.required_foods),
            favourite_foods=list(cand.favourite_foods),
            favourite_is_junk=cand.favourite_is_junk,
            community_id=cand.community_id,
            virtues=list(cand.virtues),
            vices=list(cand.vices),
            portrait_seed=cand.portrait_seed,
            energy=cand.energy,
            happiness=cand.happiness,
            satiation=cand.satiation,
            template_id=str(getattr(cand, "template_id", "") or ""),
            tier=int(getattr(cand, "tier", 1) or 1),
        )
        villager.priorities = list(DEFAULT_PRIORITIES_UNASSIGNED)
        self.next_villager_id += 1
        self.villagers.append(villager)
        self.hire_candidates = [c for c in self.hire_candidates if c.id != cand.id]
        self._assign_housing(villager)
        self._refresh_villager_season_pay(villager)
        note = ""
        if unmet and pay:
            note = (
                f" Paying {villager.season_pay_due} coins/season "
                "until requirements are met."
            )
        house_note = "No bed yet. "
        if villager.housed and villager.housing_id is not None:
            house = self.buildings.get(villager.housing_id)
            if house is not None:
                house_note = (
                    f"Housed in {BUILDING_LABELS[house.kind]} #{house.id}. "
                )
            else:
                house_note = "Housed. "
        self._set_status(
            f"Hired {villager.name}. "
            + house_note
            + "Assign a workplace when ready."
            + note
        )

    def _hire_villager(self) -> None:
        """Hire the first candidate who meets requirements (legacy Hire button)."""
        for cand in list(self.hire_candidates):
            ok, _ = self._hire_requirements_met(cand)
            if ok:
                self._hire_candidate(cand.id)
                return
        if self.hire_candidates:
            self._set_status(
                "No travellers meet housing/food requirements. "
                "Use Pay to hire anyway (2 coins/season per unmet requirement)."
            )
        else:
            self._set_status("No hireable travellers left in nearby camps.")

    def _update_villager_wellbeing(self, villager: Villager, day_frac: float) -> None:
        """Energy drain, happiness drift, skill decay, leave check."""
        if villager.state == VillagerState.SLEEPING:
            house = self.buildings.get(villager.housing_id or -1)
            at_home = (
                house is not None
                and (villager.x, villager.y) == house.center_cell()
            )
            if at_home:
                villager.energy = min(
                    1.0, villager.energy + self._legacy_per_tick(ENERGY_SLEEP_GAIN)
                )
                if villager.energy >= 0.95:
                    villager.state = VillagerState.IDLE
                    villager.target = None
            elif house is not None:
                villager.target = house.center_cell()
            else:
                # No bed — cannot sleep; wake and keep draining slowly.
                villager.state = VillagerState.IDLE
                villager.target = None
        else:
            # Energy is spent only when work ticks fire (_spend_work_energy).
            if villager.energy <= ENERGY_SLEEP_THRESHOLD:
                house = self.buildings.get(villager.housing_id or -1)
                if villager.housed and house is not None:
                    villager.state = VillagerState.SLEEPING
                    villager.target = house.center_cell()
                    villager.seeking_food = False
                    return

        # Happiness from housing excess over need + recent meal variety.
        target = 0.45
        if villager.housed:
            house = self.buildings.get(villager.housing_id or -1)
            lvl = housing_level_of(house.kind) if house else 0
            excess = max(0, lvl - int(villager.housing_need))
            target += HAPPINESS_HOUSING_BONUS_PER_LEVEL * excess
        else:
            target -= HAPPINESS_MISSING_REQ_PENALTY
        target += HAPPINESS_FOOD_VARIETY_BONUS * min(3, len(villager.last_meal))
        foods = getattr(self, "_tick_village_food", None)
        if foods is None:
            foods = self._village_food_amounts()
        if not staple_food_available(foods, villager.required_foods):
            target -= HAPPINESS_MISSING_REQ_PENALTY
        if villager.favourite_foods and not any(
            f in villager.last_meal for f in villager.favourite_foods
        ):
            target -= HAPPINESS_FAVOURITE_MISS_PENALTY
        villager.happiness += (target - villager.happiness) * min(1.0, day_frac * 3.0)
        villager.happiness = max(0.0, min(1.0, villager.happiness))
        unmet = villager_unmet_requirements(villager, self.buildings, foods)
        villager.season_pay_due = season_pay_coins(unmet)

        tick_skill_decay(villager, day_frac)

        # Leaving is checked once per season (see _check_seasonal_happiness_leaves).

    def _villager_leaves(self, villager: Villager) -> None:
        """Unhappy villager returns to the traveller hire pool."""
        name = villager.name or f"Villager {villager.id}"
        camp = None
        if self.communities:
            if villager.community_id is not None:
                camp = next(
                    (c for c in self.communities if c.id == villager.community_id),
                    None,
                )
            if camp is None:
                camp = self.communities[0]
        cand_id = int(self.next_hire_id)
        self.next_hire_id = cand_id + 1
        if camp is not None:
            cand = HireCandidate(
                id=cand_id,
                name=name,
                community_id=camp.id,
                x=camp.x,
                y=camp.y,
                skills=dict(villager.skills),
                housing_need=int(villager.housing_need),
                required_foods=list(villager.required_foods),
                favourite_foods=list(villager.favourite_foods),
                favourite_is_junk=bool(villager.favourite_is_junk),
                virtues=list(getattr(villager, "virtues", []) or []),
                vices=list(getattr(villager, "vices", []) or []),
                energy=max(0.4, float(villager.energy)),
                satiation=max(0.4, float(villager.satiation)),
                happiness=max(0.2, float(villager.happiness)),
                portrait_seed=int(getattr(villager, "portrait_seed", 0) or 0),
                template_id=str(getattr(villager, "template_id", "") or ""),
                tier=int(getattr(villager, "tier", 1) or 1),
            )
            self.hire_candidates.append(cand)
        self.villagers = [v for v in self.villagers if v.id != villager.id]
        self._rehouse_villagers()
        self._set_status(f"{name} left the village and rejoined the travellers.")

    def _check_seasonal_happiness_leaves(self) -> None:
        """Leave after 2 consecutive seasons below 10% happiness."""
        leavers = []
        for villager in self.villagers:
            if villager.happiness < HAPPINESS_LEAVE_THRESHOLD:
                villager.low_happiness_seasons = (
                    int(getattr(villager, "low_happiness_seasons", 0) or 0) + 1
                )
            else:
                villager.low_happiness_seasons = 0
            if villager.low_happiness_seasons >= HAPPINESS_LEAVE_SEASONS:
                leavers.append(villager)
        for villager in leavers:
            self._villager_leaves(villager)

    def _top_up_hire_candidates(self) -> None:
        """Keep the traveller list topped up to MAX_TRAVELLERS each season."""
        if not self.communities:
            return
        need = MAX_TRAVELLERS - len(self.hire_candidates)
        if need <= 0:
            return
        used = {
            str(c.template_id)
            for c in self.hire_candidates
            if getattr(c, "template_id", "")
        }
        used.update(
            str(getattr(v, "template_id", "") or "")
            for v in self.villagers
            if getattr(v, "template_id", "")
        )
        used.discard("")
        rng = random.Random(
            int(getattr(self.world, "seed", 0) or 0)
            ^ (int(self.calendar_day) * 7919)
            ^ (self.next_hire_id * 97)
        )
        new_cands, self.next_hire_id = spawn_travellers_from_templates(
            self.communities,
            rng,
            count=need,
            next_id=int(self.next_hire_id),
            exclude_template_ids=used,
        )
        if new_cands:
            self.hire_candidates.extend(new_cands)
            self._set_status(
                f"{len(new_cands)} travellers arrived nearby "
                f"({len(self.hire_candidates)}/{MAX_TRAVELLERS})."
            )

    def _record_seasonal_happiness_events(self, villager: Villager, foods: dict[str, int]) -> None:
        """Snapshot seasonal happiness contributions as Events."""
        from resources import resource_icon

        day = int(self.calendar_day)
        variety = min(3, len(villager.last_meal))
        if variety > 0:
            icon = resource_icon(villager.last_meal[0]) if villager.last_meal else "meat"
            push_happiness_event(
                villager,
                icon=icon,
                label=f"Food variety (+{variety})",
                delta=variety,
                day=day,
            )
        if villager.housed:
            house = self.buildings.get(villager.housing_id or -1)
            lvl = housing_level_of(house.kind) if house else 0
            excess = max(0, lvl - int(villager.housing_need))
            if excess > 0:
                from management_window import _BUILD_ICON

                icon = (
                    _BUILD_ICON.get(house.kind, "tent") if house is not None else "tent"
                )
                push_happiness_event(
                    villager,
                    icon=icon,
                    label=f"Housing over need (+{excess})",
                    delta=excess,
                    day=day,
                )
        else:
            push_happiness_event(
                villager,
                icon="tent",
                label="No housing (−4)",
                delta=-4,
                day=day,
            )
            apply_happiness_points(villager, -4)

    def _apply_seasonal_hire_requirement_fees(self) -> None:
        """Charge 2 coins/season per unmet hire requirement from regional wealth."""
        foods = self._village_food_amounts()
        fee_total = 0
        unpaid = 0
        for villager in self.villagers:
            self._record_seasonal_happiness_events(villager, foods)
            unmet = villager_unmet_requirements(villager, self.buildings, foods)
            due = season_pay_coins(unmet)
            villager.season_pay_due = due
            if due <= 0:
                villager.seasons_without_reqs = 0
                continue
            villager.seasons_without_reqs += 1
            wealth = int(self.regional_wealth)
            if wealth >= due:
                self.regional_wealth = wealth - due
                villager.coins_paid_total = int(villager.coins_paid_total) + due
                fee_total += due
                push_happiness_event(
                    villager,
                    icon="coins",
                    label=f"Paid {due} coins (unmet reqs)",
                    delta=0,
                    day=int(self.calendar_day),
                )
            else:
                unpaid += 1
                points = -8
                apply_happiness_points(villager, points)
                push_happiness_event(
                    villager,
                    icon="coins",
                    label=f"Unpaid upkeep ({due} coins)",
                    delta=points,
                    day=int(self.calendar_day),
                )
        if fee_total > 0:
            msg = f"Paid {fee_total} coins in seasonal villager upkeep."
            if unpaid:
                msg += f" {unpaid} unpaid (happiness hit)."
            self._set_status(msg)
        elif unpaid:
            self._set_status(
                f"{unpaid} villagers unpaid for unmet requirements (happiness hit)."
            )

    def _spend_work_energy(self, villager: Villager) -> None:
        """Spend energy on an actual work tick (extract / process / build)."""
        drain = ENERGY_WORK_DRAIN * self._temp_energy_mult(villager.inventory)
        villager.energy = max(0.0, villager.energy - drain)

    def _gain_job_skill(self, villager: Villager, kind_name: str) -> None:
        skill, _ = skill_for_building(kind_name)
        gain_skill(villager, skill)

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
            from wild_species import resolve_species

            species = resolve_species("REED", cell.crop_kind)
            produce_key = (
                species.resource_key if species is not None else "reeds"
            ) or "reeds"
            need = int(species.yield_amount) if species is not None else REED_YIELD
            if need <= 0:
                if status:
                    self._set_status("Nothing to harvest here.")
                return False
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
        from wild_species import WILD_BY_KEY

        wild = WILD_BY_KEY.get(crop_key)
        if wild is not None and wild.feature == "REED":
            amount = max(0, int(wild.yield_amount))
            if amount <= 0:
                return True
            inventory.add_item(wild.resource_key or "reeds", amount)
            self.record_produced(wild.resource_key or "reeds", amount)
            self.world.apply_extraction_disturbance(x, y)
            self._refresh_indicators()
            if status:
                label = wild.label.lower()
                self._set_status(
                    f"Collected {amount} {label}{'' if amount == 1 else 's'}."
                )
            return True
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
        # First touch on a ripe tile locks in the produce remaining on the plant.
        if cell.deposit <= 0:
            cell.deposit = self._farm_produce_yield_at(x, y)
        remaining = int(cell.deposit)
        if remaining <= 0:
            if status:
                self._set_status("Crop not ready.")
            return False
        take = 0
        while take < remaining and inventory.can_add(take + 1, key=crop.produce_key):
            take += 1
        if take <= 0:
            if status:
                self._set_status("Inventory is full.")
            return False
        cell.deposit = remaining - take
        if not inventory.add_item(crop.produce_key, take):
            cell.deposit = remaining
            if status:
                self._set_status("Could not store harvest.")
            return False
        self.record_produced(crop.produce_key, take)

        straw_msg = ""
        seed_msg = ""
        finished = cell.deposit <= 0
        if finished:
            crop_key = self.world.harvest_crop_herb(x, y)
            if crop_key is None:
                # Produce already taken; force-clear the tile.
                cell.feature = FeatureType.NONE
                cell.growth_ticks = 0
                cell.crop_kind = None
                cell.deposit = 0
                from soil import drop_fertility_on_harvest

                drop_fertility_on_harvest(cell)
                crop_key = crop.key
            crop = CROP_BY_KEY.get(crop_key, crop)
            if crop.key not in ("wheat", "rye"):
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
                    seed_msg = (
                        f" +{got} {crop.label.lower()} seed{'s' if got != 1 else ''}"
                    )
            self.world.apply_extraction_disturbance(x, y)
            self._refresh_indicators()
        if status:
            left = f" ({cell.deposit} left)" if not finished else ""
            qty = f" ×{take}" if take != 1 else ""
            self._set_status(
                f"Harvested farm {crop.label.lower()}{qty}{left}{seed_msg}{straw_msg}."
            )
        return True

    def _forester_needs_axe(self, building: Building) -> bool:
        return building.kind == BuildingKind.FORESTER

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
        if inv.tool_slots_free() > 0 and int(getattr(self.home_storage, tool_key, 0)) > 0:
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
        recipe = self._craftable_split_recipe(building, worker=villager)
        if recipe is None or villager.work_cooldown > 0:
            return False
        self._spend_work_energy(villager)
        if building.advance_recipe_progress(recipe, split=True):
            self._apply_recipe_tracked(building, recipe)
            self._gain_job_skill(villager, building.kind.name)
        villager.work_cooldown = self._villager_work_interval(villager)
        return True

    def _deposit_home(self, inventory: Inventory, status: bool = True) -> bool:
        items = inventory.clear()
        if sum(items.values()) == 0:
            if status:
                self._set_status("Nothing to deposit.")
            return False
        coins = int(items.pop("coins", 0) or 0)
        if coins > 0:
            self.regional_wealth = int(self.regional_wealth) + coins
        if items:
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
            if coins > 0:
                setattr(bag, "coins", coins)
            lines = format_grouped_counts(amounts_from_obj(bag), skip_zero=True)
            self._set_status("Deposited. " + " · ".join(lines) if lines else "Deposited.")
        return True

    def _allowed_tools_for_villager(self, villager: Villager) -> set[str]:
        """Tools matching any priority workplace slot (or empty for pure haulers)."""
        allowed: set[str] = set()
        for bid in villager.active_workplace_slot_ids(self.season):
            if bid is None:
                continue
            building = self.buildings.get(bid)
            if building is None:
                continue
            primary = WORKPLACE_TOOL.get(building.kind)
            if primary:
                allowed.add(primary)
            for extra in WORKPLACE_EXTRA_TOOLS.get(building.kind, ()):
                allowed.add(extra)
            for also in WORKPLACE_ALSO_REQUIRES.get(building.kind, ()):
                allowed.add(also)
        return allowed

    @staticmethod
    def _cell_has_hunt_loot(cell) -> bool:
        return (
            cell.meat_deposit > 0
            or cell.hide_deposit > 0
            or cell.fur_deposit > 0
        )

    def _apply_hunt_recipe_to_inventory(
        self, inventory: Inventory, recipe_name: str
    ) -> bool:
        recipe = hunt_recipe(recipe_name)
        if recipe is None or not recipe.outputs:
            return False
        if not recipe_outputs_fit(inventory, recipe):
            return False
        apply_recipe_outputs(inventory, recipe)
        for key, n in recipe.outputs.items():
            self.record_produced(key, n)
        return True

    def _drop_hunt_yields(
        self,
        x: int,
        y: int,
        kind,
        *,
        building: Building | None = None,
    ) -> int:
        """Leave hunt loot on the kill tile from hunter CSV outputs. Returns meat amount."""
        name = kind.name.lower()
        if building is not None and not building.allows_hunt_kind(name):
            return 0
        recipe = hunt_recipe(name)
        outputs = dict(recipe.outputs) if recipe is not None else {}
        meat = 0
        for key, amount in outputs.items():
            if amount <= 0:
                continue
            if key == "meat":
                self.world.add_meat_deposit(x, y, amount)
                meat += amount
            elif key == "hide":
                self.world.add_hide_deposit(x, y, amount)
            elif key == "fur":
                self.world.add_fur_deposit(x, y, amount)
        return meat

    def _hunt_recipe_status_bits(self, recipe_name: str) -> list[str]:
        recipe = hunt_recipe(recipe_name)
        if recipe is None:
            return []
        bits: list[str] = []
        for key, amount in recipe.outputs.items():
            if amount <= 0:
                continue
            from resources import resource_label

            label = resource_label(key)
            bits.append(f"{amount} {label}" if amount != 1 else label)
        return bits

    def _villager_needs_home_restock(self, villager: Villager) -> bool:
        """True when storehouse can refill a missing job tool, arrows, or clothing."""
        inv = villager.inventory
        home = self.home_storage
        for tool in self._allowed_tools_for_villager(villager):
            if inv.has_equipped_tool(tool):
                continue
            if int(getattr(home, tool, 0)) > 0 and inv.tool_slots_free() > 0:
                return True
        if self._hunter_prefers_bow(villager) or inv.has_equipped_tool("bow"):
            from resources import STACK_SIZES

            stack = int(STACK_SIZES.get("stone_arrows", 10))
            have = int(getattr(inv, "stone_arrows", 0))
            if have < stack and int(getattr(home, "stone_arrows", 0)) > 0:
                return True
        if self._clothing_upgrade_available(villager):
            return True
        return False

    def _best_clothing_for_slot(
        self, inventory: Inventory, slot: str
    ) -> tuple[str | None, str | None]:
        """Return (item_key, source) where source is worn/cargo/home."""
        prefs = preferred_clothing_for_temp(ambient_temperature_c(self.calendar_day))
        keys = prefs.get(slot, ())
        home = self.home_storage
        for key in keys:
            if inventory.equipped_in_slot(slot) == key:
                return key, "worn"
            if int(getattr(inventory, key, 0)) > 0:
                return key, "cargo"
            if int(getattr(home, key, 0)) > 0:
                return key, "home"
        return None, None

    def _clothing_upgrade_available(self, villager: Villager) -> bool:
        """True when a better seasonal garment is in cargo or the storehouse."""
        inv = villager.inventory
        prefs = preferred_clothing_for_temp(ambient_temperature_c(self.calendar_day))
        for slot in prefs:
            best, source = self._best_clothing_for_slot(inv, slot)
            if best is None or source == "worn":
                continue
            worn = inv.equipped_in_slot(slot)
            if worn is None:
                return True
            keys = prefs[slot]
            if worn not in keys:
                return True
            if best in keys and keys.index(best) < keys.index(worn):
                return True
        return False

    def _try_equip_preferred_clothing_from_cargo(self, villager: Villager) -> bool:
        """Equip better seasonal clothing already in cargo. Returns True if any change."""
        inv = villager.inventory
        prefs = preferred_clothing_for_temp(ambient_temperature_c(self.calendar_day))
        changed = False
        for slot in prefs:
            best, source = self._best_clothing_for_slot(inv, slot)
            if best is None or source != "cargo":
                continue
            worn = inv.equipped_in_slot(slot)
            if worn == best:
                continue
            if inv.equip_clothing(best):
                changed = True
        return changed

    def _restock_clothing_at_home(self, villager: Villager) -> None:
        """Swap in season/temp-appropriate clothing from cargo or storehouse."""
        if (villager.x, villager.y) != self.world.home_pos:
            return
        inv = villager.inventory
        home = self.home_storage
        prefs = preferred_clothing_for_temp(ambient_temperature_c(self.calendar_day))
        for slot in prefs:
            best, source = self._best_clothing_for_slot(inv, slot)
            if best is None or source == "worn":
                continue
            worn = inv.equipped_in_slot(slot)
            if worn == best:
                continue
            if worn is not None:
                if not inv.unequip_clothing(slot):
                    continue
                # Park the old garment in the storehouse so cargo stays free.
                have = int(getattr(inv, worn, 0))
                if have > 0:
                    setattr(inv, worn, have - 1)
                    setattr(home, worn, int(getattr(home, worn, 0)) + 1)
            if source == "cargo":
                inv.equip_clothing(best)
                continue
            stock = int(getattr(home, best, 0))
            if stock <= 0:
                continue
            setattr(home, best, stock - 1)
            inv.equip_clothing_from_transfer(best)

    def _restock_workplace_gear_at_home(self, villager: Villager) -> None:
        """Equip missing job tools, clothing, and top up arrows at the storehouse."""
        if (villager.x, villager.y) != self.world.home_pos:
            return
        inv = villager.inventory
        for tool in self._allowed_tools_for_villager(villager):
            if inv.has_equipped_tool(tool):
                continue
            if inv.tool_slots_free() <= 0:
                break
            stock = int(getattr(self.home_storage, tool, 0))
            if stock <= 0:
                continue
            setattr(self.home_storage, tool, stock - 1)
            inv.equip_tool_from_transfer(tool)
        if self._hunter_prefers_bow(villager) or inv.has_equipped_tool("bow"):
            from resources import STACK_SIZES

            stack = int(STACK_SIZES.get("stone_arrows", 10))
            have = int(getattr(inv, "stone_arrows", 0))
            need = stack - have
            if need > 0:
                stock = int(getattr(self.home_storage, "stone_arrows", 0))
                take = min(need, stock)
                while take > 0 and not inv.can_add(take, key="stone_arrows"):
                    take -= 1
                if take > 0:
                    setattr(
                        self.home_storage,
                        "stone_arrows",
                        stock - take,
                    )
                    inv.add_item("stone_arrows", take)
        self._try_equip_preferred_clothing_from_cargo(villager)
        self._restock_clothing_at_home(villager)

    def _update_home_restock(self, villager: Villager) -> None:
        """Walk to the storehouse to withdraw tools / seasonal clothing."""
        home = self.world.home_pos
        villager.state = VillagerState.WORKING
        villager.target = home
        if (villager.x, villager.y) != home:
            if villager.move_cooldown == 0:
                self._step_villager_toward(villager, home)
            return
        if self._inventory_needs_store_deposit(villager.inventory):
            self._deposit_home(villager.inventory, status=False)
        self._restock_workplace_gear_at_home(villager)
        villager.target = None
        if villager.state == VillagerState.WORKING:
            villager.state = VillagerState.IDLE

    def _unequip_mismatched_tools(self, villager: Villager) -> bool:
        """Unequip tools that don't match priority jobs. Returns True if any moved."""
        allowed = self._allowed_tools_for_villager(villager)
        inv = villager.inventory
        changed = False
        for tool in list(inv.equipped_tools):
            if tool in allowed:
                continue
            if inv.unequip_tool(tool):
                changed = True
        return changed

    def _inventory_needs_store_deposit(self, inventory: Inventory) -> bool:
        """True when cargo or loose (unequipped) tools should go to the storehouse."""
        if inventory.has_delivery_cargo():
            return True
        return any(int(getattr(inventory, key, 0)) > 0 for key in TOOL_KEYS)

    def _begin_job_change_deposit(self, villager: Villager) -> None:
        """After a job/slot change: return mismatched tools and deposit old cargo."""
        self._bump_work_gen()
        self._unequip_mismatched_tools(villager)
        if not self._inventory_needs_store_deposit(villager.inventory):
            villager.job_change_deposit = False
            return
        villager.job_change_deposit = True
        villager.clear_work_stickies()
        villager.haul_building_id = None
        villager.state = VillagerState.DELIVERING
        villager.target = self.world.home_pos
        self._clear_villager_path(villager)

    def _return_mismatched_tools_to_store(self, villager: Villager) -> None:
        """Unequip tools that don't match priority jobs and send them to the storehouse."""
        self._unequip_mismatched_tools(villager)
        inv = villager.inventory
        if not any(int(getattr(inv, key, 0)) > 0 for key in TOOL_KEYS):
            return
        villager.job_change_deposit = True
        villager.clear_work_stickies()
        villager.haul_building_id = None
        villager.state = VillagerState.DELIVERING
        villager.target = self.world.home_pos
        self._clear_villager_path(villager)

    def _tick_job_change_deposit(self, villager: Villager) -> bool:
        """Walk to storehouse and deposit. True while still handling the deposit."""
        if not villager.job_change_deposit:
            return False
        self._unequip_mismatched_tools(villager)
        if not self._inventory_needs_store_deposit(villager.inventory):
            villager.job_change_deposit = False
            if villager.state == VillagerState.DELIVERING:
                villager.state = VillagerState.IDLE
                villager.target = None
            return False
        home = self.world.home_pos
        villager.state = VillagerState.DELIVERING
        villager.target = home
        villager.haul_building_id = None
        if (villager.x, villager.y) == home:
            self._deposit_home(villager.inventory, status=False)
            self._restock_workplace_gear_at_home(villager)
            villager.job_change_deposit = False
            villager.state = VillagerState.IDLE
            villager.target = None
            return False
        if villager.move_cooldown == 0:
            self._step_villager_toward(villager, home)
        return True

    def _collect_meat(self, x: int, y: int, inventory: Inventory, status: bool = False) -> bool:
        if inventory.is_full:
            if status:
                self._set_status("Inventory is full.")
            return False
        taken = self.world.harvest_meat(x, y, amount=1)
        hide_taken = 0
        fur_taken = 0
        if inventory.can_add(1, key="hide"):
            hide_taken = self.world.harvest_hide(x, y, amount=1)
            if hide_taken > 0:
                inventory.add_item("hide", hide_taken)
                self.record_produced("hide", hide_taken)
        if inventory.can_add(1, key="fur"):
            fur_taken = self.world.harvest_fur(x, y, amount=1)
            if fur_taken > 0:
                inventory.add_item("fur", fur_taken)
                self.record_produced("fur", fur_taken)
        if taken <= 0 and hide_taken <= 0 and fur_taken <= 0:
            if status:
                self._set_status("No meat here.")
            return False
        if taken > 0:
            inventory.add_meat(taken)
            self.record_produced("meat", taken)
        if status:
            left = self.world.get_cell(x, y)
            remaining = left.meat_deposit if left else 0
            bits = []
            if taken:
                bits.append(f"{taken} meat ({remaining} left)")
            if hide_taken:
                bits.append(f"{hide_taken} hide")
            if fur_taken:
                bits.append(f"{fur_taken} fur")
            self._set_status("Collected " + ", ".join(bits) + ".")
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

    def _adjacent_colony(self, x: int, y: int, *, kind: AnimalKind | None = None):
        """Colony nest on this cell or within Chebyshev distance 1."""
        best = None
        best_dist = 99
        for colony in self.wildlife.colonies:
            if kind is not None and colony.kind != kind:
                continue
            dist = max(abs(colony.x - x), abs(colony.y - y))
            if dist <= 1 and dist < best_dist:
                best = colony
                best_dist = dist
        return best

    def _player_harvest_honey(self, colony) -> None:
        """Collect honey from a bee nest (no tool required)."""
        inv = self.player.inventory
        if not colony.can_harvest() or colony.kind != AnimalKind.BEE:
            self._set_status("Bee nest is not ready to harvest.")
            return
        if not inv.can_add(HONEY_PER_BEE_LEVEL, key="honey"):
            self._set_status("Inventory is full.")
            return
        result = self.wildlife.harvest_colony(colony.id, kind=AnimalKind.BEE)
        if result is None:
            self._set_status("Could not harvest honey.")
            return
        _kind, amount = result
        inv.add_item("honey", amount)
        self.record_produced("honey", amount)
        self.world.apply_extraction_disturbance(colony.x, colony.y)
        self._refresh_indicators()
        self._finish_player_work()
        left = (
            self.wildlife.colony_by_id(colony.id).level
            if self.wildlife.colony_by_id(colony.id) is not None
            else 0
        )
        self._set_status(f"Collected {amount} honey (nest level now {left}).")

    def _player_hunt_warren(self, colony) -> None:
        """Spear-hunt a rabbit warren within melee range."""
        inv = self.player.inventory
        if not inv.has_equipped_tool("knife"):
            self._set_status("Equip a knife (I or Q) to dress rabbits.")
            return
        if not inv.has_equipped_tool("spear"):
            self._set_status("Equip a spear (I or Q) to hunt rabbits.")
            return
        if not colony.can_harvest() or colony.kind != AnimalKind.RABBIT:
            self._set_status("Warren is not ready to hunt.")
            return
        recipe = hunt_recipe("rabbit")
        if recipe is None or not recipe_outputs_fit(inv, recipe):
            self._set_status("Inventory is full.")
            return
        result = self.wildlife.harvest_colony(colony.id, kind=AnimalKind.RABBIT)
        if result is None:
            self._set_status("Rabbits got away.")
            return
        if not self._apply_hunt_recipe_to_inventory(inv, "rabbit"):
            self._set_status("Inventory is full.")
            return
        self.world.apply_extraction_disturbance(colony.x, colony.y)
        self._refresh_indicators()
        self._finish_player_work()
        loot = ", ".join(self._hunt_recipe_status_bits("rabbit")) or "loot"
        self._set_status(f"Hunted warren. {loot}.")

    def _player_hunt(self, animal) -> None:
        inv = self.player.inventory
        if not inv.has_equipped_tool("knife"):
            self._set_status("Equip a knife (I or Q) to dress carcasses.")
            return
        has_spear = inv.has_equipped_tool("spear")
        has_bow = inv.has_equipped_tool("bow") and int(getattr(inv, "stone_arrows", 0)) > 0
        if not has_spear and not has_bow:
            self._set_status("Equip a spear or bow+arrows (I or Q) to hunt.")
            return
        result = self.wildlife.kill_animal(animal.id)
        if result is None:
            self._set_status("Animal got away.")
            return
        if has_bow and not has_spear:
            inv.consume_item("stone_arrows", 1)
            self.record_consumed("stone_arrows", 1)
        x, y, kind = result
        meat = self._drop_hunt_yields(x, y, kind)
        label = "boar" if kind == AnimalKind.BOAR else "deer"
        self.world.apply_extraction_disturbance(x, y)
        if kind in (AnimalKind.DEER, AnimalKind.BOAR):
            self.wildlife.scare_from_kill(x, y)
        self._refresh_indicators()
        self._finish_player_work()
        weapon = "spear" if has_spear else "bow"
        loot = ", ".join(self._hunt_recipe_status_bits(kind.name.lower())) or f"{meat} meat"
        self._set_status(
            f"Hunted {label} with {weapon}. {loot} on ({x}, {y})."
        )

    def _hunt_threat_positions(self) -> list[tuple[int, int]]:
        """Player + all villagers — wildlife flees these positions."""
        threats: list[tuple[int, int]] = [(self.player.x, self.player.y)]
        threats.extend((v.x, v.y) for v in self.villagers)
        return threats

    def _hunter_flee_interval(self) -> int:
        """Deer/boar/wolf flee pace from File → Balance → Wildlife."""
        from settings import seconds_to_ticks

        try:
            seconds = float(self.balance.get_float("ANIMAL_FLEE_SECONDS_AT_X1"))
        except Exception:
            from settings import ANIMAL_FLEE_SECONDS_AT_X1

            seconds = float(ANIMAL_FLEE_SECONDS_AT_X1)
        return max(4, seconds_to_ticks(seconds))

    def _tick_wildlife(self, day: float) -> None:
        self.wildlife.tick(
            self.world,
            day,
            hunter_threats=self._hunt_threat_positions(),
            flee_interval=self._hunter_flee_interval(),
            biodiversity=getattr(self.env_maps, "biodiversity", None),
        )

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
        if not self.player.inventory.has_equipped_tool("fishing_rod"):
            self._set_status("Equip a fishing rod (Q) to fish.")
            return
        from wildlife import fish_yield_for

        result = self.fish.kill_fish(item.id)
        if result is None:
            self._set_status("Fish got away.")
            return
        x, y, kind = result
        yield_n = fish_yield_for(kind)
        self.world.add_fish_deposit(x, y, yield_n)
        self.world.apply_extraction_disturbance(x, y)
        self._refresh_indicators()
        self._finish_player_work()
        self._set_status(
            f"Caught {kind.name.lower()}. {yield_n} fish left on shore."
        )

    # ------------------------------------------------------------------
    # Villager AI
    # ------------------------------------------------------------------
    def _update_villagers(self) -> None:
        for villager in self.villagers:
            if villager.move_cooldown > 0:
                villager.move_cooldown -= 1
            if villager.work_cooldown > 0:
                villager.work_cooldown -= 1
            if villager.decision_cooldown > 0:
                villager.decision_cooldown -= 1

        self._tick_village_food = self._village_food_amounts()
        if any(self._villager_needs_ai_pass(v) for v in self.villagers):
            self._rebuild_villager_claim_snapshot()
        else:
            self._reset_tick_claims()

        for villager in list(self.villagers):
            day_frac = 1.0 / max(1, self.ticks_per_day)
            self._update_villager_wellbeing(villager, day_frac)
            if villager.id not in {v.id for v in self.villagers}:
                continue
            if villager.state == VillagerState.SLEEPING:
                if (
                    villager.target is not None
                    and (villager.x, villager.y) != villager.target
                    and villager.move_cooldown == 0
                ):
                    self._step_villager_toward(villager, villager.target)
                    villager.move_cooldown = self._villager_move_interval(villager)
                continue

            if self._tick_job_change_deposit(villager):
                continue

            villager.satiation = max(
                0.0,
                villager.satiation
                - self._satiation_decay() * villager.food_hunger_mult,
            )

            if self._idle_decision_pending(villager):
                continue

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

            # Withdraw tools / seasonal clothing from the storehouse when available.
            if (
                villager.state
                not in (
                    VillagerState.DELIVERING,
                    VillagerState.HAULING,
                    VillagerState.BUILDING,
                )
                and self._villager_needs_home_restock(villager)
            ):
                self._try_equip_preferred_clothing_from_cargo(villager)
                if self._villager_needs_home_restock(villager):
                    self._update_home_restock(villager)
                    continue

            prios = villager.active_priorities(self.season)
            acted = False
            # Mid-build / carrying mats always finishes. Otherwise only preempt the
            # priority loop when BUILD is actually on this villager's list (S7).
            if self._construction_delivery_active(villager):
                if (
                    self._carrying_build_mats(villager)
                    or villager.state == VillagerState.BUILDING
                    or WorkPriority.BUILD in prios
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
            # Finish an in-progress haul / deposit. DELIVERING with no haul claim
            # (assigned drop at workplace or storehouse) must not fall through to
            # primary workplace work — that caused field ↔ store thrash with
            # leftover foreign cargo (e.g. fish on a farmer).
            if villager.state in (VillagerState.HAULING, VillagerState.DELIVERING):
                if self._uses_general_haul_update(villager):
                    self._update_hauler(villager)
                else:
                    building = self.buildings.get(villager.building_id)
                    if building is not None:
                        self._update_assigned_transport(villager, building)
                    else:
                        home = self.world.home_pos
                        villager.haul_building_id = None
                        villager.target = home
                        if (villager.x, villager.y) == home:
                            self._deposit_home(villager.inventory, status=False)
                            villager.state = VillagerState.IDLE
                            villager.target = None
                        else:
                            self._step_villager_toward(villager, home)
                continue
            for priority in prios:
                if priority == WorkPriority.NONE:
                    continue
                if priority == WorkPriority.WORKPLACE:
                    bid = self._pick_workplace_building(villager)
                    if bid is not None:
                        self._update_workplace_worker(villager, bid)
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
                    or WorkPriority.BUILD in prios
                ):
                    self._update_builder(villager)
                elif self._leftover_build_mats_need_home(villager):
                    self._update_leftover_build_mats(villager)
                elif not villager.inventory.is_empty and self._is_general_hauler(
                    villager
                ):
                    self._update_hauler(villager)
                elif WorkPriority.WORKPLACE in prios and (
                    villager.building_id is not None
                    or self._villager_workplace_ids(villager)
                ):
                    bid = self._pick_workplace_building(villager)
                    if bid is not None:
                        self._update_workplace_worker(villager, bid)
                        acted = True
                    else:
                        self._set_workplace_idle(villager)
                elif villager.state not in (VillagerState.DELIVERING, VillagerState.HAULING, VillagerState.BUILDING):
                    villager.state = VillagerState.IDLE
                    villager.target = None
            if (
                not acted
                and villager.state == VillagerState.IDLE
                and villager.target is None
                and not villager.seeking_food
            ):
                self._park_idle_decision(villager)

    def _satiation_speed_factor(self, satiation: float) -> float:
        """1.0 when full, down to 0.4 when starving — scales move/work pace."""
        s = max(0.0, min(1.0, float(satiation)))
        return 0.4 + 0.6 * s

    def _move_interval_for(
        self,
        *,
        satiation: float,
        food_walk_mult: float,
        happiness: float,
        energy: float,
    ) -> int:
        """Ticks between steps — fixed vs ticks/day; ×N playback runs N ticks/frame."""
        factor = (
            self._satiation_speed_factor(satiation)
            * max(0.1, float(food_walk_mult))
            * (0.7 + 0.3 * max(0.0, min(1.0, happiness)))
            * (0.55 + 0.45 * max(0.0, min(1.0, energy)))
        )
        base = self._walk_interval_ticks()
        return max(4, int(round(base / max(0.15, factor))))

    def _work_interval_for(
        self,
        *,
        satiation: float,
        food_work_mult: float,
        happiness: float,
        energy: float,
        skill_mult: float = 1.0,
    ) -> int:
        """Ticks between work actions — fixed vs ticks/day; speed buttons scale playback."""
        factor = (
            self._satiation_speed_factor(satiation)
            * max(0.1, float(food_work_mult))
            * max(0.15, float(skill_mult))
            * (0.65 + 0.35 * max(0.0, min(1.0, happiness)))
            * (0.5 + 0.5 * max(0.0, min(1.0, energy)))
        )
        base = self._work_interval_ticks()
        return max(6, int(round(base / max(0.15, factor))))

    def _temp_impact(self, inventory: Inventory):
        """Hot/cold impact for this inventory's equipped clothing."""
        return temperature_impact(
            ambient_temperature_c(self.calendar_day),
            inventory.gear_heat_protection,
            inventory.gear_cold_protection,
        )

    def _temp_walk_mult(self, inventory: Inventory) -> float:
        """Walk speed multiplier from temperature impact (1.0 when comfortable)."""
        return float(self._temp_impact(inventory).walk_mult)

    def _temp_energy_mult(self, inventory: Inventory) -> float:
        """Energy drain multiplier from temperature impact."""
        return float(self._temp_impact(inventory).energy_mult)

    def _villager_move_interval(self, villager: Villager) -> int:
        return self._move_interval_for(
            satiation=villager.satiation,
            food_walk_mult=(
                villager.food_walk_mult
                * villager.inventory.gear_walk_mult
                * self._temp_walk_mult(villager.inventory)
            ),
            happiness=villager.happiness,
            energy=villager.energy,
        )

    def _player_move_interval(self) -> int:
        p = self.player
        return self._move_interval_for(
            satiation=p.satiation,
            food_walk_mult=(
                p.food_walk_mult
                * p.inventory.gear_walk_mult
                * self._temp_walk_mult(p.inventory)
            ),
            happiness=p.happiness,
            energy=p.energy,
        )

    def _villager_work_interval(self, villager: Villager) -> int:
        skill_mult = 1.0
        if villager.building_id is not None:
            building = self.buildings.get(villager.building_id)
            if building is not None:
                skill, _ = skill_for_building(building.kind.name)
                skill_mult = skill_efficiency(villager, skill)
        elif villager.assigned_to_home:
            skill_mult = skill_efficiency(villager, SkillType.TRANSPORT)
        elif villager.state == VillagerState.BUILDING:
            skill_mult = skill_efficiency(villager, SkillType.LABOUR)
        return self._work_interval_for(
            satiation=villager.satiation,
            food_work_mult=villager.food_work_mult,
            happiness=villager.happiness,
            energy=villager.energy,
            skill_mult=skill_mult,
        )

    def _player_work_interval(self) -> int:
        p = self.player
        return self._work_interval_for(
            satiation=p.satiation,
            food_work_mult=p.food_work_mult,
            happiness=p.happiness,
            energy=p.energy,
        )

    def _finish_player_work(self) -> None:
        """Spend energy and start the villager-paced work cooldown after an action."""
        self.player.energy = max(
            0.0,
            self.player.energy
            - ENERGY_WORK_DRAIN * self._temp_energy_mult(self.player.inventory),
        )
        self.player.work_cooldown = self._player_work_interval()

    def _clear_player_build(self) -> None:
        self.player_build_site_id = None

    def _player_work_construction(self, site: ConstructionSite) -> None:
        """Deposit materials and/or start continuous building on a construction site."""
        if site.is_complete:
            self._clear_player_build()
            return
        if self.player.work_cooldown > 0 and self.player_build_site_id != site.id:
            self._set_status("Still working…")
            return

        delivered = False
        while site.wood_needed > 0 and self.player.inventory.wood > 0:
            self.player.inventory.wood -= 1
            site.have_wood += 1
            self.record_consumed("wood", 1)
            delivered = True
        while site.logs_needed > 0 and self.player.inventory.logs > 0:
            self.player.inventory.logs -= 1
            site.have_logs += 1
            self.record_consumed("logs", 1)
            delivered = True
        while site.hardwood_needed > 0 and self.player.inventory.hardwood_logs > 0:
            self.player.inventory.hardwood_logs -= 1
            site.have_hardwood += 1
            self.record_consumed("hardwood_logs", 1)
            delivered = True
        while site.rock_needed > 0 and self.player.inventory.rock > 0:
            self.player.inventory.rock -= 1
            site.have_rock += 1
            self.record_consumed("rock", 1)
            delivered = True
        if delivered:
            self._finish_player_work()
            self._set_status(
                f"Delivered to site. Now {site.have_wood}/{site.need_wood} wood "
                f"{site.have_logs}/{site.need_logs} logs "
                f"{site.have_hardwood}/{site.need_hardwood} hwood "
                f"{site.have_rock}/{site.need_rock} rock."
            )
            if site.materials_ready and not site.is_complete:
                self.player_build_site_id = site.id
            return

        if not site.materials_ready:
            self._clear_player_build()
            self._set_status(
                f"{BUILDING_LABELS[site.kind]} site: "
                f"{site.have_wood}/{site.need_wood} wood "
                f"{site.have_logs}/{site.need_logs} logs "
                f"{site.have_hardwood}/{site.need_hardwood} hwood "
                f"{site.have_rock}/{site.need_rock} rock — need materials"
            )
            return

        # Materials ready: start / continue continuous build (like Craft).
        if self.sim_speed <= 0:
            self._set_status("Unpause (Space) to build.")
            return
        self.player_build_site_id = site.id
        if self.player.work_cooldown <= 0:
            self._advance_player_build_step()
        else:
            pct = int(
                100 * site.build_progress / max(1, site.build_required_ticks())
            )
            self._set_status(
                f"Building {BUILDING_LABELS[site.kind]}… {pct}%."
            )

    def _advance_player_build_step(self) -> bool:
        """One work tick on the sticky construction job. Returns False if stopped."""
        sid = self.player_build_site_id
        if sid is None:
            return False
        site = self.construction_sites.get(sid)
        if site is None or site.is_complete:
            self._clear_player_build()
            return False
        px, py = self.player.x, self.player.y
        if not site.contains_plot(px, py):
            self._clear_player_build()
            self._set_status("Left the site — building stopped.")
            return False
        if not site.materials_ready:
            self._clear_player_build()
            self._set_status("Need more materials at the site.")
            return False
        if self.sim_speed <= 0:
            return False
        site.build_progress += 1
        self._finish_player_work()
        if site.is_complete:
            label = BUILDING_LABELS[site.kind]
            self._complete_construction(site)
            self._clear_player_build()
            self._set_status(f"Finished {label}.")
            return False
        pct = int(100 * site.build_progress / max(1, site.build_required_ticks()))
        self._set_status(
            f"Building {BUILDING_LABELS[site.kind]}… {pct}% "
            f"({site.build_progress}/{site.build_required_ticks()})."
        )
        return True

    def _player_craft_recipe(self, recipe_name: str) -> None:
        """Start (or retarget) continuous player crafting on the inspected building."""
        from recipes import recipe_label, recipe_output_fits, recipe_ready
        from resources import resource_label

        if not self.building_inspect.allow_player_craft:
            self._set_status("Stand on the building (or its barn) and open it to craft.")
            return
        if self.sim_speed <= 0:
            self._set_status("Unpause (Space) to craft.")
            return
        building = self._inspect_building()
        if building is None:
            return
        if not self._player_at_craft_site(building):
            self._set_status("Stand on the farm or barn to thresh.")
            return
        recipe = None
        is_split = False
        for r in (
            *building.known_recipes(),
            *building.addon_craft_recipes(),
        ):
            if r.name == recipe_name:
                recipe = r
                break
        if recipe is None:
            for r in building.split_recipes():
                if r.name == recipe_name:
                    recipe = r
                    is_split = True
                    break
        if recipe is None:
            for r in building.plant_recipes():
                if r.name == recipe_name:
                    recipe = r
                    break
        if recipe is None:
            self._set_status("Unknown recipe.")
            return

        tool = WORKPLACE_TOOL.get(building.kind)
        extras = WORKPLACE_EXTRA_TOOLS.get(building.kind, ())
        if recipe in building.addon_craft_recipes():
            if building.kind == BuildingKind.HUNTER:
                tool = "knife"
                extras = ()
            elif building.kind == BuildingKind.FARM:
                # Barn threshing — hoe is for plough / weed only.
                tool = None
                extras = ()
        if tool is not None:
            inv = self.player.inventory
            ok = inv.has_equipped_tool(tool) or any(
                inv.has_equipped_tool(t) for t in extras
            )
            if not ok:
                need = resource_label(tool)
                self._set_status(f"Equip a {need} (I or Q) to craft here.")
                return

        if not building.is_recipe_enabled(recipe.name):
            # Player Craft implies enabling a newly added / toggled-off recipe.
            building.ensure_recipe_state()
            building.recipe_enabled[recipe.name] = True

        # Pull matching inputs from the player into the building first.
        building.deposit_needed_from(self.player.inventory)
        for key in recipe.inputs:
            while int(getattr(building, key, 0)) < int(recipe.inputs[key]):
                if not building.deposit_one_from(self.player.inventory, key):
                    break

        if building.kind == BuildingKind.KITCHEN and not building.has_cooking_fuel():
            self._set_status("Kitchen needs wood fuel.")
            return
        if not recipe_ready(building, recipe):
            missing = [
                resource_label(k)
                for k, n in recipe.inputs.items()
                if int(getattr(building, k, 0)) < int(n)
            ]
            self._set_status(
                "Need inputs in building: "
                + (", ".join(missing) if missing else "materials")
            )
            return
        if not recipe_output_fits(
            building,
            recipe,
            capacity=building.capacity,
            stock_amounts=self._village_stock_amounts(),
        ):
            self._set_status("No room for craft output.")
            return

        self.player_craft_building_id = building.id
        self.player_craft_recipe = recipe.name
        self.player_craft_split = is_split
        # Kick the first step immediately if idle; otherwise resume on next ready tick.
        if self.player.work_cooldown <= 0:
            self._advance_player_craft_step()
        else:
            self._set_status(
                f"Crafting {recipe_label(recipe)}… "
                f"{int(building.recipe_progress_fraction(recipe.name) * 100)}%."
            )

    def _clear_player_craft(self) -> None:
        self.player_craft_building_id = None
        self.player_craft_recipe = None
        self.player_craft_split = False

    def _advance_player_craft_step(self) -> bool:
        """One work tick of the active player craft job. Returns False if stopped."""
        from recipes import recipe_label, recipe_output_fits, recipe_ready
        from resources import resource_label

        bid = self.player_craft_building_id
        name = self.player_craft_recipe
        if bid is None or name is None:
            return False
        building = self.buildings.get(bid)
        if building is None:
            self._clear_player_craft()
            return False
        # Must stay on the workplace or a linked extension (barn / drying rack).
        if not self._player_at_craft_site(building):
            self._clear_player_craft()
            self._set_status("Left the building — crafting stopped.")
            return False

        tool = WORKPLACE_TOOL.get(building.kind)
        extras = WORKPLACE_EXTRA_TOOLS.get(building.kind, ())
        recipe_probe = None
        for group in (
            building.known_recipes(),
            building.addon_craft_recipes(),
            building.split_recipes(),
            building.plant_recipes(),
        ):
            for r in group:
                if r.name == name:
                    recipe_probe = r
                    break
            if recipe_probe is not None:
                break
        if recipe_probe is not None and recipe_probe in building.addon_craft_recipes():
            if building.kind == BuildingKind.HUNTER:
                tool = "knife"
                extras = ()
            elif building.kind == BuildingKind.FARM:
                tool = None
                extras = ()
        if tool is not None:
            inv = self.player.inventory
            ok = inv.has_equipped_tool(tool) or any(
                inv.has_equipped_tool(t) for t in extras
            )
            if not ok:
                self._clear_player_craft()
                self._set_status(f"Craft stopped — equip a {resource_label(tool)}.")
                return False

        recipe = recipe_probe
        if recipe is None or not building.is_recipe_enabled(recipe.name):
            self._clear_player_craft()
            self._set_status("Craft stopped — recipe unavailable.")
            return False

        building.deposit_needed_from(self.player.inventory)
        for key in recipe.inputs:
            while int(getattr(building, key, 0)) < int(recipe.inputs[key]):
                if not building.deposit_one_from(self.player.inventory, key):
                    break

        if building.kind == BuildingKind.KITCHEN and not building.has_cooking_fuel():
            self._clear_player_craft()
            self._set_status("Craft stopped — kitchen needs wood fuel.")
            return False
        if not recipe_ready(building, recipe):
            self._clear_player_craft()
            self._set_status(f"Craft stopped — need more inputs for {recipe_label(recipe)}.")
            return False
        if not recipe_output_fits(
            building,
            recipe,
            capacity=building.capacity,
            stock_amounts=self._village_stock_amounts(),
        ):
            self._clear_player_craft()
            self._set_status("Craft stopped — no room for output.")
            return False

        done = building.advance_recipe_progress(
            recipe, split=self.player_craft_split
        )
        self._finish_player_work()
        label = recipe_label(recipe)
        if done:
            fuel = 1 if building.kind == BuildingKind.KITCHEN else 0
            self._apply_recipe_tracked(building, recipe, fuel_wood=fuel)
            if fuel:
                building.fuel_wood = max(0, building.fuel_wood - 1)
            # Keep producing the same recipe while inputs remain.
            village_stock = self._village_stock_amounts()
            if (
                recipe_ready(building, recipe)
                and recipe_output_fits(
                    building,
                    recipe,
                    capacity=building.capacity,
                    stock_amounts=village_stock,
                )
                and (
                    building.kind != BuildingKind.KITCHEN
                    or building.has_cooking_fuel()
                )
            ):
                self._set_status(f"Crafted {label}. Continuing…")
            else:
                self._clear_player_craft()
                self._set_status(f"Crafted {label}.")
        else:
            frac = building.recipe_progress_fraction(recipe.name)
            self._set_status(f"Crafting {label}… {int(frac * 100)}%.")
        return True

    def _tick_player(self, ticks: int = 1) -> None:
        """Advance player cooldowns, hunger, and optional auto-eat."""
        if ticks <= 0:
            return
        p = self.player
        p.move_cooldown = max(0, p.move_cooldown - ticks)
        p.work_cooldown = max(0, p.work_cooldown - ticks)
        p.satiation = max(
            0.0,
            p.satiation - self._satiation_decay() * p.food_hunger_mult * ticks,
        )
        # Idle recovery (no sleep bed) — slower than villager sleep.
        p.energy = min(
            1.0,
            p.energy + self._legacy_per_tick(ENERGY_SLEEP_GAIN) * 0.35 * ticks,
        )
        if p.auto_eat and p.needs_food() and self._food_count(p.inventory) > 0:
            eaten = self._eat_random_from(p.inventory, p)
            if eaten > 0:
                meal = ", ".join(p.last_meal) if p.last_meal else "food"
                self._set_status(
                    f"Auto-ate {meal}. Walk ×{format_buff_mult(p.food_walk_mult)} · "
                    f"Work ×{format_buff_mult(p.food_work_mult)}."
                )
        # Continue an active craft / build job when the work cooldown rolls over.
        if (
            self.player_craft_building_id is not None
            and p.work_cooldown <= 0
            and self.sim_speed > 0
        ):
            self._advance_player_craft_step()
        if (
            self.player_build_site_id is not None
            and p.work_cooldown <= 0
            and self.sim_speed > 0
        ):
            self._advance_player_build_step()

    def _highlighted_player_food(self) -> str | None:
        """Food key selected or hovered in the player inventory UI."""
        key = self.player_inventory.highlighted_key()
        if key is None:
            return None
        if key not in VILLAGER_FOOD_KEYS:
            return None
        if int(getattr(self.player.inventory, key, 0)) <= 0:
            return None
        return key

    def _player_eat(self, *, manual: bool = False) -> None:
        """Eat only the highlighted inventory food (F). No auto-eat."""
        if not manual:
            return
        key = self._highlighted_player_food()
        if key is None:
            if self._food_count(self.player.inventory) <= 0:
                self._set_status("No food in inventory — forage or take from a store.")
            else:
                self._set_status(
                    "Highlight food in inventory (I): select or hover, then F — "
                    "or right-click food."
                )
            return
        self._player_eat_item(key)

    def _player_eat_item(self, key: str) -> None:
        """Consume one unit of ``key`` from the player inventory."""
        from resources import resource_label

        p = self.player
        label = resource_label(key)
        if key not in VILLAGER_FOOD_KEYS:
            self._set_status(f"{label} is not edible.")
            return
        amount = int(getattr(p.inventory, key, 0))
        if amount <= 0:
            self._set_status(f"No {label} left.")
            return
        setattr(p.inventory, key, amount - 1)
        self.record_consumed(key, 1)
        fx = food_def(key)
        p.satiation = min(1.0, p.satiation + satiation_from_points(fx.satiation))
        p.last_meal = [key]
        walk, work, hunger = self._combine_eater_meal_buffs(p, [key])
        p.apply_food_buffs(walk=walk, work=work, hunger=hunger)
        if self.player_inventory.selected_key == key and getattr(
            p.inventory, key, 0
        ) <= 0:
            self.player_inventory.selected_key = None
        self._set_status(
            f"Ate {label}. Walk ×{format_buff_mult(p.food_walk_mult)} · "
            f"Work ×{format_buff_mult(p.food_work_mult)}."
        )

    def _player_cycle_tool(self) -> None:
        """Equip next cargo tool, or unequip the last slot if cargo has none."""
        from resources import resource_label

        inv = self.player.inventory
        for key in TOOL_KEYS:
            if inv.equip_tool(key):
                self._set_status(f"Equipped {resource_label(key)}.")
                return
        if inv.equipped_tools:
            key = inv.equipped_tools[-1]
            if inv.unequip_tool(key):
                self._set_status(f"Unequipped {resource_label(key)}.")
                return
            self._set_status("Inventory full — cannot unequip tool.")
            return
        self._set_status("No tools in inventory to equip.")

    def _apply_player_inventory_action(self) -> None:
        action = self.player_inventory.take_action()
        if action is None:
            return
        from resources import resource_label

        inv = self.player.inventory
        if action == "tool_equip":
            self._player_cycle_tool()
            return
        if action.startswith("equip:"):
            key = action.split(":", 1)[1]
            if inv.equip_tool(key):
                self._set_status(f"Equipped {resource_label(key)}.")
            else:
                self._set_status(f"Cannot equip {resource_label(key)}.")
            return
        if action.startswith("equip_clothing:"):
            key = action.split(":", 1)[1]
            if inv.equip_clothing(key):
                self._set_status(f"Equipped {resource_label(key)}.")
            else:
                self._set_status(f"Cannot equip {resource_label(key)}.")
            return
        if action.startswith("clothing_equip:"):
            slot = action.split(":", 1)[1]
            from entities import CLOTHING_ITEM_SLOT

            for key, item_slot in CLOTHING_ITEM_SLOT.items():
                if item_slot != slot:
                    continue
                if inv.equip_clothing(key):
                    self._set_status(f"Equipped {resource_label(key)}.")
                    return
            self._set_status("No clothing for that slot in cargo.")
            return
        if action.startswith("clothing_unequip:"):
            slot = action.split(":", 1)[1]
            key = inv.equipped_in_slot(slot)
            if key and inv.unequip_clothing(slot):
                self._set_status(f"Unequipped {resource_label(key)}.")
            else:
                self._set_status("Inventory full — cannot unequip clothing.")
            return
        if action.startswith("unequip:"):
            key = action.split(":", 1)[1]
            if inv.unequip_tool(key):
                self._set_status(f"Unequipped {resource_label(key)}.")
            else:
                self._set_status("Inventory full — cannot unequip tool.")
            return
        if action.startswith("select:"):
            key = action.split(":", 1)[1]
            self._set_status(f"{resource_label(key)} ×{int(getattr(inv, key, 0))}")
            return
        if action.startswith("eat:"):
            self._player_eat_item(action.split(":", 1)[1])
            return
        if action == "toggle_auto_eat":
            self.player.auto_eat = not self.player.auto_eat
            state = "on" if self.player.auto_eat else "off"
            self._set_status(f"Auto-eat {state}.")
            return
    def _handle_player_hud_click(self, pos: tuple[int, int]) -> bool:
        """Equip/unequip from the map-corner player status HUD."""
        from resources import resource_label

        for rect, action in getattr(self, "_player_hud_tool_hits", []):
            if not rect.collidepoint(pos):
                continue
            inv = self.player.inventory
            if action == "tool_equip":
                self._player_cycle_tool()
                return True
            if action.startswith("tool_unequip:"):
                key = action.split(":", 1)[1]
                if inv.unequip_tool(key):
                    self._set_status(f"Unequipped {resource_label(key)}.")
                else:
                    self._set_status("Inventory full — cannot unequip tool.")
                return True
        return False

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
        """Best village food stockpile: meal quality first, then distance."""
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

        def rank(pos: tuple[int, int]) -> tuple[float, int]:
            storage = self._food_store_at(pos)
            score = (
                storage_meal_score(
                    storage, required_foods=list(villager.required_foods)
                )
                if storage is not None
                else 0.0
            )
            dist = abs(pos[0] - villager.x) + abs(pos[1] - villager.y)
            return (-score, dist)

        return min(options, key=rank)

    def _eat_random_from(
        self, storage, eater: Villager | Player | None = None
    ) -> int:
        """Consume food toward a meal. Returns how many items eaten.

        One unit of each food type, up to ``MAX_FOOD_TYPES_PER_MEAL`` types,
        preferring buff foods over debuff snacks, then satiation.
        After a full meat meal, one sweet dessert may still be taken for a
        walk-speed buff even when satiation is already full.
        """
        target = eater.ration_refill() if eater is not None else 0.75
        available = [
            key for key in VILLAGER_FOOD_KEYS if getattr(storage, key, 0) > 0
        ]
        required = (
            list(eater.required_foods)
            if isinstance(eater, Villager)
            else None
        )
        available.sort(key=lambda k: food_preference_key(k, required))
        eaten_keys: list[str] = []
        points = 0.0

        def _consume(key: str) -> None:
            nonlocal points
            setattr(storage, key, getattr(storage, key) - 1)
            self.record_consumed(key, 1)
            fx = food_def(key)
            points += fx.satiation
            eaten_keys.append(key)
            if eater is not None:
                eater.satiation = min(
                    1.0, eater.satiation + satiation_from_points(fx.satiation)
                )

        for key in available:
            if len(eaten_keys) >= MAX_FOOD_TYPES_PER_MEAL:
                break
            if eater is not None and eater.satiation >= target and eaten_keys:
                break
            if eater is None and points >= 5.0 and eaten_keys:
                break
            _consume(key)
            if eater is not None:
                if eater.satiation >= target:
                    break
            elif points >= 5.0:
                break

        # Dessert: full meat meal can take one sweet for a speed buff.
        if (
            eaten_keys
            and meal_includes_meat(eaten_keys)
            and not any(food_is_sweet(k) for k in eaten_keys)
            and (
                (eater is not None and eater.satiation >= target)
                or (eater is None and points >= 5.0)
            )
        ):
            dessert_keys = [
                key
                for key in available
                if food_is_sweet(key)
                and key not in eaten_keys
                and int(getattr(storage, key, 0)) > 0
            ]
            dessert_keys.sort(
                key=lambda k: (
                    -food_def(k).walk_speed,
                    -food_def(k).work_efficiency,
                    k,
                )
            )
            if dessert_keys:
                _consume(dessert_keys[0])

        if eater is not None and eaten_keys:
            eater.last_meal = list(eaten_keys)
            walk, work, hunger = self._combine_eater_meal_buffs(eater, eaten_keys)
            if isinstance(eater, Villager):
                # Missing hire staple in this meal lowers happiness immediately.
                if eater.required_foods and not meal_covers_any_requirement(
                    eaten_keys, eater.required_foods
                ):
                    from resources import resource_icon

                    miss = next(
                        (
                            f
                            for f in eater.required_foods
                            if not any(
                                meal_covers_any_requirement([k], [f])
                                for k in eaten_keys
                            )
                        ),
                        eater.required_foods[0],
                    )
                    hap_pts = -4
                    apply_happiness_points(eater, hap_pts)
                    push_happiness_event(
                        eater,
                        icon=resource_icon(miss) if miss else "meat",
                        label=f"Meal missing {requirement_label(miss)}",
                        delta=hap_pts,
                        day=int(self.calendar_day),
                    )
                else:
                    variety = min(3, len(eaten_keys))
                    if variety > 0:
                        from resources import resource_icon

                        push_happiness_event(
                            eater,
                            icon=resource_icon(eaten_keys[0]),
                            label=f"Food variety (+{variety})",
                            delta=variety,
                            day=int(self.calendar_day),
                        )
                    if eater.favourite_foods and any(
                        f in eaten_keys for f in eater.favourite_foods
                    ):
                        from resources import resource_icon

                        fav = next(
                            f for f in eater.favourite_foods if f in eaten_keys
                        )
                        apply_happiness_points(eater, 1)
                        push_happiness_event(
                            eater,
                            icon=resource_icon(fav),
                            label=f"Favourite {requirement_label(fav)}",
                            delta=1,
                            day=int(self.calendar_day),
                        )
            eater.apply_food_buffs(walk, work, hunger)
        return len(eaten_keys)

    def _update_seek_food(self, villager: Villager) -> None:
        """Walk to food; at the storehouse also deposit cargo and restock gear."""
        villager.seeking_food = True
        home = self.world.home_pos
        needs_home_stop = self._inventory_needs_store_deposit(
            villager.inventory
        ) or self._villager_needs_home_restock(villager)

        dest = self._find_nearest_food_store(villager)
        store = self._food_store_at(dest) if dest is not None else None
        store_score = (
            storage_meal_score(store, required_foods=list(villager.required_foods))
            if store is not None
            else 0.0
        )
        inv_score = storage_meal_score(
            villager.inventory, required_foods=list(villager.required_foods)
        )

        # Eat carried food only when it matches the best village meal and we do not
        # still need a storehouse stop for deposits / tool restock.
        if (
            not needs_home_stop
            and self._food_count(villager.inventory) > 0
            and inv_score + 0.05 >= store_score
        ):
            eaten = self._eat_random_from(villager.inventory, villager)
            if eaten > 0:
                villager.seeking_food = False
                villager.work_cooldown = self._villager_work_interval(villager)
                villager.state = VillagerState.WORKING
            return

        # Drop cargo / restock tools at home before (or instead of) a kitchen run.
        if needs_home_stop:
            dest = home

        if dest is None:
            # Nowhere better to eat — finish any carried snacks as a last resort.
            if self._food_count(villager.inventory) > 0:
                eaten = self._eat_random_from(villager.inventory, villager)
                if eaten > 0:
                    villager.seeking_food = False
                    villager.work_cooldown = self._villager_work_interval(villager)
                    villager.state = VillagerState.WORKING
                    return
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
            if dest == home:
                if self._inventory_needs_store_deposit(villager.inventory):
                    self._deposit_home(villager.inventory, status=False)
                self._restock_workplace_gear_at_home(villager)
            storage = self._food_store_at(dest)
            if storage is None:
                # Deposited at home with no food left here — retry next tick (kitchen).
                villager.seeking_food = villager.needs_food()
                return
            if self._food_count(storage) <= 0:
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
        if WorkPriority.TRANSPORT not in villager.active_priorities(self.season):
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
            return self._craftable_recipe(building) is not None
        if building.is_splitter() or building.kind == BuildingKind.FORESTER:
            return self._craftable_split_recipe(building) is not None
        return False

    def _claimed_haul_targets(self, exclude_id: int) -> set[int]:
        """Buildings already reserved by another hauler / assigned transporter.

        Only active HAULING/DELIVERING claims count — a farmer who left
        ``haul_building_id`` set while weeding must not fence the farm off.
        """
        claimed: set[int] = set()
        for other in self.villagers:
            if other.id == exclude_id:
                continue
            if other.haul_building_id is None:
                continue
            if other.state not in (VillagerState.HAULING, VillagerState.DELIVERING):
                continue
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
            keys.update(("logs", "hardwood_logs", "wood"))
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
        demand = self._building_supply_demand(building)
        if not demand:
            return False
        return any(self._village_supply_have(key) > 0 for key in demand)

    def _village_supply_have(self, key: str) -> int:
        """Units of ``key`` available for workplace supply (storehouse + farm surplus)."""
        total = int(getattr(self.home_storage, key, 0))
        for building in self.buildings.values():
            if building.kind == BuildingKind.FARM:
                total += int(building.haulable_amount(key))
        return total

    def _best_supply_pickup(
        self, demand: dict[str, int]
    ) -> tuple[object | None, tuple[int, int] | None]:
        """Prefer storehouse stock; otherwise a farm holding surplus demand goods."""
        if not demand:
            return None, None
        home = self.world.home_pos
        if any(int(getattr(self.home_storage, key, 0)) > 0 for key in demand):
            return self.home_storage, home
        origin = home
        best: Building | None = None
        best_key: tuple | None = None
        for building in self.buildings.values():
            if building.kind != BuildingKind.FARM:
                continue
            available = sum(
                min(int(want), building.haulable_amount(key))
                for key, want in demand.items()
            )
            if available <= 0:
                continue
            bx, by = building.center_cell()
            dist = abs(bx - origin[0]) + abs(by - origin[1])
            key = (-available, dist, building.id)
            if best_key is None or key < best_key:
                best_key = key
                best = building
        if best is None:
            return None, None
        return best, best.center_cell()

    def _building_supply_demand(self, building: Building) -> dict[str, int]:
        """Ingredient gaps for a workplace, including plan-based farm seeds."""
        cache = getattr(self, "_tick_supply_demand", None)
        if cache is not None and building.id in cache:
            return cache[building.id]
        demand = dict(building.supply_demand())
        if building.kind == BuildingKind.FARM:
            for key, want in self._farm_plan_seed_demand(building).items():
                demand[key] = max(demand.get(key, 0), want)
            barn = self._linked_barn(building)
            if barn is not None:
                self._migrate_sheaves_to_barn(building)
                for key in barn_sheaf_keys():
                    target = max(barn_sheaf_keep_amount(key), 2)
                    have = int(getattr(barn, key, 0))
                    room = barn.space_for_key(key)
                    want = min(max(0, target - have), room)
                    if want > 0:
                        demand[key] = max(demand.get(key, 0), want)
        if cache is not None:
            cache[building.id] = demand
        return demand

    def _farm_plan_seed_demand(self, farm: Building) -> dict[str, int]:
        """Seeds needed for nearby field plans that are in a plantable phase."""
        demand: dict[str, int] = {}
        for key, unsown in self._farm_unsown_seed_counts(farm).items():
            target = max(unsown, 3, int(farm.item_mins.get(key, 0)))
            have = int(getattr(farm, key, 0))
            if have >= target:
                continue
            room = farm.space_for_key(key)
            if room <= 0:
                continue
            want = min(target - have, room)
            if want > 0:
                demand[key] = max(demand.get(key, 0), want)
        return demand

    def _farm_unsown_seed_counts(self, farm: Building) -> dict[str, int]:
        """Unsown plant-phase tiles per seed key (nearby fields). Cached per tick."""
        cache = getattr(self, "_tick_farm_unsown", None)
        if cache is not None and farm.id in cache:
            return cache[farm.id]
        counts: dict[str, int] = {}
        season = self.season
        for field_b in self._fields_near_farm(farm):
            for plan in field_b.plans:
                crop = CROP_BY_KEY.get(plan.crop_kind, CROP_BY_KEY["sage"])
                if not phase_allows_plough_plant(phase_for_crop(crop, season)):
                    continue
                key = crop.seed_key
                n = 0
                for x, y in plan.cells():
                    if not self.world.is_walkable(x, y):
                        continue
                    cell = self.world.get_cell(x, y)
                    if cell is None:
                        continue
                    if cell.terrain in SOIL_LIKE and cell.feature == FeatureType.NONE:
                        n += 1
                if n > 0:
                    counts[key] = counts.get(key, 0) + n
        if cache is not None:
            cache[farm.id] = counts
        return counts

    def _farm_needed_seed_keys(self, farm: Building) -> tuple[str, ...]:
        return tuple(self._farm_unsown_seed_counts(farm))

    def _gather_cargo_needs_delivery(
        self, villager: Villager, building: Building
    ) -> bool:
        """True when the worker should stop gathering and deposit cargo."""
        inv = villager.inventory
        if inv.is_empty:
            return False
        if inv.is_full or not inv.can_add(1):
            return True
        if building.kind == BuildingKind.FORESTER:
            wood = int(getattr(inv, "wood", 0))
            log_cargo = int(inv.logs) + int(getattr(inv, "hardwood_logs", 0))
            # Split outputs go to the storehouse (never park wood at the lodge).
            if wood > 0:
                return True
            # Full-ish packs, or lodge already waiting to split — return logs.
            if log_cargo > 0 and (
                self._craftable_split_recipe(building) is not None or not inv.can_add(2)
            ):
                return True
            return False
        # Farm / forager: deliver whenever the next enabled yield won't fit —
        # even if cargo is "wrong" (e.g. leftover wood), so space frees up.
        if building.kind == BuildingKind.FARM:
            # Keep harvesting until the pack cannot take another produce unit;
            # deposit goes to the farm building (not the storehouse).
            return building.has_gather_cargo(inv) and not inv.can_add(1)
        if building.kind == BuildingKind.FORAGER:
            for recipe in building.enabled_recipes():
                need = self._forage_yield_amount(recipe.name)
                key = "wood" if recipe.name == "wood" else recipe.name
                if inv.can_add(need, key=key):
                    return False
            return True
        if building.kind == BuildingKind.FISHER:
            # Deposit fish at the hut whenever the next catch won't fit.
            return int(getattr(inv, "fish", 0)) > 0 and not inv.can_add(
                FISH_YIELD, key="fish"
            )
        if building.kind == BuildingKind.HUNTER:
            return building.has_gather_cargo(inv) and not inv.can_add(1)
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
        villager.hunt_shot = None
        villager.fish_target_id = None
        villager.fish_catch_pos = None
        villager.fish_post_pos = None
        villager.forage_colony_id = None
        self._clear_villager_path(villager)

    def _force_assigned_delivery(
        self, villager: Villager, building: Building
    ) -> bool:
        """Clear stickies and deposit / haul — even when primary work is still available."""
        self._clear_gather_stickies(villager)
        # Bypass `_maybe_assigned_transport`'s primary-available gate: a full pack
        # must be deposited even while fish/prey are still in range.
        return self._update_assigned_transport(villager, building)

    def _workplace_required_tool(
        self, villager: Villager, building: Building
    ) -> str | None:
        """Tool the worker must hold for this workplace's primary job, if any."""
        if building.kind == BuildingKind.FARM:
            return "hoe"
        if building.kind == BuildingKind.FORESTER:
            return "axe" if self._forester_needs_axe(building) else None
        if building.kind == BuildingKind.HUNTER:
            if self._hunter_weapon_ready(villager):
                return None
            if self._hunter_prefers_bow(villager):
                return "bow"
            return "spear"
        if building.kind == BuildingKind.FISHER:
            if not fishing_allowed(self.calendar_day):
                return None
            return "fishing_rod"
        return WORKPLACE_TOOL.get(building.kind)

    def _hunter_prefers_bow(self, villager: Villager) -> bool:
        from society import SkillType

        if villager_skill_level(villager, SkillType.HUNTING) < HUNTER_BOW_MIN_SKILL:
            return False
        inv = villager.inventory
        if inv.has_equipped_tool("bow") or int(getattr(inv, "bow", 0)) > 0:
            return True
        if int(getattr(self.home_storage, "bow", 0)) > 0:
            return True
        return False

    def _hunter_can_ranged(self, villager: Villager) -> bool:
        from society import SkillType

        if villager_skill_level(villager, SkillType.HUNTING) < HUNTER_BOW_MIN_SKILL:
            return False
        inv = villager.inventory
        if not inv.has_equipped_tool("bow"):
            return False
        return int(getattr(inv, "stone_arrows", 0)) > 0

    def _hunter_weapon_ready(self, villager: Villager) -> bool:
        inv = villager.inventory
        if inv.has_equipped_tool("spear"):
            return True
        return self._hunter_can_ranged(villager)

    def _ensure_hunter_arrows(self, villager: Villager, amount: int = 10) -> bool:
        """Ensure stone arrows in cargo; fetch one stack from storehouse if needed."""
        from resources import STACK_SIZES

        inv = villager.inventory
        if int(getattr(inv, "stone_arrows", 0)) > 0:
            return True
        stock = int(getattr(self.home_storage, "stone_arrows", 0))
        if stock <= 0:
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
        stack = int(STACK_SIZES.get("stone_arrows", 10))
        take = min(amount, stack, stock)
        if take <= 0 or not inv.can_add(take, key="stone_arrows"):
            return False
        setattr(self.home_storage, "stone_arrows", stock - take)
        inv.add_item("stone_arrows", take)
        villager.target = None
        return int(getattr(inv, "stone_arrows", 0)) > 0

    def _ensure_hunter_weapon(self, villager: Villager) -> bool:
        """Equip spear or (skill 4+) bow+arrows for hunting."""
        if self._hunter_prefers_bow(villager):
            if self._ensure_work_tool(villager, "bow") and self._ensure_hunter_arrows(
                villager
            ):
                return True
        if villager.inventory.has_equipped_tool("spear"):
            return True
        if self._hunter_can_ranged(villager):
            return True
        return self._ensure_work_tool(villager, "spear")

    def _ensure_hunter_tools(self, villager: Villager) -> bool:
        """Knife for dressing plus spear or bow for the kill."""
        for tool in WORKPLACE_ALSO_REQUIRES.get(BuildingKind.HUNTER, ()):
            if not self._ensure_work_tool(villager, tool):
                return False
        return self._ensure_hunter_weapon(villager)

    def _workplace_needs_tool_fetch(
        self, villager: Villager, building: Building
    ) -> bool:
        """True when primary is blocked only by a missing but fetchable tool."""
        tool = self._workplace_required_tool(villager, building)
        if tool is None:
            return False
        if villager.inventory.has_equipped_tool(tool):
            return False
        return self._tool_fetchable(villager, tool)

    def _linked_barn(self, farm: Building) -> Building | None:
        """Completed barn annex for this farm, if any."""
        if farm.kind != BuildingKind.FARM:
            return None
        from extensions import linked_extensions

        for b in linked_extensions(farm, self.buildings):
            if b.kind == BuildingKind.BARN:
                return b
        return None

    def _migrate_sheaves_to_barn(self, farm: Building) -> None:
        """Move leftover farm sheaves into the barn (one-time drain)."""
        barn = self._linked_barn(farm)
        if barn is None:
            return
        for key in barn_sheaf_keys():
            while int(getattr(farm, key, 0)) > 0 and barn.space_for_key(key) > 0:
                if not barn.can_add(1, key=key):
                    break
                setattr(farm, key, int(getattr(farm, key, 0)) - 1)
                barn.add_item(key, 1)

    def _barn_sheaf_have(
        self,
        farm: Building,
        key: str,
        extra: object | None = None,
    ) -> int:
        """Sheaves available for thresh: barn + leftover farm + optional pack."""
        barn = self._linked_barn(farm)
        total = int(getattr(barn, key, 0)) if barn is not None else 0
        total += int(getattr(farm, key, 0))
        if extra is not None:
            total += int(getattr(extra, key, 0))
        return total

    def _deposit_sheaves_to_barn(
        self, farm: Building, inventory: Inventory
    ) -> int:
        """Put sheaf produce into the barn; other goods still go to the farm."""
        barn = self._linked_barn(farm)
        moved = 0
        if barn is not None:
            self._migrate_sheaves_to_barn(farm)
            for key in barn_sheaf_keys():
                moved += barn.deposit_key_from(inventory, key)
        farm.deposit_from_inventory(inventory)
        return moved

    def _consume_barn_thresh_inputs(
        self, farm: Building, recipe, inventory: Inventory
    ) -> None:
        """Pull sheaf inputs from pack, then barn, then farm leftovers."""
        barn = self._linked_barn(farm)
        for key, need in recipe.inputs.items():
            left = int(need)
            take_inv = min(left, int(getattr(inventory, key, 0)))
            if take_inv:
                setattr(inventory, key, int(getattr(inventory, key, 0)) - take_inv)
                left -= take_inv
            if barn is not None and left > 0:
                take_b = min(left, int(getattr(barn, key, 0)))
                if take_b:
                    setattr(barn, key, int(getattr(barn, key, 0)) - take_b)
                    left -= take_b
            if left > 0:
                take_f = min(left, int(getattr(farm, key, 0)))
                if take_f:
                    setattr(farm, key, int(getattr(farm, key, 0)) - take_f)
                    left -= take_f
            if left > 0:
                raise RuntimeError(f"barn thresh missing {key} x{left}")

    def _apply_barn_thresh_recipe(
        self, farm: Building, recipe, inventory: Inventory
    ) -> None:
        """Thresh: consume sheaves from barn, grain/straw land on the farm."""
        self._consume_barn_thresh_inputs(farm, recipe, inventory)
        from recipes import apply_recipe_outputs

        apply_recipe_outputs(farm, recipe)
        for key, n in recipe.inputs.items():
            self.record_consumed(key, n)
        for key, n in recipe.outputs.items():
            self.record_produced(key, n)

    def _barn_thresh_recipe_ready(
        self, farm: Building, villager: Villager, recipe
    ) -> bool:
        from society import recipe_skill_gate
        from recipes import recipe_output_fits

        if not farm.is_recipe_enabled(recipe.name):
            return False
        if not recipe_skill_gate(recipe, worker=villager):
            return False
        stock = self._village_stock_amounts()
        if not farm._recipe_output_fits(recipe, stock_amounts=stock):
            return False
        for key, need in recipe.inputs.items():
            if self._barn_sheaf_have(farm, key, villager.inventory) < int(need):
                return False
        return True

    def _farm_barn_needs_sheaf_delivery(self, building: Building) -> bool:
        """True when the barn sheaf buffer is below keep and storehouse has sheaves."""
        if building.kind != BuildingKind.FARM or not building.addon_craft_recipes():
            return False
        barn = self._linked_barn(building)
        if barn is None:
            return False
        self._migrate_sheaves_to_barn(building)
        for key in barn_sheaf_keys():
            target = max(barn_sheaf_keep_amount(key), 2)
            have = int(getattr(barn, key, 0))
            if have >= target:
                continue
            if barn.space_for_key(key) <= 0:
                continue
            if int(getattr(self.home_storage, key, 0)) > 0:
                return True
        return False

    def _farm_barn_craft_available(
        self, villager: Villager, building: Building
    ) -> bool:
        """True when barn sheaves can be threshed into farm grain."""
        if building.kind != BuildingKind.FARM or not building.addon_craft_recipes():
            return False
        self._migrate_sheaves_to_barn(building)
        for recipe in building.addon_craft_recipes():
            if self._barn_thresh_recipe_ready(building, villager, recipe):
                return True
        return False

    def _workplace_can_accept_cargo(
        self, building: Building, inventory: Inventory
    ) -> bool:
        """Like Building.can_accept_from, but routes farm sheaves into the barn."""
        if building.kind == BuildingKind.FARM:
            barn = self._linked_barn(building)
            if barn is not None:
                for key in barn_sheaf_keys():
                    if (
                        int(getattr(inventory, key, 0)) > 0
                        and barn.space_for_key(key) > 0
                    ):
                        return True
        return building.can_accept_from(inventory)

    def _sink_space_for_key(self, sink: Building, key: str) -> int:
        """Room at a supply sink (barn buffer for farm sheaves)."""
        if sink.kind == BuildingKind.FARM and key in barn_sheaf_keys():
            barn = self._linked_barn(sink)
            if barn is not None:
                return barn.space_for_key(key)
        return sink.space_for_key(key)

    def _deposit_workplace_cargo(
        self, building: Building, inventory: Inventory
    ) -> None:
        """Deposit into a workplace; farm sheaves go to the linked barn."""
        if building.kind == BuildingKind.FARM and self._linked_barn(building) is not None:
            self._deposit_sheaves_to_barn(building, inventory)
            return
        building.deposit_from_inventory(inventory)

    def _farm_export_grain_keys(self) -> tuple[str, ...]:
        """Mill inputs that also act as cereal seeds — surplus leaves the farm."""
        return ("wheat_grain", "rye_grain")

    def _farm_pack_has_export_cargo(
        self, inventory: Inventory, villager: Villager | None = None
    ) -> bool:
        """True when grain/straw should leave for mill/storehouse (not farm unload)."""
        job = getattr(villager, "farm_job_kind", None) if villager is not None else None
        if job in (
            FarmJobKind.SEED_FETCH.name,
            FarmJobKind.SOW.name,
            FarmJobKind.SHEAF_FETCH.name,
        ):
            return False
        has_grain = any(
            int(getattr(inventory, k, 0)) > 0 for k in self._farm_export_grain_keys()
        )
        has_straw = int(getattr(inventory, "straw", 0)) > 0
        if not has_grain and not has_straw:
            return False
        # Active export trip — finish it even with a partial pack.
        if job == FarmJobKind.EXPORT.name:
            return True
        # Full packs with grain/straw must not dump back onto the farm.
        return inventory.is_full or not inventory.can_add(1)

    def _farm_pack_needs_barn_or_farm_unload(
        self, villager: Villager, building: Building
    ) -> bool:
        """Harvest unload: sheaves → barn, field produce → farm (not grain export)."""
        inv = villager.inventory
        if inv.is_empty:
            return False
        barn = self._linked_barn(building)
        if barn is not None:
            for key in barn_sheaf_keys():
                if int(getattr(inv, key, 0)) > 0 and barn.space_for_key(key) > 0:
                    return True
        # Non-cereal produce (cabbage, flax, …) belongs on the farm tray.
        sheaves = set(barn_sheaf_keys())
        grain = set(self._farm_export_grain_keys())
        for key in building.gather_deposit_keys():
            if key in sheaves or key in grain or key == "straw":
                continue
            if int(getattr(inv, key, 0)) > 0 and building.space_for_key(key) > 0:
                return True
        return False

    def _farm_export_destination(
        self, villager: Villager, building: Building
    ) -> tuple[tuple[int, int], Building | None]:
        """Prefer mill when carrying grain it needs; else storehouse."""
        home = self.world.home_pos
        inv = villager.inventory
        best: Building | None = None
        best_key: tuple | None = None
        for mill in self.buildings.values():
            if mill.kind != BuildingKind.MILL:
                continue
            useful = False
            for key in self._farm_export_grain_keys():
                if int(getattr(inv, key, 0)) <= 0:
                    continue
                if mill.space_for_key(key) > 0:
                    useful = True
                    break
            if not useful:
                continue
            mx, my = mill.center_cell()
            dist = abs(mx - villager.x) + abs(my - villager.y)
            key = (dist, mill.id)
            if best_key is None or key < best_key:
                best_key = key
                best = mill
        origin = (villager.x, villager.y)
        if best is not None:
            bx, by = best.center_cell()
            walk = self._walk_goal_for_target(
                bx, by, prefer_adjacent=True, from_pos=origin
            )
            return (walk or (bx, by)), best
        walk = self._walk_goal_for_target(
            home[0], home[1], prefer_adjacent=True, from_pos=origin
        )
        return (walk or home), None

    def _farm_at_export_drop(
        self,
        villager: Villager,
        dest: tuple[int, int],
        sink: Building | None,
    ) -> bool:
        if (villager.x, villager.y) == dest:
            return True
        # Mill / home centres are often blocked — adjacent tile is enough to drop.
        if sink is not None:
            sx, sy = sink.center_cell()
            return max(abs(villager.x - sx), abs(villager.y - sy)) <= 1
        hx, hy = self.world.home_pos
        return max(abs(villager.x - hx), abs(villager.y - hy)) <= 1

    def _farm_finish_export_trip(
        self, villager: Villager, building: Building
    ) -> bool:
        """Walk export cargo to mill or storehouse; never dump it back on the farm."""
        if villager.inventory.is_empty:
            return False
        dest, sink = self._farm_export_destination(villager, building)
        home = self.world.home_pos
        villager.haul_building_id = sink.id if sink is not None else None
        villager.state = VillagerState.DELIVERING
        villager.target = dest
        villager.farm_job_kind = FarmJobKind.EXPORT.name
        if not self._farm_at_export_drop(villager, dest, sink):
            self._step_villager_toward(villager, dest)
            return True
        if villager.work_cooldown > 0:
            return True
        if sink is not None:
            sink.deposit_supply_from(villager.inventory)
            # Leftover non-mill cargo → storehouse next.
            if not villager.inventory.is_empty:
                villager.haul_building_id = None
                walk_home = self._walk_goal_for_target(
                    home[0],
                    home[1],
                    prefer_adjacent=True,
                    from_pos=(villager.x, villager.y),
                )
                villager.target = walk_home or home
                villager.work_cooldown = self._villager_work_interval(villager)
                return True
        else:
            self._deposit_home(villager.inventory, status=False)
            self._restock_workplace_gear_at_home(villager)
        villager.work_cooldown = self._villager_work_interval(villager)
        if villager.inventory.is_empty:
            villager.farm_job_kind = None
            villager.state = VillagerState.IDLE
            villager.target = None
            villager.haul_building_id = None
        return True

    def _farm_thresh_site(self, building: Building) -> tuple[int, int]:
        barn = self._linked_barn(building)
        if barn is not None:
            return barn.center_cell()
        return building.center_cell()

    def _execute_farm_sheaf_fetch(
        self, villager: Villager, building: Building
    ) -> None:
        """Idle farmer: storehouse → barn sheaf buffer (no haul claim)."""
        barn = self._linked_barn(building)
        if barn is None:
            villager.farm_job_kind = None
            return
        sheaf_keys = barn_sheaf_keys()
        carrying = any(
            int(getattr(villager.inventory, k, 0)) > 0 for k in sheaf_keys
        )
        villager.state = VillagerState.WORKING

        if carrying:
            dest = barn.center_cell()
            villager.target = dest
            if (villager.x, villager.y) != dest:
                if villager.move_cooldown > 0:
                    return
                self._step_villager_toward(villager, dest)
                return
            if villager.work_cooldown > 0:
                return
            self._deposit_sheaves_to_barn(building, villager.inventory)
            villager.work_cooldown = self._villager_work_interval(villager)
            still = any(
                int(getattr(villager.inventory, k, 0)) > 0 for k in sheaf_keys
            )
            if not still and not self._farm_barn_needs_sheaf_delivery(building):
                villager.farm_job_kind = None
                villager.target = None
            return

        if not self._farm_barn_needs_sheaf_delivery(building):
            villager.farm_job_kind = None
            return

        if not any(villager.inventory.can_add(1, key=k) for k in sheaf_keys):
            # Pack blocked — dump compatible cargo at farm/barn first.
            if self._workplace_can_accept_cargo(building, villager.inventory):
                dest = building.center_cell()
                villager.target = dest
                if (villager.x, villager.y) != dest:
                    if villager.move_cooldown > 0:
                        return
                    self._step_villager_toward(villager, dest)
                    return
                if villager.work_cooldown > 0:
                    return
                self._deposit_workplace_cargo(building, villager.inventory)
                villager.work_cooldown = self._villager_work_interval(villager)
                return
            villager.farm_job_kind = None
            return

        home = self.world.home_pos
        villager.target = home
        if (villager.x, villager.y) != home:
            if villager.move_cooldown > 0:
                return
            self._step_villager_toward(villager, home)
            return
        if villager.work_cooldown > 0:
            return
        taken = 0
        for key in sheaf_keys:
            target = max(barn_sheaf_keep_amount(key), 2)
            have_b = int(getattr(barn, key, 0))
            have_i = int(getattr(villager.inventory, key, 0))
            want = max(0, target - have_b - have_i)
            room = barn.space_for_key(key) - have_i
            while (
                want > 0
                and room > 0
                and taken < 6
                and int(getattr(self.home_storage, key, 0)) > 0
                and villager.inventory.can_add(1, key=key)
            ):
                setattr(
                    self.home_storage, key, int(getattr(self.home_storage, key, 0)) - 1
                )
                setattr(
                    villager.inventory,
                    key,
                    int(getattr(villager.inventory, key, 0)) + 1,
                )
                taken += 1
                want -= 1
                room -= 1
        villager.work_cooldown = self._villager_work_interval(villager)
        if taken <= 0:
            villager.farm_job_kind = None
        return

    def _workplace_primary_available(
        self, villager: Villager, building: Building
    ) -> bool:
        """True when the worker can perform their main job this tick (not transport)."""
        tool = self._workplace_required_tool(villager, building)
        if tool is not None and not villager.inventory.has_equipped_tool(tool):
            # Tool walks are a separate picker phase — not primary produce.
            return False

        if building.kind in (
            BuildingKind.MILL,
            BuildingKind.KITCHEN,
            BuildingKind.CRAFT_BENCH,
            BuildingKind.ALCHEMIST,
            BuildingKind.TAILOR,
            BuildingKind.COBBLER,
        ):
            if self._craftable_recipe(building) is not None:
                return True
            # Cooldown alone must not latch an empty station (blocks supply / P2).
            if villager.work_cooldown > 0 and building.can_accept_from(
                villager.inventory
            ):
                return True
            return False

        if building.kind == BuildingKind.MARKET:
            return (
                self._market_can_sell(building)
                or bool(building.supply_demand())
                or building.can_accept_from(villager.inventory)
            )

        # Full / harvest-blocked cargo must deliver — sticky targets must not block that.
        if self._gather_cargo_needs_delivery(villager, building):
            return False

        # Farm: pipeline job board — any claimable job counts as primary.
        if building.kind == BuildingKind.FARM:
            if building.space_left <= 0 and building.haulable_total() > 0:
                return True  # EXPORT work
            return self._farm_board_has_work(villager, building)

        # Hunt / fish / forage stickies first — cheap ids, and they must not pay
        # `_work_target_valid` on a prey/shore cell that is not a gather tile.
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

        # Sticky field targets only — home/station centres are tool-fetch or craft walks,
        # not primary gather work (those must not block delivery / idle).
        if (
            villager.target is not None
            and villager.state == VillagerState.WORKING
            and not self._is_station_or_home_cell(villager.target)
            and self._work_target_valid(villager, building, villager.target)
        ):
            return True

        if building.kind == BuildingKind.FORESTER:
            if (
                villager.inventory.is_full
                and building.has_gather_cargo(villager.inventory)
            ):
                return False
            if villager.target is not None and self._work_target_valid(
                villager, building, villager.target
            ):
                return True
            if self._craftable_split_recipe(building, worker=villager) is not None:
                return True
            return self._forester_has_nearby_tree_or_plant(villager, building)

        if building.kind == BuildingKind.HUNTER:
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
                and self._under_production_max(building, "meat")
                and self._within_work_search(origin, (a.x, a.y))
                for a in self.wildlife.animals
            ):
                return True
            from wildlife import AnimalKind

            if (
                building.allows_hunt_kind("rabbit")
                and self._under_production_max(building, "meat")
                and any(
                c.kind == AnimalKind.RABBIT
                and c.can_harvest()
                and self._within_work_search(origin, (c.x, c.y))
                for c in self.wildlife.colonies
            )
            ):
                return True
            return self._meat_deposit_available(building, villager.id)

        if building.kind == BuildingKind.FISHER:
            if not fishing_allowed(self.calendar_day):
                return False
            if villager.inventory.is_full:
                return False
            # Cheap availability only — full shore pathfinding runs in update.
            if villager.fish_post_pos is not None or villager.fish_catch_pos is not None:
                return True
            if self._fisher_candidate_fish(villager, building):
                return True
            return self._fish_deposit_available(building, villager.id)

        if building.kind == BuildingKind.FORAGER:
            if (
                villager.inventory.is_full
                and building.has_gather_cargo(villager.inventory)
            ):
                return False
            if villager.forage_colony_id is not None:
                return True
            if (
                villager.target is not None
                and villager.state == VillagerState.WORKING
                and not self._is_station_or_home_cell(villager.target)
                and self._work_target_valid(villager, building, villager.target)
            ):
                return True
            # Cheap presence probe — full pathfinding runs when selecting a target.
            return self._forager_has_nearby_work(villager, building)

        return self._find_work_in_building(villager, building) is not None

    def _assigned_transport_has_work(
        self, villager: Villager, building: Building
    ) -> bool:
        """Supply fetch or deposit for an assigned worker when primary work is blocked."""
        # Always finish delivering / clearing cargo even when field work remains.
        if not villager.inventory.is_empty:
            return True
        if self._gather_cargo_needs_delivery(villager, building):
            return True
        if (
            (
                building.is_processor()
                or building.kind == BuildingKind.FARM
            )
            and self._farm_or_processor_needs_clear(building)
            and not self._general_hauler_serving(building.id)
            and self._owns_haul_claim(villager, building.id)
        ):
            return True
        if self._workplace_primary_available(villager, building):
            return False
        # Soft gather-cargo deposit is handled last by `_pick_workplace_building`.
        if not self._owns_haul_claim(villager, building.id):
            return False
        if self._workplace_needs_home_supply(building):
            return True
        return False

    def _processor_blocked_on_output(
        self, building: Building, worker: Villager | None = None
    ) -> bool:
        """True when inputs are ready but no recipe fits in the output pool.

        Without this, craft/alchemist workers fall through to P2 whenever the tray
        is partly full (below the 75% clear latch) even though they should clear.
        """
        if not building.is_processor() or building.output_capacity <= 0:
            return False
        if building.haulable_total() <= 0:
            return False
        from recipes import recipe_output_fits, recipe_ready
        from society import recipe_skill_gate

        input_ready = False
        for recipe in building.enabled_recipes():
            if not recipe.inputs:
                continue
            if worker is not None and not recipe_skill_gate(recipe, worker=worker):
                continue
            if not recipe_ready(building, recipe):
                continue
            input_ready = True
            if recipe_output_fits(
                building,
                recipe,
                output_capacity=building.output_capacity,
                output_keys=building.processor_output_keys(),
                stock_amounts=self._village_stock_amounts(),
            ):
                return False
        return input_ready

    def _processor_should_clear(self, building: Building, worker: Villager | None = None) -> bool:
        if self._workplace_output_backed_up(building) or self._processor_blocked_on_output(
            building, worker
        ):
            return True
        # Input tray full of the wrong ingredient — haul excess so missing items fit.
        if (
            building.is_processor()
            and building.input_capacity > 0
            and building.input_space_left() <= 0
            and building._supply_target_recipes()
            and any(building.excess_input_amounts().values())
        ):
            return True
        return False

    def _farm_clear_in_progress(self, building: Building) -> bool:
        """True when an assigned farmer is clearing farm produce to the storehouse."""
        home = self.world.home_pos
        bx, by = building.center_cell()
        for v in self.villagers:
            if v.haul_building_id != building.id:
                if (
                    v.building_id == building.id
                    and v.state == VillagerState.DELIVERING
                    and v.target == home
                    and building.has_gather_cargo(v.inventory)
                ):
                    return True
                continue
            # Draining haulable stock home — not supply runs (home fetch → farm drop).
            if v.state == VillagerState.DELIVERING and v.target == home:
                return True
            if (
                v.state == VillagerState.HAULING
                and v.target == (bx, by)
                and v.inventory.is_empty
            ):
                return True
        return False

    def _farm_or_processor_needs_clear(self, building: Building) -> bool:
        """True when stock should be moved to the storehouse."""
        if building.haulable_total() <= 0:
            return False
        if building.kind == BuildingKind.FARM:
            # Start clearing when jammed / ≥75% full. Stay clearing down to ~40%
            # while a trip is in flight so packs don't bounce back into the farm.
            if building.space_left <= 0:
                return True
            if building.capacity <= 0:
                return False
            stored = building.cargo_stored_total
            if stored * 4 >= building.capacity * 3:
                return True
            if stored * 5 >= building.capacity * 2 and self._farm_clear_in_progress(
                building
            ):
                return True
            if building.seed_capacity > 0:
                seed_full = building.seed_space_left() <= 0
                seed_backed = (
                    building.seed_stored_total * 4 >= building.seed_capacity * 3
                )
                if seed_full or seed_backed:
                    needed = self._farm_needed_seed_keys(building)
                    blocked = any(building.space_for_key(key) <= 0 for key in needed)
                    if (seed_full or blocked) and any(
                        building.haulable_amount(key) > 0
                        for key in building.plant_keys()
                    ):
                        return True
            return False
        return self._workplace_output_backed_up(building)

    def _clear_backed_up_outputs_to_home(
        self, villager: Villager, building: Building
    ) -> bool:
        """Assigned worker hauls recipe outputs to the storehouse when output is full."""
        home = self.world.home_pos
        if not villager.inventory.is_empty:
            if building.kind == BuildingKind.FARM:
                return self._farm_finish_export_trip(villager, building)
            # Carrying cleared meals / wares → storehouse (not back into the station).
            villager.haul_building_id = None
            villager.state = VillagerState.DELIVERING
            villager.target = home
            if (villager.x, villager.y) == home:
                self._deposit_home(villager.inventory, status=False)
                self._restock_workplace_gear_at_home(villager)
                villager.state = VillagerState.IDLE
                villager.target = None
                return True
            self._step_villager_toward(villager, home)
            return True

        if building.haulable_total() <= 0:
            return False
        dest = building.center_cell()
        villager.haul_building_id = building.id
        villager.state = VillagerState.HAULING
        villager.target = dest
        if (villager.x, villager.y) != dest:
            self._step_villager_toward(villager, dest)
            return True
        if villager.work_cooldown > 0:
            return True
        self._withdraw_workplace_recipe_output(villager, building)
        villager.work_cooldown = self._villager_work_interval(villager)
        if villager.inventory.is_empty:
            villager.haul_building_id = None
            villager.state = VillagerState.IDLE
            villager.target = None
            return False
        villager.haul_building_id = None
        villager.state = VillagerState.DELIVERING
        villager.target = home
        return True

    def _workplace_accepts_carry(self, villager: Villager, building: Building) -> bool:
        """True when inventory holds something this workplace should take now."""
        if villager.inventory.is_empty:
            return False
        if building.can_accept_from(villager.inventory):
            return True
        if building.has_gather_cargo(villager.inventory):
            return True
        return False

    def _workplace_earlier_slot_preempts(
        self, villager: Villager, building: Building
    ) -> bool:
        """True when an earlier P-slot should yank the worker off a later job."""
        if self._workplace_primary_available(villager, building):
            return True
        if self._workplace_needs_tool_fetch(villager, building):
            return True
        if self._owns_haul_claim(villager, building.id) and self._workplace_needs_home_supply(
            building
        ):
            return True
        if building.is_processor() and self._processor_should_clear(building, villager):
            return True
        return False

    def _pick_workplace_building(self, villager: Villager) -> int | None:
        """Choose P1→P3 work: produce, tool, supply — delivery last.

        Per slot (P1, then P2, then P3):
        1. Primary harvest/produce/plant/collect
        2. Fetch required tool from storehouse if missing
        3. Fetch storehouse ingredients for that slot
        Then (all slots):
        4. Soft re-check primary (covers “re-check P1 after P2” across the list)
        5. Deposit personal cargo (including pack-full gather goods)
        """
        ids = self._villager_workplace_ids(villager)
        if not ids:
            return None

        # Finish an active haul claim for one of our workplaces.
        hid = villager.haul_building_id
        if (
            hid is not None
            and hid in ids
            and villager.state in (VillagerState.HAULING, VillagerState.DELIVERING)
        ):
            return hid

        # Stick to the current workplace while it still has useful work so P1↔P2
        # (craft↔alchemist) does not thrash when craftable flickers for a tick.
        # Earlier slots may still preempt for primary, tool, supply, or a jam.
        cur = villager.building_id
        if cur is not None and cur in ids and self._workplace_has_work_at(villager, cur):
            cur_i = ids.index(cur)
            for bid in ids[:cur_i]:
                building = self.buildings.get(bid)
                if building is None:
                    continue
                if self._workplace_earlier_slot_preempts(villager, building):
                    return bid
            return cur

        # Per slot: primary → tool fetch → storehouse ingredients → clear full outputs.
        for bid in ids:
            building = self.buildings.get(bid)
            if building is None:
                continue
            if self._workplace_primary_available(villager, building):
                return bid
            if self._workplace_needs_tool_fetch(villager, building):
                return bid
            if self._owns_haul_claim(villager, bid) and self._workplace_needs_home_supply(
                building
            ):
                return bid
            # Keep the worker on P1 when a *processor* is blocked only by full
            # outputs (kitchen meals) — otherwise they fall through to P2.
            # Gather huts (fisher) must not use this: they accept their own cargo
            # and emergency clear↔deposit loops forever.
            if building.is_processor() and self._processor_should_clear(building, villager):
                return bid
            if building.is_market() and building.haulable_total() > 0:
                return bid
            if (
                building.kind == BuildingKind.FARM
                and self._farm_or_processor_needs_clear(building)
            ):
                return bid
            if self._farm_board_has_work(villager, building):
                return bid

        # Re-scan primary only (step 5/7): if any slot can produce now, prefer it
        # over delivery — e.g. P1 became free of a false tool latch.
        for bid in ids:
            building = self.buildings.get(bid)
            if building is None:
                continue
            if self._workplace_primary_available(villager, building):
                return bid

        # Delivery last: pack-full gather cargo or any depositable carry.
        for bid in ids:
            building = self.buildings.get(bid)
            if building is None:
                continue
            if self._gather_cargo_needs_delivery(villager, building):
                return bid
            if self._workplace_accepts_carry(villager, building):
                return bid

        return None

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
        """Assigned workers drop cargo at workplace storage (barn for sheaves)."""
        if building.kind == BuildingKind.FARM:
            barn = self._linked_barn(building)
            if barn is not None and any(
                int(getattr(villager.inventory, k, 0)) > 0 for k in barn_sheaf_keys()
            ):
                bx, by = barn.center_cell()
                walk = self._walk_goal_for_target(
                    bx, by, prefer_adjacent=True, from_pos=(villager.x, villager.y)
                )
                return walk or (bx, by)
        return building.center_cell()

    def _withdraw_workplace_recipe_output(
        self, villager: Villager, building: Building
    ) -> None:
        if building.kind == BuildingKind.FARM:
            # Produce / straw only — never strip seed stock reserved for sowing.
            keys = building.haul_keys()
        else:
            recipe_keys = self._workplace_recipe_keys(building)
            keys = tuple(k for k in building.haul_keys() if k in recipe_keys)
        for key in keys:
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
        self._park_idle_decision(villager)

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

        if not villager.inventory.is_empty:
            # Farm harvest → farm store when it has room; otherwise storehouse.
            # While the farm cannot take this cargo, only divert full packs home —
            # partial packs must keep harvesting instead of bouncing to the store.
            # Export grain/straw never unloads at the farm (bounce loop).
            if (
                building.kind == BuildingKind.FARM
                and (
                    getattr(villager, "farm_job_kind", None) == FarmJobKind.EXPORT.name
                    or self._farm_pack_has_export_cargo(villager.inventory, villager)
                )
            ):
                return self._farm_finish_export_trip(villager, building)

            farm_harvest = (
                building.kind == BuildingKind.FARM
                and (
                    self._farm_pack_needs_barn_or_farm_unload(villager, building)
                    or building.has_gather_cargo(villager.inventory)
                )
                and not self._farm_pack_has_export_cargo(villager.inventory, villager)
            )
            gather_cargo = building.has_gather_cargo(villager.inventory)
            # Fisher/hunter/forager: once walking to the storehouse with gather
            # cargo, finish that trip. Haulers clearing the hut mid-walk must not
            # yank the worker back (storehouse ↔ hut thrash with a full pack).
            homebound_gather = (
                gather_cargo
                and not farm_harvest
                and villager.state == VillagerState.DELIVERING
                and villager.target == home
            )
            if homebound_gather:
                villager.haul_building_id = None
                if (villager.x, villager.y) == home:
                    self._deposit_home(villager.inventory, status=False)
                    self._restock_workplace_gear_at_home(villager)
                    villager.state = VillagerState.IDLE
                    villager.target = None
                    return True
                self._step_villager_toward(villager, home)
                return True
            farm_can_take = farm_harvest and self._workplace_can_accept_cargo(
                building, villager.inventory
            )
            pack_full = (
                villager.inventory.is_full or not villager.inventory.can_add(1)
            )
            if farm_harvest and not farm_can_take and not pack_full:
                # Over item-cap / blocked farm — resume field work with partial pack
                # even if already walking to the storehouse.
                villager.haul_building_id = None
                villager.state = VillagerState.WORKING
                villager.target = None
                return False
            farm_divert_home = farm_harvest and (
                building.space_left <= 0 or not farm_can_take
            )
            if farm_divert_home:
                villager.haul_building_id = None
                villager.state = VillagerState.DELIVERING
                villager.target = home
                if (villager.x, villager.y) == home:
                    self._deposit_home(villager.inventory, status=False)
                    self._restock_workplace_gear_at_home(villager)
                    villager.state = VillagerState.IDLE
                    villager.target = None
                    return True
                self._step_villager_toward(villager, home)
                return True
            if farm_harvest or self._workplace_can_accept_cargo(building, villager.inventory):
                villager.haul_building_id = None
                dest = self._assigned_transport_destination(villager, building)
                villager.state = VillagerState.DELIVERING
                villager.target = dest
                if (villager.x, villager.y) == dest:
                    if villager.work_cooldown == 0:
                        if building.is_processor():
                            building.deposit_supply_from(villager.inventory)
                        else:
                            self._deposit_workplace_cargo(building, villager.inventory)
                        villager.work_cooldown = self._villager_work_interval(villager)
                        if villager.inventory.is_empty:
                            villager.state = VillagerState.IDLE
                            villager.target = None
                            return True
                        if self._workplace_can_accept_cargo(building, villager.inventory):
                            # More workplace-compatible cargo — keep depositing next tick.
                            return True
                        # Leftover cargo this workplace will not take (e.g. fish on a
                        # farmer after dropping seeds/produce) — finish at storehouse.
                        # Idling here caused field ↔ farm-store thrash with foreign goods.
                        villager.haul_building_id = None
                        villager.state = VillagerState.DELIVERING
                        villager.target = home
                        return True
                    return True
                self._step_villager_toward(villager, dest)
                return True
            # Already walking home with cargo the workplace rejects — finish the trip
            # even if the workplace later accepts something else mid-walk.
            if (
                villager.state == VillagerState.DELIVERING
                and villager.target == home
            ):
                villager.haul_building_id = None
                if (villager.x, villager.y) == home:
                    self._deposit_home(villager.inventory, status=False)
                    self._restock_workplace_gear_at_home(villager)
                    villager.state = VillagerState.IDLE
                    villager.target = None
                    return True
                self._step_villager_toward(villager, home)
                return True
            villager.haul_building_id = None
            villager.state = VillagerState.DELIVERING
            villager.target = home
            if (villager.x, villager.y) == home:
                self._deposit_home(villager.inventory, status=False)
                self._restock_workplace_gear_at_home(villager)
                villager.state = VillagerState.IDLE
                villager.target = None
                return True
            self._step_villager_toward(villager, home)
            return True

        villager.haul_building_id = building.id

        # Clear a jammed / nearly-full farm before seed top-ups — otherwise empty
        # farmers walk to the storehouse for seeds while produce sits on-site.
        if (
            building.kind == BuildingKind.FARM
            and self._farm_or_processor_needs_clear(building)
            and not self._general_hauler_serving(building.id)
            and self._owns_haul_claim(villager, building.id)
        ):
            return self._clear_backed_up_outputs_to_home(villager, building)

        if self._workplace_needs_home_supply(building):
            if not self._owns_haul_claim(villager, building.id):
                villager.haul_building_id = None
                return False
            demand = self._building_supply_demand(building)
            _, pickup = self._best_supply_pickup(demand)
            if pickup is None:
                villager.haul_building_id = None
                return False
            villager.state = VillagerState.HAULING
            villager.target = pickup
            if (villager.x, villager.y) != pickup:
                self._step_villager_toward(villager, pickup)
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

        if self._workplace_output_backed_up(building) and not self._general_hauler_serving(
            building.id
        ):
            # Only processors (kitchen/craft): gather huts accept their own cargo, so
            # "clear then deposit back" becomes an infinite fish/meat loop.
            if building.is_processor():
                return self._clear_backed_up_outputs_to_home(villager, building)

        villager.haul_building_id = None
        return False

    def _maybe_assigned_transport(
        self, villager: Villager, building: Building
    ) -> bool:
        """Fetch storehouse supply or deposit when primary work is blocked.

        Returns True when this tick handled transport. Returns False when primary
        work is available, or when there is no transport work (caller may idle
        or switch P2/P3).
        """
        if self._workplace_primary_available(villager, building):
            return False
        return self._update_assigned_transport(villager, building)

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
        """One work tick: drop off inputs / plant stock, then fill remaining space with produce."""
        if building.kind == BuildingKind.FARM and self._linked_barn(building) is not None:
            self._deposit_sheaves_to_barn(building, villager.inventory)
            building.deposit_supply_from(villager.inventory)
        elif building.is_processor() or building.is_splitter() or building.is_market() or building.kind in (
            BuildingKind.FARM,
            BuildingKind.FORESTER,
        ):
            building.deposit_supply_from(villager.inventory)
        else:
            building.deposit_from_inventory(villager.inventory)
        # Pure outputs and excess inputs — haulable_amount skips dual-role stock
        # (e.g. twine) that enabled recipes still consume.
        out_keys = tuple(
            k for k in building.haul_keys() if building.haulable_amount(k) > 0
        )
        if out_keys and not villager.inventory.is_full:
            building.withdraw_to_inventory(villager.inventory, keys=out_keys)
        villager.work_cooldown = self._villager_work_interval(villager)

    def _villager_workplace_ids(self, villager: Villager) -> list[int]:
        slots = villager.active_workplace_slot_ids(self.season)
        ids = [
            bid
            for bid in slots
            if bid is not None and bid in self.buildings
        ]
        if ids:
            return ids
        if villager.building_id is not None and villager.building_id in self.buildings:
            return [villager.building_id]
        return []

    def _workplace_has_work_at(self, villager: Villager, building_id: int) -> bool:
        building = self.buildings.get(building_id)
        if building is None:
            return False
        if (
            villager.haul_building_id == building.id
            and villager.state in (VillagerState.HAULING, VillagerState.DELIVERING)
        ):
            return True
        if self._workplace_primary_available(villager, building):
            return True
        if self._workplace_needs_tool_fetch(villager, building):
            return True
        if self._gather_cargo_needs_delivery(villager, building):
            return True
        if self._owns_haul_claim(villager, building.id) and self._workplace_needs_home_supply(
            building
        ):
            return True
        if building.is_processor() and self._processor_should_clear(building, villager):
            return True
        if building.is_market() and building.haulable_total() > 0:
            return True
        if (
            building.kind == BuildingKind.FARM
            and self._farm_or_processor_needs_clear(building)
        ):
            return True
        if self._farm_board_has_work(villager, building):
            return True
        if self._workplace_accepts_carry(villager, building):
            return True
        return False

    def _workplace_has_work(self, villager: Villager) -> bool:
        return self._pick_workplace_building(villager) is not None

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
                and self._under_production_max(building, "honey")
            ):
                return True
        if building.kind == BuildingKind.FORESTER:
            allow_collect = bool(building.enabled_recipes())
            allow_plant = bool(building.enabled_plant_recipes()) and building.allows_planting()
        else:
            mode = building.work_mode
            allow_collect = mode in (WorkMode.COLLECT, WorkMode.ALL)
            allow_plant = mode in (WorkMode.PLANT, WorkMode.ALL) and building.allows_planting()
        can_plant_sapling, can_plant_berry, can_plant_herb = self._can_plant_from(
            villager, building
        )
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

        # Carrying build mats only counts if some site still needs them.
        # Otherwise release the claim so transport can clear leftover cargo.
        if self._carrying_build_mats(villager):
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
            elif (
                (site.wood_needed > 0 and self._material_available("wood"))
                or (site.logs_needed > 0 and self._material_available("logs"))
                or (site.hardwood_needed > 0 and self._material_available("hardwood_logs"))
                or (site.rock_needed > 0 and self._material_available("rock"))
            ):
                return True
            else:
                # Assigned to a half-built site with nothing left to fetch.
                villager.construction_id = None

        for site in self.construction_sites.values():
            if not site.materials_ready:
                if site.wood_needed > 0 and self._material_available("wood"):
                    return True
                if site.logs_needed > 0 and self._material_available("logs"):
                    return True
                if site.hardwood_needed > 0 and self._material_available("hardwood_logs"):
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
        inv = villager.inventory
        return (
            inv.wood > 0
            or inv.logs > 0
            or inv.rock > 0
            or inv.hardwood_logs > 0
        )

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
                self._restock_workplace_gear_at_home(villager)
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

        # Deliver carried wood/rock/hardwood to a needing site.
        if carrying:
            useful = self._find_site_needing_materials(villager)
            if useful is None:
                # Leftover mats no site needs — send to workplace/home.
                self._update_leftover_build_mats(villager)
                return
            # Prefer current site only if it can still take what we carry.
            if site is None or not (
                (site.wood_needed > 0 and villager.inventory.wood > 0)
                or (site.logs_needed > 0 and villager.inventory.logs > 0)
                or (site.rock_needed > 0 and villager.inventory.rock > 0)
                or (site.hardwood_needed > 0 and villager.inventory.hardwood_logs > 0)
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
                    if (
                        (site.wood_needed > 0 and villager.inventory.wood > 0)
                        or (site.logs_needed > 0 and villager.inventory.logs > 0)
                        or (site.rock_needed > 0 and villager.inventory.rock > 0)
                        or (
                            site.hardwood_needed > 0
                            and villager.inventory.hardwood_logs > 0
                        )
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
            self._spend_work_energy(villager)
            self._gain_job_skill(villager, "BUILD")
            if site.is_complete:
                self._complete_construction(site)
                villager.construction_id = None
                villager.state = VillagerState.IDLE
            return

        # Fetch materials from storage.
        source = self._find_material_source(
            villager,
            site.wood_needed > 0,
            site.rock_needed > 0,
            site.hardwood_needed > 0,
            site.logs_needed > 0,
        )
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
        if self._carrying_build_mats(villager):
            villager.state = VillagerState.DELIVERING
            villager.target = site.center_cell()
        else:
            villager.construction_id = None
            villager.state = VillagerState.IDLE

    def _find_site_needing_materials(self, villager: Villager) -> ConstructionSite | None:
        inv = villager.inventory
        candidates = [
            s
            for s in self.construction_sites.values()
            if not s.is_deconstruct
            and (
                (s.wood_needed > 0 and inv.wood > 0)
                or (s.logs_needed > 0 and inv.logs > 0)
                or (s.rock_needed > 0 and inv.rock > 0)
                or (s.hardwood_needed > 0 and inv.hardwood_logs > 0)
            )
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
            if not s.is_deconstruct
            and not s.materials_ready
            and (
                (s.wood_needed > 0 and self._material_available("wood"))
                or (s.logs_needed > 0 and self._material_available("logs"))
                or (s.rock_needed > 0 and self._material_available("rock"))
                or (s.hardwood_needed > 0 and self._material_available("hardwood_logs"))
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
        self,
        villager: Villager,
        want_wood: bool,
        want_rock: bool,
        want_hardwood: bool = False,
        want_logs: bool = False,
    ) -> tuple[int, int, str] | None:
        """Return (x, y, 'home'|'bID') for nearest build-material stock."""
        options: list[tuple[int, int, str, int]] = []
        hx, hy = self.world.home_pos

        def stock_ok(storage) -> bool:
            return (
                (want_wood and getattr(storage, "wood", 0) > 0)
                or (want_logs and getattr(storage, "logs", 0) > 0)
                or (want_rock and getattr(storage, "rock", 0) > 0)
                or (want_hardwood and getattr(storage, "hardwood_logs", 0) > 0)
            )

        if stock_ok(self.home_storage):
            options.append((hx, hy, "home", abs(hx - villager.x) + abs(hy - villager.y)))
        for building in self.buildings.values():
            if stock_ok(building):
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

        def pull(storage, key: str, amount: int) -> int:
            got = 0
            while (
                got < amount
                and getattr(storage, key) > 0
                and villager.inventory.can_add(1, key=key)
            ):
                setattr(storage, key, getattr(storage, key) - 1)
                setattr(villager.inventory, key, getattr(villager.inventory, key) + 1)
                got += 1
            return got

        def remaining_cap() -> int:
            return villager.inventory.capacity - villager.inventory.cargo_total

        storage = self.home_storage if kind == "home" else None
        if kind.startswith("b"):
            storage = self.buildings.get(int(kind[1:]))
        if storage is None:
            return
        if site.wood_needed > 0:
            pull(storage, "wood", min(site.wood_needed, remaining_cap()))
        if site.logs_needed > 0:
            pull(storage, "logs", min(site.logs_needed, remaining_cap()))
        if site.hardwood_needed > 0:
            pull(storage, "hardwood_logs", min(site.hardwood_needed, remaining_cap()))
        if site.rock_needed > 0:
            pull(storage, "rock", min(site.rock_needed, remaining_cap()))

    def _deposit_materials_at_site(self, villager: Villager, site: ConstructionSite) -> None:
        while site.wood_needed > 0 and villager.inventory.wood > 0:
            villager.inventory.wood -= 1
            site.have_wood += 1
            self.record_consumed("wood", 1)
        while site.logs_needed > 0 and villager.inventory.logs > 0:
            villager.inventory.logs -= 1
            site.have_logs += 1
            self.record_consumed("logs", 1)
        while site.hardwood_needed > 0 and villager.inventory.hardwood_logs > 0:
            villager.inventory.hardwood_logs -= 1
            site.have_hardwood += 1
            self.record_consumed("hardwood_logs", 1)
        while site.rock_needed > 0 and villager.inventory.rock > 0:
            villager.inventory.rock -= 1
            site.have_rock += 1
            self.record_consumed("rock", 1)

    def _update_workplace_worker(
        self, villager: Villager, building_id: int | None = None
    ) -> None:
        bid = building_id if building_id is not None else villager.building_id
        building = self.buildings.get(bid) if bid else None
        if building is None:
            if building_id is None:
                villager.clear_assignment()
            return
        if bid is not None:
            villager.building_id = bid

        if building.kind == BuildingKind.HUNTER:
            self._update_hunter(villager, building)
            return
        if building.kind == BuildingKind.FISHER:
            self._update_fisher(villager, building)
            return
        if building.kind == BuildingKind.FARM:
            self._update_farmer(villager, building)
            return
        if building.kind == BuildingKind.FORESTER:
            self._update_forester(villager, building)
            return
        if building.kind in (
            BuildingKind.MILL,
            BuildingKind.KITCHEN,
            BuildingKind.CRAFT_BENCH,
            BuildingKind.ALCHEMIST,
            BuildingKind.TAILOR,
            BuildingKind.COBBLER,
        ):
            self._update_processor(villager, building)
            return
        if building.kind == BuildingKind.MARKET:
            self._update_market(villager, building)
            return

        if self._gather_cargo_needs_delivery(villager, building):
            self._force_assigned_delivery(villager, building)
            return

        # Primary gather before storehouse supply / soft delivery.
        if self._workplace_primary_available(villager, building):
            pass
        elif self._maybe_assigned_transport(villager, building):
            return
        elif self._update_plant_stock_withdraw(villager, building):
            return
        elif self._workplace_accepts_carry(villager, building):
            self._force_assigned_delivery(villager, building)
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
            search_cd = int(getattr(villager, "_work_search_cd", 0))
            if search_cd > 0:
                villager._work_search_cd = search_cd - 1  # type: ignore[attr-defined]
                if self._workplace_accepts_carry(villager, building):
                    self._force_assigned_delivery(villager, building)
                    return
                self._set_workplace_idle(villager)
                return
            target = self._find_work_in_building(villager, building)
            if target is None:
                villager._work_search_cd = 48  # type: ignore[attr-defined]
                if self._maybe_assigned_transport(villager, building):
                    return
                if self._workplace_accepts_carry(villager, building):
                    self._force_assigned_delivery(villager, building)
                    return
                self._set_workplace_idle(villager)
                return
            villager._work_search_cd = 0  # type: ignore[attr-defined]
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

    def _update_forester(self, villager: Villager, building: Building) -> None:
        """Forester: choose collect / split / plant by recipe priority."""
        if self._gather_cargo_needs_delivery(villager, building):
            self._force_assigned_delivery(villager, building)
            return
        if self._forester_needs_axe(building) and not self._ensure_forester_axe(
            villager, building
        ):
            self._maybe_assigned_transport(villager, building)
            return
        # Collect / split / plant before storehouse sapling trips.
        if self._workplace_primary_available(villager, building):
            pass
        elif self._maybe_assigned_transport(villager, building):
            return
        elif self._update_plant_stock_withdraw(villager, building):
            return
        elif self._workplace_accepts_carry(villager, building):
            self._force_assigned_delivery(villager, building)
            return

        bx, by = building.center_cell()
        sticky = villager.target
        sticky_ok = False
        if sticky is not None:
            if sticky == (bx, by):
                sticky_ok = self._craftable_split_recipe(building, worker=villager) is not None
            elif not building.areas:
                sticky_ok = (
                    abs(sticky[0] - bx) + abs(sticky[1] - by) <= WORK_SEARCH_RADIUS
                    and self._work_target_valid(villager, building, sticky)
                )
            else:
                sticky_ok = self._work_target_valid(villager, building, sticky)
            if not sticky_ok:
                villager.target = None
                self._clear_villager_path(villager)
                sticky = None

        # Keep sticky collect/plant while walking/working — only re-scan when
        # idle, or when a craftable split should preempt field work.
        kind: str
        target: tuple[int, int]
        if sticky is not None and sticky_ok and sticky != (bx, by):
            split_recipe = self._craftable_split_recipe(building, worker=villager)
            if split_recipe is not None:
                target, kind = (bx, by), "split"
            else:
                target = sticky
                cell = self.world.get_cell(sticky[0], sticky[1])
                if cell is not None and self._cell_matches_manage_plant(
                    cell, can_plant_sapling=True
                ):
                    kind = "plant"
                else:
                    kind = "collect"
        elif sticky is not None and sticky_ok and sticky == (bx, by):
            target, kind = (bx, by), "split"
        else:
            pick = self._pick_forester_all_work(villager, building)
            if pick is None:
                self._maybe_assigned_transport(villager, building)
                return
            target, kind = pick

        if villager.target is not None and villager.target != target:
            self._clear_villager_path(villager)
        villager.target = target
        villager.state = VillagerState.WORKING
        if kind != "split":
            self._register_field_claim(villager, target)

        if (villager.x, villager.y) == target:
            if villager.work_cooldown > 0:
                return
            if kind == "split" or target == (bx, by):
                building.deposit_from_inventory(villager.inventory)
                if self._forester_try_split(villager, building):
                    return
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

    def _forester_has_nearby_tree_or_plant(
        self, villager: Villager, building: Building
    ) -> bool:
        """True if any chop/plant cell exists in range (no pathfinding)."""
        from trees import resolve_tree

        bx, by = building.center_cell()
        enabled_collect = {r.name for r in building.enabled_recipes()}
        can_plant_sapling = any(
            self._can_plant_recipe(villager, building, r.name)
            for r in building.enabled_plant_recipes()
        )
        allow_plant = building.allows_planting() and can_plant_sapling

        def cell_ok(x: int, y: int) -> bool:
            cell = self.world.get_cell(x, y)
            if cell is None or not self.world.is_walkable(x, y):
                return False
            if (
                cell.feature == FeatureType.TREE
                and cell.deposit > 0
                and resolve_tree(cell.tree_species).yield_key in enabled_collect
            ):
                return True
            return bool(
                allow_plant
                and self._cell_matches_manage_plant(cell, can_plant_sapling=True)
            )

        if building.areas:
            for area in building.areas:
                if area.task_type not in (
                    TaskType.CHOP_TREES,
                    TaskType.FULL_MANAGE,
                    TaskType.PLANT_SAPLINGS,
                ):
                    continue
                for x, y in area.cells():
                    if cell_ok(x, y):
                        return True
            return False

        r = min(16, WORK_SEARCH_RADIUS)  # cheap presence band
        rows, cols = self.world.rows, self.world.cols
        for y in range(max(0, by - r), min(rows, by + r + 1)):
            for x in range(max(0, bx - r), min(cols, bx + r + 1)):
                if abs(x - bx) + abs(y - by) > r:
                    continue
                if cell_ok(x, y):
                    return True
        return False

    def _pick_forester_all_work(
        self, villager: Villager, building: Building
    ) -> tuple[tuple[int, int], str] | None:
        """Return (target, kind) for ALL mode using recipe priorities.

        ``kind`` is ``split``, ``collect``, or ``plant``. Lower priority number
        wins; ties prefer split, then collect, then plant.
        """
        candidates: list[tuple[int, int, tuple[int, int], str]] = []

        split_recipe = self._craftable_split_recipe(building, worker=villager)
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
            for recipe in building.enabled_plant_recipes():
                if not self._can_plant_recipe(villager, building, recipe.name):
                    continue
                plant = self._find_forester_plant_target(
                    villager, building, claimed, recipe_name=recipe.name
                )
                if plant is not None:
                    candidates.append(
                        (
                            building.get_recipe_priority(recipe.name),
                            2,
                            plant,
                            "plant",
                        )
                    )
                    break

        if not candidates:
            return None
        candidates.sort()
        _prio, _tie, target, kind = candidates[0]
        return target, kind

    def _find_forester_collect_by_priority(
        self, villager: Villager, building: Building
    ) -> tuple[tuple[int, int], int] | None:
        """Best collect target: nearby first, then recipe priority within each band."""
        claimed = self._claimed_work_cells(villager.id)
        origin = (
            (villager.x, villager.y)
            if building.areas
            else building.center_cell()
        )
        ox, oy = origin
        band = max(1, int(FORAGER_PRIORITY_BAND))
        candidates: list[tuple[int, int, int, tuple[int, int], int]] = []
        for recipe in building.enabled_recipes():
            target = self._find_forester_tree_target(
                villager, building, recipe.name, claimed
            )
            if target is None:
                continue
            dist = abs(target[0] - ox) + abs(target[1] - oy)
            prio = building.get_recipe_priority(recipe.name)
            candidates.append((dist // band, prio, dist, target, prio))
        if not candidates:
            return None
        candidates.sort()
        _band, _p, _d, target, prio = candidates[0]
        return target, prio

    def _find_forester_tree_target(
        self,
        villager: Villager,
        building: Building,
        yield_key: str,
        claimed: set[tuple[int, int]],
    ) -> tuple[int, int] | None:
        """Closest reachable tree whose species yields ``yield_key``.

        With drawn areas, search those cells from the villager. Without areas,
        only consider trees within ``WORK_SEARCH_RADIUS`` of the building.
        """
        from trees import resolve_tree

        bx, by = building.center_cell()
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
        else:
            r = WORK_SEARCH_RADIUS
            rows, cols = self.world.rows, self.world.cols
            for y in range(max(0, by - r), min(rows, by + r + 1)):
                for x in range(max(0, bx - r), min(cols, bx + r + 1)):
                    if abs(x - bx) + abs(y - by) > r:
                        continue
                    consider(x, y)

        # Rank by distance from the workplace. Path cache is only seeded when
        # origin == villager pos, so this will not soft-lock movement.
        return self._pick_nearest_reachable(
            (bx, by),
            cells,
            pos_fn=lambda p: p,
            villager=villager,
            max_radius=WORK_SEARCH_RADIUS,
        )

    def _find_forester_plant_target(
        self,
        villager: Villager,
        building: Building,
        claimed: set[tuple[int, int]],
        *,
        recipe_name: str | None = None,
    ) -> tuple[int, int] | None:
        if recipe_name is not None and not self._can_plant_recipe(
            villager, building, recipe_name
        ):
            return None
        can_plant_sapling = recipe_name is None or self._can_plant_recipe(
            villager, building, recipe_name
        )
        if not can_plant_sapling:
            return None
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
            return self._pick_nearest_reachable(
                (villager.x, villager.y),
                plant,
                pos_fn=lambda p: p,
                villager=villager,
                max_radius=WORK_SEARCH_RADIUS,
            )
        ox, oy = building.center_cell()
        return self._find_closest_manage_plant_cell(
            ox, oy, can_plant_sapling=True, exclude_cells=claimed
        )

    def _farm_barn_has_work(
        self, villager: Villager, building: Building
    ) -> bool:
        """True when barn thresh or sheaf buffer top-up should run."""
        if building.kind != BuildingKind.FARM:
            return False
        if self._farm_barn_craft_available(villager, building):
            return True
        return self._farm_barn_needs_sheaf_delivery(building)

    def _farm_has_pending_field_work(
        self, villager: Villager, building: Building
    ) -> bool:
        """True when sow/harvest/weed/plough tiles exist (used by clear latch)."""
        if not self._fields_near_farm(building):
            return False
        if self._find_farm_harvest(villager, building, in_season_only=True) is not None:
            return True
        if self._find_farm_sow_work(villager, building) is not None:
            return True
        if self._find_farm_weed_work(villager, building) is not None:
            return True
        return self._find_farm_plough_work(villager, building) is not None

    def _farm_sow_waiting_on_barn_grain(
        self, villager: Villager, building: Building
    ) -> bool:
        """Unsown plant-phase tiles need wheat/rye grain that the barn can thresh."""
        if building.kind != BuildingKind.FARM or not building.addon_craft_recipes():
            return False
        if not self._farm_has_unsown_soil(villager, building):
            return False
        needed = set(self._farm_needed_seed_keys(building))
        grain = needed & {"wheat_grain", "rye_grain"}
        if not grain:
            return False
        if any(
            self._plant_stock_at(building, key) > 0
            or int(getattr(villager.inventory, key, 0)) > 0
            for key in grain
        ):
            return False
        return self._farm_barn_craft_available(
            villager, building
        ) or self._farm_barn_needs_sheaf_delivery(building)

    def _coworker_addon_craft_claims(
        self, building: Building, villager_id: int
    ) -> frozenset[str]:
        """Addon recipe names reserved by in-progress craft or a coworker."""
        building.ensure_recipe_state()
        names: set[str] = set()
        villager = next((v for v in self.villagers if v.id == villager_id), None)
        own_craft = villager.craft_recipe_name if villager is not None else None
        for recipe in building.addon_craft_recipes():
            if int(building.recipe_progress.get(recipe.name, 0)) > 0:
                if recipe.name != own_craft:
                    names.add(recipe.name)
        bx, by = building.center_cell()
        for other in self.villagers:
            if other.id == villager_id or other.building_id != building.id:
                continue
            name = other.craft_recipe_name
            if not name:
                continue
            if other.state not in (VillagerState.WORKING, VillagerState.IDLE):
                continue
            if (other.x, other.y) == (bx, by) or other.target == (bx, by):
                names.add(name)
        return frozenset(names)

    # ------------------------------------------------------------------
    # Farm pipeline job board
    # ------------------------------------------------------------------
    def _farm_parse_job_kind(self, villager: Villager) -> FarmJobKind | None:
        raw = getattr(villager, "farm_job_kind", None)
        if not raw:
            return None
        try:
            return FarmJobKind[str(raw)]
        except KeyError:
            villager.farm_job_kind = None
            return None

    def _farm_clear_job(self, villager: Villager) -> None:
        villager.farm_job_kind = None
        villager.craft_recipe_name = None
        if villager.state == VillagerState.WORKING:
            villager.target = None
            self._clear_villager_path(villager)

    def _farm_thresh_slot_taken(
        self, building: Building, villager_id: int
    ) -> bool:
        site = self._farm_thresh_site(building)
        for other in self.villagers:
            if other.id == villager_id:
                continue
            if building.id not in self._villager_workplace_ids(other):
                continue
            if getattr(other, "farm_job_kind", None) == FarmJobKind.THRESH.name:
                return True
            if other.craft_recipe_name and other.state == VillagerState.WORKING:
                if other.target == site or (other.x, other.y) == site:
                    return True
        return False

    def _farm_can_take_logistics(
        self, villager: Villager, building: Building
    ) -> bool:
        """Assigned farmer may fetch/export if haul claim is free or owned."""
        if self._owns_haul_claim(villager, building.id):
            return True
        claimers = [
            v
            for v in self.villagers
            if v.haul_building_id == building.id
            and v.state in (VillagerState.HAULING, VillagerState.DELIVERING)
        ]
        return not claimers

    def _farm_board_has_work(
        self, villager: Villager, building: Building
    ) -> bool:
        return self._assign_farm_job(villager, building, preview=True) is not None

    def _farm_job_still_valid(
        self, villager: Villager, building: Building, kind: FarmJobKind
    ) -> bool:
        if kind == FarmJobKind.DELIVER:
            return self._gather_cargo_needs_delivery(
                villager, building
            ) or building.has_gather_cargo(villager.inventory)
        if kind == FarmJobKind.THRESH:
            return self._farm_barn_craft_available(villager, building)
        if kind == FarmJobKind.SEED_FETCH:
            return self._farm_has_unsown_soil(
                villager, building
            ) and self._workplace_needs_home_supply(building)
        if kind == FarmJobKind.SHEAF_FETCH:
            carrying = any(
                int(getattr(villager.inventory, k, 0)) > 0 for k in barn_sheaf_keys()
            )
            return carrying or self._farm_barn_needs_sheaf_delivery(building)
        if kind == FarmJobKind.EXPORT:
            # Finish the outbound trip before looking for more clear work.
            if not villager.inventory.is_empty:
                return True
            return building.haulable_total() > 0 and (
                self._farm_or_processor_needs_clear(building)
                or building.space_left <= 0
                or any(
                    building.haulable_amount(k) > 0
                    for k in ("wheat_grain", "rye_grain", "wheat", "rye", "straw")
                )
            )
        if kind in (
            FarmJobKind.SOW,
            FarmJobKind.HARVEST,
            FarmJobKind.WEED,
            FarmJobKind.PLOUGH,
        ):
            cell = villager.target
            if cell is None:
                return False
            return self._farm_target_still_valid(villager, building, cell)
        return False

    def _assign_farm_job(
        self,
        villager: Villager,
        building: Building,
        *,
        preview: bool = False,
    ) -> FarmJob | None:
        """Pick the highest-priority open job for this farmer (pipeline order)."""
        bid = building.id

        # Full harvest pack: unload sheaves to barn / produce to farm.
        # Grain/straw packs are EXPORT (mill / storehouse) — never bounce at farm.
        if not villager.inventory.is_empty:
            if (
                getattr(villager, "farm_job_kind", None) == FarmJobKind.EXPORT.name
                or self._farm_pack_has_export_cargo(villager.inventory, villager)
            ):
                return FarmJob(FarmJobKind.EXPORT, bid)
            if self._gather_cargo_needs_delivery(
                villager, building
            ) or self._farm_pack_needs_barn_or_farm_unload(villager, building):
                return FarmJob(FarmJobKind.DELIVER, bid)

        if self._fields_near_farm(building):
            sow = self._find_farm_sow_work(villager, building)
            if sow is not None:
                if not preview and not self._ensure_work_tool(villager, "hoe"):
                    sow = None
                if sow is not None:
                    return FarmJob(FarmJobKind.SOW, bid, cell=sow)

            harvest = self._find_farm_harvest(
                villager, building, in_season_only=True
            )
            if harvest is not None:
                if not preview and not self._ensure_work_tool(villager, "hoe"):
                    harvest = None
                if harvest is not None:
                    return FarmJob(FarmJobKind.HARVEST, bid, cell=harvest)

            hoe_ok = preview or self._ensure_work_tool(villager, "hoe")
            if hoe_ok:
                weed = self._find_farm_weed_work(villager, building)
                if weed is not None:
                    return FarmJob(FarmJobKind.WEED, bid, cell=weed)
                plough = self._find_farm_plough_work(villager, building)
                if plough is not None:
                    return FarmJob(FarmJobKind.PLOUGH, bid, cell=plough)
                leftover = self._find_farm_harvest(villager, building)
                if leftover is not None:
                    return FarmJob(FarmJobKind.HARVEST, bid, cell=leftover)

        if self._farm_barn_craft_available(villager, building):
            if preview or not self._farm_thresh_slot_taken(building, villager.id):
                return FarmJob(FarmJobKind.THRESH, bid)

        # Idle farmers top up the barn — no haul-claim required.
        if self._farm_barn_needs_sheaf_delivery(building):
            carrying = any(
                int(getattr(villager.inventory, k, 0)) > 0 for k in barn_sheaf_keys()
            )
            fetchers = sum(
                1
                for o in self.villagers
                if o.id != villager.id
                and getattr(o, "farm_job_kind", None) == FarmJobKind.SHEAF_FETCH.name
                and building.id in self._villager_workplace_ids(o)
            )
            if preview or carrying or fetchers < 2:
                return FarmJob(FarmJobKind.SHEAF_FETCH, bid)

        if (
            self._farm_has_unsown_soil(villager, building)
            and self._find_farm_sow_work(villager, building) is None
            and self._workplace_needs_home_supply(building)
            and self._farm_can_take_logistics(villager, building)
        ):
            demand = self._building_supply_demand(building)
            seed_demand = {k: v for k, v in demand.items() if k in SEED_KEYS}
            if seed_demand:
                return FarmJob(FarmJobKind.SEED_FETCH, bid)

        if (
            building.haulable_total() > 0
            and self._farm_can_take_logistics(villager, building)
            and not self._general_hauler_serving(building.id)
        ):
            if (
                self._farm_or_processor_needs_clear(building)
                or building.space_left <= 0
                or any(
                    building.haulable_amount(k) > 0
                    for k in ("wheat_grain", "rye_grain")
                )
            ):
                return FarmJob(FarmJobKind.EXPORT, bid)

        return None

    def _execute_farm_job(
        self, villager: Villager, building: Building, kind: FarmJobKind
    ) -> None:
        if kind == FarmJobKind.DELIVER:
            if self._farm_pack_has_export_cargo(villager.inventory, villager):
                villager.farm_job_kind = FarmJobKind.EXPORT.name
                self._farm_finish_export_trip(villager, building)
                return
            self._force_assigned_delivery(villager, building)
            if villager.inventory.is_empty:
                villager.farm_job_kind = None
            elif self._farm_pack_has_export_cargo(villager.inventory, villager):
                villager.farm_job_kind = FarmJobKind.EXPORT.name
            return

        if kind == FarmJobKind.THRESH:
            if self._try_addon_craft(villager, building):
                return
            villager.farm_job_kind = None
            return

        if kind == FarmJobKind.SEED_FETCH:
            if self._update_plant_stock_withdraw(villager, building):
                return
            if self._maybe_assigned_transport(villager, building):
                return
            villager.farm_job_kind = None
            return

        if kind == FarmJobKind.SHEAF_FETCH:
            self._execute_farm_sheaf_fetch(villager, building)
            return

        if kind == FarmJobKind.EXPORT:
            if not villager.inventory.is_empty:
                self._farm_finish_export_trip(villager, building)
                return
            if self._clear_backed_up_outputs_to_home(villager, building):
                villager.farm_job_kind = FarmJobKind.EXPORT.name
                return
            villager.farm_job_kind = None
            return

        if not self._ensure_work_tool(villager, "hoe"):
            self._maybe_assigned_transport(villager, building)
            return
        target = villager.target
        if target is None or not self._farm_target_still_valid(
            villager, building, target
        ):
            villager.farm_job_kind = None
            villager.target = None
            return
        claimed = self._claimed_work_cells(villager.id)
        if target in claimed:
            villager.farm_job_kind = None
            villager.target = None
            return
        self._register_field_claim(villager, target)
        villager.state = VillagerState.WORKING
        if (villager.x, villager.y) == target:
            if villager.work_cooldown == 0:
                self._villager_perform_farm(villager, building, target)
                villager.work_cooldown = self._villager_work_interval(villager)
                villager.target = None
                villager.farm_job_kind = None
                self._clear_villager_path(villager)
                if self._farm_pack_has_export_cargo(villager.inventory, villager) and (
                    self._gather_cargo_needs_delivery(villager, building)
                    or not villager.inventory.can_add(1)
                ):
                    villager.farm_job_kind = FarmJobKind.EXPORT.name
                    self._farm_finish_export_trip(villager, building)
                elif self._gather_cargo_needs_delivery(villager, building):
                    villager.farm_job_kind = FarmJobKind.DELIVER.name
                    self._force_assigned_delivery(villager, building)
        else:
            self._step_or_clear_field_target(villager, target)

    def _update_farmer(self, villager: Villager, building: Building) -> None:
        """Farm pipeline: claim one job, run it to completion."""
        job_name = getattr(villager, "farm_job_kind", None)

        # Mid-trip export must reach mill/storehouse — never re-deposit on the farm.
        if (
            not villager.inventory.is_empty
            and (
                job_name == FarmJobKind.EXPORT.name
                or self._farm_pack_has_export_cargo(villager.inventory, villager)
            )
        ):
            self._farm_finish_export_trip(villager, building)
            return

        if villager.state in (VillagerState.HAULING, VillagerState.DELIVERING):
            if job_name == FarmJobKind.DELIVER.name or self._farm_pack_needs_barn_or_farm_unload(
                villager, building
            ):
                if self._update_assigned_transport(villager, building):
                    return
            elif self._update_assigned_transport(villager, building):
                return
            villager.farm_job_kind = None

        kind = self._farm_parse_job_kind(villager)
        if kind is not None and not self._farm_job_still_valid(
            villager, building, kind
        ):
            self._farm_clear_job(villager)
            kind = None

        if kind is None:
            job = self._assign_farm_job(villager, building)
            if job is None:
                self._set_workplace_idle(villager)
                return
            villager.farm_job_kind = job.kind.name
            kind = job.kind
            if job.cell is not None:
                villager.target = job.cell
                self._register_field_claim(villager, job.cell)
                villager.state = VillagerState.WORKING

        self._execute_farm_job(villager, building, kind)

    def _update_processor(self, villager: Villager, building: Building) -> None:
        """Mill / Kitchen / Craft bench: stay on-site and craft from building stock."""
        required = WORKPLACE_TOOL.get(building.kind)
        if required is not None and not self._ensure_work_tool(villager, required):
            if self._maybe_assigned_transport(villager, building):
                return
            return

        # Craft when possible; otherwise fetch storehouse inputs; clear full outputs;
        # deposit last.
        if self._workplace_primary_available(villager, building):
            pass
        elif self._maybe_assigned_transport(villager, building):
            return
        elif self._processor_should_clear(building, villager):
            # Hauler is already clearing, or we just queued transport above.
            # Stay on-site so the picker does not bounce the cook to P2.
            if self._general_hauler_serving(building.id):
                bx, by = building.center_cell()
                villager.target = (bx, by)
                villager.state = VillagerState.WORKING
                if (villager.x, villager.y) != (bx, by):
                    self._step_villager_toward(villager, (bx, by))
                return
            if self._clear_backed_up_outputs_to_home(villager, building):
                return
            self._set_workplace_idle(villager)
            return
        elif self._workplace_accepts_carry(villager, building):
            self._force_assigned_delivery(villager, building)
            return
        else:
            self._set_workplace_idle(villager)
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

        claimed: set[str] = set()
        for other in self.villagers:
            if other.id == villager.id:
                continue
            if other.building_id != building.id:
                continue
            name = other.craft_recipe_name
            if name:
                claimed.add(name)

        recipe = self._craftable_recipe(
            building,
            worker=villager,
            prefer_name=villager.craft_recipe_name,
            avoid_names=claimed,
        )
        if recipe is None:
            villager.craft_recipe_name = None
            return
        villager.craft_recipe_name = recipe.name
        if villager.work_cooldown > 0:
            return
        self._spend_work_energy(villager)
        if building.advance_recipe_progress(recipe):
            fuel = 1 if building.kind == BuildingKind.KITCHEN else 0
            self._apply_recipe_tracked(building, recipe, fuel_wood=fuel)
            if fuel:
                building.fuel_wood = max(0, building.fuel_wood - 1)
            self._gain_job_skill(villager, building.kind.name)
        villager.work_cooldown = self._villager_work_interval(villager)

    def _try_addon_craft(self, villager: Villager, building: Building) -> bool:
        """Farm barn / hunter drying-rack crafts on the parent workplace."""
        recipes = building.addon_craft_recipes()
        if not recipes:
            return False

        barn = (
            self._linked_barn(building)
            if building.kind == BuildingKind.FARM
            else None
        )
        if barn is not None:
            return self._try_barn_thresh(villager, building, barn, recipes)

        bx, by = building.center_cell()
        at_site = (villager.x, villager.y) == (bx, by)
        if at_site:
            building.deposit_from_inventory(villager.inventory)

        claimed = self._coworker_addon_craft_claims(building, villager.id)
        stock = self._village_stock_amounts()
        prefer = villager.craft_recipe_name
        if prefer in claimed:
            prefer = None
        ordered = list(recipes)
        if prefer:
            ordered.sort(key=lambda r: 0 if r.name == prefer else 1)

        def _carries_inputs(recipe) -> bool:
            for key, need in recipe.inputs.items():
                have = int(getattr(building, key, 0)) + int(
                    getattr(villager.inventory, key, 0)
                )
                if have < int(need):
                    return False
            return True

        ready = None
        for candidate in ordered:
            if candidate.name in claimed:
                continue
            if not building.is_recipe_enabled(candidate.name):
                continue
            probe = self._craftable_recipe(
                building,
                worker=villager,
                prefer_name=candidate.name,
                avoid_names=claimed,
                stock_amounts=stock,
            )
            if probe is not None and probe.name == candidate.name:
                ready = probe
                break

        if ready is None:
            resume = villager.craft_recipe_name
            if resume and int(building.recipe_progress.get(resume, 0)) > 0:
                ready = next((r for r in recipes if r.name == resume), None)
            if ready is None:
                villager.craft_recipe_name = None
                if not at_site:
                    for candidate in ordered:
                        if candidate.name in claimed:
                            continue
                        if not building.is_recipe_enabled(candidate.name):
                            continue
                        if _carries_inputs(candidate):
                            villager.craft_recipe_name = candidate.name
                            villager.target = (bx, by)
                            villager.state = VillagerState.WORKING
                            if villager.move_cooldown > 0:
                                return True
                            self._step_villager_toward(villager, (bx, by))
                            return True
                    for candidate in ordered:
                        if candidate.name in claimed:
                            continue
                        probe = self._craftable_recipe(
                            building,
                            worker=villager,
                            prefer_name=candidate.name,
                            avoid_names=claimed,
                            stock_amounts=stock,
                        )
                        if probe is not None:
                            villager.craft_recipe_name = probe.name
                            villager.target = (bx, by)
                            villager.state = VillagerState.WORKING
                            if villager.move_cooldown > 0:
                                return True
                            self._step_villager_toward(villager, (bx, by))
                            return True
                return False

        # Leather needs a knife; barn threshing needs no tool (hoe is plough/weed only).
        if building.kind == BuildingKind.HUNTER:
            if not self._ensure_work_tool(villager, "knife"):
                return False

        recipe = ready
        villager.target = (bx, by)
        villager.state = VillagerState.WORKING
        if not at_site:
            if villager.move_cooldown > 0:
                return True
            self._step_villager_toward(villager, (bx, by))
            return True

        building.deposit_from_inventory(villager.inventory)
        villager.craft_recipe_name = recipe.name
        if villager.work_cooldown > 0:
            return True
        self._spend_work_energy(villager)
        if building.advance_recipe_progress(recipe):
            self._apply_recipe_tracked(building, recipe)
            self._gain_job_skill(villager, building.kind.name)
        villager.work_cooldown = self._villager_work_interval(villager)
        return True

    def _try_barn_thresh(
        self, villager: Villager, farm: Building, barn: Building, recipes
    ) -> bool:
        """Thresh at the barn: consume barn sheaves, grain/straw land on the farm."""
        site = barn.center_cell()
        at_site = (villager.x, villager.y) == site
        if at_site:
            self._deposit_sheaves_to_barn(farm, villager.inventory)

        claimed = self._coworker_addon_craft_claims(farm, villager.id)
        prefer = villager.craft_recipe_name
        if prefer in claimed:
            prefer = None
        ordered = list(recipes)
        if prefer:
            ordered.sort(key=lambda r: 0 if r.name == prefer else 1)

        ready = None
        for candidate in ordered:
            if candidate.name in claimed:
                continue
            if self._barn_thresh_recipe_ready(farm, villager, candidate):
                ready = candidate
                break

        if ready is None:
            resume = villager.craft_recipe_name
            if resume and int(farm.recipe_progress.get(resume, 0)) > 0:
                # Finish an in-progress craft if inputs are still available.
                cand = next((r for r in recipes if r.name == resume), None)
                if cand is not None and self._barn_thresh_recipe_ready(
                    farm, villager, cand
                ):
                    ready = cand
            if ready is None:
                villager.craft_recipe_name = None
                if not at_site and self._farm_barn_craft_available(villager, farm):
                    villager.target = site
                    villager.state = VillagerState.WORKING
                    if villager.move_cooldown > 0:
                        return True
                    self._step_villager_toward(villager, site)
                    return True
                return False

        villager.target = site
        villager.state = VillagerState.WORKING
        if not at_site:
            if villager.move_cooldown > 0:
                return True
            self._step_villager_toward(villager, site)
            return True

        self._deposit_sheaves_to_barn(farm, villager.inventory)
        villager.craft_recipe_name = ready.name
        if villager.work_cooldown > 0:
            return True
        self._spend_work_energy(villager)
        if farm.advance_recipe_progress(ready):
            self._apply_barn_thresh_recipe(farm, ready, villager.inventory)
            self._gain_job_skill(villager, farm.kind.name)
        villager.work_cooldown = self._villager_work_interval(villager)
        return True

    def _market_storehouse_surplus(self, key: str, reserve: int) -> int:
        """Storehouse units of ``key`` above the configured supply reserve."""
        have = int(getattr(self.home_storage, key, 0))
        return max(0, have - max(0, int(reserve)))

    def _market_offer_amount(self, building: Building, key: str) -> int:
        """Units available toward demand (stall stock + haulable surplus, capped)."""
        if not building.market_supply_enabled(key):
            return 0
        demand = building.market_demand_remaining(key)
        if demand <= 0:
            return 0
        at_market = int(getattr(building, key, 0))
        surplus = self._market_storehouse_surplus(key, building.market_supply_min(key))
        target = building.market_stock_target(key)
        if target <= 0:
            return 0
        return min(demand, target, at_market + surplus)

    def _market_can_sell(self, building: Building) -> bool:
        """True when stall has an enabled good with remaining demand."""
        from market_economy import MARKET_PRICES

        for key in building.market_supply_mins:
            if building.market_demand_remaining(key) <= 0:
                continue
            if int(getattr(building, key, 0)) <= 0:
                continue
            if int(MARKET_PRICES.get(key, 0)) > 0:
                return True
        return False

    def _market_try_sell(self, building: Building) -> bool:
        """Sell one stall unit into regional wealth (goods must be on-site)."""
        import random

        from market_economy import MARKET_PRICES

        candidates: list[str] = []
        for key in building.market_supply_mins:
            if building.market_demand_remaining(key) <= 0:
                continue
            if int(getattr(building, key, 0)) <= 0:
                continue
            if int(MARKET_PRICES.get(key, 0)) <= 0:
                continue
            candidates.append(key)
        if not candidates:
            return False
        key = random.choice(candidates)
        price = int(MARKET_PRICES[key])
        have = int(getattr(building, key, 0))
        if have <= 0:
            return False
        setattr(building, key, have - 1)
        self.regional_wealth = int(self.regional_wealth) + price
        demand_left = int(building.market_demand.get(key, 0)) - 1
        if demand_left <= 0:
            building.market_demand.pop(key, None)
        else:
            building.market_demand[key] = demand_left
        self.record_consumed(key, 1)
        self.record_produced("coins", price)
        return True

    def _market_sell_chance(self, building: Building) -> float:
        """Scale sale odds so remaining stall stock tends to clear over the season."""
        from seasons import DAYS_PER_SEASON, day_in_season
        from market_economy import MARKET_SELL_INTERVAL

        remaining = sum(
            min(
                building.market_demand_remaining(key),
                int(getattr(building, key, 0)),
            )
            for key in building.market_supply_mins
        )
        if remaining <= 0:
            return 0.0
        days_left = DAYS_PER_SEASON - day_in_season(self.calendar_day)
        day_frac = max(0.0, float(self.day_tick) / max(1, self.ticks_per_day))
        days_left_f = max(0.2, float(days_left - 1) + day_frac)
        attempts = max(1.0, days_left_f * self.ticks_per_day / max(1, MARKET_SELL_INTERVAL))
        return min(0.9, remaining / attempts)

    def _refresh_market_demands(self) -> None:
        """Regenerate each market's seasonal demand board (supply mins persist)."""
        from market_economy import generate_seasonal_demand

        season = self.season
        for building in self.buildings.values():
            if not building.is_market():
                continue
            building.market_demand = generate_seasonal_demand(season, self._drop_rng)
            building.market_demand_season = season.name

    def _ensure_market_demand(self, building: Building) -> None:
        """Fill demand if missing or stale relative to the current season."""
        if not building.is_market():
            return
        if (
            building.market_demand
            and building.market_demand_season == self.season.name
        ):
            return
        from market_economy import generate_seasonal_demand

        building.market_demand = generate_seasonal_demand(self.season, self._drop_rng)
        building.market_demand_season = self.season.name

    def _absorb_coins_to_wealth(self) -> None:
        """Move any leftover coin stock into regional wealth (no physical coins)."""
        total = 0
        for key_holder in (self.home_storage, self.player.inventory):
            n = int(getattr(key_holder, "coins", 0))
            if n > 0:
                setattr(key_holder, "coins", 0)
                total += n
        for building in self.buildings.values():
            n = int(getattr(building, "coins", 0))
            if n > 0:
                building.coins = 0
                total += n
        for villager in self.villagers:
            n = int(getattr(villager.inventory, "coins", 0))
            if n > 0:
                villager.inventory.coins = 0
                total += n
        if total > 0:
            self.regional_wealth = int(self.regional_wealth) + total

    def _update_market(self, villager: Villager, building: Building) -> None:
        """Deposit haul, then sell stall stock against seasonal demand."""
        from market_economy import MARKET_SELL_INTERVAL

        self._ensure_market_demand(building)

        if self._workplace_primary_available(villager, building):
            pass
        elif self._maybe_assigned_transport(villager, building):
            return
        elif building.haulable_total() > 0 and not self._general_hauler_serving(
            building.id
        ):
            if self._clear_backed_up_outputs_to_home(villager, building):
                return
            self._set_workplace_idle(villager)
            return
        elif self._workplace_accepts_carry(villager, building):
            self._force_assigned_delivery(villager, building)
            return
        else:
            if not self._market_can_sell(building):
                self._set_workplace_idle(villager)
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

        if villager.work_cooldown > 0:
            return
        if self._market_can_sell(building):
            import random

            self._spend_work_energy(villager)
            if random.random() < self._market_sell_chance(building) and self._market_try_sell(
                building
            ):
                self._gain_job_skill(villager, building.kind.name)
            villager.work_cooldown = max(
                self._villager_work_interval(villager), MARKET_SELL_INTERVAL
            )
            return
        villager.work_cooldown = self._villager_work_interval(villager)

    def _find_farm_harvest(
        self,
        villager: Villager,
        building: Building,
        *,
        in_season_only: bool = False,
    ) -> tuple[int, int] | None:
        """Closest ripe crop on a nearby field.

        ``in_season_only`` skips leftover ripe tiles whose crop is not in a
        harvest phase, so they cannot block plough / plant / thresh.
        """
        if not villager.inventory.can_add(1):
            return None
        if building.space_left <= 0 and building.cargo_stored_total > 0:
            return None
        claimed = self._claimed_work_cells(villager.id)
        cache = getattr(self, "_tick_farm_harvest", None)
        cache_key = (building.id, in_season_only)
        tiles = None if cache is None else cache.get(cache_key)
        if tiles is None:
            tiles = []
            for field_b in self._fields_near_farm(building):
                for x, y in field_b.plot_cells():
                    if not self.world.is_walkable(x, y):
                        continue
                    if not self.world.crop_herb_ready(x, y):
                        continue
                    if in_season_only:
                        cell = self.world.get_cell(x, y)
                        crop_key = (
                            getattr(cell, "crop_kind", None) if cell is not None else None
                        )
                        crop = CROP_BY_KEY.get(crop_key or "", None)
                        if crop is None or not phase_allows_harvest(
                            phase_for_crop(crop, self.season)
                        ):
                            continue
                    tiles.append((x, y))
            if cache is not None:
                cache[cache_key] = tiles
        harvest = [pos for pos in tiles if pos not in claimed]
        return self._closest_of((villager.x, villager.y), harvest)

    def _farm_weed_hoe_threshold(self) -> float:
        """Cover at which farmers hoe.

        Saves may still have the old 0.2 default; clamp so workers clear the UI
        "watch weed cover" band (~0.10+) instead of idling/threshing beside it.
        """
        configured = float(self.balance.get_float("WEED_ACTION_THRESHOLD"))
        return min(max(0.05, configured), 0.1)

    def _find_farm_weed_work(
        self, villager: Villager, building: Building
    ) -> tuple[int, int] | None:
        """Closest crop tile whose weeds need the hoe (not a harvest)."""
        threshold = self._farm_weed_hoe_threshold()
        claimed = self._claimed_work_cells(villager.id)
        cache = getattr(self, "_tick_farm_weed", None)
        cache_key = (building.id, round(threshold, 3))
        tiles = None if cache is None else cache.get(cache_key)
        if tiles is None:
            tiles = []
            for field_b in self._fields_near_farm(building):
                for x, y in field_b.plot_cells():
                    if not self.world.is_walkable(x, y):
                        continue
                    cell = self.world.get_cell(x, y)
                    if cell is None or cell.feature != FeatureType.CROP_HERB:
                        continue
                    if float(getattr(cell, "weeds", 0.0)) >= threshold:
                        tiles.append((x, y))
            if cache is not None:
                cache[cache_key] = tiles
        weedy = [pos for pos in tiles if pos not in claimed]
        return self._closest_of((villager.x, villager.y), weedy)

    def _farm_target_still_valid(
        self, villager: Villager, building: Building, pos: tuple[int, int]
    ) -> bool:
        """True if a sticky farm tile is still worth working."""
        x, y = pos
        if not self.world.is_walkable(x, y):
            return False
        cell = self.world.get_cell(x, y)
        if cell is None:
            return False
        if cell.feature == FeatureType.CROP_HERB:
            if float(getattr(cell, "weeds", 0.0)) >= self._farm_weed_hoe_threshold():
                return True
            if self.world.crop_herb_ready(x, y):
                return villager.inventory.can_add(1)
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

    def _find_farm_sow_work(
        self, villager: Villager, building: Building
    ) -> tuple[int, int] | None:
        """Closest soil tile that can be sown with local seed stock."""
        cache = getattr(self, "_tick_farm_sow", None)
        tiles = None if cache is None else cache.get(building.id)
        if tiles is None:
            tiles = []
            season = self.season
            for field_b in self._fields_near_farm(building):
                for plan in field_b.plans:
                    crop = CROP_BY_KEY.get(plan.crop_kind, CROP_BY_KEY["sage"])
                    phase = phase_for_crop(crop, season)
                    if not phase_allows_plough_plant(phase):
                        continue
                    seed_key = crop.seed_key
                    for x, y in plan.cells():
                        if not self.world.is_walkable(x, y):
                            continue
                        cell = self.world.get_cell(x, y)
                        if cell is None or cell.feature == FeatureType.CROP_HERB:
                            continue
                        if cell.terrain in SOIL_LIKE and cell.feature == FeatureType.NONE:
                            tiles.append((x, y, seed_key))
            if cache is not None:
                cache[building.id] = tiles
        claimed = self._claimed_work_cells(villager.id)
        sow: list[tuple[int, int]] = []
        for x, y, seed_key in tiles:
            if (x, y) in claimed:
                continue
            can_sow = (
                getattr(villager.inventory, seed_key, 0) > 0
                or self._plant_stock_at(building, seed_key) > 0
            )
            if not can_sow:
                continue
            if getattr(villager.inventory, seed_key, 0) > 0 or villager.inventory.can_add(
                1, key=seed_key
            ):
                sow.append((x, y))
        return self._closest_of((villager.x, villager.y), sow)

    def _find_farm_plough_work(
        self, villager: Villager, building: Building
    ) -> tuple[int, int] | None:
        """Closest tile that still needs ploughing for a current plant plan."""
        claimed = self._claimed_work_cells(villager.id)
        plough: list[tuple[int, int]] = []
        season = self.season
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
            FeatureType.TAILOR,
            FeatureType.MARKET,
            FeatureType.CONSTRUCTION_SITE,
            FeatureType.STRUCTURE_PAD,
        )
        for field_b in self._fields_near_farm(building):
            for plan in field_b.plans:
                crop = CROP_BY_KEY.get(plan.crop_kind, CROP_BY_KEY["sage"])
                phase = phase_for_crop(crop, season)
                if not phase_allows_plough_plant(phase):
                    continue
                for x, y in plan.cells():
                    if (x, y) in claimed:
                        continue
                    if not self.world.is_walkable(x, y):
                        continue
                    cell = self.world.get_cell(x, y)
                    if cell is None or cell.feature == FeatureType.CROP_HERB:
                        continue
                    if cell.terrain in SOIL_LIKE and cell.feature == FeatureType.NONE:
                        continue
                    if is_water_terrain(cell.terrain) or cell.terrain == TerrainType.ROCK:
                        continue
                    if cell.feature not in blocked:
                        plough.append((x, y))
        return self._closest_of((villager.x, villager.y), plough)

    def _farm_has_unsown_soil(self, villager: Villager, building: Building) -> bool:
        """True when a plan has ploughed soil ready to sow (seeds may be missing)."""
        return any(n > 0 for n in self._farm_unsown_seed_counts(building).values())

    def _find_farm_plant_work(
        self, villager: Villager, building: Building
    ) -> tuple[int, int] | None:
        """Closest sow (local seeds) or plough tile (no harvest)."""
        return self._find_farm_sow_work(villager, building) or self._find_farm_plough_work(
            villager, building
        )

    def _find_farm_work(
        self, villager: Villager, building: Building
    ) -> tuple[int, int] | None:
        """Priority: sow → in-season harvest → weed → plough → leftover harvest."""
        found = self._find_farm_sow_work(villager, building)
        if found is not None:
            return found
        found = self._find_farm_harvest(villager, building, in_season_only=True)
        if found is not None:
            return found
        found = self._find_farm_weed_work(villager, building)
        if found is not None:
            return found
        found = self._find_farm_plough_work(villager, building)
        if found is not None:
            return found
        return self._find_farm_harvest(villager, building)

    def _fields_near_farm(self, farm: Building) -> list[Building]:
        """Field buildings whose plot is within Chebyshev radius of the farm."""
        cache = getattr(self, "_tick_fields_near", None)
        if cache is not None and farm.id in cache:
            return cache[farm.id]
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
        if cache is not None:
            cache[farm.id] = nearby
        return nearby

    def _crop_overview_from_cells(
        self, cells_by_crop: dict[str, set[tuple[int, int]]]
    ) -> list[dict]:
        from crops import CROP_BY_KEY, PHASE_SHORT

        base = farm_produce_yield()
        rows: list[dict] = []
        for key in sorted(
            cells_by_crop,
            key=lambda k: (CROP_BY_KEY[k].label if k in CROP_BY_KEY else k),
        ):
            crop = CROP_BY_KEY.get(key)
            if crop is None:
                continue
            cells = cells_by_crop[key]
            rows.append(
                {
                    "key": key,
                    "label": crop.label,
                    "icon": crop.produce_key or key,
                    "phases": tuple(PHASE_SHORT[p] for p in crop.year_phases),
                    "tiles": len(cells),
                    "max_yield": len(cells) * base,
                    "est_yield": sum(
                        self._farm_produce_yield_at(x, y) for x, y in cells
                    ),
                }
            )
        return rows

    def _farm_crop_overview(self, farm: Building) -> list[dict]:
        """Crops planned on nearby fields: season phases, max and estimated yield."""
        from collections import defaultdict

        cells_by_crop: dict[str, set[tuple[int, int]]] = defaultdict(set)
        for field in self._fields_near_farm(farm):
            for plan in field.plans:
                for cell in plan.cells():
                    if field.contains_plot(*cell):
                        cells_by_crop[plan.crop_kind].add(cell)
        return self._crop_overview_from_cells(cells_by_crop)

    def _field_crop_overview(self, field: Building) -> list[dict]:
        from collections import defaultdict

        cells_by_crop: dict[str, set[tuple[int, int]]] = defaultdict(set)
        for plan in field.plans:
            for cell in plan.cells():
                if field.contains_plot(*cell):
                    cells_by_crop[plan.crop_kind].add(cell)
        return self._crop_overview_from_cells(cells_by_crop)

    def _field_env_status(self, field: Building) -> dict:
        """Live ecology chips for one field (pest, health, pollination, ecology)."""
        from world import disturbance_activity_multiplier, effective_disturbance_at

        cells = field.plot_cells()
        health = self._field_crop_health(field)
        boost = max(0.0, float(getattr(field, "pest_boost", 0.0)))
        pest_bio = self.env_maps.farm_pest_control(cells)
        pest = pest_bio + boost
        cap = crop_health_cap_from_pest_control(pest)
        poll = self.env_maps.farm_pollination(cells)
        poll_mult = pollination_yield_multiplier(poll)
        dist_vals = [
            effective_disturbance_at(self.world, x, y) for x, y in cells
        ] or [0.0]
        dist = sum(dist_vals) / len(dist_vals)
        ecology = disturbance_activity_multiplier(dist)
        from soil import fertility_base_for, overlay_fertility, weed_yield_multiplier

        fert_vals = []
        pot_vals = []
        weed_vals = []
        for x, y in cells:
            cell = self.world.get_cell(x, y)
            if cell is None:
                continue
            fert_vals.append(overlay_fertility(cell))
            pot_vals.append(fertility_base_for(cell.terrain))
            weed_vals.append(float(getattr(cell, "weeds", 0.0)))
        fertility = (sum(fert_vals) / len(fert_vals)) if fert_vals else 0.0
        fertility_potential = (sum(pot_vals) / len(pot_vals)) if pot_vals else 1.0
        weeds = (sum(weed_vals) / len(weed_vals)) if weed_vals else 0.0
        weed_mult = weed_yield_multiplier(weeds)
        erosion_grid = self.env_maps.erosion
        ero_vals = []
        for x, y in cells:
            if 0 <= y < len(erosion_grid) and 0 <= x < len(erosion_grid[y]):
                ero_vals.append(float(erosion_grid[y][x]))
        erosion = (sum(ero_vals) / len(ero_vals)) if ero_vals else 0.0
        from field_yield import calculate_tile_yield_breakdown

        base = farm_produce_yield()
        got = calculate_tile_yield_breakdown(
            base=base,
            pest_control=pest,
            crop_health=health,
            pollination=poll_mult,
            ecology=ecology,
            fertility=fertility,
            weed_penalty=weed_mult,
            weeds=weeds,
        ).final_rounded
        return {
            "biodiversity": self.env_maps.farm_biodiversity(cells),
            "bio_lo": self.balance.get_float("PEST_CONTROL_RICHNESS_LOW"),
            "bio_mid": self.balance.get_float("PEST_CONTROL_RICHNESS_MID"),
            "bio_hi": self.balance.get_float("PEST_CONTROL_RICHNESS_HIGH"),
            "pest_from_bio": pest_bio,
            "pest_boost": boost,
            "pest_mult": pest,
            "pest_lo": self.balance.get_float("PEST_CONTROL_MULT_LOW"),
            "pest_hi": self.balance.get_float("PEST_CONTROL_MULT_HIGH"),
            "health": health,
            "health_cap": cap,
            "health_min": crop_health_min(),
            "health_drop": crop_health_max_drop(),
            "poll_coverage": poll,
            "poll_mult": poll_mult,
            "ecology": ecology,
            "disturbance": dist,
            "ecology_floor": self.balance.get_float("DISTURBANCE_ACTIVITY_FLOOR"),
            "fertility": fertility,
            "fertility_potential": fertility_potential,
            "weeds": weeds,
            "weed_mult": weed_mult,
            "weed_threshold": self._farm_weed_hoe_threshold(),
            "weed_penalty": self.balance.get_float("WEED_HARVEST_PENALTY"),
            "erosion": erosion,
            "base_yield": base,
            "harvest_yield": got,
        }

    def _field_yield_cells(self, field: Building) -> set[tuple[int, int]]:
        """Planned and/or planted cells used for field yield estimates."""
        cells: set[tuple[int, int]] = set()
        for plan in getattr(field, "plans", ()) or ():
            for cell in plan.cells():
                if field.contains_plot(*cell):
                    cells.add(cell)
        for x, y in field.plot_cells():
            cell = self.world.get_cell(x, y)
            if cell is not None and cell.feature == FeatureType.CROP_HERB:
                cells.add((x, y))
        return cells

    def _field_yield_summary(self, field: Building):
        """Per-tile expected yields for the Status panel (same maths as harvest)."""
        from field_yield import summarize_tile_yields

        base = float(farm_produce_yield())
        tile_yields: dict[tuple[int, int], int] = {}
        unrounded: list[float] = []
        after_land: list[float] = []
        after_crop: list[float] = []
        any_locked = False
        for x, y in self._field_yield_cells(field):
            cell = self.world.get_cell(x, y)
            bd = self._farm_produce_breakdown_at(x, y)
            unrounded.append(bd.final_unrounded)
            after_land.append(bd.after_landscape)
            after_crop.append(bd.after_crop_condition)
            # Ripe tile with deposit > 0: harvest lock in progress — use remaining.
            if (
                cell is not None
                and cell.feature == FeatureType.CROP_HERB
                and cell.growth_ticks <= 0
                and int(cell.deposit) > 0
            ):
                tile_yields[(x, y)] = int(cell.deposit)
                any_locked = True
            else:
                tile_yields[(x, y)] = bd.final_rounded
        n = len(unrounded)
        mean_u = (sum(unrounded) / n) if n else 0.0
        mean_land = (sum(after_land) / n) if n else 0.0
        mean_crop = (sum(after_crop) / n) if n else 0.0
        summary = summarize_tile_yields(
            tile_yields,
            base_per_tile=base,
            locked_total=None,
            unrounded_mean=mean_u,
            mean_after_landscape=mean_land,
            mean_after_crop_condition=mean_crop,
        )
        if any_locked:
            summary.locked_total = summary.expected_total
        return summary

    def _field_headline(self, field: Building) -> str:
        """Dominant crop + phase line for the Status tab."""
        from collections import Counter
        from crops import CROP_BY_KEY, PHASE_LABELS, phase_for_crop

        counts: Counter[str] = Counter()
        for x, y in field.plot_cells():
            cell = self.world.get_cell(x, y)
            if cell is not None and cell.feature == FeatureType.CROP_HERB and cell.crop_kind:
                counts[cell.crop_kind] += 1
        if not counts:
            for plan in getattr(field, "plans", ()) or ():
                n = sum(1 for c in plan.cells() if field.contains_plot(*c))
                if n:
                    counts[plan.crop_kind] += n
        if not counts:
            return ""
        kind = counts.most_common(1)[0][0]
        crop = CROP_BY_KEY.get(kind)
        label = crop.label if crop else kind
        if crop is not None:
            phase = phase_for_crop(crop, self.season)
            phase_txt = PHASE_LABELS.get(phase, str(phase))
            harvest = ", ".join(s.name.title() for s in crop.harvest_seasons) or "—"
            # Live plant state overrides schedule phase when planted.
            planted = any(
                (c := self.world.get_cell(x, y)) is not None
                and c.feature == FeatureType.CROP_HERB
                and (c.crop_kind or "") == kind
                for x, y in field.plot_cells()
            )
            if planted:
                ripe = any(
                    (c := self.world.get_cell(x, y)) is not None
                    and c.feature == FeatureType.CROP_HERB
                    and (c.crop_kind or "") == kind
                    and c.growth_ticks <= 0
                    for x, y in field.plot_cells()
                )
                state = "Ready" if ripe else "Growing"
            else:
                state = phase_txt
            return f"{label} · {state} · Harvest {harvest}"
        return label

    def _farm_env_status(self, farm: Building) -> dict | None:
        fields = self._fields_near_farm(farm)
        if not fields:
            return None
        statuses = [self._field_env_status(f) for f in fields]
        n = len(statuses)
        avg = statuses[0].copy()
        for key in (
            "biodiversity",
            "pest_from_bio",
            "pest_boost",
            "pest_mult",
            "health",
            "health_cap",
            "poll_coverage",
            "poll_mult",
            "ecology",
            "disturbance",
            "harvest_yield",
            "fertility",
            "weeds",
            "weed_mult",
            "erosion",
        ):
            avg[key] = sum(float(s[key]) for s in statuses) / n
        avg["harvest_yield"] = max(1, int(round(avg["harvest_yield"])))
        avg["base_yield"] = farm_produce_yield()
        return avg

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

        if (
            cell.feature == FeatureType.CROP_HERB
            and float(getattr(cell, "weeds", 0.0)) > 0.0
        ):
            # Ripe crop: harvest first — weeding must not block pickup forever.
            if not (allow_harvest and self.world.crop_herb_ready(x, y)):
                if self.world.clear_weeds(x, y):
                    self.world.apply_disturbance(x, y)
                    self._spend_work_energy(villager)
                    self._gain_job_skill(villager, building.kind.name)
                return

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
            self._spend_work_energy(villager)
            self._gain_job_skill(villager, building.kind.name)
            return

        if (
            cell.feature == FeatureType.CROP_HERB
            and float(getattr(cell, "weeds", 0.0)) >= self._farm_weed_hoe_threshold()
        ):
            if self.world.clear_weeds(x, y):
                self.world.apply_disturbance(x, y)
                self._spend_work_energy(villager)
                self._gain_job_skill(villager, building.kind.name)
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
                self._spend_work_energy(villager)
                self._gain_job_skill(villager, building.kind.name)
            return
        # Plough: harvest wild crops / herbs into the pack first; saplings are lost.
        if cell.feature in (FeatureType.WILD_CROP, FeatureType.HERB):
            if not self._collect_herb(x, y, inv, status=False):
                # Pack full — leave the plant and try another tile next tick.
                return
        self.world.plough_tile(x, y)
        self.world.apply_extraction_disturbance(x, y)
        self._refresh_indicators()
        self._spend_work_energy(villager)
        self._gain_job_skill(villager, building.kind.name)

    def _update_hunter(self, villager: Villager, building: Building) -> None:
        """Hunt in areas, or nearest animal if no area is drawn."""
        if villager.inventory.is_full or self._gather_cargo_needs_delivery(
            villager, building
        ):
            self._force_assigned_delivery(villager, building)
            return
        if not self._ensure_hunter_tools(villager):
            if self._try_addon_craft(villager, building):
                return
            self._maybe_assigned_transport(villager, building)
            return
        # Finish leather while hide is waiting — don't leave it for "no prey" only.
        if self._try_addon_craft(villager, building):
            return
        if self._workplace_primary_available(villager, building):
            pass
        elif self._maybe_assigned_transport(villager, building):
            return
        elif self._workplace_accepts_carry(villager, building):
            self._force_assigned_delivery(villager, building)
            return
        elif self._try_addon_craft(villager, building):
            return

        # Resolve a pending bow shot (animation + hit/miss).
        if villager.hunt_shot is not None:
            self._tick_hunter_shot(villager)
            return

        meat_pos = villager.hunt_meat_pos
        if meat_pos is not None:
            cell = self.world.get_cell(*meat_pos)
            if cell is None or not self._cell_has_hunt_loot(cell):
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
                    if self._collect_meat(*meat_pos, villager.inventory, status=False):
                        self._spend_work_energy(villager)
                        self._gain_job_skill(villager, building.kind.name)
                    villager.work_cooldown = self._villager_work_interval(villager)
                    cell = self.world.get_cell(*meat_pos)
                    if cell is None or not self._cell_has_hunt_loot(cell):
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
                    recipe = hunt_recipe("rabbit")
                    if recipe is None or not recipe_outputs_fit(
                        villager.inventory, recipe
                    ):
                        villager.hunt_colony_id = None
                        self._force_assigned_delivery(villager, building)
                        return
                    result = self.wildlife.harvest_colony(
                        colony.id, kind=colony.kind
                    )
                    villager.hunt_colony_id = None
                    if result is not None:
                        if self._apply_hunt_recipe_to_inventory(
                            villager.inventory, "rabbit"
                        ):
                            self.world.apply_extraction_disturbance(colony.x, colony.y)
                            self._refresh_indicators()
                            self._spend_work_energy(villager)
                            self._gain_job_skill(villager, building.kind.name)
                            self._force_assigned_delivery(villager, building)
                        villager.work_cooldown = self._villager_work_interval(villager)
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
            if self._try_addon_craft(villager, building):
                return
            if self._maybe_assigned_transport(villager, building):
                return
            villager._work_search_cd = self._decision_slot_ticks()
            self._set_workplace_idle(villager)
            return

        villager.state = VillagerState.WORKING
        dist = max(abs(animal.x - villager.x), abs(animal.y - villager.y))
        can_ranged = self._hunter_can_ranged(villager)
        has_spear = villager.inventory.has_equipped_tool("spear")

        if can_ranged and dist <= HUNTER_BOW_RANGE:
            if villager.work_cooldown == 0:
                self._hunter_fire_bow(villager, building, animal)
            return

        if has_spear and dist <= 1:
            if villager.work_cooldown == 0:
                result = self.wildlife.kill_animal(animal.id)
                villager.hunt_animal_id = None
                if result is not None:
                    x, y, kind = result
                    self._drop_hunt_yields(x, y, kind, building=building)
                    self.world.apply_extraction_disturbance(x, y)
                    if kind in (AnimalKind.DEER, AnimalKind.BOAR):
                        self.wildlife.scare_from_kill(x, y)
                    self._refresh_indicators()
                    villager.hunt_meat_pos = (x, y)
                    self._register_field_claim(villager, (x, y))
                    self._spend_work_energy(villager)
                    self._gain_job_skill(villager, building.kind.name)
                villager.work_cooldown = self._villager_work_interval(villager)
            return

        approach = (animal.x, animal.y)
        if not self.world.is_walkable(*approach):
            for ny, nx in self.world.neighbourhood(animal.x, animal.y, radius=1):
                if self.world.is_walkable(nx, ny):
                    approach = (nx, ny)
                    break
        # Keep chasing the last approach cell while prey is still nearby so we
        # do not re-BFS every tick as the animal flees one tile at a time.
        cache_goal = getattr(villager, "_path_goal", None)
        if (
            cache_goal is not None
            and max(abs(cache_goal[0] - animal.x), abs(cache_goal[1] - animal.y)) <= 2
        ):
            approach = cache_goal
        if not self._step_villager_toward(villager, approach):
            villager.hunt_animal_id = None
            self._clear_villager_path(villager)

    def _hunter_fire_bow(self, villager: Villager, building: Building, animal) -> None:
        """Consume one arrow, spawn flight FX, and queue hit/miss resolution."""
        inv = villager.inventory
        if int(getattr(inv, "stone_arrows", 0)) <= 0:
            return
        inv.consume_item("stone_arrows", 1)
        hit = random.random() < HUNTER_BOW_HIT_CHANCE
        duration = max(4, self._villager_work_interval(villager) // 2)
        villager.hunt_shot = (animal.id, hit, duration)
        self._arrow_shots.append(
            (
                float(villager.x),
                float(villager.y),
                float(animal.x),
                float(animal.y),
                0,
                duration,
                hit,
            )
        )
        self._spend_work_energy(villager)
        villager.work_cooldown = self._villager_work_interval(villager)

    def _tick_hunter_shot(self, villager: Villager) -> None:
        shot = villager.hunt_shot
        if shot is None:
            return
        animal_id, hit, ticks_left = shot
        ticks_left -= 1
        if ticks_left > 0:
            villager.hunt_shot = (animal_id, hit, ticks_left)
            villager.state = VillagerState.WORKING
            return
        villager.hunt_shot = None
        villager.hunt_animal_id = None
        if not hit:
            return
        result = self.wildlife.kill_animal(animal_id)
        if result is None:
            return
        x, y, kind = result
        building = self.buildings.get(villager.building_id) if villager.building_id else None
        self._drop_hunt_yields(x, y, kind, building=building)
        self.world.apply_extraction_disturbance(x, y)
        if kind in (AnimalKind.DEER, AnimalKind.BOAR):
            self.wildlife.scare_from_kill(x, y)
        self._refresh_indicators()
        villager.hunt_meat_pos = (x, y)
        self._register_field_claim(villager, (x, y))
        if building is not None:
            self._gain_job_skill(villager, building.kind.name)

    def _tick_arrow_shots(self) -> None:
        if not self._arrow_shots:
            return
        next_shots: list[tuple[float, float, float, float, int, int, bool]] = []
        for x0, y0, x1, y1, age, duration, hit in self._arrow_shots:
            age += 1
            if age < duration:
                next_shots.append((x0, y0, x1, y1, age, duration, hit))
        self._arrow_shots = next_shots

    def _draw_arrow_shots(self) -> None:
        if not self._arrow_shots:
            return
        for x0, y0, x1, y1, age, duration, hit in self._arrow_shots:
            t = min(1.0, age / max(1, duration))
            ax = x0 + (x1 - x0) * t
            ay = y0 + (y1 - y0) * t
            cx, cy = self._cell_center(ax, ay)
            # Slight trail behind the tip.
            bx = x0 + (x1 - x0) * max(0.0, t - 0.12)
            by = y0 + (y1 - y0) * max(0.0, t - 0.12)
            px, py = self._cell_center(bx, by)
            colour = (210, 180, 120) if hit else (160, 160, 160)
            pygame.draw.line(self.screen, colour, (px, py), (cx, cy), 2)
            pygame.draw.circle(self.screen, (90, 90, 95), (cx, cy), 3)

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
        recipe = hunt_recipe("rabbit")
        if recipe is None or not recipe_outputs_fit(villager.inventory, recipe):
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
        origin = (villager.x, villager.y)
        animals = [
            a
            for a in animals
            if building.allows_hunt_kind(a.kind.name)
            and self._under_production_max(building, "meat")
            and a.id not in taken
            and self._within_work_search(origin, (a.x, a.y))
        ]
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
                    if cell is not None and self._cell_has_hunt_loot(cell):
                        cells.append((x, y))
            origin = building.center_cell()
            # Prefer nearest to a hunter currently looking — use building centre.
        else:
            for y in range(self.world.rows):
                for x in range(self.world.cols):
                    if (x, y) in claimed:
                        continue
                    cell = self.world.cells[y][x]
                    if self._cell_has_hunt_loot(cell):
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
                    if cell is not None and self._cell_has_hunt_loot(cell):
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
                cell = self.world.cells[y][x]
                if not self._cell_has_hunt_loot(cell):
                    continue
                if self._within_work_search(origin, (x, y)):
                    return True
        return False

    def _update_fisher(self, villager: Villager, building: Building) -> None:
        """Collect shore deposits, else stand at a dense shoreline and wait for fish."""
        if not fishing_allowed(self.calendar_day):
            villager.fish_target_id = None
            villager.fish_post_pos = None
            villager.fish_catch_pos = None
            if self._maybe_assigned_transport(villager, building):
                return
            self._set_workplace_idle(villager)
            return

        if villager.inventory.is_full or self._gather_cargo_needs_delivery(
            villager, building
        ):
            self._force_assigned_delivery(villager, building)
            return

        if not self._ensure_work_tool(villager, "fishing_rod"):
            self._maybe_assigned_transport(villager, building)
            return
        if self._workplace_primary_available(villager, building):
            pass
        elif self._maybe_assigned_transport(villager, building):
            return
        elif self._workplace_accepts_carry(villager, building):
            self._force_assigned_delivery(villager, building)
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
                    if self._collect_fish(*catch_pos, villager.inventory, status=False):
                        self._spend_work_energy(villager)
                        self._gain_job_skill(villager, building.kind.name)
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
        # Yield is per species (roach 1 … pike 4); only require space for a fish
        # that actually fits — gating on max yield blocked catches in 1–3 free slots.
        if villager.work_cooldown != 0:
            return
        from wildlife import fish_yield_for

        if not villager.inventory.can_add(1, key="fish"):
            if int(getattr(villager.inventory, "fish", 0)) > 0:
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
            and villager.inventory.can_add(fish_yield_for(f.kind), key="fish")
        ]
        if not catchable:
            if int(getattr(villager.inventory, "fish", 0)) > 0 and not villager.inventory.can_add(
                FISH_YIELD, key="fish"
            ):
                self._force_assigned_delivery(villager, building)
                return
            villager.work_cooldown = max(4, self._villager_move_interval(villager) // 4)
            return
        target = min(
            catchable,
            key=lambda f: abs(f.x - villager.x) + abs(f.y - villager.y),
        )
        yield_n = fish_yield_for(target.kind)
        pos = self.fish.kill_fish(target.id)
        if pos is None:
            return
        if not villager.inventory.add_fish(yield_n):
            # Capacity raced away — leave the catch on shore rather than lose it.
            self.world.add_fish_deposit(pos[0], pos[1], yield_n)
        else:
            self.record_produced("fish", yield_n)
        self.world.apply_extraction_disturbance(pos[0], pos[1])
        self._refresh_indicators()
        villager.work_cooldown = self._villager_work_interval(villager)
        if villager.inventory.is_full or self._gather_cargo_needs_delivery(
            villager, building
        ):
            self._force_assigned_delivery(villager, building)

    def _is_fishing_shore(self, x: int, y: int) -> bool:
        """Walkable land tile that touches water (a place to stand and fish)."""
        shores = self._ensure_fishing_shore_cache()
        return (x, y) in shores

    def _ensure_fishing_shore_cache(self) -> set[tuple[int, int]]:
        rev = int(getattr(self.world, "terrain_revision", 0))
        shores = self._fishing_shore_cache
        if shores is not None and self._fishing_shore_revision == rev:
            return shores
        return self._rebuild_fishing_shore_cache()

    def _rebuild_fishing_shore_cache(self) -> set[tuple[int, int]]:
        """Precompute shore tiles once — fish-post search hits this heavily."""
        shores: set[tuple[int, int]] = set()
        world = self.world
        for y in range(world.rows):
            for x in range(world.cols):
                if not world.is_walkable(x, y):
                    continue
                for ny, nx in world.neighbourhood(x, y, radius=1):
                    if (nx, ny) == (x, y):
                        continue
                    cell = world.get_cell(nx, ny)
                    if cell is not None and is_water_terrain(cell.terrain):
                        shores.add((x, y))
                        break
        self._fishing_shore_cache = shores
        self._fishing_shore_revision = int(getattr(world, "terrain_revision", 0))
        return shores

    def _invalidate_fishing_shore_cache(self) -> None:
        self._fishing_shore_cache = None
        self._fishing_shore_revision = -1

    def _fisher_candidate_fish(self, villager: Villager, building: Building):
        """Fish the workplace may target (area filter + search radius from villager)."""
        if not self._under_production_max(building, "fish"):
            return []
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
        shores = self._ensure_fishing_shore_cache()
        # O(fish × r²): each fish votes for nearby shore tiles (was O(fish² × r²)).
        shore_scores: dict[tuple[int, int], int] = {}
        r = FISH_POST_SCORE_RADIUS
        for item in fish_list:
            for ny, nx in self.world.neighbourhood(item.x, item.y, radius=r):
                shore = (nx, ny)
                if shore in claimed or shore not in shores:
                    continue
                if not self._within_work_search(origin, shore):
                    continue
                shore_scores[shore] = shore_scores.get(shore, 0) + 1
        dense = {
            s: d for s, d in shore_scores.items() if d >= FISH_POST_MIN_FISH
        }
        if not dense:
            dense = {s: d for s, d in shore_scores.items() if d >= 1}
        if not dense:
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
            for s, d in dense.items()
            if abs(s[0] - origin[0]) + abs(s[1] - origin[1]) <= FISH_POST_LOCAL_RADIUS
        }
        if local:
            chosen = pick_from(local)
            if chosen is not None:
                return chosen
        chosen = pick_from(dense)
        if chosen is not None:
            return chosen
        # Densest shores can be unreachable (detour / blocked). Fall back to any
        # scored shore by distance so fishers still leave the storehouse.
        return self._pick_nearest_reachable(
            origin,
            list(shore_scores.keys()),
            pos_fn=lambda p: p,
            prefer_adjacent=False,
            villager=villager,
        )

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
                # Stay while any fish remain nearby — avoid re-scanning every tick
                # when a school briefly dips below MIN_FISH.
                if self._fish_post_density(post, fish_list) >= 1:
                    return post
            villager.fish_post_pos = None
            self._clear_villager_path(villager)
        cd = int(getattr(villager, "_fish_post_search_cd", 0) or 0)
        if cd > 0:
            villager._fish_post_search_cd = cd - 1
            return None
        post = self._find_fish_post(villager, building)
        villager._fish_post_search_cd = 12 if post is None else 0
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

        # Carrying goods → another workplace that needs them, else storehouse.
        # Re-check when idle/delivering or when the current claim will not take the
        # pack — but do not steal a mid-trip supply claim every tick.
        if not villager.inventory.is_empty:
            current = (
                self.buildings.get(villager.haul_building_id)
                if villager.haul_building_id is not None
                else None
            )
            keep_claim = False
            if (
                villager.state == VillagerState.HAULING
                and current is not None
                and self._workplace_can_accept_cargo(current, villager.inventory)
            ):
                demand = self._building_supply_demand(current)
                keep_claim = any(
                    int(getattr(villager.inventory, key, 0)) > 0 for key in demand
                )
            if not keep_claim:
                exclude: set[int] = set()
                last = getattr(villager, "_haul_last_stop_id", None)
                if last is not None:
                    exclude.add(int(last))
                sink = self._find_processor_input_sink(villager, exclude_ids=exclude)
                if sink is None and exclude:
                    sink = self._find_processor_input_sink(villager)
                if sink is not None:
                    villager.haul_building_id = sink.id
                    villager.state = VillagerState.HAULING
                elif villager.state != VillagerState.DELIVERING:
                    villager.haul_building_id = None
                    villager.state = VillagerState.DELIVERING
                    villager.target = home

        if villager.state == VillagerState.DELIVERING:
            if villager.inventory.is_empty:
                villager.haul_building_id = None
                villager.state = VillagerState.IDLE
                return
            if (villager.x, villager.y) == home:
                self._deposit_home(villager.inventory, status=False)
                self._restock_workplace_gear_at_home(villager)
                self._gain_job_skill(villager, "HOME")
                villager.haul_building_id = None
                villager._haul_last_stop_id = None
                villager.state = VillagerState.IDLE
                return
            self._step_villager_toward(villager, home)
            return

        if villager.state == VillagerState.HAULING and villager.haul_building_id is not None:
            claimed = self.buildings.get(villager.haul_building_id)
            # Empty pack + haulable stock: clear the workplace (farm produce, etc.).
            # Farms always ``needs_supplied()`` for seed top-ups — that must not
            # steal a clear-stock claim before we withdraw.
            if (
                claimed is not None
                and villager.inventory.is_empty
                and claimed.haulable_total() > 0
            ):
                if not self._owns_haul_claim(villager, claimed.id):
                    villager.haul_building_id = None
                else:
                    dest = claimed.center_cell()
                    if (villager.x, villager.y) == dest:
                        if villager.work_cooldown == 0:
                            claimed.withdraw_to_inventory(villager.inventory)
                            villager.work_cooldown = self._villager_work_interval(
                                villager
                            )
                            villager._haul_last_stop_id = claimed.id
                            self._hauler_route_cargo(
                                villager, exclude_ids={claimed.id}
                            )
                        return
                    self._step_villager_toward(villager, dest)
                    return
            elif claimed is not None and claimed.needs_supplied():
                # Deliver ingredients the processor / forester splitter still needs.
                if (
                    not villager.inventory.is_empty
                    and self._workplace_can_accept_cargo(claimed, villager.inventory)
                ):
                    dest = claimed.center_cell()
                    villager.target = dest
                    if (villager.x, villager.y) == dest:
                        if villager.work_cooldown == 0:
                            self._hauler_exchange_at_processor(villager, claimed)
                            villager._haul_last_stop_id = claimed.id
                            # Leftover cargo → next needy building, else home.
                            self._hauler_route_cargo(
                                villager, exclude_ids={claimed.id}
                            )
                        return
                    self._step_villager_toward(villager, dest)
                    return
                if not villager.inventory.is_empty:
                    # Cargo left that this sink will not take — grab produce first
                    # if standing at the station, then route elsewhere / home.
                    dest = claimed.center_cell()
                    out_keys = tuple(
                        k
                        for k in claimed.haul_keys()
                        if claimed.haulable_amount(k) > 0
                    )
                    if (
                        (villager.x, villager.y) == dest
                        and villager.work_cooldown == 0
                        and out_keys
                        and not villager.inventory.is_full
                    ):
                        claimed.withdraw_to_inventory(villager.inventory, keys=out_keys)
                        villager.work_cooldown = self._villager_work_interval(villager)
                    villager._haul_last_stop_id = claimed.id
                    self._hauler_route_cargo(villager, exclude_ids={claimed.id})
                    return
                # Mid-trip sticky: finish walking home / packing for this claim only.
                if self._processor_can_be_supplied(claimed) and self._owns_haul_claim(
                    villager, claimed.id
                ):
                    demand = self._building_supply_demand(claimed)
                    _, pickup = self._best_supply_pickup(demand)
                    if pickup is None:
                        villager.haul_building_id = None
                        villager.state = VillagerState.IDLE
                        return
                    if (villager.x, villager.y) != pickup:
                        self._step_villager_toward(villager, pickup)
                        return
                    taken = self._withdraw_processor_supply(villager, claimed)
                    if taken <= 0:
                        villager.haul_building_id = None
                        villager.state = VillagerState.IDLE
                    else:
                        # Pack other recipe gaps into the same trip, then walk to
                        # whichever sink best matches the actual cargo (kitchen may
                        # outrank the original craft/forester claim).
                        self._withdraw_extra_supply_for_others(villager, claimed)
                        self._hauler_route_cargo(villager)
                    return
                villager.haul_building_id = None
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
                    villager._haul_last_stop_id = source.id
                    self._hauler_route_cargo(villager, exclude_ids={source.id})
                return
            self._step_villager_toward(villager, source.center_cell())
            return

        # Avoid immediately re-supplying the building we just finished if others wait.
        avoid = getattr(villager, "_haul_last_stop_id", None)
        sink = self._find_processor_needing_supply_for(villager)
        if sink is not None and avoid is not None and sink.id == avoid:
            claimed = self._claimed_haul_targets(villager.id)
            others = [
                b
                for b in self.buildings.values()
                if b.id != avoid
                and b.id not in claimed
                and b.needs_supplied()
                and self._processor_can_be_supplied(b)
            ]
            if others:
                sink = min(others, key=self._supply_sink_sort_key)
        if sink is not None:
            demand = self._building_supply_demand(sink)
            _, pickup = self._best_supply_pickup(demand)
            if pickup is None:
                villager.haul_building_id = None
                villager.state = VillagerState.IDLE
                return
            villager.haul_building_id = sink.id
            villager.state = VillagerState.HAULING
            if (villager.x, villager.y) != pickup:
                self._step_villager_toward(villager, pickup)
                return
            taken = self._withdraw_processor_supply(villager, sink)
            if taken <= 0:
                villager.haul_building_id = None
                villager.state = VillagerState.IDLE
            else:
                self._withdraw_extra_supply_for_others(villager, sink)
                self._hauler_route_cargo(villager)
            return

        villager.haul_building_id = None
        villager.state = VillagerState.IDLE

    def _processor_can_be_supplied(self, building: Building) -> bool:
        demand = self._building_supply_demand(building)
        if not demand:
            return False
        return any(self._village_supply_have(key) > 0 for key in demand)

    def _withdraw_processor_supply(self, villager: Villager, sink: Building) -> int:
        """Pack ingredients for a workplace from storehouse or the farm underfoot."""
        demand = self._building_supply_demand(sink)
        if not demand:
            return 0
        source_obj, _ = self._best_supply_pickup(demand)
        # Prefer whatever stockpile the worker is standing on.
        at_home = (villager.x, villager.y) == self.world.home_pos
        here_farm = None
        for building in self.buildings.values():
            if building.kind == BuildingKind.FARM and building.center_cell() == (
                villager.x,
                villager.y,
            ):
                here_farm = building
                break
        if at_home and any(int(getattr(self.home_storage, k, 0)) > 0 for k in demand):
            source_obj = self.home_storage
        elif here_farm is not None and any(
            here_farm.haulable_amount(k) > 0 for k in demand
        ):
            source_obj = here_farm
        if source_obj is None:
            return 0

        amounts: dict[str, int] = {}
        inv = villager.inventory
        cargo_left = inv.capacity - inv.cargo_total
        seed_left = inv.seed_capacity - inv.seed_total

        def _have(key: str, already: int) -> int:
            if source_obj is self.home_storage:
                have = int(getattr(self.home_storage, key, 0)) - already
                if sink.is_market() and sink.market_supply_enabled(key):
                    have = min(
                        have,
                        self._market_storehouse_surplus(key, sink.market_supply_min(key))
                        - already,
                    )
                return max(0, have)
            return max(0, int(source_obj.haulable_amount(key)) - already)

        def _take_key(key: str, want: int) -> None:
            nonlocal cargo_left, seed_left
            if want <= 0:
                return
            already = amounts.get(key, 0)
            have = _have(key, already)
            room = self._sink_space_for_key(sink, key) - already
            if Inventory.is_seed_key(key):
                pack_room = seed_left
            else:
                pack_room = cargo_left
            n = min(want, have, room, pack_room)
            if n > 0:
                amounts[key] = already + n
                if Inventory.is_seed_key(key):
                    seed_left -= n
                else:
                    cargo_left -= n

        for key, want in demand.items():
            _take_key(key, want)

        others_need_gap = any(
            b.id != sink.id
            and b.needs_supplied()
            and sum(b.recipe_gap_demand().values()) > 0
            and self._processor_can_be_supplied(b)
            for b in self.buildings.values()
        )
        # Don't pack-fill a processor with one demand key — that monopolises the
        # shared input tray and leaves no room for the missing cook ingredients.
        if (
            (cargo_left > 0 or seed_left > 0)
            and not others_need_gap
            and not sink.is_processor()
        ):
            fill_keys = list(demand.keys())
            progressed = True
            while (cargo_left > 0 or seed_left > 0) and progressed:
                progressed = False
                for key in fill_keys:
                    before_c, before_s = cargo_left, seed_left
                    _take_key(key, 1)
                    if cargo_left < before_c or seed_left < before_s:
                        progressed = True
                    if cargo_left <= 0 and seed_left <= 0:
                        break

        if not amounts:
            return 0
        if source_obj is self.home_storage:
            return self.home_storage.withdraw_amounts_to(villager.inventory, amounts)
        # Farm surplus: honour haulable caps via per-key withdraw.
        taken = 0
        for key, want in amounts.items():
            for _ in range(want):
                if source_obj.haulable_amount(key) <= 0:
                    break
                if not villager.inventory.can_add(1, key=key):
                    break
                if int(getattr(source_obj, key, 0)) <= 0:
                    break
                setattr(source_obj, key, int(getattr(source_obj, key, 0)) - 1)
                setattr(
                    villager.inventory,
                    key,
                    int(getattr(villager.inventory, key, 0)) + 1,
                )
                taken += 1
        return taken

    def _haul_source_sort_key(
        self, building: Building, origin: tuple[int, int]
    ) -> tuple:
        """Lower is better — blocked processor outputs beat nearby log piles."""
        haulable = building.haulable_total()
        out_full = (
            building.is_processor()
            and building.output_capacity > 0
            and building.output_space_left() <= 0
            and haulable > 0
        )
        backed = self._workplace_output_backed_up(building)
        has_proc_out = building.is_processor() and any(
            building.haulable_amount(key) > 0
            for key in building.processor_output_keys()
        )
        # Gather huts (fisher / forager / hunter / farm): near-full storage is urgent so
        # haulers clear stock before workers jam the lodge.
        gather_full = False
        gather_backed = False
        if (
            not building.is_processor()
            and building.capacity > 0
            and haulable > 0
            and building.kind
            in (
                BuildingKind.FISHER,
                BuildingKind.FORAGER,
                BuildingKind.HUNTER,
                BuildingKind.MASON,
                BuildingKind.FARM,
            )
        ):
            stored = building.cargo_stored_total
            gather_full = building.space_left <= 0
            gather_backed = stored * 4 >= building.capacity * 3
        if out_full or gather_full:
            tier = 0
        elif backed or gather_backed:
            tier = 1
        elif has_proc_out:
            tier = 2
        else:
            tier = 3
        # Prefer kitchen meals, then fisher fish (kitchen inputs), over craft/logs.
        if building.kind == BuildingKind.KITCHEN:
            kind_rank = 0
        elif building.kind == BuildingKind.FISHER:
            kind_rank = 1
        elif building.kind == BuildingKind.FARM:
            kind_rank = 1
        else:
            kind_rank = 2
        dist = abs(building.center_cell()[0] - origin[0]) + abs(
            building.center_cell()[1] - origin[1]
        )
        return (tier, kind_rank, dist, -haulable)

    def _find_haul_source(self, villager: Villager) -> Building | None:
        claimed = self._claimed_haul_targets(villager.id)
        origin = (villager.x, villager.y)
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
        return min(stocked, key=lambda b: self._haul_source_sort_key(b, origin))

    def _find_processor_needing_supply(self) -> Building | None:
        return self._find_processor_needing_supply_for(None)

    def _supply_sink_sort_key(self, building: Building) -> tuple:
        """Lower is better: kitchen recipe gaps, then other gaps, then reserve top-ups."""
        gap = sum(building.recipe_gap_demand().values())
        if building.kind == BuildingKind.KITCHEN and gap > 0:
            tier = 0
        elif gap > 0:
            tier = 1
        elif building.kind == BuildingKind.KITCHEN:
            tier = 2
        else:
            tier = 3
        hx, hy = self.world.home_pos
        dist = abs(building.center_cell()[0] - hx) + abs(building.center_cell()[1] - hy)
        rr = (
            int(self.calendar_day) * max(1, self.ticks_per_day)
            + int(self.day_tick)
            + building.id
        ) % 7
        return (tier, -gap, rr, dist)

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
        return min(needy, key=self._supply_sink_sort_key)

    def _withdraw_extra_supply_for_others(
        self, villager: Villager, primary: Building
    ) -> int:
        """Fill remaining pack space with recipe-gap stock for other workplaces.

        One storehouse visit can then drop at craft and continue to kitchen / farm
        without an extra home round-trip.
        """
        inv = villager.inventory
        if inv.is_full:
            return 0
        claimed = self._claimed_haul_targets(villager.id)
        extras = [
            b
            for b in self.buildings.values()
            if b.id != primary.id
            and b.id not in claimed
            and b.needs_supplied()
            and self._processor_can_be_supplied(b)
            and sum(b.recipe_gap_demand().values()) > 0
        ]
        if not extras:
            # Fall back to any other supplyable demand (reserve top-ups) if pack empty-ish.
            extras = [
                b
                for b in self.buildings.values()
                if b.id != primary.id
                and b.id not in claimed
                and b.needs_supplied()
                and self._processor_can_be_supplied(b)
            ]
        extras.sort(key=self._supply_sink_sort_key)
        taken_total = 0
        for sink in extras:
            if inv.is_full:
                break
            taken_total += self._withdraw_processor_supply(villager, sink)
        return taken_total

    def _find_processor_input_sink(
        self,
        villager: Villager,
        *,
        exclude_ids: set[int] | None = None,
    ) -> Building | None:
        """Best workplace that can take cargo already in the pack.

        Prefers recipe gaps (especially kitchen) over nearest reserve top-up so a
        hauler leaving the craft bench can drop wood/food elsewhere before home.
        """
        exclude = exclude_ids or set()
        inv = villager.inventory
        sinks: list[Building] = []
        for building in self.buildings.values():
            if building.id in exclude:
                continue
            if not building.needs_supplied():
                continue
            if not building.can_accept_from(inv):
                continue
            gap = building.recipe_gap_demand()
            full = self._building_supply_demand(building)
            if not any(int(getattr(inv, key, 0)) > 0 for key in full) and not any(
                int(getattr(inv, key, 0)) > 0 for key in gap
            ):
                # Accepts something we carry, but does not currently need it
                # (e.g. craft with full wood stock) — skip so we go home / elsewhere.
                continue
            sinks.append(building)
        if not sinks:
            return None

        def _useful_overlap(demand: dict[str, int]) -> int:
            return sum(
                min(int(getattr(inv, key, 0)), want)
                for key, want in demand.items()
                if int(getattr(inv, key, 0)) > 0
            )

        def _sink_key(b: Building) -> tuple:
            gap = b.recipe_gap_demand()
            full = self._building_supply_demand(b)
            gap_hit = _useful_overlap(gap)
            full_hit = _useful_overlap(full)
            if b.kind == BuildingKind.KITCHEN and gap_hit > 0:
                tier = 0
            elif gap_hit > 0:
                tier = 1
            elif full_hit > 0:
                tier = 2
            else:
                tier = 3
            dist = abs(b.center_cell()[0] - villager.x) + abs(
                b.center_cell()[1] - villager.y
            )
            return (tier, -gap_hit, -full_hit, dist)

        return min(sinks, key=_sink_key)

    def _hauler_route_cargo(
        self,
        villager: Villager,
        *,
        exclude_ids: set[int] | None = None,
    ) -> None:
        """After pickup / exchange: deliver to another needy building, else storehouse."""
        home = self.world.home_pos
        if villager.inventory.is_empty:
            villager.haul_building_id = None
            villager.state = VillagerState.IDLE
            return
        # Do not fall back to an excluded stop — that recreates craft↔craft thrash.
        sink = self._find_processor_input_sink(
            villager, exclude_ids=set(exclude_ids or ())
        )
        if sink is not None:
            villager.haul_building_id = sink.id
            villager.state = VillagerState.HAULING
            villager.target = sink.center_cell()
            return
        villager.haul_building_id = None
        villager.state = VillagerState.DELIVERING
        villager.target = home

    def _plant_stock_in_inv(self, villager: Villager, building: Building) -> bool:
        return any(getattr(villager.inventory, key, 0) > 0 for key in building.plant_keys())

    def _plant_stock_at(self, building: Building, key: str) -> int:
        """Plantables available locally at the workplace (not the storehouse)."""
        return int(getattr(building, key, 0))

    def _can_plant_recipe(
        self, villager: Villager, building: Building, recipe_name: str
    ) -> bool:
        from trees import sapling_keys_for_plant_recipe

        if not building.is_recipe_enabled(recipe_name):
            return False
        keys = sapling_keys_for_plant_recipe(recipe_name)
        if not keys:
            return False
        inv = villager.inventory
        if any(getattr(inv, key, 0) > 0 for key in keys):
            return True
        if building.kind != BuildingKind.FORESTER:
            return False
        stocked = any(self._plant_stock_at(building, key) > 0 for key in keys)
        return stocked and any(inv.can_add(1, key=key) for key in keys)

    def _ensure_sapling_for_recipe(
        self, villager: Villager, building: Building, recipe_name: str
    ) -> bool:
        from trees import sapling_keys_for_plant_recipe

        keys = sapling_keys_for_plant_recipe(recipe_name)
        inv = villager.inventory
        if any(getattr(inv, key, 0) > 0 for key in keys):
            return True
        for key in keys:
            if building.give_item_to(inv, key):
                return True
        return False

    def _plant_sapling_recipe(
        self, x: int, y: int, inventory: Inventory, recipe_name: str
    ) -> bool:
        from trees import resolve_tree, sapling_keys_for_plant_recipe, species_from_sapling_key

        for key in sapling_keys_for_plant_recipe(recipe_name):
            if getattr(inventory, key, 0) <= 0:
                continue
            species = species_from_sapling_key(key)
            if not self.world.plant_sapling(x, y, species=species):
                continue
            inventory.consume_item(key, 1)
            self.record_consumed(key, 1)
            self.world.apply_disturbance(x, y)
            self._refresh_indicators()
            return True
        return False

    def _pick_forester_plant_recipe(
        self, villager: Villager, building: Building
    ):
        for recipe in building.enabled_plant_recipes():
            if self._can_plant_recipe(villager, building, recipe.name):
                return recipe
        return None

    def _can_plant_from(self, villager: Villager, building: Building) -> tuple[bool, bool, bool]:
        """Whether sapling / berry / crop-seed planting is currently possible."""
        inv = villager.inventory
        if building.kind == BuildingKind.FORESTER:
            can_sapling = any(
                self._can_plant_recipe(villager, building, r.name)
                for r in building.enabled_plant_recipes()
            )
        else:
            can_sapling = inv.saplings > 0
        can_berry = False
        can_herb = False
        if building.kind == BuildingKind.FARM:
            can_herb = any(getattr(inv, k, 0) > 0 for k in SEED_KEYS) or (
                any(self._plant_stock_at(building, k) > 0 for k in SEED_KEYS)
                and any(inv.can_add(1, key=k) for k in SEED_KEYS)
            )
        return can_sapling, can_berry, can_herb

    def _plant_withdraw_destination(
        self, building: Building, keys: tuple[str, ...] | None = None
    ) -> tuple[int, int] | None:
        """Prefer workplace stock; fall back to the storehouse when empty."""
        wanted = keys if keys is not None else building.plant_keys()
        if any(getattr(building, key, 0) > 0 for key in wanted):
            return building.center_cell()
        if any(getattr(self.home_storage, key, 0) > 0 for key in wanted):
            return self.world.home_pos
        return None

    def _update_plant_stock_withdraw(
        self, villager: Villager, building: Building
    ) -> bool:
        """Walk to storage and pull saplings/seeds before planting. Consumes the turn."""
        if building.kind == BuildingKind.FORESTER:
            if not building.enabled_plant_recipes():
                return False
        elif building.kind != BuildingKind.FARM:
            return False
        if not building.allows_planting():
            return False
        if building.kind == BuildingKind.FARM:
            needed = self._farm_needed_seed_keys(building)
            if not needed:
                return False
            if any(int(getattr(villager.inventory, key, 0)) > 0 for key in needed):
                return False
            plant_keys = needed
        else:
            if self._plant_stock_in_inv(villager, building):
                return False
            plant_keys = building.plant_keys()
        # Need room for at least one plantable of this workplace's type.
        if not any(villager.inventory.can_add(1, key=k) for k in plant_keys):
            return False
        dest = self._plant_withdraw_destination(building, plant_keys)
        if dest is None:
            return False
        # Only interrupt for withdraw when planting is part of upcoming work.
        can_sapling, can_berry, can_herb = self._can_plant_from(villager, building)
        if building.kind == BuildingKind.FORESTER and not can_sapling:
            return False
        if building.kind == BuildingKind.FARM:
            if not self._farm_has_unsown_soil(villager, building):
                return False

        villager.state = VillagerState.WORKING
        if (villager.x, villager.y) == dest:
            if villager.work_cooldown > 0:
                return True
            taken = 0
            if dest == self.world.home_pos:
                for key in plant_keys:
                    while (
                        taken < 3
                        and getattr(self.home_storage, key, 0) > 0
                        and villager.inventory.can_add(1, key=key)
                    ):
                        setattr(self.home_storage, key, getattr(self.home_storage, key) - 1)
                        setattr(
                            villager.inventory,
                            key,
                            getattr(villager.inventory, key) + 1,
                        )
                        taken += 1
            else:
                taken = building.withdraw_plantables_to(
                    villager.inventory, max_items=3, keys=plant_keys
                )
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
        ring, takes the first few acceptable BFS paths (nearest-first). Optionally
        seeds the villager path cache for the chosen approach goal.
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

        per_ring = max(1, int(PATH_PICK_MAX_PER_RING))
        for d in sorted(by_dist):
            tried = 0
            for item in by_dist[d]:
                if tried >= per_ring:
                    break
                px, py = pos_fn(item)
                goal = self._walk_goal_for_target(
                    px, py, prefer_adjacent=prefer_adjacent, from_pos=origin
                )
                if goal is None:
                    continue
                path = self.world.find_path(origin, goal)
                tried += 1
                if path is None:
                    continue
                plen = len(path)
                straight = abs(goal[0] - ox) + abs(goal[1] - oy)
                if not self._path_detour_ok(straight, plen):
                    continue
                # Nearest ring with an acceptable path wins — no need to scan further.
                if (
                    villager is not None
                    # Only cache a path that starts at the villager — seeding from
                    # a workplace/search origin teleports or soft-locks movement.
                    and origin == (villager.x, villager.y)
                ):
                    villager._path_cache = list(path)  # type: ignore[attr-defined]
                    villager._path_goal = goal  # type: ignore[attr-defined]
                return item
        return None

    def _find_work_in_building(
        self, villager: Villager, building: Building
    ) -> tuple[int, int] | None:
        can_plant_sapling, can_plant_berry, can_plant_herb = self._can_plant_from(
            villager, building
        )
        if building.kind == BuildingKind.FORESTER:
            allow_collect = bool(building.enabled_recipes())
            allow_plant = bool(building.enabled_plant_recipes()) and building.allows_planting()
        else:
            mode = building.work_mode
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
                chosen = self._pick_nearest_reachable(
                    origin,
                    plant,
                    pos_fn=lambda p: p,
                    villager=villager,
                    max_radius=WORK_SEARCH_RADIUS,
                )
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
            if allow_collect and building.kind == BuildingKind.FORESTER:
                collect = self._find_forester_collect_by_priority(villager, building)
                return collect[0] if collect is not None else None
            if allow_collect:
                return self._pick_nearest_reachable(
                    origin,
                    gather,
                    pos_fn=lambda p: p,
                    villager=villager,
                    max_radius=WORK_SEARCH_RADIUS,
                )
            return self._pick_nearest_reachable(
                origin,
                plant,
                pos_fn=lambda p: p,
                villager=villager,
                max_radius=WORK_SEARCH_RADIUS,
            )

        # No areas: whole-map behaviour from work_mode.
        ox, oy = building.center_cell()
        if building.kind == BuildingKind.FORESTER:
            collect = (
                self._find_forester_collect_by_priority(villager, building)
                if allow_collect
                else None
            )
            plant = None
            plant_prio = RECIPE_PRIORITY_MAX + 1
            if allow_plant and can_plant_sapling:
                for recipe in building.enabled_plant_recipes():
                    if not self._can_plant_recipe(villager, building, recipe.name):
                        continue
                    target = self._find_forester_plant_target(
                        villager,
                        building,
                        claimed,
                        recipe_name=recipe.name,
                    )
                    if target is None:
                        continue
                    prio = building.get_recipe_priority(recipe.name)
                    if plant is None or prio < plant_prio:
                        plant = target
                        plant_prio = prio
            if collect is not None and plant is not None:
                if plant_prio <= collect[1]:
                    return plant
                return collect[0]
            if plant is not None:
                return plant
            if collect is not None:
                return collect[0]
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
        max_radius: int | None = None,
    ) -> tuple[int, int] | None:
        best: tuple[int, int] | None = None
        best_d = 10**9
        cells = self.world.cells
        rows = self.world.rows
        cols = self.world.cols
        r_max = WORK_SEARCH_RADIUS if max_radius is None else max(0, int(max_radius))
        for y in range(max(0, oy - r_max), min(rows, oy + r_max + 1)):
            row = cells[y]
            for x in range(max(0, ox - r_max), min(cols, ox + r_max + 1)):
                d = abs(x - ox) + abs(y - oy)
                if d > r_max or d >= best_d:
                    continue
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
                best_d = d
                best = (x, y)
                if best_d == 0:
                    return best
        return best

    def _forager_has_nearby_work(
        self, villager: Villager, building: Building
    ) -> bool:
        """True if any enabled forage target exists in search radius (no pathfinding)."""
        from wildlife import AnimalKind

        origin = (villager.x, villager.y)
        ox, oy = origin
        r = WORK_SEARCH_RADIUS
        enabled = {rec.name for rec in building.enabled_recipes()}
        if "honey" in enabled and self._under_production_max(building, "honey"):
            for colony in self.wildlife.colonies:
                if (
                    colony.kind == AnimalKind.BEE
                    and colony.can_harvest()
                    and abs(colony.x - ox) + abs(colony.y - oy) <= r
                ):
                    return True

        forage_areas = [
            a
            for a in building.areas
            if a.task_type
            in (
                TaskType.FULL_FORAGE,
                TaskType.FORAGE_BERRIES,
                TaskType.FORAGE_MUSHROOMS,
                TaskType.FORAGE_HERBS,
            )
        ]

        def cell_ok(x: int, y: int) -> bool:
            cell = self.world.get_cell(x, y)
            if cell is None or not self.world.is_walkable(x, y):
                return False
            key = self._forage_key_for_cell(cell)
            return (
                key is not None
                and key in enabled
                and self._building_allows_cell(building, cell)
            )

        if forage_areas:
            for area in forage_areas:
                for x, y in area.cells():
                    if cell_ok(x, y):
                        return True
            return False

        for key in enabled:
            if key == "honey":
                continue
            for x, y in self._forage_cells_for_key(key):
                if abs(x - ox) + abs(y - oy) > r:
                    continue
                if cell_ok(x, y):
                    return True
        return False

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

        Scans the forage index once, then path-tests only the best few candidates
        (not one full path search per enabled recipe).
        """
        ox, oy = origin
        band = max(1, int(FORAGER_PRIORITY_BAND))
        recipe_meta: list[tuple[str, int, str, int]] = []
        for recipe in building.enabled_recipes():
            priority = building.get_recipe_priority(recipe.name)
            need = self._forage_yield_amount(recipe.name)
            cargo_key = "wood" if recipe.name == "wood" else recipe.name
            if recipe.outputs:
                cargo_key = next(iter(recipe.outputs))
            if not villager.inventory.can_add(need, key=cargo_key):
                continue
            recipe_meta.append((recipe.name, priority, cargo_key, need))
        if not recipe_meta:
            villager.forage_colony_id = None
            return None

        candidates: list[tuple[int, int, int, tuple[int, int], int | None]] = []

        def consider_cell(x: int, y: int) -> None:
            if (x, y) in claimed:
                return
            cell = self.world.get_cell(x, y)
            if cell is None or not self.world.is_walkable(x, y):
                return
            if not self._building_allows_cell(building, cell):
                return
            key = self._forage_key_for_cell(cell)
            if key is None:
                return
            for name, priority, _cargo_key, _need in recipe_meta:
                if name != key:
                    continue
                dist = abs(x - ox) + abs(y - oy)
                if dist > WORK_SEARCH_RADIUS:
                    return
                candidates.append((dist // band, priority, dist, (x, y), None))
                return

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
                    consider_cell(x, y)
        else:
            enabled_keys = {name for name, *_ in recipe_meta if name != "honey"}
            index = self._ensure_forage_cell_index()
            for key in enabled_keys:
                for x, y in index.get(key, []):
                    consider_cell(x, y)

        for name, priority, _cargo_key, _need in recipe_meta:
            if name != "honey":
                continue
            colony = self._find_honey_colony(
                villager, building, origin=origin
            )
            if colony is None:
                continue
            dist = abs(colony.x - ox) + abs(colony.y - oy)
            if dist <= WORK_SEARCH_RADIUS:
                candidates.append(
                    (dist // band, priority, dist, (colony.x, colony.y), colony.id)
                )

        if not candidates:
            villager.forage_colony_id = None
            return None

        candidates.sort(key=lambda c: (c[0], c[1], c[2], c[3]))
        path_tries = max(1, int(PATH_PICK_MAX_PER_RING)) * 3
        tried = 0
        for _band, _prio, _dist, target, colony_id in candidates:
            if tried >= path_tries:
                break
            tried += 1
            goal = self._walk_goal_for_target(
                target[0], target[1], prefer_adjacent=False, from_pos=origin
            )
            if goal is None:
                continue
            path = self.world.find_path(origin, goal)
            if path is None:
                continue
            straight = abs(goal[0] - ox) + abs(goal[1] - oy)
            if not self._path_detour_ok(straight, len(path)):
                continue
            villager.forage_colony_id = colony_id
            if colony_id is not None:
                self._register_colony_claim(colony_id)
            self._register_field_claim(villager, target)
            if origin == (villager.x, villager.y):
                villager._path_cache = list(path)  # type: ignore[attr-defined]
                villager._path_goal = goal  # type: ignore[attr-defined]
            return target

        villager.forage_colony_id = None
        return None

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
        if not self._under_production_max(building, "honey"):
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
        self._forage_index_age = 0

    def _maybe_invalidate_forage_index(self) -> None:
        """Rebuild forage cells every ~32 ticks, not every live tick."""
        self._forage_index_age = getattr(self, "_forage_index_age", 0) + 1
        if self._forage_index_age >= 32:
            self._invalidate_forage_index()

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
        max_radius: int | None = None,
    ) -> tuple[int, int] | None:
        if not can_plant_sapling:
            return None
        cells = self.world.cells
        rows = self.world.rows
        cols = self.world.cols
        r_max = WORK_SEARCH_RADIUS if max_radius is None else max(0, int(max_radius))
        for dist in range(0, r_max + 1):
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
        if cell.feature == FeatureType.ROCK and cell.deposit > 0:
            return "rock"
        if cell.feature == FeatureType.WOOD_BUSH and cell.deposit > 0:
            return "wood"
        if cell.feature == FeatureType.BERRY_BUSH and cell.deposit > 0:
            return "berries"
        if cell.feature == FeatureType.REED:
            from wild_species import is_harvestable, resolve_species

            species = resolve_species("REED", cell.crop_kind)
            if not is_harvestable(species):
                return None
            return (species.resource_key if species is not None else None) or "reeds"
        if cell.feature in (FeatureType.HERB, FeatureType.WILD_CROP):
            crop = CROP_BY_KEY.get(cell.crop_kind or "sage", CROP_BY_KEY["sage"])
            return crop.produce_key
        if cell.feature == FeatureType.TREE and cell.deposit > 0:
            from trees import resolve_tree

            return resolve_tree(cell.tree_species).yield_key
        return None

    def _building_allows_cell(self, building: Building, cell) -> bool:
        """Respect gather-recipe toggles and Max for forester / forager cells."""
        if building.kind == BuildingKind.FORESTER:
            if cell.feature == FeatureType.TREE and cell.deposit > 0:
                from trees import resolve_tree

                key = resolve_tree(cell.tree_species).yield_key
                return building.allows_tree_yield(key) and self._under_production_max(
                    building, key
                )
            return True
        if building.kind == BuildingKind.FORAGER:
            key = self._forage_key_for_cell(cell)
            if key is None:
                return True
            # Reeds have no recipe toggle — leave them for manual collection.
            if key == "reeds":
                return False
            return building.allows_forage_key(key) and self._under_production_max(
                building, key
            )
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
            if cell.feature in (FeatureType.HERB, FeatureType.WILD_CROP):
                return True
            if cell.feature == FeatureType.REED:
                from wild_species import is_harvestable, resolve_species

                return is_harvestable(resolve_species("REED", cell.crop_kind))
            return False
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
            if cell.feature == FeatureType.ROCK and cell.deposit > 0:
                return True
            if cell.feature == FeatureType.WOOD_BUSH and cell.deposit > 0:
                return True
            if cell.feature == FeatureType.BERRY_BUSH and cell.deposit > 0:
                return True
            if cell.feature in (FeatureType.HERB, FeatureType.WILD_CROP):
                return True
            if cell.feature == FeatureType.REED:
                from wild_species import is_harvestable, resolve_species

                return is_harvestable(resolve_species("REED", cell.crop_kind))
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
        if building.kind == BuildingKind.FORESTER:
            allow_collect = bool(building.enabled_recipes())
            allow_plant = bool(building.enabled_plant_recipes()) and building.allows_planting()
        else:
            allow_collect = mode in (WorkMode.COLLECT, WorkMode.ALL)
            allow_plant = mode in (WorkMode.PLANT, WorkMode.ALL) and building.allows_planting()
        can_plant_sapling, can_plant_berry, can_plant_herb = self._can_plant_from(
            villager, building
        )
        if not allow_plant:
            can_plant_sapling = can_plant_berry = can_plant_herb = False
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
            and self._under_production_max(building, "honey")
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
                    self._spend_work_energy(villager)
                    self._gain_job_skill(villager, building.kind.name)
                return

        did_work = False
        if (
            allow_collect
            and cell.feature == FeatureType.TREE
            and (TaskType.CHOP_TREES in tasks or TaskType.FULL_MANAGE in tasks)
            and self._building_allows_cell(building, cell)
        ):
            if self._chop_tree(x, y, inv, status=False, require_axe=require_axe):
                did_work = True
        elif allow_collect and cell.feature == FeatureType.ROCK and (
            TaskType.COLLECT_ROCKS in tasks or TaskType.FULL_FORAGE in tasks
        ) and self._building_allows_cell(building, cell):
            if self._collect_rock(x, y, inv, status=False):
                did_work = True
        elif (
            allow_collect
            and cell.feature == FeatureType.MUSHROOM
            and (TaskType.FORAGE_MUSHROOMS in tasks or TaskType.FULL_FORAGE in tasks)
            and self._building_allows_cell(building, cell)
        ):
            if self._collect_mushroom(x, y, inv, status=False):
                did_work = True
        elif (
            allow_collect
            and cell.feature == FeatureType.WOOD_BUSH
            and TaskType.FULL_FORAGE in tasks
            and self._building_allows_cell(building, cell)
        ):
            if self._collect_wood_bush(x, y, inv, status=False):
                did_work = True
        elif (
            allow_collect
            and cell.feature == FeatureType.BERRY_BUSH
            and (TaskType.FORAGE_BERRIES in tasks or TaskType.FULL_FORAGE in tasks)
            and self._building_allows_cell(building, cell)
        ):
            if self._collect_berries(x, y, inv, status=False):
                did_work = True
        elif (
            allow_collect
            and cell.feature in (FeatureType.HERB, FeatureType.WILD_CROP, FeatureType.REED)
            and (TaskType.FORAGE_HERBS in tasks or TaskType.FULL_FORAGE in tasks)
            and self._building_allows_cell(building, cell)
        ):
            if cell.feature == FeatureType.REED:
                from wild_species import is_harvestable, resolve_species

                if not is_harvestable(resolve_species("REED", cell.crop_kind)):
                    return
            if self._collect_herb(x, y, inv, status=False):
                did_work = True
        elif (
            allow_collect
            and cell.feature == FeatureType.TREE
            and TaskType.FULL_FORAGE in tasks
            and self._building_allows_cell(building, cell)
        ):
            if self._chop_tree(x, y, inv, status=False, require_axe=require_axe):
                did_work = True
        elif allow_plant and cell.feature == FeatureType.NONE:
            # Prefer inventory stock (filled by storage withdraw). Fall back to remote pull.
            if building.kind == BuildingKind.FORESTER and (
                TaskType.PLANT_SAPLINGS in tasks or TaskType.FULL_MANAGE in tasks
            ):
                recipe = self._pick_forester_plant_recipe(villager, building)
                if recipe is not None and self._ensure_sapling_for_recipe(
                    villager, building, recipe.name
                ):
                    if self._plant_sapling_recipe(x, y, inv, recipe.name):
                        did_work = True
        if did_work:
            self._spend_work_energy(villager)
            self._gain_job_skill(villager, building.kind.name)

    def _step_villager_toward(self, villager: Villager, goal: tuple[int, int]) -> bool:
        """Step along a path toward goal. Returns False if the goal is unreachable."""
        if villager.move_cooldown > 0:
            return True
        if (villager.x, villager.y) == goal:
            return True
        cache_goal = getattr(villager, "_path_goal", None)
        cache: list[tuple[int, int]] | None = getattr(villager, "_path_cache", None)
        # Drop stale caches (e.g. seeded from a workplace instead of the villager).
        if cache and cache_goal == goal:
            nxt = cache[0]
            if max(abs(nxt[0] - villager.x), abs(nxt[1] - villager.y)) > 1:
                cache = None
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
        villager.energy = max(
            0.0,
            villager.energy
            - ENERGY_MOVE_DRAIN * self._temp_energy_mult(villager.inventory),
        )
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
        if self.overlay_mode == OverlayMode.EROSION:
            self.overlay_values = [row[:] for row in self.env_maps.erosion]
            return
        if self.overlay_mode == OverlayMode.SOIL_MOISTURE:
            self.overlay_values = [row[:] for row in self.env_maps.soil_moisture]
            return
        if self.overlay_mode == OverlayMode.TEMPERATURE:
            self.overlay_values = [row[:] for row in self.env_maps.temperature]
            return
        if self.overlay_mode == OverlayMode.FIELD_YIELD:
            cols, rows = self.world.cols, self.world.rows
            grid = [[0.0] * cols for _ in range(rows)]
            field = self._field_plan_building()
            if field is None:
                sel = self._selected_building()
                if sel is not None and sel.kind == BuildingKind.FIELD:
                    field = sel
            base = float(farm_produce_yield()) or 1.0
            if field is not None:
                for x, y in field.plot_cells():
                    yld = self._farm_produce_yield_at(x, y)
                    # High = good; normalised to base so ~1.0 is max potential.
                    grid[y][x] = max(0.0, min(1.0, float(yld) / base))
            self.overlay_values = grid
            return
        self.overlay_values = build_overlay_grid(self.world, self.overlay_mode)

    def _update_status_timer(self) -> None:
        if self.status_timer > 0:
            self.status_timer -= 1
            if self.status_timer == 0:
                self.status_message = ""

    def _update_simulation(self) -> None:
        self._maybe_invalidate_forage_index()
        self.day_tick -= 1
        if self.day_tick <= 0:
            day = float(self.calendar_day) + (
                1.0 / max(1, self.ticks_per_day)
            )
            pending = getattr(self, "_eco_pending", 0) + 1
            self._tick_world_ecology(pending, day=day)
            self._eco_pending = 0
            self.day_tick = self.ticks_per_day
            self._advance_day()
            day = float(self.calendar_day)
        else:
            day = float(self.calendar_day) + (1.0 - self.day_tick / self.ticks_per_day)
            self._eco_pending = getattr(self, "_eco_pending", 0) + 1
            if self._eco_pending >= 16:
                self._tick_world_ecology(self._eco_pending, day=day)
                self._eco_pending = 0
        self._update_villagers()
        self._tick_player(1)
        self._tick_food_spoilage()
        self._tick_arrow_shots()
        self._wildlife_pending = getattr(self, "_wildlife_pending", 0) + 1
        if self._wildlife_pending >= 4:
            self._tick_wildlife(day)
            self.fish.tick(self.world, day)
            self._wildlife_pending = 0
        # Biodiversity is sample-based; skip live refresh for sampled modes.
        if self.overlay_mode not in (
            OverlayMode.NONE,
            OverlayMode.BIODIVERSITY,
            OverlayMode.FLORAL_RESOURCES,
            OverlayMode.POLLINATION,
            OverlayMode.EROSION,
            OverlayMode.SOIL_MOISTURE,
            OverlayMode.TEMPERATURE,
            OverlayMode.FIELD_YIELD,
        ):
            self._refresh_indicators()
        try:
            if self.bug_log.enabled:
                self.bug_log.scan(self)
        except Exception:
            pass

    def _advance_sim_ticks(self, ticks: int, *, flush: bool = True) -> None:
        """Advance `ticks` simulation steps, batching idle waits and ecology."""
        remaining = ticks
        eco_pending = getattr(self, "_eco_pending", 0)
        wildlife_pending = getattr(self, "_wildlife_pending", 0)

        def flush_eco(day: float) -> None:
            nonlocal eco_pending
            if eco_pending <= 0:
                return
            self._tick_world_ecology(eco_pending, day=day)
            eco_pending = 0

        while remaining > 0:
            skip = self._idle_cooldown_skip(remaining)
            day = float(self.calendar_day) + (1.0 - self.day_tick / self.ticks_per_day)

            if skip > 1:
                self._idle_skip_events += 1
                self._idle_skip_ticks += skip
                self._forage_index_age = getattr(self, "_forage_index_age", 0) + skip
                if self._forage_index_age >= 32:
                    self._invalidate_forage_index()
                flush_eco(day)
                for villager in self.villagers:
                    traveling = self._apply_travel_skip(villager, skip)
                    if not traveling:
                        villager.move_cooldown = max(0, villager.move_cooldown - skip)
                    villager.work_cooldown = max(0, villager.work_cooldown - skip)
                    villager.decision_cooldown = max(
                        0, villager.decision_cooldown - skip
                    )
                    search_cd = int(getattr(villager, "_work_search_cd", 0) or 0)
                    if search_cd > 0:
                        villager._work_search_cd = max(0, search_cd - skip)  # type: ignore[attr-defined]
                    if villager.state == VillagerState.SLEEPING:
                        house = self.buildings.get(villager.housing_id or -1)
                        at_home = (
                            house is not None
                            and (villager.x, villager.y) == house.center_cell()
                        )
                        if at_home:
                            villager.energy = min(
                                1.0,
                                villager.energy
                                + self._legacy_per_tick(ENERGY_SLEEP_GAIN) * skip,
                            )
                            if villager.energy >= 0.95:
                                villager.state = VillagerState.IDLE
                                villager.target = None
                    else:
                        villager.satiation = max(
                            0.0,
                            villager.satiation
                            - self._satiation_decay()
                            * villager.food_hunger_mult
                            * skip,
                        )
                self._tick_player(skip)
                self._tick_food_spoilage(skip)
                eco_left = skip
                while eco_left > 0:
                    step = min(eco_left, self.day_tick)
                    self.day_tick -= step
                    eco_left -= step
                    if self.day_tick <= 0:
                        self.day_tick = self.ticks_per_day
                        self._advance_day()
                day = float(self.calendar_day)
                self._tick_world_ecology(skip, day=day)
                wildlife_pending += skip
                while wildlife_pending >= 4:
                    self._tick_wildlife(day)
                    self.fish.tick(self.world, day)
                    wildlife_pending -= 4
                remaining -= skip
                continue

            # Single active tick (someone can act).
            self._maybe_invalidate_forage_index()
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
            self._tick_player(1)
            self._tick_food_spoilage(1)
            self._tick_arrow_shots()
            if wildlife_pending >= 4:
                self._tick_wildlife(day)
                self.fish.tick(self.world, day)
                wildlife_pending = 0
            remaining -= 1

        self._eco_pending = eco_pending
        self._wildlife_pending = wildlife_pending
        if flush:
            day = float(self.calendar_day) + (1.0 - self.day_tick / self.ticks_per_day)
            flush_eco(day)
            self._eco_pending = 0
            if self._wildlife_pending:
                self._tick_wildlife(day)
                self.fish.tick(self.world, day)
                self._wildlife_pending = 0

    def _villager_travel_goal(self, villager: Villager) -> tuple[int, int] | None:
        """Cell this villager is currently walking toward, if any."""
        if villager.hunt_shot is not None:
            return None
        if villager.target is not None and (villager.x, villager.y) != villager.target:
            return villager.target
        path_goal = getattr(villager, "_path_goal", None)
        if (
            path_goal is not None
            and (villager.x, villager.y) != path_goal
        ):
            return path_goal
        if (
            villager.hunt_meat_pos is not None
            and (villager.x, villager.y) != villager.hunt_meat_pos
        ):
            return villager.hunt_meat_pos
        if villager.state == VillagerState.DELIVERING:
            home = self.world.home_pos
            if (villager.x, villager.y) != home:
                return home
        if (
            villager.state == VillagerState.HAULING
            and villager.haul_building_id is not None
        ):
            building = self.buildings.get(villager.haul_building_id)
            if building is not None:
                dest = building.center_cell()
                if (villager.x, villager.y) != dest:
                    return dest
        return None

    def _villager_is_traveling(self, villager: Villager) -> bool:
        """True when the next real act is walking toward a destination."""
        return self._villager_travel_goal(villager) is not None

    def _ensure_travel_path(self, villager: Villager) -> list[tuple[int, int]] | None:
        goal = self._villager_travel_goal(villager)
        if goal is None:
            return None
        cache_goal = getattr(villager, "_path_goal", None)
        cache: list[tuple[int, int]] | None = getattr(villager, "_path_cache", None)
        if cache and cache_goal == goal:
            nxt = cache[0]
            if max(abs(nxt[0] - villager.x), abs(nxt[1] - villager.y)) <= 1:
                return cache
        path = self.world.find_path((villager.x, villager.y), goal)
        villager._path_cache = path if path is not None else []  # type: ignore[attr-defined]
        villager._path_goal = goal  # type: ignore[attr-defined]
        cache = villager._path_cache  # type: ignore[attr-defined]
        return cache or None

    def _hunger_cap_ticks(self, villager: Villager, wait: int) -> int:
        decay = self._satiation_decay() * villager.food_hunger_mult
        if decay <= 0:
            return max(1, wait)
        headroom = villager.satiation - villager.eat_threshold()
        if headroom <= 0:
            return 1
        return max(1, min(wait, math.ceil(headroom / decay)))

    def _travel_ticks_to_arrive(self, villager: Villager) -> int:
        """Ticks until the last path step is taken (inclusive of that step)."""
        # Moving prey: skip only the wait, then re-path on a real tick.
        if villager.hunt_animal_id is not None or villager.hunt_colony_id is not None:
            wait = max(1, villager.move_cooldown)
            if villager.needs_food() or villager.seeking_food:
                return wait
            return self._hunger_cap_ticks(villager, wait)
        path = self._ensure_travel_path(villager)
        if not path:
            return 1
        interval = max(1, self._villager_move_interval(villager))
        steps = len(path)
        cd = max(0, villager.move_cooldown)
        if cd <= 0:
            ticks = 1 + (steps - 1) * interval
        else:
            ticks = cd + (steps - 1) * interval
        if villager.needs_food() or villager.seeking_food:
            return max(1, ticks)
        return self._hunger_cap_ticks(villager, ticks)

    def _apply_travel_skip(self, villager: Villager, ticks: int) -> bool:
        """Walk along a cached path for ``ticks``. Returns True if traveling."""
        if ticks <= 0 or not self._villager_is_traveling(villager):
            return False
        chasing = (
            villager.hunt_animal_id is not None or villager.hunt_colony_id is not None
        )
        path = None if chasing else self._ensure_travel_path(villager)
        if not chasing and not path:
            villager.move_cooldown = max(0, villager.move_cooldown - ticks)
            return True
        drain = ENERGY_MOVE_DRAIN * self._temp_energy_mult(villager.inventory)
        goal = self._villager_travel_goal(villager)
        for _ in range(ticks):
            if villager.move_cooldown > 0:
                villager.move_cooldown -= 1
            if chasing or not path or goal is None:
                continue
            if (villager.x, villager.y) == goal:
                continue
            if villager.move_cooldown == 0:
                step = path.pop(0)
                interval = max(1, self._villager_move_interval(villager))
                note_cell_step(villager, step[0], step[1])
                self._record_path_traffic(step[0], step[1])
                villager.move_cooldown = interval
                arm_cell_step_visual(villager, interval)
                villager.energy = max(0.0, villager.energy - drain)
                self._travel_skip_steps += 1
        return True

    def _ticks_until_villager_action(self, villager: Villager) -> int:
        """Ticks until this villager needs a real AI/work pass."""
        if villager.hunt_shot is not None:
            return 1

        traveling = self._villager_is_traveling(villager)

        if villager.seeking_food or villager.job_change_deposit:
            if traveling:
                return self._travel_ticks_to_arrive(villager)
            return 1
        if villager.needs_food():
            return 1

        if villager.state == VillagerState.SLEEPING:
            house = self.buildings.get(villager.housing_id or -1)
            at_home = (
                house is not None
                and (villager.x, villager.y) == house.center_cell()
            )
            if not at_home:
                if traveling:
                    return self._travel_ticks_to_arrive(villager)
                return 1 if villager.move_cooldown <= 0 else villager.move_cooldown
            remain = 0.95 - villager.energy
            if remain <= 0:
                return 1
            return max(
                1, math.ceil(remain / max(1e-9, self._legacy_per_tick(ENERGY_SLEEP_GAIN)))
            )

        if self._idle_decision_pending(villager):
            return self._hunger_cap_ticks(villager, max(1, villager.decision_cooldown))

        search_cd = int(getattr(villager, "_work_search_cd", 0) or 0)
        if search_cd > 0 and not traveling:
            return self._hunger_cap_ticks(villager, search_cd)

        # Standing on the work/haul cell: only work cooldown (not leftover move_cd).
        if (
            villager.target is not None
            and (villager.x, villager.y) == villager.target
        ):
            if villager.work_cooldown <= 0:
                return 1
            return self._hunger_cap_ticks(villager, villager.work_cooldown)

        if traveling:
            return self._travel_ticks_to_arrive(villager)

        if villager.work_cooldown > 0:
            return self._hunger_cap_ticks(villager, villager.work_cooldown)
        if villager.move_cooldown > 0:
            return self._hunger_cap_ticks(villager, villager.move_cooldown)
        return 1

    def _idle_cooldown_skip(self, limit: int) -> int:
        """Largest N≤limit where every villager can be bulk-advanced."""
        if (
            not getattr(self, "_cooldown_skip_enabled", True)
            or limit <= 1
            or not self.villagers
        ):
            return 1
        if getattr(self, "_arrow_shots", None):
            return 1
        skip = min(limit, max(1, self.day_tick))
        for villager in self.villagers:
            wait = self._ticks_until_villager_action(villager)
            if wait <= 1:
                return 1
            skip = min(skip, wait)
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
        self._center_cache = {}
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
        self._draw_arrow_shots()
        self._draw_player()
        self._draw_player_status_hud()
        self._draw_overlay_hud()
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
            playback_ticks=self._playback_ticks(),
            walk_seconds=self._walk_seconds(),
            work_seconds=self._work_seconds(),
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
            housed=housed_count(self.villagers),
            needing=len(self.villagers),
            regional_wealth=self.regional_wealth,
            overlay_mode=self.overlay_mode,
        )
        self.toolbar.draw(
            self.screen,
            self.place_kind,
            self._selected_building(),
            self.sim_speed,
            mouse,
            season_label=(
                f"{format_date(self.calendar_day)}  "
                f"Temperature: {ambient_temperature_c(self.calendar_day):.0f}C"
            ),
            field_crop=self.field_crop_kind,
            built_kinds=unlock_built_kinds(self.buildings),
        )
        field_b = self._field_plan_building()
        field_overview = (
            self._field_crop_overview(field_b) if field_b is not None else None
        )
        field_env = self._field_env_status(field_b) if field_b is not None else None
        field_yield = (
            self._field_yield_summary(field_b) if field_b is not None else None
        )
        field_headline = self._field_headline(field_b) if field_b is not None else ""
        embed_field = (
            self.management.open
            and self.management.tab == MgmtTab.BUILDINGS
            and self.field_plan_dialog.open
        )
        inspect_b = self._inspect_building()
        hire_candidates = None
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
            hire_candidates = list(self.hire_candidates)
        elif is_housing_kind(inspect_b.kind):
            inspect_workers = [
                v
                for v in self.villagers
                if v.housed and v.housing_id == inspect_b.id
            ]
            storage_amounts = None
            hired_count = 0
        else:
            inspect_workers = [v for v in self.villagers if v.building_id == inspect_b.id]
            storage_amounts = None
            hired_count = 0

        def _draw_building_detail(surf: pygame.Surface, rect: pygame.Rect) -> None:
            if field_b is not None and embed_field:
                self.field_plan_dialog.configure_embed(rect)
                if self.overlay_mode == OverlayMode.FIELD_YIELD:
                    self._refresh_indicators()
                self.field_plan_dialog.draw(
                    surf,
                    field_b,
                    crop_overview=field_overview,
                    env_status=field_env,
                    yield_summary=field_yield,
                    headline=field_headline,
                    current_season=self.season,
                    mouse_pos=mouse,
                    yield_map_active=self.overlay_mode == OverlayMode.FIELD_YIELD,
                    debug=bool(getattr(self.bug_log, "enabled", False)),
                )
                return
            if inspect_b is None:
                return
            self.building_inspect.configure_embed(rect)
            self.building_inspect.draw(
                surf,
                inspect_b,
                inspect_workers,
                selected_villager_id=self.selected_villager_id,
                mouse_pos=mouse,
                storage_amounts=storage_amounts,
                player_inventory=self.player.inventory,
                hired_count=hired_count,
                hire_candidates=hire_candidates,
                food_amounts=self._village_food_amounts(),
                free_beds=free_housing_beds(self.buildings, self.villagers),
                housing_level=max_housing_level(self.buildings),
                area_draw_task=self.area_draw_task,
                home_storage=self.home_storage,
                market_offer_fn=(
                    (lambda b, k: self._market_offer_amount(b, k))
                    if inspect_b is not None and inspect_b.is_market()
                    else None
                ),
                village_stock=self._village_stock_amounts(),
                crop_overview=(
                    self._farm_crop_overview(inspect_b)
                    if inspect_b.kind == BuildingKind.FARM
                    else None
                ),
                env_status=(
                    self._farm_env_status(inspect_b)
                    if inspect_b.kind == BuildingKind.FARM
                    else None
                ),
                current_season=self.season,
            )

        def _draw_villager_detail(surf: pygame.Surface, rect: pygame.Rect) -> None:
            inspect_v = self._get_villager(self.management.selected_villager_id or -1)
            if inspect_v is None:
                return
            self.villager_inspect.configure_embed(rect)
            self.villager_inspect.draw(
                surf,
                inspect_v,
                building_icon_for=self._building_icon_for_id,
                housing_icon=self._villager_housing_icon(inspect_v),
                current_season=self.season,
                calendar_day=self.calendar_day,
                mouse_pos=mouse,
                player_inventory=self.player.inventory,
                requirement_rows=villager_requirement_rows(
                    inspect_v,
                    self.buildings,
                    self._village_food_amounts(),
                    housing_icon=self._villager_housing_icon(inspect_v),
                ),
                activity_label=self._villager_activity_label(inspect_v),
            )

        hire_entries = None
        can_hire_fn = None
        if self.management.open and self.management.people_mode == "hire":
            foods = self._village_food_amounts()
            beds = free_housing_beds(self.buildings, self.villagers)
            lvl = max_housing_level(self.buildings)
            hire_entries = self._hire_roster_entries()

            def can_hire_fn(entry):
                return (
                    beds > 0
                    and lvl >= entry.housing_need
                    and staple_food_available(foods, entry.required_foods)
                )

        if self.management.open:
            if self.management.selected_habitat is not None:
                kind, pid = self.management.selected_habitat
                if (
                    self.selected_habitat_kind != kind
                    or self.selected_habitat_id != pid
                ):
                    self.selected_habitat_kind = kind
                    self.selected_habitat_id = pid
            self.management.draw(
                self.screen,
                villagers=self.villagers,
                buildings=self.buildings,
                construction_sites=self.construction_sites,
                wildlife_rows=self._wildlife_management_rows(),
                habitat_view=self._habitat_inspect_view(),
                mouse_pos=mouse,
                hire_entries=hire_entries,
                can_hire=can_hire_fn,
                food_amounts=self._village_food_amounts(),
                draw_villager_detail=_draw_villager_detail,
                draw_building_detail=_draw_building_detail,
            )
        else:
            # Villager/building inspect only live inside Management — never float.
            if self.building_inspect.open:
                self.building_inspect.close()
            if self.villager_inspect.open:
                self.villager_inspect.close()
            if self.field_plan_dialog.open and self.field_plan_dialog.embedded:
                self.field_plan_dialog.close()
        if self.assign_picker.open:
            self.assign_picker.draw(
                self.screen,
                villagers=self.villagers,
                buildings=self.buildings,
                mouse_pos=mouse,
                job_label=self._villager_assignment_label,
            )
        if self.player_inventory.open:
            self.player_inventory.draw(
                self.screen, self.player, mouse_pos=mouse
            )
        self.resource_inspect.draw(self.screen, mouse_pos=mouse)
        self.resource_tracker.draw(
            self.screen,
            self.resource_history,
            stock_now=self._village_stock_amounts(),
            mouse_pos=mouse,
        )
        self.balance_dialog.draw(self.screen, self.balance, mouse_pos=mouse)
        if self.villager_roster.open:
            if self.villager_roster.mode == "hire":
                foods = self._village_food_amounts()
                beds = free_housing_beds(self.buildings, self.villagers)
                lvl = max_housing_level(self.buildings)

                def _can_hire(entry) -> bool:
                    return (
                        beds > 0
                        and lvl >= entry.housing_need
                        and staple_food_available(foods, entry.required_foods)
                    )

                self.villager_roster.draw(
                    self.screen,
                    self._hire_roster_entries(),
                    mouse_pos=mouse,
                    title=f"Travellers ({len(self.hire_candidates)})",
                    subtitle=(
                        f"Hired {len(self.villagers)}/{MAX_VILLAGERS}  ·  "
                        f"Beds free {beds}  ·  Housing lvl {lvl}"
                    ),
                    show_hire_actions=True,
                    can_hire=_can_hire,
                )
            else:
                bid = self.villager_roster.assign_building_id
                b = self.buildings.get(bid) if bid is not None else None
                subtitle = None
                if self.villager_roster.mode == "assign" and b is not None:
                    subtitle = f"Assign to {BUILDING_LABELS[b.kind]} #{b.id}"
                self.villager_roster.draw(
                    self.screen,
                    self._roster_entries_for_villagers(),
                    mouse_pos=mouse,
                    subtitle=subtitle,
                )
        # Modals last so they sit above the market inspect / management panes.
        self.file_dialog.draw(self.screen)
        self.number_input.draw(self.screen)
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
            # Bump when soft-join math changes so in-session rebakes pick it up.
            "ms-soft-mottle-v2",
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
        try:
            from terrain_fills import clear_fill_cache

            clear_fill_cache()
        except ImportError:
            pass
        try:
            from terrain_mottle import clear_mottle_cache

            clear_mottle_cache()
        except ImportError:
            pass
        # Density fields are seed-stable; terrain paint only needs remask.

    def _visual_terrain_at(
        self, x: int, y: int, farm_cells: set[tuple[int, int]]
    ) -> TerrainType:
        """Terrain used for tiling; farm plots render as soil.

        Worn paths keep their underlying ``cell.terrain`` for simulation, but
        tile as PATH so the sandy trail texture shows (including under height warp).
        """
        if not (0 <= x < self.world.cols and 0 <= y < self.world.rows):
            # Out of bounds matches nearest edge cell so borders stay solid.
            cx = min(max(0, x), self.world.cols - 1)
            cy = min(max(0, y), self.world.rows - 1)
            if (cx, cy) in farm_cells:
                return TerrainType.SOIL
            cell = self.world.cells[cy][cx]
            if cell.path_worn and cell.terrain != TerrainType.URBAN:
                return TerrainType.PATH
            return cell.terrain
        if (x, y) in farm_cells:
            return TerrainType.SOIL
        cell = self.world.cells[y][x]
        if cell.path_worn and cell.terrain != TerrainType.URBAN:
            return TerrainType.PATH
        return cell.terrain

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

    def _note_path_visual_change(self) -> None:
        """Path overlay changed — refresh baked height warp and world layer."""
        self._path_visual_gen = int(getattr(self, "_path_visual_gen", 0)) + 1
        self._invalidate_height_sample_cache()
        self._world_layer = None
        self._world_layer_key = None

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
            self._terrain_base.fill(COLOUR_GRASS)
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
            if any(
                self.world.in_bounds(x, y)
                and self.world.cells[y][x].terrain != TerrainType.URBAN
                and not self.world.cells[y][x].path_worn
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

    def _blit_season_mute(
        self, mute: tuple[int, int, int] | None, map_clip: pygame.Rect
    ) -> None:
        if mute is None:
            return
        key = (map_clip.w, map_clip.h, mute)
        surf = getattr(self, "_mute_tint_surf", None)
        if surf is None or getattr(self, "_mute_tint_key", None) != key:
            surf = pygame.Surface((map_clip.w, map_clip.h))
            surf.fill(mute)
            self._mute_tint_surf = surf
            self._mute_tint_key = key
        self.screen.blit(
            surf, map_clip.topleft, special_flags=pygame.BLEND_RGB_MULT
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

    def _season_fade_days(self) -> float:
        try:
            from terrain_settings import get_anim_params

            return max(0.05, float(get_anim_params().fade_days))
        except Exception:
            return self._SEASON_FADE_DAYS

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

    def _path_worn_mask(self) -> pygame.Surface:
        """Half-res coverage for path overlays (not PATH terrain)."""
        key = ("path_worn", self.world.terrain_revision, self._fleck_size())
        # path_worn toggles without bumping terrain_revision — include a wear stamp.
        wear_n = len(self._path_traffic)
        key = ("path_worn", wear_n, self._fleck_size())
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
                if self.world.cells[y][x].path_worn:
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
        if tag == "grass_meadow":
            return self._types_mask(frozenset({TerrainType.GRASS, TerrainType.MEADOW}))
        if tag == "meadow":
            return self._types_mask(frozenset({TerrainType.MEADOW}))
        if tag == "soil":
            return self._types_mask(frozenset({TerrainType.SOIL}))
        if tag == "forest":
            return self._types_mask(frozenset({TerrainType.FOREST_FLOOR}))
        if tag == "rock":
            return self._types_mask(frozenset({TerrainType.ROCK}))
        if tag == "path":
            return self._path_worn_mask()
        if tag == "riparian":
            return self._types_mask(frozenset({TerrainType.RIPARIAN}))
        if tag == "urban":
            return self._types_mask(frozenset({TerrainType.URBAN}))
        if tag == "water":
            return self._types_mask(frozenset({TerrainType.WATER, TerrainType.RIVER}))
        if tag == "all_land":
            from terrain_flecks import MASK_TYPES

            return self._types_mask(MASK_TYPES["all_land"])
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
        from terrain_flecks import period_recipe

        return period_recipe(period)

    def _halo_radius_for_period(self, period: int) -> int:
        from terrain_flecks import halo_radius_for_period

        return halo_radius_for_period(period)

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
        fleck_on = True
        clusters_on = True
        master = 1.0
        cluster_mul = 1.0
        try:
            from terrain_settings import get_anim_params, get_fleck

            period = self._season_fade_to
            if period is None:
                period = self._season_mask_period(self.calendar_day)
            fleck = get_fleck(int(period))
            anim = get_anim_params()
            fleck_on = bool(fleck.enabled)
            clusters_on = bool(fleck.clusters_enabled)
            master = float(anim.opacity) * max(0.0, float(fleck.speckle_alpha))
            if fleck.speckle_alpha > 1e-6:
                cluster_mul = max(0.0, float(fleck.cluster_alpha)) / float(fleck.speckle_alpha)
            else:
                cluster_mul = max(0.0, float(fleck.cluster_alpha))
        except Exception:
            pass
        if not fleck_on:
            return overlay
        for field, (rgb, tag) in recipe.items():
            if field in skip:
                continue
            if field.startswith("cluster") and not clusters_on:
                continue
            density = self._season_densities[field]
            if density is None:
                continue
            layer = self._tint_density(density, rgb)
            mask = self._mask_for(tag, water_mask, halo_radius=halo_radius)
            layer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            scale = alpha_scale * master
            if field.startswith("cluster"):
                scale *= cluster_mul
            if scale < 0.999:
                layer.set_alpha(max(0, min(255, int(255 * scale))))
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
        speed = max(0, int(self.sim_speed) * self._playback_ticks())
        if speed <= 0:
            return False
        total = max(1, int(self.ticks_per_day * self._season_fade_days()))
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
        total = max(1, int(self.ticks_per_day * self._season_fade_days()))
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
        if abs(zoom - 1.0) < 1e-4:
            ox = dest[0] - int(round(sx - src.x))
            oy = dest[1] - int(round(sy - src.y))
            self.screen.blit(piece, (ox, oy), special_flags=special_flags)
            return
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
        map_clip = pygame.Rect(0, MAP_OFFSET_Y, map_view_width(), map_view_height())
        layer_key = (
            round(self.camera.x, 3),
            round(self.camera.y, 3),
            self.camera.view_cell_px(),
            self.world.terrain_revision,
            int(getattr(self, "_path_visual_gen", 0)),
            int(self.calendar_day),
            self.day_tick // 16,
            getattr(self, "_work_gen", 0),
            round(vibrancy, 1),
            int(freeze * 5),
            bool(self.height_sample_enabled),
        )
        layer = getattr(self, "_world_layer", None)
        if (
            layer is not None
            and getattr(self, "_world_layer_key", None) == layer_key
            and layer.get_width() == map_clip.w
            and layer.get_height() == map_clip.h
        ):
            self.screen.blit(layer, map_clip.topleft)
            return

        farm_cells = self._farm_field_cells()
        base, water_mask, grass_mask, soil_mask = self._ensure_terrain_base(farm_cells)
        self.screen.set_clip(map_clip)

        origin = (0, MAP_OFFSET_Y)
        mute = self._ensure_season_mute(vibrancy)
        # Opaque grass underfill: height-warp gaps and SRCALPHA icon punches
        # must not leave dest-alpha holes that later show COLOUR_BG through
        # villager / wildlife sprites.
        self.screen.fill(COLOUR_GRASS, map_clip)

        if self.height_sample_enabled and self.height_sample is not None:
            self._refresh_season_masks(grass_mask, soil_mask, water_mask)
            self._draw_height_sample(base)
            self._blit_season_mute(mute, map_clip)
            if self._season_period_overlay is not None:
                self._blit_camera_world_surface(self._season_period_overlay, origin)
        else:
            self._refresh_season_masks(grass_mask, soil_mask, water_mask)
            ice = self._ensure_ice_overlay(freeze, water_mask)
            self._blit_camera_world_surface(base, origin)
            self._blit_season_mute(mute, map_clip)
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
                elif (
                    cell.feature != FeatureType.NONE
                    or cell.meat_deposit > 0
                    or cell.fish_deposit > 0
                ):
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
            weeds = float(getattr(cell, "weeds", 0.0))
            if cell.feature == FeatureType.CROP_HERB and weeds > 0.04:
                from icons import blit_icon

                weed_size = max(8, int(round(draw_size * (0.4 + 0.6 * weeds))))
                blit_icon(self.screen, "crop_weeds", cx, cy, weed_size)
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
        self._store_opaque_world_layer(map_clip, layer_key)

    def _store_opaque_world_layer(
        self, map_clip: pygame.Rect, layer_key: tuple
    ) -> None:
        """Flatten the map view to 24-bit so entity icons cannot punch to COLOUR_BG.

        SRCALPHA tree/crop blits on a display surface often set dest-alpha to 0
        in transparent texels. Caching that and blitting it back leaves black
        holes behind idle villagers and wildlife.
        """
        size = (map_clip.w, map_clip.h)
        layer = getattr(self, "_world_layer", None)
        if (
            layer is None
            or layer.get_size() != size
            or layer.get_bitsize() != 24
        ):
            layer = pygame.Surface(size, depth=24)
            self._world_layer = layer
        layer.fill(COLOUR_GRASS)
        layer.blit(self.screen, (0, 0), map_clip)
        self._world_layer_key = layer_key
        self.screen.blit(layer, map_clip.topleft)

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
            # Match terrain base fill so height-warp gaps don't read as black seams.
            self.screen.fill(COLOUR_GRASS, wipe)

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
        dest_x = int(round((ix - sx) * zoom))
        dest_y = MAP_OFFSET_Y + int(round((iy - sy) * zoom))
        if abs(zoom - 1.0) < 1e-4:
            self.screen.blit(cache, (dest_x, dest_y), src)
            return
        scaled = pygame.transform.scale(
            cache.subsurface(src),
            (max(1, int(round(src.w * zoom))), max(1, int(round(src.h * zoom)))),
        )
        if scaled.get_bitsize() != 24 and scaled.get_flags() & pygame.SRCALPHA:
            opaque = pygame.Surface(scaled.get_size(), depth=24)
            opaque.blit(scaled, (0, 0))
            scaled = opaque
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
        field_only = self.overlay_mode == OverlayMode.FIELD_YIELD
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if not self.world.in_bounds(x, y):
                    continue
                value = self.overlay_values[y][x]
                if field_only and value <= 0.0:
                    continue
                colour = overlay_colour(self.overlay_mode, value)
                self._draw_height_quad(x, y, colour, OVERLAY_ALPHA)
        self.screen.set_clip(None)

    def _draw_overlay_hud(self) -> None:
        """Show active overlay name and the value under the cursor on the map."""
        if self.overlay_mode == OverlayMode.NONE or self.height_edit_mode:
            return
        name = OVERLAY_LABELS.get(self.overlay_mode, self.overlay_mode.name)
        hover = self._map_cell_from_pos(pygame.mouse.get_pos())
        value_text = "—"
        if hover is not None:
            hx, hy = hover
            if (
                self.overlay_values
                and 0 <= hy < len(self.overlay_values)
                and 0 <= hx < len(self.overlay_values[hy])
            ):
                value_text = format_overlay_value(
                    self.overlay_mode, float(self.overlay_values[hy][hx])
                )
            value_text = f"({hx}, {hy})  {value_text}"

        font = pygame.font.SysFont("menlo", 13, bold=True)
        font_s = pygame.font.SysFont("menlo", 12)
        title = font.render(name, True, COLOUR_TEXT)
        detail = font_s.render(value_text, True, COLOUR_TEXT_DIM)
        pad_x, pad_y, gap = 12, 8, 4
        box_w = max(title.get_width(), detail.get_width()) + pad_x * 2
        box_h = title.get_height() + detail.get_height() + gap + pad_y * 2
        mw = map_view_width()
        x = max(8, (mw - box_w) // 2)
        y = MAP_OFFSET_Y + 8
        panel = pygame.Rect(x, y, box_w, box_h)
        bg = pygame.Surface((panel.w, panel.h), pygame.SRCALPHA)
        bg.fill((24, 26, 32, 210))
        self.screen.blit(bg, panel.topleft)
        pygame.draw.rect(self.screen, COLOUR_TOOLBAR_BORDER, panel, 1, border_radius=4)
        self.screen.blit(title, (panel.x + pad_x, panel.y + pad_y))
        self.screen.blit(
            detail,
            (panel.x + pad_x, panel.y + pad_y + title.get_height() + gap),
        )

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

        # Field tool: 1-cell cursor before the player starts dragging.
        elif (
            self.place_kind == BuildingKind.FIELD
            and not self.drawing
            and not self._placing_field
        ):
            mouse = pygame.mouse.get_pos()
            hover = self._map_cell_from_pos(mouse)
            if hover is not None:
                hx, hy = hover
                overlap = self._field_drag_overlaps(hx, hy, hx, hy)
                colour = (180, 70, 70) if overlap else COLOUR_TASK_FARM
                self._draw_height_quad(hx, hy, colour, 70)
                self._draw_field_plot_outline(
                    hx, hy, hx, hy, colour=colour, width=2, fill_alpha=0
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
                preview = TASK_COLOURS.get(
                    self.area_draw_task or building.draw_task_type,
                    COLOUR_TASK_PREVIEW,
                )
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

        elif (
            self.area_draw_task is not None
            and not self.drawing
            and self.place_kind is None
            and not self._placing_field
        ):
            mouse = pygame.mouse.get_pos()
            hover = self._map_cell_from_pos(mouse)
            if hover is not None:
                preview = TASK_COLOURS.get(self.area_draw_task, COLOUR_TASK_PREVIEW)
                hx, hy = hover
                self._draw_height_quad(hx, hy, preview, 70)
                self._draw_field_plot_outline(
                    hx,
                    hy,
                    hx,
                    hy,
                    colour=preview,
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
        from wildlife_species import (
            animal_icon_for,
            bird_icon_for,
            body_colour_for,
            member_icon_for,
            nest_icon_for,
        )
        from icons import blit_icon

        size = self.camera.view_cell_px()
        # Draw cull only — wildlife.tick still moves every animal.
        x0, y0, x1, y1 = self.camera.visible_range(self.world.cols, self.world.rows)
        pad = 1
        vx0, vy0, vx1, vy1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
        for animal in self.wildlife.animals:
            if animal.kind not in (AnimalKind.DEER, AnimalKind.BOAR):
                continue
            if not (vx0 <= animal.x <= vx1 and vy0 <= animal.y <= vy1):
                continue
            ax, ay = entity_draw_xy(animal)
            cx, cy = self._cell_center(ax, ay)
            cy += max(1, size // 20)
            female = animal.sex == AnimalSex.FEMALE
            name = animal_icon_for(animal.kind.name, female=female)
            colour = body_colour_for(animal.kind.name, female=female)
            if colour is not None:
                blit_icon(
                    self.screen, name, cx, cy, size, recolour={"body": colour}
                )
            else:
                blit_icon(self.screen, name, cx, cy, size)

        # Colony nests + members — use SVG colours (no body wash).
        member_size = max(8, size * 2 // 3)
        cpad = 3
        cx0, cy0, cx1, cy1 = x0 - cpad, y0 - cpad, x1 + cpad, y1 + cpad
        for colony in self.wildlife.colonies:
            if not (cx0 <= colony.x <= cx1 and cy0 <= colony.y <= cy1):
                continue
            nest_name = nest_icon_for(colony.kind.name)
            member_name = member_icon_for(colony.kind.name)
            if not nest_name or not member_name:
                continue
            if vx0 <= colony.x <= vx1 and vy0 <= colony.y <= vy1:
                nx, ny = entity_draw_xy(colony)
                cx, cy = self._cell_center(nx, ny)
                blit_icon(self.screen, nest_name, cx, cy, size)
            for member in colony.members:
                if not (vx0 <= member.x <= vx1 and vy0 <= member.y <= vy1):
                    continue
                mx, my = entity_draw_xy(member)
                cx, cy = self._cell_center(mx, my)
                cy += max(1, size // 20)
                blit_icon(self.screen, member_name, cx, cy, member_size)

        # Fox / wolf packs — native SVG colours, same cull pattern as deer.
        for pack in self.wildlife.wolf_packs:
            pack_key = pack.kind.name
            for member in pack.members:
                if not (vx0 <= member.x <= vx1 and vy0 <= member.y <= vy1):
                    continue
                mx, my = entity_draw_xy(member)
                cx, cy = self._cell_center(mx, my)
                cy += max(1, size // 20)
                name = animal_icon_for(
                    pack_key, female=member.sex == AnimalSex.FEMALE
                )
                blit_icon(self.screen, name, cx, cy, size)

        # Hawks / owls — directional icons.
        for animal in self.wildlife.animals:
            if animal.kind not in (AnimalKind.OWL, AnimalKind.HAWK):
                continue
            if not (vx0 <= animal.x <= vx1 and vy0 <= animal.y <= vy1):
                continue
            ax, ay = entity_draw_xy(animal)
            cx, cy = self._cell_center(ax, ay)
            cy += max(1, size // 20)
            name = bird_icon_for(
                animal.kind.name, facing_right=animal.facing_right
            )
            blit_icon(self.screen, name, cx, cy, size)

    def _draw_fish(self) -> None:
        from icons import blit_icon
        from wildlife import fish_icon_for

        size = self.camera.view_cell_px()
        # Draw cull only — FishManager.tick still moves every fish.
        # Species SVGs keep native colours (no body recolour).
        x0, y0, x1, y1 = self.camera.visible_range(self.world.cols, self.world.rows)
        for item in self.fish.fish:
            if not (x0 <= item.x <= x1 and y0 <= item.y <= y1):
                continue
            fx, fy = entity_draw_xy(item)
            cx, cy = self._cell_center(fx, fy)
            blit_icon(self.screen, fish_icon_for(item.kind), cx, cy, size)

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

        vx, vy = entity_draw_xy(self.player)
        cx, cy = self._cell_center(vx, vy)
        blit_icon(
            self.screen,
            ICON_PLAYER,
            cx,
            cy,
            self.camera.view_cell_px(),
            recolour={"body": COLOUR_PLAYER},
        )

    def _draw_player_status_hud(self) -> None:
        """Compact vitals + status effects overlay in the top-left of the map view."""
        from icons import blit_icon
        from inventory_ui import GRID_CELL, draw_hover_tooltip
        from resources import resource_icon, resource_label
        from status_effects_ui import (
            HIGHLIGHT_BORDER,
            MOD_CELL,
            MOD_GAP,
            active_temp_event,
            cause_is_highlighted,
            collect_status_mods,
            draw_effect_total_columns,
            draw_mod_row,
            effect_totals,
            resolve_hover_state,
        )
        from villager_roster import SORT_LABELS, RosterSort, draw_status_bar

        p = self.player
        mouse = pygame.mouse.get_pos()
        pad = 8
        x0 = pad
        y0 = MAP_OFFSET_Y + pad
        content_x = x0 + 46
        skill_row_h = 14 + 14 + 4
        panel_w = max(260, content_x + MOD_CELL * 2 + MOD_GAP + pad)

        all_mods = collect_status_mods(
            last_meal=list(p.last_meal),
            inventory=p.inventory,
            calendar_day=self.calendar_day,
        )
        buffs = [m for m in all_mods if m.is_buff]
        debuffs = [m for m in all_mods if m.is_debuff]
        temp_ev = active_temp_event(p.inventory, self.calendar_day)

        panel_h = (
            18
            + 3 * 14
            + skill_row_h
            + MOD_CELL
            + 4
            + MOD_CELL
            + 4
            + MOD_CELL
            + 4
            + MOD_CELL
            + 4
            + GRID_CELL
            + 6
            + 14
        )

        panel = pygame.Rect(x0, y0, panel_w, panel_h)
        bg = pygame.Surface((panel.w, panel.h), pygame.SRCALPHA)
        bg.fill((24, 26, 32, 200))
        self.screen.blit(bg, panel.topleft)
        pygame.draw.rect(self.screen, COLOUR_TOOLBAR_BORDER, panel, 1, border_radius=4)

        font = pygame.font.SysFont("menlo", 12, bold=True)
        font_s = pygame.font.SysFont("menlo", 11)
        font_t = pygame.font.SysFont("menlo", 10)
        self.screen.blit(font.render("Player", True, COLOUR_TEXT), (x0 + 6, y0 + 4))
        hint = font_t.render("F eat · Q tool", True, COLOUR_TEXT_DIM)
        self.screen.blit(hint, (x0 + panel_w - hint.get_width() - 6, y0 + 5))

        y = y0 + 20
        bar_w = 52
        bar_h = 8
        row_h = 14
        for sort_key, kind, value in (
            (RosterSort.ENERGY, "energy", p.energy),
            (RosterSort.SATIATION, "sat", p.satiation),
            (RosterSort.HAPPINESS, "happy", p.happiness),
        ):
            label = SORT_LABELS[sort_key]
            self.screen.blit(font_t.render(label, True, COLOUR_TEXT_DIM), (x0 + 6, y))
            draw_status_bar(
                self.screen, x0 + 30, y + 2, bar_w, bar_h, value, kind=kind
            )
            y += row_h

        walk_t, work_t, hunger_t = effect_totals(
            food_walk=p.food_walk_mult,
            food_work=p.food_work_mult,
            food_hunger=p.food_hunger_mult,
            inventory=p.inventory,
            calendar_day=self.calendar_day,
        )
        _, total_tips = draw_effect_total_columns(
            self.screen,
            x0 + 6,
            y,
            walk=walk_t,
            work=work_t,
            hunger=hunger_t,
            font=font_t,
        )
        y += skill_row_h

        meal_y = y
        buff_y = meal_y + MOD_CELL + 4
        debuff_y = buff_y + MOD_CELL + 4
        events_y = debuff_y + MOD_CELL + 4
        hover = resolve_hover_state(
            mouse,
            meal_keys=list(p.last_meal[:3]),
            meal_x=content_x,
            meal_y=meal_y,
            buffs=buffs,
            debuffs=debuffs,
            buff_x=content_x,
            buff_y=buff_y,
            debuff_x=content_x,
            debuff_y=debuff_y,
            temp_event=temp_ev,
            event_x=content_x,
            event_y=events_y,
            cell_size=MOD_CELL,
            gap=MOD_GAP,
        )

        tip_hits: list[tuple[pygame.Rect, str]] = list(total_tips)

        # Meal
        self.screen.blit(
            font_t.render("Meal", True, COLOUR_TEXT_DIM),
            (x0 + 6, meal_y + MOD_CELL // 2 - 6),
        )
        mx = content_x
        if p.last_meal:
            for key in p.last_meal[:3]:
                cell = pygame.Rect(mx, meal_y, MOD_CELL, MOD_CELL)
                hi = cause_is_highlighted("meal", key, hover)
                pygame.draw.rect(self.screen, (36, 38, 44), cell, border_radius=3)
                border = HIGHLIGHT_BORDER if hi else COLOUR_TOOLBAR_BORDER
                pygame.draw.rect(
                    self.screen, border, cell, 2 if hi else 1, border_radius=3
                )
                blit_icon(
                    self.screen,
                    resource_icon(key),
                    cell.centerx,
                    cell.centery,
                    MOD_CELL - 14,
                )
                tip_hits.append((cell, resource_label(key)))
                mx += MOD_CELL + MOD_GAP
        else:
            self.screen.blit(
                font_t.render("—", True, COLOUR_TEXT_DIM),
                (content_x, meal_y + MOD_CELL // 2 - 6),
            )

        # Buffs
        self.screen.blit(
            font_t.render("Buffs", True, COLOUR_TEXT_DIM),
            (x0 + 6, buff_y + MOD_CELL // 2 - 6),
        )
        if buffs:
            _, hits, _ = draw_mod_row(
                self.screen,
                content_x,
                buff_y,
                buffs,
                mouse_pos=mouse,
                hover=hover,
                icon_size=MOD_CELL,
                gap=MOD_GAP,
            )
            tip_hits.extend((rect, mod.tip) for rect, mod in hits)
        else:
            self.screen.blit(
                font_t.render("—", True, COLOUR_TEXT_DIM),
                (content_x, buff_y + MOD_CELL // 2 - 6),
            )

        # Debuffs
        self.screen.blit(
            font_t.render("Debuffs", True, COLOUR_TEXT_DIM),
            (x0 + 6, debuff_y + MOD_CELL // 2 - 6),
        )
        if debuffs:
            _, hits, _ = draw_mod_row(
                self.screen,
                content_x,
                debuff_y,
                debuffs,
                mouse_pos=mouse,
                hover=hover,
                icon_size=MOD_CELL,
                gap=MOD_GAP,
            )
            tip_hits.extend((rect, mod.tip) for rect, mod in hits)
        else:
            self.screen.blit(
                font_t.render("—", True, COLOUR_TEXT_DIM),
                (content_x, debuff_y + MOD_CELL // 2 - 6),
            )

        # Events (temperature)
        self.screen.blit(
            font_t.render("Events", True, COLOUR_TEXT_DIM),
            (x0 + 6, events_y + MOD_CELL // 2 - 6),
        )
        if temp_ev is not None:
            cell = pygame.Rect(content_x, events_y, MOD_CELL, MOD_CELL)
            key = str(temp_ev["key"])
            hi = cause_is_highlighted("events", key, hover)
            pygame.draw.rect(self.screen, (36, 38, 44), cell, border_radius=3)
            border = HIGHLIGHT_BORDER if hi else COLOUR_TOOLBAR_BORDER
            pygame.draw.rect(
                self.screen, border, cell, 2 if hi else 1, border_radius=3
            )
            blit_icon(
                self.screen,
                str(temp_ev["icon"]),
                cell.centerx,
                cell.centery,
                MOD_CELL - 14,
            )
            tip_hits.append((cell, str(temp_ev["tip"])))
        else:
            self.screen.blit(
                font_t.render("—", True, COLOUR_TEXT_DIM),
                (content_x, events_y + MOD_CELL // 2 - 6),
            )

        # Tools
        tools_y = events_y + MOD_CELL + 4
        self.screen.blit(
            font_t.render("Tools", True, COLOUR_TEXT_DIM),
            (x0 + 6, tools_y + GRID_CELL // 2 - 6),
        )
        self._player_hud_tool_hits = []
        tools = list(p.inventory.equipped_tools)
        tx = content_x
        for i in range(3):
            cell = pygame.Rect(tx + i * (GRID_CELL + MOD_GAP), tools_y, GRID_CELL, GRID_CELL)
            key = tools[i] if i < len(tools) else None
            pygame.draw.rect(self.screen, (36, 38, 44), cell, border_radius=3)
            pygame.draw.rect(self.screen, COLOUR_TOOLBAR_BORDER, cell, 1, border_radius=3)
            if key:
                blit_icon(
                    self.screen,
                    resource_icon(key),
                    cell.centerx,
                    cell.centery,
                    GRID_CELL - 14,
                )
                self._player_hud_tool_hits.append((cell, f"tool_unequip:{key}"))
            elif i == len(tools):
                self._player_hud_tool_hits.append((cell, "tool_equip"))

        for rect, text in tip_hits:
            if rect.collidepoint(mouse):
                draw_hover_tooltip(
                    self.screen, mouse_pos=mouse, text=text, font=font_s
                )
                break

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
        if self.habitat_view_mode:
            from wildlife import OpenHabitat

            for kind in (
                AnimalKind.DEER,
                AnimalKind.BOAR,
                AnimalKind.BEE,
                AnimalKind.RABBIT,
                AnimalKind.FROG,
                AnimalKind.VOLE,
            ):
                if kind in (AnimalKind.DEER, AnimalKind.BOAR):
                    base_colour = (92, 122, 86) if kind == AnimalKind.DEER else (128, 106, 78)
                else:
                    base_colour = (108, 128, 78)
                for hab in self.wildlife.breeding_grounds(kind):
                    breed = set(self.wildlife._breeding_for(kind, hab))
                    if not breed:
                        continue
                    if isinstance(hab, OpenHabitat):
                        roam = set(hab.forage_tiles) - breed
                    else:
                        roam = self.wildlife._cold_roaming_for(kind, hab) - breed
                    if roam:
                        self._draw_cell_set_outline(roam, colour=base_colour, width=1)
                    self._draw_cell_set_outline(breed, colour=base_colour, width=2)
        if self.habitat_view_mode and self._habitat_hover is not None:
            kind, hid = self._habitat_hover
            if kind in (AnimalKind.WOLF, AnimalKind.FOX):
                pack = self._wolf_pack_by_id(hid)
                if pack is not None and pack.kind == kind:
                    tiles = {(m.x, m.y) for m in pack.members} | {(pack.x, pack.y)}
                    if tiles:
                        self._draw_cell_set_outline(
                            tiles,
                            colour=COLOUR_SELECTED_ENTITY,
                            width=3,
                        )
            elif kind in (AnimalKind.OWL, AnimalKind.HAWK):
                bird = next(
                    (
                        a
                        for a in self.wildlife.animals
                        if a.id == hid and a.kind == kind
                    ),
                    None,
                )
                if bird is not None:
                    self._draw_cell_set_outline(
                        {(bird.x, bird.y)},
                        colour=COLOUR_SELECTED_ENTITY,
                        width=3,
                    )
            else:
                hab = self.wildlife.habitat(hid, kind)
                if hab is not None:
                    tiles = set(self.wildlife._breeding_for(kind, hab))
                    roam = self.wildlife._cold_roaming_for(kind, hab)
                    roam_only = roam - tiles
                    if roam_only:
                        self._draw_cell_set_outline(
                            roam_only,
                            colour=COLOUR_SELECTED_ENTITY,
                            width=2,
                        )
                    if tiles:
                        self._draw_cell_set_outline(
                            tiles,
                            colour=COLOUR_SELECTED_ENTITY,
                            width=3,
                        )
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
            if kind in (AnimalKind.WOLF, AnimalKind.FOX):
                pack = self._wolf_pack_by_id(self.selected_habitat_id)
                if pack is not None and pack.kind == kind:
                    tiles = {(m.x, m.y) for m in pack.members} | {(pack.x, pack.y)}
                    if tiles:
                        self._draw_cell_set_outline(
                            tiles,
                            colour=COLOUR_SELECTED_ENTITY,
                            width=2,
                        )
            elif kind in (AnimalKind.OWL, AnimalKind.HAWK):
                bird = next(
                    (
                        a
                        for a in self.wildlife.animals
                        if a.id == self.selected_habitat_id and a.kind == kind
                    ),
                    None,
                )
                if bird is not None:
                    self._draw_cell_set_outline(
                        {(bird.x, bird.y)},
                        colour=COLOUR_SELECTED_ENTITY,
                        width=2,
                    )
            else:
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
            COLOUR_TAILOR,
            COLOUR_COBBLER,
            COLOUR_MARKET,
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
            BuildingKind.TAILOR: COLOUR_TAILOR,
            BuildingKind.COBBLER: COLOUR_COBBLER,
            BuildingKind.MARKET: COLOUR_MARKET,
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
