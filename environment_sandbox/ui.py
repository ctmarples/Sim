"""UI panel, legends, and text helpers (scrollable side panel)."""

from __future__ import annotations

import pygame

from crops import CROP_BY_KEY, PHASE_LABELS, phase_for_crop
from entities import (
    BUILDING_LABELS,
    PRIORITY_LABELS,
    RATION_LABELS,
    TASK_LABELS,
    WORK_MODE_LABELS,
    WORK_MODE_SHORT,
    Building,
    BuildingKind,
    ConstructionSite,
    HomeStorage,
    Player,
    RationMode,
    Villager,
    WorkPriority,
)
from indicators import OVERLAY_LABELS, OverlayMode
from seasons import Season, adjust_colour, blend_colour, format_date
from settings import (
    CELL_SIZE,
    COLOUR_ANIMAL,
    COLOUR_BERRY,
    COLOUR_BOAR,
    COLOUR_CROP,
    COLOUR_DEER,
    COLOUR_FARM,
    COLOUR_FIELD,
    COLOUR_FISH,
    COLOUR_FISHER,
    COLOUR_FORAGER,
    COLOUR_FORESTER,
    COLOUR_GRASS,
    COLOUR_HERB,
    COLOUR_HOME,
    COLOUR_HUNTER,
    COLOUR_ICE,
    COLOUR_MASON,
    COLOUR_MEADOW,
    COLOUR_MEAT,
    COLOUR_MENU_BG,
    COLOUR_MUSHROOM,
    COLOUR_PANEL_BG,
    COLOUR_PANEL_BORDER,
    COLOUR_PLAYER,
    COLOUR_REED,
    COLOUR_RIPARIAN,
    COLOUR_ROCK_FEATURE,
    COLOUR_ROCK_TERRAIN,
    COLOUR_ROCK_TERRAIN_DARK,
    COLOUR_SAPLING,
    COLOUR_SELECTED_ENTITY,
    COLOUR_SOIL,
    COLOUR_STATUS,
    COLOUR_TEXT,
    COLOUR_TEXT_DIM,
    COLOUR_TOOLBAR_BTN,
    COLOUR_TOOLBAR_BTN_ACTIVE,
    COLOUR_TOOLBAR_BORDER,
    COLOUR_TREE_CANOPY,
    COLOUR_VILLAGER,
    COLOUR_WATER,
    COLOUR_WORKSTATION,
    MAP_OFFSET_Y,
    MAX_VILLAGERS,
    PANEL_WIDTH,
    TERRAIN_SUBDIV,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    map_view_width,
)
from wildlife import AnimalKind, FishManager, WildlifeManager
from world import FeatureType, TerrainType, World


def _panel_height() -> int:
    return WINDOW_HEIGHT - MAP_OFFSET_Y


def _blit_text(
    surface: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    pos: tuple[int, int],
    colour: tuple[int, int, int] = COLOUR_TEXT,
) -> int:
    rendered = font.render(text, True, colour)
    surface.blit(rendered, pos)
    return pos[1] + rendered.get_height() + 4


