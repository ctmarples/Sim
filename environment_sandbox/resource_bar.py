"""Resource bar under the toolbar: category totals with hover detail popups."""

from __future__ import annotations

from enum import Enum, auto

import pygame

from entities import Building, HomeStorage, Player, Villager
from indicators import OVERLAY_LABELS, OverlayMode
from resources import (
    GROUP_LABELS,
    GROUP_ORDER,
    amounts_from_obj,
    group_totals,
    merge_amounts,
    resources_by_group,
)
from settings import (
    COLOUR_MENU_BG,
    COLOUR_TEXT,
    COLOUR_TOOLBAR_BG,
    COLOUR_TOOLBAR_BORDER,
    COLOUR_TOOLBAR_BTN,
    COLOUR_TOOLBAR_BTN_ACTIVE,
    COLOUR_TOOLBAR_BTN_HOVER,
    MAP_OFFSET_Y,
    RESOURCE_BAR_HEIGHT,
    TOOLBAR_HEIGHT,
    WINDOW_WIDTH,
)


class ResourceView(Enum):
    PLAYER = auto()
    STOREHOUSE = auto()
    TOTAL = auto()  # storehouse + local building storage


VIEW_LABELS = {
    ResourceView.PLAYER: "Player",
    ResourceView.STOREHOUSE: "Storehouse",
    ResourceView.TOTAL: "Total",
}


