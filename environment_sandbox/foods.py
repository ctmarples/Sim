"""Edible food effects — re-exported from ``resource_balance``.

Prefer importing from ``resource_balance`` for new code.
"""

from __future__ import annotations

from resource_balance import (
    FOOD_BY_KEY,
    FOODS,
    FoodDef,
    MAX_FOOD_TYPES_PER_MEAL,
    MEAL_POINTS_FULL,
    combine_meal_buffs,
    food_def,
    satiation_from_points,
)

__all__ = [
    "FOOD_BY_KEY",
    "FOODS",
    "FoodDef",
    "MAX_FOOD_TYPES_PER_MEAL",
    "MEAL_POINTS_FULL",
    "combine_meal_buffs",
    "food_def",
    "satiation_from_points",
]
