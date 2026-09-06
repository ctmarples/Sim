"""Floating player inventory: cargo grid + tool slots with drag-drop equip."""

from __future__ import annotations

import pygame

from entities import CLOTHING_ITEM_SLOT, CLOTHING_SLOTS, TOOL_KEYS, TOOL_SLOT_MAX, Player
from inventory_ui import (
    GRID_CELL,
    GRID_GAP,
    draw_clothing_slots,
    draw_inv_grid,
    draw_item_tooltip,
    draw_resource_cell,
    present_keys,
)
from resources import amounts_from_obj, resource_label
from settings import (
    COLOUR_MENU_BG,
    COLOUR_SELECTED_ENTITY,
    COLOUR_TEXT,
    COLOUR_TEXT_DIM,
    COLOUR_TOOLBAR_BORDER,
    COLOUR_TOOLBAR_BTN,
    COLOUR_TOOLBAR_BTN_HOVER,
    MAP_OFFSET_Y,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    map_view_width,
)

TITLE_BAR_H = 28
PAD = 12
BTN_H = 24


class PlayerInventoryDialog:
    """Movable inventory window opened with I."""

    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 14)
        self.font_small = pygame.font.SysFont("menlo", 12)
        self.font_tiny = pygame.font.SysFont("menlo", 11, bold=True)
        self.font_title = pygame.font.SysFont("menlo", 15, bold=True)
        self._open = False
        self._panel_x = 80
        self._panel_y = MAP_OFFSET_Y + 40
        self._panel_w = 280
        self._panel_h = 320
        self._moving = False
        self._move_offset = (0, 0)
        self._close_rect = pygame.Rect(0, 0, 0, 0)
        self._title_rect = pygame.Rect(0, 0, 0, 0)
        self._pending_action: str | None = None
        self.selected_key: str | None = None
        self._inv_hits: list[tuple[pygame.Rect, str, str]] = []
        self._tool_hits: list[tuple[pygame.Rect, str]] = []
        self._tool_slot_rects: list[pygame.Rect] = []
        self._clothing_hits: list[tuple[pygame.Rect, str]] = []
        self._clothing_slot_rects: dict[str, pygame.Rect] = {}
        self._cargo_rect = pygame.Rect(0, 0, 0, 0)
        self._drag_key: str | None = None
        self._drag_from: str | None = None  # "cargo" | "tool" | "clothing"
        self._drag_active = False
        self._tooltip_key: str | None = None
        self._auto_eat_rect = pygame.Rect(0, 0, 0, 0)

    @property
    def open(self) -> bool:
        return self._open

    def open_window(self) -> None:
        self._open = True
        self._moving = False
        self._pending_action = None
        self._clear_drag()
        map_w = map_view_width()
        self._panel_w = 280
        self._panel_h = 340
        self._panel_x = max(8, (map_w - self._panel_w) // 2 - 40)
        self._panel_y = MAP_OFFSET_Y + 48
        self._clamp_panel()

    def close(self) -> None:
        self._open = False
        self._moving = False
        self._pending_action = None
        self._clear_drag()

    def toggle(self) -> None:
        if self.open:
            self.close()
        else:
            self.open_window()

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

    def _clear_drag(self) -> None:
        self._drag_key = None
        self._drag_from = None
        self._drag_active = False

    def handle_keydown(self, event: pygame.event.Event) -> bool:
        if not self.open:
            return False
        if event.key == pygame.K_ESCAPE:
            self.close()
            return True
        if event.key == pygame.K_i:
            self.close()
            return True
        return False

    def handle_mousedown(self, pos: tuple[int, int], *, button: int = 1) -> bool:
        if not self.open or not self.contains(pos):
            return False
        if button == 3:
            for rect, _side, key in self._inv_hits:
                if rect.collidepoint(pos):
                    self.selected_key = key
                    if key == "book":
                        self._pending_action = f"use:{key}"
                    elif key in CLOTHING_ITEM_SLOT:
                        self._pending_action = f"equip_clothing:{key}"
                    elif key in TOOL_KEYS:
                        self._pending_action = f"equip:{key}"
                    else:
                        self._pending_action = f"eat:{key}"
                    return True
            return True
        if button != 1:
            return True
        if self._close_rect.collidepoint(pos):
            self.close()
            return True
        if self._auto_eat_rect.collidepoint(pos):
            self._pending_action = "toggle_auto_eat"
            return True
        if self._title_rect.collidepoint(pos):
            self._moving = True
            self._move_offset = (pos[0] - self._panel_x, pos[1] - self._panel_y)
            return True
        for rect, action in self._tool_hits:
            if rect.collidepoint(pos):
                if action.startswith("tool_unequip:"):
                    key = action.split(":", 1)[1]
                    self._drag_key = key
                    self._drag_from = "tool"
                    self._drag_active = True
                elif action == "tool_equip":
                    self._pending_action = "tool_equip"
                return True
        for rect, action in self._clothing_hits:
            if rect.collidepoint(pos):
                if action.startswith("clothing_unequip:"):
                    slot = action.split(":", 1)[1]
                    # Drag worn clothing out (item key resolved in draw via worn map).
                    worn_key = None
                    for s, r in self._clothing_slot_rects.items():
                        if r == rect:
                            # Find key from last drawn hits action pairing
                            worn_key = slot  # temporary; draw stores slot→key
                            break
                    # Store slot for drag; mouseup unequips to cargo.
                    self._drag_key = slot
                    self._drag_from = "clothing"
                    self._drag_active = True
                elif action.startswith("clothing_equip:"):
                    self._pending_action = action
                return True
        for rect, side, key in self._inv_hits:
            if rect.collidepoint(pos):
                if key in TOOL_KEYS:
                    self._drag_key = key
                    self._drag_from = "cargo"
                    self._drag_active = True
                elif key in CLOTHING_ITEM_SLOT:
                    self._drag_key = key
                    self._drag_from = "cargo"
                    self._drag_active = True
                else:
                    self.selected_key = key
                    self._pending_action = f"select:{key}"
                return True
        return True

    def highlighted_key(self) -> str | None:
        """Hovered cargo item, else the last left-clicked selection."""
        if self.open and self._tooltip_key:
            return self._tooltip_key
        return self.selected_key

    def handle_mouseup(self, pos: tuple[int, int]) -> bool:
        if not self.open:
            return False
        if self._moving:
            self._moving = False
            self._clamp_panel()
            return True
        if self._drag_active and self._drag_key:
            key = self._drag_key
            origin = self._drag_from
            self._clear_drag()
            # Drop onto a tool slot → equip from cargo.
            for i, slot in enumerate(self._tool_slot_rects):
                if slot.collidepoint(pos):
                    if origin == "cargo" and key in TOOL_KEYS:
                        self._pending_action = f"equip:{key}"
                    elif origin == "tool":
                        pass
                    return True
            # Drop onto a clothing slot matching the item's type.
            for slot_name, slot_rect in self._clothing_slot_rects.items():
                if slot_rect.collidepoint(pos):
                    if origin == "cargo" and CLOTHING_ITEM_SLOT.get(key) == slot_name:
                        self._pending_action = f"equip_clothing:{key}"
                    elif origin == "clothing":
                        pass
                    return True
            # Drop onto cargo area → unequip tool / clothing.
            if origin == "tool" and self._cargo_rect.collidepoint(pos):
                self._pending_action = f"unequip:{key}"
                return True
            if origin == "clothing" and self._cargo_rect.collidepoint(pos):
                # drag_key is the clothing slot name when dragging from a slot.
                self._pending_action = f"clothing_unequip:{key}"
                return True
            # Drop outside: click-equip if cargo item released on itself.
            if origin == "cargo":
                for rect, _side, hit_key in self._inv_hits:
                    if hit_key == key and rect.collidepoint(pos):
                        if key in TOOL_KEYS:
                            self._pending_action = f"equip:{key}"
                        elif key in CLOTHING_ITEM_SLOT:
                            self._pending_action = f"equip_clothing:{key}"
                        return True
            return True
        return self.contains(pos)

    def handle_mousemotion(self, pos: tuple[int, int]) -> bool:
        if not self.open:
            return False
        if self._moving:
            self._panel_x = pos[0] - self._move_offset[0]
            self._panel_y = pos[1] - self._move_offset[1]
            self._clamp_panel()
            return True
        self._tooltip_key = None
        if self.contains(pos) and not self._drag_active:
            for rect, _side, key in self._inv_hits:
                if rect.collidepoint(pos):
                    self._tooltip_key = key
                    break
            if self._tooltip_key is None:
                for rect, action in self._tool_hits:
                    if rect.collidepoint(pos) and action.startswith("tool_unequip:"):
                        self._tooltip_key = action.split(":", 1)[1]
                        break
        return self.contains(pos) or self._drag_active

    def draw(
        self,
        surface: pygame.Surface,
        player: Player,
        *,
        mouse_pos: tuple[int, int] | None = None,
    ) -> None:
        if not self.open:
            return
        fonts = (self.font, self.font_small, self.font_tiny)
        inv = player.inventory
        amounts = amounts_from_obj(inv)
        from food_spoilage import qualities_for_display

        qualities = qualities_for_display(inv)
        keys = present_keys(amounts)
        # Estimate height from cargo rows + tools.
        from inventory_ui import grid_height

        body_h = max(GRID_CELL, grid_height(max(1, len(keys))))
        clothes_h = 18 + GRID_CELL + 12 + 8
        self._panel_h = (
            TITLE_BAR_H
            + PAD
            + 18
            + GRID_CELL
            + 10
            + clothes_h
            + 18
            + body_h
            + PAD
            + BTN_H
            + 10
            + 8
        )
        self._panel_w = max(280, 5 * (GRID_CELL + GRID_GAP) + PAD * 2)
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
            self.font_title.render("Inventory", True, COLOUR_TEXT),
            (panel.x + 10, panel.y + 6),
        )
        hint = self.font_tiny.render("F / RMB eat · drag tools", True, COLOUR_TEXT_DIM)
        surface.blit(hint, (panel.x + 100, panel.y + 8))
        self._close_rect = pygame.Rect(panel.right - 28, panel.y + 4, 22, 20)
        close_hov = mouse_pos is not None and self._close_rect.collidepoint(mouse_pos)
        colour = COLOUR_TOOLBAR_BTN_HOVER if close_hov else COLOUR_TOOLBAR_BTN
        pygame.draw.rect(surface, colour, self._close_rect, border_radius=4)
        pygame.draw.rect(
            surface, COLOUR_TOOLBAR_BORDER, self._close_rect, 1, border_radius=4
        )
        x_txt = self.font_small.render("×", True, COLOUR_TEXT)
        surface.blit(
            x_txt,
            (
                self._close_rect.x + (self._close_rect.w - x_txt.get_width()) // 2,
                self._close_rect.y + (self._close_rect.h - x_txt.get_height()) // 2,
            ),
        )

        x = panel.x + PAD
        y = panel.y + TITLE_BAR_H + PAD
        inner_w = panel.w - PAD * 2

        # Tool slots
        surface.blit(self.font.render("Tools", True, COLOUR_TEXT), (x, y))
        y += 18
        tools = list(inv.equipped_tools)
        self._tool_hits = []
        self._tool_slot_rects = []
        for i in range(TOOL_SLOT_MAX):
            cell = pygame.Rect(x + i * (GRID_CELL + GRID_GAP), y, GRID_CELL, GRID_CELL)
            self._tool_slot_rects.append(cell)
            key = tools[i] if i < len(tools) else None
            hovered = mouse_pos is not None and cell.collidepoint(mouse_pos)
            if key and not (self._drag_active and self._drag_from == "tool" and self._drag_key == key):
                draw_resource_cell(
                    surface,
                    cell=cell,
                    key=key,
                    fonts=fonts,
                    hovered=hovered,
                    active=True,
                )
                self._tool_hits.append((cell, f"tool_unequip:{key}"))
            else:
                bg = (55, 62, 50) if hovered else (36, 38, 44)
                border = COLOUR_SELECTED_ENTITY if hovered else COLOUR_TOOLBAR_BORDER
                pygame.draw.rect(surface, bg, cell, border_radius=4)
                pygame.draw.rect(surface, border, cell, 1, border_radius=4)
                dash = self.font_small.render("—", True, COLOUR_TEXT_DIM)
                surface.blit(
                    dash,
                    (
                        cell.centerx - dash.get_width() // 2,
                        cell.centery - dash.get_height() // 2,
                    ),
                )
                if len(tools) < TOOL_SLOT_MAX and i == len(tools):
                    self._tool_hits.append((cell, "tool_equip"))
        y += GRID_CELL + 10

        # Clothing slots
        clothes_h, clothes_hits, _ctip = draw_clothing_slots(
            surface,
            origin=(x, y),
            equipped_clothing=dict(inv.equipped_clothing),
            mouse_pos=mouse_pos if not self._drag_active else None,
            fonts=fonts,
            interactive=True,
        )
        self._clothing_hits = clothes_hits
        self._clothing_slot_rects = {}
        # Rebuild slot rects from hits for drag targeting.
        for rect, action in clothes_hits:
            if ":" in action:
                slot = action.split(":", 1)[1]
                self._clothing_slot_rects[slot] = rect
        y += clothes_h + 4

        # Cargo grid
        self._inv_hits = []
        h, hits, _tips, _hov, _ch, _vh = draw_inv_grid(
            surface,
            origin=(x, y),
            width=inner_w,
            title="Cargo",
            subtitle=(
                f"{inv.cargo_total}/{inv.effective_capacity}"
                f"  seeds {inv.seed_total}/{inv.seed_capacity}"
            ),
            amounts=amounts,
            allowed=None,
            side="player",
            mouse_pos=mouse_pos if not self._drag_active else None,
            fonts=fonts,
            interactive=True,
            selected_key=self.selected_key,
            qualities=qualities,
        )
        self._inv_hits = hits
        self._cargo_rect = pygame.Rect(x, y, inner_w, h)
        y += h + 8

        # Auto-eat toggle
        auto_on = bool(getattr(player, "auto_eat", False))
        label = f"Auto-eat: {'On' if auto_on else 'Off'}"
        btn_w = max(110, 16 + self.font_small.size(label)[0])
        self._auto_eat_rect = pygame.Rect(x, y, btn_w, 24)
        auto_hov = (
            mouse_pos is not None and self._auto_eat_rect.collidepoint(mouse_pos)
        )
        if auto_on:
            bg = COLOUR_TOOLBAR_BTN_HOVER if auto_hov else (55, 85, 55)
        else:
            bg = COLOUR_TOOLBAR_BTN_HOVER if auto_hov else COLOUR_TOOLBAR_BTN
        pygame.draw.rect(surface, bg, self._auto_eat_rect, border_radius=4)
        pygame.draw.rect(
            surface, COLOUR_TOOLBAR_BORDER, self._auto_eat_rect, 1, border_radius=4
        )
        txt = self.font_small.render(label, True, COLOUR_TEXT)
        surface.blit(
            txt,
            (
                self._auto_eat_rect.centerx - txt.get_width() // 2,
                self._auto_eat_rect.centery - txt.get_height() // 2,
            ),
        )

        # Drag ghost
        if self._drag_active and self._drag_key and mouse_pos is not None:
            ghost = pygame.Rect(
                mouse_pos[0] - GRID_CELL // 2,
                mouse_pos[1] - GRID_CELL // 2,
                GRID_CELL,
                GRID_CELL,
            )
            draw_resource_cell(
                surface,
                cell=ghost,
                key=self._drag_key,
                fonts=fonts,
                hovered=True,
                active=True,
            )

        if self._tooltip_key and mouse_pos is not None and not self._drag_active:
            draw_item_tooltip(
                surface,
                mouse_pos=mouse_pos,
                key=self._tooltip_key,
                font=self.font_small,
            )
