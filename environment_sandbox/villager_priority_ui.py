"""Workplace plan widgets for villager inspect UI.

Each P1–P3 slot is a building pick: production buildings = Workplace work,
storehouse = Labourer (Build + Transport). Empty = —.
"""

from __future__ import annotations

from collections.abc import Callable

import pygame

from entities import PRIORITY_ICONS, PRIORITY_LABELS, WorkPriority, WorkplaceSlot
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
    empty_glyph: str = "+",
) -> None:
    pygame.draw.rect(surface, _slot_bg(hovered=hovered), rect, border_radius=4)
    pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, rect, 1, border_radius=4)
    if icon:
        blit_icon(surface, icon, rect.centerx, rect.centery, min(rect.w, rect.h) - 6)
    else:
        plus = font.render(empty_glyph, True, COLOUR_TEXT_DIM)
        surface.blit(
            plus,
            (
                rect.x + (rect.w - plus.get_width()) // 2,
                rect.y + (rect.h - plus.get_height()) // 2,
            ),
        )


def plan_slot_icon(
    slot: WorkplaceSlot,
    *,
    icon_for_building: Callable[[int | None], str | None],
) -> str | None:
    slot = slot.normalized()
    if slot.kind == WorkPriority.WORKPLACE:
        return icon_for_building(slot.building_id) or PRIORITY_ICONS.get(
            WorkPriority.WORKPLACE
        )
    if slot.kind == WorkPriority.LABOURER:
        if slot.building_id is not None:
            return icon_for_building(slot.building_id) or PRIORITY_ICONS[
                WorkPriority.LABOURER
            ]
        return PRIORITY_ICONS[WorkPriority.LABOURER]
    return None


def plan_slot_tip(
    slot: WorkplaceSlot,
    *,
    icon_for_building: Callable[[int | None], str | None],
    season_name: str | None = None,
    slot_index: int = 0,
) -> str:
    slot = slot.normalized()
    prefix = f"P{slot_index + 1}"
    if season_name:
        prefix = f"{season_name.title()} {prefix}"
    if slot.kind == WorkPriority.NONE:
        return f"{prefix}: empty — click to assign"
    if slot.kind == WorkPriority.LABOURER:
        return f"{prefix}: Labourer (Build + Transport) — click to change"
    icon = icon_for_building(slot.building_id)
    label = (icon or "workplace").replace("_", " ").title()
    return f"{prefix}: {label} — click to change"


def draw_workplace_plan_row(
    surface: pygame.Surface,
    x: int,
    y: int,
    plan: list[WorkplaceSlot],
    *,
    icon_for_building: Callable[[int | None], str | None],
    font: pygame.font.Font,
    mouse_pos: tuple[int, int] | None = None,
    season: Season | None = None,
    interactive: bool = True,
) -> tuple[list[tuple[str, pygame.Rect]], int]:
    hits: list[tuple[str, pygame.Rect]] = []
    row = list(plan)
    while len(row) < 3:
        row.append(WorkplaceSlot())
    bx = x
    for slot_i in range(3):
        rect = pygame.Rect(bx, y, SLOT_SIZE, SLOT_SIZE)
        slot = row[slot_i].normalized()
        icon = plan_slot_icon(slot, icon_for_building=icon_for_building)
        hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
        empty_glyph = "—" if slot.kind == WorkPriority.NONE else "+"
        draw_workplace_slot(
            surface,
            rect,
            icon=icon,
            font=font,
            hovered=hovered,
            empty_glyph=empty_glyph,
        )
        if interactive:
            if season is not None:
                action = f"assign_workplace:{slot_i}:{season.name}"
            else:
                action = f"assign_workplace:{slot_i}"
            hits.append((action, rect))
        bx += SLOT_SIZE + SLOT_GAP
    return hits, SLOT_SIZE


def draw_seasonal_workplace_plan_grid(
    surface: pygame.Surface,
    x: int,
    y: int,
    season_plans: dict[str, list[WorkplaceSlot]],
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
        row = list(season_plans.get(season.name, empty_plan_row()))
        row_hits, rh = draw_workplace_plan_row(
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


def empty_plan_row() -> list[WorkplaceSlot]:
    return [WorkplaceSlot(), WorkplaceSlot(), WorkplaceSlot()]


# --- Legacy helpers kept for any remaining call sites ---


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
    plan = [
        WorkplaceSlot(WorkPriority.WORKPLACE, bid) if bid is not None else WorkplaceSlot()
        for bid in slot_ids
    ]
    return draw_workplace_plan_row(
        surface,
        x,
        y,
        plan,
        icon_for_building=icon_for_building,
        font=font,
        mouse_pos=mouse_pos,
        season=season,
        interactive=interactive,
    )


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
    plans = {
        key: [
            WorkplaceSlot(WorkPriority.WORKPLACE, bid)
            if bid is not None
            else WorkplaceSlot()
            for bid in row
        ]
        for key, row in season_slots.items()
    }
    return draw_seasonal_workplace_plan_grid(
        surface,
        x,
        y,
        plans,
        icon_for_building=icon_for_building,
        font=font,
        font_small=font_small,
        current_season=current_season,
        mouse_pos=mouse_pos,
    )


def draw_priority_slot_row(
    surface: pygame.Surface,
    x: int,
    y: int,
    prios: list[WorkPriority],
    *,
    font: pygame.font.Font,
    mouse_pos: tuple[int, int] | None = None,
    season: Season | None = None,
    interactive: bool = True,
) -> tuple[list[tuple[str, pygame.Rect]], int]:
    hits: list[tuple[str, pygame.Rect]] = []
    while len(prios) < 3:
        prios.append(WorkPriority.NONE)
    bx = x
    for slot in range(3):
        rect = pygame.Rect(bx, y, SLOT_SIZE, SLOT_SIZE)
        mode = prios[slot]
        icon = PRIORITY_ICONS.get(mode) or None
        hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
        draw_workplace_slot(surface, rect, icon=icon, font=font, hovered=hovered)
        if not icon:
            glyph = "—" if mode == WorkPriority.NONE else PRIORITY_LABELS[mode][:1]
            label = font.render(glyph, True, COLOUR_TEXT_DIM)
            surface.blit(
                label,
                (
                    rect.x + (rect.w - label.get_width()) // 2,
                    rect.y + (rect.h - label.get_height()) // 2,
                ),
            )
        if interactive:
            if season is not None:
                action = f"prio_kind:{slot}:{season.name}"
            else:
                action = f"prio_kind:{slot}"
            hits.append((action, rect))
        bx += SLOT_SIZE + SLOT_GAP
    return hits, SLOT_SIZE


def draw_seasonal_priority_grid(
    surface: pygame.Surface,
    x: int,
    y: int,
    season_prios: dict[str, list[WorkPriority]],
    *,
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
        row = list(season_prios.get(season.name, [WorkPriority.NONE] * 3))
        row_hits, rh = draw_priority_slot_row(
            surface,
            x + SEASON_LABEL_W,
            row_y,
            row,
            font=font,
            mouse_pos=mouse_pos,
            season=season,
        )
        hits.extend(row_hits)
        row_y += rh + 4
    return hits, row_y - y
