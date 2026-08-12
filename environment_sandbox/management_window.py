"""Central management window: People / Buildings / Wildlife.

Left pane = selected entity detail; right pane = list. Independent pane
toggles keep at least one pane visible. Villager/building selection opens
this window; resource and wildlife floating inspects stay separate
(wildlife is also browsable here).
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Any, Callable

import pygame

from entities import BUILDING_LABELS, Building, BuildingKind, ConstructionSite, Villager
from habitat_inspect_dialog import HabitatInspectView
from icons import blit_icon
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
from society import (
    SKILL_ORDER,
    candidate_requirement_rows,
    free_housing_beds,
    is_housing_kind,
    max_housing_level,
    villager_requirement_rows,
)
from villager_roster import (
    COL_BAR_W,
    COL_HOUSE_W,
    COL_NAME_W,
    COL_PAY_W,
    HEADER_H,
    PORTRAIT_SIZE,
    REQ_ICON,
    ROW_H,
    RosterEntry,
    RosterSort,
    SKILL_COL_W,
    SORT_LABELS,
    _column_layout,
    _table_width,
    draw_portrait,
    draw_requirement_icons,
    draw_skill_cell,
    draw_status_bar,
    entry_from_villager,
    sort_entries,
    villager_job_colour,
)

TITLE_BAR_H = 32
TAB_H = 36
PANE_BTN_H = 26
PAD = 10
LIST_ROW_H = 36


class MgmtTab(Enum):
    PEOPLE = auto()
    BUILDINGS = auto()
    WILDLIFE = auto()


_TAB_META: dict[MgmtTab, tuple[str, str]] = {
    MgmtTab.PEOPLE: ("villager", "People"),
    MgmtTab.BUILDINGS: ("construction_site", "Buildings"),
    MgmtTab.WILDLIFE: ("deer_male", "Wildlife"),
}

_BUILD_ICON: dict[BuildingKind, str] = {
    BuildingKind.HOME: "storehouse",
    BuildingKind.WORKSTATION: "workstation",
    BuildingKind.FORAGER: "forager",
    BuildingKind.CRAFT_BENCH: "craft_bench",
    BuildingKind.HUNTER: "hunter",
    BuildingKind.FORESTER: "forester",
    BuildingKind.MASON: "mason",
    BuildingKind.FISHER: "fisher",
    BuildingKind.FARM: "farm",
    BuildingKind.FIELD: "field",
    BuildingKind.KITCHEN: "kitchen",
    BuildingKind.MILL: "mill",
    BuildingKind.ALCHEMIST: "alchemist",
    BuildingKind.TAILOR: "tailor",
    BuildingKind.COBBLER: "cobbler",
    BuildingKind.MARKET: "market",
    BuildingKind.TENT: "tent",
    BuildingKind.HOUSE_SMALL: "house_small",
    BuildingKind.HOUSE: "house",
    BuildingKind.BARN: "barn",
    BuildingKind.PANTRY: "pantry",
    BuildingKind.DRYING_RACK: "drying_rack",
}

_MAT_ICON = {
    "wood": "wood",
    "logs": "log_wood",
    "hardwood_logs": "log_hardwood",
    "rock": "rock_1",
}


def _draw_inspect_glyph(
    surface: pygame.Surface, rect: pygame.Rect, colour: tuple[int, int, int]
) -> None:
    """Document + magnifier drawn with pygame lines."""
    doc = pygame.Rect(rect.x + 5, rect.y + 4, 10, 14)
    pygame.draw.rect(surface, colour, doc, 1)
    for i in range(3):
        ly = doc.y + 3 + i * 3
        pygame.draw.line(surface, colour, (doc.x + 2, ly), (doc.right - 2, ly), 1)
    cx, cy = rect.x + 16, rect.y + 15
    pygame.draw.circle(surface, colour, (cx, cy), 5, 1)
    pygame.draw.line(surface, colour, (cx + 3, cy + 3), (cx + 7, cy + 7), 2)


def _draw_list_glyph(
    surface: pygame.Surface, rect: pygame.Rect, colour: tuple[int, int, int]
) -> None:
    """Hamburger list lines."""
    x0, x1 = rect.x + 6, rect.right - 6
    mid = rect.centery
    for dy in (-5, 0, 5):
        pygame.draw.line(surface, colour, (x0, mid + dy), (x1, mid + dy), 2)


class ManagementWindow:
    """Anchored central panel with tabs and dual panes."""

    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 14)
        self.font_small = pygame.font.SysFont("menlo", 12)
        self.font_tiny = pygame.font.SysFont("menlo", 11, bold=True)
        self.font_title = pygame.font.SysFont("menlo", 15, bold=True)
        self.open = False
        self.tab = MgmtTab.PEOPLE
        self.show_detail: bool = True
        self.show_list: bool = True
        self.selected_villager_id: int | None = None
        self.selected_building_id: int | None = None
        self.selected_construction_id: int | None = None
        self.selected_habitat: tuple[Any, int] | None = None  # (AnimalKind, id)
        self.show_player = False
        # hire / assign / roster modes for people tab list actions
        self.people_mode: str = "roster"  # roster | hire | assign
        self.assign_building_id: int | None = None
        self._scroll = 0
        self._pending_action: str | None = None
        self._buttons: list[tuple[str, pygame.Rect]] = []
        self._list_hits: list[tuple[pygame.Rect, str, int | str]] = []
        self._header_hits: list[tuple[pygame.Rect, RosterSort]] = []
        self._tooltip: tuple[str, tuple[int, int]] | None = None
        self._panel = pygame.Rect(0, 0, 0, 0)
        self._close_rect = pygame.Rect(0, 0, 0, 0)
        self._detail_rect = pygame.Rect(0, 0, 0, 0)
        self._list_rect = pygame.Rect(0, 0, 0, 0)
        self._moving = False
        self._move_offset = (0, 0)
        self._title_rect = pygame.Rect(0, 0, 0, 0)
        self._roster_sort = RosterSort.NAME
        self._roster_asc = True
        # Nested inspect dialogs draw into detail pane when set by Game.
        self.embed_building_inspect = True
        self.embed_villager_inspect = True

    def open_window(
        self,
        tab: MgmtTab = MgmtTab.PEOPLE,
        *,
        people_mode: str = "roster",
        assign_building_id: int | None = None,
    ) -> None:
        self.open = True
        self.tab = tab
        self.people_mode = people_mode
        self.assign_building_id = assign_building_id
        self._pending_action = None
        self._scroll = 0
        self._layout_panel()

    def open_people_list(self) -> None:
        """Open People tab with the villager roster list visible."""
        self.open_window(MgmtTab.PEOPLE, people_mode="roster")
        self.show_list = True
        self._layout_panel()

    def close(self) -> None:
        self.open = False
        self._pending_action = "mgmt_closed"
        self._moving = False
        self.people_mode = "roster"
        self.assign_building_id = None
        self.show_player = False

    def take_action(self) -> str | None:
        action = self._pending_action
        self._pending_action = None
        return action

    def select_villager(
        self, vid: int, *, show_player: bool = False, detail_only: bool = False
    ) -> None:
        # Preserve hire/assign context when already open.
        mode = self.people_mode if self.open else "roster"
        assign = self.assign_building_id if self.open else None
        self.open_window(
            MgmtTab.PEOPLE, people_mode=mode, assign_building_id=assign
        )
        self.selected_villager_id = vid
        self.selected_building_id = None
        self.selected_construction_id = None
        self.selected_habitat = None
        self.show_player = show_player
        self._scroll = 0
        if detail_only:
            self.show_detail = True
            self.show_list = False
            self._layout_panel()

    def select_building(
        self, bid: int, *, show_player: bool = False, detail_only: bool = False
    ) -> None:
        self.open_window(MgmtTab.BUILDINGS)
        self.selected_building_id = bid
        self.selected_construction_id = None
        self.selected_villager_id = None
        self.selected_habitat = None
        self.show_player = show_player
        self._scroll = 0
        if detail_only:
            self.show_detail = True
            self.show_list = False
            self._layout_panel()

    def select_construction(self, sid: int, *, detail_only: bool = False) -> None:
        self.open_window(MgmtTab.BUILDINGS)
        self.selected_construction_id = sid
        self.selected_building_id = None
        self.selected_villager_id = None
        self.selected_habitat = None
        self.show_player = False
        self._scroll = 0
        if detail_only:
            self.show_detail = True
            self.show_list = False
            self._layout_panel()

    def select_habitat(self, kind: Any, patch_id: int) -> None:
        self.open_window(MgmtTab.WILDLIFE)
        self.selected_habitat = (kind, patch_id)
        self.selected_building_id = None
        self.selected_construction_id = None
        self.selected_villager_id = None
        self._scroll = 0

    def contains(self, pos: tuple[int, int]) -> bool:
        return self.open and self._panel.collidepoint(pos)

    def detail_rect(self) -> pygame.Rect:
        return self._detail_rect.copy()

    def list_rect(self) -> pygame.Rect:
        return self._list_rect.copy()

    def _people_actions(self) -> bool:
        return self.people_mode in ("hire", "assign")

    def _layout_panel(self) -> None:
        map_w = map_view_width()
        h = min(520, max(360, WINDOW_HEIGHT - MAP_OFFSET_Y - 48))
        list_need = _table_width(actions=self._people_actions()) + 48
        detail_min = 300
        if self.show_detail and self.show_list:
            w = min(map_w - 40, max(560, detail_min + 8 + list_need))
        elif self.show_detail:
            w = min(420, map_w - 40)
        elif self.tab == MgmtTab.PEOPLE:
            w = min(
                map_w - 40,
                max(400, list_need),
            )
        elif self.tab == MgmtTab.BUILDINGS:
            w = min(400, map_w - 40)
        else:
            w = min(360, map_w - 40)

        if self._panel.w > 0:
            cx, cy = self._panel.center
            self._panel.size = (w, h)
            self._panel.center = (cx, cy)
        else:
            self._panel = pygame.Rect(
                (map_w - w) // 2,
                MAP_OFFSET_Y + 24,
                w,
                h,
            )
        self._clamp()

    def handle_keydown(self, event: pygame.event.Event) -> bool:
        if not self.open:
            return False
        if event.key == pygame.K_ESCAPE:
            self.close()
            return True
        return False

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.open:
            return False
        if event.type == pygame.KEYDOWN:
            return self.handle_keydown(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return self.handle_mousedown(event.pos)
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._moving = False
            return False
        if event.type == pygame.MOUSEMOTION and self._moving:
            self._panel.x = event.pos[0] - self._move_offset[0]
            self._panel.y = event.pos[1] - self._move_offset[1]
            self._clamp()
            return True
        if event.type == pygame.MOUSEWHEEL and self.contains(pygame.mouse.get_pos()):
            pos = pygame.mouse.get_pos()
            # Only scroll the list pane — detail/inspect has its own scroll.
            if self._list_rect.w > 0 and self._list_rect.collidepoint(pos):
                step = ROW_H if self.tab == MgmtTab.PEOPLE else LIST_ROW_H
                self._scroll = max(0, self._scroll - event.y * step)
                return True
            # Consume wheel over the rest of the window (don't zoom map).
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
            self._move_offset = (pos[0] - self._panel.x, pos[1] - self._panel.y)
            return True
        for rect, sort_key in self._header_hits:
            if rect.collidepoint(pos):
                if self._roster_sort == sort_key:
                    self._roster_asc = not self._roster_asc
                else:
                    self._roster_sort = sort_key
                    self._roster_asc = True
                return True
        for action, rect in self._buttons:
            if rect.collidepoint(pos):
                if action == "toggle_detail":
                    if self.show_detail and not self.show_list:
                        return True
                    self.show_detail = not self.show_detail
                    self._layout_panel()
                    return True
                if action == "toggle_list":
                    if self.show_list and not self.show_detail:
                        return True
                    self.show_list = not self.show_list
                    self._layout_panel()
                    return True
                self._pending_action = action
                return True
        for rect, kind, item_id in self._list_hits:
            if rect.collidepoint(pos):
                self._pending_action = f"select_{kind}:{item_id}"
                return True
        return True  # consume clicks inside panel

    def _clamp(self) -> None:
        self._panel.x = max(4, min(self._panel.x, WINDOW_WIDTH - self._panel.w - 4))
        self._panel.y = max(
            MAP_OFFSET_Y, min(self._panel.y, WINDOW_HEIGHT - self._panel.h - 4)
        )

    def _draw_btn(
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

    def _icon_btn(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        icon: str,
        tip: str,
        *,
        active: bool,
        mouse: tuple[int, int] | None,
        action: str,
    ) -> None:
        hovered = mouse is not None and rect.collidepoint(mouse)
        bg = (
            COLOUR_TOOLBAR_BTN_ACTIVE
            if active
            else COLOUR_TOOLBAR_BTN_HOVER
            if hovered
            else COLOUR_TOOLBAR_BTN
        )
        pygame.draw.rect(surface, bg, rect, border_radius=4)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, rect, 1, border_radius=4)
        blit_icon(surface, icon, rect.centerx, rect.centery, min(rect.w, rect.h) - 6)
        self._buttons.append((action, rect))
        if hovered:
            self._tooltip = (tip, (rect.centerx, rect.top))

    def _glyph_btn(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        kind: str,
        tip: str,
        *,
        active: bool,
        mouse: tuple[int, int] | None,
        action: str,
    ) -> None:
        hovered = mouse is not None and rect.collidepoint(mouse)
        bg = (
            COLOUR_TOOLBAR_BTN_ACTIVE
            if active
            else COLOUR_TOOLBAR_BTN_HOVER
            if hovered
            else COLOUR_TOOLBAR_BTN
        )
        pygame.draw.rect(surface, bg, rect, border_radius=4)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, rect, 1, border_radius=4)
        if kind == "inspect":
            _draw_inspect_glyph(surface, rect, COLOUR_TEXT)
        else:
            _draw_list_glyph(surface, rect, COLOUR_TEXT)
        self._buttons.append((action, rect))
        if hovered:
            self._tooltip = (tip, (rect.centerx, rect.top))

    def draw(
        self,
        surface: pygame.Surface,
        *,
        villagers: list[Villager],
        buildings: dict[int, Building],
        construction_sites: dict[int, ConstructionSite],
        wildlife_rows: list[tuple[Any, int, str, str]],
        habitat_view: HabitatInspectView | None,
        mouse_pos: tuple[int, int] | None = None,
        hire_entries: list[RosterEntry] | None = None,
        can_hire: Callable[[RosterEntry], bool] | None = None,
        food_amounts: dict[str, int] | None = None,
        draw_villager_detail: Callable[[pygame.Surface, pygame.Rect], None] | None = None,
        draw_building_detail: Callable[[pygame.Surface, pygame.Rect], None] | None = None,
    ) -> None:
        if not self.open:
            return
        self._layout_panel()
        self._buttons = []
        self._list_hits = []
        self._header_hits = []
        self._tooltip = None

        panel = self._panel
        pygame.draw.rect(surface, COLOUR_MENU_BG, panel, border_radius=8)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, panel, 1, border_radius=8)

        # Title
        self._title_rect = pygame.Rect(panel.x, panel.y, panel.w - 36, TITLE_BAR_H)
        title = {
            MgmtTab.PEOPLE: "Management — People",
            MgmtTab.BUILDINGS: "Management — Buildings",
            MgmtTab.WILDLIFE: "Management — Wildlife",
        }[self.tab]
        surface.blit(
            self.font_title.render(title, True, COLOUR_TEXT),
            (panel.x + PAD, panel.y + 8),
        )
        self._close_rect = pygame.Rect(panel.right - 30, panel.y + 4, 24, 24)
        hovered_x = mouse_pos is not None and self._close_rect.collidepoint(mouse_pos)
        self._draw_btn(surface, self._close_rect, "×", hovered=hovered_x)

        # Tabs + pane toggles
        y = panel.y + TITLE_BAR_H
        bx = panel.x + PAD
        for tab in MgmtTab:
            icon, label = _TAB_META[tab]
            rect = pygame.Rect(bx, y, 34, TAB_H - 4)
            self._icon_btn(
                surface,
                rect,
                icon,
                label,
                active=self.tab == tab,
                mouse=mouse_pos,
                action=f"tab_{tab.name.lower()}",
            )
            bx += 40
        bx += 12
        self._glyph_btn(
            surface,
            pygame.Rect(bx, y + 4, 28, PANE_BTN_H),
            "inspect",
            "Toggle detail pane",
            active=self.show_detail,
            mouse=mouse_pos,
            action="toggle_detail",
        )
        bx += 32
        self._glyph_btn(
            surface,
            pygame.Rect(bx, y + 4, 28, PANE_BTN_H),
            "list",
            "Toggle list pane",
            active=self.show_list,
            mouse=mouse_pos,
            action="toggle_list",
        )

        body_top = y + TAB_H
        body = pygame.Rect(
            panel.x + PAD,
            body_top,
            panel.w - 2 * PAD,
            panel.bottom - body_top - PAD,
        )

        if self.show_detail and self.show_list:
            list_need = _table_width(actions=self._people_actions()) + 16
            detail_min = 280
            gap = 8
            if self.tab == MgmtTab.PEOPLE:
                list_w = min(list_need, max(200, body.w - detail_min - gap))
                detail_w = body.w - list_w - gap
            else:
                detail_w = body.w // 2 - 4
                list_w = body.w - detail_w - gap
            self._detail_rect = pygame.Rect(body.x, body.y, detail_w, body.h)
            self._list_rect = pygame.Rect(body.x + detail_w + gap, body.y, list_w, body.h)
        elif self.show_detail:
            self._detail_rect = body.copy()
            self._list_rect = pygame.Rect(0, 0, 0, 0)
        else:
            self._list_rect = body.copy()
            self._detail_rect = pygame.Rect(0, 0, 0, 0)

        if self.show_detail and self._detail_rect.w > 0:
            pygame.draw.rect(
                surface, (38, 40, 46), self._detail_rect, border_radius=6
            )
            pygame.draw.rect(
                surface, COLOUR_TOOLBAR_BORDER, self._detail_rect, 1, border_radius=6
            )
            if self.tab == MgmtTab.PEOPLE and draw_villager_detail is not None:
                draw_villager_detail(surface, self._detail_rect)
            elif self.tab == MgmtTab.BUILDINGS:
                site = (
                    construction_sites.get(self.selected_construction_id)
                    if self.selected_construction_id is not None
                    else None
                )
                if site is not None:
                    self._draw_construction_detail(surface, self._detail_rect, site)
                elif draw_building_detail is not None:
                    draw_building_detail(surface, self._detail_rect)
                else:
                    self._blit_dim(surface, self._detail_rect, "Select a building")
            elif self.tab == MgmtTab.WILDLIFE:
                self._draw_wildlife_detail(surface, self._detail_rect, habitat_view)

        if self.show_list and self._list_rect.w > 0:
            pygame.draw.rect(surface, (38, 40, 46), self._list_rect, border_radius=6)
            pygame.draw.rect(
                surface, COLOUR_TOOLBAR_BORDER, self._list_rect, 1, border_radius=6
            )
            if self.tab == MgmtTab.PEOPLE:
                self._draw_people_list(
                    surface,
                    villagers,
                    buildings=buildings,
                    hire_entries=hire_entries,
                    can_hire=can_hire,
                    food_amounts=food_amounts,
                    mouse_pos=mouse_pos,
                )
            elif self.tab == MgmtTab.BUILDINGS:
                self._draw_buildings_list(
                    surface,
                    buildings,
                    construction_sites,
                    villagers,
                    mouse_pos,
                )
            else:
                self._draw_wildlife_list(surface, wildlife_rows, mouse_pos)

        if self._tooltip is not None:
            tip, (tx, ty) = self._tooltip
            text = self.font_tiny.render(tip, True, COLOUR_TEXT)
            tip_r = text.get_rect()
            tip_r.midbottom = (tx, ty - 4)
            tip_r.x = max(4, min(tip_r.x, WINDOW_WIDTH - tip_r.w - 4))
            bg = tip_r.inflate(8, 4)
            pygame.draw.rect(surface, (30, 32, 38), bg, border_radius=4)
            pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, bg, 1, border_radius=4)
            surface.blit(text, tip_r)

    def _blit_dim(self, surface: pygame.Surface, rect: pygame.Rect, msg: str) -> None:
        t = self.font_small.render(msg, True, COLOUR_TEXT_DIM)
        surface.blit(t, (rect.x + PAD, rect.y + PAD))

    def _draw_construction_detail(
        self, surface: pygame.Surface, rect: pygame.Rect, site: ConstructionSite
    ) -> None:
        x = rect.x + PAD
        y = rect.y + PAD
        icon = _BUILD_ICON.get(site.kind, "construction_site")
        blit_icon(surface, icon, x + 20, y + 20, 40)
        surface.blit(
            self.font_title.render(BUILDING_LABELS[site.kind], True, COLOUR_TEXT),
            (x + 48, y + 4),
        )
        surface.blit(
            self.font_small.render(site.phase_label(), True, COLOUR_TEXT_DIM),
            (x + 48, y + 24),
        )
        y += 52
        surface.blit(self.font.render("Materials", True, COLOUR_TEXT), (x, y))
        y += 20
        for key, have, need in site.material_rows():
            ic = _MAT_ICON.get(key, key)
            blit_icon(surface, ic, x + 11, y + 11, 22)
            label = f"{have}/{need}"
            surface.blit(
                self.font_small.render(label, True, COLOUR_TEXT), (x + 28, y + 4)
            )
            y += 26
        y += 8
        bar = pygame.Rect(x, y, rect.w - 2 * PAD, 12)
        pygame.draw.rect(surface, (40, 40, 45), bar, border_radius=3)
        if site.materials_ready or site.is_deconstruct:
            frac = site.work_progress_frac()
            colour = (80, 180, 100) if not site.is_deconstruct else (200, 140, 70)
            label = "Deconstruct" if site.is_deconstruct else "Build"
        else:
            frac = site.materials_delivered_frac()
            colour = (220, 180, 60)
            label = "Deliver"
        fill = pygame.Rect(bar.x, bar.y, int(bar.w * frac), bar.h)
        pygame.draw.rect(surface, colour, fill, border_radius=3)
        y += 18
        surface.blit(
            self.font_tiny.render(f"{label} {int(frac * 100)}%", True, COLOUR_TEXT_DIM),
            (x, y),
        )

    def _draw_wildlife_detail(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        view: HabitatInspectView | None,
    ) -> None:
        if view is None:
            self._blit_dim(surface, rect, "Select a wildlife ground")
            return
        x = rect.x + PAD
        y = rect.y + PAD
        surface.blit(self.font_title.render(view.title, True, COLOUR_TEXT), (x, y))
        y += 22
        surface.blit(
            self.font_small.render(view.subtitle, True, COLOUR_TEXT_DIM), (x, y)
        )
        y += 20
        for label, value in (
            ("Population", view.population),
            ("Breeding tiles", str(view.breeding_tiles)),
            ("Roam tiles", str(view.roam_tiles)),
            ("Health", f"{view.health_pct:.0f}%"),
            ("Breed chance", f"{view.breed_chance_pct:.0f}%"),
        ):
            surface.blit(
                self.font_small.render(f"{label}: {value}", True, COLOUR_TEXT),
                (x, y),
            )
            y += 18
        y += 6
        for name, val in view.benefits:
            surface.blit(
                self.font_small.render(f"{name}: {val}", True, COLOUR_TEXT_DIM),
                (x, y),
            )
            y += 16

    def _job_for_villager(
        self, v: Villager, buildings: dict[int, Building]
    ) -> str:
        if v.assigned_to_home:
            return "hauler"
        if v.building_id and v.building_id in buildings:
            return BUILDING_LABELS[buildings[v.building_id].kind]
        return "free"

    def _housing_icon_for(self, v: Villager, buildings: dict[int, Building]) -> str:
        if v.housed and v.housing_id is not None:
            building = buildings.get(v.housing_id)
            if building is not None:
                return _BUILD_ICON.get(building.kind, "tent")
        return "tent"

    def _villager_entry(
        self,
        v: Villager,
        buildings: dict[int, Building],
        foods: dict[str, int],
    ) -> RosterEntry:
        return entry_from_villager(
            v,
            job=self._job_for_villager(v, buildings),
            status="EAT" if v.seeking_food else v.state.name.title(),
            job_colour=villager_job_colour(v, buildings),
            requirement_rows=villager_requirement_rows(
                v,
                buildings,
                foods,
                housing_icon=self._housing_icon_for(v, buildings),
            ),
        )

    def _draw_people_list(
        self,
        surface: pygame.Surface,
        villagers: list[Villager],
        *,
        buildings: dict[int, Building],
        hire_entries: list[RosterEntry] | None,
        can_hire: Callable[[RosterEntry], bool] | None,
        food_amounts: dict[str, int] | None,
        mouse_pos: tuple[int, int] | None,
    ) -> None:
        rect = self._list_rect
        x = rect.x + 6
        y = rect.y + 6
        show_actions = self._people_actions()
        foods = dict(food_amounts or {})

        if self.people_mode == "hire":
            entries = list(hire_entries or [])
            beds = free_housing_beds(buildings, villagers)
            lvl = max_housing_level(buildings)
            for e in entries:
                if e.requirement_rows:
                    continue
                e.requirement_rows = candidate_requirement_rows(
                    housing_need=e.housing_need,
                    required_foods=list(e.required_foods),
                    foods=foods,
                    free_beds=beds,
                    max_housing_level=lvl,
                )
            surface.blit(
                self.font_small.render("Travellers", True, COLOUR_TEXT), (x, y)
            )
        elif self.people_mode == "assign":
            entries = [self._villager_entry(v, buildings, foods) for v in villagers]
            surface.blit(
                self.font_small.render("Pick villager", True, COLOUR_TEXT), (x, y)
            )
        else:
            entries = [self._villager_entry(v, buildings, foods) for v in villagers]
            surface.blit(
                self.font_small.render("Villagers", True, COLOUR_TEXT), (x, y)
            )
        y += HEADER_H

        entries = sort_entries(
            entries, self._roster_sort, reverse=not self._roster_asc
        )
        cols = _column_layout(x, actions=show_actions)

        header_defs: list[tuple[RosterSort, str, int]] = [
            (RosterSort.NAME, "name", COL_NAME_W),
            (RosterSort.ENERGY, "energy", COL_BAR_W),
            (RosterSort.SATIATION, "satiation", COL_BAR_W),
            (RosterSort.HAPPINESS, "happiness", COL_BAR_W),
            (RosterSort.HOUSING, "house", COL_HOUSE_W),
            (RosterSort.PAY, "pay", COL_PAY_W),
            (RosterSort.EXTRACTION, "extraction", SKILL_COL_W),
            (RosterSort.FARMING, "farming", SKILL_COL_W),
            (RosterSort.HUNTING, "hunting", SKILL_COL_W),
            (RosterSort.CRAFTING, "crafting", SKILL_COL_W),
            (RosterSort.LABOUR, "labour", SKILL_COL_W),
            (RosterSort.TRANSPORT, "transport", SKILL_COL_W),
        ]
        for sort_key, col_key, w in header_defs:
            hx = cols[col_key]
            label = SORT_LABELS[sort_key]
            if self._roster_sort == sort_key:
                label = ("▼" if not self._roster_asc else "▲") + label
            hrect = pygame.Rect(hx, y, w, HEADER_H)
            colour = COLOUR_TEXT if self._roster_sort == sort_key else COLOUR_TEXT_DIM
            surface.blit(self.font_tiny.render(label, True, colour), (hx + 2, y + 4))
            self._header_hits.append((hrect, sort_key))
        if show_actions:
            surface.blit(
                self.font_tiny.render("Act", True, COLOUR_TEXT_DIM),
                (cols["actions"] + 2, y + 4),
            )
        y += HEADER_H + 4

        view = pygame.Rect(rect.x + 2, y, rect.w - 4, rect.bottom - y - 4)
        content_h = max(ROW_H, len(entries) * ROW_H)
        max_scroll = max(0, content_h - view.h)
        self._scroll = min(self._scroll, max_scroll)
        old = surface.get_clip()
        surface.set_clip(view)

        for i, entry in enumerate(entries):
            row_y = view.y + i * ROW_H - self._scroll
            row = pygame.Rect(view.x + 2, row_y, view.w - 8, ROW_H - 4)
            if not row.colliderect(view):
                continue
            selected = (
                self.people_mode != "hire" and self.selected_villager_id == entry.id
            )
            hovered = mouse_pos is not None and row.collidepoint(mouse_pos)
            if selected:
                pygame.draw.rect(surface, (55, 70, 55), row, border_radius=4)
                pygame.draw.rect(
                    surface, COLOUR_SELECTED_ENTITY, row, 1, border_radius=4
                )
            elif hovered:
                pygame.draw.rect(surface, (55, 58, 66), row, border_radius=4)
                pygame.draw.rect(surface, (60, 62, 70), row, 1, border_radius=4)
            else:
                pygame.draw.rect(surface, (60, 62, 70), row, 1, border_radius=4)

            draw_portrait(
                surface,
                cols["portrait"] + PORTRAIT_SIZE // 2,
                row_y + ROW_H // 2 - 2,
                entry.portrait_seed,
                job_colour=entry.job_colour,
            )

            name_x = cols["name"]
            name_max_w = COL_NAME_W - 6
            name = entry.name
            while self.font.size(name)[0] > name_max_w and len(name) > 3:
                name = name[:-2] + "…"
            surface.blit(self.font.render(name, True, COLOUR_TEXT), (name_x, row_y + 6))

            req = "/".join(entry.required_foods) or "—"
            meta_parts: list[str] = []
            if entry.job:
                meta_parts.append(entry.job)
            if entry.status:
                meta_parts.append(entry.status)
            meta = " · ".join(meta_parts) if meta_parts else "—"
            while self.font_tiny.size(meta)[0] > name_max_w and len(meta) > 4:
                meta = meta[:-2] + "…"
            surface.blit(
                self.font_tiny.render(meta, True, COLOUR_TEXT_DIM),
                (name_x, row_y + 24),
            )

            traits: list[str] = []
            if entry.virtues:
                traits.append("+" + ",".join(entry.virtues[:2]))
            if entry.vices:
                traits.append("-" + ",".join(entry.vices[:2]))
            if traits:
                tline = " ".join(traits)
                while self.font_tiny.size(tline)[0] > name_max_w and len(tline) > 4:
                    tline = tline[:-2] + "…"
                surface.blit(
                    self.font_tiny.render(tline, True, COLOUR_TEXT_DIM),
                    (name_x, row_y + 40),
                )

            bar_y = row_y + (ROW_H // 2) - 4
            draw_status_bar(
                surface,
                cols["energy"] + 4,
                bar_y,
                COL_BAR_W - 8,
                8,
                entry.energy,
                kind="energy",
            )
            draw_status_bar(
                surface,
                cols["satiation"] + 4,
                bar_y,
                COL_BAR_W - 8,
                8,
                entry.satiation,
                kind="sat",
            )
            draw_status_bar(
                surface,
                cols["happiness"] + 4,
                bar_y,
                COL_BAR_W - 8,
                8,
                entry.happiness,
                kind="happy",
            )

            if entry.requirement_rows:
                draw_requirement_icons(
                    surface,
                    cols["house"] + 2,
                    row_y + (ROW_H - REQ_ICON) // 2,
                    entry.requirement_rows,
                )
            else:
                house_txt = "bed" if entry.housed else f"≥{entry.housing_need}"
                ht = self.font_tiny.render(house_txt, True, COLOUR_TEXT_DIM)
                surface.blit(
                    ht,
                    (
                        cols["house"] + (COL_HOUSE_W - ht.get_width()) // 2,
                        row_y + (ROW_H - ht.get_height()) // 2,
                    ),
                )

            if entry.season_pay > 0:
                pay_txt = f"{entry.season_pay}/s"
            elif entry.coins_paid > 0:
                pay_txt = f"{entry.coins_paid}"
            else:
                pay_txt = "—"
            pt = self.font_tiny.render(pay_txt, True, COLOUR_TEXT_DIM)
            surface.blit(
                pt,
                (
                    cols["pay"] + (COL_PAY_W - pt.get_width()) // 2,
                    row_y + 18,
                ),
            )
            if entry.kind == "villager" and entry.coins_paid > 0 and entry.season_pay > 0:
                paid = self.font_tiny.render(
                    f"{entry.coins_paid} tot", True, COLOUR_TEXT_DIM
                )
                surface.blit(
                    paid,
                    (
                        cols["pay"] + (COL_PAY_W - paid.get_width()) // 2,
                        row_y + 34,
                    ),
                )

            skill_y = row_y + 12
            for sk in SKILL_ORDER:
                st = entry.skills.get(sk)
                lvl = int(getattr(st, "level", 1) or 1)
                draw_skill_cell(
                    surface,
                    cols[sk.name.lower()],
                    skill_y,
                    sk,
                    lvl,
                    self.font_tiny,
                    icon_size=14,
                )

            if self.people_mode == "hire":
                ax = cols["actions"]
                hire_r = pygame.Rect(ax, row_y + 18, 44, 24)
                pay_r = pygame.Rect(ax + 48, row_y + 18, 40, 24)
                ok = can_hire(entry) if can_hire else True
                self._draw_btn(
                    surface,
                    hire_r,
                    "Hire",
                    active=ok,
                    hovered=mouse_pos is not None and hire_r.collidepoint(mouse_pos),
                )
                self._draw_btn(
                    surface,
                    pay_r,
                    "Pay",
                    hovered=mouse_pos is not None and pay_r.collidepoint(mouse_pos),
                )
                if ok:
                    self._buttons.append((f"hire_cand:{entry.id}", hire_r))
                self._buttons.append((f"pay_cand:{entry.id}", pay_r))
            elif self.people_mode == "assign":
                pick_r = pygame.Rect(cols["actions"] + 8, row_y + 18, 56, 24)
                self._draw_btn(
                    surface,
                    pick_r,
                    "Pick",
                    hovered=mouse_pos is not None and pick_r.collidepoint(mouse_pos),
                )
                self._buttons.append((f"assign_pick:{entry.id}", pick_r))
                self._list_hits.append((row, "villager", entry.id))
            else:
                self._list_hits.append((row, "villager", entry.id))

        surface.set_clip(old)

    def _draw_buildings_list(
        self,
        surface: pygame.Surface,
        buildings: dict[int, Building],
        sites: dict[int, ConstructionSite],
        villagers: list[Villager],
        mouse_pos: tuple[int, int] | None,
    ) -> None:
        del mouse_pos
        rect = self._list_rect
        y = rect.y + 6 - self._scroll
        view = pygame.Rect(rect.x + 2, rect.y + 2, rect.w - 4, rect.h - 4)
        old = surface.get_clip()
        surface.set_clip(view)

        for site in sites.values():
            row = pygame.Rect(view.x + 2, y, view.w - 8, LIST_ROW_H)
            selected = self.selected_construction_id == site.id
            if selected:
                pygame.draw.rect(surface, (55, 70, 55), row, border_radius=3)
                pygame.draw.rect(
                    surface, COLOUR_SELECTED_ENTITY, row, 1, border_radius=3
                )
            icon = _BUILD_ICON.get(site.kind, "construction_site")
            blit_icon(surface, icon, row.x + 18, row.centery, 28)
            label = f"{BUILDING_LABELS[site.kind]} (site)"
            surface.blit(
                self.font_small.render(label, True, COLOUR_TEXT),
                (row.x + 36, row.y + 4),
            )
            pct = int(
                (
                    site.work_progress_frac()
                    if site.materials_ready
                    else site.materials_delivered_frac()
                )
                * 100
            )
            surface.blit(
                self.font_tiny.render(
                    f"{site.phase_label()} {pct}%", True, COLOUR_TEXT_DIM
                ),
                (row.x + 36, row.y + 20),
            )
            self._list_hits.append((row, "construction", site.id))
            y += LIST_ROW_H + 2

        for b in buildings.values():
            if b.kind == BuildingKind.FIELD:
                continue
            row = pygame.Rect(view.x + 2, y, view.w - 8, LIST_ROW_H)
            selected = self.selected_building_id == b.id
            if selected:
                pygame.draw.rect(surface, (55, 70, 55), row, border_radius=3)
                pygame.draw.rect(
                    surface, COLOUR_SELECTED_ENTITY, row, 1, border_radius=3
                )
            icon = _BUILD_ICON.get(b.kind, "construction_site")
            blit_icon(surface, icon, row.x + 18, row.centery, 28)
            surface.blit(
                self.font_small.render(
                    f"{BUILDING_LABELS[b.kind]} #{b.id}", True, COLOUR_TEXT
                ),
                (row.x + 36, row.y + 10),
            )
            if b.kind == BuildingKind.HOME:
                workers = [v for v in villagers if v.assigned_to_home]
            elif is_housing_kind(b.kind):
                workers = [
                    v for v in villagers if v.housed and v.housing_id == b.id
                ]
            else:
                workers = [v for v in villagers if v.building_id == b.id]
            if workers:
                px = row.right - 8
                for v in reversed(workers[:6]):
                    px -= 16
                    draw_portrait(
                        surface,
                        px,
                        row.centery,
                        v.portrait_seed,
                        size=14,
                        job_colour=villager_job_colour(v, buildings),
                    )
            self._list_hits.append((row, "building", b.id))
            y += LIST_ROW_H + 2
        surface.set_clip(old)

    def _draw_wildlife_list(
        self,
        surface: pygame.Surface,
        rows: list[tuple[Any, int, str, str]],
        mouse_pos: tuple[int, int] | None,
    ) -> None:
        del mouse_pos
        rect = self._list_rect
        y = rect.y + 6 - self._scroll
        view = pygame.Rect(rect.x + 2, rect.y + 2, rect.w - 4, rect.h - 4)
        old = surface.get_clip()
        surface.set_clip(view)
        icon_for = {
            "DEER": "deer_male",
            "BOAR": "boar_male",
            "BEE": "bee_hive",
            "RABBIT": "burrow",
        }
        for kind, patch_id, title, subtitle in rows:
            row = pygame.Rect(view.x + 2, y, view.w - 8, LIST_ROW_H)
            selected = self.selected_habitat == (kind, patch_id)
            if selected:
                pygame.draw.rect(surface, (55, 70, 55), row, border_radius=3)
                pygame.draw.rect(
                    surface, COLOUR_SELECTED_ENTITY, row, 1, border_radius=3
                )
            name = kind.name if hasattr(kind, "name") else str(kind)
            blit_icon(
                surface, icon_for.get(name, "deer_male"), row.x + 18, row.centery, 28
            )
            surface.blit(
                self.font_small.render(title, True, COLOUR_TEXT),
                (row.x + 36, row.y + 4),
            )
            surface.blit(
                self.font_tiny.render(subtitle, True, COLOUR_TEXT_DIM),
                (row.x + 36, row.y + 20),
            )
            self._list_hits.append((row, "habitat", f"{name}:{patch_id}"))
            y += LIST_ROW_H + 2
        surface.set_clip(old)
