"""Game configuration: dimensions, colours, capacities, and seed.

Window / cell size is finalised at runtime via configure_for_display().
The world grid (WORLD_COLS × WORLD_ROWS) is much larger than the viewport;
the camera pans/zooms over it.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# World grid (logical map — larger than the on-screen viewport)
# ---------------------------------------------------------------------------
WORLD_COLS: int = 96
WORLD_ROWS: int = 72

# ---------------------------------------------------------------------------
# Viewport & window (defaults; overwritten by configure_for_display)
# GRID_COLS/ROWS ≈ visible cells at zoom 1 (layout / legacy references).
# ---------------------------------------------------------------------------
GRID_COLS: int = 24
GRID_ROWS: int = 18
CELL_SIZE: int = 40
PANEL_WIDTH: int = 300
PANEL_COLLAPSED: bool = False
TOOLBAR_HEIGHT: int = 64
RESOURCE_BAR_HEIGHT: int = 36
MAP_OFFSET_Y: int = TOOLBAR_HEIGHT + RESOURCE_BAR_HEIGHT
WINDOW_WIDTH: int = GRID_COLS * CELL_SIZE + PANEL_WIDTH
WINDOW_HEIGHT: int = MAP_OFFSET_Y + GRID_ROWS * CELL_SIZE
FPS: int = 60
SIM_SPEEDS: tuple[int, ...] = (0, 1, 2, 4, 8, 16, 32, 64, 128)
# In-game ticks per day (at 60 FPS: 480 ≈ 8 s/day at sim ×1). Cycled with [ ] in play.
# Lower = faster calendar (better for path-traffic testing); villager pacing scales to match.
TICKS_PER_DAY_OPTIONS: tuple[int, ...] = (30, 60, 120, 240, 480, 960, 1920)
REFERENCE_TICKS_PER_DAY: int = FPS * 8
# Native terrain tile size (pre-rendered, then scaled to CELL_SIZE and stitched).
TERRAIN_SUBDIV: int = 25
# Terrain edge backend: "procedural" (MS opaque joins + mottling) or "png"
# (legacy soft joins). Preview mottling: python preview_terrain_fills.py
TERRAIN_FILL_MODE: str = "procedural"
# Map / UI icons: when True, prefer baked ``assets/icons/*.png`` whenever
# present (recolour / class_scales / omit are ignored for that blit). When
# False (default), runtime uses SVG so class recolour / omit / scale work;
# PNG export + shade pipeline stays available via export_icons_png.py.
ICON_USE_PNG: bool = False
# After rasterising building SVGs, bake stipple once at full-zoom size
# (CELL_SIZE * ZOOM_MAX * BUILDING_FOOTPRINT) into _stipple_tmp/; lower zooms
# nearest-neighbour scale that bake so max zoom stays 1:1 sharp.
ICON_BUILDING_STIPPLE: bool = True

# Camera
ZOOM_MIN: float = 0.35
ZOOM_MAX: float = 2.5
ZOOM_STEP: float = 0.12
# Legacy discrete pan step (kept for compatibility); continuous WASD uses speed.
CAMERA_PAN_CELLS: float = 0.55
CAMERA_PAN_SPEED: float = 14.0  # world cells / second at zoom 1
ZOOM_SMOOTH_RATE: float = 14.0  # higher = snappier zoom lerp
PLAYER_VIS_SPEED: float = 10.0  # cells / second toward logical cell
MINIMAP_WIDTH: int = 168
MINIMAP_HEIGHT: int = 126


def map_view_width() -> int:
    return max(1, WINDOW_WIDTH - effective_panel_width())


def map_view_height() -> int:
    return max(1, WINDOW_HEIGHT - MAP_OFFSET_Y)


def effective_panel_width() -> int:
    """Sidebar width (0 when collapsed)."""
    return 0 if PANEL_COLLAPSED else PANEL_WIDTH


def set_panel_collapsed(collapsed: bool) -> None:
    global PANEL_COLLAPSED
    PANEL_COLLAPSED = bool(collapsed)


def toggle_panel_collapsed() -> bool:
    """Toggle the right sidebar. Returns the new collapsed state."""
    set_panel_collapsed(not PANEL_COLLAPSED)
    return PANEL_COLLAPSED


def configure_for_display(screen_w: int, screen_h: int) -> None:
    """Pick cell size and window so the map viewport + sidebar fill the display.

    World size stays at WORLD_COLS × WORLD_ROWS; only the viewport scales.
    """
    global GRID_COLS, GRID_ROWS, CELL_SIZE, WINDOW_WIDTH, WINDOW_HEIGHT
    global PANEL_WIDTH, TOOLBAR_HEIGHT, RESOURCE_BAR_HEIGHT, MAP_OFFSET_Y
    global PANEL_COLLAPSED

    PANEL_COLLAPSED = False
    PANEL_WIDTH = 300
    TOOLBAR_HEIGHT = 64
    RESOURCE_BAR_HEIGHT = 36
    MAP_OFFSET_Y = TOOLBAR_HEIGHT + RESOURCE_BAR_HEIGHT
    # Tight margins: leave room for OS menu / title / dock without huge empty borders.
    usable_w = max(800, int(screen_w) - 12)
    usable_h = max(560, int(screen_h) - 72)

    map_w = max(400, usable_w - PANEL_WIDTH)
    map_h = max(320, usable_h - MAP_OFFSET_Y)

    # Prefer a large cell that still shows a useful viewport (≥18×14 cells).
    cell = 12
    cols = 18
    rows = 14
    for candidate in range(48, 11, -1):
        c = map_w // candidate
        r = map_h // candidate
        if c >= 18 and r >= 14:
            cell = candidate
            cols = c
            rows = r
            break
    else:
        cell = max(12, min(map_w // 18, map_h // 14))
        cols = max(16, map_w // cell)
        rows = max(12, map_h // cell)

    GRID_COLS = cols
    GRID_ROWS = rows
    CELL_SIZE = cell
    # Fill the usable display; leftover pixels become a thin border inside the window.
    WINDOW_WIDTH = min(usable_w, cols * cell + PANEL_WIDTH)
    WINDOW_HEIGHT = min(usable_h, MAP_OFFSET_Y + rows * cell)
    # If we still have spare room, grow the window to match the display usable area.
    WINDOW_WIDTH = usable_w
    WINDOW_HEIGHT = usable_h
    # Recompute cell so the map tiles the available map area tightly.
    map_w = WINDOW_WIDTH - PANEL_WIDTH
    map_h = WINDOW_HEIGHT - MAP_OFFSET_Y
    CELL_SIZE = max(12, min(48, min(map_w // max(16, cols), map_h // max(12, rows))))
    GRID_COLS = max(16, map_w // CELL_SIZE)
    GRID_ROWS = max(12, map_h // CELL_SIZE)


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------
RANDOM_SEED: int = 77
INVENTORY_CAPACITY: int = 20
SEED_CARRY_CAPACITY: int = 20  # villager/player berry + crop seeds (carry pool)
MAX_VILLAGERS: int = 20

# ---------------------------------------------------------------------------
# Building storage (single source of truth)
# Edit BUILDING_STORAGE below — construction + save load both apply these.
# Optional pools: input/output (processors), fuel (kitchen), seeds (farm).
# Zero = that pool is unused (items share ``capacity`` instead).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BuildingStorageSpec:
    """Storage pools for one building kind."""

    capacity: int = 40  # general cargo (or display total when split)
    input_capacity: int = 0
    output_capacity: int = 0
    fuel_capacity: int = 0
    seed_capacity: int = 0  # crop seeds; separate from produce cargo


_CARGO: int = 40
_PROC_IN: int = 40
_PROC_OUT: int = 10
_FUEL: int = 10
_SEEDS: int = 40

BUILDING_STORAGE: dict[str, BuildingStorageSpec] = {
    "home": BuildingStorageSpec(capacity=_CARGO * 50),
    "workstation": BuildingStorageSpec(capacity=0),
    "forester": BuildingStorageSpec(capacity=_CARGO),
    "mason": BuildingStorageSpec(capacity=_CARGO),
    "hunter": BuildingStorageSpec(capacity=_CARGO),
    "forager": BuildingStorageSpec(capacity=_CARGO, seed_capacity=_SEEDS),
    "fisher": BuildingStorageSpec(capacity=_CARGO),
    "farm": BuildingStorageSpec(capacity=100, seed_capacity=_SEEDS),
    "field": BuildingStorageSpec(capacity=0),
    "mill": BuildingStorageSpec(
        capacity=_PROC_IN + _PROC_OUT,
        input_capacity=_PROC_IN,
        output_capacity=_PROC_OUT,
    ),
    "kitchen": BuildingStorageSpec(
        capacity=_PROC_IN + _PROC_OUT,
        input_capacity=_PROC_IN,
        output_capacity=_PROC_OUT,
        fuel_capacity=_FUEL,
    ),
    "craft_bench": BuildingStorageSpec(
        capacity=_PROC_IN + _PROC_OUT,
        input_capacity=_PROC_IN,
        output_capacity=_PROC_OUT,
    ),
    "alchemist": BuildingStorageSpec(
        capacity=_PROC_IN + _PROC_OUT,
        input_capacity=_PROC_IN,
        output_capacity=_PROC_OUT,
    ),
    "tailor": BuildingStorageSpec(
        capacity=_PROC_IN + _PROC_OUT,
        input_capacity=_PROC_IN,
        output_capacity=_PROC_OUT,
    ),
    "market": BuildingStorageSpec(
        capacity=_PROC_IN + _PROC_OUT,
        input_capacity=_PROC_IN,
        output_capacity=_PROC_OUT,
    ),
    "tent": BuildingStorageSpec(capacity=0),
    "house_small": BuildingStorageSpec(capacity=0),
    "house": BuildingStorageSpec(capacity=0),
}


def building_storage_spec(kind_name: str) -> BuildingStorageSpec:
    """Lookup by BuildingKind.name (case-insensitive). Unknown → default cargo."""
    key = kind_name.strip().lower()
    if key in BUILDING_STORAGE:
        return BUILDING_STORAGE[key]
    return BuildingStorageSpec(capacity=_CARGO)


# Back-compat aliases (prefer BUILDING_STORAGE / building_storage_spec).
BUILDING_STORAGE_CAPACITY: int = _CARGO
MILL_INPUT_CAPACITY: int = BUILDING_STORAGE["mill"].input_capacity
MILL_OUTPUT_CAPACITY: int = BUILDING_STORAGE["mill"].output_capacity
KITCHEN_INPUT_CAPACITY: int = BUILDING_STORAGE["kitchen"].input_capacity
KITCHEN_OUTPUT_CAPACITY: int = BUILDING_STORAGE["kitchen"].output_capacity
KITCHEN_FUEL_CAPACITY: int = BUILDING_STORAGE["kitchen"].fuel_capacity
CRAFT_BENCH_INPUT_CAPACITY: int = BUILDING_STORAGE["craft_bench"].input_capacity
CRAFT_BENCH_OUTPUT_CAPACITY: int = BUILDING_STORAGE["craft_bench"].output_capacity
ALCHEMIST_INPUT_CAPACITY: int = BUILDING_STORAGE["alchemist"].input_capacity
ALCHEMIST_OUTPUT_CAPACITY: int = BUILDING_STORAGE["alchemist"].output_capacity
TAILOR_INPUT_CAPACITY: int = BUILDING_STORAGE["tailor"].input_capacity
TAILOR_OUTPUT_CAPACITY: int = BUILDING_STORAGE["tailor"].output_capacity
FARM_SEED_CAPACITY: int = BUILDING_STORAGE["farm"].seed_capacity

FORESTER_COST_WOOD: int = 2
FORESTER_COST_ROCK: int = 2
FORESTER_DEFAULT_LOGS_MIN: int = 5
FORESTER_DEFAULT_HARDWOOD_LOGS_MIN: int = 2
MASON_COST_WOOD: int = 2
MASON_COST_ROCK: int = 2
HUNTER_COST_WOOD: int = 2
HUNTER_COST_ROCK: int = 2
FORAGER_COST_WOOD: int = 2
FORAGER_COST_ROCK: int = 2
FISHER_COST_WOOD: int = 2
FISHER_COST_ROCK: int = 4
FARM_COST_WOOD: int = 2
FARM_COST_ROCK: int = 4
FIELD_COST_WOOD: int = 1
FIELD_COST_ROCK: int = 0
MILL_COST_WOOD: int = 2
MILL_COST_ROCK: int = 4
KITCHEN_COST_WOOD: int = 2
KITCHEN_COST_ROCK: int = 4
CRAFT_BENCH_COST_WOOD: int = 2
CRAFT_BENCH_COST_ROCK: int = 2
ALCHEMIST_COST_WOOD: int = 0
ALCHEMIST_COST_ROCK: int = 4
ALCHEMIST_COST_HARDWOOD: int = 4
TAILOR_COST_WOOD: int = 0
TAILOR_COST_ROCK: int = 4
TAILOR_COST_HARDWOOD: int = 4
WORKSTATION_COST_WOOD: int = 2
WORKSTATION_COST_ROCK: int = 4
# Chebyshev distance from Farm to a Field plot for workers to manage it.
FARM_FIELD_RADIUS: int = 20

STARTING_WOOD: int = 2  # processed wood (not logs)
STARTING_ROCK: int = 2
STARTING_TWINE: int = 5
STARTING_VILLAGERS: int = 3
# Fresh game boots from this save (terrain / height / wildlife), then strips
# to storehouse-only + starting villagers.
AUTOLOAD_SAVE: str = "valley_trial.json"
BUILD_SECONDS_PER_ITEM: float = 2.0
# Ticks of construction work required per wood/rock unit (at simulation ×1).
BUILD_TICKS_PER_ITEM: int = int(FPS * BUILD_SECONDS_PER_ITEM)
# Square footprint (cells) for storehouse, hiring hall, and production buildings.
BUILDING_FOOTPRINT: int = 3

INDICATOR_RADIUS: int = 2

# Resource yields, food effects, forage spawn rates: edit resource_balance.py

VILLAGER_MOVE_INTERVAL: int = 48
VILLAGER_WORK_INTERVAL: int = 144
# Work actions (each spaced by villager work interval) to finish one mill/kitchen craft.
PROCESSOR_RECIPE_STEPS: int = 3

# Wildlife tick cadence (ecology amounts live in resource_balance.py).
ANIMAL_MOVE_INTERVAL: int = 80
ANIMAL_GROWTH_INTERVAL: int = 480

FISH_MOVE_INTERVAL: int = 80
FISH_GROWTH_INTERVAL: int = 480

DISTURBANCE_DECAY_PER_TICK: float = 0.002
DISTURBANCE_INTERACTION_BOOST: float = 0.25
DISTURBANCE_NEIGHBOUR_SPREAD: float = 0.08
DISTURBANCE_EXTRACTION_BOOST: float = 0.55
DISTURBANCE_EXTRACTION_SPREAD: float = 0.14
DISTURBANCE_MAX: float = 1.0
# Permanent floors while terrain type is present (no decay on these tiles).
DISTURBANCE_URBAN_LEVEL: float = 0.85
DISTURBANCE_PATH_LEVEL: float = 0.45
# Ecology/farming multiplier at full disturbance (0.25 → 25% effectiveness).
DISTURBANCE_ACTIVITY_FLOOR: float = 0.25
# Chebyshev radius for neighbourhood-averaged disturbance (read + spread falloff).
DISTURBANCE_RADIUS: int = 2

STATUS_MESSAGE_FRAMES: int = 150

# Visual-only height warp (toggle with H). Logic grid stays flat.
HEIGHT_SAMPLE_ENABLED_DEFAULT: bool = True
# Absolute height units matching valley hydrology.
HEIGHT_LAKE: float = 0.0
HEIGHT_RIVER_HEAD: float = 40.0  # upstream river end; falls to HEIGHT_LAKE at the lake
# Valley walls: rise with distance from the river/lake channel.
HEIGHT_VALLEY_RISE_PER_CELL: float = 2.8
HEIGHT_VALLEY_RISE_MAX: float = 36.0
# Screen lift in pixels per height unit at zoom 1 (scales with view_cell / CELL_SIZE).
HEIGHT_LIFT_PX: float = 1.0
# Legacy alias used by older call sites.
HEIGHT_SAMPLE_PX: float = HEIGHT_LIFT_PX
HEIGHT_SAMPLE_LIGHT_NW: float = 0.28  # slope response; highlights kept gentle
# Per-pixel shade tint: highlights → light yellow, shadows → dark brown.
HEIGHT_SAMPLE_SHADE_LIT: tuple[int, int, int] = (248, 228, 175)
HEIGHT_SAMPLE_SHADE_SHADOW: tuple[int, int, int] = (72, 46, 28)
# How strongly extreme slopes lean into the tint colours (0..1).
HEIGHT_SAMPLE_SHADE_MIX: float = 0.48
# Highlight mix is separate — light was too strong at full SHADE_MIX.
HEIGHT_SAMPLE_SHADE_LIT_MIX: float = 0.16
# Map edit tools (Y). Flat map; warp stays off while editing.
HEIGHT_EDIT_BRUSH_MIN: int = 0
HEIGHT_EDIT_BRUSH_MAX: int = 10
HEIGHT_EDIT_VALUE_MAX: float = 80.0
HEIGHT_EDIT_VALUE_STEP: float = 1.0
HEIGHT_EDIT_DELTA_DEFAULT: float = 2.0
# Viewport bake margin (cells). Unused — height warp bakes the full map once.
HEIGHT_VIEW_MARGIN: int = 14

# ---------------------------------------------------------------------------
# Colours (RGB)
# ---------------------------------------------------------------------------
Colour = tuple[int, int, int]

COLOUR_BG: Colour = (30, 30, 34)
COLOUR_PANEL_BG: Colour = (40, 42, 48)
COLOUR_PANEL_BORDER: Colour = (70, 74, 84)
COLOUR_TEXT: Colour = (230, 230, 235)
COLOUR_TEXT_DIM: Colour = (160, 164, 176)
COLOUR_STATUS: Colour = (255, 220, 120)
COLOUR_PLAYER: Colour = (50, 120, 255)
COLOUR_VILLAGER: Colour = (220, 140, 50)
COLOUR_ANIMAL: Colour = (160, 100, 60)  # deer (legacy)
COLOUR_DEER: Colour = (160, 100, 60)
COLOUR_BOAR: Colour = (90, 70, 55)
COLOUR_BEE: Colour = (110, 89, 56)  # match bee / hive SVG browns
COLOUR_RABBIT: Colour = (110, 89, 56)  # match rabbit / burrow SVG browns
COLOUR_REED: Colour = (70, 120, 80)
COLOUR_WORKSTATION: Colour = (106, 100, 128)  # match workstation.svg walls
COLOUR_FORESTER: Colour = (106, 122, 90)
COLOUR_MASON: Colour = (136, 136, 128)
COLOUR_HUNTER: Colour = (154, 128, 112)
COLOUR_FORAGER: Colour = (106, 120, 96)
COLOUR_FISHER: Colour = (88, 112, 136)
COLOUR_MEAT: Colour = (180, 60, 70)
COLOUR_FISH: Colour = (80, 160, 200)
COLOUR_MUSHROOM: Colour = (200, 170, 140)
COLOUR_BERRY: Colour = (160, 40, 90)
COLOUR_HERB: Colour = (90, 170, 70)
COLOUR_SELECTED_ENTITY: Colour = (255, 240, 80)
COLOUR_TASK_AREA: Colour = (255, 220, 40)
COLOUR_TASK_PREVIEW: Colour = (255, 255, 120)
COLOUR_TASK_CHOP: Colour = (180, 90, 40)
COLOUR_TASK_ROCK: Colour = (140, 140, 160)
COLOUR_TASK_PLANT: Colour = (80, 180, 100)
COLOUR_TASK_MANAGE: Colour = (120, 200, 160)
COLOUR_TASK_HUNT: Colour = (200, 90, 70)
COLOUR_TASK_FORAGE: Colour = (100, 160, 120)
COLOUR_TASK_FISH: Colour = (60, 140, 190)
COLOUR_TASK_FARM: Colour = (150, 130, 60)
COLOUR_FARM: Colour = (177, 147, 105)  # match farm.svg
COLOUR_FIELD: Colour = (176, 160, 96)
COLOUR_MILL: Colour = (176, 160, 112)
COLOUR_KITCHEN: Colour = (160, 112, 88)
COLOUR_CRAFT_BENCH: Colour = (160, 144, 112)
COLOUR_ALCHEMIST: Colour = (154, 120, 184)
COLOUR_TAILOR: Colour = (122, 152, 176)
COLOUR_MARKET: Colour = (176, 120, 72)
COLOUR_CROP: Colour = (110, 190, 80)

COLOUR_TOOLBAR_BG: Colour = (36, 38, 44)
COLOUR_TOOLBAR_BTN: Colour = (55, 58, 68)
COLOUR_TOOLBAR_BTN_HOVER: Colour = (70, 74, 88)
COLOUR_TOOLBAR_BTN_ACTIVE: Colour = (70, 110, 160)
COLOUR_TOOLBAR_BORDER: Colour = (80, 84, 96)
COLOUR_MENU_BG: Colour = (48, 50, 58)

COLOUR_SOIL: Colour = (139, 105, 70)
COLOUR_FOREST_FLOOR: Colour = (95, 68, 42)  # darker soil under trees
COLOUR_GRASS: Colour = (90, 150, 70)
COLOUR_MEADOW: Colour = (100, 175, 85)  # slightly greener than grass
COLOUR_RIPARIAN: Colour = (148, 142, 158)  # light grey–purple–green shoreline
COLOUR_WATER: Colour = (60, 120, 190)
COLOUR_RIVER: Colour = (60, 120, 190)  # same look as lake; distinct terrain (no freeze)
COLOUR_ICE: Colour = (170, 205, 230)
COLOUR_ROCK_TERRAIN: Colour = (118, 118, 124)
COLOUR_ROCK_TERRAIN_DARK: Colour = (95, 95, 102)
# Packed earth under large building clusters; worn tracks are sandier PATH.
COLOUR_URBAN: Colour = (145, 128, 108)
COLOUR_PATH: Colour = (196, 178, 128)

# Villager path-wear → PATH terrain (tracked every step; painted daily).
PATH_TRAFFIC_STEP: float = 1.0  # added each villager cell-enter
PATH_TRAFFIC_THRESHOLD: float = 4.0  # wear needed to first paint PATH
PATH_TRAFFIC_DECAY: float = 0.78  # multiply traffic each env sample (8×/year)
PATH_TRAFFIC_KEEP: float = 0.75  # PATH stays until wear falls below this
PATH_TRAFFIC_OVERLAY_MAX: float = 12.0  # wear mapped to 1.0 on traffic overlay
URBAN_MIN_BUILDINGS: int = 3  # fewer → no urban core; only worn PATH under footprints

COLOUR_TREE_CANOPY: Colour = (34, 120, 45)
COLOUR_TREE_TRUNK: Colour = (90, 55, 30)
COLOUR_SAPLING: Colour = (140, 210, 90)
COLOUR_ROCK_FEATURE: Colour = (130, 130, 140)
COLOUR_HOME: Colour = (158, 151, 142)  # match home/storehouse wall
COLOUR_HOME_ROOF: Colour = (240, 161, 60)

OVERLAY_ALPHA: int = 110
COLOUR_DIVERSITY_LOW: Colour = (40, 40, 80)
COLOUR_DIVERSITY_HIGH: Colour = (80, 220, 255)
COLOUR_TREE_DENSITY_LOW: Colour = (20, 40, 20)
COLOUR_TREE_DENSITY_HIGH: Colour = (40, 220, 60)
COLOUR_SPECIES_DIVERSITY_LOW: Colour = (30, 40, 30)
COLOUR_SPECIES_DIVERSITY_HIGH: Colour = (180, 255, 90)
COLOUR_BIODIVERSITY_1: Colour = (220, 40, 40)    # 0 species — red
COLOUR_BIODIVERSITY_5: Colour = (240, 220, 50)   # ~5 species — yellow
COLOUR_BIODIVERSITY_10: Colour = (80, 255, 100)  # ~10+ species — bright green
# Legacy aliases (unused by biodiversity colour ramp).
COLOUR_BIODIVERSITY_LOW: Colour = COLOUR_BIODIVERSITY_1
COLOUR_BIODIVERSITY_HIGH: Colour = COLOUR_BIODIVERSITY_10
COLOUR_DISTURBANCE_LOW: Colour = (40, 20, 20)
COLOUR_DISTURBANCE_HIGH: Colour = (255, 70, 40)
COLOUR_PATH_TRAFFIC_LOW: Colour = (35, 35, 55)
COLOUR_PATH_TRAFFIC_HIGH: Colour = (255, 130, 45)
