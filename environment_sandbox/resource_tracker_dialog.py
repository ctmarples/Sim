"""Floating popup: 24-month charts with multi-resource compare."""

from __future__ import annotations

import pygame

from resources import GROUP_LABELS, GROUP_ORDER, RESOURCES, ResourceDef
from resource_tracker import HISTORY_MONTHS, ResourceHistory
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
LIST_W = 178
MAX_SELECTED = 8
CHART_COLOUR_PROD = (90, 190, 120)
CHART_COLOUR_CONS = (220, 120, 100)
CHART_COLOUR_STOCK = (110, 170, 230)
CHART_GRID = (55, 58, 68)
CHART_AXIS = (90, 95, 110)

# Distinct hues for multi-resource compare.
RESOURCE_PALETTE: tuple[tuple[int, int, int], ...] = (
    (90, 190, 120),
    (220, 120, 100),
    (110, 170, 230),
    (230, 190, 80),
    (180, 120, 220),
    (80, 200, 190),
    (230, 140, 80),
    (160, 200, 100),
)


class ResourceTrackerDialog:
    """Movable window with multi-select resource list and line charts."""

    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 13)
        self.font_small = pygame.font.SysFont("menlo", 11)
        self.font_title = pygame.font.SysFont("menlo", 15, bold=True)
        self._open = False
        self._panel_x = 40
        self._panel_y = MAP_OFFSET_Y + 24
        self._panel_w = 760
        self._panel_h = 460
        self._moving = False
        self._move_offset = (0, 0)
        self._close_rect = pygame.Rect(0, 0, 0, 0)
        self._title_rect = pygame.Rect(0, 0, 0, 0)
        self._list_rects: list[tuple[pygame.Rect, str]] = []
        self._metric_rects: list[tuple[pygame.Rect, str]] = []
        self._scroll = 0
        self.selected_keys: list[str] = ["wood"]
        self.show_produced: bool = True
        self.show_consumed: bool = True
        self.show_stock: bool = True
        self._row_h = 20

    @property
    def open(self) -> bool:
        return self._open

    def open_tracker(self, history: ResourceHistory | None = None) -> None:
        self._open = True
        self._moving = False
        self._scroll = 0
        if history is not None and not self.selected_keys:
            active = history.keys_with_activity()
            for res in RESOURCES:
                if res.key in active:
                    self.selected_keys = [res.key]
                    break
            if not self.selected_keys:
                self.selected_keys = ["wood"]
        self._clamp_panel()

    def close(self) -> None:
        self._open = False
        self._moving = False

    def toggle(self, history: ResourceHistory | None = None) -> None:
        if self._open:
            self.close()
        else:
            self.open_tracker(history)

    def panel_rect(self) -> pygame.Rect:
        return pygame.Rect(self._panel_x, self._panel_y, self._panel_w, self._panel_h)

    def contains(self, pos: tuple[int, int]) -> bool:
        return self.open and self.panel_rect().collidepoint(pos)

    def _clamp_panel(self) -> None:
        self._panel_x = max(4, min(self._panel_x, WINDOW_WIDTH - self._panel_w - 4))
        self._panel_y = max(
            MAP_OFFSET_Y, min(self._panel_y, WINDOW_HEIGHT - self._panel_h - 4)
        )

    def _resource_colour(self, key: str) -> tuple[int, int, int]:
        if key in self.selected_keys:
            idx = self.selected_keys.index(key)
            return RESOURCE_PALETTE[idx % len(RESOURCE_PALETTE)]
        return COLOUR_TEXT_DIM

    def _toggle_key(self, key: str) -> None:
        if key in self.selected_keys:
            if len(self.selected_keys) <= 1:
                return
            self.selected_keys = [k for k in self.selected_keys if k != key]
            return
        if len(self.selected_keys) >= MAX_SELECTED:
            self.selected_keys = self.selected_keys[1:] + [key]
        else:
            self.selected_keys = self.selected_keys + [key]

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
        for rect, metric in self._metric_rects:
            if rect.collidepoint(pos):
                if metric == "produced":
                    self.show_produced = not self.show_produced
                elif metric == "consumed":
                    self.show_consumed = not self.show_consumed
                elif metric == "stock":
                    self.show_stock = not self.show_stock
                # Keep at least one metric visible.
                if not (self.show_produced or self.show_consumed or self.show_stock):
                    if metric == "produced":
                        self.show_produced = True
                    elif metric == "consumed":
                        self.show_consumed = True
                    else:
                        self.show_stock = True
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
        if self._moving:
            self._moving = False
            self._clamp_panel()
            return True
        return self.contains(pos)

    def handle_mousewheel(self, dy: int, pos: tuple[int, int] | None = None) -> bool:
        if not self.open:
            return False
        if pos is not None and not self.contains(pos):
            return False
        panel = self.panel_rect()
        list_area = pygame.Rect(
            panel.x + PAD,
            panel.y + TITLE_BAR_H + PAD,
            LIST_W,
            panel.h - TITLE_BAR_H - PAD * 2,
        )
        if pos is not None and not list_area.collidepoint(pos):
            return False
        self._scroll = max(0, self._scroll - dy * 3)
        return True

    def _resource_rows(self) -> list[tuple[str, ResourceDef | None]]:
        rows: list[tuple[str, ResourceDef | None]] = []
        by_group: dict[str, list[ResourceDef]] = {g: [] for g in GROUP_ORDER}
        for res in RESOURCES:
            by_group.setdefault(res.group, []).append(res)
        for group in GROUP_ORDER:
            rows.append((GROUP_LABELS.get(group, group), None))
            for res in by_group.get(group, []):
                rows.append((res.label, res))
        return rows

    def _label_for(self, key: str) -> str:
        return next((r.label for r in RESOURCES if r.key == key), key)

    def draw(
        self,
        surface: pygame.Surface,
        history: ResourceHistory,
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
            self.font_title.render("Resource tracker", True, COLOUR_TEXT),
            (panel.x + 10, panel.y + 6),
        )
        hint = self.font_small.render("click to multi-select", True, COLOUR_TEXT_DIM)
        surface.blit(hint, (panel.x + 170, panel.y + 8))
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
        chart_rect = pygame.Rect(
            list_rect.right + PAD,
            body_top,
            panel.w - LIST_W - PAD * 3,
            body_h,
        )

        pygame.draw.rect(surface, (38, 40, 48), list_rect, border_radius=4)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, list_rect, 1, border_radius=4)

        active = history.keys_with_activity()
        rows = self._resource_rows()
        max_scroll = max(0, len(rows) - max(1, body_h // self._row_h))
        self._scroll = min(self._scroll, max_scroll)

        self._list_rects = []
        y = list_rect.y + 4
        for i, (label, res) in enumerate(rows):
            if i < self._scroll:
                continue
            if y + self._row_h > list_rect.bottom - 2:
                break
            if res is None:
                surface.blit(
                    self.font_small.render(label.upper(), True, COLOUR_TEXT_DIM),
                    (list_rect.x + 6, y + 2),
                )
                y += self._row_h
                continue
            row_rect = pygame.Rect(list_rect.x + 2, y, list_rect.w - 4, self._row_h - 1)
            selected = res.key in self.selected_keys
            row_hover = mouse_pos is not None and row_rect.collidepoint(mouse_pos)
            if selected:
                pygame.draw.rect(
                    surface, COLOUR_TOOLBAR_BTN_ACTIVE, row_rect, border_radius=3
                )
            elif row_hover:
                pygame.draw.rect(
                    surface, COLOUR_TOOLBAR_BTN_HOVER, row_rect, border_radius=3
                )
            if selected:
                pygame.draw.circle(
                    surface,
                    self._resource_colour(res.key),
                    (row_rect.x + 10, row_rect.centery),
                    4,
                )
            colour = COLOUR_TEXT if res.key in active or selected else COLOUR_TEXT_DIM
            surface.blit(
                self.font_small.render(res.label, True, colour),
                (row_rect.x + 20, row_rect.y + 2),
            )
            now = int(stock_now.get(res.key, 0))
            if now > 0 or selected:
                t = self.font_small.render(str(now), True, COLOUR_TEXT_DIM)
                surface.blit(t, (row_rect.right - 6 - t.get_width(), row_rect.y + 2))
            self._list_rects.append((row_rect, res.key))
            y += self._row_h

        self._draw_chart(surface, history, stock_now, chart_rect, mouse_pos)

    def _draw_metric_toggles(
        self,
        surface: pygame.Surface,
        area: pygame.Rect,
        mouse_pos: tuple[int, int] | None,
    ) -> int:
        """Draw Prod / Cons / Total toggles; return y below them."""
        self._metric_rects = []
        specs = (
            ("produced", "Production", self.show_produced, CHART_COLOUR_PROD),
            ("consumed", "Consumption", self.show_consumed, CHART_COLOUR_CONS),
            ("stock", "Total", self.show_stock, CHART_COLOUR_STOCK),
        )
        x = area.x + 10
        y = area.y + 8
        for key, label, on, colour in specs:
            tw = 10 + self.font_small.size(label)[0]
            rect = pygame.Rect(x, y, tw + 16, 18)
            hover = mouse_pos is not None and rect.collidepoint(mouse_pos)
            bg = COLOUR_TOOLBAR_BTN_ACTIVE if on else COLOUR_TOOLBAR_BTN
            if hover and not on:
                bg = COLOUR_TOOLBAR_BTN_HOVER
            pygame.draw.rect(surface, bg, rect, border_radius=3)
            pygame.draw.circle(surface, colour, (rect.x + 8, rect.centery), 3)
            surface.blit(
                self.font_small.render(label, True, COLOUR_TEXT),
                (rect.x + 16, rect.y + 2),
            )
            self._metric_rects.append((rect, key))
            x = rect.right + 6
        return y + 22

    def _draw_chart(
        self,
        surface: pygame.Surface,
        history: ResourceHistory,
        stock_now: dict[str, int],
        area: pygame.Rect,
        mouse_pos: tuple[int, int] | None,
    ) -> None:
        pygame.draw.rect(surface, (34, 36, 44), area, border_radius=4)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, area, 1, border_radius=4)

        below_toggles = self._draw_metric_toggles(surface, area, mouse_pos)

        keys = list(self.selected_keys) or ["wood"]
        multi = len(keys) > 1

        # Summary lines for selected resources
        summary_y = below_toggles + 2
        for key in keys[:4]:
            labels, produced, consumed, stock = history.series(key)
            del labels, stock
            tot_p, tot_c = sum(produced), sum(consumed)
            now = int(stock_now.get(key, 0))
            colour = self._resource_colour(key) if multi else COLOUR_TEXT
            line = (
                f"{self._label_for(key)}  stock {now}  "
                f"prod {tot_p}  cons {tot_c}"
            )
            surface.blit(
                self.font_small.render(line, True, colour),
                (area.x + 10, summary_y),
            )
            summary_y += 14
        if len(keys) > 4:
            surface.blit(
                self.font_small.render(
                    f"+{len(keys) - 4} more…", True, COLOUR_TEXT_DIM
                ),
                (area.x + 10, summary_y),
            )
            summary_y += 14

        plot_top = max(summary_y + 4, area.y + 78)
        plot = pygame.Rect(area.x + 44, plot_top, area.w - 56, area.bottom - plot_top - 28)
        if plot.h < 80:
            plot.h = max(60, area.bottom - plot_top - 28)
        pygame.draw.rect(surface, (28, 30, 36), plot, border_radius=2)

        # Gather series for ymax
        series_list: list[tuple[str, str, list[int], tuple[int, int, int]]] = []
        labels: list[str] = []
        for key in keys:
            labs, produced, consumed, stock = history.series(key)
            labels = labs
            base = self._resource_colour(key) if multi else None
            if self.show_produced:
                series_list.append(
                    (
                        key,
                        "prod",
                        produced,
                        base if multi else CHART_COLOUR_PROD,
                    )
                )
            if self.show_consumed:
                series_list.append(
                    (
                        key,
                        "cons",
                        consumed,
                        base if multi else CHART_COLOUR_CONS,
                    )
                )
            if self.show_stock:
                series_list.append(
                    (
                        key,
                        "stock",
                        stock,
                        base if multi else CHART_COLOUR_STOCK,
                    )
                )

        ymax = 1
        for _, _, values, _ in series_list:
            if values:
                ymax = max(ymax, max(values))
        for step in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000):
            if step * 4 >= ymax:
                ymax = step * 4
                break

        n = len(labels) if labels else HISTORY_MONTHS
        if n < 2:
            return

        def pt(i: int, value: int) -> tuple[int, int]:
            x = plot.x + int(i * (plot.w - 1) / (n - 1))
            y = plot.bottom - 1 - int(value * (plot.h - 1) / ymax)
            return x, y

        for g in range(5):
            gy = plot.y + int(g * (plot.h - 1) / 4)
            pygame.draw.line(surface, CHART_GRID, (plot.x, gy), (plot.right, gy), 1)
            val = int(round(ymax * (4 - g) / 4))
            t = self.font_small.render(str(val), True, COLOUR_TEXT_DIM)
            surface.blit(t, (plot.x - 6 - t.get_width(), gy - t.get_height() // 2))

        pygame.draw.line(
            surface, CHART_AXIS, (plot.x, plot.bottom), (plot.right, plot.bottom), 1
        )
        pygame.draw.line(
            surface, CHART_AXIS, (plot.x, plot.y), (plot.x, plot.bottom), 1
        )

        # Multi-metric: vary dash pattern via point skipping / width.
        for key, kind, values, colour in series_list:
            pts = [pt(i, values[i]) for i in range(n)]
            width = 2 if kind == "prod" or not multi else 2
            if len(pts) >= 2:
                if kind == "consumed":
                    # Dashed: draw segments every other pair
                    for i in range(0, len(pts) - 1, 2):
                        pygame.draw.line(surface, colour, pts[i], pts[i + 1], width)
                elif kind == "stock":
                    # Dotted markers connected thinly
                    pygame.draw.lines(surface, colour, False, pts, 1)
                    for p in pts:
                        pygame.draw.circle(surface, colour, p, 2)
                else:
                    pygame.draw.lines(surface, colour, False, pts, width)
                    for p in pts:
                        pygame.draw.circle(surface, colour, p, 2)

        for i, name in enumerate(labels):
            if i % 3 != 0 and i != n - 1:
                continue
            x = plot.x + int(i * (plot.w - 1) / (n - 1))
            t = self.font_small.render(name, True, COLOUR_TEXT_DIM)
            surface.blit(t, (x - t.get_width() // 2, plot.bottom + 6))
