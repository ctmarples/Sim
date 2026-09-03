#!/usr/bin/env python3
"""Live preview: per-biome mottling + texture overlays + seasonal flecks.

Usage (from environment_sandbox):

    python preview_terrain_fills.py

Mottle + overlay knobs are per biome. Fleck knobs are per season half.
Save writes ``assets/terrain/terrain_look.json`` for the game bake/sim.
"""

from __future__ import annotations

import random
import sys
from dataclasses import replace

import pygame

from seasons import DAYS_PER_SEASON, YEAR_DAYS
from terrain_fills import PREVIEW_TERRAINS
from terrain_flecks import (
    FleckParams,
    apply_flecks_for_day,
    period_for_day,
    period_name,
    preview_terrain_grid,
)
from terrain_mottle import MottleParams
from terrain_overlays import OverlayParams, apply_overlays_to_field
from terrain_settings import (
    AnimParams,
    active_setting_set,
    get_anim_params,
    get_fleck,
    get_mottle,
    get_overlay,
    list_setting_sets,
    load_setting_set,
    load_settings,
    reset_defaults,
    save_setting_set,
    season_transition,
    set_anim_params,
    set_fleck,
    set_mottle,
    settings_path,
    update_fleck,
    update_mottle,
    update_overlay,
)
from terrain_tiles_procedural import cell_corners, compose_cell_fills
from world import TerrainType

WINDOW_W = 1280
WINDOW_H = 900
GRID = 6
PAD = 16
PANEL_W = 300
SLIDER_W = 250
SLIDER_H = 10
ROW_H = 28
PANEL_TOP = 8
PANEL_BOTTOM_PAD = 8
# Set at runtime from field size.
PANEL_X = 560

_SEASON_CHIPS: tuple[tuple[int, str], ...] = (
    (0, "Spr early"),
    (1, "Spr late"),
    (2, "Sum early"),
    (3, "Sum late"),
    (4, "Aut early"),
    (5, "Aut late"),
    (6, "Win early"),
    (7, "Win late"),
)

_MOTTLE_SLIDERS: list[tuple[str, str, float, float, bool]] = [
    ("coarse_scale", "coarse scale", 0.005, 0.12, False),
    ("mid_scale", "mid scale", 0.02, 0.4, False),
    ("fine_scale", "fine scale", 0.08, 1.2, False),
    ("coarse_amp", "coarse amp", 0.0, 0.6, False),
    ("mid_amp", "mid amp", 0.0, 0.4, False),
    ("fine_amp", "fine amp", 0.0, 0.3, False),
    ("speckle", "palette speckle", 0.0, 0.5, False),
    ("palette_mix", "palette mix", 0.0, 1.0, False),
    ("seed", "mottle seed", 0, 9999, True),
]

_FLECK_SLIDERS: list[tuple[str, str, float, float, bool]] = [
    ("speckle_density", "speckle density", 0.0, 3.0, False),
    ("cluster_density", "cluster density", 0.0, 3.0, False),
    ("speckle_alpha", "speckle alpha", 0.0, 1.5, False),
    ("cluster_alpha", "cluster alpha", 0.0, 1.5, False),
    ("cluster_spread", "cluster spread", 0.5, 2.0, False),
    ("seed", "fleck seed", 0, 9999, True),
]

_OVERLAY_SLIDERS: list[tuple[str, str, float, float, bool]] = [
    ("rocks_density", "rocks density", 0.0, 3.0, False),
    ("foliage_density", "foliage density", 0.0, 3.0, False),
    ("pebbles_density", "pebbles density", 0.0, 3.0, False),
    ("scale", "stamp scale", 0.25, 2.5, False),
    ("opacity", "stamp opacity", 0.0, 1.0, False),
    ("seed", "overlay seed", 0, 9999, True),
]

_ANIM_SLIDERS: list[tuple[str, str, float, float, bool]] = [
    ("fade_days", "fade days", 0.2, 8.0, False),
    ("fade_ease", "fade ease", 0.0, 1.0, False),
    ("intro_delay", "intro delay", 0.0, 0.8, False),
    ("exit_hold", "exit hold", 0.0, 0.8, False),
    ("opacity", "fleck opacity", 0.0, 1.5, False),
    ("autoplay_speed", "play speed (d/s)", 0.5, 20.0, False),
]


