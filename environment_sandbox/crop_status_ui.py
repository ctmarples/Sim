"""Shared crop calendar table and environmental factor chips for farm/field inspect."""

from __future__ import annotations

import pygame

from icons import blit_icon
from seasons import SEASON_LABELS, SEASON_ORDER, Season
from settings import (
    COLOUR_TEXT,
    COLOUR_TEXT_DIM,
    COLOUR_TOOLBAR_BORDER,
)

CHIP_H = 26
CHIP_GAP = 4
OVERVIEW_ROW_H = 22
SECTION_GAP = 16
COLOUR_TEXT = (72, 48, 31)
COLOUR_TEXT_DIM = (112, 84, 58)


def _scribble_highlight(
    surface: pygame.Surface, rect: pygame.Rect, colour: tuple[int, int, int]
) -> None:
    layer = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.polygon(
        layer,
        (*colour, 62),
        [(1, 3), (rect.w - 2, 1), (rect.w - 1, rect.h - 3), (3, rect.h - 1)],
    )
    pygame.draw.line(
        layer,
        (*colour, 34),
        (3, rect.h // 2 + 1),
        (rect.w - 4, rect.h // 2 - 1),
        max(2, rect.h // 3),
    )
    surface.blit(layer, rect.topleft)


def traffic_colour(t: float) -> tuple[int, int, int]:
    """0 = red (bad), 0.5 = yellow, 1 = green (good)."""
    x = max(0.0, min(1.0, float(t)))
    if x < 0.5:
        u = x * 2.0
        return (220, int(48 + 172 * u), 40)
    u = (x - 0.5) * 2.0
    return (int(220 - 155 * u), int(220 - 20 * u), int(40 + 50 * u))


def _score_t(value: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 1.0 if value >= hi else 0.0
    return max(0.0, min(1.0, (float(value) - lo) / (hi - lo)))


def draw_crop_overview(
    surface: pygame.Surface,
    x: int,
    y: int,
    inner_w: int,
    rows: list[dict],
    current_season: Season | None,
    *,
    fonts: tuple[pygame.font.Font, pygame.font.Font, pygame.font.Font],
    empty_label: str = "No crop plans",
    title: str = "Crops",
) -> int:
    """Season × crop grid with max / estimated harvest yields. Returns next y."""
    font, _font_small, font_tiny = fonts
    surface.blit(font.render(title, True, COLOUR_TEXT), (x, y))
    y += font.get_height() + 7
    season_w = 32
    num_w = 40
    crop_w = max(56, inner_w - 4 * season_w - 2 * num_w - 8)
    headers = ["Crop"] + [SEASON_LABELS[s][:3] for s in SEASON_ORDER] + ["Max", "Est"]
    widths = [crop_w] + [season_w] * 4 + [num_w, num_w]
    col_x = x
    cur_i = (
        SEASON_ORDER.index(current_season) if current_season in SEASON_ORDER else -1
    )
    for i, (head, w) in enumerate(zip(headers, widths)):
        if i == cur_i + 1 and cur_i >= 0:
            _scribble_highlight(surface, pygame.Rect(col_x, y - 1, w, 18), (221, 174, 73))
        surface.blit(
            font_tiny.render(head, True, COLOUR_TEXT_DIM),
            (col_x + 2, y),
        )
        col_x += w
    y += 20
    if not rows:
        surface.blit(font_tiny.render(empty_label, True, COLOUR_TEXT_DIM), (x, y))
        return y + OVERVIEW_ROW_H + SECTION_GAP
    for row in rows:
        col_x = x
        label = str(row.get("label") or row.get("key") or "")
        phases = tuple(row.get("phases") or ("—", "—", "—", "—"))
        cells = [
            label[:10],
            *[str(p) for p in phases[:4]],
            str(int(row.get("max_yield") or 0)),
            str(int(row.get("est_yield") or 0)),
        ]
        key = str(row.get("icon") or row.get("key") or "")
        if key:
            try:
                blit_icon(surface, key, x + 8, y + 7, 12)
            except Exception:
                pass
        for i, (text, w) in enumerate(zip(cells, widths)):
            if i == cur_i + 1 and cur_i >= 0:
                _scribble_highlight(
                    surface, pygame.Rect(col_x, y - 1, w, 19), (229, 204, 139)
                )
            tx = col_x + (14 if i == 0 and key else 2)
            surface.blit(font_tiny.render(text, True, COLOUR_TEXT), (tx, y))
            col_x += w
        y += OVERVIEW_ROW_H
    return y + SECTION_GAP


def overview_height(n_rows: int) -> int:
    n = max(1, int(n_rows))
    # Allow for the taller handwritten heading used by the book UI.
    return 32 + 20 + n * OVERVIEW_ROW_H + SECTION_GAP


def env_factors_height(inner_w: int, n_chips: int = 9) -> int:
    """Chrome height for the Environment chip row(s), including title."""
    approx_chip = 78
    cols = max(1, int(inner_w) // (approx_chip + CHIP_GAP))
    rows = max(1, (max(1, n_chips) + cols - 1) // cols)
    return 18 + rows * CHIP_H + (rows - 1) * CHIP_GAP + 6 + SECTION_GAP


def draw_env_factors(
    surface: pygame.Surface,
    x: int,
    y: int,
    inner_w: int,
    status: dict,
    *,
    fonts: tuple[pygame.font.Font, pygame.font.Font, pygame.font.Font],
    mouse_pos: tuple[int, int] | None = None,
) -> tuple[int, str]:
    """Icon chips for bio / pest / health / pollination / ecology. Returns (next y, hover tip)."""
    font, font_small, _tiny = fonts
    surface.blit(font.render("Environment", True, COLOUR_TEXT), (x, y))
    y += 18
    chips = _env_chips(status)
    cx = x
    row_y = y
    hover_tip = ""
    for icon, label, t, tip in chips:
        text = font_small.render(label, True, COLOUR_TEXT)
        w = 8 + 16 + 4 + text.get_width() + 8
        if cx > x and cx + w > x + inner_w:
            cx = x
            row_y += CHIP_H + CHIP_GAP
        rect = pygame.Rect(cx, row_y, w, CHIP_H)
        colour = traffic_colour(t)
        fill = (colour[0] // 5 + 28, colour[1] // 5 + 28, colour[2] // 5 + 28)
        pygame.draw.rect(surface, fill, rect, border_radius=4)
        pygame.draw.rect(surface, colour, rect, 2, border_radius=4)
        try:
            blit_icon(surface, icon, rect.x + 14, rect.centery, 16)
        except Exception:
            pass
        surface.blit(text, (rect.x + 26, rect.y + (CHIP_H - text.get_height()) // 2))
        if mouse_pos is not None and rect.collidepoint(mouse_pos):
            hover_tip = tip
            pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, rect, 1, border_radius=4)
        cx += w + CHIP_GAP
    return row_y + CHIP_H + 6 + SECTION_GAP, hover_tip


def draw_env_hover(
    surface: pygame.Surface,
    mouse_pos: tuple[int, int] | None,
    tip: str,
    font: pygame.font.Font,
) -> None:
    if not tip or mouse_pos is None:
        return
    lines = _wrap_tip(font, tip, 320)
    if not lines:
        return
    pad = 6
    line_h = font.get_height()
    w = max(font.size(line)[0] for line in lines) + pad * 2
    h = len(lines) * line_h + pad * 2
    tip_rect = pygame.Rect(mouse_pos[0] + 14, mouse_pos[1] + 12, w, h)
    if tip_rect.right > surface.get_width() - 4:
        tip_rect.x = mouse_pos[0] - tip_rect.w - 8
    if tip_rect.bottom > surface.get_height() - 4:
        tip_rect.y = mouse_pos[1] - tip_rect.h - 8
    tip_bg = pygame.Surface(tip_rect.size, pygame.SRCALPHA)
    tip_bg.fill((105, 46, 44, 50))
    surface.blit(tip_bg, tip_rect.topleft)
    for i, line in enumerate(lines):
        surface.blit(
            font.render(line, True, (0, 0, 0)),
            (tip_rect.x + pad, tip_rect.y + pad + i * line_h),
        )


def _wrap_tip(font: pygame.font.Font, text: str, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if font.size(trial)[0] <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _env_chips(
    status: dict,
) -> list[tuple[str, str, float, str]]:
    bio = float(status.get("biodiversity") or 0.0)
    bio_lo = float(status.get("bio_lo") or 1.0)
    bio_mid = float(status.get("bio_mid") or 5.0)
    bio_hi = float(status.get("bio_hi") or 10.0)
    pest = float(status.get("pest_mult") or 1.0)
    pest_bio = float(status.get("pest_from_bio") or pest)
    boost = float(status.get("pest_boost") or 0.0)
    pest_lo = float(status.get("pest_lo") or 0.75)
    pest_hi = float(status.get("pest_hi") or 1.15)
    health = float(status.get("health") or 1.0)
    cap = float(status.get("health_cap") or 1.0)
    hmin = float(status.get("health_min") or 0.7)
    drop = float(status.get("health_drop") or 0.05)
    poll = float(status.get("poll_coverage") or 0.0)
    poll_mult = float(status.get("poll_mult") or 1.0)
    ecology = float(status.get("ecology") or 1.0)
    dist = float(status.get("disturbance") or 0.0)
    eco_floor = float(status.get("ecology_floor") or 0.25)
    fertility = float(status.get("fertility") or 0.0)
    weeds = float(status.get("weeds") or 0.0)
    weed_mult = float(status.get("weed_mult") or 1.0)
    weed_threshold = float(status.get("weed_threshold") or 0.2)
    weed_penalty = float(status.get("weed_penalty") or 0.5)
    erosion = float(status.get("erosion") or 0.0)
    base = int(status.get("base_yield") or 0)
    got = int(status.get("harvest_yield") or 0)

    bio_tip = (
        f"Species diversity {bio:.1f} species nearby "
        f"(low {bio_lo:g} · mid {bio_mid:g} · high {bio_hi:g}). "
        f"Higher richness improves pest control."
    )
    pest_tip = (
        f"Pest control ×{pest:.2f} (from bio ×{pest_bio:.2f}"
        + (f" + treatment {boost:+.2f}" if boost else "")
        + "). Sets the crop-health cap "
        f"(now {cap * 100:.0f}%); does not multiply harvest directly."
    )
    health_tip = (
        f"Crop health {health * 100:.0f}% (cap {cap * 100:.0f}% from pest pressure). "
        f"Health only falls, at most {drop * 100:.0f}% each env sample "
        f"(8× per year), never below {hmin * 100:.0f}%. "
        f"This is the yield pathway for pest pressure."
    )
    poll_tip = (
        f"Bee coverage {poll * 100:.0f}% → yield ×{poll_mult:.2f}. "
        f"Nests in range pollinate the field."
    )
    eco_tip = (
        f"Disturbance {dist * 100:.0f}% → yield ×{ecology:.2f} "
        f"(floor {eco_floor:.2f} at max disturbance). "
        f"Urban, paths and extraction feed this layer."
    )
    fert_pot = float(status.get("fertility_potential") or fertility or 1.0)
    fert_tip = (
        f"Soil fertility {fertility:.2f} / potential {fert_pot:.2f}. "
        f"Healthy cultivated soil is 1.0; harvests deplete the square. "
        f"Higher fertility also grows weeds faster."
    )
    weed_tip = (
        f"Weeds {weeds * 100:.0f}% → harvest ×{weed_mult:.2f} "
        f"(up to −{weed_penalty * 100:.0f}% at full weeds). "
        f"Farmers with a hoe pull weeds at {weed_threshold * 100:.0f}%+; "
        f"that is not a harvest. Left too long, weeds cut the square's yield."
    )
    ero_tip = (
        f"Erosion potential {erosion * 100:.0f}% from height-map slope "
        f"(prebaked, stored in the save). Steeper ground is more at risk."
    )
    harvest_tip = (
        f"Harvest {base}→{got} per tile. "
        f"{base} × poll {poll_mult:.2f} × disturbance {ecology:.2f} "
        f"× health {health:.2f} × fertility {fertility:.2f} "
        f"× weeds {weed_mult:.2f} "
        f"(pest control shapes health over time, not this product)."
    )
    harvest_t = _score_t(got, max(1, int(base * 0.6)), max(base, got))
    return [
        ("deer_male", f"{bio:.1f}", _score_t(bio, bio_lo, bio_hi), bio_tip),
        ("insect_repellant", f"×{pest:.2f}", _score_t(pest, pest_lo, pest_hi), pest_tip),
        (
            "crop_plant_1",
            f"{health * 100:.0f}%",
            _score_t(health, hmin, 1.0),
            health_tip,
        ),
        ("bee", f"×{poll_mult:.2f}", poll, poll_tip),
        (
            "tree_round_1",
            f"×{ecology:.2f}",
            _score_t(ecology, eco_floor, 1.0),
            eco_tip,
        ),
        (
            "mineral_powder",
            f"{fertility * 100:.0f}%",
            fertility,
            fert_tip,
        ),
        (
            "crop_weeds",
            f"{weeds * 100:.0f}%",
            1.0 - weeds,
            weed_tip,
        ),
        (
            "rock",
            f"{erosion * 100:.0f}%",
            1.0 - erosion,
            ero_tip,
        ),
        ("seeds", f"{base}→{got}", harvest_t, harvest_tip),
    ]
