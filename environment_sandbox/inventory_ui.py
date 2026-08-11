"""Shared inventory grid drawing for building / villager inspect dialogs."""

from __future__ import annotations

import math

import pygame

from resources import RESOURCE_KEYS, resource_icon_style, resource_label
from settings import (
    COLOUR_SELECTED_ENTITY,
    COLOUR_TEXT,
    COLOUR_TEXT_DIM,
    COLOUR_TOOLBAR_BORDER,
)

GRID_CELL = 52
GRID_GAP = 4
GRID_COLS = 4
INV_PANEL_GAP = 10


def present_keys(
    amounts: dict[str, int], allowed: tuple[str, ...] | None = None
) -> list[str]:
    keys = allowed if allowed is not None else RESOURCE_KEYS
    return [k for k in keys if int(amounts.get(k, 0)) > 0]


def grid_height(n_items: int, *, cols: int = GRID_COLS) -> int:
    rows = max(1, math.ceil(max(1, n_items) / max(1, cols)))
    return rows * (GRID_CELL + GRID_GAP) - GRID_GAP


def draw_resource_cell(
    surface: pygame.Surface,
    *,
    cell: pygame.Rect,
    key: str,
    count: int | None = None,
    fonts: tuple[pygame.font.Font, pygame.font.Font, pygame.font.Font],
    hovered: bool = False,
    dimmed: bool = False,
    active: bool = False,
    count_label: str | None = None,
) -> None:
    """Draw one inventory-style resource icon cell (optional count / dim)."""
    from icons import blit_icon

    _font, _font_small, font_tiny = fonts
    if active and not dimmed:
        bg = (55, 70, 55) if hovered else (48, 58, 48)
        border = COLOUR_SELECTED_ENTITY
    elif hovered:
        bg = (55, 62, 50)
        border = COLOUR_SELECTED_ENTITY
    else:
        bg = (42, 44, 52)
        border = COLOUR_TOOLBAR_BORDER
    pygame.draw.rect(surface, bg, cell, border_radius=4)
    pygame.draw.rect(surface, border, cell, 1, border_radius=4)

    icon_size = cell.w - 14
    try:
        style = resource_icon_style(key)
        blit_icon(
            surface,
            style.name,
            cell.centerx,
            cell.centery - 4,
            icon_size,
            recolour=style.recolour,
            class_scales=style.class_scales,
            omit_classes=style.omit_classes or None,
        )
        if style.badge_key is not None:
            badge = resource_icon_style(style.badge_key)
            badge_size = max(10, icon_size // 2)
            bx = cell.x + cell.w // 4
            by = cell.y + cell.h // 4
            blit_icon(
                surface,
                badge.name,
                bx,
                by,
                badge_size,
                recolour=badge.recolour,
                class_scales=badge.class_scales,
                omit_classes=badge.omit_classes or None,
            )
    except (FileNotFoundError, OSError, ValueError, TypeError):
        tip = resource_label(key)[:3]
        t = font_tiny.render(tip, True, COLOUR_TEXT)
        surface.blit(
            t,
            (
                cell.centerx - t.get_width() // 2,
                cell.centery - t.get_height() // 2 - 4,
            ),
        )

    label = count_label if count_label is not None else (
        str(count) if count is not None else None
    )
    if label is not None:
        badge = font_tiny.render(label, True, COLOUR_TEXT)
        bx = cell.right - badge.get_width() - 3
        by = cell.bottom - badge.get_height() - 2
        pygame.draw.rect(
            surface,
            (28, 30, 36),
            pygame.Rect(bx - 2, by - 1, badge.get_width() + 4, badge.get_height() + 2),
            border_radius=2,
        )
        surface.blit(badge, (bx, by))

    if dimmed:
        overlay = pygame.Surface((cell.w, cell.h), pygame.SRCALPHA)
        overlay.fill((28, 30, 36, 150))
        surface.blit(overlay, cell.topleft)


def draw_inv_grid(
    surface: pygame.Surface,
    *,
    origin: tuple[int, int],
    width: int,
    title: str,
    subtitle: str,
    amounts: dict[str, int],
    allowed: tuple[str, ...] | None,
    side: str,
    mouse_pos: tuple[int, int] | None,
    fonts: tuple[pygame.font.Font, pygame.font.Font, pygame.font.Font],
    interactive: bool = True,
    hover_inv: tuple[str, str] | None = None,
    selected_key: str | None = None,
    item_caps: dict[str, int] | None = None,
    scroll_y: int = 0,
    max_body_h: int | None = None,
) -> tuple[
    int,
    list[tuple[pygame.Rect, str, str]],
    list[tuple[pygame.Rect, str, str]],
    tuple[str, str] | None,
    int,
    int,
]:
    """Draw an inventory grid.

    Returns
    ``(height, click_hits, tip_hits, hovered_side_key, body_content_h, body_view_h)``.
    When ``max_body_h`` is set, only the icon body scrolls (title stays fixed).
    """
    from icons import blit_icon

    font, font_small, font_tiny = fonts
    x0, y0 = origin
    y = y0
    surface.blit(font.render(title, True, COLOUR_TEXT), (x0, y))
    y += 18
    surface.blit(font_small.render(subtitle, True, COLOUR_TEXT_DIM), (x0, y))
    y += 16

    hits: list[tuple[pygame.Rect, str, str]] = []
    tip_hits: list[tuple[pygame.Rect, str, str]] = []
    hovered: tuple[str, str] | None = None
    keys = present_keys(amounts, allowed)
    if item_caps:
        for k in item_caps:
            if (allowed is None or k in allowed) and k not in keys:
                keys.append(k)
    if not keys:
        surface.blit(
            font_small.render("(empty)", True, COLOUR_TEXT_DIM),
            (x0, y + 8),
        )
        return (y + 28) - y0, hits, tip_hits, None, 28, 28

    cols = max(1, min(GRID_COLS, max(1, width // (GRID_CELL + GRID_GAP))))
    rows = math.ceil(len(keys) / cols)
    content_h = rows * (GRID_CELL + GRID_GAP) - GRID_GAP
    view_h = content_h if max_body_h is None else min(content_h, max_body_h)
    scroll = max(0, min(int(scroll_y), max(0, content_h - view_h)))
    body = pygame.Rect(x0, y, width, view_h)

    old_clip = surface.get_clip()
    clipped = body.clip(old_clip) if old_clip.width > 0 else body
    surface.set_clip(clipped)

    for i, key in enumerate(keys):
        col = i % cols
        row = i // cols
        cx = x0 + col * (GRID_CELL + GRID_GAP)
        cy = y + row * (GRID_CELL + GRID_GAP) - scroll
        cell = pygame.Rect(cx, cy, GRID_CELL, GRID_CELL)
        if not cell.colliderect(body):
            continue
        is_sel = selected_key is not None and selected_key == key
        is_hov = body.collidepoint(mouse_pos or (-1, -1)) and (
            hover_inv == (side, key)
            or (mouse_pos is not None and cell.collidepoint(mouse_pos))
        )
        if is_hov:
            hovered = (side, key)
        if is_sel:
            bg = (55, 70, 55) if is_hov else (48, 58, 48)
            border = COLOUR_SELECTED_ENTITY
        elif is_hov:
            bg = (55, 62, 50)
            border = COLOUR_SELECTED_ENTITY
        else:
            bg = (42, 44, 52)
            border = COLOUR_TOOLBAR_BORDER
        pygame.draw.rect(surface, bg, cell, border_radius=4)
        pygame.draw.rect(surface, border, cell, 1, border_radius=4)

        icon_size = GRID_CELL - 14
        try:
            style = resource_icon_style(key)
            blit_icon(
                surface,
                style.name,
                cell.centerx,
                cell.centery - 4,
                icon_size,
                recolour=style.recolour,
                class_scales=style.class_scales,
                omit_classes=style.omit_classes or None,
            )
            if style.badge_key is not None:
                badge = resource_icon_style(style.badge_key)
                badge_size = max(10, icon_size // 2)
                bx = cell.x + cell.w // 4
                by = cell.y + cell.h // 4
                blit_icon(
                    surface,
                    badge.name,
                    bx,
                    by,
                    badge_size,
                    recolour=badge.recolour,
                    class_scales=badge.class_scales,
                    omit_classes=badge.omit_classes or None,
                )
        except (FileNotFoundError, OSError, ValueError, TypeError):
            tip = resource_label(key)[:3]
            t = font_tiny.render(tip, True, COLOUR_TEXT)
            surface.blit(
                t,
                (
                    cell.centerx - t.get_width() // 2,
                    cell.centery - t.get_height() // 2 - 4,
                ),
            )

        count = int(amounts.get(key, 0))
        cap = item_caps.get(key) if item_caps else None
        count_txt = f"{count}/{cap}" if cap is not None else str(count)
        badge = font_tiny.render(count_txt, True, COLOUR_TEXT)
        bx = cell.right - badge.get_width() - 3
        by = cell.bottom - badge.get_height() - 2
        pygame.draw.rect(
            surface,
            (28, 30, 36),
            pygame.Rect(bx - 2, by - 1, badge.get_width() + 4, badge.get_height() + 2),
            border_radius=2,
        )
        surface.blit(badge, (bx, by))
        tip_hits.append((cell, side, key))
        if interactive:
            hits.append((cell, side, key))

    surface.set_clip(old_clip)
    return (y + view_h) - y0, hits, tip_hits, hovered, content_h, view_h


def draw_item_tooltip(
    surface: pygame.Surface,
    *,
    mouse_pos: tuple[int, int],
    key: str,
    font: pygame.font.Font,
    extra: str | None = None,
) -> None:
    """Draw a small name label near the cursor for a hovered inventory item."""
    label = resource_label(key)
    if extra:
        label = f"{label} — {extra}"
    draw_hover_tooltip(surface, mouse_pos=mouse_pos, text=label, font=font)


def draw_hover_tooltip(
    surface: pygame.Surface,
    *,
    mouse_pos: tuple[int, int],
    text: str,
    font: pygame.font.Font,
) -> None:
    """Draw a free-text tooltip near the cursor."""
    if not text:
        return
    rendered = font.render(text, True, COLOUR_TEXT)
    pad = 4
    tip = pygame.Rect(
        mouse_pos[0] + 14,
        mouse_pos[1] + 12,
        rendered.get_width() + pad * 2,
        rendered.get_height() + pad * 2,
    )
    if tip.right > surface.get_width() - 4:
        tip.x = mouse_pos[0] - tip.w - 8
    if tip.bottom > surface.get_height() - 4:
        tip.y = mouse_pos[1] - tip.h - 8
    pygame.draw.rect(surface, (28, 30, 36), tip, border_radius=3)
    pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, tip, 1, border_radius=3)
    surface.blit(rendered, (tip.x + pad, tip.y + pad))


def draw_tool_slot(
    surface: pygame.Surface,
    *,
    origin: tuple[int, int],
    equipped_tools: list[str] | None = None,
    equipped_tool: str | None = None,
    mouse_pos: tuple[int, int] | None,
    fonts: tuple[pygame.font.Font, pygame.font.Font, pygame.font.Font],
    interactive: bool = True,
) -> tuple[int, list[tuple[pygame.Rect, str]], str | None]:
    """Draw up to three tool slots. Returns (height, click_hits, hovered_tool_key)."""
    from entities import TOOL_SLOT_MAX

    font, font_small, _font_tiny = fonts
    x0, y0 = origin
    y = y0
    tools = list(equipped_tools or [])
    if equipped_tool and equipped_tool not in tools:
        tools.insert(0, equipped_tool)
    surface.blit(font.render("Tools", True, COLOUR_TEXT), (x0, y))
    y += 18
    hits: list[tuple[pygame.Rect, str]] = []
    tip_key: str | None = None
    for i in range(TOOL_SLOT_MAX):
        cell = pygame.Rect(x0 + i * (GRID_CELL + GRID_GAP), y, GRID_CELL, GRID_CELL)
        key = tools[i] if i < len(tools) else None
        hovered = mouse_pos is not None and cell.collidepoint(mouse_pos)
        if key:
            draw_resource_cell(
                surface,
                cell=cell,
                key=key,
                fonts=fonts,
                hovered=hovered,
                active=True,
            )
        else:
            bg = (55, 62, 50) if hovered else (36, 38, 44)
            border = COLOUR_SELECTED_ENTITY if hovered else COLOUR_TOOLBAR_BORDER
            pygame.draw.rect(surface, bg, cell, border_radius=4)
            pygame.draw.rect(surface, border, cell, 1, border_radius=4)
            dash = font_small.render("—", True, COLOUR_TEXT_DIM)
            surface.blit(
                dash,
                (
                    cell.centerx - dash.get_width() // 2,
                    cell.centery - dash.get_height() // 2,
                ),
            )
        if interactive:
            if key:
                hits.append((cell, f"tool_unequip:{key}"))
            elif len(tools) < TOOL_SLOT_MAX and i == len(tools):
                hits.append((cell, "tool_equip"))
        if hovered:
            tip_key = key if key else "_empty_tool_"
    row_w = TOOL_SLOT_MAX * GRID_CELL + (TOOL_SLOT_MAX - 1) * GRID_GAP
    return y + GRID_CELL + 8 - y0, hits, tip_key