def _fmt(value: float, is_int: bool, lo: float, hi: float) -> str:
    if is_int:
        return str(int(round(value)))
    if hi - lo < 0.5:
        return f"{value:.3f}"
    return f"{value:.2f}"


class Slider:
    def __init__(
        self,
        name: str,
        label: str,
        lo: float,
        hi: float,
        is_int: bool,
        x: int,
        y: int,
        *,
        target: str,
    ) -> None:
        self.name = name
        self.label = label
        self.lo = lo
        self.hi = hi
        self.is_int = is_int
        self.base_y = y
        self.rect = pygame.Rect(x, y, SLIDER_W, SLIDER_H)
        self.target = target  # mottle | overlay | fleck | anim | year

    def set_scroll(self, scroll: int) -> None:
        self.rect.y = self.base_y - scroll
    def value_of(
        self,
        mottle: MottleParams,
        fleck: FleckParams,
        anim: AnimParams,
        year_day: float,
        overlay: OverlayParams | None = None,
    ) -> float:
        if self.target == "year":
            return year_day
        if self.target == "fleck":
            return float(getattr(fleck, self.name))
        if self.target == "anim":
            return float(getattr(anim, self.name))
        if self.target == "overlay":
            assert overlay is not None
            return float(getattr(overlay, self.name))
        return float(getattr(mottle, self.name))

    def apply(
        self,
        mx: int,
        *,
        biome: TerrainType,
        period: int,
        mottle: MottleParams,
        fleck: FleckParams,
        anim: AnimParams,
        year_day: float,
        overlay: OverlayParams,
    ) -> tuple[MottleParams, FleckParams, AnimParams, float, OverlayParams]:
        t = (mx - self.rect.x) / max(1, self.rect.w)
        t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
        raw = self.lo + (self.hi - self.lo) * t
        if self.is_int:
            raw = int(round(raw))
        if self.target == "year":
            return mottle, fleck, anim, float(raw) % float(YEAR_DAYS), overlay
        if self.target == "fleck":
            fleck = update_fleck(period, **{self.name: raw})
            return mottle, fleck, anim, year_day, overlay
        if self.target == "anim":
            anim = replace(anim, **{self.name: raw})
            set_anim_params(anim)
            return mottle, fleck, anim, year_day, overlay
        if self.target == "overlay":
            overlay = update_overlay(biome, **{self.name: raw})
            return mottle, fleck, anim, year_day, overlay
        mottle = update_mottle(biome, **{self.name: raw})
        return mottle, fleck, anim, year_day, overlay

    def draw(
        self,
        screen: pygame.Surface,
        font: pygame.font.Font,
        mottle: MottleParams,
        fleck: FleckParams,
        anim: AnimParams,
        year_day: float,
        overlay: OverlayParams,
    ) -> None:
        val = self.value_of(mottle, fleck, anim, year_day, overlay)
        t = 0.0 if self.hi == self.lo else (val - self.lo) / (self.hi - self.lo)
        t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
        colours = {
            "mottle": (90, 140, 100),
            "overlay": (140, 150, 100),
            "fleck": (100, 130, 160),
            "anim": (150, 120, 90),
            "year": (160, 140, 70),
        }
        colour = colours.get(self.target, (90, 140, 100))
        pygame.draw.rect(screen, (50, 54, 60), self.rect, border_radius=3)
        fill = self.rect.copy()
        fill.w = max(2, int(self.rect.w * t))
        pygame.draw.rect(screen, colour, fill, border_radius=3)
        pygame.draw.rect(screen, (120, 130, 140), self.rect, 1, border_radius=3)
        knob_x = self.rect.x + int(self.rect.w * t)
        pygame.draw.circle(screen, (220, 230, 210), (knob_x, self.rect.centery), 6)
        screen.blit(
            font.render(
                f"{self.label}: {_fmt(val, self.is_int, self.lo, self.hi)}",
                True,
                (200, 205, 195),
            ),
            (self.rect.x, self.rect.y - 14),
        )


