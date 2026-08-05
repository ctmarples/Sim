"""Crafting and gather recipes for workplaces.

Builtin recipes live in this module. Additional recipes are loaded from
``recipes_data/<building>/*.json`` (building folder → workplace recipe list).
Each JSON may declare ``resource`` / ``food`` metadata so new outputs get
catalogue entries and use ``assets/icons/<icon_key>.svg`` automatically.

Harvest yields and food satiation/buffs: ``resource_balance.py``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from crops import PRODUCE_KEYS

_RECIPES_DATA_DIR = Path(__file__).resolve().parent / "recipes_data"

# Folder name under recipes_data → attribute holding that building's recipes.
_BUILDING_RECIPE_ATTR: dict[str, str] = {
    "kitchen": "KITCHEN_RECIPES",
    "mill": "MILL_RECIPES",
    "craft_bench": "CRAFT_BENCH_RECIPES",
    "forester": "FORESTER_RECIPES",
    "forester_split": "FORESTER_SPLIT_RECIPES",
    "hunter": "HUNTER_RECIPES",
    "forager": "FORAGER_RECIPES",
}


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
# Extra kitchen recipes (e.g. mushroom_stew) load from recipes_data/kitchen/.
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

KITCHEN_FUEL_KEY: str = "wood"


def _recipe_from_json(data: dict) -> Recipe:
    name = str(data["name"])
    inputs = {str(k): int(v) for k, v in dict(data.get("inputs") or {}).items()}
    outputs = {str(k): int(v) for k, v in dict(data.get("outputs") or {}).items()}
    icon_key = data.get("icon_key")
    if icon_key is not None:
        icon_key = str(icon_key)
    return Recipe(name, inputs, outputs, icon_key=icon_key)


def _apply_recipe_metadata(data: dict, recipe: Recipe) -> None:
    """Register labels, resource catalogue, and food defs from optional JSON fields."""
    label = data.get("label")
    if label:
        RECIPE_LABELS[recipe.name] = str(label)

    resource = data.get("resource")
    if isinstance(resource, dict) and recipe.outputs:
        from resources import register_resource

        out_key = next(iter(recipe.outputs))
        register_resource(
            out_key,
            label=str(resource.get("label") or RECIPE_LABELS.get(recipe.name) or out_key),
            group=str(resource.get("group") or "food"),
            short=str(resource.get("short") or out_key[:4]),
        )

    food = data.get("food")
    if isinstance(food, dict) and recipe.outputs:
        from resource_balance import MEAL_POINTS_FULL, register_food

        out_key = next(iter(recipe.outputs))
        register_food(
            out_key,
            satiation=float(food.get("satiation", MEAL_POINTS_FULL)),
            walk_speed=float(food.get("walk_speed", 1.0)),
            work_efficiency=float(food.get("work_efficiency", 1.0)),
            hunger_rate=float(food.get("hunger_rate", 1.0)),
            edible=bool(food.get("edible", True)),
        )


def _load_directory_recipes() -> None:
    """Merge ``recipes_data/<building>/*.json`` into the matching recipe tuples."""
    global MILL_RECIPES, KITCHEN_RECIPES, CRAFT_BENCH_RECIPES
    global FORESTER_RECIPES, FORESTER_SPLIT_RECIPES, HUNTER_RECIPES, FORAGER_RECIPES

    if not _RECIPES_DATA_DIR.is_dir():
        return

    g = globals()
    for building, attr in _BUILDING_RECIPE_ATTR.items():
        folder = _RECIPES_DATA_DIR / building
        if not folder.is_dir():
            continue
        existing: list[Recipe] = list(g[attr])
        seen = {r.name for r in existing}
        for path in sorted(folder.glob("*.json")):
            with path.open(encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict) or "name" not in data:
                continue
            recipe = _recipe_from_json(data)
            if recipe.name in seen:
                continue
            existing.append(recipe)
            seen.add(recipe.name)
            _apply_recipe_metadata(data, recipe)
        g[attr] = tuple(existing)


def output_keys_for_recipes(recipes: tuple[Recipe, ...] | list[Recipe]) -> tuple[str, ...]:
    keys: list[str] = []
    seen: set[str] = set()
    for recipe in recipes:
        for key in recipe.outputs:
            if key not in seen:
                seen.add(key)
                keys.append(key)
    return tuple(keys)


def input_keys_for_recipes(recipes: tuple[Recipe, ...] | list[Recipe]) -> tuple[str, ...]:
    keys: list[str] = []
    seen: set[str] = set()
    for recipe in recipes:
        for key in recipe.inputs:
            if key not in seen:
                seen.add(key)
                keys.append(key)
    return tuple(keys)


_load_directory_recipes()

MILL_INPUT_KEYS: tuple[str, ...] = input_keys_for_recipes(MILL_RECIPES)
MILL_OUTPUT_KEYS: tuple[str, ...] = output_keys_for_recipes(MILL_RECIPES)
CRAFT_BENCH_INPUT_KEYS: tuple[str, ...] = input_keys_for_recipes(CRAFT_BENCH_RECIPES)
CRAFT_BENCH_OUTPUT_KEYS: tuple[str, ...] = output_keys_for_recipes(CRAFT_BENCH_RECIPES)
KITCHEN_INPUT_KEYS: tuple[str, ...] = input_keys_for_recipes(KITCHEN_RECIPES)
KITCHEN_OUTPUT_KEYS: tuple[str, ...] = output_keys_for_recipes(KITCHEN_RECIPES)

# All crafted / milled goods stored as cargo.
PROCESSED_KEYS: tuple[str, ...] = tuple(
    dict.fromkeys(
        (
            *MILL_OUTPUT_KEYS,
            *KITCHEN_OUTPUT_KEYS,
            *CRAFT_BENCH_OUTPUT_KEYS,
        )
    )
)


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
