"""Resource catalogue: keys, labels, and display groups.

Add new resources here so inventory UI and totals stay consistent.
Yields, drops, and food effects: ``resource_balance.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
import csv
from pathlib import Path

from crops import CROPS
from trees import TREES


@dataclass(frozen=True)
class ResourceDef:
    key: str
    label: str
    group: str
    short: str
    icon_key: str = ""
    usage: str = "resource"
    stack_size: int = 1
    tool_effectiveness: float = 1.0
    tool_targets: str = ""


# Display order within each group follows this list order.
# Edible vegetables and pulses are food; fibre and unprocessed sheaves stay wares.
_FOOD_CROP_KEYS = frozenset(
    {
        "onion",
        "cabbage",
        "carrot",
        "garlic",
        "peas",
        "beans",
        "turnip",
        "potato",
        "pumpkin",
        "kale",
        "leek",
    }
)
_CROP_PRODUCE_FOOD = tuple(
    ResourceDef(c.produce_key, c.label, "food", c.short)
    for c in CROPS
    if c.key in _FOOD_CROP_KEYS
)
_CROP_PRODUCE_WARES = tuple(
    ResourceDef(
        c.produce_key,
        f"{c.label} sheaf" if c.key in ("wheat", "rye") else c.label,
        "wares",
        c.short,
    )
    for c in CROPS
    if c.key not in _FOOD_CROP_KEYS
)
_CROP_SEEDS = tuple(
    ResourceDef(
        c.seed_key,
        c.label if c.key in ("wheat", "rye") else f"{c.label} seeds",
        "agriculture",
        c.short if c.key in ("wheat", "rye") else f"{c.short}.s",
    )
    for c in CROPS
)
_TREE_SAPLINGS = tuple(
    ResourceDef(f"{t.key}_saplings", f"{t.label} saplings", "agriculture", f"{t.short}.p")
    for t in TREES
)
_TREE_SEEDS = tuple(
    ResourceDef(f"{t.key}_seeds", f"{t.label} seeds", "agriculture", f"{t.short}.s")
    for t in TREES
)

RESOURCES: list[ResourceDef] = [
    ResourceDef("meat", "Meat", "food", "meat"),
    ResourceDef("fish", "Fish", "food", "fish"),
    ResourceDef("blackberries", "Blackberries", "food", "blkb"),
    ResourceDef("sloe_berries", "Sloe berries", "food", "sloe"),
    ResourceDef("elderberries", "Elderberries", "food", "eldr"),
    ResourceDef("hazelnuts", "Hazelnuts", "food", "hazl"),
    ResourceDef("mushrooms", "Mushrooms", "food", "mush"),
    ResourceDef("nettles", "Nettles", "food", "nett"),
    ResourceDef("honey", "Honey", "food", "hone"),
    ResourceDef("book", "Old farm book", "wares", "book", "book_inventory"),
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
    ResourceDef("bow", "Bow", "wares", "bow"),
    ResourceDef("stone_arrows", "Stone arrows", "wares", "s.arr"),
    ResourceDef("insect_repellant", "Insect repellant", "wares", "rep"),
    ResourceDef("mineral_powder", "Mineral powder", "wares", "min"),
    ResourceDef("spices", "Spices", "wares", "spc"),
    ResourceDef("spoilage", "Spoilage", "wares", "spoil"),
    ResourceDef("compost", "Compost", "agriculture", "comp"),
    ResourceDef("rock", "Rock", "wares", "rock"),
    ResourceDef("reeds", "Reeds", "wares", "reed"),
    ResourceDef("straw", "Straw", "wares", "strw"),
    ResourceDef("fur", "Fur", "wares", "fur"),
    ResourceDef("feathers", "Feathers", "wares", "fthr"),
    ResourceDef("hide", "Hide", "wares", "hide"),
    ResourceDef("leather", "Leather", "wares", "leth"),
    *_CROP_PRODUCE_WARES,
    ResourceDef("coins", "Coins", "wares", "coin"),
    ResourceDef("wheat_flour", "Wheat flour", "wares", "w.fl"),
    ResourceDef("rye_flour", "Rye flour", "wares", "r.fl"),
    *_TREE_SAPLINGS,
    *_TREE_SEEDS,
    ResourceDef("berry_seeds", "Berry seeds", "agriculture", "b.sd"),
    ResourceDef("blackberry_seeds", "Blackberry seeds", "agriculture", "bk.s"),
    ResourceDef("sloe_berry_seeds", "Sloe berry seeds", "agriculture", "sl.s"),
    ResourceDef("elder_berry_seeds", "Elder berry seeds", "agriculture", "el.s"),
    ResourceDef("hazel_seeds", "Hazel seeds", "agriculture", "hz.s"),
    *_CROP_SEEDS,
]

GROUP_ORDER: tuple[str, ...] = ("food", "wares", "agriculture")
GROUP_LABELS: dict[str, str] = {
    "food": "Food",
    "wares": "Wares",
    "agriculture": "Agriculture",
    "construction": "Wares",
}

_BUILTIN_RESOURCES: tuple[ResourceDef, ...] = tuple(RESOURCES)
AUTHORED_RESOURCE_PATH = Path(__file__).resolve().parent / "resources_data" / "resources.csv"
AUTHORED_RESOURCE_HEADER = ("key", "label", "group", "short", "icon_key", "usage", "stack_size", "tool_effectiveness", "tool_targets")


def reload_authored_resources(path: Path | None = None) -> int:
    """Rebuild the runtime catalogue from built-ins plus editable CSV overrides."""
    global RESOURCE_KEYS
    RESOURCES[:] = list(_BUILTIN_RESOURCES)
    source = Path(path or AUTHORED_RESOURCE_PATH)
    if source.is_file():
        with source.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                key = str(row.get("key") or "").strip()
                if not key: continue
                entry = ResourceDef(key, str(row.get("label") or key.replace("_", " ").title()), str(row.get("group") or "wares"), str(row.get("short") or key[:4]), str(row.get("icon_key") or ""), str(row.get("usage") or "resource"), max(1, int(row.get("stack_size") or 1)), max(0.01, float(row.get("tool_effectiveness") or 1.0)), str(row.get("tool_targets") or ""))
                index = next((i for i, item in enumerate(RESOURCES) if item.key == key), None)
                if index is None: RESOURCES.append(entry)
                else: RESOURCES[index] = entry
    RESOURCE_KEYS = tuple(r.key for r in RESOURCES)
    # Modules historically imported the tuple by value. Refresh those live
    # bindings so newly authored resources appear without restarting.
    import sys
    for module_name in ("game", "inventory_ui", "resource_tracker_dialog", "developer_tools.authoring_ui", "developer_tools.content_lab"):
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, "RESOURCE_KEYS"):
            setattr(module, "RESOURCE_KEYS", RESOURCE_KEYS)
    return len(RESOURCES)


RESOURCE_KEYS: tuple[str, ...] = ()
reload_authored_resources()

# Cargo / building capacity: these keys occupy ceil(count / size) slots.
# Count stays the real amount (e.g. arrows left); UI shows that number on the icon.
STACK_SIZES: dict[str, int] = {
    "stone_arrows": 10,
}


def stack_size(key: str) -> int | None:
    authored = next((r.stack_size for r in RESOURCES if r.key == key and r.stack_size > 1), None)
    size = authored or STACK_SIZES.get(key)
    return int(size) if size else None


def stack_units(key: str, count: int) -> int:
    """Cargo slots occupied by ``count`` of ``key`` (1 per stack, or 1:1)."""
    n = max(0, int(count))
    if n <= 0:
        return 0
    size = stack_size(key)
    if size is None or size <= 1:
        return n
    return (n + size - 1) // size


def cargo_units_after_add(key: str, have: int, add: int) -> int:
    """Net cargo-slot delta when adding ``add`` items to ``have`` already stored."""
    return stack_units(key, int(have) + int(add)) - stack_units(key, have)


def items_for_stack_room(key: str, have: int, room_units: int) -> int:
    """How many items of ``key`` fit in ``room_units`` free cargo slots."""
    room = max(0, int(room_units))
    if room <= 0 and stack_size(key) is None:
        return 0
    size = stack_size(key)
    if size is None or size <= 1:
        return room
    have_n = max(0, int(have))
    fill = 0
    if have_n > 0:
        rem = have_n % size
        if rem:
            fill = size - rem
    return fill + room * size


def register_resource(
    key: str,
    *,
    label: str,
    group: str = "food",
    short: str | None = None,
    icon_key: str | None = None,
) -> None:
    """Add or replace a catalogue entry (used by recipe JSON loader)."""
    global RESOURCE_KEYS
    short_label = short or key[:4]
    icon = (icon_key or "").strip()
    entry = ResourceDef(key, label, group, short_label, icon)
    for i, existing in enumerate(RESOURCES):
        if existing.key == key:
            # Recipe metadata may update label/group/icon; keep usage/stack/tool
            # fields from any prior catalogue or CSV override.
            RESOURCES[i] = ResourceDef(
                key,
                label,
                group,
                short_label,
                icon or existing.icon_key,
                existing.usage,
                existing.stack_size,
                existing.tool_effectiveness,
                existing.tool_targets,
            )
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


FOOD_TIER_SECTION_ORDER: tuple[str, ...] = ("t0", "t1", "t2", "t3", "t4")
FOOD_TIER_SECTION_LABELS: dict[str, str] = {
    "t0": "T0 Raw",
    "t1": "T1 Fire",
    "t2": "T2 Simple",
    "t3": "T3 Kitchen",
    "t4": "T4 Feast",
}


def food_tier_section_key(resource_key: str) -> str:
    """Map a food resource to its T0–T4 panel section (recipe steps, else raw)."""
    from resource_balance import food_tier

    tier = food_tier(resource_key)
    if tier is None:
        return "t0"
    return f"t{max(0, min(4, int(tier)))}"


# Legacy catalogue rows superseded by craft outputs (meat_stew, wheat_bread, …).
_FOOD_PANEL_EXCLUDE: frozenset[str] = frozenset(
    {"stew", "fish_stew", "bread", "bread_wheat"}
)


def resources_by_food_tier() -> list[tuple[str, list[ResourceDef]]]:
    """Food catalogue split into hire/cook tiers for the stock popup."""
    buckets: dict[str, list[ResourceDef]] = {k: [] for k in FOOD_TIER_SECTION_ORDER}
    for res in RESOURCES:
        if res.group != "food":
            continue
        if res.key in _FOOD_PANEL_EXCLUDE:
            continue
        buckets.setdefault(food_tier_section_key(res.key), []).append(res)
    return [
        (FOOD_TIER_SECTION_LABELS.get(section, section), buckets[section])
        for section in FOOD_TIER_SECTION_ORDER
        if buckets.get(section)
    ]


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


def tool_effectiveness(key: str, target: str = "") -> float:
    item = next((r for r in RESOURCES if r.key == key and r.usage == "tool"), None)
    if item is None: return 1.0
    targets = {v.strip().lower() for v in item.tool_targets.replace(",", ";").split(";") if v.strip()}
    return item.tool_effectiveness if not targets or not target or target.lower() in targets else 1.0


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


def _crop_plant_style(crop, *, dense: bool = False) -> ResourceIconStyle:
    """Wild/forage-style plant glyph: stem + flower recolours from CropDef."""
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


def _soup_style(accent: tuple[int, int, int], *, body: tuple[int, int, int] = (120, 140, 70)) -> ResourceIconStyle:
    return ResourceIconStyle("vegetable_soup", {"body": body, "accent": accent})


def _stew_style(accent: tuple[int, int, int], *, body: tuple[int, int, int] = (140, 100, 70)) -> ResourceIconStyle:
    return ResourceIconStyle("stew", {"body": body, "accent": accent})


def _porridge_style(accent: tuple[int, int, int]) -> ResourceIconStyle:
    return ResourceIconStyle("porridge", {"body": (210, 190, 140), "accent": accent})


def _cooked_food_icon_style(key: str) -> ResourceIconStyle | None:
    """Distinct inventory glyphs for each craft output (not raw crop plants)."""
    from icons import ICON_FISH, ICON_MEAT_MARKER, ICON_MUSHROOM

    styles: dict[str, ResourceIconStyle] = {
        # T1 grill (roasted roots fall through to crop plant glyphs)
        "grilled_mushrooms": ResourceIconStyle(
            ICON_MUSHROOM, {"cap": (160, 100, 50), "stem": (210, 200, 180)}
        ),
        "grilled_fish": ResourceIconStyle(ICON_FISH, {"body": (200, 140, 70)}),
        "grilled_meat": ResourceIconStyle(ICON_MEAT_MARKER, {"body": (160, 90, 45)}),
        # T2 porridge / soups — each dish its own accent so they do not read as pea soup
        "barley_gruel": _porridge_style((190, 160, 90)),
        "wheat_porridge": _porridge_style((220, 190, 120)),
        "rye_porridge": _porridge_style((160, 120, 70)),
        "nettle_soup": _soup_style((70, 140, 80)),
        "pea_soup": _soup_style((150, 180, 60)),
        "potato_soup": _soup_style((210, 190, 120)),
        "bean_stew": _soup_style((140, 90, 50)),
        "pumpkin_soup": _soup_style((220, 140, 40)),
        "mushroom_soup": ResourceIconStyle(
            "mushroom_stew", {"body": (140, 100, 70), "accent": (107, 74, 46)}
        ),
        "leek_potato_soup": _soup_style((120, 170, 90)),
        "kale_soup": _soup_style((50, 110, 55)),
        # T3
        "pea_ham_soup": _stew_style((160, 100, 50)),
        "meat_stew": _stew_style((192, 96, 48)),
        "fish_soup": ResourceIconStyle(
            "fish_stew", {"body": (140, 100, 70), "accent": (64, 128, 176)}
        ),
        "root_stew": _soup_style((170, 120, 55)),
        "souper_greens": _soup_style((60, 130, 70)),
        "wheat_bread": ResourceIconStyle("bread", {"body": (210, 170, 100)}),
        "rye_bread": ResourceIconStyle("bread", {"body": (160, 110, 60)}),
        "bread": ResourceIconStyle("bread", {"body": (210, 170, 100)}),
        "berry_jam": ResourceIconStyle(
            "berry_jam", {"body": (160, 60, 90), "accent": (200, 80, 110)}
        ),
        # T4
        "mushroom_pie": ResourceIconStyle(
            "mushroom_stew", {"body": (140, 100, 70), "accent": (120, 80, 40)}
        ),
        "fish_pie": ResourceIconStyle(
            "fish_stew", {"body": (140, 100, 70), "accent": (50, 110, 160)}
        ),
        "meat_pie": _stew_style((170, 70, 40)),
        "spiced_stew": ResourceIconStyle(
            "spiced_stew", {"body": (140, 100, 70), "accent": (180, 80, 40)}
        ),
        "berry_tart": ResourceIconStyle(
            "berry_tart", {"body": (180, 120, 70), "accent": (160, 50, 90)}
        ),
        "lebkuchen": ResourceIconStyle(
            "lebkuchen", {"body": (150, 90, 50), "accent": (100, 60, 30)}
        ),
        # Legacy keys
        "stew": _stew_style((192, 96, 48)),
        "fish_stew": ResourceIconStyle(
            "fish_stew", {"body": (140, 100, 70), "accent": (64, 128, 176)}
        ),
        "mushroom_stew": ResourceIconStyle(
            "mushroom_stew", {"body": (140, 100, 70), "accent": (107, 74, 46)}
        ),
        "vegetable_soup": _soup_style((80, 140, 60)),
    }
    return styles.get(key)


def _icon_stem_style(stem: str) -> ResourceIconStyle | None:
    """Default recolour when a resource only names an icon stem."""
    stem = str(stem or "").strip()
    if not stem:
        return None
    defaults: dict[str, ResourceIconStyle] = {
        "vegetable_soup": _soup_style((80, 140, 60)),
        "stew": _stew_style((192, 96, 48)),
        "fish_stew": ResourceIconStyle(
            "fish_stew", {"body": (140, 100, 70), "accent": (64, 128, 176)}
        ),
        "mushroom_stew": ResourceIconStyle(
            "mushroom_stew", {"body": (140, 100, 70), "accent": (107, 74, 46)}
        ),
        "spiced_stew": ResourceIconStyle(
            "spiced_stew", {"body": (140, 100, 70), "accent": (180, 80, 40)}
        ),
        "porridge": _porridge_style((200, 170, 100)),
        "bread": ResourceIconStyle("bread", {"body": (210, 170, 100)}),
        "berry_jam": ResourceIconStyle(
            "berry_jam", {"body": (160, 60, 90), "accent": (200, 80, 110)}
        ),
        "berry_tart": ResourceIconStyle(
            "berry_tart", {"body": (180, 120, 70), "accent": (160, 50, 90)}
        ),
        "lebkuchen": ResourceIconStyle(
            "lebkuchen", {"body": (150, 90, 50), "accent": (100, 60, 30)}
        ),
    }
    return defaults.get(stem)


def resource_icon_style(key: str) -> ResourceIconStyle:
    """Return icon style matching map feature colours (and seed composites)."""
    # Per-key cooked styles first so CSV icon_key alone does not flatten every
    # T2 soup to the same un-recoloured vegetable_soup glyph.
    cooked = _cooked_food_icon_style(key)
    if cooked is not None:
        return cooked

    authored = next((r for r in RESOURCES if r.key == key and r.icon_key), None)
    if authored is not None:
        # Recipe/CSV stem: prefer a known style for that stem, else bare icon.
        stem_style = _icon_stem_style(authored.icon_key)
        if stem_style is not None:
            return stem_style
        from crops import CROP_BY_KEY

        crop = CROP_BY_KEY.get(authored.icon_key)
        if crop is not None:
            return _crop_plant_style(crop, dense=False)
        return ResourceIconStyle(authored.icon_key, {})
    from icons import (
        ICON_AXE,
        ICON_BERRIES,
        ICON_BREAD,
        ICON_BOW,
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
        ICON_STONE_ARROWS,
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

    if key == "coins":
        from icons import ICON_COINS

        return ResourceIconStyle(ICON_COINS, {})

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

    if key == "bow":
        return ResourceIconStyle(ICON_BOW, {})

    if key == "stone_arrows":
        return ResourceIconStyle(ICON_STONE_ARROWS, {})

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
        from icons import ICON_FISH_ROACH

        return ResourceIconStyle(ICON_FISH_ROACH, {"body": COLOUR_FISH})
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
    if key in ("blackberries", "sloe_berries", "elderberries", "hazelnuts"):
        from berry_bushes import berry_fruit_colour, berry_kind_for_seed, normalize_berry_kind
        kind = {
            "blackberries": "blackberry",
            "sloe_berries": "sloe",
            "elderberries": "elderberry",
            "hazelnuts": "hazel",
        }[key]
        return ResourceIconStyle(ICON_BERRIES, {"berry": berry_fruit_colour(kind)})
    if key == "berry_seeds":
        return ResourceIconStyle(
            ICON_SEEDS,
            {"flower": _SEED_COLOUR},
            badge_key="berries",
        )
    if key in ("blackberry_seeds", "sloe_berry_seeds", "elder_berry_seeds", "hazel_seeds"):
        from berry_bushes import berry_fruit_colour, berry_kind_for_seed
        kind = berry_kind_for_seed(key) or "blackberry"
        return ResourceIconStyle(
            ICON_SEEDS,
            {"flower": berry_fruit_colour(kind)},
            badge_key="berries",
        )
    if key == "reeds":
        return ResourceIconStyle(ICON_REED, {"stem": COLOUR_REED})

    if key == "wheat_flour":
        return ResourceIconStyle("flour_wheat", {})
    if key == "rye_flour":
        return ResourceIconStyle("flour_rye", {})

    if key == "fur":
        return ResourceIconStyle("fur", {"body": (210, 190, 170)})
    if key == "hide":
        return ResourceIconStyle("hide", {"body": (196, 168, 130)})
    if key == "leather":
        return ResourceIconStyle("leather", {"body": (139, 90, 43)})
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
    if key == "spiced_stew":
        return ResourceIconStyle(
            "spiced_stew",
            {"body": (140, 100, 70), "accent": (180, 80, 40)},
        )
    if key == "vegetable_soup":
        return ResourceIconStyle(
            "vegetable_soup",
            {"body": (120, 140, 70), "accent": (80, 140, 60)},
        )
    if key == "berry_jam":
        return ResourceIconStyle(
            "berry_jam",
            {"body": (160, 60, 90), "accent": (200, 80, 110)},
        )
    if key == "berry_tart":
        return ResourceIconStyle(
            "berry_tart",
            {"body": (180, 120, 70), "accent": (160, 50, 90)},
        )
    if key == "lebkuchen":
        return ResourceIconStyle(
            "lebkuchen",
            {"body": (150, 90, 50), "accent": (100, 60, 30)},
        )
    if key == "grilled_meat":
        # Same marker as raw meat, browned/cooked tint.
        return ResourceIconStyle(ICON_MEAT_MARKER, {"body": (160, 90, 45)})
    if key == "grilled_fish":
        return ResourceIconStyle(ICON_FISH, {"body": (200, 140, 70)})
    if key == "grilled_mushrooms":
        return ResourceIconStyle(
            ICON_MUSHROOM, {"cap": (160, 100, 50), "stem": (210, 200, 180)}
        )

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

    if key.endswith("_grain"):
        crop_key = key[: -len("_grain")]
        if crop_key in CROP_BY_KEY:
            return ResourceIconStyle(
                ICON_SEEDS,
                {"flower": _SEED_COLOUR},
                badge_key=crop_key,
            )

    crop = CROP_BY_KEY.get(key)
    if crop is None:
        # produce_key may differ from CropDef.key (e.g. orchard berries already handled).
        crop = next((c for c in CROP_BY_KEY.values() if c.produce_key == key), None)
    if crop is not None:
        # Sparse plant icon matches wild flora / diary (not field-dense canopy).
        return _crop_plant_style(crop, dense=False)

    # Wild herbs / forage (nettles, etc.) — use sparse plant recolours, not dense.
    try:
        from wild_species import WILD_SPECIES

        wild = next(
            (
                s
                for s in WILD_SPECIES
                if s.resource_key == key or s.key == key
            ),
            None,
        )
        if wild is not None and getattr(wild, "icon_base", None):
            recolour = {
                str(cls): tuple(int(c) for c in colour)  # type: ignore[misc]
                for cls, colour in (getattr(wild, "icon_recolour", ()) or ())
            }
            return ResourceIconStyle(str(wild.icon_base), recolour)
    except Exception:
        pass

    # Drop-in recipe icons: any category below assets/icons, resolved by stem.
    from icons import has_icon

    if has_icon(key):
        return ResourceIconStyle(key, {})

    # Never fall back to dense crop canopy for catalogue foods — that made every
    # unrecognised cooked dish look like a generic plant.
    if any(r.key == key and r.group == "food" for r in RESOURCES):
        return ResourceIconStyle(ICON_FLOWER, {"stem": COLOUR_TREE_CANOPY})

    try:
        return ResourceIconStyle(
            crop_icon_base(key, dense=False), {"stem": COLOUR_TREE_CANOPY}
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
        if res.key == "coins":
            # Shown as its own resource-bar chip, not rolled into Wares.
            continue
        totals[res.group] = totals.get(res.group, 0) + int(amounts.get(res.key, 0))
    return totals
