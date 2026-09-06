"""Central management window: People / Buildings / Wildlife / Flora.

Left pane = selected entity detail; right pane = list. Independent pane
toggles keep at least one pane visible. Villager/building selection opens
this window; wildlife habitats inspect in the Wildlife detail pane
(H habitat view also selects into this pane).
"""

from __future__ import annotations

from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable

import pygame

from entities import BUILDING_LABELS, Building, BuildingKind, ConstructionSite, Villager
from extensions import is_extension_kind, linked_extensions
from habitat_inspect_dialog import HabitatInspectView
from icons import blit_icon
from settings import (
    COLOUR_SELECTED_ENTITY,
    COLOUR_TEXT as UI_TEXT,
    COLOUR_TOOLBAR_BORDER,
    COLOUR_TOOLBAR_BTN,
    COLOUR_TOOLBAR_BTN_ACTIVE,
    COLOUR_TOOLBAR_BTN_HOVER,
    FARM_FIELD_RADIUS,
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
from crops import CROP_BY_KEY
from trees import TREES, TREE_BY_KEY, TreeDef
from wild_species import WILD_BY_KEY, WILD_SPECIES, WildSpeciesDef

TITLE_BAR_H = 32
TAB_H = 36
PANE_BTN_H = 26
PAD = 10
LIST_ROW_H = 36

# Management content is drawn directly on pale paper, unlike the other dark
# overlays.  Keep its copy legible while controls/tooltips retain UI colours.
COLOUR_TEXT = (72, 48, 31)
COLOUR_TEXT_DIM = (112, 84, 58)
_BOOK_FONT_PATH = (
    Path(__file__).resolve().parent
    / "assets/fonts/Gloria_Hallelujah/GloriaHallelujah-Regular.ttf"
)

# The three book variants use the same authored coordinate system and spine at
# x=160.  The single-page SVGs are positioned relative to that line rather than
# stretched edge-to-edge; this keeps the spine on the pane boundary.
_BOOK_DIR = Path(__file__).resolve().parent / "assets" / "UI"
_BOOK_PATHS = {
    "both": _BOOK_DIR / "book.svg",
    "detail": _BOOK_DIR / "book_left.svg",
    "list": _BOOK_DIR / "book_right.svg",
}
_BOOK_NATIVE_SIZE = (320, 250)
_BOOK_VIEWBOX_Y = -40
_BOOK_SPINE_X = 160
_BOOK_PAGE_BOUNDS = {
    "detail": (15, -5, 135, 190),
    "list": (175, -5, 135, 190),
}
_BOOK_TAB_POLYGONS = (
    ((12.9, 12.2), (32.7, 9.0), (32.6, 31.7), (12.8, 35.8)),
    ((32.7, 9.0), (57.7, 7.0), (56.3, 28.9), (32.6, 31.7)),
    ((57.7, 7.0), (83.1, 6.3), (83.4, 28.0), (56.3, 28.9)),
    ((83.1, 6.3), (110.8, 6.5), (109.6, 28.3), (83.4, 28.0)),
)
_PLAYER_TAB_POLYGON = (
    (110.8, 6.5), (141.5, 8.5), (141.5, 32.0), (109.6, 28.3)
)


class MgmtTab(Enum):
    PEOPLE = auto()
    BUILDINGS = auto()
    WILDLIFE = auto()
    FLORA = auto()
    PLAYER = auto()


_TAB_META: dict[MgmtTab, tuple[str, str]] = {
    MgmtTab.PEOPLE: ("villager", "People"),
    MgmtTab.BUILDINGS: ("construction_site", "Buildings"),
    MgmtTab.WILDLIFE: ("deer_male", "Wildlife"),
    MgmtTab.FLORA: ("flower_plant", "Flora"),
    MgmtTab.PLAYER: ("player_portrait", "Player"),
}


def _flora_icon(species: WildSpeciesDef | TreeDef) -> str:
    if isinstance(species, TreeDef):
        return "tree_cone" if species.shape == "cone" else "tree_round"
    if species.icon_base:
        return species.icon_base
    crop = CROP_BY_KEY.get(species.crop_key or species.key)
    return crop.icon_base if crop is not None else "flower_plant"


def _season_name(day: float) -> str:
    return ("Spring", "Summer", "Autumn", "Winter")[int(day) % 112 // 28]


def _window_text(start: tuple[float, float], end: tuple[float, float]) -> str:
    return f"{_season_name(start[0])} to {_season_name(end[1])}"


def _niche_text(species: WildSpeciesDef) -> str:
    terrain = ", ".join(t.replace("_", " ").title() for t in species.terrains)
    if species.edge_terrains:
        edges = ", ".join(t.replace("_", " ").title() for t in species.edge_terrains)
        terrain += f", beside {edges}"
    preferences: list[str] = []
    for label, niche in (("moisture", species.moisture_niche),
                         ("fertility", species.fertility_niche),
                         ("disturbance", species.disturbance_niche)):
        if niche is None:
            continue
        mid = (niche.optimum_low + niche.optimum_high) / 2
        level = "low" if mid < .36 else "moderate" if mid < .68 else "high"
        preferences.append(f"{level} {label}")
    suffix = f"; prefers {', '.join(preferences)}" if preferences else ""
    return f"Found on {terrain}{suffix}."


def _wild_description(species: WildSpeciesDef) -> str:
    kinds = {
        "BERRY_BUSH": "A perennial fruiting shrub",
        "REED": "A waterside perennial",
        "MUSHROOM": "A seasonal woodland fungus",
        "WOOD_BUSH": "Fallen woody vegetation",
        "WILD_CROP": "A feral crop plant",
        "HERB": "A wild herbaceous plant",
    }
    return f"{kinds.get(species.feature, 'A wild plant')} in the world ecosystem."


def _growth_text(species: WildSpeciesDef | TreeDef) -> str:
    if isinstance(species, TreeDef):
        return f"Saplings mature in about {species.growth_years:g} year(s)."
    if species.fruiting:
        return f"Permanent growth; fruits {_window_text(species.fruit_rise, species.fruit_fall)}."
    if species.spawn_peak <= 0:
        return "Persistent growth with no seasonal establishment window."
    active = _window_text(species.spawn_rise, species.spawn_fall)
    if species.clear_from_day >= 0:
        return f"Appears {active}; clears in {_season_name(species.clear_from_day)}."
    return f"Active growth from {active}."


def _uses_text(species: WildSpeciesDef | TreeDef) -> str:
    if isinstance(species, TreeDef):
        wood = species.yield_key.replace("_", " ")
        return f"Forestry: yields {species.yield_amount} {wood}; saplings can be replanted."
    uses: list[str] = []
    if species.resource_key and species.yield_amount > 0:
        uses.append(f"harvested for {species.yield_amount} {species.resource_key.replace('_', ' ')}")
    tag_uses = {
        "flowering": "supports flowers", "pollinator_food": "feeds pollinators",
        "grazer_forage": "feeds grazing wildlife", "wetland_cover": "provides wetland cover",
        "amphibian_habitat": "shelters amphibians", "feral_crop": "provides wild seed stock",
    }
    uses.extend(tag_uses[tag] for tag in species.ecology_tags if tag in tag_uses)
    return ("; ".join(uses).capitalize() + ".") if uses else "Ecological ground cover; not harvestable."

_BUILD_ICON: dict[BuildingKind, str] = {
    BuildingKind.FIRE: "fire",
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
    BuildingKind.COMPOST_HEAP: "compost",
    BuildingKind.PANTRY: "pantry",
    BuildingKind.CELLAR: "cellar",
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


def _chebyshev_to_plot(
    farm: Building, left: int, top: int, right: int, bottom: int
) -> int:
    fcx, fcy = farm.center_cell()
    cx = min(max(fcx, left), right)
    cy = min(max(fcy, top), bottom)
    return max(abs(cx - fcx), abs(cy - fcy))


def _nearest_farm(
    buildings: dict[int, Building], left: int, top: int, right: int, bottom: int
) -> Building | None:
    best: Building | None = None
    best_d = FARM_FIELD_RADIUS + 1
    for farm in buildings.values():
        if farm.kind != BuildingKind.FARM:
            continue
        d = _chebyshev_to_plot(farm, left, top, right, bottom)
        if d < best_d:
            best = farm
            best_d = d
    return best if best_d <= FARM_FIELD_RADIUS else None


def _fields_for_farm(
    farm: Building, buildings: dict[int, Building]
) -> list[Building]:
    out: list[Building] = []
    for b in buildings.values():
        if b.kind != BuildingKind.FIELD:
            continue
        left, top, right, bottom = b.plot_bounds()
        home = _nearest_farm(buildings, left, top, right, bottom)
        if home is not None and home.id == farm.id:
            out.append(b)
    out.sort(key=lambda b: b.id)
    return out


def _iter_building_list_rows(
    buildings: dict[int, Building], sites: dict[int, ConstructionSite]
) -> list[tuple[str, object, int]]:
    """Yield (kind, entity, indent) for the Buildings list.

    Fields nest under the nearest farm; extensions (and their sites) nest
    under their parent workplace. Orphan fields stay top-level.
    """
    nested_building_ids: set[int] = set()
    nested_site_ids: set[int] = set()
    rows: list[tuple[str, object, int]] = []

    for b in buildings.values():
        if is_extension_kind(b.kind):
            if b.parent_building_id is not None and b.parent_building_id in buildings:
                nested_building_ids.add(b.id)
        elif b.kind == BuildingKind.FIELD:
            left, top, right, bottom = b.plot_bounds()
            if _nearest_farm(buildings, left, top, right, bottom) is not None:
                nested_building_ids.add(b.id)
    for site in sites.values():
        parent_id = getattr(site, "parent_building_id", None)
        if parent_id is not None and parent_id in buildings:
            nested_site_ids.add(site.id)
        elif site.kind == BuildingKind.FIELD:
            left, top, right, bottom = site.plot_bounds()
            if _nearest_farm(buildings, left, top, right, bottom) is not None:
                nested_site_ids.add(site.id)

    for site in sites.values():
        if site.id in nested_site_ids:
            continue
        rows.append(("construction", site, 0))

    top_level = [
        b
        for b in buildings.values()
        if b.id not in nested_building_ids
    ]
    top_level.sort(key=lambda b: (BUILDING_LABELS[b.kind], b.id))
    for b in top_level:
        rows.append(("building", b, 0))
        if b.kind == BuildingKind.FARM:
            for field in _fields_for_farm(b, buildings):
                rows.append(("building", field, 1))
            for site in sites.values():
                if site.kind != BuildingKind.FIELD or site.id not in nested_site_ids:
                    continue
                left, top, right, bottom = site.plot_bounds()
                home = _nearest_farm(buildings, left, top, right, bottom)
                if home is not None and home.id == b.id:
                    rows.append(("construction", site, 1))
        for ext in linked_extensions(b, buildings):
            rows.append(("building", ext, 1))
        for site in sites.values():
            if getattr(site, "parent_building_id", None) == b.id:
                rows.append(("construction", site, 1))
    return rows


class ManagementWindow:
    """Anchored central panel with tabs and dual panes."""

    def __init__(self) -> None:
        self.font = pygame.font.Font(str(_BOOK_FONT_PATH), 14)
        self.font_small = pygame.font.Font(str(_BOOK_FONT_PATH), 12)
        self.font_tiny = pygame.font.Font(str(_BOOK_FONT_PATH), 11)
        self.font_title = pygame.font.Font(str(_BOOK_FONT_PATH), 15)
        self.open = False
        self.tab = MgmtTab.PEOPLE
        self.show_detail: bool = True
        self.show_list: bool = True
        self.selected_villager_id: int | None = None
        self.selected_building_id: int | None = None
        self.selected_construction_id: int | None = None
        self.selected_habitat: tuple[Any, int] | None = None  # (AnimalKind, id)
        self.selected_flora_key: str | None = None
        self.show_player = False
        self.quest_navigation = None
        self.objectives_filter = "current"
        self.expanded_objective: str | None = None
        self._objective_scroll = 0
        self._objective_max_scroll = 0
        self._objective_focus: str | None = None
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
        self._book_scaled: tuple[str, tuple[int, int], pygame.Surface] | None = None
        # Nested inspect dialogs draw into detail pane when set by Game.
        self.embed_building_inspect = True
        self.embed_villager_inspect = True
        # Wildlife list filters
        self.wildlife_inhabited_only: bool = True
        self.wildlife_species: set[str] = {
            "DEER",
            "BOAR",
            "BEE",
            "RABBIT",
            "FROG",
            "VOLE",
            "WOLF",
            "FOX",
            "HAWK",
            "OWL",
        }

    def open_window(
        self,
        tab: MgmtTab = MgmtTab.PEOPLE,
        *,
        people_mode: str = "roster",
        assign_building_id: int | None = None,
        reset_scroll: bool | None = None,
    ) -> None:
        same_context = (
            self.open
            and self.tab == tab
            and self.people_mode == people_mode
            and self.assign_building_id == assign_building_id
        )
        self.open = True
        self.tab = tab
        self.people_mode = people_mode
        self.assign_building_id = assign_building_id
        self._pending_action = None
        if reset_scroll is None:
            reset_scroll = not same_context
        if reset_scroll:
            self._scroll = 0
        self._layout_panel()

    def open_people_list(self) -> None:
        """Open People tab with the villager roster list visible."""
        self.open_window(MgmtTab.PEOPLE, people_mode="roster", reset_scroll=True)
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
        same = (
            self.open
            and self.tab == MgmtTab.PEOPLE
            and self.people_mode == mode
            and self.assign_building_id == assign
        )
        self.open_window(
            MgmtTab.PEOPLE,
            people_mode=mode,
            assign_building_id=assign,
            reset_scroll=not same,
        )
        self.selected_villager_id = vid
        self.selected_building_id = None
        self.selected_construction_id = None
        self.selected_habitat = None
        self.show_player = show_player
        if detail_only:
            self.show_detail = True
            self.show_list = False
            self._layout_panel()

    def select_building(
        self, bid: int, *, show_player: bool = False, detail_only: bool = False
    ) -> None:
        same = self.open and self.tab == MgmtTab.BUILDINGS
        self.open_window(MgmtTab.BUILDINGS, reset_scroll=not same)
        self.selected_building_id = bid
        self.selected_construction_id = None
        self.selected_villager_id = None
        self.selected_habitat = None
        self.show_player = show_player
        if detail_only:
            self.show_detail = True
            self.show_list = False
            self._layout_panel()

    def select_construction(self, sid: int, *, detail_only: bool = False) -> None:
        same = self.open and self.tab == MgmtTab.BUILDINGS
        self.open_window(MgmtTab.BUILDINGS, reset_scroll=not same)
        self.selected_construction_id = sid
        self.selected_building_id = None
        self.selected_villager_id = None
        self.selected_habitat = None
        self.show_player = False
        if detail_only:
            self.show_detail = True
            self.show_list = False
            self._layout_panel()

    def select_habitat(self, kind: Any, patch_id: int) -> None:
        same = self.open and self.tab == MgmtTab.WILDLIFE
        self.open_window(MgmtTab.WILDLIFE, reset_scroll=not same)
        self.selected_habitat = (kind, patch_id)
        self.selected_building_id = None
        self.selected_construction_id = None
        self.selected_villager_id = None
        self.show_detail = True
        self.show_list = True
        self._layout_panel()

    def contains(self, pos: tuple[int, int]) -> bool:
        return self.open and self._panel.collidepoint(pos)

    def detail_rect(self) -> pygame.Rect:
        return self._detail_rect.copy()

    def list_rect(self) -> pygame.Rect:
        return self._list_rect.copy()

    def _people_actions(self) -> bool:
        return self.people_mode in ("hire", "assign")

    def _layout_panel(self) -> None:
        if self.tab == MgmtTab.PLAYER:
            self.show_detail = self.show_list = True
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
            w = min(400 if self.tab == MgmtTab.FLORA else 360, map_w - 40)

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
            if self.tab == MgmtTab.PLAYER and self._list_rect.collidepoint(pos):
                self._objective_scroll = max(0, min(self._objective_max_scroll,
                                                   self._objective_scroll - event.y * LIST_ROW_H))
                return True
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
                if action.startswith("objectives_filter:"):
                    self.objectives_filter = action.split(":", 1)[1]
                    self._objective_scroll = 0
                    return True
                if action.startswith('quest_group:'):
                    group = action.split(':', 1)[1]
                    choices = [row for row in self._quest_rows if row.get('group') == group]
                    if choices:
                        selected = next((row for row in choices if not row['completed']), choices[-1])
                        self.expanded_objective = selected['id']
                        if self.quest_navigation is not None:
                            self.quest_navigation.select(selected['id'])
                    return True
                if action.startswith("objective:"):
                    key = action.split(":", 1)[1]
                    self.expanded_objective = None if self.expanded_objective == key else key
                    if self.quest_navigation is not None:
                        self.quest_navigation.select(key)
                    return True
                if action == "toggle_detail":
                    if self.show_detail and not self.show_list:
                        return True
                    self.show_detail = not self.show_detail
                    self._layout_panel()
                    return True
                if action == "toggle_list":
                    if self.tab == MgmtTab.PLAYER:
                        return True
                    if self.show_list and not self.show_detail:
                        return True
                    self.show_list = not self.show_list
                    self._layout_panel()
                    return True
                if action == "wild_occ_inhabited":
                    self.wildlife_inhabited_only = True
                    self._scroll = 0
                    return True
                if action == "wild_occ_all":
                    self.wildlife_inhabited_only = False
                    self._scroll = 0
                    return True
                if action.startswith("wild_sp_"):
                    name = action[len("wild_sp_") :]
                    if name in self.wildlife_species:
                        # Keep at least one species visible.
                        if len(self.wildlife_species) > 1:
                            self.wildlife_species.discard(name)
                    else:
                        self.wildlife_species.add(name)
                    self._scroll = 0
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
        text_colour = COLOUR_TEXT if active or hovered else COLOUR_TEXT_DIM
        text = self.font_small.render(label, True, text_colour)
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

    def _book_mode(self) -> str:
        if self.show_detail and self.show_list:
            return "both"
        return "detail" if self.show_detail else "list"

    def _book_x(self, panel: pygame.Rect, authored_x: float) -> int:
        """Map an SVG x coordinate while pinning x=160 to the pane boundary."""
        mode = self._book_mode()
        if mode == "detail":
            return panel.x + round(authored_x * panel.w / _BOOK_SPINE_X)
        if mode == "list":
            right_w = _BOOK_NATIVE_SIZE[0] - _BOOK_SPINE_X
            return panel.x + round((authored_x - _BOOK_SPINE_X) * panel.w / right_w)
        return panel.x + round(authored_x * panel.w / _BOOK_NATIVE_SIZE[0])

    def _book_surface(self, size: tuple[int, int]) -> pygame.Surface:
        """Render the active SVG with its single-page binding overhang intact."""
        mode = self._book_mode()
        if (
            self._book_scaled is None
            or self._book_scaled[0] != mode
            or self._book_scaled[1] != size
        ):
            if mode == "detail":
                scale_w = size[0] / _BOOK_SPINE_X
                rendered_w = round(_BOOK_NATIVE_SIZE[0] * scale_w)
            elif mode == "list":
                right_w = _BOOK_NATIVE_SIZE[0] - _BOOK_SPINE_X
                scale_w = size[0] / right_w
                rendered_w = round(_BOOK_NATIVE_SIZE[0] * scale_w)
            else:
                rendered_w = size[0]
            # Render at the SVG's aspect ratio first, then adapt only its
            # height, matching the established resizable-book behaviour.
            source_h = max(
                1,
                round(
                    rendered_w * _BOOK_NATIVE_SIZE[1]
                    / _BOOK_NATIVE_SIZE[0]
                ),
            )
            rendered = pygame.image.load_sized_svg(
                str(_BOOK_PATHS[mode]), (max(1, rendered_w), source_h)
            ).convert_alpha()
            if rendered.get_size() != (rendered_w, size[1]):
                rendered = pygame.transform.smoothscale(rendered, (rendered_w, size[1]))
            self._book_scaled = (mode, size, rendered)
        return self._book_scaled[2]

    def _book_blit_offset(self, panel: pygame.Rect) -> int:
        """Place x=160 at the panel's left edge for the right-page variant."""
        if self._book_mode() != "list":
            return 0
        right_w = _BOOK_NATIVE_SIZE[0] - _BOOK_SPINE_X
        return -round(_BOOK_SPINE_X * panel.w / right_w)

    def _book_point(
        self, panel: pygame.Rect, point: tuple[float, float]
    ) -> tuple[int, int]:
        return (
            self._book_x(panel, point[0]),
            panel.y + round(point[1] * panel.h / _BOOK_NATIVE_SIZE[1]),
        )

    def _book_rect(
        self, panel: pygame.Rect, bounds: tuple[int, int, int, int]
    ) -> pygame.Rect:
        """Transform an authored transparent page bounding box to the screen."""
        x, y, width, height = bounds
        left = self._book_x(panel, x)
        right = self._book_x(panel, x + width)
        top = panel.y + round(
            (y - _BOOK_VIEWBOX_Y) * panel.h / _BOOK_NATIVE_SIZE[1]
        )
        bottom = panel.y + round(
            (y + height - _BOOK_VIEWBOX_Y) * panel.h / _BOOK_NATIVE_SIZE[1]
        )
        return pygame.Rect(left, top, right - left, bottom - top)

    def _book_tab(
        self,
        surface: pygame.Surface,
        panel: pygame.Rect,
        tab: MgmtTab,
        polygon: tuple[tuple[float, float], ...],
        mouse: tuple[int, int] | None,
    ) -> None:
        """Add interaction and a bevel highlight around an illustrated tab."""
        points = [self._book_point(panel, point) for point in polygon]
        hit = pygame.Rect(points[0], (1, 1)).unionall(
            [pygame.Rect(point, (1, 1)) for point in points[1:]]
        ).inflate(4, 4)
        hovered = mouse is not None and hit.collidepoint(mouse)
        active = self.tab == tab
        if active or hovered:
            outer = (102, 64, 35) if active else (139, 104, 61)
            inner = (255, 232, 157) if active else (229, 204, 137)
            pygame.draw.lines(surface, outer, True, points, 4)
            pygame.draw.lines(surface, inner, True, points, 2)
            # A short dark lower/right pass gives the outline its bevel.
            pygame.draw.line(surface, (77, 43, 27), points[2], points[3], 2)
        label = _TAB_META[tab][1]
        self._buttons.append((f"tab_{tab.name.lower()}", hit))
        if hovered:
            self._tooltip = (label, (hit.centerx, hit.top))

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
            _draw_inspect_glyph(surface, rect, UI_TEXT)
        else:
            _draw_list_glyph(surface, rect, UI_TEXT)
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
        wildlife_rows: list[tuple[Any, int, str, str, bool]],
        habitat_view: HabitatInspectView | None,
        mouse_pos: tuple[int, int] | None = None,
        hire_entries: list[RosterEntry] | None = None,
        can_hire: Callable[[RosterEntry], bool] | None = None,
        food_amounts: dict[str, int] | None = None,
        draw_villager_detail: Callable[[pygame.Surface, pygame.Rect], None] | None = None,
        draw_building_detail: Callable[[pygame.Surface, pygame.Rect], None] | None = None,
        flora_keys: set[str] | None = None,
        objectives: list[dict] | None = None,
    ) -> None:
        if not self.open:
            return
        self._layout_panel()
        self._buttons = []
        self._list_hits = []
        self._header_hits = []
        self._tooltip = None

        panel = self._panel
        surface.blit(
            self._book_surface(panel.size),
            (panel.x + self._book_blit_offset(panel), panel.y),
        )

        # Title
        # Reserve the illustrated tabs on the left and the close control on the
        # right; dragging remains available from the title on the right page.
        self._title_rect = pygame.Rect(
            panel.centerx + 8, panel.y, panel.w // 2 - 44, TITLE_BAR_H
        )
        title = {
            MgmtTab.PEOPLE: "Management — People",
            MgmtTab.BUILDINGS: "Management — Buildings",
            MgmtTab.WILDLIFE: "Management — Wildlife",
            MgmtTab.FLORA: "Management — Flora",
            MgmtTab.PLAYER: "Management — Player",
        }[self.tab]
        surface.blit(self.font_title.render(title, True, (74, 47, 30)),
                     (panel.centerx + 12, panel.y + 8))
        self._close_rect = pygame.Rect(panel.right - 30, panel.y + 4, 24, 24)
        hovered_x = mouse_pos is not None and self._close_rect.collidepoint(mouse_pos)
        self._draw_btn(surface, self._close_rect, "×", hovered=hovered_x)

        # Tabs + pane toggles
        y = panel.y + TITLE_BAR_H
        if self._book_mode() != "list":
            for tab, polygon in zip(tuple(MgmtTab)[:4], _BOOK_TAB_POLYGONS):
                self._book_tab(surface, panel, tab, polygon, mouse_pos)
            self._book_tab(
                surface, panel, MgmtTab.PLAYER, _PLAYER_TAB_POLYGON, mouse_pos
            )
            px, py = self._book_point(panel, (125.5, 18.5))
            blit_icon(surface, "player_portrait", px, py, max(18, panel.w // 22))
        bx = panel.centerx - 66
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

        if self.show_detail and self.show_list:
            self._detail_rect = self._book_rect(
                panel, _BOOK_PAGE_BOUNDS["detail"]
            )
            self._list_rect = self._book_rect(panel, _BOOK_PAGE_BOUNDS["list"])
        elif self.show_detail:
            self._detail_rect = self._book_rect(
                panel, _BOOK_PAGE_BOUNDS["detail"]
            )
            self._list_rect = pygame.Rect(0, 0, 0, 0)
        else:
            self._list_rect = self._book_rect(panel, _BOOK_PAGE_BOUNDS["list"])
            self._detail_rect = pygame.Rect(0, 0, 0, 0)

        if self.show_detail and self._detail_rect.w > 0:
            pane_clip = surface.get_clip()
            surface.set_clip(self._detail_rect)
            if self.tab in (MgmtTab.PEOPLE, MgmtTab.PLAYER) and draw_villager_detail is not None:
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
            elif self.tab == MgmtTab.FLORA:
                self._draw_flora_detail(surface, self._detail_rect, flora_keys)
            surface.set_clip(pane_clip)

        if self.show_list and self._list_rect.w > 0:
            pane_clip = surface.get_clip()
            surface.set_clip(self._list_rect)
            if self.tab == MgmtTab.PLAYER:
                self._draw_objectives(surface, objectives or [])
            elif self.tab == MgmtTab.PEOPLE:
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
            elif self.tab == MgmtTab.WILDLIFE:
                self._draw_wildlife_list(surface, wildlife_rows, mouse_pos)
            else:
                self._draw_flora_list(surface, flora_keys)
            surface.set_clip(pane_clip)

        if self._tooltip is not None:
            tip, (tx, ty) = self._tooltip
            text = self.font_tiny.render(tip, True, (0, 0, 0))
            tip_r = text.get_rect()
            tip_r.midbottom = (tx, ty - 4)
            tip_r.x = max(4, min(tip_r.x, WINDOW_WIDTH - tip_r.w - 4))
            bg = tip_r.inflate(8, 4)
            tip_bg = pygame.Surface(bg.size, pygame.SRCALPHA)
            tip_bg.fill((105, 46, 44, 50))
            surface.blit(tip_bg, bg.topleft)
            surface.blit(text, tip_r)

    def focus_objective(self, objective_id: str) -> None:
        self.objectives_filter = "current"
        self.expanded_objective = objective_id
        self._objective_focus = objective_id
        self._objective_scroll = 0

    def _draw_objectives(self, surface: pygame.Surface, objectives: list[dict]) -> None:
        self._quest_rows = objectives
        pane = self._list_rect
        x, y = pane.x + PAD, pane.y + PAD
        width = max(40, pane.w - 2 * PAD)
        surface.blit(self.font_title.render("Quests", True, COLOUR_TEXT), (x, y))
        y += self.font_title.get_linesize() + 8
        for index, (label, key) in enumerate((("Current", "current"), ("All", "all"))):
            rect = pygame.Rect(x + index * 84, y, 80, 28)
            self._draw_btn(surface, rect, label, active=self.objectives_filter == key)
            if self.objectives_filter == key:
                pygame.draw.line(surface, COLOUR_TEXT, rect.bottomleft, rect.bottomright)
            self._buttons.append((f"objectives_filter:{key}", rect))
        y += 38
        view = pygame.Rect(x, y, width, max(1, pane.bottom - PAD - y))
        active_groups = {row.get('group') for row in objectives if not row['completed']}
        rows = [row for row in objectives if (row['completed'] if self.objectives_filter == 'all' else row.get('group') in active_groups)]
        # Lay out before drawing so a headline link can reveal an offscreen entry immediately.
        layouts = []
        offset = 0
        last_group = None
        group_headers = []
        for row in rows:
            if row.get('group') != last_group:
                group_headers.append((offset, row.get('group_title', 'Quests'), row.get('group', '')))
                offset += self.font_title.get_linesize() + 14
                last_group = row.get('group')
            from quest_ui import detail_lines
            lines = detail_lines(self.font_small, row, width, explanation=True) if self.expanded_objective == row["id"] else []
            headline_h = self.font.get_linesize() + 12
            height = headline_h + len(lines) * self.font_small.get_linesize() + 12
            layouts.append((row, offset, headline_h, lines))
            offset += height
        content_height = offset
        self._objective_max_scroll = max(0, content_height - view.h)
        if self._objective_focus:
            target = next((offset for row, offset, _, _ in layouts if row["id"] == self._objective_focus), None)
            if target is not None:
                self._objective_scroll = target
            self._objective_focus = None
        self._objective_scroll = min(self._objective_scroll, self._objective_max_scroll)
        old = surface.get_clip()
        surface.set_clip(view.clip(old))
        if not rows:
            message = "No completed quests yet." if self.objectives_filter == "all" else "No current quests."
            surface.blit(self.font_small.render(message, True, COLOUR_TEXT_DIM), view.topleft)
        for header_offset, title, group in group_headers:
            hit = pygame.Rect(x, view.y + header_offset - self._objective_scroll, width, self.font_title.get_linesize()+10).clip(view)
            if hit.height:
                self._buttons.append((f'quest_group:{group}', hit))
            surface.blit(self.font_title.render(title, True, COLOUR_TEXT), (x, view.y + header_offset - self._objective_scroll))
        for row, offset, headline_h, lines in layouts:
            top = view.y + offset - self._objective_scroll
            rect = pygame.Rect(x, top, width, headline_h)
            marker = "−" if row["id"] == self.expanded_objective else "+"
            text = f"{marker} {row['headline']}" + (" ✓" if row["completed"] else "")
            surface.blit(self.font.render(text, True, COLOUR_TEXT), (x, top + 4))
            clipped = rect.clip(view)
            if clipped.height:
                self._buttons.append((f"objective:{row['id']}", clipped))
            ly = top + headline_h
            from quest_ui import draw_line
            for line, checked in lines:
                draw_line(surface, self.font_small, line, checked, x, ly, COLOUR_TEXT_DIM)
                ly += self.font_small.get_linesize()
            pygame.draw.line(surface, COLOUR_TEXT_DIM, (x, ly + 5), (view.right, ly + 5))
        surface.set_clip(old)
        if self._objective_max_scroll:
            track = pygame.Rect(pane.right - 6, view.y, 3, view.h)
            thumb_h = max(16, view.h * view.h // max(1, content_height))
            thumb_y = view.y + (view.h - thumb_h) * self._objective_scroll // self._objective_max_scroll
            pygame.draw.rect(surface, COLOUR_TEXT_DIM, (track.x, thumb_y, 3, thumb_h))

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

        if view.panel_kind in ("wolf", "bird"):
            is_bird = view.panel_kind == "bird"
            rows = (
                [
                    ("Bird", view.population),
                    ("Activity", view.activity or "—"),
                    ("Diet", view.food_status or "—"),
                ]
                if is_bird
                else [
                    ("Pack", view.population),
                    ("Activity", view.activity or "—"),
                    ("Last meal", view.last_meal or "None yet"),
                    ("Food", view.food_status or "Hungry"),
                    ("Fed until", view.fed_until or "—"),
                ]
            )
            for label, value in rows:
                surface.blit(
                    self.font_small.render(f"{label}: {value}", True, COLOUR_TEXT),
                    (x, y),
                )
                y += 18
            y += 6
            surface.blit(self.font_small.render("Status", True, COLOUR_TEXT), (x, y))
            y += 18
            for name, val in view.benefits:
                surface.blit(
                    self.font_small.render(f"{name}: {val}", True, COLOUR_TEXT_DIM),
                    (x, y),
                )
                y += 16
            y += 6
            surface.blit(self.font_small.render("Vitality", True, COLOUR_TEXT), (x, y))
            y += 18
            health_colour = COLOUR_TEXT
            if view.health_pct < 40:
                health_colour = (220, 100, 90)
            elif view.health_pct < 70:
                health_colour = (220, 180, 80)
            surface.blit(
                self.font_small.render(
                    f"Overall health: {view.health_pct:.0f}%", True, health_colour
                ),
                (x, y),
            )
            if not is_bird:
                y += 18
                surface.blit(
                    self.font_small.render(
                        f"Breeding chance: {view.breed_chance_pct:.0f}% / tick",
                        True,
                        COLOUR_TEXT,
                    ),
                    (x, y),
                )
            return

        for label, value in (
            ("Population", view.population),
            ("Breeding area", f"{view.breeding_tiles} cells"),
            ("Roaming / forage", f"{view.roam_tiles} cells"),
        ):
            surface.blit(
                self.font_small.render(f"{label}: {value}", True, COLOUR_TEXT),
                (x, y),
            )
            y += 18
        y += 6
        surface.blit(self.font_small.render("Environment", True, COLOUR_TEXT), (x, y))
        y += 18
        for name, val in view.benefits:
            surface.blit(
                self.font_small.render(f"{name}: {val}", True, COLOUR_TEXT_DIM),
                (x, y),
            )
            y += 16
        y += 6
        surface.blit(self.font_small.render("Disturbance", True, COLOUR_TEXT), (x, y))
        y += 18
        for label, value in (
            ("Average (radius)", f"{view.avg_disturbance * 100:.0f}%"),
            ("Peak", f"{view.max_disturbance * 100:.0f}%"),
            ("Ecology modifier", f"×{view.ecology_mult:.2f}"),
        ):
            surface.blit(
                self.font_small.render(f"{label}: {value}", True, COLOUR_TEXT),
                (x, y),
            )
            y += 18
        y += 6
        surface.blit(self.font_small.render("Vitality", True, COLOUR_TEXT), (x, y))
        y += 18
        health_colour = COLOUR_TEXT
        if view.health_pct < 40:
            health_colour = (220, 100, 90)
        elif view.health_pct < 70:
            health_colour = (220, 180, 80)
        surface.blit(
            self.font_small.render(
                f"Overall health: {view.health_pct:.0f}%", True, health_colour
            ),
            (x, y),
        )
        y += 18
        surface.blit(
            self.font_small.render(
                f"Breeding chance: {view.breed_chance_pct:.0f}% / tick",
                True,
                COLOUR_TEXT,
            ),
            (x, y),
        )

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
            del selected, hovered

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
                req_x = cols["house"] + 2
                req_y = row_y + (ROW_H - REQ_ICON) // 2
                draw_requirement_icons(
                    surface,
                    req_x,
                    req_y,
                    entry.requirement_rows,
                )
                if mouse_pos is not None:
                    for req_i, requirement in enumerate(entry.requirement_rows[:4]):
                        icon_rect = pygame.Rect(
                            req_x + req_i * (REQ_ICON + 2), req_y, REQ_ICON, REQ_ICON
                        )
                        if icon_rect.collidepoint(mouse_pos):
                            detail = str(requirement.get("label") or "Requirement")
                            coins = int(requirement.get("coins", 0) or 0)
                            if coins > 0:
                                detail += f" · {coins} coins/season if unmet"
                            self._tooltip = (detail, (icon_rect.centerx, icon_rect.top))
                            break
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

        def _workers_for(b: Building) -> list[Villager]:
            if b.kind == BuildingKind.HOME:
                return [v for v in villagers if v.assigned_to_home]
            if is_housing_kind(b.kind):
                return [v for v in villagers if v.housed and v.housing_id == b.id]
            if b.kind == BuildingKind.FIELD:
                return []
            return [v for v in villagers if v.building_id == b.id]

        def _draw_site_row(site: ConstructionSite, indent: int) -> None:
            nonlocal y
            pad = 10 * indent
            row = pygame.Rect(view.x + 2 + pad, y, view.w - 8 - pad, LIST_ROW_H)
            selected = self.selected_construction_id == site.id
            del selected
            icon = _BUILD_ICON.get(site.kind, "construction_site")
            blit_icon(surface, icon, row.x + 14, row.centery, 24 if indent else 28)
            label = f"{BUILDING_LABELS[site.kind]} (site)"
            surface.blit(
                self.font_small.render(label, True, COLOUR_TEXT),
                (row.x + 32, row.y + 4),
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
                (row.x + 32, row.y + 20),
            )
            self._list_hits.append((row, "construction", site.id))
            y += LIST_ROW_H + 2

        def _draw_building_row(b: Building, indent: int) -> None:
            nonlocal y
            pad = 10 * indent
            row = pygame.Rect(view.x + 2 + pad, y, view.w - 8 - pad, LIST_ROW_H)
            selected = self.selected_building_id == b.id
            del selected
            icon = _BUILD_ICON.get(b.kind, "construction_site")
            blit_icon(surface, icon, row.x + 14, row.centery, 24 if indent else 28)
            if b.kind == BuildingKind.FIELD:
                label = "Field Planner" if getattr(b, "_tutorial_planner_entry", False) else f"Field #{b.id}"
                name = f"{label} · {b.plot_size_label()}"
            else:
                name = f"{BUILDING_LABELS[b.kind]} #{b.id}"
            surface.blit(
                self.font_small.render(name, True, COLOUR_TEXT),
                (row.x + 32, row.y + 10),
            )
            workers = _workers_for(b)
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

        for kind, entity, indent in _iter_building_list_rows(buildings, sites):
            if kind == "construction":
                _draw_site_row(entity, indent)  # type: ignore[arg-type]
            else:
                _draw_building_row(entity, indent)  # type: ignore[arg-type]
        surface.set_clip(old)

    def _draw_wildlife_list(
        self,
        surface: pygame.Surface,
        rows: list[tuple[Any, int, str, str, bool]],
        mouse_pos: tuple[int, int] | None,
    ) -> None:
        rect = self._list_rect
        filter_h = 72
        filter_rect = pygame.Rect(rect.x + 2, rect.y + 2, rect.w - 4, filter_h)
        self._draw_wildlife_filters(surface, filter_rect, mouse_pos)

        view = pygame.Rect(
            rect.x + 2, rect.y + 2 + filter_h, rect.w - 4, rect.h - 4 - filter_h
        )
        y = view.y + 4 - self._scroll
        old = surface.get_clip()
        surface.set_clip(view)
        icon_for = {
            "DEER": "deer_male",
            "BOAR": "boar_male",
            "BEE": "bee_hive",
            "RABBIT": "burrow",
            "FROG": "frog",
            "VOLE": "vole",
            "WOLF": "wolf_male",
            "FOX": "fox_male",
            "HAWK": "hawk_right",
            "OWL": "owl_right",
        }
        shown = 0
        for kind, patch_id, title, subtitle, inhabited in rows:
            name = kind.name if hasattr(kind, "name") else str(kind)
            if name not in self.wildlife_species:
                continue
            if self.wildlife_inhabited_only and not inhabited:
                continue
            row = pygame.Rect(view.x + 2, y, view.w - 8, LIST_ROW_H)
            selected = self.selected_habitat == (kind, patch_id)
            del selected
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
            # Only hit-test rows currently visible in the clip.
            if row.bottom >= view.y and row.top <= view.bottom:
                self._list_hits.append((row, "habitat", f"{name}:{patch_id}"))
            y += LIST_ROW_H + 2
            shown += 1
        if shown == 0:
            surface.blit(
                self.font_small.render("No matching wildlife", True, COLOUR_TEXT_DIM),
                (view.x + 8, view.y + 8),
            )
        surface.set_clip(old)

    def _flora_rows(self, allowed: set[str] | None = None) -> list[tuple[str, WildSpeciesDef | TreeDef]]:
        rows: list[tuple[str, WildSpeciesDef | TreeDef]] = [
            (f"wild:{species.key}", species) for species in WILD_SPECIES
        ]
        rows.extend((f"tree:{tree.key}", tree) for tree in TREES)
        if allowed is not None:
            rows = [row for row in rows if row[0] in allowed]
        return sorted(rows, key=lambda item: item[1].label)

    def _draw_flora_list(self, surface: pygame.Surface, allowed: set[str] | None = None) -> None:
        rect = self._list_rect
        view = pygame.Rect(rect.x + 2, rect.y + 2, rect.w - 4, rect.h - 4)
        y = view.y + 4 - self._scroll
        old = surface.get_clip()
        surface.set_clip(view)
        for key, species in self._flora_rows(allowed):
            row = pygame.Rect(view.x + 2, y, view.w - 8, LIST_ROW_H)
            blit_icon(surface, _flora_icon(species), row.x + 18, row.centery, 28)
            surface.blit(self.font_small.render(species.label, True, COLOUR_TEXT),
                         (row.x + 38, row.y + 4))
            group = "Tree" if isinstance(species, TreeDef) else species.feature.replace("_", " ").title()
            surface.blit(self.font_tiny.render(group, True, COLOUR_TEXT_DIM),
                         (row.x + 38, row.y + 20))
            if row.bottom >= view.y and row.top <= view.bottom:
                self._list_hits.append((row, "flora", key))
            y += LIST_ROW_H + 2
        surface.set_clip(old)

    def _wrapped(self, text: str, max_width: int) -> list[str]:
        lines: list[str] = []
        line = ""
        for word in text.split():
            candidate = f"{line} {word}".strip()
            if line and self.font_small.size(candidate)[0] > max_width:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
        return lines

    def _draw_flora_detail(self, surface: pygame.Surface, rect: pygame.Rect, allowed: set[str] | None = None) -> None:
        lookup: dict[str, WildSpeciesDef | TreeDef] = {
            **{f"wild:{key}": value for key, value in WILD_BY_KEY.items()},
            **{f"tree:{key}": value for key, value in TREE_BY_KEY.items()},
        }
        selected = self.selected_flora_key or ""
        species = lookup.get(selected) if allowed is None or selected in allowed else None
        if species is None:
            self._blit_dim(surface, rect, "Select a flora species")
            return
        x, y = rect.x + PAD, rect.y + PAD
        blit_icon(surface, _flora_icon(species), x + 24, y + 24, 44)
        surface.blit(self.font_title.render(species.label, True, COLOUR_TEXT), (x + 54, y + 7))
        kind = "Tree" if isinstance(species, TreeDef) else species.feature.replace("_", " ").title()
        surface.blit(self.font_tiny.render(kind, True, COLOUR_TEXT_DIM), (x + 54, y + 27))
        y += 62
        if isinstance(species, TreeDef):
            sections = (
                ("Description", f"A {species.shape}-canopied woodland tree species."),
                ("Environment niche", "Found in wooded soil and managed forest plots."),
                ("Seasonal growth", _growth_text(species)),
                ("Uses", _uses_text(species)),
            )
        else:
            sections = (
                ("Description", _wild_description(species)),
                ("Environment niche", _niche_text(species)),
                ("Seasonal growth", _growth_text(species)),
                ("Uses", _uses_text(species)),
            )
        max_width = rect.w - PAD * 2
        for heading, body in sections:
            surface.blit(self.font.render(heading, True, COLOUR_TEXT), (x, y))
            y += 19
            for line in self._wrapped(body, max_width):
                surface.blit(self.font_small.render(line, True, COLOUR_TEXT_DIM), (x, y))
                y += 16
            y += 10

    def _draw_wildlife_filters(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        mouse_pos: tuple[int, int] | None,
    ) -> None:
        x = rect.x + 6
        y = rect.y + 6
        for label, action, active in (
            ("Inhabited", "wild_occ_inhabited", self.wildlife_inhabited_only),
            ("All", "wild_occ_all", not self.wildlife_inhabited_only),
        ):
            btn = pygame.Rect(x, y, 72, 18)
            hovered = mouse_pos is not None and btn.collidepoint(mouse_pos)
            self._draw_btn(surface, btn, label, active=active, hovered=hovered)
            self._buttons.append((action, btn))
            if hovered:
                tip = (
                    "Show grounds/nests with animals"
                    if action == "wild_occ_inhabited"
                    else "Show empty and occupied sites"
                )
                self._tooltip = (tip, (btn.centerx, btn.top))
            x += 76

        x = rect.x + 6
        y = rect.y + 28
        species = (
            ("DEER", "deer_male", "Deer"),
            ("BOAR", "boar_male", "Boar"),
            ("BEE", "bee_hive", "Bees"),
            ("RABBIT", "burrow", "Rabbits"),
            ("FROG", "frog", "Frogs"),
            ("VOLE", "vole", "Voles"),
            ("WOLF", "wolf_male", "Wolves"),
            ("FOX", "fox_male", "Foxes"),
            ("HAWK", "hawk_right", "Hawks"),
            ("OWL", "owl_right", "Owls"),
        )
        for name, icon, tip in species:
            if x + 26 > rect.right - 4:
                x = rect.x + 6
                y += 22
            btn = pygame.Rect(x, y, 26, 20)
            active = name in self.wildlife_species
            hovered = mouse_pos is not None and btn.collidepoint(mouse_pos)
            bg = (
                COLOUR_TOOLBAR_BTN_ACTIVE
                if active
                else (COLOUR_TOOLBAR_BTN_HOVER if hovered else COLOUR_TOOLBAR_BTN)
            )
            pygame.draw.rect(surface, bg, btn, border_radius=3)
            pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, btn, 1, border_radius=3)
            blit_icon(surface, icon, btn.centerx, btn.centery, 18)
            self._buttons.append((f"wild_sp_{name}", btn))
            if hovered:
                state = "on" if active else "off"
                self._tooltip = (f"{tip} filter ({state})", (btn.centerx, btn.top))
            x += 30
