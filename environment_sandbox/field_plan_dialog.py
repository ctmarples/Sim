"""Floating in-game building editor window (Field crop plans for now)."""

from __future__ import annotations

import pygame

from crops import (
    CROP_BY_KEY,
    PLAN_COLOUR_GROW,
    PLAN_COLOUR_HARVEST,
    PLAN_COLOUR_PLANT,
    SeasonPhase,
    crop_for_season,
    phase_allows_harvest,
    phase_allows_plough_plant,
    phase_for_crop,
)
from entities import Building, BuildingKind
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
    """Movable floating editor for a Field building. Does not dim or block the map."""

    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 14)
        self.font_small = pygame.font.SysFont("menlo", 12)
        self.building_id: int | None = None
        self.season: Season = Season.SPRING
        self.crop_kind: str = "sage"
        self._drag_start: tuple[int, int] | None = None  # local grid coords
        self._drag_current: tuple[int, int] | None = None
        self._buttons: list[tuple[str, pygame.Rect]] = []
        self._grid_origin = (0, 0)
        self._cell_px = 24
        self._result: str | None = None
        self._pending_plan: tuple[int, int, int, int, str] | None = None
        # Floating window position (top-left of panel).
        self._panel_x = 80
        self._panel_y = MAP_OFFSET_Y + 40
        self._panel_w = 420
        self._panel_h = 280
        self._moving = False
        self._move_offset = (0, 0)
        self._close_rect = pygame.Rect(0, 0, 0, 0)
        self._title_rect = pygame.Rect(0, 0, 0, 0)

    @property
    def open(self) -> bool:
        return self.building_id is not None

    def open_for(self, building: Building, *, season: Season | None = None) -> None:
        if building.kind != BuildingKind.FIELD:
            return
        self.building_id = building.id
        self.season = season or Season.SPRING
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
        self._moving = False
        self._layout_for(building)
        # Place near the field on the map when possible.
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
        self._result = "closed"

    def take_result(self) -> str | None:
        result = self._result
        self._result = None
        return result

    def take_pending_plan(self) -> tuple[int, int, int, int, str] | None:
        plan = self._pending_plan
        self._pending_plan = None
        return plan

    def panel_rect(self) -> pygame.Rect:
        return pygame.Rect(self._panel_x, self._panel_y, self._panel_w, self._panel_h)

    def contains(self, pos: tuple[int, int]) -> bool:
        return self.open and self.panel_rect().collidepoint(pos)

    def _layout_for(self, building: Building) -> None:
        pw, ph = max(1, building.plot_w), max(1, building.plot_h)
        max_grid_w = min(WINDOW_WIDTH - 60, 560)
        max_grid_h = min(WINDOW_HEIGHT - 220, 420)
        cell = min(28, max(12, max_grid_w // pw), max(12, max_grid_h // ph))
        self._cell_px = cell
        grid_w = pw * cell
        grid_h = ph * cell
        # Title + seasons + crops (up to 2 wrap rows) + grid + tip + crop counts + padding.
        crop_rows = self._crop_row_count(max(420, grid_w + PAD * 2))
        chrome = TITLE_BAR_H + PAD + BTN_H + 6 + crop_rows * (BTN_H + 4) + 8 + 22 + 18 + PAD
        self._panel_w = max(420, grid_w + PAD * 2)
        self._panel_h = chrome + grid_h

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
        """Return True if consumed. Esc closes; other keys pass through."""
        if not self.open:
            return False
        if event.key == pygame.K_ESCAPE:
            self.close()
            return True
        return False

    def handle_mousedown(self, pos: tuple[int, int], building: Building | None) -> bool:
        """Return True if the event was consumed by this window."""
        if not self.open or building is None or not self.contains(pos):
            return False
        # Close button
        if self._close_rect.collidepoint(pos):
            self.close()
            return True
        # Title bar drag
        if self._title_rect.collidepoint(pos):
            self._moving = True
            self._move_offset = (pos[0] - self._panel_x, pos[1] - self._panel_y)
            return True
        for action, rect in self._buttons:
            if rect.collidepoint(pos):
                self._on_action(action, building)
                return True
        local = self._pos_to_local(pos, building)
        if local is not None and crop_for_season(self.season):
            self._drag_start = local
            self._drag_current = local
        return True

    def handle_mousemotion(self, pos: tuple[int, int], building: Building | None) -> bool:
        if not self.open:
            return False
        if self._moving:
            self._panel_x = pos[0] - self._move_offset[0]
            self._panel_y = pos[1] - self._move_offset[1]
            self._clamp_panel()
            return True
        if self._drag_start is None or building is None:
            return False
        local = self._pos_to_local(pos, building)
        if local is not None:
            self._drag_current = local
        return True

    def handle_mouseup(self, pos: tuple[int, int], building: Building | None) -> bool:
        if not self.open:
            return False
        if self._moving:
            self._moving = False
            self._clamp_panel()
            return True
        if self._drag_start is None:
            return self.contains(pos)
        if building is None:
            self._drag_start = None
            self._drag_current = None
            return True
        end = self._pos_to_local(pos, building) or self._drag_current or self._drag_start
        start = self._drag_start
        self._drag_start = None
        self._drag_current = None
        if start is None or end is None or not crop_for_season(self.season):
            return True
        lx0, ly0 = min(start[0], end[0]), min(start[1], end[1])
        lx1, ly1 = max(start[0], end[0]), max(start[1], end[1])
        self._pending_plan = (
            building.x + lx0,
            building.y + ly0,
            building.x + lx1,
            building.y + ly1,
            self.crop_kind,
        )
        return True

    def _on_action(self, action: str, building: Building) -> None:
        if action == "close":
            self.close()
        elif action == "clear_plans":
            self._result = "cleared"
        elif action == "delete_field":
            self._result = "deleted"
            self.building_id = None
        elif action.startswith("season_"):
            try:
                self.season = Season[action[len("season_") :]]
            except KeyError:
                return
            options = crop_for_season(self.season)
            if options and self.crop_kind not in {c.key for c in options}:
                self.crop_kind = options[0].key
            self._layout_for(building)
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

    def draw(
        self,
        surface: pygame.Surface,
        building: Building | None,
        *,
        crop_counts: dict[str, int] | None = None,
    ) -> None:
        if not self.open or building is None or building.kind != BuildingKind.FIELD:
            return
        self._layout_for(building)
        self._clamp_panel()
        panel = self.panel_rect()

        # Soft drop shadow (no full-screen dim).
        shadow = panel.move(3, 4)
        sh = pygame.Surface((shadow.w, shadow.h), pygame.SRCALPHA)
        sh.fill((0, 0, 0, 70))
        surface.blit(sh, shadow.topleft)

        pygame.draw.rect(surface, COLOUR_MENU_BG, panel, border_radius=6)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, panel, 2, border_radius=6)

        # Title bar
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
        # X close
        self._close_rect = pygame.Rect(panel.right - 28, panel.y + 4, 22, 20)
        hover = self._close_rect.collidepoint(pygame.mouse.get_pos())
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
        y = panel.y + TITLE_BAR_H + PAD
        inner_left = panel.x + PAD
        inner_right = panel.right - PAD

        # Season row
        x = inner_left
        for season in SEASON_ORDER:
            label = SEASON_LABELS[season][:3]
            w = max(44, 10 + self.font_small.size(label)[0])
            rect = pygame.Rect(x, y, w, BTN_H)
            self._draw_btn(surface, rect, label, season == self.season)
            self._buttons.append((f"season_{season.name}", rect))
            x += w + 4

        # Utility actions on the season row (right-aligned)
        ax = inner_right
        for label, action in (("Clr plans", "clear_plans"), ("Delete", "delete_field")):
            w = max(56, 10 + self.font_small.size(label)[0])
            ax -= w
            rect = pygame.Rect(ax, y, w, BTN_H)
            self._draw_btn(surface, rect, label, False)
            self._buttons.append((action, rect))
            ax -= 4

        # Crop row(s) below seasons
        y += BTN_H + 6
        options = crop_for_season(self.season)
        x = inner_left
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
                if x > inner_left and x + w > inner_right:
                    y += BTN_H + 4
                    x = inner_left
                rect = pygame.Rect(x, y, w, BTN_H)
                self._draw_btn(surface, rect, label, crop.key == self.crop_kind)
                self._buttons.append((f"crop_{crop.key}", rect))
                x += w + 4
            y += BTN_H + 8

        # Grid
        pw, ph = max(1, building.plot_w), max(1, building.plot_h)
        cell = self._cell_px
        grid_w, grid_h = pw * cell, ph * cell
        gx = panel.x + (panel.w - grid_w) // 2
        gy = y
        self._grid_origin = (gx, gy)

        sel: tuple[int, int, int, int] | None = None
        if self._drag_start is not None and self._drag_current is not None:
            sx, sy = self._drag_start
            cx, cy = self._drag_current
            sel = (min(sx, cx), min(sy, cy), max(sx, cx), max(sy, cy))

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
                    self._paint_cell(
                        surface, rect, harvest_crop, SeasonPhase.HARVEST
                    )
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
            (panel.x + PAD, gy + grid_h + 6),
        )
        counts = crop_counts or {}
        if counts:
            parts = []
            for key, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
                crop = CROP_BY_KEY.get(key)
                label = crop.label if crop else key
                parts.append(f"{n} {label}")
            count_line = "On field: " + ", ".join(parts)
        else:
            count_line = "On field: none"
        surface.blit(
            self.font_small.render(count_line, True, COLOUR_TEXT),
            (panel.x + PAD, gy + grid_h + 22),
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
                crop.stem_colour,
                crop.flower_colour,
                scale=rect.w / 28,
                icon_base=crop.plant_icon(),
            )
            _draw_crop_glyph(
                surface,
                rect.left + 2 * rect.w // 3,
                rect.top + 2 * rect.h // 3,
                crop.stem_colour,
                crop.flower_colour,
                scale=rect.w / 28,
                icon_base=crop.plant_icon(),
            )
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
