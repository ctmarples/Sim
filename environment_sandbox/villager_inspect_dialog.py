"""Floating inspection window for a selected villager.

Cargo is shown as a grid. The player inventory grid appears only when the
menu was opened by interacting while standing on/near the villager.
"""

from __future__ import annotations

from collections.abc import Callable

import pygame

from entities import (
    RATION_LABELS,
    Inventory,
    RationMode,
    Villager,
)
from icons import blit_icon
from inventory_ui import (
    GRID_CELL,
    INV_PANEL_GAP,
    draw_clothing_slots,
    draw_hover_tooltip,
    draw_inv_grid,
    draw_item_tooltip,
    draw_tool_slot,
    grid_height,
    present_keys,
)
from resources import amounts_from_obj, resource_icon, resource_label
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
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    map_view_width,
)
from status_effects_ui import (
    HIGHLIGHT_BORDER,
    MOD_CELL,
    MOD_GAP,
    active_temp_event,
    cause_is_highlighted,
    collect_status_mods,
    draw_effect_total_columns,
    draw_mod_row,
    effect_totals,
    resolve_hover_state,
)

from villager_priority_ui import (
    SLOT_GAP,
    SLOT_SIZE,
    draw_seasonal_workplace_grid,
    draw_workplace_slot_row,
)
from villager_roster import SORT_LABELS, RosterSort, draw_skill_icons, draw_status_bar

TITLE_BAR_H = 28
PAD = 12
BTN_H = 24
ROW_H = 22
SECTION_GAP = 10
SCROLL_STEP = 28
ICON_BTN = 26
BAR_W = 72
BAR_H = 10


