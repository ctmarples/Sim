"""Visual-only heightfield: corner heights + column-warped terrain bake.

Logic/pathfinding stay flat; only drawing uses these helpers.
Heights are absolute units (lake = 0, river head = 40, valley walls rise outward).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

from settings import (
    HEIGHT_LIFT_PX,
    HEIGHT_SAMPLE_LIGHT_NW,
    HEIGHT_SAMPLE_SHADE_LIT,
    HEIGHT_SAMPLE_SHADE_LIT_MIX,
    HEIGHT_SAMPLE_SHADE_MIX,
    HEIGHT_SAMPLE_SHADE_SHADOW,
)

try:
    import numpy as np
    from pygame import surfarray as _surfarray

    _HAS_NUMPY = True
except ImportError:  # pragma: no cover - optional accel
    np = None  # type: ignore[assignment]
    _surfarray = None  # type: ignore[assignment]
    _HAS_NUMPY = False


@dataclass
class HeightSample:
    """World (or region) heights at cell *corners* for continuous warping.

    ``corners[ly][lx]`` covers corner (lx, ly) with
    ``lx`` in ``0..width``, ``ly`` in ``0..height``.
    World cell (x, y) uses corners at local (x-x0, y-y0) … (+1,+1).
    """

    x0: int
    y0: int
    width: int
    height: int
    corners: list[list[float]]
    max_height: float = 0.0

    def __post_init__(self) -> None:
        if self.max_height <= 0.0 and self.corners:
            peak = 0.0
            for row in self.corners:
                for v in row:
                    if v > peak:
                        peak = v
            self.max_height = peak

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

    def subregion(self, x0: int, y0: int, x1: int, y1: int) -> HeightSample:
        """Corner-sharing sub-sample covering cells x0..x1, y0..y1 inclusive."""
        x0 = max(self.x0, x0)
        y0 = max(self.y0, y0)
        x1 = min(self.x1, x1)
        y1 = min(self.y1, y1)
        w = max(0, x1 - x0 + 1)
        h = max(0, y1 - y0 + 1)
        lx0 = x0 - self.x0
        ly0 = y0 - self.y0
        corners = [
            self.corners[ly0 + ly][lx0 : lx0 + w + 1]
            for ly in range(h + 1)
        ]
        return HeightSample(
            x0=x0,
            y0=y0,
            width=w,
            height=h,
            corners=corners,
            max_height=self.max_height,
        )


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def height_sample_from_corners(
    cols: int,
    rows: int,
    corners: list[list[float]],
) -> HeightSample:
    """Wrap a full-world corner heightfield (size (rows+1) × (cols+1))."""
    return HeightSample(
        x0=0,
        y0=0,
        width=cols,
        height=rows,
        corners=corners,
    )


def generate_height_sample(
    world_cols: int,
    world_rows: int,
    *,
    seed: int = 0,
    corners: list[list[float]] | None = None,
) -> HeightSample:
    """Build a full-map height sample from world corners (or zeros)."""
    del seed
    if corners is None:
        corners = [[0.0] * (world_cols + 1) for _ in range(world_rows + 1)]
    return height_sample_from_corners(world_cols, world_rows, corners)


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
    # Normalise by typical valley gradient so shade stays readable.
    lit = (-gx - gy) * 0.5 / max(8.0, sample.max_height * 0.15)
    return max(0.70, min(1.10, 1.0 + lit * strength * 4.0))


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
    return height * HEIGHT_LIFT_PX * scale


def bake_pad_px(max_height: float | None = None) -> int:
    """Top padding so max lift stays in-bounds."""
    peak = float(max_height) if max_height is not None else 80.0
    return int(math.ceil(peak * HEIGHT_LIFT_PX)) + 2


def _shade_rgb(colour: pygame.Color | tuple, factor: float) -> tuple[int, int, int]:
    """Soft relief tint: lit → light yellow, shaded → dark brown."""
    r, g, b = int(colour[0]), int(colour[1]), int(colour[2])
    if factor >= 1.0:
        mix = max(0.0, min(1.0, HEIGHT_SAMPLE_SHADE_LIT_MIX))
        t = min(1.0, (factor - 1.0) / 0.10) * mix
        tr, tg, tb = HEIGHT_SAMPLE_SHADE_LIT
    else:
        mix = max(0.0, min(1.0, HEIGHT_SAMPLE_SHADE_MIX))
        t = min(1.0, (1.0 - factor) / 0.28) * mix
        tr, tg, tb = HEIGHT_SAMPLE_SHADE_SHADOW
    return (
        max(0, min(255, int(r + (tr - r) * t))),
        max(0, min(255, int(g + (tg - g) * t))),
        max(0, min(255, int(b + (tb - b) * t))),
    )


def _shade_tile_bilinear(
    tile: pygame.Surface,
    shades: tuple[float, float, float, float],
) -> pygame.Surface:
    """Return a shaded copy of ``tile`` (bilinear corner factors)."""
    nw, ne, sw, se = shades
    w, h = tile.get_size()
    if w <= 0 or h <= 0:
        return tile

    if _HAS_NUMPY and _surfarray is not None and np is not None:
        src = _surfarray.array3d(tile).astype(np.float32)
        xs = np.linspace(0.0, 1.0, w, dtype=np.float32)
        ys = np.linspace(0.0, 1.0, h, dtype=np.float32)
        fx = xs[:, None]
        fy = ys[None, :]
        top = nw * (1.0 - fx) + ne * fx
        bot = sw * (1.0 - fx) + se * fx
        factor = top * (1.0 - fy) + bot * fy

        lit = HEIGHT_SAMPLE_SHADE_LIT
        shadow = HEIGHT_SAMPLE_SHADE_SHADOW
        lit_mix = float(HEIGHT_SAMPLE_SHADE_LIT_MIX)
        sh_mix = float(HEIGHT_SAMPLE_SHADE_MIX)

        out = src.copy()
        hi = factor >= 1.0
        if np.any(hi):
            t = np.clip((factor - 1.0) / 0.10, 0.0, 1.0) * lit_mix
            for c in range(3):
                ch = out[:, :, c]
                ch[hi] = ch[hi] + (lit[c] - ch[hi]) * t[hi]
                out[:, :, c] = ch
        lo = ~hi
        if np.any(lo):
            t = np.clip((1.0 - factor) / 0.28, 0.0, 1.0) * sh_mix
            for c in range(3):
                ch = out[:, :, c]
                ch[lo] = ch[lo] + (shadow[c] - ch[lo]) * t[lo]
                out[:, :, c] = ch
        shaded = pygame.Surface((w, h), depth=24)
        _surfarray.blit_array(shaded, np.clip(out, 0, 255).astype(np.uint8))
        return shaded

    if tile.get_bitsize() != 24:
        fixed = pygame.Surface((w, h), depth=24)
        fixed.blit(tile, (0, 0))
        tile = fixed
    buf = bytearray(tile.get_buffer())
    pitch = tile.get_pitch()
    inv_x = 1.0 / max(1, w - 1)
    inv_y = 1.0 / max(1, h - 1)
    for y in range(h):
        fy = y * inv_y
        row = y * pitch
        for x in range(w):
            fx = x * inv_x
            factor = (nw * (1.0 - fx) + ne * fx) * (1.0 - fy) + (
                sw * (1.0 - fx) + se * fx
            ) * fy
            i = row + x * 3
            b, g, r = buf[i], buf[i + 1], buf[i + 2]
            sr, sg, sb = _shade_rgb((r, g, b), factor)
            buf[i], buf[i + 1], buf[i + 2] = sb, sg, sr
    return pygame.image.frombuffer(bytes(buf), (w, h), "BGR").convert()


def blit_warped_cell_columns(
    dest: pygame.Surface,
    src: pygame.Surface,
    flat_rect: pygame.Rect,
    lifts: tuple[float, float, float, float],
    shades: tuple[float, float, float, float],
) -> None:
    """Y-only warp; shade is applied on the flat tile first."""
    nw_h, ne_h, sw_h, se_h = lifts
    w = flat_rect.w
    if w <= 0 or flat_rect.h <= 0:
        return

    tile = _shade_tile_bilinear(src, shades)
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
        top_y = flat_rect.top - top_lift
        bot_y = flat_rect.bottom - bot_lift
        y0 = int(math.floor(top_y))
        y1 = int(math.ceil(bot_y))
        dest_h = max(1, y1 - y0)
        col = tile.subsurface((i, 0, 1, sh))
        if dest_h != sh:
            col = pygame.transform.scale(col, (1, dest_h))
        dest.blit(col, (flat_rect.left + i, y0))


def bake_height_sample_surface(
    sample: HeightSample,
    terrain_patch: pygame.Surface,
    *,
    cell_size: int,
) -> tuple[pygame.Surface, int]:
    """Bake warped sample at native cell size. Returns (surface, top_pad_px).

    ``terrain_patch`` covers the sample footprint only:
    ``(sample.width * cell_size) × (sample.height * cell_size)``.
    """
    pad = bake_pad_px(sample.max_height)
    w = sample.width * cell_size
    h = sample.height * cell_size + pad
    surf = pygame.Surface((w, h), depth=24)
    surf.fill((40, 55, 35))
    patch = terrain_patch
    if patch.get_bitsize() != 24:
        opaque = pygame.Surface(patch.get_size(), depth=24)
        opaque.blit(patch, (0, 0))
        patch = opaque
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
                nw * HEIGHT_LIFT_PX,
                ne * HEIGHT_LIFT_PX,
                sw * HEIGHT_LIFT_PX,
                se * HEIGHT_LIFT_PX,
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


def patch_height_sample_cells(
    dest: pygame.Surface,
    dest_pad: int,
    sample: HeightSample,
    terrain_base: pygame.Surface,
    cells: list[tuple[int, int]],
    *,
    cell_size: int,
    margin: int = 1,
) -> None:
    """Re-warp dirty cells in-place on an existing full-map height cache.

    Must not blit a sub-bake (that stamps the subregion's top pad into mid-map).
    Restore flat terrain for an AABB large enough for lift bleed, then warp
    north→south into ``dest``.
    """
    if not cells or sample.width <= 0:
        return
    lift_m = max(
        margin,
        int(math.ceil(float(sample.max_height) * HEIGHT_LIFT_PX / max(1, cell_size)))
        + 1,
    )
    xs = [x for x, _y in cells]
    ys = [y for _x, y in cells]
    x0 = max(sample.x0, min(xs) - margin)
    y0 = max(sample.y0, min(ys) - lift_m)
    x1 = min(sample.x1, max(xs) + margin)
    y1 = min(sample.y1, max(ys) + margin)
    if x1 < x0 or y1 < y0:
        return

    base = terrain_base
    if base.get_bitsize() != 24:
        opaque = pygame.Surface(base.get_size(), depth=24)
        opaque.blit(base, (0, 0))
        base = opaque

    # 1) Restore flat terrain under the AABB (clears old warp in this band).
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            src = pygame.Rect(x * cell_size, y * cell_size, cell_size, cell_size)
            try:
                tile = base.subsurface(src)
            except ValueError:
                continue
            dest.blit(tile, (x * cell_size, dest_pad + y * cell_size))

    # Top pad: only the global strip (y == 0 lifts). Refresh from top terrain row.
    if y0 == sample.y0:
        top = pygame.Surface(( (x1 - x0 + 1) * cell_size, 1), depth=24)
        try:
            top.blit(
                base.subsurface(
                    pygame.Rect(x0 * cell_size, 0, (x1 - x0 + 1) * cell_size, 1)
                ),
                (0, 0),
            )
        except ValueError:
            top.fill((40, 55, 35))
        for yy in range(dest_pad):
            dest.blit(top, (x0 * cell_size, yy))

    # 2) Warp cells north→south so southern lifts paint over northern flats.
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            src = pygame.Rect(x * cell_size, y * cell_size, cell_size, cell_size)
            try:
                tile_src = base.subsurface(src)
            except ValueError:
                continue
            tile = pygame.Surface(tile_src.get_size(), depth=24)
            tile.blit(tile_src, (0, 0))
            flat = pygame.Rect(
                x * cell_size,
                dest_pad + y * cell_size,
                cell_size,
                cell_size,
            )
            nw, ne, sw, se = sample.cell_corners(x, y)
            lifts = (
                nw * HEIGHT_LIFT_PX,
                ne * HEIGHT_LIFT_PX,
                sw * HEIGHT_LIFT_PX,
                se * HEIGHT_LIFT_PX,
            )
            shades = cell_corner_shades(sample, x, y)
            blit_warped_cell_columns(dest, tile, flat, lifts, shades)
