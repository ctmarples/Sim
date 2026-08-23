"""Floating inspection window for wildlife breeding grounds / nest habitats."""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from settings import (
    COLOUR_MENU_BG,
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
ROW_H = 20
SECTION_GAP = 8


@dataclass
class HabitatInspectView:
    """Precomputed habitat stats for the inspector panel."""

    title: str
    subtitle: str
    population: str
    breeding_tiles: int
    roam_tiles: int
    avg_disturbance: float
    max_disturbance: float
    ecology_mult: float
    breed_chance_pct: float
    health_pct: float
    benefits: list[tuple[str, str]]
    # "habitat" (deer/boar/bee/rabbit/frog/vole), "wolf"/"fox" packs, or "bird"
    panel_kind: str = "habitat"
    activity: str = ""
    last_meal: str = ""
    food_status: str = ""
    fed_until: str = ""


class HabitatInspectDialog:
    """Movable floating inspector for deer/boar grounds and bee/rabbit nests."""

    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 14)
        self.font_small = pygame.font.SysFont("menlo", 12)
        self.font_title = pygame.font.SysFont("menlo", 15, bold=True)
        self.habitat_kind = None
        self.habitat_id: int | None = None
        self._panel_x = 80
        self._panel_y = MAP_OFFSET_Y + 40
        self._panel_w = 340
        self._panel_h = 320
        self._moving = False
        self._move_offset = (0, 0)
        self._close_rect = pygame.Rect(0, 0, 0, 0)
        self._title_rect = pygame.Rect(0, 0, 0, 0)

    @property
    def open(self) -> bool:
        return self.habitat_id is not None and self.habitat_kind is not None

    def open_for(
        self,
        kind,
        patch_id: int,
        *,
        screen_xy: tuple[int, int] | None = None,
    ) -> None:
        self.habitat_kind = kind
        self.habitat_id = patch_id
        self._moving = False
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
        self.habitat_kind = None
        self.habitat_id = None
        self._moving = False

    def panel_rect(self) -> pygame.Rect:
        return pygame.Rect(self._panel_x, self._panel_y, self._panel_w, self._panel_h)

    def contains(self, pos: tuple[int, int]) -> bool:
        return self.open and self.panel_rect().collidepoint(pos)

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
        return True

    def handle_mousedown(self, pos: tuple[int, int]) -> bool:
        if not self.open:
            return False
        if self._close_rect.collidepoint(pos):
            self.close()
            return True
        if self._title_rect.collidepoint(pos):
            self._moving = True
            self._move_offset = (pos[0] - self._panel_x, pos[1] - self._panel_y)
            return True
        return self.panel_rect().collidepoint(pos)

    def handle_mouseup(self, pos: tuple[int, int]) -> bool:
        if not self.open:
            return False
        if self._moving:
            self._moving = False
            return True
        return self.panel_rect().collidepoint(pos)

    def handle_mousemotion(self, pos: tuple[int, int]) -> None:
        if self._moving:
            self._panel_x = pos[0] - self._move_offset[0]
            self._panel_y = pos[1] - self._move_offset[1]
            self._clamp_panel()

    def _draw_button(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        label: str,
        *,
        hovered: bool = False,
    ) -> None:
        bg = COLOUR_TOOLBAR_BTN_HOVER if hovered else COLOUR_TOOLBAR_BTN
        pygame.draw.rect(surface, bg, rect)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, rect, 1)
        text = self.font_small.render(label, True, COLOUR_TEXT)
        surface.blit(
            text,
            (rect.x + (rect.w - text.get_width()) // 2, rect.y + (rect.h - text.get_height()) // 2),
        )

    def _line(
        self,
        surface: pygame.Surface,
        y: int,
        label: str,
        value: str,
        *,
        dim_value: bool = False,
    ) -> int:
        surface.blit(self.font_small.render(label, True, COLOUR_TEXT_DIM), (self._panel_x + PAD, y))
        val_colour = COLOUR_TEXT_DIM if dim_value else COLOUR_TEXT
        val = self.font.render(value, True, val_colour)
        surface.blit(val, (self._panel_x + self._panel_w - PAD - val.get_width(), y - 1))
        return y + ROW_H

    def draw(
        self,
        surface: pygame.Surface,
        view: HabitatInspectView | None,
        *,
        mouse_pos: tuple[int, int] | None = None,
    ) -> None:
        if not self.open or view is None:
            return
        panel = self.panel_rect()
        pygame.draw.rect(surface, COLOUR_MENU_BG, panel)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, panel, 2)

        self._title_rect = pygame.Rect(panel.x, panel.y, panel.w, TITLE_BAR_H)
        title = self.font_title.render(view.title, True, COLOUR_TEXT)
        surface.blit(title, (panel.x + PAD, panel.y + 6))
        self._close_rect = pygame.Rect(panel.right - 28, panel.y + 4, 22, 20)
        mp = mouse_pos or (0, 0)
        self._draw_button(
            surface,
            self._close_rect,
            "×",
            hovered=self._close_rect.collidepoint(mp),
        )

        y = panel.y + TITLE_BAR_H + 4
        surface.blit(
            self.font_small.render(view.subtitle, True, COLOUR_TEXT_DIM),
            (panel.x + PAD, y),
        )
        y += ROW_H + 4

        if view.panel_kind in ("wolf", "bird"):
            is_bird = view.panel_kind == "bird"
            y = self._line(
                surface, y, "Bird" if is_bird else "Pack", view.population
            )
            y = self._line(surface, y, "Activity", view.activity or "—")
            if is_bird:
                y = self._line(surface, y, "Diet", view.food_status or "—")
            else:
                y = self._line(surface, y, "Last meal", view.last_meal or "None yet")
                y = self._line(surface, y, "Food", view.food_status or "Hungry")
                y = self._line(surface, y, "Fed until", view.fed_until or "—")
            y += SECTION_GAP

            surface.blit(
                self.font_small.render("Status", True, COLOUR_TEXT),
                (panel.x + PAD, y),
            )
            y += ROW_H
            for label, value in view.benefits:
                y = self._line(surface, y, label, value, dim_value=True)
            y += SECTION_GAP

            health_colour = COLOUR_TEXT
            if view.health_pct < 40:
                health_colour = (220, 100, 90)
            elif view.health_pct < 70:
                health_colour = (220, 180, 80)
            surface.blit(
                self.font_small.render("Vitality", True, COLOUR_TEXT),
                (panel.x + PAD, y),
            )
            y += ROW_H
            y = self._line(surface, y, "Overall health", f"{view.health_pct:.0f}%")
            health_val = self.font.render(
                f"{view.health_pct:.0f}%", True, health_colour
            )
            surface.blit(
                health_val,
                (
                    panel.x + self._panel_w - PAD - health_val.get_width(),
                    y - ROW_H - 1,
                ),
            )
            if not is_bird:
                y = self._line(
                    surface,
                    y,
                    "Breeding chance",
                    f"{view.breed_chance_pct:.0f}% / tick",
                )
            return

        y = self._line(surface, y, "Population", view.population)
        y = self._line(surface, y, "Breeding area", f"{view.breeding_tiles} cells")
        y = self._line(surface, y, "Roaming / forage", f"{view.roam_tiles} cells")
        y += SECTION_GAP

        surface.blit(self.font_small.render("Environment", True, COLOUR_TEXT), (panel.x + PAD, y))
        y += ROW_H
        for label, value in view.benefits:
            y = self._line(surface, y, label, value, dim_value=True)
        y += SECTION_GAP

        surface.blit(self.font_small.render("Disturbance", True, COLOUR_TEXT), (panel.x + PAD, y))
        y += ROW_H
        y = self._line(
            surface,
            y,
            "Average (radius)",
            f"{view.avg_disturbance * 100:.0f}%",
        )
        y = self._line(
            surface,
            y,
            "Peak",
            f"{view.max_disturbance * 100:.0f}%",
        )
        y = self._line(
            surface,
            y,
            "Ecology modifier",
            f"×{view.ecology_mult:.2f}",
        )
        y += SECTION_GAP

        health_colour = COLOUR_TEXT
        if view.health_pct < 40:
            health_colour = (220, 100, 90)
        elif view.health_pct < 70:
            health_colour = (220, 180, 80)
        surface.blit(self.font_small.render("Vitality", True, COLOUR_TEXT), (panel.x + PAD, y))
        y += ROW_H
        y = self._line(surface, y, "Overall health", f"{view.health_pct:.0f}%")
        health_val = self.font.render(f"{view.health_pct:.0f}%", True, health_colour)
        surface.blit(
            health_val,
            (panel.x + self._panel_w - PAD - health_val.get_width(), y - ROW_H - 1),
        )
        y = self._line(
            surface,
            y,
            "Breeding chance",
            f"{view.breed_chance_pct:.0f}% / spring",
        )
