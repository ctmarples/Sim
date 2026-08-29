"""Normalized 3x3 visual footprints for resources inside ecology cells."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ObjectFootprint:
    """Single source of truth for an object's subcell presentation and collision."""

    slots: int
    centre_u: float
    centre_v: float
    occupied_slots: frozenset[int]
    hard_slots: frozenset[int]
    family: str
    max_per_cell: int
    floor_layer: bool

    @property
    def scale(self) -> float:
        return footprint_scale(self.slots)


def stable_anchor_slot(x: int, y: int, variant: int = 1) -> int:
    """Return a deterministic 0..8 hard-anchor slot for an object."""
    return (x * 17 + y * 31 + max(1, int(variant)) * 7) % 9


def stable_drop_slot(x: int, y: int, kind: str) -> int:
    """Stable starting slot for loose drops without pretending they are objects."""
    salt = sum(ord(char) for char in str(kind).upper())
    return (x * 23 + y * 37 + salt) % 9


def slot_centre(slot: int) -> tuple[float, float]:
    slot = max(0, min(8, int(slot)))
    return (slot % 3 + 0.5) / 3.0, (slot // 3 + 0.5) / 3.0


def _two_by_two_centre(slot: int, x: int, y: int) -> tuple[float, float]:
    """Place the hard anchor in one of an aligned 2x2 footprint's slots."""
    slot = max(0, min(8, int(slot)))
    u, v = slot_centre(slot)
    col, row = slot % 3, slot // 3
    # Edge anchors grow inward. Middle anchors choose a stable side, allowing
    # the soft footprint to cross the parent boundary where appropriate.
    x_sign = 1 if col == 0 else -1 if col == 2 else (1 if (x + y) % 2 == 0 else -1)
    y_sign = 1 if row == 0 else -1 if row == 2 else (1 if (x * 3 + y) % 2 == 0 else -1)
    return u + x_sign / 6.0, v + y_sign / 6.0


def feature_subtile_layout(
    feature_name: str,
    x: int,
    y: int,
    *,
    tree_age_years: int = 0,
    variant: int = 1,
    deposit: int = 0,
    crop_kind: str | None = None,
    anchor_slot: int | None = None,
) -> tuple[int, float, float]:
    """Return visual footprint size and centre around a stable hard anchor.

    The centre is allowed to sit near a parent-cell edge. Larger footprints
    therefore overhang that edge instead of moving their trunk/anchor as they
    grow.
    """
    name = str(feature_name).upper()
    slot = stable_anchor_slot(x, y, variant) if anchor_slot is None else int(anchor_slot)
    u, v = slot_centre(slot)
    one_slot = {
        "SAPLING", "MUSHROOM", "HERB", "WILD_CROP",
        "BERRY_BUSH", "WOOD_BUSH", "MEAT", "FISH", "HIDE", "FUR",
        "FEATHER",
    }
    if name in {"HERB", "WILD_CROP", "CROP_HERB"} and crop_kind:
        from crops import CROP_BY_KEY

        crop = CROP_BY_KEY.get(str(crop_kind))
        if crop is not None and crop.icon_base == "crop_vine":
            centre_u, centre_v = _two_by_two_centre(slot, x, y)
            return 4, centre_u, centre_v
    if name in one_slot:
        return 1, u, v
    if name == "REED":
        # Reed, cattail, and sedge species all share FeatureType.REED.
        centre_u, centre_v = _two_by_two_centre(slot, x, y)
        return 4, centre_u, centre_v
    if name == "ROCK":
        if int(deposit) < 20:
            return 1, u, v
        centre_u, centre_v = _two_by_two_centre(slot, x, y)
        return 4, centre_u, centre_v
    if name == "TREE":
        if int(tree_age_years) >= 6:
            return 9, u, v
        centre_u, centre_v = _two_by_two_centre(slot, x, y)
        return 4, centre_u, centre_v
    return 9, 0.5, 0.5


def _covered_parent_slots(centre_u: float, centre_v: float, scale: float) -> frozenset[int]:
    """Return parent-cell subcells touched by an axis-aligned visual footprint."""
    half = scale * 0.5
    left, right = centre_u - half, centre_u + half
    top, bottom = centre_v - half, centre_v + half
    covered: set[int] = set()
    for slot in range(9):
        col, row = slot % 3, slot // 3
        sl, sr = col / 3.0, (col + 1) / 3.0
        st, sb = row / 3.0, (row + 1) / 3.0
        if min(right, sr) - max(left, sl) > 1e-9 and min(bottom, sb) - max(top, st) > 1e-9:
            covered.add(slot)
    return frozenset(covered)


def object_footprint(
    feature_name: str,
    x: int,
    y: int,
    *,
    tree_age_years: int = 0,
    variant: int = 1,
    deposit: int = 0,
    crop_kind: str | None = None,
    anchor_slot: int | None = None,
) -> ObjectFootprint:
    """Describe visual occupancy, hard collision, family, and cell capacity."""
    name = str(feature_name).upper()
    anchor = stable_anchor_slot(x, y, variant) if anchor_slot is None else max(0, min(8, int(anchor_slot)))
    slots, u, v = feature_subtile_layout(
        name,
        x,
        y,
        tree_age_years=tree_age_years,
        variant=variant,
        deposit=deposit,
        crop_kind=crop_kind,
        anchor_slot=anchor,
    )
    hard = frozenset({anchor}) if name == "TREE" or (name == "ROCK" and int(deposit) >= 20) else frozenset()
    if name == "SAPLING":
        family, maximum = "tree", 3
    elif name == "TREE":
        family, maximum = "tree", 2 if slots == 4 else 2
    elif name in {"MUSHROOM", "WOOD_BUSH"}:
        family, maximum = "forest_litter", 3
    elif name in {"HERB", "WILD_CROP", "REED", "BERRY_BUSH"}:
        family, maximum = "wild_plant", 3
    elif name in {"MEAT", "FISH", "HIDE", "FUR", "FEATHER"}:
        family, maximum = "loose_drop", 9
    else:
        family, maximum = name.lower(), 1 if hard else 3
    floor_layer = (
        name in {"SAPLING", "MUSHROOM", "WOOD_BUSH"}
        or (name == "ROCK" and slots == 1)
        or (name in {"HERB", "WILD_CROP", "BERRY_BUSH"} and slots == 1)
    )
    return ObjectFootprint(
        slots=slots,
        centre_u=u,
        centre_v=v,
        occupied_slots=_covered_parent_slots(u, v, footprint_scale(slots)),
        hard_slots=hard,
        family=family,
        max_per_cell=maximum,
        floor_layer=floor_layer,
    )


def placement_allowed(candidate: ObjectFootprint, existing: list[ObjectFootprint]) -> bool:
    """Apply shared density and overlap rules for one ecology cell."""
    same_family = [item for item in existing if item.family == candidate.family]
    if len(same_family) >= candidate.max_per_cell:
        return False
    occupied = frozenset().union(*(item.occupied_slots for item in existing)) if existing else frozenset()
    hard = frozenset().union(*(item.hard_slots for item in existing)) if existing else frozenset()
    # A trunk / big-rock core is exclusive, and nothing may be placed over it.
    if candidate.hard_slots & occupied or candidate.occupied_slots & hard:
        return False
    overlap = candidate.occupied_slots & occupied
    if candidate.family == "tree":
        # Two 2x2 young trees may share one soft/canopy subcell. Saplings and a
        # large overhanging tree otherwise need a genuinely free parent subcell.
        return candidate.slots == 4 and all(item.slots == 4 for item in same_family) and len(overlap) <= 1 or not overlap
    return not overlap


def first_available_anchor(
    feature_name: str,
    x: int,
    y: int,
    existing: list[ObjectFootprint],
    *,
    tree_age_years: int = 0,
    variant: int = 1,
    deposit: int = 0,
    crop_kind: str | None = None,
    preferred: int | None = None,
) -> tuple[int, ObjectFootprint] | None:
    """Choose a deterministic legal anchor, preferring the requested slot."""
    initial = stable_anchor_slot(x, y, variant) if preferred is None else max(0, min(8, int(preferred)))
    order = [initial, *(slot for slot in range(9) if slot != initial)]
    for anchor in order:
        candidate = object_footprint(
            feature_name,
            x,
            y,
            tree_age_years=tree_age_years,
            variant=variant,
            deposit=deposit,
            crop_kind=crop_kind,
            anchor_slot=anchor,
        )
        if placement_allowed(candidate, existing):
            return anchor, candidate
    return None


def footprint_scale(slots: int) -> float:
    if slots <= 1:
        return 1.0 / 3.0
    if slots <= 4:
        return 2.0 / 3.0
    return 1.0


def tree_icon_scale(slots: int) -> float:
    """SVG cell scale: 2x2 trees normal, 3x3 trees enlarged by 1.5."""
    return 1.5 if int(slots) >= 9 else 1.0
