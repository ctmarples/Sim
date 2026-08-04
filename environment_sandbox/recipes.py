"""Crafting recipes for Mill and Kitchen workplaces."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Recipe:
    """Consume ``inputs`` from building storage to produce ``outputs``."""

    name: str
    inputs: dict[str, int]
    outputs: dict[str, int]


# 10 grain → 1 flour
MILL_RECIPES: tuple[Recipe, ...] = (
    Recipe("wheat_flour", {"wheat": 10}, {"wheat_flour": 1}),
    Recipe("rye_flour", {"rye": 10}, {"rye_flour": 1}),
)

# Prefer stew, then wheat bread, then rye bread.
KITCHEN_RECIPES: tuple[Recipe, ...] = (
    Recipe(
        "stew",
        {"meat": 2, "onion": 2, "cabbage": 1, "carrot": 1},
        {"stew": 1},
    ),
    Recipe("bread_wheat", {"wheat_flour": 2}, {"bread": 1}),
    Recipe("bread_rye", {"rye_flour": 4}, {"bread": 1}),
)

MILL_INPUT_KEYS: tuple[str, ...] = ("wheat", "rye")
MILL_OUTPUT_KEYS: tuple[str, ...] = ("wheat_flour", "rye_flour")
KITCHEN_INPUT_KEYS: tuple[str, ...] = (
    "wheat_flour",
    "rye_flour",
    "meat",
    "onion",
    "cabbage",
    "carrot",
)
KITCHEN_OUTPUT_KEYS: tuple[str, ...] = ("bread", "stew")

# All crafted / milled goods stored as cargo.
PROCESSED_KEYS: tuple[str, ...] = (
    "wheat_flour",
    "rye_flour",
    "bread",
    "stew",
)

RECIPE_LABELS: dict[str, str] = {
    "wheat_flour": "Wheat flour",
    "rye_flour": "Rye flour",
    "stew": "Stew",
    "bread_wheat": "Bread (wheat)",
    "bread_rye": "Bread (rye)",
}


def recipe_label(recipe: Recipe) -> str:
    return RECIPE_LABELS.get(recipe.name, recipe.name.replace("_", " ").title())


def recipe_inputs_text(recipe: Recipe) -> str:
    from resources import resource_label

    return ", ".join(f"{n} {resource_label(k)}" for k, n in recipe.inputs.items())


def recipe_ready(storage: object, recipe: Recipe) -> bool:
    return all(int(getattr(storage, key, 0)) >= n for key, n in recipe.inputs.items())


def recipe_output_fits(
    storage: object,
    recipe: Recipe,
    *,
    capacity: int | None = None,
    output_capacity: int | None = None,
    output_keys: tuple[str, ...] | None = None,
) -> bool:
    out_total = sum(recipe.outputs.values())
    if output_capacity is not None and output_keys is not None:
        out_stored = sum(int(getattr(storage, key, 0)) for key in output_keys)
        return out_stored + out_total <= output_capacity
    if capacity is None:
        return True
    stored = int(getattr(storage, "stored_total", 0))
    if stored + out_total > capacity:
        return False
    in_total = sum(recipe.inputs.values())
    return stored - in_total + out_total <= capacity


def can_craft(
    storage: object,
    recipes: tuple[Recipe, ...],
    *,
    capacity: int | None = None,
    output_capacity: int | None = None,
    output_keys: tuple[str, ...] | None = None,
) -> Recipe | None:
    for recipe in recipes:
        if recipe_ready(storage, recipe) and recipe_output_fits(
            storage,
            recipe,
            capacity=capacity,
            output_capacity=output_capacity,
            output_keys=output_keys,
        ):
            return recipe
    return None


def apply_recipe(storage: object, recipe: Recipe) -> None:
    for key, n in recipe.inputs.items():
        setattr(storage, key, int(getattr(storage, key, 0)) - n)
    for key, n in recipe.outputs.items():
        setattr(storage, key, int(getattr(storage, key, 0)) + n)


def missing_inputs(storage: object, recipe: Recipe) -> dict[str, int]:
    need: dict[str, int] = {}
    for key, n in recipe.inputs.items():
        have = int(getattr(storage, key, 0))
        if have < n:
            need[key] = n - have
    return need


def input_keys_for_recipes(recipes: tuple[Recipe, ...] | list[Recipe]) -> tuple[str, ...]:
    keys: list[str] = []
    seen: set[str] = set()
    for recipe in recipes:
        for key in recipe.inputs:
            if key not in seen:
                seen.add(key)
                keys.append(key)
    return tuple(keys)
