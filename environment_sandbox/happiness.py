"""Villager happiness: ongoing target, temporary capped moods, immediate shots.

Conceptual model
----------------
underlying_target =
    base
  + housing
  + ration adequacy
  + meal variety
  + job satisfaction
  + clothing / weather comfort
  + active sociopolitical pressures

underlying_happiness gradually approaches underlying_target.

displayed_happiness =
    underlying_happiness
  + temporary meal mood
  + other temporary event moods

Clamped: displayed ∈ [0, 1], target ∈ [TARGET_MIN, TARGET_MAX].
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from entities import BuildingKind, RationMode, Villager, VillagerState


class HappinessEffectMode(str, Enum):
    ONGOING_TARGET = "ongoing_target"
    TEMPORARY_CAPPED = "temporary_capped"
    IMMEDIATE = "immediate"


# ---------------------------------------------------------------------------
# Balance knobs (ordinary ~0.03–0.10, severe ~0.15–0.20)
# ---------------------------------------------------------------------------

HAPPINESS_BASE: float = 0.55
HAPPINESS_TARGET_MIN: float = 0.05
HAPPINESS_TARGET_MAX: float = 0.95
# Fraction of the gap closed per full calendar day (tick rate = this × day_frac).
HAPPINESS_CONVERGENCE_PER_DAY: float = 2.8

# Housing
HAP_HOUSING_MISSING: float = -0.10
HAP_HOUSING_EXCESS_PER_LEVEL: float = 0.03
HAP_HOUSING_EXCESS_MAX: float = 0.09

# Meal variety (ongoing from last_meal types)
HAP_MEAL_VARIETY_PER: float = 0.03
HAP_MEAL_VARIETY_MAX_TYPES: int = 3

# Rations
HAP_HALF_RATION: float = -0.12
HAP_DOUBLE_RATION: float = 0.10
# Common Provision softens half-ration ongoing pressure.
HAP_PROVISION_HALF_SCALE: float = 0.75

# Job (only while actively working that assignment)
HAP_JOB_MATCH_WORKING: float = 0.06
HAP_JOB_OFF_SKILL_WORKING: float = -0.08
HAP_JOB_UNASSIGNED_IDLE: float = -0.04  # mild without principle; principle intensifies

# Thermal: discomfort per residual level; small comfort when not stressed
HAP_THERMAL_PER_LEVEL: float = -0.05  # level 1..3 → −0.05 .. −0.15
HAP_THERMAL_COMFORT: float = 0.04

# Temporary meal mood (single channel, non-stacking)
HAP_MEAL_FAVOURITE_CAP: float = 0.08
HAP_MEAL_DISLIKED_CAP: float = -0.08
HAP_MEAL_MOOD_HOURS: float = 8.0
MEAL_MOOD_CHANNEL: str = "meal"

# Other temporary caps
HAP_UNPAID_UPKEEP_CAP: float = -0.08
HAP_UNPAID_UPKEEP_HOURS: float = 24.0
HAP_TEMP_DEFAULT_HOURS: float = 6.0
HAP_TEMP_MAX_CHANNELS: int = 6

# Sociopolitical ongoing conflicts (principle → institution intensifies, no stack)
HAP_ASSIGNED_LABOUR_UNASSIGNED: float = -0.08
HAP_ASSIGNED_LABOUR_OFF_SKILL: float = -0.06
HAP_OFFICE_OFF_SKILL: float = -0.12  # replaces principle off-skill while working
HAP_OFFICE_UNASSIGNED: float = -0.10  # replaces principle unassigned
HAP_COMMON_HARVEST_UNEQUAL: float = -0.08
HAP_EQUAL_RATIONS_UNEQUAL: float = -0.06
HAP_PROTECTED_HABITAT_EXTRACTIVE: float = -0.06
HAP_COVENANT_EXTRACTIVE: float = -0.10  # replaces protected_habitat while extractive

# Immediate decision point scale (1 point = this bar delta)
HAP_IMMEDIATE_POINT_SCALE: float = 0.01
# Soft cap so one decision cannot dump Content → ~0
HAP_IMMEDIATE_MAX_ABS: float = 0.08

EXTRACTIVE_KINDS: frozenset[BuildingKind] = frozenset(
    {
        BuildingKind.FORESTER,
        BuildingKind.FIELD,
        BuildingKind.ORCHARD,
    }
)

WORKING_JOB_STATES: frozenset[VillagerState] = frozenset(
    {
        VillagerState.WORKING,
        VillagerState.BUILDING,
        VillagerState.HAULING,
        VillagerState.DELIVERING,
    }
)


@dataclass
class HappinessModifier:
    """One inspectable contribution (target component or temporary overlay)."""

    key: str
    label: str
    amount: float
    mode: HappinessEffectMode
    source: str
    hours_left: float | None = None
    channel: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "amount": round(float(self.amount), 4),
            "mode": self.mode.value,
            "source": self.source,
            "hours_left": (
                None if self.hours_left is None else round(float(self.hours_left), 2)
            ),
            "channel": self.channel,
        }


@dataclass
class HappinessBreakdown:
    target_components: list[HappinessModifier] = field(default_factory=list)
    target: float = HAPPINESS_BASE
    underlying: float = HAPPINESS_BASE
    temporary: list[HappinessModifier] = field(default_factory=list)
    temporary_total: float = 0.0
    displayed: float = HAPPINESS_BASE

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_components": [c.to_dict() for c in self.target_components],
            "target": round(self.target, 4),
            "underlying": round(self.underlying, 4),
            "temporary": [c.to_dict() for c in self.temporary],
            "temporary_total": round(self.temporary_total, 4),
            "displayed": round(self.displayed, 4),
        }


def clamp_target(value: float) -> float:
    return max(HAPPINESS_TARGET_MIN, min(HAPPINESS_TARGET_MAX, float(value)))


def clamp_displayed(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _ensure_underlying(villager: Villager) -> float:
    raw = getattr(villager, "underlying_happiness", None)
    if raw is None:
        # Migrate older saves / new villagers: treat displayed as underlying.
        underlying = float(getattr(villager, "happiness", HAPPINESS_BASE) or HAPPINESS_BASE)
        setattr(villager, "underlying_happiness", underlying)
        return underlying
    return float(raw)


def _temporary_moods(villager: Villager) -> list[dict]:
    moods = getattr(villager, "happiness_temporary", None)
    if moods is None:
        moods = []
        setattr(villager, "happiness_temporary", moods)
    return moods


def temporary_mood_value(mood: dict) -> float:
    """Linear decay from peak → 0 over the mood's lifetime."""
    peak = float(mood.get("peak", 0.0) or 0.0)
    ticks_left = max(0, int(mood.get("ticks_left", 0) or 0))
    ticks_total = max(1, int(mood.get("ticks_total", 1) or 1))
    return peak * (ticks_left / ticks_total)


