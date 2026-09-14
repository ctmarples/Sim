"""Farm pipeline: typed jobs with a stable priority order.

Field → deposit → thresh → export/seed intake, instead of competing
per-tick interrupts. Mill/kitchen stay on existing processor logic until
farm export of grain is reliable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

class FarmJobKind(Enum):
    """Jobs a farm-assigned worker may claim."""

    DELIVER = auto()  # dump gather pack at farm / storehouse
    SOW = auto()
    HARVEST = auto()
    THRESH = auto()  # barn addon craft
    SEED_FETCH = auto()  # storehouse → farm seeds for unsown tiles
    WEED = auto()
    TREAT = auto()
    PLOUGH = auto()
    EXPORT = auto()  # surplus / clear latch → storehouse
    SHEAF_FETCH = auto()  # storehouse → barn sheaf buffer


# Lower index = higher priority when claiming.
FARM_JOB_PRIORITY: tuple[FarmJobKind, ...] = (
    FarmJobKind.DELIVER,  # unload full harvest pack to barn / farm
    FarmJobKind.HARVEST,  # ripe standing crops before weeding / sowing
    FarmJobKind.WEED,
    FarmJobKind.SOW,
    FarmJobKind.TREAT,
    FarmJobKind.PLOUGH,
    FarmJobKind.THRESH,
    FarmJobKind.SHEAF_FETCH,  # only when field work is clear
    FarmJobKind.SEED_FETCH,
    FarmJobKind.EXPORT,  # surplus grain / produce → mill / storehouse
)


@dataclass(frozen=True)
class FarmJob:
    kind: FarmJobKind
    building_id: int
    cell: tuple[int, int] | None = None


def farm_job_priority(kind: FarmJobKind) -> int:
    try:
        return FARM_JOB_PRIORITY.index(kind)
    except ValueError:
        return 99


def barn_sheaf_keys() -> tuple[str, ...]:
    """Produce keys the barn stores for threshing (recipe inputs)."""
    from recipes import BARN_RECIPES

    keys: set[str] = set()
    for recipe in BARN_RECIPES:
        keys.update(str(k) for k in recipe.inputs)
    return tuple(sorted(keys))


def barn_sheaf_keep_amount(key: str) -> int:
    """On-barn buffer: two crafts of each sheaf input."""
    from recipes import BARN_RECIPES

    keep = 0
    for recipe in BARN_RECIPES:
        need = int(recipe.inputs.get(key, 0))
        if need > 0:
            keep = max(keep, need * 2)
    return keep


def needs_hoe(kind: FarmJobKind) -> bool:
    return kind in (
        FarmJobKind.SOW,
        FarmJobKind.HARVEST,
        FarmJobKind.WEED,
        FarmJobKind.PLOUGH,
    )


def is_field_job(kind: FarmJobKind) -> bool:
    return kind in (
        FarmJobKind.SOW,
        FarmJobKind.HARVEST,
        FarmJobKind.WEED,
        FarmJobKind.TREAT,
        FarmJobKind.PLOUGH,
    )


def is_logistics_job(kind: FarmJobKind) -> bool:
    return kind in (
        FarmJobKind.DELIVER,
        FarmJobKind.SEED_FETCH,
        FarmJobKind.EXPORT,
        FarmJobKind.SHEAF_FETCH,
    )
