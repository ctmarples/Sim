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
    COLOUR_HOME_ROOF,
    COLOUR_HUNTER,
    COLOUR_ICE,
    COLOUR_KITCHEN,
    COLOUR_MASON,
    COLOUR_MEADOW,
    COLOUR_MEAT,
    COLOUR_MENU_BG,
    COLOUR_MILL,
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
    COLOUR_FOREST_FLOOR,
    COLOUR_STATUS,
    COLOUR_TEXT,
    COLOUR_TEXT_DIM,
    COLOUR_TOOLBAR_BTN,
    COLOUR_TOOLBAR_BTN_ACTIVE,
    COLOUR_TOOLBAR_BORDER,
    COLOUR_TREE_CANOPY,
    COLOUR_TREE_TRUNK,
    COLOUR_VILLAGER,
    COLOUR_WATER,
    COLOUR_WORKSTATION,
    MAP_OFFSET_Y,
    MAX_VILLAGERS,
    PANEL_WIDTH,
    ROCK_LARGE_MIN,
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
        buff_bits: list[str] = []
        if abs(villager.food_walk_mult - 1.0) > 0.01:
            buff_bits.append(f"walk ×{villager.food_walk_mult:g}")
        if abs(villager.food_work_mult - 1.0) > 0.01:
            buff_bits.append(f"work ×{villager.food_work_mult:g}")
        if abs(villager.food_hunger_mult - 1.0) > 0.01:
            buff_bits.append(f"hunger ×{villager.food_hunger_mult:g}")
        if buff_bits:
            tip = f"{tip} · {', '.join(buff_bits)}"
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
            (COLOUR_MILL, "Mill"),
            (COLOUR_KITCHEN, "Kitchen"),
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
        TerrainType.FOREST_FLOOR: COLOUR_FOREST_FLOOR,
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
        if terrain in (TerrainType.SOIL, TerrainType.FOREST_FLOOR)
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

def _iso_shade(
    colour: tuple[int, int, int], amount: float
) -> tuple[int, int, int]:
    """Lighten (amount>0) or darken (amount<0) for isometric faces."""
    return _shift_colour(colour, amount)


def _iso_building_recolour(
    wall: tuple[int, int, int],
    *,
    roof: tuple[int, int, int] | None = None,
    accent: tuple[int, int, int] | None = None,
    accent2: tuple[int, int, int] | None = None,
    stem: tuple[int, int, int] | None = None,
    vibrancy: float = 1.0,
) -> dict[str, tuple[int, int, int]]:
    """Map building SVG face classes to shaded colours from a wall/roof base."""
    from seasons import adjust_colour

    w = adjust_colour(wall, vibrancy)
    r = adjust_colour(roof if roof is not None else wall, vibrancy)
    out: dict[str, tuple[int, int, int]] = {
        "wall_l": _iso_shade(w, -0.28),
        "wall_r": _iso_shade(w, 0.14),
        "body": _iso_shade(w, -0.1),
        "roof": r,
        "roof_dark": _iso_shade(r, -0.22),
        "door": _iso_shade(w, -0.45),
        "trim": _iso_shade(r, -0.12),
    }
    if accent is not None:
        out["accent"] = adjust_colour(accent, vibrancy)
    if accent2 is not None:
        out["accent2"] = adjust_colour(accent2, vibrancy)
    if stem is not None:
        out["stem"] = adjust_colour(stem, vibrancy)
    return out