class UI:
    _ICON_SIZE = 16

    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 13)
        self.font_small = pygame.font.SysFont("menlo", 12)
        self.font_title = pygame.font.SysFont("menlo", 15, bold=True)
        self.font_icon = pygame.font.SysFont("menlo", 11, bold=True)
        self.scroll_y = 0
        self.content_height = _panel_height()
        self._content = pygame.Surface((PANEL_WIDTH, _panel_height()))
        self._content.fill(COLOUR_PANEL_BG)
        self.priority_hits: list[tuple[pygame.Rect, int, int]] = []
        self.list_hits: list[tuple[pygame.Rect, str, int]] = []
        # (rect, action_id, tooltip)
        self.action_hits: list[tuple[pygame.Rect, str, str]] = []
        self._tooltip: tuple[str, tuple[int, int]] | None = None

    def _local_pos(self, pos: tuple[int, int]) -> tuple[int, int]:
        panel_x = map_view_width()
        return pos[0] - panel_x, pos[1] - MAP_OFFSET_Y + self.scroll_y

    def hit_priority(self, pos: tuple[int, int]) -> tuple[int, int] | None:
        local = self._local_pos(pos)
        for rect, vid, slot in self.priority_hits:
            if rect.collidepoint(local):
                return vid, slot
        return None

    def hit_action(self, pos: tuple[int, int]) -> str | None:
        local = self._local_pos(pos)
        for rect, action, _tip in self.action_hits:
            if rect.collidepoint(local):
                return action
        return None

    def hit_list(self, pos: tuple[int, int]) -> tuple[str, int] | None:
        local = self._local_pos(pos)
        # Prefer action / priority hits so clicks on buttons don't reselect the row.
        if self.hit_action(pos) is not None or self.hit_priority(pos) is not None:
            return None
        for rect, kind, item_id in self.list_hits:
            if rect.collidepoint(local):
                return kind, item_id
        return None

    def scroll(self, delta: int) -> None:
        max_scroll = max(0, self.content_height - _panel_height())
        self.scroll_y = max(0, min(max_scroll, self.scroll_y - delta))

    def _ensure_content_surface(self, height: int) -> pygame.Surface:
        height = max(_panel_height(), height)
        if self._content.get_height() < height:
            self._content = pygame.Surface((PANEL_WIDTH, height))
        return self._content

    def _draw_icon_button(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        glyph: str,
        *,
        active: bool = False,
        hovered: bool = False,
    ) -> None:
        if active:
            colour = COLOUR_TOOLBAR_BTN_ACTIVE
        elif hovered:
            colour = (70, 78, 92)
        else:
            colour = COLOUR_TOOLBAR_BTN
        pygame.draw.rect(surface, colour, rect, border_radius=3)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, rect, 1, border_radius=3)
        text = self.font_icon.render(glyph, True, COLOUR_TEXT)
        surface.blit(
            text,
            (
                rect.x + (rect.w - text.get_width()) // 2,
                rect.y + (rect.h - text.get_height()) // 2,
            ),
        )

    def _draw_list_row(
        self,
        surface: pygame.Surface,
        text: str,
        x: int,
        y: int,
        *,
        selected: bool,
        hit_kind: str,
        hit_id: int,
        trailing_btns: list[tuple[str, str, str, bool]] | None = None,
        local_mouse: tuple[int, int] | None = None,
    ) -> int:
        """Draw one list row. trailing_btns: (glyph, action_id, tooltip, active)."""
        row_h = 20
        row = pygame.Rect(x - 4, y - 1, PANEL_WIDTH - 20, row_h)
        if selected:
            pygame.draw.rect(surface, (55, 70, 55), row, border_radius=3)
            pygame.draw.rect(surface, COLOUR_SELECTED_ENTITY, row, 1, border_radius=3)

        btns = trailing_btns or []
        btn_space = len(btns) * (self._ICON_SIZE + 3) + (4 if btns else 0)
        max_text_w = PANEL_WIDTH - 28 - btn_space
        label = text
        while self.font_small.size(label)[0] > max_text_w and len(label) > 4:
            label = label[:-2] + "…"

        colour = COLOUR_TEXT if selected else COLOUR_TEXT_DIM
        surface.blit(self.font_small.render(label, True, colour), (x, y + 2))
        self.list_hits.append((row, hit_kind, hit_id))

        bx = row.right - 4 - self._ICON_SIZE
        for glyph, action, tip, active in reversed(btns):
            rect = pygame.Rect(bx, y + (row_h - self._ICON_SIZE) // 2, self._ICON_SIZE, self._ICON_SIZE)
            hovered = local_mouse is not None and rect.collidepoint(local_mouse)
            self._draw_icon_button(surface, rect, glyph, active=active, hovered=hovered)
            self.action_hits.append((rect, action, tip))
            if hovered:
                self._tooltip = (tip, (rect.centerx, rect.top))
            bx -= self._ICON_SIZE + 3

        return y + row_h + 2

    def _inline_priority_buttons(
        self,
        villager: Villager,
        assign_workplace_mode: bool,
    ) -> list[tuple[str, str, str, bool]]:
        while len(villager.priorities) < 3:
            villager.priorities.append(WorkPriority.NONE)
        glyphs = {
            WorkPriority.BUILD: "B",
            WorkPriority.TRANSPORT: "T",
            WorkPriority.WORKPLACE: "W",
            WorkPriority.NONE: "·",
        }
        btns: list[tuple[str, str, str, bool]] = []
        for slot in range(3):
            mode = villager.priorities[slot]
            tip = f"Priority {slot + 1}: {PRIORITY_LABELS[mode]} (click to cycle)"
            btns.append((glyphs[mode], f"prio:{villager.id}:{slot}", tip, False))
        btns.append(
            (
                "→",
                "assign_workplace",
                "Assign to workplace — then pick building or home",
                assign_workplace_mode,
            )
        )
        btns.append(("H", "assign_home", "Assign as home hauler", False))
        return btns

    def _hunger_bar_colour(self, satiation: float) -> tuple[int, int, int]:
        s = max(0.0, min(1.0, satiation))
        if s >= 0.6:
            return (80, 170, 90)
        if s >= 0.3:
            return (200, 160, 50)
        return (190, 70, 60)

    def _draw_hunger_bar(
        self,
        surface: pygame.Surface,
        x: int,
        y: int,
        w: int,
        h: int,
        satiation: float,
    ) -> None:
        pygame.draw.rect(surface, (40, 42, 48), pygame.Rect(x, y, w, h), border_radius=2)
        fill_w = max(0, int(w * max(0.0, min(1.0, satiation))))
        if fill_w > 0:
            pygame.draw.rect(
                surface,
                self._hunger_bar_colour(satiation),
                pygame.Rect(x, y, fill_w, h),
                border_radius=2,
            )
        pygame.draw.rect(surface, (70, 72, 80), pygame.Rect(x, y, w, h), 1, border_radius=2)

    def _draw_villager_row(
        self,
        surface: pygame.Surface,
        villager: Villager,
        label: str,
        x: int,
        y: int,
        *,
        selected: bool,
        assign_workplace_mode: bool,
        local_mouse: tuple[int, int] | None,
    ) -> int:
        row_h = 22
        row = pygame.Rect(x - 4, y - 1, PANEL_WIDTH - 20, row_h)
        if selected:
            pygame.draw.rect(surface, (55, 70, 55), row, border_radius=3)
            pygame.draw.rect(surface, COLOUR_SELECTED_ENTITY, row, 1, border_radius=3)

        ration_label = RATION_LABELS[villager.ration_mode]
        trailing: list[tuple[str, str, str, bool]] = [
            (
                ration_label,
                f"ration:{villager.id}",
                f"Rations {ration_label} (click: ½ / ×1 / ×2)",
                False,
            )
        ]
        if selected:
            trailing = self._inline_priority_buttons(villager, assign_workplace_mode) + trailing

        # Ration button is wider for "×1" / "½".
        btn_space = 0
        for glyph, _a, _t, _act in trailing:
            btn_w = max(self._ICON_SIZE, 8 + self.font_small.size(glyph)[0])
            btn_space += btn_w + 3
        btn_space += 4
        bar_w = 36
        gap = 6
        max_text_w = PANEL_WIDTH - 28 - btn_space - bar_w - gap
        text = label
        while self.font_small.size(text)[0] > max_text_w and len(text) > 4:
            text = text[:-2] + "…"

        colour = COLOUR_TEXT if selected else COLOUR_TEXT_DIM
        surface.blit(self.font_small.render(text, True, colour), (x, y + 3))
        self.list_hits.append((row, "villager", villager.id))

        text_w = self.font_small.size(text)[0]
        bar_x = x + text_w + 6
        bar_y = y + (row_h - 7) // 2
        self._draw_hunger_bar(surface, bar_x, bar_y, bar_w, 7, villager.satiation)
        tip = f"Hunger {int(villager.satiation * 100)}%"
        bar_rect = pygame.Rect(bar_x, bar_y, bar_w, 7)
        if local_mouse is not None and bar_rect.collidepoint(local_mouse):
            self._tooltip = (tip, (bar_rect.centerx, bar_rect.top))

        bx = row.right - 4
        for glyph, action, tip, active in reversed(trailing):
            btn_w = max(self._ICON_SIZE, 8 + self.font_small.size(glyph)[0])
            bx -= btn_w
            rect = pygame.Rect(bx, y + (row_h - self._ICON_SIZE) // 2, btn_w, self._ICON_SIZE)
            hovered = local_mouse is not None and rect.collidepoint(local_mouse)
            self._draw_icon_button(surface, rect, glyph, active=active, hovered=hovered)
            self.action_hits.append((rect, action, tip))
            if hovered:
                self._tooltip = (tip, (rect.centerx, rect.top))
            bx -= 3

        return y + row_h + 2

    def draw_panel(
        self,
        surface: pygame.Surface,
        world: World,
        player: Player,
        home_storage: HomeStorage,
        villagers: list[Villager],
        buildings: dict[int, Building],
        wildlife: WildlifeManager,
        selected_building_id: int | None,
        selected_villager_id: int | None,
        place_kind: BuildingKind | None,
        overlay_mode: OverlayMode,
        status_message: str,
        sim_speed: int = 1,
        fish_manager: FishManager | None = None,
        construction_sites: dict[int, ConstructionSite] | None = None,
        assign_workplace_mode: bool = False,
        mouse_pos: tuple[int, int] | None = None,
        season: Season = Season.SPRING,
        calendar_day: int = 0,
        selected_field_id: int | None = None,
        selected_habitat_kind: AnimalKind | None = None,
        selected_habitat_id: int | None = None,
    ) -> None:
        panel_x = map_view_width()
        panel_h = _panel_height()
        self.priority_hits = []
        self.list_hits = []
        self.action_hits = []
        self._tooltip = None
        content = self._ensure_content_surface(max(self.content_height, panel_h + 200))
        content.fill(COLOUR_PANEL_BG)

        local_mouse: tuple[int, int] | None = None
        if mouse_pos is not None:
            local_mouse = self._local_pos(mouse_pos)

        x = 10
        y = 8

        y = _blit_text(content, self.font_title, "Environment Sandbox", (x, y))
        y = _blit_text(content, self.font_small, "WASD · Enter/E · toolbar build", (x, y), COLOUR_TEXT_DIM)
        y = _blit_text(content, self.font_small, f"Speed x{sim_speed}" if sim_speed else "Paused", (x, y), COLOUR_TEXT_DIM)
        y = _blit_text(
            content,
            self.font_small,
            format_date(calendar_day),
            (x, y),
            COLOUR_STATUS,
        )
        y += 6

        # Buildings / sites
        y = _blit_text(content, self.font_title, "Buildings", (x, y))
        if not buildings and not construction_sites:
            y = _blit_text(content, self.font_small, "None yet", (x, y), COLOUR_TEXT_DIM)
        else:
            if construction_sites:
                for site in construction_sites.values():
                    y = _blit_text(
                        content,
                        self.font_small,
                        f"Site {BUILDING_LABELS[site.kind]} "
                        f"{site.have_wood}/{site.need_wood}w "
                        f"{site.have_rock}/{site.need_rock}r",
                        (x, y),
                        COLOUR_TEXT_DIM,
                    )
            for b in buildings.values():
                selected = selected_building_id == b.id
                trailing = None
                
                # Special handling for HOME
                if b.kind == BuildingKind.HOME:
                    haulers = sum(1 for v in villagers if v.assigned_to_home)
                    label = f"{BUILDING_LABELS[b.kind]} #{b.id}  {haulers} hauler(s)"
                    if selected:
                        trailing = [
                            (
                                "+",
                                "assign_villager",
                                "Assign an unassigned villager as hauler",
                                False,
                            ),
                            (
                                "-",
                                "unassign_villager",
                                "Unassign a hauler",
                                False,
                            ),
                        ]
                # Special handling for WORKSTATION
                elif b.kind == BuildingKind.WORKSTATION:
                    hired_count = len(villagers)
                    label = f"{BUILDING_LABELS[b.kind]} #{b.id}  {hired_count}/{MAX_VILLAGERS} hired"
                    if selected:
                        trailing = [
                            (
                                "Hire",
                                "hire_villager",
                                "Hire a new villager",
                                False,
                            ),
                        ]
                # Regular buildings
                elif b.kind == BuildingKind.FIELD:
                    plans_n = len(b.plans)
                    plans_txt = f"{plans_n} plan" if plans_n == 1 else f"{plans_n} plans"
                    label = (
                        f"{BUILDING_LABELS[b.kind]} #{b.id}  "
                        f"{b.plot_size_label()} · {plans_txt}"
                    )
                    if selected:
                        trailing = [
                            (
                                "Plan",
                                "open_field_plan",
                                "Open crop plan editor",
                                False,
                            ),
                        ]
                else:
                    workers = sum(1 for v in villagers if v.building_id == b.id)
                    label = (
                        f"{BUILDING_LABELS[b.kind]} #{b.id}  "
                        f"{b.stored_total}/{b.capacity} · {workers}w · "
                        f"{WORK_MODE_SHORT[b.work_mode]}"
                    )
                    if selected:
                        mode = b.work_mode
                        mode_tip = (
                            f"Behaviour: {WORK_MODE_LABELS[mode]}"
                            + (
                                " (click to cycle Collect / Plant / Both)"
                                if b.allows_planting()
                                else " (collect only)"
                            )
                        )
                        trailing = [
                            (
                                WORK_MODE_SHORT[mode],
                                "cycle_work_mode",
                                mode_tip,
                                False,
                            ),
                            (
                                "+",
                                "assign_villager",
                                "Assign an unassigned villager here",
                                False,
                            ),
                            (
                                "-",
                                "unassign_villager",
                                "Unassign a worker from this building",
                                False,
                            ),
                        ]
                
                y = self._draw_list_row(
                    content,
                    label,
                    x,
                    y,
                    selected=selected,
                    hit_kind="building",
                    hit_id=b.id,
                    trailing_btns=trailing,
                    local_mouse=local_mouse,
                )
                if selected and b.kind == BuildingKind.FIELD and b.plans:
                    for plan in b.plans:
                        crop = CROP_BY_KEY.get(plan.crop_kind, CROP_BY_KEY["sage"])
                        phase = phase_for_crop(crop, season)
                        pl, pt, pr, pb = plan.normalised()
                        y = _blit_text(
                            content,
                            self.font_small,
                            f"  {crop.label} {pr - pl + 1}×{pb - pt + 1}: "
                            f"{PHASE_LABELS[phase]}",
                            (x, y),
                            COLOUR_STATUS if selected else COLOUR_TEXT_DIM,
                        )
        y += 4

        # Villagers
        y = _blit_text(content, self.font_title, "Villagers", (x, y))
        y = _blit_text(
            content,
            self.font_small,
            f"Hired {len(villagers)}/{MAX_VILLAGERS}",
            (x, y),
            COLOUR_TEXT_DIM,
        )
        for v in villagers:
            if v.assigned_to_home:
                job = "home"
            elif v.building_id and v.building_id in buildings:
                job = BUILDING_LABELS[buildings[v.building_id].kind][:4]
            else:
                job = "free"
            selected = selected_villager_id == v.id
            state = "EAT" if v.seeking_food else v.state.name[:4]
            y = self._draw_villager_row(
                content,
                v,
                f"#{v.id} {state} → {job}",
                x,
                y,
                selected=selected,
                assign_workplace_mode=assign_workplace_mode,
                local_mouse=local_mouse,
            )
        y += 4

        y = _blit_text(content, self.font_title, "World", (x, y))
        wild_line = (
            f"Deer {len(wildlife.deer())}  Boar {len(wildlife.boars())}"
        )
        if fish_manager is not None:
            wild_line += (
                f" · Fish {len(fish_manager.fish)}/"
                f"{fish_manager.total_capacity(world)}"
            )
        y = _blit_text(content, self.font_small, wild_line, (x, y), COLOUR_TEXT_DIM)

        y = _blit_text(content, self.font_small, "Deer grounds", (x, y), COLOUR_TEXT_DIM)
        deer_grounds = wildlife.breeding_grounds(AnimalKind.DEER)
        if not deer_grounds:
            y = _blit_text(content, self.font_small, "  none", (x, y), COLOUR_TEXT_DIM)
        else:
            for hab in deer_grounds:
                _present, migrating, total, pairs = wildlife.patch_occupancy(
                    AnimalKind.DEER, hab.id
                )
                selected = (
                    selected_habitat_kind == AnimalKind.DEER
                    and selected_habitat_id == hab.id
                )
                pair_txt = f"{pairs} pair" if pairs == 1 else f"{pairs} pairs"
                if migrating:
                    label = (
                        f"  #{hab.id}  {total}/{hab.deer_cap}  "
                        f"{pair_txt}  {migrating} migrating"
                    )
                else:
                    label = f"  #{hab.id}  {total}/{hab.deer_cap}  {pair_txt}"
                y = self._draw_list_row(
                    content,
                    label,
                    x,
                    y,
                    selected=selected,
                    hit_kind="deer_ground",
                    hit_id=hab.id,
                )

        y = _blit_text(content, self.font_small, "Boar grounds", (x, y), COLOUR_TEXT_DIM)
        boar_grounds = wildlife.breeding_grounds(AnimalKind.BOAR)
        if not boar_grounds:
            y = _blit_text(content, self.font_small, "  none", (x, y), COLOUR_TEXT_DIM)
        else:
            for hab in boar_grounds:
                _present, migrating, total, pairs = wildlife.patch_occupancy(
                    AnimalKind.BOAR, hab.id
                )
                selected = (
                    selected_habitat_kind == AnimalKind.BOAR
                    and selected_habitat_id == hab.id
                )
                pair_txt = f"{pairs} pair" if pairs == 1 else f"{pairs} pairs"
                if migrating:
                    label = (
                        f"  #{hab.id}  {total}/{hab.boar_cap}  "
                        f"{pair_txt}  {migrating} migrating"
                    )
                else:
                    label = f"  #{hab.id}  {total}/{hab.boar_cap}  {pair_txt}"
                y = self._draw_list_row(
                    content,
                    label,
                    x,
                    y,
                    selected=selected,
                    hit_kind="boar_ground",
                    hit_id=hab.id,
                )

        y = _blit_text(
            content,
            self.font_small,
            f"Overlay: {OVERLAY_LABELS[overlay_mode]}",
            (x, y),
            COLOUR_TEXT_DIM,
        )
        y += 4

        y = _blit_text(content, self.font_title, "Status", (x, y))
        msg = status_message if status_message else "—"
        colour = COLOUR_STATUS if status_message else COLOUR_TEXT_DIM
        for line in _wrap(msg, 30):
            y = _blit_text(content, self.font_small, line, (x, y), colour)
        y += 8

        y = self._draw_legend(content, x, y)
        y += 12

        if y > content.get_height():
            self._content = pygame.Surface((PANEL_WIDTH, y + 64))
            return self.draw_panel(
                surface,
                world,
                player,
                home_storage,
                villagers,
                buildings,
                wildlife,
                selected_building_id,
                selected_villager_id,
                place_kind,
                overlay_mode,
                status_message,
                sim_speed=sim_speed,
                fish_manager=fish_manager,
                construction_sites=construction_sites,
                assign_workplace_mode=assign_workplace_mode,
                mouse_pos=mouse_pos,
                season=season,
                calendar_day=calendar_day,
                selected_habitat_kind=selected_habitat_kind,
                selected_habitat_id=selected_habitat_id,
            )

        self.content_height = max(panel_h, y)
        max_scroll = max(0, self.content_height - panel_h)
        self.scroll_y = max(0, min(self.scroll_y, max_scroll))

        panel = pygame.Rect(panel_x, MAP_OFFSET_Y, PANEL_WIDTH, panel_h)
        pygame.draw.rect(surface, COLOUR_PANEL_BG, panel)
        surface.blit(
            content,
            (panel_x, MAP_OFFSET_Y),
            pygame.Rect(0, self.scroll_y, PANEL_WIDTH, panel_h),
        )
        pygame.draw.line(
            surface,
            COLOUR_PANEL_BORDER,
            (panel_x, MAP_OFFSET_Y),
            (panel_x, WINDOW_HEIGHT),
            2,
        )

        if max_scroll > 0:
            track_h = panel_h - 16
            thumb_h = max(24, int(track_h * panel_h / self.content_height))
            thumb_y = MAP_OFFSET_Y + 8 + int((track_h - thumb_h) * (self.scroll_y / max_scroll))
            bar_x = panel_x + PANEL_WIDTH - 8
            pygame.draw.rect(surface, (60, 62, 70), pygame.Rect(bar_x, MAP_OFFSET_Y + 8, 4, track_h))
            pygame.draw.rect(surface, (140, 144, 160), pygame.Rect(bar_x, thumb_y, 4, thumb_h))

        if self._tooltip is not None and mouse_pos is not None:
            tip, _anchor = self._tooltip
            self._draw_tooltip(surface, tip, mouse_pos)

    def _draw_tooltip(
        self, surface: pygame.Surface, text: str, mouse_pos: tuple[int, int]
    ) -> None:
        padding = 6
        rendered = self.font_small.render(text, True, COLOUR_TEXT)
        tw, th = rendered.get_width(), rendered.get_height()
        popup = pygame.Rect(mouse_pos[0] + 12, mouse_pos[1] + 14, tw + padding * 2, th + padding * 2)
        if popup.right > WINDOW_WIDTH - 4:
            popup.x = mouse_pos[0] - popup.w - 8
        if popup.bottom > WINDOW_HEIGHT - 4:
            popup.y = mouse_pos[1] - popup.h - 8
        pygame.draw.rect(surface, COLOUR_MENU_BG, popup, border_radius=4)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, popup, 1, border_radius=4)
        surface.blit(rendered, (popup.x + padding, popup.y + padding))

    def _draw_legend(self, surface: pygame.Surface, x: int, y: int) -> int:
        y = _blit_text(surface, self.font_title, "Legend", (x, y))
        entries = [
            (COLOUR_HOME, "Home"),
            (COLOUR_WORKSTATION, "Hire"),
            (COLOUR_FORESTER, "Forester"),
            (COLOUR_MASON, "Mason"),
            (COLOUR_HUNTER, "Hunter"),
            (COLOUR_FORAGER, "Forager"),
            (COLOUR_FISHER, "Fisher"),
            (COLOUR_FARM, "Farm"),
            (COLOUR_FIELD, "Field"),
            ((90, 90, 70), "Site"),
            (COLOUR_PLAYER, "Player"),
            (COLOUR_VILLAGER, "Villager"),
            (COLOUR_ANIMAL, "Deer"),
            (COLOUR_BOAR, "Boar"),
            (COLOUR_FISH, "Fish"),
        ]
        for colour, label in entries:
            pygame.draw.rect(surface, colour, pygame.Rect(x, y + 1, 10, 10))
            y = _blit_text(surface, self.font_small, label, (x + 16, y), COLOUR_TEXT_DIM)
        return y


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) <= width:
            current += " " + word
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def terrain_colour(
    terrain: TerrainType,
    *,
    freeze: float = 0.0,
    vibrancy: float = 1.0,
) -> tuple[int, int, int]:
    base = {
        TerrainType.SOIL: COLOUR_SOIL,
        TerrainType.GRASS: COLOUR_GRASS,
        TerrainType.MEADOW: COLOUR_MEADOW,
        TerrainType.RIPARIAN: COLOUR_RIPARIAN,
        TerrainType.WATER: COLOUR_WATER,
        TerrainType.ROCK: COLOUR_ROCK_TERRAIN,
    }[terrain]
    if terrain == TerrainType.WATER and freeze > 0.0:
        base = blend_colour(COLOUR_WATER, COLOUR_ICE, freeze)
    return adjust_colour(base, vibrancy)