class ChipButton:
    def __init__(self, label: str, x: int, y: int, w: int = 78, h: int = 24) -> None:
        self.label = label
        self.rect = pygame.Rect(x, y, w, h)

    def hit(self, pos: tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)

    def draw(
        self,
        screen: pygame.Surface,
        font: pygame.font.Font,
        *,
        selected: bool,
        accent: tuple[int, int, int] = (90, 140, 100),
    ) -> None:
        bg = accent if selected else (48, 52, 58)
        border = (220, 230, 200) if selected else (100, 108, 112)
        pygame.draw.rect(screen, bg, self.rect, border_radius=5)
        pygame.draw.rect(screen, border, self.rect, 1, border_radius=5)
        text = font.render(self.label, True, (235, 238, 230) if selected else (170, 175, 170))
        screen.blit(
            text,
            (
                self.rect.centerx - text.get_width() // 2,
                self.rect.centery - text.get_height() // 2,
            ),
        )


class ActionButton:
    def __init__(self, label: str, x: int, y: int, w: int = 120, h: int = 28) -> None:
        self.label = label
        self.base_y = y
        self.rect = pygame.Rect(x, y, w, h)
        self.flash = 0

    def set_scroll(self, scroll: int) -> None:
        self.rect.y = self.base_y - scroll

    def hit(self, pos: tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)

    def draw(self, screen: pygame.Surface, font: pygame.font.Font, *, active: bool = False) -> None:
        if self.flash > 0:
            bg = (90, 150, 100)
            self.flash -= 1
        elif active:
            bg = (70, 120, 85)
        else:
            bg = (55, 58, 64)
        pygame.draw.rect(screen, bg, self.rect, border_radius=5)
        pygame.draw.rect(screen, (140, 150, 145), self.rect, 1, border_radius=5)
        text = font.render(self.label, True, (230, 235, 225))
        screen.blit(
            text,
            (
                self.rect.centerx - text.get_width() // 2,
                self.rect.centery - text.get_height() // 2,
            ),
        )


def _layout_chips(
    labels: list[str],
    x0: int,
    y0: int,
    *,
    max_w: int,
    chip_h: int = 24,
    gap: int = 6,
    min_w: int = 64,
) -> list[ChipButton]:
    chips: list[ChipButton] = []
    x, y = x0, y0
    for label in labels:
        w = max(min_w, min(100, 12 + len(label) * 7))
        if x + w > x0 + max_w and x > x0:
            x = x0
            y += chip_h + gap
        chips.append(ChipButton(label, x, y, w=w, h=chip_h))
        x += w + gap
    return chips


def _build_field(
    terrain_grid: list[list[TerrainType]],
    cell: int,
) -> pygame.Surface:
    grid = len(terrain_grid)
    field_px = grid * cell
    out = pygame.Surface((field_px, field_px)).convert()

    def terrain_at(x: int, y: int) -> TerrainType:
        xx = max(0, min(grid - 1, x))
        yy = max(0, min(grid - 1, y))
        return terrain_grid[yy][xx]

    for cy in range(grid):
        for cx in range(grid):
            corners = cell_corners(terrain_at, cx, cy)
            rgb, _, _, _, _ = compose_cell_fills(
                *corners, cell_x=cx, cell_y=cy, size=cell
            )
            out.blit(rgb.convert(), (cx * cell, cy * cell))
    apply_overlays_to_field(out, terrain_grid, cell)
    return out


