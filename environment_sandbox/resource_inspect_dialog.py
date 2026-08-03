"""Floating popup for map resources (wood/rock/food piles — not seeds)."""

from __future__ import annotations

import pygame

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

TITLE_BAR_H = 28
PAD = 12


class ResourceInspectDialog:
    """Small movable info window for a clicked map resource."""

    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 14)
        self.font_small = pygame.font.SysFont("menlo", 12)
        self.font_title = pygame.font.SysFont("menlo", 15, bold=True)
        self.title: str = ""
        self.quantity: int = 0
        self.unit: str = ""
        self.detail: str = ""
        self.cell: tuple[int, int] | None = None
        self._open = False
        self._panel_x = 80
        self._panel_y = MAP_OFFSET_Y + 40
        self._panel_w = 220
        self._panel_h = 110
        self._moving = False
        self._move_offset = (0, 0)
        self._close_rect = pygame.Rect(0, 0, 0, 0)
        self._title_rect = pygame.Rect(0, 0, 0, 0)

    @property
    def open(self) -> bool:
        return self._open

    def open_for(
        self,
        *,
        title: str,
        quantity: int,
        unit: str,
        detail: str = "",
        cell: tuple[int, int] | None = None,
        screen_xy: tuple[int, int] | None = None,
    ) -> None:
        self.title = title
        self.quantity = int(quantity)
        self.unit = unit
        self.detail = detail
        self.cell = cell
        self._open = True
        self._moving = False
        self._panel_w = 220
        self._panel_h = 110 if not detail else 128
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
        self._open = False
        self._moving = False
        self.cell = None

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

    def draw(self, surface: pygame.Surface, mouse_pos: tuple[int, int] | None = None) -> None:
        if not self.open:
            return
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
            self.font_title.render(self.title, True, COLOUR_TEXT),
            (panel.x + 10, panel.y + 6),
        )
        self._close_rect = pygame.Rect(panel.right - 28, panel.y + 4, 22, 20)
        hover = mouse_pos is not None and self._close_rect.collidepoint(mouse_pos)
        pygame.draw.rect(
            surface,
            COLOUR_TOOLBAR_BTN_HOVER if hover else COLOUR_TOOLBAR_BTN,
            self._close_rect,
            border_radius=3,
        )
        x_txt = self.font_small.render("×", True, COLOUR_TEXT)
        surface.blit(
            x_txt,
            (
                self._close_rect.centerx - x_txt.get_width() // 2,
                self._close_rect.centery - x_txt.get_height() // 2 - 1,
            ),
        )

        y = panel.y + TITLE_BAR_H + PAD
        qty_line = f"Quantity: {self.quantity}"
        if self.unit:
            qty_line += f" {self.unit}"
        surface.blit(self.font.render(qty_line, True, COLOUR_TEXT), (panel.x + PAD, y))
        y += 22
        if self.cell is not None:
            surface.blit(
                self.font_small.render(
                    f"Cell ({self.cell[0]}, {self.cell[1]})", True, COLOUR_TEXT_DIM
                ),
                (panel.x + PAD, y),
            )
            y += 18
        if self.detail:
            surface.blit(
                self.font_small.render(self.detail, True, COLOUR_TEXT_DIM),
                (panel.x + PAD, y),
            )
