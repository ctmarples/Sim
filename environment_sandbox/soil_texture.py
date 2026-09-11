"""Persistent continuous soil-texture field (0 = sandy/coarse … 1 = clayey/fine).

Generated once from the world seed as broad low-frequency regions with soft
terrain nudges. Terrain paint / plough must never regenerate this field.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world import World

# ---------------------------------------------------------------------------
# Tuning — keep these modest; fertility stays a separate axis.
# ---------------------------------------------------------------------------
# Regional / mid / tile noise amplitudes around a 0.45 loam centre.
TEXTURE_BASE: float = 0.45
TEXTURE_REGIONAL_AMP: float = 0.32
TEXTURE_MID_AMP: float = 0.16
TEXTURE_FINE_AMP: float = 0.04
# Soft blur radius (Chebyshev) for terrain bias so meadow↔forest stays continuous.
TEXTURE_BIAS_BLUR: int = 2
# Max |terrain bias| after blur (~0.10–0.12).
TEXTURE_BIAS_CAP: float = 0.12


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def effective_soil_texture(cell) -> float:
    """Readable 0..1 texture; unset cells (legacy / water) read as loam mid."""
    raw = float(getattr(cell, "soil_texture", -1.0))
    if raw < 0.0:
        return TEXTURE_BASE
    return clamp01(raw)


def texture_band_label(value: float) -> str:
    """Descriptive band only — not a simulation class."""
    t = clamp01(value)
    if t < 0.28:
        return "sandy"
    if t < 0.42:
        return "sandy loam"
    if t < 0.58:
        return "loam"
    if t < 0.72:
        return "clay loam"
    return "clayey"


def _terrain_bias(terrain) -> float:
    """Weak overlapping nudge from terrain; never replaces the regional field."""
    from world import TerrainType

    # Centres relative to TEXTURE_BASE (0.45). Cap magnitude via TEXTURE_BIAS_CAP.
    table = {
        TerrainType.GRASS: -0.04,  # slightly coarser open ground
        TerrainType.MEADOW: 0.03,  # near-loam centre
        TerrainType.FOREST_FLOOR: -0.02,  # very weak
        TerrainType.SOIL: 0.0,
        TerrainType.RIPARIAN: 0.10,  # modest fine-soil tendency
        TerrainType.ROCK: -0.06,
        TerrainType.PATH: -0.02,
        TerrainType.URBAN: 0.0,
        TerrainType.WATER: 0.0,
        TerrainType.RIVER: 0.0,
    }
    return float(table.get(terrain, 0.0))


def _smooth(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


def _value_noise_field(
    width: int,
    height: int,
    rng: random.Random,
    *,
    spacing: int,
    persistence: float,
) -> list[list[float]]:
    """Multi-octave bilinear value noise in 0..1 (same pattern as map generator)."""
    result = [[0.0] * width for _ in range(height)]
    amplitude = 1.0
    total_amp = 0.0
    step = max(1, int(spacing))
    while step >= 1:
        gw, gh = width // step + 2, height // step + 2
        knots = [[rng.random() for _ in range(gw)] for _ in range(gh)]
        for y in range(height):
            fy, iy = y / step, y // step
            ty = _smooth(fy - iy)
            for x in range(width):
                fx, ix = x / step, x // step
                tx = _smooth(fx - ix)
                a = knots[iy][ix] * (1 - tx) + knots[iy][ix + 1] * tx
                b = knots[iy + 1][ix] * (1 - tx) + knots[iy + 1][ix + 1] * tx
                result[y][x] += (a * (1 - ty) + b * ty) * amplitude
        total_amp += amplitude
        amplitude *= persistence
        step //= 2
    if total_amp <= 0:
        return result
    return [[value / total_amp for value in row] for row in result]


def _blur_field(field: list[list[float]], radius: int) -> list[list[float]]:
    """Box mean over Chebyshev neighbourhood — softens terrain-bias seams."""
    if radius <= 0 or not field:
        return field
    rows, cols = len(field), len(field[0])
    out = [[0.0] * cols for _ in range(rows)]
    for y in range(rows):
        y0, y1 = max(0, y - radius), min(rows - 1, y + radius)
        for x in range(cols):
            x0, x1 = max(0, x - radius), min(cols - 1, x + radius)
            total = 0.0
            count = 0
            for ny in range(y0, y1 + 1):
                row = field[ny]
                for nx in range(x0, x1 + 1):
                    total += row[nx]
                    count += 1
            out[y][x] = total / max(1, count)
    return out


# Public aliases — preferred entry points for experimental landscape fields.
value_noise_field = _value_noise_field
blur_field = _blur_field


def generate_soil_texture_field(
    width: int,
    height: int,
    seed: int,
    *,
    base: float = TEXTURE_BASE,
    regional_amp: float = TEXTURE_REGIONAL_AMP,
    mid_amp: float = TEXTURE_MID_AMP,
    fine_amp: float = TEXTURE_FINE_AMP,
    regional_spacing: int | None = None,
    mid_spacing: int | None = None,
    fine_spacing: int = 2,
    blur_radius: int = 0,
    seed_mixin: int = 0x50117E87,
) -> list[list[float]]:
    """Seeded continuous soil-texture field without terrain bias.

    Used by production generation (plus a weak terrain nudge) and by the
    isolated Landscape Fields prototype (broader spacing / weaker fine noise).
    """
    cols, rows = max(1, int(width)), max(1, int(height))
    rng = random.Random(int(seed) ^ int(seed_mixin))
    short = max(8, min(cols, rows))
    reg_sp = max(4, int(regional_spacing if regional_spacing is not None else max(14, short // 4)))
    mid_sp = max(2, int(mid_spacing if mid_spacing is not None else max(5, short // 10)))
    fine_sp = max(1, int(fine_spacing))
    regional = _value_noise_field(cols, rows, rng, spacing=reg_sp, persistence=0.55)
    mid = _value_noise_field(cols, rows, rng, spacing=mid_sp, persistence=0.50)
    fine = _value_noise_field(cols, rows, rng, spacing=fine_sp, persistence=0.40)
    out = [
        [
            clamp01(
                float(base)
                + (regional[y][x] - 0.5) * (2.0 * float(regional_amp))
                + (mid[y][x] - 0.5) * (2.0 * float(mid_amp))
                + (fine[y][x] - 0.5) * (2.0 * float(fine_amp))
            )
            for x in range(cols)
        ]
        for y in range(rows)
    ]
    if blur_radius > 0:
        out = _blur_field(out, int(blur_radius))
        out = [[clamp01(v) for v in row] for row in out]
    return out


def generate_soil_texture(world: "World", *, seed: int | None = None) -> None:
    """Fill every cell with a persistent clustered soil_texture in [0, 1].

    Deterministic for a given world seed. Safe to call once after terrain is
    painted; later terrain conversion must not call this again.
    """
    cols, rows = world.cols, world.rows
    if cols <= 0 or rows <= 0:
        return
    field_seed = int(world.seed if seed is None else seed)
    field = generate_soil_texture_field(cols, rows, field_seed)

    bias = [
        [_terrain_bias(cell.terrain) for cell in row] for row in world.cells
    ]
    bias = _blur_field(bias, TEXTURE_BIAS_BLUR)

    for y in range(rows):
        for x in range(cols):
            nudge = max(-TEXTURE_BIAS_CAP, min(TEXTURE_BIAS_CAP, bias[y][x]))
            world.cells[y][x].soil_texture = clamp01(field[y][x] + nudge)


def ensure_soil_texture(world: "World") -> None:
    """Generate texture for unset (−1) cells without wiping already-persisted values."""
    has_unset = False
    existing = [
        [float(getattr(cell, "soil_texture", -1.0)) for cell in row]
        for row in world.cells
    ]
    for row in existing:
        for value in row:
            if value < 0.0:
                has_unset = True
                break
        if has_unset:
            break
    if not has_unset:
        return
    generate_soil_texture(world)
    for y, row in enumerate(existing):
        for x, value in enumerate(row):
            if value >= 0.0:
                world.cells[y][x].soil_texture = clamp01(value)
