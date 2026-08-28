"""Normalized 3x3 visual footprints for resources inside ecology cells."""

from __future__ import annotations


def stable_anchor_slot(x: int, y: int, variant: int = 1) -> int:
    """Return a deterministic 0..8 hard-anchor slot for an object."""
    return (x * 17 + y * 31 + max(1, int(variant)) * 7) % 9


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
        "SAPLING", "MUSHROOM", "HERB", "WILD_CROP", "REED",
        "BERRY_BUSH", "WOOD_BUSH",
    }
    if name in one_slot:
        return 1, u, v
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


def footprint_scale(slots: int) -> float:
    if slots <= 1:
        return 1.0 / 3.0
    if slots <= 4:
        return 2.0 / 3.0
    return 1.0
