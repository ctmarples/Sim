"""Field management panel: Status (yield / environment) and Rotation (crop plans)."""

from __future__ import annotations

import pygame

from crops import (
    CROP_BY_KEY,
    PHASE_SHORT,
    PLAN_COLOUR_GROW,
    PLAN_COLOUR_HARVEST,
    PLAN_COLOUR_PLANT,
    SeasonPhase,
    crop_for_season,
    phase_allows_harvest,
    phase_allows_plough_plant,
    phase_for_crop,
)
from crop_status_ui import draw_crop_overview, draw_env_hover
from entities import Building, BuildingKind
from field_yield import (
    SEVERITY_COLOUR,
    FieldFactorDisplay,
    FieldYieldSummary,
    Severity,
    build_field_factors,
    main_limitation,
    stage_effect_pct,
)
from seasons import SEASON_LABELS, SEASON_ORDER, Season
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
    map_view_width,
)

TITLE_BAR_H = 28
PAD = 12
BTN_H = 24
TAB_H = 24
ROW_H = 22
SECTION_GAP = 10
SCROLL_STEP = 28


def _draw_crop_glyph(
    surface: pygame.Surface,
    cx: int,
    cy: int,
    stem: tuple[int, int, int],
    flower: tuple[int, int, int] | None,
    *,
    scale: float = 1.0,
    icon_base: str = "crop_plant",
) -> None:
    from icons import blit_icon

    size = max(8, int(round(24 * max(0.5, scale))))
    recolour = {"stem": stem}
    omit: tuple[str, ...] = ()
    if flower is not None:
        recolour["flower"] = flower
    else:
        omit = ("flower",)
    blit_icon(
        surface,
        icon_base,
        cx,
        cy,
        size,
        variant=1,
        recolour=recolour,
        omit_classes=omit,
    )


