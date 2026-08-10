"""Workplace slot widgets for villager inspect UI."""

from __future__ import annotations

from collections.abc import Callable

import pygame

from icons import blit_icon
from seasons import SEASON_LABELS, SEASON_ORDER, Season
from settings import (
    COLOUR_TEXT,
    COLOUR_TEXT_DIM,
    COLOUR_TOOLBAR_BORDER,
    COLOUR_TOOLBAR_BTN,
    COLOUR_TOOLBAR_BTN_HOVER,
)

SLOT_SIZE = 28
SLOT_GAP = 4
SEASON_LABEL_W = 52


def _slot_bg(*, hovered: bool) -> tuple[int, int, int]:
    if hovered:
        return COLOUR_TOOLBAR_BTN_HOVER
    return COLOUR_TOOLBAR_BTN


def draw_workplace_slot(
    surface: pygame.Surface,
    rect: pygame.Rect,
    *,
    icon: str | None,
    font: pygame.font.Font,
    hovered: bool = False,
) -> None:
    pygame.draw.rect(surface, _slot_bg(hovered=hovered), rect, border_radius=4)
    pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, rect, 1, border_radius=4)
    if icon:
        blit_icon(surface, icon, rect.centerx, rect.centery, min(rect.w, rect.h) - 6)
    else:
        plus = font.render("+", True, COLOUR_TEXT_DIM)
        surface.blit(
            plus,
            (
                rect.x + (rect.w - plus.get_width()) // 2,
                rect.y + (rect.h - plus.get_height()) // 2,
            ),
        )


def draw_workplace_slot_row(
    surface: pygame.Surface,
    x: int,
    y: int,
    slot_ids: list[int | None],
    *,
    icon_for_building: Callable[[int | None], str | None],
    font: pygame.font.Font,
    mouse_pos: tuple[int, int] | None = None,
    action_prefix: str = "assign_workplace",
    season: Season | None = None,
    interactive: bool = True,
) -> tuple[list[tuple[str, pygame.Rect]], int]:
    hits: list[tuple[str, pygame.Rect]] = []
    while len(slot_ids) < 3:
        slot_ids.append(None)
    bx = x
    for slot in range(3):
        rect = pygame.Rect(bx, y, SLOT_SIZE, SLOT_SIZE)
        bid = slot_ids[slot]
        icon = icon_for_building(bid)
        hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
        draw_workplace_slot(surface, rect, icon=icon, font=font, hovered=hovered)
        if interactive:
            if season is not None:
                action = f"{action_prefix}:{slot}:{season.name}"
            else:
                action = f"{action_prefix}:{slot}"
            hits.append((action, rect))
        bx += SLOT_SIZE + SLOT_GAP
    return hits, SLOT_SIZE


def draw_seasonal_workplace_grid(
    surface: pygame.Surface,
    x: int,
    y: int,
    season_slots: dict[str, list[int | None]],
    *,
    icon_for_building: Callable[[int | None], str | None],
    font: pygame.font.Font,
    font_small: pygame.font.Font,
    current_season: Season | None = None,
    mouse_pos: tuple[int, int] | None = None,
) -> tuple[list[tuple[str, pygame.Rect]], int]:
    hits: list[tuple[str, pygame.Rect]] = []
    row_y = y
    for season in SEASON_ORDER:
        label = SEASON_LABELS[season]
        if current_season == season:
            label = f"▸ {label}"
        surface.blit(font_small.render(label, True, COLOUR_TEXT), (x, row_y + 6))
        row = list(season_slots.get(season.name, [None, None, None]))
        row_hits, rh = draw_workplace_slot_row(
            surface,
            x + SEASON_LABEL_W,
            row_y,
            row,
            icon_for_building=icon_for_building,
            font=font,
            mouse_pos=mouse_pos,
            season=season,
        )
        hits.extend(row_hits)
        row_y += rh + 4
    return hits, row_y - y
