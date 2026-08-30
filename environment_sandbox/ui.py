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
    WorkplaceSlot,
)
from indicators import OVERLAY_LABELS, OverlayMode
from seasons import Season, adjust_colour, blend_colour, format_date
from settings import (
    CELL_SIZE,
    COLOUR_ANIMAL,
    COLOUR_BEE,
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
    PLAYBACK_TICKS_AT_X1,
    WALK_SECONDS_AT_X1,
    WORK_SECONDS_AT_X1,
    seconds_to_ticks,
    ticks_to_seconds,
    COLOUR_HOME_ROOF,
    COLOUR_HUNTER,
    COLOUR_ICE,
    COLOUR_KITCHEN,
    COLOUR_CRAFT_BENCH,
    COLOUR_ALCHEMIST,
    COLOUR_TAILOR,
    COLOUR_COBBLER,
    COLOUR_MARKET,
    COLOUR_MASON,
    COLOUR_MEADOW,
    COLOUR_MEAT,
    COLOUR_MENU_BG,
    COLOUR_MILL,
    COLOUR_MUSHROOM,
    COLOUR_PANEL_BG,
    COLOUR_PANEL_BORDER,
    COLOUR_PLAYER,
    COLOUR_RABBIT,
    COLOUR_REED,
    COLOUR_RIPARIAN,
    COLOUR_ROCK_FEATURE,
    COLOUR_ROCK_TERRAIN,
    COLOUR_ROCK_TERRAIN_DARK,
    COLOUR_URBAN,
    COLOUR_PATH,
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
    PANEL_COLLAPSED,
    PANEL_WIDTH,
    TERRAIN_SUBDIV,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    map_view_width,
)
from resource_balance import ROCK_LARGE_MIN
from wildlife import AnimalKind, FishManager, WildlifeManager
from world import (
    EDIT_PAINTABLE_TERRAIN,
    MapEditTool,
    TERRAIN_EDIT_LABELS,
    FeatureType,
    TerrainType,
    World,
)


def _panel_height() -> int:
    return WINDOW_HEIGHT - MAP_OFFSET_Y


def _blit_text(
    surface: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    pos: tuple[int, int],
    colour: tuple[int, int, int] = COLOUR_TEXT,
) -> int:
    rendered = _cached_font_surf(font, text, colour)
    surface.blit(rendered, pos)
    return pos[1] + rendered.get_height() + 4


_FONT_SURF_CACHE: dict[tuple, pygame.Surface] = {}
_FONT_SURF_CACHE_MAX = 768
_FONT_SIZE_CACHE: dict[tuple, int] = {}
_ELLIPSIZE_CACHE: dict[tuple, str] = {}


def _cached_font_surf(
    font: pygame.font.Font, text: str, colour: tuple[int, int, int]
) -> pygame.Surface:
    key = (id(font), text, colour)
    surf = _FONT_SURF_CACHE.get(key)
    if surf is None:
        surf = font.render(text, True, colour)
        if len(_FONT_SURF_CACHE) >= _FONT_SURF_CACHE_MAX:
            _FONT_SURF_CACHE.clear()
        _FONT_SURF_CACHE[key] = surf
    return surf


def _cached_font_width(font: pygame.font.Font, text: str) -> int:
    key = (id(font), text)
    width = _FONT_SIZE_CACHE.get(key)
    if width is None:
        width = font.size(text)[0]
        if len(_FONT_SIZE_CACHE) >= _FONT_SURF_CACHE_MAX:
            _FONT_SIZE_CACHE.clear()
        _FONT_SIZE_CACHE[key] = width
    return width