def _hash01(x: int, y: int, salt: int = 0) -> float:
    n = (x * 374761393 + y * 668265263 + salt * 1274126177) & 0x7FFFFFFF
    return (n % 10007) / 10007.0


def _mix_colours(
    colours: list[tuple[int, int, int]], weights: list[float]
) -> tuple[int, int, int]:
    total = sum(weights) or 1.0
    r = g = b = 0.0
    for (cr, cg, cb), w in zip(colours, weights):
        f = w / total
        r += cr * f
        g += cg * f
        b += cb * f
    return int(r), int(g), int(b)


def _shift_colour(
    colour: tuple[int, int, int], amount: float
) -> tuple[int, int, int]:
    """Lighten/darken by amount in [-1, 1]."""
    r, g, b = colour
    if amount >= 0:
        return (
            min(255, int(r + (255 - r) * amount)),
            min(255, int(g + (255 - g) * amount)),
            min(255, int(b + (255 - b) * amount)),
        )
    a = -amount
    return (
        max(0, int(r * (1.0 - a))),
        max(0, int(g * (1.0 - a))),
        max(0, int(b * (1.0 - a))),
    )


def _terrain_at(world: World, x: int, y: int, fallback: TerrainType) -> TerrainType:
    cell = world.get_cell(x, y)
    return cell.terrain if cell is not None else fallback


