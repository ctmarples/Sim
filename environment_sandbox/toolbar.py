"""Top toolbar: File menu, build buttons, farm field/plan editors, sim speed."""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from building_unlock import (
    building_cost,
    visible_build_order,
)
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

# Icon stem per placeable building (matches assets/icons).
_BUILD_ICON: dict[BuildingKind, str] = {
    BuildingKind.FORAGER: "forager",
    BuildingKind.CRAFT_BENCH: "craft_bench",
    BuildingKind.HUNTER: "hunter",
    BuildingKind.FORESTER: "forester",
    BuildingKind.MASON: "mason",
    BuildingKind.WORKSTATION: "workstation",
    BuildingKind.FISHER: "fisher",
    BuildingKind.FARM: "farm",
    BuildingKind.FIELD: "field",
    BuildingKind.KITCHEN: "kitchen",
    BuildingKind.MILL: "mill",
    BuildingKind.ALCHEMIST: "alchemist",
    BuildingKind.TAILOR: "tailor",
    BuildingKind.MARKET: "market",
    BuildingKind.TENT: "tent",
    BuildingKind.HOUSE_SMALL: "house_small",
    BuildingKind.HOUSE: "house",
}


@dataclass
class ToolbarButton:
    action: str
    label: str
    rect: pygame.Rect
    group: str = ""
    kind: BuildingKind | None = None