def _ellipsize(font: pygame.font.Font, text: str, max_w: int) -> str:
    key = (id(font), text, max_w)
    cached = _ELLIPSIZE_CACHE.get(key)
    if cached is not None:
        return cached
    label = text
    while _cached_font_width(font, label) > max_w and len(label) > 4:
        label = label[:-2] + "…"
    if len(_ELLIPSIZE_CACHE) >= _FONT_SURF_CACHE_MAX:
        _ELLIPSIZE_CACHE.clear()
    _ELLIPSIZE_CACHE[key] = label
    return label


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
        # Screen-space tab when the sidebar is collapsed (Tab / click to restore).
        self.expand_tab_rect: pygame.Rect | None = None

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
        if self.expand_tab_rect is not None and self.expand_tab_rect.collidepoint(pos):
            return "toggle_panel"
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

    def _blit_panel_to_screen(
        self,
        surface: pygame.Surface,
        panel_x: int,
        panel_h: int,
        mouse_pos: tuple[int, int] | None = None,
    ) -> None:
        content = self._content
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
            thumb_y = MAP_OFFSET_Y + 8 + int(
                (track_h - thumb_h) * (self.scroll_y / max_scroll)
            )
            bar_x = panel_x + PANEL_WIDTH - 8
            pygame.draw.rect(
                surface, (60, 62, 70), pygame.Rect(bar_x, MAP_OFFSET_Y + 8, 4, track_h)
            )
            pygame.draw.rect(
                surface, (140, 144, 160), pygame.Rect(bar_x, thumb_y, 4, thumb_h)
            )
        if self._tooltip is not None and mouse_pos is not None:
            tip, _anchor = self._tooltip
            self._draw_tooltip(surface, tip, mouse_pos)

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

    def _register_tool_button(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        glyph: str,
        action: str,
        tip: str,
        *,
        active: bool,
        local_mouse: tuple[int, int] | None,
    ) -> None:
        hovered = local_mouse is not None and rect.collidepoint(local_mouse)
        self._draw_icon_button(surface, rect, glyph, active=active, hovered=hovered)
        self.action_hits.append((rect, action, tip))
        if hovered:
            self._tooltip = (tip, (rect.centerx, rect.top))

    def _draw_labelled_tool_button(
        self,
        surface: pygame.Surface,
        x: int,
        y: int,
        w: int,
        h: int,
        label: str,
        action: str,
        tip: str,
        *,
        active: bool,
        local_mouse: tuple[int, int] | None,
    ) -> None:
        rect = pygame.Rect(x, y, w, h)
        hovered = local_mouse is not None and rect.collidepoint(local_mouse)
        if active:
            colour = COLOUR_TOOLBAR_BTN_ACTIVE
        elif hovered:
            colour = (70, 78, 92)
        else:
            colour = COLOUR_TOOLBAR_BTN
        pygame.draw.rect(surface, colour, rect, border_radius=3)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, rect, 1, border_radius=3)
        text = self.font_small.render(label, True, COLOUR_TEXT)
        surface.blit(
            text,
            (
                rect.x + (rect.w - text.get_width()) // 2,
                rect.y + (rect.h - text.get_height()) // 2,
            ),
        )
        self.action_hits.append((rect, action, tip))
        if hovered:
            self._tooltip = (tip, (rect.centerx, rect.top))

    def _draw_map_edit_panel(
        self,
        content: pygame.Surface,
        x: int,
        y: int,
        *,
        map_edit_tool: MapEditTool,
        map_edit_terrain: TerrainType,
        height_paint_value: float,
        height_delta_step: float,
        height_brush_radius: int,
        local_mouse: tuple[int, int] | None,
    ) -> int:
        """Tool palette shown instead of the entity list while map-edit is on."""
        y = _blit_text(content, self.font_title, "Map Edit", (x, y))
        y = _blit_text(
            content,
            self.font_small,
            "Y / Esc exit · scroll zoom",
            (x, y),
            COLOUR_TEXT_DIM,
        )
        y += 6

        y = _blit_text(content, self.font_title, "Height", (x, y))
        btn_h = 22
        gap = 4
        tools_h = (
            (MapEditTool.HEIGHT_SET, "Set", "Paint a specific height"),
            (MapEditTool.HEIGHT_RAISE, "Raise", "Raise terrain under the brush"),
            (MapEditTool.HEIGHT_LOWER, "Lower", "Lower terrain under the brush"),
        )
        bx = x
        for tool, label, tip in tools_h:
            tw = 54 if label != "Raise" else 58
            self._draw_labelled_tool_button(
                content,
                bx,
                y,
                tw,
                btn_h,
                label,
                f"edit_tool:{tool.value}",
                tip,
                active=map_edit_tool == tool,
                local_mouse=local_mouse,
            )
            bx += tw + gap
        y += btn_h + 8

        height_tools = {
            MapEditTool.HEIGHT_SET,
            MapEditTool.HEIGHT_RAISE,
            MapEditTool.HEIGHT_LOWER,
        }
        if map_edit_tool in height_tools:
            if map_edit_tool == MapEditTool.HEIGHT_SET:
                y = _blit_text(
                    content,
                    self.font_small,
                    f"Paint height: {height_paint_value:.0f}",
                    (x, y),
                    COLOUR_TEXT,
                )
                row = (
                    ("−", "edit_value:-1", "Decrease paint height"),
                    ("+", "edit_value:+1", "Increase paint height"),
                    ("0", "edit_value:0", "Set paint height to 0"),
                )
            else:
                y = _blit_text(
                    content,
                    self.font_small,
                    f"Step: {height_delta_step:.0f}",
                    (x, y),
                    COLOUR_TEXT,
                )
                row = (
                    ("−", "edit_delta:-1", "Decrease raise/lower step"),
                    ("+", "edit_delta:+1", "Increase raise/lower step"),
                )
            bx = x
            for glyph, action, tip in row:
                self._register_tool_button(
                    content,
                    pygame.Rect(bx, y, 22, 22),
                    glyph,
                    action,
                    tip,
                    active=False,
                    local_mouse=local_mouse,
                )
                bx += 26
            y += 28

        y = _blit_text(content, self.font_title, "Terrain", (x, y))
        tools_t = (
            (MapEditTool.TERRAIN_PAINT, "Paint", "Paint the selected terrain type"),
            (MapEditTool.SEED_FOREST, "Forest", "Seed mixed trees + forest floor"),
        )
        bx = x
        for tool, label, tip in tools_t:
            self._draw_labelled_tool_button(
                content,
                bx,
                y,
                64,
                btn_h,
                label,
                f"edit_tool:{tool.value}",
                tip,
                active=map_edit_tool == tool,
                local_mouse=local_mouse,
            )
            bx += 68
        y += btn_h + 8

        if map_edit_tool == MapEditTool.TERRAIN_PAINT:
            y = _blit_text(content, self.font_small, "Terrain type", (x, y), COLOUR_TEXT_DIM)
            col_w = (PANEL_WIDTH - 28) // 2
            col = 0
            row_y = y
            for terrain in EDIT_PAINTABLE_TERRAIN:
                label = TERRAIN_EDIT_LABELS.get(terrain, terrain.name.title())
                tx = x + col * (col_w + 4)
                self._draw_labelled_tool_button(
                    content,
                    tx,
                    row_y,
                    col_w,
                    btn_h,
                    label,
                    f"edit_terrain:{terrain.name}",
                    f"Paint {label}",
                    active=map_edit_terrain == terrain,
                    local_mouse=local_mouse,
                )
                col += 1
                if col >= 2:
                    col = 0
                    row_y += btn_h + gap
            if col != 0:
                row_y += btn_h + gap
            y = row_y + 4

        y = _blit_text(
            content,
            self.font_small,
            f"Brush radius: {height_brush_radius}",
            (x, y),
            COLOUR_TEXT,
        )
        bx = x
        for glyph, action, tip in (
            ("[", "edit_brush:-1", "Shrink brush"),
            ("]", "edit_brush:+1", "Grow brush"),
        ):
            self._register_tool_button(
                content,
                pygame.Rect(bx, y, 22, 22),
                glyph,
                action,
                tip,
                active=False,
                local_mouse=local_mouse,
            )
            bx += 26
        y += 30

        y = _blit_text(content, self.font_title, "Status", (x, y))
        return y

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
        label = _ellipsize(self.font_small, text, max_text_w)

        colour = COLOUR_TEXT if selected else COLOUR_TEXT_DIM
        surface.blit(_cached_font_surf(self.font_small, label, colour), (x, y + 2))
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
        season: Season | None = None,
    ) -> list[tuple[str, str, str, bool]]:
        plan = villager.active_workplace_plan(season)
        while len(plan) < 3:
            plan.append(WorkplaceSlot())
        glyphs = {
            WorkPriority.LABOURER: "L",
            WorkPriority.WORKPLACE: "W",
            WorkPriority.NONE: "·",
            WorkPriority.BUILD: "L",
            WorkPriority.TRANSPORT: "L",
        }
        btns: list[tuple[str, str, str, bool]] = []
        for slot in range(3):
            mode = plan[slot].normalized().kind
            tip = f"P{slot + 1}: {PRIORITY_LABELS.get(mode, '—')} (click to assign building)"
            btns.append((glyphs.get(mode, "·"), f"prio:{villager.id}:{slot}", tip, False))
        btns.append(
            (
                "→",
                "assign_workplace",
                "Assign workplace — pick building (storehouse = labourer)",
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
        job_colour: tuple[int, int, int] | None = None,
        season: Season | None = None,
    ) -> int:
        from villager_roster import draw_portrait, draw_status_bar

        row_h = 36
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
            trailing = self._inline_priority_buttons(
                villager, assign_workplace_mode, season
            ) + trailing

        btn_space = 0
        for glyph, _a, _t, _act in trailing:
            btn_w = max(self._ICON_SIZE, 8 + _cached_font_width(self.font_small, glyph))
            btn_space += btn_w + 3
        btn_space += 4
        draw_portrait(
            surface,
            x + 10,
            y + row_h // 2,
            int(getattr(villager, "portrait_seed", 0) or villager.id * 9973),
            size=20,
            job_colour=job_colour,
        )
        text_x = x + 24
        max_text_w = PANEL_WIDTH - 48 - btn_space
        text = _ellipsize(self.font_small, label, max_text_w)

        colour = COLOUR_TEXT if selected else COLOUR_TEXT_DIM
        surface.blit(_cached_font_surf(self.font_small, text, colour), (text_x, y + 2))
        self.list_hits.append((row, "villager", villager.id))

        bar_y = y + 20
        draw_status_bar(surface, text_x, bar_y, 32, 5, villager.energy, kind="energy")
        draw_status_bar(
            surface, text_x + 36, bar_y, 32, 5, villager.satiation, kind="sat"
        )
        draw_status_bar(
            surface, text_x + 72, bar_y, 32, 5, villager.happiness, kind="happy"
        )
        tip = (
            f"E {int(villager.energy * 100)}% · "
            f"Sat {int(villager.satiation * 100)}% · "
            f"Happy {int(villager.happiness * 100)}%"
        )
        bar_rect = pygame.Rect(text_x, bar_y, 104, 5)
        if local_mouse is not None and bar_rect.collidepoint(local_mouse):
            self._tooltip = (tip, (bar_rect.centerx, bar_rect.top))

        bx = x + PANEL_WIDTH - 28
        for glyph, action, tip, active in reversed(trailing):
            bw = max(self._ICON_SIZE, 8 + self.font_small.size(glyph)[0])
            bx -= bw + 3
            rect = pygame.Rect(bx, y + (row_h - self._ICON_SIZE) // 2, bw, self._ICON_SIZE)
            hovered = local_mouse is not None and rect.collidepoint(local_mouse)
            self._draw_icon_button(surface, rect, glyph, active=active, hovered=hovered)
            self.action_hits.append((rect, action, tip))
            if hovered:
                self._tooltip = (tip, (rect.centerx, rect.top))
        return y + row_h + 2

    def _draw_normal_panel_body(
        self,
        content: pygame.Surface,
        x: int,
        y: int,
        *,
        world: World,
        player: Player,
        home_storage: HomeStorage,
        villagers: list[Villager],
        buildings: dict[int, Building],
        wildlife: WildlifeManager,
        selected_building_id: int | None,
        selected_villager_id: int | None,
        overlay_mode: OverlayMode,
        status_message: str,
        sim_speed: int,
        ticks_per_day: int,
        playback_ticks: int,
        walk_seconds: float,
        work_seconds: float,
        fish_manager: FishManager | None,
        construction_sites: dict[int, ConstructionSite] | None,
        assign_workplace_mode: bool,
        local_mouse: tuple[int, int] | None,
        season: Season,
        calendar_day: int,
        selected_habitat_kind: AnimalKind | None,
        selected_habitat_id: int | None,
    ) -> int:
        y = _blit_text(content, self.font_title, "Environment Sandbox", (x, y))
        y = _blit_text(content, self.font_small, "WASD · Enter/E · Y map edit · H habitats", (x, y), COLOUR_TEXT_DIM)
        y = _blit_text(content, self.font_small, f"Speed x{sim_speed}" if sim_speed else "Paused", (x, y), COLOUR_TEXT_DIM)
        day_secs = ticks_to_seconds(ticks_per_day, playback_ticks)
        tiles = ticks_per_day / max(1, seconds_to_ticks(walk_seconds, playback_ticks)) if walk_seconds else 0
        y = _blit_text(
            content,
            self.font_small,
            f"Day {day_secs:g}s at ×1   [ ] change",
            (x, y),
            COLOUR_TEXT_DIM,
        )
        y = _blit_text(
            content,
            self.font_small,
            f"Walk {walk_seconds:.2f}s/tile  ·  ~{tiles:.0f}/day",
            (x, y),
            COLOUR_TEXT_DIM,
        )
        y = _blit_text(
            content,
            self.font_small,
            f"Work {work_seconds:.2f}s/action  ·  File→Balance",
            (x, y),
            COLOUR_TEXT_DIM,
        )
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
                    phase = site.phase_label() if hasattr(site, "phase_label") else ""
                    y = self._draw_list_row(
                        content,
                        f"Site {BUILDING_LABELS[site.kind]} {phase}".strip(),
                        x,
                        y,
                        selected=selected_habitat_id is None
                        and False,  # selection via Management / map
                        hit_kind="construction",
                        hit_id=site.id,
                        local_mouse=local_mouse,
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
                        f"{b.capacity_label()} · {workers}w · "
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
        from society import housed_count

        housed = housed_count(villagers)
        y = _blit_text(
            content,
            self.font_small,
            f"Hired {len(villagers)}/{MAX_VILLAGERS}  ·  Housing {housed}/{len(villagers)}",
            (x, y),
            COLOUR_TEXT_DIM,
        )
        open_w = 12 + self.font_small.size("Table…")[0]
        self._draw_labelled_tool_button(
            content,
            x,
            y,
            open_w,
            18,
            "Table…",
            "open_villager_roster",
            "Open sortable villager table",
            active=False,
            local_mouse=local_mouse,
        )
        y += 22
        from villager_roster import villager_job_colour

        for v in villagers:
            if v.assigned_to_home:
                job = "home"
            elif v.building_id and v.building_id in buildings:
                job = BUILDING_LABELS[buildings[v.building_id].kind][:4]
            else:
                job = "free"
            selected = selected_villager_id == v.id
            state = "EAT" if v.seeking_food else v.state.name[:4]
            name = getattr(v, "name", None) or f"#{v.id}"
            y = self._draw_villager_row(
                content,
                v,
                f"{name} {state} → {job}",
                x,
                y,
                selected=selected,
                assign_workplace_mode=assign_workplace_mode,
                local_mouse=local_mouse,
                job_colour=villager_job_colour(v, buildings),
                season=season,
            )
        y += 4

        y = _blit_text(content, self.font_title, "World", (x, y))
        wild_line = (
            f"Deer {len(wildlife.deer())}  Boar {len(wildlife.boars())}  "
            f"Wolf {wildlife.wolf_count()}  "
            f"Bee {len(wildlife.bee_colonies())}c/"
            f"{wildlife.colony_members_total(AnimalKind.BEE)}  "
            f"Rabbit {len(wildlife.rabbit_colonies())}c/"
            f"{wildlife.colony_members_total(AnimalKind.RABBIT)}"
        )
        if fish_manager is not None:
            wild_line += (
                f" · Fish {len(fish_manager.fish)}/"
                f"{fish_manager.total_capacity(world)}"
            )
        y = _blit_text(content, self.font_small, wild_line, (x, y), COLOUR_TEXT_DIM)

        def _draw_grounds(
            title: str,
            kind: AnimalKind,
            hit_kind: str,
            cap_attr: str,
            y: int,
        ) -> int:
            y = _blit_text(content, self.font_small, title, (x, y), COLOUR_TEXT_DIM)
            grounds = wildlife.breeding_grounds(kind)
            if not grounds:
                return _blit_text(
                    content, self.font_small, "  none", (x, y), COLOUR_TEXT_DIM
                )
            for hab in grounds:
                selected = (
                    selected_habitat_kind == kind and selected_habitat_id == hab.id
                )
                if kind in (AnimalKind.BEE, AnimalKind.RABBIT):
                    colony = wildlife._colony_on_habitat(kind, hab.id)
                    if colony is None:
                        label = f"  #{hab.id}  empty"
                    else:
                        label = (
                            f"  #{hab.id}  L{colony.level}  "
                            f"{colony.target_members()} visible"
                        )
                else:
                    _present, migrating, total, pairs = wildlife.patch_occupancy(
                        kind, hab.id
                    )
                    pair_txt = f"{pairs} pair" if pairs == 1 else f"{pairs} pairs"
                    cap = getattr(hab, cap_attr)
                    if migrating:
                        label = (
                            f"  #{hab.id}  {total}/{cap}  "
                            f"{pair_txt}  {migrating} migrating"
                        )
                    else:
                        label = f"  #{hab.id}  {total}/{cap}  {pair_txt}"
                y = self._draw_list_row(
                    content,
                    label,
                    x,
                    y,
                    selected=selected,
                    hit_kind=hit_kind,
                    hit_id=hab.id,
                )
            return y

        y = _draw_grounds("Deer grounds", AnimalKind.DEER, "deer_ground", "deer_cap", y)
        y = _draw_grounds("Boar grounds", AnimalKind.BOAR, "boar_ground", "boar_cap", y)
        y = _draw_grounds("Bee nests", AnimalKind.BEE, "bee_ground", "bee_cap", y)
        y = _draw_grounds(
            "Rabbit nests", AnimalKind.RABBIT, "rabbit_ground", "rabbit_cap", y
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

        return y

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
        ticks_per_day: int = 480,
        playback_ticks: int = PLAYBACK_TICKS_AT_X1,
        walk_seconds: float = WALK_SECONDS_AT_X1,
        work_seconds: float = WORK_SECONDS_AT_X1,
        fish_manager: FishManager | None = None,
        construction_sites: dict[int, ConstructionSite] | None = None,
        assign_workplace_mode: bool = False,
        mouse_pos: tuple[int, int] | None = None,
        season: Season = Season.SPRING,
        calendar_day: int = 0,
        selected_field_id: int | None = None,
        selected_habitat_kind: AnimalKind | None = None,
        selected_habitat_id: int | None = None,
        map_edit_mode: bool = False,
        map_edit_tool: MapEditTool = MapEditTool.HEIGHT_SET,
        map_edit_terrain: TerrainType = TerrainType.GRASS,
        height_paint_value: float = 20.0,
        height_delta_step: float = 2.0,
        height_brush_radius: int = 2,
    ) -> None:
        panel_x = map_view_width()
        panel_h = _panel_height()
        self.priority_hits = []
        self.list_hits = []
        self.action_hits = []
        self._tooltip = None
        self.expand_tab_rect = None

        if PANEL_COLLAPSED:
            # Slim restore tab on the right edge of the map.
            tab = pygame.Rect(WINDOW_WIDTH - 22, MAP_OFFSET_Y + 8, 18, 52)
            self.expand_tab_rect = tab
            hovered = mouse_pos is not None and tab.collidepoint(mouse_pos)
            colour = (70, 78, 92) if hovered else COLOUR_TOOLBAR_BTN
            pygame.draw.rect(surface, colour, tab, border_top_left_radius=4, border_bottom_left_radius=4)
            pygame.draw.rect(
                surface,
                COLOUR_TOOLBAR_BORDER,
                tab,
                1,
                border_top_left_radius=4,
                border_bottom_left_radius=4,
            )
            tip = self.font_icon.render("◀", True, COLOUR_TEXT)
            surface.blit(
                tip,
                (
                    tab.x + (tab.w - tip.get_width()) // 2,
                    tab.y + (tab.h - tip.get_height()) // 2,
                ),
            )
            if hovered:
                self._tooltip = ("Show sidebar (Tab)", mouse_pos or tab.center)
                self._draw_tooltip(surface, "Show sidebar (Tab)", mouse_pos or tab.center)
            return

        mouse_over = mouse_pos is not None and mouse_pos[0] >= panel_x
        fp = (
            calendar_day,
            selected_building_id,
            selected_villager_id,
            selected_habitat_kind,
            selected_habitat_id,
            overlay_mode,
            sim_speed,
            assign_workplace_mode,
            status_message,
            map_edit_mode,
            place_kind,
        )
        wait = getattr(self, "_panel_rebuild_wait", 0)
        if (
            not mouse_over
            and getattr(self, "_panel_fp", None) == fp
            and wait > 0
            and getattr(self, "_panel_built", False)
        ):
            self._panel_rebuild_wait = wait - 1
            self._blit_panel_to_screen(surface, panel_x, panel_h)
            return
        self._panel_rebuild_wait = 4
        self._panel_fp = fp
        self._panel_built = True

        content = self._ensure_content_surface(max(self.content_height, panel_h + 200))
        content.fill(COLOUR_PANEL_BG)

        local_mouse: tuple[int, int] | None = None
        if mouse_pos is not None:
            local_mouse = self._local_pos(mouse_pos)

        # Collapse control at top of sidebar.
        collapse = pygame.Rect(PANEL_WIDTH - 28, 6, 20, 20)
        collapse_hov = local_mouse is not None and collapse.collidepoint(local_mouse)
        self._draw_icon_button(
            content, collapse, "▶", hovered=collapse_hov
        )
        self.action_hits.append(
            (collapse, "toggle_panel", "Hide sidebar (Tab)")
        )
        if collapse_hov:
            self._tooltip = ("Hide sidebar (Tab)", (collapse.centerx, collapse.bottom + 4))
        x = 10
        y = 8

        if map_edit_mode:
            y = self._draw_map_edit_panel(
                content,
                x,
                y,
                map_edit_tool=map_edit_tool,
                map_edit_terrain=map_edit_terrain,
                height_paint_value=height_paint_value,
                height_delta_step=height_delta_step,
                height_brush_radius=height_brush_radius,
                local_mouse=local_mouse,
            )
            msg = status_message if status_message else "—"
            colour = COLOUR_STATUS if status_message else COLOUR_TEXT_DIM
            for line in _wrap(msg, 30):
                y = _blit_text(content, self.font_small, line, (x, y), colour)
            y += 12
        else:
            y = self._draw_normal_panel_body(
                content,
                x,
                y,
                world=world,
                player=player,
                home_storage=home_storage,
                villagers=villagers,
                buildings=buildings,
                wildlife=wildlife,
                selected_building_id=selected_building_id,
                selected_villager_id=selected_villager_id,
                overlay_mode=overlay_mode,
                status_message=status_message,
                sim_speed=sim_speed,
                ticks_per_day=ticks_per_day,
                playback_ticks=playback_ticks,
                walk_seconds=walk_seconds,
                work_seconds=work_seconds,
                fish_manager=fish_manager,
                construction_sites=construction_sites,
                assign_workplace_mode=assign_workplace_mode,
                local_mouse=local_mouse,
                season=season,
                calendar_day=calendar_day,
                selected_habitat_kind=selected_habitat_kind,
                selected_habitat_id=selected_habitat_id,
            )

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
                ticks_per_day=ticks_per_day,
                playback_ticks=playback_ticks,
                walk_seconds=walk_seconds,
                work_seconds=work_seconds,
                fish_manager=fish_manager,
                construction_sites=construction_sites,
                assign_workplace_mode=assign_workplace_mode,
                mouse_pos=mouse_pos,
                season=season,
                calendar_day=calendar_day,
                selected_field_id=selected_field_id,
                selected_habitat_kind=selected_habitat_kind,
                selected_habitat_id=selected_habitat_id,
                map_edit_mode=map_edit_mode,
                map_edit_tool=map_edit_tool,
                map_edit_terrain=map_edit_terrain,
                height_paint_value=height_paint_value,
                height_delta_step=height_delta_step,
                height_brush_radius=height_brush_radius,
            )

        self.content_height = max(panel_h, y)
        self._blit_panel_to_screen(surface, panel_x, panel_h, mouse_pos)

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
            (COLOUR_CRAFT_BENCH, "Craft bench"),
            (COLOUR_ALCHEMIST, "Alchemist"),
            (COLOUR_TAILOR, "Tailor"),
            (COLOUR_COBBLER, "Cobbler"),
            (COLOUR_MARKET, "Market"),
            ((90, 90, 70), "Site"),
            (COLOUR_PLAYER, "Player"),
            (COLOUR_VILLAGER, "Villager"),
            (COLOUR_ANIMAL, "Deer"),
            (COLOUR_BOAR, "Boar"),
            (COLOUR_BEE, "Bee"),
            (COLOUR_RABBIT, "Rabbit"),
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
        TerrainType.RIVER: COLOUR_WATER,
        TerrainType.ROCK: COLOUR_ROCK_TERRAIN,
        TerrainType.URBAN: COLOUR_URBAN,
        TerrainType.PATH: COLOUR_PATH,
    }[terrain]
    # Only standing lake water freezes — rivers stay open.
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
    if terrain in (TerrainType.WATER, TerrainType.RIVER):
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
    baked: bool = False,
) -> dict[str, tuple[int, int, int]]:
    """Map building SVG face classes to shaded colours from a wall/roof base.

    When ``baked`` is True (cabin-style icons with fills in the SVG), only
    accent / accent2 / stem are remapped so wall and roof colours from the
    file are preserved.
    """
    from seasons import adjust_colour

    if baked:
        out: dict[str, tuple[int, int, int]] = {}
        if accent is not None:
            out["accent"] = adjust_colour(accent, vibrancy)
        if accent2 is not None:
            out["accent2"] = adjust_colour(accent2, vibrancy)
        if stem is not None:
            out["stem"] = adjust_colour(stem, vibrancy)
        return out

    w = adjust_colour(wall, vibrancy)
    r = adjust_colour(roof if roof is not None else wall, vibrancy)
    out = {
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
    growth_ticks: int = 0,
    icon_base_override: str | None = None,
) -> None:
    if feature == FeatureType.NONE:
        return
    if feature == FeatureType.STRUCTURE_PAD:
        return
    # Quantize vibrancy so icon cache keys stay stable across fine day drift.
    # Step 0.25 → a few seasonal buckets/year instead of re-rasterising SVGs
    # on every small vibrancy nudge (very visible at low ticks/day).
    vibrancy = round(float(vibrancy) * 4.0) / 4.0
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
        ICON_CRAFT_BENCH,
        ICON_ALCHEMIST,
        ICON_TAILOR,
        ICON_COBBLER,
        ICON_MARKET,
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
        ICON_WOOD,
        ICON_WORKSTATION,
        blit_icon,
    )
    from settings import ICON_BUILDING_STIPPLE
    from trees import resolve_tree

    def blit_building(*args, **kwargs):
        kwargs.setdefault("stipple", bool(ICON_BUILDING_STIPPLE))
        return blit_icon(*args, **kwargs)

    if icon_base_override:
        blit_icon(surface, icon_base_override, cx, cy, size, variant=icon_variant)
        return

    trunk = adjust_colour(COLOUR_TREE_TRUNK, vibrancy)
    v = icon_variant

    if feature == FeatureType.TREE:
        tree = resolve_tree(tree_species)
        base = ICON_TREE_CONE if tree.shape == "cone" else ICON_TREE_ROUND
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
        blit_building(
            surface,
            ICON_HOME,
            cx,
            cy,
            size,
            variant=v,
            recolour=_iso_building_recolour(
                COLOUR_HOME, roof=COLOUR_HOME_ROOF, vibrancy=vibrancy,
                baked=True,
            ),
        )
    elif feature == FeatureType.WORKSTATION:
        blit_building(
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
                baked=True,
            ),
        )
    elif feature == FeatureType.FORESTER:
        blit_building(
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
                baked=True,
            ),
        )
    elif feature == FeatureType.MASON:
        blit_building(
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
                baked=True,
            ),
        )
    elif feature == FeatureType.HUNTER:
        blit_building(
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
                baked=True,
            ),
        )
    elif feature == FeatureType.FORAGER:
        blit_building(
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
                baked=True,
            ),
        )
    elif feature == FeatureType.CONSTRUCTION_SITE:
        blit_building(
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
                baked=True,
            ),
        )
    elif feature == FeatureType.FISHER:
        blit_building(
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
                baked=True,
            ),
        )
    elif feature == FeatureType.FARM:
        blit_building(
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
                baked=True,
            ),
        )
    elif feature == FeatureType.FIELD:
        blit_building(
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
                baked=True,
            ),
        )
    elif feature == FeatureType.MILL:
        blit_building(
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
                baked=True,
            ),
        )
    elif feature == FeatureType.KITCHEN:
        blit_building(
            surface,
            ICON_KITCHEN,
            cx,
            cy,
            size,
            variant=v,
            recolour=_iso_building_recolour(
                COLOUR_KITCHEN,
                roof=(120, 50, 40),
                accent=(232, 120, 64),
                accent2=(240, 192, 96),
                vibrancy=vibrancy,
                baked=True,
            ),
        )
    elif feature == FeatureType.CRAFT_BENCH:
        blit_building(
            surface,
            ICON_CRAFT_BENCH,
            cx,
            cy,
            size,
            variant=v,
            recolour=_iso_building_recolour(
                COLOUR_CRAFT_BENCH,
                roof=(100, 70, 45),
                accent=(200, 170, 110),
                vibrancy=vibrancy,
                baked=True,
            ),
        )
    elif feature == FeatureType.ALCHEMIST:
        blit_building(
            surface,
            ICON_ALCHEMIST,
            cx,
            cy,
            size,
            variant=v,
            recolour=_iso_building_recolour(
                COLOUR_ALCHEMIST,
                roof=(70, 40, 100),
                accent=(200, 160, 230),
                vibrancy=vibrancy,
                baked=True,
            ),
        )
    elif feature == FeatureType.TAILOR:
        blit_building(
            surface,
            ICON_TAILOR,
            cx,
            cy,
            size,
            variant=v,
            recolour=_iso_building_recolour(
                COLOUR_TAILOR,
                roof=(50, 70, 100),
                accent=(180, 200, 220),
                vibrancy=vibrancy,
                baked=True,
            ),
        )
    elif feature == FeatureType.COBBLER:
        blit_building(
            surface,
            ICON_COBBLER,
            cx,
            cy,
            size,
            variant=v,
            recolour=_iso_building_recolour(
                COLOUR_COBBLER,
                roof=(70, 50, 35),
                accent=(200, 170, 130),
                vibrancy=vibrancy,
                baked=True,
            ),
        )
    elif feature == FeatureType.MARKET:
        blit_building(
            surface,
            ICON_MARKET,
            cx,
            cy,
            size,
            variant=v,
            recolour=_iso_building_recolour(
                COLOUR_MARKET,
                roof=(120, 70, 40),
                accent=(220, 180, 100),
                vibrancy=vibrancy,
                baked=True,
            ),
        )
    elif feature == FeatureType.TENT:
        blit_building(surface, "tent", cx, cy, size, variant=v)
    elif feature == FeatureType.HOUSE_SMALL:
        blit_building(surface, "house_small", cx, cy, size, variant=v)
    elif feature == FeatureType.HOUSE:
        blit_building(surface, "house", cx, cy, size, variant=v)
    elif feature == FeatureType.COMMUNITY:
        blit_building(surface, "tent", cx, cy, size, variant=v)
    elif feature in (
        FeatureType.MUSHROOM,
        FeatureType.WOOD_BUSH,
        FeatureType.BERRY_BUSH,
        FeatureType.REED,
    ):
        import wild_species as wild_catalogue
        from wild_species import icon_recolour_for, resolve_species

        species = resolve_species(feature.name, crop_kind)
        if species is not None and species.icon_base:
            recolour = {
                cls: adjust_colour(rgb, vibrancy)
                for cls, rgb in icon_recolour_for(species, deposit=deposit).items()
            }
            blit_icon(
                surface,
                species.icon_base,
                cx,
                cy,
                size,
                variant=v,
                recolour=recolour,
                omit_classes=getattr(wild_catalogue,"WILD_ICON_OMIT_BY_KEY",{}).get(species.key,()),
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
        elif feature == FeatureType.WOOD_BUSH:
            blit_icon(
                surface,
                ICON_WOOD,
                cx,
                cy,
                size,
                variant=v,
                recolour={
                    "body": adjust_colour((120, 90, 50), vibrancy),
                    "leaf": adjust_colour((70, 130, 55), vibrancy),
                },
            )
        elif feature == FeatureType.BERRY_BUSH:
            berry_colour = (
                adjust_colour(COLOUR_BERRY, vibrancy)
                if deposit > 0
                else adjust_colour((70, 95, 55), vibrancy)
            )
            blit_icon(
                surface,
                ICON_BERRY_BUSH,
                cx,
                cy,
                size,
                variant=v,
                recolour={
                    "bush": adjust_colour((50, 110, 50), vibrancy),
                    "berry": berry_colour,
                },
            )
        else:
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
        import wild_species as wild_catalogue
        from wild_species import icon_recolour_for, resolve_species

        species = resolve_species(feature.name, crop_kind)
        # Farmed crops always use CropDef so growth can switch sparse/dense art
        # and retain the crop's stem/flower palette. Explicit Wild Species
        # presentation applies only to genuinely wild map plants.
        if feature != FeatureType.CROP_HERB and species is not None and species.icon_base:
            recolour = {
                cls: adjust_colour(rgb, vibrancy)
                for cls, rgb in icon_recolour_for(species, deposit=deposit).items()
            }
            blit_icon(
                surface,
                species.icon_base,
                cx,
                cy,
                size,
                variant=v,
                recolour=recolour,
                omit_classes=getattr(wild_catalogue,"WILD_ICON_OMIT_BY_KEY",{}).get(species.key,()),
            )
        else:
            crop = CROP_BY_KEY.get(crop_kind or "sage") or CROP_BY_KEY["sage"]
            stem = adjust_colour(crop.stem_colour, vibrancy)
            # Farm crops look sparse while growing; dense only when ready to harvest.
            ripe = feature != FeatureType.CROP_HERB or growth_ticks <= 0
            name = crop.plant_icon(dense=ripe and feature == FeatureType.CROP_HERB)
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
