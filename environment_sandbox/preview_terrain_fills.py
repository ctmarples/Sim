#!/usr/bin/env python3
"""Live preview of procedural terrain mottling with parameter knobs.

Usage (from environment_sandbox):

    python preview_terrain_fills.py

What you see
------------
  One continuous world-UV mottling field (no repeating period tile).
  Drawn as GRID×GRID game cells so you can see cell size vs mottling scale.

Controls
--------
  Left / Right   — cycle biome
  G              — toggle cell-grid overlay
  R              — reseed
  D              — reset knobs to defaults
  Esc / Q        — quit

  Click filter toggles / drag sliders — field updates live.
"""

from __future__ import annotations

import random
import sys
from dataclasses import replace

import pygame

from settings import CELL_SIZE
from terrain_fills import PREVIEW_TERRAINS
from terrain_mottle import (
    MottleParams,
    get_params,
    set_params,
    world_mottle_region,
)
from world import TerrainType

WINDOW_W = 1120
WINDOW_H = 780
# How many game cells across/down in the preview field.
GRID = 8
PAD = 16
PANEL_X = 560
SLIDER_W = 240
SLIDER_H = 14
ROW_H = 34

_SLIDER_SPECS: list[tuple[str, str, float, float, bool]] = [
    ("coarse_scale", "coarse scale", 0.005, 0.12, False),
    ("mid_scale", "mid scale", 0.02, 0.4, False),
    ("fine_scale", "fine scale", 0.08, 1.2, False),
    ("coarse_amp", "coarse amp", 0.0, 0.6, False),
    ("mid_amp", "mid amp", 0.0, 0.4, False),
    ("fine_amp", "fine amp", 0.0, 0.3, False),
    ("speckle", "speckle", 0.0, 0.5, False),
    ("palette_mix", "palette mix", 0.0, 1.0, False),
    ("seed", "seed", 0, 9999, True),
]


def _fmt(value: float, is_int: bool, lo: float, hi: float) -> str:
    if is_int:
        return str(int(round(value)))
    if hi - lo < 0.5:
        return f"{value:.3f}"
    return f"{value:.2f}"


class Slider:
    def __init__(
        self, name: str, label: str, lo: float, hi: float, is_int: bool, x: int, y: int
    ) -> None:
        self.name = name
        self.label = label
        self.lo = lo
        self.hi = hi
        self.is_int = is_int
        self.rect = pygame.Rect(x, y, SLIDER_W, SLIDER_H)

    def set_from_mouse(self, mx: int, params: MottleParams) -> MottleParams:
        t = (mx - self.rect.x) / max(1, self.rect.w)
        t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
        raw = self.lo + (self.hi - self.lo) * t
        if self.is_int:
            raw = int(round(raw))
        return replace(params, **{self.name: raw})

    def draw(self, screen: pygame.Surface, font: pygame.font.Font, params: MottleParams) -> None:
        val = float(getattr(params, self.name))
        t = 0.0 if self.hi == self.lo else (val - self.lo) / (self.hi - self.lo)
        t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
        pygame.draw.rect(screen, (50, 54, 60), self.rect, border_radius=3)
        fill = self.rect.copy()
        fill.w = max(2, int(self.rect.w * t))
        pygame.draw.rect(screen, (90, 140, 100), fill, border_radius=3)
        pygame.draw.rect(screen, (120, 130, 140), self.rect, 1, border_radius=3)
        knob_x = self.rect.x + int(self.rect.w * t)
        pygame.draw.circle(screen, (220, 230, 210), (knob_x, self.rect.centery), 7)
        screen.blit(
            font.render(
                f"{self.label}: {_fmt(val, self.is_int, self.lo, self.hi)}",
                True,
                (200, 205, 195),
            ),
            (self.rect.x, self.rect.y - 16),
        )


class Toggle:
    def __init__(self, name: str, label: str, x: int, y: int) -> None:
        self.name = name
        self.label = label
        self.rect = pygame.Rect(x, y, SLIDER_W, 26)

    def hit(self, pos: tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)

    def flip(self, params: MottleParams) -> MottleParams:
        return replace(params, **{self.name: not bool(getattr(params, self.name))})

    def draw(self, screen: pygame.Surface, font: pygame.font.Font, params: MottleParams) -> None:
        on = bool(getattr(params, self.name))
        bg = (70, 120, 85) if on else (55, 58, 64)
        pygame.draw.rect(screen, bg, self.rect, border_radius=4)
        pygame.draw.rect(screen, (140, 150, 145), self.rect, 1, border_radius=4)
        state = "ON" if on else "OFF"
        screen.blit(
            font.render(f"{self.label}:  {state}", True, (230, 235, 225)),
            (self.rect.x + 10, self.rect.y + 5),
        )


