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
    DISTURBANCE_URBAN_LEVEL,
    INDICATOR_RADIUS,
    PATH_TRAFFIC_DECAY,
    PATH_TRAFFIC_KEEP,
    PATH_TRAFFIC_OVERLAY_MAX,
    PATH_TRAFFIC_STEP,
    PATH_TRAFFIC_THRESHOLD,
    URBAN_MIN_BUILDINGS,
    VILLAGER_MOVE_INTERVAL,
    VILLAGER_WORK_INTERVAL,
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


@dataclass(frozen=True)
class BalanceCategory:
    id: str
    title: str
    params: tuple[BalanceParam, ...]


BALANCE_CATEGORIES: tuple[BalanceCategory, ...] = (
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
                "Traffic overlay cap",
                "float",
                PATH_TRAFFIC_OVERLAY_MAX,
                4.0,
                40.0,
                1.0,
                "Wear mapped to 100% on overlay 9.",
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
        "villagers",
        "Villagers",
        (
            BalanceParam(
                "VILLAGER_MOVE_INTERVAL",
                "Move interval (ticks)",
                "int",
                float(VILLAGER_MOVE_INTERVAL),
                4,
                240,
                4,
                "Base ticks between steps at reference day length.",
            ),
            BalanceParam(
                "VILLAGER_WORK_INTERVAL",
                "Work interval (ticks)",
                "int",
                float(VILLAGER_WORK_INTERVAL),
                6,
                360,
                6,
                "Base ticks between work actions.",
            ),
        ),
    ),
    BalanceCategory(
        "disturbance",
        "Disturbance",
        (
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
