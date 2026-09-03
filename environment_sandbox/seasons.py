"""Calendar, seasons, and gradual ecology envelopes."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, auto

from wild_species import (
    WILD_BY_KEY,
    species_despawn_rate,
    species_spawn_rate,
    spawn_group_leader,
)
from settings import FPS, TICKS_PER_DAY as TICKS_PER_DAY_DEFAULT


class Season(Enum):
    SPRING = auto()
    SUMMER = auto()
    AUTUMN = auto()
    WINTER = auto()


SEASON_ORDER: tuple[Season, ...] = (
    Season.SPRING,
    Season.SUMMER,
    Season.AUTUMN,
    Season.WINTER,
)

SEASON_LABELS: dict[Season, str] = {
    Season.SPRING: "Spring",
    Season.SUMMER: "Summer",
    Season.AUTUMN: "Autumn",
    Season.WINTER: "Winter",
}

# ASCII fallbacks if fancy glyphs fail to render.
SEASON_SYMBOLS: dict[Season, str] = {
    Season.SPRING: "*",
    Season.SUMMER: "O",
    Season.AUTUMN: "^",
    Season.WINTER: "+",
}

# Prefer these when the font supports them.
SEASON_SYMBOLS_FANCY: dict[Season, str] = {
    Season.SPRING: "✿",
    Season.SUMMER: "☀",
    Season.AUTUMN: "❧",
    Season.WINTER: "❄",
}

DAYS_PER_SEASON: int = 28
YEAR_DAYS: int = DAYS_PER_SEASON * 4  # 112
# Default day length is wall-clock seconds at ×1 (see settings.DAY_SECONDS_AT_X1).
TICKS_PER_DAY: int = TICKS_PER_DAY_DEFAULT

# Kept for older saves that stored season_timer.
SEASON_LENGTH_TICKS: int = TICKS_PER_DAY * DAYS_PER_SEASON

# Ambient air temperature (°C): −cos wave, coldest mid-winter / hottest mid-summer.
TEMP_WINTER_C: float = -10.0
TEMP_SUMMER_C: float = 35.0
# Mid-season day indices within the year (spring=0…).
_MID_SUMMER_DAY: float = DAYS_PER_SEASON * 1 + DAYS_PER_SEASON / 2  # 42
_MID_WINTER_DAY: float = DAYS_PER_SEASON * 3 + DAYS_PER_SEASON / 2  # 98

# Walk / energy multipliers for temperature impact levels 1–3 (0 = none).
TEMP_WALK_MULT: dict[int, float] = {0: 1.0, 1: 0.9, 2: 0.8, 3: 0.7}
TEMP_ENERGY_MULT: dict[int, float] = {0: 1.0, 1: 1.1, 2: 1.2, 3: 1.3}


def set_ticks_per_day(ticks: int) -> int:
    """Set runtime ticks per day; keeps seasons/crops/villager pacing in sync."""
    global TICKS_PER_DAY, SEASON_LENGTH_TICKS
    TICKS_PER_DAY = max(1, int(ticks))
    SEASON_LENGTH_TICKS = TICKS_PER_DAY * DAYS_PER_SEASON
    return TICKS_PER_DAY

AUTUMN_SEED_MULTIPLIER: float = 3.0

# Per-tile stagger window (days) so appear/disappear is not map-wide.
TILE_STAGGER_DAYS: float = 12.0


def season_for_day(day: int) -> Season:
    d = int(day) % YEAR_DAYS
    return SEASON_ORDER[d // DAYS_PER_SEASON]


def day_in_season(day: int) -> int:
    return int(day) % DAYS_PER_SEASON


def season_symbol(season: Season, *, fancy: bool = True) -> str:
    if fancy:
        return SEASON_SYMBOLS_FANCY.get(season, SEASON_SYMBOLS[season])
    return SEASON_SYMBOLS[season]


def format_date(day: int, *, fancy: bool = True) -> str:
    season = season_for_day(day)
    sym = season_symbol(season, fancy=fancy)
    return f"{sym} {SEASON_LABELS[season]}  Day {day_in_season(day) + 1}/{DAYS_PER_SEASON}"


def ambient_temperature_c(day: float) -> float:
    """Air temperature (°C) from a −cos annual wave.

    Mid-winter ≈ ``TEMP_WINTER_C``, mid-summer ≈ ``TEMP_SUMMER_C``.
    """
    d = float(day) % YEAR_DAYS
    phase = 2.0 * math.pi * (d - _MID_WINTER_DAY) / float(YEAR_DAYS)
    mid = 0.5 * (TEMP_WINTER_C + TEMP_SUMMER_C)
    amp = 0.5 * (TEMP_SUMMER_C - TEMP_WINTER_C)
    return mid + amp * (-math.cos(phase))


def _temp_mid_c() -> float:
    return 0.5 * (TEMP_WINTER_C + TEMP_SUMMER_C)


def _raw_severity_from_frac(frac: float) -> int:
    """Map 0..1 progress toward an extreme onto impact levels 1–3."""
    f = max(0.0, min(1.0, float(frac)))
    if f <= 0.0:
        return 0
    if f < 1.0 / 3.0:
        return 1
    if f < 2.0 / 3.0:
        return 2
    return 3


def raw_temperature_levels(temp_c: float) -> tuple[int, int]:
    """Return ``(heat_raw, cold_raw)``; at most one side is non-zero (0–3)."""
    mid = _temp_mid_c()
    t = float(temp_c)
    # Tiny epsilon so floating-point midpoints stay at level 0.
    if abs(t - mid) < 1e-6:
        return 0, 0
    if t > mid:
        span = TEMP_SUMMER_C - mid
        frac = (t - mid) / span if span > 0 else 0.0
        return _raw_severity_from_frac(frac), 0
    span = mid - TEMP_WINTER_C
    frac = (mid - t) / span if span > 0 else 0.0
    return 0, _raw_severity_from_frac(frac)


@dataclass(frozen=True)
class TempImpact:
    """Resolved hot/cold impact after clothing protection."""

    kind: str  # "none" | "hot" | "cold"
    level: int  # 0–3 after protection
    raw_level: int
    protection: int
    walk_mult: float
    energy_mult: float
    temp_c: float

    @property
    def active(self) -> bool:
        return self.level > 0 and self.kind in ("hot", "cold")


def temperature_impact(
    temp_c: float,
    heat_protection: float = 0.0,
    cold_protection: float = 0.0,
) -> TempImpact:
    """Hot/cold level after subtracting worn protection points.

    At max summer heat the raw heat level is 3; each point of heat protection
    reduces it (e.g. sun hat = 2 → final level 1 → walk ×0.9, energy ×1.1).
    Cold works the same with cold protection.
    """
    heat_raw, cold_raw = raw_temperature_levels(temp_c)
    if heat_raw > 0:
        prot = max(0, int(round(float(heat_protection))))
        level = max(0, min(3, heat_raw - prot))
        return TempImpact(
            kind="hot" if level > 0 else "none",
            level=level,
            raw_level=heat_raw,
            protection=prot,
            walk_mult=TEMP_WALK_MULT[level],
            energy_mult=TEMP_ENERGY_MULT[level],
            temp_c=float(temp_c),
        )
    if cold_raw > 0:
        prot = max(0, int(round(float(cold_protection))))
        level = max(0, min(3, cold_raw - prot))
        return TempImpact(
            kind="cold" if level > 0 else "none",
            level=level,
            raw_level=cold_raw,
            protection=prot,
            walk_mult=TEMP_WALK_MULT[level],
            energy_mult=TEMP_ENERGY_MULT[level],
            temp_c=float(temp_c),
        )
    return TempImpact(
        kind="none",
        level=0,
        raw_level=0,
        protection=0,
        walk_mult=1.0,
        energy_mult=1.0,
        temp_c=float(temp_c),
    )


def next_season(current: Season) -> Season:
    idx = SEASON_ORDER.index(current)
    return SEASON_ORDER[(idx + 1) % len(SEASON_ORDER)]


def tile_phase(x: int, y: int) -> float:
    """Stable 0..1 hash per tile for staggered transitions."""
    n = (x * 374761393 + y * 668265263) & 0x7FFFFFFF
    return (n % 1000) / 1000.0


def _clamp01(v: float) -> float:
    return 0.0 if v <= 0.0 else 1.0 if v >= 1.0 else v


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    if edge1 <= edge0:
        return 1.0 if x >= edge1 else 0.0
    t = _clamp01((x - edge0) / (edge1 - edge0))
    return t * t * (3.0 - 2.0 * t)


def local_day(day: float, x: int, y: int, stagger: float = TILE_STAGGER_DAYS) -> float:
    """Day-of-year shifted earlier/later per tile."""
    return float(day) - tile_phase(x, y) * stagger


def _year_pos(day: float) -> float:
    return day % YEAR_DAYS


# --- Presence / rate envelopes (day-of-year 0..YEAR_DAYS) -----------------
# Spring 0-28, Summer 28-56, Autumn 56-84, Winter 84-112
# Tunables live in ``wild_species.py``; these wrappers keep tile stagger.


def herb_spawn_rate(day: float, x: int, y: int) -> float:
    """Chance per herb-tick for an empty grass tile to sprout a herb."""
    leader = spawn_group_leader("wild_crop")
    if leader is None:
        return 0.0
    return species_spawn_rate(leader, local_day(day, x, y))


def herb_despawn_rate(day: float, x: int, y: int) -> float:
    """Chance per herb-tick for an existing herb to wither."""
    leader = spawn_group_leader("wild_crop")
    if leader is None:
        return 0.0
    return species_despawn_rate(leader, local_day(day, x, y))


def reed_spawn_rate(day: float, x: int, y: int) -> float:
    """Chance per herb-tick for an empty riparian tile to sprout reeds."""
    return species_spawn_rate(WILD_BY_KEY["reed"], local_day(day, x, y))


def reed_despawn_rate(day: float, x: int, y: int) -> float:
    """Reeds persist year-round once established."""
    return species_despawn_rate(WILD_BY_KEY["reed"], local_day(day, x, y))


def berry_spawn_rate(day: float, x: int, y: int) -> float:
    """Legacy envelope (natural bush spawn is disabled)."""
    return species_spawn_rate(WILD_BY_KEY["berry_bush"], local_day(day, x, y))


def berry_fruiting(day: float, x: int = 0, y: int = 0) -> bool:
    """True throughout spring and summer; bush coordinates do not shift it."""
    del x, y
    return season_for_day(int(day)) in (Season.SPRING, Season.SUMMER)


def berry_despawn_rate(day: float, x: int, y: int) -> float:
    # Bushes are permanent; legacy callers still get a no-op fade of 0.
    del day, x, y
    return 0.0


def mushroom_spawn_rate(day: float, x: int, y: int) -> float:
    """Autumn only — stop before winter (day 84)."""
    return species_spawn_rate(WILD_BY_KEY["mushroom"], local_day(day, x, y))


def wood_bush_spawn_rate(day: float, x: int, y: int) -> float:
    """Fallen wood near trees — peaks through autumn, gone by winter."""
    return species_spawn_rate(WILD_BY_KEY["wood_bush"], local_day(day, x, y))


def mushroom_despawn_rate(day: float, x: int, y: int) -> float:
    """Clear as winter begins; no lingering mushrooms in winter."""
    return species_despawn_rate(WILD_BY_KEY["mushroom"], local_day(day, x, y))


def trees_grow_factor(day: float) -> float:
    """1 in spring/summer growth window, 0 in deep winter."""
    d = _year_pos(day)
    warm = _smoothstep(0.0, 6.0, d) * (1.0 - _smoothstep(52.0, 62.0, d))
    return warm


def trees_spread_factor(day: float) -> float:
    d = _year_pos(day)
    return _smoothstep(56.0, 66.0, d) * (1.0 - _smoothstep(78.0, 88.0, d))


def freeze_amount(day: float) -> float:
    """0 open water … 1 solid ice. Ramps late autumn → winter, thaws in spring."""
    d = _year_pos(day)
    if d >= 78.0:
        return _smoothstep(78.0, 92.0, d)
    if d <= 12.0:
        return max(0.0, 1.0 - _smoothstep(0.0, 12.0, d))
    return 0.0


def terrain_vibrancy(day: float) -> float:
    """Colour saturation multiplier: dull winter → vivid summer."""
    d = _year_pos(day)
    # Peak mid-summer (~42), trough mid-winter (~98).
    summer = _smoothstep(20.0, 40.0, d) * (1.0 - _smoothstep(50.0, 70.0, d))
    # Base 0.62, up to 1.0 in summer, down further when frozen.
    return _clamp01(0.62 + 0.38 * summer - 0.18 * freeze_amount(d))


def grass_winter_fade(day: float) -> float:
    """0..1 winter wash on grass / meadow."""
    d = _year_pos(day)
    # Late autumn → winter peak → thaw in early spring.
    if d >= 70.0:
        return _smoothstep(70.0, 88.0, d)
    if d <= 16.0:
        return max(0.0, 1.0 - _smoothstep(0.0, 16.0, d))
    return 0.0


def summer_bloom(day: float) -> float:
    """0..1 mid-summer verdancy for grass speckles / soil greens.

    Peaks early–mid summer and eases off before late summer so flecks
    don't stay fully bright into the autumn shoulder.
    """
    d = _year_pos(day)
    return _smoothstep(22.0, 34.0, d) * (1.0 - _smoothstep(46.0, 58.0, d))


def autumn_bloom(day: float) -> float:
    """0..1 autumn leaf-tint speckles on grass / meadow / soil.

    Begins late summer so mid-summer→autumn sample windows already show flecks.
    """
    d = _year_pos(day)
    return _smoothstep(46.0, 56.0, d) * (1.0 - _smoothstep(78.0, 90.0, d))


def growth_halted(day: float) -> bool:
    return freeze_amount(day) >= 0.85


def water_frozen(day: float) -> bool:
    return freeze_amount(day) >= 0.45


def fishing_allowed(day: float) -> bool:
    """Rivers stay open year-round; fishing is never season-locked.

    Lake ice is visual only — breeding is gated separately via
    ``fish_breeding_allowed``.
    """
    del day
    return True


def fish_breeding_allowed(day: float) -> bool:
    """Fish populations grow in spring and summer only."""
    return season_for_day(int(day)) in (Season.SPRING, Season.SUMMER)


def animals_slow(day: float) -> bool:
    return freeze_amount(day) >= 0.35


def animals_multiply(day: float) -> bool:
    return freeze_amount(day) < 0.55


def seed_chance_multiplier(day: float) -> float:
    d = _year_pos(day)
    # Peak through autumn harvest.
    autumn = _smoothstep(56.0, 66.0, d) * (1.0 - _smoothstep(82.0, 92.0, d))
    return 1.0 + (AUTUMN_SEED_MULTIPLIER - 1.0) * autumn


def adjust_colour(
    colour: tuple[int, ...], vibrancy: float
) -> tuple[int, ...]:
    """Lerp toward muted grey-green when vibrancy is low."""
    r, g, b = colour[:3]
    mute_r, mute_g, mute_b = 72, 78, 70
    t = _clamp01(vibrancy)
    result = (
        int(mute_r + (r - mute_r) * t),
        int(mute_g + (g - mute_g) * t),
        int(mute_b + (b - mute_b) * t),
    )
    return result+(int(colour[3]),) if len(colour)>3 else result


def blend_colour(
    a: tuple[int, int, int], b: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    t = _clamp01(t)
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


# --- Back-compat wrappers used by older call sites expecting Season ------


def herbs_active(season: Season) -> bool:
    return season == Season.SPRING


def berries_active(season: Season) -> bool:
    return season == Season.SUMMER


def mushrooms_active(season: Season) -> bool:
    return season == Season.AUTUMN


def wood_bushes_active(season: Season) -> bool:
    return season == Season.AUTUMN


def trees_grow(season: Season) -> bool:
    return season in (Season.SPRING, Season.SUMMER)


def trees_spread(season: Season) -> bool:
    return season == Season.AUTUMN
