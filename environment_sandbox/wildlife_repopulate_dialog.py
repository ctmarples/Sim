"""In-game controls for clearing and reseeding wildlife."""

from __future__ import annotations

import pygame

from settings import (
    COLOUR_MENU_BG, COLOUR_TEXT, COLOUR_TEXT_DIM, COLOUR_TOOLBAR_BORDER,
    COLOUR_TOOLBAR_BTN, COLOUR_TOOLBAR_BTN_HOVER, MAP_OFFSET_Y,
    WINDOW_HEIGHT, WINDOW_WIDTH,
)

SPECIES = (
    ("deer", "Deer"), ("boar", "Boar"), ("rabbit", "Rabbits"),
    ("bee", "Bees"), ("frog", "Frogs"), ("vole", "Voles"),
    ("wolf", "Wolves"), ("fox", "Foxes"), ("owl", "Owls"),
    ("hawk", "Hawks"), ("fish", "Fish"),
)


class WildlifeRepopulateDialog:
    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 12)
        self.title_font = pygame.font.SysFont("menlo", 15, bold=True)
        self.open = False
        self.values = {key: 100 for key, _ in SPECIES}
        self.pending_apply: dict[str, int] | None = None
        self._panel = pygame.Rect(0, 0, 480, 478)
        self._close = pygame.Rect(0, 0, 0, 0)
        self._apply = pygame.Rect(0, 0, 0, 0)
        self._sliders: dict[str, pygame.Rect] = {}
        self._drag_key: str | None = None

    def open_dialog(self) -> None:
        self.open = True
        self.pending_apply = None

    def close(self) -> None:
        self.open = False
        self._drag_key = None

    def _layout(self) -> None:
        self._panel.center = (WINDOW_WIDTH // 2, max(MAP_OFFSET_Y, WINDOW_HEIGHT // 2))
        self._close = pygame.Rect(self._panel.right - 30, self._panel.y + 5, 22, 20)
        self._apply = pygame.Rect(self._panel.x + 95, self._panel.bottom - 48, 290, 30)
        self._sliders = {
            key: pygame.Rect(self._panel.x + 190, self._panel.y + 76 + i * 27, 220, 12)
            for i, (key, _) in enumerate(SPECIES)
        }

    def contains(self, pos: tuple[int, int]) -> bool:
        self._layout()
        return self.open and self._panel.collidepoint(pos)

    def handle_keydown(self, event: pygame.event.Event) -> bool:
        if not self.open:
            return False
        if event.key == pygame.K_ESCAPE:
            self.close()
        return True

    def _set_from_mouse(self, key: str, x: int) -> None:
        rect = self._sliders[key]
        fraction = max(0.0, min(1.0, (x - rect.x) / rect.w))
        self.values[key] = int(round(fraction * 10.0)) * 10

    def handle_mousedown(self, pos: tuple[int, int]) -> bool:
        self._layout()
        if self._close.collidepoint(pos):
            self.close()
            return True
        if self._apply.collidepoint(pos):
            self.pending_apply = dict(self.values)
            self.close()
            return True
        for key, rect in self._sliders.items():
            if rect.inflate(0, 12).collidepoint(pos):
                self._drag_key = key
                self._set_from_mouse(key, pos[0])
                return True
        return self._panel.collidepoint(pos)

    def handle_mouseup(self, pos: tuple[int, int]) -> bool:
        if self._drag_key is not None:
            self._set_from_mouse(self._drag_key, pos[0])
            self._drag_key = None
            return True
        return self.open and self.contains(pos)

    def handle_mousemotion(self, pos: tuple[int, int]) -> None:
        if self._drag_key is not None:
            self._set_from_mouse(self._drag_key, pos[0])

    def draw(self, surface: pygame.Surface, mouse_pos: tuple[int, int]) -> None:
        if not self.open:
            return
        self._layout()
        pygame.draw.rect(surface, COLOUR_MENU_BG, self._panel)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, self._panel, 2)
        surface.blit(self.title_font.render("Repopulate wildlife", True, COLOUR_TEXT),
                     (self._panel.x + 12, self._panel.y + 9))
        surface.blit(self.font.render("Population relative to normal map seeding", True, COLOUR_TEXT_DIM),
                     (self._panel.x + 12, self._panel.y + 39))
        for key, label in SPECIES:
            rect = self._sliders[key]
            surface.blit(self.font.render(label, True, COLOUR_TEXT),
                         (self._panel.x + 28, rect.y - 3))
            pygame.draw.rect(surface, (28, 35, 36), rect, border_radius=6)
            fill = rect.copy()
            fill.w = round(rect.w * self.values[key] / 100)
            pygame.draw.rect(surface, (91, 139, 91), fill, border_radius=6)
            pygame.draw.circle(surface, COLOUR_TEXT, (rect.x + fill.w, rect.centery), 6)
            surface.blit(self.font.render(f"{self.values[key]}%", True, COLOUR_TEXT_DIM),
                         (rect.right + 12, rect.y - 3))
        for rect, label in ((self._close, "×"), (self._apply, "Remove all wildlife and repopulate")):
            colour = COLOUR_TOOLBAR_BTN_HOVER if rect.collidepoint(mouse_pos) else COLOUR_TOOLBAR_BTN
            pygame.draw.rect(surface, colour, rect, border_radius=3)
            pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, rect, 1, border_radius=3)
            text = self.font.render(label, True, COLOUR_TEXT)
            surface.blit(text, (rect.centerx - text.get_width() // 2,
                                rect.centery - text.get_height() // 2))
