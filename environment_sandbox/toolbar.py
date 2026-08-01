"""Top toolbar: File menu, build buttons, task buttons, sim speed."""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from entities import (
    BUILDING_LABELS,
    FORAGER_TASK_CYCLE,
    FORESTER_TASK_CYCLE,
    TASK_LABELS,
    Building,
    BuildingKind,
    TaskType,
)
from settings import (
    COLOUR_MENU_BG,
    COLOUR_TEXT,
    COLOUR_TOOLBAR_BG,
    COLOUR_TOOLBAR_BORDER,
    COLOUR_TOOLBAR_BTN,
    COLOUR_TOOLBAR_BTN_ACTIVE,
    COLOUR_TOOLBAR_BTN_HOVER,
    SIM_SPEEDS,
    TOOLBAR_HEIGHT,
    WINDOW_WIDTH,
)

TASK_SHORT: dict[TaskType, str] = {
    TaskType.CHOP_TREES: "Chop",
    TaskType.PLANT_SAPLINGS: "Plant",
    TaskType.FULL_MANAGE: "Manage",
    TaskType.COLLECT_ROCKS: "Rocks",
    TaskType.HUNT: "Hunt",
    TaskType.FISH: "Fish",
    TaskType.FORAGE_MUSHROOMS: "Mush",
    TaskType.FORAGE_BERRIES: "Berry",
    TaskType.FORAGE_HERBS: "Herb",
    TaskType.PLANT_BERRY_SEEDS: "B.seed",
    TaskType.PLANT_HERB_SEEDS: "H.seed",
    TaskType.FULL_FORAGE: "Forage+",
}

BUILD_ORDER: list[BuildingKind | None] = [
    BuildingKind.FORESTER,
    BuildingKind.MASON,
    BuildingKind.HUNTER,
    BuildingKind.FORAGER,
    BuildingKind.FISHER,
    None,
]


@dataclass
class ToolbarButton:
    action: str
    label: str
    rect: pygame.Rect
    group: str = ""


class Toolbar:
    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 12)
        self.font_small = pygame.font.SysFont("menlo", 11)
        self.file_menu_open = False
        self._hover: str | None = None
        self._buttons: list[ToolbarButton] = []
        self._menu_buttons: list[ToolbarButton] = []
        self._rebuild_static()

    def _make_btn(
        self, action: str, label: str, x: int, y: int, w: int, h: int, group: str = ""
    ) -> ToolbarButton:
        return ToolbarButton(action=action, label=label, rect=pygame.Rect(x, y, w, h), group=group)

    def _rebuild_static(self) -> None:
        self._buttons = []
        x = 8
        y = 8
        h = 22
        self._buttons.append(self._make_btn("file_toggle", "File", x, y, 48, h, "file"))
        x += 56
        self._buttons.append(self._make_btn("file_save", "Save", x, y, 48, h, "file"))
        x += 52
        self._buttons.append(self._make_btn("file_load", "Load", x, y, 48, h, "file"))
        x += 64

        for kind in BUILD_ORDER:
            label = "Off" if kind is None else BUILDING_LABELS[kind][:4]
            action = "build_off" if kind is None else f"build_{kind.name.lower()}"
            w = 40 if kind is None else 52
            self._buttons.append(self._make_btn(action, label, x, y, w, h, "build"))
            x += w + 3

        speed_x = WINDOW_WIDTH - 8
        speed_btns: list[ToolbarButton] = []
        for speed in reversed(SIM_SPEEDS):
            w = 36
            speed_x -= w + 4
            speed_btns.append(
                self._make_btn(f"speed_{speed}", f"x{speed}", speed_x, y, w, h, "speed")
            )
        self._buttons.extend(reversed(speed_btns))

        # Second row reserved for task buttons (dynamic).
        self._menu_buttons = [
            self._make_btn("file_save", "Save…", 8, TOOLBAR_HEIGHT, 100, 24, "menu"),
            self._make_btn("file_load", "Load…", 8, TOOLBAR_HEIGHT + 26, 100, 24, "menu"),
            self._make_btn("file_reset", "Reset world", 8, TOOLBAR_HEIGHT + 52, 100, 24, "menu"),
            self._make_btn("file_quit", "Quit", 8, TOOLBAR_HEIGHT + 78, 100, 24, "menu"),
        ]

    def task_buttons_for(self, building: Building | None) -> list[ToolbarButton]:
        buttons: list[ToolbarButton] = []
        x = 8
        y = 36
        h = 22
        if building is None:
            return buttons
        if building.kind == BuildingKind.FORESTER:
            tasks = FORESTER_TASK_CYCLE
        elif building.kind == BuildingKind.MASON:
            tasks = (TaskType.COLLECT_ROCKS,)
        elif building.kind == BuildingKind.HUNTER:
            tasks = (TaskType.HUNT,)
        elif building.kind == BuildingKind.FISHER:
            tasks = (TaskType.FISH,)
        else:
            tasks = FORAGER_TASK_CYCLE
        for task in tasks:
            label = TASK_SHORT.get(task, TASK_LABELS[task][:6])
            w = max(44, 8 + self.font_small.size(label)[0])
            buttons.append(
                self._make_btn(f"task_{task.name}", label, x, y, w, h, "task")
            )
            x += w + 4
        buttons.append(self._make_btn("task_clear", "Clear", x, y, 48, h, "task"))
        return buttons

    def hit_test(
        self, pos: tuple[int, int], building: Building | None
    ) -> str | None:
        mx, my = pos
        if self.file_menu_open:
            for btn in self._menu_buttons:
                if btn.rect.collidepoint(mx, my):
                    return btn.action
            # Click on File toggle still counts.
            for btn in self._buttons:
                if btn.action == "file_toggle" and btn.rect.collidepoint(mx, my):
                    return btn.action
            # Click elsewhere closes menu (handled by caller via None + close).
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
        for btn in self.task_buttons_for(building):
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
        active_task = (
            f"task_{building.draw_task_type.name}" if building is not None else None
        )
        active_speed = f"speed_{sim_speed}"

        all_btns = list(self._buttons) + self.task_buttons_for(building)
        for btn in all_btns:
            hovered = btn.rect.collidepoint(mouse_pos)
            if hovered:
                self._hover = btn.action
            active = (
                btn.action == active_build
                or btn.action == active_task
                or btn.action == active_speed
                or (btn.action == "file_toggle" and self.file_menu_open)
            )
            self._draw_button(surface, btn, active=active, hovered=hovered)

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
        tx = btn.rect.x + (btn.rect.w - text.get_width()) // 2
        ty = btn.rect.y + (btn.rect.h - text.get_height()) // 2
        surface.blit(text, (tx, ty))
