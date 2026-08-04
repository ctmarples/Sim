"""Top toolbar: File menu, build buttons, farm field/plan editors, sim speed."""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from entities import (
    BUILDING_LABELS,
    WORK_MODE_LABELS,
    Building,
    BuildingKind,
    WorkMode,
)
from seasons import Season
from settings import (
    COLOUR_MENU_BG,
    COLOUR_TEXT,
    COLOUR_TEXT_DIM,
    COLOUR_TOOLBAR_BG,
    COLOUR_TOOLBAR_BORDER,
    COLOUR_TOOLBAR_BTN,
    COLOUR_TOOLBAR_BTN_ACTIVE,
    COLOUR_TOOLBAR_BTN_HOVER,
    SIM_SPEEDS,
    TOOLBAR_HEIGHT,
    WINDOW_WIDTH,
)

BUILD_ORDER: list[BuildingKind | None] = [
    BuildingKind.FORESTER,
    BuildingKind.MASON,
    BuildingKind.HUNTER,
    BuildingKind.FORAGER,
    BuildingKind.FISHER,
    BuildingKind.FARM,
    BuildingKind.FIELD,
    BuildingKind.MILL,
    BuildingKind.KITCHEN,
    None,
]

_BUILD_SHORT: dict[BuildingKind, str] = {
    BuildingKind.FORESTER: "For",
    BuildingKind.MASON: "Mas",
    BuildingKind.HUNTER: "Hunt",
    BuildingKind.FORAGER: "Fora",
    BuildingKind.FISHER: "Fish",
    BuildingKind.FARM: "Farm",
    BuildingKind.FIELD: "Field",
    BuildingKind.MILL: "Mill",
    BuildingKind.KITCHEN: "Kit",
}


@dataclass
class ToolbarButton:
    action: str
    label: str
    rect: pygame.Rect
    group: str = ""


