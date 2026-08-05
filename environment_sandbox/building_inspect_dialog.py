"""Floating inspection window for workplace buildings (not Fields).

Storage is always a grid. The player inventory grid is only shown when the
menu was opened while the player stands on the building (transfer mode).
"""

from __future__ import annotations

import pygame

from entities import (
    BUILDING_LABELS,
    WORK_MODE_LABELS,
    Building,
    BuildingKind,
    Inventory,
    Villager,
)
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

TITLE_BAR_H = 28
PAD = 12
BTN_H = 24
ROW_H = 22
RECIPE_ROW_H = GRID_CELL + 14
SECTION_GAP = 10
SCROLL_STEP = 28
# Visible size before a section starts scrolling.
MAX_RECIPE_VIEW_H = 3 * RECIPE_ROW_H
MAX_GATHER_VIEW_H = 2 * (GRID_CELL + GRID_GAP) - GRID_GAP
MAX_CAP_VIEW_H = 2 * (GRID_CELL + GRID_GAP) - GRID_GAP
MAX_STORAGE_BODY_H = 3 * (GRID_CELL + GRID_GAP) - GRID_GAP
MAX_WORKER_VIEW_H = 4 * (ROW_H + 2)


class BuildingInspectDialog:
    """Movable floating inspector: options, workers, inventory grid(s)."""

    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 14)
        self.font_small = pygame.font.SysFont("menlo", 12)
        self.font_tiny = pygame.font.SysFont("menlo", 11, bold=True)
        self.font_title = pygame.font.SysFont("menlo", 15, bold=True)
        self.building_id: int | None = None
        self.show_player: bool = False
        self._buttons: list[tuple[str, pygame.Rect]] = []
        self._worker_hits: list[tuple[pygame.Rect, int]] = []
        self._inv_hits: list[tuple[pygame.Rect, str, str]] = []
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
        self.caps_expanded: bool = False
        self.mins_expanded: bool = False
        self._scroll: dict[str, int] = {}
        # name → (view_rect, content_h, view_h) rebuilt each draw.
        self._scroll_areas: dict[str, tuple[pygame.Rect, int, int]] = {}

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
        if building.kind == BuildingKind.FIELD:
            return
        self.building_id = building.id
        self.show_player = show_player and bool(building.depositable_keys())
        self._pending_action = None
        self._moving = False
        self._hover_worker = None
        self._hover_inv = None
        self._tooltip_key = None
        self.selected_cap_key = None
        self.selected_min_key = None
        self._scroll = {}
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
        self._moving = False
        self._pending_action = None
        self._hover_worker = None
        self._hover_inv = None
        self._tooltip_key = None
        self.selected_cap_key = None
        self.selected_min_key = None
        self._scroll = {}
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
            not in (BuildingKind.HOME, BuildingKind.WORKSTATION, BuildingKind.FIELD)
            and bool(building.depositable_keys())
        )

    def _scroll_value(self, name: str, content_h: int, view_h: int) -> int:
        max_s = max(0, content_h - view_h)
        value = max(0, min(int(self._scroll.get(name, 0)), max_s))
        self._scroll[name] = value
        return value

    def _register_scroll(
        self, name: str, view: pygame.Rect, content_h: int, view_h: int
    ) -> int:
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
                self._scroll[name] = self._scroll_value(name, content_h, view_h) - dy * SCROLL_STEP
                self._scroll_value(name, content_h, view_h)
                return True
        panel = self._scroll_areas.get("panel_body")
        if panel is not None:
            rect, content_h, view_h = panel
            if content_h > view_h:
                self._scroll["panel_body"] = (
                    self._scroll_value("panel_body", content_h, view_h) - dy * SCROLL_STEP
                )
                self._scroll_value("panel_body", content_h, view_h)
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
        if self._title_rect.collidepoint(pos):
            self._moving = True
            self._move_offset = (pos[0] - self._panel_x, pos[1] - self._panel_y)
            return True
        for action, rect in self._buttons:
            if rect.collidepoint(pos):
                self._pending_action = action
                return True
        for rect, vid in self._worker_hits:
            if rect.collidepoint(pos):
                self._pending_action = f"select_worker:{vid}"
                return True
        for rect, side, key in self._inv_hits:
            if rect.collidepoint(pos):
                if side == "cap":
                    self._pending_action = f"select_cap:{key}"
                elif side == "min":
                    self._pending_action = f"select_min:{key}"
                elif side == "storage":
                    if self.show_player:
                        self._pending_action = f"xfer_to_player:{key}"
                    else:
                        self._pending_action = f"select_cap:{key}"
                else:
                    self._pending_action = f"xfer_to_storage:{key}"
                return True
        return True

    def _craft_recipes_block_height(self, recipe_count: int) -> int:
        if recipe_count <= 0:
            return 0
        return 18 + min(recipe_count * RECIPE_ROW_H, MAX_RECIPE_VIEW_H) + SECTION_GAP

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
    ) -> tuple[int, str | None]:
        """Kitchen-style recipe rows with inputs. Returns (height, hovered tip key)."""
        from inventory_ui import draw_resource_cell
        from recipes import KITCHEN_FUEL_KEY

        if not recipes:
            return 0, None
        building.ensure_recipe_state()
        surface.blit(self.font.render(title, True, COLOUR_TEXT), (x, y))
        y += 18
        content_h = len(recipes) * RECIPE_ROW_H
        view_h = min(content_h, MAX_RECIPE_VIEW_H)
        view = pygame.Rect(x, y, inner_w, view_h)
        scroll = self._register_scroll(scroll_name, view, content_h, view_h)
        old_clip = surface.get_clip()
        surface.set_clip(view.clip(old_clip) if old_clip.width else view)
        tip_key: str | None = None
        for i, recipe in enumerate(recipes):
            row_y = y + i * RECIPE_ROW_H - scroll
            if row_y + RECIPE_ROW_H < view.top or row_y > view.bottom:
                continue
            enabled = building.is_recipe_enabled(recipe.name)
            out_key = recipe.display_icon_key()
            out_n = int(next(iter(recipe.outputs.values()))) if recipe.outputs else 1
            out_cell = pygame.Rect(x, row_y, GRID_CELL, GRID_CELL)
            out_hov = (
                view.collidepoint(mouse_pos or (-1, -1))
                and mouse_pos is not None
                and out_cell.collidepoint(mouse_pos)
            )
            draw_resource_cell(
                surface,
                cell=out_cell,
                key=out_key,
                count=out_n if out_n != 1 else None,
                fonts=fonts,
                hovered=out_hov,
                dimmed=not enabled,
                active=enabled,
            )
            if out_cell.colliderect(view):
                self._buttons.append((f"toggle_recipe:{recipe.name}", out_cell))
                self._inv_tip_hits.append((out_cell, "recipe", out_key))
            if out_hov:
                tip_key = out_key
            if recipe.inputs:
                ix = out_cell.right + GRID_GAP + 6
                arrow = self.font_small.render("←", True, COLOUR_TEXT_DIM)
                surface.blit(
                    arrow,
                    (ix, row_y + (GRID_CELL - arrow.get_height()) // 2),
                )
                ix += arrow.get_width() + 6
                for in_key, in_n in recipe.inputs.items():
                    if ix + GRID_CELL > x + inner_w:
                        break
                    in_cell = pygame.Rect(ix, row_y, GRID_CELL, GRID_CELL)
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
                    ix = out_cell.right + GRID_GAP + 6
                    arrow2 = self.font_small.render("←", True, COLOUR_TEXT_DIM)
                    surface.blit(
                        arrow2,
                        (ix, row_y + (GRID_CELL - arrow2.get_height()) // 2),
                    )
                    ix += arrow2.get_width() + 6
                fuel_cell = pygame.Rect(ix, row_y, GRID_CELL, GRID_CELL)
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
            bar_x = x
            bar_y = row_y + GRID_CELL + 3
            bar_w = inner_w - 8
            pygame.draw.rect(
                surface,
                (40, 40, 40),
                pygame.Rect(bar_x, bar_y, bar_w, 7),
                border_radius=2,
            )
            fill = building.recipe_progress_fraction(recipe.name) if enabled else 0.0
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
        return view_h + SECTION_GAP, tip_key

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
    ) -> None:
        if not self.open or building is None or building.kind == BuildingKind.FIELD:
            return
        if building.id != self.building_id:
            return

        has_storage = self._has_storage(building)
        dual = self.show_player and has_storage
        storage_keys = building.depositable_keys()
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
            if building.kind == BuildingKind.KITCHEN and building.fuel_capacity > 0:
                capacity_label += (
                    f"  · fuel {building.fuel_wood}/{building.fuel_capacity}"
                )
        else:
            amounts = {}
            capacity_label = "—"

        if player_amounts is None and player_inventory is not None:
            from resources import amounts_from_obj

            player_amounts = amounts_from_obj(player_inventory)
        player_amounts = player_amounts or {}

        player_sub = "—"
        if player_inventory is not None:
            player_sub = (
                f"{player_inventory.cargo_total}/{player_inventory.capacity}"
                f"  seeds {player_inventory.seed_total}/{player_inventory.seed_capacity}"
            )

        options_h = BTN_H + 8
        if building.kind == BuildingKind.WORKSTATION:
            options_h = BTN_H + 8
        elif building.supported_work_modes():
            options_h = BTN_H * 2 + 12
        elif building.has_recipes():
            options_h = BTN_H + 8

        gather_recipes = (
            building.known_recipes() if building.is_gather_recipe_building() else ()
        )
        split_recipes = (
            building.split_recipes() if building.kind == BuildingKind.FORESTER else ()
        )
        craft_recipes = (
            building.known_recipes()
            if building.has_recipes() and not building.is_gather_recipe_building()
            else ()
        )
        recipes_h = 0
        if gather_recipes:
            cols = max(1, (380 - PAD * 2) // (GRID_CELL + GRID_GAP))
            rows = max(1, (len(gather_recipes) + cols - 1) // cols)
            content = rows * (GRID_CELL + GRID_GAP) - GRID_GAP
            recipes_h += 18 + min(content, MAX_GATHER_VIEW_H) + SECTION_GAP
        recipes_h += self._craft_recipes_block_height(len(split_recipes))
        recipes_h += self._craft_recipes_block_height(len(craft_recipes))

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
        if supports_caps and cap_keys:
            caps_h = self._stock_limit_block_height(
                expanded=self.caps_expanded,
                key_count=len(cap_keys),
                inner_w=layout_w,
            )
            min_key_count = len({*cap_keys, *building.item_mins.keys()})
            mins_h = self._stock_limit_block_height(
                expanded=self.mins_expanded,
                key_count=min_key_count,
                inner_w=layout_w,
            )

        workers_content = (
            ROW_H
            if building.kind == BuildingKind.WORKSTATION or not workers
            else len(workers) * (ROW_H + 2)
        )
        workers_h = 18 + min(workers_content, MAX_WORKER_VIEW_H)

        if dual:
            body = max(
                min(grid_height(storage_items), MAX_STORAGE_BODY_H),
                min(grid_height(player_items), MAX_STORAGE_BODY_H),
                GRID_CELL,
            )
            grid_h = 18 + 16 + body + 22
            self._panel_w = 520
        elif has_storage:
            grid_h = 18 + 16 + min(grid_height(storage_items), MAX_STORAGE_BODY_H) + 8
            self._panel_w = 380 if (building.has_recipes() or supports_caps) else 300
        else:
            grid_h = 40
            self._panel_w = 300

        body_h = (
            PAD
            + 18
            + options_h
            + SECTION_GAP
            + recipes_h
            + workers_h
            + SECTION_GAP
            + grid_h
            + caps_h
            + mins_h
            + PAD
            + 8
        )
        max_panel = WINDOW_HEIGHT - MAP_OFFSET_Y - 8
        self._panel_h = min(TITLE_BAR_H + body_h, max_panel)
        self._clamp_panel()
        panel = self.panel_rect()
        self._scroll_areas = {}
        client_h = max(1, self._panel_h - TITLE_BAR_H)
        panel_scroll = self._scroll_value("panel_body", body_h, client_h)
        client_rect = pygame.Rect(panel.x, panel.y + TITLE_BAR_H, panel.w, client_h)
        self._register_scroll("panel_body", client_rect, body_h, client_h)

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
        title = f"{BUILDING_LABELS[building.kind]} #{building.id}"
        surface.blit(
            self.font_title.render(title, True, COLOUR_TEXT),
            (panel.x + 10, panel.y + 6),
        )
        self._close_rect = pygame.Rect(panel.right - 28, panel.y + 4, 22, 20)
        close_hov = mouse_pos is not None and self._close_rect.collidepoint(mouse_pos)
        self._draw_button(surface, self._close_rect, "×", hovered=close_hov)

        self._buttons = []
        self._worker_hits = []
        self._inv_hits = []
        self._inv_tip_hits: list[tuple[pygame.Rect, str, str]] = []
        content_top = panel.y + TITLE_BAR_H
        old_body_clip = surface.get_clip()
        body_clip = client_rect.clip(old_body_clip) if old_body_clip.width else client_rect
        surface.set_clip(body_clip)
        x = panel.x + PAD
        y = content_top + PAD - panel_scroll
        inner_w = panel.w - PAD * 2

        # --- Options ---
        surface.blit(self.font.render("Options", True, COLOUR_TEXT), (x, y))
        y += 18
        bx = x
        if building.kind == BuildingKind.WORKSTATION:
            label = f"Hire ({hired_count}/{MAX_VILLAGERS})"
            w = max(120, 12 + self.font_small.size(label)[0])
            rect = pygame.Rect(bx, y, w, BTN_H)
            hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
            self._draw_button(surface, rect, label, hovered=hovered)
            self._buttons.append(("hire_villager", rect))
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
            y += BTN_H + 6
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
            if building.kind not in (
                BuildingKind.FARM,
                BuildingKind.MILL,
                BuildingKind.KITCHEN,
                BuildingKind.CRAFT_BENCH,
            ):
                clear_w = max(48, 10 + self.font_small.size("Clear")[0])
                if bx + clear_w > x + inner_w and bx > x:
                    bx = x
                    y += BTN_H + 4
                rect = pygame.Rect(bx, y, clear_w, BTN_H)
                hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
                self._draw_button(surface, rect, "Clear", hovered=hovered)
                self._buttons.append(("task_clear", rect))
            y += BTN_H + 6
            bx = x
            for label, action in (("Assign +", "assign_villager"), ("Unassign −", "unassign_villager")):
                w = max(72, 10 + self.font_small.size(label)[0])
                rect = pygame.Rect(bx, y, w, BTN_H)
                hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
                self._draw_button(surface, rect, label, hovered=hovered)
                self._buttons.append((action, rect))
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
            cols = max(1, inner_w // (GRID_CELL + GRID_GAP))
            rows = max(1, (len(gather_recipes) + cols - 1) // cols)
            content_h = rows * (GRID_CELL + GRID_GAP) - GRID_GAP
            view_h = min(content_h, MAX_GATHER_VIEW_H)
            view = pygame.Rect(x, y, inner_w, view_h)
            scroll = self._register_scroll("gather_recipes", view, content_h, view_h)
            old_clip = surface.get_clip()
            surface.set_clip(view.clip(old_clip) if old_clip.width else view)
            for i, recipe in enumerate(gather_recipes):
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
                enabled = building.is_recipe_enabled(recipe.name)
                hov = (
                    view.collidepoint(mouse_pos or (-1, -1))
                    and mouse_pos is not None
                    and cell.collidepoint(mouse_pos)
                )
                draw_resource_cell(
                    surface,
                    cell=cell,
                    key=recipe.display_icon_key(),
                    count=None,
                    fonts=fonts,
                    hovered=hov,
                    dimmed=not enabled,
                    active=enabled,
                )
                self._buttons.append((f"toggle_recipe:{recipe.name}", cell))
                self._inv_tip_hits.append((cell, "recipe", recipe.display_icon_key()))
                if hov:
                    tip_key = recipe.display_icon_key()
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
            )
            y += block_h
            if split_tip:
                tip_key = split_tip
        if craft_recipes:
            block_h, craft_tip = self._draw_craft_recipes(
                surface,
                building=building,
                recipes=craft_recipes,
                title="Recipes",
                x=x,
                y=y,
                inner_w=inner_w,
                mouse_pos=mouse_pos,
                fonts=fonts,
                scroll_name="craft_recipes",
                show_fuel=building.kind == BuildingKind.KITCHEN,
            )
            y += block_h
            if craft_tip:
                tip_key = craft_tip

        # --- Workers / haulers ---
        workers_title = (
            "Haulers"
            if building.kind == BuildingKind.HOME
            else "Workers"
            if building.kind != BuildingKind.WORKSTATION
            else "Note"
        )
        surface.blit(self.font.render(workers_title, True, COLOUR_TEXT), (x, y))
        y += 18
        if building.kind == BuildingKind.WORKSTATION:
            surface.blit(
                self.font_small.render(
                    "Hire villagers here. Assign them to workplaces.",
                    True,
                    COLOUR_TEXT_DIM,
                ),
                (x, y),
            )
            y += ROW_H
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

        if dual:
            col_w = (inner_w - INV_PANEL_GAP) // 2
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
                scroll_y=self._scroll.get("storage", 0),
                max_body_h=MAX_STORAGE_BODY_H,
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
                max_body_h=MAX_STORAGE_BODY_H,
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
                scroll_y=self._scroll.get("storage", 0),
                max_body_h=MAX_STORAGE_BODY_H,
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

        if self._supports_item_caps(building):
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

        surface.set_clip(old_body_clip)
        if body_h > client_h:
            self._draw_scrollbar(surface, client_rect, body_h, panel_scroll)

        if tip_key is not None:
            self._tooltip_key = tip_key
        if self._tooltip_key and mouse_pos is not None:
            draw_item_tooltip(
                surface, mouse_pos=mouse_pos, key=self._tooltip_key, font=self.font_small
            )
