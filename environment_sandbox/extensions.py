"""Building extensions: 1×1 annexes attached to a parent workplace.

Barn → Farm, Pantry → Kitchen, Drying rack → Hunter.
"""

from __future__ import annotations

from entities import Building, BuildingKind
from settings import BuildingStorageSpec, building_storage_spec

# Extension kind → required parent kind.
EXTENSION_PARENT: dict[BuildingKind, BuildingKind] = {
    BuildingKind.BARN: BuildingKind.FARM,
    BuildingKind.COMPOST_HEAP: BuildingKind.FARM,
    BuildingKind.PANTRY: BuildingKind.KITCHEN,
    BuildingKind.CELLAR: BuildingKind.KITCHEN,
    BuildingKind.DRYING_RACK: BuildingKind.HUNTER,
}

EXTENSION_KINDS: frozenset[BuildingKind] = frozenset(EXTENSION_PARENT)

# Parent kind → available extension kinds (menu order).
EXTENSIONS_FOR_PARENT: dict[BuildingKind, tuple[BuildingKind, ...]] = {
    BuildingKind.FARM: (BuildingKind.BARN, BuildingKind.COMPOST_HEAP),
    BuildingKind.KITCHEN: (BuildingKind.PANTRY, BuildingKind.CELLAR),
    BuildingKind.HUNTER: (BuildingKind.DRYING_RACK,),
}

EXTENSION_LABELS: dict[BuildingKind, str] = {
    BuildingKind.BARN: "Barn",
    BuildingKind.COMPOST_HEAP: "Compost heap",
    BuildingKind.PANTRY: "Pantry",
    BuildingKind.CELLAR: "Cellar",
    BuildingKind.DRYING_RACK: "Drying rack",
}


def is_extension_kind(kind: BuildingKind) -> bool:
    return kind in EXTENSION_KINDS


def extension_parent_kind(kind: BuildingKind) -> BuildingKind | None:
    return EXTENSION_PARENT.get(kind)


def extensions_for_parent(kind: BuildingKind) -> tuple[BuildingKind, ...]:
    return EXTENSIONS_FOR_PARENT.get(kind, ())


def linked_extensions(
    parent: Building, buildings: dict[int, Building]
) -> list[Building]:
    """Completed extensions whose ``parent_building_id`` points at ``parent``."""
    return [
        b
        for b in buildings.values()
        if is_extension_kind(b.kind) and b.parent_building_id == parent.id
    ]


def has_extension(
    parent: Building, buildings: dict[int, Building], kind: BuildingKind
) -> bool:
    return any(b.kind == kind for b in linked_extensions(parent, buildings))


def extension_or_site_claimed(
    parent_id: int,
    kind: BuildingKind,
    buildings: dict[int, Building],
    sites: dict[int, object],
) -> bool:
    """True if this parent already has this extension built or under construction."""
    for b in buildings.values():
        if b.kind == kind and b.parent_building_id == parent_id:
            return True
    for site in sites.values():
        if getattr(site, "kind", None) == kind and getattr(
            site, "parent_building_id", None
        ) == parent_id:
            return True
    return False


def refresh_parent_extension_links(buildings: dict[int, Building]) -> None:
    """Sync ``linked_extensions`` sets on parents from completed annexes."""
    for b in buildings.values():
        b.linked_extensions = frozenset()
        b._pantry_storage = None
        b._food_storages = ()
    for b in buildings.values():
        if not is_extension_kind(b.kind) or b.parent_building_id is None:
            continue
        parent = buildings.get(b.parent_building_id)
        if parent is None:
            continue
        parent.linked_extensions = frozenset(parent.linked_extensions | {b.kind})
        if b.kind in (BuildingKind.PANTRY, BuildingKind.CELLAR):
            parent._food_storages = (*parent._food_storages, b)
            if parent._pantry_storage is None:
                parent._pantry_storage = b
        parent._recipe_state_ready = False
        parent._invalidate_recipe_policy()


def apply_extension_storage_boosts(buildings: dict[int, Building]) -> None:
    """Reset parent storage to base + sum of attached extension bonuses."""
    from entities import apply_building_storage

    refresh_parent_extension_links(buildings)
    # Reset every non-extension first so demolishing an annex drops the boost.
    for b in buildings.values():
        if is_extension_kind(b.kind):
            continue
        apply_building_storage(b)
    for parent in buildings.values():
        if not parent.linked_extensions:
            continue
        for ext_kind in parent.linked_extensions:
            if ext_kind in (
                BuildingKind.PANTRY,
                BuildingKind.CELLAR,
                BuildingKind.COMPOST_HEAP,
            ):
                # These extensions have real separate inventory stores.
                continue
            bonus = building_storage_spec(ext_kind.name)
            parent.capacity += bonus.capacity
            parent.input_capacity += bonus.input_capacity
            parent.output_capacity += bonus.output_capacity
            parent.fuel_capacity += bonus.fuel_capacity
            parent.seed_capacity += bonus.seed_capacity
    migrate_kitchen_food_to_pantries(buildings)


def migrate_kitchen_food_to_pantries(buildings: dict[int, Building]) -> None:
    """Move legacy/local kitchen food into its pantry without losing quality."""
    from food_spoilage import food_quality, on_food_merged, on_food_removed

    for kitchen in buildings.values():
        if kitchen.kind != BuildingKind.KITCHEN:
            continue
        storages = kitchen.linked_food_storages()
        if not storages:
            continue
        for key in kitchen.pantry_storage_keys():
            have = int(getattr(kitchen, key, 0) or 0)
            quality = food_quality(kitchen, key)
            for pantry in storages:
                move = min(have, pantry.space_for_key(key))
                if move <= 0:
                    continue
                before = int(getattr(pantry, key, 0) or 0)
                have -= move
                setattr(kitchen, key, have)
                on_food_removed(kitchen, key)
                setattr(pantry, key, before + move)
                on_food_merged(pantry, key, amount_before=before, amount_added=move, src_quality=quality)
                if have <= 0:
                    break


def footprints_orthogonally_adjacent(
    a_cells: set[tuple[int, int]], b_cells: set[tuple[int, int]]
) -> bool:
    for x, y in a_cells:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if (x + dx, y + dy) in b_cells:
                return True
    return False
