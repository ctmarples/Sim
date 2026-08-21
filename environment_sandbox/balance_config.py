"""Runtime game-balance parameters (defaults from settings; tunable in-game).

Add new entries to ``BALANCE_CATEGORIES`` to extend the balance popup.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from settings import (
    DISTURBANCE_ACTIVITY_FLOOR,
    DISTURBANCE_DECAY_PER_TICK,
    DISTURBANCE_EXTRACTION_BOOST,
    DISTURBANCE_EXTRACTION_SPREAD,
    DISTURBANCE_INTERACTION_BOOST,
    DISTURBANCE_MAX,
    DISTURBANCE_NEIGHBOUR_SPREAD,
    DISTURBANCE_PATH_LEVEL,
    DISTURBANCE_RADIUS,
    DISTURBANCE_URBAN_LEVEL,
    FOOD_SPOILAGE_DAYS,
    FOOD_SPOILAGE_CARRIED_RATE,
    INDICATOR_RADIUS,
    PATH_TRAFFIC_DECAY,
    PATH_TRAFFIC_KEEP,
    PATH_TRAFFIC_OVERLAY_MAX,
    PATH_TRAFFIC_STEP,
    PATH_TRAFFIC_THRESHOLD,
    PLAYBACK_TICKS_AT_X1,
    DAY_SECONDS_AT_X1,
    WALK_SECONDS_AT_X1,
    WORK_SECONDS_AT_X1,
    ANIMAL_MOVE_SECONDS_AT_X1,
    ANIMAL_FLEE_SECONDS_AT_X1,
    FISH_MOVE_SECONDS_AT_X1,
    RABBIT_MOVE_PAUSE_SECONDS_AT_X1,
    WOLF_SEEK_SPEED_MULT,
    WOLF_CHASE_SPEED_MULT,
    ANIMAL_WEIGHT_BIODIVERSITY,
    ANIMAL_WEIGHT_AWAY_DISTURBANCE,
    WOLF_WEIGHT_BIODIVERSITY,
    WOLF_WEIGHT_AWAY_DISTURBANCE,
    WOLF_WEIGHT_TOWARD_PREY,
    BUFF_STRENGTH_SPEED,
    BUFF_STRENGTH_HUNGER,
    BUFF_STRENGTH_WORK,
    CROP_HEALTH_MAX_DROP,
    CROP_HEALTH_MIN,
    EROSION_SLOPE_SCALE,
    FARM_PRODUCE_YIELD,
    FERTILITY_FOREST,
    FERTILITY_GRASS,
    FERTILITY_HARVEST_DROP,
    FERTILITY_MEADOW,
    FERTILITY_RIPARIAN,
    FERTILITY_ROCK,
    FERTILITY_SOIL,
    FERTILITY_WATER,
    INSECT_REPELLANT_PEST_BOOST,
    PEST_CONTROL_MULT_HIGH,
    PEST_CONTROL_MULT_LOW,
    PEST_CONTROL_MULT_MID,
    PEST_CONTROL_RICHNESS_HIGH,
    PEST_CONTROL_RICHNESS_LOW,
    PEST_CONTROL_RICHNESS_MID,
    POLLINATION_YIELD_HIGH,
    POLLINATION_YIELD_LOW,
    URBAN_MIN_BUILDINGS,
    WEED_ACTION_THRESHOLD,
    WEED_GROWTH_RATE,
    WEED_HARVEST_PENALTY,
    WEED_MAX_APPEARANCES_PER_SEASON,
    WILDLIFE_BREED_CHANCE,
    WILDLIFE_COLONY_GROW_CHANCE,
    WILDLIFE_COLONY_SPLIT_CHANCE,
    WILDLIFE_DISTURBANCE_SENSITIVITY,
    WILDLIFE_BEE_FORAGE_PER_LEVEL,
    WILDLIFE_RABBIT_FORAGE_PER_LEVEL,
    WILDLIFE_FROG_FORAGE_PER_LEVEL,
    WILDLIFE_VOLE_FORAGE_PER_LEVEL,
    WOLF_MAX_POPULATION,
    WOLF_SEED_PACKS,
    WOLF_BREED_CHANCE,
    WOLF_HUNT_BOAR_MIN,
    WOLF_HUNT_DEER_MIN,
    WOLF_HUNT_RABBIT_MIN,
    WOLF_FEED_BOAR_DAYS,
    WOLF_FEED_DEER_DAYS,
    WOLF_FEED_RABBIT_DAYS,
    WOLF_HUNT_FOX_MIN,
    WOLF_FEED_FOX_DAYS,
    FOX_MAX_POPULATION,
    FOX_SEED_PACKS,
    FOX_BREED_CHANCE,
    WEATHER_EVENT_DAYS,
    WEATHER_FREQUENCY,
    WEATHER_INTENSITY,
    WEATHER_LOCAL_VARIATION,
    WEATHER_RAIN_CELLS,
    WEATHER_CELL_RADIUS,
)
from resource_balance import VILLAGER_SATIATION_DAYS

ParamKind = Literal["float", "int"]


@dataclass(frozen=True)
class BalanceParam:
    key: str
    label: str
    kind: ParamKind
    default: float
    minimum: float
    maximum: float
    step: float
    hint: str = ""
    suffix: str = ""


@dataclass(frozen=True)
class BalanceCategory:
    id: str
    title: str
    params: tuple[BalanceParam, ...]


BALANCE_CATEGORIES: tuple[BalanceCategory, ...] = (
    BalanceCategory(
        "time",
        "Time & pace",
        (
            BalanceParam(
                "DAY_SECONDS_AT_X1",
                "Calendar day length at ×1",
                "float",
                DAY_SECONDS_AT_X1,
                1.0,
                60.0,
                1.0,
                "Real seconds for one calendar day at ×1. 1s lasts 1s; ×2 makes that day elapse in 0.5s.",
                "s",
            ),
            BalanceParam(
                "WALK_SECONDS_AT_X1",
                "Walk one tile at ×1",
                "float",
                WALK_SECONDS_AT_X1,
                0.05,
                2.0,
                0.05,
                "Real seconds to cross one tile. Lower = snappier walking.",
                "s",
            ),
            BalanceParam(
                "WORK_SECONDS_AT_X1",
                "One work action at ×1",
                "float",
                WORK_SECONDS_AT_X1,
                0.15,
                6.0,
                0.15,
                "Real seconds between chops / harvests / craft steps.",
                "s",
            ),
            BalanceParam(
                "PLAYBACK_TICKS_AT_X1",
                "Sim steps per frame at ×1",
                "int",
                float(PLAYBACK_TICKS_AT_X1),
                1,
                8,
                1,
                "Usually leave at 2. Speed buttons multiply this. Higher = more sim per displayed frame.",
            ),
        ),
    ),
    BalanceCategory(
        "weather",
        "Weather & rainfall",
        (
            BalanceParam(
                "WEATHER_EVENT_DAYS", "Rain event duration", "int",
                WEATHER_EVENT_DAYS, 1, 14, 1,
                "Number of consecutive days that a rain event keeps the same regional intensity and local rain cells.",
                " days",
            ),
            BalanceParam(
                "WEATHER_FREQUENCY", "Rain event frequency", "float",
                WEATHER_FREQUENCY, 0.0, 2.0, 0.1,
                "Multiplier on the seasonal chance of a new rain event starting. 0 disables new rain.",
                "×",
            ),
            BalanceParam(
                "WEATHER_INTENSITY", "Rain intensity", "float",
                WEATHER_INTENSITY, 0.1, 2.0, 0.1,
                "Multiplier on event strength, affecting visuals, the rainfall layer, and soil recharge.",
                "×",
            ),
            BalanceParam(
                "WEATHER_LOCAL_VARIATION", "Local intensity variation", "float",
                WEATHER_LOCAL_VARIATION, 0.0, 1.0, 0.05,
                "How strongly random rain cells separate wet and dry parts of the map. 0 is regionally uniform.",
            ),
            BalanceParam(
                "WEATHER_RAIN_CELLS", "Rain cells per event", "int",
                WEATHER_RAIN_CELLS, 1, 12, 1,
                "Number of randomly positioned areas of concentrated rain in each event.",
            ),
            BalanceParam(
                "WEATHER_CELL_RADIUS", "Rain-cell radius", "float",
                WEATHER_CELL_RADIUS, 0.05, 0.75, 0.05,
                "Approximate radius of each rain cell as a fraction of the map size.",
            ),
        ),
    ),
    BalanceCategory(
        "buffs",
        "Buffs & debuffs",
        (
            BalanceParam(
                "VILLAGER_SATIATION_DAYS",
                "Full satiation duration",
                "float",
                VILLAGER_SATIATION_DAYS,
                0.5,
                90.0,
                0.5,
                "Calendar days for satiation to fall from full to empty before a meal's hunger-rate multiplier.",
                " days",
            ),
            BalanceParam(
                "BUFF_STRENGTH_SPEED",
                "Food: walk-speed effect strength",
                "int",
                float(BUFF_STRENGTH_SPEED),
                0,
                5,
                1,
                "How hard food speed buffs/debuffs hit. Scales the gap from ×1.0 "
                "(e.g. recipe 0.8 at 3/5 → 0.7 at 4/5). 0/5 turns speed food effects off.",
                "/5",
            ),
            BalanceParam(
                "BUFF_STRENGTH_HUNGER",
                "Food: hunger-rate effect strength",
                "int",
                float(BUFF_STRENGTH_HUNGER),
                0,
                5,
                1,
                "How hard food hunger-rate buffs/debuffs hit (gap from ×1.0). "
                "0/5 turns hunger food effects off.",
                "/5",
            ),
            BalanceParam(
                "BUFF_STRENGTH_WORK",
                "Food: work-speed effect strength",
                "int",
                float(BUFF_STRENGTH_WORK),
                0,
                5,
                1,
                "How hard food work-efficiency buffs/debuffs hit (gap from ×1.0). "
                "0/5 turns work food effects off.",
                "/5",
            ),
        ),
    ),
    BalanceCategory(
        "farm",
        "Farm harvest",
        (
            BalanceParam(
                "FARM_PRODUCE_YIELD",
                "Produce from a perfect tile",
                "int",
                float(FARM_PRODUCE_YIELD),
                1,
                24,
                1,
                "Units picked from one square when every multiplier is ×1. "
                "Real harvest is this × bees × land-stress × crop health × weeds × fertility.",
            ),
            BalanceParam(
                "PEST_CONTROL_RICHNESS_LOW",
                "Wildlife count = “poor” fields",
                "float",
                PEST_CONTROL_RICHNESS_LOW,
                0.0,
                20.0,
                0.5,
                "Nearby species richness at or below this is treated as poor pest control. "
                "That slowly pulls crop health down (it does not cut the harvest number in one pick).",
            ),
            BalanceParam(
                "PEST_CONTROL_RICHNESS_MID",
                "Wildlife count = healthy fields",
                "float",
                PEST_CONTROL_RICHNESS_MID,
                0.5,
                20.0,
                0.5,
                "At this richness, pest control is “ok”: crop health can sit at 100%. "
                "Below it, health is allowed to sink toward the health floor.",
            ),
            BalanceParam(
                "PEST_CONTROL_RICHNESS_HIGH",
                "Wildlife count = best fields",
                "float",
                PEST_CONTROL_RICHNESS_HIGH,
                1.0,
                30.0,
                0.5,
                "Richness needed for the strongest pest-control rating. "
                "Does not heal fields by itself — health only stops falling when habitat is good enough.",
            ),
            BalanceParam(
                "PEST_CONTROL_MULT_LOW",
                "Pest rating when wildlife is poor",
                "float",
                PEST_CONTROL_MULT_LOW,
                0.3,
                1.5,
                0.05,
                "Pest-control score at low biodiversity. Sets how sick the health target can get "
                "(not a direct harvest multiply). Lower = fields get sicker over the year.",
            ),
            BalanceParam(
                "PEST_CONTROL_MULT_MID",
                "Pest rating for full crop health",
                "float",
                PEST_CONTROL_MULT_MID,
                0.5,
                2.0,
                0.05,
                "Pest-control score that allows 100% crop health. "
                "Raise this if you want only rich habitat to keep fields healthy.",
            ),
            BalanceParam(
                "PEST_CONTROL_MULT_HIGH",
                "Pest rating when wildlife is rich",
                "float",
                PEST_CONTROL_MULT_HIGH,
                0.8,
                2.5,
                0.05,
                "Best pest-control score at high biodiversity. Mostly diagnostic; "
                "harvest already uses crop health, not this number directly.",
            ),
            BalanceParam(
                "CROP_HEALTH_MIN",
                "Sickest a field can get",
                "float",
                CROP_HEALTH_MIN,
                0.2,
                1.0,
                0.05,
                "Crop health never falls below this (shown as % on the field). "
                "Harvest is multiplied by health, so 0.7 means at worst you keep 70% of the pick.",
            ),
            BalanceParam(
                "CROP_HEALTH_MAX_DROP",
                "How fast fields get sicker",
                "float",
                CROP_HEALTH_MAX_DROP,
                0.0,
                0.25,
                0.01,
                "Max health lost each env sample (8× per year) when pest control is poor. "
                "Health does not climb back up — only stops falling when habitat improves.",
            ),
            BalanceParam(
                "POLLINATION_YIELD_LOW",
                "Harvest with no bees",
                "float",
                POLLINATION_YIELD_LOW,
                0.4,
                1.5,
                0.05,
                "Harvest multiplier on a field with zero bee coverage. "
                "0.9 = 10% less produce than a “normal” tile before other factors.",
            ),
            BalanceParam(
                "POLLINATION_YIELD_HIGH",
                "Harvest with full bees",
                "float",
                POLLINATION_YIELD_HIGH,
                0.8,
                2.5,
                0.05,
                "Harvest multiplier at full bee coverage. "
                "1.2 = 20% more produce than a “normal” tile before other factors.",
            ),
            BalanceParam(
                "INSECT_REPELLANT_PEST_BOOST",
                "Repellant: boost to pest control",
                "float",
                INSECT_REPELLANT_PEST_BOOST,
                0.0,
                0.5,
                0.02,
                "Added to the field’s pest-control rating when repellant is applied. "
                "Helps the health target a bit; does not instantly heal the field.",
            ),
            BalanceParam(
                "FERTILITY_FOREST",
                "Starting soil: forest floor",
                "float",
                FERTILITY_FOREST,
                0.0,
                1.0,
                0.05,
                "Initial fertility (0–1) when land is forest floor. Harvest multiplies by this.",
            ),
            BalanceParam(
                "FERTILITY_MEADOW",
                "Starting soil: meadow",
                "float",
                FERTILITY_MEADOW,
                0.0,
                1.0,
                0.05,
                "Initial fertility on meadow. Harvest multiplies by this.",
            ),
            BalanceParam(
                "FERTILITY_GRASS",
                "Starting soil: grass",
                "float",
                FERTILITY_GRASS,
                0.0,
                1.0,
                0.05,
                "Initial fertility on grass. Harvest multiplies by this.",
            ),
            BalanceParam(
                "FERTILITY_SOIL",
                "Starting soil: ploughed field",
                "float",
                FERTILITY_SOIL,
                0.0,
                1.0,
                0.05,
                "Fertility after ploughing to soil. Harvests only lower it — they never raise it.",
            ),
            BalanceParam(
                "FERTILITY_RIPARIAN",
                "Starting soil: shoreline",
                "float",
                FERTILITY_RIPARIAN,
                0.0,
                1.0,
                0.05,
                "Initial fertility on riparian / bank tiles.",
            ),
            BalanceParam(
                "FERTILITY_ROCK",
                "Starting soil: rock",
                "float",
                FERTILITY_ROCK,
                0.0,
                1.0,
                0.05,
                "Usually 0 — rock does not grow crops well.",
            ),
            BalanceParam(
                "FERTILITY_WATER",
                "Starting soil: water",
                "float",
                FERTILITY_WATER,
                0.0,
                1.0,
                0.05,
                "Usually 0 — water / river tiles.",
            ),
            BalanceParam(
                "FERTILITY_HARVEST_DROP",
                "Soil lost each full harvest",
                "float",
                FERTILITY_HARVEST_DROP,
                0.0,
                0.5,
                0.05,
                "Fertility subtracted from that square when a crop is fully harvested. "
                "Higher = fields wear out faster unless you leave them fallow.",
            ),
            BalanceParam(
                "WEED_GROWTH_RATE",
                "How fast weeds fill a square",
                "float",
                WEED_GROWTH_RATE,
                0.0,
                0.5,
                0.01,
                "At fertility 1.0, weeds gain this much cover each day. "
                "Richer soil grows weeds faster.",
            ),
            BalanceParam(
                "WEED_ACTION_THRESHOLD",
                "When farmers hoe weeds",
                "float",
                WEED_ACTION_THRESHOLD,
                0.05,
                1.0,
                0.05,
                "Hoe-equipped farmers clear weeds once cover reaches this "
                "(capped at 10% so they act in the UI watch band). "
                "Lower = they spend more time weeding.",
            ),
            BalanceParam(
                "WEED_MAX_APPEARANCES_PER_SEASON",
                "Weed outbreaks per season",
                "int",
                WEED_MAX_APPEARANCES_PER_SEASON,
                0,
                8,
                1,
                "How many times weeds may start on a square each season. "
                "After clearing, they stay gone until the next season. Winter: none.",
            ),
            BalanceParam(
                "WEED_HARVEST_PENALTY",
                "Harvest lost at full weeds",
                "float",
                WEED_HARVEST_PENALTY,
                0.0,
                1.0,
                0.05,
                "At 100% weed cover, this fraction of the harvest is thrown away. "
                "0.5 = half the pick lost on a choked square.",
            ),
            BalanceParam(
                "EROSION_SLOPE_SCALE",
                "Steepness that counts as max erosion",
                "float",
                EROSION_SLOPE_SCALE,
                1.0,
                40.0,
                0.5,
                "Height-map slope mapped to 100% erosion potential. "
                "Baked into the save — change mainly affects new land / rebakes.",
            ),
        ),
    ),
    BalanceCategory(
        "paths_urban",
        "Paths & village paving",
        (
            BalanceParam(
                "PATH_TRAFFIC_STEP",
                "Foot traffic added per step",
                "float",
                PATH_TRAFFIC_STEP,
                0.25,
                4.0,
                0.25,
                "Each time a villager walks onto a cell, wear goes up by this. "
                "Higher = paths and village paving form faster (and stress fields sooner).",
            ),
            BalanceParam(
                "PATH_TRAFFIC_THRESHOLD",
                "Wear needed to turn grass into path",
                "float",
                PATH_TRAFFIC_THRESHOLD,
                1.0,
                40.0,
                0.5,
                "When wear reaches this, the tile becomes PATH. "
                "High (default) = only busy corridors; low = muddy tracks everywhere.",
            ),
            BalanceParam(
                "PATH_TRAFFIC_KEEP",
                "Wear needed to keep a path",
                "float",
                PATH_TRAFFIC_KEEP,
                0.0,
                16.0,
                0.25,
                "Path stays until wear falls below this. Higher = abandoned tracks linger longer.",
            ),
            BalanceParam(
                "PATH_TRAFFIC_DECAY",
                "How fast foot traffic fades",
                "float",
                PATH_TRAFFIC_DECAY,
                0.3,
                1.0,
                0.02,
                "Wear is multiplied by this 8× per year. "
                "0.78 keeps most wear; closer to 0.3 clears tracks quickly.",
            ),
            BalanceParam(
                "PATH_TRAFFIC_OVERLAY_MAX",
                "Wear shown as full disturbance",
                "float",
                PATH_TRAFFIC_OVERLAY_MAX,
                4.0,
                40.0,
                1.0,
                "Foot-traffic wear that maps to 100% on the disturbance overlay. "
                "Does not change path painting by itself.",
            ),
            BalanceParam(
                "URBAN_MIN_BUILDINGS",
                "Buildings before a village “core” forms",
                "int",
                float(URBAN_MIN_BUILDINGS),
                1,
                12,
                1,
                "Fewer buildings than this: only footpaths. "
                "At or above: a paved URBAN core can appear and permanently stress nearby land.",
            ),
        ),
    ),
    BalanceCategory(
        "disturbance",
        "Land stress (hurts farm yield)",
        (
            BalanceParam(
                "DISTURBANCE_RADIUS",
                "How far stress spreads to neighbours",
                "int",
                float(DISTURBANCE_RADIUS),
                0,
                5,
                1,
                "Farm ecology uses the average stress in this many cells around the tile. "
                "Larger = a busy path or village poisons a wider ring of fields.",
            ),
            BalanceParam(
                "DISTURBANCE_URBAN_LEVEL",
                "Permanent stress on village paving",
                "float",
                DISTURBANCE_URBAN_LEVEL,
                0.0,
                1.0,
                0.05,
                "Always-on land stress on URBAN tiles (does not decay). "
                "Higher = town centres permanently cut harvest on nearby fields. "
                "This is the “urban floor” — a minimum stress, not a yield bonus.",
            ),
            BalanceParam(
                "DISTURBANCE_PATH_LEVEL",
                "Permanent stress on worn paths",
                "float",
                DISTURBANCE_PATH_LEVEL,
                0.0,
                1.0,
                0.05,
                "Always-on stress on PATH tiles while they stay worn. "
                "Higher = busy routes keep hurting adjacent crops.",
            ),
            BalanceParam(
                "DISTURBANCE_EXTRACTION_BOOST",
                "Stress from harvest / hunt / fish / plough",
                "float",
                DISTURBANCE_EXTRACTION_BOOST,
                0.0,
                1.0,
                0.05,
                "Added when someone extracts from the land. Lasts longer than a footstep. "
                "Higher = working a field stresses it more.",
            ),
            BalanceParam(
                "DISTURBANCE_EXTRACTION_SPREAD",
                "Extraction stress to neighbours",
                "float",
                DISTURBANCE_EXTRACTION_SPREAD,
                0.0,
                0.5,
                0.01,
                "Fraction of an extraction hit that spills onto neighbouring cells.",
            ),
            BalanceParam(
                "DISTURBANCE_ACTIVITY_FLOOR",
                "Harvest left when land is fully stressed",
                "float",
                DISTURBANCE_ACTIVITY_FLOOR,
                0.0,
                1.0,
                0.05,
                "At maximum land stress, farm (and similar) activity still gets this fraction. "
                "0.3 ≈ only 30% ecology mult left on trashed land; raise toward 1.0 for gentler towns.",
            ),
            BalanceParam(
                "DISTURBANCE_DECAY_PER_TICK",
                "How fast stress fades each tick",
                "float",
                DISTURBANCE_DECAY_PER_TICK,
                0.0,
                0.02,
                0.0005,
                "Subtracted from cell stress every sim tick (except urban’s permanent floor). "
                "Higher = fields recover faster after traffic.",
            ),
            BalanceParam(
                "DISTURBANCE_INTERACTION_BOOST",
                "Stress from light interactions",
                "float",
                DISTURBANCE_INTERACTION_BOOST,
                0.0,
                1.0,
                0.05,
                "Small stress bump from light use (not full harvest). "
                "Usually much weaker than extraction.",
            ),
            BalanceParam(
                "DISTURBANCE_NEIGHBOUR_SPREAD",
                "Light stress to neighbours",
                "float",
                DISTURBANCE_NEIGHBOUR_SPREAD,
                0.0,
                0.5,
                0.01,
                "Fraction of light-interaction stress that spills to neighbouring cells.",
            ),
            BalanceParam(
                "DISTURBANCE_MAX",
                "Maximum land stress",
                "float",
                DISTURBANCE_MAX,
                0.1,
                2.0,
                0.1,
                "Cap on stored disturbance. Higher allows nastier hotspots before clamping.",
            ),
        ),
    ),
    BalanceCategory(
        "overlays",
        "Overlays",
        (
            BalanceParam(
                "INDICATOR_RADIUS",
                "Overlay neighbourhood size",
                "int",
                float(INDICATOR_RADIUS),
                1,
                8,
                1,
                "How many cells around a tile count for habitat / biodiversity overlays. "
                "Display only — does not change harvest math by itself.",
            ),
        ),
    ),
    BalanceCategory(
        "wildlife",
        "Wildlife",
        (
            BalanceParam(
                "ANIMAL_MOVE_SECONDS_AT_X1",
                "Deer/boar roam (sec/tile)",
                "float",
                ANIMAL_MOVE_SECONDS_AT_X1,
                0.15,
                4.0,
                0.05,
                "Wall-clock seconds for a deer or boar to step one tile at ×1 "
                "(also bee roam). Lower = faster.",
                "s",
            ),
            BalanceParam(
                "ANIMAL_FLEE_SECONDS_AT_X1",
                "Deer/boar flee (sec/tile)",
                "float",
                ANIMAL_FLEE_SECONDS_AT_X1,
                0.10,
                2.0,
                0.05,
                "Seconds per tile when deer/boar flee villagers, wolves, or a hunt scare. "
                "Defaults to villager walk pace.",
                "s",
            ),
            BalanceParam(
                "FISH_MOVE_SECONDS_AT_X1",
                "Fish swim (sec/tile)",
                "float",
                FISH_MOVE_SECONDS_AT_X1,
                0.15,
                4.0,
                0.05,
                "Wall-clock seconds for a fish to move one water tile at ×1.",
                "s",
            ),
            BalanceParam(
                "RABBIT_MOVE_PAUSE_SECONDS_AT_X1",
                "Rabbit hop pause (sec)",
                "float",
                RABBIT_MOVE_PAUSE_SECONDS_AT_X1,
                0.20,
                6.0,
                0.10,
                "Pause after each rabbit hop before the next step at ×1.",
                "s",
            ),
            BalanceParam(
                "WOLF_SEEK_SPEED_MULT",
                "Wolf hunt seek speed",
                "float",
                WOLF_SEEK_SPEED_MULT,
                1.0,
                3.0,
                0.1,
                "How much faster than deer/boar roam wolves move while seeking prey "
                "(1.5 = 50% faster).",
                "×",
            ),
            BalanceParam(
                "WOLF_CHASE_SPEED_MULT",
                "Wolf close-chase speed",
                "float",
                WOLF_CHASE_SPEED_MULT,
                1.0,
                3.0,
                0.1,
                "How much faster than deer/boar flee wolves move when close to prey.",
                "×",
            ),
            BalanceParam(
                "ANIMAL_WEIGHT_BIODIVERSITY",
                "Prey → biodiversity",
                "float",
                ANIMAL_WEIGHT_BIODIVERSITY,
                0.0,
                5.0,
                0.1,
                "How strongly deer/boar prefer higher-biodiversity tiles when roaming. "
                "0 = ignore biodiversity.",
            ),
            BalanceParam(
                "ANIMAL_WEIGHT_AWAY_DISTURBANCE",
                "Prey ← disturbance",
                "float",
                ANIMAL_WEIGHT_AWAY_DISTURBANCE,
                0.0,
                5.0,
                0.1,
                "How strongly deer/boar prefer lower-disturbance tiles when roaming. "
                "0 = ignore disturbance.",
            ),
            BalanceParam(
                "WOLF_WEIGHT_BIODIVERSITY",
                "Wolves → biodiversity",
                "float",
                WOLF_WEIGHT_BIODIVERSITY,
                0.0,
                5.0,
                0.1,
                "How strongly wolves prefer higher-biodiversity tiles (roam / fed retreat). "
                "0 = ignore.",
            ),
            BalanceParam(
                "WOLF_WEIGHT_AWAY_DISTURBANCE",
                "Wolves ← disturbance",
                "float",
                WOLF_WEIGHT_AWAY_DISTURBANCE,
                0.0,
                5.0,
                0.1,
                "How strongly wolves prefer lower-disturbance tiles when moving. 0 = ignore.",
            ),
            BalanceParam(
                "WOLF_WEIGHT_TOWARD_PREY",
                "Wolves → prey",
                "float",
                WOLF_WEIGHT_TOWARD_PREY,
                0.0,
                8.0,
                0.1,
                "How strongly wolves bias steps toward current prey while hunting. "
                "0 = equal weight among improving steps.",
            ),
            BalanceParam(
                "WILDLIFE_BREED_CHANCE",
                "Deer / boar breed chance",
                "float",
                WILDLIFE_BREED_CHANCE,
                0.05,
                1.0,
                0.05,
                "Base chance a mating pair breeds each wildlife tick, "
                "then scaled down by local disturbance.",
            ),
            BalanceParam(
                "WILDLIFE_COLONY_GROW_CHANCE",
                "Colony level-up chance",
                "float",
                WILDLIFE_COLONY_GROW_CHANCE,
                0.02,
                1.0,
                0.02,
                "Base chance a bee/rabbit colony gains a level when fed, "
                "scaled by disturbance at the nest.",
            ),
            BalanceParam(
                "WILDLIFE_COLONY_SPLIT_CHANCE",
                "Colony split chance",
                "float",
                WILDLIFE_COLONY_SPLIT_CHANCE,
                0.0,
                1.0,
                0.02,
                "Chance a max-level colony founds a new nest when space exists.",
            ),
            BalanceParam(
                "WILDLIFE_DISTURBANCE_SENSITIVITY",
                "Disturbance hurts wildlife",
                "float",
                WILDLIFE_DISTURBANCE_SENSITIVITY,
                0.0,
                3.0,
                0.1,
                "How hard land stress suppresses breed/grow. 1 = normal floor curve; "
                "higher = wildlife fades faster near paths and buildings; 0 = ignore.",
            ),
            BalanceParam(
                "WILDLIFE_BEE_FORAGE_PER_LEVEL",
                "Bee forage tiles / level",
                "int",
                float(WILDLIFE_BEE_FORAGE_PER_LEVEL),
                1,
                40,
                1,
                "A bee nest needs this many forage tiles per colony level "
                "(level 1 → N, level 4 → 4N). Below N tiles the hive is removed.",
            ),
            BalanceParam(
                "WILDLIFE_RABBIT_FORAGE_PER_LEVEL",
                "Rabbit forage tiles / level",
                "int",
                float(WILDLIFE_RABBIT_FORAGE_PER_LEVEL),
                1,
                40,
                1,
                "A warren needs this many forage tiles per colony level "
                "(level 1 → N, level 4 → 4N). Below N tiles the warren is removed.",
            ),
            BalanceParam(
                "WILDLIFE_FROG_FORAGE_PER_LEVEL",
                "Frog forage tiles / level",
                "int",
                float(WILDLIFE_FROG_FORAGE_PER_LEVEL),
                1,
                40,
                1,
                "Riparian frog colonies — lower than rabbits (thin shore strips).",
            ),
            BalanceParam(
                "WILDLIFE_VOLE_FORAGE_PER_LEVEL",
                "Vole forage tiles / level",
                "int",
                float(WILDLIFE_VOLE_FORAGE_PER_LEVEL),
                1,
                40,
                1,
                "Vole colonies on grass, meadow, and riparian.",
            ),
            BalanceParam(
                "WOLF_MAX_POPULATION",
                "Wolf population cap",
                "int",
                float(WOLF_MAX_POPULATION),
                2,
                60,
                1,
                "Maximum wolf individuals on the map across all packs.",
            ),
            BalanceParam(
                "WOLF_SEED_PACKS",
                "Starting wolf packs",
                "int",
                float(WOLF_SEED_PACKS),
                0,
                10,
                1,
                "Packs seeded on a new map (each starts as 1 male + 1 female).",
            ),
            BalanceParam(
                "WOLF_BREED_CHANCE",
                "Wolf breed chance",
                "float",
                WOLF_BREED_CHANCE,
                0.0,
                1.0,
                0.05,
                "Chance a pack with both sexes adds a pup each wildlife growth tick "
                "while under the population cap.",
            ),
            BalanceParam(
                "WOLF_HUNT_BOAR_MIN",
                "Wolves to hunt boar",
                "int",
                float(WOLF_HUNT_BOAR_MIN),
                1,
                12,
                1,
                "Minimum pack size required to kill a boar.",
            ),
            BalanceParam(
                "WOLF_HUNT_DEER_MIN",
                "Wolves to hunt deer",
                "int",
                float(WOLF_HUNT_DEER_MIN),
                1,
                12,
                1,
                "Minimum pack size required to kill a deer.",
            ),
            BalanceParam(
                "WOLF_HUNT_RABBIT_MIN",
                "Wolves to hunt rabbit",
                "int",
                float(WOLF_HUNT_RABBIT_MIN),
                1,
                12,
                1,
                "Minimum pack size required to harvest a rabbit warren level.",
            ),
            BalanceParam(
                "WOLF_FEED_BOAR_DAYS",
                "Boar feeds pack (days)",
                "float",
                WOLF_FEED_BOAR_DAYS,
                1.0,
                20.0,
                0.5,
                "Calendar days a pack stays fed after killing a boar "
                "(retreats toward high biodiversity).",
                "d",
            ),
            BalanceParam(
                "WOLF_FEED_DEER_DAYS",
                "Deer feeds pack (days)",
                "float",
                WOLF_FEED_DEER_DAYS,
                1.0,
                20.0,
                0.5,
                "Calendar days a pack stays fed after killing a deer.",
                "d",
            ),
            BalanceParam(
                "WOLF_FEED_RABBIT_DAYS",
                "Rabbit feeds pack (days)",
                "float",
                WOLF_FEED_RABBIT_DAYS,
                1.0,
                20.0,
                0.5,
                "Calendar days a pack stays fed after taking a rabbit warren level.",
                "d",
            ),
            BalanceParam(
                "WOLF_HUNT_FOX_MIN",
                "Wolves to hunt fox",
                "int",
                float(WOLF_HUNT_FOX_MIN),
                1,
                12,
                1,
                "Minimum pack size required to kill a fox.",
            ),
            BalanceParam(
                "WOLF_FEED_FOX_DAYS",
                "Fox feeds wolf pack (days)",
                "float",
                WOLF_FEED_FOX_DAYS,
                1.0,
                20.0,
                0.5,
                "Calendar days a wolf pack stays fed after killing a fox.",
                "d",
            ),
            BalanceParam(
                "FOX_MAX_POPULATION",
                "Fox population cap",
                "int",
                float(FOX_MAX_POPULATION),
                2,
                80,
                1,
                "Maximum fox individuals on the map across all packs.",
            ),
            BalanceParam(
                "FOX_SEED_PACKS",
                "Starting fox packs",
                "int",
                float(FOX_SEED_PACKS),
                0,
                10,
                1,
                "Fox packs seeded on a new map (each starts as 1 male + 1 female).",
            ),
            BalanceParam(
                "FOX_BREED_CHANCE",
                "Fox breed chance",
                "float",
                FOX_BREED_CHANCE,
                0.0,
                1.0,
                0.05,
                "Chance a fox pack with both sexes adds a pup each wildlife growth tick "
                "while under the population cap.",
            ),
        ),
    ),
    BalanceCategory(
        "food",
        "Food & spoilage",
        (
            BalanceParam(
                "FOOD_SPOILAGE_DAYS",
                "Days per spoiled item",
                "float",
                FOOD_SPOILAGE_DAYS,
                1.0,
                60.0,
                1.0,
                "Calendar days for the oldest item in a stack to spoil. The next item then starts fresh.",
                "d",
            ),
            BalanceParam(
                "FOOD_SPOILAGE_CARRIED_RATE",
                "Carried-food ageing rate",
                "float",
                FOOD_SPOILAGE_CARRIED_RATE,
                0.0,
                3.0,
                0.1,
                "Food ageing multiplier in player and villager packs. 0 pauses ageing while carried; 1 matches storage.",
                "×",
            ),
        ),
    ),
)

_PARAM_BY_KEY: dict[str, BalanceParam] = {
    p.key: p for cat in BALANCE_CATEGORIES for p in cat.params
}


@dataclass(frozen=True)
class BalancePreset:
    """Named outcome pack: reset to defaults, then apply these overrides."""

    id: str
    label: str
    hint: str
    values: dict[str, float]


# Outcome packs for quick A/B in the balance dialog (paths / farm stress / habitat).
BALANCE_PRESETS: tuple[BalancePreset, ...] = (
    BalancePreset(
        "default",
        "Default",
        "Main-route paths only; fields feel town/path stress (current settings defaults).",
        {},
    ),
    BalancePreset(
        "main_routes",
        "Main routes",
        "Even rarer path paint — only the heaviest corridors. Wear still stresses land.",
        {
            "PATH_TRAFFIC_THRESHOLD": 24.0,
            "PATH_TRAFFIC_DECAY": 0.65,
            "PATH_TRAFFIC_KEEP": 4.0,
            "PATH_TRAFFIC_OVERLAY_MAX": 9.0,
        },
    ),
    BalancePreset(
        "harsh_fields",
        "Harsh fields",
        "Paths stay sparse; farm harvest takes a harder hit from nearby disturbance.",
        {
            "PATH_TRAFFIC_THRESHOLD": 16.0,
            "PATH_TRAFFIC_DECAY": 0.70,
            "DISTURBANCE_ACTIVITY_FLOOR": 0.10,
            "DISTURBANCE_RADIUS": 4.0,
            "DISTURBANCE_URBAN_LEVEL": 0.88,
            "DISTURBANCE_PATH_LEVEL": 0.50,
            "DISTURBANCE_EXTRACTION_BOOST": 0.70,
            "PATH_TRAFFIC_OVERLAY_MAX": 8.0,
        },
    ),
    BalancePreset(
        "chill_farms",
        "Chill farms",
        "Sparse paths, but disturbance barely cuts farm yield — abundance test.",
        {
            "PATH_TRAFFIC_THRESHOLD": 16.0,
            "DISTURBANCE_ACTIVITY_FLOOR": 0.70,
            "DISTURBANCE_RADIUS": 1.0,
            "DISTURBANCE_URBAN_LEVEL": 0.55,
            "DISTURBANCE_PATH_LEVEL": 0.20,
            "CROP_HEALTH_MIN": 0.85,
            "CROP_HEALTH_MAX_DROP": 0.02,
        },
    ),
    BalancePreset(
        "muddy_map",
        "Muddy map",
        "Old sensitive paths — tracks form easily (aesthetic stress test / contrast).",
        {
            "PATH_TRAFFIC_THRESHOLD": 4.0,
            "PATH_TRAFFIC_DECAY": 0.78,
            "PATH_TRAFFIC_KEEP": 0.75,
            "PATH_TRAFFIC_OVERLAY_MAX": 12.0,
            "DISTURBANCE_ACTIVITY_FLOOR": 0.30,
            "DISTURBANCE_RADIUS": 2.0,
            "DISTURBANCE_URBAN_LEVEL": 0.72,
            "DISTURBANCE_PATH_LEVEL": 0.30,
        },
    ),
    BalancePreset(
        "habitat",
        "Habitat",
        "Sparse paths; bees and wildlife matter more for harvest and crop health.",
        {
            "PATH_TRAFFIC_THRESHOLD": 18.0,
            "DISTURBANCE_ACTIVITY_FLOOR": 0.25,
            "DISTURBANCE_RADIUS": 3.0,
            "POLLINATION_YIELD_LOW": 0.55,
            "POLLINATION_YIELD_HIGH": 1.35,
            "PEST_CONTROL_RICHNESS_MID": 6.0,
            "CROP_HEALTH_MAX_DROP": 0.08,
            "CROP_HEALTH_MIN": 0.55,
        },
    ),
)

_PRESET_BY_ID: dict[str, BalancePreset] = {p.id: p for p in BALANCE_PRESETS}


class BalanceState:
    """Mutable runtime balance values."""

    def __init__(self) -> None:
        self._values: dict[str, float] = {}
        self._autosave_path: Path | None = None
        self.reset()

    def enable_autosave(self, path: Path | str) -> None:
        """Write prefs whenever values change (and load existing prefs if present)."""
        self._autosave_path = Path(path)
        if self._autosave_path.is_file():
            self.load_dict(self._read_prefs_file())

    def _read_prefs_file(self) -> dict[str, float]:
        import json

        if self._autosave_path is None or not self._autosave_path.is_file():
            return {}
        try:
            raw = json.loads(self._autosave_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if isinstance(raw, dict) and isinstance(raw.get("values"), dict):
            raw = raw["values"]
        if not isinstance(raw, dict):
            return {}
        out: dict[str, float] = {}
        for key, value in raw.items():
            try:
                out[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
        return out

    def _autosave(self) -> None:
        if self._autosave_path is None:
            return
        import json

        try:
            self._autosave_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"values": self.to_dict()}
            self._autosave_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass

    def to_dict(self) -> dict[str, float]:
        return {k: float(v) for k, v in self._values.items()}

    def load_dict(self, data: dict[str, float] | None) -> None:
        """Apply saved values onto defaults (unknown keys ignored)."""
        self._values = {p.key: float(p.default) for p in _PARAM_BY_KEY.values()}
        if data:
            for key, value in data.items():
                if key in _PARAM_BY_KEY:
                    try:
                        self.set(key, float(value), autosave=False)
                    except (TypeError, ValueError):
                        continue
        self._autosave()

    def reset(self) -> None:
        self._values = {p.key: float(p.default) for p in _PARAM_BY_KEY.values()}
        self._autosave()

    def reset_category(self, category_id: str) -> None:
        for cat in BALANCE_CATEGORIES:
            if cat.id != category_id:
                continue
            for p in cat.params:
                self._values[p.key] = float(p.default)
            self._autosave()
            return

    def apply_preset(self, preset_id: str) -> str:
        """Reset to defaults, apply preset overrides. Returns the preset label."""
        preset = _PRESET_BY_ID.get(preset_id)
        if preset is None:
            self.reset()
            return "Default"
        # Avoid double autosave from reset + sets.
        self._values = {p.key: float(p.default) for p in _PARAM_BY_KEY.values()}
        for key, value in preset.values.items():
            if key in _PARAM_BY_KEY:
                self.set(key, value, autosave=False)
        self._autosave()
        return preset.label

    def param(self, key: str) -> BalanceParam:
        return _PARAM_BY_KEY[key]

    def get(self, key: str) -> float:
        return float(self._values[key])

    def get_int(self, key: str) -> int:
        return int(round(self.get(key)))

    def get_float(self, key: str) -> float:
        return self.get(key)

    def set(self, key: str, value: float, *, autosave: bool = True) -> None:
        spec = self.param(key)
        clamped = max(spec.minimum, min(spec.maximum, float(value)))
        if spec.kind == "int":
            clamped = float(int(round(clamped)))
        self._values[key] = clamped
        if autosave:
            self._autosave()

    def adjust(self, key: str, delta: float) -> None:
        spec = self.param(key)
        self.set(key, self.get(key) + delta * spec.step)


_active: BalanceState | None = None


def set_active_balance(state: BalanceState) -> None:
    global _active
    _active = state


def active_balance() -> BalanceState:
    global _active
    if _active is None:
        _active = BalanceState()
    return _active
