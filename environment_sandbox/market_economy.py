"""Market prices and seasonal demand generation."""

from __future__ import annotations

import random
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from seasons import Season

# Goods the market accepts for sale → coin value per unit.
MARKET_PRICES: dict[str, int] = {
    "blackberries": 1,
    "sloe_berries": 1,
    "elderberries": 1,
    "hazelnuts": 1,
    "mushrooms": 1,
    "reeds": 1,
    "straw": 1,
    "honey": 2,
    "meat": 3,
    "fish": 3,
    "fur": 3,
    "onion": 2,
    "cabbage": 2,
    "carrot": 2,
    "garlic": 2,
    "wheat": 2,
    "rye": 2,
    "wheat_grain": 2,
    "rye_grain": 2,
    "flax": 2,
    "hemp": 2,
    "sage": 2,
    "mint": 2,
    "bread": 4,
    "stew": 5,
    "fish_stew": 5,
    "mushroom_stew": 4,
    "grilled_meat": 5,
    "grilled_fish": 5,
    "spiced_stew": 10,
    "wheat_flour": 3,
    "rye_flour": 3,
    "wood": 1,
    "rock": 1,
    "twine": 2,
    "sun_hat": 10,
    "winter_hat": 15,
    "light_shirt": 15,
    "winter_coat": 20,
    "leather_shoes": 18,
    "leather_satchel": 14,
}

MARKET_SELLABLE_KEYS: tuple[str, ...] = tuple(MARKET_PRICES.keys())


@lru_cache(maxsize=8)
def market_supply_resource_keys(group: str | None = None) -> tuple[str, ...]:
    """All catalogue resources in food/wares/agriculture (excludes coins)."""
    from resources import GROUP_ORDER, RESOURCES

    keys: list[str] = []
    for res in RESOURCES:
        if res.key == "coins":
            continue
        if res.group not in GROUP_ORDER:
            continue
        if group is not None and res.group != group:
            continue
        keys.append(res.key)
    return tuple(keys)

# How often a market worker attempts a sale (work ticks between rolls).
MARKET_SELL_INTERVAL: int = 8

# Soft cap on how many distinct goods appear in one season's demand board.
MARKET_DEMAND_KIND_MIN: int = 4
MARKET_DEMAND_KIND_MAX: int = 8

# Per-good demand range (units buyers want this season).
MARKET_DEMAND_AMOUNT_MIN: int = 3
MARKET_DEMAND_AMOUNT_MAX: int = 14

# Season-biased pools (still drawn from MARKET_PRICES). Missing keys fall back
# to the full catalogue so new goods stay eligible.
_SEASON_BIAS: dict[str, tuple[str, ...]] = {
    "SPRING": (
        "onion",
        "cabbage",
        "carrot",
        "garlic",
        "sage",
        "mint",
        "flax",
        "reeds",
        "wood",
        "twine",
    ),
    "SUMMER": (
        "blackberries",
        "honey",
        "fish",
        "meat",
        "hemp",
        "mint",
        "sage",
        "mushrooms",
        "grilled_fish",
        "stew",
    ),
    "AUTUMN": (
        "wheat",
        "rye",
        "wheat_grain",
        "rye_grain",
        "wheat_flour",
        "rye_flour",
        "bread",
        "meat",
        "fur",
        "straw",
        "mushroom_stew",
        "grilled_meat",
    ),
    "WINTER": (
        "bread",
        "stew",
        "fish_stew",
        "spiced_stew",
        "fur",
        "wood",
        "rock",
        "meat",
        "twine",
        "honey",
    ),
}


def generate_seasonal_demand(
    season: Season | str,
    rng: random.Random | None = None,
) -> dict[str, int]:
    """Pick a seasonal basket of goods with per-key demand counts."""
    roll = rng.randrange if rng is not None else random.randrange
    sample = rng.sample if rng is not None else random.sample

    season_name = season.name if hasattr(season, "name") else str(season)
    biased = [k for k in _SEASON_BIAS.get(season_name, ()) if k in MARKET_PRICES]
    pool = list(dict.fromkeys([*biased, *MARKET_SELLABLE_KEYS]))
    n_kinds = min(
        len(pool),
        max(
            MARKET_DEMAND_KIND_MIN,
            roll(MARKET_DEMAND_KIND_MIN, MARKET_DEMAND_KIND_MAX + 1),
        ),
    )
    # Prefer biased goods first, then fill from the rest.
    picks: list[str] = []
    if biased:
        take = min(len(biased), max(2, n_kinds - 1))
        picks.extend(sample(biased, take) if take < len(biased) else list(biased))
    rest = [k for k in pool if k not in picks]
    while len(picks) < n_kinds and rest:
        picks.append(rest.pop(roll(0, len(rest))))
    demand: dict[str, int] = {}
    for key in picks:
        # Slightly higher demand for cheaper staples.
        price = max(1, int(MARKET_PRICES.get(key, 1)))
        lo = MARKET_DEMAND_AMOUNT_MIN
        hi = MARKET_DEMAND_AMOUNT_MAX + max(0, 4 - price)
        demand[key] = roll(lo, hi + 1)
    return demand


def demand_keys(demand: dict[str, int]) -> tuple[str, ...]:
    """Stable display order: higher demand first, then catalogue order."""
    order = {k: i for i, k in enumerate(MARKET_SELLABLE_KEYS)}
    return tuple(
        sorted(
            (k for k, n in demand.items() if int(n) > 0),
            key=lambda k: (-int(demand.get(k, 0)), order.get(k, 999), k),
        )
    )
