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
from enum import Enum, auto

from settings import (
    BUFF_STRENGTH_HUNGER,
    BUFF_STRENGTH_REF,
    BUFF_STRENGTH_SPEED,
    BUFF_STRENGTH_WORK,
    FARM_PRODUCE_YIELD,
    INSECT_REPELLANT_PEST_BOOST,
    DAY_SECONDS_AT_X1,
    pace_ticks,
    seconds_to_ticks,
)

# ---------------------------------------------------------------------------
# Starting stock (home storehouse)
# ---------------------------------------------------------------------------
STARTING_FOOD: int = 12  # berries so early hires can eat

# ---------------------------------------------------------------------------
# Hunger / meals
# ---------------------------------------------------------------------------
# Satiation 1.0 → 0.0 over this many calendar days. The legacy default was
# 180 seconds with a 10-second day, hence 18 days preserves existing balance.
VILLAGER_SATIATION_DAYS: float = 18.0
# Compatibility for diagnostics that still report the default wall-clock duration.
VILLAGER_SATIATION_SECONDS: float = VILLAGER_SATIATION_DAYS * DAY_SECONDS_AT_X1


def satiation_decay_per_tick(
    playback: int | None = None, *, ticks_per_day: int | None = None
) -> float:
    """Hunger drain per tick, locked to a number of calendar days."""
    day_ticks = (
        max(1, int(ticks_per_day))
        if ticks_per_day is not None
        else seconds_to_ticks(DAY_SECONDS_AT_X1, playback)
    )
    return 1.0 / max(1.0, VILLAGER_SATIATION_DAYS * day_ticks)


VILLAGER_SATIATION_DECAY_PER_TICK: float = satiation_decay_per_tick()

# Prefer these HomeStorage / inventory food keys when eating.
# Kitchen craft outputs are appended via ``register_food`` when recipes.csv loads.
VILLAGER_FOOD_KEYS: list[str] = [
    "berries",
    "blackberries",
    "sloe_berries",
    "elderberries",
    "hazelnuts",
    "mushrooms",
    "honey",
    "fish",
    "meat",
    "onion",
    "peas",
    "beans",
    "turnip",
    "cabbage",
    "carrot",
    "garlic",
]

# 5 meal-points ≈ one full stew-sized meal.
MEAL_POINTS_FULL: float = 5.0
# Max distinct food types in one meal (1 unit of each type).
MAX_FOOD_TYPES_PER_MEAL: int = 3
# Dessert extras after a full meat meal (kitchen sweets + honey).
SWEET_FOOD_KEYS: set[str] = {"honey"}


def register_sweet_food(key: str) -> None:
    """Mark ``key`` as a dessert that can accompany a full meat meal."""
    if key:
        SWEET_FOOD_KEYS.add(str(key))


def food_is_sweet(key: str) -> bool:
    return str(key) in SWEET_FOOD_KEYS


def meal_includes_meat(food_keys: list[str]) -> bool:
    """True when the meal covers the meat staple (not fish-only)."""
    return any(food_covers_requirement(k, "meat") for k in food_keys)


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


