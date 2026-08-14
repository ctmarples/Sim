"""Runtime game-balance parameters (defaults from settings; tunable in-game).

Add new entries to ``BALANCE_CATEGORIES`` to extend the balance popup.
"""

from __future__ import annotations

from dataclasses import dataclass
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
)

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
        "buffs",
        "Buffs & debuffs",
        (
            BalanceParam(
                "BUFF_STRENGTH_SPEED",
                "Speed",
                "int",
                float(BUFF_STRENGTH_SPEED),
                0,
                5,
                1,
                "Scales the gap from 1.0. Recipe 0.8 at 3/5 becomes 0.7 at 4/5; 1.2 becomes 1.3. 0/5 turns them off.",
                "/5",
            ),
            BalanceParam(
                "BUFF_STRENGTH_HUNGER",
                "Hunger",
                "int",
                float(BUFF_STRENGTH_HUNGER),
                0,
                5,
                1,
                "Scales the gap from 1.0 on food hunger-rate. Shown to one decimal. 0/5 turns them off.",
                "/5",
            ),
            BalanceParam(
                "BUFF_STRENGTH_WORK",
                "Work efficiency",
                "int",
                float(BUFF_STRENGTH_WORK),
                0,
                5,
                1,
                "Scales the gap from 1.0 on food work efficiency. Shown to one decimal. 0/5 turns them off.",
                "/5",
            ),
        ),
    ),
    BalanceCategory(
        "farm",
        "Farm & fields",
        (
            BalanceParam(
                "FARM_PRODUCE_YIELD",
                "Base harvest per tile",
                "int",
                float(FARM_PRODUCE_YIELD),
                1,
                24,
                1,
                "Produce units at ×1.0 pest, health, pollination, and ecology.",
            ),
            BalanceParam(
                "PEST_CONTROL_RICHNESS_LOW",
                "Bio richness (poor)",
                "float",
                PEST_CONTROL_RICHNESS_LOW,
                0.0,
                20.0,
                0.5,
                "Species count treated as poor pest control.",
            ),
            BalanceParam(
                "PEST_CONTROL_RICHNESS_MID",
                "Bio richness (ok)",
                "float",
                PEST_CONTROL_RICHNESS_MID,
                0.5,
                20.0,
                0.5,
                "Species count for ×1.0 pest control and full health cap.",
            ),
            BalanceParam(
                "PEST_CONTROL_RICHNESS_HIGH",
                "Bio richness (rich)",
                "float",
                PEST_CONTROL_RICHNESS_HIGH,
                1.0,
                30.0,
                0.5,
                "Species count that reaches the best pest-control multiplier.",
            ),
            BalanceParam(
                "PEST_CONTROL_MULT_LOW",
                "Pest yield at poor bio",
                "float",
                PEST_CONTROL_MULT_LOW,
                0.3,
                1.5,
                0.05,
                "Harvest multiplier at low biodiversity. Also the health-cap floor.",
            ),
            BalanceParam(
                "PEST_CONTROL_MULT_MID",
                "Pest yield at ok bio",
                "float",
                PEST_CONTROL_MULT_MID,
                0.5,
                2.0,
                0.05,
                "Harvest multiplier at mid biodiversity. Health cap is 100% at or above this.",
            ),
            BalanceParam(
                "PEST_CONTROL_MULT_HIGH",
                "Pest yield at rich bio",
                "float",
                PEST_CONTROL_MULT_HIGH,
                0.8,
                2.5,
                0.05,
                "Harvest multiplier at high biodiversity.",
            ),
            BalanceParam(
                "CROP_HEALTH_MIN",
                "Crop health floor",
                "float",
                CROP_HEALTH_MIN,
                0.2,
                1.0,
                0.05,
                "Health never drops below this. Shown as a percent on the field.",
            ),
            BalanceParam(
                "CROP_HEALTH_MAX_DROP",
                "Health drop per sample",
                "float",
                CROP_HEALTH_MAX_DROP,
                0.0,
                0.25,
                0.01,
                "Max health lost each env sample (8× per year) when pest control is poor. Health does not recover.",
            ),
            BalanceParam(
                "POLLINATION_YIELD_LOW",
                "Pollination yield (none)",
                "float",
                POLLINATION_YIELD_LOW,
                0.4,
                1.5,
                0.05,
                "Harvest multiplier with no bee coverage.",
            ),
            BalanceParam(
                "POLLINATION_YIELD_HIGH",
                "Pollination yield (full)",
                "float",
                POLLINATION_YIELD_HIGH,
                0.8,
                2.5,
                0.05,
                "Harvest multiplier at full bee coverage.",
            ),
            BalanceParam(
                "INSECT_REPELLANT_PEST_BOOST",
                "Repellant pest boost",
                "float",
                INSECT_REPELLANT_PEST_BOOST,
                0.0,
                0.5,
                0.02,
                "Added to pest-control yield when applied on a field. Does not raise the health cap.",
            ),
            BalanceParam(
                "FERTILITY_FOREST",
                "Fertility: forest",
                "float",
                FERTILITY_FOREST,
                0.0,
                1.0,
                0.05,
                "Starting fertility on forest floor.",
            ),
            BalanceParam(
                "FERTILITY_MEADOW",
                "Fertility: meadow",
                "float",
                FERTILITY_MEADOW,
                0.0,
                1.0,
                0.05,
                "Starting fertility on meadow.",
            ),
            BalanceParam(
                "FERTILITY_GRASS",
                "Fertility: grass",
                "float",
                FERTILITY_GRASS,
                0.0,
                1.0,
                0.05,
                "Starting fertility on grass.",
            ),
            BalanceParam(
                "FERTILITY_SOIL",
                "Fertility: soil",
                "float",
                FERTILITY_SOIL,
                0.0,
                1.0,
                0.05,
                "Starting fertility on ploughed soil. Harvests cannot raise it back.",
            ),
            BalanceParam(
                "FERTILITY_RIPARIAN",
                "Fertility: riparian",
                "float",
                FERTILITY_RIPARIAN,
                0.0,
                1.0,
                0.05,
                "Starting fertility on shoreline.",
            ),
            BalanceParam(
                "FERTILITY_ROCK",
                "Fertility: rock",
                "float",
                FERTILITY_ROCK,
                0.0,
                1.0,
                0.05,
                "Starting fertility on rock (usually 0).",
            ),
            BalanceParam(
                "FERTILITY_WATER",
                "Fertility: water",
                "float",
                FERTILITY_WATER,
                0.0,
                1.0,
                0.05,
                "Starting fertility on water / river (usually 0).",
            ),
            BalanceParam(
                "FERTILITY_HARVEST_DROP",
                "Fertility lost per harvest",
                "float",
                FERTILITY_HARVEST_DROP,
                0.0,
                0.5,
                0.05,
                "Subtracted from that square when a crop is fully harvested.",
            ),
            BalanceParam(
                "WEED_GROWTH_RATE",
                "Weed growth per day",
                "float",
                WEED_GROWTH_RATE,
                0.0,
                0.5,
                0.01,
                "At fertility 1.0, weeds fill this much each day. Higher fertility grows weeds faster.",
            ),
            BalanceParam(
                "WEED_ACTION_THRESHOLD",
                "Hoe weeds at",
                "float",
                WEED_ACTION_THRESHOLD,
                0.05,
                1.0,
                0.05,
                "Farmers with a hoe pull weeds at this cover. Does not count as a harvest.",
            ),
            BalanceParam(
                "WEED_MAX_APPEARANCES_PER_SEASON",
                "Weed appearances / season",
                "int",
                WEED_MAX_APPEARANCES_PER_SEASON,
                0,
                8,
                1,
                "Max times weeds may start growing on a square each season. "
                "Cleared weeds do not return until the next season. Winter: no new growth.",
            ),
            BalanceParam(
                "WEED_HARVEST_PENALTY",
                "Weed harvest penalty",
                "float",
                WEED_HARVEST_PENALTY,
                0.0,
                1.0,
                0.05,
                "At full weeds, this fraction of harvest is lost on that square.",
            ),
            BalanceParam(
                "EROSION_SLOPE_SCALE",
                "Erosion slope scale",
                "float",
                EROSION_SLOPE_SCALE,
                1.0,
                40.0,
                0.5,
                "Height-map slope that maps to 100% erosion potential. Prebaked into the save.",
            ),
        ),
    ),
    BalanceCategory(
        "paths_urban",
        "Paths & urban",
        (
            BalanceParam(
                "PATH_TRAFFIC_STEP",
                "Wear per villager step",
                "float",
                PATH_TRAFFIC_STEP,
                0.25,
                4.0,
                0.25,
                "Added each time a villager enters a cell.",
            ),
            BalanceParam(
                "PATH_TRAFFIC_THRESHOLD",
                "Wear to paint path",
                "float",
                PATH_TRAFFIC_THRESHOLD,
                1.0,
                24.0,
                0.5,
                "Stored in settings.py; lower = paths appear sooner.",
            ),
            BalanceParam(
                "PATH_TRAFFIC_KEEP",
                "Wear to keep path",
                "float",
                PATH_TRAFFIC_KEEP,
                0.0,
                8.0,
                0.25,
                "Path terrain persists until wear drops below this.",
            ),
            BalanceParam(
                "PATH_TRAFFIC_DECAY",
                "Wear decay (env sample)",
                "float",
                PATH_TRAFFIC_DECAY,
                0.3,
                1.0,
                0.02,
                "Multiplied 8× per year on env sample days.",
            ),
            BalanceParam(
                "PATH_TRAFFIC_OVERLAY_MAX",
                "Traffic disturbance cap",
                "float",
                PATH_TRAFFIC_OVERLAY_MAX,
                4.0,
                40.0,
                1.0,
                "Wear mapped to 100% on the disturbance overlay (mixed with urban).",
            ),
            BalanceParam(
                "URBAN_MIN_BUILDINGS",
                "Buildings for urban core",
                "int",
                float(URBAN_MIN_BUILDINGS),
                1,
                12,
                1,
                "Fewer clusters stay grass/path from traffic only.",
            ),
        ),
    ),
    BalanceCategory(
        "disturbance",
        "Disturbance",
        (
            BalanceParam(
                "DISTURBANCE_RADIUS",
                "Disturbance radius (cells)",
                "int",
                float(DISTURBANCE_RADIUS),
                0,
                5,
                1,
                "Neighbourhood average for effects and wider spread.",
            ),
            BalanceParam(
                "DISTURBANCE_URBAN_LEVEL",
                "Urban floor",
                "float",
                DISTURBANCE_URBAN_LEVEL,
                0.0,
                1.0,
                0.05,
                "Constant disturbance on URBAN tiles (no decay).",
            ),
            BalanceParam(
                "DISTURBANCE_PATH_LEVEL",
                "Path floor",
                "float",
                DISTURBANCE_PATH_LEVEL,
                0.0,
                1.0,
                0.05,
                "Constant disturbance on PATH tiles while worn.",
            ),
            BalanceParam(
                "DISTURBANCE_EXTRACTION_BOOST",
                "Extraction boost",
                "float",
                DISTURBANCE_EXTRACTION_BOOST,
                0.0,
                1.0,
                0.05,
                "Harvest/hunt/fish/plough — lasts longer than light foot traffic.",
            ),
            BalanceParam(
                "DISTURBANCE_EXTRACTION_SPREAD",
                "Extraction neighbour spread",
                "float",
                DISTURBANCE_EXTRACTION_SPREAD,
                0.0,
                0.5,
                0.01,
            ),
            BalanceParam(
                "DISTURBANCE_ACTIVITY_FLOOR",
                "Ecology floor at max D",
                "float",
                DISTURBANCE_ACTIVITY_FLOOR,
                0.0,
                1.0,
                0.05,
                "Farm/breed/spread multiplier at disturbance 1.0.",
            ),
            BalanceParam(
                "DISTURBANCE_DECAY_PER_TICK",
                "Decay per tick",
                "float",
                DISTURBANCE_DECAY_PER_TICK,
                0.0,
                0.02,
                0.0005,
            ),
            BalanceParam(
                "DISTURBANCE_INTERACTION_BOOST",
                "Light interaction boost",
                "float",
                DISTURBANCE_INTERACTION_BOOST,
                0.0,
                1.0,
                0.05,
            ),
            BalanceParam(
                "DISTURBANCE_NEIGHBOUR_SPREAD",
                "Neighbour spread",
                "float",
                DISTURBANCE_NEIGHBOUR_SPREAD,
                0.0,
                0.5,
                0.01,
            ),
            BalanceParam(
                "DISTURBANCE_MAX",
                "Maximum",
                "float",
                DISTURBANCE_MAX,
                0.1,
                2.0,
                0.1,
            ),
        ),
    ),
    BalanceCategory(
        "overlays",
        "Overlays",
        (
            BalanceParam(
                "INDICATOR_RADIUS",
                "Indicator radius (cells)",
                "int",
                float(INDICATOR_RADIUS),
                1,
                8,
                1,
                "Neighbourhood radius for habitat/biodiversity overlays.",
            ),
        ),
    ),
)

_PARAM_BY_KEY: dict[str, BalanceParam] = {
    p.key: p for cat in BALANCE_CATEGORIES for p in cat.params
}


class BalanceState:
    """Mutable runtime balance values."""

    def __init__(self) -> None:
        self._values: dict[str, float] = {}
        self.reset()

    def reset(self) -> None:
        self._values = {p.key: float(p.default) for p in _PARAM_BY_KEY.values()}

    def reset_category(self, category_id: str) -> None:
        for cat in BALANCE_CATEGORIES:
            if cat.id != category_id:
                continue
            for p in cat.params:
                self._values[p.key] = float(p.default)
            return

    def param(self, key: str) -> BalanceParam:
        return _PARAM_BY_KEY[key]

    def get(self, key: str) -> float:
        return float(self._values[key])

    def get_int(self, key: str) -> int:
        return int(round(self.get(key)))

    def get_float(self, key: str) -> float:
        return self.get(key)

    def set(self, key: str, value: float) -> None:
        spec = self.param(key)
        clamped = max(spec.minimum, min(spec.maximum, float(value)))
        if spec.kind == "int":
            clamped = float(int(round(clamped)))
        self._values[key] = clamped

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
