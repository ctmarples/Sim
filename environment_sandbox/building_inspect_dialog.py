"""Floating inspection window for workplace buildings (not Fields).

Storage is always a grid. The player inventory grid is only shown when the
menu was opened while the player stands on the building (transfer mode).
"""

from __future__ import annotations

from pathlib import Path

import pygame

from entities import (
    BUILDING_LABELS,
    TASK_LABELS,
    WORK_MODE_LABELS,
    Building,
    BuildingKind,
    Inventory,
    TaskType,
    Villager,
)
from icons import ICON_AXE, ICON_SAPLING_CONE, ICON_TREE_ROUND, blit_icon
from inventory_ui import (
    GRID_CELL,
    GRID_GAP,
    INV_PANEL_GAP,
    draw_inv_grid,
    draw_item_tooltip,
    draw_resource_cell,
    grid_height,
    present_keys,
)
from seasons import Season
from settings import (
    COLOUR_MENU_BG,
    COLOUR_SELECTED_ENTITY,
    COLOUR_TEXT,
    COLOUR_TEXT_DIM,
    COLOUR_TOOLBAR_BORDER,
    COLOUR_TOOLBAR_BTN,
    COLOUR_TOOLBAR_BTN_ACTIVE,
    COLOUR_TOOLBAR_BTN_HOVER,
    MAP_OFFSET_Y,
    MAX_VILLAGERS,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    map_view_width,
)
from society import housing_beds_of, housing_level_of, is_housing_kind

TITLE_BAR_H = 28
COLOUR_TEXT = (72, 48, 31)
COLOUR_TEXT_DIM = (112, 84, 58)
_BOOK_FONT_PATH = (
    Path(__file__).resolve().parent
    / "assets/fonts/Gloria_Hallelujah/GloriaHallelujah-Regular.ttf"
)
PAD = 12
BTN_H = 24
ROW_H = 22
RECIPE_OUT_CELL = 56  # room for Max / Sto labels like market supply cells
RECIPE_ROW_H = RECIPE_OUT_CELL + 14
# Extra gap so collection priority badges sit outside the icon (top-right).
GATHER_PRIO_GAP = 18
GATHER_CELL_STRIDE = RECIPE_OUT_CELL + GATHER_PRIO_GAP
SECTION_GAP = 10
SCROLL_IMPULSE = 760.0
SCROLL_FRICTION = 8.5
# Visible size before a section starts scrolling.
MAX_RECIPE_VIEW_H = 3 * RECIPE_ROW_H
MAX_GATHER_VIEW_H = 2 * (RECIPE_OUT_CELL + GRID_GAP) - GRID_GAP
MAX_CAP_VIEW_H = 2 * (GRID_CELL + GRID_GAP) - GRID_GAP
MAX_WORKER_VIEW_H = 4 * (ROW_H + 2)


