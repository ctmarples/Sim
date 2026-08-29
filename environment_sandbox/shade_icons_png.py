#!/usr/bin/env python3
"""Apply tree_cone_1-style directional stipple shading to icon PNGs.

Usage (from environment_sandbox)::

    python shade_icons_png.py

Skips ``tree_cone_1.png`` (hand-edited reference). Re-run after re-exporting
PNGs from SVG if you want to re-bake flat colours then shade again.
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import numpy as np
import pygame

ROOT = Path(__file__).resolve().parent
ICONS = ROOT / "assets" / "icons"
SKIP = {"tree_cone_1.png"}


def _hash01(x: int, y: int, salt: int = 0) -> float:
    n = (x * 374761393 + y * 668265263 + salt * 982451653) & 0xFFFFFFFF
    n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
    return (n & 0xFFFFFF) / float(0xFFFFFF)


def shade_surface(surf: pygame.Surface) -> pygame.Surface:
    w, h = surf.get_size()
    out = surf.copy()
    opaque = [
        (x, y)
        for y in range(h)
        for x in range(w)
        if surf.get_at((x, y))[3] > 24
    ]
    if len(opaque) < 8:
        return out

    xs = [p[0] for p in opaque]
    ys = [p[1] for p in opaque]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    bw = max(1, x1 - x0)
    bh = max(1, y1 - y0)

    alpha = np.zeros((h, w), dtype=np.float32)
    px = pygame.surfarray.pixels_alpha(surf)
    alpha[:, :] = px.T.astype(np.float32) / 255.0
    del px

    for x, y in opaque:
        r, g, b, a = surf.get_at((x, y))
        u = (x - x0) / bw
        v = (y - y0) / bh

        xm, xp = max(0, x - 1), min(w - 1, x + 1)
        ym, yp = max(0, y - 1), min(h - 1, y + 1)
        gx = float(alpha[y, xp] - alpha[y, xm])
        gy = float(alpha[yp, x] - alpha[ym, x])
        gn = math.hypot(gx, gy)
        if gn > 1e-4:
            nx, ny = gx / gn, gy / gn
        else:
            cx = x0 + bw * 0.45
            cy = y0 + bh * 0.45
            dx, dy = x - cx, y - cy
            dn = math.hypot(dx, dy) + 1e-6
            nx, ny = dx / dn, dy / dn

        Lx, Ly = -0.62, -0.72
        ndotl = max(0.0, nx * Lx + ny * Ly)
        wrap = 0.55 - 0.38 * u - 0.22 * v
        light = max(0.0, min(1.0, 0.35 * wrap + 0.75 * ndotl + 0.12))

        n1 = _hash01(x, y, 11)
        n2 = _hash01(x, y, 29)
        stipple = 1.0 if n1 > 0.55 else (0.35 if n1 > 0.28 else 0.0)

        if light >= 0.52:
            t = (light - 0.52) / 0.48
            t = t * (0.35 + 0.65 * stipple)
            lift = 0.22 + 0.18 * t
            rr = min(255, int(r + (255 - r) * lift * t + 18 * t * stipple))
            gg = min(255, int(g + (255 - g) * lift * t + 14 * t * stipple))
            bb = min(255, int(b + (255 - b) * (lift * 0.7) * t + 6 * t * stipple))
            if stipple > 0.9 and n2 > 0.82:
                rr = min(255, rr + 28)
                gg = min(255, gg + 24)
                bb = min(255, bb + 10)
        else:
            t = (0.52 - light) / 0.52
            dark = 0.28 + 0.42 * t
            if n2 < 0.18:
                dark += 0.08
            rr = max(0, int(r * (1.0 - dark)))
            gg = max(0, int(g * (1.0 - dark * 0.95)))
            bb = max(0, int(b * (1.0 - dark * 0.85)))
            if t > 0.55 and n1 < 0.4:
                rr = max(0, rr - 6)
                bb = min(255, bb + 4)

        out.set_at((x, y), (rr, gg, bb, a))

    soft = out.copy()
    for x, y in opaque:
        if _hash01(x, y, 7) < 0.55:
            continue
        neigh = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                xx, yy = x + dx, y + dy
                if 0 <= xx < w and 0 <= yy < h:
                    c = out.get_at((xx, yy))
                    if c[3] > 24:
                        neigh.append(c)
        if len(neigh) < 3:
            continue
        r0, g0, b0, a0 = out.get_at((x, y))
        ar = int(0.7 * r0 + 0.3 * (sum(c[0] for c in neigh) / len(neigh)))
        ag = int(0.7 * g0 + 0.3 * (sum(c[1] for c in neigh) / len(neigh)))
        ab = int(0.7 * b0 + 0.3 * (sum(c[2] for c in neigh) / len(neigh)))
        soft.set_at((x, y), (ar, ag, ab, a0))
    return soft


def main() -> int:
    pygame.init()
    pygame.display.set_mode((1, 1))
    done = 0
    for path in sorted(ICONS.rglob("*.png")):
        if any(part.startswith("_") for part in path.relative_to(ICONS).parts[:-1]):
            continue
        if path.name in SKIP or path.name.startswith("_"):
            print(f"skip {path.name}")
            continue
        surf = pygame.image.load(str(path)).convert_alpha()
        shaded = shade_surface(surf)
        pygame.image.save(shaded, str(path))
        print(f"ok   {path.name}")
        done += 1
    print(f"\nShaded {done} icons")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