def main() -> int:
    pygame.init()
    load_settings()
    info = pygame.display.Info()
    # Prefer a size that fits the display; OS may still shrink it.
    win_w = min(WINDOW_W, max(1100, min(info.current_w - 40, 1480)))
    win_h = min(max(WINDOW_H, 920), max(780, min(info.current_h - 80, 1100)))
    screen = pygame.display.set_mode((win_w, win_h), pygame.RESIZABLE)
    pygame.display.set_caption("Terrain look preview")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("menlo", 13)
    small = pygame.font.SysFont("menlo", 12)
    tiny = pygame.font.SysFont("menlo", 10)

    biomes = list(PREVIEW_TERRAINS)
    bi = 0
    year_day = 0.0
    show_grid = True
    forest_center = False
    dirty = True
    field_base: pygame.Surface | None = None
    field_surf: pygame.Surface | None = None
    active: Slider | None = None
    status = "Loaded settings" if settings_path().is_file() else "Using defaults"
    save_msg = ""
    panel_scroll = 0
    set_names = list(list_setting_sets()) or ["default"]
    selected_set = active_setting_set()
    if selected_set not in set_names:
        set_names.append(selected_set)
        set_names.sort(key=str.casefold)
    set_index = set_names.index(selected_set)

    cell = 72
    field_px = GRID * cell
    field_origin = (PAD, PAD + 52)
    panel_x = field_origin[0] + field_px + 20

    chip_y = field_origin[1] + field_px + 6
    biome_chips = _layout_chips(
        [t.name for t in biomes], PAD, chip_y + 14, max_w=field_px, min_w=64
    )
    season_y = (biome_chips[-1].rect.bottom + 6) if biome_chips else chip_y + 36
    season_chips = _layout_chips(
        [lbl for _p, lbl in _SEASON_CHIPS],
        PAD,
        season_y + 14,
        max_w=field_px,
        min_w=68,
    )

    year_slider = Slider(
        "year_day",
        "year day (animation)",
        0,
        YEAR_DAYS - 0.01,
        False,
        PAD,
        season_chips[-1].rect.bottom + 24,
        target="year",
    )
    year_slider.rect.w = field_px

    # Right panel layout (content Y; scrolled via set_scroll)
    y0 = 28
    mottle_knobs = [
        Slider(n, lbl, lo, hi, is_int, panel_x, y0 + i * ROW_H, target="mottle")
        for i, (n, lbl, lo, hi, is_int) in enumerate(_MOTTLE_SLIDERS)
    ]
    y_overlay = y0 + len(mottle_knobs) * ROW_H + 20
    btn_rocks = ActionButton("Rocks OFF", panel_x, y_overlay, w=78, h=22)
    btn_foliage = ActionButton("Foliage OFF", panel_x + 84, y_overlay, w=84, h=22)
    btn_pebbles = ActionButton("Pebbles OFF", panel_x + 174, y_overlay, w=86, h=22)
    overlay_knobs = [
        Slider(
            n,
            lbl,
            lo,
            hi,
            is_int,
            panel_x,
            y_overlay + 28 + i * ROW_H,
            target="overlay",
        )
        for i, (n, lbl, lo, hi, is_int) in enumerate(_OVERLAY_SLIDERS)
    ]
    y_fleck = y_overlay + 28 + len(overlay_knobs) * ROW_H + 20
    fleck_knobs = [
        Slider(n, lbl, lo, hi, is_int, panel_x, y_fleck + i * ROW_H, target="fleck")
        for i, (n, lbl, lo, hi, is_int) in enumerate(_FLECK_SLIDERS)
    ]
    y_anim = y_fleck + len(fleck_knobs) * ROW_H + 20
    anim_knobs = [
        Slider(n, lbl, lo, hi, is_int, panel_x, y_anim + i * ROW_H, target="anim")
        for i, (n, lbl, lo, hi, is_int) in enumerate(_ANIM_SLIDERS)
    ]
    btn_y = y_anim + len(anim_knobs) * ROW_H + 8
    btn_clusters = ActionButton("Clusters ON", panel_x, btn_y, w=118, h=24)
    btn_flecks = ActionButton("Flecks ON", panel_x + 126, btn_y, w=118, h=24)
    btn_play = ActionButton("Play year", panel_x, btn_y + 30, w=118, h=24)
    btn_forest = ActionButton("Forest OFF", panel_x + 126, btn_y + 30, w=118, h=24)
    btn_set_prev = ActionButton("<", panel_x, btn_y + 60, w=30, h=24)
    btn_set_next = ActionButton(">", panel_x + 36, btn_y + 60, w=30, h=24)
    btn_set_load = ActionButton("Load set", panel_x + 72, btn_y + 60, w=82, h=24)
    btn_set_new = ActionButton("New set", panel_x + 160, btn_y + 60, w=84, h=24)
    btn_save = ActionButton("Save current set", panel_x, btn_y + 90, w=244, h=28)
    btn_reset = ActionButton("Reset defaults", panel_x, btn_y + 124, w=244, h=26)

    panel_sliders = mottle_knobs + overlay_knobs + fleck_knobs + anim_knobs
    panel_buttons = [
        btn_rocks,
        btn_foliage,
        btn_pebbles,
        btn_clusters,
        btn_flecks,
        btn_play,
        btn_forest,
        btn_set_prev,
        btn_set_next,
        btn_set_load,
        btn_set_new,
        btn_save,
        btn_reset,
    ]

    panel_section_ys = (
        (y0 - 18, "mottle"),
        (y_overlay - 16, "overlays"),
        (y_fleck - 16, "flecks"),
        (y_anim - 16, "animation"),
    )
    tip_lines = (
        "Mottle + overlays: selected biome.",
        "PNGs: assets/terrain/overlays/{kind}_N.png",
        "Flecks: selected season.  Wheel scrolls panel.",
        "S save set   D reset   Space play   G grid",
    )
    tip_base_y = btn_reset.base_y + 34
    panel_content_h = tip_base_y + len(tip_lines) * 13 + 8
    all_sliders = panel_sliders + [year_slider]

    # Ensure window is wide enough for field + panel.
    need_w = panel_x + PANEL_W + 24
    need_h = max(year_slider.base_y + 48, field_origin[1] + field_px + 220)
    if screen.get_width() < need_w or screen.get_height() < min(need_h, 900):
        screen = pygame.display.set_mode(
            (max(screen.get_width(), need_w), max(screen.get_height(), min(need_h, 980))),
            pygame.RESIZABLE,
        )

    def current_period() -> int:
        return period_for_day(int(year_day))

    def sync_from_store() -> tuple[MottleParams, FleckParams, AnimParams, OverlayParams]:
        return (
            get_mottle(biomes[bi]),
            get_fleck(current_period()),
            get_anim_params(),
            get_overlay(biomes[bi]),
        )

    def panel_view_h() -> int:
        return max(120, screen.get_height() - PANEL_TOP - PANEL_BOTTOM_PAD)

    def max_panel_scroll() -> int:
        return max(0, panel_content_h - panel_view_h())

    def apply_panel_scroll() -> None:
        nonlocal panel_scroll
        panel_scroll = max(0, min(max_panel_scroll(), panel_scroll))
        for s in panel_sliders:
            s.set_scroll(panel_scroll)
        for b in panel_buttons:
            b.set_scroll(panel_scroll)

    def panel_hit(pos: tuple[int, int]) -> bool:
        return pos[0] >= panel_x - 8 and pos[1] >= PANEL_TOP

    def panel_clip_rect() -> pygame.Rect:
        return pygame.Rect(panel_x - 10, PANEL_TOP, PANEL_W + 20, panel_view_h())

    mottle, fleck, anim, overlay = sync_from_store()
    apply_panel_scroll()

    running = True
    while running:
        dt = clock.tick(30) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.VIDEORESIZE:
                apply_panel_scroll()
            elif event.type == pygame.MOUSEWHEEL:
                if panel_hit(pygame.mouse.get_pos()):
                    panel_scroll -= event.y * 28
                    apply_panel_scroll()
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_RIGHT:
                    bi = (bi + 1) % len(biomes)
                    mottle = get_mottle(biomes[bi])
                    overlay = get_overlay(biomes[bi])
                    dirty = True
                elif event.key == pygame.K_LEFT:
                    bi = (bi - 1) % len(biomes)
                    mottle = get_mottle(biomes[bi])
                    overlay = get_overlay(biomes[bi])
                    dirty = True
                elif event.key == pygame.K_LEFTBRACKET:
                    year_day = (year_day - DAYS_PER_SEASON // 2) % YEAR_DAYS
                    fleck = get_fleck(current_period())
                    dirty = True
                elif event.key == pygame.K_RIGHTBRACKET:
                    year_day = (year_day + DAYS_PER_SEASON // 2) % YEAR_DAYS
                    fleck = get_fleck(current_period())
                    dirty = True
                elif event.key == pygame.K_g:
                    show_grid = not show_grid
                elif event.key == pygame.K_s:
                    path = save_setting_set(set_names[set_index])
                    save_msg = f"Saved set → {path.stem}"
                    btn_save.flash = 20
                    status = save_msg
                elif event.key == pygame.K_r:
                    mottle = update_mottle(biomes[bi], seed=random.randint(0, 9999))
                    fleck = update_fleck(current_period(), seed=random.randint(0, 9999))
                    overlay = update_overlay(biomes[bi], seed=random.randint(0, 9999))
                    dirty = True
                elif event.key == pygame.K_d:
                    reset_defaults()
                    mottle, fleck, anim, overlay = sync_from_store()
                    dirty = True
                    status = "Reset to defaults"
                elif event.key == pygame.K_SPACE:
                    anim = replace(anim, autoplay=not anim.autoplay)
                    set_anim_params(anim)
                    btn_play.flash = 8
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                handled = False
                for i, chip in enumerate(biome_chips):
                    if chip.hit(event.pos):
                        bi = i
                        mottle = get_mottle(biomes[bi])
                        overlay = get_overlay(biomes[bi])
                        dirty = True
                        handled = True
                        break
                if not handled:
                    for period_i, chip in enumerate(season_chips):
                        if chip.hit(event.pos):
                            year_day = float(period_i * (DAYS_PER_SEASON // 2))
                            fleck = get_fleck(period_i)
                            dirty = True
                            handled = True
                            break
                if not handled:
                    panel_rect = panel_clip_rect()
                    in_panel = panel_rect.collidepoint(event.pos)
                    if in_panel and btn_rocks.hit(event.pos):
                        overlay = update_overlay(biomes[bi], rocks=not overlay.rocks)
                        dirty = True
                        handled = True
                    elif in_panel and btn_foliage.hit(event.pos):
                        overlay = update_overlay(biomes[bi], foliage=not overlay.foliage)
                        dirty = True
                        handled = True
                    elif in_panel and btn_pebbles.hit(event.pos):
                        overlay = update_overlay(biomes[bi], pebbles=not overlay.pebbles)
                        dirty = True
                        handled = True
                    elif in_panel and btn_clusters.hit(event.pos):
                        fleck = update_fleck(
                            current_period(),
                            clusters_enabled=not fleck.clusters_enabled,
                        )
                        dirty = True
                        handled = True
                    elif in_panel and btn_flecks.hit(event.pos):
                        fleck = update_fleck(
                            current_period(), enabled=not fleck.enabled
                        )
                        dirty = True
                        handled = True
                    elif in_panel and btn_play.hit(event.pos):
                        anim = replace(anim, autoplay=not anim.autoplay)
                        set_anim_params(anim)
                        handled = True
                    elif in_panel and btn_forest.hit(event.pos):
                        forest_center = not forest_center
                        dirty = True
                        handled = True
                    elif in_panel and btn_set_prev.hit(event.pos):
                        set_index = (set_index - 1) % len(set_names)
                        status = f"Selected set: {set_names[set_index]}"
                        handled = True
                    elif in_panel and btn_set_next.hit(event.pos):
                        set_index = (set_index + 1) % len(set_names)
                        status = f"Selected set: {set_names[set_index]}"
                        handled = True
                    elif in_panel and btn_set_load.hit(event.pos):
                        name = set_names[set_index]
                        if load_setting_set(name):
                            mottle, fleck, anim, overlay = sync_from_store()
                            dirty = True
                            status = f"Loaded set: {name}"
                        else:
                            status = f"Could not load set: {name}"
                        handled = True
                    elif in_panel and btn_set_new.hit(event.pos):
                        used = set(set_names)
                        number = 1
                        while f"terrain_set_{number}" in used:
                            number += 1
                        name = f"terrain_set_{number}"
                        set_names.append(name)
                        set_names.sort(key=str.casefold)
                        set_index = set_names.index(name)
                        path = save_setting_set(name)
                        status = f"Created set: {path.stem}"
                        handled = True
                    elif in_panel and btn_save.hit(event.pos):
                        path = save_setting_set(set_names[set_index])
                        save_msg = f"Saved set → {path.stem}"
                        status = save_msg
                        btn_save.flash = 24
                        handled = True
                    elif in_panel and btn_reset.hit(event.pos):
                        reset_defaults()
                        mottle, fleck, anim, overlay = sync_from_store()
                        dirty = True
                        status = "Reset to defaults"
                        handled = True
                if handled:
                    continue
                # Panel widgets only when inside the visible panel strip.
                panel_rect = panel_clip_rect()
                for s in all_sliders:
                    if s.target != "year" and not panel_rect.collidepoint(event.pos):
                        continue
                    pad_r = pygame.Rect(
                        s.rect.x - 4, s.rect.y - 14, s.rect.w + 8, s.rect.h + 18
                    )
                    if pad_r.collidepoint(event.pos):
                        active = s
                        mottle, fleck, anim, year_day, overlay = s.apply(
                            event.pos[0],
                            biome=biomes[bi],
                            period=current_period(),
                            mottle=mottle,
                            fleck=fleck,
                            anim=anim,
                            year_day=year_day,
                            overlay=overlay,
                        )
                        fleck = get_fleck(current_period())
                        dirty = True
                        break
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                active = None
            elif event.type == pygame.MOUSEMOTION and active is not None:
                mottle, fleck, anim, year_day, overlay = active.apply(
                    event.pos[0],
                    biome=biomes[bi],
                    period=current_period(),
                    mottle=mottle,
                    fleck=fleck,
                    anim=anim,
                    year_day=year_day,
                    overlay=overlay,
                )
                fleck = get_fleck(current_period())
                dirty = True

        if anim.autoplay:
            year_day = (year_day + anim.autoplay_speed * dt) % YEAR_DAYS
            fleck = get_fleck(current_period())
            dirty = True

        terrain = biomes[bi]
        period = current_period()
        to_p, from_p, fade_t = season_transition(year_day, anim=anim)
        terrain_grid = preview_terrain_grid(
            terrain, GRID, forest_center=forest_center, forest_radius=1
        )

        if dirty:
            status_draw = "Baking…"
            screen.set_clip(None)
            screen.fill((28, 30, 34))
            screen.blit(font.render(status_draw, True, (220, 200, 140)), (PAD, PAD))
            pygame.display.flip()
            try:
                field_base = _build_field(terrain_grid, cell)
                field_surf = field_base.copy()
                apply_flecks_for_day(
                    field_surf,
                    day=year_day,
                    terrain_grid=terrain_grid,
                    cell_size=cell,
                    forest_center=forest_center,
                )
                status = "Ready" if not save_msg.startswith("Saved") else status
            except Exception as exc:
                status = f"Bake error: {exc}"
                if field_base is not None:
                    field_surf = field_base.copy()
            dirty = False
            save_msg = ""

        # Always clear clip before the main frame — a leftover panel clip
        # would hide the terrain field on the left.
        screen.set_clip(None)
        screen.fill((28, 30, 34))
        assert field_surf is not None
        screen.blit(field_surf, field_origin)

        if show_grid:
            ox, oy = field_origin
            for i in range(GRID + 1):
                x = ox + i * cell
                y = oy + i * cell
                pygame.draw.line(screen, (40, 48, 42), (x, oy), (x, oy + field_px), 1)
                pygame.draw.line(screen, (40, 48, 42), (ox, y), (ox + field_px, y), 1)

        fade_note = ""
        if from_p is not None:
            fade_note = f"  fade {period_name(from_p)}→{period_name(to_p)} t={fade_t:.2f}"
        title = f"{terrain.name} mottling  ·  {period_name(period)} flecks  ·  day {year_day:.1f}"
        screen.blit(font.render(title, True, (230, 230, 220)), (PAD, PAD))
        screen.blit(
            small.render(
                f"per-biome mottle / per-season flecks{fade_note}",
                True,
                (180, 200, 160),
            ),
            (PAD, PAD + 20),
        )
        screen.blit(
            tiny.render(status, True, (150, 160, 150)),
            (PAD, PAD + 38),
        )

        screen.blit(small.render("biome (mottle)", True, (180, 190, 160)), (PAD, chip_y))
        for i, chip in enumerate(biome_chips):
            chip.draw(screen, tiny, selected=(i == bi), accent=(70, 120, 85))
        screen.blit(small.render("season (flecks)", True, (170, 185, 200)), (PAD, season_y))
        for i, chip in enumerate(season_chips):
            chip.draw(screen, tiny, selected=(i == period), accent=(80, 110, 150))
        year_slider.draw(screen, tiny, mottle, fleck, anim, year_day, overlay)

        # Scrollable right panel
        apply_panel_scroll()
        panel_rect = panel_clip_rect()
        pygame.draw.rect(screen, (36, 38, 44), panel_rect)
        pygame.draw.rect(screen, (70, 74, 82), panel_rect, 1)
        screen.set_clip(panel_rect)

        section_colours = {
            "mottle": (180, 190, 170),
            "overlays": (190, 195, 150),
            "flecks": (170, 185, 200),
            "animation": (200, 180, 140),
        }
        for base_y, key in panel_section_ys:
            label = (
                f"{key} · {terrain.name}"
                if key in ("mottle", "overlays")
                else (f"{key} · {period_name(period)}" if key == "flecks" else key)
            )
            screen.blit(
                font.render(label, True, section_colours[key]),
                (panel_x, base_y - panel_scroll),
            )
        for s in panel_sliders:
            s.draw(screen, tiny, mottle, fleck, anim, year_day, overlay)

        btn_rocks.label = "Rocks ON" if overlay.rocks else "Rocks OFF"
        btn_foliage.label = "Foliage ON" if overlay.foliage else "Foliage OFF"
        btn_pebbles.label = "Pebbles ON" if overlay.pebbles else "Pebbles OFF"
        btn_clusters.label = "Clusters ON" if fleck.clusters_enabled else "Clusters OFF"
        btn_flecks.label = "Flecks ON" if fleck.enabled else "Flecks OFF"
        btn_play.label = "Pause year" if anim.autoplay else "Play year"
        btn_forest.label = "Forest ON" if forest_center else "Forest OFF"
        set_name = set_names[set_index]
        for b, on in (
            (btn_rocks, overlay.rocks),
            (btn_foliage, overlay.foliage),
            (btn_pebbles, overlay.pebbles),
            (btn_clusters, fleck.clusters_enabled),
            (btn_flecks, fleck.enabled),
            (btn_play, anim.autoplay),
            (btn_forest, forest_center),
        ):
            b.draw(screen, small, active=on)
        btn_set_prev.draw(screen, small)
        btn_set_next.draw(screen, small)
        btn_set_load.draw(screen, small)
        btn_set_new.draw(screen, small)
        btn_save.draw(screen, small)
        btn_reset.draw(screen, small)
        screen.blit(
            tiny.render(f"terrain set: {set_name}", True, (185, 195, 175)),
            (panel_x, btn_y + 48 - panel_scroll),
        )

        for i, line in enumerate(tip_lines):
            screen.blit(
                tiny.render(line, True, (120, 125, 120)),
                (panel_x, tip_base_y - panel_scroll + i * 13),
            )
        screen.set_clip(None)

        # Scroll cue
        if max_panel_scroll() > 0:
            bar_h = max(24, int(panel_view_h() * panel_view_h() / panel_content_h))
            bar_y = PANEL_TOP + int(
                (panel_view_h() - bar_h) * panel_scroll / max(1, max_panel_scroll())
            )
            pygame.draw.rect(
                screen,
                (70, 74, 80),
                pygame.Rect(panel_x + PANEL_W + 4, bar_y, 4, bar_h),
                border_radius=2,
            )

        pygame.display.flip()

    # Closing the editor commits the set currently shown in the preview. The
    # parent game notices process exit and reloads this active set.
    save_setting_set(set_names[set_index])
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
    active_setting_set,
    list_setting_sets,
    load_setting_set,