def sum_temporary_moods(villager: Villager) -> float:
    return sum(temporary_mood_value(m) for m in _temporary_moods(villager))


def sync_displayed_happiness(villager: Villager) -> float:
    underlying = _ensure_underlying(villager)
    displayed = clamp_displayed(underlying + sum_temporary_moods(villager))
    villager.happiness = displayed
    return displayed


def apply_immediate_happiness(
    villager: Villager,
    points: float,
    *,
    icon: str = "stew",
    label: str = "Decision",
    day: int = 0,
    source: str = "decision",
) -> float:
    """One-shot change to underlying happiness (no linger). Returns bar delta."""
    from society import push_happiness_event

    delta = float(points) * HAP_IMMEDIATE_POINT_SCALE
    delta = max(-HAP_IMMEDIATE_MAX_ABS, min(HAP_IMMEDIATE_MAX_ABS, delta))
    underlying = _ensure_underlying(villager)
    underlying = clamp_displayed(underlying + delta)
    setattr(villager, "underlying_happiness", underlying)
    push_happiness_event(
        villager,
        icon=icon,
        label=label,
        delta=int(round(delta / HAP_IMMEDIATE_POINT_SCALE)),
        day=day,
    )
    sync_displayed_happiness(villager)
    return delta


def set_temporary_capped_mood(
    villager: Villager,
    *,
    channel: str,
    peak: float,
    hours: float,
    ticks_per_day: int,
    icon: str = "stew",
    label: str = "Mood",
    day: int = 0,
    source: str = "event",
    record_event: bool = True,
) -> None:
    """Apply or reset a non-stacking temporary mood on ``channel``."""
    from society import push_happiness_event

    peak = float(peak)
    if abs(peak) < 1e-9:
        return
    ticks_total = max(1, int(round(float(hours) / 24.0 * max(1, int(ticks_per_day)))))
    moods = _temporary_moods(villager)
    # Replace same channel (reset to cap — never stack).
    moods[:] = [m for m in moods if str(m.get("channel") or "") != channel]
    moods.append(
        {
            "channel": channel,
            "peak": peak,
            "ticks_left": ticks_total,
            "ticks_total": ticks_total,
            "icon": icon,
            "label": label,
            "source": source,
            "day": int(day),
        }
    )
    # Bound total distinct channels.
    if len(moods) > HAP_TEMP_MAX_CHANNELS:
        overflow = moods[:-HAP_TEMP_MAX_CHANNELS]
        del moods[: len(overflow)]
    if record_event:
        push_happiness_event(
            villager,
            icon=icon,
            label=label,
            delta=int(round(peak / HAP_IMMEDIATE_POINT_SCALE)),
            day=day,
        )
    sync_displayed_happiness(villager)