class BuildingInspectDialog:
    """Movable floating inspector: options, workers, inventory grid(s)."""

    def __init__(self) -> None:
        self.font = pygame.font.Font(str(_BOOK_FONT_PATH), 14)
        self.font_small = pygame.font.Font(str(_BOOK_FONT_PATH), 12)
        self.font_tiny = pygame.font.Font(str(_BOOK_FONT_PATH), 11)
        self.font_title = pygame.font.Font(str(_BOOK_FONT_PATH), 15)
        self.building_id: int | None = None
        self.show_player: bool = False
        self.allow_player_craft: bool = False
        self._buttons: list[tuple[str, pygame.Rect]] = []
        self._worker_hits: list[tuple[pygame.Rect, int]] = []
        self._inv_hits: list[tuple[pygame.Rect, str, str]] = []
        self._inv_tip_hits: list[tuple[pygame.Rect, str, str]] = []
        self._pending_action: str | None = None
        self._panel_x = 80
        self._panel_y = MAP_OFFSET_Y + 40
        self._panel_w = 300
        self._panel_h = 320
        self._moving = False
        self._move_offset = (0, 0)
        self._close_rect = pygame.Rect(0, 0, 0, 0)
        self._title_rect = pygame.Rect(0, 0, 0, 0)
        self._hover_worker: int | None = None
        self._hover_inv: tuple[str, str] | None = None
        self._tooltip_key: str | None = None
        self.selected_cap_key: str | None = None
        self.selected_min_key: str | None = None
        self.selected_market_supply_key: str | None = None
        self.caps_expanded: bool = False
        self.mins_expanded: bool = False
        self.market_demand_expanded: bool = True
        self.market_supply_expanded: bool = True
        self.market_supply_group: str = "food"
        # Active category tab for craft recipes (kitchen stews/grill/…); None = auto.
        self.recipe_category_tab: str | None = None
        self._scroll: dict[str, float] = {}
        self._scroll_velocity: dict[str, float] = {}
        self._scroll_tick = pygame.time.get_ticks()
        self._measured_body_h = 0
        # name → (view_rect, content_h, view_h) rebuilt each draw.
        self._scroll_areas: dict[str, tuple[pygame.Rect, int, int]] = {}
        self.embedded = False

    def configure_embed(self, rect: pygame.Rect) -> None:
        """Draw as an embedded pane (no close/drag chrome)."""
        self.embedded = True
        self._panel_x = rect.x
        self._panel_y = rect.y
        self._panel_w = max(120, rect.w)
        self._panel_h = max(120, rect.h)

    @property
    def open(self) -> bool:
        return self.building_id is not None

    def open_for(
        self,
        building: Building,
        *,
        screen_xy: tuple[int, int] | None = None,
        show_player: bool = False,
    ) -> None:
        if building.is_field_plot:
            return
        self.building_id = building.id
        self.allow_player_craft = bool(show_player)
        self.show_player = show_player and bool(building.depositable_keys())
        self._pending_action = None
        self._moving = False
        self._hover_worker = None
        self._hover_inv = None
        self._tooltip_key = None
        self.selected_cap_key = None
        self.selected_min_key = None
        self.selected_market_supply_key = None
        self._scroll = {}
        self._scroll_velocity = {}
        self._scroll_tick = pygame.time.get_ticks()
        self._measured_body_h = 0
        self._scroll_areas = {}
        self._layout(building)
        map_w = map_view_width()
        if screen_xy is not None:
            prefer_x = screen_xy[0] + 24
            prefer_y = max(MAP_OFFSET_Y, screen_xy[1])
        else:
            prefer_x = 80
            prefer_y = MAP_OFFSET_Y + 40
        if prefer_x + self._panel_w > map_w - 8:
            prefer_x = max(8, (screen_xy[0] if screen_xy else 80) - self._panel_w - 16)
        self._panel_x = prefer_x
        self._panel_y = prefer_y
        self._clamp_panel()

    def close(self) -> None:
        self.building_id = None
        self.show_player = False
        self.allow_player_craft = False
        self.embedded = False
        self._moving = False
        self._pending_action = None
        self._hover_worker = None
        self._hover_inv = None
        self._tooltip_key = None
        self.selected_cap_key = None
        self.selected_min_key = None
        self.selected_market_supply_key = None
        self._scroll = {}
        self._scroll_velocity = {}
        self._scroll_areas = {}

    def take_action(self) -> str | None:
        action = self._pending_action
        self._pending_action = None
        return action

    def panel_rect(self) -> pygame.Rect:
        return pygame.Rect(self._panel_x, self._panel_y, self._panel_w, self._panel_h)

    def contains(self, pos: tuple[int, int]) -> bool:
        return self.open and self.panel_rect().collidepoint(pos)

    def _has_storage(self, building: Building) -> bool:
        return bool(building.depositable_keys())

    def _supports_item_caps(self, building: Building) -> bool:
        return (
            building.kind
            not in (
                BuildingKind.HOME,
                BuildingKind.WORKSTATION,
                BuildingKind.FIELD,
                BuildingKind.MARKET,
            )
            and bool(building.depositable_keys())
        )

    def _scroll_value(self, name: str, content_h: int, view_h: int) -> float:
        max_s = max(0, content_h - view_h)
        value = max(0.0, min(float(self._scroll.get(name, 0.0)), float(max_s)))
        self._scroll[name] = value
        return value

    def _advance_scroll(self) -> None:
        """Integrate wheel velocity for smooth, pixel-based momentum."""
        now = pygame.time.get_ticks()
        dt = min(0.05, max(0.0, (now - self._scroll_tick) / 1000.0))
        self._scroll_tick = now
        decay = max(0.0, 1.0 - SCROLL_FRICTION * dt)
        for name, velocity in list(self._scroll_velocity.items()):
            area = self._scroll_areas.get(name)
            if area is None:
                continue
            _rect, content_h, view_h = area
            before = self._scroll_value(name, content_h, view_h)
            self._scroll[name] = before + velocity * dt
            after = self._scroll_value(name, content_h, view_h)
            velocity *= decay
            if after == before and (after <= 0 or after >= content_h - view_h):
                velocity = 0.0
            self._scroll_velocity[name] = 0.0 if abs(velocity) < 4.0 else velocity

    def _register_scroll(
        self, name: str, view: pygame.Rect, content_h: int, view_h: int
    ) -> float:
        scroll = self._scroll_value(name, content_h, view_h)
        self._scroll_areas[name] = (view, content_h, view_h)
        return scroll

    def _draw_scrollbar(
        self,
        surface: pygame.Surface,
        view: pygame.Rect,
        content_h: int,
        scroll: int,
    ) -> None:
        if content_h <= view.h:
            return
        track = pygame.Rect(view.right - 5, view.y, 4, view.h)
        pygame.draw.rect(surface, (40, 42, 48), track, border_radius=2)
        ratio = view.h / content_h
        thumb_h = max(12, int(view.h * ratio))
        thumb_y = view.y + int((view.h - thumb_h) * (scroll / max(1, content_h - view.h)))
        pygame.draw.rect(
            surface,
            (120, 130, 140),
            pygame.Rect(track.x, thumb_y, track.w, thumb_h),
            border_radius=2,
        )

    def handle_mousewheel(self, dy: int, pos: tuple[int, int]) -> bool:
        """Scroll the section under the cursor. Returns True if the event is consumed."""
        if not self.open or not self.contains(pos):
            return False
        for name, (rect, content_h, view_h) in self._scroll_areas.items():
            if name == "panel_body":
                continue
            if content_h <= view_h:
                continue
            if rect.collidepoint(pos):
                self._scroll_velocity[name] = self._scroll_velocity.get(name, 0.0) - float(dy) * SCROLL_IMPULSE
                return True
        panel = self._scroll_areas.get("panel_body")
        if panel is not None:
            rect, content_h, view_h = panel
            if content_h > view_h:
                self._scroll_velocity["panel_body"] = self._scroll_velocity.get("panel_body", 0.0) - float(dy) * SCROLL_IMPULSE
        return True

    def _layout(self, building: Building | None = None) -> None:
        if building is not None and self.show_player and self._has_storage(building):
            self._panel_w = 520
        else:
            self._panel_w = 300
        self._panel_h = TITLE_BAR_H + PAD + 120 + 8 * ROW_H + 100

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

    def handle_mousedown(self, pos: tuple[int, int]) -> bool:
        if not self.open or not self.contains(pos):
            return False
        if self._close_rect.collidepoint(pos):
            self.close()
            return True
        if not self.embedded and self._title_rect.collidepoint(pos):
            self._moving = True
            self._move_offset = (pos[0] - self._panel_x, pos[1] - self._panel_y)
            return True
        for action, rect in reversed(self._buttons):
            if rect.collidepoint(pos):
                self._pending_action = action
                return True
        for rect, vid in self._worker_hits:
            if rect.collidepoint(pos):
                self._pending_action = f"select_worker:{vid}"
                return True
        for rect, side, key in reversed(self._inv_hits):
            if rect.collidepoint(pos):
                if side == "cap":
                    self._pending_action = f"edit_item_cap:{key}"
                elif side == "min":
                    self._pending_action = f"edit_item_reserve:{key}"
                elif side == "storage":
                    if self.show_player:
                        self._pending_action = f"xfer_to_player:{key}"
                    else:
                        self._pending_action = f"select_cap:{key}"
                else:
                    self._pending_action = f"xfer_to_storage:{key}"
                return True
        return True

    def _craft_recipes_block_height(
        self, recipes: tuple, *, player_craft: bool = False
    ) -> int:
        if not recipes:
            return 0
        from recipes import recipes_by_category

        row_h = RECIPE_ROW_H + (BTN_H + 4 if player_craft else 0)
        groups = recipes_by_category(recipes)
        show_tabs = len(groups) > 1 or (groups and groups[0][0] is not None)
        if show_tabs:
            active = self._active_recipe_category(recipes)
            visible = next((g for c, g in groups if c == active), groups[0][1])
            tab_h = BTN_H + 6
        else:
            visible = list(recipes)
            tab_h = 0
        content_h = len(visible) * row_h
        max_h = MAX_RECIPE_VIEW_H + (BTN_H + 4 if player_craft else 0)
        return 18 + tab_h + min(content_h, max_h) + SECTION_GAP

    def _recipe_category_tabs(self, recipes: tuple) -> list[str | None]:
        from recipes import recipes_by_category

        return [cat for cat, _ in recipes_by_category(recipes)]

    def _active_recipe_category(self, recipes: tuple) -> str | None:
        tabs = self._recipe_category_tabs(recipes)
        if not tabs:
            return None
        if self.recipe_category_tab in tabs:
            return self.recipe_category_tab
        return tabs[0]

    def _recipe_output_key(self, recipe) -> str | None:
        if recipe.outputs:
            return next(iter(recipe.outputs))
        return recipe.display_icon_key() or None

    def _draw_recipe_stock_cell(
        self,
        surface: pygame.Surface,
        *,
        building: Building,
        recipe,
        cell: pygame.Rect,
        mouse_pos: tuple[int, int] | None,
        view: pygame.Rect | None = None,
        stock_amounts: dict[str, int] | None = None,
    ) -> tuple[str | None, bool]:
        """Draw Max (top) / Sto (bottom) on a recipe output cell.

        Returns ``(tip_key, hovered)``. Max → production cap (∞ default when
        enabled; click to edit). Sto → total village storage count (display).
        """
        from icons import blit_icon
        from resources import resource_icon_style

        enabled = building.is_recipe_enabled(recipe.name)
        out_key = self._recipe_output_key(recipe)
        if out_key is None:
            return None, False
        hov = (
            (view is None or view.collidepoint(mouse_pos or (-1, -1)))
            and mouse_pos is not None
            and cell.collidepoint(mouse_pos)
        )
        if enabled or hov:
            bg = (40, 48, 40) if hov else (32, 38, 34)
            border = COLOUR_SELECTED_ENTITY
        elif hov:
            bg = (48, 50, 42)
            border = COLOUR_SELECTED_ENTITY
        else:
            bg = (36, 38, 42)
            border = COLOUR_TOOLBAR_BORDER
        pygame.draw.rect(surface, bg, cell, border_radius=4)
        pygame.draw.rect(surface, border, cell, 1, border_radius=4)

        cap = building.item_cap(out_key) if enabled else None
        if stock_amounts is not None:
            stock_n = int(stock_amounts.get(out_key, 0))
        else:
            stock_n = int(getattr(building, out_key, 0))
        text_col = COLOUR_TEXT if enabled else COLOUR_TEXT_DIM
        max_txt = self.font_tiny.render(
            f"Max: {'∞' if (not enabled or cap is None) else cap}", True, text_col
        )
        sto_txt = self.font_tiny.render(f"Sto: {stock_n}", True, text_col)
        max_rect = pygame.Rect(
            cell.x + 2, cell.y + 2, cell.w - 4, max_txt.get_height() + 2
        )
        surface.blit(
            max_txt,
            (cell.centerx - max_txt.get_width() // 2, max_rect.y + 1),
        )
        surface.blit(
            sto_txt,
            (
                cell.centerx - sto_txt.get_width() // 2,
                cell.bottom - sto_txt.get_height() - 3,
            ),
        )

        icon_size = max(16, cell.w - 28)
        try:
            # Prefer recipe icon_key (e.g. deer/boar) over the output stock key (meat).
            icon_key = recipe.display_icon_key() or out_key
            style = resource_icon_style(icon_key)
            blit_icon(
                surface,
                style.name,
                cell.centerx,
                cell.centery + 1,
                icon_size,
                recolour=style.recolour,
                class_scales=style.class_scales,
                omit_classes=style.omit_classes or None,
            )
        except (FileNotFoundError, OSError, ValueError, TypeError):
            pass

        if not enabled:
            overlay = pygame.Surface((cell.w, cell.h), pygame.SRCALPHA)
            overlay.fill((28, 30, 36, 110))
            surface.blit(overlay, cell.topleft)

        if view is None or cell.colliderect(view):
            # Reverse-scanned: Max edit beats the toggle. Sto is display-only.
            self._buttons.append((f"toggle_recipe:{recipe.name}", cell))
            if enabled:
                self._buttons.append((f"edit_recipe_max:{out_key}", max_rect))
            self._inv_tip_hits.append((cell, "recipe", out_key))
        return out_key, hov

    def _market_demand_block_height(
        self, *, expanded: bool, key_count: int, inner_w: int
    ) -> int:
        if key_count <= 0:
            return 18 + ROW_H + SECTION_GAP
        if not expanded:
            return BTN_H + SECTION_GAP
        cols = max(1, inner_w // (GRID_CELL + GRID_GAP))
        rows = max(1, (key_count + cols - 1) // cols)
        content = rows * (GRID_CELL + GRID_GAP) - GRID_GAP
        return BTN_H + 4 + min(content, MAX_CAP_VIEW_H) + SECTION_GAP

    def _market_supply_block_height(
        self, *, expanded: bool, key_count: int, inner_w: int
    ) -> int:
        if key_count <= 0:
            return 0
        if not expanded:
            return BTN_H + SECTION_GAP
        cell = max(GRID_CELL, 56)
        cols = max(1, inner_w // (cell + GRID_GAP))
        rows = max(1, (key_count + cols - 1) // cols)
        content = rows * (cell + GRID_GAP) - GRID_GAP
        view_h = min(content, max(MAX_CAP_VIEW_H, cell * 2 + GRID_GAP))
        return BTN_H + 4 + BTN_H + 6 + view_h + SECTION_GAP

    def _stock_limit_block_height(
        self, *, expanded: bool, key_count: int, inner_w: int
    ) -> int:
        if key_count <= 0:
            return 0
        if not expanded:
            return BTN_H + SECTION_GAP
        cols = max(1, inner_w // (GRID_CELL + GRID_GAP))
        rows = max(1, (key_count + cols - 1) // cols)
        content = rows * (GRID_CELL + GRID_GAP) - GRID_GAP
        return (
            BTN_H
            + 4
            + min(content, MAX_CAP_VIEW_H)
            + BTN_H
            + 8
            + SECTION_GAP
        )

    def _draw_section_toggle(
        self,
        surface: pygame.Surface,
        *,
        x: int,
        y: int,
        inner_w: int,
        label: str,
        expanded: bool,
        action: str,
        mouse_pos: tuple[int, int] | None,
    ) -> int:
        rect = pygame.Rect(x, y, inner_w, BTN_H)
        hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
        self._draw_button(surface, rect, f"{'▼' if expanded else '▶'} {label}", hovered=hovered)
        self._buttons.append((action, rect))
        return BTN_H + 4

    def _draw_craft_recipes(
        self,
        surface: pygame.Surface,
        *,
        building: Building,
        recipes: tuple,
        title: str,
        x: int,
        y: int,
        inner_w: int,
        mouse_pos: tuple[int, int] | None,
        fonts: tuple,
        scroll_name: str,
        show_fuel: bool = False,
        player_craft: bool = False,
        stock_amounts: dict[str, int] | None = None,
        progress_fractions: dict[str, float] | None = None,
    ) -> tuple[int, str | None]:
        """Kitchen-style recipe rows with inputs. Returns (height, hovered tip key)."""
        from inventory_ui import draw_resource_cell
        from recipes import (
            KITCHEN_FUEL_KEY,
            category_label,
            recipe_output_fits,
            recipe_ready,
            recipe_ready_with_extra,
            recipes_by_category,
        )

        if not recipes:
            return 0, None
        building.ensure_recipe_state()
        top_y = y
        surface.blit(self.font.render(title, True, COLOUR_TEXT), (x, y))
        y += 18
        row_h = RECIPE_ROW_H + (BTN_H + 4 if player_craft else 0)
        ordered = building._recipes_by_priority(recipes)
        groups = recipes_by_category(ordered)
        show_tabs = len(groups) > 1 or (groups and groups[0][0] is not None)
        if show_tabs:
            active = self._active_recipe_category(recipes)
            # Category filter tabs (same pattern as market supply).
            bx = x
            for cat in (c for c, _ in groups):
                label = category_label(cat)
                w = max(56, 12 + self.font_small.size(label)[0])
                if bx + w > x + inner_w and bx > x:
                    y += BTN_H + 4
                    bx = x
                rect = pygame.Rect(bx, y, w, BTN_H)
                is_active = cat == active
                hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
                self._draw_button(
                    surface, rect, label, hovered=hovered, active=is_active
                )
                tab_key = cat if cat is not None else ""
                self._buttons.append((f"recipe_category:{tab_key}", rect))
                bx += w + 4
            y += BTN_H + 6
            visible = next((g for c, g in groups if c == active), groups[0][1])
        else:
            visible = list(ordered)

        content_h = len(visible) * row_h
        max_view = MAX_RECIPE_VIEW_H + (BTN_H + 4 if player_craft else 0)
        view_h = min(content_h, max_view) if content_h else 0
        tip_key: str | None = None
        if view_h <= 0:
            return y - top_y + SECTION_GAP, tip_key
        view = pygame.Rect(x, y, inner_w, view_h)
        scroll = self._register_scroll(scroll_name, view, content_h, view_h)
        pygame.draw.rect(surface, (27, 30, 37), view, border_radius=4)
        old_clip = surface.get_clip()
        surface.set_clip(view.clip(old_clip) if old_clip.width else view)
        for i, recipe in enumerate(visible):
            row_y = y + i * row_h - scroll
            if row_y + row_h < view.top or row_y > view.bottom:
                continue
            enabled = building.is_recipe_enabled(recipe.name)
            priority = building.get_recipe_priority(recipe.name)
            out_cell = pygame.Rect(x, row_y, RECIPE_OUT_CELL, RECIPE_OUT_CELL)
            out_key, out_hov = self._draw_recipe_stock_cell(
                surface,
                building=building,
                recipe=recipe,
                cell=out_cell,
                mouse_pos=mouse_pos,
                view=view,
                stock_amounts=stock_amounts,
            )
            if out_hov and out_key:
                tip_key = out_key
            prio_cell = pygame.Rect(out_cell.right + 2, row_y + 2, 16, 16)
            if prio_cell.colliderect(view):
                self._draw_priority_badge(
                    surface,
                    prio_cell,
                    priority,
                    enabled=enabled,
                    hovered=(
                        mouse_pos is not None and prio_cell.collidepoint(mouse_pos)
                    ),
                )
                self._buttons.append((f"cycle_recipe_priority:{recipe.name}", prio_cell))
            ix = out_cell.right + GRID_GAP
            for out_key_extra, out_n in list(recipe.outputs.items())[1:]:
                if ix + GRID_CELL > x + inner_w:
                    break
                out_cell_extra = pygame.Rect(
                    ix,
                    row_y + (RECIPE_OUT_CELL - GRID_CELL) // 2,
                    GRID_CELL,
                    GRID_CELL,
                )
                out_hov_extra = (
                    view.collidepoint(mouse_pos or (-1, -1))
                    and mouse_pos is not None
                    and out_cell_extra.collidepoint(mouse_pos)
                )
                draw_resource_cell(
                    surface,
                    cell=out_cell_extra,
                    key=out_key_extra,
                    count=out_n,
                    fonts=fonts,
                    hovered=out_hov_extra,
                    dimmed=not enabled,
                )
                if out_cell_extra.colliderect(view):
                    self._inv_tip_hits.append((out_cell_extra, "recipe", out_key_extra))
                if out_hov_extra:
                    tip_key = out_key_extra
                ix += GRID_CELL + GRID_GAP
            if recipe.inputs:
                arrow = self.font_small.render("→", True, COLOUR_TEXT_DIM)
                if ix + arrow.get_width() + 6 + GRID_CELL <= x + inner_w:
                    surface.blit(
                        arrow,
                        (ix, row_y + (RECIPE_OUT_CELL - arrow.get_height()) // 2),
                    )
                    ix += arrow.get_width() + GRID_GAP
                for in_key, in_n in recipe.inputs.items():
                    if ix + GRID_CELL > x + inner_w:
                        break
                    in_cell = pygame.Rect(
                        ix,
                        row_y + (RECIPE_OUT_CELL - GRID_CELL) // 2,
                        GRID_CELL,
                        GRID_CELL,
                    )
                    in_hov = (
                        view.collidepoint(mouse_pos or (-1, -1))
                        and mouse_pos is not None
                        and in_cell.collidepoint(mouse_pos)
                    )
                    draw_resource_cell(
                        surface,
                        cell=in_cell,
                        key=in_key,
                        count=in_n,
                        fonts=fonts,
                        hovered=in_hov,
                        dimmed=not enabled,
                    )
                    if in_cell.colliderect(view):
                        self._inv_tip_hits.append((in_cell, "recipe", in_key))
                    if in_hov:
                        tip_key = in_key
                    ix += GRID_CELL + GRID_GAP
            if show_fuel:
                if ix + GRID_CELL > x + inner_w:
                    ix = out_cell.right + GRID_GAP
                fuel_cell = pygame.Rect(
                    ix,
                    row_y + (RECIPE_OUT_CELL - GRID_CELL) // 2,
                    GRID_CELL,
                    GRID_CELL,
                )
                fuel_hov = (
                    view.collidepoint(mouse_pos or (-1, -1))
                    and mouse_pos is not None
                    and fuel_cell.collidepoint(mouse_pos)
                )
                has_fuel = building.has_cooking_fuel()
                draw_resource_cell(
                    surface,
                    cell=fuel_cell,
                    key=KITCHEN_FUEL_KEY,
                    count=1,
                    fonts=fonts,
                    hovered=fuel_hov,
                    dimmed=not has_fuel or not enabled,
                )
                if fuel_cell.colliderect(view):
                    self._inv_tip_hits.append((fuel_cell, "recipe", KITCHEN_FUEL_KEY))
                if fuel_hov:
                    tip_key = KITCHEN_FUEL_KEY
            fill = (
                float(progress_fractions.get(recipe.name, 0.0))
                if enabled and progress_fractions is not None
                else building.recipe_progress_fraction(recipe.name) if enabled else 0.0
            )
            fill = max(0.0, min(1.0, fill))
            if player_craft:
                player_inv = getattr(self, "_draw_player_inventory", None)
                storage_amounts = getattr(self, "_draw_storage_amounts", None)
                if (
                    building.kind == BuildingKind.FARM
                    and recipe in building.addon_craft_recipes()
                    and storage_amounts is not None
                ):
                    inputs_ok = all(
                        int(storage_amounts.get(key, 0)) >= int(need)
                        for key, need in recipe.inputs.items()
                    )
                else:
                    inputs_ok = recipe_ready_with_extra(building, recipe, player_inv)
                can_craft = (
                    enabled
                    and inputs_ok
                    and recipe_output_fits(
                        building,
                        recipe,
                        capacity=building.capacity,
                        stock_amounts=stock_amounts,
                    )
                )
                if show_fuel:
                    can_craft = can_craft and building.has_cooking_fuel()
                craft_rect = pygame.Rect(
                    out_cell.x,
                    out_cell.bottom + 2,
                    max(out_cell.w, 10 + self.font_small.size("Craft")[0]),
                    BTN_H,
                )
                if craft_rect.colliderect(view):
                    hov = mouse_pos is not None and craft_rect.collidepoint(mouse_pos)
                    self._draw_button(
                        surface,
                        craft_rect,
                        "Craft",
                        active=can_craft and fill > 0,
                        hovered=hov and can_craft,
                    )
                    if not can_craft:
                        shade = pygame.Surface(
                            (craft_rect.w, craft_rect.h), pygame.SRCALPHA
                        )
                        shade.fill((30, 30, 34, 120))
                        surface.blit(shade, craft_rect.topleft)
                    self._buttons.append((f"craft_recipe:{recipe.name}", craft_rect))
            bar_x = x
            bar_y = row_y + RECIPE_OUT_CELL + (BTN_H + 6 if player_craft else 3)
            bar_w = inner_w - 8
            pygame.draw.rect(
                surface,
                (40, 40, 40),
                pygame.Rect(bar_x, bar_y, bar_w, 7),
                border_radius=2,
            )
            if fill > 0:
                fill_c = (90, 150, 200) if enabled else (70, 70, 70)
                pygame.draw.rect(
                    surface,
                    fill_c,
                    pygame.Rect(bar_x, bar_y, max(1, int(bar_w * fill)), 7),
                    border_radius=2,
                )
        surface.set_clip(old_clip)
        self._draw_scrollbar(surface, view, content_h, scroll)
        return (y - top_y) + view_h + SECTION_GAP, tip_key

    def _draw_priority_badge(
        self,
        surface: pygame.Surface,
        cell: pygame.Rect,
        priority: int,
        *,
        enabled: bool,
        hovered: bool,
    ) -> None:
        """Small clickable 1/2/3 chip (1 = highest priority)."""
        if priority <= 1:
            bg = (70, 110, 70) if enabled else (50, 55, 50)
        elif priority == 2:
            bg = (70, 80, 95) if enabled else (50, 52, 55)
        else:
            bg = (95, 75, 55) if enabled else (55, 50, 48)
        if hovered:
            bg = tuple(min(255, c + 25) for c in bg)
        pygame.draw.rect(surface, bg, cell, border_radius=3)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, cell, 1, border_radius=3)
        label = self.font_tiny.render(str(priority), True, COLOUR_TEXT if enabled else COLOUR_TEXT_DIM)
        surface.blit(
            label,
            (
                cell.centerx - label.get_width() // 2,
                cell.centery - label.get_height() // 2,
            ),
        )

    def handle_mousemotion(self, pos: tuple[int, int]) -> bool:
        if not self.open:
            return False
        if self._moving:
            self._panel_x = pos[0] - self._move_offset[0]
            self._panel_y = pos[1] - self._move_offset[1]
            self._clamp_panel()
            return True
        self._hover_worker = None
        self._hover_inv = None
        self._tooltip_key = None
        if self.contains(pos):
            for rect, vid in self._worker_hits:
                if rect.collidepoint(pos):
                    self._hover_worker = vid
                    break
            for rect, side, key in self._inv_hits:
                if rect.collidepoint(pos):
                    self._hover_inv = (side, key)
                    self._tooltip_key = key
                    break
            # Also tip on non-interactive display-only cells tracked via hover paint.
            if self._tooltip_key is None:
                for rect, side, key in getattr(self, "_inv_tip_hits", []):
                    if rect.collidepoint(pos):
                        self._tooltip_key = key
                        break
        return self.contains(pos)

    def handle_mouseup(self, pos: tuple[int, int]) -> bool:
        if not self.open:
            return False
        if self._moving:
            self._moving = False
            self._clamp_panel()
            return True
        return self.contains(pos)

    def _draw_button(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        label: str,
        *,
        active: bool = False,
        hovered: bool = False,
    ) -> None:
        if active:
            colour = COLOUR_TOOLBAR_BTN_ACTIVE
        elif hovered:
            colour = COLOUR_TOOLBAR_BTN_HOVER
        else:
            colour = COLOUR_TOOLBAR_BTN
        if not self.embedded:
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

    def _draw_icon_btn(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        *,
        icons: tuple[str, ...] = (),
        label: str | None = None,
        active: bool = False,
        hovered: bool = False,
    ) -> None:
        if active:
            colour = COLOUR_TOOLBAR_BTN_ACTIVE
        elif hovered:
            colour = COLOUR_TOOLBAR_BTN_HOVER
        else:
            colour = COLOUR_TOOLBAR_BTN
        if not self.embedded or label is None:
            pygame.draw.rect(surface, colour, rect, border_radius=4)
            pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, rect, 1, border_radius=4)
        if icons:
            pad = 4
            slot_w = max(1, (rect.w - pad * 2) // max(1, len(icons)))
            for i, icon in enumerate(icons):
                cx = rect.x + pad + slot_w * i + slot_w // 2
                blit_icon(surface, icon, cx, rect.centery, min(rect.h, slot_w) - 6)
        elif label:
            text = self.font_small.render(label, True, COLOUR_TEXT)
            surface.blit(
                text,
                (
                    rect.x + (rect.w - text.get_width()) // 2,
                    rect.y + (rect.h - text.get_height()) // 2,
                ),
            )

    def _worker_label(self, villager: Villager) -> str:
        if villager.seeking_food:
            state = "EAT"
        else:
            state = villager.state.name[:4]
        return f"#{villager.id} {state}"

    def _fonts(self) -> tuple[pygame.font.Font, pygame.font.Font, pygame.font.Font]:
        return self.font, self.font_small, self.font_tiny

    def draw(
        self,
        surface: pygame.Surface,
        building: Building | None,
        workers: list[Villager],
        *,
        selected_villager_id: int | None = None,
        mouse_pos: tuple[int, int] | None = None,
        storage_amounts: dict[str, int] | None = None,
        player_amounts: dict[str, int] | None = None,
        player_inventory: Inventory | None = None,
        hired_count: int = 0,
        hire_candidates: list | None = None,
        food_amounts: dict[str, int] | None = None,
        free_beds: int = 0,
        housing_level: int = 0,
        area_draw_task: TaskType | None = None,
        home_storage=None,
        market_offer_fn=None,
        village_stock: dict[str, int] | None = None,
        recipe_progress_fractions: dict[str, float] | None = None,
        crop_overview: list[dict] | None = None,
        env_status: dict | None = None,
        current_season: Season | None = None,
        forage_allowed_keys: frozenset[str] | None = None,
    ) -> None:
        if not self.open or building is None or building.is_field_plot:
            return
        if building.id != self.building_id:
            return
        self._forage_allowed_keys = forage_allowed_keys
        self._advance_scroll()

        self._draw_player_inventory = player_inventory
        self._draw_storage_amounts = storage_amounts
        has_storage = self._has_storage(building)
        dual = self.show_player and has_storage
        storage_keys = building.depositable_keys()
        linked_food_inventory = (
            building.linked_food_inventory()
            if building.kind in (BuildingKind.KITCHEN, BuildingKind.PANTRY, BuildingKind.CELLAR)
            else ()
        )
        linked_food_storages = tuple(b for b in linked_food_inventory if b is not building)
        if linked_food_inventory and len(linked_food_inventory) > 1 and storage_amounts is None:
            storage_keys = tuple(
                dict.fromkeys(
                    (*storage_keys, *(k for store in linked_food_inventory for k in store.depositable_keys()))
                )
            )
            storage_amounts = {
                key: sum(int(getattr(store, key, 0)) for store in linked_food_inventory)
                for key in storage_keys
            }
        if storage_amounts is not None:
            storage_keys = tuple(dict.fromkeys((*storage_keys, *storage_amounts.keys())))
        if storage_keys:
            amounts = storage_amounts or {
                k: int(getattr(building, k, 0)) for k in storage_keys
            }
            stored_total = sum(int(amounts.get(k, 0)) for k in storage_keys)
            capacity_label = (
                f"{stored_total}"
                if building.kind == BuildingKind.HOME
                else building.capacity_label()
            )
            if linked_food_storages:
                storage_used = sum(store.cargo_stored_total for store in linked_food_inventory)
                storage_capacity = sum(store.capacity for store in linked_food_inventory)
                capacity_label = (
                    f"{storage_used}/"
                    f"{storage_capacity} linked storage"
                )
        else:
            amounts = {}
            capacity_label = "—"

        if player_amounts is None and player_inventory is not None:
            from resources import amounts_from_obj

            player_amounts = amounts_from_obj(player_inventory)
        player_amounts = player_amounts or {}

        from food_spoilage import qualities_for_display

        storage_qualities = qualities_for_display(building) if has_storage else {}
        player_qualities = (
            qualities_for_display(player_inventory)
            if player_inventory is not None
            else {}
        )

        player_sub = "—"
        if player_inventory is not None:
            player_sub = (
                f"{player_inventory.cargo_total}/{player_inventory.capacity}"
                f"  seeds {player_inventory.seed_total}/{player_inventory.seed_capacity}"
            )

        candidates = list(hire_candidates or [])
        options_h = BTN_H + 8
        if building.kind == BuildingKind.WORKSTATION:
            options_h = BTN_H + 28
        elif is_housing_kind(building.kind):
            options_h = BTN_H * 2 + 28
        elif building.kind == BuildingKind.FORESTER:
            options_h = BTN_H + 28
        elif building.supported_work_modes():
            options_h = BTN_H * 2 + 12
        elif building.has_recipes():
            options_h = BTN_H + 8
        from extensions import extensions_for_parent

        if extensions_for_parent(building.kind):
            options_h += BTN_H + 8

        overview_h = 0
        if building.kind == BuildingKind.FARM:
            from crop_status_ui import env_factors_height, overview_height

            n = max(1, len(crop_overview or []))
            overview_h = overview_height(n)
            if env_status:
                overview_h += env_factors_height(356)

        gather_recipes = (
            building.known_recipes() if building.is_gather_recipe_building() else ()
        )
        if (
            building.kind == BuildingKind.FORAGER
            and getattr(self, "_forage_allowed_keys", None) is not None
        ):
            allowed = self._forage_allowed_keys
            gather_recipes = tuple(r for r in gather_recipes if r.name in allowed)
        split_recipes = (
            building.split_recipes() if building.kind == BuildingKind.FORESTER else ()
        )
        plant_recipes = (
            building.plant_recipes() if building.kind == BuildingKind.FORESTER else ()
        )
        craft_recipes = (
            building.known_recipes()
            if building.has_recipes() and not building.is_gather_recipe_building()
            else ()
        )
        if building.is_gather_recipe_building() and building.addon_craft_recipes():
            craft_recipes = building.addon_craft_recipes()
        recipes_h = 0
        if gather_recipes:
            cols = max(1, (380 - PAD * 2) // GATHER_CELL_STRIDE)
            rows = max(1, (len(gather_recipes) + cols - 1) // cols)
            content = rows * (RECIPE_OUT_CELL + GRID_GAP) - GRID_GAP
            recipes_h += 18 + min(content, MAX_GATHER_VIEW_H) + SECTION_GAP
        recipes_h += self._craft_recipes_block_height(
            split_recipes, player_craft=self.allow_player_craft
        )
        recipes_h += self._craft_recipes_block_height(
            plant_recipes, player_craft=self.allow_player_craft
        )
        recipes_h += self._craft_recipes_block_height(
            craft_recipes, player_craft=self.allow_player_craft
        )

        storage_items = len(present_keys(amounts, storage_keys or None))
        if building.item_caps:
            storage_items = len(
                {
                    *present_keys(amounts, storage_keys or None),
                    *building.item_caps.keys(),
                }
            )
        player_items = len(present_keys(player_amounts, None))
        supports_caps = self._supports_item_caps(building)
        cap_keys = building.depositable_keys() if supports_caps else ()
        layout_w = 380 - PAD * 2
        caps_h = 0
        mins_h = 0
        market_h = 0
        if building.kind == BuildingKind.MARKET:
            from market_economy import demand_keys, market_supply_resource_keys

            demand_n = len(demand_keys(building.market_demand))
            market_h = self._market_demand_block_height(
                expanded=self.market_demand_expanded,
                key_count=max(1, demand_n),
                inner_w=layout_w,
            )
            supply_n = len(
                market_supply_resource_keys(self.market_supply_group)
            )
            market_h += self._market_supply_block_height(
                expanded=self.market_supply_expanded,
                key_count=max(1, supply_n),
                inner_w=layout_w,
            )
        # Caps and reserves are edited directly on storage cells.

        hire_row_h = ROW_H
        embed_w, embed_h = self._panel_w, self._panel_h
        if building.kind == BuildingKind.WORKSTATION:
            workers_content = ROW_H + BTN_H + 24
            self._panel_w = 360
        elif not workers:
            workers_content = ROW_H
        else:
            workers_content = len(workers) * (ROW_H + 2)
        workers_h = 18 + min(workers_content, MAX_WORKER_VIEW_H)

        if dual:
            dual_col_w = (520 - PAD * 2 - INV_PANEL_GAP) // 2
            dual_cols = max(1, min(6, dual_col_w // (GRID_CELL + GRID_GAP)))
            body = max(
                grid_height(storage_items, cols=dual_cols),
                grid_height(player_items, cols=dual_cols),
                GRID_CELL,
            )
            grid_h = 18 + 16 + body + 22
            self._panel_w = 520
        elif has_storage:
            grid_h = 18 + 16 + grid_height(storage_items) + 8
            self._panel_w = 380 if (
                building.has_recipes() or supports_caps or building.kind == BuildingKind.MARKET
            ) else 300
        else:
            grid_h = 40
            self._panel_w = 420 if building.kind == BuildingKind.WORKSTATION else 300

        body_h = (
            PAD
            + overview_h
            + 18
            + options_h
            + SECTION_GAP
            + recipes_h
            + workers_h
            + SECTION_GAP
            + grid_h
            + market_h
            + caps_h
            + mins_h
            + PAD
            + 8
        )
        body_h = max(body_h, self._measured_body_h)
        max_panel = WINDOW_HEIGHT - MAP_OFFSET_Y - 8
        if self.embedded:
            self._panel_w = embed_w
            self._panel_h = embed_h
        else:
            self._panel_h = min(TITLE_BAR_H + body_h, max_panel)
            self._clamp_panel()
        panel = self.panel_rect()
        self._scroll_areas = {}
        client_h = max(1, self._panel_h - TITLE_BAR_H)
        panel_scroll = self._scroll_value("panel_body", body_h, client_h)
        client_rect = pygame.Rect(panel.x, panel.y + TITLE_BAR_H, panel.w, client_h)
        self._register_scroll("panel_body", client_rect, body_h, client_h)

        if not self.embedded:
            shadow = panel.move(3, 4)
            sh = pygame.Surface((shadow.w, shadow.h), pygame.SRCALPHA)
            sh.fill((0, 0, 0, 70))
            surface.blit(sh, shadow.topleft)
            pygame.draw.rect(surface, COLOUR_MENU_BG, panel, border_radius=6)
            pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, panel, 2, border_radius=6)

        if body_h > client_h and not self.embedded:
            pygame.draw.rect(surface, (43, 45, 53), client_rect)

        title_bar = pygame.Rect(panel.x, panel.y, panel.w, TITLE_BAR_H)
        if not self.embedded:
            pygame.draw.rect(
                surface,
                (48, 50, 58),
                title_bar,
                border_top_left_radius=6,
                border_top_right_radius=6,
            )
        self._title_rect = pygame.Rect(panel.x, panel.y, panel.w - 32, TITLE_BAR_H)
        title = f"{BUILDING_LABELS[building.kind]} #{building.id}"
        surface.blit(
            self.font_title.render(title, True, COLOUR_TEXT),
            (panel.x + 10, panel.y + 6),
        )
        if self.embedded:
            self._close_rect = pygame.Rect(0, 0, 0, 0)
        else:
            self._close_rect = pygame.Rect(panel.right - 28, panel.y + 4, 22, 20)
            close_hov = mouse_pos is not None and self._close_rect.collidepoint(mouse_pos)
            self._draw_button(surface, self._close_rect, "×", hovered=close_hov)

        self._buttons = []
        self._worker_hits = []
        self._inv_hits = []
        self._inv_tip_hits: list[tuple[pygame.Rect, str, str]] = []
        env_hover_tip = ""
        content_top = panel.y + TITLE_BAR_H
        old_body_clip = surface.get_clip()
        body_clip = client_rect.clip(old_body_clip) if old_body_clip.width else client_rect
        surface.set_clip(body_clip)
        x = panel.x + PAD
        y = content_top + PAD - panel_scroll
        inner_w = panel.w - PAD * 2

        if building.kind == BuildingKind.FARM:
            from crop_status_ui import draw_crop_overview, draw_env_factors

            y = draw_crop_overview(
                surface,
                x,
                y,
                inner_w,
                crop_overview or [],
                current_season,
                fonts=self._fonts(),
                empty_label="No crop plans on nearby fields",
            )
            if env_status:
                y, env_hover_tip = draw_env_factors(
                    surface,
                    x,
                    y,
                    inner_w,
                    env_status,
                    fonts=self._fonts(),
                    mouse_pos=mouse_pos,
                )

        # --- Options ---
        surface.blit(self.font.render("Options", True, COLOUR_TEXT), (x, y))
        y += 18
        bx = x
        if building.kind == BuildingKind.WORKSTATION:
            label = f"Hire first fit ({hired_count}/{MAX_VILLAGERS})"
            w = max(140, 12 + self.font_small.size(label)[0])
            rect = pygame.Rect(bx, y, w, BTN_H)
            hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
            self._draw_button(surface, rect, label, hovered=hovered)
            self._buttons.append(("hire_villager", rect))
            y += BTN_H + 4
            status = (
                f"Beds free {free_beds}  ·  Housing lvl {housing_level}  ·  "
                f"{len(candidates)} travellers"
            )
            surface.blit(
                self.font_tiny.render(status, True, COLOUR_TEXT_DIM),
                (x, y),
            )
            y += 16
            relocate_w = max(72, 10 + self.font_small.size("Relocate")[0])
            rect = pygame.Rect(x, y, relocate_w, BTN_H)
            hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
            self._draw_button(surface, rect, "Relocate", hovered=hovered)
            self._buttons.append(("relocate_building", rect))
            y += BTN_H + 6
        elif building.kind == BuildingKind.HOME:
            for label, action in (
                ("Assign hauler +", "assign_villager"),
                ("Unassign −", "unassign_villager"),
            ):
                w = max(90, 10 + self.font_small.size(label)[0])
                rect = pygame.Rect(bx, y, w, BTN_H)
                hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
                self._draw_button(surface, rect, label, hovered=hovered)
                self._buttons.append((action, rect))
                bx += w + 4
            # Relocate for storehouse too
            relocate_w = max(72, 10 + self.font_small.size("Relocate")[0])
            rect = pygame.Rect(bx, y, relocate_w, BTN_H)
            hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
            self._draw_button(surface, rect, "Relocate", hovered=hovered)
            self._buttons.append(("relocate_building", rect))
            y += BTN_H + 6
        elif is_housing_kind(building.kind):
            beds = housing_beds_of(building.kind)
            used = len(workers)
            lvl = housing_level_of(building.kind)
            surface.blit(
                self.font_tiny.render(
                    f"Level {lvl}  ·  Beds {used}/{beds}",
                    True,
                    COLOUR_TEXT_DIM,
                ),
                (x, y),
            )
            y += 16
            for label, action in (
                ("Assign resident +", "assign_villager"),
                ("Unassign −", "unassign_villager"),
            ):
                w = max(100, 10 + self.font_small.size(label)[0])
                rect = pygame.Rect(bx, y, w, BTN_H)
                hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
                self._draw_button(surface, rect, label, hovered=hovered)
                self._buttons.append((action, rect))
                bx += w + 4
            relocate_w = max(72, 10 + self.font_small.size("Relocate")[0])
            if bx + relocate_w > x + inner_w and bx > x:
                bx = x
                y += BTN_H + 4
            rect = pygame.Rect(bx, y, relocate_w, BTN_H)
            hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
            self._draw_button(surface, rect, "Relocate", hovered=hovered)
            self._buttons.append(("relocate_building", rect))
            y += BTN_H + SECTION_GAP
        else:
            for mode in building.supported_work_modes():
                label = WORK_MODE_LABELS[mode]
                w = max(52, 10 + self.font_small.size(label)[0])
                if bx + w > x + inner_w and bx > x:
                    bx = x
                    y += BTN_H + 4
                rect = pygame.Rect(bx, y, w, BTN_H)
                active = building.work_mode == mode
                hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
                self._draw_button(surface, rect, label, active=active, hovered=hovered)
                self._buttons.append((f"mode_{mode.name}", rect))
                bx += w + 4
            if building.kind == BuildingKind.FORESTER:
                clear_w = max(48, 10 + self.font_small.size("Clear")[0])
                plant_active = area_draw_task == TaskType.PLANT_SAPLINGS
                collect_active = area_draw_task == TaskType.CHOP_TREES
                plant_rect = pygame.Rect(bx, y, BTN_H, BTN_H)
                hov = mouse_pos is not None and plant_rect.collidepoint(mouse_pos)
                self._draw_icon_btn(
                    surface,
                    plant_rect,
                    icons=(ICON_SAPLING_CONE,),
                    active=plant_active,
                    hovered=hov,
                )
                self._buttons.append(("toggle_draw_plant", plant_rect))
                bx += BTN_H + 4
                rect = pygame.Rect(bx, y, clear_w, BTN_H)
                hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
                self._draw_button(surface, rect, "Clear", hovered=hovered)
                self._buttons.append(("clear_plant_areas", rect))
                bx += clear_w + 8
                collect_rect = pygame.Rect(bx, y, BTN_H + 18, BTN_H)
                hov = mouse_pos is not None and collect_rect.collidepoint(mouse_pos)
                self._draw_icon_btn(
                    surface,
                    collect_rect,
                    icons=(ICON_TREE_ROUND, ICON_AXE),
                    active=collect_active,
                    hovered=hov,
                )
                self._buttons.append(("toggle_draw_collect", collect_rect))
                bx += collect_rect.w + 4
                rect = pygame.Rect(bx, y, clear_w, BTN_H)
                hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
                self._draw_button(surface, rect, "Clear", hovered=hovered)
                self._buttons.append(("clear_collect_areas", rect))
                bx += clear_w + 4
            elif building.kind not in (
                BuildingKind.FARM,
                BuildingKind.MILL,
                BuildingKind.KITCHEN,
                BuildingKind.FIRE,
                BuildingKind.CRAFT_BENCH,
                BuildingKind.ALCHEMIST,
                BuildingKind.TAILOR,
                BuildingKind.COBBLER,
                BuildingKind.MARKET,
            ):
                clear_w = max(48, 10 + self.font_small.size("Clear")[0])
                if bx + clear_w > x + inner_w and bx > x:
                    bx = x
                    y += BTN_H + 4
                rect = pygame.Rect(bx, y, clear_w, BTN_H)
                hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
                self._draw_button(surface, rect, "Clear", hovered=hovered)
                self._buttons.append(("task_clear", rect))
                bx += clear_w + 4
            if building.kind in (
                BuildingKind.MASON,
                BuildingKind.HUNTER,
                BuildingKind.FORAGER,
                BuildingKind.FISHER,
            ):
                draw_task = building.default_draw_task()
                draw_label = "Draw areas" if area_draw_task != draw_task else "Drawing…"
                draw_w = max(88, 10 + self.font_small.size(draw_label)[0])
                if bx + draw_w > x + inner_w and bx > x:
                    bx = x
                    y += BTN_H + 4
                rect = pygame.Rect(bx, y, draw_w, BTN_H)
                hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
                self._draw_button(
                    surface,
                    rect,
                    draw_label,
                    active=area_draw_task == draw_task,
                    hovered=hovered,
                )
                self._buttons.append(("toggle_area_draw", rect))
                bx += draw_w + 4
            relocate_w = max(72, 10 + self.font_small.size("Relocate")[0])
            if bx + relocate_w > x + inner_w and bx > x:
                bx = x
                y += BTN_H + 4
            rect = pygame.Rect(bx, y, relocate_w, BTN_H)
            hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
            self._draw_button(surface, rect, "Relocate", hovered=hovered)
            self._buttons.append(("relocate_building", rect))
            bx += relocate_w + 4
            y += BTN_H + 6
            bx = x
            for label, action in (("Assign +", "assign_villager"), ("Unassign −", "unassign_villager")):
                w = max(72, 10 + self.font_small.size(label)[0])
                rect = pygame.Rect(bx, y, w, BTN_H)
                hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
                self._draw_button(surface, rect, label, hovered=hovered)
                self._buttons.append((action, rect))
                bx += w + 4
            y += BTN_H + 4
            bx = x
            from extensions import EXTENSION_LABELS, extensions_for_parent

            for ext_kind in extensions_for_parent(building.kind):
                claimed = ext_kind in building.linked_extensions
                label = f"Add {EXTENSION_LABELS.get(ext_kind, ext_kind.name)}"
                if claimed:
                    label = f"{EXTENSION_LABELS.get(ext_kind, ext_kind.name)} ✓"
                w = max(90, 10 + self.font_small.size(label)[0])
                if bx + w > x + inner_w and bx > x:
                    bx = x
                    y += BTN_H + 4
                rect = pygame.Rect(bx, y, w, BTN_H)
                hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
                self._draw_button(
                    surface, rect, label, hovered=hovered and not claimed
                )
                if not claimed:
                    self._buttons.append((f"place_extension:{ext_kind.name}", rect))
                bx += w + 4
            y += BTN_H + SECTION_GAP

        if building.kind in (BuildingKind.HOME, BuildingKind.WORKSTATION):
            y += SECTION_GAP // 2

        # --- Recipes / collect toggles ---
        fonts = self._fonts()
        tip_key: str | None = None
        if gather_recipes:
            building.ensure_recipe_state()
            surface.blit(self.font.render("Collect", True, COLOUR_TEXT), (x, y))
            y += 18
            cols = max(1, inner_w // GATHER_CELL_STRIDE)
            rows = max(1, (len(gather_recipes) + cols - 1) // cols)
            content_h = rows * (RECIPE_OUT_CELL + GRID_GAP) - GRID_GAP
            view_h = min(content_h, MAX_GATHER_VIEW_H)
            view = pygame.Rect(x, y, inner_w, view_h)
            scroll = self._register_scroll("gather_recipes", view, content_h, view_h)
            old_clip = surface.get_clip()
            surface.set_clip(view.clip(old_clip) if old_clip.width else view)
            for i, recipe in enumerate(building._recipes_by_priority(gather_recipes)):
                col = i % cols
                row = i // cols
                cell = pygame.Rect(
                    x + col * GATHER_CELL_STRIDE,
                    y + row * (RECIPE_OUT_CELL + GRID_GAP) - scroll,
                    RECIPE_OUT_CELL,
                    RECIPE_OUT_CELL,
                )
                if not cell.colliderect(view):
                    continue
                priority = building.get_recipe_priority(recipe.name)
                out_key, hov = self._draw_recipe_stock_cell(
                    surface,
                    building=building,
                    recipe=recipe,
                    cell=cell,
                    mouse_pos=mouse_pos,
                    view=view,
                    stock_amounts=village_stock,
                )
                enabled = building.is_recipe_enabled(recipe.name)
                # Same placement as production recipes: top-right outside the icon.
                prio_cell = pygame.Rect(cell.right + 2, cell.y + 2, 16, 16)
                prio_hov = mouse_pos is not None and prio_cell.collidepoint(mouse_pos)
                self._draw_priority_badge(
                    surface, prio_cell, priority, enabled=enabled, hovered=prio_hov
                )
                self._buttons.append((f"cycle_recipe_priority:{recipe.name}", prio_cell))
                if hov and not prio_hov and out_key:
                    tip_key = recipe.display_icon_key() or out_key
            surface.set_clip(old_clip)
            self._draw_scrollbar(surface, view, content_h, scroll)
            y += view_h + SECTION_GAP
        if split_recipes:
            block_h, split_tip = self._draw_craft_recipes(
                surface,
                building=building,
                recipes=split_recipes,
                title="Split",
                x=x,
                y=y,
                inner_w=inner_w,
                mouse_pos=mouse_pos,
                fonts=fonts,
                scroll_name="split_recipes",
                player_craft=self.allow_player_craft,
                stock_amounts=village_stock,
                progress_fractions=recipe_progress_fractions,
            )
            y += block_h
            if split_tip:
                tip_key = split_tip
        if plant_recipes:
            block_h, plant_tip = self._draw_craft_recipes(
                surface,
                building=building,
                recipes=plant_recipes,
                title="Plant",
                x=x,
                y=y,
                inner_w=inner_w,
                mouse_pos=mouse_pos,
                fonts=fonts,
                scroll_name="plant_recipes",
                player_craft=self.allow_player_craft,
                stock_amounts=village_stock,
                progress_fractions=recipe_progress_fractions,
            )
            y += block_h
            if plant_tip:
                tip_key = plant_tip
        if craft_recipes:
            farm_exts = building.kind == BuildingKind.FARM
            craft_title = "Farm extensions" if farm_exts else "Recipes"
            block_h, craft_tip = self._draw_craft_recipes(
                surface,
                building=building,
                recipes=craft_recipes,
                title=craft_title,
                x=x,
                y=y,
                inner_w=inner_w,
                mouse_pos=mouse_pos,
                fonts=fonts,
                scroll_name="craft_recipes",
                show_fuel=building.is_cooking_building(),
                player_craft=self.allow_player_craft,
                stock_amounts=village_stock,
                progress_fractions=recipe_progress_fractions,
            )
            y += block_h
            if craft_tip:
                tip_key = craft_tip

        # --- Workers / haulers / hire pool ---
        workers_title = (
            "Haulers"
            if building.kind == BuildingKind.HOME
            else "Travellers"
            if building.kind == BuildingKind.WORKSTATION
            else "Residents"
            if is_housing_kind(building.kind)
            else "Workers"
        )
        if is_housing_kind(building.kind):
            beds = housing_beds_of(building.kind)
            workers_title = f"Residents ({len(workers)}/{beds})"
        surface.blit(self.font.render(workers_title, True, COLOUR_TEXT), (x, y))
        y += 18
        if building.kind == BuildingKind.WORKSTATION:
            surface.blit(
                self.font_small.render(
                    f"{len(candidates)} travellers nearby — open roster to hire.",
                    True,
                    COLOUR_TEXT_DIM,
                ),
                (x, y),
            )
            y += 20
            open_r = pygame.Rect(x, y, 160, BTN_H)
            hov = mouse_pos is not None and open_r.collidepoint(mouse_pos)
            self._draw_button(surface, open_r, "Open travellers…", hovered=hov)
            self._buttons.append(("hire_villager", open_r))
            y += BTN_H + 4
        elif not workers:
            surface.blit(
                self.font_small.render("None assigned", True, COLOUR_TEXT_DIM),
                (x, y),
            )
            y += ROW_H
        else:
            content_h = len(workers) * (ROW_H + 2)
            view_h = min(content_h, MAX_WORKER_VIEW_H)
            view = pygame.Rect(x - 2, y - 1, inner_w + 4, view_h)
            scroll = self._register_scroll("workers", view, content_h, view_h)
            pygame.draw.rect(surface, (32, 35, 42), view, border_radius=4)
            old_clip = surface.get_clip()
            surface.set_clip(view.clip(old_clip) if old_clip.width else view)
            for i, villager in enumerate(workers):
                row_y = y + i * (ROW_H + 2) - scroll
                row = pygame.Rect(x - 2, row_y - 1, inner_w + 4, ROW_H)
                if not row.colliderect(view):
                    continue
                selected = selected_villager_id == villager.id
                hovered = self._hover_worker == villager.id or (
                    view.collidepoint(mouse_pos or (-1, -1))
                    and mouse_pos is not None
                    and row.collidepoint(mouse_pos)
                )
                if selected:
                    pygame.draw.rect(surface, (55, 70, 55), row, border_radius=3)
                    pygame.draw.rect(
                        surface, COLOUR_SELECTED_ENTITY, row, 1, border_radius=3
                    )
                elif hovered:
                    pygame.draw.rect(surface, (45, 48, 55), row, border_radius=3)
                label = self._worker_label(villager)
                colour = COLOUR_TEXT if selected or hovered else COLOUR_TEXT_DIM
                surface.blit(
                    self.font_small.render(label, True, colour),
                    (x + 2, row_y + 3),
                )
                bar_x = x + 2 + self.font_small.size(label)[0] + 8
                bar_y = row_y + (ROW_H - 7) // 2
                bar_w = 36
                pygame.draw.rect(
                    surface, (40, 40, 40), pygame.Rect(bar_x, bar_y, bar_w, 7), border_radius=2
                )
                fill = max(0, min(1.0, villager.satiation))
                fill_c = (
                    (70, 160, 80)
                    if fill > 0.5
                    else (180, 140, 50)
                    if fill > 0.25
                    else (180, 70, 60)
                )
                pygame.draw.rect(
                    surface,
                    fill_c,
                    pygame.Rect(bar_x, bar_y, int(bar_w * fill), 7),
                    border_radius=2,
                )
                tip = "Seeking food" if villager.seeking_food else villager.state.name
                surface.blit(
                    self.font_small.render(tip[:8], True, COLOUR_TEXT_DIM),
                    (bar_x + bar_w + 6, row_y + 3),
                )
                self._worker_hits.append((row, villager.id))
            surface.set_clip(old_clip)
            self._draw_scrollbar(surface, view, content_h, scroll)
            y += view_h

        y += SECTION_GAP

        if building.kind == BuildingKind.MARKET:
            from market_economy import MARKET_PRICES, MARKET_SELLABLE_KEYS, demand_keys
            from resources import resource_label

            demand_list = demand_keys(building.market_demand)
            y += self._draw_section_toggle(
                surface,
                x=x,
                y=y,
                inner_w=inner_w,
                label="Season demand",
                expanded=self.market_demand_expanded,
                action="toggle_market_demand",
                mouse_pos=mouse_pos,
            )
            if self.market_demand_expanded:
                if not demand_list:
                    surface.blit(
                        self.font_small.render(
                            "No buyer demand this season.",
                            True,
                            COLOUR_TEXT_DIM,
                        ),
                        (x, y),
                    )
                    y += ROW_H + SECTION_GAP
                else:
                    cols = max(1, inner_w // (GRID_CELL + GRID_GAP))
                    rows = max(1, (len(demand_list) + cols - 1) // cols)
                    content_h = rows * (GRID_CELL + GRID_GAP) - GRID_GAP
                    view_h = min(content_h, MAX_CAP_VIEW_H)
                    view = pygame.Rect(x, y, inner_w, view_h)
                    scroll = self._register_scroll("market_demand", view, content_h, view_h)
                    old_clip = surface.get_clip()
                    surface.set_clip(view.clip(old_clip) if old_clip.width else view)
                    for i, key in enumerate(demand_list):
                        col = i % cols
                        row = i // cols
                        cell = pygame.Rect(
                            x + col * (GRID_CELL + GRID_GAP),
                            y + row * (GRID_CELL + GRID_GAP) - scroll,
                            GRID_CELL,
                            GRID_CELL,
                        )
                        if not cell.colliderect(view):
                            continue
                        hov = (
                            view.collidepoint(mouse_pos or (-1, -1))
                            and mouse_pos is not None
                            and cell.collidepoint(mouse_pos)
                        )
                        demand_n = building.market_demand_remaining(key)
                        offer_n = 0
                        if market_offer_fn is not None:
                            offer_n = int(market_offer_fn(building, key))
                        elif building.market_supply_enabled(key) and home_storage is not None:
                            have = int(getattr(home_storage, key, 0))
                            surplus = max(0, have - building.market_supply_min(key))
                            offer_n = min(surplus, demand_n)
                        supplying = building.market_supply_enabled(key) and offer_n > 0
                        draw_resource_cell(
                            surface,
                            cell=cell,
                            key=key,
                            count_label=f"{offer_n}/{demand_n}",
                            fonts=fonts,
                            hovered=hov,
                            active=supplying,
                            dimmed=not building.market_supply_enabled(key),
                        )
                        self._inv_tip_hits.append((cell, "market", key))
                        if hov:
                            tip_key = key
                    surface.set_clip(old_clip)
                    self._draw_scrollbar(surface, view, content_h, scroll)
                    y += view_h + SECTION_GAP

            y += self._draw_section_toggle(
                surface,
                x=x,
                y=y,
                inner_w=inner_w,
                label="Supply",
                expanded=self.market_supply_expanded,
                action="toggle_market_supply",
                mouse_pos=mouse_pos,
            )
            if self.market_supply_expanded:
                from icons import blit_icon
                from market_economy import market_supply_resource_keys
                from resources import GROUP_LABELS, GROUP_ORDER, resource_icon_style

                # Category filter tabs.
                bx = x
                for group in GROUP_ORDER:
                    label = GROUP_LABELS.get(group, group)
                    w = max(56, 12 + self.font_small.size(label)[0])
                    rect = pygame.Rect(bx, y, w, BTN_H)
                    active = self.market_supply_group == group
                    hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
                    self._draw_button(
                        surface, rect, label, hovered=hovered, active=active
                    )
                    self._buttons.append((f"market_supply_group:{group}", rect))
                    bx += w + 4
                y += BTN_H + 6

                supply_keys = list(market_supply_resource_keys(self.market_supply_group))
                cell_size = max(GRID_CELL, 56)
                cols = max(1, inner_w // (cell_size + GRID_GAP))
                rows = max(1, (len(supply_keys) + cols - 1) // cols)
                content_h = rows * (cell_size + GRID_GAP) - GRID_GAP
                view_h = min(content_h, max(MAX_CAP_VIEW_H, cell_size * 2 + GRID_GAP))
                view = pygame.Rect(x, y, inner_w, view_h)
                scroll = self._register_scroll("market_supply", view, content_h, view_h)
                old_clip = surface.get_clip()
                surface.set_clip(view.clip(old_clip) if old_clip.width else view)
                for i, key in enumerate(supply_keys):
                    col = i % cols
                    row = i // cols
                    cell = pygame.Rect(
                        x + col * (cell_size + GRID_GAP),
                        y + row * (cell_size + GRID_GAP) - scroll,
                        cell_size,
                        cell_size,
                    )
                    if not cell.colliderect(view):
                        continue
                    hov = (
                        view.collidepoint(mouse_pos or (-1, -1))
                        and mouse_pos is not None
                        and cell.collidepoint(mouse_pos)
                    )
                    enabled = building.market_supply_enabled(key)
                    selected = self.selected_market_supply_key == key
                    if enabled or selected:
                        bg = (40, 48, 40) if hov else (32, 38, 34)
                        border = COLOUR_SELECTED_ENTITY
                    elif hov:
                        bg = (48, 50, 42)
                        border = COLOUR_SELECTED_ENTITY
                    else:
                        bg = (36, 38, 42)
                        border = COLOUR_TOOLBAR_BORDER
                    pygame.draw.rect(surface, bg, cell, border_radius=4)
                    pygame.draw.rect(surface, border, cell, 1, border_radius=4)

                    store_n = (
                        int(getattr(home_storage, key, 0))
                        if home_storage is not None
                        else 0
                    )
                    local_n = int(getattr(building, key, 0))
                    stock_n = store_n + local_n
                    reserve_n = building.market_supply_min(key) if enabled else 0
                    text_col = COLOUR_TEXT if enabled else COLOUR_TEXT_DIM
                    sto = self.font_tiny.render(f"Sto: {stock_n}", True, text_col)
                    res = self.font_tiny.render(f"Res: {reserve_n}", True, text_col)
                    sto_rect = pygame.Rect(
                        cell.x + 2,
                        cell.y + 2,
                        cell.w - 4,
                        sto.get_height() + 2,
                    )
                    res_rect = pygame.Rect(
                        cell.x + 2,
                        cell.bottom - res.get_height() - 4,
                        cell.w - 4,
                        res.get_height() + 2,
                    )
                    surface.blit(
                        sto,
                        (cell.centerx - sto.get_width() // 2, sto_rect.y + 1),
                    )
                    surface.blit(
                        res,
                        (cell.centerx - res.get_width() // 2, res_rect.y + 1),
                    )

                    icon_size = max(18, cell.w - 28)
                    icon_cy = cell.centery + 1
                    try:
                        style = resource_icon_style(key)
                        blit_icon(
                            surface,
                            style.name,
                            cell.centerx,
                            icon_cy,
                            icon_size,
                            recolour=style.recolour,
                            class_scales=style.class_scales,
                            omit_classes=style.omit_classes or None,
                        )
                    except (FileNotFoundError, OSError, ValueError, TypeError):
                        pass

                    if not enabled:
                        overlay = pygame.Surface((cell.w, cell.h), pygame.SRCALPHA)
                        overlay.fill((28, 30, 36, 110))
                        surface.blit(overlay, cell.topleft)

                    # Whole cell toggles; Res hit box wins via reverse scan.
                    # Sto is display-only (storehouse + local stock).
                    self._buttons.append((f"toggle_market_supply_key:{key}", cell))
                    self._buttons.append((f"edit_market_reserve:{key}", res_rect))
                    self._inv_tip_hits.append((cell, "market_supply", key))
                    if hov:
                        tip_key = key
                surface.set_clip(old_clip)
                self._draw_scrollbar(surface, view, content_h, scroll)
                y += view_h + SECTION_GAP

        if dual:
            col_w = (inner_w - INV_PANEL_GAP) // 2
            # Paired inventories each own exactly half of the transfer area,
            # including empty space beneath a short/empty item list.
            section_h = max(grid_h, 18 + 16 + GRID_CELL + 22)
            pygame.draw.rect(
                surface, (29, 33, 40), pygame.Rect(x - 4, y - 4, col_w + 8, section_h), border_radius=5
            )
            pygame.draw.rect(
                surface,
                (39, 35, 43),
                pygame.Rect(x + col_w + INV_PANEL_GAP - 4, y - 4, col_w + 8, section_h),
                border_radius=5,
            )
            left_h, left_hits, left_tips, left_hov, left_ch, left_vh = draw_inv_grid(
                surface,
                origin=(x, y),
                width=col_w,
                title="Storage",
                subtitle=capacity_label,
                amounts=amounts,
                allowed=storage_keys,
                side="storage",
                mouse_pos=mouse_pos,
                fonts=fonts,
                interactive=True,
                hover_inv=self._hover_inv,
                selected_key=self.selected_cap_key,
                item_caps=building.item_caps,
                item_mins=building.item_mins,
                inline_stock_controls=supports_caps,
                scroll_y=self._scroll.get("storage", 0),
                max_body_h=None,
                qualities=storage_qualities,
            )
            right_h, right_hits, right_tips, right_hov, right_ch, right_vh = draw_inv_grid(
                surface,
                origin=(x + col_w + INV_PANEL_GAP, y),
                width=col_w,
                title="Player",
                subtitle=player_sub,
                amounts=player_amounts,
                allowed=None,
                side="player",
                mouse_pos=mouse_pos,
                fonts=fonts,
                interactive=True,
                hover_inv=self._hover_inv,
                scroll_y=self._scroll.get("player", 0),
                max_body_h=None,
                qualities=player_qualities,
            )
            # Register body viewports (below title+subtitle ≈ 34px).
            header = 34
            self._register_scroll(
                "storage",
                pygame.Rect(x, y + header, col_w, left_vh),
                left_ch,
                left_vh,
            )
            self._draw_scrollbar(
                surface,
                pygame.Rect(x, y + header, col_w, left_vh),
                left_ch,
                self._scroll_value("storage", left_ch, left_vh),
            )
            self._register_scroll(
                "player",
                pygame.Rect(x + col_w + INV_PANEL_GAP, y + header, col_w, right_vh),
                right_ch,
                right_vh,
            )
            self._draw_scrollbar(
                surface,
                pygame.Rect(x + col_w + INV_PANEL_GAP, y + header, col_w, right_vh),
                right_ch,
                self._scroll_value("player", right_ch, right_vh),
            )
            self._inv_hits.extend(left_hits)
            self._inv_hits.extend(right_hits)
            self._inv_tip_hits.extend(left_tips)
            self._inv_tip_hits.extend(right_tips)
            y += max(left_h, right_h)
            if left_hov:
                tip_key = left_hov[1]
            elif right_hov:
                tip_key = right_hov[1]
            surface.blit(
                self.font_small.render(
                    "Click an item to move one to the other inventory.",
                    True,
                    COLOUR_TEXT_DIM,
                ),
                (x, y + 6),
            )
            y += 22
        elif has_storage:
            h, hits, tips, hov, ch, vh = draw_inv_grid(
                surface,
                origin=(x, y),
                width=inner_w,
                title="Storage",
                subtitle=capacity_label,
                amounts=amounts,
                allowed=storage_keys,
                side="storage",
                mouse_pos=mouse_pos,
                fonts=fonts,
                interactive=self._supports_item_caps(building),
                hover_inv=self._hover_inv,
                selected_key=self.selected_cap_key,
                item_caps=building.item_caps,
                item_mins=building.item_mins,
                inline_stock_controls=supports_caps,
                scroll_y=self._scroll.get("storage", 0),
                max_body_h=None,
                qualities=storage_qualities,
            )
            header = 34
            body = pygame.Rect(x, y + header, inner_w, vh)
            self._register_scroll("storage", body, ch, vh)
            self._draw_scrollbar(
                surface, body, ch, self._scroll_value("storage", ch, vh)
            )
            self._inv_hits.extend(hits)
            self._inv_tip_hits.extend(tips)
            if hov:
                tip_key = hov[1]
            y += h
        else:
            surface.blit(self.font.render("Storage", True, COLOUR_TEXT), (x, y))
            y += 18
            surface.blit(
                self.font_small.render("No local storage", True, COLOUR_TEXT_DIM),
                (x, y),
            )

        if False:  # Legacy separate cap/reserve sections replaced by cell controls.
            y += SECTION_GAP
            keys = list(building.depositable_keys())
            cols = max(1, inner_w // (GRID_CELL + GRID_GAP))

            y += self._draw_section_toggle(
                surface,
                x=x,
                y=y,
                inner_w=inner_w,
                label="Item caps",
                expanded=self.caps_expanded,
                action="toggle_caps",
                mouse_pos=mouse_pos,
            )
            if self.caps_expanded:
                rows = max(1, (len(keys) + cols - 1) // cols)
                content_h = rows * (GRID_CELL + GRID_GAP) - GRID_GAP
                view_h = min(content_h, MAX_CAP_VIEW_H)
                view = pygame.Rect(x, y, inner_w, view_h)
                scroll = self._register_scroll("caps", view, content_h, view_h)
                old_clip = surface.get_clip()
                surface.set_clip(view.clip(old_clip) if old_clip.width else view)
                for i, key in enumerate(keys):
                    col = i % cols
                    row = i // cols
                    cell = pygame.Rect(
                        x + col * (GRID_CELL + GRID_GAP),
                        y + row * (GRID_CELL + GRID_GAP) - scroll,
                        GRID_CELL,
                        GRID_CELL,
                    )
                    if not cell.colliderect(view):
                        continue
                    hov = (
                        view.collidepoint(mouse_pos or (-1, -1))
                        and mouse_pos is not None
                        and cell.collidepoint(mouse_pos)
                    )
                    selected = self.selected_cap_key == key
                    cap = building.item_cap(key)
                    draw_resource_cell(
                        surface,
                        cell=cell,
                        key=key,
                        count=cap,
                        fonts=fonts,
                        hovered=hov,
                        active=selected,
                        dimmed=cap is None and not selected,
                    )
                    self._inv_hits.append((cell, "cap", key))
                    self._inv_tip_hits.append((cell, "cap", key))
                    if hov:
                        tip_key = key
                surface.set_clip(old_clip)
                self._draw_scrollbar(surface, view, content_h, scroll)
                y += view_h + 6

                sel = self.selected_cap_key
                if sel is not None and sel in building.depositable_keys():
                    from resources import resource_label

                    cap = building.item_cap(sel)
                    cap_txt = "∞" if cap is None else str(cap)
                    label = f"{resource_label(sel)}: {cap_txt}"
                    surface.blit(
                        self.font_small.render(label, True, COLOUR_TEXT_DIM),
                        (x, y + 4),
                    )
                    bx = x + max(120, 8 + self.font_small.size(label)[0])
                    for glyph, action in (
                        ("−", "cap_dec"),
                        ("+", "cap_inc"),
                        ("∞", "cap_clear"),
                    ):
                        w = max(28, 10 + self.font_small.size(glyph)[0])
                        rect = pygame.Rect(bx, y, w, BTN_H)
                        hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
                        self._draw_button(surface, rect, glyph, hovered=hovered)
                        self._buttons.append((action, rect))
                        bx += w + 4
                    y += BTN_H + SECTION_GAP
                else:
                    surface.blit(
                        self.font_small.render(
                            "Select an item, then + / − to set a max.",
                            True,
                            COLOUR_TEXT_DIM,
                        ),
                        (x, y),
                    )
                    y += ROW_H + SECTION_GAP

            y += self._draw_section_toggle(
                surface,
                x=x,
                y=y,
                inner_w=inner_w,
                label="Min reserve",
                expanded=self.mins_expanded,
                action="toggle_mins",
                mouse_pos=mouse_pos,
            )
            if self.mins_expanded:
                min_keys = list(keys)
                for mk in building.item_mins:
                    if mk not in min_keys:
                        min_keys.append(mk)
                rows = max(1, (len(min_keys) + cols - 1) // cols)
                content_h = rows * (GRID_CELL + GRID_GAP) - GRID_GAP
                view_h = min(content_h, MAX_CAP_VIEW_H)
                view = pygame.Rect(x, y, inner_w, view_h)
                scroll = self._register_scroll("mins", view, content_h, view_h)
                old_clip = surface.get_clip()
                surface.set_clip(view.clip(old_clip) if old_clip.width else view)
                for i, key in enumerate(min_keys):
                    col = i % cols
                    row = i // cols
                    cell = pygame.Rect(
                        x + col * (GRID_CELL + GRID_GAP),
                        y + row * (GRID_CELL + GRID_GAP) - scroll,
                        GRID_CELL,
                        GRID_CELL,
                    )
                    if not cell.colliderect(view):
                        continue
                    hov = (
                        view.collidepoint(mouse_pos or (-1, -1))
                        and mouse_pos is not None
                        and cell.collidepoint(mouse_pos)
                    )
                    selected = self.selected_min_key == key
                    reserve = building.item_min(key)
                    draw_resource_cell(
                        surface,
                        cell=cell,
                        key=key,
                        count=reserve,
                        fonts=fonts,
                        hovered=hov,
                        active=selected,
                        dimmed=reserve is None and not selected,
                    )
                    self._inv_hits.append((cell, "min", key))
                    self._inv_tip_hits.append((cell, "min", key))
                    if hov:
                        tip_key = key
                surface.set_clip(old_clip)
                self._draw_scrollbar(surface, view, content_h, scroll)
                y += view_h + 6

                sel = self.selected_min_key
                if sel is not None and sel in building.depositable_keys():
                    from resources import resource_label

                    reserve = building.item_min(sel)
                    reserve_txt = "—" if reserve is None else str(reserve)
                    label = f"{resource_label(sel)}: {reserve_txt}"
                    surface.blit(
                        self.font_small.render(label, True, COLOUR_TEXT_DIM),
                        (x, y + 4),
                    )
                    bx = x + max(120, 8 + self.font_small.size(label)[0])
                    for glyph, action in (
                        ("−", "min_dec"),
                        ("+", "min_inc"),
                        ("0", "min_clear"),
                    ):
                        w = max(28, 10 + self.font_small.size(glyph)[0])
                        rect = pygame.Rect(bx, y, w, BTN_H)
                        hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
                        self._draw_button(surface, rect, glyph, hovered=hovered)
                        self._buttons.append((action, rect))
                        bx += w + 4
                    y += BTN_H + SECTION_GAP
                else:
                    surface.blit(
                        self.font_small.render(
                            "Select an item, then + / − to set a min haul reserve.",
                            True,
                            COLOUR_TEXT_DIM,
                        ),
                        (x, y),
                    )
                    y += ROW_H + SECTION_GAP

        measured_body_h = max(1, int(y + panel_scroll - content_top + PAD))
        self._measured_body_h = measured_body_h
        measured_scroll = self._scroll_value("panel_body", measured_body_h, client_h)
        self._scroll_areas["panel_body"] = (client_rect, measured_body_h, client_h)
        surface.set_clip(old_body_clip)
        if measured_body_h > client_h:
            self._draw_scrollbar(surface, client_rect, measured_body_h, measured_scroll)

        if tip_key is not None:
            self._tooltip_key = tip_key
        if env_hover_tip:
            from crop_status_ui import draw_env_hover

            draw_env_hover(surface, mouse_pos, env_hover_tip, self.font_small)
        elif self._tooltip_key and mouse_pos is not None:
            extra = None
            if building.kind == BuildingKind.MARKET:
                from market_economy import MARKET_PRICES

                price = MARKET_PRICES.get(self._tooltip_key)
                demand = building.market_demand_remaining(self._tooltip_key)
                enabled = building.market_supply_enabled(self._tooltip_key)
                bits: list[str] = []
                if demand > 0:
                    offer = 0
                    if market_offer_fn is not None:
                        offer = int(market_offer_fn(building, self._tooltip_key))
                    at_m = int(getattr(building, self._tooltip_key, 0))
                    bits.append(f"supply {offer}/{demand}")
                    bits.append(f"at market {at_m}")
                if enabled:
                    bits.append(f"stock {building.market_supply_stock(self._tooltip_key)}")
                    bits.append(f"reserve {building.market_supply_min(self._tooltip_key)}")
                elif self._tooltip_key in building.market_demand:
                    bits.append("supply off")
                if price is not None:
                    bits.append(f"{int(price)} coin{'s' if int(price) != 1 else ''}")
                if bits:
                    extra = " · ".join(bits)
            draw_item_tooltip(
                surface,
                mouse_pos=mouse_pos,
                key=self._tooltip_key,
                font=self.font_small,
                extra=extra,
            )
