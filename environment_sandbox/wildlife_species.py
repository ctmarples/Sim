"""Central catalogue for wildlife (animals, colonies, packs, fish).

Edit ``WILDLIFE_SPECIES`` to add or tune a species — icons (SVG bases under
``assets/icons/``), fish spawn/yield, and display labels.

Runtime kinds still use ``AnimalKind`` / ``FishKind`` enums in ``wildlife.py``
(behaviour, habitats, hunting). Keep ``key`` equal to the enum member name
(e.g. ``DEER``, ``CARP``). New behaviour still needs a matching enum entry and
logic hooks; this file owns the art + fish catch table.
"""

from __future__ import annotations

from dataclasses import dataclass


Colour = tuple[int, int, int]


@dataclass(frozen=True)
class WildlifeSpeciesDef:
    key: str
    label: str
    # forest | colony | pack | fish
    group: str
    # Unisex / roaming member icon (bee, rabbit, fish fallback).
    icon: str = ""
    icon_male: str = ""
    icon_female: str = ""
    # Directional icons (hawks / owls).
    icon_left: str = ""
    icon_right: str = ""
    # Colony nest marker (bee_hive, burrow).
    nest_icon: str = ""
    # Optional SVG ``body`` recolour (deer / boar). None = native SVG colours.
    body_colour: Colour | None = None
    # Added to body_colour for females when body_colour is set.
    female_body_boost: Colour = (28, 18, 22)

    # --- Fish catch ------------------------------------------------------
    spawn_weight: int = 0
    yield_amount: int = 0
    resource_key: str = ""


WILDLIFE_SPECIES: tuple[WildlifeSpeciesDef, ...] = (
    # --- BIRDS ---------------------------------------------------------
    WildlifeSpeciesDef(
        key="OWL",
        label="Owl",
        group="bird",
        icon_left="owl_left",
        icon_right="owl_right",
        nest_icon="bird_nest",
    ),
    WildlifeSpeciesDef(
        key="HAWK",
        label="Hawk",
        group="bird",
        icon_left="hawk_left",
        icon_right="hawk_right",
        nest_icon="bird_nest",
    ),
    # --- Forest roamers --------------------------------------------------
    WildlifeSpeciesDef(
        key="DEER",
        label="Deer",
        group="forest",
        icon_male="deer_male",
        icon_female="deer_female",
        body_colour=(160, 100, 60),
    ),
    WildlifeSpeciesDef(
        key="BOAR",
        label="Boar",
        group="forest",
        icon_male="boar_male",
        icon_female="boar_female",
        body_colour=(90, 70, 55),
    ),
    # --- Colonies --------------------------------------------------------
    WildlifeSpeciesDef(
        key="BEE",
        label="Bee",
        group="colony",
        icon="bee",
        nest_icon="bee_hive",
        resource_key="honey",
    ),
    WildlifeSpeciesDef(
        key="RABBIT",
        label="Rabbit",
        group="colony",
        icon="rabbit",
        nest_icon="burrow",
    ),
    WildlifeSpeciesDef(
        key="VOLE",
        label="Vole",
        group="colony",
        icon="vole",
        nest_icon="burrow",
    ),
    WildlifeSpeciesDef(
        key="FROG",
        label="Frog",
        group="colony",
        icon="frog",
        nest_icon="burrow",
    ),
    # --- Packs -----------------------------------------------------------
    WildlifeSpeciesDef(
        key="WOLF",
        label="Wolf",
        group="pack",
        icon_male="wolf_male",
        icon_female="wolf_female",
    ),
    WildlifeSpeciesDef(
        key="FOX",
        label="Fox",
        group="pack",
        icon_male="fox_male",
        icon_female="fox_female",
    ),
    # --- Fish ------------------------------------------------------------
    WildlifeSpeciesDef(
        key="CARP",
        label="Carp",
        group="fish",
        icon="fish_carp",
        spawn_weight=2,
        yield_amount=3,
        resource_key="fish",
    ),
    WildlifeSpeciesDef(
        key="PERCH",
        label="Perch",
        group="fish",
        icon="fish_perch",
        spawn_weight=3,
        yield_amount=2,
        resource_key="fish",
    ),
    WildlifeSpeciesDef(
        key="PIKE",
        label="Pike",
        group="fish",
        icon="fish_pike",
        spawn_weight=1,
        yield_amount=4,
        resource_key="fish",
    ),
    WildlifeSpeciesDef(
        key="ROACH",
        label="Roach",
        group="fish",
        icon="fish_roach",
        spawn_weight=4,
        yield_amount=1,
        resource_key="fish",
    ),
)

WILDLIFE_BY_KEY: dict[str, WildlifeSpeciesDef] = {s.key: s for s in WILDLIFE_SPECIES}


def species_in_group(group: str) -> tuple[WildlifeSpeciesDef, ...]:
    return tuple(s for s in WILDLIFE_SPECIES if s.group == group)


def resolve_wildlife(key: str | None) -> WildlifeSpeciesDef | None:
    if not key:
        return None
    return WILDLIFE_BY_KEY.get(str(key).upper())


def bird_icon_for(key: str, *, facing_right: bool = True) -> str:
    """SVG base for a directional bird (hawk / owl)."""
    s = resolve_wildlife(key)
    if s is None:
        return ""
    if facing_right and s.icon_right:
        return s.icon_right
    if not facing_right and s.icon_left:
        return s.icon_left
    return s.icon_right or s.icon_left or s.icon or s.icon_male or s.icon_female


def animal_icon_for(key: str, *, female: bool = False) -> str:
    """SVG base for a land animal / pack member."""
    s = resolve_wildlife(key)
    if s is None:
        return ""
    if female and s.icon_female:
        return s.icon_female
    if not female and s.icon_male:
        return s.icon_male
    return s.icon or s.icon_male or s.icon_female


def nest_icon_for(key: str) -> str:
    s = resolve_wildlife(key)
    return s.nest_icon if s is not None else ""


def member_icon_for(key: str) -> str:
    """Colony wanderer icon (bee / rabbit)."""
    s = resolve_wildlife(key)
    if s is None:
        return ""
    return s.icon or s.icon_male or s.icon_female


def body_colour_for(key: str, *, female: bool = False) -> Colour | None:
    s = resolve_wildlife(key)
    if s is None or s.body_colour is None:
        return None
    if not female:
        return s.body_colour
    br, bg, bb = s.female_body_boost
    r, g, b = s.body_colour
    return (min(255, r + br), min(255, g + bg), min(255, b + bb))


def fish_icon_name(key: str) -> str:
    s = resolve_wildlife(key)
    if s is None or s.group != "fish":
        return "fish_roach"
    return s.icon or "fish_roach"


def fish_yield_amount(key: str) -> int:
    s = resolve_wildlife(key)
    if s is None:
        return 1
    return max(1, int(s.yield_amount))


def fish_spawn_weight_table() -> dict[str, int]:
    return {
        s.key: max(0, int(s.spawn_weight))
        for s in WILDLIFE_SPECIES
        if s.group == "fish"
    }


def fish_yield_table() -> dict[str, int]:
    return {
        s.key: max(1, int(s.yield_amount))
        for s in WILDLIFE_SPECIES
        if s.group == "fish"
    }


def max_fish_yield() -> int:
    yields = [int(s.yield_amount) for s in WILDLIFE_SPECIES if s.group == "fish"]
    return max(yields) if yields else 1
