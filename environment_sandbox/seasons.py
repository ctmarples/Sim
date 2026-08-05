"""Calendar, seasons, and gradual ecology envelopes."""

from __future__ import annotations

from enum import Enum, auto

from resource_balance import (
    BERRY_DESPAWN_FADE,
    BERRY_DESPAWN_LEFTOVER,
    BERRY_SPAWN_RATE_PEAK,
    HERB_DESPAWN_FADE,
    HERB_DESPAWN_LEFTOVER,
    HERB_SPAWN_RATE_PEAK,
    MUSHROOM_SPAWN_RATE_PEAK,
    WOOD_BUSH_SPAWN_RATE_PEAK,
)
from settings import FPS


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
# ~4 seconds of real time per in-game day at simulation ×1.
TICKS_PER_DAY: int = FPS * 8

# Kept for older saves that stored season_timer.
SEASON_LENGTH_TICKS: int = TICKS_PER_DAY * DAYS_PER_SEASON

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


def herb_spawn_rate(day: float, x: int, y: int) -> float:
    """Chance per herb-tick for an empty grass tile to sprout a herb."""
    d = local_day(day, x, y)
    # Rise through early spring, peak mid-spring, taper late spring.
    rise = _smoothstep(0.0, 8.0, d) * (1.0 - _smoothstep(18.0, 30.0, d))
    return HERB_SPAWN_RATE_PEAK * rise


def herb_despawn_rate(day: float, x: int, y: int) -> float:
    """Chance per herb-tick for an existing herb to wither."""
    d = local_day(day, x, y)
    # Begin late summer, finish mid-autumn.
    fade = _smoothstep(48.0, 58.0, d) * (1.0 - _smoothstep(72.0, 82.0, d))
    # Also clear any leftovers deep into autumn/winter.
    leftover = _smoothstep(70.0, 78.0, d)
    return min(1.0, HERB_DESPAWN_FADE * fade + HERB_DESPAWN_LEFTOVER * leftover)


def berry_spawn_rate(day: float, x: int, y: int) -> float:
    d = local_day(day, x, y)
    rise = _smoothstep(26.0, 36.0, d) * (1.0 - _smoothstep(48.0, 58.0, d))
    return BERRY_SPAWN_RATE_PEAK * rise


def berry_despawn_rate(day: float, x: int, y: int) -> float:
    d = local_day(day, x, y)
    fade = _smoothstep(54.0, 64.0, d) * (1.0 - _smoothstep(78.0, 88.0, d))
    leftover = _smoothstep(76.0, 84.0, d)
    return min(1.0, BERRY_DESPAWN_FADE * fade + BERRY_DESPAWN_LEFTOVER * leftover)


def mushroom_spawn_rate(day: float, x: int, y: int) -> float:
    """Autumn only — stop before winter (day 84)."""
    d = local_day(day, x, y)
    rise = _smoothstep(56.0, 64.0, d) * (1.0 - _smoothstep(78.0, 84.0, d))
    return MUSHROOM_SPAWN_RATE_PEAK * rise


def wood_bush_spawn_rate(day: float, x: int, y: int) -> float:
    """Fallen wood near trees — peaks through autumn, gone by winter."""
    d = local_day(day, x, y)
    rise = _smoothstep(54.0, 62.0, d) * (1.0 - _smoothstep(78.0, 84.0, d))
    return WOOD_BUSH_SPAWN_RATE_PEAK * rise


def mushroom_despawn_rate(day: float, x: int, y: int) -> float:
    """Clear as winter begins; no lingering mushrooms in winter."""
    d = local_day(day, x, y)
    if d >= float(DAYS_PER_SEASON * 3):  # winter start (day 84)
        return 1.0
    # Ramp hard in the last days of autumn so they vanish at the season change.
    return _smoothstep(80.0, 84.0, d)


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
    return freeze_amount(day) < 0.45


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
    colour: tuple[int, int, int], vibrancy: float
) -> tuple[int, int, int]:
    """Lerp toward muted grey-green when vibrancy is low."""
    r, g, b = colour
    mute_r, mute_g, mute_b = 72, 78, 70
    t = _clamp01(vibrancy)
    return (
        int(mute_r + (r - mute_r) * t),
        int(mute_g + (g - mute_g) * t),
        int(mute_b + (b - mute_b) * t),
    )


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
