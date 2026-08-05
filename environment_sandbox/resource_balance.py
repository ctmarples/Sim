"""Central resource balance: yields, drops, spawn rates, and food effects.

Edit amounts and consumption here. Related catalogues (not duplicated):
- ``resources.py`` — inventory keys / labels / icons
- ``crops.py`` — per-crop seasons, growth days, colours (uses seed defaults below)
- ``trees.py`` — per-species wood yield and growth years
- ``recipes.py`` — mill / kitchen craft input→output ratios
"""

from __future__ import annotations

from dataclasses import dataclass

from settings import FPS

# ---------------------------------------------------------------------------
# Starting stock (home storehouse)
# ---------------------------------------------------------------------------
STARTING_FOOD: int = 12  # berries so early hires can eat

# ---------------------------------------------------------------------------
# Hunger / meals
# ---------------------------------------------------------------------------
# Satiation 1.0 → 0.0 over this many seconds at ×1.
VILLAGER_SATIATION_SECONDS: float = 180.0
VILLAGER_SATIATION_DECAY_PER_TICK: float = 1.0 / (FPS * VILLAGER_SATIATION_SECONDS)

# Prefer these HomeStorage / inventory food keys when eating.
VILLAGER_FOOD_KEYS: tuple[str, ...] = (
    "berries",
    "mushrooms",
    "fish",
    "meat",
    "onion",
    "cabbage",
    "carrot",
    "garlic",
    "bread",
    "stew",
    "fish_stew",
    "grilled_meat",
    "grilled_fish",
)

# 5 meal-points ≈ one full stew-sized meal.
MEAL_POINTS_FULL: float = 5.0
# Max distinct food types in one meal (1 unit of each type).
MAX_FOOD_TYPES_PER_MEAL: int = 3


@dataclass(frozen=True)
class FoodDef:
    key: str
    # Meal points added to satiation (5 points → +1.0 satiation when empty).
    satiation: float
    # Multipliers applied until the next meal (1.0 = unchanged).
    walk_speed: float = 1.0
    work_efficiency: float = 1.0
    # Hunger / satiation decay rate (0.5 = half as fast).
    hunger_rate: float = 1.0


FOODS: tuple[FoodDef, ...] = (
    FoodDef("berries", satiation=1.0),
    FoodDef("mushrooms", satiation=1.0),
    FoodDef("onion", satiation=1.0),
    FoodDef("cabbage", satiation=1.0),
    FoodDef("carrot", satiation=1.0),
    FoodDef("garlic", satiation=1.0),
    # 3 meat ≈ 1 stew → 5/3 points each. Raw: mild speed/work penalty.
    FoodDef("meat", satiation=MEAL_POINTS_FULL / 3.0, walk_speed=0.8, work_efficiency=0.8),
    FoodDef("fish", satiation=MEAL_POINTS_FULL / 3.0, walk_speed=0.8, work_efficiency=0.8),
    FoodDef("grilled_meat", satiation=MEAL_POINTS_FULL / 3.0),
    FoodDef("grilled_fish", satiation=MEAL_POINTS_FULL / 3.0),
    # Bread: solid meal, halves hunger until next meal.
    FoodDef("bread", satiation=2.5, hunger_rate=0.5),
    # Stew: full meal, doubles walk + work.
    FoodDef("stew", satiation=MEAL_POINTS_FULL, walk_speed=2.0, work_efficiency=2.0),
    FoodDef(
        "fish_stew",
        satiation=MEAL_POINTS_FULL,
        walk_speed=2.0,
        work_efficiency=2.0,
    ),
)

FOOD_BY_KEY: dict[str, FoodDef] = {f.key: f for f in FOODS}
_DEFAULT_FOOD = FoodDef("default", satiation=1.0)


def food_def(key: str) -> FoodDef:
    return FOOD_BY_KEY.get(key, _DEFAULT_FOOD)


def satiation_from_points(points: float) -> float:
    """Convert meal-points into 0–1 satiation delta."""
    return max(0.0, float(points) / MEAL_POINTS_FULL)