def _paint_texture(
    surface: pygame.Surface,
    rect: pygame.Rect,
    base: tuple[int, int, int],
    terrain: TerrainType,
    gx: int,
    gy: int,
) -> None:
    """Deterministic speckles / strokes so tiles aren't flat colour."""
    density = (
        14
        if terrain in (TerrainType.GRASS, TerrainType.MEADOW, TerrainType.RIPARIAN)
        else 10
        if terrain == TerrainType.SOIL
        else 8
    )
    if terrain == TerrainType.WATER:
        density = 6
    if terrain == TerrainType.ROCK:
        density = 12
    for i in range(density):
        u = _hash01(gx, gy, 17 + i * 3)
        v = _hash01(gx, gy, 91 + i * 5)
        px = rect.left + int(u * max(1, rect.w - 1))
        py = rect.top + int(v * max(1, rect.h - 1))
        shade = (_hash01(gx, gy, 200 + i) - 0.5) * 0.22
        colour = _shift_colour(base, shade)
        if terrain in (TerrainType.GRASS, TerrainType.MEADOW, TerrainType.RIPARIAN):
            length = 2 + int(_hash01(gx, gy, 40 + i) * 4)
            pygame.draw.line(
                surface,
                colour,
                (px, py),
                (px + int((_hash01(gx, gy, 55 + i) - 0.5) * 3), py - length),
                1,
            )
        elif terrain == TerrainType.WATER:
            pygame.draw.line(
                surface,
                _shift_colour(base, 0.12),
                (px, py),
                (px + 3 + int(u * 4), py + 1),
                1,
            )
        elif terrain == TerrainType.ROCK:
            pygame.draw.circle(surface, colour, (px, py), 1 + int(v * 2))
        else:
            pygame.draw.circle(surface, colour, (px, py), 1)


