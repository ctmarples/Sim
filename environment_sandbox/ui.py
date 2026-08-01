"""UI panel, legends, and text helpers (scrollable side panel)."""

from __future__ import annotations

import pygame

from entities import (
    BUILDING_LABELS,
    TASK_LABELS,
    Building,
    BuildingKind,
    HomeStorage,
    Inventory,
    Player,
    Villager,
)
from indicators import OVERLAY_LABELS, OverlayMode
from settings import (
    CELL_SIZE,
    COLOUR_ANIMAL,
    COLOUR_BERRY,
    COLOUR_FORAGER,
    COLOUR_FORESTER,
    COLOUR_GRASS,
    COLOUR_HERB,
    COLOUR_HOME,
    COLOUR_HUNTER,
    COLOUR_MASON,
    COLOUR_MEAT,
    COLOUR_MUSHROOM,
    COLOUR_PANEL_BG,
    COLOUR_PANEL_BORDER,
    COLOUR_PLAYER,
    COLOUR_ROCK_FEATURE,
    COLOUR_SAPLING,
    COLOUR_SOIL,
    COLOUR_STATUS,
    COLOUR_TEXT,
    COLOUR_TEXT_DIM,
    COLOUR_TREE_CANOPY,
    COLOUR_VILLAGER,
    COLOUR_WATER,
    COLOUR_WORKSTATION,
    FORESTER_COST_ROCK,
    FORESTER_COST_WOOD,
    FORAGER_COST_ROCK,
    FORAGER_COST_WOOD,
    GRID_COLS,
    HUNTER_COST_ROCK,
    HUNTER_COST_WOOD,
    INVENTORY_CAPACITY,
    MASON_COST_ROCK,
    MASON_COST_WOOD,
    MAX_VILLAGERS,
    PANEL_WIDTH,
    WINDOW_HEIGHT,
)
from wildlife import WildlifeManager
from world import FeatureType, TerrainType, World


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
    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 13)
        self.font_small = pygame.font.SysFont("menlo", 12)
        self.font_title = pygame.font.SysFont("menlo", 15, bold=True)
        self.scroll_y = 0
        self.content_height = WINDOW_HEIGHT
        # Reused each frame — allocating a tall surface every tick freezes the UI.
        self._content = pygame.Surface((PANEL_WIDTH, WINDOW_HEIGHT))
        self._content.fill(COLOUR_PANEL_BG)

    def scroll(self, delta: int) -> None:
        """delta > 0 scrolls content up (typical mouse-wheel away)."""
        max_scroll = max(0, self.content_height - WINDOW_HEIGHT)
        self.scroll_y = max(0, min(max_scroll, self.scroll_y - delta))

    def _ensure_content_surface(self, height: int) -> pygame.Surface:
        height = max(WINDOW_HEIGHT, height)
        if self._content.get_height() < height:
            self._content = pygame.Surface((PANEL_WIDTH, height))
        return self._content

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
    ) -> None:
        panel_x = GRID_COLS * CELL_SIZE
        # Grow if needed, then clear only the used region.
        content = self._ensure_content_surface(max(self.content_height, WINDOW_HEIGHT + 200))
        content.fill(COLOUR_PANEL_BG)

        x = 10
        y = 8

        y = _blit_text(content, self.font_title, "Environment Sandbox", (x, y))
        y = _blit_text(content, self.font_small, "WASD move · E interact", (x, y), COLOUR_TEXT_DIM)
        y = _blit_text(content, self.font_small, "B build · click select", (x, y), COLOUR_TEXT_DIM)
        y = _blit_text(content, self.font_small, "Drag areas · T task · Esc", (x, y), COLOUR_TEXT_DIM)
        y = _blit_text(content, self.font_small, "Scroll panel: mouse wheel", (x, y), COLOUR_TEXT_DIM)
        y += 6

        y = _blit_text(content, self.font_title, "Player", (x, y))
        cell = world.get_cell(player.x, player.y)
        feat = cell.feature.name if cell else "—"
        y = _blit_text(content, self.font_small, f"({player.x},{player.y}) {feat}", (x, y))
        if cell is not None and cell.deposit > 0:
            if cell.feature.name == "TREE":
                unit = "wood"
            elif cell.feature.name == "BERRY_BUSH":
                unit = "berries"
            else:
                unit = "rock"
            y = _blit_text(
                content,
                self.font_small,
                f"Deposit: {cell.deposit} {unit}",
                (x, y),
                COLOUR_TEXT_DIM,
            )
        if cell is not None and cell.meat_deposit > 0:
            y = _blit_text(
                content,
                self.font_small,
                f"Meat on ground: {cell.meat_deposit}",
                (x, y),
                COLOUR_TEXT_DIM,
            )
        inv: Inventory = player.inventory
        y = _blit_text(
            content,
            self.font,
            f"Carry {inv.wood}w {inv.rock}r {inv.meat}m {inv.saplings}s",
            (x, y),
        )
        y = _blit_text(
            content,
            self.font_small,
            f"  {inv.mushrooms}mush {inv.berries}b {inv.berry_seeds}bs "
            f"{inv.herbs}h {inv.herb_seeds}hs",
            (x, y),
            COLOUR_TEXT_DIM,
        )
        y = _blit_text(
            content,
            self.font_small,
            f"({inv.total}/{INVENTORY_CAPACITY})",
            (x, y),
            COLOUR_TEXT_DIM,
        )
        y += 4

        y = _blit_text(content, self.font_title, "Home storage", (x, y))
        y = _blit_text(
            content,
            self.font,
            f"{home_storage.wood}w {home_storage.rock}r "
            f"{home_storage.meat}m {home_storage.saplings}s",
            (x, y),
        )
        y = _blit_text(
            content,
            self.font_small,
            f"  {home_storage.mushrooms}mush {home_storage.berries}b "
            f"{home_storage.herbs}h",
            (x, y),
            COLOUR_TEXT_DIM,
        )
        y += 4

        y = _blit_text(content, self.font_title, "Build", (x, y))
        if place_kind is None:
            y = _blit_text(content, self.font_small, "Mode: off (press B)", (x, y), COLOUR_TEXT_DIM)
        elif place_kind == BuildingKind.FORESTER:
            y = _blit_text(
                content,
                self.font,
                f"Forester ({FORESTER_COST_WOOD}w/{FORESTER_COST_ROCK}r)",
                (x, y),
            )
        elif place_kind == BuildingKind.MASON:
            y = _blit_text(
                content,
                self.font,
                f"Mason ({MASON_COST_WOOD}w/{MASON_COST_ROCK}r)",
                (x, y),
            )
        elif place_kind == BuildingKind.HUNTER:
            y = _blit_text(
                content,
                self.font,
                f"Hunter ({HUNTER_COST_WOOD}w/{HUNTER_COST_ROCK}r)",
                (x, y),
            )
        else:
            y = _blit_text(
                content,
                self.font,
                f"Forager ({FORAGER_COST_WOOD}w/{FORAGER_COST_ROCK}r)",
                (x, y),
            )
        y += 4

        y = _blit_text(content, self.font_title, "Selection", (x, y))
        if selected_building_id is not None and selected_building_id in buildings:
            b = buildings[selected_building_id]
            y = _blit_text(content, self.font, BUILDING_LABELS[b.kind], (x, y))
            y = _blit_text(
                content,
                self.font_small,
                f"Store {b.wood}w {b.rock}r {b.meat}m {b.saplings}s / {b.capacity}",
                (x, y),
                COLOUR_TEXT_DIM,
            )
            y = _blit_text(
                content,
                self.font_small,
                f"Draw: {TASK_LABELS[b.draw_task_type]}",
                (x, y),
            )
            y = _blit_text(
                content,
                self.font_small,
                f"Areas: {len(b.areas)}",
                (x, y),
                COLOUR_TEXT_DIM,
            )
        elif selected_villager_id is not None:
            y = _blit_text(content, self.font, f"Villager {selected_villager_id}", (x, y))
            y = _blit_text(
                content,
                self.font_small,
                "Click building/home to assign",
                (x, y),
                COLOUR_TEXT_DIM,
            )
        else:
            y = _blit_text(content, self.font_small, "(none)", (x, y), COLOUR_TEXT_DIM)
        y += 4

        y = _blit_text(content, self.font_title, "Buildings", (x, y))
        if not buildings:
            y = _blit_text(content, self.font_small, "None yet", (x, y), COLOUR_TEXT_DIM)
        else:
            for b in buildings.values():
                workers = sum(1 for v in villagers if v.building_id == b.id)
                y = _blit_text(
                    content,
                    self.font_small,
                    f"{BUILDING_LABELS[b.kind]} #{b.id}: "
                    f"{b.stored_total}/{b.capacity} · {workers}w",
                    (x, y),
                    COLOUR_TEXT_DIM,
                )
        y += 4

        y = _blit_text(content, self.font_title, "Villagers", (x, y))
        y = _blit_text(
            content,
            self.font,
            f"Hired {len(villagers)}/{MAX_VILLAGERS}",
            (x, y),
        )
        haulers = sum(1 for v in villagers if v.assigned_to_home)
        y = _blit_text(
            content,
            self.font_small,
            f"Haulers: {haulers}",
            (x, y),
            COLOUR_TEXT_DIM,
        )
        for v in villagers:
            if v.assigned_to_home:
                job = "home"
            elif v.building_id and v.building_id in buildings:
                job = BUILDING_LABELS[buildings[v.building_id].kind][:4]
            else:
                job = "—"
            y = _blit_text(
                content,
                self.font_small,
                f"#{v.id} {v.state.name[:4]} → {job} "
                f"({v.inventory.wood}w{v.inventory.rock}r"
                f"{v.inventory.meat}m{v.inventory.saplings}s)",
                (x, y),
                COLOUR_TEXT_DIM,
            )
        y += 4

        y = _blit_text(content, self.font_title, "Wildlife", (x, y))
        cap = wildlife.total_capacity(world)
        y = _blit_text(
            content,
            self.font_small,
            f"Animals {len(wildlife.animals)}/{cap}",
            (x, y),
            COLOUR_TEXT_DIM,
        )
        y += 4

        y = _blit_text(content, self.font_title, "Overlay", (x, y))
        y = _blit_text(content, self.font_small, OVERLAY_LABELS[overlay_mode], (x, y))
        y += 4

        y = _blit_text(content, self.font_title, "Status", (x, y))
        msg = status_message if status_message else "—"
        colour = COLOUR_STATUS if status_message else COLOUR_TEXT_DIM
        for line in _wrap(msg, 30):
            y = _blit_text(content, self.font_small, line, (x, y), colour)
        y += 6

        y = self._draw_legend(content, x, y)
        y += 12

        # If content grew past the buffer, redraw once onto a larger surface.
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
            )

        self.content_height = max(WINDOW_HEIGHT, y)
        max_scroll = max(0, self.content_height - WINDOW_HEIGHT)
        self.scroll_y = max(0, min(self.scroll_y, max_scroll))

        panel = pygame.Rect(panel_x, 0, PANEL_WIDTH, WINDOW_HEIGHT)
        pygame.draw.rect(surface, COLOUR_PANEL_BG, panel)
        surface.blit(
            content,
            (panel_x, 0),
            pygame.Rect(0, self.scroll_y, PANEL_WIDTH, WINDOW_HEIGHT),
        )
        pygame.draw.line(surface, COLOUR_PANEL_BORDER, (panel_x, 0), (panel_x, WINDOW_HEIGHT), 2)

        if max_scroll > 0:
            track_h = WINDOW_HEIGHT - 16
            thumb_h = max(24, int(track_h * WINDOW_HEIGHT / self.content_height))
            thumb_y = 8 + int((track_h - thumb_h) * (self.scroll_y / max_scroll))
            bar_x = panel_x + PANEL_WIDTH - 8
            pygame.draw.rect(surface, (60, 62, 70), pygame.Rect(bar_x, 8, 4, track_h))
            pygame.draw.rect(surface, (140, 144, 160), pygame.Rect(bar_x, thumb_y, 4, thumb_h))

    def _draw_legend(self, surface: pygame.Surface, x: int, y: int) -> int:
        y = _blit_text(surface, self.font_title, "Legend", (x, y))
        entries = [
            (COLOUR_HOME, "Home"),
            (COLOUR_WORKSTATION, "Hire station"),
            (COLOUR_FORESTER, "Forester"),
            (COLOUR_MASON, "Mason"),
            (COLOUR_HUNTER, "Hunter"),
            (COLOUR_FORAGER, "Forager"),
            (COLOUR_MUSHROOM, "Mushroom"),
            (COLOUR_BERRY, "Berry bush"),
            (COLOUR_HERB, "Herb"),
            (COLOUR_MEAT, "Meat"),
            (COLOUR_PLAYER, "Player"),
            (COLOUR_VILLAGER, "Villager"),
            (COLOUR_ANIMAL, "Wild animal"),
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


def terrain_colour(terrain: TerrainType) -> tuple[int, int, int]:
    from settings import COLOUR_ROCK_TERRAIN

    return {
        TerrainType.SOIL: COLOUR_SOIL,
        TerrainType.GRASS: COLOUR_GRASS,
        TerrainType.WATER: COLOUR_WATER,
        TerrainType.ROCK: COLOUR_ROCK_TERRAIN,
    }[terrain]


def draw_feature(surface: pygame.Surface, feature: FeatureType, cx: int, cy: int, size: int) -> None:
    if feature == FeatureType.NONE:
        return
    if feature == FeatureType.TREE:
        trunk_w = max(2, size // 10)
        trunk_h = size // 4
        pygame.draw.rect(
            surface,
            (90, 55, 30),
            pygame.Rect(cx - trunk_w // 2, cy, trunk_w, trunk_h),
        )
        pygame.draw.circle(surface, COLOUR_TREE_CANOPY, (cx, cy - size // 10), size // 4)
    elif feature == FeatureType.SAPLING:
        pygame.draw.circle(surface, COLOUR_SAPLING, (cx, cy), max(3, size // 8))
        pygame.draw.line(surface, (90, 55, 30), (cx, cy), (cx, cy + size // 8), 2)
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
    elif feature == FeatureType.MUSHROOM:
        pygame.draw.circle(surface, COLOUR_MUSHROOM, (cx, cy - 2), max(4, size // 7))
        pygame.draw.rect(surface, (210, 200, 180), pygame.Rect(cx - 2, cy, 4, size // 8))
    elif feature == FeatureType.BERRY_BUSH:
        pygame.draw.circle(surface, (50, 110, 50), (cx, cy), size // 5)
        for ox, oy in ((-4, -2), (3, -3), (0, 2), (4, 1), (-3, 3)):
            pygame.draw.circle(surface, COLOUR_BERRY, (cx + ox, cy + oy), 2)
    elif feature == FeatureType.HERB:
        for ox in (-3, 0, 3):
            pygame.draw.line(
                surface,
                COLOUR_HERB,
                (cx + ox, cy + 4),
                (cx + ox // 2, cy - 6),
                2,
            )