def combine_meal_buffs(food_keys: list[str]) -> tuple[float, float, float]:
    """Return (walk_speed, work_efficiency, hunger_rate) for a finished meal.

    Multipliers stack multiplicatively so debuffs (<1) and buffs (>1) both apply.
    """
    walk = 1.0
    work = 1.0
    hunger = 1.0
    for key in food_keys:
        fx = food_def(key)
        walk *= fx.walk_speed
        work *= fx.work_efficiency
        hunger *= fx.hunger_rate
    return walk, work, hunger


# ---------------------------------------------------------------------------
# Harvest / deposit yields (units into inventory or left on the ground)
# ---------------------------------------------------------------------------
# Trees: per-species amounts live on TreeDef.yield_amount in trees.py.
TREE_WOOD_DEPOSIT: int = 2  # legacy default; species yields override
SAPLING_DROP_CHANCE: float = 0.25
SAPLING_GROWTH_TICKS: int = 3840  # legacy; growth_ticks_for(tree) is preferred

ROCK_DEPOSIT: int = 10  # legacy default
ROCK_SMALL_MIN: int = 2
ROCK_SMALL_MAX: int = 5
ROCK_LARGE_MIN: int = 20
ROCK_LARGE_MAX: int = 28

DEER_MEAT_YIELD: int = 3
BOAR_MEAT_YIELD: int = 5
ANIMAL_MEAT_YIELD: int = DEER_MEAT_YIELD  # legacy alias
FISH_YIELD: int = 2

BERRY_BUSH_YIELD: int = 5
BERRY_REGEN_TICKS: int = 2400
BERRY_SEED_DROP_CHANCE: float = 0.08

MUSHROOM_YIELD: int = 5  # per mushroom tile foraged
REED_YIELD: int = 3
WILD_PRODUCE_YIELD: int = 1  # wild crop / herb produce per harvest
FARM_PRODUCE_YIELD: int = 3  # farmed crop produce per harvest

# Crop seed drops (defaults applied on every CropDef in crops.py).
WILD_SEED_CHANCE: float = 1.0 / 3.0  # forage: chance of 1 seed
FARM_SEED_AMOUNTS: tuple[int, ...] = (1, 2, 3)  # farm: always one of these
HERB_SEED_DROP_CHANCE: float = WILD_SEED_CHANCE  # legacy alias
FARM_HERB_SEED_DROP_CHANCE: float = 1.0  # farm always rolls farm_seed_amounts

# ---------------------------------------------------------------------------
# Wild plant presence / spawn timing
# ---------------------------------------------------------------------------
# Wild crops / berry bushes may cover at most this fraction of each terrain type.
WILD_PLANT_MAX_FRACTION: float = 0.20

NATURAL_SPROUT_MIN_PATCH: int = 4
NATURAL_SPROUT_CHANCE: float = 1.0 / 8.0
NATURAL_SPROUT_INTERVAL: int = 180

BERRY_SPREAD_CHANCE: float = 0.02  # legacy; seasonal rates drive spawn now
BERRY_SPREAD_INTERVAL: int = 600

MUSHROOM_SPAWN_CHANCE: float = 0.012  # legacy peak; see seasonal peaks below
MUSHROOM_SPREAD_CHANCE: float = 0.02  # into neighbouring soil
MUSHROOM_TICK_INTERVAL: int = 360

HERB_SPAWN_CHANCE: float = 0.03  # legacy peak; see seasonal peaks below
HERB_TICK_INTERVAL: int = 150

# Peak multipliers used by seasons.py spawn envelopes (chance per forage tick).
HERB_SPAWN_RATE_PEAK: float = 0.045
HERB_DESPAWN_FADE: float = 0.08
HERB_DESPAWN_LEFTOVER: float = 0.15
BERRY_SPAWN_RATE_PEAK: float = 0.025
BERRY_DESPAWN_FADE: float = 0.07
BERRY_DESPAWN_LEFTOVER: float = 0.18
MUSHROOM_SPAWN_RATE_PEAK: float = 0.03

# Farm crop growth fallback (~32 in-game days at TICKS_PER_DAY = FPS*4).
FARM_CROP_GROWTH_TICKS: int = FPS * 4 * 32
