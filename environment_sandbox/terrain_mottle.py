"""World-UV procedural terrain mottling (palette + multi-scale noise).

Non-repeating continuous world noise (no period tile). Game bake uses
numpy + chunk cache so a full map stays interactive; preview samples the
same field.

Optional post filters: Gaussian (on/off) and 1:1 smooth resample.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, fields, replace

import numpy as np
import pygame

from settings import (
    COLOUR_FOREST_FLOOR,
    COLOUR_GRASS,
    COLOUR_MEADOW,
    COLOUR_PATH,
    COLOUR_RIPARIAN,
    COLOUR_ROCK_TERRAIN,
    COLOUR_SOIL,
    COLOUR_URBAN,
    COLOUR_WATER,
    TERRAIN_SUBDIV,
)
from world import TerrainType

TILE = TERRAIN_SUBDIV
Colour = tuple[int, int, int]

# World chunks for fast bake (continuous UV; not a repeating period tile).
_CHUNK = 256

_COLOURS: dict[TerrainType, Colour] = {
    TerrainType.SOIL: COLOUR_SOIL,
    TerrainType.FOREST_FLOOR: COLOUR_FOREST_FLOOR,
    TerrainType.GRASS: COLOUR_GRASS,
    TerrainType.MEADOW: COLOUR_MEADOW,
    TerrainType.RIPARIAN: COLOUR_RIPARIAN,
    TerrainType.WATER: COLOUR_WATER,
    TerrainType.RIVER: COLOUR_WATER,
    TerrainType.ROCK: COLOUR_ROCK_TERRAIN,
    TerrainType.URBAN: COLOUR_URBAN,
    TerrainType.PATH: COLOUR_PATH,
}

_DEFAULT_PALETTE: dict[TerrainType, tuple[Colour, ...]] = {
    TerrainType.GRASS: (
        (72, 140, 48),
        (96, 158, 52),
        (58, 118, 40),
        (110, 168, 64),
        (84, 132, 44),
    ),
    TerrainType.MEADOW: (
        (100, 170, 55),
        (120, 185, 70),
        (85, 155, 48),
        (140, 195, 80),
    ),
    TerrainType.SOIL: (
        (130, 95, 55),
        (150, 110, 65),
        (110, 80, 48),
        (165, 120, 75),
    ),
    TerrainType.FOREST_FLOOR: (
        (95, 68, 42),
        (120, 85, 50),
        (80, 58, 36),
        (140, 100, 55),
        (160, 120, 60),
    ),
    TerrainType.RIPARIAN: (
        (70, 130, 70),
        (90, 145, 85),
        (55, 110, 60),
        (100, 150, 95),
    ),
    TerrainType.ROCK: (
        (110, 110, 115),
        (130, 130, 135),
        (90, 90, 95),
        (150, 148, 145),
    ),
    TerrainType.PATH: (
        (120, 118, 112),
        (140, 136, 128),
        (100, 98, 94),
        (155, 150, 142),
    ),
    TerrainType.URBAN: (
        (105, 105, 108),
        (125, 125, 128),
        (88, 88, 92),
    ),
    TerrainType.WATER: (
        (45, 105, 160),
        (55, 125, 175),
        (35, 90, 145),
        (70, 140, 185),
    ),
    TerrainType.RIVER: (
        (45, 105, 160),
        (55, 125, 175),
        (35, 90, 145),
    ),
}

_MID_COS = math.cos(math.radians(37.0))
_MID_SIN = math.sin(math.radians(37.0))
_FINE_COS = math.cos(math.radians(71.0))
_FINE_SIN = math.sin(math.radians(71.0))


@dataclass
class MottleParams:
    """Live-tunable mottling knobs (also used by the previewer)."""

    coarse_scale: float = 0.035
    mid_scale: float = 0.11
    fine_scale: float = 0.38
    coarse_amp: float = 0.22
    mid_amp: float = 0.12
    fine_amp: float = 0.07
    speckle: float = 0.14
    palette_mix: float = 0.65
    gaussian: bool = False
    smooth_resample: bool = True
    seed: int = 0


PARAMS = MottleParams()

_CHUNK_CACHE: dict[tuple, pygame.Surface] = {}
_REGION_CACHE: dict[tuple, pygame.Surface] = {}
_PALETTE_OVERRIDE: dict[TerrainType, list[Colour]] = {}


def get_params() -> MottleParams:
    return PARAMS


def set_params(params: MottleParams) -> None:
    global PARAMS
    PARAMS = params
    clear_mottle_cache()


def update_params(**kwargs: float | int | bool) -> MottleParams:
    global PARAMS
    PARAMS = replace(PARAMS, **kwargs)
    clear_mottle_cache()
    return PARAMS


def clear_mottle_cache() -> None:
    _CHUNK_CACHE.clear()
    _REGION_CACHE.clear()


def params_as_dict() -> dict:
    return asdict(PARAMS)


def param_fields() -> tuple[str, ...]:
    return tuple(f.name for f in fields(MottleParams))


def _params_key(p: MottleParams) -> tuple:
    return (
        p.seed,
        p.coarse_scale,
        p.mid_scale,
        p.fine_scale,
        p.coarse_amp,
        p.mid_amp,
        p.fine_amp,
        p.speckle,
        p.palette_mix,
        bool(p.gaussian),
        bool(p.smooth_resample),
    )


def _hash01(x: int, y: int, salt: int = 0) -> float:
    n = (x * 374761393) ^ (y * 668265263) ^ (salt * 1274126177)
    n = (n ^ (n >> 13)) * 1274126177
    n ^= n >> 16
    return (n & 0x7FFFFFFF) / float(0x7FFFFFFF)


def _hash01_arr(x: np.ndarray, y: np.ndarray, salt: int) -> np.ndarray:
    n = (
        (x.astype(np.int64) * np.int64(374761393))
        ^ (y.astype(np.int64) * np.int64(668265263))
        ^ np.int64(salt * 1274126177)
    )
    n = (n ^ (n >> np.int64(13))) * np.int64(1274126177)
    n = n ^ (n >> np.int64(16))
    return (n & np.int64(0x7FFFFFFF)).astype(np.float64) / float(0x7FFFFFFF)


def _smoothstep(t: float) -> float:
    t = 0.0 if t <= 0.0 else 1.0 if t >= 1.0 else t
    return t * t * (3.0 - 2.0 * t)


def _smoothstep_arr(t: np.ndarray) -> np.ndarray:
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _lerp_colour(a: Colour, b: Colour, t: float) -> Colour:
    t = 0.0 if t <= 0.0 else 1.0 if t >= 1.0 else t
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _shift(colour: Colour, amount: float) -> Colour:
    r, g, b = colour
    if amount >= 0:
        return (
            min(255, int(r + (255 - r) * amount)),
            min(255, int(g + (255 - g) * amount)),
            min(255, int(b + (255 - b) * amount)),
        )
    a = -amount
    return (
        max(0, int(r * (1.0 - a))),
        max(0, int(g * (1.0 - a))),
        max(0, int(b * (1.0 - a))),
    )


def _value_noise(x: float, y: float, salt: int) -> float:
    x0, y0 = math.floor(x), math.floor(y)
    fx, fy = x - x0, y - y0
    sx, sy = _smoothstep(fx), _smoothstep(fy)
    n00 = _hash01(x0, y0, salt)
    n10 = _hash01(x0 + 1, y0, salt)
    n01 = _hash01(x0, y0 + 1, salt)
    n11 = _hash01(x0 + 1, y0 + 1, salt)
    return _lerp(_lerp(n00, n10, sx), _lerp(n01, n11, sx), sy)


def _value_noise_arr(xs: np.ndarray, ys: np.ndarray, salt: int) -> np.ndarray:
    x0 = np.floor(xs).astype(np.int64)
    y0 = np.floor(ys).astype(np.int64)
    fx = xs - x0.astype(np.float64)
    fy = ys - y0.astype(np.float64)
    sx = _smoothstep_arr(fx)
    sy = _smoothstep_arr(fy)
    n00 = _hash01_arr(x0, y0, salt)
    n10 = _hash01_arr(x0 + 1, y0, salt)
    n01 = _hash01_arr(x0, y0 + 1, salt)
    n11 = _hash01_arr(x0 + 1, y0 + 1, salt)
    top = n00 + (n10 - n00) * sx
    bot = n01 + (n11 - n01) * sx
    return top + (bot - top) * sy


def palette_for(terrain: TerrainType) -> list[Colour]:
    hit = _PALETTE_OVERRIDE.get(terrain)
    if hit:
        return hit
    try:
        from terrain_fills import ensure_palette, _STEM

        stem = _STEM.get(terrain)
        if stem:
            colours, _w, _cdf = ensure_palette(terrain)
            if colours:
                return list(colours[:48])
    except Exception:
        pass
    base = _DEFAULT_PALETTE.get(terrain)
    if base:
        return list(base)
    return [_COLOURS.get(terrain, COLOUR_GRASS)]


def set_palette_override(terrain: TerrainType, colours: list[Colour] | None) -> None:
    if colours is None:
        _PALETTE_OVERRIDE.pop(terrain, None)
    else:
        _PALETTE_OVERRIDE[terrain] = list(colours)
    clear_mottle_cache()


def sample_mottle(
    terrain: TerrainType,
    wx: int,
    wy: int,
    params: MottleParams | None = None,
) -> Colour:
    """Opaque mottled colour at unique world pixel (no tiling)."""
    p = PARAMS if params is None else params
    base = _COLOURS.get(terrain, COLOUR_GRASS)
    salt = 1000 + terrain.value * 97 + int(p.seed) * 13

    c_n = _value_noise(wx * p.coarse_scale, wy * p.coarse_scale, salt)
    mx = wx * _MID_COS - wy * _MID_SIN
    my = wx * _MID_SIN + wy * _MID_COS
    m_n = _value_noise(mx * p.mid_scale, my * p.mid_scale, salt + 3)
    fx = wx * _FINE_COS - wy * _FINE_SIN
    fy = wx * _FINE_SIN + wy * _FINE_COS
    f_n = _value_noise(fx * p.fine_scale, fy * p.fine_scale, salt + 7)

    shade = (c_n - 0.5) * 2.0 * p.coarse_amp
    shade += (m_n - 0.5) * 2.0 * p.mid_amp
    shade += (f_n - 0.5) * 2.0 * p.fine_amp
    shaded = _shift(base, shade)

    palette = palette_for(terrain)
    mix_field = _smoothstep(0.35 + 0.55 * c_n + 0.15 * (m_n - 0.5))
    idx = int(_hash01(wx // 2, wy // 2, salt + 21) * len(palette)) % len(palette)
    mixed = _lerp_colour(shaded, palette[idx], p.palette_mix * mix_field)

    if p.speckle > 0.0 and _hash01(wx, wy, salt + 40) > (1.0 - p.speckle):
        speck = palette[int(_hash01(wx, wy, salt + 41) * len(palette)) % len(palette)]
        mixed = _lerp_colour(mixed, speck, 0.55)

    return mixed


def _fill_raw_array(
    terrain: TerrainType,
    x0: int,
    y0: int,
    w: int,
    h: int,
    params: MottleParams,
) -> np.ndarray:
    """RGB uint8 array (h, w, 3) of unique world-UV mottling."""
    p = params
    base = _COLOURS.get(terrain, COLOUR_GRASS)
    salt = 1000 + terrain.value * 97 + int(p.seed) * 13
    palette = palette_for(terrain)
    pal = np.asarray(palette, dtype=np.float64)
    n_pal = len(palette)

    xs = (np.arange(w, dtype=np.float64) + x0)[None, :]
    ys = (np.arange(h, dtype=np.float64) + y0)[:, None]
    wx = np.broadcast_to(xs, (h, w)).astype(np.int64)
    wy = np.broadcast_to(ys, (h, w)).astype(np.int64)
    wxf = wx.astype(np.float64)
    wyf = wy.astype(np.float64)

    c_n = _value_noise_arr(wxf * p.coarse_scale, wyf * p.coarse_scale, salt)
    mx = wxf * _MID_COS - wyf * _MID_SIN
    my = wxf * _MID_SIN + wyf * _MID_COS
    m_n = _value_noise_arr(mx * p.mid_scale, my * p.mid_scale, salt + 3)
    fx = wxf * _FINE_COS - wyf * _FINE_SIN
    fy = wxf * _FINE_SIN + wyf * _FINE_COS
    f_n = _value_noise_arr(fx * p.fine_scale, fy * p.fine_scale, salt + 7)

    shade = (c_n - 0.5) * 2.0 * p.coarse_amp
    shade = shade + (m_n - 0.5) * 2.0 * p.mid_amp
    shade = shade + (f_n - 0.5) * 2.0 * p.fine_amp

    br = np.full((h, w), float(base[0]), dtype=np.float64)
    bg = np.full((h, w), float(base[1]), dtype=np.float64)
    bb = np.full((h, w), float(base[2]), dtype=np.float64)
    pos = shade >= 0.0
    amt = np.abs(shade)
    br = np.where(pos, br + (255.0 - br) * amt, br * (1.0 - amt))
    bg = np.where(pos, bg + (255.0 - bg) * amt, bg * (1.0 - amt))
    bb = np.where(pos, bb + (255.0 - bb) * amt, bb * (1.0 - amt))

    mix_field = _smoothstep_arr(0.35 + 0.55 * c_n + 0.15 * (m_n - 0.5))
    mix_t = np.clip(p.palette_mix * mix_field, 0.0, 1.0)
    idx = (_hash01_arr(wx // 2, wy // 2, salt + 21) * n_pal).astype(np.int64) % n_pal
    pr = pal[idx, 0]
    pg = pal[idx, 1]
    pb = pal[idx, 2]
    br = br + (pr - br) * mix_t
    bg = bg + (pg - bg) * mix_t
    bb = bb + (pb - bb) * mix_t

    if p.speckle > 0.0:
        speck_mask = _hash01_arr(wx, wy, salt + 40) > (1.0 - p.speckle)
        sidx = (_hash01_arr(wx, wy, salt + 41) * n_pal).astype(np.int64) % n_pal
        sr = pal[sidx, 0]
        sg = pal[sidx, 1]
        sb = pal[sidx, 2]
        br = np.where(speck_mask, br + (sr - br) * 0.55, br)
        bg = np.where(speck_mask, bg + (sg - bg) * 0.55, bg)
        bb = np.where(speck_mask, bb + (sb - bb) * 0.55, bb)

    out = np.empty((h, w, 3), dtype=np.uint8)
    out[..., 0] = np.clip(br, 0, 255).astype(np.uint8)
    out[..., 1] = np.clip(bg, 0, 255).astype(np.uint8)
    out[..., 2] = np.clip(bb, 0, 255).astype(np.uint8)
    return out


def _array_to_surface(arr: np.ndarray) -> pygame.Surface:
    # pygame surfarray expects (w, h, 3)
    return pygame.surfarray.make_surface(np.transpose(arr, (1, 0, 2)))


def _gaussian_kernel(radius: int, sigma: float) -> list[float]:
    vals = [math.exp(-(i * i) / (2.0 * sigma * sigma)) for i in range(-radius, radius + 1)]
    s = sum(vals) or 1.0
    return [v / s for v in vals]


def _gaussian_blur(surf: pygame.Surface, radius: int = 2, sigma: float = 1.15) -> pygame.Surface:
    if radius <= 0:
        return surf
    arr = pygame.surfarray.array3d(surf).astype(np.float64)  # w,h,3
    kern = np.asarray(_gaussian_kernel(radius, sigma), dtype=np.float64)
    r = len(kern) // 2
    # Separable blur with edge clamp via pad
    pad_w = np.pad(arr, ((r, r), (0, 0), (0, 0)), mode="edge")
    tmp = np.zeros_like(arr)
    for i, k in enumerate(kern):
        tmp += pad_w[i : i + arr.shape[0]] * k
    pad_h = np.pad(tmp, ((0, 0), (r, r), (0, 0)), mode="edge")
    out = np.zeros_like(arr)
    for i, k in enumerate(kern):
        out += pad_h[:, i : i + arr.shape[1]] * k
    return pygame.surfarray.make_surface(np.clip(out, 0, 255).astype(np.uint8))


def _smooth_resample_1to1(surf: pygame.Surface) -> pygame.Surface:
    w, h = surf.get_size()
    return pygame.transform.smoothscale(surf, (w, h))


def apply_filters(surf: pygame.Surface, params: MottleParams | None = None) -> pygame.Surface:
    p = PARAMS if params is None else params
    out = surf
    if p.gaussian:
        out = _gaussian_blur(out)
    if p.smooth_resample:
        out = _smooth_resample_1to1(out)
    return out


def _fill_raw(
    terrain: TerrainType,
    x0: int,
    y0: int,
    w: int,
    h: int,
    params: MottleParams,
) -> pygame.Surface:
    return _array_to_surface(_fill_raw_array(terrain, x0, y0, w, h, params))


def _chunk_surface(
    terrain: TerrainType,
    chunk_x: int,
    chunk_y: int,
    params: MottleParams,
) -> pygame.Surface:
    """Filtered mottling for one world chunk [cx*_CHUNK, cy*_CHUNK)."""
    key = (terrain, chunk_x, chunk_y, _params_key(params))
    hit = _CHUNK_CACHE.get(key)
    if hit is not None:
        return hit
    pad = 2 if params.gaussian else 0
    x0 = chunk_x * _CHUNK - pad
    y0 = chunk_y * _CHUNK - pad
    raw = _fill_raw(terrain, x0, y0, _CHUNK + 2 * pad, _CHUNK + 2 * pad, params)
    filtered = apply_filters(raw, params)
    if pad:
        out = filtered.subsurface(pygame.Rect(pad, pad, _CHUNK, _CHUNK)).copy()
    else:
        out = filtered
    _CHUNK_CACHE[key] = out
    return out


def world_mottle_surface(
    terrain: TerrainType,
    cell_x: int,
    cell_y: int,
    size: int,
    params: MottleParams | None = None,
) -> pygame.Surface:
    """``size``×``size`` unique world-UV mottling for one game cell (chunk-backed)."""
    p = PARAMS if params is None else params
    wx0 = cell_x * size
    wy0 = cell_y * size
    out = pygame.Surface((size, size))
    y = wy0
    while y < wy0 + size:
        x = wx0
        row_h = 0
        while x < wx0 + size:
            cx = x // _CHUNK
            cy = y // _CHUNK
            chunk = _chunk_surface(terrain, int(cx), int(cy), p)
            src_x = x - cx * _CHUNK
            src_y = y - cy * _CHUNK
            copy_w = min(wx0 + size - x, _CHUNK - src_x)
            copy_h = min(wy0 + size - y, _CHUNK - src_y)
            out.blit(
                chunk,
                (x - wx0, y - wy0),
                pygame.Rect(src_x, src_y, copy_w, copy_h),
            )
            row_h = copy_h
            x += copy_w
        y += row_h
    return out


def world_mottle_region(
    terrain: TerrainType,
    x0: int,
    y0: int,
    width: int,
    height: int,
    params: MottleParams | None = None,
) -> pygame.Surface:
    """Continuous mottling over a world-pixel rectangle (preview / diagnostics)."""
    p = PARAMS if params is None else params
    key = (terrain, x0, y0, width, height, _params_key(p))
    hit = _REGION_CACHE.get(key)
    if hit is not None:
        return hit
    if width * height <= _CHUNK * _CHUNK:
        raw = _fill_raw(terrain, x0, y0, width, height, p)
        out = apply_filters(raw, p)
    else:
        out = pygame.Surface((width, height))
        y = y0
        while y < y0 + height:
            x = x0
            row_h = 0
            while x < x0 + width:
                cx = x // _CHUNK
                cy = y // _CHUNK
                chunk = _chunk_surface(terrain, int(cx), int(cy), p)
                src_x = x - cx * _CHUNK
                src_y = y - cy * _CHUNK
                copy_w = min(x0 + width - x, _CHUNK - src_x)
                copy_h = min(y0 + height - y, _CHUNK - src_y)
                out.blit(
                    chunk,
                    (x - x0, y - y0),
                    pygame.Rect(src_x, src_y, copy_w, copy_h),
                )
                row_h = copy_h
                x += copy_w
            y += row_h
    _REGION_CACHE[key] = out
    return out
