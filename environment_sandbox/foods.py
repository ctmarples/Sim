"""Edible food effects: satiation value and meal buffs.

Satiation values are meal-points where 5 points ≈ one full stew-sized meal
(so 5 carrots = 5 berries = 3 meat = 1 stew).
A meal takes at most one unit of each food type, up to
``MAX_FOOD_TYPES_PER_MEAL`` types, preferring higher satiation first.
Buffs last until the next meal replaces them.
"""

from __future__ import annotations

from dataclasses import dataclass


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


# 5 points = one stew.
MEAL_POINTS_FULL: float = 5.0

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

# Default for any key listed as food but missing a FoodDef.
_DEFAULT_FOOD = FoodDef("default", satiation=1.0)

# Max distinct food types in one meal (1 unit of each type).
MAX_FOOD_TYPES_PER_MEAL: int = 3


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
