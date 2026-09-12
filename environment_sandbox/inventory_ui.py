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
GRID_COLS = 6
INV_PANEL_GAP = 10
COLOUR_TEXT = (72, 48, 31)
COLOUR_TEXT_DIM = (112, 84, 58)
SLOT_BG_RGBA = (105, 46, 44, 50)
SLOT_BADGE_BG_RGBA = (105, 46, 44, 170)
SLOT_BADGE_TEXT = (252, 244, 232)
SLOT_BADGE_TEXT_DIM = (232, 214, 196)


def _slot_background(surface: pygame.Surface, rect: pygame.Rect) -> None:
    layer = pygame.Surface(rect.size, pygame.SRCALPHA)
    layer.fill(SLOT_BG_RGBA)
    surface.blit(layer, rect.topleft)


def _slot_badge(
    surface: pygame.Surface,
    rect: pygame.Rect,
    *,
    rgba: tuple[int, int, int, int] = SLOT_BADGE_BG_RGBA,
) -> None:
    layer = pygame.Surface(rect.size, pygame.SRCALPHA)
    layer.fill(rgba)
    surface.blit(layer, rect.topleft)


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
    quality: float | None = None,
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
    _slot_background(surface, cell)
    pygame.draw.rect(surface, border, cell, 1, border_radius=4)

    # Food quality: full bar at top; depletes right→left (empty grows from the right).
    if quality is not None and count is not None and count > 0:
        q = max(0.0, min(1.0, float(quality)))
        meter = pygame.Rect(cell.x + 3, cell.y + 3, cell.w - 6, 4)
        _slot_badge(surface, meter, rgba=(105, 46, 44, 120))
        fill_w = max(0, int(round(meter.w * q)))
        if fill_w > 0:
            fill = pygame.Rect(meter.x, meter.y, fill_w, meter.h)
            # Green → amber → red as quality falls.
            if q > 0.55:
                colour = (90, 170, 90)
            elif q > 0.25:
                colour = (200, 160, 60)
            else:
                colour = (190, 70, 60)
            pygame.draw.rect(surface, colour, fill, border_radius=1)

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
        badge = font_tiny.render(label, True, SLOT_BADGE_TEXT)
        bx = cell.right - badge.get_width() - 3
        by = cell.bottom - badge.get_height() - 2
        _slot_badge(
            surface,
            pygame.Rect(bx - 2, by - 1, badge.get_width() + 4, badge.get_height() + 2),
        )
        surface.blit(badge, (bx, by))

    if dimmed:
        overlay = pygame.Surface((cell.w, cell.h), pygame.SRCALPHA)
        overlay.fill((105, 46, 44, 90))
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
    item_mins: dict[str, int] | None = None,
    inline_stock_controls: bool = False,
    scroll_y: int = 0,
    max_body_h: int | None = None,
    qualities: dict[str, float] | None = None,
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
    y += font.get_linesize() + 4
    surface.blit(font_small.render(subtitle, True, COLOUR_TEXT_DIM), (x0, y))
    y += font_small.get_linesize() + 5

    hits: list[tuple[pygame.Rect, str, str]] = []
    tip_hits: list[tuple[pygame.Rect, str, str]] = []
    hovered: tuple[str, str] | None = None
    keys = present_keys(amounts, allowed)
    configured_keys = {*item_caps} if item_caps else set()
    configured_keys.update(item_mins or {})
    if configured_keys:
        for k in configured_keys:
            if (allowed is None or k in allowed) and k not in keys:
                keys.append(k)
    if not keys:
        surface.blit(
            font_small.render("(empty)", True, COLOUR_TEXT_DIM),
            (x0, y + 8),
        )
        return (y + 28) - y0, hits, tip_hits, None, 28, 28

    cols = max(1, min(GRID_COLS, max(1, width // (GRID_CELL + GRID_GAP))))
    used_w = cols * GRID_CELL
    col_gap = GRID_GAP if cols <= 1 else max(GRID_GAP, (width - used_w) // (cols - 1))
    rows = math.ceil(len(keys) / cols)
    content_h = rows * (GRID_CELL + GRID_GAP) - GRID_GAP
    view_h = content_h if max_body_h is None else min(content_h, max_body_h)
    scroll = max(0, min(int(scroll_y), max(0, content_h - view_h)))
    body = pygame.Rect(x0, y, width, view_h)

    # A distinct plane separates paired inventories and clearly marks the
    # portion of the inspector that can contain more items.

    old_clip = surface.get_clip()
    clipped = body.clip(old_clip) if old_clip.width > 0 else body
    surface.set_clip(clipped)

    for i, key in enumerate(keys):
        col = i % cols
        row = i // cols
        cx = x0 + col * (GRID_CELL + col_gap)
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
        if interactive:
            # Added before the smaller inline controls so reverse hit-testing
            # gives Cap / reserve precedence over the whole cell.
            hits.append((cell, side, key))
        if is_sel:
            bg = (55, 70, 55) if is_hov else (48, 58, 48)
            border = COLOUR_SELECTED_ENTITY
        elif is_hov:
            bg = (55, 62, 50)
            border = COLOUR_SELECTED_ENTITY
        else:
            bg = (42, 44, 52)
            border = COLOUR_TOOLBAR_BORDER
        _slot_background(surface, cell)
        pygame.draw.rect(surface, border, cell, 1, border_radius=4)

        count = int(amounts.get(key, 0))
        if qualities is not None and key in qualities and count > 0:
            q = max(0.0, min(1.0, float(qualities[key])))
            meter = pygame.Rect(cell.x + 3, cell.y + 3, cell.w - 6, 4)
            _slot_badge(surface, meter, rgba=(105, 46, 44, 120))
            fill_w = max(0, int(round(meter.w * q)))
            if fill_w > 0:
                fill = pygame.Rect(meter.x, meter.y, fill_w, meter.h)
                if q > 0.55:
                    colour = (90, 170, 90)
                elif q > 0.25:
                    colour = (200, 160, 60)
                else:
                    colour = (190, 70, 60)
                pygame.draw.rect(surface, colour, fill, border_radius=1)

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
        reserve = item_mins.get(key) if item_mins else None
        if inline_stock_controls:
            cap_txt = font_tiny.render(
                f"Cap:{cap if cap is not None else '∞'}", True, SLOT_BADGE_TEXT
            )
            cap_bg = pygame.Rect(
                cell.right - cap_txt.get_width() - 5,
                cell.y + 2,
                cap_txt.get_width() + 3,
                cap_txt.get_height() + 2,
            )
            _slot_badge(surface, cap_bg)
            surface.blit(cap_txt, (cap_bg.x + 1, cap_bg.y + 1))
            hits.append((cap_bg, "cap", key))
        count_txt = (
            f"{count}/{reserve if reserve is not None else 0}"
            if inline_stock_controls
            else (f"{count}/{cap}" if cap is not None else str(count))
        )
        badge = font_tiny.render(count_txt, True, SLOT_BADGE_TEXT)
        bx = cell.right - badge.get_width() - 3
        by = cell.bottom - badge.get_height() - 2
        _slot_badge(
            surface,
            pygame.Rect(bx - 2, by - 1, badge.get_width() + 4, badge.get_height() + 2),
        )
        surface.blit(badge, (bx, by))
        if inline_stock_controls:
            hits.append((pygame.Rect(bx - 2, by - 1, badge.get_width() + 4, badge.get_height() + 2), "min", key))
        tip_hits.append((cell, side, key))

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
    subtext: str | None = None,
    progress: float | None = None,
) -> None:
    """Draw a free-text tooltip near the cursor.

    Optional ``subtext`` and ``progress`` (0–1) add a skill-style XP line and bar.
    """
    if not text:
        return
    rendered = font.render(text, True, (0, 0, 0))
    sub_rendered = (
        font.render(subtext, True, (40, 40, 40)) if subtext else None
    )
    pad = 4
    bar_h = 6 if progress is not None else 0
    bar_gap = 4 if progress is not None else 0
    sub_h = (sub_rendered.get_height() + 2) if sub_rendered is not None else 0
    inner_w = rendered.get_width()
    if sub_rendered is not None:
        inner_w = max(inner_w, sub_rendered.get_width())
    if progress is not None:
        inner_w = max(inner_w, 88)
    tip = pygame.Rect(
        mouse_pos[0] + 14,
        mouse_pos[1] + 12,
        inner_w + pad * 2,
        rendered.get_height() + sub_h + bar_h + bar_gap + pad * 2,
    )
    if tip.right > surface.get_width() - 4:
        tip.x = mouse_pos[0] - tip.w - 8
    if tip.bottom > surface.get_height() - 4:
        tip.y = mouse_pos[1] - tip.h - 8
    _slot_background(surface, tip)
    y = tip.y + pad
    surface.blit(rendered, (tip.x + pad, y))
    y += rendered.get_height()
    if progress is not None:
        y += bar_gap
        bar = pygame.Rect(tip.x + pad, y, tip.w - pad * 2, bar_h)
        pygame.draw.rect(surface, (55, 55, 60), bar, border_radius=2)
        fill_w = max(0, int(round(bar.w * max(0.0, min(1.0, float(progress))))))
        if fill_w > 0:
            fill = pygame.Rect(bar.x, bar.y, fill_w, bar.h)
            pygame.draw.rect(surface, (70, 175, 85), fill, border_radius=2)
        pygame.draw.rect(surface, (90, 90, 98), bar, 1, border_radius=2)
        y += bar_h
    if sub_rendered is not None:
        y += 2
        surface.blit(sub_rendered, (tip.x + pad, y))


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
    y += font.get_linesize() + 6
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
            _slot_background(surface, cell)
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


def draw_clothing_slots(
    surface: pygame.Surface,
    *,
    origin: tuple[int, int],
    equipped_clothing: dict[str, str] | None,
    mouse_pos: tuple[int, int] | None,
    fonts: tuple[pygame.font.Font, pygame.font.Font, pygame.font.Font],
    interactive: bool = True,
    cols: int = 5,
) -> tuple[int, list[tuple[pygame.Rect, str]], str | None]:
    """Draw hat/shirt/trousers/shoes/bag slots. Returns (height, hits, tip_key)."""
    from entities import CLOTHING_SLOT_LABELS, CLOTHING_SLOTS

    font, font_small, _font_tiny = fonts
    x0, y0 = origin
    y = y0
    worn = dict(equipped_clothing or {})
    surface.blit(font.render("Clothes", True, COLOUR_TEXT), (x0, y))
    y += font.get_linesize() + 6
    hits: list[tuple[pygame.Rect, str]] = []
    tip_key: str | None = None
    label_h = font_small.get_linesize()
    for i, slot in enumerate(CLOTHING_SLOTS):
        col = i % max(1, cols)
        row = i // max(1, cols)
        cell = pygame.Rect(
            x0 + col * (GRID_CELL + GRID_GAP),
            y + label_h + 5 + row * (GRID_CELL + GRID_GAP + label_h + 5),
            GRID_CELL,
            GRID_CELL,
        )
        key = worn.get(slot)
        hovered = mouse_pos is not None and cell.collidepoint(mouse_pos)
        label = {
            "hat": "Hat",
            "shirt": "Shirt",
            "trousers": "Pants",
            "shoes": "Shoes",
            "bag": "Bag",
        }.get(slot, CLOTHING_SLOT_LABELS.get(slot, slot).title())
        lab = font_small.render(label, True, COLOUR_TEXT_DIM)
        surface.blit(
            lab,
            (cell.centerx - lab.get_width() // 2, cell.y - label_h - 5),
        )
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
            _slot_background(surface, cell)
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
                hits.append((cell, f"clothing_unequip:{slot}"))
            else:
                hits.append((cell, f"clothing_equip:{slot}"))
        if hovered:
            tip_key = key if key else f"_empty_{slot}_"
    rows = (len(CLOTHING_SLOTS) + cols - 1) // cols
    return rows * (GRID_CELL + GRID_GAP + label_h + 5) + 8, hits, tip_key
