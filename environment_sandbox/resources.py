"""Resource catalogue: keys, labels, and display groups.

Add new resources here so inventory UI and totals stay consistent.
"""

from __future__ import annotations

from dataclasses import dataclass

from crops import CROPS


@dataclass(frozen=True)
class ResourceDef:
    key: str
    label: str
    group: str
    short: str


# Display order within each group follows this list order.
_CROP_PRODUCE = tuple(
    ResourceDef(c.produce_key, c.label, "wares", c.short) for c in CROPS
)
_CROP_SEEDS = tuple(
    ResourceDef(c.seed_key, f"{c.label} seeds", "agriculture", f"{c.short}.s")
    for c in CROPS
)

RESOURCES: tuple[ResourceDef, ...] = (
    ResourceDef("meat", "Meat", "food", "meat"),
    ResourceDef("fish", "Fish", "food", "fish"),
    ResourceDef("berries", "Berries", "food", "berr"),
    ResourceDef("mushrooms", "Mushrooms", "food", "mush"),
    ResourceDef("wood", "Wood", "wares", "wood"),
    ResourceDef("rock", "Rock", "wares", "rock"),
    *_CROP_PRODUCE,
    ResourceDef("saplings", "Saplings", "agriculture", "sapl"),
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
