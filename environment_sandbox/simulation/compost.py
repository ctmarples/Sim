"""Compost operations on existing building and storage state.

No clock, renderer or Game object is owned here. Callers decide when to perform
work or seasonal conversion. Accounting callbacks run synchronously at the old
mutation points, preserving history and work/stock cache invalidation. The
surplus callback supplies the existing shared storehouse reserve policy.

Building lookup follows stable parent IDs and preserves collection order.
"""

from __future__ import annotations

from collections.abc import Callable

from entities import Building, BuildingKind, HomeStorage
from recipes import Recipe


def linked_compost_heap(
    farm: Building, buildings: dict[int, Building]
) -> Building | None:
    """Completed compost-heap annex for this farm, if any."""
    if farm.kind != BuildingKind.FARM:
        return None
    from extensions import linked_extensions

    return next(
        (b for b in linked_extensions(farm, buildings) if b.kind == BuildingKind.COMPOST_HEAP),
        None,
    )


def migrate_spoilage_to_heap(farm: Building, buildings: dict[int, Building]) -> None:
    """Move farm-tray spoilage into the linked compost heap."""
    heap = linked_compost_heap(farm, buildings)
    if heap is None:
        return
    while int(getattr(farm, "spoilage", 0) or 0) > 0 and heap.space_for_key(
        "spoilage"
    ) > 0:
        farm.spoilage = int(farm.spoilage) - 1
        heap.spoilage = int(getattr(heap, "spoilage", 0) or 0) + 1


def compost_input_have(farm: Building, key: str, buildings: dict[int, Building]) -> int:
    heap = linked_compost_heap(farm, buildings)
    total = int(getattr(farm, key, 0) or 0)
    if heap is not None:
        total += int(getattr(heap, key, 0) or 0)
    return total


def compost_recipe_ready(
    farm: Building, recipe: Recipe, buildings: dict[int, Building]
) -> bool:
    migrate_spoilage_to_heap(farm, buildings)
    return all(
        compost_input_have(farm, key, buildings) >= int(need)
        for key, need in recipe.inputs.items()
    )


def apply_compost_recipe(
    farm: Building,
    recipe: Recipe,
    buildings: dict[int, Building],
    *,
    record_consumed: Callable[[str, int], None],
    record_produced: Callable[[str, int], None],
) -> None:
    """Consume spoilage / produce compost on the linked heap."""
    heap = linked_compost_heap(farm, buildings)
    if heap is None:
        return
    migrate_spoilage_to_heap(farm, buildings)
    for key, need in recipe.inputs.items():
        left = int(need)
        take_farm = min(left, int(getattr(farm, key, 0) or 0))
        if take_farm:
            setattr(farm, key, int(getattr(farm, key, 0) or 0) - take_farm)
            left -= take_farm
        if left > 0:
            take_heap = min(left, int(getattr(heap, key, 0) or 0))
            if take_heap:
                setattr(heap, key, int(getattr(heap, key, 0) or 0) - take_heap)
                left -= take_heap
        record_consumed(key, int(need) - left)
    for key, n in recipe.outputs.items():
        before = int(getattr(heap, key, 0) or 0)
        setattr(heap, key, before + int(n))
        record_produced(key, int(n))


def pull_compost_food_from_storehouse(
    heap: Building,
    home_storage: HomeStorage,
    *,
    storehouse_surplus: Callable[[str, int], int],
) -> int:
    """Move enabled food surplus from the storehouse onto the heap up to caps."""
    from food_spoilage import on_food_merged, on_food_removed

    moved = 0
    for key in list(heap.compost_food_mins):
        surplus = storehouse_surplus(key, heap.compost_food_reserve(key))
        if surplus <= 0:
            continue
        have = int(getattr(heap, key, 0) or 0)
        target = heap.compost_food_target(key)
        want = max(0, target - have)
        room = heap.space_for_key(key)
        take = min(surplus, want, room)
        if take <= 0:
            continue
        store_before = int(getattr(home_storage, key, 0) or 0)
        setattr(home_storage, key, store_before - take)
        on_food_removed(home_storage, key)
        heap_before = have
        setattr(heap, key, heap_before + take)
        on_food_merged(
            heap,
            key,
            amount_before=heap_before,
            amount_added=take,
            src_quality=1.0,
        )
        moved += take
    return moved


def convert_seasonal_compost(
    buildings: dict[int, Building],
    home_storage: HomeStorage,
    *,
    storehouse_surplus: Callable[[str, int], int],
    record_consumed: Callable[[str, int], None],
    record_produced: Callable[[str, int], None],
) -> int:
    """Convert complete batches physically stored in enabled compost heaps.

    Spoilage and player-enabled food on the heap both count toward the
    compost recipe input ratio (default 10→1).
    """
    made = 0
    for farm in buildings.values():
        if farm.kind != BuildingKind.FARM:
            continue
        recipe = next(
            (r for r in farm.addon_craft_recipes() if "compost" in r.outputs),
            None,
        )
        heap = linked_compost_heap(farm, buildings)
        if recipe is None or heap is None or not farm.is_recipe_enabled(recipe.name):
            continue
        migrate_spoilage_to_heap(farm, buildings)
        pull_compost_food_from_storehouse(
            heap, home_storage, storehouse_surplus=storehouse_surplus
        )
        need = max(1, int(recipe.inputs.get("spoilage", 10)))
        out = max(1, int(recipe.outputs.get("compost", 1)))
        food_pool = sum(
            int(getattr(heap, key, 0) or 0) for key in heap.compost_food_mins
        )
        pool = int(getattr(heap, "spoilage", 0) or 0) + food_pool
        batches = pool // need
        if batches <= 0:
            continue
        left = batches * need
        take_spoil = min(int(getattr(heap, "spoilage", 0) or 0), left)
        if take_spoil:
            heap.spoilage -= take_spoil
            left -= take_spoil
            record_consumed("spoilage", take_spoil)
        if left > 0:
            from food_spoilage import on_food_removed

            for key in list(heap.compost_food_mins):
                if left <= 0:
                    break
                have = int(getattr(heap, key, 0) or 0)
                take = min(have, left)
                if take <= 0:
                    continue
                setattr(heap, key, have - take)
                on_food_removed(heap, key)
                record_consumed(key, take)
                left -= take
        produced = batches * out
        heap.compost += produced
        record_produced("compost", produced)
        made += produced
    return made