def apply_meal_mood(
    villager: Villager,
    *,
    favourite: bool | None,
    ticks_per_day: int,
    icon: str,
    label: str,
    day: int = 0,
) -> None:
    """Favourite / disliked meal mood. ``favourite is None`` → normal food (no clear)."""
    if favourite is None:
        # Normal / acceptable food does not abruptly remove an existing meal mood.
        return
    peak = HAP_MEAL_FAVOURITE_CAP if favourite else HAP_MEAL_DISLIKED_CAP
    try:
        from traits import trait_meal_mood_scale

        peak *= float(trait_meal_mood_scale(villager))
    except Exception:
        pass
    peak = max(-0.16, min(0.16, peak))
    set_temporary_capped_mood(
        villager,
        channel=MEAL_MOOD_CHANNEL,
        peak=peak,
        hours=HAP_MEAL_MOOD_HOURS,
        ticks_per_day=ticks_per_day,
        icon=icon,
        label=label,
        day=day,
        source="meal",
    )


def tick_temporary_moods(villager: Villager, ticks: int = 1) -> None:
    moods = _temporary_moods(villager)
    if not moods:
        return
    kept: list[dict] = []
    for mood in moods:
        left = max(0, int(mood.get("ticks_left", 0) or 0) - max(1, int(ticks)))
        if left <= 0:
            continue
        mood = dict(mood)
        mood["ticks_left"] = left
        kept.append(mood)
    setattr(villager, "happiness_temporary", kept)


def hours_left_for_mood(mood: dict, ticks_per_day: int) -> float:
    tpd = max(1, int(ticks_per_day))
    return float(mood.get("ticks_left", 0) or 0) * 24.0 / tpd


def _job_match(villager: Villager, buildings: dict) -> bool | None:
    """True match, False mismatch, None if unassigned / no workplace."""
    if villager.building_id is None:
        return None
    try:
        from sociopolitical_hooks import job_matches_strongest

        return bool(job_matches_strongest(villager, buildings))
    except Exception:
        return True


def _is_actively_working(villager: Villager) -> bool:
    return villager.state in WORKING_JOB_STATES


def _ration_modes_unequal(villagers: Iterable[Villager]) -> bool:
    modes = {v.ration_mode for v in villagers}
    return len(modes) > 1


