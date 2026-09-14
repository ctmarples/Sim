"""Shared field yield breakdown, factor display, and qualitative labels.

UI and harvest must use the same multipliers so inspect never drifts from pickup.

Pest control does **not** multiply harvest directly: biodiversity → pest pressure →
crop-health cap → sticky crop health → yield. Landscape yield uses pollination;
crop-condition yield uses disturbance (ecology), health, and weeds. Fertility is
current / landscape potential so compost above potential boosts harvest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world import World


class Severity(Enum):
    POSITIVE = auto()
    NEUTRAL = auto()
    WARNING = auto()
    CRITICAL = auto()


@dataclass(frozen=True)
class YieldBreakdown:
    """Per-tile harvest factors and intermediate staircase values."""

    base: float
    pest_control: float  # recorded for debug; not applied to the product
    crop_health: float
    pollination: float
    ecology: float  # disturbance activity multiplier (internal name)
    fertility: float
    weed_penalty: float
    weeds: float = 0.0
    moisture: float = 1.0
    soil_texture: float = 1.0
    after_landscape: float = 0.0
    after_crop_condition: float = 0.0
    final_unrounded: float = 0.0
    final_rounded: int = 1


def fertility_yield_multiplier(fertility: float, potential: float) -> float:
    """Yield × from current fertility vs landscape potential (1.0 = at potential).

    Compost may push fertility above potential and return a bonus (>1.0).
    """
    pot = max(1e-6, float(potential))
    return max(0.0, float(fertility) / pot)


def calculate_tile_yield_breakdown(
    *,
    base: float,
    pest_control: float,
    crop_health: float,
    pollination: float,
    ecology: float,
    fertility: float,
    weed_penalty: float,
    weeds: float = 0.0,
    moisture: float = 1.0,
    soil_texture: float = 1.0,
) -> YieldBreakdown:
    """Single source of truth for farm tile harvest (same product as pickup).

    Product: base × pollination × ecology × crop_health × weed_penalty
    × fertility × moisture × soil_texture.

    Staircase stages match Field Status sections:
    - Landscape = pollination only (pest control is not a yield ×)
    - Crop condition = disturbance (ecology) × crop health × weeds
    - Soil = fertility × moisture × soil texture

    ``fertility`` is the relative yield multiplier (current / potential).
    ``pest_control`` is retained for diagnostics only (feeds health over time).
    """
    b = max(0.0, float(base))
    pest = float(pest_control)
    health = float(crop_health)
    poll = float(pollination)
    eco = float(ecology)
    fert = float(fertility)
    weed = float(weed_penalty)
    moist = float(moisture)
    texture = float(soil_texture)
    after_landscape = b * poll
    after_crop = after_landscape * eco * health * weed
    final = after_crop * fert * moist * texture
    rounded = max(1, int(round(final)))
    return YieldBreakdown(
        base=b,
        pest_control=pest,
        crop_health=health,
        pollination=poll,
        ecology=eco,
        fertility=fert,
        weed_penalty=weed,
        weeds=float(weeds),
        moisture=moist,
        soil_texture=texture,
        after_landscape=after_landscape,
        after_crop_condition=after_crop,
        final_unrounded=final,
        final_rounded=rounded,
    )


@dataclass
class FieldYieldSummary:
    mean_expected: float
    min_expected: int
    max_expected: int
    expected_total: int
    max_total: int
    tile_count: int
    base_per_tile: float
    mean_unrounded: float
    locked_total: int | None = None  # sum of frozen deposits when any tile locked
    tile_yields: dict[tuple[int, int], int] = field(default_factory=dict)
    mean_after_landscape: float = 0.0
    mean_after_crop_condition: float = 0.0


@dataclass
class FieldFactorDisplay:
    key: str
    label: str
    icon: str
    section: str  # landscape | condition | soil
    state_text: str
    value_text: str
    effect_text: str | None
    severity: Severity
    overlay_key: str | None
    detail_lines: list[str]
    effect_mult: float = 1.0  # for main-limitation ranking (1.0 = neutral)
    management: str = ""  # Habitat | Location | Persistent | …
    hint: str = ""
    # Optional right-column badge when not a yield ±% (e.g. "cap 100%", "35% risk").
    right_badge: str | None = None


def niche_yield_multiplier(
    value: float,
    niche,
    *,
    floor: float = 0.75,
    ceiling: float = 1.05,
) -> float:
    """Soft yield factor from a wild niche response (None niche → neutral 1.0)."""
    if niche is None:
        return 1.0
    from wild_species import niche_response

    response = niche_response(float(value), niche)
    return float(floor) + (float(ceiling) - float(floor)) * response


def crop_moisture_texture_multipliers(
    crop_kind: str | None,
    *,
    soil_moisture: float,
    soil_texture: float,
) -> tuple[float, float]:
    """Look up wild niches for a planted crop key; missing niches stay neutral."""
    if not crop_kind:
        return 1.0, 1.0
    from wild_species import WILD_BY_KEY

    species = WILD_BY_KEY.get(str(crop_kind))
    if species is None:
        return 1.0, 1.0
    return (
        niche_yield_multiplier(soil_moisture, species.moisture_niche),
        niche_yield_multiplier(soil_texture, species.texture_niche),
    )


def effect_pct_text(mult: float) -> str | None:
    """Player-facing yield effect vs ×1.0. Returns None when effectively neutral."""
    delta = (float(mult) - 1.0) * 100.0
    if abs(delta) < 0.5:
        return None
    if delta > 0:
        return f"+{delta:.0f}%"
    return f"{delta:.0f}%"


def stage_effect_pct(prev: float, nxt: float) -> str:
    """Percent change from one staircase stage to the next."""
    p = float(prev)
    if abs(p) < 1e-9:
        return "—"
    return effect_pct_text(float(nxt) / p) or "±0%"


def severity_for_mult(mult: float, *, higher_is_better: bool = True) -> Severity:
    m = float(mult)
    if higher_is_better:
        if m >= 1.08:
            return Severity.POSITIVE
        if m >= 0.92:
            return Severity.NEUTRAL
        if m >= 0.70:
            return Severity.WARNING
        return Severity.CRITICAL
    if m <= 0.92:
        return Severity.POSITIVE
    if m <= 1.08:
        return Severity.NEUTRAL
    if m <= 1.30:
        return Severity.WARNING
    return Severity.CRITICAL


def severity_for_ratio(ratio: float, *, higher_is_better: bool = True) -> Severity:
    """0–1 state ratios (coverage, fertility, weeds, disturbance)."""
    t = max(0.0, min(1.0, float(ratio)))
    if higher_is_better:
        if t >= 0.80:
            return Severity.POSITIVE
        if t >= 0.50:
            return Severity.NEUTRAL
        if t >= 0.25:
            return Severity.WARNING
        return Severity.CRITICAL
    if t <= 0.20:
        return Severity.POSITIVE
    if t <= 0.45:
        return Severity.NEUTRAL
    if t <= 0.70:
        return Severity.WARNING
    return Severity.CRITICAL


def label_pollination(coverage: float) -> str:
    t = max(0.0, min(1.0, float(coverage)))
    if t < 0.20:
        return "Poor"
    if t < 0.50:
        return "Fair"
    if t < 0.80:
        return "Good"
    return "Excellent"


def label_disturbance(d: float) -> str:
    t = max(0.0, min(1.0, float(d)))
    if t < 0.20:
        return "Low"
    if t < 0.45:
        return "Moderate"
    if t < 0.70:
        return "High"
    return "Severe"


def label_fertility_relative(rel: float) -> str:
    """Condition vs local soil potential (1.0 = at potential; >1 = compost boost)."""
    t = max(0.0, float(rel))
    if t > 1.02:
        return "Boosted"
    if t >= 0.98:
        return "Optimal"
    if t >= 0.80:
        return "Good"
    if t >= 0.60:
        return "Fair"
    if t >= 0.40:
        return "Poor"
    return "Critical"


def label_fertility(f: float) -> str:
    """Absolute fertility band (legacy / debug). Prefer label_fertility_relative."""
    t = max(0.0, min(1.0, float(f)))
    if t >= 0.98:
        return "Excellent"
    if t >= 0.80:
        return "Good"
    if t >= 0.60:
        return "Fair"
    if t >= 0.40:
        return "Poor"
    return "Critical"


def label_health(h: float) -> str:
    t = max(0.0, min(1.0, float(h)))
    if t >= 0.95:
        return "Excellent"
    if t >= 0.85:
        return "Good"
    if t >= 0.75:
        return "Fair"
    if t >= 0.70:
        return "Poor"
    return "Critical"


def label_pest(mult: float) -> str:
    m = float(mult)
    if m >= 1.10:
        return "Excellent"
    if m >= 1.00:
        return "Good"
    if m >= 0.85:
        return "Fair"
    if m >= 0.75:
        return "Poor"
    return "Critical"


def label_weeds(w: float) -> str:
    t = max(0.0, min(1.0, float(w)))
    if t < 0.10:
        return "None"
    if t < 0.25:
        return "Low"
    if t < 0.50:
        return "Moderate"
    if t < 0.75:
        return "High"
    return "Severe"


def label_erosion(e: float) -> str:
    t = max(0.0, min(1.0, float(e)))
    if t < 0.25:
        return "Low"
    if t < 0.50:
        return "Moderate"
    if t < 0.75:
        return "High"
    return "Severe"


SEVERITY_COLOUR: dict[Severity, tuple[int, int, int]] = {
    Severity.POSITIVE: (90, 180, 100),
    Severity.NEUTRAL: (180, 175, 90),
    Severity.WARNING: (220, 140, 60),
    Severity.CRITICAL: (220, 70, 55),
}


def build_field_factors(status: dict) -> list[FieldFactorDisplay]:
    """Player-facing factor rows from ``_field_env_status`` (or equivalent)."""
    pest = float(status.get("pest_mult") or 1.0)
    health = float(status.get("health") or 1.0)
    health_cap = float(status.get("health_cap") or 1.0)
    poll = float(status.get("poll_coverage") or 0.0)
    poll_mult = float(status.get("poll_mult") or 1.0)
    ecology = float(status.get("ecology") or 1.0)
    dist = float(status.get("disturbance") or 0.0)
    fertility = float(status.get("fertility") or 0.0)
    fert_pot = float(status.get("fertility_potential") or fertility or 1.0)
    fert_rel = fertility_yield_multiplier(fertility, fert_pot)
    weeds = float(status.get("weeds") or 0.0)
    weed_mult = float(status.get("weed_mult") or 1.0)
    erosion = float(status.get("erosion") or 0.0)
    foot = float(status.get("foot_traffic") or 0.0)
    settlement = float(status.get("settlement_disturbance") or 0.0)
    nearest_colony = status.get("nearest_colony_tiles")

    poll_details = [
        "Pollination depends on how well nearby bee colonies cover this field.",
    ]
    if nearest_colony is not None:
        poll_details.append(f"Nearest colony: {int(nearest_colony)} tiles away")

    dist_details = [
        "Foot traffic and nearby buildings increase disturbance around the field.",
        f"Foot traffic: {label_disturbance(foot)} · "
        f"Settlement pressure: {label_disturbance(settlement)}",
    ]

    prev_health = float(status.get("previous_crop_health") or health)
    from environment import crop_health_carryover

    started = crop_health_carryover(prev_health)
    health_details = [
        "Crop health belongs to the current planting. Poor natural pest control "
        "gradually wears it down through the seasons. A new crop starts halfway "
        "between the previous crop's ending health and full health.",
        f"Current: {health * 100:.0f}% · Pest-control cap: {health_cap * 100:.0f}%",
        f"Previous crop ended at {prev_health * 100:.0f}% → this crop started at "
        f"{started * 100:.0f}%",
    ]

    rows: list[FieldFactorDisplay] = [
        FieldFactorDisplay(
            key="pollination",
            label="Pollination",
            icon="bee",
            section="landscape",
            state_text=label_pollination(poll),
            value_text=f"{poll * 100:.0f}% coverage",
            effect_text=effect_pct_text(poll_mult),
            severity=severity_for_mult(poll_mult),
            overlay_key="POLLINATION",
            effect_mult=poll_mult,
            management="Habitat",
            hint=poll_details[0],
            detail_lines=poll_details,
        ),
        FieldFactorDisplay(
            key="pest",
            label="Natural pest control",
            icon="insect_repellant",
            section="landscape",
            state_text=label_pest(pest),
            value_text=f"bio {float(status.get('biodiversity') or 0):.1f}",
            effect_text=None,
            severity=severity_for_mult(pest),
            overlay_key="BIODIVERSITY",
            effect_mult=1.0,
            management="Habitat",
            hint="Nearby diversity sets how well the crop is protected.",
            detail_lines=[
                "Nearby plant and animal diversity determines how well the crop "
                "is naturally protected from pests.",
                f"Crop-health cap: {health_cap * 100:.0f}%",
            ],
            right_badge=f"cap {health_cap * 100:.0f}%",
        ),
        FieldFactorDisplay(
            key="health",
            label="Crop health",
            icon="crop_plant_1",
            section="condition",
            state_text=label_health(health),
            value_text=f"{health * 100:.0f}%",
            effect_text=effect_pct_text(health),
            severity=severity_for_mult(health),
            overlay_key=None,
            effect_mult=health,
            management="Persistent",
            hint=health_details[0],
            detail_lines=health_details,
        ),
        FieldFactorDisplay(
            key="weeds",
            label="Weeds",
            icon="crop_weeds",
            section="condition",
            state_text=label_weeds(weeds),
            value_text=f"{weeds * 100:.0f}%",
            effect_text=effect_pct_text(weed_mult),
            severity=severity_for_mult(weed_mult),
            overlay_key=None,
            effect_mult=weed_mult,
            management="Field work",
            hint="Weeds compete with the crop for harvest share.",
            detail_lines=[
                "Weeds compete with the crop and reduce the harvest as they spread.",
            ],
        ),
        FieldFactorDisplay(
            key="disturbance",
            label="Disturbance",
            icon="tree_round_1",
            section="condition",
            state_text=label_disturbance(dist),
            value_text=f"{dist * 100:.0f}%",
            effect_text=effect_pct_text(ecology),
            severity=severity_for_mult(ecology),
            overlay_key="DISTURBANCE",
            effect_mult=ecology,
            management="Location",
            hint=dist_details[0],
            detail_lines=dist_details,
        ),
        FieldFactorDisplay(
            key="fertility",
            label="Fertility",
            icon="mineral_powder",
            section="soil",
            state_text=label_fertility_relative(fert_rel),
            value_text=f"{fertility:.2f}/{fert_pot:.2f}",
            effect_text=(
                None if abs(fert_rel - 1.0) < 0.02 else effect_pct_text(fert_rel)
            ),
            severity=(
                Severity.POSITIVE
                if fert_rel > 1.02
                else severity_for_ratio(min(1.0, fert_rel), higher_is_better=True)
            ),
            overlay_key="FERTILITY",
            effect_mult=float(fert_rel),
            management="Rotation",
            hint="Fertility vs local soil potential.",
            detail_lines=[
                "Fertility is the soil's current productive condition relative "
                "to its local potential.",
                f"{fertility:.2f} of {fert_pot:.2f} potential",
            ],
        ),
        FieldFactorDisplay(
            key="erosion",
            label="Erosion risk",
            icon="rock",
            section="soil",
            state_text=label_erosion(erosion),
            value_text=f"{erosion * 100:.0f}%",
            effect_text=None,
            severity=severity_for_ratio(erosion, higher_is_better=False),
            overlay_key="EROSION",
            effect_mult=1.0,
            management="Soil",
            hint="Slope-based risk; not yet in harvest.",
            detail_lines=[
                "Erosion risk is determined by the slope of the ground beneath "
                "the field.",
            ],
            right_badge=f"{erosion * 100:.0f}% risk",
        ),
    ]
    if "moisture" in status:
        moisture = float(status["moisture"])
        moist_mult = float(status.get("moisture_mult") or 1.0)
        rows.insert(-1, FieldFactorDisplay(
            key="moisture", label="Moisture", icon="water", section="soil",
            state_text="Dry" if moisture < .3 else "Good" if moisture < .75 else "Wet",
            value_text=f"{moisture * 100:.0f}%",
            effect_text=effect_pct_text(moist_mult),
            severity=severity_for_mult(moist_mult),
            overlay_key="SOIL_MOISTURE",
            effect_mult=moist_mult,
            detail_lines=[
                "Each crop grows best within its preferred range of soil moisture.",
            ],
            management="Persistent",
            hint="Match moisture to the crop.",
        ))
    if "soil_texture" in status or "soil_texture_mult" in status:
        texture = float(status.get("soil_texture") or 0.45)
        texture_mult = float(status.get("soil_texture_mult") or 1.0)
        from soil_texture import texture_band_label

        rows.insert(-1, FieldFactorDisplay(
            key="soil_texture", label="Soil texture", icon="field", section="soil",
            state_text=texture_band_label(texture).title(),
            value_text=f"{texture * 100:.0f}%",
            effect_text=effect_pct_text(texture_mult),
            severity=severity_for_mult(texture_mult),
            overlay_key="SOIL_TEXTURE",
            effect_mult=texture_mult,
            detail_lines=[
                "Different crops are better suited to different soil textures.",
            ],
            management="Persistent",
            hint="Choose crops that match local texture.",
        ))
    return rows



def main_limitation(factors: list[FieldFactorDisplay]) -> str | None:
    """Factor with the greatest negative yield impact, or None if none hurt yield."""
    candidates = [
        f for f in factors if f.effect_mult < 0.995 and f.key != "erosion"
    ]
    if not candidates:
        return None
    worst = min(candidates, key=lambda f: f.effect_mult)
    return worst.label


def summarize_tile_yields(
    tile_yields: dict[tuple[int, int], int],
    *,
    base_per_tile: float,
    locked_total: int | None = None,
    unrounded_mean: float | None = None,
    mean_after_landscape: float = 0.0,
    mean_after_crop_condition: float = 0.0,
) -> FieldYieldSummary:
    if not tile_yields:
        base = float(base_per_tile)
        return FieldYieldSummary(
            mean_expected=0.0,
            min_expected=0,
            max_expected=0,
            expected_total=0,
            max_total=0,
            tile_count=0,
            base_per_tile=base,
            mean_unrounded=0.0,
            locked_total=locked_total,
            tile_yields={},
        )
    vals = list(tile_yields.values())
    n = len(vals)
    total = sum(vals)
    mean = total / n
    base = float(base_per_tile)
    return FieldYieldSummary(
        mean_expected=mean,
        min_expected=min(vals),
        max_expected=max(vals),
        expected_total=total,
        max_total=int(round(base * n)),
        tile_count=n,
        base_per_tile=base,
        mean_unrounded=float(unrounded_mean if unrounded_mean is not None else mean),
        locked_total=locked_total,
        tile_yields=dict(tile_yields),
        mean_after_landscape=float(mean_after_landscape),
        mean_after_crop_condition=float(mean_after_crop_condition),
    )


def audit_disturbance_stats(world: World) -> dict[str, dict[str, float | int]]:
    """Development helper: disturbance percentiles for farmable / context cells."""
    from world import TerrainType, effective_disturbance_at

    paths: set[tuple[int, int]] = set()
    urbans: set[tuple[int, int]] = set()
    for y in range(world.rows):
        for x in range(world.cols):
            cell = world.get_cell(x, y)
            if cell is None:
                continue
            if cell.terrain == TerrainType.PATH or getattr(cell, "path_worn", False):
                paths.add((x, y))
            elif cell.terrain == TerrainType.URBAN:
                urbans.add((x, y))

    def near(x: int, y: int, sites: set[tuple[int, int]], radius: int = 2) -> bool:
        for sx, sy in sites:
            if max(abs(sx - x), abs(sy - y)) <= radius:
                return True
        return False

    buckets: dict[str, list[float]] = {
        "soil_remote": [],
        "soil_near_path": [],
        "soil_near_urban": [],
        "path": [],
        "urban": [],
    }
    for y in range(world.rows):
        for x in range(world.cols):
            cell = world.get_cell(x, y)
            if cell is None:
                continue
            d = effective_disturbance_at(world, x, y)
            if cell.terrain == TerrainType.SOIL:
                if near(x, y, urbans):
                    buckets["soil_near_urban"].append(d)
                elif near(x, y, paths):
                    buckets["soil_near_path"].append(d)
                else:
                    buckets["soil_remote"].append(d)
            elif cell.terrain == TerrainType.PATH or getattr(cell, "path_worn", False):
                buckets["path"].append(d)
            elif cell.terrain == TerrainType.URBAN:
                buckets["urban"].append(d)

    def _pct(xs: list[float], p: float) -> float:
        xs = sorted(xs)
        i = int(round((len(xs) - 1) * p))
        return float(xs[i])

    out: dict[str, dict[str, float | int]] = {}
    for name, xs in buckets.items():
        if not xs:
            out[name] = {"n": 0}
            continue
        out[name] = {
            "n": len(xs),
            "min": float(min(xs)),
            "p25": _pct(xs, 0.25),
            "median": _pct(xs, 0.5),
            "p75": _pct(xs, 0.75),
            "max": float(max(xs)),
            "mean": float(sum(xs) / len(xs)),
        }
    return out
