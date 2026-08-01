"""Crop catalogue: wild & farmed plants, seasons, and seed rates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from seasons import SEASON_ORDER, Season
from settings import Colour


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

# Map overlay tints for seasonal plan indicators (RGB).
PHASE_COLOURS: dict[SeasonPhase, Colour] = {
    SeasonPhase.FALLOW: (90, 90, 90),
    SeasonPhase.GROW: (70, 130, 200),
    SeasonPhase.HARVEST: (210, 170, 50),
    SeasonPhase.PLOUGH_PLANT: (140, 100, 50),
    SeasonPhase.HARVEST_PLOUGH_PLANT: (180, 120, 40),
}


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


WILD_SEED_CHANCE: float = 1.0 / 3.0
FARM_SEED_AMOUNTS: tuple[int, ...] = (1, 2, 3)


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
        seed_key="wheat_seeds",
        short="wht",
        stem_colour=(200, 170, 55),
        flower_colour=None,
        plant_season=Season.AUTUMN,
        harvest_seasons=(Season.AUTUMN,),
        growth_days=84,  # autumn plant → autumn harvest (W+Sp+Su grow)
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
    ),
    CropDef(
        key="hemp",
        label="Hemp",
        produce_key="hemp",
        seed_key="hemp_seeds",
        short="hmp",
        stem_colour=(60, 140, 55),
        flower_colour=None,
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
)

CROP_BY_KEY: dict[str, CropDef] = {c.key: c for c in CROPS}
CROP_KEYS: tuple[str, ...] = tuple(c.key for c in CROPS)
PRODUCE_KEYS: tuple[str, ...] = tuple(c.produce_key for c in CROPS)
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


def calendar_label(crop: CropDef) -> str:
    """Compact S_S_A_W calendar string for UI."""
    parts = [PHASE_LABELS[p] for p in crop.year_phases]
    return " · ".join(parts)
