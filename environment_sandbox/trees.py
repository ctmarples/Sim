"""Tree species catalogue: growth, yields, and drawing hints.

Per-species ``yield_amount`` / ``yield_key`` are the wood harvest amounts.
Other resource yields and food effects: ``resource_balance.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

from seasons import YEAR_DAYS


@dataclass(frozen=True)
class TreeDef:
    key: str
    label: str
    short: str
    # Years from sapling to mature tree (base ticks; seasonal grow may stretch).
    growth_years: float
    yield_amount: int
    yield_key: str  # "logs" or "hardwood_logs"
    canopy: tuple[int, int, int]
    sapling_colour: tuple[int, int, int]
    shape: str  # "round" | "cone"
    cone_scale: float = 1.0  # relative cone size for pine/cedar


def growth_ticks_for(tree: TreeDef) -> int:
    from seasons import TICKS_PER_DAY

    return max(1, int(round(tree.growth_years * YEAR_DAYS * TICKS_PER_DAY)))


TREES: tuple[TreeDef, ...] = (
    TreeDef(
        key="oak",
        label="Oak",
        short="oak",
        growth_years=3.0,
        yield_amount=4,
        yield_key="hardwood_logs",
        canopy=(34, 120, 45),
        sapling_colour=(140, 210, 90),
        shape="round",
    ),
    TreeDef(
        key="maple",
        label="Maple",
        short="mpl",
        growth_years=2.0,
        yield_amount=2,
        yield_key="hardwood_logs",
        canopy=(90, 170, 70),  # lighter green
        sapling_colour=(160, 220, 110),
        shape="round",
    ),
    TreeDef(
        key="pine",
        label="Pine",
        short="pine",
        growth_years=1.0,
        yield_amount=2,
        yield_key="logs",
        canopy=(20, 90, 45),  # dark green
        sapling_colour=(60, 140, 70),
        shape="cone",
        cone_scale=1.0,
    ),
    TreeDef(
        key="cedar",
        label="Cedar",
        short="cdr",
        growth_years=2.0,
        yield_amount=3,
        yield_key="logs",
        canopy=(30, 110, 55),
        sapling_colour=(80, 160, 90),
        shape="cone",
        cone_scale=1.35,  # larger conical crown
    ),
)

TREE_BY_KEY: dict[str, TreeDef] = {t.key: t for t in TREES}
TREE_KEYS: tuple[str, ...] = tuple(t.key for t in TREES)
DEFAULT_TREE_KEY: str = "oak"

# Inventory / storage keys — one sapling stack per species.
SAPLING_ITEM_KEYS: tuple[str, ...] = tuple(f"{k}_saplings" for k in TREE_KEYS)


def sapling_item_key(species: str | None) -> str:
    return f"{resolve_tree(species).key}_saplings"


def species_from_sapling_key(key: str) -> str:
    if key.endswith("_saplings"):
        species = key[: -len("_saplings")]
        if species in TREE_BY_KEY:
            return species
    return DEFAULT_TREE_KEY

# Weighted mix when placing trees in wooded soil.
TREE_SPAWN_WEIGHTS: dict[str, float] = {
    "oak": 0.30,
    "maple": 0.25,
    "pine": 0.25,
    "cedar": 0.20,
}


def pick_tree_species(rng) -> str:
    """Weighted random species key."""
    keys = list(TREE_SPAWN_WEIGHTS.keys())
    weights = [TREE_SPAWN_WEIGHTS[k] for k in keys]
    total = sum(weights)
    r = rng.random() * total
    acc = 0.0
    for key, w in zip(keys, weights):
        acc += w
        if r <= acc:
            return key
    return keys[-1]


def resolve_tree(key: str | None) -> TreeDef:
    if key and key in TREE_BY_KEY:
        return TREE_BY_KEY[key]
    return TREE_BY_KEY[DEFAULT_TREE_KEY]