def compute_happiness_target(
    villager: Villager,
    *,
    buildings: dict,
    political: Any | None = None,
    villagers: Iterable[Villager] | None = None,
    temp_impact: Any | None = None,
) -> tuple[float, list[HappinessModifier]]:
    """Return (clamped target, ongoing components)."""
    components: list[HappinessModifier] = []

    def add(key: str, label: str, amount: float, source: str) -> None:
        if abs(amount) < 1e-9:
            return
        components.append(
            HappinessModifier(
                key=key,
                label=label,
                amount=float(amount),
                mode=HappinessEffectMode.ONGOING_TARGET,
                source=source,
            )
        )

    add("base", "Baseline", HAPPINESS_BASE, "living")

    # Housing
    if villager.housed:
        house = buildings.get(villager.housing_id or -1)
        if house is not None:
            from society import housing_level_of

            lvl = housing_level_of(house.kind)
            excess = max(0, int(lvl) - int(villager.housing_need))
            bonus = min(HAP_HOUSING_EXCESS_MAX, HAP_HOUSING_EXCESS_PER_LEVEL * excess)
            add("housing_excess", "Housing above need", bonus, "housing")
    else:
        add("housing_missing", "No housing", HAP_HOUSING_MISSING, "housing")

    # Meal variety
    variety_n = min(HAP_MEAL_VARIETY_MAX_TYPES, len(getattr(villager, "last_meal", None) or []))
    add(
        "meal_variety",
        f"Meal variety ({variety_n})",
        HAP_MEAL_VARIETY_PER * variety_n,
        "food",
    )

    # Rations
    if villager.ration_mode == RationMode.HALF:
        scale = 1.0
        source = "rations"
        if political is not None and getattr(political, "has_institution", lambda *_: False)(
            "common_provision"
        ):
            scale = HAP_PROVISION_HALF_SCALE
            source = "common_provision"
        add("half_rations", "Half rations", HAP_HALF_RATION * scale, source)
    elif villager.ration_mode == RationMode.DOUBLE:
        add("double_rations", "Double rations", HAP_DOUBLE_RATION, "rations")

    # Job / political assignment pressure — institutions replace supporting principles.
    actively = _is_actively_working(villager)
    match = _job_match(villager, buildings)
    political_job = _political_job_components(
        villager,
        political=political,
        actively_working=actively,
        job_match=match,
    )
    if political_job:
        components.extend(political_job)
    elif actively and match is True:
        add("job_match", "Working matched job", HAP_JOB_MATCH_WORKING, "job")
    elif actively and match is False:
        add("job_off_skill", "Working off-skill job", HAP_JOB_OFF_SKILL_WORKING, "job")
    elif villager.building_id is None and not villager.assigned_to_home:
        add("unassigned", "Unassigned", HAP_JOB_UNASSIGNED_IDLE, "job")

    # Thermal discomfort / comfort
    if temp_impact is not None and getattr(temp_impact, "level", 0):
        level = int(temp_impact.level)
        kind = str(getattr(temp_impact, "kind", "") or "thermal")
        amount = HAP_THERMAL_PER_LEVEL * level
        add(
            f"thermal_{kind}",
            f"Thermal discomfort ({kind} {level})",
            amount,
            "weather",
        )
    else:
        add("thermal_comfort", "Comfortable clothing/weather", HAP_THERMAL_COMFORT, "weather")

    # Other sociopolitical pressures (rations equality, extractive habitat)
    _add_political_other_components(
        components,
        villager,
        buildings=buildings,
        political=political,
        villagers=villagers,
        actively_working=actively,
    )

    # Character traits (virtues / vices)
    try:
        from traits import trait_happiness_components

        for key, label, amount in trait_happiness_components(villager):
            add(key, label, amount, f"trait:{label}")
    except Exception:
        pass

    total = sum(c.amount for c in components)
    return clamp_target(total), components