class VillagerInspectDialog:
    """Movable floating inspector: status, work options, inventory grid(s)."""

    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 14)
        self.font_small = pygame.font.SysFont("menlo", 12)
        self.font_tiny = pygame.font.SysFont("menlo", 11, bold=True)
        self.font_title = pygame.font.SysFont("menlo", 15, bold=True)
        self.villager_id: int | None = None
        self.show_player: bool = False
        self._buttons: list[tuple[str, pygame.Rect]] = []
        self._inv_hits: list[tuple[pygame.Rect, str, str]] = []
        self._tool_hits: list[tuple[pygame.Rect, str]] = []
        self._clothing_hits: list[tuple[pygame.Rect, str]] = []
        self._inv_tip_hits: list[tuple[pygame.Rect, str, str]] = []
        self._icon_tips: list[tuple[pygame.Rect, str]] = []
        self._pending_action: str | None = None
        self._panel_x = 80
        self._panel_y = MAP_OFFSET_Y + 40
        self._panel_w = 300
        self._panel_h = 360
        self._moving = False
        self._move_offset = (0, 0)
        self._close_rect = pygame.Rect(0, 0, 0, 0)
        self._title_rect = pygame.Rect(0, 0, 0, 0)
        self._hover_inv: tuple[str, str] | None = None
        self._tooltip_key: str | None = None
        self._tooltip_text: str | None = None
        self.embedded = False
        self._scroll: dict[str, int] = {}
        self._scroll_areas: dict[str, tuple[pygame.Rect, int, int]] = {}

    @property
    def open(self) -> bool:
        return self.villager_id is not None

    def configure_embed(self, rect: pygame.Rect) -> None:
        self.embedded = True
        self._panel_x = rect.x
        self._panel_y = rect.y
        self._panel_w = max(120, rect.w)
        self._panel_h = max(120, rect.h)

    def open_for(
        self,
        villager: Villager,
        *,
        screen_xy: tuple[int, int] | None = None,
        show_player: bool = False,
    ) -> None:
        self.villager_id = villager.id
        self.show_player = show_player
        self._pending_action = None
        self._moving = False
        self._hover_inv = None
        self._tooltip_key = None
        self._tooltip_text = None
        self._scroll = {}
        self._scroll_areas = {}
        self._panel_w = 520 if show_player else 320
        self._panel_h = 420
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
        self.villager_id = None
        self.show_player = False
        self.embedded = False
        self._moving = False
        self._pending_action = None
        self._hover_inv = None
        self._tooltip_key = None
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

    def _clamp_panel(self) -> None:
        self._panel_x = max(4, min(self._panel_x, WINDOW_WIDTH - self._panel_w - 4))
        self._panel_y = max(
            MAP_OFFSET_Y, min(self._panel_y, WINDOW_HEIGHT - self._panel_h - 4)
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
        thumb_y = view.y + int(
            (view.h - thumb_h) * (scroll / max(1, content_h - view.h))
        )
        pygame.draw.rect(
            surface,
            (120, 130, 140),
            pygame.Rect(track.x, thumb_y, track.w, thumb_h),
            border_radius=2,
        )

    def handle_mousewheel(self, dy: int, pos: tuple[int, int]) -> bool:
        if not self.open or not self.contains(pos):
            return False
        panel = self._scroll_areas.get("panel_body")
        if panel is not None:
            rect, content_h, view_h = panel
            if content_h > view_h:
                self._scroll["panel_body"] = (
                    self._scroll_value("panel_body", content_h, view_h) - dy * SCROLL_STEP
                )
                self._scroll_value("panel_body", content_h, view_h)
        return True

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
        for action, rect in self._buttons:
            if rect.collidepoint(pos):
                self._pending_action = action
                return True
        for rect, action in self._tool_hits:
            if rect.collidepoint(pos):
                self._pending_action = action
                return True
        for rect, action in self._clothing_hits:
            if rect.collidepoint(pos):
                self._pending_action = action
                return True
        for rect, side, key in self._inv_hits:
            if rect.collidepoint(pos):
                if side == "villager":
                    self._pending_action = f"xfer_to_player:{key}"
                else:
                    self._pending_action = f"xfer_to_villager:{key}"
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
        self._hover_inv = None
        self._tooltip_key = None
        if self.contains(pos):
            for rect, side, key in self._inv_hits:
                if rect.collidepoint(pos):
                    self._hover_inv = (side, key)
                    self._tooltip_key = key
                    break
            if self._tooltip_key is None:
                for rect, side, key in self._inv_tip_hits:
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

    def _fonts(self) -> tuple[pygame.font.Font, pygame.font.Font, pygame.font.Font]:
        return self.font, self.font_small, self.font_tiny

    def _draw_icon_btn(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        *,
        icon: str | None = None,
        label: str | None = None,
        active: bool = False,
        hovered: bool = False,
        border: tuple[int, int, int] | None = None,
        fill: tuple[int, int, int] | None = None,
    ) -> None:
        if fill is not None:
            colour = fill
        elif active:
            colour = COLOUR_TOOLBAR_BTN_ACTIVE
        elif hovered:
            colour = COLOUR_TOOLBAR_BTN_HOVER
        else:
            colour = COLOUR_TOOLBAR_BTN
        edge = border if border is not None else COLOUR_TOOLBAR_BORDER
        pygame.draw.rect(surface, colour, rect, border_radius=4)
        pygame.draw.rect(surface, edge, rect, 2 if border is not None else 1, border_radius=4)
        if icon:
            blit_icon(surface, icon, rect.centerx, rect.centery, min(rect.w, rect.h) - 6)
        elif label:
            text = self.font_small.render(label, True, COLOUR_TEXT)
            surface.blit(
                text,
                (
                    rect.x + (rect.w - text.get_width()) // 2,
                    rect.y + (rect.h - text.get_height()) // 2,
                ),
            )

    def draw(
        self,
        surface: pygame.Surface,
        villager: Villager | None,
        *,
        building_icon_for: Callable[[int | None], str | None],
        housing_icon: str = "tent",
        current_season: Season | None = None,
        calendar_day: int = 0,
        mouse_pos: tuple[int, int] | None = None,
        player_inventory: Inventory | None = None,
        requirement_rows: list[dict] | None = None,
    ) -> None:
        if not self.open or villager is None:
            return
        if villager.id != self.villager_id:
            return

        villager_amounts = amounts_from_obj(villager.inventory)
        player_amounts = (
            amounts_from_obj(player_inventory) if player_inventory is not None else {}
        )
        v_sub = (
            f"{villager.inventory.cargo_total}/{villager.inventory.effective_capacity}"
            f"  seeds {villager.inventory.seed_total}/{villager.inventory.seed_capacity}"
        )
        p_sub = "—"
        if player_inventory is not None:
            p_sub = (
                f"{player_inventory.cargo_total}/{player_inventory.effective_capacity}"
                f"  seeds {player_inventory.seed_total}/{player_inventory.seed_capacity}"
            )

        dual = self.show_player
        embed_w, embed_h = self._panel_w, self._panel_h
        v_items = len(present_keys(villager_amounts, None))
        p_items = len(present_keys(player_amounts, None))
        if dual:
            grid_h = (
                18
                + 16
                + max(grid_height(v_items), grid_height(p_items), GRID_CELL)
                + 22
            )
            self._panel_w = 520
        else:
            grid_h = 18 + 16 + grid_height(v_items) + 8
            self._panel_w = 380

        prio_extra = 4 * (SLOT_SIZE + 4) if villager.seasonal_priorities else (SLOT_SIZE + 8)
        skill_row_h = 14 + 14 + 4
        body_h = (
            PAD
            + 18
            + skill_row_h
            + 16
            + BAR_H
            + 8
            + ICON_BTN
            + 4  # home
            + MOD_CELL
            + 4  # meal
            + MOD_CELL
            + 4  # buffs
            + MOD_CELL
            + 4  # debuffs
            + ICON_BTN
            + 4  # requirements
            + MOD_CELL
            + 4  # events
            + SLOT_SIZE
            + 6
            + SECTION_GAP
            + 18
            + ICON_BTN
            + 8
            + prio_extra
            + SECTION_GAP
            + ICON_BTN
            + 8
            + GRID_CELL
            + 26
            + GRID_CELL
            + 24
            + SECTION_GAP
            + grid_h
            + PAD
        )
        if self.embedded:
            self._panel_w = embed_w
            self._panel_h = embed_h
        else:
            max_panel = WINDOW_HEIGHT - MAP_OFFSET_Y - 8
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
            self.font_title.render(
                villager.name or f"Villager #{villager.id}", True, COLOUR_TEXT
            ),
            (panel.x + 10, panel.y + 6),
        )
        if self.embedded:
            self._close_rect = pygame.Rect(0, 0, 0, 0)
        else:
            self._close_rect = pygame.Rect(panel.right - 28, panel.y + 4, 22, 20)
            close_hov = mouse_pos is not None and self._close_rect.collidepoint(mouse_pos)
            self._draw_button(surface, self._close_rect, "×", hovered=close_hov)

        self._buttons = []
        self._inv_hits = []
        self._tool_hits = []
        self._clothing_hits = []
        self._inv_tip_hits = []
        self._icon_tips = []
        self._tooltip_key = None
        self._tooltip_text = None
        old_clip = surface.get_clip()
        body_clip = client_rect.clip(old_clip) if old_clip.width else client_rect
        surface.set_clip(body_clip)
        x = panel.x + PAD
        y = panel.y + TITLE_BAR_H + PAD - panel_scroll
        inner_w = panel.w - PAD * 2

        # --- Status ---
        surface.blit(self.font.render("Status", True, COLOUR_TEXT), (x, y))
        y += 18

        skill_w, skill_tips = draw_skill_icons(
            surface, x, y, villager.skills, self.font_tiny, icon_size=14
        )
        self._icon_tips.extend(skill_tips)
        walk_t, work_t, hunger_t = effect_totals(
            food_walk=villager.food_walk_mult,
            food_work=villager.food_work_mult,
            food_hunger=villager.food_hunger_mult,
            inventory=villager.inventory,
            calendar_day=calendar_day,
        )
        _, total_tips = draw_effect_total_columns(
            surface,
            x + skill_w + 6,
            y,
            walk=walk_t,
            work=work_t,
            hunger=hunger_t,
            font=self.font_tiny,
        )
        self._icon_tips.extend(total_tips)
        y += 14 + 14 + 4

        state = (
            "Seeking food"
            if villager.seeking_food
            else villager.state.name.replace("_", " ").title()
        )
        surface.blit(self.font_small.render(state, True, COLOUR_TEXT_DIM), (x, y))
        y += 16

        # Energy / Satiation / Happiness — same order and labels as roster
        bar_y = y
        bx = x
        for sort_key, kind, value in (
            (RosterSort.ENERGY, "energy", villager.energy),
            (RosterSort.SATIATION, "sat", villager.satiation),
            (RosterSort.HAPPINESS, "happy", villager.happiness),
        ):
            label = SORT_LABELS[sort_key]
            surface.blit(
                self.font_tiny.render(label, True, COLOUR_TEXT_DIM),
                (bx, bar_y + 1),
            )
            draw_status_bar(
                surface, bx + 18, bar_y, BAR_W - 18, BAR_H, value, kind=kind
            )
            bx += BAR_W + 6
        y += BAR_H + 8

        # Home: housing type icon
        surface.blit(
            self.font_small.render("Home:", True, COLOUR_TEXT_DIM),
            (x, y + 5),
        )
        home_rect = pygame.Rect(x + 52, y, ICON_BTN, ICON_BTN)
        home_hov = mouse_pos is not None and home_rect.collidepoint(mouse_pos)
        self._draw_icon_btn(surface, home_rect, icon=housing_icon, hovered=home_hov)
        self._buttons.append(("assign_housing", home_rect))
        home_tip = (
            "Click to assign housing"
            if not villager.housed
            else f"Home ({housing_icon.replace('_', ' ')}) — click to change"
        )
        if not villager.housed:
            home_tip = f"Needs housing level ≥{villager.housing_need} — click to assign"
        self._icon_tips.append((home_rect, home_tip))
        y += ICON_BTN + 4

        all_mods = collect_status_mods(
            last_meal=list(villager.last_meal),
            inventory=villager.inventory,
            calendar_day=calendar_day,
        )
        buffs = [m for m in all_mods if m.is_buff]
        debuffs = [m for m in all_mods if m.is_debuff]
        temp_ev = active_temp_event(villager.inventory, calendar_day)
        content_x = x + 52
        meal_y = y
        buff_y = meal_y + MOD_CELL + 4
        debuff_y = buff_y + MOD_CELL + 4
        req_y = debuff_y + MOD_CELL + 4
        events_y = req_y + ICON_BTN + 4
        hover = resolve_hover_state(
            mouse_pos,
            meal_keys=list(villager.last_meal[:3]),
            meal_x=content_x,
            meal_y=meal_y,
            buffs=buffs,
            debuffs=debuffs,
            buff_x=content_x,
            buff_y=buff_y,
            debuff_x=content_x,
            debuff_y=debuff_y,
            temp_event=temp_ev,
            event_x=content_x,
            event_y=events_y,
            cell_size=MOD_CELL,
            gap=MOD_GAP,
        )

        # Last meal icons
        surface.blit(
            self.font_small.render("Meal:", True, COLOUR_TEXT_DIM),
            (x, meal_y + MOD_CELL // 2 - 6),
        )
        meal_x = content_x
        if villager.last_meal:
            for key in villager.last_meal[:3]:
                mrect = pygame.Rect(meal_x, meal_y, MOD_CELL, MOD_CELL)
                hi = cause_is_highlighted("meal", key, hover)
                mhov = mouse_pos is not None and mrect.collidepoint(mouse_pos)
                self._draw_icon_btn(
                    surface,
                    mrect,
                    icon=resource_icon(key),
                    hovered=mhov or hi,
                    border=HIGHLIGHT_BORDER if hi else None,
                )
                self._icon_tips.append((mrect, resource_label(key)))
                meal_x += MOD_CELL + MOD_GAP
        else:
            surface.blit(
                self.font_small.render("—", True, COLOUR_TEXT_DIM),
                (meal_x, meal_y + MOD_CELL // 2 - 6),
            )
        y = buff_y

        # Buff / Debuff rows (compound cause→effect icons)
        surface.blit(
            self.font_small.render("Buffs:", True, COLOUR_TEXT_DIM),
            (x, y + MOD_CELL // 2 - 6),
        )
        if buffs:
            _, buff_hits, _ = draw_mod_row(
                surface,
                content_x,
                y,
                buffs,
                mouse_pos=mouse_pos,
                hover=hover,
                icon_size=MOD_CELL,
                gap=MOD_GAP,
            )
            for rect, mod in buff_hits:
                self._icon_tips.append((rect, mod.tip))
        else:
            surface.blit(
                self.font_small.render("—", True, COLOUR_TEXT_DIM),
                (content_x, y + MOD_CELL // 2 - 6),
            )
        y = debuff_y

        surface.blit(
            self.font_small.render("Debuffs:", True, COLOUR_TEXT_DIM),
            (x, y + MOD_CELL // 2 - 6),
        )
        if debuffs:
            _, debuff_hits, _ = draw_mod_row(
                surface,
                content_x,
                y,
                debuffs,
                mouse_pos=mouse_pos,
                hover=hover,
                icon_size=MOD_CELL,
                gap=MOD_GAP,
            )
            for rect, mod in debuff_hits:
                self._icon_tips.append((rect, mod.tip))
        else:
            surface.blit(
                self.font_small.render("—", True, COLOUR_TEXT_DIM),
                (content_x, y + MOD_CELL // 2 - 6),
            )
        y = req_y

        # Requirements (green = met, red = unmet + 2 coins/season)
        surface.blit(
            self.font_small.render("Reqs:", True, COLOUR_TEXT_DIM),
            (x, y + 5),
        )
        req_x = x + 52
        rows = list(requirement_rows or [])
        if rows:
            for row in rows:
                ic = str(row.get("icon") or "tent")
                met = bool(row.get("met"))
                coins = int(row.get("coins", 0) or 0)
                rrect = pygame.Rect(req_x, y, ICON_BTN, ICON_BTN)
                rhov = mouse_pos is not None and rrect.collidepoint(mouse_pos)
                border = (70, 160, 85) if met else (190, 70, 60)
                fill = (40, 70, 48) if met else (70, 40, 40)
                self._draw_icon_btn(
                    surface,
                    rrect,
                    icon=ic,
                    hovered=rhov,
                    border=border,
                    fill=fill,
                )
                tip = str(row.get("label") or "Requirement")
                if met:
                    tip = f"{tip} (met)"
                else:
                    tip = f"{tip} — {coins} coins/season"
                    if coins > 0:
                        coin_r = pygame.Rect(rrect.right + 2, y + 4, 18, 18)
                        blit_icon(surface, "coins", coin_r.centerx, coin_r.centery, 14)
                        cost = self.font_tiny.render(str(coins), True, (220, 180, 90))
                        surface.blit(cost, (coin_r.right + 1, y + 7))
                        self._icon_tips.append(
                            (coin_r, f"{coins} coins per season while unmet")
                        )
                        req_x = coin_r.right + cost.get_width() + 8
                    else:
                        req_x = rrect.right + 4
                    self._icon_tips.append((rrect, tip))
                    continue
                self._icon_tips.append((rrect, tip))
                req_x = rrect.right + 4
        else:
            surface.blit(
                self.font_small.render("—", True, COLOUR_TEXT_DIM),
                (req_x, y + 4),
            )
        y += ICON_BTN + 4

        # Events: temperature cause + happiness history
        surface.blit(
            self.font_small.render("Events:", True, COLOUR_TEXT_DIM),
            (x, events_y + MOD_CELL // 2 - 6),
        )
        event_x = content_x
        any_event = False
        if temp_ev is not None:
            any_event = True
            ic = str(temp_ev["icon"])
            key = str(temp_ev["key"])
            irect = pygame.Rect(event_x, events_y, MOD_CELL, MOD_CELL)
            hi = cause_is_highlighted("events", key, hover)
            ihov = mouse_pos is not None and irect.collidepoint(mouse_pos)
            self._draw_icon_btn(
                surface,
                irect,
                icon=ic,
                hovered=ihov or hi,
                border=HIGHLIGHT_BORDER if hi else None,
            )
            self._icon_tips.append((irect, str(temp_ev["tip"])))
            event_x += MOD_CELL + MOD_GAP
        events = list(
            getattr(villager, "happiness_events", None)
            or getattr(villager, "happiness_impacts", None)
            or []
        )
        if events:
            for ev in events[-6:]:
                if not isinstance(ev, dict):
                    continue
                any_event = True
                ic = str(ev.get("icon") or "coins")
                irect = pygame.Rect(event_x, events_y, ICON_BTN, ICON_BTN)
                ihov = mouse_pos is not None and irect.collidepoint(mouse_pos)
                self._draw_icon_btn(surface, irect, icon=ic, hovered=ihov)
                delta = int(round(float(ev.get("delta", 0) or 0)))
                sign = "+" if delta > 0 else ""
                label = str(ev.get("label") or "Event")
                if delta != 0:
                    tip = (
                        f"{label}"
                        if f"{sign}{delta}" in label
                        else f"{label} ({sign}{delta})"
                    )
                else:
                    tip = label
                badge = self.font_tiny.render(
                    f"{sign}{delta}" if delta != 0 else "·",
                    True,
                    (120, 200, 120)
                    if delta > 0
                    else ((200, 120, 100) if delta < 0 else COLOUR_TEXT_DIM),
                )
                surface.blit(
                    badge,
                    (
                        irect.x + (irect.w - badge.get_width()) // 2,
                        irect.bottom - badge.get_height(),
                    ),
                )
                self._icon_tips.append((irect, tip))
                event_x += ICON_BTN + 2
        if not any_event:
            surface.blit(
                self.font_small.render("—", True, COLOUR_TEXT_DIM),
                (event_x, events_y + MOD_CELL // 2 - 6),
            )
        y = events_y + MOD_CELL + 4

        display_season = current_season if villager.seasonal_priorities else None
        status_slots = villager.active_workplace_slot_ids(display_season)
        surface.blit(
            self.font_small.render("Workplace:", True, COLOUR_TEXT_DIM),
            (x, y + 6),
        )
        draw_workplace_slot_row(
            surface,
            x + 82,
            y,
            list(status_slots),
            icon_for_building=building_icon_for,
            font=self.font_small,
            interactive=False,
        )
        slot_x = x + 82
        for slot_i, bid in enumerate(list(status_slots)[:3]):
            srect = pygame.Rect(slot_x, y, SLOT_SIZE, SLOT_SIZE)
            icon = building_icon_for(bid)
            if bid is None:
                tip = "Empty workplace slot"
            else:
                tip = (icon or "workplace").replace("_", " ").title()
            self._icon_tips.append((srect, tip))
            slot_x += SLOT_SIZE + SLOT_GAP
        y += SLOT_SIZE + 6 + SECTION_GAP

        # --- Work options ---
        surface.blit(self.font.render("Work", True, COLOUR_TEXT), (x, y))
        y += 18

        # Ration: meat icon buttons (½ / ×1 / ×2)
        surface.blit(
            self.font_small.render("Ration", True, COLOUR_TEXT_DIM),
            (x, y + 5),
        )
        bx = x + 58
        for mode in (RationMode.HALF, RationMode.NORMAL, RationMode.DOUBLE):
            rect = pygame.Rect(bx, y, ICON_BTN, ICON_BTN)
            active = villager.ration_mode == mode
            hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
            self._draw_icon_btn(
                surface, rect, icon=resource_icon("meat"), active=active, hovered=hovered
            )
            badge = self.font_tiny.render(RATION_LABELS[mode], True, COLOUR_TEXT)
            surface.blit(
                badge,
                (
                    rect.x + (rect.w - badge.get_width()) // 2,
                    rect.bottom - badge.get_height() - 1,
                ),
            )
            self._buttons.append((f"ration_{mode.name}", rect))
            self._icon_tips.append(
                (rect, f"Ration {RATION_LABELS[mode]}")
            )
            bx += ICON_BTN + 4
        toggle_rect = pygame.Rect(x + inner_w - ICON_BTN, y, ICON_BTN, ICON_BTN)
        toggle_hov = mouse_pos is not None and toggle_rect.collidepoint(mouse_pos)
        self._draw_icon_btn(
            surface,
            toggle_rect,
            label="S",
            active=villager.seasonal_priorities,
            hovered=toggle_hov,
        )
        self._buttons.append(("seasonal_toggle", toggle_rect))
        self._icon_tips.append(
            (
                toggle_rect,
                "Seasonal priorities on"
                if villager.seasonal_priorities
                else "Seasonal priorities off",
            )
        )
        y += ICON_BTN + 8

        if villager.seasonal_priorities:
            surface.blit(
                self.font_small.render("Seasonal", True, COLOUR_TEXT_DIM),
                (x, y + 6),
            )
            villager.ensure_season_workplace_slots()
            grid_hits, grid_h = draw_seasonal_workplace_grid(
                surface,
                x + 58,
                y,
                villager.season_workplace_slots,
                icon_for_building=building_icon_for,
                font=self.font_small,
                font_small=self.font_tiny,
                current_season=current_season,
                mouse_pos=mouse_pos,
            )
            for action, rect in grid_hits:
                self._buttons.append((action, rect))
                # assign_workplace:slot:SEASON
                parts = action.split(":")
                tip = "Workplace slot (click to assign)"
                if len(parts) >= 3:
                    try:
                        slot_i = int(parts[1])
                        season_name = parts[2]
                        row = list(
                            villager.season_workplace_slots.get(
                                season_name, [None, None, None]
                            )
                        )
                        bid = row[slot_i] if 0 <= slot_i < len(row) else None
                        icon = building_icon_for(bid)
                        if bid is None:
                            tip = f"{season_name.title()} empty slot"
                        else:
                            tip = f"{season_name.title()}: {(icon or 'workplace').replace('_', ' ').title()}"
                    except ValueError:
                        pass
                self._icon_tips.append((rect, tip))
            y += max(grid_h, SLOT_SIZE) + 8
        else:
            surface.blit(
                self.font_small.render("Priority", True, COLOUR_TEXT_DIM),
                (x, y + 6),
            )
            villager.ensure_workplace_slots()
            row_hits, _ = draw_workplace_slot_row(
                surface,
                x + 58,
                y,
                list(villager.workplace_slots),
                icon_for_building=building_icon_for,
                font=self.font_small,
                mouse_pos=mouse_pos,
            )
            for action, rect in row_hits:
                self._buttons.append((action, rect))
                bid = None
                try:
                    slot_i = int(action.rsplit(":", 1)[-1])
                    slots = list(villager.workplace_slots)
                    if 0 <= slot_i < len(slots):
                        bid = slots[slot_i]
                except ValueError:
                    bid = None
                icon = building_icon_for(bid)
                tip = (
                    "Empty workplace slot"
                    if bid is None
                    else (icon or "workplace").replace("_", " ").title()
                )
                self._icon_tips.append((rect, tip + " (click to assign)"))
            y += SLOT_SIZE + 8

        y += SECTION_GAP

        tool_h, tool_hits, tool_tip = draw_tool_slot(
            surface,
            origin=(x, y),
            equipped_tools=list(villager.inventory.equipped_tools),
            mouse_pos=mouse_pos,
            fonts=self._fonts(),
            interactive=True,
        )
        self._tool_hits = tool_hits
        y += tool_h + 4
        clothes_h, clothes_hits, clothes_tip = draw_clothing_slots(
            surface,
            origin=(x, y),
            equipped_clothing=dict(villager.inventory.equipped_clothing),
            mouse_pos=mouse_pos,
            fonts=self._fonts(),
            interactive=True,
        )
        self._clothing_hits = clothes_hits
        y += clothes_h + SECTION_GAP
        surface.blit(
            self.font_small.render(
                "Click a slot to equip or unequip tools / clothes.",
                True,
                COLOUR_TEXT_DIM,
            ),
            (x, y - 6),
        )

        tip_key: str | None = tool_tip or clothes_tip
        if dual:
            col_w = (inner_w - INV_PANEL_GAP) // 2
            left_h, left_hits, left_tips, left_hov, *_ = draw_inv_grid(
                surface,
                origin=(x, y),
                width=col_w,
                title="Villager",
                subtitle=v_sub,
                amounts=villager_amounts,
                allowed=None,
                side="villager",
                mouse_pos=mouse_pos,
                fonts=self._fonts(),
                interactive=True,
                hover_inv=self._hover_inv,
            )
            right_h, right_hits, right_tips, right_hov, *_ = draw_inv_grid(
                surface,
                origin=(x + col_w + INV_PANEL_GAP, y),
                width=col_w,
                title="Player",
                subtitle=p_sub,
                amounts=player_amounts,
                allowed=None,
                side="player",
                mouse_pos=mouse_pos,
                fonts=self._fonts(),
                interactive=True,
                hover_inv=self._hover_inv,
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
        else:
            h, _hits, tips, hov, *_ = draw_inv_grid(
                surface,
                origin=(x, y),
                width=inner_w,
                title="Carried",
                subtitle=v_sub,
                amounts=villager_amounts,
                allowed=None,
                side="villager",
                mouse_pos=mouse_pos,
                fonts=self._fonts(),
                interactive=False,
                hover_inv=self._hover_inv,
            )
            self._inv_tip_hits.extend(tips)
            if hov:
                tip_key = hov[1]
            y += h

        surface.set_clip(old_clip)
        self._draw_scrollbar(surface, client_rect, body_h, panel_scroll)

        if tip_key is not None:
            if tip_key == "_empty_tool_":
                self._tooltip_text = "Empty tool slot"
            else:
                self._tooltip_key = tip_key
        if mouse_pos is not None:
            for rect, text in self._icon_tips:
                if rect.collidepoint(mouse_pos):
                    self._tooltip_text = text
                    break
        if self._tooltip_text and mouse_pos is not None:
            draw_hover_tooltip(
                surface,
                mouse_pos=mouse_pos,
                text=self._tooltip_text,
                font=self.font_small,
            )
        elif self._tooltip_key and mouse_pos is not None:
            draw_item_tooltip(
                surface, mouse_pos=mouse_pos, key=self._tooltip_key, font=self.font_small
            )

        pygame.draw.rect(surface, COLOUR_SELECTED_ENTITY, panel, 1, border_radius=6)
