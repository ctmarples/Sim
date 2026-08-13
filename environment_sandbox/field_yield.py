"""Shared field yield breakdown, factor display, and qualitative labels.

UI and harvest must use the same multipliers so inspect never drifts from pickup.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class Severity(Enum):
    POSITIVE = auto()
    NEUTRAL = auto()
    WARNING = auto()
    CRITICAL = auto()


@dataclass(frozen=True)
class YieldBreakdown:
    """Per-tile harvest factors and intermediate staircase values."""

    base: float
    pest_control: float
    crop_health: float
    pollination: float
    ecology: float  # disturbance activity multiplier (internal name)
    fertility: float
    weed_penalty: float
    weeds: float = 0.0
    after_landscape: float = 0.0
    after_crop_condition: float = 0.0
    final_unrounded: float = 0.0
    final_rounded: int = 1


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
) -> YieldBreakdown:
    """Single source of truth for farm tile harvest (same product as pickup)."""
    b = max(0.0, float(base))
    pest = float(pest_control)
    health = float(crop_health)
    poll = float(pollination)
    eco = float(ecology)
    fert = float(fertility)
    weed = float(weed_penalty)
    after_landscape = b * pest * poll * eco
    after_crop = after_landscape * health * weed
    final = after_crop * fert
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


def effect_pct_text(mult: float) -> str | None:
    """Player-facing yield effect vs ×1.0. Returns None when effectively neutral."""
    delta = (float(mult) - 1.0) * 100.0
    if abs(delta) < 0.5:
        return None
    if delta > 0:
        return f"+{delta:.0f}%"
    return f"{delta:.0f}%"


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
    # lower mult is better (unused for yield factors; kept for completeness)
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
    # lower is better (disturbance, weeds, erosion)
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


def label_fertility(f: float) -> str:
    t = max(0.0, min(1.0, float(f)))
    if t >= 0.80:
        return "Excellent"
    if t >= 0.60:
        return "Good"
    if t >= 0.40:
        return "Fair"
    if t >= 0.20:
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
    pest_bio = float(status.get("pest_from_bio") or pest)
    boost = float(status.get("pest_boost") or 0.0)
    bio = float(status.get("biodiversity") or 0.0)
    health = float(status.get("health") or 1.0)
    health_cap = float(status.get("health_cap") or 1.0)
    poll = float(status.get("poll_coverage") or 0.0)
    poll_mult = float(status.get("poll_mult") or 1.0)
    ecology = float(status.get("ecology") or 1.0)
    dist = float(status.get("disturbance") or 0.0)
    fertility = float(status.get("fertility") or 0.0)
    weeds = float(status.get("weeds") or 0.0)
    weed_mult = float(status.get("weed_mult") or 1.0)
    weed_threshold = float(status.get("weed_threshold") or 0.2)
    erosion = float(status.get("erosion") or 0.0)

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
            detail_lines=[
                f"Bee coverage {poll * 100:.0f}%",
                f"Yield multiplier {poll_mult:.2f}×",
                f"Yield effect {effect_pct_text(poll_mult) or '±0%'}",
                "Based on nearby established bee colonies.",
            ],
        ),
        FieldFactorDisplay(
            key="pest",
            label="Pest control",
            icon="insect_repellant",
            section="landscape",
            state_text=label_pest(pest),
            value_text=f"bio {bio:.1f}",
            effect_text=effect_pct_text(pest),
            severity=severity_for_mult(pest),
            overlay_key="BIODIVERSITY",
            effect_mult=pest,
            detail_lines=[
                f"Species richness {bio:.1f}",
                f"Biological multiplier {pest_bio:.2f}×",
                f"Field treatment boost {boost:+.2f}",
                f"Yield pest (bio + boost) {pest:.2f}×",
                f"Yield effect {effect_pct_text(pest) or '±0%'}",
                "Health cap uses biological pest only (not treatment boost).",
                f"Crop-health cap now {health_cap * 100:.0f}%.",
            ],
        ),
        FieldFactorDisplay(
            key="disturbance",
            label="Disturbance",
            icon="tree_round_1",
            section="landscape",
            state_text=label_disturbance(dist),
            value_text=f"{dist * 100:.0f}%",
            effect_text=effect_pct_text(ecology),
            severity=severity_for_mult(ecology),
            overlay_key="DISTURBANCE",
            effect_mult=ecology,
            detail_lines=[
                f"Field mean disturbance {dist * 100:.0f}%",
                f"Yield multiplier {ecology:.2f}×",
                f"Yield effect {effect_pct_text(ecology) or '±0%'}",
                "Sources may include settlement, path traffic, and extraction.",
                "Updates continuously (not only on seasonal samples).",
            ],
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
            detail_lines=[
                f"Crop health {health * 100:.0f}%",
                f"Cap from biological pest {health_cap * 100:.0f}%",
                f"Yield effect {effect_pct_text(health) or '±0%'}",
                "Health only falls toward the pest-control cap; it does not recover alone.",
                "Shared by the whole field (not per tile).",
            ],
        ),
        FieldFactorDisplay(
            key="fertility",
            label="Fertility",
            icon="mineral_powder",
            section="condition",
            state_text=label_fertility(fertility),
            value_text=f"{fertility * 100:.0f}%",
            effect_text=effect_pct_text(fertility),
            severity=severity_for_mult(fertility),
            overlay_key="FERTILITY",
            effect_mult=fertility,
            detail_lines=[
                f"Current field mean {fertility:.2f}",
                f"Yield effect {effect_pct_text(fertility) or '±0%'}",
                "Terrain sets the starting base; harvests deplete the square.",
                "Varies by tile — harvest uses each cell's fertility.",
            ],
        ),
        FieldFactorDisplay(
            key="weeds",
            label="Weeds",
            icon="crop_weeds",
            section="condition",
            state_text=label_weeds(weeds),
            value_text=f"{weeds * 100:.0f}% cover",
            effect_text=effect_pct_text(weed_mult),
            severity=severity_for_mult(weed_mult),
            overlay_key=None,
            effect_mult=weed_mult,
            detail_lines=[
                f"Mean cover {weeds * 100:.0f}%",
                f"Yield multiplier {weed_mult:.2f}×",
                f"Yield effect {effect_pct_text(weed_mult) or '±0%'}",
                f"Farmers hoe at {weed_threshold * 100:.0f}%+ cover (not a harvest).",
                "Higher fertility grows weeds faster.",
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
            detail_lines=[
                f"Field mean {erosion * 100:.0f}% ({label_erosion(erosion)})",
                "Slope-based potential from the height map.",
                "Currently does not directly modify harvest.",
            ],
        ),
    ]
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
