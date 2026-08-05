"""Crafting and gather recipes for workplaces.

Input/output ratios for mill and kitchen crafts live here.
Harvest yields and food satiation/buffs: ``resource_balance.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

from crops import PRODUCE_KEYS


@dataclass(frozen=True)
class Recipe:
    """Consume ``inputs`` to produce ``outputs`` (gather recipes use empty inputs)."""

    name: str
    inputs: dict[str, int]
    outputs: dict[str, int]
    # Inventory / animal icon key for UI (defaults to first output key).
    icon_key: str | None = None

    def display_icon_key(self) -> str:
        if self.icon_key:
            return self.icon_key
        if self.outputs:
            return next(iter(self.outputs))
        return self.name


# 10 grain → 1 flour
MILL_RECIPES: tuple[Recipe, ...] = (
    Recipe("wheat_flour", {"wheat": 10}, {"wheat_flour": 1}),
    Recipe("rye_flour", {"rye": 10}, {"rye_flour": 1}),
)

# Prefer meat stew, fish stew, grilled, then breads. Fuel wood consumed separately.
KITCHEN_RECIPES: tuple[Recipe, ...] = (
    Recipe(
        "stew",
        {"meat": 2, "onion": 2, "cabbage": 1, "carrot": 1},
        {"stew": 1},
    ),
    Recipe(
        "fish_stew",
        {"fish": 2, "garlic": 1},
        {"fish_stew": 1},
    ),
    Recipe("grilled_meat", {"meat": 1}, {"grilled_meat": 1}),
    Recipe("grilled_fish", {"fish": 1}, {"grilled_fish": 1}),
    Recipe("bread_wheat", {"wheat_flour": 2}, {"bread": 1}),
    Recipe("bread_rye", {"rye_flour": 4}, {"bread": 1}),
)

CRAFT_BENCH_RECIPES: tuple[Recipe, ...] = (
    Recipe("twine", {"hemp": 1, "flax": 1}, {"twine": 1}),
    Recipe("axe", {"wood": 1, "rock": 1, "twine": 1}, {"axe": 1}),
    Recipe("spear", {"wood": 1}, {"spear": 1}),
    Recipe("fishing_rod", {"wood": 1, "twine": 2}, {"fishing_rod": 1}),
    Recipe("hoe", {"wood": 1, "rock": 1, "twine": 1}, {"hoe": 1}),
    Recipe("knife", {"wood": 1, "rock": 1, "twine": 1}, {"knife": 1}),
)

# Gather toggles (chop trees → logs / hardwood logs).
FORESTER_RECIPES: tuple[Recipe, ...] = (
    Recipe("logs", {}, {"logs": 1}),
    Recipe("hardwood_logs", {}, {"hardwood_logs": 1}),
)

# Split logs at the forester building (work mode Split).
FORESTER_SPLIT_RECIPES: tuple[Recipe, ...] = (
    Recipe("split_log", {"logs": 1}, {"wood": 7}),
    Recipe("split_hardwood", {"hardwood_logs": 1}, {"wood": 10}),
)

HUNTER_RECIPES: tuple[Recipe, ...] = (
    Recipe("deer", {}, {"meat": 1}, icon_key="deer"),
    Recipe("boar", {}, {"meat": 1}, icon_key="boar"),
)

FORAGER_RECIPES: tuple[Recipe, ...] = (
    Recipe("wood", {}, {"wood": 1}),
    Recipe("berries", {}, {"berries": 1}),
    Recipe("mushrooms", {}, {"mushrooms": 1}),
    *(Recipe(key, {}, {key: 1}) for key in PRODUCE_KEYS),
)

MILL_INPUT_KEYS: tuple[str, ...] = ("wheat", "rye")
MILL_OUTPUT_KEYS: tuple[str, ...] = ("wheat_flour", "rye_flour")
CRAFT_BENCH_INPUT_KEYS: tuple[str, ...] = (
    "hemp",
    "flax",
    "wood",
    "rock",
    "twine",
)
CRAFT_BENCH_OUTPUT_KEYS: tuple[str, ...] = (
    "twine",
    "axe",
    "spear",
    "fishing_rod",
    "hoe",
    "knife",
)
KITCHEN_INPUT_KEYS: tuple[str, ...] = (
    "wheat_flour",
    "rye_flour",
    "meat",
    "fish",
    "onion",
    "cabbage",
    "carrot",
    "garlic",
)
KITCHEN_OUTPUT_KEYS: tuple[str, ...] = (
    "bread",
    "stew",
    "fish_stew",
    "grilled_meat",
    "grilled_fish",
)
KITCHEN_FUEL_KEY: str = "wood"

# All crafted / milled goods stored as cargo.
PROCESSED_KEYS: tuple[str, ...] = (
    "wheat_flour",
    "rye_flour",
    "bread",
    "stew",
    "fish_stew",
    "grilled_meat",
    "grilled_fish",
    "twine",
    "axe",
    "spear",
    "fishing_rod",
    "hoe",
    "knife",
)

RECIPE_LABELS: dict[str, str] = {
    "wheat_flour": "Wheat flour",
    "rye_flour": "Rye flour",
    "stew": "Stew",
    "fish_stew": "Fish stew",
    "grilled_meat": "Grilled meat",
    "grilled_fish": "Grilled fish",
    "bread_wheat": "Bread (wheat)",
    "bread_rye": "Bread (rye)",
    "twine": "Twine",
    "axe": "Axe",
    "spear": "Spear",
    "fishing_rod": "Fishing rod",
    "hoe": "Hoe",
    "knife": "Knife",
    "split_log": "Split log",
    "split_hardwood": "Split hardwood log",
    "logs": "Logs",
    "hardwood_logs": "Hardwood logs",
    "wood": "Wood",
    "deer": "Deer",
    "boar": "Boar",
    "berries": "Berries",
    "mushrooms": "Mushrooms",
}


def recipe_label(recipe: Recipe) -> str:
    if recipe.name in RECIPE_LABELS:
        return RECIPE_LABELS[recipe.name]
    from resources import resource_label

    if recipe.outputs:
        return resource_label(next(iter(recipe.outputs)))
    return recipe.name.replace("_", " ").title()


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
        if out_stored + out_total > output_capacity:
            return False
    elif capacity is not None:
        stored = int(getattr(storage, "stored_total", 0))
        in_total = sum(recipe.inputs.values())
        # Net change after consuming inputs — gross ``stored + out_total`` wrongly
        # blocks crafts when the building is nearly full (e.g. forester split).
        if stored - in_total + out_total > capacity:
            return False
    # Per-item caps (Building.item_caps).
    caps = getattr(storage, "item_caps", None)
    if isinstance(caps, dict) and caps:
        for key, n in recipe.outputs.items():
            cap = caps.get(key)
            if cap is not None and int(getattr(storage, key, 0)) + n > int(cap):
                return False
    return True


def can_craft(
    storage: object,
    recipes: tuple[Recipe, ...],
    *,
    capacity: int | None = None,
    output_capacity: int | None = None,
    output_keys: tuple[str, ...] | None = None,
) -> Recipe | None:
    for recipe in recipes:
        if not recipe.inputs:
            continue
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
