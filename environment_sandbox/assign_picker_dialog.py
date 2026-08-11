"""Floating picker to assign a villager to a building (or the reverse).

Shown over Management so Assign actions do not switch tabs/views.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Any

import pygame

from entities import BUILDING_LABELS, Building, BuildingKind, Villager
from icons import blit_icon
from settings import (
    COLOUR_MENU_BG,
    COLOUR_TEXT,
    COLOUR_TEXT_DIM,
    COLOUR_TOOLBAR_BORDER,
    COLOUR_TOOLBAR_BTN,
    COLOUR_TOOLBAR_BTN_HOVER,
    MAP_OFFSET_Y,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    map_view_width,
)
from society import housing_beds_of, housing_level_of, is_housing_kind
from villager_roster import draw_portrait

TITLE_BAR_H = 28
PAD = 10
ROW_H = 36
LIST_VIEW_H = 320
SCROLL_STEP = 28

_BUILD_ICON: dict[BuildingKind, str] = {
    BuildingKind.HOME: "storehouse",
    BuildingKind.WORKSTATION: "workstation",
    BuildingKind.FORESTER: "forester",
    BuildingKind.FORAGER: "forager",
    BuildingKind.FARM: "farm",
    BuildingKind.MILL: "mill",
    BuildingKind.KITCHEN: "kitchen",
    BuildingKind.CRAFT_BENCH: "craft_bench",
    BuildingKind.ALCHEMIST: "alchemist",
    BuildingKind.TAILOR: "tailor",
    BuildingKind.MARKET: "market",
    BuildingKind.MASON: "mason",
    BuildingKind.HUNTER: "hunter",
    BuildingKind.FISHER: "fisher",
    BuildingKind.TENT: "tent",
    BuildingKind.HOUSE_SMALL: "house_small",
    BuildingKind.HOUSE: "house",
}


class AssignPickerMode(Enum):
    VILLAGER = auto()  # pick villager → assign to building
    BUILDING = auto()  # pick building → assign villager


class AssignPickerDialog:
    """Movable list popup with close button; pick closes and emits an action."""

    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 14)
        self.font_small = pygame.font.SysFont("menlo", 12)
        self.font_title = pygame.font.SysFont("menlo", 15, bold=True)
        self.mode: AssignPickerMode | None = None
        self.target_building_id: int | None = None
        self.target_villager_id: int | None = None
        self._open = False
        self._panel = pygame.Rect(0, 0, 340, TITLE_BAR_H + LIST_VIEW_H + PAD * 2)
        self._scroll = 0
        self._moving = False
        self._move_offset = (0, 0)
        self._close_rect = pygame.Rect(0, 0, 0, 0)
        self._title_rect = pygame.Rect(0, 0, 0, 0)
        self._list_rect = pygame.Rect(0, 0, 0, 0)
        self._row_hits: list[tuple[pygame.Rect, int]] = []
        self._pending_action: str | None = None
        self._content_h = 0
        self._title = "Assign"
        self.housing_only = False

    @property
    def open(self) -> bool:
        return self._open

    def open_villagers(self, building_id: int, *, title: str | None = None) -> None:
        self.mode = AssignPickerMode.VILLAGER
        self.target_building_id = building_id
        self.target_villager_id = None
        self.housing_only = False
        self._title = title or "Assign villager"
        self._open_common()

    def open_buildings(self, villager_id: int, *, title: str | None = None) -> None:
        self.mode = AssignPickerMode.BUILDING
        self.target_villager_id = villager_id
        self.target_building_id = None
        self.housing_only = False
        self._title = title or "Assign workplace"
        self._open_common()

    def open_housing(self, villager_id: int, *, title: str | None = None) -> None:
        self.mode = AssignPickerMode.BUILDING
        self.target_villager_id = villager_id
        self.target_building_id = None
        self.housing_only = True
        self._title = title or "Assign housing"
        self._open_common()

    def _open_common(self) -> None:
        self._open = True
        self._scroll = 0
        self._moving = False
        self._pending_action = None
        map_w = map_view_width()
        self._panel.w = 360
        self._panel.h = TITLE_BAR_H + LIST_VIEW_H + PAD * 2
        self._panel.center = (map_w // 2, MAP_OFFSET_Y + (WINDOW_HEIGHT - MAP_OFFSET_Y) // 2)
        self._clamp()

    def close(self) -> None:
        self._open = False
        self._moving = False
        self.mode = None
        self.target_building_id = None
        self.target_villager_id = None
        self.housing_only = False
        self._pending_action = None

    def take_action(self) -> str | None:
        action = self._pending_action
        self._pending_action = None
        return action

    def contains(self, pos: tuple[int, int]) -> bool:
        return self.open and self._panel.collidepoint(pos)

    def _clamp(self) -> None:
        self._panel.x = max(4, min(self._panel.x, WINDOW_WIDTH - self._panel.w - 4))
        self._panel.y = max(
            MAP_OFFSET_Y, min(self._panel.y, WINDOW_HEIGHT - self._panel.h - 4)
        )

    def handle_keydown(self, event: pygame.event.Event) -> bool:
        if not self.open:
            return False
        if event.key == pygame.K_ESCAPE:
            self.close()
            return True
        return False

    def handle_mousedown(self, pos: tuple[int, int]) -> bool:
        if not self.open or not self.contains(pos):
            return False
        if self._close_rect.collidepoint(pos):
            self.close()
            return True
        if self._title_rect.collidepoint(pos):
            self._moving = True
            self._move_offset = (pos[0] - self._panel.x, pos[1] - self._panel.y)
            return True
        for rect, item_id in self._row_hits:
            if rect.collidepoint(pos):
                if self.mode == AssignPickerMode.VILLAGER:
                    self._pending_action = f"pick_villager:{item_id}"
                else:
                    self._pending_action = f"pick_building:{item_id}"
                return True
        return True

    def handle_mouseup(self, _pos: tuple[int, int]) -> bool:
        if not self.open:
            return False
        if self._moving:
            self._moving = False
            return True
        return False

    def handle_mousemotion(self, pos: tuple[int, int]) -> bool:
        if not self.open:
            return False
        if self._moving:
            self._panel.x = pos[0] - self._move_offset[0]
            self._panel.y = pos[1] - self._move_offset[1]
            self._clamp()
            return True
        return self.contains(pos)

    def handle_mousewheel(self, dy: int, pos: tuple[int, int] | None = None) -> bool:
        if not self.open:
            return False
        if pos is not None and not self.contains(pos):
            return False
        max_scroll = max(0, self._content_h - self._list_rect.h)
        self._scroll = max(0, min(max_scroll, self._scroll - dy * SCROLL_STEP))
        return True

    def draw(
        self,
        surface: pygame.Surface,
        *,
        villagers: list[Villager],
        buildings: dict[int, Building],
        mouse_pos: tuple[int, int] | None = None,
        job_label: Any = None,
    ) -> None:
        if not self.open or self.mode is None:
            return
        panel = self._panel
        pygame.draw.rect(surface, COLOUR_MENU_BG, panel, border_radius=8)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, panel, 2, border_radius=8)

        self._title_rect = pygame.Rect(panel.x, panel.y, panel.w - 36, TITLE_BAR_H)
        surface.blit(
            self.font_title.render(self._title, True, COLOUR_TEXT),
            (panel.x + PAD, panel.y + 6),
        )
        self._close_rect = pygame.Rect(panel.right - 30, panel.y + 4, 24, 22)
        hovered = mouse_pos is not None and self._close_rect.collidepoint(mouse_pos)
        colour = COLOUR_TOOLBAR_BTN_HOVER if hovered else COLOUR_TOOLBAR_BTN
        pygame.draw.rect(surface, colour, self._close_rect, border_radius=4)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, self._close_rect, 1, border_radius=4)
        x_txt = self.font_small.render("×", True, COLOUR_TEXT)
        surface.blit(
            x_txt,
            (
                self._close_rect.x + (self._close_rect.w - x_txt.get_width()) // 2,
                self._close_rect.y + (self._close_rect.h - x_txt.get_height()) // 2,
            ),
        )

        self._list_rect = pygame.Rect(
            panel.x + PAD,
            panel.y + TITLE_BAR_H + 4,
            panel.w - PAD * 2,
            panel.h - TITLE_BAR_H - PAD - 4,
        )
        pygame.draw.rect(surface, (38, 40, 46), self._list_rect, border_radius=4)
        pygame.draw.rect(
            surface, COLOUR_TOOLBAR_BORDER, self._list_rect, 1, border_radius=4
        )

        self._row_hits = []
        rows: list[tuple[int, str, str, Any]] = []
        if self.mode == AssignPickerMode.VILLAGER:
            for v in villagers:
                if callable(job_label):
                    job = str(job_label(v))
                elif v.assigned_to_home:
                    job = "hauler"
                elif v.building_id and v.building_id in buildings:
                    job = BUILDING_LABELS[buildings[v.building_id].kind]
                else:
                    job = "free"
                name = v.name or f"Villager #{v.id}"
                rows.append((v.id, name, job, ("villager", v.portrait_seed)))
        else:
            for b in buildings.values():
                if b.kind == BuildingKind.FIELD:
                    continue
                if b.kind == BuildingKind.WORKSTATION:
                    continue
                if self.housing_only:
                    if not is_housing_kind(b.kind):
                        continue
                    beds = housing_beds_of(b.kind)
                    used = sum(
                        1
                        for v in villagers
                        if v.housed and v.housing_id == b.id
                    )
                    lvl = housing_level_of(b.kind)
                    label = f"{BUILDING_LABELS[b.kind]} #{b.id}"
                    sub = f"{used}/{beds} beds · lvl {lvl}"
                    icon = _BUILD_ICON.get(b.kind, "construction_site")
                    rows.append((b.id, label, sub, ("building", icon)))
                    continue
                if is_housing_kind(b.kind):
                    continue
                label = f"{BUILDING_LABELS[b.kind]} #{b.id}"
                if b.kind == BuildingKind.HOME:
                    workers = sum(1 for v in villagers if v.assigned_to_home)
                    sub = f"{workers} hauler(s)"
                else:
                    workers = sum(1 for v in villagers if v.building_id == b.id)
                    sub = f"{workers} worker(s)"
                icon = _BUILD_ICON.get(b.kind, "construction_site")
                rows.append((b.id, label, sub, ("building", icon)))

        self._content_h = len(rows) * (ROW_H + 2)
        max_scroll = max(0, self._content_h - self._list_rect.h)
        self._scroll = min(self._scroll, max_scroll)

        old = surface.get_clip()
        surface.set_clip(self._list_rect)
        y = self._list_rect.y + 4 - self._scroll
        for item_id, title, subtitle, visual in rows:
            row = pygame.Rect(
                self._list_rect.x + 4, y, self._list_rect.w - 8, ROW_H
            )
            hovered = mouse_pos is not None and row.collidepoint(mouse_pos)
            if hovered:
                pygame.draw.rect(surface, (55, 70, 55), row, border_radius=3)
            kind, data = visual
            if kind == "villager":
                draw_portrait(surface, row.x + 16, row.centery, int(data), size=22)
            else:
                blit_icon(surface, str(data), row.x + 16, row.centery, 24)
            surface.blit(
                self.font_small.render(title, True, COLOUR_TEXT),
                (row.x + 36, row.y + 4),
            )
            surface.blit(
                self.font_small.render(subtitle, True, COLOUR_TEXT_DIM),
                (row.x + 36, row.y + 18),
            )
            self._row_hits.append((row, item_id))
            y += ROW_H + 2
        surface.set_clip(old)

        if max_scroll > 0:
            track = pygame.Rect(
                self._list_rect.right - 6, self._list_rect.y + 2, 4, self._list_rect.h - 4
            )
            pygame.draw.rect(surface, (40, 42, 48), track, border_radius=2)
            ratio = self._list_rect.h / max(1, self._content_h)
            thumb_h = max(12, int(self._list_rect.h * ratio))
            thumb_y = track.y + int(
                (track.h - thumb_h) * (self._scroll / max(1, max_scroll))
            )
            pygame.draw.rect(
                surface,
                (120, 130, 140),
                pygame.Rect(track.x, thumb_y, track.w, thumb_h),
                border_radius=2,
            )
