"""Central resource balance: yields, drops, spawn rates, food effects, and wildlife ecology.

Edit amounts and consumption here. Related catalogues (not duplicated):
- ``resources.py`` — inventory keys / labels / icons
- ``crops.py`` — per-crop seasons, growth days, colours (uses seed defaults below)
- ``trees.py`` — per-species wood yield and growth years
- ``recipes.py`` — mill / kitchen craft input→output ratios
- ``settings.py`` — tick cadence (animal/fish move & growth intervals)
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
VILLAGER_FOOD_KEYS: list[str] = [
    "berries",
    "mushrooms",
    "honey",
    "fish",
    "meat",
    "onion",
    "cabbage",
    "carrot",
    "garlic",
    "bread",
    "stew",
    "fish_stew",
    "mushroom_stew",
    "spiced_stew",
    "grilled_meat",
    "grilled_fish",
]

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


FOODS: list[FoodDef] = [
    FoodDef("berries", satiation=1.0),
    FoodDef("mushrooms", satiation=1.0),
    FoodDef("honey", satiation=1.5, hunger_rate=0.8, walk_speed=1.5),
    FoodDef("onion", satiation=1.0),
    FoodDef("cabbage", satiation=1.0),
    FoodDef("carrot", satiation=1.0),
    FoodDef("garlic", satiation=1.0),
    # 3 meat ≈ 1 stew → 5/3 points each. Raw: mild speed/work penalty.
    FoodDef("meat", satiation=MEAL_POINTS_FULL / 3.0, walk_speed=0.8, work_efficiency=0.8),
    FoodDef("fish", satiation=MEAL_POINTS_FULL / 3.0, walk_speed=0.8, work_efficiency=0.8),
    FoodDef("grilled_meat", satiation=MEAL_POINTS_FULL / 3.0),
    FoodDef("grilled_fish", satiation=MEAL_POINTS_FULL / 3.0),
    FoodDef("grilled_mushrooms", satiation=1.5),
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
    FoodDef("mushroom_stew", satiation=MEAL_POINTS_FULL, walk_speed=1.5, work_efficiency=1.5),
    FoodDef(
        "spiced_stew",
        satiation=MEAL_POINTS_FULL,
        walk_speed=1.75,
        work_efficiency=1.75,
    ),
]

FOOD_BY_KEY: dict[str, FoodDef] = {f.key: f for f in FOODS}
_DEFAULT_FOOD = FoodDef("default", satiation=1.0)


def register_food(
    key: str,
    *,
    satiation: float,
    walk_speed: float = 1.0,
    work_efficiency: float = 1.0,
    hunger_rate: float = 1.0,
    edible: bool = True,
) -> None:
    """Add or replace a food def (used by recipe JSON loader)."""
    fx = FoodDef(
        key,
        satiation=satiation,
        walk_speed=walk_speed,
        work_efficiency=work_efficiency,
        hunger_rate=hunger_rate,
    )
    FOOD_BY_KEY[key] = fx
    for i, existing in enumerate(FOODS):
        if existing.key == key:
            FOODS[i] = fx
            break
    else:
        FOODS.append(fx)
    if edible and key not in VILLAGER_FOOD_KEYS:
        VILLAGER_FOOD_KEYS.append(key)


def food_def(key: str) -> FoodDef:
    return FOOD_BY_KEY.get(key, _DEFAULT_FOOD)


def satiation_from_points(points: float) -> float:
    """Convert meal-points into 0–1 satiation delta."""
    return max(0.0, float(points) / MEAL_POINTS_FULL)


def food_preference_key(key: str, required_foods: list[str] | None = None) -> tuple:
    """Sort key for meal picking: required staples first, then buffs, then satiation."""
    fx = food_def(key)
    req_miss = 0
    if required_foods:
        # 0 = covers a required staple (prefer), 1 = does not.
        req_miss = 0 if food_covers_any_requirement(key, required_foods) else 1
    debuff = 1 if (fx.walk_speed < 1.0 or fx.work_efficiency < 1.0) else 0
    return (
        req_miss,
        debuff,
        -(fx.walk_speed * fx.work_efficiency),
        -fx.satiation,
        -1.0 / max(0.05, fx.hunger_rate),
        key,
    )


def meal_quality_score(food_keys: list[str]) -> float:
    """Higher is better. Combines satiation with stacked walk/work/hunger buffs."""
    if not food_keys:
        return 0.0
    walk, work, hunger = combine_meal_buffs(food_keys)
    sat = sum(food_def(k).satiation for k in food_keys)
    return sat * walk * work / max(0.05, hunger)


def storage_meal_score(
    storage: object,
    food_keys: list[str] | None = None,
    *,
    required_foods: list[str] | None = None,
) -> float:
    """Best meal score available from ``storage`` (up to ``MAX_FOOD_TYPES_PER_MEAL``)."""
    keys = food_keys if food_keys is not None else VILLAGER_FOOD_KEYS
    available = [key for key in keys if int(getattr(storage, key, 0)) > 0]
    if not available:
        return 0.0
    available.sort(key=lambda k: food_preference_key(k, required_foods))
    picked = available[:MAX_FOOD_TYPES_PER_MEAL]
    score = meal_quality_score(picked)
    # Strong bonus when the best available bite covers a hire staple.
    if required_foods and any(
        food_covers_any_requirement(k, required_foods) for k in picked
    ):
        score += 50.0
    return score


# Local alias so this module does not import society (cycle risk).
HIRE_STAPLE_FOODS_LOCAL: tuple[str, ...] = ("meat", "fish", "bread")

# Which edible keys count toward hire staple requirements (meat / fish / bread).
# Cooked dishes inherit the staple(s) in their recipe.
FOOD_STAPLE_TAGS: dict[str, frozenset[str]] = {
    "meat": frozenset({"meat"}),
    "grilled_meat": frozenset({"meat"}),
    "stew": frozenset({"meat"}),
    "spiced_stew": frozenset({"meat"}),
    "fish": frozenset({"fish"}),
    "grilled_fish": frozenset({"fish"}),
    "fish_stew": frozenset({"fish"}),
    "bread": frozenset({"bread"}),
}


def food_staple_tags(key: str) -> frozenset[str]:
    tags = FOOD_STAPLE_TAGS.get(key)
    if tags is not None:
        return tags
    if key in HIRE_STAPLE_FOODS_LOCAL:
        return frozenset({key})
    return frozenset()


def food_covers_requirement(food_key: str, requirement: str) -> bool:
    return requirement in food_staple_tags(food_key) or food_key == requirement


def food_covers_any_requirement(food_key: str, required: list[str] | None) -> bool:
    if not required:
        return False
    return any(food_covers_requirement(food_key, r) for r in required)


def meal_covers_any_requirement(
    eaten_keys: list[str], required: list[str] | None
) -> bool:
    if not required:
        return True
    return any(food_covers_any_requirement(k, required) for k in eaten_keys)


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
# After a deer/boar kill: other deer & boar in this Chebyshev radius flee.
HUNT_SCARE_RADIUS: int = 5
# How many flee steps each scared animal takes.
HUNT_SCARE_STEPS: int = 4
# Deer/boar start fleeing when a hunter/player is within this Chebyshev radius.
HUNT_APPROACH_RADIUS: int = 6
# Flee pace fallback (= healthy unbuffed villager walk). Game passes scaled interval.
HUNT_SCARE_MOVE_INTERVAL: int = 48
FISH_YIELD: int = 2

# ---------------------------------------------------------------------------
# Wildlife / fish ecology (population, habitats, seeding)
# ---------------------------------------------------------------------------
# Patch capacity from breeding-ground size.
ANIMAL_TREES_PER_CAP: int = 3  # deer: 1 per 3 deer-breeding tiles
BOAR_CELLS_PER_CAP: int = 6  # boar: 1 per 6 forest/breeding tiles in patch
# Forage flood-fill radius from nest (Chebyshev) for bee/rabbit colonies.
SMALL_GAME_FORAGE_RADIUS: int = 2
# Usable breeding habitats must hold at least a mating pair.
MIN_BREEDING_CAPACITY: int = 2
DEER_CROP_EAT_CHANCE: float = 0.50
BOAR_CROP_EAT_CHANCE: float = 0.25
# Chance per growth tick that a pair starts its once-per-year migration.
ANIMAL_MIGRATION_CHANCE: float = 0.18
# Chance a mating pair produces one offspring per growth tick (if under cap).
ANIMAL_BREED_CHANCE: float = 0.55
# Initial seed: how many deer / boar breeding grounds to populate, and animals each.
WILDLIFE_SEED_GROUNDS: int = 4
WILDLIFE_SEED_COUNT: int = 2
# Pair seeded onto a random breeding ground when a species is extinct at new year.
WILDLIFE_RESEED_PAIR: int = 2
FISH_WATER_PER_CAP: int = 4

# ---------------------------------------------------------------------------
# Bee / rabbit colonies (not individual animals)
# ---------------------------------------------------------------------------
COLONY_LEVEL_MAX: int = 4
# Visible individuals around the nest for levels 1..4.
COLONY_MEMBERS_BY_LEVEL: tuple[int, ...] = (1, 2, 4, 7)
# How far members may wander from the nest (Chebyshev).
COLONY_MEMBER_RADIUS: int = 2
# Pollination overlay: hive reach grows with colony level.
# Bee nest forage/pollination reach (Chebyshev tiles from nest).
POLLINATOR_BASE_RADIUS: int = 8
POLLINATOR_RADIUS_PER_LEVEL: int = 3
# Nest coverage strength before distance falloff (level 1 → ~0.85, higher → 1.0).
POLLINATOR_BASE_STRENGTH: float = 0.85
POLLINATOR_STRENGTH_PER_LEVEL: float = 0.05

# Alchemist field treatments (player applies with Enter on a field / soil).
INSECT_REPELLANT_PEST_BOOST: float = 0.12
MINERAL_POWDER_PEST_BOOST: float = 0.04
FIELD_PEST_BOOST_MAX: float = 0.30
# Initial colonies seeded per kind on new maps.
COLONY_SEED_GROUNDS: int = 3
# Per growth tick: level-up when food is available (levels 1–3 → next).
COLONY_GROW_CHANCE: float = 0.20
# Per growth tick: a level-3 colony with food may found a new level-1 colony.
COLONY_SPLIT_LEVEL: int = 3
COLONY_SPLIT_CHANCE: float = 0.12
# Rabbits nibble crops near the nest; bees do not.
COLONY_RABBIT_CROP_EAT_CHANCE: float = 0.30
# After a hunt/honey collect: growth ticks before the colony can be harvested again.
COLONY_HARVEST_COOLDOWN: int = 8
# Hunter: one level drop yields this much meat (one hunt = one level).
RABBIT_MEAT_PER_LEVEL: int = 3
# Hunter: fur from each rabbit colony level drop (alongside meat).
RABBIT_FUR_PER_LEVEL: int = 1
# Farm: straw byproduct when harvesting wheat or rye.
GRAIN_STRAW_YIELD: int = 2
# Forager: one level drop yields this much honey (one collect = one level).
HONEY_PER_BEE_LEVEL: int = 5
# Rabbit members: pause this many ticks after each one-tile hop.
RABBIT_MOVE_PAUSE: int = 120


BERRY_BUSH_YIELD: int = 4
BERRY_REGEN_TICKS: int = 2400
BERRY_SEED_DROP_CHANCE: float = 0.05
# Permanent starter bushes on new maps (fruit is seasonal; bushes stay year-round).
BERRY_INITIAL_COUNT: int = 6

MUSHROOM_YIELD: int = 4  # per mushroom tile foraged
REED_YIELD: int = 3
WOOD_BUSH_YIELD: int = 1  # processed wood from bush tiles
# Chance an empty neighbour of a tree gets fallen wood when forests are seeded.
WOOD_BUSH_SEED_CHANCE: float = 0.1
# Peak chance per mushroom-tick for fallen wood to appear next to a tree (autumn).
WOOD_BUSH_SPAWN_RATE_PEAK: float = 0.01

# Forager target pick: within each N-tile band, prefer recipe priority 1→3;
# only look further out when nothing nearer is available.
FORAGER_PRIORITY_BAND: int = 8
# Workplace gather/hunt/fish: only consider targets within this Manhattan radius
# of the search origin (villager if areas drawn, else building).
WORK_SEARCH_RADIUS: int = 48
# Reject a BFS path if it is much longer than the Manhattan straight-line:
# path_len > max(straight * RATIO, straight + SLACK).
PATH_DETOUR_RATIO: float = 2.0
PATH_DETOUR_SLACK: int = 10
# Hard cap on BFS nodes for a single path search (long hauls still fit on typical maps).
PATH_FIND_MAX_NODES: int = 2500
# Within each Manhattan ring, stop after this many successful path checks.
PATH_PICK_MAX_PER_RING: int = 4
# Fisher: walk to a shore near fish density and wait; catch when fish pass.
# Chebyshev radius used when scoring how many fish a shore "covers".
FISH_POST_SCORE_RADIUS: int = 8
FISH_POST_MIN_FISH: int = 2
# Prefer a local school when one exists; otherwise walk farther for density.
FISH_POST_LOCAL_RADIUS: int = 16

WILD_PRODUCE_YIELD: int = 3  # wild crop / herb produce per harvest
FARM_PRODUCE_YIELD: int = 9  # farmed crop produce per harvest

# Crop seed drops (defaults applied on every CropDef in crops.py).
WILD_SEED_CHANCE: float = 1.0 / 3.0  # forage: chance of 1 seed
FARM_SEED_AMOUNTS: tuple[int, ...] = (1, 2, 3)  # farm: always one of these
HERB_SEED_DROP_CHANCE: float = WILD_SEED_CHANCE  # legacy alias
FARM_HERB_SEED_DROP_CHANCE: tuple[int, ...] = (1, 2, 3)  # farm always rolls farm_seed_amounts

# ---------------------------------------------------------------------------
# Wild plant presence / spawn timing
# ---------------------------------------------------------------------------
# Wild crops / berry bushes may cover at most this fraction of each terrain type.
WILD_PLANT_MAX_FRACTION: float = 0.20

NATURAL_SPROUT_MIN_PATCH: int = 4
NATURAL_SPROUT_CHANCE: float = 1.0 / 8.0
NATURAL_SPROUT_INTERVAL: int = 180

BERRY_SPREAD_CHANCE: float = 0.01  # legacy; seasonal rates drive spawn now
BERRY_SPREAD_INTERVAL: int = 600

MUSHROOM_SPAWN_CHANCE: float = 0.006  # legacy peak; see seasonal peaks below
MUSHROOM_SPREAD_CHANCE: float = 0.01  # into neighbouring soil
MUSHROOM_TICK_INTERVAL: int = 360

HERB_SPAWN_CHANCE: float = 0.03  # legacy peak; see seasonal peaks below
HERB_TICK_INTERVAL: int = 150

# Peak multipliers used by seasons.py spawn envelopes (chance per forage tick).
HERB_SPAWN_RATE_PEAK: float = 0.045
HERB_DESPAWN_FADE: float = 0.08
HERB_DESPAWN_LEFTOVER: float = 0.15
BERRY_SPAWN_RATE_PEAK: float = 0.0  # natural bush spawn off; fruit uses berry_fruiting()
BERRY_DESPAWN_FADE: float = 0.07
BERRY_DESPAWN_LEFTOVER: float = 0.18
MUSHROOM_SPAWN_RATE_PEAK: float = 0.015

# Farm crop growth fallback (~32 in-game days at TICKS_PER_DAY = FPS*4).
FARM_CROP_GROWTH_TICKS: int = FPS * 4 * 32
