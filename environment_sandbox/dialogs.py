"""In-game modal dialogs for save (filename) and load (file list)."""

from __future__ import annotations

from pathlib import Path

import pygame

from save_load import list_save_files, saves_dir
from settings import (
    COLOUR_MENU_BG,
    COLOUR_TEXT,
    COLOUR_TEXT_DIM,
    COLOUR_TOOLBAR_BORDER,
    COLOUR_TOOLBAR_BTN,
    COLOUR_TOOLBAR_BTN_ACTIVE,
    COLOUR_TOOLBAR_BTN_HOVER,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)

LIST_ROW_H = 22
LIST_VIEW_H = 140
SCROLL_STEP = LIST_ROW_H


class FileDialog:
    """Modal Save / Load overlay. Blocks map input while open."""

    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 14)
        self.font_small = pygame.font.SysFont("menlo", 12)
        self.mode: str | None = None  # "save" | "load"
        self.save_name = "savegame"
        self.load_files: list[str] = []
        self.load_index = 0
        self.load_scroll = 0
        self._cursor_blink = 0
        self.result_path: Path | None = None
        self.cancelled = False

    @property
    def open(self) -> bool:
        return self.mode is not None

    def open_save(self, initial: str = "savegame") -> None:
        self.mode = "save"
        self.save_name = initial.removesuffix(".json")
        self.result_path = None
        self.cancelled = False
        self._cursor_blink = 0

    def open_load(self) -> None:
        self.mode = "load"
        self.load_files = list_save_files()
        self.load_index = 0
        self.load_scroll = 0
        self.result_path = None
        self.cancelled = False

    def close(self) -> None:
        self.mode = None

    def _panel_rect(self) -> pygame.Rect:
        w, h = 420, 280
        return pygame.Rect((WINDOW_WIDTH - w) // 2, (WINDOW_HEIGHT - h) // 2, w, h)

    def _list_rect(self, panel: pygame.Rect) -> pygame.Rect:
        return pygame.Rect(panel.x + 20, panel.y + 72, panel.w - 40, LIST_VIEW_H)

    def _list_content_h(self) -> int:
        if not self.load_files:
            return LIST_VIEW_H
        return max(LIST_VIEW_H, len(self.load_files) * LIST_ROW_H + 8)

    def _clamp_scroll(self) -> None:
        max_scroll = max(0, self._list_content_h() - LIST_VIEW_H)
        self.load_scroll = max(0, min(int(self.load_scroll), max_scroll))

    def _ensure_index_visible(self) -> None:
        if not self.load_files:
            self.load_scroll = 0
            return
        row_y = 4 + self.load_index * LIST_ROW_H
        if row_y < self.load_scroll:
            self.load_scroll = row_y
        elif row_y + LIST_ROW_H > self.load_scroll + LIST_VIEW_H:
            self.load_scroll = row_y + LIST_ROW_H - LIST_VIEW_H
        self._clamp_scroll()

    def handle_keydown(self, event: pygame.event.Event) -> bool:
        """Return True if the event was consumed."""
        if not self.open:
            return False
        if event.key == pygame.K_ESCAPE:
            self.cancelled = True
            self.close()
            return True
        if self.mode == "save":
            return self._save_keydown(event)
        return self._load_keydown(event)

    def handle_mousewheel(self, dy: int) -> bool:
        """Scroll the load list. Returns True if consumed."""
        if not self.open or self.mode != "load" or not self.load_files:
            return self.open
        self.load_scroll -= dy * SCROLL_STEP
        self._clamp_scroll()
        return True

    def _save_keydown(self, event: pygame.event.Event) -> bool:
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._confirm_save()
            return True
        if event.key == pygame.K_BACKSPACE:
            self.save_name = self.save_name[:-1]
            return True
        ch = event.unicode
        if ch and ch.isprintable() and ch not in ('/', '\\', ':', '*', '?', '"', '<', '>', '|'):
            if len(self.save_name) < 40:
                self.save_name += ch
            return True
        return True

    def _load_keydown(self, event: pygame.event.Event) -> bool:
        if not self.load_files:
            return True
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._confirm_load()
            return True
        if event.key in (pygame.K_UP, pygame.K_w):
            self.load_index = max(0, self.load_index - 1)
            self._ensure_index_visible()
            return True
        if event.key in (pygame.K_DOWN, pygame.K_s):
            self.load_index = min(len(self.load_files) - 1, self.load_index + 1)
            self._ensure_index_visible()
            return True
        if event.key == pygame.K_PAGEUP:
            self.load_index = max(0, self.load_index - 5)
            self._ensure_index_visible()
            return True
        if event.key == pygame.K_PAGEDOWN:
            self.load_index = min(len(self.load_files) - 1, self.load_index + 5)
            self._ensure_index_visible()
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

        if self.mode == "save":
            save_btn = pygame.Rect(panel.x + 24, panel.bottom - 48, 100, 28)
            cancel_btn = pygame.Rect(panel.x + 136, panel.bottom - 48, 100, 28)
            if save_btn.collidepoint(pos):
                self._confirm_save()
            elif cancel_btn.collidepoint(pos):
                self.cancelled = True
                self.close()
            return True

        list_rect = self._list_rect(panel)
        if list_rect.collidepoint(pos) and self.load_files:
            local_y = pos[1] - list_rect.y + self.load_scroll - 4
            if local_y >= 0:
                idx = local_y // LIST_ROW_H
                if 0 <= idx < len(self.load_files):
                    self.load_index = idx
        load_btn = pygame.Rect(panel.x + 24, panel.bottom - 48, 100, 28)
        cancel_btn = pygame.Rect(panel.x + 136, panel.bottom - 48, 100, 28)
        if load_btn.collidepoint(pos) and self.load_files:
            self._confirm_load()
        elif cancel_btn.collidepoint(pos):
            self.cancelled = True
            self.close()
        return True

    def _confirm_save(self) -> None:
        name = self.save_name.strip() or "savegame"
        if not name.endswith(".json"):
            name += ".json"
        self.result_path = saves_dir() / name
        self.close()

    def _confirm_load(self) -> None:
        if not self.load_files:
            self.cancelled = True
            self.close()
            return
        self.result_path = saves_dir() / self.load_files[self.load_index]
        self.close()

    def draw(self, surface: pygame.Surface) -> None:
        if not self.open:
            return
        self._cursor_blink = (self._cursor_blink + 1) % 60
        shade = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 140))
        surface.blit(shade, (0, 0))

        panel = self._panel_rect()
        pygame.draw.rect(surface, COLOUR_MENU_BG, panel, border_radius=6)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, panel, 2, border_radius=6)

        title = "Save game" if self.mode == "save" else "Load game"
        surface.blit(self.font.render(title, True, COLOUR_TEXT), (panel.x + 20, panel.y + 16))

        if self.mode == "save":
            self._draw_save(surface, panel)
        else:
            self._draw_load(surface, panel)

    def _draw_button(
        self, surface: pygame.Surface, rect: pygame.Rect, label: str, active: bool = False
    ) -> None:
        mouse = pygame.mouse.get_pos()
        colour = COLOUR_TOOLBAR_BTN_ACTIVE if active else COLOUR_TOOLBAR_BTN
        if rect.collidepoint(mouse):
            colour = COLOUR_TOOLBAR_BTN_HOVER
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

    def _draw_save(self, surface: pygame.Surface, panel: pygame.Rect) -> None:
        surface.blit(
            self.font_small.render("File name", True, COLOUR_TEXT_DIM),
            (panel.x + 24, panel.y + 56),
        )
        field = pygame.Rect(panel.x + 24, panel.y + 78, panel.w - 48, 30)
        pygame.draw.rect(surface, (30, 32, 38), field, border_radius=4)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, field, 1, border_radius=4)
        cursor = "_" if self._cursor_blink < 30 else " "
        shown = f"{self.save_name}{cursor}.json"
        surface.blit(self.font.render(shown, True, COLOUR_TEXT), (field.x + 8, field.y + 6))
        surface.blit(
            self.font_small.render(f"Saved to: {saves_dir()}", True, COLOUR_TEXT_DIM),
            (panel.x + 24, panel.y + 120),
        )
        self._draw_button(surface, pygame.Rect(panel.x + 24, panel.bottom - 48, 100, 28), "Save")
        self._draw_button(surface, pygame.Rect(panel.x + 136, panel.bottom - 48, 100, 28), "Cancel")

    def _draw_load(self, surface: pygame.Surface, panel: pygame.Rect) -> None:
        surface.blit(
            self.font_small.render(f"Saves in {saves_dir().name}/", True, COLOUR_TEXT_DIM),
            (panel.x + 24, panel.y + 48),
        )
        list_rect = self._list_rect(panel)
        pygame.draw.rect(surface, (30, 32, 38), list_rect, border_radius=4)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, list_rect, 1, border_radius=4)

        if not self.load_files:
            surface.blit(
                self.font_small.render("No save files found.", True, COLOUR_TEXT_DIM),
                (list_rect.x + 10, list_rect.y + 12),
            )
        else:
            self._clamp_scroll()
            content_h = self._list_content_h()
            old_clip = surface.get_clip()
            surface.set_clip(list_rect.clip(old_clip) if old_clip.width else list_rect)
            for i, name in enumerate(self.load_files):
                y = list_rect.y + 4 + i * LIST_ROW_H - self.load_scroll
                if y + LIST_ROW_H < list_rect.top or y > list_rect.bottom:
                    continue
                row = pygame.Rect(list_rect.x + 4, y, list_rect.w - 8, LIST_ROW_H)
                if i == self.load_index:
                    pygame.draw.rect(surface, COLOUR_TOOLBAR_BTN_ACTIVE, row, border_radius=3)
                colour = COLOUR_TEXT if i == self.load_index else COLOUR_TEXT_DIM
                surface.blit(
                    self.font_small.render(name, True, colour),
                    (row.x + 6, row.y + 4),
                )
            surface.set_clip(old_clip)

            if content_h > LIST_VIEW_H:
                track = pygame.Rect(list_rect.right - 6, list_rect.y + 2, 4, list_rect.h - 4)
                pygame.draw.rect(surface, (40, 42, 48), track, border_radius=2)
                ratio = LIST_VIEW_H / content_h
                thumb_h = max(12, int(track.h * ratio))
                max_scroll = content_h - LIST_VIEW_H
                thumb_y = track.y + int(
                    (track.h - thumb_h) * (self.load_scroll / max(1, max_scroll))
                )
                pygame.draw.rect(
                    surface,
                    (120, 130, 140),
                    pygame.Rect(track.x, thumb_y, track.w, thumb_h),
                    border_radius=2,
                )

        self._draw_button(
            surface,
            pygame.Rect(panel.x + 24, panel.bottom - 48, 100, 28),
            "Load",
            active=bool(self.load_files),
        )
        self._draw_button(surface, pygame.Rect(panel.x + 136, panel.bottom - 48, 100, 28), "Cancel")
