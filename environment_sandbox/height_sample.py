"""Visual-only height sample: corner heightmap + fast column-warped cache.

Logic/pathfinding stay flat; only drawing uses these helpers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

from settings import (
    HEIGHT_SAMPLE_H,
    HEIGHT_SAMPLE_LIGHT_NW,
    HEIGHT_SAMPLE_PX,
    HEIGHT_SAMPLE_SHADE_LIT,
    HEIGHT_SAMPLE_SHADE_MIX,
    HEIGHT_SAMPLE_SHADE_SHADOW,
    HEIGHT_SAMPLE_W,
)


@dataclass
class HeightSample:
    """Fixed rect with heights at cell *corners* for continuous warping.

    ``corners[ly][lx]`` covers local corner (lx, ly) with
    ``lx`` in ``0..width``, ``ly`` in ``0..height``.
    """

    x0: int
    y0: int
    width: int
    height: int
    corners: list[list[float]]

    @property
    def x1(self) -> int:
        return self.x0 + self.width - 1

    @property
    def y1(self) -> int:
        return self.y0 + self.height - 1

    def contains(self, x: int, y: int) -> bool:
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1

    def corner_at_local(self, lx: int, ly: int) -> float:
        lx = max(0, min(self.width, lx))
        ly = max(0, min(self.height, ly))
        return self.corners[ly][lx]

    def height_at(self, x: int, y: int) -> float:
        if not self.contains(x, y):
            return 0.0
        return self.height_world(float(x) + 0.5, float(y) + 0.5)

    def height_world(self, wx: float, wy: float) -> float:
        """Bilinear height at continuous world cell coordinates."""
        lx = wx - self.x0
        ly = wy - self.y0
        if lx < 0.0 or ly < 0.0 or lx > self.width or ly > self.height:
            return 0.0
        x0 = int(math.floor(lx))
        y0 = int(math.floor(ly))
        x1 = min(self.width, x0 + 1)
        y1 = min(self.height, y0 + 1)
        x0 = max(0, min(self.width, x0))
        y0 = max(0, min(self.height, y0))
        fx = 0.0 if lx >= self.width else (lx - math.floor(lx))
        fy = 0.0 if ly >= self.height else (ly - math.floor(ly))
        v00 = self.corners[y0][x0]
        v10 = self.corners[y0][x1]
        v01 = self.corners[y1][x0]
        v11 = self.corners[y1][x1]
        return _lerp(_lerp(v00, v10, fx), _lerp(v01, v11, fx), fy)

    def cell_corners(self, x: int, y: int) -> tuple[float, float, float, float]:
        """NW, NE, SW, SE corner heights for cell (x, y)."""
        lx = x - self.x0
        ly = y - self.y0
        return (
            self.corner_at_local(lx, ly),
            self.corner_at_local(lx + 1, ly),
            self.corner_at_local(lx, ly + 1),
            self.corner_at_local(lx + 1, ly + 1),
        )


def _smooth_noise(ix: int, iy: int, seed: int) -> float:
    n = (ix * 374761393 + iy * 668265263 + seed * 1274126177) & 0x7FFFFFFF
    n = (n ^ (n >> 13)) * 1274126177
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _value_noise_2d(x: float, y: float, seed: int) -> float:
    x0 = int(math.floor(x))
    y0 = int(math.floor(y))
    fx = _smoothstep(x - x0)
    fy = _smoothstep(y - y0)
    v00 = _smooth_noise(x0, y0, seed)
    v10 = _smooth_noise(x0 + 1, y0, seed)
    v01 = _smooth_noise(x0, y0 + 1, seed)
    v11 = _smooth_noise(x0 + 1, y0 + 1, seed)
    return _lerp(_lerp(v00, v10, fx), _lerp(v01, v11, fx), fy)


def _height_field(lx: float, ly: float, width: float, height: float, seed: int) -> float:
    """Diagonal valley / ridge undulations with soft edge falloff."""
    # Primary diagonal valleys (NW–SE troughs).
    v1 = math.sin((lx + ly) * (math.pi / 4.2) + 0.35)
    # Crossing diagonal undulation (NE–SW).
    v2 = math.sin((lx - ly) * (math.pi / 5.0) + 1.1)
    # Longer-wavelength roll so the patch isn't only short ripples.
    v3 = math.sin((lx + 0.6 * ly) * (math.pi / 7.5) + 0.2)
    v4 = math.cos((0.7 * lx - ly) * (math.pi / 6.0) + 0.9)
    # Map sines from [-1,1] into gentle hills / valleys.
    undulation = (
        0.50
        + 0.22 * v1
        + 0.18 * v2
        + 0.12 * v3
        + 0.10 * v4
    )
    # Fine noise for irregularity along the valleys.
    n = _value_noise_2d(lx * 0.45 + 2.1, ly * 0.45 + 1.3, seed) * 0.18
    n2 = _value_noise_2d(lx * 0.18, ly * 0.18, seed + 9) * 0.12
    h = undulation + n + n2 - 0.08
    # Soft edge so the patch meets flat land.
    edge = min(lx, ly, width - lx, height - ly)
    h *= _smoothstep(edge / 2.2)
    return max(0.0, min(1.0, h))


def generate_height_sample(
    world_cols: int,
    world_rows: int,
    *,
    seed: int = 42,
    width: int = HEIGHT_SAMPLE_W,
    height: int = HEIGHT_SAMPLE_H,
) -> HeightSample:
    """Build a centred sample with shared corner heights (smooth warp field)."""
    width = max(4, min(width, world_cols))
    height = max(4, min(height, world_rows))
    x0 = max(0, (world_cols - width) // 2)
    y0 = max(0, (world_rows - height) // 2)
    corners: list[list[float]] = []
    for ly in range(height + 1):
        row: list[float] = []
        for lx in range(width + 1):
            row.append(_height_field(float(lx), float(ly), float(width), float(height), seed))
        corners.append(row)
    return HeightSample(x0=x0, y0=y0, width=width, height=height, corners=corners)


def corner_shade_factor(
    sample: HeightSample,
    lx: int,
    ly: int,
    *,
    strength: float = HEIGHT_SAMPLE_LIGHT_NW,
) -> float:
    """NW-light shade at a heightfield corner (local corner indices)."""
    h = sample.corner_at_local(lx, ly)
    he = sample.corner_at_local(lx + 1, ly) if lx < sample.width else h
    hw = sample.corner_at_local(lx - 1, ly) if lx > 0 else h
    hs = sample.corner_at_local(lx, ly + 1) if ly < sample.height else h
    hn = sample.corner_at_local(lx, ly - 1) if ly > 0 else h
    if lx == 0:
        gx = he - h
    elif lx == sample.width:
        gx = h - hw
    else:
        gx = (he - hw) * 0.5
    if ly == 0:
        gy = hs - h
    elif ly == sample.height:
        gy = h - hn
    else:
        gy = (hs - hn) * 0.5
    lit = (-gx - gy) * 0.5
    # Narrow band — tint handles colour; avoid crushed blacks / blown whites.
    return max(0.72, min(1.22, 1.0 + lit * strength * 4.0))


def cell_corner_shades(
    sample: HeightSample, x: int, y: int
) -> tuple[float, float, float, float]:
    """NW, NE, SW, SE shade factors for cell (x, y)."""
    lx = x - sample.x0
    ly = y - sample.y0
    return (
        corner_shade_factor(sample, lx, ly),
        corner_shade_factor(sample, lx + 1, ly),
        corner_shade_factor(sample, lx, ly + 1),
        corner_shade_factor(sample, lx + 1, ly + 1),
    )


def slope_shade_factor(
    sample: HeightSample,
    x: int,
    y: int,
    *,
    strength: float = HEIGHT_SAMPLE_LIGHT_NW,
) -> float:
    """Cell-centre shade (average of corners); kept for callers/debug."""
    del strength
    if not sample.contains(x, y):
        return 1.0
    nw, ne, sw, se = cell_corner_shades(sample, x, y)
    return (nw + ne + sw + se) * 0.25


def screen_lift_px(height: float, view_cell: float, cell_size: float) -> float:
    scale = view_cell / max(1.0, cell_size)
    return height * HEIGHT_SAMPLE_PX * scale


def bake_pad_px() -> int:
    """Top padding in the bake surface so max lift stays in-bounds."""
    return int(math.ceil(HEIGHT_SAMPLE_PX)) + 2


def _shade_rgb(colour: pygame.Color | tuple, factor: float) -> tuple[int, int, int]:
    """Soft relief tint: lit → light yellow, shaded → dark brown (no hard B/W)."""
    r, g, b = int(colour[0]), int(colour[1]), int(colour[2])
    mix = max(0.0, min(1.0, HEIGHT_SAMPLE_SHADE_MIX))
    if factor >= 1.0:
        t = min(1.0, (factor - 1.0) / 0.22) * mix
        tr, tg, tb = HEIGHT_SAMPLE_SHADE_LIT
    else:
        t = min(1.0, (1.0 - factor) / 0.28) * mix
        tr, tg, tb = HEIGHT_SAMPLE_SHADE_SHADOW
    return (
        max(0, min(255, int(r + (tr - r) * t))),
        max(0, min(255, int(g + (tg - g) * t))),
        max(0, min(255, int(b + (tb - b) * t))),
    )


def blit_warped_cell_columns(
    dest: pygame.Surface,
    src: pygame.Surface,
    flat_rect: pygame.Rect,
    lifts: tuple[float, float, float, float],
    shades: tuple[float, float, float, float],
) -> None:
    """Y-only warp with per-pixel bilinear shade from the four corners."""
    nw_h, ne_h, sw_h, se_h = lifts
    nw_s, ne_s, sw_s, se_s = shades
    w = flat_rect.w
    if w <= 0 or flat_rect.h <= 0:
        return

    tile = src
    sw, sh = tile.get_size()
    if sw != w or sh != flat_rect.h:
        tile = pygame.transform.scale(tile, (w, flat_rect.h))
        if tile.get_bitsize() != 24:
            fixed = pygame.Surface(tile.get_size(), depth=24)
            fixed.blit(tile, (0, 0))
            tile = fixed
        sw, sh = tile.get_size()

    inv_u = 1.0 / max(1, w - 1)
    for i in range(w):
        u = i * inv_u if w > 1 else 0.0
        top_lift = nw_h * (1.0 - u) + ne_h * u
        bot_lift = sw_h * (1.0 - u) + se_h * u
        top_shade = nw_s * (1.0 - u) + ne_s * u
        bot_shade = sw_s * (1.0 - u) + se_s * u
        top_y = flat_rect.top - top_lift
        bot_y = flat_rect.bottom - bot_lift
        y0 = int(math.floor(top_y))
        y1 = int(math.ceil(bot_y)) + 1
        dest_h = max(1, y1 - y0)
        inv_v = 1.0 / max(1, dest_h - 1)

        # Map each dest column pixel from source v, with bilinear shade.
        out = pygame.Surface((1, dest_h), depth=24)
        for j in range(dest_h):
            v = j * inv_v if dest_h > 1 else 0.0
            # Sample source along the unwarped column (same v).
            sy = min(sh - 1, max(0, int(round(v * (sh - 1)))))
            shade = top_shade * (1.0 - v) + bot_shade * v
            out.set_at((0, j), _shade_rgb(tile.get_at((i, sy)), shade))
        dest.blit(out, (flat_rect.left + i, y0))


def bake_height_sample_surface(
    sample: HeightSample,
    terrain_patch: pygame.Surface,
    *,
    cell_size: int,
) -> tuple[pygame.Surface, int]:
    """Bake warped sample once at native cell size. Returns (surface, top_pad_px).

    ``terrain_patch`` must cover the sample footprint only:
    ``(sample.width * cell_size) × (sample.height * cell_size)``, already
    composited with mute / season flecks / ice as needed.
    """
    pad = bake_pad_px()
    w = sample.width * cell_size
    h = sample.height * cell_size + pad
    # depth=24: no per-pixel alpha. (Display is often SRCALPHA; alpha-0 RGB
    # blits are invisible and look like a dark wiped box.)
    surf = pygame.Surface((w, h), depth=24)
    surf.fill((40, 55, 35))
    patch = terrain_patch
    if patch.get_bitsize() != 24:
        opaque = pygame.Surface(patch.get_size(), depth=24)
        opaque.blit(patch, (0, 0))
        patch = opaque
    # Flat ground under the pad, then warp cells on top.
    if patch.get_width() >= w and patch.get_height() >= sample.height * cell_size:
        surf.blit(patch, (0, pad))
        top_row = pygame.Surface((w, 1), depth=24)
        top_row.blit(patch, (0, 0), pygame.Rect(0, 0, w, 1))
        for yy in range(pad):
            surf.blit(top_row, (0, yy))

    for ly in range(sample.height):
        for lx in range(sample.width):
            x = sample.x0 + lx
            y = sample.y0 + ly
            flat = pygame.Rect(lx * cell_size, pad + ly * cell_size, cell_size, cell_size)
            nw, ne, sw, se = sample.cell_corners(x, y)
            lifts = (
                nw * HEIGHT_SAMPLE_PX,
                ne * HEIGHT_SAMPLE_PX,
                sw * HEIGHT_SAMPLE_PX,
                se * HEIGHT_SAMPLE_PX,
            )
            shades = cell_corner_shades(sample, x, y)
            src = pygame.Rect(lx * cell_size, ly * cell_size, cell_size, cell_size)
            try:
                tile_src = patch.subsurface(src)
            except ValueError:
                continue
            tile = pygame.Surface(tile_src.get_size(), depth=24)
            tile.blit(tile_src, (0, 0))
            blit_warped_cell_columns(surf, tile, flat, lifts, shades)
    return surf, pad