class FieldPlanDialog:
    """Field inspect + crop planner. Status tab by default; Rotation holds plans."""

    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 14)
        self.font_small = pygame.font.SysFont("menlo", 12)
        self.font_tiny = pygame.font.SysFont("menlo", 11, bold=True)
        self.font_title = pygame.font.SysFont("menlo", 15, bold=True)
        self.building_id: int | None = None
        self._crop_overview: list[dict] = []
        self._env_status: dict | None = None
        self._yield_summary: FieldYieldSummary | None = None
        self._headline: str = ""
        self._factors: list[FieldFactorDisplay] = []
        self.tab: str = "status"  # status | rotation
        self.expanded_factor: str | None = None
        self._scroll = 0
        self._content_h = 0
        self._view_rect = pygame.Rect(0, 0, 0, 0)
        self._pending_overlay: str | None = None
        self._pending_yield_map = False
        self._debug = False
        self.season: Season = Season.SPRING
        self.crop_kind: str = "sage"
        self._drag_start: tuple[int, int] | None = None
        self._drag_current: tuple[int, int] | None = None
        self._buttons: list[tuple[str, pygame.Rect]] = []
        self._grid_origin = (0, 0)
        self._cell_px = 24
        self._result: str | None = None
        self._pending_plan: tuple[int, int, int, int, str] | None = None
        self._panel_x = 80
        self._panel_y = MAP_OFFSET_Y + 40
        self._panel_w = 420
        self._panel_h = 280
        self._moving = False
        self._move_offset = (0, 0)
        self._close_rect = pygame.Rect(0, 0, 0, 0)
        self._title_rect = pygame.Rect(0, 0, 0, 0)
        self.embedded = False

    @property
    def open(self) -> bool:
        return self.building_id is not None

    def configure_embed(self, rect: pygame.Rect) -> None:
        self.embedded = True
        self._panel_x = rect.x
        self._panel_y = rect.y
        self._panel_w = max(120, rect.w)
        self._panel_h = max(120, rect.h)

    def open_for(self, building: Building, *, season: Season | None = None) -> None:
        if building.kind != BuildingKind.FIELD:
            return
        self.building_id = building.id
        self.season = season or Season.SPRING
        self.tab = "status"
        self.expanded_factor = None
        self._scroll = 0
        options = crop_for_season(self.season)
        if options:
            if self.crop_kind not in {c.key for c in options}:
                self.crop_kind = options[0].key
        else:
            self.crop_kind = "sage"
        self._drag_start = None
        self._drag_current = None
        self._result = None
        self._pending_plan = None
        self._pending_overlay = None
        self._pending_yield_map = False
        self._moving = False
        self._layout_for(building)
        if self.embedded:
            return
        from settings import CELL_SIZE

        map_w = map_view_width()
        prefer_x = building.x * CELL_SIZE + building.plot_w * CELL_SIZE + 16
        prefer_y = MAP_OFFSET_Y + building.y * CELL_SIZE
        if prefer_x + self._panel_w > map_w - 8:
            prefer_x = max(8, building.x * CELL_SIZE - self._panel_w - 16)
        self._panel_x = prefer_x
        self._panel_y = prefer_y
        self._clamp_panel()

    def close(self) -> None:
        self.building_id = None
        self._drag_start = None
        self._drag_current = None
        self._moving = False
        self.embedded = False
        self._result = "closed"

    def take_result(self) -> str | None:
        result = self._result
        self._result = None
        return result

    def take_pending_plan(self) -> tuple[int, int, int, int, str] | None:
        plan = self._pending_plan
        self._pending_plan = None
        return plan

    def take_pending_overlay(self) -> str | None:
        key = self._pending_overlay
        self._pending_overlay = None
        return key

    def take_yield_map_request(self) -> bool:
        flag = self._pending_yield_map
        self._pending_yield_map = False
        return flag

    def panel_rect(self) -> pygame.Rect:
        return pygame.Rect(self._panel_x, self._panel_y, self._panel_w, self._panel_h)

    def contains(self, pos: tuple[int, int]) -> bool:
        return self.open and self.panel_rect().collidepoint(pos)

    def _layout_for(self, building: Building) -> None:
        pw, ph = max(1, building.plot_w), max(1, building.plot_h)
        if self.embedded:
            if self.tab == "rotation":
                inner_w = max(40, self._panel_w - PAD * 2)
                crop_rows = self._crop_row_count(inner_w)
                n = max(1, len(self._crop_overview))
                chrome = (
                    TITLE_BAR_H
                    + TAB_H
                    + 8
                    + PAD
                    + 18
                    + 16
                    + n * 18
                    + 10
                    + BTN_H
                    + 6
                    + crop_rows * (BTN_H + 4)
                    + 8
                    + 22
                    + PAD
                )
                avail_h = max(24, self._panel_h - chrome)
                cell_w = max(8, inner_w // pw)
                cell_h = max(8, avail_h // ph)
                self._cell_px = min(28, cell_w, cell_h)
            else:
                self._cell_px = 16
            return
        max_grid_w = min(WINDOW_WIDTH - 60, 560)
        max_grid_h = min(WINDOW_HEIGHT - 220, 420)
        cell = min(28, max(12, max_grid_w // pw), max(12, max_grid_h // ph))
        self._cell_px = cell
        grid_w = pw * cell
        grid_h = ph * cell
        crop_rows = self._crop_row_count(max(420, grid_w + PAD * 2))
        chrome = (
            TITLE_BAR_H
            + TAB_H
            + 8
            + PAD
            + BTN_H
            + 6
            + crop_rows * (BTN_H + 4)
            + 8
            + 22
            + PAD
        )
        self._panel_w = max(420, grid_w + PAD * 2)
        self._panel_h = chrome + grid_h + 120

    def _crop_row_count(self, inner_w: int) -> int:
        options = crop_for_season(self.season)
        if not options:
            return 1
        x = 0
        rows = 1
        for crop in options:
            label = crop.label[:6]
            w = max(44, 10 + self.font_small.size(label)[0])
            if x > 0 and x + w > inner_w - PAD * 2:
                rows += 1
                x = 0
            x += w + 4
        return rows

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

    def handle_mousedown(self, pos: tuple[int, int], building: Building) -> None:
        if not self.open or building is None:
            return
        if self._close_rect.collidepoint(pos):
            self.close()
            return
        if not self.embedded and self._title_rect.collidepoint(pos):
            self._moving = True
            self._move_offset = (pos[0] - self._panel_x, pos[1] - self._panel_y)
            return
        for action, rect in self._buttons:
            if rect.collidepoint(pos):
                self._on_action(action, building)
                return
        if self.tab == "rotation":
            local = self._pos_to_local(pos, building)
            if local is not None:
                self._drag_start = local
                self._drag_current = local

    def handle_mousemotion(self, pos: tuple[int, int], building: Building) -> None:
        if self._moving:
            self._panel_x = pos[0] - self._move_offset[0]
            self._panel_y = pos[1] - self._move_offset[1]
            self._clamp_panel()
            return
        if self._drag_start is not None and self.tab == "rotation":
            local = self._pos_to_local(pos, building)
            if local is not None:
                self._drag_current = local

    def handle_mouseup(self, pos: tuple[int, int], building: Building) -> None:
        if self._moving:
            self._moving = False
            return
        if self._drag_start is not None and building is not None and self.tab == "rotation":
            local = self._pos_to_local(pos, building) or self._drag_current
            if local is not None:
                sx, sy = self._drag_start
                cx, cy = local
                x0, x1 = min(sx, cx), max(sx, cx)
                y0, y1 = min(sy, cy), max(sy, cy)
                self._pending_plan = (
                    building.x + x0,
                    building.y + y0,
                    building.x + x1,
                    building.y + y1,
                    self.crop_kind,
                )
            self._drag_start = None
            self._drag_current = None

    def handle_scroll(self, pos: tuple[int, int], dy: int) -> bool:
        if not self.open or self.tab != "status":
            return False
        if not self._view_rect.collidepoint(pos):
            return False
        max_scroll = max(0, self._content_h - self._view_rect.h)
        self._scroll = max(0, min(max_scroll, self._scroll - dy * SCROLL_STEP))
        return True

    def _on_action(self, action: str, building: Building) -> None:
        if action == "tab_status":
            self.tab = "status"
            self._scroll = 0
            self._drag_start = None
            self._drag_current = None
        elif action == "tab_rotation":
            self.tab = "rotation"
            self.expanded_factor = None
            self._layout_for(building)
        elif action == "clear_plans":
            self._result = "cleared"
        elif action == "delete_field":
            self._result = "deleted"
        elif action == "add_fence":
            self._result = "add_fence"
        elif action == "show_yield_map":
            self._pending_yield_map = True
        elif action.startswith("overlay_"):
            self._pending_overlay = action[len("overlay_") :]
        elif action.startswith("factor_"):
            key = action[len("factor_") :]
            self.expanded_factor = None if self.expanded_factor == key else key
        elif action.startswith("season_"):
            name = action[len("season_") :]
            try:
                self.season = Season[name]
            except KeyError:
                return
            options = crop_for_season(self.season)
            if options and self.crop_kind not in {c.key for c in options}:
                self.crop_kind = options[0].key
            self._layout_for(building)
            if not self.embedded:
                self._clamp_panel()
        elif action.startswith("crop_"):
            key = action[len("crop_") :]
            if key in CROP_BY_KEY:
                self.crop_kind = key

    def _pos_to_local(
        self, pos: tuple[int, int], building: Building
    ) -> tuple[int, int] | None:
        ox, oy = self._grid_origin
        cell = self._cell_px
        mx, my = pos
        if mx < ox or my < oy:
            return None
        lx = (mx - ox) // cell
        ly = (my - oy) // cell
        if 0 <= lx < max(1, building.plot_w) and 0 <= ly < max(1, building.plot_h):
            return lx, ly
        return None

    def _fonts(self) -> tuple[pygame.font.Font, pygame.font.Font, pygame.font.Font]:
        return self.font, self.font_small, self.font_tiny

    def draw(
        self,
        surface: pygame.Surface,
        building: Building | None,
        *,
        crop_overview: list[dict] | None = None,
        env_status: dict | None = None,
        yield_summary: FieldYieldSummary | None = None,
        headline: str = "",
        current_season: Season | None = None,
        mouse_pos: tuple[int, int] | None = None,
        yield_map_active: bool = False,
        debug: bool = False,
    ) -> None:
        if not self.open or building is None or building.kind != BuildingKind.FIELD:
            return
        self._crop_overview = list(crop_overview or [])
        self._env_status = env_status
        self._yield_summary = yield_summary
        self._headline = headline
        self._factors = build_field_factors(env_status) if env_status else []
        self._debug = debug
        self._layout_for(building)
        if not self.embedded:
            self._clamp_panel()
        panel = self.panel_rect()
        if mouse_pos is None:
            mouse_pos = pygame.mouse.get_pos()

        old_clip = surface.get_clip()
        if self.embedded:
            surface.set_clip(panel)
        else:
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
        title = f"Field #{building.id} · {building.plot_size_label()}"
        surface.blit(
            self.font.render(title, True, COLOUR_TEXT),
            (panel.x + 10, panel.y + 6),
        )
        if self.embedded:
            self._close_rect = pygame.Rect(0, 0, 0, 0)
        else:
            self._close_rect = pygame.Rect(panel.right - 28, panel.y + 4, 22, 20)
            hover = self._close_rect.collidepoint(mouse_pos)
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

        self._buttons = []
        y = panel.y + TITLE_BAR_H + 6
        inner_left = panel.x + PAD
        inner_right = panel.right - PAD
        inner_w = max(40, inner_right - inner_left)

        # Tabs
        for label, key in (("Status", "status"), ("Rotation", "rotation")):
            w = max(64, 12 + self.font_small.size(label)[0])
            rect = pygame.Rect(inner_left if key == "status" else inner_left + 72, y, w, TAB_H)
            self._draw_btn(surface, rect, label, self.tab == key)
            self._buttons.append((f"tab_{key}", rect))
        y += TAB_H + 8

        hover_tip = ""
        if self.tab == "status":
            hover_tip = self._draw_status(
                surface,
                building,
                x=inner_left,
                y=y,
                inner_w=inner_w,
                bottom=panel.bottom - PAD,
                mouse_pos=mouse_pos,
                current_season=current_season or self.season,
                yield_map_active=yield_map_active,
            )
        else:
            self._draw_rotation(
                surface,
                building,
                x=inner_left,
                y=y,
                inner_w=inner_w,
                mouse_pos=mouse_pos,
                current_season=current_season or self.season,
            )

        surface.set_clip(old_clip)
        draw_env_hover(surface, mouse_pos, hover_tip, self.font_small)

    def _draw_status(
        self,
        surface: pygame.Surface,
        building: Building,
        *,
        x: int,
        y: int,
        inner_w: int,
        bottom: int,
        mouse_pos: tuple[int, int] | None,
        current_season: Season,
        yield_map_active: bool,
    ) -> str:
        from icons import blit_icon

        view = pygame.Rect(x, y, inner_w, max(40, bottom - y))
        self._view_rect = view
        hover_tip = ""
        summary = self._yield_summary
        sections = (
            ("LANDSCAPE", "landscape"),
            ("FIELD CONDITION", "condition"),
            ("SOIL", "soil"),
        )

        def _expanded_h(fac: FieldFactorDisplay) -> int:
            if self.expanded_factor != fac.key:
                return 0
            h = len(fac.detail_lines) * 13
            if fac.overlay_key:
                h += BTN_H + 2
            return h + 2

        cy = 0
        cy += 20 if self._headline else 18
        cy += 16
        if summary is None or summary.tile_count <= 0:
            cy += 18
        else:
            cy += self.font_title.get_height() + 2 + 14 + 12 + 16
        for _t, sec in sections:
            rows = [f for f in self._factors if f.section == sec]
            if not rows:
                continue
            cy += 16
            for fac in rows:
                cy += ROW_H + 2 + _expanded_h(fac)
            cy += 4
        if summary is not None and summary.tile_count > 0:
            cy += 16 + 4 * 14 + 6
            if getattr(self, "_debug", False) and self._env_status:
                cy += 4 + 14 + 12 + 12
        cy += BTN_H * 2 + 10
        self._content_h = cy
        max_scroll = max(0, self._content_h - view.h)
        self._scroll = max(0, min(max_scroll, self._scroll))

        old = surface.get_clip()
        surface.set_clip(view.clip(old) if old.width else view)
        sy = view.y - self._scroll

        def _blit(font, text, colour, ox, oy):
            surface.blit(font.render(text, True, colour), (view.x + ox, oy))

        if self._headline:
            _blit(self.font_title, self._headline, COLOUR_TEXT, 0, sy)
            sy += 20
        else:
            _blit(self.font_small, "No active crop on this field", COLOUR_TEXT_DIM, 0, sy)
            sy += 18

        _blit(self.font, "EXPECTED HARVEST", COLOUR_TEXT, 0, sy)
        sy += 16
        if summary is None or summary.tile_count <= 0:
            _blit(
                self.font_small,
                "No planned / planted tiles to estimate.",
                COLOUR_TEXT_DIM,
                0,
                sy,
            )
            sy += 18
        else:
            locked = summary.locked_total is not None
            total = summary.locked_total if locked else summary.expected_total
            ratio = total / summary.max_total if summary.max_total > 0 else 0.0
            ratio = max(0.0, min(1.0, ratio))
            pct_label = f"{ratio * 100:.0f}%"
            if locked:
                pct_label = f"locked · {pct_label}"
            big = self.font_title.render(
                f"{total} / {summary.max_total}", True, COLOUR_TEXT
            )
            surface.blit(big, (view.x, sy))
            pct_s = self.font_small.render(pct_label, True, COLOUR_TEXT_DIM)
            surface.blit(pct_s, (view.x + inner_w - pct_s.get_width(), sy + 2))
            sy += big.get_height() + 2
            left = f"{summary.mean_expected:.1f} / {summary.base_per_tile:g} per tile"
            _blit(self.font_small, left, COLOUR_TEXT, 0, sy)
            if summary.min_expected != summary.max_expected:
                rng = f"range {summary.min_expected}–{summary.max_expected}"
                rt = self.font_tiny.render(rng, True, COLOUR_TEXT_DIM)
                surface.blit(rt, (view.x + inner_w - rt.get_width(), sy + 1))
                if mouse_pos is not None:
                    tip_rect = pygame.Rect(
                        view.x + inner_w - rt.get_width() - 4,
                        sy,
                        rt.get_width() + 8,
                        16,
                    )
                    if tip_rect.collidepoint(mouse_pos):
                        hover_tip = (
                            "Harvest varies by tile "
                            "(local disturbance, fertility, weeds)."
                        )
            sy += 14
            bar = pygame.Rect(view.x, sy, inner_w, 8)
            pygame.draw.rect(surface, (40, 42, 48), bar, border_radius=3)
            fill = pygame.Rect(view.x, sy, max(2, int(inner_w * ratio)), 8)
            colour = (
                (90, 170, 100)
                if ratio >= 0.75
                else ((200, 160, 60) if ratio >= 0.45 else (200, 80, 60))
            )
            pygame.draw.rect(surface, colour, fill, border_radius=3)
            sy += 12
            limit = main_limitation(self._factors)
            if limit:
                _blit(
                    self.font_small,
                    f"Main limitation: {limit}",
                    SEVERITY_COLOUR[Severity.WARNING],
                    0,
                    sy,
                )
            else:
                _blit(
                    self.font_small,
                    "No major limitations",
                    SEVERITY_COLOUR[Severity.POSITIVE],
                    0,
                    sy,
                )
            sy += 16

        for title, sec in sections:
            rows = [f for f in self._factors if f.section == sec]
            if not rows:
                continue
            _blit(self.font, title, COLOUR_TEXT, 0, sy)
            sy += 16
            for fac in rows:
                colour = SEVERITY_COLOUR[fac.severity]
                expanded = self.expanded_factor == fac.key
                rect = pygame.Rect(view.x, sy, inner_w, ROW_H)
                accent = pygame.Rect(view.x, sy + 2, 3, ROW_H - 4)
                pygame.draw.rect(surface, colour, accent, border_radius=1)
                if expanded:
                    soft = (
                        colour[0] // 8 + 28,
                        colour[1] // 8 + 28,
                        colour[2] // 8 + 28,
                    )
                    pygame.draw.rect(surface, soft, rect, border_radius=3)
                try:
                    blit_icon(surface, fac.icon, view.x + 14, sy + ROW_H // 2, 13)
                except Exception:
                    pass
                surface.blit(
                    self.font_small.render(fac.label, True, COLOUR_TEXT),
                    (view.x + 26, sy + (ROW_H - self.font_small.get_height()) // 2),
                )
                if fac.key == "fertility":
                    mid = f"{fac.state_text}  {fac.value_text}"
                else:
                    mid = fac.state_text
                surface.blit(
                    self.font_small.render(mid, True, COLOUR_TEXT_DIM),
                    (view.x + 128, sy + (ROW_H - self.font_small.get_height()) // 2),
                )
                if fac.effect_text and fac.effect_text.startswith("+"):
                    right = f"▲ {fac.effect_text}"
                elif fac.effect_text and fac.effect_text.startswith("-"):
                    right = f"▼ {fac.effect_text}"
                elif fac.key in ("pest", "fertility") and not fac.effect_text:
                    right = "—"
                else:
                    right = fac.effect_text or fac.value_text
                rt = self.font_small.render(right, True, colour)
                surface.blit(
                    rt,
                    (
                        view.x + inner_w - rt.get_width() - 4,
                        sy + (ROW_H - rt.get_height()) // 2,
                    ),
                )
                if view.colliderect(rect):
                    self._buttons.append((f"factor_{fac.key}", rect))
                if mouse_pos is not None and rect.collidepoint(mouse_pos):
                    bits = [fac.value_text]
                    if fac.management:
                        bits.append(fac.management)
                    if fac.effect_text:
                        bits.append(f"yield {fac.effect_text}")
                    hover_tip = " · ".join(bits)
                sy += ROW_H + 2
                if expanded:
                    inset_x = view.x + 10
                    for line in fac.detail_lines:
                        surface.blit(
                            self.font_tiny.render(line, True, COLOUR_TEXT_DIM),
                            (inset_x, sy),
                        )
                        sy += 13
                    if fac.overlay_key:
                        btn = pygame.Rect(
                            inset_x, sy, min(140, inner_w - 16), BTN_H - 2
                        )
                        hovered = (
                            mouse_pos is not None and btn.collidepoint(mouse_pos)
                        )
                        self._draw_btn(surface, btn, "Show layer", hovered)
                        if view.colliderect(btn):
                            self._buttons.append(
                                (f"overlay_{fac.overlay_key}", btn)
                            )
                        sy += BTN_H
                    sy += 2
            sy += 4

        if summary is not None and summary.tile_count > 0:
            sy = self._draw_why_block(surface, view.x, sy, inner_w)

        map_label = "Hide yield map" if yield_map_active else "Show yield map"
        map_rect = pygame.Rect(view.x, sy, min(150, inner_w), BTN_H)
        hovered = mouse_pos is not None and map_rect.collidepoint(mouse_pos)
        self._draw_btn(surface, map_rect, map_label, yield_map_active or hovered)
        if view.colliderect(map_rect):
            self._buttons.append(("show_yield_map", map_rect))
        sy += BTN_H + 4
        fence_rect = pygame.Rect(view.x, sy, min(190, inner_w), BTN_H)
        planned = bool(building.fence_edges or building.fence_gates)
        fence_label = "Add / place gates" if planned else "Add field fencing"
        hovered = mouse_pos is not None and fence_rect.collidepoint(mouse_pos)
        self._draw_btn(surface, fence_rect, fence_label, hovered)
        if view.colliderect(fence_rect):
            self._buttons.append(("add_fence", fence_rect))

        surface.set_clip(old)

        if max_scroll > 0:
            track = pygame.Rect(view.right - 4, view.y, 3, view.h)
            pygame.draw.rect(surface, (50, 52, 58), track, border_radius=2)
            thumb_h = max(16, int(view.h * view.h / max(1, self._content_h)))
            thumb_y = view.y + int((view.h - thumb_h) * (self._scroll / max_scroll))
            pygame.draw.rect(
                surface,
                COLOUR_TOOLBAR_BORDER,
                pygame.Rect(track.x, thumb_y, 3, thumb_h),
                border_radius=2,
            )
        return hover_tip

    def _draw_why_block(
        self, surface: pygame.Surface, x: int, y: int, inner_w: int
    ) -> int:
        summary = self._yield_summary
        base = float(summary.base_per_tile) if summary is not None else float(
            (self._env_status or {}).get("base_yield") or 0
        )
        mean = summary.mean_unrounded if summary is not None else base
        after_land = (
            summary.mean_after_landscape if summary is not None else mean
        )
        after_crop = (
            summary.mean_after_crop_condition if summary is not None else mean
        )
        surface.blit(
            self.font.render("YIELD BREAKDOWN", True, COLOUR_TEXT),
            (x, y),
        )
        y += 16
        stages = [
            ("Base potential", None, base),
            ("Landscape", stage_effect_pct(base, after_land), after_land),
            ("Crop condition", stage_effect_pct(after_land, after_crop), after_crop),
            ("Soil", stage_effect_pct(after_crop, mean), mean),
        ]
        for label, delta, val in stages:
            left = self.font_small.render(label, True, COLOUR_TEXT_DIM)
            surface.blit(left, (x, y))
            if delta:
                mid = self.font_small.render(delta, True, COLOUR_TEXT_DIM)
                surface.blit(mid, (x + 130, y))
            right = self.font_small.render(f"{val:5.1f}", True, COLOUR_TEXT)
            surface.blit(right, (x + inner_w - right.get_width(), y))
            y += 14
        if getattr(self, "_debug", False) and self._env_status:
            y += 4
            surface.blit(
                self.font_tiny.render("DEBUG multipliers", True, COLOUR_TEXT_DIM),
                (x, y),
            )
            y += 14
            st = self._env_status
            dbg = (
                f"pest={float(st.get('pest_mult') or 0):.3f}(info)  "
                f"health={float(st.get('health') or 0):.3f}  "
                f"poll={float(st.get('poll_mult') or 0):.3f}"
            )
            surface.blit(self.font_tiny.render(dbg, True, COLOUR_TEXT_DIM), (x, y))
            y += 12
            fert = float(st.get("fertility") or 0)
            pot = float(st.get("fertility_potential") or fert or 1)
            dbg2 = (
                f"ecology={float(st.get('ecology') or 0):.3f}  "
                f"fert={fert:.3f}/{pot:.3f}  "
                f"weed={float(st.get('weed_mult') or 0):.3f}"
            )
            surface.blit(self.font_tiny.render(dbg2, True, COLOUR_TEXT_DIM), (x, y))
            y += 14
        y += 6
        return y

    def _draw_rotation(
        self,
        surface: pygame.Surface,
        building: Building,
        *,
        x: int,
        y: int,
        inner_w: int,
        mouse_pos: tuple[int, int] | None,
        current_season: Season,
    ) -> None:
        fonts = self._fonts()
        y = draw_crop_overview(
            surface,
            x,
            y,
            inner_w,
            self._crop_overview,
            current_season,
            fonts=fonts,
            empty_label="No crop plans on this field",
            title="ROTATION PLAN",
        )
        if self._env_status:
            fert = float(self._env_status.get("fertility") or 0.0)
            pot = float(self._env_status.get("fertility_potential") or fert or 1.0)
            surface.blit(
                self.font_small.render(
                    f"Current fertility  {fert:.2f} / {pot:.2f}",
                    True,
                    COLOUR_TEXT_DIM,
                ),
                (x, y),
            )
            y += 16
            crop = CROP_BY_KEY.get(self.crop_kind)
            effect = getattr(crop, "fertility_effect", None) if crop else None
            if effect is not None:
                projected = max(0.0, min(1.0, fert + float(effect)))
                surface.blit(
                    self.font_small.render(
                        f"Selected: {crop.label}  fertility {float(effect):+.2f}",
                        True,
                        COLOUR_TEXT,
                    ),
                    (x, y),
                )
                y += 14
                surface.blit(
                    self.font_small.render(
                        f"Projected after crop  {projected:.2f}",
                        True,
                        COLOUR_TEXT_DIM,
                    ),
                    (x, y),
                )
                y += 16
            else:
                surface.blit(
                    self.font_tiny.render(
                        "Crop fertility effects: awaiting crop data (not active yet).",
                        True,
                        COLOUR_TEXT_DIM,
                    ),
                    (x, y),
                )
                y += 14

        # Season row
        sx = x
        for season in SEASON_ORDER:
            label = SEASON_LABELS[season][:3]
            w = max(44, 10 + self.font_small.size(label)[0])
            rect = pygame.Rect(sx, y, w, BTN_H)
            self._draw_btn(surface, rect, label, season == self.season)
            self._buttons.append((f"season_{season.name}", rect))
            sx += w + 4
        ax = x + inner_w
        for label, action in (("Clr plans", "clear_plans"), ("Delete", "delete_field")):
            w = max(56, 10 + self.font_small.size(label)[0])
            ax -= w
            rect = pygame.Rect(ax, y, w, BTN_H)
            self._draw_btn(surface, rect, label, False)
            self._buttons.append((action, rect))
            ax -= 4
        y += BTN_H + 6

        options = crop_for_season(self.season)
        cx = x
        if not options:
            surface.blit(
                self.font_small.render(
                    "No plantable crops this season", True, COLOUR_TEXT_DIM
                ),
                (x, y + 4),
            )
            y += BTN_H + 4
        else:
            for crop in options:
                label = crop.label[:6]
                w = max(44, 10 + self.font_small.size(label)[0])
                if cx > x and cx + w > x + inner_w:
                    y += BTN_H + 4
                    cx = x
                rect = pygame.Rect(cx, y, w, BTN_H)
                self._draw_btn(surface, rect, label, crop.key == self.crop_kind)
                self._buttons.append((f"crop_{crop.key}", rect))
                cx += w + 4
            y += BTN_H + 8

        pw, ph = max(1, building.plot_w), max(1, building.plot_h)
        cell = self._cell_px
        grid_w, grid_h = pw * cell, ph * cell
        gx = x + max(0, (inner_w - grid_w) // 2)
        gy = y
        self._grid_origin = (gx, gy)

        sel: tuple[int, int, int, int] | None = None
        if self._drag_start is not None and self._drag_current is not None:
            sx0, sy0 = self._drag_start
            cx0, cy0 = self._drag_current
            sel = (min(sx0, cx0), min(sy0, cy0), max(sx0, cx0), max(sy0, cy0))

        for ly in range(ph):
            for lx in range(pw):
                wx, wy = building.x + lx, building.y + ly
                rect = pygame.Rect(gx + lx * cell, gy + ly * cell, cell, cell)
                harvest_crop = None
                plant_crop = None
                grow_crop = None
                for plan in building.plans_covering(wx, wy):
                    crop = CROP_BY_KEY.get(plan.crop_kind, CROP_BY_KEY["sage"])
                    phase = phase_for_crop(crop, self.season)
                    if phase_allows_harvest(phase):
                        harvest_crop = crop
                    if phase_allows_plough_plant(phase):
                        plant_crop = crop
                    if phase == SeasonPhase.GROW:
                        grow_crop = crop
                if harvest_crop is not None and plant_crop is not None:
                    self._paint_split_cell(surface, rect, harvest_crop, plant_crop)
                elif harvest_crop is not None:
                    self._paint_cell(surface, rect, harvest_crop, SeasonPhase.HARVEST)
                elif plant_crop is not None:
                    self._paint_cell(
                        surface, rect, plant_crop, SeasonPhase.PLOUGH_PLANT
                    )
                elif grow_crop is not None:
                    self._paint_cell(surface, rect, grow_crop, SeasonPhase.GROW)
                else:
                    pygame.draw.rect(surface, (55, 58, 64), rect)
                if sel is not None and sel[0] <= lx <= sel[2] and sel[1] <= ly <= sel[3]:
                    preview = pygame.Surface((cell, cell), pygame.SRCALPHA)
                    preview.fill((*PLAN_COLOUR_PLANT, 160))
                    surface.blit(preview, rect.topleft)
                    crop = CROP_BY_KEY.get(self.crop_kind, CROP_BY_KEY["sage"])
                    _draw_crop_glyph(
                        surface,
                        rect.centerx,
                        rect.centery,
                        crop.stem_colour,
                        crop.flower_colour,
                        scale=cell / 24,
                        icon_base=crop.plant_icon(),
                    )
                pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, rect, 1)

        tip = (
            f"{SEASON_LABELS[self.season]} — "
            + (
                f"drag to plant {CROP_BY_KEY.get(self.crop_kind, CROP_BY_KEY['sage']).label}"
                if options
                else "switch season to plant"
            )
        )
        surface.blit(
            self.font_small.render(tip, True, COLOUR_TEXT_DIM),
            (x, gy + grid_h + 6),
        )

    def _paint_split_cell(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        harvest_crop,
        plant_crop,
    ) -> None:
        tl = (rect.left, rect.top)
        tr = (rect.right, rect.top)
        br = (rect.right, rect.bottom)
        bl = (rect.left, rect.bottom)
        pygame.draw.polygon(surface, PLAN_COLOUR_HARVEST, [tl, tr, bl])
        pygame.draw.polygon(surface, PLAN_COLOUR_PLANT, [tr, br, bl])
        _draw_crop_glyph(
            surface,
            rect.left + rect.w // 3,
            rect.top + rect.h // 3,
            harvest_crop.stem_colour,
            harvest_crop.flower_colour,
            scale=rect.w / 28,
            icon_base=harvest_crop.plant_icon(),
        )
        _draw_crop_glyph(
            surface,
            rect.left + 2 * rect.w // 3,
            rect.top + 2 * rect.h // 3,
            plant_crop.stem_colour,
            plant_crop.flower_colour,
            scale=rect.w / 28,
            icon_base=plant_crop.plant_icon(),
        )

    def _paint_cell(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        crop,
        phase: SeasonPhase,
    ) -> None:
        if phase == SeasonPhase.FALLOW:
            pygame.draw.rect(surface, (55, 58, 64), rect)
            return
        if phase == SeasonPhase.HARVEST_PLOUGH_PLANT:
            self._paint_split_cell(surface, rect, crop, crop)
            return
        if phase_allows_harvest(phase):
            colour = PLAN_COLOUR_HARVEST
        elif phase_allows_plough_plant(phase):
            colour = PLAN_COLOUR_PLANT
        else:
            colour = PLAN_COLOUR_GROW
        pygame.draw.rect(surface, colour, rect)
        _draw_crop_glyph(
            surface,
            rect.centerx,
            rect.centery,
            crop.stem_colour,
            crop.flower_colour,
            scale=rect.w / 24,
            icon_base=crop.plant_icon(),
        )

    def _draw_btn(
        self, surface: pygame.Surface, rect: pygame.Rect, label: str, active: bool
    ) -> None:
        colour = COLOUR_TOOLBAR_BTN_ACTIVE if active else COLOUR_TOOLBAR_BTN
        pygame.draw.rect(surface, colour, rect, border_radius=4)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, rect, 1, border_radius=4)
        text = self.font_small.render(label, True, COLOUR_TEXT)
        surface.blit(
            text,
            (rect.centerx - text.get_width() // 2, rect.centery - text.get_height() // 2),
        )
