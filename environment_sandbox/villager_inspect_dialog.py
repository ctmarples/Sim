"""Floating inspection window for a selected villager."""

from __future__ import annotations

import pygame

from entities import (
    PRIORITY_LABELS,
    RATION_LABELS,
    RationMode,
    WorkPriority,
    Villager,
)
from resources import format_grouped_counts, resource_label
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
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    map_view_width,
)

TITLE_BAR_H = 28
PAD = 12
BTN_H = 24
ROW_H = 22
SECTION_GAP = 10


class VillagerInspectDialog:
    """Movable floating inspector: status, work options, carried items."""

    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 14)
        self.font_small = pygame.font.SysFont("menlo", 12)
        self.font_title = pygame.font.SysFont("menlo", 15, bold=True)
        self.villager_id: int | None = None
        self._buttons: list[tuple[str, pygame.Rect]] = []
        self._pending_action: str | None = None
        self._panel_x = 80
        self._panel_y = MAP_OFFSET_Y + 40
        self._panel_w = 300
        self._panel_h = 360
        self._moving = False
        self._move_offset = (0, 0)
        self._close_rect = pygame.Rect(0, 0, 0, 0)
        self._title_rect = pygame.Rect(0, 0, 0, 0)

    @property
    def open(self) -> bool:
        return self.villager_id is not None

    def open_for(
        self,
        villager: Villager,
        *,
        screen_xy: tuple[int, int] | None = None,
    ) -> None:
        self.villager_id = villager.id
        self._pending_action = None
        self._moving = False
        self._panel_w = 300
        self._panel_h = 360
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
        self.villager_id = None
        self._moving = False
        self._pending_action = None

    def take_action(self) -> str | None:
        action = self._pending_action
        self._pending_action = None
        return action

    def panel_rect(self) -> pygame.Rect:
        return pygame.Rect(self._panel_x, self._panel_y, self._panel_w, self._panel_h)

    def contains(self, pos: tuple[int, int]) -> bool:
        return self.open and self.panel_rect().collidepoint(pos)

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
        return True

    def handle_mousemotion(self, pos: tuple[int, int]) -> bool:
        if not self.open:
            return False
        if self._moving:
            self._panel_x = pos[0] - self._move_offset[0]
            self._panel_y = pos[1] - self._move_offset[1]
            self._clamp_panel()
            return True
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

    def draw(
        self,
        surface: pygame.Surface,
        villager: Villager | None,
        *,
        assignment_label: str = "—",
        mouse_pos: tuple[int, int] | None = None,
    ) -> None:
        if not self.open or villager is None:
            return
        if villager.id != self.villager_id:
            return

        cargo_lines = format_grouped_counts(
            {
                k: int(getattr(villager.inventory, k, 0))
                for k in (
                    "wood",
                    "hardwood",
                    "rock",
                    "meat",
                    "fish",
                    "berries",
                    "mushrooms",
                    "oak_saplings",
                    "maple_saplings",
                    "pine_saplings",
                    "cedar_saplings",
                    "wheat",
                    "flax",
                    "sage",
                    "hemp",
                    "rye",
                    "onion",
                    "cabbage",
                    "carrot",
                    "berry_seeds",
                    "wheat_seeds",
                    "flax_seeds",
                    "sage_seeds",
                    "hemp_seeds",
                    "rye_seeds",
                    "onion_seeds",
                    "cabbage_seeds",
                    "carrot_seeds",
                )
            },
            skip_zero=True,
        )
        if not cargo_lines:
            cargo_lines = ["(empty)"]

        body_h = (
            PAD
            + 18
            + 4 * 16
            + SECTION_GAP
            + 18
            + BTN_H
            + 6
            + 3 * (BTN_H + 4)
            + SECTION_GAP
            + 18
            + BTN_H
            + 6
            + SECTION_GAP
            + 18
            + len(cargo_lines) * 16
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
        surface.blit(
            self.font_title.render(f"Villager #{villager.id}", True, COLOUR_TEXT),
            (panel.x + 10, panel.y + 6),
        )
        self._close_rect = pygame.Rect(panel.right - 28, panel.y + 4, 22, 20)
        close_hov = mouse_pos is not None and self._close_rect.collidepoint(mouse_pos)
        self._draw_button(surface, self._close_rect, "×", hovered=close_hov)

        self._buttons = []
        x = panel.x + PAD
        y = panel.y + TITLE_BAR_H + PAD
        inner_w = panel.w - PAD * 2

        # --- Status ---
        surface.blit(self.font.render("Status", True, COLOUR_TEXT), (x, y))
        y += 18
        state = (
            "Seeking food"
            if villager.seeking_food
            else villager.state.name.replace("_", " ").title()
        )
        last = (
            resource_label(villager.last_food)
            if villager.last_food
            else "—"
        )
        for line in (
            f"State: {state}",
            f"Workplace: {assignment_label}",
            f"Satiation: {int(round(villager.satiation * 100))}%",
            f"Last food: {last}",
        ):
            surface.blit(self.font_small.render(line, True, COLOUR_TEXT_DIM), (x, y))
            y += 16

        y += SECTION_GAP
        # --- Work options ---
        surface.blit(self.font.render("Work", True, COLOUR_TEXT), (x, y))
        y += 18

        # Ration
        bx = x
        for mode in (RationMode.HALF, RationMode.NORMAL, RationMode.DOUBLE):
            label = RATION_LABELS[mode]
            w = max(40, 10 + self.font_small.size(label)[0])
            rect = pygame.Rect(bx, y, w, BTN_H)
            active = villager.ration_mode == mode
            hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
            self._draw_button(surface, rect, label, active=active, hovered=hovered)
            self._buttons.append((f"ration_{mode.name}", rect))
            bx += w + 4
        surface.blit(
            self.font_small.render("Ration", True, COLOUR_TEXT_DIM),
            (bx + 4, y + 4),
        )
        y += BTN_H + 6

        # Priority slots
        while len(villager.priorities) < 3:
            villager.priorities.append(WorkPriority.NONE)
        for slot in range(3):
            bx = x
            surface.blit(
                self.font_small.render(f"P{slot + 1}", True, COLOUR_TEXT_DIM),
                (bx, y + 4),
            )
            bx += 22
            for prio in (
                WorkPriority.BUILD,
                WorkPriority.TRANSPORT,
                WorkPriority.WORKPLACE,
                WorkPriority.NONE,
            ):
                label = PRIORITY_LABELS[prio][:4]
                w = max(48, 8 + self.font_small.size(label)[0])
                if bx + w > x + inner_w and bx > x + 22:
                    break
                rect = pygame.Rect(bx, y, w, BTN_H)
                active = villager.priorities[slot] == prio
                hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
                self._draw_button(surface, rect, label, active=active, hovered=hovered)
                self._buttons.append((f"prio:{slot}:{prio.name}", rect))
                bx += w + 3
            y += BTN_H + 4

        y += SECTION_GAP // 2
        # Assign / unassign
        bx = x
        for label, action in (
            ("Assign workplace", "assign_workplace"),
            ("Unassign", "unassign"),
        ):
            w = max(100, 10 + self.font_small.size(label)[0])
            rect = pygame.Rect(bx, y, w, BTN_H)
            hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
            self._draw_button(surface, rect, label, hovered=hovered)
            self._buttons.append((action, rect))
            bx += w + 4
        y += BTN_H + SECTION_GAP

        # --- Carried ---
        surface.blit(self.font.render("Carried", True, COLOUR_TEXT), (x, y))
        y += 18
        for line in cargo_lines:
            surface.blit(self.font_small.render(line, True, COLOUR_TEXT_DIM), (x, y))
            y += 16

        # Selection accent
        pygame.draw.rect(surface, COLOUR_SELECTED_ENTITY, panel, 1, border_radius=6)