def _political_job_components(
    villager: Villager,
    *,
    political: Any | None,
    actively_working: bool,
    job_match: bool | None,
) -> list[HappinessModifier]:
    """Assigned Labour / Office conflict lines (replace generic job terms)."""
    if political is None:
        return []
    enacted = set(getattr(political, "enacted_principle_ids", None) or [])
    has_inst = getattr(political, "has_institution", lambda *_: False)
    office = bool(has_inst("settlement_office"))
    if not office and "assigned_labour" not in enacted:
        return []
    out: list[HappinessModifier] = []

    def add(key: str, label: str, amount: float, source: str) -> None:
        out.append(
            HappinessModifier(
                key=key,
                label=label,
                amount=float(amount),
                mode=HappinessEffectMode.ONGOING_TARGET,
                source=source,
            )
        )

    if villager.building_id is None and not villager.assigned_to_home:
        if office:
            add(
                "office_unassigned",
                "Settlement Office: unassigned",
                HAP_OFFICE_UNASSIGNED,
                "settlement_office",
            )
        else:
            add(
                "assigned_labour_unassigned",
                "Assigned Labour: unassigned",
                HAP_ASSIGNED_LABOUR_UNASSIGNED,
                "assigned_labour",
            )
    elif actively_working and job_match is False:
        if office:
            add(
                "office_off_skill",
                "Settlement Office: off-skill work",
                HAP_OFFICE_OFF_SKILL,
                "settlement_office",
            )
        else:
            add(
                "assigned_labour_off_skill",
                "Assigned Labour: off-skill work",
                HAP_ASSIGNED_LABOUR_OFF_SKILL + HAP_JOB_OFF_SKILL_WORKING,
                "assigned_labour",
            )
    elif actively_working and job_match is True:
        add("job_match", "Working matched job", HAP_JOB_MATCH_WORKING, "job")
    return out


def _add_political_other_components(
    components: list[HappinessModifier],
    villager: Villager,
    *,
    buildings: dict,
    political: Any | None,
    villagers: Iterable[Villager] | None,
    actively_working: bool,
) -> None:
    if political is None:
        return
    enacted = set(getattr(political, "enacted_principle_ids", None) or [])
    has_inst = getattr(political, "has_institution", lambda *_: False)

    def add(key: str, label: str, amount: float, source: str) -> None:
        if abs(amount) < 1e-9:
            return
        components.append(
            HappinessModifier(
                key=key,
                label=label,
                amount=float(amount),
                mode=HappinessEffectMode.ONGOING_TARGET,
                source=source,
            )
        )

    peers = list(villagers) if villagers is not None else []
    unequal = _ration_modes_unequal(peers) if peers else False
    if unequal and not has_inst("common_provision"):
        if "common_harvest" in enacted:
            add(
                "common_harvest_unequal",
                "Common Harvest: unequal rations",
                HAP_COMMON_HARVEST_UNEQUAL,
                "common_harvest",
            )
        elif "equal_rations" in enacted:
            add(
                "equal_rations_unequal",
                "Equal Rations: unequal rations",
                HAP_EQUAL_RATIONS_UNEQUAL,
                "equal_rations",
            )

    building = buildings.get(villager.building_id or -1)
    extractive = (
        actively_working
        and building is not None
        and building.kind in EXTRACTIVE_KINDS
    )
    if extractive:
        if has_inst("covenant_of_the_land"):
            add(
                "covenant_extractive",
                "Covenant: extractive work",
                HAP_COVENANT_EXTRACTIVE,
                "covenant_of_the_land",
            )
        elif "protected_habitat" in enacted:
            add(
                "protected_habitat_extractive",
                "Protected Habitat: extractive work",
                HAP_PROTECTED_HABITAT_EXTRACTIVE,
                "protected_habitat",
            )


