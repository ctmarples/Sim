"""Berry bush species: blackberry, sloe, elderberry, and hazel."""

from __future__ import annotations

# key → (label, food_key, seed_key, fruit_rgb, bush_rgb, empty_fruit_rgb)
BERRY_BUSH_DEFS: tuple[tuple[str, str, str, str, tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]], ...] = (
    ("blackberry", "Blackberry bush", "blackberries", "blackberry_seeds", (40, 20, 55), (45, 100, 45), (70, 95, 55)),
    ("sloe", "Sloe berry bush", "sloe_berries", "sloe_berry_seeds", (55, 45, 120), (55, 105, 50), (75, 100, 55)),
    ("elderberry", "Elder berry bush", "elderberries", "elder_berry_seeds", (110, 30, 90), (50, 115, 55), (70, 95, 55)),
    ("hazel", "Hazel bush", "hazelnuts", "hazel_seeds", (150, 105, 45), (60, 110, 50), (85, 100, 60)),
)

BERRY_BUSH_KEYS: tuple[str, ...] = tuple(row[0] for row in BERRY_BUSH_DEFS)
BERRY_FOOD_KEYS: tuple[str, ...] = tuple(row[2] for row in BERRY_BUSH_DEFS)
BERRY_SEED_KEYS: tuple[str, ...] = tuple(row[3] for row in BERRY_BUSH_DEFS)
LEGACY_BERRY_KIND = "berry_bush"
LEGACY_BERRY_FOOD = "berries"
LEGACY_BERRY_SEED = "berry_seeds"

# Trade rewards from the berry traveller.
TRADE_SEED_REWARDS: tuple[tuple[str, int], ...] = (
    ("blackberry_seeds", 2),
    ("sloe_berry_seeds", 2),
    ("elder_berry_seeds", 2),
)
TRADE_FOOD_COST = 20


def normalize_berry_kind(kind: str | None) -> str:
    if not kind or kind == LEGACY_BERRY_KIND:
        return "blackberry"
    return kind if kind in BERRY_BUSH_KEYS else "blackberry"


def berry_food_key(kind: str | None) -> str:
    kind = normalize_berry_kind(kind)
    for key, _label, food, _seed, *_rest in BERRY_BUSH_DEFS:
        if key == kind:
            return food
    return "blackberries"


def berry_seed_key(kind: str | None) -> str:
    kind = normalize_berry_kind(kind)
    for key, _label, _food, seed, *_rest in BERRY_BUSH_DEFS:
        if key == kind:
            return seed
    return "blackberry_seeds"


def berry_kind_for_seed(seed_key: str) -> str | None:
    if seed_key == LEGACY_BERRY_SEED:
        return "blackberry"
    for key, _label, _food, seed, *_rest in BERRY_BUSH_DEFS:
        if seed == seed_key:
            return key
    return None


def berry_fruit_colour(kind: str | None) -> tuple[int, int, int]:
    kind = normalize_berry_kind(kind)
    for key, _label, _food, _seed, fruit, _bush, _empty in BERRY_BUSH_DEFS:
        if key == kind:
            return fruit
    return (40, 20, 55)


def berry_bush_colour(kind: str | None) -> tuple[int, int, int]:
    kind = normalize_berry_kind(kind)
    for key, _label, _food, _seed, _fruit, bush, _empty in BERRY_BUSH_DEFS:
        if key == kind:
            return bush
    return (50, 110, 50)


def berry_empty_fruit_colour(kind: str | None) -> tuple[int, int, int]:
    kind = normalize_berry_kind(kind)
    for key, _label, _food, _seed, _fruit, _bush, empty in BERRY_BUSH_DEFS:
        if key == kind:
            return empty
    return (70, 95, 55)


def first_carried_berry_seed(inventory) -> str | None:
    for key in (*BERRY_SEED_KEYS, LEGACY_BERRY_SEED):
        if int(getattr(inventory, key, 0) or 0) > 0:
            return key
    return None
