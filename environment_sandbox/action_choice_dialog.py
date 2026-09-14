"""Compact multi-choice action popup anchored next to the player."""

from __future__ import annotations

from dataclasses import dataclass

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
    map_view_width,
)

PAD = 8
ROW_H = 26
TITLE_H = 22


@dataclass(frozen=True)
class ActionChoice:
    """One selectable world interaction."""

    id: str
    label: str


class ActionChoiceDialog:
    """Numbered / clickable list of actions, placed beside the player."""

    def __init__(self) -> None:
        self.font = None
        self.font_title = None
        self.choices: tuple[ActionChoice, ...] = ()
        self.choice_id: str | None = None
        self.dismissed = False
        self._open = False
        self._panel = pygame.Rect(0, 0, 0, 0)
        self._row_rects: list[tuple[str, pygame.Rect]] = []

    def _ensure_fonts(self) -> None:
        if self.font is None:
            self.font = pygame.font.SysFont("menlo", 13)
            self.font_title = pygame.font.SysFont("menlo", 12, bold=True)

    @property
    def open(self) -> bool:
        return self._open

    def show(
        self,
        choices: list[ActionChoice] | tuple[ActionChoice, ...],
        *,
        screen_xy: tuple[int, int] | None = None,
    ) -> None:
        self._ensure_fonts()
        self.choices = tuple(choices)
        self.choice_id = None
        self.dismissed = False
        self._open = bool(self.choices)
        if not self._open:
            return
        assert self.font is not None
        width = 168
        for choice in self.choices:
            width = max(width, 28 + self.font.size(f"{choice.label}")[0] + PAD * 2)
        height = TITLE_H + PAD + len(self.choices) * ROW_H + PAD
        map_w = map_view_width()
        if screen_xy is not None:
            prefer_x = screen_xy[0] + 20
            prefer_y = max(MAP_OFFSET_Y + 4, screen_xy[1] - height // 2)
        else:
            prefer_x = 80
            prefer_y = MAP_OFFSET_Y + 40
        if prefer_x + width > map_w - 8:
            prefer_x = max(8, (screen_xy[0] if screen_xy else 80) - width - 16)
        if prefer_y + height > WINDOW_HEIGHT - 8:
            prefer_y = max(MAP_OFFSET_Y + 4, WINDOW_HEIGHT - height - 8)
        self._panel = pygame.Rect(prefer_x, prefer_y, width, height)

    def close(self) -> None:
        self._open = False
        self.choices = ()
        self.choice_id = None
        self._row_rects = []

    def _select(self, choice_id: str | None) -> None:
        self.choice_id = choice_id
        self.dismissed = True
        self._open = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self._open:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE,):
                self._select(None)
                return True
            keys = (
                (pygame.K_1, pygame.K_KP1),
                (pygame.K_2, pygame.K_KP2),
                (pygame.K_3, pygame.K_KP3),
                (pygame.K_4, pygame.K_KP4),
                (pygame.K_5, pygame.K_KP5),
                (pygame.K_6, pygame.K_KP6),
                (pygame.K_7, pygame.K_KP7),
                (pygame.K_8, pygame.K_KP8),
                (pygame.K_9, pygame.K_KP9),
            )
            for index, pair in enumerate(keys):
                if index < len(self.choices) and event.key in pair:
                    self._select(self.choices[index].id)
                    return True
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for choice_id, rect in self._row_rects:
                if rect.collidepoint(event.pos):
                    self._select(choice_id)
                    return True
            if not self._panel.collidepoint(event.pos):
                self._select(None)
                return True
            return True
        return True

    def draw(self, surface: pygame.Surface, mouse_pos: tuple[int, int] | None = None) -> None:
        if not self._open:
            return
        self._ensure_fonts()
        assert self.font is not None and self.font_title is not None
        pygame.draw.rect(surface, COLOUR_MENU_BG, self._panel, border_radius=4)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, self._panel, 1, border_radius=4)
        title = self.font_title.render("Actions", True, COLOUR_TEXT_DIM)
        surface.blit(title, (self._panel.x + PAD, self._panel.y + 4))
        self._row_rects = []
        y = self._panel.y + TITLE_H
        for i, choice in enumerate(self.choices):
            row = pygame.Rect(
                self._panel.x + PAD,
                y,
                self._panel.w - PAD * 2,
                ROW_H - 2,
            )
            hovered = mouse_pos is not None and row.collidepoint(mouse_pos)
            fill = COLOUR_TOOLBAR_BTN_HOVER if hovered else COLOUR_TOOLBAR_BTN
            pygame.draw.rect(surface, fill, row, border_radius=3)
            text = self.font.render(choice.label, True, COLOUR_TEXT)
            surface.blit(text, (row.x + 6, row.y + 5))
            self._row_rects.append((choice.id, row))
            y += ROW_H
