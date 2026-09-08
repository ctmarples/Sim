"""Floating inspection window for a selected villager.

Cargo is shown as a grid. The player inventory grid appears only when the
menu was opened by interacting while standing on/near the villager.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from pathlib import Path

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

COLOUR_TEXT = (72, 48, 31)
COLOUR_TEXT_DIM = (112, 84, 58)
_BOOK_FONT_PATH = (
    Path(__file__).resolve().parent
    / "assets/fonts/Gloria_Hallelujah/GloriaHallelujah-Regular.ttf"
)

from villager_priority_ui import (
    SLOT_GAP,
    SLOT_SIZE,
    draw_seasonal_workplace_plan_grid,
    draw_workplace_plan_row,
    plan_slot_tip,
)
from villager_roster import SORT_LABELS, RosterSort, draw_skill_icons, draw_status_bar

TITLE_BAR_H = 28
PAD = 12
BTN_H = 24
ROW_H = 22
SECTION_GAP = 10
SCROLL_IMPULSE = 760.0
SCROLL_FRICTION = 8.5
ICON_BTN = 26
BAR_W = 72
BAR_H = 10
CAT_TAB_H = BTN_H


class DetailCategory(str, Enum):
    OVERVIEW = "overview"
    WORK = "work"
    SKILLS = "skills"
    BUFFS = "buffs"
    INVENTORY = "inventory"
    TOOLS = "inventory"  # compatibility with the former standalone layout


_DETAIL_TABS: tuple[tuple[DetailCategory, str, str], ...] = (
    (DetailCategory.OVERVIEW, "Overview", "Status, home, and expectations"),
    (DetailCategory.WORK, "Work", "Workplace and seasonal assignments"),
    (DetailCategory.SKILLS, "Skills", "Skills and effect totals"),
    (DetailCategory.BUFFS, "Buffs", "Meals, buffs, debuffs, and events"),
    (DetailCategory.INVENTORY, "Inventory", "Tools, clothing, and carried items"),
)


class VillagerInspectDialog:
    """Movable floating inspector: status, work options, inventory grid(s)."""

    def __init__(self) -> None:
        self.font = pygame.font.Font(str(_BOOK_FONT_PATH), 14)
        self.font_small = pygame.font.Font(str(_BOOK_FONT_PATH), 12)
        self.font_tiny = pygame.font.Font(str(_BOOK_FONT_PATH), 11)
        self.font_title = pygame.font.Font(str(_BOOK_FONT_PATH), 15)
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
        self.detail_category = DetailCategory.OVERVIEW
        self._scroll: dict[str, float] = {}
        self._scroll_velocity: dict[str, float] = {}
        self._scroll_tick = pygame.time.get_ticks()
        self._measured_body_h = 0
        self._scroll_areas: dict[str, tuple[pygame.Rect, int, int]] = {}
        self._section_anchors: dict[DetailCategory, int] = {}
        self._scrollbar_track = pygame.Rect(0, 0, 0, 0)
        self._scrollbar_thumb = pygame.Rect(0, 0, 0, 0)
        self._scroll_dragging = False
        self._scroll_drag_offset = 0

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
        self._scroll_velocity = {}
        self._scroll_tick = pygame.time.get_ticks()
        self._measured_body_h = 0
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

    def _clamp_panel(self) -> None:
        self._panel_x = max(4, min(self._panel_x, WINDOW_WIDTH - self._panel_w - 4))
        self._panel_y = max(
            MAP_OFFSET_Y, min(self._panel_y, WINDOW_HEIGHT - self._panel_h - 4)
        )

    def _scroll_value(self, name: str, content_h: int, view_h: int) -> float:
        max_s = max(0, content_h - view_h)
        value = max(0.0, min(float(self._scroll.get(name, 0.0)), float(max_s)))
        self._scroll[name] = value
        return value

    def _advance_scroll(self) -> None:
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
            self._scrollbar_track = pygame.Rect(0, 0, 0, 0)
            self._scrollbar_thumb = pygame.Rect(0, 0, 0, 0)
            return
        track = pygame.Rect(view.right + 3, view.y, 5, view.h)
        pygame.draw.rect(surface, (126, 91, 52), track, border_radius=2)
        ratio = view.h / content_h
        thumb_h = max(12, int(view.h * ratio))
        thumb_y = view.y + int(
            (view.h - thumb_h) * (scroll / max(1, content_h - view.h))
        )
        thumb = pygame.Rect(track.x, thumb_y, track.w, thumb_h)
        pygame.draw.rect(
            surface,
            (218, 119, 55),
            thumb,
            border_radius=2,
        )
        self._scrollbar_track = track
        self._scrollbar_thumb = thumb

    def handle_mousewheel(self, dy: int, pos: tuple[int, int]) -> bool:
        if not self.open or not self.contains(pos):
            return False
        panel = self._scroll_areas.get("panel_body")
        if panel is not None:
            rect, content_h, view_h = panel
            if content_h > view_h:
                self._scroll_velocity["panel_body"] = self._scroll_velocity.get("panel_body", 0.0) - float(dy) * SCROLL_IMPULSE
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
        if self._scrollbar_thumb.collidepoint(pos):
            self._scroll_dragging = True
            self._scroll_drag_offset = pos[1] - self._scrollbar_thumb.y
            self._scroll_velocity["panel_body"] = 0.0
            return True
        if not self.embedded and self._title_rect.collidepoint(pos):
            self._moving = True
            self._move_offset = (pos[0] - self._panel_x, pos[1] - self._panel_y)
            return True
        for action, rect in self._buttons:
            if rect.collidepoint(pos):
                if action.startswith("diary_link:"):
                    try:
                        category = DetailCategory(action.split(":", 1)[1])
                    except ValueError:
                        return True
                    self.detail_category = category
                    self._scroll["panel_body"] = float(
                        self._section_anchors.get(category, 0)
                    )
                    self._scroll_velocity["panel_body"] = 0.0
                    return True
                if action.startswith("detail_cat:"):
                    try:
                        self.detail_category = DetailCategory(action.split(":", 1)[1])
                    except ValueError:
                        pass
                    return True
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
        if self._scroll_dragging:
            area = self._scroll_areas.get("panel_body")
            if area is not None:
                _view, content_h, view_h = area
                travel = max(1, self._scrollbar_track.h - self._scrollbar_thumb.h)
                thumb_y = max(
                    self._scrollbar_track.y,
                    min(
                        pos[1] - self._scroll_drag_offset,
                        self._scrollbar_track.bottom - self._scrollbar_thumb.h,
                    ),
                )
                ratio = (thumb_y - self._scrollbar_track.y) / travel
                self._scroll["panel_body"] = ratio * max(0, content_h - view_h)
            return True
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
        if self._scroll_dragging:
            self._scroll_dragging = False
            return True
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

    def _fonts(self) -> tuple[pygame.font.Font, pygame.font.Font, pygame.font.Font]:
        return self.font, self.font_small, self.font_tiny

    @staticmethod
    def _detail_category_panel_height() -> int:
        skills_h = 14 + 14 + 4
        tools_h = 18 + GRID_CELL + 8 + 18 + 12 + GRID_CELL + 8 + 14
        buffs_h = 3 * (MOD_CELL + 4) + (ICON_BTN + 4) + (MOD_CELL + 4)
        return max(skills_h, tools_h, buffs_h)

    def _draw_detail_category_tabs(
        self,
        surface: pygame.Surface,
        x: int,
        y: int,
        inner_w: int,
        mouse_pos: tuple[int, int] | None,
    ) -> int:
        bx = x
        row_y = y
        for cat, label, tip in _DETAIL_TABS:
            w = max(52, 10 + self.font_small.size(label)[0])
            if bx + w > x + inner_w and bx > x:
                row_y += CAT_TAB_H + 4
                bx = x
            rect = pygame.Rect(bx, row_y, w, CAT_TAB_H)
            active = self.detail_category == cat
            hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
            self._draw_button(surface, rect, label, active=active, hovered=hovered)
            self._buttons.append((f"detail_cat:{cat.value}", rect))
            if hovered:
                self._icon_tips.append((rect, tip))
            bx += w + 4
        return row_y + CAT_TAB_H + 4

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
        if not self.embedded or label is None:
            pygame.draw.rect(surface, colour, rect, border_radius=4)
            pygame.draw.rect(
                surface,
                edge,
                rect,
                2 if border is not None else 1,
                border_radius=4,
            )
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

    def _draw_diary_page(
        self,
        surface: pygame.Surface,
        villager: Villager,
        *,
        building_icon_for: Callable[[int | None], str | None],
        housing_icon: str,
        current_season: Season | None,
        calendar_day: int,
        mouse_pos: tuple[int, int] | None,
        requirement_rows: list[dict] | None,
        activity_label: str | None,
        extra_status_mods: list | None = None,
        political_work_mult: float = 1.0,
    ) -> None:
        """Focused, paper-native inspect pages modelled on the field inspector."""
        panel = self.panel_rect()
        pad = 10
        x = panel.x + pad
        inner_w = panel.w - pad * 2 - 10
        old_clip = surface.get_clip()
        panel_clip = panel.clip(old_clip) if old_clip.width else panel
        surface.set_clip(panel_clip)

        self._buttons = []
        self._inv_hits = []
        self._tool_hits = []
        self._clothing_hits = []
        self._inv_tip_hits = []
        self._icon_tips = []
        self._tooltip_key = None
        self._tooltip_text = None

        is_player = villager.id < 0
        header_y = panel.y
        title = (
            "PLAYER"
            if is_player
            else (villager.name or f"VILLAGER #{villager.id}").upper()
        )
        surface.blit(self.font_title.render(title, True, COLOUR_TEXT), (x, header_y))
        header_y += self.font_title.get_linesize() + 5

        # Page navigation uses the same marker treatment as the field planner.
        tx = x
        for category, label, tip in _DETAIL_TABS:
            width = self.font_small.size(label)[0] + 8
            if tx + width > panel.right - pad - 10 and tx > x:
                tx = x
                header_y += CAT_TAB_H + 3
            rect = pygame.Rect(tx, header_y, width, CAT_TAB_H)
            active = self.detail_category == category
            hovered = mouse_pos is not None and rect.collidepoint(mouse_pos)
            if active or hovered:
                marker = pygame.Surface(rect.size, pygame.SRCALPHA)
                colour = (221, 174, 73, 76 if active else 42)
                pygame.draw.polygon(
                    marker,
                    colour,
                    [(1, 4), (rect.w - 2, 2), (rect.w - 1, rect.h - 3), (2, rect.h - 1)],
                )
                surface.blit(marker, rect.topleft)
            label_s = self.font_small.render(label, True, COLOUR_TEXT)
            surface.blit(label_s, (rect.x + 4, rect.y + 2))
            self._buttons.append((f"diary_link:{category.value}", rect))
            if hovered:
                self._icon_tips.append((rect, tip))
            tx += width + 3
        body_top = header_y + CAT_TAB_H + 8
        view = pygame.Rect(x, body_top, inner_w, max(1, panel.bottom - body_top))
        scroll = int(self._scroll_value("panel_body", self._measured_body_h, view.h))
        for category, anchor in sorted(
            self._section_anchors.items(), key=lambda item: item[1]
        ):
            if scroll + 12 >= anchor:
                self.detail_category = category
        if self._measured_body_h > view.h and scroll >= self._measured_body_h - view.h - 2:
            self.detail_category = DetailCategory.INVENTORY
        surface.set_clip(view.clip(panel_clip))
        y = view.y - scroll

        def heading(label: str) -> None:
            nonlocal y
            pygame.draw.line(
                surface, (151, 119, 76), (x, y), (view.right - 4, y + 1), 1
            )
            y += 7
            surface.blit(self.font.render(label, True, COLOUR_TEXT), (x, y))
            y += self.font.get_linesize() + 7

        self._section_anchors = {}
        self._section_anchors[DetailCategory.OVERVIEW] = y + scroll - view.y
        if True:
            heading("STATUS")
            state = activity_label or (
                "Exploring" if is_player else villager.state.name.replace("_", " ").title()
            )
            surface.blit(self.font_small.render(state, True, COLOUR_TEXT), (x, y))
            y += self.font_small.get_linesize() + 4
            if not is_player:
                from society import happiness_band_label, is_happiness_break_state

                band = happiness_band_label(float(villager.happiness))
                surface.blit(
                    self.font_small.render(f"Mood: {band}", True, COLOUR_TEXT_DIM),
                    (x, y),
                )
                y += self.font_small.get_linesize() + 2
                if is_happiness_break_state(villager.state):
                    reason = str(getattr(villager, "break_reason", "") or "Morale break")
                    surface.blit(
                        self.font_small.render(
                            f"Break: {reason}", True, COLOUR_TEXT
                        ),
                        (x, y),
                    )
                    y += self.font_small.get_linesize() + 2
                    thought = str(getattr(villager, "break_thought", "") or "").strip()
                    if thought:
                        tip = thought if len(thought) < 42 else thought[:39] + "…"
                        surface.blit(
                            self.font_small.render(f"“{tip}”", True, COLOUR_TEXT_DIM),
                            (x, y),
                        )
                        y += self.font_small.get_linesize() + 2
                events = list(getattr(villager, "happiness_events", None) or [])
                if events:
                    recent = events[-2:]
                    bits = []
                    for ev in recent:
                        if not isinstance(ev, dict):
                            continue
                        label = str(ev.get("label") or "").strip()
                        if label:
                            bits.append(label[:28])
                    if bits:
                        surface.blit(
                            self.font_small.render(
                                "Recent: " + " · ".join(bits),
                                True,
                                COLOUR_TEXT_DIM,
                            ),
                            (x, y),
                        )
                        y += self.font_small.get_linesize() + 2
            y += 6
            for label, kind, value in (
                ("Energy", "energy", villager.energy),
                ("Satiation", "sat", villager.satiation),
                ("Happiness", "happy", villager.happiness),
            ):
                surface.blit(self.font_small.render(label, True, COLOUR_TEXT_DIM), (x, y))
                draw_status_bar(surface, x + 92, y + 5, max(70, inner_w - 104), 10, value, kind=kind)
                y += self.font_small.get_linesize() + 5

            if not is_player:
                y += 6
                heading("HOME & EXPECTATIONS")
                home = housing_icon.replace("_", " ").title() if villager.housed else "No home"
                mark = "✓" if villager.housed else "×"
                blit_icon(surface, housing_icon, x + 12, y + 11, 22)
                surface.blit(self.font_small.render(f"{home}  {mark}", True, COLOUR_TEXT), (x + 28, y))
                y += self.font_small.get_linesize() + 4
                for row in list(requirement_rows or []):
                    label = str(row.get("label") or "Expectation")
                    met = bool(row.get("met"))
                    coins = int(row.get("coins", 0) or 0)
                    suffix = "✓" if met else "×"
                    if not met and coins:
                        suffix += f"  pay {coins} coin{'s' if coins != 1 else ''}"
                    blit_icon(surface, str(row.get("icon") or "meat"), x + 12, y + 11, 20)
                    surface.blit(self.font_small.render(f"{label}  {suffix}", True, COLOUR_TEXT_DIM), (x + 28, y))
                    y += self.font_small.get_linesize() + 3

        self._section_anchors[DetailCategory.WORK] = y + scroll - view.y
        if True:
            heading("WORK")
            if is_player:
                surface.blit(self.font_small.render("Free / player controlled", True, COLOUR_TEXT), (x, y))
                y += self.font_small.get_linesize()
            else:
                label = activity_label or "Free / Unassigned"
                surface.blit(self.font_small.render(label, True, COLOUR_TEXT), (x, y))
                y += self.font_small.get_linesize() + 8
                assign = pygame.Rect(x, y, min(145, inner_w - 80), BTN_H)
                self._draw_button(surface, assign, "Assign workplace")
                self._buttons.append(("assign_workplace", assign))
                seasonal = pygame.Rect(assign.right + 7, y, min(82, view.right - assign.right - 7), BTN_H)
                self._draw_button(surface, seasonal, "Seasonal", active=villager.seasonal_priorities)
                self._buttons.append(("seasonal_toggle", seasonal))
                y += BTN_H + 12
                if villager.seasonal_priorities:
                    villager.ensure_season_workplace_plan(
                        copy_from=villager.ensure_workplace_plan()
                    )
                    hits, grid_h = draw_seasonal_workplace_plan_grid(
                        surface, x, y, villager.season_workplace_plan,
                        icon_for_building=building_icon_for,
                        font=self.font_small, font_small=self.font_tiny,
                        current_season=current_season, mouse_pos=mouse_pos,
                    )
                else:
                    villager.ensure_workplace_plan()
                    hits, grid_h = draw_workplace_plan_row(
                        surface, x, y, list(villager.workplace_plan),
                        icon_for_building=building_icon_for,
                        font=self.font_small, mouse_pos=mouse_pos,
                    )
                self._buttons.extend(hits)
                y += grid_h + 10

        self._section_anchors[DetailCategory.SKILLS] = y + scroll - view.y
        if True:
            heading("SKILLS")
            traits = (
                list(getattr(villager, "virtues", []) or [])
                + list(getattr(villager, "vices", []) or [])
            )
            if traits and not is_player:
                surface.blit(
                    self.font_small.render(" · ".join(traits), True, COLOUR_TEXT),
                    (x, y),
                )
                y += self.font_small.get_linesize() + 8
            if is_player or not villager.skills:
                surface.blit(self.font_small.render("No trained village skills", True, COLOUR_TEXT_DIM), (x, y))
                y += self.font_small.get_linesize()
            else:
                _width, tips = draw_skill_icons(
                    surface, x, y, villager.skills, self.font_small,
                    icon_size=26, col_w=62,
                )
                self._icon_tips.extend(tips)
                y += 48
            y += 8
            heading("EFFECTS")
            walk, work, hunger = effect_totals(
                food_walk=villager.food_walk_mult,
                food_work=villager.food_work_mult,
                food_hunger=villager.food_hunger_mult,
                inventory=villager.inventory,
                calendar_day=calendar_day,
                work_extra_mult=political_work_mult,
                satiation=float(villager.satiation),
                happiness=float(villager.happiness),
            )
            _w, tips = draw_effect_total_columns(
                surface, x, y, walk=walk, work=work, hunger=hunger,
                font=self.font_small, icon_size=26, col_w=82,
            )
            self._icon_tips.extend(tips)
            y += 50

        self._section_anchors[DetailCategory.BUFFS] = y + scroll - view.y
        if True:
            heading("BUFFS")
            mods = collect_status_mods(
                last_meal=list(villager.last_meal), inventory=villager.inventory,
                calendar_day=calendar_day,
                satiation=float(villager.satiation),
                villager=villager,
            )
            if extra_status_mods:
                mods = list(mods) + list(extra_status_mods)
            positive = [mod for mod in mods if mod.is_buff]
            negative = [mod for mod in mods if mod.is_debuff]
            for rows, edge in ((positive, (66, 145, 72)), (negative, (181, 66, 58))):
                if rows:
                    _end, hits, _, tip_hits = draw_mod_row(
                        surface, x, y, rows, mouse_pos=mouse_pos, icon_size=MOD_CELL, gap=MOD_GAP
                    )
                    for rect, _mod in hits:
                        pygame.draw.rect(surface, edge, rect, 2, border_radius=4)
                    self._icon_tips.extend(tip_hits)
                else:
                    surface.blit(self.font_small.render("—", True, COLOUR_TEXT_DIM), (x, y + 8))
                y += MOD_CELL + 8

        self._section_anchors[DetailCategory.INVENTORY] = y + scroll - view.y
        if True:
            heading("INVENTORY")
            tool_h, tool_hits, tool_tip = draw_tool_slot(
                surface, origin=(x, y), equipped_tools=list(villager.inventory.equipped_tools),
                mouse_pos=mouse_pos, fonts=self._fonts(), interactive=True,
            )
            self._tool_hits = tool_hits
            y += tool_h + 7
            clothes_h, clothes_hits, clothes_tip = draw_clothing_slots(
                surface, origin=(x, y), equipped_clothing=dict(villager.inventory.equipped_clothing),
                mouse_pos=mouse_pos, fonts=self._fonts(), interactive=True,
            )
            self._clothing_hits = clothes_hits
            y += clothes_h + 12
            amounts = amounts_from_obj(villager.inventory)
            from food_spoilage import qualities_for_display
            inv_h, _hits, tips, hovered_item, *_ = draw_inv_grid(
                surface, origin=(x, y), width=inner_w, title="Carried",
                subtitle=f"{villager.inventory.cargo_total}/{villager.inventory.effective_capacity}",
                amounts=amounts, allowed=None, side="villager", mouse_pos=mouse_pos,
                fonts=self._fonts(), interactive=False, hover_inv=self._hover_inv,
                qualities=qualities_for_display(villager.inventory),
            )
            self._inv_tip_hits.extend(tips)
            self._tooltip_key = (hovered_item[1] if hovered_item else tool_tip or clothes_tip)
            y += inv_h

        content_h = max(1, y + scroll - view.y + pad)
        self._measured_body_h = content_h
        measured_scroll = self._register_scroll("panel_body", view, content_h, view.h)
        surface.set_clip(old_clip)
        self._draw_scrollbar(surface, view, content_h, int(measured_scroll))
        if mouse_pos is not None:
            for rect, text in self._icon_tips:
                if rect.collidepoint(mouse_pos):
                    self._tooltip_text = text
                    break
        if self._tooltip_text:
            draw_hover_tooltip(surface, mouse_pos=mouse_pos, text=self._tooltip_text, font=self.font_small)
        elif self._tooltip_key:
            draw_item_tooltip(surface, mouse_pos=mouse_pos, key=self._tooltip_key, font=self.font_small)

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
        activity_label: str | None = None,
        extra_status_mods: list | None = None,
        political_work_mult: float = 1.0,
    ) -> None:
        if not self.open or villager is None:
            return
        if villager.id != self.villager_id:
            return
        self._advance_scroll()
        if self.embedded:
            self._draw_diary_page(
                surface,
                villager,
                building_icon_for=building_icon_for,
                housing_icon=housing_icon,
                current_season=current_season,
                calendar_day=calendar_day,
                mouse_pos=mouse_pos,
                requirement_rows=requirement_rows,
                activity_label=activity_label,
                extra_status_mods=extra_status_mods,
                political_work_mult=political_work_mult,
            )
            return

        villager_amounts = amounts_from_obj(villager.inventory)
        player_amounts = (
            amounts_from_obj(player_inventory) if player_inventory is not None else {}
        )
        from food_spoilage import qualities_for_display

        villager_qualities = qualities_for_display(villager.inventory)
        player_qualities = (
            qualities_for_display(player_inventory)
            if player_inventory is not None
            else {}
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
            dual_col_w = (520 - PAD * 2 - INV_PANEL_GAP) // 2
            dual_cols = max(1, min(6, dual_col_w // (GRID_CELL + 4)))
            grid_h = (
                18
                + 16
                + max(
                    grid_height(v_items, cols=dual_cols),
                    grid_height(p_items, cols=dual_cols),
                    GRID_CELL,
                )
                + 22
            )
            self._panel_w = 520
        else:
            grid_h = 18 + 16 + grid_height(v_items) + 8
            self._panel_w = 380

        prio_extra = (
            8 * (SLOT_SIZE + 4)
            if villager.seasonal_priorities
            else (SLOT_SIZE + 8)
        )
        category_panel_h = self._detail_category_panel_height()
        body_h = (
            PAD
            + 18
            + CAT_TAB_H
            + 4
            + category_panel_h
            + 16
            + BAR_H
            + 8
            + ICON_BTN
            + 4  # home
            + SECTION_GAP
            + 18  # Workplace heading
            + ICON_BTN
            + 8  # ration + seasonal toggle
            + prio_extra
            + SECTION_GAP
            + grid_h
            + PAD
        )
        body_h = max(body_h, self._measured_body_h)
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

        all_mods = collect_status_mods(
            last_meal=list(villager.last_meal),
            inventory=villager.inventory,
            calendar_day=calendar_day,
            satiation=float(villager.satiation),
            villager=villager,
        )
        if extra_status_mods:
            all_mods = list(all_mods) + list(extra_status_mods)
        buffs = [m for m in all_mods if m.is_buff]
        debuffs = [m for m in all_mods if m.is_debuff]
        temp_ev = active_temp_event(villager.inventory, calendar_day)
        tip_key: str | None = None

        y = self._draw_detail_category_tabs(surface, x, y, inner_w, mouse_pos)
        panel_top = y
        panel_h = self._detail_category_panel_height()
        content_x = x + 52

        if self.detail_category == DetailCategory.SKILLS:
            skill_w, skill_tips = draw_skill_icons(
                surface, x, panel_top, villager.skills, self.font_tiny, icon_size=14
            )
            self._icon_tips.extend(skill_tips)
            walk_t, work_t, hunger_t = effect_totals(
                food_walk=villager.food_walk_mult,
                food_work=villager.food_work_mult,
                food_hunger=villager.food_hunger_mult,
                inventory=villager.inventory,
                calendar_day=calendar_day,
                work_extra_mult=political_work_mult,
                satiation=float(villager.satiation),
                happiness=float(villager.happiness),
            )
            _, total_tips = draw_effect_total_columns(
                surface,
                x + skill_w + 6,
                panel_top,
                walk=walk_t,
                work=work_t,
                hunger=hunger_t,
                font=self.font_tiny,
            )
            self._icon_tips.extend(total_tips)
        elif self.detail_category == DetailCategory.TOOLS:
            tool_y = panel_top
            tool_h, tool_hits, tool_tip = draw_tool_slot(
                surface,
                origin=(x, tool_y),
                equipped_tools=list(villager.inventory.equipped_tools),
                mouse_pos=mouse_pos,
                fonts=self._fonts(),
                interactive=True,
            )
            self._tool_hits = tool_hits
            clothes_y = tool_y + tool_h + 4
            clothes_h, clothes_hits, clothes_tip = draw_clothing_slots(
                surface,
                origin=(x, clothes_y),
                equipped_clothing=dict(villager.inventory.equipped_clothing),
                mouse_pos=mouse_pos,
                fonts=self._fonts(),
                interactive=True,
            )
            self._clothing_hits = clothes_hits
            hint_y = clothes_y + clothes_h + 2
            surface.blit(
                self.font_small.render(
                    "Click a slot to equip or unequip tools / clothes.",
                    True,
                    COLOUR_TEXT_DIM,
                ),
                (x, hint_y),
            )
            tip_key = tool_tip or clothes_tip
        else:
            meal_y = panel_top
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

            surface.blit(
                self.font_small.render("Buffs:", True, COLOUR_TEXT_DIM),
                (x, buff_y + MOD_CELL // 2 - 6),
            )
            if buffs:
                _, buff_hits, _, tip_hits = draw_mod_row(
                    surface,
                    content_x,
                    buff_y,
                    buffs,
                    mouse_pos=mouse_pos,
                    hover=hover,
                    icon_size=MOD_CELL,
                    gap=MOD_GAP,
                )
                self._icon_tips.extend(tip_hits)
            else:
                surface.blit(
                    self.font_small.render("—", True, COLOUR_TEXT_DIM),
                    (content_x, buff_y + MOD_CELL // 2 - 6),
                )

            surface.blit(
                self.font_small.render("Debuffs:", True, COLOUR_TEXT_DIM),
                (x, debuff_y + MOD_CELL // 2 - 6),
            )
            if debuffs:
                _, debuff_hits, _, tip_hits = draw_mod_row(
                    surface,
                    content_x,
                    debuff_y,
                    debuffs,
                    mouse_pos=mouse_pos,
                    hover=hover,
                    icon_size=MOD_CELL,
                    gap=MOD_GAP,
                )
                self._icon_tips.extend(tip_hits)
            else:
                surface.blit(
                    self.font_small.render("—", True, COLOUR_TEXT_DIM),
                    (content_x, debuff_y + MOD_CELL // 2 - 6),
                )

            surface.blit(
                self.font_small.render("Reqs:", True, COLOUR_TEXT_DIM),
                (x, req_y + 5),
            )
            req_x = content_x
            rows = list(requirement_rows or [])
            if rows:
                for row in rows:
                    ic = str(row.get("icon") or "tent")
                    met = bool(row.get("met"))
                    coins = int(row.get("coins", 0) or 0)
                    rrect = pygame.Rect(req_x, req_y, ICON_BTN, ICON_BTN)
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
                            coin_r = pygame.Rect(rrect.right + 2, req_y + 4, 18, 18)
                            blit_icon(
                                surface, "coins", coin_r.centerx, coin_r.centery, 14
                            )
                            cost = self.font_tiny.render(
                                str(coins), True, (220, 180, 90)
                            )
                            surface.blit(cost, (coin_r.right + 1, req_y + 7))
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
                    (req_x, req_y + 4),
                )

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

        y = panel_top + panel_h

        if activity_label:
            state = activity_label
        elif villager.seeking_food:
            state = "Seeking food"
        else:
            state = villager.state.name.replace("_", " ").title()
        # Wrap long activity lines into the panel width.
        max_w = inner_w
        words = state.split()
        line = ""
        for word in words:
            trial = f"{line} {word}".strip()
            if self.font_small.size(trial)[0] <= max_w or not line:
                line = trial
            else:
                surface.blit(
                    self.font_small.render(line, True, COLOUR_TEXT_DIM), (x, y)
                )
                y += 14
                line = word
        if line:
            surface.blit(self.font_small.render(line, True, COLOUR_TEXT_DIM), (x, y))
            y += 16
        else:
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
        y += ICON_BTN + 4 + SECTION_GAP

        # --- Workplace (P1–P3 building picks; S expands seasons) ---
        surface.blit(self.font.render("Workplace", True, COLOUR_TEXT), (x, y))
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
                "Seasonal workplace on"
                if villager.seasonal_priorities
                else "Seasonal workplace off — year-round P1–P3",
            )
        )
        y += ICON_BTN + 8

        if villager.seasonal_priorities:
            villager.ensure_season_workplace_plan()
            grid_hits, grid_h = draw_seasonal_workplace_plan_grid(
                surface,
                x,
                y,
                villager.season_workplace_plan,
                icon_for_building=building_icon_for,
                font=self.font_small,
                font_small=self.font_tiny,
                current_season=current_season,
                mouse_pos=mouse_pos,
            )
            for action, rect in grid_hits:
                self._buttons.append((action, rect))
                parts = action.split(":")
                tip = "Workplace slot (click to assign)"
                if len(parts) >= 3:
                    try:
                        slot_i = int(parts[1])
                        season_name = parts[2]
                        row = list(
                            villager.season_workplace_plan.get(
                                season_name, []
                            )
                        )
                        slot = row[slot_i] if 0 <= slot_i < len(row) else None
                        if slot is not None:
                            tip = plan_slot_tip(
                                slot,
                                icon_for_building=building_icon_for,
                                season_name=season_name,
                                slot_index=slot_i,
                            )
                    except ValueError:
                        pass
                self._icon_tips.append((rect, tip))
            y += max(grid_h, SLOT_SIZE) + 8
        else:
            villager.ensure_workplace_plan()
            row_hits, _ = draw_workplace_plan_row(
                surface,
                x,
                y,
                list(villager.workplace_plan),
                icon_for_building=building_icon_for,
                font=self.font_small,
                mouse_pos=mouse_pos,
            )
            for action, rect in row_hits:
                self._buttons.append((action, rect))
                tip = "Workplace slot (click to assign)"
                try:
                    slot_i = int(action.rsplit(":", 1)[-1])
                    plan = list(villager.workplace_plan)
                    if 0 <= slot_i < len(plan):
                        tip = plan_slot_tip(
                            plan[slot_i],
                            icon_for_building=building_icon_for,
                            slot_index=slot_i,
                        )
                except ValueError:
                    pass
                self._icon_tips.append((rect, tip))
            y += SLOT_SIZE + 8

        y += SECTION_GAP

        if dual:
            col_w = (inner_w - INV_PANEL_GAP) // 2
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
                qualities=villager_qualities,
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
                qualities=player_qualities,
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
                qualities=villager_qualities,
            )
            self._inv_tip_hits.extend(tips)
            if hov:
                tip_key = hov[1]
            y += h

        content_top = panel.y + TITLE_BAR_H
        measured_body_h = max(1, int(y + panel_scroll - content_top + PAD))
        self._measured_body_h = measured_body_h
        measured_scroll = self._scroll_value("panel_body", measured_body_h, client_h)
        self._scroll_areas["panel_body"] = (client_rect, measured_body_h, client_h)
        surface.set_clip(old_clip)
        self._draw_scrollbar(surface, client_rect, measured_body_h, measured_scroll)

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

        if not self.embedded:
            pygame.draw.rect(surface, COLOUR_SELECTED_ENTITY, panel, 1, border_radius=6)
