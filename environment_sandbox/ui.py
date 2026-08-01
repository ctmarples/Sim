"""UI panel, legends, and text helpers (scrollable side panel)."""

from __future__ import annotations

import pygame

from entities import (
    BUILDING_LABELS,
    PRIORITY_LABELS,
    TASK_LABELS,
    WORK_MODE_LABELS,
    WORK_MODE_SHORT,
    Building,
    BuildingKind,
    ConstructionSite,
    HomeStorage,
    Player,
    Villager,
    WorkPriority,
)
from indicators import OVERLAY_LABELS, OverlayMode
from seasons import Season, adjust_colour, blend_colour, format_date
from settings import (
    CELL_SIZE,
    COLOUR_ANIMAL,
    COLOUR_BERRY,
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
    COLOUR_MEAT,
    COLOUR_MENU_BG,
    COLOUR_MUSHROOM,
    COLOUR_PANEL_BG,
    COLOUR_PANEL_BORDER,
    COLOUR_PLAYER,
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
    GRID_COLS,
    MAP_OFFSET_Y,
    MAX_VILLAGERS,
    PANEL_WIDTH,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)
from wildlife import FishManager, WildlifeManager
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
        panel_x = GRID_COLS * CELL_SIZE
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
    ) -> None:
        panel_x = GRID_COLS * CELL_SIZE
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
                workers = sum(1 for v in villagers if v.building_id == b.id)
                selected = selected_building_id == b.id
                trailing = None
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
                    f"{BUILDING_LABELS[b.kind]} #{b.id}  "
                    f"{b.stored_total}/{b.capacity} · {workers}w · {WORK_MODE_SHORT[b.work_mode]}",
                    x,
                    y,
                    selected=selected,
                    hit_kind="building",
                    hit_id=b.id,
                    trailing_btns=trailing,
                    local_mouse=local_mouse,
                )
        y = self._draw_list_row(
            content,
            "Home (haulers)",
            x,
            y,
            selected=False,
            hit_kind="home",
            hit_id=0,
            local_mouse=local_mouse,
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
            trailing = None
            if selected:
                trailing = self._inline_priority_buttons(v, assign_workplace_mode)
            y = self._draw_list_row(
                content,
                f"#{v.id} {v.state.name[:4]} → {job}",
                x,
                y,
                selected=selected,
                hit_kind="villager",
                hit_id=v.id,
                trailing_btns=trailing,
                local_mouse=local_mouse,
            )
        y += 4

        y = _blit_text(content, self.font_title, "World", (x, y))
        cap = wildlife.total_capacity(world)
        wild_line = f"Animals {len(wildlife.animals)}/{cap}"
        if fish_manager is not None:
            wild_line += f" · Fish {len(fish_manager.fish)}/{fish_manager.total_capacity(world)}"
        y = _blit_text(content, self.font_small, wild_line, (x, y), COLOUR_TEXT_DIM)
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
            ((90, 90, 70), "Site"),
            (COLOUR_PLAYER, "Player"),
            (COLOUR_VILLAGER, "Villager"),
            (COLOUR_ANIMAL, "Animal"),
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
        TerrainType.WATER: COLOUR_WATER,
        TerrainType.ROCK: COLOUR_ROCK_TERRAIN,
    }[terrain]
    if terrain == TerrainType.WATER and freeze > 0.0:
        base = blend_colour(COLOUR_WATER, COLOUR_ICE, freeze)
    return adjust_colour(base, vibrancy)


def draw_terrain(
    surface: pygame.Surface,
    terrain: TerrainType,
    rect: pygame.Rect,
    *,
    freeze: float = 0.0,
    vibrancy: float = 1.0,
    frozen: bool = False,
) -> None:
    if frozen and freeze <= 0.0:
        freeze = 1.0
    colour = terrain_colour(terrain, freeze=freeze, vibrancy=vibrancy)
    pygame.draw.rect(surface, colour, rect)
    if terrain == TerrainType.WATER and freeze > 0.25:
        # Light ice sheen, stronger as freeze increases.
        alpha_line = blend_colour(colour, (220, 235, 245), min(1.0, freeze))
        pygame.draw.line(
            surface,
            alpha_line,
            (rect.left + 3, rect.centery - 2),
            (rect.right - 4, rect.centery + 3),
            1,
        )
    if terrain == TerrainType.ROCK:
        cx, cy = rect.center
        for ox, oy in ((-6, -4), (5, -3), (-3, 5), (4, 4), (0, -7), (7, 1)):
            px = cx + ox
            py = cy + oy
            if rect.collidepoint(px, py):
                pygame.draw.circle(surface, COLOUR_ROCK_TERRAIN_DARK, (px, py), 2)
        pygame.draw.line(
            surface,
            COLOUR_ROCK_TERRAIN_DARK,
            (rect.left + 4, rect.centery + 2),
            (rect.right - 4, rect.centery - 3),
            1,
        )


def draw_feature(
    surface: pygame.Surface,
    feature: FeatureType,
    cx: int,
    cy: int,
    size: int,
    vibrancy: float = 1.0,
) -> None:
    if feature == FeatureType.NONE:
        return
    canopy = adjust_colour(COLOUR_TREE_CANOPY, vibrancy)
    sapling_c = adjust_colour(COLOUR_SAPLING, vibrancy)
    herb_c = adjust_colour(COLOUR_HERB, vibrancy)
    berry_c = adjust_colour(COLOUR_BERRY, vibrancy)
    mush_c = adjust_colour(COLOUR_MUSHROOM, vibrancy)
    bush_c = adjust_colour((50, 110, 50), vibrancy)
    if feature == FeatureType.TREE:
        trunk_w = max(2, size // 10)
        trunk_h = size // 4
        pygame.draw.rect(
            surface,
            adjust_colour((90, 55, 30), vibrancy),
            pygame.Rect(cx - trunk_w // 2, cy, trunk_w, trunk_h),
        )
        pygame.draw.circle(surface, canopy, (cx, cy - size // 10), size // 4)
    elif feature == FeatureType.SAPLING:
        pygame.draw.circle(surface, sapling_c, (cx, cy), max(3, size // 8))
        pygame.draw.line(
            surface,
            adjust_colour((90, 55, 30), vibrancy),
            (cx, cy),
            (cx, cy + size // 8),
            2,
        )
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
    elif feature == FeatureType.MUSHROOM:
        pygame.draw.circle(surface, mush_c, (cx, cy - 2), max(4, size // 7))
        pygame.draw.rect(surface, (210, 200, 180), pygame.Rect(cx - 2, cy, 4, size // 8))
    elif feature == FeatureType.BERRY_BUSH:
        pygame.draw.circle(surface, bush_c, (cx, cy), size // 5)
        for ox, oy in ((-4, -2), (3, -3), (0, 2), (4, 1), (-3, 3)):
            pygame.draw.circle(surface, berry_c, (cx + ox, cy + oy), 2)
    elif feature == FeatureType.HERB:
        for ox in (-3, 0, 3):
            pygame.draw.line(
                surface,
                herb_c,
                (cx + ox, cy + 4),
                (cx + ox // 2, cy - 6),
                2,
            )
