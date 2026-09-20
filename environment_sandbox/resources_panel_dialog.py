"""File → Resources panel: pick catalogue items and add them to the storehouse."""

from __future__ import annotations

import pygame

from resources import GROUP_LABELS, GROUP_ORDER, RESOURCES, ResourceDef, resource_label
from settings import (
    COLOUR_MENU_BG,
    COLOUR_TEXT,
    COLOUR_TEXT_DIM,
    COLOUR_TOOLBAR_BORDER,
    COLOUR_TOOLBAR_BTN,
    COLOUR_TOOLBAR_BTN_ACTIVE,
    COLOUR_TOOLBAR_BTN_HOVER,
    MAP_OFFSET_Y,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)

TITLE_BAR_H = 28
PAD = 10
LIST_W = 220
ROW_H = 20
DEFAULT_AMOUNT = 10
MAX_AMOUNT = 9999


class ResourcesPanelDialog:
    """Movable cheat/debug panel to deposit selected resources into storehouse."""

    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 13)
        self.font_small = pygame.font.SysFont("menlo", 11)
        self.font_title = pygame.font.SysFont("menlo", 15, bold=True)
        self._open = False
        self._panel_x = 48
        self._panel_y = MAP_OFFSET_Y + 28
        self._panel_w = 520
        self._panel_h = 420
        self._moving = False
        self._move_offset = (0, 0)
        self._close_rect = pygame.Rect(0, 0, 0, 0)
        self._title_rect = pygame.Rect(0, 0, 0, 0)
        self._list_rects: list[tuple[pygame.Rect, str]] = []
        self._btn_rects: list[tuple[pygame.Rect, str]] = []
        self._scroll = 0
        self.selected_keys: list[str] = ["wood"]
        self.amount: int = DEFAULT_AMOUNT
        self.pending_add: list[str] | None = None
        self._status = ""

    @property
    def open(self) -> bool:
        return self._open

    def open_panel(self) -> None:
        self._open = True
        self._moving = False
        self._scroll = 0
        self.pending_add = None
        self._status = ""
        if not self.selected_keys:
            self.selected_keys = ["wood"]
        self._clamp_panel()

    def close(self) -> None:
        self._open = False
        self._moving = False
        self.pending_add = None

    def toggle(self) -> None:
        if self._open:
            self.close()
        else:
            self.open_panel()

    def panel_rect(self) -> pygame.Rect:
        return pygame.Rect(self._panel_x, self._panel_y, self._panel_w, self._panel_h)

    def contains(self, pos: tuple[int, int]) -> bool:
        return self.open and self.panel_rect().collidepoint(pos)

    def _clamp_panel(self) -> None:
        self._panel_x = max(4, min(self._panel_x, WINDOW_WIDTH - self._panel_w - 4))
        self._panel_y = max(
            MAP_OFFSET_Y, min(self._panel_y, WINDOW_HEIGHT - self._panel_h - 4)
        )

    def _toggle_key(self, key: str) -> None:
        if key in self.selected_keys:
            if len(self.selected_keys) <= 1:
                return
            self.selected_keys = [k for k in self.selected_keys if k != key]
            return
        self.selected_keys = self.selected_keys + [key]

    def _adjust_amount(self, delta: int) -> None:
        self.amount = max(1, min(MAX_AMOUNT, int(self.amount) + int(delta)))

    def handle_keydown(self, event: pygame.event.Event) -> bool:
        if not self.open:
            return False
        if event.key == pygame.K_ESCAPE:
            self.close()
            return True
        if event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
            self._adjust_amount(1)
            return True
        if event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self._adjust_amount(-1)
            return True
        if event.key == pygame.K_RETURN:
            if self.selected_keys:
                self.pending_add = list(self.selected_keys)
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
        for rect, action in self._btn_rects:
            if not rect.collidepoint(pos):
                continue
            if action == "amt_minus":
                self._adjust_amount(-1)
            elif action == "amt_plus":
                self._adjust_amount(1)
            elif action == "amt_minus10":
                self._adjust_amount(-10)
            elif action == "amt_plus10":
                self._adjust_amount(10)
            elif action == "add":
                if self.selected_keys:
                    self.pending_add = list(self.selected_keys)
            elif action == "clear":
                self.selected_keys = [self.selected_keys[0]] if self.selected_keys else ["wood"]
            return True
        for rect, key in self._list_rects:
            if rect.collidepoint(pos):
                self._toggle_key(key)
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
        self._moving = False
        return self.contains(pos)

    def handle_mousewheel(self, dy: int, pos: tuple[int, int]) -> bool:
        if not self.open or not self.contains(pos):
            return False
        self._scroll = max(0, self._scroll - dy * 3)
        return True

    def _resource_rows(self) -> list[tuple[str, ResourceDef | None]]:
        from resources import resources_by_food_tier

        rows: list[tuple[str, ResourceDef | None]] = []
        by_group: dict[str, list[ResourceDef]] = {g: [] for g in GROUP_ORDER}
        for res in RESOURCES:
            by_group.setdefault(res.group, []).append(res)
        for group in GROUP_ORDER:
            if group == "food":
                rows.append((GROUP_LABELS.get(group, group), None))
                for tier_label, items in resources_by_food_tier():
                    rows.append((tier_label, None))
                    for res in items:
                        rows.append((res.label, res))
                continue
            rows.append((GROUP_LABELS.get(group, group), None))
            for res in by_group.get(group, []):
                rows.append((res.label, res))
        return rows

    def set_status(self, message: str) -> None:
        self._status = message

    def draw(
        self,
        surface: pygame.Surface,
        stock_now: dict[str, int] | None = None,
        mouse_pos: tuple[int, int] | None = None,
    ) -> None:
        if not self.open:
            return
        stock_now = stock_now or {}
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
            self.font_title.render("Resources", True, COLOUR_TEXT),
            (panel.x + 10, panel.y + 6),
        )
        hint = self.font_small.render("add to storehouse", True, COLOUR_TEXT_DIM)
        surface.blit(hint, (panel.x + 120, panel.y + 8))
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

        body_top = panel.y + TITLE_BAR_H + PAD
        body_h = panel.h - TITLE_BAR_H - PAD * 2
        list_rect = pygame.Rect(panel.x + PAD, body_top, LIST_W, body_h)
        side_rect = pygame.Rect(
            list_rect.right + PAD,
            body_top,
            panel.w - LIST_W - PAD * 3,
            body_h,
        )

        pygame.draw.rect(surface, (38, 40, 48), list_rect, border_radius=4)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, list_rect, 1, border_radius=4)

        rows = self._resource_rows()
        max_scroll = max(0, len(rows) - max(1, body_h // ROW_H))
        self._scroll = min(self._scroll, max_scroll)

        self._list_rects = []
        y = list_rect.y + 4
        for i, (label, res) in enumerate(rows):
            if i < self._scroll:
                continue
            if y + ROW_H > list_rect.bottom - 4:
                break
            if res is None:
                surface.blit(
                    self.font_small.render(label, True, COLOUR_TEXT_DIM),
                    (list_rect.x + 6, y + 3),
                )
                y += ROW_H
                continue
            row = pygame.Rect(list_rect.x + 2, y, list_rect.w - 4, ROW_H - 1)
            selected = res.key in self.selected_keys
            if selected:
                pygame.draw.rect(surface, COLOUR_TOOLBAR_BTN_ACTIVE, row, border_radius=3)
            elif mouse_pos is not None and row.collidepoint(mouse_pos):
                pygame.draw.rect(surface, COLOUR_TOOLBAR_BTN_HOVER, row, border_radius=3)
            colour = COLOUR_TEXT if selected else COLOUR_TEXT_DIM
            surface.blit(self.font_small.render(label, True, colour), (row.x + 6, row.y + 3))
            stock = int(stock_now.get(res.key, 0))
            if stock:
                stock_txt = self.font_small.render(str(stock), True, COLOUR_TEXT_DIM)
                surface.blit(stock_txt, (row.right - stock_txt.get_width() - 6, row.y + 3))
            self._list_rects.append((row, res.key))
            y += ROW_H

        self._btn_rects = []
        sx, sy = side_rect.x + 4, side_rect.y + 4
        surface.blit(
            self.font.render("Selected", True, COLOUR_TEXT),
            (sx, sy),
        )
        sy += 22
        if not self.selected_keys:
            surface.blit(
                self.font_small.render("(none)", True, COLOUR_TEXT_DIM),
                (sx, sy),
            )
            sy += 18
        else:
            for key in self.selected_keys[:12]:
                stock = int(stock_now.get(key, 0))
                line = f"{resource_label(key)}  ·  stock {stock}"
                surface.blit(self.font_small.render(line, True, COLOUR_TEXT), (sx, sy))
                sy += 16
            if len(self.selected_keys) > 12:
                surface.blit(
                    self.font_small.render(
                        f"+{len(self.selected_keys) - 12} more", True, COLOUR_TEXT_DIM
                    ),
                    (sx, sy),
                )
                sy += 16

        sy = max(sy + 12, side_rect.y + 210)
        surface.blit(self.font.render("Amount", True, COLOUR_TEXT), (sx, sy))
        sy += 24

        def _btn(x: int, y0: int, w: int, label: str, action: str) -> None:
            rect = pygame.Rect(x, y0, w, 26)
            hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
            pygame.draw.rect(
                surface,
                COLOUR_TOOLBAR_BTN_HOVER if hovered else COLOUR_TOOLBAR_BTN,
                rect,
                border_radius=4,
            )
            pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, rect, 1, border_radius=4)
            txt = self.font_small.render(label, True, COLOUR_TEXT)
            surface.blit(
                txt,
                (
                    rect.centerx - txt.get_width() // 2,
                    rect.centery - txt.get_height() // 2,
                ),
            )
            self._btn_rects.append((rect, action))

        _btn(sx, sy, 40, "−10", "amt_minus10")
        _btn(sx + 44, sy, 32, "−", "amt_minus")
        amt_box = pygame.Rect(sx + 80, sy, 64, 26)
        pygame.draw.rect(surface, (38, 40, 48), amt_box, border_radius=4)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, amt_box, 1, border_radius=4)
        amt_txt = self.font.render(str(self.amount), True, COLOUR_TEXT)
        surface.blit(
            amt_txt,
            (
                amt_box.centerx - amt_txt.get_width() // 2,
                amt_box.centery - amt_txt.get_height() // 2,
            ),
        )
        _btn(sx + 148, sy, 32, "+", "amt_plus")
        _btn(sx + 184, sy, 40, "+10", "amt_plus10")

        sy += 40
        add_w = side_rect.w - 8
        _btn(sx, sy, add_w, "Add to storehouse", "add")
        sy += 34
        _btn(sx, sy, add_w, "Clear selection", "clear")

        if self._status:
            sy = side_rect.bottom - 28
            surface.blit(
                self.font_small.render(self._status, True, (140, 200, 150)),
                (sx, sy),
            )