def _water_amount(world: World, fx: float, fy: float) -> float:
    """Organic water field (0..1). Warped distance → non-rectangular shores."""
    ix, iy = int(fx), int(fy)
    # Warp the sample point so coastlines aren't axis-aligned.
    wx = fx + (_hash01(int(fx * TERRAIN_SUBDIV), int(fy * TERRAIN_SUBDIV), 3) - 0.5) * 0.45
    wy = fy + (_hash01(int(fx * TERRAIN_SUBDIV), int(fy * TERRAIN_SUBDIV), 9) - 0.5) * 0.45
    best = 0.0
    for oy in range(-2, 3):
        for ox in range(-2, 3):
            if _terrain_at(world, ix + ox, iy + oy, TerrainType.GRASS) != TerrainType.WATER:
                continue
            cx = ix + ox + 0.5
            cy = iy + oy + 0.5
            dx = wx - cx
            dy = wy - cy
            dist = (dx * dx + dy * dy) ** 0.5
            radius = 0.82 + 0.38 * (_hash01(ix + ox, iy + oy, 11) - 0.5)
            if dist < radius:
                best = max(best, 1.0 - dist / radius)
    return best


def _soft_land_colour(
    world: World,
    fx: float,
    fy: float,
    *,
    freeze: float,
    vibrancy: float,
    farm_cells: set[tuple[int, int]] | None,
) -> tuple[int, int, int]:
    """Blend grass/rock (and non-farm soil) across sub-tile boundaries."""
    ix, iy = int(fx), int(fy)
    fx_f = fx - ix
    fy_f = fy - iy
    samples = (
        (ix, iy, (1 - fx_f) * (1 - fy_f)),
        (ix + 1, iy, fx_f * (1 - fy_f)),
        (ix, iy + 1, (1 - fx_f) * fy_f),
        (ix + 1, iy + 1, fx_f * fy_f),
    )
    colours: list[tuple[int, int, int]] = []
    weights: list[float] = []
    for sx, sy, w in samples:
        if w <= 0.001:
            continue
        t = _terrain_at(world, sx, sy, TerrainType.GRASS)
        # Keep farm soil and water out of the soft mix (handled separately).
        if t == TerrainType.WATER:
            t = TerrainType.GRASS
        if farm_cells is not None and (sx, sy) in farm_cells:
            t = TerrainType.SOIL
            # Sharp farm: dominate weight when inside farm cell.
            w *= 2.5 if (ix, iy) in farm_cells or (sx, sy) == (ix, iy) else 0.15
        colours.append(terrain_colour(t, freeze=freeze, vibrancy=vibrancy))
        weights.append(w)
    if not colours:
        return terrain_colour(TerrainType.GRASS, freeze=freeze, vibrancy=vibrancy)
    return _mix_colours(colours, weights)


