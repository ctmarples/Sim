"""File → Sound settings dialog."""

from __future__ import annotations

import pygame

from settings import COLOUR_MENU_BG, COLOUR_TEXT, COLOUR_TEXT_DIM, COLOUR_TOOLBAR_BORDER, WINDOW_HEIGHT, WINDOW_WIDTH


class SoundSettingsDialog:
    def __init__(self) -> None:
        self.open = False
        self.font = pygame.font.SysFont("menlo", 14)
        self.small = pygame.font.SysFont("menlo", 12)
        self._drag: str | None = None

    def toggle(self) -> None:
        self.open = not self.open

    def close(self) -> None:
        self.open = False
        self._drag = None

    def panel(self) -> pygame.Rect:
        return pygame.Rect((WINDOW_WIDTH - 380) // 2, (WINDOW_HEIGHT - 190) // 2, 380, 190)

    def _bar(self, row: int) -> pygame.Rect:
        p = self.panel()
        return pygame.Rect(p.x + 135, p.y + 58 + row * 48, 205, 12)

    def handle_event(self, event: pygame.event.Event, sounds: object) -> bool:
        if not self.open:
            return False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            sounds.save(); self.close(); return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self.panel().collidepoint(event.pos):
                sounds.save(); self.close(); return True
            for row, key in enumerate(("sfx_volume", "ambience_volume")):
                if self._bar(row).inflate(0, 18).collidepoint(event.pos):
                    self._drag = key
                    self._set(event.pos[0], sounds)
            return True
        if event.type == pygame.MOUSEMOTION and self._drag:
            self._set(event.pos[0], sounds); return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._drag = None; sounds.save(); return True
        return True

    def _set(self, x: int, sounds: object) -> None:
        row = 0 if self._drag == "sfx_volume" else 1
        bar = self._bar(row)
        setattr(sounds, self._drag, max(0.0, min(1.0, (x - bar.x) / bar.w)))

    def draw(self, surface: pygame.Surface, sounds: object) -> None:
        if not self.open:
            return
        shade = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA); shade.fill((0, 0, 0, 120)); surface.blit(shade, (0, 0))
        p = self.panel(); pygame.draw.rect(surface, COLOUR_MENU_BG, p, border_radius=7); pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, p, 2, border_radius=7)
        surface.blit(self.font.render("Sound settings", True, COLOUR_TEXT), (p.x + 20, p.y + 16))
        for row, (label, value) in enumerate((("Sound effects", sounds.sfx_volume), ("World ambience", sounds.ambience_volume))):
            bar = self._bar(row); surface.blit(self.small.render(label, True, COLOUR_TEXT_DIM), (p.x + 20, bar.y - 3)); pygame.draw.rect(surface, (40, 45, 44), bar); pygame.draw.rect(surface, (105, 155, 120), (bar.x, bar.y, int(bar.w * value), bar.h)); pygame.draw.circle(surface, COLOUR_TEXT, (bar.x + int(bar.w * value), bar.centery), 7)
            surface.blit(self.small.render(f"{round(value * 100):d}%", True, COLOUR_TEXT), (bar.right - 35, bar.y + 17))
