"""Crop catalogue: wild & farmed plants, seasons, and growth.

Seed drop defaults (``WILD_SEED_CHANCE``, ``FARM_SEED_AMOUNTS``) live in
``resource_balance`` and are re-exported here for convenience.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from seasons import SEASON_ORDER, Season
from settings import Colour
from resource_balance import FARM_SEED_AMOUNTS, WILD_SEED_CHANCE


class SeasonPhase(Enum):
    """What a crop plan needs during one season of the year."""

    FALLOW = auto()
    GROW = auto()
    HARVEST = auto()
    PLOUGH_PLANT = auto()  # plough then sow this season
    HARVEST_PLOUGH_PLANT = auto()  # harvest ripe crop, then plough & sow next


PHASE_LABELS: dict[SeasonPhase, str] = {
    SeasonPhase.FALLOW: "Fallow",
    SeasonPhase.GROW: "Grow",
    SeasonPhase.HARVEST: "Harvest",
    SeasonPhase.PLOUGH_PLANT: "Plough/Plant",
    SeasonPhase.HARVEST_PLOUGH_PLANT: "Harvest/Plough/Plant",
}

PHASE_SHORT: dict[SeasonPhase, str] = {
    SeasonPhase.FALLOW: "—",
    SeasonPhase.GROW: "G",
    SeasonPhase.HARVEST: "H",
    SeasonPhase.PLOUGH_PLANT: "P",
    SeasonPhase.HARVEST_PLOUGH_PLANT: "H/P",
}

# Map overlay tints for seasonal plan indicators (RGB).
PHASE_COLOURS: dict[SeasonPhase, Colour] = {
    SeasonPhase.FALLOW: (90, 90, 90),
    SeasonPhase.GROW: (70, 140, 80),
    SeasonPhase.HARVEST: (210, 170, 50),
    SeasonPhase.PLOUGH_PLANT: (140, 100, 50),
    SeasonPhase.HARVEST_PLOUGH_PLANT: (180, 120, 40),
}

# Plan-mode cell backgrounds (plant / grow / harvest).
PLAN_COLOUR_PLANT: Colour = (140, 100, 50)  # brown — sowing
PLAN_COLOUR_GROW: Colour = (70, 140, 80)  # green — growing
PLAN_COLOUR_HARVEST: Colour = (210, 170, 50)  # golden — harvest


@dataclass(frozen=True)
class CropDef:
    key: str
    label: str
    produce_key: str
    seed_key: str
    short: str
    stem_colour: Colour
    flower_colour: Colour | None
    plant_season: Season
    harvest_seasons: tuple[Season, ...]
    # Growth duration in in-game days (converted to ticks by callers).
    growth_days: int
    wild_seed_chance: float  # forage: chance of 1 seed (default 1/3)
    # Farm harvest always yields a random amount from farm_seed_amounts.
    farm_seed_amounts: tuple[int, ...]
    # Year cycle S→S→A→W (Spring, Summer, Autumn, Winter).
    year_phases: tuple[SeasonPhase, SeasonPhase, SeasonPhase, SeasonPhase]
    # Icon folder base: crop_plant / flower_plant (dense → ``{base}_dense``).
    icon_base: str = "crop_plant"
    # Optional fertility delta applied on harvest/fallow once rotation effects exist.
    # None = not defined yet (UI shows projection only when set).
    fertility_effect: float | None = None

    def plant_icon(self, *, dense: bool = False) -> str:
        return f"{self.icon_base}_dense" if dense else self.icon_base


# Seed drop defaults: imported from resource_balance (re-exported for callers).


def _phases(
    spring: SeasonPhase,
    summer: SeasonPhase,
    autumn: SeasonPhase,
    winter: SeasonPhase,
) -> tuple[SeasonPhase, SeasonPhase, SeasonPhase, SeasonPhase]:
    return (spring, summer, autumn, winter)


CROPS: tuple[CropDef, ...] = (
    CropDef(
        key="wheat",
        label="Wheat",
        produce_key="wheat",
        seed_key="wheat_grain",
        short="wht",
        stem_colour=(200, 170, 55),
        flower_colour=None,
        plant_season=Season.AUTUMN,
        harvest_seasons=(Season.AUTUMN,),
        growth_days=112,  # autumn plant → next autumn harvest (full year)
        wild_seed_chance=WILD_SEED_CHANCE,
        farm_seed_amounts=FARM_SEED_AMOUNTS,
        # S_S_A_W: Grow · Grow · Harvest/Plough/Plant · Grow
        year_phases=_phases(
            SeasonPhase.GROW,
            SeasonPhase.GROW,
            SeasonPhase.HARVEST_PLOUGH_PLANT,
            SeasonPhase.GROW,
        ),
    ),
    CropDef(
        key="flax",
        label="Flax",
        produce_key="flax",
        seed_key="flax_seeds",
        short="flx",
        stem_colour=(90, 150, 70),
        flower_colour=(150, 90, 190),
        plant_season=Season.SPRING,
        harvest_seasons=(Season.SUMMER,),
        growth_days=32,
        wild_seed_chance=WILD_SEED_CHANCE,
        farm_seed_amounts=FARM_SEED_AMOUNTS,
        # S_S_A_W: Plough/Plant · Harvest · Fallow · Fallow
        year_phases=_phases(
            SeasonPhase.PLOUGH_PLANT,
            SeasonPhase.HARVEST,
            SeasonPhase.FALLOW,
            SeasonPhase.FALLOW,
        ),
        icon_base="flower_plant",
    ),
    CropDef(
        key="sage",
        label="Sage",
        produce_key="sage",
        seed_key="sage_seeds",
        short="sag",
        stem_colour=(80, 140, 90),
        flower_colour=(70, 110, 200),
        plant_season=Season.SPRING,
        harvest_seasons=(Season.SUMMER,),
        growth_days=32,
        wild_seed_chance=WILD_SEED_CHANCE,
        farm_seed_amounts=FARM_SEED_AMOUNTS,
        year_phases=_phases(
            SeasonPhase.PLOUGH_PLANT,
            SeasonPhase.HARVEST,
            SeasonPhase.FALLOW,
            SeasonPhase.FALLOW,
        ),
        icon_base="flower_plant",
    ),
    CropDef(
        key="mint",
        label="Mint",
        produce_key="mint",
        seed_key="mint_seeds",
        short="mnt",
        stem_colour=(50, 160, 100),
        flower_colour=(180, 240, 200),
        plant_season=Season.SPRING,
        harvest_seasons=(Season.SUMMER,),
        growth_days=32,
        wild_seed_chance=WILD_SEED_CHANCE,
        farm_seed_amounts=FARM_SEED_AMOUNTS,
        year_phases=_phases(
            SeasonPhase.PLOUGH_PLANT,
            SeasonPhase.HARVEST,
            SeasonPhase.FALLOW,
            SeasonPhase.FALLOW,
        ),
        icon_base="flower_plant",
    ),
    CropDef(
        key="hemp",
        label="Hemp",
        produce_key="hemp",
        seed_key="hemp_seeds",
        short="hmp",
        stem_colour=(60, 140, 55),
        flower_colour=(170, 220, 110),  # light green blooms
        plant_season=Season.SPRING,
        harvest_seasons=(Season.SUMMER,),
        growth_days=32,
        wild_seed_chance=WILD_SEED_CHANCE,
        farm_seed_amounts=FARM_SEED_AMOUNTS,
        year_phases=_phases(
            SeasonPhase.PLOUGH_PLANT,
            SeasonPhase.HARVEST,
            SeasonPhase.FALLOW,
            SeasonPhase.FALLOW,
        ),
        icon_base="flower_plant",
    ),
    CropDef(
        key="rye",
        label="Rye",
        produce_key="rye",
        seed_key="rye_grain",
        short="rye",
        stem_colour=(170, 140, 70),
        flower_colour=None,
        plant_season=Season.AUTUMN,
        harvest_seasons=(Season.SPRING,),
        growth_days=56,  # autumn plant → spring harvest (W grow)
        wild_seed_chance=WILD_SEED_CHANCE,
        farm_seed_amounts=FARM_SEED_AMOUNTS,
        # S_S_A_W: Harvest · Fallow · Plough/Plant · Grow
        year_phases=_phases(
            SeasonPhase.HARVEST,
            SeasonPhase.FALLOW,
            SeasonPhase.PLOUGH_PLANT,
            SeasonPhase.GROW,
        ),
    ),
    CropDef(
        key="onion",
        label="Onion",
        produce_key="onion",
        seed_key="onion_seeds",
        short="oni",
        stem_colour=(100, 160, 70),
        flower_colour=(220, 200, 90),
        plant_season=Season.SPRING,
        harvest_seasons=(Season.SUMMER,),
        growth_days=32,
        wild_seed_chance=WILD_SEED_CHANCE,
        farm_seed_amounts=FARM_SEED_AMOUNTS,
        year_phases=_phases(
            SeasonPhase.PLOUGH_PLANT,
            SeasonPhase.HARVEST,
            SeasonPhase.FALLOW,
            SeasonPhase.FALLOW,
        ),
    ),
    CropDef(
        key="cabbage",
        label="Cabbage",
        produce_key="cabbage",
        seed_key="cabbage_seeds",
        short="cab",
        stem_colour=(70, 150, 80),
        flower_colour=None,
        plant_season=Season.SUMMER,
        harvest_seasons=(Season.AUTUMN,),
        growth_days=32,
        wild_seed_chance=WILD_SEED_CHANCE,
        farm_seed_amounts=FARM_SEED_AMOUNTS,
        # S_S_A_W: Fallow · Plough/Plant · Harvest · Fallow
        year_phases=_phases(
            SeasonPhase.FALLOW,
            SeasonPhase.PLOUGH_PLANT,
            SeasonPhase.HARVEST,
            SeasonPhase.FALLOW,
        ),
    ),
    CropDef(
        key="carrot",
        label="Carrot",
        produce_key="carrot",
        seed_key="carrot_seeds",
        short="crt",
        stem_colour=(80, 140, 55),
        flower_colour=(220, 120, 40),
        plant_season=Season.WINTER,
        harvest_seasons=(Season.SUMMER,),
        growth_days=56,  # winter plant → summer harvest (Sp grow)
        wild_seed_chance=WILD_SEED_CHANCE,
        farm_seed_amounts=FARM_SEED_AMOUNTS,
        # S_S_A_W: Grow · Harvest · Fallow · Plough/Plant
        year_phases=_phases(
            SeasonPhase.GROW,
            SeasonPhase.HARVEST,
            SeasonPhase.FALLOW,
            SeasonPhase.PLOUGH_PLANT,
        ),
    ),
    CropDef(
        key="garlic",
        label="Garlic",
        produce_key="garlic",
        seed_key="garlic_seeds",
        short="gar",
        stem_colour=(110, 150, 80),
        flower_colour=(230, 230, 210),
        plant_season=Season.AUTUMN,
        harvest_seasons=(Season.SUMMER,),
        growth_days=80,
        wild_seed_chance=WILD_SEED_CHANCE,
        farm_seed_amounts=FARM_SEED_AMOUNTS,
        # S_S_A_W: Grow · Harvest · Plough/Plant · Grow
        year_phases=_phases(
            SeasonPhase.GROW,
            SeasonPhase.HARVEST,
            SeasonPhase.PLOUGH_PLANT,
            SeasonPhase.GROW,
        ),
    ),
)

CROP_BY_KEY: dict[str, CropDef] = {c.key: c for c in CROPS}
CROP_KEYS: tuple[str, ...] = tuple(c.key for c in CROPS)
PRODUCE_KEYS: tuple[str, ...] = tuple(dict.fromkeys(c.produce_key for c in CROPS))
SEED_KEYS: tuple[str, ...] = tuple(c.seed_key for c in CROPS)

# Legacy save migration: generic herbs → sage.
LEGACY_HERB_PRODUCE = "sage"
LEGACY_HERB_SEED = "sage_seeds"


def crop_for_season(season: Season) -> tuple[CropDef, ...]:
    return tuple(c for c in CROPS if c.plant_season == season)


def growth_ticks_for(crop: CropDef, ticks_per_day: int) -> int:
    return max(1, crop.growth_days * ticks_per_day)


def phase_for_crop(crop: CropDef, season: Season) -> SeasonPhase:
    idx = SEASON_ORDER.index(season)
    return crop.year_phases[idx]


def phase_allows_harvest(phase: SeasonPhase) -> bool:
    return phase in (SeasonPhase.HARVEST, SeasonPhase.HARVEST_PLOUGH_PLANT)


def phase_allows_plough_plant(phase: SeasonPhase) -> bool:
    return phase in (SeasonPhase.PLOUGH_PLANT, SeasonPhase.HARVEST_PLOUGH_PLANT)


def grow_seasons(crop: CropDef) -> frozenset[Season]:
    """Seasons when the crop is actively growing (not plant/harvest/fallow)."""
    return frozenset(
        season
        for season, phase in zip(SEASON_ORDER, crop.year_phases)
        if phase == SeasonPhase.GROW
    )


def grow_periods_overlap(a: CropDef, b: CropDef) -> bool:
    return bool(grow_seasons(a) & grow_seasons(b))


def _phase_wants_plant(phase: SeasonPhase) -> bool:
    return phase in (SeasonPhase.PLOUGH_PLANT, SeasonPhase.HARVEST_PLOUGH_PLANT)


def _phase_wants_harvest(phase: SeasonPhase) -> bool:
    return phase in (SeasonPhase.HARVEST, SeasonPhase.HARVEST_PLOUGH_PLANT)


def _phase_wants_grow(phase: SeasonPhase) -> bool:
    return phase == SeasonPhase.GROW


def schedules_conflict(a: CropDef, b: CropDef) -> bool:
    """True if two crops cannot share the same field cells in a year.

    Harvest + plant in the same season is allowed (rotation). Conflicting plant,
    harvest, or grow claims in the same season are not.
    """
    if a.key == b.key:
        return True  # same crop: treat as redraw/replace
    for season in SEASON_ORDER:
        pa = phase_for_crop(a, season)
        pb = phase_for_crop(b, season)
        if _phase_wants_grow(pa) and pb != SeasonPhase.FALLOW:
            return True
        if _phase_wants_grow(pb) and pa != SeasonPhase.FALLOW:
            return True
        if _phase_wants_plant(pa) and _phase_wants_plant(pb):
            return True
        if _phase_wants_harvest(pa) and _phase_wants_harvest(pb):
            return True
    return False


def calendar_label(crop: CropDef) -> str:
    """Compact S_S_A_W calendar string for UI."""
    parts = [PHASE_LABELS[p] for p in crop.year_phases]
    return " · ".join(parts)