def tick_underlying_happiness(
    villager: Villager,
    day_frac: float,
    *,
    buildings: dict,
    political: Any | None = None,
    villagers: Iterable[Villager] | None = None,
    temp_impact: Any | None = None,
) -> HappinessBreakdown:
    """Advance temporary moods, drift underlying toward target, sync displayed."""
    tick_temporary_moods(villager, ticks=1)
    target, components = compute_happiness_target(
        villager,
        buildings=buildings,
        political=political,
        villagers=villagers,
        temp_impact=temp_impact,
    )
    underlying = _ensure_underlying(villager)
    rate = min(1.0, float(day_frac) * HAPPINESS_CONVERGENCE_PER_DAY)
    underlying = underlying + (target - underlying) * rate
    # Soft-clamp underlying toward the legal target band (allow slight overshoot from immediates).
    underlying = max(0.0, min(1.0, underlying))
    setattr(villager, "underlying_happiness", underlying)

    temps: list[HappinessModifier] = []
    tpd = int(getattr(villager, "_hap_ticks_per_day", 0) or 0) or 36000
    for mood in _temporary_moods(villager):
        amount = temporary_mood_value(mood)
        if abs(amount) < 0.001:
            continue
        temps.append(
            HappinessModifier(
                key=str(mood.get("channel") or "temp"),
                label=str(mood.get("label") or "Temporary mood"),
                amount=amount,
                mode=HappinessEffectMode.TEMPORARY_CAPPED,
                source=str(mood.get("source") or "event"),
                hours_left=hours_left_for_mood(mood, tpd),
                channel=str(mood.get("channel") or ""),
            )
        )
    temp_total = sum(t.amount for t in temps)
    displayed = clamp_displayed(underlying + temp_total)
    villager.happiness = displayed
    setattr(
        villager,
        "happiness_breakdown",
        HappinessBreakdown(
            target_components=components,
            target=target,
            underlying=underlying,
            temporary=temps,
            temporary_total=temp_total,
            displayed=displayed,
        ),
    )
    return villager.happiness_breakdown


def happiness_breakdown_for(villager: Villager) -> HappinessBreakdown | None:
    bd = getattr(villager, "happiness_breakdown", None)
    return bd if isinstance(bd, HappinessBreakdown) else None


def refresh_happiness_breakdown(
    villager: Villager,
    *,
    buildings: dict,
    political: Any | None = None,
    villagers: Iterable[Villager] | None = None,
    temp_impact: Any | None = None,
    ticks_per_day: int = 36000,
) -> HappinessBreakdown:
    """Recompute breakdown without advancing time (for UI / tests)."""
    setattr(villager, "_hap_ticks_per_day", int(ticks_per_day))
    target, components = compute_happiness_target(
        villager,
        buildings=buildings,
        political=political,
        villagers=villagers,
        temp_impact=temp_impact,
    )
    underlying = _ensure_underlying(villager)
    temps: list[HappinessModifier] = []
    for mood in _temporary_moods(villager):
        amount = temporary_mood_value(mood)
        if abs(amount) < 0.001:
            continue
        temps.append(
            HappinessModifier(
                key=str(mood.get("channel") or "temp"),
                label=str(mood.get("label") or "Temporary mood"),
                amount=amount,
                mode=HappinessEffectMode.TEMPORARY_CAPPED,
                source=str(mood.get("source") or "event"),
                hours_left=hours_left_for_mood(mood, ticks_per_day),
                channel=str(mood.get("channel") or ""),
            )
        )
    temp_total = sum(t.amount for t in temps)
    displayed = clamp_displayed(underlying + temp_total)
    villager.happiness = displayed
    bd = HappinessBreakdown(
        target_components=components,
        target=target,
        underlying=underlying,
        temporary=temps,
        temporary_total=temp_total,
        displayed=displayed,
    )
    setattr(villager, "happiness_breakdown", bd)
    return bd


# Legacy aliases used by older call sites during migration
def apply_timed_happiness_impact_legacy_bridge(
    villager: Villager,
    points: float,
    *,
    icon: str = "stew",
    label: str = "Event",
    day: int = 0,
    duration_hours: float | None = None,
    until_meal: bool = False,
    ticks_per_day: int = 36000,
    channel: str | None = None,
) -> None:
    """Bridge: map old timed impacts onto temporary_capped (non-stacking by channel)."""
    peak = float(points) * HAP_IMMEDIATE_POINT_SCALE
    peak = max(-0.20, min(0.20, peak))
    ch = channel or ("meal" if until_meal else f"event:{label}")
    hours = (
        HAP_MEAL_MOOD_HOURS
        if until_meal
        else float(duration_hours or HAP_TEMP_DEFAULT_HOURS)
    )
    set_temporary_capped_mood(
        villager,
        channel=ch,
        peak=peak,
        hours=hours,
        ticks_per_day=ticks_per_day,
        icon=icon,
        label=label,
        day=day,
        source="event",
    )