class Toolbar:
    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 13)
        self.font_small = pygame.font.SysFont("menlo", 12)
        self.file_menu_open = False
        self._hover: str | None = None
        self._hover_kind: BuildingKind | None = None
        self._buttons: list[ToolbarButton] = []
        self._menu_buttons: list[ToolbarButton] = []
        self._built_kinds: set[BuildingKind] = set()
        self._icon_cache: dict[str, pygame.Surface] = {}
        self._rebuild_static()

    def set_built_kinds(self, built: set[BuildingKind]) -> None:
        """Refresh build buttons when unlock state changes."""
        if built == self._built_kinds:
            return
        self._built_kinds = set(built)
        self._rebuild_static()

    def _make_btn(
        self,
        action: str,
        label: str,
        x: int,
        y: int,
        w: int,
        h: int,
        group: str = "",
        kind: BuildingKind | None = None,
    ) -> ToolbarButton:
        return ToolbarButton(action, label, pygame.Rect(x, y, w, h), group, kind)

    def _build_icon(self, stem: str, size: int = 20) -> pygame.Surface | None:
        key = f"{stem}:{size}"
        cached = self._icon_cache.get(key)
        if cached is not None:
            return cached
        try:
            from icons import get_icon

            icon = get_icon(stem, size)
            self._icon_cache[key] = icon.surface
            return icon.surface
        except (FileNotFoundError, OSError, Exception):
            return None

    def _rebuild_static(self) -> None:
        self._buttons = []
        x = 8
        y = 6
        h = 28
        self._buttons.append(self._make_btn("file_toggle", "File", x, y, 44, h, "file"))
        x += 52
        order = visible_build_order(self._built_kinds)
        for kind in order:
            if kind is None:
                label, action = "Off", "build_off"
                w = 36
                self._buttons.append(self._make_btn(action, label, x, y, w, h, "build"))
                x += w + 4
                continue
            action = f"build_{kind.name.lower()}"
            w = 32
            self._buttons.append(
                self._make_btn(action, "", x, y, w, h, "build", kind=kind)
            )
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
            self._make_btn("file_save", "Save…", 8, TOOLBAR_HEIGHT + 4, 110, 24, "menu"),
            self._make_btn("file_load", "Load…", 8, TOOLBAR_HEIGHT + 30, 110, 24, "menu"),
            self._make_btn(
                "file_tracker", "Tracker…", 8, TOOLBAR_HEIGHT + 56, 110, 24, "menu"
            ),
            self._make_btn(
                "file_balance", "Balance…", 8, TOOLBAR_HEIGHT + 82, 110, 24, "menu"
            ),
            self._make_btn("file_reset", "Reset", 8, TOOLBAR_HEIGHT + 108, 110, 24, "menu"),
            self._make_btn("day_slower", "Day length −", 8, TOOLBAR_HEIGHT + 134, 110, 24, "menu"),
            self._make_btn("day_faster", "Day length +", 8, TOOLBAR_HEIGHT + 160, 110, 24, "menu"),
            self._make_btn("file_quit", "Quit", 8, TOOLBAR_HEIGHT + 186, 110, 24, "menu"),
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
            BuildingKind.CRAFT_BENCH,
            BuildingKind.ALCHEMIST,
            BuildingKind.TAILOR,
            BuildingKind.MARKET,
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
            menu_h = 7 * 26 + 8
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
        built_kinds: set[BuildingKind] | None = None,
    ) -> None:
        if built_kinds is not None:
            self.set_built_kinds(built_kinds)

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
        self._hover_kind = None
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
                self._hover_kind = btn.kind
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
            menu_rect = pygame.Rect(6, TOOLBAR_HEIGHT - 2, 108, 7 * 26 + 10)
            pygame.draw.rect(surface, COLOUR_MENU_BG, menu_rect)
            pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, menu_rect, 1)
            for btn in self._menu_buttons:
                hovered = btn.rect.collidepoint(mouse_pos)
                self._draw_button(surface, btn, active=False, hovered=hovered)

        if self._hover_kind is not None:
            self._draw_build_tooltip(surface, self._hover_kind, mouse_pos)

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
        if btn.kind is not None:
            stem = _BUILD_ICON.get(btn.kind)
            icon = self._build_icon(stem, 22) if stem else None
            if icon is not None:
                ix = btn.rect.centerx - icon.get_width() // 2
                iy = btn.rect.centery - icon.get_height() // 2
                surface.blit(icon, (ix, iy))
                return
        text = self.font_small.render(btn.label, True, COLOUR_TEXT)
        surface.blit(
            text,
            (
                btn.rect.centerx - text.get_width() // 2,
                btn.rect.centery - text.get_height() // 2,
            ),
        )

    def _draw_build_tooltip(
        self,
        surface: pygame.Surface,
        kind: BuildingKind,
        mouse_pos: tuple[int, int],
    ) -> None:
        cost = building_cost(kind)
        name = BUILDING_LABELS.get(kind, kind.name.title())
        title = self.font.render(name, True, COLOUR_TEXT)
        parts = cost.as_parts()
        icon_size = 18
        gap = 6
        row_h = max(icon_size, self.font_small.get_height()) + 4
        width = max(title.get_width(), 8)
        for key, amount in parts:
            label = self.font_small.render(f"×{amount}", True, COLOUR_TEXT)
            width = max(width, icon_size + 4 + label.get_width())
        pad = 8
        box_w = width + pad * 2
        box_h = pad * 2 + title.get_height() + (row_h * len(parts) if parts else 0) + 4
        mx, my = mouse_pos
        x = min(max(4, mx + 12), WINDOW_WIDTH - box_w - 4)
        y = min(max(4, my + 14), TOOLBAR_HEIGHT + 120)
        box = pygame.Rect(x, y, box_w, box_h)
        pygame.draw.rect(surface, COLOUR_MENU_BG, box, border_radius=4)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, box, 1, border_radius=4)
        surface.blit(title, (x + pad, y + pad))
        cy = y + pad + title.get_height() + 4
        for key, amount in parts:
            icon = self._build_icon(key, icon_size)
            if icon is not None:
                surface.blit(icon, (x + pad, cy))
            label = self.font_small.render(f"×{amount}", True, COLOUR_TEXT)
            lx = x + pad + (icon_size + 4 if icon is not None else 0)
            surface.blit(label, (lx, cy + (icon_size - label.get_height()) // 2))
            cy += row_h