# Scratch buffer for TERRAIN_SUBDIV × TERRAIN_SUBDIV colour painting.
_SUB_SCRATCH: pygame.Surface | None = None


def _sub_scratch() -> pygame.Surface:
    global _SUB_SCRATCH
    n = TERRAIN_SUBDIV
    if _SUB_SCRATCH is None or _SUB_SCRATCH.get_size() != (n, n):
        _SUB_SCRATCH = pygame.Surface((n, n))
    return _SUB_SCRATCH


def draw_terrain(
    surface: pygame.Surface,
    terrain: TerrainType,
    rect: pygame.Rect,
    *,
    freeze: float = 0.0,
    vibrancy: float = 1.0,
    frozen: bool = False,
    world: World | None = None,
    gx: int = 0,
    gy: int = 0,
    farm_cells: set[tuple[int, int]] | None = None,
    water_mask: pygame.Surface | None = None,
) -> None:
    """Draw a terrain tile as TERRAIN_SUBDIV² sub-squares with habitat blending.

    Water uses a sharp organic (non-rectangular) mask. Farm cells keep sharp edges.
    When water_mask is provided, organic water pixels are also written there (for
    cheap seasonal ice overlays without rebaking the map).
    """
    if frozen and freeze <= 0.0:
        freeze = 1.0

    if world is None:
        colour = terrain_colour(terrain, freeze=freeze, vibrancy=vibrancy)
        pygame.draw.rect(surface, colour, rect)
        _paint_texture(surface, rect, colour, terrain, gx, gy)
        return

    n = TERRAIN_SUBDIV
    mini = _sub_scratch()
    water_mini: pygame.Surface | None = None
    if water_mask is not None:
        water_mini = pygame.Surface((n, n), pygame.SRCALPHA)
        water_mini.fill((0, 0, 0, 0))
    is_farm = farm_cells is not None and (gx, gy) in farm_cells
    water_c = terrain_colour(TerrainType.WATER, freeze=freeze, vibrancy=vibrancy)
    soil_c = terrain_colour(TerrainType.SOIL, freeze=freeze, vibrancy=vibrancy)

    for sy in range(n):
        for sx in range(n):
            fx = gx + (sx + 0.5) / n
            fy = gy + (sy + 0.5) / n
            # Sharp organic water (thresholded field — not a soft fade).
            if _water_amount(world, fx, fy) >= 0.48:
                shade = (_hash01(gx * n + sx, gy * n + sy, 21) - 0.5) * 0.08
                colour = _shift_colour(water_c, shade)
                if water_mini is not None:
                    water_mini.set_at((sx, sy), (255, 255, 255, 255))
            elif is_farm:
                # Sharp farm interiors: solid soil colour, no neighbour bleed.
                shade = (_hash01(gx * n + sx, gy * n + sy, 33) - 0.5) * 0.06
                colour = _shift_colour(soil_c, shade)
            else:
                colour = _soft_land_colour(
                    world,
                    fx,
                    fy,
                    freeze=freeze,
                    vibrancy=vibrancy,
                    farm_cells=farm_cells,
                )
                shade = (_hash01(gx * n + sx, gy * n + sy, 44) - 0.5) * 0.05
                colour = _shift_colour(colour, shade)
            mini.set_at((sx, sy), colour)

    scaled = pygame.transform.scale(mini, (rect.w, rect.h))
    surface.blit(scaled, rect.topleft)
    if water_mask is not None and water_mini is not None:
        water_mask.blit(pygame.transform.scale(water_mini, (rect.w, rect.h)), rect.topleft)

    # Light texture overlay (coarser, on the full cell).
    base = (
        soil_c
        if is_farm
        else water_c
        if terrain == TerrainType.WATER
        else terrain_colour(terrain, freeze=freeze, vibrancy=vibrancy)
    )
    _paint_texture(surface, rect, base, TerrainType.SOIL if is_farm else terrain, gx, gy)