def draw_feature(
    surface: pygame.Surface,
    feature: FeatureType,
    cx: int,
    cy: int,
    size: int,
    vibrancy: float = 1.0,
    crop_kind: str | None = None,
    tree_species: str | None = None,
    icon_variant: int | None = None,
    deposit: int = 0,
) -> None:
    if feature == FeatureType.NONE:
        return
    if feature == FeatureType.STRUCTURE_PAD:
        return
    from crops import CROP_BY_KEY
    from icons import (
        ICON_BERRY_BUSH,
        ICON_CONSTRUCTION,
        ICON_FARM,
        ICON_FIELD,
        ICON_FISHER,
        ICON_FORAGER,
        ICON_FORESTER,
        ICON_HOME,
        ICON_HUNTER,
        ICON_KITCHEN,
        ICON_MASON,
        ICON_MILL,
        ICON_MUSHROOM,
        ICON_REED,
        ICON_ROCK,
        ICON_ROCK_BIG,
        ICON_SAPLING_CONE,
        ICON_SAPLING_ROUND,
        ICON_TREE_CONE,
        ICON_TREE_ROUND,
        ICON_WORKSTATION,
        blit_icon,
    )
    from trees import resolve_tree

    trunk = adjust_colour(COLOUR_TREE_TRUNK, vibrancy)
    v = icon_variant

    if feature == FeatureType.TREE:
        tree = resolve_tree(tree_species)
        base = ICON_TREE_CONE if tree.shape == "cone" else ICON_TREE_ROUND
        scales = {"canopy": tree.cone_scale} if tree.shape == "cone" else None
        blit_icon(
            surface,
            base,
            cx,
            cy,
            size,
            variant=v,
            recolour={
                "canopy": adjust_colour(tree.canopy, vibrancy),
                "trunk": trunk,
            },
            class_scales=scales,
        )
    elif feature == FeatureType.SAPLING:
        tree = resolve_tree(tree_species)
        base = ICON_SAPLING_CONE if tree.shape == "cone" else ICON_SAPLING_ROUND
        scales = {"canopy": tree.cone_scale} if tree.shape == "cone" else None
        blit_icon(
            surface,
            base,
            cx,
            cy,
            size,
            variant=v,
            recolour={
                "canopy": adjust_colour(tree.sapling_colour, vibrancy),
                "trunk": trunk,
            },
            class_scales=scales,
        )
    elif feature == FeatureType.ROCK:
        base = ICON_ROCK_BIG if deposit >= ROCK_LARGE_MIN else ICON_ROCK
        blit_icon(
            surface,
            base,
            cx,
            cy,
            size,
            variant=v,
            recolour={"body": COLOUR_ROCK_FEATURE},
        )
    elif feature == FeatureType.HOME:
        blit_icon(
            surface,
            ICON_HOME,
            cx,
            cy,
            size,
            variant=v,
            recolour=_iso_building_recolour(
                COLOUR_HOME, roof=COLOUR_HOME_ROOF, vibrancy=vibrancy
            ),
        )
    elif feature == FeatureType.WORKSTATION:
        blit_icon(
            surface,
            ICON_WORKSTATION,
            cx,
            cy,
            size,
            variant=v,
            recolour=_iso_building_recolour(
                COLOUR_WORKSTATION,
                accent=(255, 220, 80),
                vibrancy=vibrancy,
            ),
        )
    elif feature == FeatureType.FORESTER:
        blit_icon(
            surface,
            ICON_FORESTER,
            cx,
            cy,
            size,
            variant=v,
            recolour=_iso_building_recolour(
                COLOUR_FORESTER,
                roof=(30, 90, 40),
                accent=COLOUR_TREE_CANOPY,
                accent2=(46, 154, 60),
                vibrancy=vibrancy,
            ),
        )
    elif feature == FeatureType.MASON:
        blit_icon(
            surface,
            ICON_MASON,
            cx,
            cy,
            size,
            variant=v,
            recolour=_iso_building_recolour(
                COLOUR_MASON,
                accent=COLOUR_ROCK_FEATURE,
                vibrancy=vibrancy,
            ),
        )
    elif feature == FeatureType.HUNTER:
        blit_icon(
            surface,
            ICON_HUNTER,
            cx,
            cy,
            size,
            variant=v,
            recolour=_iso_building_recolour(
                COLOUR_HUNTER,
                roof=(120, 50, 40),
                accent=COLOUR_MEAT,
                vibrancy=vibrancy,
            ),
        )
    elif feature == FeatureType.FORAGER:
        blit_icon(
            surface,
            ICON_FORAGER,
            cx,
            cy,
            size,
            variant=v,
            recolour=_iso_building_recolour(
                COLOUR_FORAGER,
                roof=(40, 90, 55),
                accent=COLOUR_BERRY,
                accent2=COLOUR_MUSHROOM,
                vibrancy=vibrancy,
            ),
        )
    elif feature == FeatureType.CONSTRUCTION_SITE:
        blit_icon(
            surface,
            ICON_CONSTRUCTION,
            cx,
            cy,
            size,
            variant=v,
            recolour=_iso_building_recolour(
                (90, 90, 70),
                accent=(180, 160, 80),
                vibrancy=vibrancy,
            ),
        )
    elif feature == FeatureType.FISHER:
        blit_icon(
            surface,
            ICON_FISHER,
            cx,
            cy,
            size,
            variant=v,
            recolour=_iso_building_recolour(
                COLOUR_FISHER,
                roof=(40, 70, 110),
                accent=COLOUR_FISH,
                vibrancy=vibrancy,
            ),
        )
    elif feature == FeatureType.FARM:
        blit_icon(
            surface,
            ICON_FARM,
            cx,
            cy,
            size,
            variant=v,
            recolour=_iso_building_recolour(
                COLOUR_FARM,
                roof=(140, 90, 50),
                stem=COLOUR_CROP,
                vibrancy=vibrancy,
            ),
        )
    elif feature == FeatureType.FIELD:
        blit_icon(
            surface,
            ICON_FIELD,
            cx,
            cy,
            size,
            variant=v,
            recolour=_iso_building_recolour(
                COLOUR_FIELD,
                accent=(200, 180, 90),
                vibrancy=vibrancy,
            ),
        )
    elif feature == FeatureType.MILL:
        blit_icon(
            surface,
            ICON_MILL,
            cx,
            cy,
            size,
            variant=v,
            recolour=_iso_building_recolour(
                COLOUR_MILL,
                roof=(106, 80, 56),
                accent=(216, 192, 144),
                vibrancy=vibrancy,
            ),
        )
    elif feature == FeatureType.KITCHEN:
        blit_icon(
            surface,
            ICON_KITCHEN,
            cx,
            cy,
            size,
            variant=v,
            recolour=_iso_building_recolour(
                COLOUR_KITCHEN,
                roof=(120, 50, 40),
                accent=(220, 160, 80),
                vibrancy=vibrancy,
            ),
        )
    elif feature == FeatureType.MUSHROOM:
        blit_icon(
            surface,
            ICON_MUSHROOM,
            cx,
            cy,
            size,
            variant=v,
            recolour={
                "cap": adjust_colour(COLOUR_MUSHROOM, vibrancy),
                "stem": (210, 200, 180),
            },
        )
    elif feature == FeatureType.BERRY_BUSH:
        blit_icon(
            surface,
            ICON_BERRY_BUSH,
            cx,
            cy,
            size,
            variant=v,
            recolour={
                "bush": adjust_colour((50, 110, 50), vibrancy),
                "berry": adjust_colour(COLOUR_BERRY, vibrancy),
            },
        )
    elif feature == FeatureType.REED:
        blit_icon(
            surface,
            ICON_REED,
            cx,
            cy,
            size,
            variant=v,
            recolour={"stem": adjust_colour(COLOUR_REED, vibrancy)},
        )
    elif feature in (FeatureType.HERB, FeatureType.WILD_CROP, FeatureType.CROP_HERB):
        crop = CROP_BY_KEY.get(crop_kind or "sage") or CROP_BY_KEY["sage"]
        stem = adjust_colour(crop.stem_colour, vibrancy)
        name = crop.plant_icon(dense=feature == FeatureType.CROP_HERB)
        recolour = {"stem": stem}
        omit: tuple[str, ...] = ()
        if crop.flower_colour is not None:
            recolour["flower"] = adjust_colour(crop.flower_colour, vibrancy)
        else:
            omit = ("flower",)
        blit_icon(
            surface,
            name,
            cx,
            cy,
            size,
            variant=v,
            recolour=recolour,
            omit_classes=omit,
        )
