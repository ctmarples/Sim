"""Resource bar under the toolbar: category totals with hover detail popups."""

from __future__ import annotations

from enum import Enum, auto

import pygame

from entities import Building, HomeStorage, Player, Villager
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
        self.view_mode = ResourceView.TOTAL
        self._toggle_rect = pygame.Rect(0, 0, 0, 0)

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
        for group, rect in self._chip_rects.items():
            if rect.collidepoint(mouse_pos):
                self._hover_group = group
                return

    def contains(self, pos: tuple[int, int]) -> bool:
        _, my = pos
        return TOOLBAR_HEIGHT <= my < MAP_OFFSET_Y

    def handle_click(self, pos: tuple[int, int]) -> bool:
        if self._toggle_rect.collidepoint(pos):
            self.cycle_view()
            return True
        return False

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
            self._draw_popup(surface, amounts, self._hover_group)

    def _draw_popup(
        self, surface: pygame.Surface, amounts: dict[str, int], group: str
    ) -> None:
        chip = self._chip_rects.get(group)
        if chip is None:
            return
        defs = dict(resources_by_group()).get(group, [])
        lines = [f"{res.label}: {amounts.get(res.key, 0)}" for res in defs]
        if not lines:
            return

        padding = 8
        line_h = self.font_small.get_height() + 4
        width = max(self.font_small.size(line)[0] for line in lines) + padding * 2
        height = padding * 2 + line_h * len(lines)
        popup = pygame.Rect(chip.x, MAP_OFFSET_Y + 4, width, height)
        if popup.right > WINDOW_WIDTH - 8:
            popup.x = WINDOW_WIDTH - width - 8

        pygame.draw.rect(surface, COLOUR_MENU_BG, popup, border_radius=4)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, popup, 1, border_radius=4)
        ty = popup.y + padding
        for line in lines:
            surface.blit(self.font_small.render(line, True, COLOUR_TEXT), (popup.x + padding, ty))
            ty += line_h