# Scratch buffer for TERRAIN_SUBDIV × TERRAIN_SUBDIV colour painting.

def _draw_crop_plant(
    surface: pygame.Surface,
    cx: int,
    cy: int,
    stem_colour: tuple[int, int, int],
    flower_colour: tuple[int, int, int] | None,
    *,
    dense: bool = False,
) -> None:
    """Herb/crop glyph: stems flipped 180° (base near top, tip toward bottom)."""
    offsets = (-4, -1, 2, 5) if dense else (-3, 0, 3)
    for ox in offsets:
        tip_x = cx + ox // 2
        tip_y = cy + 6
        pygame.draw.line(
            surface,
            stem_colour,
            (cx + ox, cy - 4),
            (tip_x, tip_y),
            2,
        )
        if flower_colour is not None:
            pygame.draw.circle(surface, flower_colour, (tip_x, tip_y), 2)


def draw_feature(
    surface: pygame.Surface,
    feature: FeatureType,
    cx: int,
    cy: int,
    size: int,
    vibrancy: float = 1.0,
    crop_kind: str | None = None,
    tree_species: str | None = None,
) -> None:
    if feature == FeatureType.NONE:
        return
    from crops import CROP_BY_KEY
    from trees import resolve_tree

    herb_c = adjust_colour(COLOUR_HERB, vibrancy)
    berry_c = adjust_colour(COLOUR_BERRY, vibrancy)
    mush_c = adjust_colour(COLOUR_MUSHROOM, vibrancy)
    bush_c = adjust_colour((50, 110, 50), vibrancy)
    if feature == FeatureType.TREE:
        tree = resolve_tree(tree_species)
        colour = adjust_colour(tree.canopy, vibrancy)
        trunk_w = max(2, size // 10)
        trunk_h = size // 4
        pygame.draw.rect(
            surface,
            adjust_colour((90, 55, 30), vibrancy),
            pygame.Rect(cx - trunk_w // 2, cy, trunk_w, trunk_h),
        )
        if tree.shape == "cone":
            scale = tree.cone_scale
            half_w = int((size // 5) * scale)
            height = int((size // 3) * scale)
            tip = (cx, cy - height)
            left = (cx - half_w, cy + size // 16)
            right = (cx + half_w, cy + size // 16)
            pygame.draw.polygon(surface, colour, [tip, left, right])
        else:
            pygame.draw.circle(surface, colour, (cx, cy - size // 10), size // 4)
    elif feature == FeatureType.SAPLING:
        tree = resolve_tree(tree_species)
        colour = adjust_colour(tree.sapling_colour, vibrancy)
        pygame.draw.line(
            surface,
            adjust_colour((90, 55, 30), vibrancy),
            (cx, cy),
            (cx, cy + size // 8),
            2,
        )
        if tree.shape == "cone":
            scale = 0.55 * tree.cone_scale
            half_w = max(3, int((size // 8) * scale))
            height = max(5, int((size // 6) * scale))
            tip = (cx, cy - height // 2)
            left = (cx - half_w, cy + 2)
            right = (cx + half_w, cy + 2)
            pygame.draw.polygon(surface, colour, [tip, left, right])
        else:
            pygame.draw.circle(surface, colour, (cx, cy), max(3, size // 8))
    elif feature == FeatureType.ROCK:
        points = [
            (cx - size // 5, cy + size // 8),
            (cx - size // 8, cy - size // 6),
            (cx + size // 5, cy - size // 10),
            (cx + size // 4, cy + size // 8),
        ]
        pygame.draw.polygon(surface, COLOUR_ROCK_FEATURE, points)
    elif feature == FeatureType.HOME:
        half = size // 4
        body = pygame.Rect(cx - half, cy - half // 2, half * 2, half + half // 2)
        pygame.draw.rect(surface, COLOUR_HOME, body)
        roof = [(cx - half - 2, cy - half // 2), (cx, cy - half - 4), (cx + half + 2, cy - half // 2)]
        pygame.draw.polygon(surface, (170, 60, 50), roof)
    elif feature == FeatureType.WORKSTATION:
        half = size // 3
        desk = pygame.Rect(cx - half, cy - half // 2, half * 2, half)
        pygame.draw.rect(surface, COLOUR_WORKSTATION, desk)
        pygame.draw.rect(surface, (200, 200, 230), desk, 2)
        pygame.draw.circle(surface, (255, 220, 80), (cx, cy - 2), max(3, size // 10))
    elif feature == FeatureType.FORESTER:
        half = size // 3
        body = pygame.Rect(cx - half, cy - half // 2, half * 2, half)
        pygame.draw.rect(surface, COLOUR_FORESTER, body)
        pygame.draw.circle(surface, COLOUR_TREE_CANOPY, (cx, cy - half // 2 - 2), size // 6)
    elif feature == FeatureType.MASON:
        half = size // 3
        body = pygame.Rect(cx - half, cy - half // 2, half * 2, half)
        pygame.draw.rect(surface, COLOUR_MASON, body)
        pygame.draw.polygon(
            surface,
            COLOUR_ROCK_FEATURE,
            [
                (cx - size // 6, cy + 2),
                (cx, cy - size // 6),
                (cx + size // 6, cy + 2),
            ],
        )
    elif feature == FeatureType.HUNTER:
        half = size // 3
        body = pygame.Rect(cx - half, cy - half // 2, half * 2, half)
        pygame.draw.rect(surface, COLOUR_HUNTER, body)
        pygame.draw.polygon(
            surface,
            COLOUR_MEAT,
            [
                (cx - 4, cy + 4),
                (cx, cy - half // 2 - 2),
                (cx + 4, cy + 4),
            ],
        )
    elif feature == FeatureType.FORAGER:
        half = size // 3
        body = pygame.Rect(cx - half, cy - half // 2, half * 2, half)
        pygame.draw.rect(surface, COLOUR_FORAGER, body)
        pygame.draw.circle(surface, COLOUR_BERRY, (cx - 4, cy), 3)
        pygame.draw.circle(surface, COLOUR_MUSHROOM, (cx + 4, cy - 2), 3)
    elif feature == FeatureType.CONSTRUCTION_SITE:
        half = size // 3
        body = pygame.Rect(cx - half, cy - half // 2, half * 2, half)
        pygame.draw.rect(surface, (90, 90, 70), body, 1)
        pygame.draw.line(surface, (180, 160, 80), (cx - half, cy - half), (cx - half, cy + half), 2)
        pygame.draw.line(surface, (180, 160, 80), (cx + half, cy - half), (cx + half, cy + half), 2)
        pygame.draw.line(surface, (180, 160, 80), (cx - half, cy - half), (cx + half, cy - half), 2)
    elif feature == FeatureType.FISHER:
        half = size // 3
        body = pygame.Rect(cx - half, cy - half // 2, half * 2, half)
        pygame.draw.rect(surface, COLOUR_FISHER, body)
        pygame.draw.ellipse(
            surface,
            COLOUR_FISH,
            pygame.Rect(cx - 6, cy - 2, 10, 5),
        )
    elif feature == FeatureType.FARM:
        half = size // 3
        body = pygame.Rect(cx - half, cy - half // 2, half * 2, half)
        pygame.draw.rect(surface, COLOUR_FARM, body)
        _draw_crop_plant(surface, cx, cy, COLOUR_CROP, None, dense=False)
    elif feature == FeatureType.FIELD:
        half = size // 3
        body = pygame.Rect(cx - half, cy - half // 2, half * 2, half)
        pygame.draw.rect(surface, COLOUR_FIELD, body)
        pygame.draw.line(surface, (200, 180, 90), (cx - half + 2, cy), (cx + half - 2, cy), 1)
        pygame.draw.line(surface, (200, 180, 90), (cx, cy - half // 2 + 2), (cx, cy + half // 2 - 2), 1)
    elif feature == FeatureType.MUSHROOM:
        pygame.draw.circle(surface, mush_c, (cx, cy - 2), max(4, size // 7))
        pygame.draw.rect(surface, (210, 200, 180), pygame.Rect(cx - 2, cy, 4, size // 8))
    elif feature == FeatureType.BERRY_BUSH:
        pygame.draw.circle(surface, bush_c, (cx, cy), size // 5)
        for ox, oy in ((-4, -2), (3, -3), (0, 2), (4, 1), (-3, 3)):
            pygame.draw.circle(surface, berry_c, (cx + ox, cy + oy), 2)
    elif feature == FeatureType.REED:
        reed_c = adjust_colour(COLOUR_REED, vibrancy)
        for ox in (-3, 0, 3):
            tip_x = cx + ox // 2
            pygame.draw.line(
                surface,
                reed_c,
                (cx + ox, cy + 4),
                (tip_x, cy - 8),
                2,
            )
    elif feature in (FeatureType.HERB, FeatureType.WILD_CROP, FeatureType.CROP_HERB):
        crop = CROP_BY_KEY.get(crop_kind or "sage") or CROP_BY_KEY["sage"]
        stem = adjust_colour(crop.stem_colour, vibrancy)
        flower = (
            adjust_colour(crop.flower_colour, vibrancy)
            if crop.flower_colour is not None
            else None
        )
        dense = feature == FeatureType.CROP_HERB
        _draw_crop_plant(surface, cx, cy, stem, flower, dense=dense)
