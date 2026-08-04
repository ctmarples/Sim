"""Resource catalogue: keys, labels, and display groups.

Add new resources here so inventory UI and totals stay consistent.
"""

from __future__ import annotations

from dataclasses import dataclass

from crops import CROPS
from trees import TREES


@dataclass(frozen=True)
class ResourceDef:
    key: str
    label: str
    group: str
    short: str


# Display order within each group follows this list order.
# Onion / cabbage / carrot are edible produce (food); other crops stay wares.
_FOOD_CROP_KEYS = frozenset({"onion", "cabbage", "carrot"})
_CROP_PRODUCE_FOOD = tuple(
    ResourceDef(c.produce_key, c.label, "food", c.short)
    for c in CROPS
    if c.key in _FOOD_CROP_KEYS
)
_CROP_PRODUCE_WARES = tuple(
    ResourceDef(c.produce_key, c.label, "wares", c.short)
    for c in CROPS
    if c.key not in _FOOD_CROP_KEYS
)
_CROP_SEEDS = tuple(
    ResourceDef(c.seed_key, f"{c.label} seeds", "agriculture", f"{c.short}.s")
    for c in CROPS
)
_TREE_SAPLINGS = tuple(
    ResourceDef(f"{t.key}_saplings", f"{t.label} saplings", "agriculture", f"{t.short}.p")
    for t in TREES
)

RESOURCES: tuple[ResourceDef, ...] = (
    ResourceDef("meat", "Meat", "food", "meat"),
    ResourceDef("fish", "Fish", "food", "fish"),
    ResourceDef("berries", "Berries", "food", "berr"),
    ResourceDef("mushrooms", "Mushrooms", "food", "mush"),
    *_CROP_PRODUCE_FOOD,
    ResourceDef("wood", "Wood", "wares", "wood"),
    ResourceDef("hardwood", "Hardwood", "wares", "hwood"),
    ResourceDef("rock", "Rock", "wares", "rock"),
    ResourceDef("reeds", "Reeds", "wares", "reed"),
    *_CROP_PRODUCE_WARES,
    *_TREE_SAPLINGS,
    ResourceDef("berry_seeds", "Berry seeds", "agriculture", "b.sd"),
    *_CROP_SEEDS,
)

GROUP_ORDER: tuple[str, ...] = ("food", "wares", "agriculture")
GROUP_LABELS: dict[str, str] = {
    "food": "Food",
    "wares": "Wares",
    "agriculture": "Agriculture",
    "construction": "Wares",
}

RESOURCE_KEYS: tuple[str, ...] = tuple(r.key for r in RESOURCES)


def resources_by_group() -> list[tuple[str, list[ResourceDef]]]:
    grouped: dict[str, list[ResourceDef]] = {g: [] for g in GROUP_ORDER}
    for res in RESOURCES:
        grouped.setdefault(res.group, []).append(res)
    return [(g, grouped[g]) for g in GROUP_ORDER if grouped.get(g)]


def format_grouped_counts(amounts: dict[str, int], *, skip_zero: bool = False) -> list[str]:
    """Return lines like 'Food: 2 meat, 1 fish' for UI panels."""
    lines: list[str] = []
    for group, defs in resources_by_group():
        parts: list[str] = []
        for res in defs:
            n = int(amounts.get(res.key, 0))
            if skip_zero and n <= 0:
                continue
            parts.append(f"{n} {res.short}")
        if parts:
            lines.append(f"{GROUP_LABELS.get(group, group)}: " + ", ".join(parts))
        elif not skip_zero:
            lines.append(f"{GROUP_LABELS.get(group, group)}: —")
    return lines


def resource_label(key: str) -> str:
    for res in RESOURCES:
        if res.key == key:
            return res.label
    return key


def resource_icon(key: str) -> str:
    """Map an inventory resource key to an ``icons`` base name for UI grids."""
    from icons import (
        ICON_BERRY_BUSH,
        ICON_CROP,
        ICON_FISH,
        ICON_FLOWER,
        ICON_MEAT_MARKER,
        ICON_MUSHROOM,
        ICON_REED,
        ICON_ROCK,
        ICON_SAPLING_CONE,
        ICON_SAPLING_ROUND,
        ICON_TREE_CONE,
        ICON_TREE_ROUND,
        crop_icon_base,
    )
    from trees import TREES

    static = {
        "wood": ICON_TREE_ROUND,
        "hardwood": ICON_TREE_CONE,
        "rock": ICON_ROCK,
        "meat": ICON_MEAT_MARKER,
        "fish": ICON_FISH,
        "mushrooms": ICON_MUSHROOM,
        "berries": ICON_BERRY_BUSH,
        "berry_seeds": ICON_BERRY_BUSH,
        "reeds": ICON_REED,
    }
    if key in static:
        return static[key]
    for tree in TREES:
        sap = f"{tree.key}_saplings"
        if key == sap:
            return ICON_SAPLING_CONE if tree.shape == "cone" else ICON_SAPLING_ROUND
    if key.endswith("_seeds"):
        crop_key = key[: -len("_seeds")]
        try:
            return crop_icon_base(crop_key, dense=False)
        except Exception:
            return ICON_CROP
    # Crop produce keys match crop.key.
    try:
        return crop_icon_base(key, dense=True)
    except Exception:
        return ICON_FLOWER


def amounts_from_obj(obj: object) -> dict[str, int]:
    return {key: int(getattr(obj, key, 0)) for key in RESOURCE_KEYS}


def merge_amounts(*dicts: dict[str, int]) -> dict[str, int]:
    totals = {key: 0 for key in RESOURCE_KEYS}
    for data in dicts:
        for key in RESOURCE_KEYS:
            totals[key] += int(data.get(key, 0))
    return totals


def group_totals(amounts: dict[str, int]) -> dict[str, int]:
    totals = {group: 0 for group in GROUP_ORDER}
    for res in RESOURCES:
        totals[res.group] = totals.get(res.group, 0) + int(amounts.get(res.key, 0))
    return totals
