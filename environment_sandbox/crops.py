"""Crop catalogue: wild & farmed plants, seasons, and seed rates."""

from __future__ import annotations

from dataclasses import dataclass

from seasons import Season
from settings import Colour


@dataclass(frozen=True)
class CropDef:
    key: str
    label: str
    produce_key: str
    seed_key: str
    short: str
    stem_colour: Colour
    flower_colour: Colour | None
    # Wheat: golden stems, no flower. Flax: purple flower. Sage: blue. Hemp: green only.
    plant_season: Season
    harvest_seasons: tuple[Season, ...]
    # Growth duration in in-game days (converted to ticks by callers).
    growth_days: int
    wild_seed_chance: float
    farm_seed_chance: float


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
        harvest_seasons=(Season.SUMMER,),
        growth_days=90,  # autumn → following summer
        wild_seed_chance=0.06,
        farm_seed_chance=0.55,
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
        wild_seed_chance=0.08,
        farm_seed_chance=0.55,
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
        wild_seed_chance=0.08,
        farm_seed_chance=0.55,
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
        wild_seed_chance=0.08,
        farm_seed_chance=0.55,
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
