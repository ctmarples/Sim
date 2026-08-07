"""Resource catalogue: keys, labels, and display groups.

Add new resources here so inventory UI and totals stay consistent.
Yields, drops, and food effects: ``resource_balance.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

from crops import CROPS
from trees import TREES


@dataclass(frozen=True)
class ResourceDef:
    key: str
    label: str
    group: str
    short: str


# Display order within each group follows this list order.
# Onion / cabbage / carrot are edible produce (food); other crops stay wares.
_FOOD_CROP_KEYS = frozenset({"onion", "cabbage", "carrot", "garlic"})
_CROP_PRODUCE_FOOD = tuple(
    ResourceDef(c.produce_key, c.label, "food", c.short)
    for c in CROPS
    if c.key in _FOOD_CROP_KEYS
)
_CROP_PRODUCE_WARES = tuple(
    ResourceDef(c.produce_key, c.label, "wares", c.short)
    for c in CROPS
    if c.key not in _FOOD_CROP_KEYS
)
_CROP_SEEDS = tuple(
    ResourceDef(c.seed_key, f"{c.label} seeds", "agriculture", f"{c.short}.s")
    for c in CROPS
)
_TREE_SAPLINGS = tuple(
    ResourceDef(f"{t.key}_saplings", f"{t.label} saplings", "agriculture", f"{t.short}.p")
    for t in TREES
)

RESOURCES: list[ResourceDef] = [
    ResourceDef("meat", "Meat", "food", "meat"),
    ResourceDef("fish", "Fish", "food", "fish"),
    ResourceDef("berries", "Berries", "food", "berr"),
    ResourceDef("mushrooms", "Mushrooms", "food", "mush"),
    ResourceDef("honey", "Honey", "food", "hone"),
    *_CROP_PRODUCE_FOOD,
    ResourceDef("bread", "Bread", "food", "bread"),
    ResourceDef("stew", "Stew", "food", "stew"),
    ResourceDef("fish_stew", "Fish stew", "food", "f.stw"),
    ResourceDef("grilled_meat", "Grilled meat", "food", "g.mt"),
    ResourceDef("grilled_fish", "Grilled fish", "food", "g.fh"),
    ResourceDef("logs", "Logs", "wares", "logs"),
    ResourceDef("hardwood_logs", "Hardwood logs", "wares", "hlogs"),
    ResourceDef("wood", "Wood", "wares", "wood"),
    ResourceDef("twine", "Twine", "wares", "twine"),
    ResourceDef("axe", "Axe", "wares", "axe"),
    ResourceDef("spear", "Spear", "wares", "spr"),
    ResourceDef("fishing_rod", "Fishing rod", "wares", "rod"),
    ResourceDef("hoe", "Hoe", "wares", "hoe"),
    ResourceDef("knife", "Knife", "wares", "knf"),
    ResourceDef("insect_repellant", "Insect repellant", "wares", "rep"),
    ResourceDef("mineral_powder", "Mineral powder", "wares", "min"),
    ResourceDef("spices", "Spices", "wares", "spc"),
    ResourceDef("rock", "Rock", "wares", "rock"),
    ResourceDef("reeds", "Reeds", "wares", "reed"),
    *_CROP_PRODUCE_WARES,
    ResourceDef("wheat_flour", "Wheat flour", "wares", "w.fl"),
    ResourceDef("rye_flour", "Rye flour", "wares", "r.fl"),
    *_TREE_SAPLINGS,
    ResourceDef("berry_seeds", "Berry seeds", "agriculture", "b.sd"),
    *_CROP_SEEDS,
]

GROUP_ORDER: tuple[str, ...] = ("food", "wares", "agriculture")
GROUP_LABELS: dict[str, str] = {
    "food": "Food",
    "wares": "Wares",
    "agriculture": "Agriculture",
    "construction": "Wares",
}

RESOURCE_KEYS: tuple[str, ...] = tuple(r.key for r in RESOURCES)


def register_resource(
    key: str,
    *,
    label: str,
    group: str = "food",
    short: str | None = None,
) -> None:
    """Add or replace a catalogue entry (used by recipe JSON loader)."""
    global RESOURCE_KEYS
    short_label = short or key[:4]
    entry = ResourceDef(key, label, group, short_label)
    for i, existing in enumerate(RESOURCES):
        if existing.key == key:
            RESOURCES[i] = entry
            RESOURCE_KEYS = tuple(r.key for r in RESOURCES)
            return
    # Insert foods before wares when possible.
    insert_at = len(RESOURCES)
    if group == "food":
        for i, existing in enumerate(RESOURCES):
            if existing.group != "food":
                insert_at = i
                break
    RESOURCES.insert(insert_at, entry)
    RESOURCE_KEYS = tuple(r.key for r in RESOURCES)


def resources_by_group() -> list[tuple[str, list[ResourceDef]]]:
    grouped: dict[str, list[ResourceDef]] = {g: [] for g in GROUP_ORDER}
    for res in RESOURCES:
        grouped.setdefault(res.group, []).append(res)
    return [(g, grouped[g]) for g in GROUP_ORDER if grouped.get(g)]


def format_grouped_counts(amounts: dict[str, int], *, skip_zero: bool = False) -> list[str]:
    """Return lines like 'Food: 2 meat, 1 fish' for UI panels."""
    lines: list[str] = []
    for group, defs in resources_by_group():
        parts: list[str] = []
        for res in defs:
            n = int(amounts.get(res.key, 0))
            if skip_zero and n <= 0:
                continue
            parts.append(f"{n} {res.short}")
        if parts:
            lines.append(f"{GROUP_LABELS.get(group, group)}: " + ", ".join(parts))
        elif not skip_zero:
            lines.append(f"{GROUP_LABELS.get(group, group)}: —")
    return lines


def resource_label(key: str) -> str:
    for res in RESOURCES:
        if res.key == key:
            return res.label
    return key


def resource_icon(key: str) -> str:
    """Map an inventory resource key to an ``icons`` base name for UI grids."""
    return resource_icon_style(key).name


@dataclass(frozen=True)
class ResourceIconStyle:
    """Raster style for an inventory grid icon (matches map feature colours)."""

    name: str
    recolour: dict[str, tuple[int, int, int]]
    class_scales: dict[str, float] | None = None
    omit_classes: tuple[str, ...] = ()
    # If set, draw this resource's icon as a small badge in the top-left quarter.
    badge_key: str | None = None


# Seed pile colour (matches seeds.svg brown).
_SEED_COLOUR: tuple[int, int, int] = (130, 62, 39)


def _crop_plant_style(crop, *, dense: bool) -> ResourceIconStyle:
    recolour: dict[str, tuple[int, int, int]] = {"stem": crop.stem_colour}
    omit: tuple[str, ...] = ()
    if crop.flower_colour is not None:
        recolour["flower"] = crop.flower_colour
    else:
        omit = ("flower",)
    return ResourceIconStyle(
        name=crop.plant_icon(dense=dense),
        recolour=recolour,
        omit_classes=omit,
    )


def resource_icon_style(key: str) -> ResourceIconStyle:
    """Return icon style matching map feature colours (and seed composites)."""
    from icons import (
        ICON_AXE,
        ICON_BERRIES,
        ICON_BREAD,
        ICON_FISH,
        ICON_FISHING_ROD,
        ICON_FLOWER,

        ICON_HOE,
        ICON_KNIFE,
        ICON_LOG_HARDWOOD,
        ICON_LOG_WOOD,
        ICON_MEAT_MARKER,
        ICON_MUSHROOM,
        ICON_REED,
        ICON_ROCK,
        ICON_SAPLING_CONE,
        ICON_SAPLING_ROUND,
        ICON_SEEDS,
        ICON_SPEAR,
        ICON_STEW,
        ICON_FISH_STEW,
        ICON_TWINE,
        ICON_WOOD,
        crop_icon_base,
    )
    from settings import (
        COLOUR_BERRY,
        COLOUR_FISH,
        COLOUR_MEAT,
        COLOUR_MUSHROOM,
        COLOUR_REED,
        COLOUR_ROCK_FEATURE,
        COLOUR_TREE_CANOPY,
        COLOUR_TREE_TRUNK,
    )
    from trees import TREES

    trunk = COLOUR_TREE_TRUNK

    if key == "logs":
        return ResourceIconStyle(ICON_LOG_WOOD, {})

    if key == "hardwood_logs":
        return ResourceIconStyle(ICON_LOG_HARDWOOD, {})

    if key == "wood":
        return ResourceIconStyle(ICON_WOOD, {})

    if key == "twine":
        return ResourceIconStyle(ICON_TWINE, {})

    if key == "axe":
        return ResourceIconStyle(ICON_AXE, {})

    if key == "spear":
        return ResourceIconStyle(ICON_SPEAR, {})

    if key == "fishing_rod":
        return ResourceIconStyle(ICON_FISHING_ROD, {})

    if key == "hoe":
        return ResourceIconStyle(ICON_HOE, {})

    if key == "knife":
        return ResourceIconStyle(ICON_KNIFE, {})

    if key == "rock":
        return ResourceIconStyle(ICON_ROCK, {"body": COLOUR_ROCK_FEATURE})
    if key == "meat":
        return ResourceIconStyle(ICON_MEAT_MARKER, {"body": COLOUR_MEAT})
    if key == "deer":
        from icons import ICON_DEER_MALE
        from settings import COLOUR_DEER

        return ResourceIconStyle(ICON_DEER_MALE, {"body": COLOUR_DEER})
    if key == "boar":
        from icons import ICON_BOAR_MALE
        from settings import COLOUR_BOAR

        return ResourceIconStyle(ICON_BOAR_MALE, {"body": COLOUR_BOAR})
    if key == "fish":
        return ResourceIconStyle(ICON_FISH, {"body": COLOUR_FISH})
    if key == "mushrooms":
        return ResourceIconStyle(
            ICON_MUSHROOM, {"cap": COLOUR_MUSHROOM, "stem": (210, 200, 180)}
        )
    if key == "honey":
        from icons import ICON_HONEY

        return ResourceIconStyle(ICON_HONEY, {})
    if key == "rabbit":
        from icons import ICON_RABBIT

        return ResourceIconStyle(ICON_RABBIT, {})
    if key == "berries":
        return ResourceIconStyle(ICON_BERRIES, {"berry": COLOUR_BERRY})
    if key == "berry_seeds":
        return ResourceIconStyle(
            ICON_SEEDS,
            {"flower": _SEED_COLOUR},
            badge_key="berries",
        )
    if key == "reeds":
        return ResourceIconStyle(ICON_REED, {"stem": COLOUR_REED})

    if key == "wheat_flour":
        return ResourceIconStyle(
            ICON_SEEDS,
            {"flower": (220, 200, 140)},
            badge_key="wheat",
        )
    if key == "rye_flour":
        return ResourceIconStyle(
            ICON_SEEDS,
            {"flower": (190, 160, 110)},
            badge_key="rye",
        )
    if key == "bread":
        return ResourceIconStyle(ICON_BREAD, {"body": (210, 170, 100)})
    if key == "stew":
        return ResourceIconStyle(
            ICON_STEW,
            {"body": (140, 100, 70), "accent": (192, 96, 48)},
        )
    if key == "fish_stew":
        return ResourceIconStyle(
            ICON_FISH_STEW,
            {"body": (140, 100, 70), "accent": (64, 128, 176)},
        )
    if key == "mushroom_stew":
        return ResourceIconStyle(
            "mushroom_stew",
            {"body": (140, 100, 70), "accent": (107, 74, 46)},
        )
    if key == "grilled_meat":
        # Same marker as raw meat, browned/cooked tint.
        return ResourceIconStyle(ICON_MEAT_MARKER, {"body": (160, 90, 45)})
    if key == "grilled_fish":
        return ResourceIconStyle(ICON_FISH, {"body": (200, 140, 70)})

    for tree in TREES:
        if key == f"{tree.key}_saplings":
            base = ICON_SAPLING_CONE if tree.shape == "cone" else ICON_SAPLING_ROUND
            scales = {"canopy": tree.cone_scale} if tree.shape == "cone" else None
            return ResourceIconStyle(
                base,
                {"canopy": tree.sapling_colour, "trunk": trunk},
                scales,
            )

    from crops import CROP_BY_KEY

    if key.endswith("_seeds"):
        crop_key = key[: -len("_seeds")]
        if crop_key in CROP_BY_KEY:
            return ResourceIconStyle(
                ICON_SEEDS,
                {"flower": _SEED_COLOUR},
                badge_key=crop_key,
            )
        return ResourceIconStyle(ICON_SEEDS, {"flower": _SEED_COLOUR})

    crop = CROP_BY_KEY.get(key)
    if crop is not None:
        return _crop_plant_style(crop, dense=True)

    # Drop-in recipe icons: assets/icons/<key>.png (or .svg)
    from icons import icons_dir

    if (icons_dir() / f"{key}.png").is_file() or (icons_dir() / f"{key}.svg").is_file():
        return ResourceIconStyle(key, {})

    try:
        return ResourceIconStyle(
            crop_icon_base(key, dense=True), {"stem": COLOUR_TREE_CANOPY}
        )
    except Exception:
        return ResourceIconStyle(ICON_FLOWER, {"stem": COLOUR_TREE_CANOPY})


def amounts_from_obj(obj: object) -> dict[str, int]:
    return {key: int(getattr(obj, key, 0)) for key in RESOURCE_KEYS}


def merge_amounts(*dicts: dict[str, int]) -> dict[str, int]:
    totals = {key: 0 for key in RESOURCE_KEYS}
    for data in dicts:
        for key in RESOURCE_KEYS:
            totals[key] += int(data.get(key, 0))
    return totals


def group_totals(amounts: dict[str, int]) -> dict[str, int]:
    totals = {group: 0 for group in GROUP_ORDER}
    for res in RESOURCES:
        totals[res.group] = totals.get(res.group, 0) + int(amounts.get(res.key, 0))
    return totals
