"""Read-only resource-reference view model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceEntry:
    key: str
    label: str
    group: str
    short: str
    icon: str
    food: bool
    edible: bool
    source: str


def resource_entries(search: str = "") -> list[ResourceEntry]:
    from resource_balance import FOOD_BY_KEY, VILLAGER_FOOD_KEYS
    from resources import RESOURCES, resource_icon

    needle = search.casefold().strip(); result = []
    for item in RESOURCES:
        if needle and needle not in f"{item.key} {item.label} {item.group}".casefold(): continue
        source = "crops.py (derived)" if item.key.endswith("_seeds") else "resources.py / recipe metadata"
        result.append(ResourceEntry(item.key, item.label, item.group, item.short, resource_icon(item.key), item.key in FOOD_BY_KEY, item.key in VILLAGER_FOOD_KEYS, source))
    return result
