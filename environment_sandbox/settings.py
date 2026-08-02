"""Game configuration: dimensions, colours, capacities, and seed.

Window / grid size is finalised at runtime via configure_for_display()
so the map fills the screen beside the sidebar.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Grid & window (defaults; overwritten by configure_for_display)
# ---------------------------------------------------------------------------
GRID_COLS: int = 24
GRID_ROWS: int = 18
CELL_SIZE: int = 40
PANEL_WIDTH: int = 300
TOOLBAR_HEIGHT: int = 64
RESOURCE_BAR_HEIGHT: int = 36
MAP_OFFSET_Y: int = TOOLBAR_HEIGHT + RESOURCE_BAR_HEIGHT
WINDOW_WIDTH: int = GRID_COLS * CELL_SIZE + PANEL_WIDTH
WINDOW_HEIGHT: int = MAP_OFFSET_Y + GRID_ROWS * CELL_SIZE
FPS: int = 60
SIM_SPEEDS: tuple[int, ...] = (0, 1, 2, 4, 8, 16)
# Native terrain tile size (pre-rendered, then scaled to CELL_SIZE and stitched).
TERRAIN_SUBDIV: int = 25


def configure_for_display(screen_w: int, screen_h: int) -> None:
    """Pick grid and cell size so the map + sidebar fit inside the display.

    Leaves room for OS chrome (menu bar, window title, dock/taskbar), the
    top toolbar, and the resource bar. Adds +8 map cells on each axis vs a
    large-cell baseline, then shrinks cells so the window fits.
    """
    global GRID_COLS, GRID_ROWS, CELL_SIZE, WINDOW_WIDTH, WINDOW_HEIGHT
    global PANEL_WIDTH, TOOLBAR_HEIGHT, RESOURCE_BAR_HEIGHT, MAP_OFFSET_Y

    PANEL_WIDTH = 300
    TOOLBAR_HEIGHT = 64
    RESOURCE_BAR_HEIGHT = 36
    MAP_OFFSET_Y = TOOLBAR_HEIGHT + RESOURCE_BAR_HEIGHT
    # Client area from set_mode does not include title bar; dock/menu also
    # steal vertical space — keep a generous height margin on macOS/Windows.
    usable_w = max(800, screen_w - 24)
    usable_h = max(560, screen_h - 110 - MAP_OFFSET_Y)
    map_w = max(400, usable_w - PANEL_WIDTH)

    base_cols = 20
    base_rows = 15
    for cell in range(48, 27, -1):
        cols = map_w // cell
        rows = usable_h // cell
        if cols >= 20 and rows >= 15:
            base_cols = cols
            base_rows = rows
            break

    # +4 twice from the original fill baseline.
    cols = base_cols + 8
    rows = base_rows + 8
    cell = min(map_w // cols, usable_h // rows)
    if cell < 14:
        cols, rows = base_cols + 4, base_rows + 4
        cell = max(12, min(map_w // cols, usable_h // rows))

    # Shrink until the window fits (never force a min cell that overflows).
    while cell > 12 and (
        cols * cell + PANEL_WIDTH > usable_w
        or MAP_OFFSET_Y + rows * cell > usable_h + MAP_OFFSET_Y
    ):
        cell -= 1

    GRID_COLS = cols
    GRID_ROWS = rows
    CELL_SIZE = cell
    WINDOW_WIDTH = cols * cell + PANEL_WIDTH
    WINDOW_HEIGHT = MAP_OFFSET_Y + rows * cell
# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------
RANDOM_SEED: int = 42
INVENTORY_CAPACITY: int = 8
SEED_CARRY_CAPACITY: int = 20  # berry + crop seeds (separate from general cargo)
MAX_VILLAGERS: int = 20
BUILDING_STORAGE_CAPACITY: int = 20
FORESTER_COST_WOOD: int = 2
FORESTER_COST_ROCK: int = 2
MASON_COST_WOOD: int = 2
MASON_COST_ROCK: int = 2
HUNTER_COST_WOOD: int = 2
HUNTER_COST_ROCK: int = 2
FORAGER_COST_WOOD: int = 2
FORAGER_COST_ROCK: int = 2
FISHER_COST_WOOD: int = 2
FISHER_COST_ROCK: int = 2
FARM_COST_WOOD: int = 2
FARM_COST_ROCK: int = 2
FIELD_COST_WOOD: int = 1
FIELD_COST_ROCK: int = 0
# Chebyshev distance from Farm to a Field plot for workers to manage it.
FARM_FIELD_RADIUS: int = 12

STARTING_WOOD: int = 2
STARTING_ROCK: int = 2
STARTING_FOOD: int = 12  # berries at home so early hires can eat
BUILD_SECONDS_PER_ITEM: float = 2.0
# Ticks of construction work required per wood/rock unit (at simulation ×1).
BUILD_TICKS_PER_ITEM: int = int(FPS * BUILD_SECONDS_PER_ITEM)

# Satiation 1.0 → 0.0 over this many seconds at ×1 (75%→50% ≈ 45s, matching old meal pace).
VILLAGER_SATIATION_SECONDS: float = 180.0
VILLAGER_SATIATION_DECAY_PER_TICK: float = 1.0 / (FPS * VILLAGER_SATIATION_SECONDS)

# Prefer these HomeStorage / inventory food keys when eating at random.
VILLAGER_FOOD_KEYS: tuple[str, ...] = (
    "berries",
    "mushrooms",
    "fish",
    "meat",
)

INDICATOR_RADIUS: int = 2

SAPLING_GROWTH_TICKS: int = 3840
SAPLING_DROP_CHANCE: float = 0.25

NATURAL_SPROUT_MIN_PATCH: int = 4
NATURAL_SPROUT_CHANCE: float = 1.0 / 8.0
NATURAL_SPROUT_INTERVAL: int = 180

TREE_WOOD_DEPOSIT: int = 2
ROCK_DEPOSIT: int = 10  # legacy default
ROCK_SMALL_MIN: int = 2
ROCK_SMALL_MAX: int = 5
ROCK_LARGE_MIN: int = 20
ROCK_LARGE_MAX: int = 28
ANIMAL_MEAT_YIELD: int = 3
FISH_YIELD: int = 2

# Forage resources
BERRY_BUSH_YIELD: int = 5
BERRY_REGEN_TICKS: int = 2400
BERRY_SEED_DROP_CHANCE: float = 0.08
BERRY_SPREAD_CHANCE: float = 0.02  # per bush per forage tick
BERRY_SPREAD_INTERVAL: int = 600

MUSHROOM_SPAWN_CHANCE: float = 0.012  # soil next to tree, per forage tick
MUSHROOM_SPREAD_CHANCE: float = 0.02  # into neighbouring soil
MUSHROOM_TICK_INTERVAL: int = 360

HERB_SPAWN_CHANCE: float = 0.03  # empty grass per forage tick (legacy name)
HERB_SEED_DROP_CHANCE: float = 1.0 / 3.0  # forage fallback
HERB_TICK_INTERVAL: int = 150
# Farm crop growth fallback (~32 in-game days at TICKS_PER_DAY = FPS*4).
FARM_CROP_GROWTH_TICKS: int = FPS * 4 * 32
FARM_HERB_SEED_DROP_CHANCE: float = 1.0  # farm always yields 1–3 seeds (see crops.py)

VILLAGER_MOVE_INTERVAL: int = 48
VILLAGER_WORK_INTERVAL: int = 72

ANIMAL_MOVE_INTERVAL: int = 80
ANIMAL_GROWTH_INTERVAL: int = 480
ANIMAL_TREES_PER_CAP: int = 4

FISH_MOVE_INTERVAL: int = 80
FISH_GROWTH_INTERVAL: int = 480
FISH_WATER_PER_CAP: int = 4

DISTURBANCE_DECAY_PER_TICK: float = 0.002
DISTURBANCE_INTERACTION_BOOST: float = 0.25
DISTURBANCE_NEIGHBOUR_SPREAD: float = 0.08
DISTURBANCE_MAX: float = 1.0

STATUS_MESSAGE_FRAMES: int = 150

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
COLOUR_ANIMAL: Colour = (160, 100, 60)
COLOUR_WORKSTATION: Colour = (90, 90, 140)
COLOUR_FORESTER: Colour = (40, 110, 55)
COLOUR_MASON: Colour = (120, 115, 100)
COLOUR_HUNTER: Colour = (140, 70, 50)
COLOUR_FORAGER: Colour = (70, 130, 90)
COLOUR_FISHER: Colour = (50, 100, 150)
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
COLOUR_FARM: Colour = (160, 130, 70)
COLOUR_FIELD: Colour = (140, 120, 55)
COLOUR_CROP: Colour = (110, 190, 80)

COLOUR_TOOLBAR_BG: Colour = (36, 38, 44)
COLOUR_TOOLBAR_BTN: Colour = (55, 58, 68)
COLOUR_TOOLBAR_BTN_HOVER: Colour = (70, 74, 88)
COLOUR_TOOLBAR_BTN_ACTIVE: Colour = (70, 110, 160)
COLOUR_TOOLBAR_BORDER: Colour = (80, 84, 96)
COLOUR_MENU_BG: Colour = (48, 50, 58)

COLOUR_SOIL: Colour = (139, 105, 70)
COLOUR_GRASS: Colour = (90, 150, 70)
COLOUR_WATER: Colour = (60, 120, 190)
COLOUR_ICE: Colour = (170, 205, 230)
COLOUR_ROCK_TERRAIN: Colour = (118, 118, 124)
COLOUR_ROCK_TERRAIN_DARK: Colour = (95, 95, 102)

COLOUR_TREE_CANOPY: Colour = (34, 120, 45)
COLOUR_TREE_TRUNK: Colour = (90, 55, 30)
COLOUR_SAPLING: Colour = (140, 210, 90)
COLOUR_ROCK_FEATURE: Colour = (130, 130, 140)
COLOUR_HOME: Colour = (150, 90, 50)
COLOUR_HOME_ROOF: Colour = (170, 60, 50)

OVERLAY_ALPHA: int = 110
COLOUR_DIVERSITY_LOW: Colour = (40, 40, 80)
COLOUR_DIVERSITY_HIGH: Colour = (80, 220, 255)
COLOUR_TREE_DENSITY_LOW: Colour = (20, 40, 20)
COLOUR_TREE_DENSITY_HIGH: Colour = (40, 220, 60)
COLOUR_DISTURBANCE_LOW: Colour = (40, 20, 20)
COLOUR_DISTURBANCE_HIGH: Colour = (255, 70, 40)
