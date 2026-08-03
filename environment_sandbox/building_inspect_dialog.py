"""Floating inspection window for workplace buildings (not Fields)."""

from __future__ import annotations

import pygame

from entities import (
    BUILDING_LABELS,
    WORK_MODE_LABELS,
    Building,
    BuildingKind,
    Villager,
)
from resources import format_grouped_counts
from settings import (
    COLOUR_MENU_BG,
    COLOUR_SELECTED_ENTITY,
    COLOUR_TEXT,
    COLOUR_TEXT_DIM,
    COLOUR_TOOLBAR_BORDER,
    COLOUR_TOOLBAR_BTN,
    COLOUR_TOOLBAR_BTN_ACTIVE,
    COLOUR_TOOLBAR_BTN_HOVER,
    MAP_OFFSET_Y,
    MAX_VILLAGERS,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    map_view_width,
)

TITLE_BAR_H = 28
PAD = 12
BTN_H = 24
ROW_H = 22
SECTION_GAP = 10


class BuildingInspectDialog:
    """Movable floating inspector: options, workers, local storage."""

    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 14)
        self.font_small = pygame.font.SysFont("menlo", 12)
        self.font_title = pygame.font.SysFont("menlo", 15, bold=True)
        self.building_id: int | None = None
        self._buttons: list[tuple[str, pygame.Rect]] = []
        self._worker_hits: list[tuple[pygame.Rect, int]] = []
        self._pending_action: str | None = None
        self._panel_x = 80
        self._panel_y = MAP_OFFSET_Y + 40
        self._panel_w = 300
        self._panel_h = 320
        self._moving = False
        self._move_offset = (0, 0)
        self._close_rect = pygame.Rect(0, 0, 0, 0)
        self._title_rect = pygame.Rect(0, 0, 0, 0)
        self._hover_worker: int | None = None

    @property
    def open(self) -> bool:
        return self.building_id is not None

    def open_for(
        self,
        building: Building,
        *,
        screen_xy: tuple[int, int] | None = None,
    ) -> None:
        if building.kind == BuildingKind.FIELD:
            return
        self.building_id = building.id
        self._pending_action = None
        self._moving = False
        self._hover_worker = None
        self._layout()
        map_w = map_view_width()
        if screen_xy is not None:
            prefer_x = screen_xy[0] + 24
            prefer_y = max(MAP_OFFSET_Y, screen_xy[1])
        else:
            prefer_x = 80
            prefer_y = MAP_OFFSET_Y + 40
        if prefer_x + self._panel_w > map_w - 8:
            prefer_x = max(8, (screen_xy[0] if screen_xy else 80) - self._panel_w - 16)
        self._panel_x = prefer_x
        self._panel_y = prefer_y
        self._clamp_panel()

    def close(self) -> None:
        self.building_id = None
        self._moving = False
        self._pending_action = None
        self._hover_worker = None

    def take_action(self) -> str | None:
        action = self._pending_action
        self._pending_action = None
        return action

    def panel_rect(self) -> pygame.Rect:
        return pygame.Rect(self._panel_x, self._panel_y, self._panel_w, self._panel_h)

    def contains(self, pos: tuple[int, int]) -> bool:
        return self.open and self.panel_rect().collidepoint(pos)

    def _layout(self) -> None:
        self._panel_w = 300
        self._panel_h = TITLE_BAR_H + PAD + 120 + 8 * ROW_H + 100

    def _clamp_panel(self) -> None:
        self._panel_x = max(4, min(self._panel_x, WINDOW_WIDTH - self._panel_w - 4))
        self._panel_y = max(
            MAP_OFFSET_Y, min(self._panel_y, WINDOW_HEIGHT - self._panel_h - 4)
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
            self._move_offset = (pos[0] - self._panel_x, pos[1] - self._panel_y)
            return True
        for action, rect in self._buttons:
            if rect.collidepoint(pos):
                self._pending_action = action
                return True
        for rect, vid in self._worker_hits:
            if rect.collidepoint(pos):
                self._pending_action = f"select_worker:{vid}"
                return True
        return True

    def handle_mousemotion(self, pos: tuple[int, int]) -> bool:
        if not self.open:
            return False
        if self._moving:
            self._panel_x = pos[0] - self._move_offset[0]
            self._panel_y = pos[1] - self._move_offset[1]
            self._clamp_panel()
            return True
        self._hover_worker = None
        if self.contains(pos):
            for rect, vid in self._worker_hits:
                if rect.collidepoint(pos):
                    self._hover_worker = vid
                    break
        return self.contains(pos)

    def handle_mouseup(self, pos: tuple[int, int]) -> bool:
        if not self.open:
            return False
        if self._moving:
            self._moving = False
            self._clamp_panel()
            return True
        return self.contains(pos)

    def _draw_button(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        label: str,
        *,
        active: bool = False,
        hovered: bool = False,
    ) -> None:
        if active:
            colour = COLOUR_TOOLBAR_BTN_ACTIVE
        elif hovered:
            colour = COLOUR_TOOLBAR_BTN_HOVER
        else:
            colour = COLOUR_TOOLBAR_BTN
        pygame.draw.rect(surface, colour, rect, border_radius=4)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, rect, 1, border_radius=4)
        text = self.font_small.render(label, True, COLOUR_TEXT)
        surface.blit(
            text,
            (
                rect.x + (rect.w - text.get_width()) // 2,
                rect.y + (rect.h - text.get_height()) // 2,
            ),
        )

    def _worker_label(self, villager: Villager) -> str:
        if villager.seeking_food:
            state = "EAT"
        else:
            state = villager.state.name[:4]
        return f"#{villager.id} {state}"

    def draw(
        self,
        surface: pygame.Surface,
        building: Building | None,
        workers: list[Villager],
        *,
        selected_villager_id: int | None = None,
        mouse_pos: tuple[int, int] | None = None,
        storage_amounts: dict[str, int] | None = None,
        hired_count: int = 0,
    ) -> None:
        if not self.open or building is None or building.kind == BuildingKind.FIELD:
            return
        if building.id != self.building_id:
            return

        storage_keys = building.depositable_keys()
        if storage_keys:
            amounts = storage_amounts or {
                k: int(getattr(building, k, 0)) for k in storage_keys
            }
            storage_lines = format_grouped_counts(
                {k: int(amounts.get(k, 0)) for k in storage_keys},
                skip_zero=True,
            )
            if not storage_lines:
                storage_lines = ["(empty)"]
            stored_total = sum(int(amounts.get(k, 0)) for k in storage_keys)
            capacity_label = (
                f"{stored_total}"
                if building.kind == BuildingKind.HOME
                else f"{building.stored_total}/{building.capacity}"
            )
        else:
            storage_lines = ["—"]
            capacity_label = "—"

        n_workers = max(1, len(workers))
        options_h = BTN_H + 8
        if building.kind == BuildingKind.WORKSTATION:
            options_h = BTN_H + 8
        elif building.supported_work_modes():
            options_h = BTN_H * 2 + 12
        body_h = (
            PAD
            + 18
            + options_h
            + SECTION_GAP
            + 18
            + n_workers * (ROW_H + 2)
            + SECTION_GAP
            + 18
            + len(storage_lines) * 16
            + 24
            + PAD
        )
        self._panel_h = TITLE_BAR_H + body_h
        self._clamp_panel()
        panel = self.panel_rect()

        shadow = panel.move(3, 4)
        sh = pygame.Surface((shadow.w, shadow.h), pygame.SRCALPHA)
        sh.fill((0, 0, 0, 70))
        surface.blit(sh, shadow.topleft)

        pygame.draw.rect(surface, COLOUR_MENU_BG, panel, border_radius=6)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, panel, 2, border_radius=6)

        title_bar = pygame.Rect(panel.x, panel.y, panel.w, TITLE_BAR_H)
        pygame.draw.rect(
            surface,
            (48, 50, 58),
            title_bar,
            border_top_left_radius=6,
            border_top_right_radius=6,
        )
        self._title_rect = pygame.Rect(panel.x, panel.y, panel.w - 32, TITLE_BAR_H)
        title = f"{BUILDING_LABELS[building.kind]} #{building.id}"
        surface.blit(
            self.font_title.render(title, True, COLOUR_TEXT),
            (panel.x + 10, panel.y + 6),
        )
        self._close_rect = pygame.Rect(panel.right - 28, panel.y + 4, 22, 20)
        close_hov = mouse_pos is not None and self._close_rect.collidepoint(mouse_pos)
        self._draw_button(surface, self._close_rect, "×", hovered=close_hov)

        self._buttons = []
        self._worker_hits = []
        x = panel.x + PAD
        y = panel.y + TITLE_BAR_H + PAD
        inner_w = panel.w - PAD * 2

        # --- Options ---
        surface.blit(self.font.render("Options", True, COLOUR_TEXT), (x, y))
        y += 18
        bx = x
        if building.kind == BuildingKind.WORKSTATION:
            label = f"Hire ({hired_count}/{MAX_VILLAGERS})"
            w = max(120, 12 + self.font_small.size(label)[0])
            rect = pygame.Rect(bx, y, w, BTN_H)
            hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
            self._draw_button(surface, rect, label, hovered=hovered)
            self._buttons.append(("hire_villager", rect))
            y += BTN_H + 6
        elif building.kind == BuildingKind.HOME:
            for label, action in (
                ("Assign hauler +", "assign_villager"),
                ("Unassign −", "unassign_villager"),
            ):
                w = max(90, 10 + self.font_small.size(label)[0])
                rect = pygame.Rect(bx, y, w, BTN_H)
                hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
                self._draw_button(surface, rect, label, hovered=hovered)
                self._buttons.append((action, rect))
                bx += w + 4
            y += BTN_H + 6
        else:
            for mode in building.supported_work_modes():
                label = WORK_MODE_LABELS[mode]
                w = max(52, 10 + self.font_small.size(label)[0])
                if bx + w > x + inner_w and bx > x:
                    bx = x
                    y += BTN_H + 4
                rect = pygame.Rect(bx, y, w, BTN_H)
                active = building.work_mode == mode
                hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
                self._draw_button(surface, rect, label, active=active, hovered=hovered)
                self._buttons.append((f"mode_{mode.name}", rect))
                bx += w + 4
            if building.kind != BuildingKind.FARM:
                clear_w = max(48, 10 + self.font_small.size("Clear")[0])
                if bx + clear_w > x + inner_w and bx > x:
                    bx = x
                    y += BTN_H + 4
                rect = pygame.Rect(bx, y, clear_w, BTN_H)
                hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
                self._draw_button(surface, rect, "Clear", hovered=hovered)
                self._buttons.append(("task_clear", rect))
            y += BTN_H + 6
            bx = x
            for label, action in (("Assign +", "assign_villager"), ("Unassign −", "unassign_villager")):
                w = max(72, 10 + self.font_small.size(label)[0])
                rect = pygame.Rect(bx, y, w, BTN_H)
                hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
                self._draw_button(surface, rect, label, hovered=hovered)
                self._buttons.append((action, rect))
                bx += w + 4
            y += BTN_H + SECTION_GAP

        if building.kind in (BuildingKind.HOME, BuildingKind.WORKSTATION):
            y += SECTION_GAP // 2

        # --- Workers / haulers ---
        workers_title = (
            "Haulers"
            if building.kind == BuildingKind.HOME
            else "Workers"
            if building.kind != BuildingKind.WORKSTATION
            else "Note"
        )
        surface.blit(self.font.render(workers_title, True, COLOUR_TEXT), (x, y))
        y += 18
        if building.kind == BuildingKind.WORKSTATION:
            surface.blit(
                self.font_small.render(
                    "Hire villagers here. Assign them to workplaces.",
                    True,
                    COLOUR_TEXT_DIM,
                ),
                (x, y),
            )
            y += ROW_H
        elif not workers:
            surface.blit(
                self.font_small.render("None assigned", True, COLOUR_TEXT_DIM),
                (x, y),
            )
            y += ROW_H
        else:
            for villager in workers:
                row = pygame.Rect(x - 2, y - 1, inner_w + 4, ROW_H)
                selected = selected_villager_id == villager.id
                hovered = self._hover_worker == villager.id or (
                    mouse_pos is not None and row.collidepoint(mouse_pos)
                )
                if selected:
                    pygame.draw.rect(surface, (55, 70, 55), row, border_radius=3)
                    pygame.draw.rect(
                        surface, COLOUR_SELECTED_ENTITY, row, 1, border_radius=3
                    )
                elif hovered:
                    pygame.draw.rect(surface, (45, 48, 55), row, border_radius=3)
                label = self._worker_label(villager)
                colour = COLOUR_TEXT if selected or hovered else COLOUR_TEXT_DIM
                surface.blit(
                    self.font_small.render(label, True, colour),
                    (x + 2, y + 3),
                )
                bar_x = x + 2 + self.font_small.size(label)[0] + 8
                bar_y = y + (ROW_H - 7) // 2
                bar_w = 36
                pygame.draw.rect(
                    surface, (40, 40, 40), pygame.Rect(bar_x, bar_y, bar_w, 7), border_radius=2
                )
                fill = max(0, min(1.0, villager.satiation))
                fill_c = (
                    (70, 160, 80)
                    if fill > 0.5
                    else (180, 140, 50)
                    if fill > 0.25
                    else (180, 70, 60)
                )
                pygame.draw.rect(
                    surface,
                    fill_c,
                    pygame.Rect(bar_x, bar_y, int(bar_w * fill), 7),
                    border_radius=2,
                )
                tip = "Seeking food" if villager.seeking_food else villager.state.name
                surface.blit(
                    self.font_small.render(tip[:8], True, COLOUR_TEXT_DIM),
                    (bar_x + bar_w + 6, y + 3),
                )
                self._worker_hits.append((row, villager.id))
                y += ROW_H + 2

        y += SECTION_GAP
        # --- Storage ---
        surface.blit(self.font.render("Storage", True, COLOUR_TEXT), (x, y))
        y += 18
        surface.blit(
            self.font_small.render(capacity_label, True, COLOUR_TEXT_DIM),
            (x, y),
        )
        y += 16
        for line in storage_lines:
            text = line
            while self.font_small.size(text)[0] > inner_w and len(text) > 4:
                text = text[:-2] + "…"
            surface.blit(self.font_small.render(text, True, COLOUR_TEXT), (x, y))
            y += 16