class Toolbar:
    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 13)
        self.font_small = pygame.font.SysFont("menlo", 12)
        self.file_menu_open = False
        self._hover: str | None = None
        self._buttons: list[ToolbarButton] = []
        self._menu_buttons: list[ToolbarButton] = []
        self._rebuild_static()

    def _make_btn(
        self, action: str, label: str, x: int, y: int, w: int, h: int, group: str = ""
    ) -> ToolbarButton:
        return ToolbarButton(action, label, pygame.Rect(x, y, w, h), group)

    def _rebuild_static(self) -> None:
        self._buttons = []
        x = 8
        y = 6
        h = 22
        self._buttons.append(self._make_btn("file_toggle", "File", x, y, 44, h, "file"))
        x += 52
        for kind in BUILD_ORDER:
            if kind is None:
                label, action = "Off", "build_off"
            else:
                label = _BUILD_SHORT.get(kind, BUILDING_LABELS[kind][:4])
                action = f"build_{kind.name.lower()}"
            w = max(40, 8 + self.font_small.size(label)[0])
            self._buttons.append(self._make_btn(action, label, x, y, w, h, "build"))
            x += w + 4

        speed_x = WINDOW_WIDTH - 8
        speed_btns: list[ToolbarButton] = []
        for speed in reversed(SIM_SPEEDS):
            label = "Pause" if speed == 0 else f"x{speed}"
            w = max(40, 8 + self.font_small.size(label)[0])
            speed_x -= w
            speed_btns.append(
                self._make_btn(f"speed_{speed}", label, speed_x, y, w, h, "speed")
            )
            speed_x -= 4
        self._buttons.extend(reversed(speed_btns))

        self._menu_buttons = [
            self._make_btn("file_save", "Save…", 8, TOOLBAR_HEIGHT + 4, 100, 24, "menu"),
            self._make_btn("file_load", "Load…", 8, TOOLBAR_HEIGHT + 30, 100, 24, "menu"),
            self._make_btn("file_reset", "Reset", 8, TOOLBAR_HEIGHT + 56, 100, 24, "menu"),
            self._make_btn("file_quit", "Quit", 8, TOOLBAR_HEIGHT + 82, 100, 24, "menu"),
        ]

    def task_buttons_for(
        self,
        building: Building | None,
        *,
        place_kind: BuildingKind | None = None,
        field_season: Season = Season.SPRING,
        field_crop: str = "sage",
        selected_field_id: int | None = None,
        farm_draw_mode: str = "field",
    ) -> list[ToolbarButton]:
        buttons: list[ToolbarButton] = []
        x = 8
        y = 36
        h = 22

        if building is None:
            return buttons

        # Field / home / hiring hall: options live in their popups.
        if building.kind in (
            BuildingKind.FIELD,
            BuildingKind.HOME,
            BuildingKind.WORKSTATION,
        ):
            return buttons

        modes = building.supported_work_modes()
        for mode in modes:
            label = WORK_MODE_LABELS[mode]
            w = max(52, 10 + self.font_small.size(label)[0])
            buttons.append(
                self._make_btn(f"mode_{mode.name}", label, x, y, w, h, "mode")
            )
            x += w + 4
        if building.kind not in (
            BuildingKind.FARM,
            BuildingKind.MILL,
            BuildingKind.KITCHEN,
        ):
            clear_label = "Clear"
            clear_w = max(48, 10 + self.font_small.size(clear_label)[0])
            buttons.append(
                self._make_btn("task_clear", clear_label, x, y, clear_w, h, "task")
            )
        return buttons

    def hit_test(
        self,
        pos: tuple[int, int],
        building: Building | None,
        *,
        place_kind: BuildingKind | None = None,
        field_season: Season = Season.SPRING,
        field_crop: str = "sage",
        selected_field_id: int | None = None,
        farm_draw_mode: str = "field",
    ) -> str | None:
        mx, my = pos
        if self.file_menu_open:
            for btn in self._menu_buttons:
                if btn.rect.collidepoint(mx, my):
                    return btn.action
            for btn in self._buttons:
                if btn.action == "file_toggle" and btn.rect.collidepoint(mx, my):
                    return btn.action
            if my < TOOLBAR_HEIGHT:
                for btn in self._buttons:
                    if btn.rect.collidepoint(mx, my):
                        return btn.action
            return None

        if my >= TOOLBAR_HEIGHT:
            return None
        for btn in self._buttons:
            if btn.rect.collidepoint(mx, my):
                return btn.action
        for btn in self.task_buttons_for(
            building,
            place_kind=place_kind,
            field_season=field_season,
            field_crop=field_crop,
            selected_field_id=selected_field_id,
            farm_draw_mode=farm_draw_mode,
        ):
            if btn.rect.collidepoint(mx, my):
                return btn.action
        return None

    def contains(self, pos: tuple[int, int]) -> bool:
        _, my = pos
        if my < TOOLBAR_HEIGHT:
            return True
        if self.file_menu_open:
            menu_h = 4 * 26 + 8
            if 8 <= pos[0] <= 112 and TOOLBAR_HEIGHT <= my <= TOOLBAR_HEIGHT + menu_h:
                return True
        return False

    def draw(
        self,
        surface: pygame.Surface,
        place_kind: BuildingKind | None,
        building: Building | None,
        sim_speed: int,
        mouse_pos: tuple[int, int],
        season_label: str | None = None,
        field_season: Season = Season.SPRING,
        field_crop: str = "sage",
        selected_field_id: int | None = None,
        farm_draw_mode: str = "field",
    ) -> None:
        bar = pygame.Rect(0, 0, WINDOW_WIDTH, TOOLBAR_HEIGHT)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BG, bar)
        pygame.draw.line(
            surface,
            COLOUR_TOOLBAR_BORDER,
            (0, TOOLBAR_HEIGHT - 1),
            (WINDOW_WIDTH, TOOLBAR_HEIGHT - 1),
            1,
        )

        self._hover = None
        active_build = (
            "build_off"
            if place_kind is None
            else f"build_{place_kind.name.lower()}"
        )
        active_mode = (
            f"mode_{building.work_mode.name}" if building is not None else None
        )
        active_speed = f"speed_{sim_speed}"

        all_btns = list(self._buttons) + self.task_buttons_for(
            building,
            place_kind=place_kind,
            field_season=field_season,
            field_crop=field_crop,
            selected_field_id=selected_field_id,
            farm_draw_mode=farm_draw_mode,
        )
        for btn in all_btns:
            hovered = btn.rect.collidepoint(mouse_pos)
            if hovered:
                self._hover = btn.action
            active = (
                btn.action == active_build
                or btn.action == active_mode
                or btn.action == active_speed
                or (btn.action == "file_toggle" and self.file_menu_open)
            )
            self._draw_button(surface, btn, active=active, hovered=hovered)

        if season_label:
            speed_btns = [b for b in self._buttons if b.group == "speed"]
            if speed_btns:
                left = min(b.rect.x for b in speed_btns) - 8
                text = self.font.render(season_label, True, COLOUR_TEXT_DIM)
                surface.blit(text, (left - text.get_width(), 10))

        if self.file_menu_open:
            menu_rect = pygame.Rect(6, TOOLBAR_HEIGHT - 2, 108, 4 * 26 + 10)
            pygame.draw.rect(surface, COLOUR_MENU_BG, menu_rect)
            pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, menu_rect, 1)
            for btn in self._menu_buttons:
                hovered = btn.rect.collidepoint(mouse_pos)
                self._draw_button(surface, btn, active=False, hovered=hovered)

    def _draw_button(
        self,
        surface: pygame.Surface,
        btn: ToolbarButton,
        *,
        active: bool,
        hovered: bool,
    ) -> None:
        if active:
            colour = COLOUR_TOOLBAR_BTN_ACTIVE
        elif hovered:
            colour = COLOUR_TOOLBAR_BTN_HOVER
        else:
            colour = COLOUR_TOOLBAR_BTN
        pygame.draw.rect(surface, colour, btn.rect, border_radius=3)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, btn.rect, 1, border_radius=3)
        text = self.font_small.render(btn.label, True, COLOUR_TEXT)
        surface.blit(
            text,
            (
                btn.rect.x + (btn.rect.w - text.get_width()) // 2,
                btn.rect.y + (btn.rect.h - text.get_height()) // 2,
            ),
        )
