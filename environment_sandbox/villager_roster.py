"""Shared villager / traveller roster table with sorting and status bars."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable

import pygame

from entities import Building, BuildingKind
from icons import blit_icon, get_icon
from settings import (
    COLOUR_ALCHEMIST,
    COLOUR_COBBLER,
    COLOUR_CRAFT_BENCH,
    COLOUR_FARM,
    COLOUR_FISHER,
    COLOUR_FORESTER,
    COLOUR_FORAGER,
    COLOUR_HOME,
    COLOUR_HUNTER,
    COLOUR_KITCHEN,
    COLOUR_MARKET,
    COLOUR_MASON,
    COLOUR_MENU_BG,
    COLOUR_MILL,
    COLOUR_SELECTED_ENTITY,
    COLOUR_TAILOR,
    COLOUR_TEXT,
    COLOUR_TEXT_DIM,
    COLOUR_TOOLBAR_BORDER,
    COLOUR_TOOLBAR_BTN,
    COLOUR_TOOLBAR_BTN_ACTIVE,
    COLOUR_TOOLBAR_BTN_HOVER,
    COLOUR_VILLAGER,
    MAP_OFFSET_Y,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)
from society import (
    SKILL_ICONS,
    SKILL_LABELS,
    SKILL_ORDER,
    SKILL_SHORT,
    SkillType,
)


class RosterSort(Enum):
    NAME = auto()
    ENERGY = auto()
    SATIATION = auto()
    HAPPINESS = auto()
    HOUSING = auto()
    PAY = auto()
    EXTRACTION = auto()
    FARMING = auto()
    HUNTING = auto()
    CRAFTING = auto()
    LABOUR = auto()
    TRANSPORT = auto()


SORT_LABELS: dict[RosterSort, str] = {
    RosterSort.NAME: "Name",
    RosterSort.ENERGY: "En",
    RosterSort.SATIATION: "Sat",
    RosterSort.HAPPINESS: "Hap",
    RosterSort.HOUSING: "Reqs",
    RosterSort.PAY: "Pay",
    RosterSort.EXTRACTION: "Ex",
    RosterSort.FARMING: "Fa",
    RosterSort.HUNTING: "Hu",
    RosterSort.CRAFTING: "Cr",
    RosterSort.LABOUR: "La",
    RosterSort.TRANSPORT: "Tr",
}

_SKILL_SORT: dict[RosterSort, SkillType] = {
    RosterSort.EXTRACTION: SkillType.EXTRACTION,
    RosterSort.FARMING: SkillType.FARMING,
    RosterSort.HUNTING: SkillType.HUNTING,
    RosterSort.CRAFTING: SkillType.CRAFTING,
    RosterSort.LABOUR: SkillType.LABOUR,
    RosterSort.TRANSPORT: SkillType.TRANSPORT,
}

PORTRAIT_SIZE = 28
ROW_H = 64
HEADER_H = 22
PAD = 10
TITLE_BAR_H = 28
ACTION_W = 100  # Hire/Pay or Pick column
SKILL_COL_W = 36

# Fixed column widths (content starts after portrait gutter).
COL_NAME_W = 140
COL_BAR_W = 44
COL_HOUSE_W = 78
COL_PAY_W = 40
REQ_ICON = 16
REQ_ICON_GAP = 2


def draw_requirement_icons(
    surface: pygame.Surface,
    x: int,
    y: int,
    rows: list[dict],
    *,
    icon_size: int = REQ_ICON,
    max_icons: int = 4,
) -> int:
    """Draw compact green/red requirement icons. Returns width used."""
    from icons import blit_icon

    cur = x
    for row in list(rows or [])[:max_icons]:
        if not isinstance(row, dict):
            continue
        met = bool(row.get("met"))
        ic = str(row.get("icon") or "tent")
        rect = pygame.Rect(cur, y, icon_size, icon_size)
        fill = (40, 70, 48) if met else (70, 40, 40)
        border = (70, 160, 85) if met else (190, 70, 60)
        pygame.draw.rect(surface, fill, rect, border_radius=3)
        pygame.draw.rect(surface, border, rect, 1, border_radius=3)
        try:
            blit_icon(surface, ic, rect.centerx, rect.centery, icon_size - 4)
        except Exception:
            pass
        cur += icon_size + REQ_ICON_GAP
    return max(0, cur - x - REQ_ICON_GAP)


def _column_layout(left: int, *, actions: bool) -> dict[str, int]:
    """Absolute x origins for each column, shared by header and rows."""
    x = left
    cols = {
        "portrait": x,
        "name": x + PORTRAIT_SIZE + 8,
    }
    x = cols["name"] + COL_NAME_W
    cols["energy"] = x
    x += COL_BAR_W
    cols["satiation"] = x
    x += COL_BAR_W
    cols["happiness"] = x
    x += COL_BAR_W
    cols["house"] = x
    x += COL_HOUSE_W
    cols["pay"] = x
    x += COL_PAY_W
    for sk in SKILL_ORDER:
        cols[sk.name.lower()] = x
        x += SKILL_COL_W
    cols["actions"] = x if actions else -1
    cols["end"] = x + (ACTION_W if actions else 0)
    return cols


def _table_width(*, actions: bool) -> int:
    return _column_layout(0, actions=actions)["end"] + PAD * 2


@dataclass
class RosterEntry:
    """Unified row for hired villagers or hire candidates."""

    id: int
    name: str
    skills: dict
    housing_need: int = 1
    required_foods: list[str] = field(default_factory=list)
    favourite_foods: list[str] = field(default_factory=list)
    virtues: list[str] = field(default_factory=list)
    vices: list[str] = field(default_factory=list)
    energy: float = 1.0
    satiation: float = 0.75
    happiness: float = 0.7
    housed: bool = False
    portrait_seed: int = 0
    job_colour: tuple[int, int, int] = COLOUR_VILLAGER
    job: str = ""
    status: str = ""
    kind: str = "villager"  # villager | traveller
    season_pay: int = 0
    coins_paid: int = 0
    requirement_rows: list[dict] = field(default_factory=list)


def entry_from_villager(
    v: Any,
    *,
    job: str = "",
    status: str = "",
    job_colour: tuple[int, int, int] | None = None,
    requirement_rows: list[dict] | None = None,
    buildings: dict[int, Building] | None = None,
) -> RosterEntry:
    if job_colour is None and buildings is not None:
        job_colour = villager_job_colour(v, buildings)
    if job_colour is None:
        job_colour = COLOUR_VILLAGER
    return RosterEntry(
        id=int(v.id),
        name=str(getattr(v, "name", None) or f"Villager {v.id}"),
        skills=dict(getattr(v, "skills", {}) or {}),
        housing_need=int(getattr(v, "housing_need", 1)),
        required_foods=list(getattr(v, "required_foods", []) or []),
        favourite_foods=list(getattr(v, "favourite_foods", []) or []),
        virtues=list(getattr(v, "virtues", []) or []),
        vices=list(getattr(v, "vices", []) or []),
        energy=float(getattr(v, "energy", 1.0)),
        satiation=float(getattr(v, "satiation", 0.75)),
        happiness=float(getattr(v, "happiness", 0.7)),
        housed=bool(getattr(v, "housed", False)),
        portrait_seed=int(getattr(v, "portrait_seed", 0) or (v.id * 9973)),
        job_colour=job_colour,
        job=job,
        status=status,
        kind="villager",
        season_pay=int(getattr(v, "season_pay_due", 0) or 0),
        coins_paid=int(getattr(v, "coins_paid_total", 0) or 0),
        requirement_rows=list(requirement_rows or []),
    )


def entry_from_candidate(
    c: Any,
    *,
    season_pay: int = 0,
    requirement_rows: list[dict] | None = None,
) -> RosterEntry:
    return RosterEntry(
        id=int(c.id),
        name=str(c.name),
        skills=dict(getattr(c, "skills", {}) or {}),
        housing_need=int(getattr(c, "housing_need", 1)),
        required_foods=list(getattr(c, "required_foods", []) or []),
        favourite_foods=list(getattr(c, "favourite_foods", []) or []),
        virtues=list(getattr(c, "virtues", []) or []),
        vices=list(getattr(c, "vices", []) or []),
        energy=float(getattr(c, "energy", 1.0)),
        satiation=float(getattr(c, "satiation", 0.75)),
        happiness=float(getattr(c, "happiness", 0.7)),
        housed=False,
        portrait_seed=int(getattr(c, "portrait_seed", 0) or c.id),
        job="traveller",
        status=(
            "Required food: "
            + (", ".join(getattr(c, "required_foods", []) or []) or "None")
            + " · Favourite: "
            + (", ".join(getattr(c, "favourite_foods", []) or []) or "None")
        ),
        kind="traveller",
        season_pay=int(season_pay),
        coins_paid=0,
        requirement_rows=list(requirement_rows or []),
    )


def sort_entries(
    entries: list[RosterEntry],
    key: RosterSort,
    *,
    reverse: bool = False,
) -> list[RosterEntry]:
    def skill_lvl(e: RosterEntry, sk: SkillType) -> int:
        st = e.skills.get(sk)
        return int(getattr(st, "level", 0) or 0)

    if key == RosterSort.NAME:
        return sorted(entries, key=lambda e: e.name.lower(), reverse=reverse)
    if key == RosterSort.ENERGY:
        return sorted(entries, key=lambda e: e.energy, reverse=not reverse)
    if key == RosterSort.SATIATION:
        return sorted(entries, key=lambda e: e.satiation, reverse=not reverse)
    if key == RosterSort.HAPPINESS:
        return sorted(entries, key=lambda e: e.happiness, reverse=not reverse)
    if key == RosterSort.HOUSING:
        return sorted(
            entries,
            key=lambda e: (e.housed, -e.housing_need, e.name.lower()),
            reverse=reverse,
        )
    if key == RosterSort.PAY:
        return sorted(
            entries,
            key=lambda e: (e.season_pay, e.coins_paid, e.name.lower()),
            reverse=not reverse,
        )
    if key in _SKILL_SORT:
        sk = _SKILL_SORT[key]
        return sorted(
            entries,
            key=lambda e: (skill_lvl(e, sk), e.name.lower()),
            reverse=not reverse,
        )
    return list(entries)


def _bar_colour(value: float, *, kind: str) -> tuple[int, int, int]:
    v = max(0.0, min(1.0, value))
    if kind == "energy":
        if v >= 0.55:
            return (70, 140, 210)
        if v >= 0.3:
            return (90, 120, 180)
        return (60, 80, 140)
    if kind == "happy":
        if v >= 0.55:
            return (200, 160, 70)
        if v >= 0.3:
            return (180, 120, 60)
        return (160, 80, 50)
    # satiation
    if v >= 0.6:
        return (80, 170, 90)
    if v >= 0.3:
        return (200, 160, 50)
    return (190, 70, 60)


def draw_status_bar(
    surface: pygame.Surface,
    x: int,
    y: int,
    w: int,
    h: int,
    value: float,
    *,
    kind: str,
) -> None:
    pygame.draw.rect(surface, (40, 42, 48), pygame.Rect(x, y, w, h), border_radius=2)
    fill = max(0, int(w * max(0.0, min(1.0, value))))
    if fill > 0:
        pygame.draw.rect(
            surface,
            _bar_colour(value, kind=kind),
            pygame.Rect(x, y, fill, h),
            border_radius=2,
        )
    pygame.draw.rect(surface, (70, 72, 80), pygame.Rect(x, y, w, h), 1, border_radius=2)


def portrait_tint(seed: int) -> tuple[int, int, int]:
    rng = seed * 1103515245 + 12345
    r = 140 + (rng >> 8) % 90
    g = 120 + (rng >> 16) % 90
    b = 110 + (rng >> 24) % 90
    return (r % 256, g % 256, b % 256)


def portrait_skin_colour(seed: int) -> tuple[int, int, int]:
    rng = seed * 1103515245 + 12345
    r = 180 + (rng >> 8) % 55
    g = 135 + (rng >> 16) % 65
    b = 95 + (rng >> 24) % 75
    return (r % 256, g % 256, b % 256)


_JOB_COLOURS: dict[BuildingKind, tuple[int, int, int]] = {
    BuildingKind.FORESTER: COLOUR_FORESTER,
    BuildingKind.MASON: COLOUR_MASON,
    BuildingKind.HUNTER: COLOUR_HUNTER,
    BuildingKind.FORAGER: COLOUR_FORAGER,
    BuildingKind.FISHER: COLOUR_FISHER,
    BuildingKind.FARM: COLOUR_FARM,
    BuildingKind.FIELD: COLOUR_FARM,
    BuildingKind.MILL: COLOUR_MILL,
    BuildingKind.KITCHEN: COLOUR_KITCHEN,
    BuildingKind.CRAFT_BENCH: COLOUR_CRAFT_BENCH,
    BuildingKind.ALCHEMIST: COLOUR_ALCHEMIST,
    BuildingKind.TAILOR: COLOUR_TAILOR,
    BuildingKind.COBBLER: COLOUR_COBBLER,
    BuildingKind.MARKET: COLOUR_MARKET,
}


def villager_job_colour(
    villager: Any,
    buildings: dict[int, Building],
) -> tuple[int, int, int]:
    if getattr(villager, "assigned_to_home", False):
        return COLOUR_HOME
    building_id = getattr(villager, "building_id", None)
    if building_id is not None:
        building = buildings.get(building_id)
        if building is not None:
            return _JOB_COLOURS.get(building.kind, COLOUR_VILLAGER)
    return COLOUR_VILLAGER


def draw_portrait(
    surface: pygame.Surface,
    cx: int,
    cy: int,
    seed: int,
    size: int = PORTRAIT_SIZE,
    *,
    job_colour: tuple[int, int, int] | None = None,
) -> None:
    job = job_colour or COLOUR_VILLAGER
    skin = portrait_skin_colour(seed)
    try:
        blit_icon(
            surface,
            "villager",
            cx,
            cy,
            size,
            recolour={"skin": skin, "shirt": job, "hat": job},
        )
    except Exception:
        rect = pygame.Rect(cx - size // 2, cy - size // 2, size, size)
        pygame.draw.ellipse(surface, job, rect)
        pygame.draw.ellipse(surface, (60, 60, 70), rect, 1)


def draw_skill_cell(
    surface: pygame.Surface,
    x: int,
    y: int,
    skill: SkillType,
    level: int,
    font: pygame.font.Font,
    *,
    icon_size: int = 14,
    col_w: int = SKILL_COL_W,
    highlighted: bool = False,
) -> None:
    """One skill column: icon centred, level digit below (no overlap)."""
    if highlighted:
        bg = pygame.Rect(x + 1, y - 1, col_w - 2, icon_size + 14)
        pygame.draw.rect(surface, (55, 85, 55), bg, border_radius=3)
        pygame.draw.rect(surface, (90, 140, 90), bg, 1, border_radius=3)
    icon = SKILL_ICONS.get(skill, "wood")
    cx = x + col_w // 2
    try:
        blit_icon(surface, icon, cx, y + icon_size // 2, icon_size)
    except Exception:
        label = SKILL_SHORT.get(skill, "?")
        text = font.render(label, True, COLOUR_TEXT_DIM)
        surface.blit(text, (cx - text.get_width() // 2, y))
    lvl_col = COLOUR_TEXT if highlighted else COLOUR_TEXT
    lvl = font.render(str(int(level)), True, lvl_col)
    surface.blit(lvl, (cx - lvl.get_width() // 2, y + icon_size + 1))


def draw_skill_icons(
    surface: pygame.Surface,
    x: int,
    y: int,
    skills: dict,
    font: pygame.font.Font,
    *,
    icon_size: int = 14,
    highlight: frozenset | set | None = None,
) -> tuple[int, list[tuple[pygame.Rect, str]]]:
    """Draw skills in fixed-width columns. Returns (width used, tip hits)."""
    from society import SKILL_LABELS

    cur = x
    tips: list[tuple[pygame.Rect, str]] = []
    hi = highlight or ()
    for sk in SKILL_ORDER:
        st = skills.get(sk)
        lvl = int(getattr(st, "level", 1) or 1)
        draw_skill_cell(
            surface,
            cur,
            y,
            sk,
            lvl,
            font,
            icon_size=icon_size,
            highlighted=sk in hi,
        )
        tip_rect = pygame.Rect(cur, y, SKILL_COL_W, icon_size + 14)
        label = SKILL_LABELS.get(sk, sk.name)
        tip = f"{label} {lvl}" + (" · used here" if sk in hi else "")
        tips.append((tip_rect, tip))
        cur += SKILL_COL_W
    return cur - x, tips


class VillagerRosterDialog:
    """Floating roster: side-list, hiring hall travellers, or assign picker."""

    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 13)
        self.font_small = pygame.font.SysFont("menlo", 11)
        self.font_tiny = pygame.font.SysFont("menlo", 10, bold=True)
        self.font_title = pygame.font.SysFont("menlo", 15, bold=True)
        self._open = False
        self.mode: str = "roster"  # roster | hire | assign
        self.sort_key = RosterSort.NAME
        self.sort_reverse = False
        self._scroll = 0
        self._panel = pygame.Rect(80, MAP_OFFSET_Y + 40, 720, 420)
        self._buttons: list[tuple[str, pygame.Rect]] = []
        self._row_hits: list[tuple[pygame.Rect, int]] = []
        self._header_hits: list[tuple[pygame.Rect, RosterSort]] = []
        self._pending: str | None = None
        self._close_rect = pygame.Rect(0, 0, 0, 0)
        self._title_rect = pygame.Rect(0, 0, 0, 0)
        self._moving = False
        self._move_offset = (0, 0)
        self.assign_building_id: int | None = None
        self._entries: list[RosterEntry] = []

    @property
    def open(self) -> bool:
        return self._open

    def close(self) -> None:
        self._open = False
        self._pending = None
        self.assign_building_id = None

    def open_roster(self) -> None:
        self.mode = "roster"
        self._open = True
        self._pending = None
        self._center()

    def open_hire(self) -> None:
        self.mode = "hire"
        self._open = True
        self._pending = None
        self._center()

    def open_assign(self, building_id: int) -> None:
        self.mode = "assign"
        self.assign_building_id = building_id
        self._open = True
        self._pending = None
        self._center()

    def _center(self) -> None:
        actions = self.mode in ("hire", "assign")
        self._panel.w = min(
            WINDOW_WIDTH - 16,
            max(640, _table_width(actions=actions) + 24),
        )
        self._panel.h = min(480, WINDOW_HEIGHT - MAP_OFFSET_Y - 24)
        self._panel.x = max(8, (WINDOW_WIDTH - self._panel.w) // 2)
        self._panel.y = MAP_OFFSET_Y + 24

    def take_action(self) -> str | None:
        action = self._pending
        self._pending = None
        return action

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self._open:
            return False
        if event.type == pygame.MOUSEWHEEL:
            self._scroll = max(0, self._scroll - event.y * ROW_H)
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            if self._close_rect.collidepoint(pos):
                self.close()
                return True
            if self._title_rect.collidepoint(pos):
                self._moving = True
                self._move_offset = (pos[0] - self._panel.x, pos[1] - self._panel.y)
                return True
            for rect, sort_key in self._header_hits:
                if rect.collidepoint(pos):
                    if self.sort_key == sort_key:
                        self.sort_reverse = not self.sort_reverse
                    else:
                        self.sort_key = sort_key
                        self.sort_reverse = False
                    return True
            for action, rect in self._buttons:
                if rect.collidepoint(pos):
                    self._pending = action
                    return True
            for rect, eid in self._row_hits:
                if rect.collidepoint(pos):
                    if self.mode == "assign":
                        self._pending = f"assign_pick:{eid}"
                    elif self.mode == "hire":
                        self._pending = f"hire_select:{eid}"
                    else:
                        self._pending = f"select_villager:{eid}"
                    return True
            if self._panel.collidepoint(pos):
                return True
            self.close()
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._moving = False
            return self._open
        if event.type == pygame.MOUSEMOTION and self._moving:
            self._panel.x = event.pos[0] - self._move_offset[0]
            self._panel.y = event.pos[1] - self._move_offset[1]
            return True
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.close()
            return True
        return False

    def draw(
        self,
        surface: pygame.Surface,
        entries: list[RosterEntry],
        *,
        mouse_pos: tuple[int, int] | None = None,
        title: str | None = None,
        subtitle: str | None = None,
        show_hire_actions: bool = False,
        can_hire: Callable[[RosterEntry], bool] | None = None,
    ) -> None:
        if not self._open:
            return
        self._entries = entries
        ordered = sort_entries(entries, self.sort_key, reverse=self.sort_reverse)
        if title is None:
            title = {
                "hire": "Travellers",
                "assign": "Assign villager",
                "roster": "Villagers",
            }.get(self.mode, "Villagers")

        show_actions = show_hire_actions or self.mode == "assign"
        # Keep panel wide enough for the live column layout.
        need_w = _table_width(actions=show_actions) + 24
        if self._panel.w < need_w:
            self._panel.w = min(WINDOW_WIDTH - 16, need_w)
            self._panel.x = max(8, (WINDOW_WIDTH - self._panel.w) // 2)

        panel = self._panel
        shadow = panel.move(3, 4)
        sh = pygame.Surface((shadow.w, shadow.h), pygame.SRCALPHA)
        sh.fill((0, 0, 0, 70))
        surface.blit(sh, shadow.topleft)
        pygame.draw.rect(surface, COLOUR_MENU_BG, panel, border_radius=6)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, panel, 2, border_radius=6)

        title_bar = pygame.Rect(panel.x, panel.y, panel.w, TITLE_BAR_H)
        pygame.draw.rect(
            surface,
            (48, 50, 58),
            title_bar,
            border_top_left_radius=6,
            border_top_right_radius=6,
        )
        self._title_rect = pygame.Rect(panel.x, panel.y, panel.w - 32, TITLE_BAR_H)
        surface.blit(
            self.font_title.render(title, True, COLOUR_TEXT),
            (panel.x + 10, panel.y + 6),
        )
        self._close_rect = pygame.Rect(panel.right - 28, panel.y + 4, 22, 20)
        hov = mouse_pos is not None and self._close_rect.collidepoint(mouse_pos)
        self._draw_btn(surface, self._close_rect, "×", hovered=hov)

        self._buttons = []
        self._row_hits = []
        self._header_hits = []

        x = panel.x + PAD
        y = panel.y + TITLE_BAR_H + 6
        inner_w = panel.w - PAD * 2
        if subtitle:
            surface.blit(self.font_small.render(subtitle, True, COLOUR_TEXT_DIM), (x, y))
            y += 16

        cols = _column_layout(x, actions=show_actions)

        # Sortable headers — same x as row cells.
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
            if self.sort_key == sort_key:
                label = ("▼" if self.sort_reverse else "▲") + label
            rect = pygame.Rect(hx, y, w, HEADER_H)
            colour = COLOUR_TEXT if self.sort_key == sort_key else COLOUR_TEXT_DIM
            surface.blit(self.font_tiny.render(label, True, colour), (hx + 2, y + 4))
            self._header_hits.append((rect, sort_key))
        if show_actions:
            surface.blit(
                self.font_tiny.render("Act", True, COLOUR_TEXT_DIM),
                (cols["actions"] + 2, y + 4),
            )
        y += HEADER_H + 4

        view_h = panel.bottom - PAD - y
        content_h = max(ROW_H, len(ordered) * ROW_H)
        max_scroll = max(0, content_h - view_h)
        self._scroll = min(self._scroll, max_scroll)
        view = pygame.Rect(x, y, inner_w, view_h)
        old = surface.get_clip()
        surface.set_clip(view)

        if not ordered:
            surface.blit(
                self.font_small.render("None available.", True, COLOUR_TEXT_DIM),
                (x, y - self._scroll),
            )

        for i, entry in enumerate(ordered):
            row_y = y + i * ROW_H - self._scroll
            row = pygame.Rect(x, row_y, inner_w, ROW_H - 4)
            if not row.colliderect(view):
                continue
            hovered = mouse_pos is not None and row.collidepoint(mouse_pos)
            if hovered:
                pygame.draw.rect(surface, (55, 58, 66), row, border_radius=4)
            pygame.draw.rect(surface, (60, 62, 70), row, 1, border_radius=4)
            self._row_hits.append((row, entry.id))

            # Portrait
            draw_portrait(
                surface,
                cols["portrait"] + PORTRAIT_SIZE // 2,
                row_y + ROW_H // 2 - 2,
                entry.portrait_seed,
                job_colour=entry.job_colour,
            )

            # Name + meta + traits (name column only — clipped width)
            name_x = cols["name"]
            name_max_w = COL_NAME_W - 6
            name = entry.name
            while self.font.size(name)[0] > name_max_w and len(name) > 3:
                name = name[:-2] + "…"
            surface.blit(self.font.render(name, True, COLOUR_TEXT), (name_x, row_y + 6))

            req = "/".join(entry.required_foods) or "—"
            meta_parts = []
            if entry.job:
                meta_parts.append(entry.job)
            if entry.status and entry.kind == "villager":
                meta_parts.append(entry.status)
            meta = " · ".join(meta_parts) if meta_parts else "—"
            while self.font_tiny.size(meta)[0] > name_max_w and len(meta) > 4:
                meta = meta[:-2] + "…"
            surface.blit(
                self.font_tiny.render(meta, True, COLOUR_TEXT_DIM),
                (name_x, row_y + 24),
            )

            traits = []
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

            # Status bars — aligned to En / Sat / Hap columns
            bar_y = row_y + (ROW_H // 2) - 4
            draw_status_bar(
                surface, cols["energy"] + 4, bar_y, COL_BAR_W - 8, 8, entry.energy, kind="energy"
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

            # Requirements column (housing + staple icons)
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

            # Payments: coins/season (and lifetime paid for hired villagers)
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

            # Skills — one per column under Ex…Tr
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

            if show_hire_actions and entry.kind == "traveller":
                ok = can_hire(entry) if can_hire else True
                ax = cols["actions"]
                hire_r = pygame.Rect(ax, row_y + 18, 44, 24)
                pay_r = pygame.Rect(ax + 48, row_y + 18, 40, 24)
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
            elif self.mode == "assign":
                pick_r = pygame.Rect(cols["actions"] + 8, row_y + 18, 56, 24)
                self._draw_btn(
                    surface,
                    pick_r,
                    "Pick",
                    hovered=mouse_pos is not None and pick_r.collidepoint(mouse_pos),
                )
                self._buttons.append((f"assign_pick:{entry.id}", pick_r))

        surface.set_clip(old)

        # Scrollbar
        if content_h > view_h:
            bar_h = max(20, int(view_h * view_h / content_h))
            bar_y = view.y + int((view_h - bar_h) * (self._scroll / max(1, max_scroll)))
            pygame.draw.rect(
                surface,
                (80, 82, 90),
                pygame.Rect(panel.right - 10, bar_y, 5, bar_h),
                border_radius=2,
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


def draw_compact_roster_row(
    surface: pygame.Surface,
    entry: RosterEntry,
    x: int,
    y: int,
    width: int,
    fonts: tuple[pygame.font.Font, pygame.font.Font],
    *,
    selected: bool = False,
) -> int:
    """Draw one compact roster row for the side panel. Returns next y."""
    font, font_tiny = fonts
    row_h = 44
    row = pygame.Rect(x - 4, y - 1, width, row_h)
    if selected:
        pygame.draw.rect(surface, (55, 70, 55), row, border_radius=3)
        pygame.draw.rect(surface, COLOUR_SELECTED_ENTITY, row, 1, border_radius=3)
    draw_portrait(
        surface,
        x + 12,
        y + row_h // 2,
        entry.portrait_seed,
        size=22,
        job_colour=entry.job_colour,
    )
    tx = x + 28
    surface.blit(font.render(entry.name[:14], True, COLOUR_TEXT if selected else COLOUR_TEXT_DIM), (tx, y + 2))
    draw_status_bar(surface, tx, y + 18, 28, 5, entry.energy, kind="energy")
    draw_status_bar(surface, tx + 32, y + 18, 28, 5, entry.satiation, kind="sat")
    draw_status_bar(surface, tx + 64, y + 18, 28, 5, entry.happiness, kind="happy")
    # Top two skills
    tops = sorted(
        ((int(getattr(st, "level", 0)), sk) for sk, st in entry.skills.items()),
        reverse=True,
    )[:3]
    sx = tx
    for lvl, sk in tops:
        surface.blit(
            font_tiny.render(f"{SKILL_SHORT.get(sk, '?')}{lvl}", True, COLOUR_TEXT_DIM),
            (sx, y + 28),
        )
        sx += 28
    return y + row_h + 2