class ResourceBar:
    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 13)
        self.font_small = pygame.font.SysFont("menlo", 12)
        self._chip_rects: dict[str, pygame.Rect] = {}
        self._hover_group: str | None = None
        self._popup_rect = pygame.Rect(0, 0, 0, 0)
        self._popup_group: str | None = None
        self._popup_grace_until = 0
        self._popup_entered = False
        self.view_mode = ResourceView.TOTAL
        self._toggle_rect = pygame.Rect(0, 0, 0, 0)
        self.layers_open = False
        self._layers_rect = pygame.Rect(0, 0, 0, 0)
        self._layer_rects: dict[OverlayMode, pygame.Rect] = {}

    @staticmethod
    def layer_modes() -> tuple[OverlayMode, ...]:
        """Layers shown in the single-select top-panel menu."""
        return tuple(mode for mode in OverlayMode if mode != OverlayMode.NONE)

    def cycle_view(self) -> ResourceView:
        order = [ResourceView.PLAYER, ResourceView.STOREHOUSE, ResourceView.TOTAL]
        idx = order.index(self.view_mode)
        self.view_mode = order[(idx + 1) % len(order)]
        return self.view_mode

    def collect_amounts(
        self,
        home: HomeStorage,
        player: Player,
        buildings: dict[int, Building],
        villagers: list[Villager],
    ) -> dict[str, int]:
        if self.view_mode == ResourceView.PLAYER:
            return amounts_from_obj(player.inventory)
        if self.view_mode == ResourceView.STOREHOUSE:
            return amounts_from_obj(home)
        # Total = storehouse + building storage (not player/villager carry)
        parts = [amounts_from_obj(home)]
        parts.extend(amounts_from_obj(b) for b in buildings.values())
        return merge_amounts(*parts)

    def update_hover(self, mouse_pos: tuple[int, int]) -> None:
        self._hover_group = None
        now = pygame.time.get_ticks()
        for group, rect in self._chip_rects.items():
            if rect.collidepoint(mouse_pos):
                self._hover_group = group
                self._popup_group = group
                self._popup_grace_until = now + 1000
                self._popup_entered = False
                return
        if (
            self._popup_group is not None
            and self._popup_rect.collidepoint(mouse_pos)
        ):
            self._hover_group = self._popup_group
            self._popup_entered = True
            return
        # Leave enough time to cross the small gap between the top-bar chip and
        # its expanded grid. Once the grid has been entered, leaving it closes
        # normally without this delay.
        if (
            self._popup_group is not None
            and not self._popup_entered
            and now <= self._popup_grace_until
        ):
            self._hover_group = self._popup_group

    def contains(self, pos: tuple[int, int]) -> bool:
        _, my = pos
        if TOOLBAR_HEIGHT <= my < MAP_OFFSET_Y:
            return True
        return self.layers_open and any(
            rect.collidepoint(pos) for rect in self._layer_rects.values()
        )

    def handle_click(
        self, pos: tuple[int, int], overlay_mode: OverlayMode
    ) -> tuple[bool, OverlayMode | None]:
        """Handle resource/layer controls; return ``(handled, new_layer)``."""
        if self._toggle_rect.collidepoint(pos):
            self.cycle_view()
            self.layers_open = False
            return True, None
        if self._layers_rect.collidepoint(pos):
            self.layers_open = not self.layers_open
            return True, None
        if self.layers_open:
            for mode, rect in self._layer_rects.items():
                if rect.collidepoint(pos):
                    self.layers_open = False
                    return True, OverlayMode.NONE if mode == overlay_mode else mode
        return False, None

    def draw(
        self,
        surface: pygame.Surface,
        home: HomeStorage,
        player: Player,
        buildings: dict[int, Building],
        villagers: list[Villager],
        mouse_pos: tuple[int, int],
        *,
        housed: int | None = None,
        needing: int | None = None,
        regional_wealth: int = 0,
        overlay_mode: OverlayMode = OverlayMode.NONE,
    ) -> None:
        bar = pygame.Rect(0, TOOLBAR_HEIGHT, WINDOW_WIDTH, RESOURCE_BAR_HEIGHT)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BG, bar)
        pygame.draw.line(
            surface,
            COLOUR_TOOLBAR_BORDER,
            (0, MAP_OFFSET_Y - 1),
            (WINDOW_WIDTH, MAP_OFFSET_Y - 1),
            1,
        )

        amounts = self.collect_amounts(home, player, buildings, villagers)
        # Coins are regional wealth — never cargo in storehouse / buildings.
        amounts["coins"] = int(regional_wealth)
        totals = group_totals(amounts)
        self._chip_rects = {}

        y = TOOLBAR_HEIGHT + 6
        h = RESOURCE_BAR_HEIGHT - 12

        # View-mode toggle
        view_label = VIEW_LABELS[self.view_mode]
        toggle_text = f"View: {view_label}"
        tw = self.font.size(toggle_text)[0]
        self._toggle_rect = pygame.Rect(12, y, tw + 20, h)
        hovered_toggle = self._toggle_rect.collidepoint(mouse_pos)
        colour = COLOUR_TOOLBAR_BTN_ACTIVE if hovered_toggle else COLOUR_TOOLBAR_BTN
        pygame.draw.rect(surface, colour, self._toggle_rect, border_radius=4)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, self._toggle_rect, 1, border_radius=4)
        rendered = self.font.render(toggle_text, True, COLOUR_TEXT)
        surface.blit(
            rendered,
            (
                self._toggle_rect.x + (self._toggle_rect.w - rendered.get_width()) // 2,
                self._toggle_rect.y + (self._toggle_rect.h - rendered.get_height()) // 2,
            ),
        )

        x = self._toggle_rect.right + 14

        # Regional wealth (always visible).
        coins = int(regional_wealth)
        try:
            from icons import ICON_COINS, blit_icon

            icon_size = max(14, h - 10)
            num = self.font.render(str(coins), True, COLOUR_TEXT)
            crect = pygame.Rect(x, y, 12 + icon_size // 2 + 8 + num.get_width() + 10, h)
            self._chip_rects["coins"] = crect
            hovered_coins = crect.collidepoint(mouse_pos)
            colour = COLOUR_TOOLBAR_BTN_HOVER if hovered_coins else COLOUR_TOOLBAR_BTN
            pygame.draw.rect(surface, colour, crect, border_radius=4)
            pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, crect, 1, border_radius=4)
            blit_icon(
                surface,
                ICON_COINS,
                crect.x + 6 + icon_size // 2,
                crect.centery,
                icon_size,
            )
            surface.blit(
                num,
                (
                    crect.x + 6 + icon_size + 4,
                    crect.y + (crect.h - num.get_height()) // 2,
                ),
            )
        except (FileNotFoundError, OSError, ValueError, TypeError):
            coin_text = f"Wealth  {coins}"
            cw = self.font.size(coin_text)[0] + 24
            crect = pygame.Rect(x, y, cw, h)
            self._chip_rects["coins"] = crect
            hovered_coins = crect.collidepoint(mouse_pos)
            colour = COLOUR_TOOLBAR_BTN_HOVER if hovered_coins else COLOUR_TOOLBAR_BTN
            pygame.draw.rect(surface, colour, crect, border_radius=4)
            pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, crect, 1, border_radius=4)
            ct = self.font.render(coin_text, True, COLOUR_TEXT)
            surface.blit(
                ct,
                (
                    crect.x + (crect.w - ct.get_width()) // 2,
                    crect.y + (crect.h - ct.get_height()) // 2,
                ),
            )
        x = crect.right + 10

        # Housing: housed villagers / total villagers (need beds).
        if housed is not None and needing is not None:
            house_text = f"Housing  {housed}/{needing}"
            hw = self.font.size(house_text)[0] + 24
            hrect = pygame.Rect(x, y, hw, h)
            self._chip_rects["housing"] = hrect
            hovered = hrect.collidepoint(mouse_pos)
            colour = COLOUR_TOOLBAR_BTN_HOVER if hovered else COLOUR_TOOLBAR_BTN
            pygame.draw.rect(surface, colour, hrect, border_radius=4)
            pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, hrect, 1, border_radius=4)
            ht = self.font.render(house_text, True, COLOUR_TEXT)
            surface.blit(
                ht,
                (
                    hrect.x + (hrect.w - ht.get_width()) // 2,
                    hrect.y + (hrect.h - ht.get_height()) // 2,
                ),
            )
            x = hrect.right + 10

        for group in GROUP_ORDER:
            label = GROUP_LABELS.get(group, group)
            total = totals.get(group, 0)
            text = f"{label}  {total}"
            tw = self.font.size(text)[0]
            w = tw + 24
            rect = pygame.Rect(x, y, w, h)
            self._chip_rects[group] = rect
            hovered = rect.collidepoint(mouse_pos)
            colour = COLOUR_TOOLBAR_BTN_HOVER if hovered else COLOUR_TOOLBAR_BTN
            pygame.draw.rect(surface, colour, rect, border_radius=4)
            pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, rect, 1, border_radius=4)
            rendered = self.font.render(text, True, COLOUR_TEXT)
            surface.blit(
                rendered,
                (
                    rect.x + (rect.w - rendered.get_width()) // 2,
                    rect.y + (rect.h - rendered.get_height()) // 2,
                ),
            )
            x += w + 10

        self.update_hover(mouse_pos)
        if self._hover_group is not None:
            self._draw_popup(surface, amounts, self._hover_group, mouse_pos)
        else:
            self._popup_rect = pygame.Rect(0, 0, 0, 0)
            self._popup_group = None
            self._popup_grace_until = 0
            self._popup_entered = False
        self._draw_layers(surface, mouse_pos, overlay_mode)

    def _draw_layers(
        self,
        surface: pygame.Surface,
        mouse_pos: tuple[int, int],
        overlay_mode: OverlayMode,
    ) -> None:
        """Draw the single-select environmental layer control and its menu."""
        y = TOOLBAR_HEIGHT + 6
        h = RESOURCE_BAR_HEIGHT - 12
        active = OVERLAY_LABELS.get(overlay_mode, "None")
        label = "Layers" if overlay_mode == OverlayMode.NONE else f"Layer: {active}"
        width = max(82, self.font.size(label)[0] + 20)
        self._layers_rect = pygame.Rect(WINDOW_WIDTH - width - 12, y, width, h)
        hovered = self._layers_rect.collidepoint(mouse_pos)
        colour = (
            COLOUR_TOOLBAR_BTN_ACTIVE
            if self.layers_open or overlay_mode != OverlayMode.NONE
            else COLOUR_TOOLBAR_BTN_HOVER if hovered else COLOUR_TOOLBAR_BTN
        )
        pygame.draw.rect(surface, colour, self._layers_rect, border_radius=4)
        pygame.draw.rect(
            surface, COLOUR_TOOLBAR_BORDER, self._layers_rect, 1, border_radius=4
        )
        text = self.font.render(label, True, COLOUR_TEXT)
        surface.blit(text, (self._layers_rect.centerx - text.get_width() // 2,
                            self._layers_rect.centery - text.get_height() // 2))

        self._layer_rects = {}
        if not self.layers_open:
            return
        modes = self.layer_modes()
        menu_width = max(
            178, max(self.font.size(OVERLAY_LABELS[mode])[0] for mode in modes) + 34
        )
        item_h = 24
        menu_x = self._layers_rect.right - menu_width
        menu_y = MAP_OFFSET_Y + 2
        menu = pygame.Rect(menu_x, menu_y, menu_width, item_h * len(modes) + 8)
        pygame.draw.rect(surface, COLOUR_MENU_BG, menu, border_radius=4)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, menu, 1, border_radius=4)
        for index, mode in enumerate(modes):
            rect = pygame.Rect(menu_x + 4, menu_y + 4 + index * item_h,
                               menu_width - 8, item_h)
            self._layer_rects[mode] = rect
            is_active = mode == overlay_mode
            if rect.collidepoint(mouse_pos) or is_active:
                pygame.draw.rect(
                    surface,
                    COLOUR_TOOLBAR_BTN_ACTIVE if is_active else COLOUR_TOOLBAR_BTN_HOVER,
                    rect,
                    border_radius=3,
                )
            marker = "• " if is_active else "  "
            item = self.font.render(marker + OVERLAY_LABELS[mode], True, COLOUR_TEXT)
            surface.blit(item, (rect.x + 7, rect.centery - item.get_height() // 2))

    def _draw_popup(
        self,
        surface: pygame.Surface,
        amounts: dict[str, int],
        group: str,
        mouse_pos: tuple[int, int],
    ) -> None:
        chip = self._chip_rects.get(group)
        if chip is None:
            return
        if group == "coins":
            lines = [f"Regional wealth: {int(amounts.get('coins', 0))}"]
        elif group == "housing":
            return
        else:
            defs = dict(resources_by_group()).get(group, [])
            lines = []
        self._popup_group = group
        if not lines:
            if group in ("coins", "housing") or not defs:
                return

            from inventory_ui import draw_item_tooltip, draw_resource_cell

            cell_size = 42
            gap = 4
            cols = min(8, max(1, len(defs)))
            rows = (len(defs) + cols - 1) // cols
            padding = 8
            width = padding * 2 + cols * cell_size + (cols - 1) * gap
            height = padding * 2 + rows * cell_size + (rows - 1) * gap
            popup = pygame.Rect(chip.x, MAP_OFFSET_Y + 4, width, height)
            if popup.right > WINDOW_WIDTH - 8:
                popup.x = WINDOW_WIDTH - width - 8
            self._popup_rect = popup

            pygame.draw.rect(surface, COLOUR_MENU_BG, popup, border_radius=4)
            pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, popup, 1, border_radius=4)
            hovered_key: str | None = None
            for index, res in enumerate(defs):
                col = index % cols
                row = index // cols
                cell = pygame.Rect(
                    popup.x + padding + col * (cell_size + gap),
                    popup.y + padding + row * (cell_size + gap),
                    cell_size,
                    cell_size,
                )
                hovered = cell.collidepoint(mouse_pos)
                draw_resource_cell(
                    surface,
                    cell=cell,
                    key=res.key,
                    count=int(amounts.get(res.key, 0)),
                    fonts=(self.font, self.font_small, self.font_small),
                    hovered=hovered,
                    dimmed=int(amounts.get(res.key, 0)) <= 0,
                )
                if hovered:
                    hovered_key = res.key
            if hovered_key is not None:
                draw_item_tooltip(
                    surface,
                    mouse_pos=mouse_pos,
                    key=hovered_key,
                    font=self.font_small,
                )
            return

        padding = 8
        line_h = self.font_small.get_height() + 4
        width = max(self.font_small.size(line)[0] for line in lines) + padding * 2
        height = padding * 2 + line_h * len(lines)
        popup = pygame.Rect(chip.x, MAP_OFFSET_Y + 4, width, height)
        if popup.right > WINDOW_WIDTH - 8:
            popup.x = WINDOW_WIDTH - width - 8
        self._popup_rect = popup

        pygame.draw.rect(surface, COLOUR_MENU_BG, popup, border_radius=4)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, popup, 1, border_radius=4)
        ty = popup.y + padding
        for line in lines:
            surface.blit(self.font_small.render(line, True, COLOUR_TEXT), (popup.x + padding, ty))
            ty += line_h
