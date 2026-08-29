"""Crafting and gather recipes for workplaces.

Recipes live in ``recipes_data/<building>/recipes.csv`` (one sheet per building).
Edit those CSVs to add or tweak recipes — no Python changes needed for I/O amounts.

Columns:
  name, label, inputs, outputs, steps, category, icon_key,
  extraction, farming, hunting, crafting, labour, transport,
  resource_group, resource_short,
  food_satiation, food_walk_speed, food_work_efficiency, food_hunger_rate, food_edible,
  walk_speed, capacity_bonus, heat_protection, cold_protection, clothing_slot

``inputs`` / ``outputs`` use ``key:qty;key:qty`` (empty inputs = gather toggle).
``steps`` is how many work ticks finish one craft (blank = ``PROCESSOR_RECIPE_STEPS``,
usually 3). Barn threshing uses ``1`` so it completes in a single work action.
``category`` groups recipes in the building inspect UI (kitchen: stews, grill, …).
Skill columns are minimum levels (1–10); leave blank for no requirement on that skill.
A recipe may require several skills at once. Optional compact ``skills`` column
also works: ``crafting:3;hunting:2``.

Optional ``resource_*`` / ``food_*`` register catalogue entries for new outputs
(icons: ``assets/icons/<icon_key or output key>.png`` / ``.svg``).
Kitchen craft food buffs live in the kitchen CSV ``food_*`` columns — not in
``resource_balance.py`` (that file keeps raw / foraged foods only).

Clothing outputs (tailor / cobbler) use ``walk_speed``, ``capacity_bonus``,
``heat_protection``, ``cold_protection``, and optional ``clothing_slot``
(hat / shirt / trousers / shoes / bag).

Crop produce gather toggles for the forager are appended from ``crops.PRODUCE_KEYS``.
Hunt yields (deer / boar / rabbit meat, hide, fur): ``recipes_data/hunter/recipes.csv``
``outputs`` column. Raw foraged food buffs: ``resource_balance.py``.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from crops import PRODUCE_KEYS
from society import SKILL_ORDER, SkillType

_SKILL_CSV_COLS: tuple[str, ...] = tuple(s.name.lower() for s in SKILL_ORDER)

_RECIPES_DATA_DIR = Path(__file__).resolve().parent / "recipes_data"
RECIPE_REGISTRY_REVISION: int = 0

# Folder name under recipes_data → module attribute holding that building's recipes.
_BUILDING_RECIPE_ATTR: dict[str, str] = {
    "kitchen": "KITCHEN_RECIPES",
    "mill": "MILL_RECIPES",
    "craft_bench": "CRAFT_BENCH_RECIPES",
    "alchemist": "ALCHEMIST_RECIPES",
    "tailor": "TAILOR_RECIPES",
    "cobbler": "COBBLER_RECIPES",
    "forester": "FORESTER_RECIPES",
    "forester_plant": "FORESTER_PLANT_RECIPES",
    "forester_split": "FORESTER_SPLIT_RECIPES",
    "hunter": "HUNTER_RECIPES",
    "forager": "FORAGER_RECIPES",
    "fisher": "FISHER_RECIPES",
    "barn": "BARN_RECIPES",
    "compost_heap": "COMPOST_HEAP_RECIPES",
    "drying_rack": "DRYING_RACK_RECIPES",
}


@dataclass(frozen=True)
class Recipe:
    """Consume ``inputs`` to produce ``outputs`` (gather recipes use empty inputs)."""

    name: str
    inputs: dict[str, int]
    outputs: dict[str, int]
    # Inventory / animal icon key for UI (defaults to first output key).
    icon_key: str | None = None
    # Minimum skill levels required (empty = no skill gate).
    skill_reqs: tuple[tuple[SkillType, int], ...] = ()
    # Optional UI group (e.g. kitchen stews / grill / bakery).
    category: str | None = None
    # Work ticks to finish one craft (CSV ``steps``). 0 = use PROCESSOR_RECIPE_STEPS.
    steps: int = 0

    def display_icon_key(self) -> str:
        if self.icon_key:
            return self.icon_key
        if self.outputs:
            return next(iter(self.outputs))
        return self.name

    def skill_req_map(self) -> dict[SkillType, int]:
        return {skill: level for skill, level in self.skill_reqs}

    @property
    def min_skill(self) -> int:
        """Highest required level across skills (compat / UI summary)."""
        if not self.skill_reqs:
            return 1
        return max(level for _, level in self.skill_reqs)

    def work_steps(self) -> int:
        """How many work ticks complete one craft of this recipe."""
        from settings import PROCESSOR_RECIPE_STEPS

        if int(self.steps) > 0:
            return max(1, int(self.steps))
        return max(1, int(PROCESSOR_RECIPE_STEPS))


MILL_RECIPES: tuple[Recipe, ...] = ()
KITCHEN_RECIPES: tuple[Recipe, ...] = ()
CRAFT_BENCH_RECIPES: tuple[Recipe, ...] = ()
ALCHEMIST_RECIPES: tuple[Recipe, ...] = ()
TAILOR_RECIPES: tuple[Recipe, ...] = ()
COBBLER_RECIPES: tuple[Recipe, ...] = ()
FORESTER_RECIPES: tuple[Recipe, ...] = ()
FORESTER_PLANT_RECIPES: tuple[Recipe, ...] = ()
FORESTER_SPLIT_RECIPES: tuple[Recipe, ...] = ()
HUNTER_RECIPES: tuple[Recipe, ...] = ()
FORAGER_RECIPES: tuple[Recipe, ...] = ()
FISHER_RECIPES: tuple[Recipe, ...] = ()
BARN_RECIPES: tuple[Recipe, ...] = ()
COMPOST_HEAP_RECIPES: tuple[Recipe, ...] = ()
DRYING_RACK_RECIPES: tuple[Recipe, ...] = ()

RECIPE_LABELS: dict[str, str] = {}
# recipe name → category key (from CSV).
RECIPE_CATEGORIES: dict[str, str] = {}
# Display order / labels for kitchen (and other) category keys.
CATEGORY_LABELS: dict[str, str] = {
    "stews": "Stews",
    "grill": "Grill",
    "bakery": "Bakery",
    "sweet": "Sweet",
}

KITCHEN_FUEL_KEY: str = "wood"

# Equipped clothing effects registered from tailor / cobbler CSV rows.
CLOTHING_WALK_MULT: dict[str, float] = {}
CLOTHING_CAPACITY_BONUS: dict[str, int] = {}
CLOTHING_HEAT_PROTECTION: dict[str, float] = {}
CLOTHING_COLD_PROTECTION: dict[str, float] = {}
# Optional CSV overrides for item → slot (merged into entities.CLOTHING_ITEM_SLOT).
CLOTHING_SLOT_FROM_CSV: dict[str, str] = {}


def clothing_walk_mult(key: str) -> float:
    from resource_balance import scale_recipe_mult

    return scale_recipe_mult(float(CLOTHING_WALK_MULT.get(key, 1.0)), "speed")


def clothing_capacity_bonus(key: str) -> int:
    return int(CLOTHING_CAPACITY_BONUS.get(key, 0))


def clothing_heat_protection(key: str) -> float:
    return float(CLOTHING_HEAT_PROTECTION.get(key, 0.0))


def clothing_cold_protection(key: str) -> float:
    return float(CLOTHING_COLD_PROTECTION.get(key, 0.0))


def _parse_amount_map(raw: str) -> dict[str, int]:
    """Parse ``key:qty;key:qty`` into a dict. Empty / whitespace → {}."""
    text = (raw or "").strip()
    if not text:
        return {}
    out: dict[str, int] = {}
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise ValueError(f"Bad amount pair {part!r} (expected key:qty)")
        key, qty = part.split(":", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Empty key in amount pair {part!r}")
        out[key] = int(qty.strip())
    return out


def _clamp_skill_level(raw: str | int) -> int:
    return max(1, min(10, int(raw)))


def _parse_skill_reqs(row: dict[str, str] | dict) -> tuple[tuple[SkillType, int], ...]:
    """Build skill requirements from per-skill columns and/or ``skills`` / ``min_skill``."""
    reqs: dict[SkillType, int] = {}

    # Per-skill columns: extraction, farming, …
    for skill in SKILL_ORDER:
        col = skill.name.lower()
        raw = ""
        if isinstance(row, dict):
            raw = _cell(row, col, f"skill_{col}")  # type: ignore[arg-type]
        if not raw:
            continue
        reqs[skill] = _clamp_skill_level(raw)

    # Compact: skills=crafting:3;hunting:2
    compact = _cell(row, "skills") if isinstance(row, dict) else ""  # type: ignore[arg-type]
    if compact:
        for key, qty in _parse_amount_map(compact).items():
            try:
                skill = SkillType[key.strip().upper()]
            except KeyError as exc:
                raise ValueError(f"Unknown skill {key!r} in skills column") from exc
            reqs[skill] = _clamp_skill_level(qty)

    # Legacy single min_skill → crafting (only if nothing else set).
    if not reqs:
        legacy = _cell(row, "min_skill") if isinstance(row, dict) else ""  # type: ignore[arg-type]
        if legacy and int(legacy) > 1:
            reqs[SkillType.CRAFTING] = _clamp_skill_level(legacy)

    return tuple((skill, reqs[skill]) for skill in SKILL_ORDER if skill in reqs)


def _cell(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        if key in row and row[key] is not None and str(row[key]).strip():
            return str(row[key]).strip()
    return ""


def _recipe_from_row(row: dict[str, str]) -> Recipe:
    name = _cell(row, "name")
    if not name:
        raise ValueError("recipe row missing name")
    inputs = _parse_amount_map(_cell(row, "inputs"))
    outputs = _parse_amount_map(_cell(row, "outputs"))
    icon_raw = _cell(row, "icon_key")
    icon_key = icon_raw or None
    skill_reqs = _parse_skill_reqs(row)
    cat_raw = _cell(row, "category")
    category = cat_raw or None
    steps_raw = _cell(row, "steps", "work_steps")
    steps = max(0, int(float(steps_raw))) if steps_raw else 0
    return Recipe(
        name,
        inputs,
        outputs,
        icon_key=icon_key,
        skill_reqs=skill_reqs,
        category=category,
        steps=steps,
    )


def _apply_row_metadata(row: dict[str, str], recipe: Recipe) -> None:
    """Register labels, resource catalogue, and food defs from optional CSV fields."""
    label = _cell(row, "label")
    if label:
        RECIPE_LABELS[recipe.name] = label
    if recipe.category:
        RECIPE_CATEGORIES[recipe.name] = recipe.category
        # Remember unknown category labels as title-cased keys.
        if recipe.category not in CATEGORY_LABELS:
            CATEGORY_LABELS[recipe.category] = recipe.category.replace("_", " ").title()

    satiation = _cell(row, "food_satiation")
    resource_group = _cell(row, "resource_group")
    # Food metadata implies a catalogue entry even if resource_group was left blank.
    if not resource_group and satiation and recipe.outputs:
        resource_group = "food"
    if resource_group and recipe.outputs:
        from resources import register_resource

        out_key = next(iter(recipe.outputs))
        register_resource(
            out_key,
            label=label or RECIPE_LABELS.get(recipe.name) or out_key,
            group=resource_group,
            short=_cell(row, "resource_short") or out_key[:4],
        )

    if satiation and recipe.outputs:
        from resource_balance import register_food, register_sweet_food

        out_key = next(iter(recipe.outputs))
        edible_raw = _cell(row, "food_edible").lower()
        edible = edible_raw not in ("0", "false", "no") if edible_raw else True
        register_food(
            out_key,
            satiation=float(satiation),
            walk_speed=float(_cell(row, "food_walk_speed") or "1.0"),
            work_efficiency=float(_cell(row, "food_work_efficiency") or "1.0"),
            hunger_rate=float(_cell(row, "food_hunger_rate") or "1.0"),
            edible=edible,
        )
        if (recipe.category or "").lower() == "sweet":
            register_sweet_food(out_key)

    _register_clothing_effects(row, recipe)


def _register_clothing_effects(row: dict[str, str], recipe: Recipe) -> None:
    """Apply optional clothing effect columns onto the primary output key."""
    if not recipe.outputs:
        return
    out_key = next(iter(recipe.outputs))
    slot = _cell(row, "clothing_slot", "slot").lower()
    if slot:
        CLOTHING_SLOT_FROM_CSV[out_key] = slot

    walk_raw = _cell(row, "walk_speed", "gear_walk_speed")
    if walk_raw:
        CLOTHING_WALK_MULT[out_key] = float(walk_raw)

    cap_raw = _cell(row, "capacity_bonus", "gear_capacity")
    if cap_raw:
        CLOTHING_CAPACITY_BONUS[out_key] = int(float(cap_raw))

    heat_raw = _cell(row, "heat_protection")
    if heat_raw:
        CLOTHING_HEAT_PROTECTION[out_key] = float(heat_raw)

    cold_raw = _cell(row, "cold_protection")
    if cold_raw:
        CLOTHING_COLD_PROTECTION[out_key] = float(cold_raw)


def _recipe_from_json(data: dict) -> Recipe:
    name = str(data["name"])
    inputs = {str(k): int(v) for k, v in dict(data.get("inputs") or {}).items()}
    outputs = {str(k): int(v) for k, v in dict(data.get("outputs") or {}).items()}
    icon_key = data.get("icon_key")
    if icon_key is not None:
        icon_key = str(icon_key)
    skill_reqs: list[tuple[SkillType, int]] = []
    raw_skills = data.get("skills") or data.get("skill_reqs")
    if isinstance(raw_skills, dict):
        for key, level in raw_skills.items():
            try:
                skill = SkillType[str(key).strip().upper()]
            except KeyError as exc:
                raise ValueError(f"Unknown skill {key!r} in recipe JSON") from exc
            skill_reqs.append((skill, _clamp_skill_level(level)))
        skill_reqs.sort(key=lambda pair: SKILL_ORDER.index(pair[0]))
    elif not skill_reqs:
        # Flat per-skill keys or legacy min_skill.
        flat = {k: str(v) for k, v in data.items() if isinstance(v, (int, float, str))}
        skill_reqs = list(_parse_skill_reqs(flat))
    cat = data.get("category")
    category = str(cat) if cat else None
    steps_raw = data.get("steps", data.get("work_steps"))
    steps = max(0, int(steps_raw)) if steps_raw is not None and str(steps_raw).strip() else 0
    return Recipe(
        name,
        inputs,
        outputs,
        icon_key=icon_key,
        skill_reqs=tuple(skill_reqs),
        category=category,
        steps=steps,
    )


def _apply_json_metadata(data: dict, recipe: Recipe) -> None:
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


def _load_building_csv(folder: Path, existing: list[Recipe], seen: set[str]) -> None:
    path = folder / "recipes.csv"
    if not path.is_file():
        return
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if not row or not _cell(row, "name"):
                continue
            try:
                recipe = _recipe_from_row(row)
            except (ValueError, KeyError) as exc:
                print(f"Skipping bad recipe row in {path}: {exc}")
                continue
            if recipe.name in seen:
                continue
            existing.append(recipe)
            seen.add(recipe.name)
            _apply_row_metadata(row, recipe)


def _load_building_json(folder: Path, existing: list[Recipe], seen: set[str]) -> None:
    """Legacy: merge ``*.json`` if still present (CSV is preferred)."""
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
        _apply_json_metadata(data, recipe)


def _append_forager_crop_produce(existing: list[Recipe], seen: set[str]) -> None:
    for key in PRODUCE_KEYS:
        if key in seen:
            continue
        existing.append(Recipe(key, {}, {key: 1}))
        seen.add(key)


def _load_directory_recipes() -> None:
    """Load ``recipes_data/<building>/recipes.csv`` (and legacy ``*.json``) into tuples."""
    global MILL_RECIPES, KITCHEN_RECIPES, CRAFT_BENCH_RECIPES, ALCHEMIST_RECIPES
    global TAILOR_RECIPES, COBBLER_RECIPES
    global FORESTER_RECIPES, FORESTER_PLANT_RECIPES, FORESTER_SPLIT_RECIPES
    global HUNTER_RECIPES, FORAGER_RECIPES, FISHER_RECIPES
    global BARN_RECIPES, COMPOST_HEAP_RECIPES, DRYING_RACK_RECIPES

    if not _RECIPES_DATA_DIR.is_dir():
        return

    g = globals()
    for building, attr in _BUILDING_RECIPE_ATTR.items():
        folder = _RECIPES_DATA_DIR / building
        existing: list[Recipe] = list(g[attr])
        seen = {r.name for r in existing}
        if folder.is_dir():
            _load_building_csv(folder, existing, seen)
            _load_building_json(folder, existing, seen)
        if building == "forager":
            _append_forager_crop_produce(existing, seen)
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
ALCHEMIST_INPUT_KEYS: tuple[str, ...] = input_keys_for_recipes(ALCHEMIST_RECIPES)
ALCHEMIST_OUTPUT_KEYS: tuple[str, ...] = output_keys_for_recipes(ALCHEMIST_RECIPES)
TAILOR_INPUT_KEYS: tuple[str, ...] = input_keys_for_recipes(TAILOR_RECIPES)
TAILOR_OUTPUT_KEYS: tuple[str, ...] = output_keys_for_recipes(TAILOR_RECIPES)
COBBLER_INPUT_KEYS: tuple[str, ...] = input_keys_for_recipes(COBBLER_RECIPES)
COBBLER_OUTPUT_KEYS: tuple[str, ...] = output_keys_for_recipes(COBBLER_RECIPES)
KITCHEN_INPUT_KEYS: tuple[str, ...] = input_keys_for_recipes(KITCHEN_RECIPES)
KITCHEN_OUTPUT_KEYS: tuple[str, ...] = output_keys_for_recipes(KITCHEN_RECIPES)

# All crafted / milled goods stored as cargo.
PROCESSED_KEYS: tuple[str, ...] = tuple(
    dict.fromkeys(
        (
            *MILL_OUTPUT_KEYS,
            *KITCHEN_OUTPUT_KEYS,
            *CRAFT_BENCH_OUTPUT_KEYS,
            *ALCHEMIST_OUTPUT_KEYS,
            *TAILOR_OUTPUT_KEYS,
            *COBBLER_OUTPUT_KEYS,
            *output_keys_for_recipes(FISHER_RECIPES),
            *output_keys_for_recipes(COMPOST_HEAP_RECIPES),
            "spoilage",
        )
    )
)


def rebuild_recipe_derived_keys() -> None:
    """Refresh module-level key summaries after a validated definitions reload."""
    global MILL_INPUT_KEYS, MILL_OUTPUT_KEYS, CRAFT_BENCH_INPUT_KEYS
    global CRAFT_BENCH_OUTPUT_KEYS, ALCHEMIST_INPUT_KEYS, ALCHEMIST_OUTPUT_KEYS
    global TAILOR_INPUT_KEYS, TAILOR_OUTPUT_KEYS, COBBLER_INPUT_KEYS, COBBLER_OUTPUT_KEYS
    global KITCHEN_INPUT_KEYS, KITCHEN_OUTPUT_KEYS, PROCESSED_KEYS
    MILL_INPUT_KEYS = input_keys_for_recipes(MILL_RECIPES)
    MILL_OUTPUT_KEYS = output_keys_for_recipes(MILL_RECIPES)
    CRAFT_BENCH_INPUT_KEYS = input_keys_for_recipes(CRAFT_BENCH_RECIPES)
    CRAFT_BENCH_OUTPUT_KEYS = output_keys_for_recipes(CRAFT_BENCH_RECIPES)
    ALCHEMIST_INPUT_KEYS = input_keys_for_recipes(ALCHEMIST_RECIPES)
    ALCHEMIST_OUTPUT_KEYS = output_keys_for_recipes(ALCHEMIST_RECIPES)
    TAILOR_INPUT_KEYS = input_keys_for_recipes(TAILOR_RECIPES)
    TAILOR_OUTPUT_KEYS = output_keys_for_recipes(TAILOR_RECIPES)
    COBBLER_INPUT_KEYS = input_keys_for_recipes(COBBLER_RECIPES)
    COBBLER_OUTPUT_KEYS = output_keys_for_recipes(COBBLER_RECIPES)
    KITCHEN_INPUT_KEYS = input_keys_for_recipes(KITCHEN_RECIPES)
    KITCHEN_OUTPUT_KEYS = output_keys_for_recipes(KITCHEN_RECIPES)
    PROCESSED_KEYS = tuple(dict.fromkeys((*MILL_OUTPUT_KEYS, *KITCHEN_OUTPUT_KEYS,
        *CRAFT_BENCH_OUTPUT_KEYS, *ALCHEMIST_OUTPUT_KEYS, *TAILOR_OUTPUT_KEYS,
        *COBBLER_OUTPUT_KEYS, *output_keys_for_recipes(FISHER_RECIPES),
        *output_keys_for_recipes(COMPOST_HEAP_RECIPES), "spoilage")))


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
    amount = getattr(storage, "recipe_storage_amount", None)
    return all(
        int(amount(key) if callable(amount) else getattr(storage, key, 0)) >= n
        for key, n in recipe.inputs.items()
    )


def recipe_ready_with_extra(
    storage: object, recipe: Recipe, extra: object | None
) -> bool:
    """True if storage + optional extra inventory cover recipe inputs."""
    if extra is None:
        return recipe_ready(storage, recipe)
    amount = getattr(storage, "recipe_storage_amount", None)
    for key, n in recipe.inputs.items():
        stored = amount(key) if callable(amount) else getattr(storage, key, 0)
        have = int(stored) + int(getattr(extra, key, 0))
        if have < int(n):
            return False
    return True


def recipe_output_fits(
    storage: object,
    recipe: Recipe,
    *,
    capacity: int | None = None,
    output_capacity: int | None = None,
    output_keys: tuple[str, ...] | None = None,
    stock_amounts: dict[str, int] | None = None,
) -> bool:
    from resources import cargo_units_after_add, stack_units

    if output_capacity is not None and output_keys is not None:
        out_stored = sum(
            stack_units(key, int(getattr(storage, key, 0))) for key in output_keys
        )
        added = 0
        for key, n in recipe.outputs.items():
            if key not in output_keys:
                continue
            have = int(getattr(storage, key, 0))
            added += cargo_units_after_add(key, have, n)
        if out_stored + added > output_capacity:
            return False
    elif capacity is not None:
        stored = int(getattr(storage, "stored_total", 0))
        # Net cargo change after consuming inputs and adding outputs.
        delta = 0
        for key, n in recipe.inputs.items():
            have = int(getattr(storage, key, 0))
            delta += stack_units(key, have - n) - stack_units(key, have)
        for key, n in recipe.outputs.items():
            have = int(getattr(storage, key, 0))
            delta += cargo_units_after_add(key, have, n)
        if stored + delta > capacity:
            return False
    # Per-item caps (Building.item_caps). When ``stock_amounts`` is provided
    # (village-wide totals matching the Sto: UI), enforce Max against that.
    caps = getattr(storage, "item_caps", None)
    if isinstance(caps, dict) and caps:
        for key, n in recipe.outputs.items():
            cap = caps.get(key)
            if cap is None:
                continue
            if stock_amounts is not None:
                have = int(stock_amounts.get(key, 0))
            else:
                have = int(getattr(storage, key, 0))
            if have + n > int(cap):
                return False
    return True


def recipes_by_category(
    recipes: tuple[Recipe, ...] | list[Recipe],
) -> list[tuple[str | None, list[Recipe]]]:
    """Group recipes into (category_key, recipes) preserving first-seen order.

    Recipes without a category are returned under ``None``.
    """
    order: list[str | None] = []
    groups: dict[str | None, list[Recipe]] = {}
    for recipe in recipes:
        cat = recipe.category or RECIPE_CATEGORIES.get(recipe.name)
        if cat not in groups:
            groups[cat] = []
            order.append(cat)
        groups[cat].append(recipe)
    # Prefer known CATEGORY_LABELS order, then remaining.
    preferred = [c for c in CATEGORY_LABELS if c in groups]
    rest = [c for c in order if c not in preferred]
    ordered_keys = preferred + rest
    return [(key, groups[key]) for key in ordered_keys]


def category_label(key: str | None) -> str:
    if key is None:
        return "Other"
    return CATEGORY_LABELS.get(key, key.replace("_", " ").title())


def can_craft(
    storage: object,
    recipes: tuple[Recipe, ...],
    *,
    capacity: int | None = None,
    output_capacity: int | None = None,
    output_keys: tuple[str, ...] | None = None,
    stock_amounts: dict[str, int] | None = None,
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
            stock_amounts=stock_amounts,
        ):
            return recipe
    return None


def apply_recipe(storage: object, recipe: Recipe) -> None:
    from food_spoilage import on_food_removed

    for key, n in recipe.inputs.items():
        consume = getattr(storage, "consume_recipe_item", None)
        if callable(consume):
            consume(str(key), int(n))
        else:
            setattr(storage, key, int(getattr(storage, key, 0)) - n)
            on_food_removed(storage, str(key))
    apply_recipe_outputs(storage, recipe)


def apply_recipe_outputs(storage: object, recipe: Recipe) -> None:
    from food_spoilage import on_food_merged

    for key, n in recipe.outputs.items():
        key_s = str(key)
        amount = int(n)
        recipe_add = getattr(storage, "add_recipe_output", None)
        if callable(recipe_add):
            recipe_add(key_s, amount)
            continue
        add_item = getattr(storage, "add_item", None)
        if callable(add_item):
            add_item(key_s, amount)
            continue
        before = int(getattr(storage, key_s, 0) or 0)
        setattr(storage, key_s, before + amount)
        on_food_merged(
            storage,
            key_s,
            amount_before=before,
            amount_added=amount,
            src_quality=1.0,
        )


def recipe_outputs_fit(storage: object, recipe: Recipe) -> bool:
    can_add = getattr(storage, "can_add", None)
    if not callable(can_add):
        return True
    for key, n in recipe.outputs.items():
        if not can_add(int(n), key=str(key)):
            return False
    return True


def hunt_recipe(name: str) -> Recipe | None:
    """Gather recipe for ``deer``, ``boar``, or ``rabbit`` (hunter CSV outputs)."""
    key = str(name).lower()
    for recipe in HUNTER_RECIPES:
        if recipe.name == key:
            return recipe
    return None


def hunt_recipe_outputs(name: str) -> dict[str, int]:
    recipe = hunt_recipe(name)
    return dict(recipe.outputs) if recipe is not None else {}


def missing_inputs(storage: object, recipe: Recipe) -> dict[str, int]:
    need: dict[str, int] = {}
    for key, n in recipe.inputs.items():
        amount = getattr(storage, "recipe_storage_amount", None)
        have = int(amount(key) if callable(amount) else getattr(storage, key, 0))
        if have < n:
            need[key] = n - have
    return need
