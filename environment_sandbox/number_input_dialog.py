"""Small modal for typing an integer value."""

from __future__ import annotations

import pygame

from settings import (
    COLOUR_MENU_BG,
    COLOUR_TEXT,
    COLOUR_TEXT_DIM,
    COLOUR_TOOLBAR_BORDER,
    COLOUR_TOOLBAR_BTN,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)


class NumberInputDialog:
    """Modal numeric entry. Blocks map input while open."""

    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 14)
        self.font_small = pygame.font.SysFont("menlo", 12)
        self.open = False
        self.title = ""
        self.text = ""
        self.min_value = 0
        self.max_value = 9999
        self.result: int | None = None
        self.cancelled = False
        self._context: str | None = None
        self._cursor_blink = 0
        self._select_all = False
        self._anchor: pygame.Rect | None = None

    def begin(
        self,
        *,
        title: str,
        initial: int,
        context: str,
        min_value: int = 0,
        max_value: int = 9999,
        anchor: pygame.Rect | None = None,
    ) -> None:
        self.open = True
        self.title = title
        self.text = str(max(min_value, int(initial)))
        self.min_value = int(min_value)
        self.max_value = int(max_value)
        self.result = None
        self.cancelled = False
        self._context = context
        self._cursor_blink = 0
        self._select_all = True
        self._anchor = pygame.Rect(anchor) if anchor is not None else None

    def close(self) -> None:
        self.open = False

    @property
    def context(self) -> str | None:
        return self._context

    def _panel_rect(self) -> pygame.Rect:
        w, h = 280, 140
        if self._anchor is not None:
            x = self._anchor.centerx - w // 2
            y = self._anchor.y - h - 10
            x = max(8, min(x, WINDOW_WIDTH - w - 8))
            y = max(8, min(y, WINDOW_HEIGHT - h - 8))
            if y + h > self._anchor.y - 4:
                y = max(8, self._anchor.y - h - 10)
            return pygame.Rect(x, y, w, h)
        return pygame.Rect((WINDOW_WIDTH - w) // 2, (WINDOW_HEIGHT - h) // 2, w, h)

    def handle_keydown(self, event: pygame.event.Event) -> bool:
        if not self.open:
            return False
        if event.key == pygame.K_ESCAPE:
            self.cancelled = True
            self.close()
            return True
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._confirm()
            return True
        if event.key == pygame.K_BACKSPACE:
            if self._select_all:
                self.text = ""
                self._select_all = False
            else:
                self.text = self.text[:-1]
            return True
        if event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_HOME, pygame.K_END):
            self._select_all = False
            return True
        ch = event.unicode
        if ch and ch.isdigit():
            if self._select_all:
                self.text = ch
                self._select_all = False
            elif len(self.text) < 6:
                self.text += ch
            return True
        return True

    def handle_click(self, pos: tuple[int, int]) -> bool:
        if not self.open:
            return False
        panel = self._panel_rect()
        if not panel.collidepoint(pos):
            self.cancelled = True
            self.close()
            return True
        field = pygame.Rect(panel.x + 20, panel.y + 48, panel.w - 40, 28)
        if field.collidepoint(pos):
            self._select_all = True
            return True
        ok = pygame.Rect(panel.x + 24, panel.bottom - 44, 90, 28)
        cancel = pygame.Rect(panel.x + 126, panel.bottom - 44, 90, 28)
        if ok.collidepoint(pos):
            self._confirm()
        elif cancel.collidepoint(pos):
            self.cancelled = True
            self.close()
        return True

    def _confirm(self) -> None:
        raw = self.text.strip()
        try:
            value = int(raw) if raw else self.min_value
        except ValueError:
            value = self.min_value
        self.result = max(self.min_value, min(self.max_value, value))
        self.close()

    def draw(self, surface: pygame.Surface) -> None:
        if not self.open:
            return
        self._cursor_blink = (self._cursor_blink + 1) % 60
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 90))
        surface.blit(overlay, (0, 0))
        panel = self._panel_rect()
        pygame.draw.rect(surface, COLOUR_MENU_BG, panel, border_radius=8)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, panel, 1, border_radius=8)
        surface.blit(
            self.font.render(self.title, True, COLOUR_TEXT),
            (panel.x + 20, panel.y + 14),
        )
        field = pygame.Rect(panel.x + 20, panel.y + 48, panel.w - 40, 28)
        pygame.draw.rect(surface, (30, 32, 38), field, border_radius=4)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, field, 1, border_radius=4)
        label = self.text or "0"
        text_surf = self.font.render(label, True, COLOUR_TEXT)
        tx, ty = field.x + 8, field.y + 6
        if self._select_all and self.text:
            sel = pygame.Rect(
                tx - 2,
                ty - 1,
                text_surf.get_width() + 4,
                text_surf.get_height() + 2,
            )
            pygame.draw.rect(surface, (70, 110, 160), sel, border_radius=2)
        surface.blit(text_surf, (tx, ty))
        if not self._select_all and self._cursor_blink < 30:
            cx = tx + text_surf.get_width() + 1
            pygame.draw.line(
                surface,
                COLOUR_TEXT,
                (cx, ty + 1),
                (cx, ty + text_surf.get_height() - 1),
                1,
            )
        tip = f"{self.min_value} – {self.max_value}"
        surface.blit(
            self.font_small.render(tip, True, COLOUR_TEXT_DIM),
            (panel.x + 20, panel.y + 84),
        )
        self._draw_button(surface, pygame.Rect(panel.x + 24, panel.bottom - 44, 90, 28), "OK")
        self._draw_button(
            surface, pygame.Rect(panel.x + 126, panel.bottom - 44, 90, 28), "Cancel"
        )

    def _draw_button(
        self, surface: pygame.Surface, rect: pygame.Rect, label: str
    ) -> None:
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BTN, rect, border_radius=4)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, rect, 1, border_radius=4)
        text = self.font_small.render(label, True, COLOUR_TEXT)
        surface.blit(
            text,
            (
                rect.x + (rect.w - text.get_width()) // 2,
                rect.y + (rect.h - text.get_height()) // 2,
            ),
        )
