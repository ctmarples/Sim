"""Persistent terrain look settings (mottle per biome, flecks per season).

Saved from the previewer to ``assets/terrain/terrain_look.json`` and loaded
by the game bake / seasonal overlay path.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

from seasons import DAYS_PER_SEASON, YEAR_DAYS
from terrain_flecks import FleckParams, clear_fleck_cache, period_for_day
from terrain_mottle import MottleParams, clear_mottle_cache
from terrain_overlays import OverlayParams, clear_overlay_cache
from world import TerrainType

_SETTINGS_PATH = Path(__file__).resolve().parent / "assets" / "terrain" / "terrain_look.json"

# Biomes that get independent mottling knobs.
MOTTLE_BIOMES: tuple[TerrainType, ...] = (
    TerrainType.GRASS,
    TerrainType.MEADOW,
    TerrainType.SOIL,
    TerrainType.FOREST_FLOOR,
    TerrainType.RIPARIAN,
    TerrainType.ROCK,
    TerrainType.PATH,
    TerrainType.URBAN,
    TerrainType.WATER,
    TerrainType.RIVER,
)

N_PERIODS = 8


@dataclass
class AnimParams:
    """How season flecks crossfade (mirrors game season-mask fade)."""

    fade_days: float = 2.5
    # 0 = linear, 1 = full smoothstep ease.
    fade_ease: float = 1.0
    # Fraction of the fade before the incoming overlay starts rising (0..1).
    intro_delay: float = 0.15
    # Fraction of the fade the outgoing overlay stays full before falling (0..1).
    exit_hold: float = 0.1
    # Master opacity for fleck overlays (0..1.5).
    opacity: float = 1.0
    # When True, preview auto-advances the year scrubber.
    autoplay: bool = False
    # In-game days advanced per real second while autoplaying.
    autoplay_speed: float = 4.0


# Mutable stores (loaded from disk if present).
_MOTTLE: dict[TerrainType, MottleParams] = {
    t: MottleParams(seed=t.value * 17) for t in MOTTLE_BIOMES
}
_OVERLAY: dict[TerrainType, OverlayParams] = {
    t: OverlayParams(seed=t.value * 23) for t in MOTTLE_BIOMES
}
_FLECKS: dict[int, FleckParams] = {i: FleckParams(seed=i * 101) for i in range(N_PERIODS)}
_ANIM = AnimParams()
_LOADED = False


def settings_path() -> Path:
    return _SETTINGS_PATH


def get_anim_params() -> AnimParams:
    _ensure_loaded()
    return _ANIM


def set_anim_params(params: AnimParams) -> None:
    global _ANIM
    _ANIM = params


def get_mottle(terrain: TerrainType) -> MottleParams:
    _ensure_loaded()
    key = TerrainType.WATER if terrain == TerrainType.RIVER else terrain
    hit = _MOTTLE.get(key)
    if hit is not None:
        return hit
    # Fallback for unexpected types.
    return _MOTTLE.setdefault(key, MottleParams(seed=key.value * 17))


def set_mottle(terrain: TerrainType, params: MottleParams) -> None:
    key = TerrainType.WATER if terrain == TerrainType.RIVER else terrain
    _MOTTLE[key] = params
    clear_mottle_cache()


def update_mottle(terrain: TerrainType, **kwargs: float | int | bool) -> MottleParams:
    p = replace(get_mottle(terrain), **kwargs)
    set_mottle(terrain, p)
    return p


def get_overlay(terrain: TerrainType) -> OverlayParams:
    _ensure_loaded()
    key = TerrainType.WATER if terrain == TerrainType.RIVER else terrain
    hit = _OVERLAY.get(key)
    if hit is not None:
        return hit
    return _OVERLAY.setdefault(key, OverlayParams(seed=key.value * 23))


def set_overlay(terrain: TerrainType, params: OverlayParams) -> None:
    key = TerrainType.WATER if terrain == TerrainType.RIVER else terrain
    _OVERLAY[key] = params
    clear_overlay_cache()


def update_overlay(terrain: TerrainType, **kwargs: float | int | bool) -> OverlayParams:
    p = replace(get_overlay(terrain), **kwargs)
    set_overlay(terrain, p)
    return p


def get_fleck(period: int) -> FleckParams:
    _ensure_loaded()
    p = int(period) & 7
    return _FLECKS.setdefault(p, FleckParams(seed=p * 101))


def set_fleck(period: int, params: FleckParams) -> None:
    _FLECKS[int(period) & 7] = params
    clear_fleck_cache()


def update_fleck(period: int, **kwargs: float | int | bool) -> FleckParams:
    p = replace(get_fleck(period), **kwargs)
    set_fleck(period, p)
    return p


def reset_defaults() -> None:
    global _MOTTLE, _OVERLAY, _FLECKS, _ANIM
    _MOTTLE = {t: MottleParams(seed=t.value * 17) for t in MOTTLE_BIOMES}
    _OVERLAY = {t: OverlayParams(seed=t.value * 23) for t in MOTTLE_BIOMES}
    _FLECKS = {i: FleckParams(seed=i * 101) for i in range(N_PERIODS)}
    _ANIM = AnimParams()
    clear_mottle_cache()
    clear_overlay_cache()
    clear_fleck_cache()


def _params_from_dict(cls: type, data: dict) -> object:
    names = {f.name for f in fields(cls)}
    kwargs = {k: v for k, v in data.items() if k in names}
    return cls(**kwargs)


def export_dict() -> dict:
    return {
        "version": 1,
        "mottle": {t.name: asdict(p) for t, p in _MOTTLE.items()},
        "overlays": {t.name: asdict(p) for t, p in _OVERLAY.items()},
        "flecks": {str(i): asdict(p) for i, p in sorted(_FLECKS.items())},
        "animation": asdict(_ANIM),
    }


def import_dict(data: dict) -> None:
    global _MOTTLE, _OVERLAY, _FLECKS, _ANIM
    mottle_raw = data.get("mottle") or {}
    overlay_raw = data.get("overlays") or {}
    flecks_raw = data.get("flecks") or {}
    anim_raw = data.get("animation") or {}

    mottle: dict[TerrainType, MottleParams] = {
        t: MottleParams(seed=t.value * 17) for t in MOTTLE_BIOMES
    }
    for name, blob in mottle_raw.items():
        try:
            terr = TerrainType[name]
        except KeyError:
            continue
        if isinstance(blob, dict):
            mottle[terr] = _params_from_dict(MottleParams, blob)  # type: ignore[assignment]

    overlays: dict[TerrainType, OverlayParams] = {
        t: OverlayParams(seed=t.value * 23) for t in MOTTLE_BIOMES
    }
    for name, blob in overlay_raw.items():
        try:
            terr = TerrainType[name]
        except KeyError:
            continue
        if isinstance(blob, dict):
            overlays[terr] = _params_from_dict(OverlayParams, blob)  # type: ignore[assignment]

    flecks: dict[int, FleckParams] = {
        i: FleckParams(seed=i * 101) for i in range(N_PERIODS)
    }
    for key, blob in flecks_raw.items():
        try:
            period = int(key) & 7
        except (TypeError, ValueError):
            continue
        if isinstance(blob, dict):
            flecks[period] = _params_from_dict(FleckParams, blob)  # type: ignore[assignment]

    anim = (
        _params_from_dict(AnimParams, anim_raw)  # type: ignore[assignment]
        if isinstance(anim_raw, dict)
        else AnimParams()
    )

    _MOTTLE = mottle
    _OVERLAY = overlays
    _FLECKS = flecks
    _ANIM = anim  # type: ignore[assignment]
    clear_mottle_cache()
    clear_overlay_cache()
    clear_fleck_cache()


def save_settings(path: Path | None = None) -> Path:
    dest = path or _SETTINGS_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(export_dict(), indent=2) + "\n", encoding="utf-8")
    return dest


def load_settings(path: Path | None = None) -> bool:
    """Load from disk. Returns True if a file was found and applied."""
    global _LOADED
    src = path or _SETTINGS_PATH
    _LOADED = True
    if not src.is_file():
        return False
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    import_dict(data)
    return True


def _ensure_loaded() -> None:
    global _LOADED
    if not _LOADED:
        load_settings()


def season_transition(
    day: float,
    *,
    anim: AnimParams | None = None,
) -> tuple[int, int | None, float]:
    """Map a continuous year-day to (to_period, from_period|None, blend t).

    ``t`` is 0 at the start of the fade into ``to_period`` and 1 when settled.
    Outside the fade window, ``from_period`` is None and ``t`` is 1.0.
    """
    a = anim if anim is not None else get_anim_params()
    day = float(day) % float(YEAR_DAYS)
    to_period = period_for_day(int(day))
    half = max(1, DAYS_PER_SEASON // 2)
    pos = day % half
    fade = max(0.05, float(a.fade_days))
    if pos >= fade:
        return to_period, None, 1.0
    raw = pos / fade
    # Ease.
    ease = max(0.0, min(1.0, float(a.fade_ease)))
    if ease > 0.0:
        s = raw * raw * (3.0 - 2.0 * raw)
        t = raw * (1.0 - ease) + s * ease
    else:
        t = raw
    from_period = (to_period - 1) & 7
    return to_period, from_period, t


def fade_alphas(
    t: float,
    *,
    anim: AnimParams | None = None,
) -> tuple[float, float]:
    """Return (from_alpha, to_alpha) for a crossfade progress ``t`` in 0..1."""
    a = anim if anim is not None else get_anim_params()
    t = 0.0 if t <= 0.0 else 1.0 if t >= 1.0 else t
    intro = max(0.0, min(0.9, float(a.intro_delay)))
    hold = max(0.0, min(0.9, float(a.exit_hold)))
    if hold + intro > 0.95:
        scale = 0.95 / (hold + intro)
        hold *= scale
        intro *= scale

    # Outgoing: full until exit_hold, then fall to 0 by (1 - leftover).
    if t <= hold:
        from_a = 1.0
    else:
        span = max(1e-6, 1.0 - hold)
        from_a = max(0.0, 1.0 - (t - hold) / span)

    # Incoming: zero until intro_delay, then rise to 1.
    if t <= intro:
        to_a = 0.0
    else:
        span = max(1e-6, 1.0 - intro)
        to_a = min(1.0, (t - intro) / span)

    return from_a, to_a


def snapshot() -> dict:
    """Deep-copy export for undo / diagnostics."""
    return deepcopy(export_dict())
