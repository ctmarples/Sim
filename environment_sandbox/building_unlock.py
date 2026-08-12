"""Build menu unlock tiers and construction material costs."""

from __future__ import annotations

from dataclasses import dataclass

from entities import BuildingKind, TaskType

# Menu order (icons left→right). Hidden until unlocked.
BUILD_MENU_ORDER: tuple[BuildingKind, ...] = (
    BuildingKind.FORAGER,
    BuildingKind.TENT,
    BuildingKind.CRAFT_BENCH,
    BuildingKind.HUNTER,
    BuildingKind.FORESTER,
    BuildingKind.MASON,
    BuildingKind.WORKSTATION,
    BuildingKind.HOUSE_SMALL,
    BuildingKind.HOUSE,
    BuildingKind.FISHER,
    BuildingKind.FARM,
    BuildingKind.FIELD,
    BuildingKind.KITCHEN,
    BuildingKind.MILL,
    BuildingKind.ALCHEMIST,
    BuildingKind.TAILOR,
    BuildingKind.COBBLER,
    BuildingKind.MARKET,
)

# Sequential unlock groups: next group opens when any building in the
# previous group has been completed (tier 0 is always available).
UNLOCK_TIERS: tuple[frozenset[BuildingKind], ...] = (
    frozenset({BuildingKind.FORAGER, BuildingKind.TENT}),
    frozenset(
        {
            BuildingKind.CRAFT_BENCH,
            BuildingKind.HUNTER,
            BuildingKind.FORESTER,
            BuildingKind.MASON,
        }
    ),
    frozenset({BuildingKind.WORKSTATION, BuildingKind.HOUSE_SMALL}),
    frozenset(
        {
            BuildingKind.FISHER,
            BuildingKind.FARM,
            BuildingKind.FIELD,
            BuildingKind.KITCHEN,
            BuildingKind.MILL,
            BuildingKind.HOUSE,
        }
    ),
    frozenset({BuildingKind.ALCHEMIST, BuildingKind.TAILOR, BuildingKind.COBBLER, BuildingKind.MARKET}),
)

# Tier-4 production set used to unlock alchemist/tailor (Field/House alone does not).
_TIER4_GATE: frozenset[BuildingKind] = frozenset(
    {
        BuildingKind.FISHER,
        BuildingKind.FARM,
        BuildingKind.KITCHEN,
        BuildingKind.MILL,
    }
)


@dataclass(frozen=True)
class BuildCost:
    """Construction materials.

    ``wood`` = processed wood (not logs).
    ``logs`` = softwood logs.
    ``hardwood`` = hardwood logs.
    """

    wood: int = 0
    logs: int = 0
    rock: int = 0
    hardwood: int = 0
    task: TaskType = TaskType.FULL_FORAGE

    def as_parts(self) -> list[tuple[str, int]]:
        """Icon key + amount for hover tooltips (skip zeros)."""
        parts: list[tuple[str, int]] = []
        if self.wood:
            parts.append(("wood", self.wood))
        if self.logs:
            parts.append(("log_wood", self.logs))
        if self.hardwood:
            parts.append(("log_hardwood", self.hardwood))
        if self.rock:
            parts.append(("rock", self.rock))
        return parts

    def summary_bits(self) -> list[str]:
        bits: list[str] = []
        if self.wood:
            bits.append(f"{self.wood} wood")
        if self.logs:
            bits.append(f"{self.logs} logs")
        if self.hardwood:
            bits.append(f"{self.hardwood} hardwood")
        if self.rock:
            bits.append(f"{self.rock} rock")
        return bits


# Costs match the early-game unlock ladder.
BUILD_COSTS: dict[BuildingKind, BuildCost] = {
    BuildingKind.FORAGER: BuildCost(wood=2, rock=2, task=TaskType.FULL_FORAGE),
    BuildingKind.CRAFT_BENCH: BuildCost(wood=2, rock=2, task=TaskType.FULL_FORAGE),
    BuildingKind.HUNTER: BuildCost(wood=2, rock=2, task=TaskType.HUNT),
    BuildingKind.FORESTER: BuildCost(wood=2, rock=2, task=TaskType.FULL_MANAGE),
    BuildingKind.MASON: BuildCost(wood=2, rock=2, task=TaskType.COLLECT_ROCKS),
    BuildingKind.WORKSTATION: BuildCost(logs=2, rock=4, task=TaskType.FULL_FORAGE),
    BuildingKind.FISHER: BuildCost(logs=2, rock=4, task=TaskType.FISH),
    BuildingKind.FARM: BuildCost(logs=2, rock=4, task=TaskType.FARM_FIELD),
    BuildingKind.FIELD: BuildCost(wood=1, rock=0, task=TaskType.FARM_FIELD),
    BuildingKind.KITCHEN: BuildCost(logs=2, rock=4, task=TaskType.FULL_FORAGE),
    BuildingKind.MILL: BuildCost(logs=2, rock=4, task=TaskType.FULL_FORAGE),
    BuildingKind.ALCHEMIST: BuildCost(hardwood=4, rock=4, task=TaskType.FULL_FORAGE),
    BuildingKind.TAILOR: BuildCost(hardwood=4, rock=4, task=TaskType.FULL_FORAGE),
    BuildingKind.COBBLER: BuildCost(logs=2, rock=2, task=TaskType.FULL_FORAGE),
    BuildingKind.MARKET: BuildCost(logs=2, rock=4, task=TaskType.FULL_FORAGE),
    BuildingKind.TENT: BuildCost(wood=2, rock=0, task=TaskType.FULL_FORAGE),
    BuildingKind.HOUSE_SMALL: BuildCost(logs=2, rock=2, task=TaskType.FULL_FORAGE),
    BuildingKind.HOUSE: BuildCost(logs=4, rock=4, task=TaskType.FULL_FORAGE),
    BuildingKind.BARN: BuildCost(logs=2, rock=2, task=TaskType.FARM_FIELD),
    BuildingKind.PANTRY: BuildCost(logs=2, rock=2, task=TaskType.FULL_FORAGE),
    BuildingKind.DRYING_RACK: BuildCost(wood=2, rock=1, task=TaskType.HUNT),
}


def built_kinds(buildings: dict[int, object]) -> set[BuildingKind]:
    out: set[BuildingKind] = set()
    for b in buildings.values():
        kind = getattr(b, "kind", None)
        if isinstance(kind, BuildingKind):
            out.add(kind)
    return out


def unlocked_kinds(built: set[BuildingKind]) -> set[BuildingKind]:
    """Return placeable kinds given completed buildings."""
    unlocked = set(UNLOCK_TIERS[0])
    if BuildingKind.FORAGER in built:
        unlocked |= UNLOCK_TIERS[1]
    if built & UNLOCK_TIERS[1]:
        unlocked |= UNLOCK_TIERS[2]
    if BuildingKind.WORKSTATION in built:
        unlocked |= UNLOCK_TIERS[3]
    if built & _TIER4_GATE:
        unlocked |= UNLOCK_TIERS[4]
    return unlocked


def building_cost(kind: BuildingKind) -> BuildCost:
    return BUILD_COSTS.get(kind, BuildCost(wood=2, rock=2))


def visible_build_order(built: set[BuildingKind]) -> list[BuildingKind | None]:
    """Toolbar / B-cycle list: unlocked buildings + Off."""
    allowed = unlocked_kinds(built)
    order: list[BuildingKind | None] = [k for k in BUILD_MENU_ORDER if k in allowed]
    order.append(None)
    return order
