"""Expandable in-game popup for tuning balance parameters."""

from __future__ import annotations

import pygame

from balance_config import BALANCE_CATEGORIES, BalanceState
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
    seconds_to_ticks,
)

TITLE_BAR_H = 28
PAD = 10
ROW_H = 26
CAT_HEADER_H = 24
BTN_W = 22
HINT_H = 44


def _wrap_hint(text: str, font: pygame.font.Font, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if font.size(trial)[0] <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines[:2]


class BalanceDialog:
    """Movable balance editor with collapsible categories."""

    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 12)
        self.font_small = pygame.font.SysFont("menlo", 11)
        self.font_title = pygame.font.SysFont("menlo", 14, bold=True)
        self._open = False
        self._panel_x = 48
        self._panel_y = MAP_OFFSET_Y + 36
        self._panel_w = 420
        self._panel_h = 520
        self._moving = False
        self._move_offset = (0, 0)
        self._scroll = 0
        self._collapsed: dict[str, bool] = {}
        self._close_rect = pygame.Rect(0, 0, 0, 0)
        self._title_rect = pygame.Rect(0, 0, 0, 0)
        self._reset_all_rect = pygame.Rect(0, 0, 0, 0)
        self._hit_regions: list[tuple[pygame.Rect, str, str | None]] = []
        # (rect, action, param_key)  action: dec|inc|toggle_cat|reset_cat

    @property
    def open(self) -> bool:
        return self._open

    def toggle(self) -> None:
        if self._open:
            self.close()
        else:
            self.open_dialog()

    def open_dialog(self) -> None:
        self._open = True
        self._moving = False
        self._clamp_panel()

    def close(self) -> None:
        self._open = False
        self._moving = False

    def panel_rect(self) -> pygame.Rect:
        return pygame.Rect(self._panel_x, self._panel_y, self._panel_w, self._panel_h)

    def contains(self, pos: tuple[int, int]) -> bool:
        return self.open and self.panel_rect().collidepoint(pos)

    def _clamp_panel(self) -> None:
        self._panel_x = max(4, min(self._panel_x, WINDOW_WIDTH - self._panel_w - 4))
        self._panel_y = max(
            MAP_OFFSET_Y, min(self._panel_y, WINDOW_HEIGHT - self._panel_h - 4)
        )

    def _content_height(self) -> int:
        h = PAD
        for cat in BALANCE_CATEGORIES:
            h += CAT_HEADER_H
            if not self._collapsed.get(cat.id, False):
                h += len(cat.params) * ROW_H
                if cat.id == "time":
                    h += ROW_H
        return h + PAD + 8

    def _view_rect(self) -> pygame.Rect:
        panel = self.panel_rect()
        top = panel.y + TITLE_BAR_H + 34
        return pygame.Rect(
            panel.x + PAD,
            top,
            panel.w - 2 * PAD,
            panel.h - (top - panel.y) - PAD - HINT_H,
        )

    def _clamp_scroll(self) -> None:
        view = self._view_rect()
        self._scroll = max(0, min(self._scroll, max(0, self._content_height() - view.h)))

    def handle_keydown(self, event: pygame.event.Event) -> bool:
        if not self.open:
            return False
        if event.key == pygame.K_ESCAPE:
            self.close()
            return True
        return True

    def handle_mousedown(self, pos: tuple[int, int]) -> bool:
        if not self.open:
            return False
        if self._title_rect.collidepoint(pos) and not self._close_rect.collidepoint(pos):
            self._moving = True
            self._move_offset = (pos[0] - self._panel_x, pos[1] - self._panel_y)
            return True
        if self._close_rect.collidepoint(pos):
            self.close()
            return True
        if self._reset_all_rect.collidepoint(pos):
            return True
        for rect, action, key in self._hit_regions:
            if rect.collidepoint(pos):
                return True
        if self.panel_rect().collidepoint(pos):
            return True
        return False

    def handle_mouseup(self, pos: tuple[int, int], balance: BalanceState) -> bool:
        if not self.open:
            return False
        if self._moving:
            self._moving = False
            return True
        if self._reset_all_rect.collidepoint(pos):
            balance.reset()
            return True
        for rect, action, key in self._hit_regions:
            if not rect.collidepoint(pos):
                continue
            if action == "dec" and key:
                balance.adjust(key, -1)
            elif action == "inc" and key:
                balance.adjust(key, 1)
            elif action == "toggle_cat" and key:
                self._collapsed[key] = not self._collapsed.get(key, False)
                self._clamp_scroll()
            elif action == "reset_cat" and key:
                balance.reset_category(key)
            return True
        return self.panel_rect().collidepoint(pos)

    def handle_mousemotion(self, pos: tuple[int, int]) -> None:
        if self._moving:
            self._panel_x = pos[0] - self._move_offset[0]
            self._panel_y = pos[1] - self._move_offset[1]
            self._clamp_panel()

    def handle_mousewheel(self, delta: int) -> bool:
        if not self.open:
            return False
        self._scroll -= delta * ROW_H
        self._clamp_scroll()
        return True

    def _draw_button(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        label: str,
        *,
        active: bool = False,
        hovered: bool = False,
    ) -> None:
        bg = COLOUR_TOOLBAR_BTN_ACTIVE if active else (
            COLOUR_TOOLBAR_BTN_HOVER if hovered else COLOUR_TOOLBAR_BTN
        )
        pygame.draw.rect(surface, bg, rect)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, rect, 1)
        text = self.font_small.render(label, True, COLOUR_TEXT)
        surface.blit(
            text,
            (rect.x + (rect.w - text.get_width()) // 2, rect.y + (rect.h - text.get_height()) // 2),
        )

    def draw(
        self,
        surface: pygame.Surface,
        balance: BalanceState,
        mouse_pos: tuple[int, int] | None = None,
    ) -> None:
        if not self.open:
            return
        self._hit_regions.clear()
        panel = self.panel_rect()
        pygame.draw.rect(surface, COLOUR_MENU_BG, panel)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, panel, 2)

        self._title_rect = pygame.Rect(panel.x, panel.y, panel.w, TITLE_BAR_H)
        title = self.font_title.render("Game balance", True, COLOUR_TEXT)
        surface.blit(title, (panel.x + PAD, panel.y + 6))
        self._close_rect = pygame.Rect(panel.right - 28, panel.y + 4, 22, 20)
        self._draw_button(
            surface,
            self._close_rect,
            "×",
            hovered=mouse_pos is not None and self._close_rect.collidepoint(mouse_pos),
        )

        hint = self.font_small.render(
            "Seconds are real time at ×1. Hover a row for what it changes.",
            True,
            COLOUR_TEXT_DIM,
        )
        surface.blit(hint, (panel.x + PAD, panel.y + TITLE_BAR_H + 2))

        self._reset_all_rect = pygame.Rect(panel.right - 88, panel.y + TITLE_BAR_H + 1, 76, 18)
        self._draw_button(
            surface,
            self._reset_all_rect,
            "Reset all",
            hovered=mouse_pos is not None and self._reset_all_rect.collidepoint(mouse_pos),
        )

        view = self._view_rect()
        content_h = self._content_height()
        self._clamp_scroll()

        clip = surface.get_clip()
        surface.set_clip(view)
        y = view.y - self._scroll
        hovered_hint = ""

        for cat in BALANCE_CATEGORIES:
            collapsed = self._collapsed.get(cat.id, False)
            header = pygame.Rect(view.x, y, view.w, CAT_HEADER_H)
            arrow = "▸" if collapsed else "▾"
            header_text = self.font.render(f"{arrow} {cat.title}", True, COLOUR_TEXT)
            surface.blit(header_text, (header.x + 2, header.y + 4))
            reset_r = pygame.Rect(header.right - 52, header.y + 3, 48, 18)
            if header.colliderect(view):
                self._draw_button(
                    surface,
                    reset_r,
                    "Reset",
                    hovered=mouse_pos is not None and reset_r.collidepoint(mouse_pos or (0, 0)),
                )
            self._hit_regions.append((header, "toggle_cat", cat.id))
            self._hit_regions.append((reset_r, "reset_cat", cat.id))
            y += CAT_HEADER_H

            if collapsed:
                continue

            for param in cat.params:
                row = pygame.Rect(view.x, y, view.w, ROW_H - 2)
                minus_r = pygame.Rect(row.x + row.w - 58, row.y + 2, BTN_W, ROW_H - 6)
                plus_r = pygame.Rect(minus_r.right + 4, row.y + 2, BTN_W, ROW_H - 6)
                if (
                    mouse_pos is not None
                    and row.collidepoint(mouse_pos)
                    and param.hint
                ):
                    hovered_hint = param.hint
                if row.colliderect(view):
                    surface.blit(
                        self.font_small.render(param.label, True, COLOUR_TEXT),
                        (row.x + 4, row.y + 2),
                    )
                    val = (
                        str(balance.get_int(param.key))
                        if param.kind == "int"
                        else f"{balance.get_float(param.key):.2f}"
                    )
                    if param.suffix:
                        val = f"{val}{param.suffix}"
                    val_s = self.font.render(val, True, COLOUR_TEXT)
                    val_x = row.x + row.w - 118
                    surface.blit(val_s, (val_x, row.y + 3))
                    minus_r.x = val_x + val_s.get_width() + 8
                    plus_r.x = minus_r.right + 4
                    mp = mouse_pos or (0, 0)
                    self._draw_button(
                        surface, minus_r, "−", hovered=minus_r.collidepoint(mp)
                    )
                    self._draw_button(
                        surface, plus_r, "+", hovered=plus_r.collidepoint(mp)
                    )
                self._hit_regions.append((minus_r, "dec", param.key))
                self._hit_regions.append((plus_r, "inc", param.key))
                y += ROW_H

            if cat.id == "time":
                pb = max(1, balance.get_int("PLAYBACK_TICKS_AT_X1"))
                day_t = seconds_to_ticks(balance.get_float("DAY_SECONDS_AT_X1"), pb)
                walk_t = max(4, seconds_to_ticks(balance.get_float("WALK_SECONDS_AT_X1"), pb))
                work_t = max(6, seconds_to_ticks(balance.get_float("WORK_SECONDS_AT_X1"), pb))
                summary = (
                    f"≈ {day_t / walk_t:.0f} tiles/day  ·  "
                    f"≈ {day_t / work_t:.1f} work actions/day"
                )
                if pygame.Rect(view.x, y, view.w, ROW_H - 2).colliderect(view):
                    surface.blit(
                        self.font_small.render(summary, True, COLOUR_TEXT_DIM),
                        (view.x + 4, y + 4),
                    )
                y += ROW_H

        surface.set_clip(clip)

        if content_h > view.h:
            track = pygame.Rect(panel.right - 10, view.y, 4, view.h)
            pygame.draw.rect(surface, (55, 58, 68), track)
            thumb_h = max(24, int(view.h * view.h / content_h))
            thumb_y = view.y + int((view.h - thumb_h) * (self._scroll / max(1, content_h - view.h)))
            pygame.draw.rect(surface, (140, 144, 160), pygame.Rect(track.x, thumb_y, 4, thumb_h))

        hint_text = hovered_hint or "Hover a row for what it changes. Defaults live in settings.py."
        hint_y = view.bottom + 6
        for line in _wrap_hint(hint_text, self.font_small, panel.w - 2 * PAD):
            surface.blit(
                self.font_small.render(line, True, COLOUR_TEXT_DIM),
                (panel.x + PAD, hint_y),
            )
            hint_y += 13