# Raw / foraged foods only. Kitchen craft foods: ``recipes_data/kitchen/recipes.csv``.
FOODS: list[FoodDef] = [
    FoodDef("berries", satiation=1.0),
    FoodDef("blackberries", satiation=1.0),
    FoodDef("sloe_berries", satiation=1.0),
    FoodDef("elderberries", satiation=1.0),
    FoodDef("hazelnuts", satiation=1.2),
    FoodDef("mushrooms", satiation=1.0),
    FoodDef("honey", satiation=1.5, hunger_rate=0.8, walk_speed=1.5),
    FoodDef("onion", satiation=1.0),
    FoodDef("peas", satiation=1.0),
    FoodDef("beans", satiation=1.0),
    FoodDef("turnip", satiation=1.0),
    FoodDef("cabbage", satiation=1.0),
    FoodDef("carrot", satiation=1.0),
    FoodDef("garlic", satiation=1.0),
    # 3 meat ≈ 1 stew → 5/3 points each. Raw: mild speed/work penalty.
    FoodDef("meat", satiation=MEAL_POINTS_FULL / 3.0, walk_speed=0.8, work_efficiency=0.8),
    FoodDef("fish", satiation=MEAL_POINTS_FULL / 3.0, walk_speed=0.8, work_efficiency=0.8),
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


class FoodSatisfaction(Enum):
    """The single preference result owned by one meal-selection event."""

    FAVOURITE = auto()
    ACCEPTABLE = auto()
    UNWANTED = auto()
    NONE = auto()


FOOD_HAPPINESS_FAVOURITE = 2
FOOD_HAPPINESS_UNWANTED = -2


def is_favourite_food(villager: object, item_key: str) -> bool:
    return str(item_key) in (getattr(villager, "favourite_foods", None) or [])


def food_satisfies_any_required_food(villager: object, item_key: str) -> bool:
    return food_covers_any_requirement(
        str(item_key), list(getattr(villager, "required_foods", None) or [])
    )


def classify_food_satisfaction(villager: object, eaten_keys: list[str]) -> FoodSatisfaction:
    if not eaten_keys:
        return FoodSatisfaction.NONE
    if any(is_favourite_food(villager, key) for key in eaten_keys):
        return FoodSatisfaction.FAVOURITE
    required = list(getattr(villager, "required_foods", None) or [])
    if not required or any(food_covers_any_requirement(key, required) for key in eaten_keys):
        return FoodSatisfaction.ACCEPTABLE
    return FoodSatisfaction.UNWANTED


def food_satisfaction_points(villager: object, result: FoodSatisfaction) -> int:
    if result is FoodSatisfaction.FAVOURITE:
        points = FOOD_HAPPINESS_FAVOURITE
        return points + (1 if "Picky" in (getattr(villager, "vices", None) or []) else 0)
    if result is FoodSatisfaction.UNWANTED:
        points = FOOD_HAPPINESS_UNWANTED
        if "Picky" in (getattr(villager, "vices", None) or []):
            points -= 1
        if "Cheerful" in (getattr(villager, "virtues", None) or []):
            points += 1
        return points
    return 0


def food_preference_key(
    key: str,
    required_foods: list[str] | None = None,
    favourite_foods: list[str] | None = None,
) -> tuple:
    """Sort key for meal picking: required staples first, then buffs, then satiation."""
    fx = food_def(key)
    req_miss = 0
    if required_foods:
        # 0 = covers a required staple (prefer), 1 = does not.
        req_miss = 0 if food_covers_any_requirement(key, required_foods) else 1
    debuff = 1 if (fx.walk_speed < 1.0 or fx.work_efficiency < 1.0) else 0
    return (
        0 if key in (favourite_foods or []) else 1,
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

# Raw produce keys that satisfy the ``vegetables`` hire requirement.
VEGETABLE_KEYS: frozenset[str] = frozenset(
    {"onion", "peas", "beans", "turnip", "cabbage", "carrot", "garlic"}
)

# Composite hire requirement keys (OR groups and category labels).
REQUIREMENT_OR_GROUPS: dict[str, frozenset[str]] = {
    "meat/fish": frozenset({"meat", "fish"}),
}

REQUIREMENT_LABELS: dict[str, str] = {
    "meat/fish": "Meat or fish",
    "vegetables": "Vegetables",
}

REQUIREMENT_ICONS: dict[str, str] = {
    "meat/fish": "meat",
    "vegetables": "vegetable_soup",
}

# Which hire requirement keys each edible item satisfies (includes cooked dishes).
FOOD_REQUIREMENT_TAGS: dict[str, frozenset[str]] = {
    "meat": frozenset({"meat", "meat/fish"}),
    "fish": frozenset({"fish", "meat/fish"}),
    "grilled_meat": frozenset({"meat", "meat/fish"}),
    "grilled_fish": frozenset({"fish", "meat/fish"}),
    "stew": frozenset({"meat", "meat/fish", "vegetables"}),
    "spiced_stew": frozenset({"meat", "meat/fish", "vegetables"}),
    "fish_stew": frozenset({"fish", "meat/fish"}),
    "bread": frozenset({"bread"}),
    "onion": frozenset({"vegetables"}),
    "cabbage": frozenset({"vegetables"}),
    "carrot": frozenset({"vegetables"}),
    "garlic": frozenset({"vegetables"}),
    "vegetable_soup": frozenset({"vegetables"}),
}

# Legacy staple tags kept for callers that only know meat / fish / bread.
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


def food_requirement_tags(key: str) -> frozenset[str]:
    tags = set(FOOD_REQUIREMENT_TAGS.get(key, ()))
    tags.update(FOOD_STAPLE_TAGS.get(key, ()))
    if key in VEGETABLE_KEYS:
        tags.add("vegetables")
    staples = tags & frozenset({"meat", "fish"})
    if staples:
        tags.add("meat/fish")
    return frozenset(tags)


def food_staple_tags(key: str) -> frozenset[str]:
    tags = FOOD_STAPLE_TAGS.get(key)
    if tags is not None:
        return tags
    if key in HIRE_STAPLE_FOODS_LOCAL:
        return frozenset({key})
    return frozenset()


def food_covers_requirement(food_key: str, requirement: str) -> bool:
    if food_key == requirement:
        return True
    return requirement in food_requirement_tags(food_key)


def requirement_met_in_stock(amounts: dict[str, int], requirement: str) -> bool:
    """True if village stock satisfies one hire food requirement key."""
    req = str(requirement)
    if req in REQUIREMENT_OR_GROUPS:
        group = REQUIREMENT_OR_GROUPS[req]
        if any(int(amounts.get(k, 0)) > 0 for k in group):
            return True
        return any(
            int(qty) > 0 and food_covers_requirement(key, req)
            for key, qty in amounts.items()
        )
    if req == "vegetables":
        if any(int(amounts.get(k, 0)) > 0 for k in VEGETABLE_KEYS):
            return True
        return any(
            int(qty) > 0 and food_covers_requirement(key, req)
            for key, qty in amounts.items()
        )
    return int(amounts.get(req, 0)) > 0 or any(
        int(qty) > 0 and food_covers_requirement(key, req)
        for key, qty in amounts.items()
    )


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


def _buff_strength(kind: str) -> int:
    """Live File → Balance fifths (0–5). Falls back to settings defaults."""
    key = {
        "speed": "BUFF_STRENGTH_SPEED",
        "work": "BUFF_STRENGTH_WORK",
        "hunger": "BUFF_STRENGTH_HUNGER",
    }[kind]
    try:
        from balance_config import active_balance

        return active_balance().get_int(key)
    except Exception:
        return {
            "speed": BUFF_STRENGTH_SPEED,
            "work": BUFF_STRENGTH_WORK,
            "hunger": BUFF_STRENGTH_HUNGER,
        }[kind]


def scale_recipe_mult(raw: float, kind: str) -> float:
    """Scale the gap from 1.0 on a recipe multiplier authored at ``BUFF_STRENGTH_REF``/5.

    0.8 is a −0.2 debuff; 1.2 is a +0.2 buff. Strength 0 turns the effect off
    (returns 1.0). Example: ±0.2 at 3/5 → 4/5 is 0.27; the multiplier is then
    rounded to one decimal: 0.8 → 0.7, 1.2 → 1.3.
    """
    value = float(raw)
    if abs(value - 1.0) <= 1e-9:
        return 1.0
    n = _buff_strength(kind)
    if n <= 0:
        return 1.0
    ref = max(1, int(BUFF_STRENGTH_REF))
    return round(1.0 + (value - 1.0) * n / ref, 1)


def format_buff_mult(value: float) -> str:
    """Always one decimal, e.g. 0.8 or 1.3."""
    return f"{float(value):.1f}"


def combine_meal_buffs(food_keys: list[str]) -> tuple[float, float, float]:
    """Return (walk_speed, work_efficiency, hunger_rate) for a finished meal.

    Recipe weights are scaled by the live speed / work / hunger strengths,
    then stack multiplicatively so debuffs (<1) and buffs (>1) both apply.
    """
    walk = 1.0
    work = 1.0
    hunger = 1.0
    for key in food_keys:
        fx = food_def(key)
        walk *= scale_recipe_mult(fx.walk_speed, "speed")
        work *= scale_recipe_mult(fx.work_efficiency, "work")
        hunger *= scale_recipe_mult(fx.hunger_rate, "hunger")
    return round(walk, 1), round(work, 1), round(hunger, 1)


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

# Deer / boar / rabbit hunt yields: recipes_data/hunter/recipes.csv (outputs column).
# After a deer/boar kill: other deer & boar in this Chebyshev radius flee.
HUNT_SCARE_RADIUS: int = 5
# How many flee steps each scared animal takes.
HUNT_SCARE_STEPS: int = 4
# Deer/boar start fleeing when a hunter/player is within this Chebyshev radius.
HUNT_APPROACH_RADIUS: int = 6
# Flee pace fallback (= healthy unbuffed villager walk). Game passes scaled interval.
HUNT_SCARE_MOVE_INTERVAL: int = pace_ticks(48)
# Fish species spawn weight / catch yield — edit ``wildlife_species.py``.
from wildlife_species import (  # noqa: E402
    fish_spawn_weight_table as _fish_spawn_weight_table,
    fish_yield_table as _fish_yield_table,
    max_fish_yield as _max_fish_yield,
)

FISH_SPAWN_WEIGHTS: dict[str, int] = _fish_spawn_weight_table()
FISH_SPECIES_YIELD: dict[str, int] = _fish_yield_table()
# Largest single-catch yield — used for "will the next catch fit?" cargo checks.
FISH_YIELD: int = _max_fish_yield()

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
# Chance a mating pair produces offspring per annual spring breeding event.
# Healthy, underpopulated habitat yields up to three births per pair.
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
MINERAL_POWDER_PEST_BOOST: float = 0.04
FIELD_PEST_BOOST_MAX: float = 0.30
# Initial colonies seeded per kind on new maps.
COLONY_SEED_GROUNDS: int = 3
# Legacy defaults; live values come from balance WILDLIFE_*_FORAGE_PER_LEVEL.
BEE_FORAGE_TILES_PER_LEVEL: int = 10
RABBIT_FORAGE_TILES_PER_LEVEL: int = 10
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
# Rabbit warren yields: recipes_data/hunter/recipes.csv (rabbit row).
# Barn threshing: straw byproduct when processing wheat/rye into grain (recipes_data/barn).
GRAIN_STRAW_YIELD: int = 2  # legacy; straw now comes from barn recipes
# Forager: one level drop yields this much honey (one collect = one level).
HONEY_PER_BEE_LEVEL: int = 5
# Rabbit members: pause this many ticks after each one-tile hop.
RABBIT_MOVE_PAUSE: int = 120


# Berry regen / seed drop are player-facing knobs (not wild-spawn envelopes).
BERRY_REGEN_TICKS: int = 2400
BERRY_SEED_DROP_CHANCE: float = 0.05

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


def farm_produce_yield() -> int:
    """Live File → Balance harvest units per farmed tile."""
    try:
        from balance_config import active_balance

        return max(1, active_balance().get_int("FARM_PRODUCE_YIELD"))
    except Exception:
        return int(FARM_PRODUCE_YIELD)

# Crop seed drops (defaults applied on every CropDef in crops.py).
WILD_SEED_CHANCE: float = 1.0 / 3.0  # forage: chance of 1 seed
FARM_SEED_AMOUNTS: tuple[int, ...] = (1, 2, 3)  # farm: always one of these
HERB_SEED_DROP_CHANCE: float = WILD_SEED_CHANCE  # legacy alias
FARM_HERB_SEED_DROP_CHANCE: tuple[int, ...] = (1, 2, 3)  # farm always rolls farm_seed_amounts

# ---------------------------------------------------------------------------
# Wild plant presence / spawn timing
# ---------------------------------------------------------------------------
# Edit flora in ``wild_species.py``. Values below re-export the catalogue so
# existing imports keep working.
from wild_species import (  # noqa: E402
    WILD_BY_KEY as _WILD_BY_KEY,
    WILD_PLANT_MAX_FRACTION,
    spawn_group_leader as _spawn_group_leader,
)

_berry = _WILD_BY_KEY["blackberry"]
_reed = _WILD_BY_KEY["reed"]
_mushroom = _WILD_BY_KEY["mushroom"]
_wood = _WILD_BY_KEY["wood_bush"]
_herb = _spawn_group_leader("wild_crop")

BERRY_BUSH_YIELD = int(_berry.yield_amount)
BERRY_INITIAL_COUNT = sum(int(getattr(_WILD_BY_KEY.get(k), "initial_count", 0) or 0)
                          for k in ("blackberry", "sloe", "elderberry", "hazel"))
MUSHROOM_YIELD = int(_mushroom.yield_amount)
REED_YIELD = int(_reed.yield_amount)
REED_INITIAL_FRACTION = float(_reed.initial_fraction)
REED_SPAWN_RATE_PEAK = float(_reed.spawn_peak)
REED_SPAWN_ACTIVITY = float(_reed.spawn_activity)
WOOD_BUSH_YIELD = int(_wood.yield_amount)
WOOD_BUSH_SEED_CHANCE = float(_wood.seed_near_chance)
WOOD_BUSH_SPAWN_RATE_PEAK = float(_wood.spawn_peak)
WILD_PRODUCE_YIELD = int(_herb.yield_amount) if _herb is not None else 3

NATURAL_SPROUT_MIN_PATCH: int = 4
NATURAL_SPROUT_CHANCE: float = 1.0 / 8.0
NATURAL_SPROUT_INTERVAL: int = pace_ticks(180)

BERRY_SPREAD_CHANCE: float = 0.01  # legacy; seasonal rates drive spawn now
BERRY_SPREAD_INTERVAL: int = pace_ticks(600)

MUSHROOM_SPAWN_CHANCE: float = float(_mushroom.spawn_peak)  # legacy peak alias
MUSHROOM_SPREAD_CHANCE: float = float(_mushroom.spread_chance)
MUSHROOM_TICK_INTERVAL: int = pace_ticks(360)

HERB_SPAWN_CHANCE: float = float(_herb.spawn_peak) if _herb is not None else 0.03
HERB_TICK_INTERVAL: int = pace_ticks(150)

# Peak multipliers used by seasons.py spawn envelopes (chance per forage tick).
HERB_SPAWN_RATE_PEAK: float = float(_herb.spawn_peak) if _herb is not None else 0.045
HERB_DESPAWN_FADE: float = (
    float(_herb.despawn_fade_chance) if _herb is not None else 0.08
)
HERB_DESPAWN_LEFTOVER: float = (
    float(_herb.despawn_leftover_chance) if _herb is not None else 0.15
)
BERRY_SPAWN_RATE_PEAK: float = float(_berry.spawn_peak)
BERRY_DESPAWN_FADE: float = 0.07  # bushes no longer despawn; legacy only
BERRY_DESPAWN_LEFTOVER: float = 0.18
MUSHROOM_SPAWN_RATE_PEAK: float = float(_mushroom.spawn_peak)

# Farm crop growth fallback (~32 in-game days at TICKS_PER_DAY = FPS*4).
FARM_CROP_GROWTH_TICKS: int = seconds_to_ticks(4.0 * 32)