def main() -> int:
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption("Terrain mottling preview")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("menlo", 15)
    small = pygame.font.SysFont("menlo", 12)
    tiny = pygame.font.SysFont("menlo", 11)

    biomes = list(PREVIEW_TERRAINS)
    bi = 0
    params = get_params()
    dirty = True
    show_grid = True
    field_surf: pygame.Surface | None = None
    active: Slider | None = None
    status = ""

    knobs = [
        Slider(name, label, lo, hi, is_int, PANEL_X, 120 + i * ROW_H)
        for i, (name, label, lo, hi, is_int) in enumerate(_SLIDER_SPECS)
    ]
    toggles = [
        Toggle("gaussian", "Gaussian filter", PANEL_X, 120 + len(knobs) * ROW_H + 8),
        Toggle(
            "smooth_resample",
            "Resample 1:1 (smooth)",
            PANEL_X,
            120 + len(knobs) * ROW_H + 42,
        ),
    ]

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_RIGHT:
                    bi = (bi + 1) % len(biomes)
                    dirty = True
                elif event.key == pygame.K_LEFT:
                    bi = (bi - 1) % len(biomes)
                    dirty = True
                elif event.key == pygame.K_g:
                    show_grid = not show_grid
                elif event.key == pygame.K_r:
                    params = replace(params, seed=random.randint(0, 9999))
                    set_params(params)
                    dirty = True
                elif event.key == pygame.K_d:
                    params = MottleParams()
                    set_params(params)
                    dirty = True
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                handled = False
                for t in toggles:
                    if t.hit(event.pos):
                        params = t.flip(params)
                        set_params(params)
                        dirty = True
                        handled = True
                        break
                if handled:
                    continue
                for s in knobs:
                    pad = pygame.Rect(s.rect.x - 4, s.rect.y - 18, s.rect.w + 8, s.rect.h + 22)
                    if pad.collidepoint(event.pos):
                        active = s
                        params = s.set_from_mouse(event.pos[0], params)
                        set_params(params)
                        dirty = True
                        break
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                active = None
            elif event.type == pygame.MOUSEMOTION and active is not None:
                params = active.set_from_mouse(event.pos[0], params)
                set_params(params)
                dirty = True

        terrain = biomes[bi]
        cell = max(24, CELL_SIZE)
        field_px = GRID * cell
        n_tiles = GRID * GRID

        if dirty:
            status = f"Baking {GRID}×{GRID} = {n_tiles} cells ({field_px}×{field_px}px)…"
            # Draw status before the slow bake so the UI doesn't look frozen.
            screen.fill((28, 30, 34))
            screen.blit(font.render(status, True, (220, 200, 140)), (PAD, PAD))
            pygame.display.flip()
            field_surf = world_mottle_region(terrain, 0, 0, field_px, field_px, params)
            dirty = False
            status = "Ready"

        screen.fill((28, 30, 34))
        assert field_surf is not None
        field_origin = (PAD, PAD + 56)
        screen.blit(field_surf, field_origin)

        if show_grid:
            ox, oy = field_origin
            for i in range(GRID + 1):
                x = ox + i * cell
                y = oy + i * cell
                pygame.draw.line(screen, (40, 48, 42), (x, oy), (x, oy + field_px), 1)
                pygame.draw.line(screen, (40, 48, 42), (ox, y), (ox + field_px, y), 1)
            # Corner labels for first cell
            screen.blit(
                tiny.render("cell (0,0)", True, (180, 190, 160)),
                (ox + 3, oy + 3),
            )

        # Title / count — make tile count impossible to miss
        title = f"{terrain.name}"
        screen.blit(font.render(title, True, (230, 230, 220)), (PAD, PAD))
        count_line = (
            f"Showing {GRID}×{GRID} game cells  =  {n_tiles} tiles   "
            f"({cell}×{cell}px each → {field_px}×{field_px}px field)"
        )
        screen.blit(small.render(count_line, True, (180, 200, 160)), (PAD, PAD + 20))
        mode_line = (
            "Continuous world noise — NOT a repeating tile.  "
            f"Filters: gaussian={'ON' if params.gaussian else 'off'}  "
            f"resample1:1={'ON' if params.smooth_resample else 'off'}"
        )
        screen.blit(tiny.render(mode_line, True, (150, 160, 150)), (PAD, PAD + 38))

        # One-cell zoom (same world UV, unique — not a period tile)
        zoom = world_mottle_region(terrain, 0, 0, cell, cell, params)
        mag = 4
        big = pygame.transform.scale(zoom, (cell * mag, cell * mag))
        zy = field_origin[1] + field_px + 12
        screen.blit(big, (PAD, zy))
        screen.blit(
            small.render(
                f"1 cell zoom (cell 0,0 only — {cell}×{cell}px ×{mag})",
                True,
                (150, 155, 150),
            ),
            (PAD, zy + cell * mag + 4),
        )

        # Right panel
        screen.blit(font.render("parameters", True, (180, 190, 170)), (PANEL_X, PAD + 8))
        screen.blit(
            tiny.render("Grid lines = game cells (press G)", True, (130, 140, 135)),
            (PANEL_X, PAD + 28),
        )
        screen.blit(
            tiny.render(f"status: {status}", True, (130, 150, 130)),
            (PANEL_X, PAD + 44),
        )
        for s in knobs:
            s.draw(screen, small, params)
        for t in toggles:
            t.draw(screen, small, params)

        tip_y = toggles[-1].rect.bottom + 20
        for i, line in enumerate(
            (
                "← → biome   G grid   R reseed   D defaults",
                "No period tile — each pixel is unique.",
                "Gaussian = soft blur kernel.",
                "Resample 1:1 = smoothscale same size.",
            )
        ):
            screen.blit(tiny.render(line, True, (120, 125, 120)), (PANEL_X, tip_y + i * 16))

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
