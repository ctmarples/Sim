"""Cause→effect status mods for villager / player inspect UIs.

Buffs and debuffs are compound icons: effect (large) + cause badge (bottom-right).
Hovering a cause highlights its effects; hovering an effect highlights its cause.
"""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from icons import blit_icon
from inventory_ui import GRID_CELL, GRID_GAP
from resource_balance import food_def, format_buff_mult, scale_recipe_mult
from resources import resource_icon
from seasons import ambient_temperature_c, temperature_impact
from settings import (
    COLOUR_TEXT,
    COLOUR_TEXT_DIM,
    COLOUR_TOOLBAR_BORDER,
    COLOUR_TOOLBAR_BTN,
    COLOUR_TOOLBAR_BTN_HOVER,
)
from villager_roster import SKILL_COL_W

# Compound mod tiles match inventory grid cells.
MOD_CELL = GRID_CELL
MOD_GAP = GRID_GAP
COLOUR_TEXT = (72, 48, 31)
COLOUR_TEXT_DIM = (112, 84, 58)
_SLOT_BG_RGBA = (105, 46, 44, 50)

# Dedicated effect glyph icons (bottom-right of compound mods).
_EFFECT_ICON_NAMES: dict[str, str] = {
    "walk": "walk_speed",
    "work": "work_efficiency",
    "hunger": "meat_marker",
    "energy": "energy_drain",
    "happiness": "happiness",
    "ration": "bread",
}
EFFECT_LABELS: dict[str, str] = {
    "walk": "Walk speed",
    "work": "Work efficiency",
    "hunger": "Hunger rate",
    "energy": "Energy drain",
    "happiness": "Happiness",
    "ration": "Rations",
}

HIGHLIGHT_BORDER = (240, 200, 70)
TEMP_CAUSE_ICONS: dict[str, str] = {"hot": "hot", "cold": "cold"}
TEMP_CAUSE_LABELS: dict[str, str] = {"hot": "Hot", "cold": "Cold"}


def effect_icon(effect: str) -> str:
    return _EFFECT_ICON_NAMES.get(effect, effect)


@dataclass(frozen=True)
class StatusMod:
    """One cause→effect multiplier shown as a compound buff/debuff icon."""

    cause_key: str
    cause_icon: str
    cause_group: str  # meal | events | gear | political
    effect: str  # walk | work | hunger | energy | happiness | ration
    mult: float
    cause_label: str | None = None  # short cause name for badge hover
    tip_override: str | None = None  # short effect tip override only
    display_kind: str | None = None  # "buff" | "debuff" | None (auto from mult)

    @property
    def label(self) -> str:
        return EFFECT_LABELS.get(self.effect, self.effect)

    @property
    def cause_name(self) -> str:
        if self.cause_label:
            return self.cause_label
        if self.cause_group == "meal":
            from resources import resource_label

            try:
                return resource_label(self.cause_key)
            except Exception:
                return str(self.cause_key).replace("_", " ").title()
        if self.cause_group == "events":
            return TEMP_CAUSE_LABELS.get(self.cause_key, self.cause_key.title())
        if self.cause_group == "gear":
            from resources import resource_label

            try:
                return resource_label(self.cause_key)
            except Exception:
                return str(self.cause_key).replace("_", " ").title()
        return str(self.cause_key).replace("_", " ").title()

    @property
    def effect_tip(self) -> str:
        """Tooltip when hovering the main effect slot."""
        if self.tip_override:
            return self.tip_override
        if self.effect == "happiness":
            return f"Happiness {int(round(self.mult)):+d}"
        if self.effect == "ration":
            return "Shared rations"
        return f"{self.label} ×{format_buff_mult(self.mult)}"

    @property
    def tip(self) -> str:
        return self.effect_tip

    @property
    def is_buff(self) -> bool:
        if self.display_kind == "buff":
            return True
        if self.display_kind == "debuff":
            return False
        if self.effect in ("hunger", "energy"):
            return self.mult < 0.99
        if self.effect == "happiness":
            return self.mult > 0
        return self.mult > 1.01

    @property
    def is_debuff(self) -> bool:
        if self.display_kind == "debuff":
            return True
        if self.display_kind == "buff":
            return False
        if self.effect == "happiness":
            return self.mult < 0
        if abs(self.mult - 1.0) <= 0.01:
            return False
        return not self.is_buff


def cause_badge_rect(slot: pygame.Rect) -> pygame.Rect:
    """Bottom-right cause badge plate inside a compound mod slot."""
    pad = max(4, slot.w // 10)
    cause_size = max(14, slot.w // 3)
    plate = pygame.Rect(0, 0, cause_size + 4, cause_size + 4)
    plate.center = (
        slot.right - cause_size // 2 - pad,
        slot.bottom - cause_size // 2 - pad,
    )
    return plate


@dataclass(frozen=True)
class HoverState:
    """Active hover on a compound mod and/or a cause tile (meal / events)."""

    mod: StatusMod | None = None
    cause: tuple[str, str] | None = None  # (group, key)


def mod_is_highlighted(mod: StatusMod, hover: HoverState | None) -> bool:
    if hover is None:
        return False
    if hover.mod is not None:
        if hover.mod is mod:
            return True
        if (
            hover.mod.cause_group == mod.cause_group
            and hover.mod.cause_key == mod.cause_key
        ):
            return True
    if hover.cause is not None:
        group, key = hover.cause
        return mod.cause_group == group and mod.cause_key == key
    return False


def cause_is_highlighted(group: str, key: str, hover: HoverState | None) -> bool:
    if hover is None:
        return False
    if hover.cause == (group, key):
        return True
    if hover.mod is not None:
        return hover.mod.cause_group == group and hover.mod.cause_key == key
    return False


def resolve_hover_state(
    mouse_pos: tuple[int, int] | None,
    *,
    meal_keys: list[str],
    meal_x: int,
    meal_y: int,
    buffs: list[StatusMod],
    debuffs: list[StatusMod],
    buff_x: int,
    buff_y: int,
    debuff_x: int,
    debuff_y: int,
    temp_event: dict | None,
    event_x: int,
    event_y: int,
    cell_size: int = MOD_CELL,
    gap: int = MOD_GAP,
) -> HoverState:
    """Detect hover on compound mods or cause tiles."""
    if mouse_pos is None:
        return HoverState()
    mx, my = mouse_pos

    cx = meal_x
    for key in meal_keys:
        if pygame.Rect(cx, meal_y, cell_size, cell_size).collidepoint(mx, my):
            return HoverState(cause=("meal", key))
        cx += cell_size + gap

    if temp_event is not None:
        key = str(temp_event["key"])
        if pygame.Rect(event_x, event_y, cell_size, cell_size).collidepoint(mx, my):
            return HoverState(cause=("events", key))

    for mods, row_x, row_y in ((buffs, buff_x, buff_y), (debuffs, debuff_x, debuff_y)):
        cx = row_x
        for mod in mods:
            if pygame.Rect(cx, row_y, cell_size, cell_size).collidepoint(mx, my):
                return HoverState(mod=mod)
            cx += cell_size + gap

    return HoverState()


def collect_status_mods(
    *,
    last_meal: list[str] | None,
    inventory,
    calendar_day: int,
    satiation: float | None = None,
    happiness: float | None = None,
    villager: object | None = None,
) -> list[StatusMod]:
    mods: list[StatusMod] = []
    for key in list(last_meal or [])[:3]:
        fx = food_def(key)
        icon = resource_icon(key)
        for effect, mult in (
            ("walk", scale_recipe_mult(float(fx.walk_speed), "speed")),
            ("work", scale_recipe_mult(float(fx.work_efficiency), "work")),
            ("hunger", scale_recipe_mult(float(fx.hunger_rate), "hunger")),
        ):
            if abs(mult - 1.0) <= 0.01:
                continue
            mods.append(
                StatusMod(
                    cause_key=str(key),
                    cause_icon=icon,
                    cause_group="meal",
                    effect=effect,
                    mult=mult,
                )
            )

    for cloth_key in getattr(inventory, "equipped_clothing", {}).values():
        from recipes import clothing_walk_mult

        walk = clothing_walk_mult(cloth_key)
        if abs(walk - 1.0) > 0.01:
            mods.append(
                StatusMod(
                    cause_key=str(cloth_key),
                    cause_icon=resource_icon(cloth_key),
                    cause_group="gear",
                    effect="walk",
                    mult=float(walk),
                )
            )

    impact = temperature_impact(
        ambient_temperature_c(calendar_day),
        float(getattr(inventory, "gear_heat_protection", 0.0) or 0.0),
        float(getattr(inventory, "gear_cold_protection", 0.0) or 0.0),
    )
    if impact.active:
        cause_key = impact.kind
        cause_icon = TEMP_CAUSE_ICONS.get(impact.kind, "hot")
        if abs(impact.walk_mult - 1.0) > 0.01:
            mods.append(
                StatusMod(
                    cause_key=cause_key,
                    cause_icon=cause_icon,
                    cause_group="events",
                    effect="walk",
                    mult=float(impact.walk_mult),
                )
            )
        if abs(impact.energy_mult - 1.0) > 0.01:
            mods.append(
                StatusMod(
                    cause_key=cause_key,
                    cause_icon=cause_icon,
                    cause_group="events",
                    effect="energy",
                    mult=float(impact.energy_mult),
                )
            )

    if satiation is not None:
        from entities import satiation_walk_mult, satiation_work_mult

        work = satiation_work_mult(satiation)
        walk = satiation_walk_mult(satiation)
        if work < 0.99:
            severe = work <= 0.81
            mods.append(
                StatusMod(
                    cause_key="hungry" if not severe else "starving",
                    cause_icon="meat_marker",
                    cause_group="events",
                    effect="work",
                    mult=work,
                    cause_label="Starving" if severe else "Hungry",
                    display_kind="debuff",
                )
            )
        if walk < 0.99:
            mods.append(
                StatusMod(
                    cause_key="starving",
                    cause_icon="meat_marker",
                    cause_group="events",
                    effect="walk",
                    mult=walk,
                    cause_label="Starving",
                    display_kind="debuff",
                )
            )

    if villager is not None:
        from society import active_happiness_status_mods
        from traits import iter_trait_effects

        mods.extend(active_happiness_status_mods(villager))
        for name, effect in iter_trait_effects(villager):
            tip = effect.tip or name
            for effect_key, mult in (
                ("work", effect.work),
                ("walk", effect.walk),
                ("hunger", effect.hunger),
            ):
                if abs(float(mult) - 1.0) <= 0.01:
                    continue
                # Hunger: lower rate is beneficial.
                if effect_key == "hunger":
                    beneficial = float(mult) < 1.0
                else:
                    beneficial = float(mult) > 1.0
                mods.append(
                    StatusMod(
                        cause_key=f"trait_{name}_{effect_key}",
                        cause_icon="stew",
                        cause_group="events",
                        effect=effect_key,
                        mult=float(mult),
                        cause_label=name,
                        tip_override=tip,
                        display_kind="buff" if beneficial else "debuff",
                    )
                )
    elif happiness is not None:
        from society import (
            HAPPINESS_BAND_LABELS,
            HappinessBand,
            happiness_band,
            happiness_work_mult,
        )

        band = happiness_band(happiness)
        work = happiness_work_mult(happiness)
        if band != HappinessBand.CONTENT:
            mods.append(
                StatusMod(
                    cause_key=f"mood_{band.value}",
                    cause_icon="stew",
                    cause_group="events",
                    effect="work",
                    mult=float(work),
                    cause_label=HAPPINESS_BAND_LABELS[band],
                    tip_override=f"Work efficiency ×{work:.2f}",
                    display_kind="buff" if work > 1.01 else "debuff",
                )
            )
    return mods


def effect_totals(
    *,
    food_walk: float,
    food_work: float,
    food_hunger: float,
    inventory,
    calendar_day: int,
    work_extra_mult: float = 1.0,
    satiation: float | None = None,
    happiness: float | None = None,
) -> tuple[float, float, float]:
    impact = temperature_impact(
        ambient_temperature_c(calendar_day),
        float(getattr(inventory, "gear_heat_protection", 0.0) or 0.0),
        float(getattr(inventory, "gear_cold_protection", 0.0) or 0.0),
    )
    gear = float(getattr(inventory, "gear_walk_mult", 1.0) or 1.0)
    sat_walk = 1.0
    sat_work = 1.0
    if satiation is not None:
        from entities import satiation_walk_mult, satiation_work_mult

        sat_walk = satiation_walk_mult(satiation)
        sat_work = satiation_work_mult(satiation)
    mood_work = 1.0
    if happiness is not None:
        from society import happiness_work_mult

        mood_work = happiness_work_mult(happiness)
    walk = max(0.05, float(food_walk) * gear * float(impact.walk_mult) * sat_walk)
    work = max(
        0.05,
        float(food_work) * max(0.05, float(work_extra_mult)) * sat_work * mood_work,
    )
    hunger = max(0.05, float(food_hunger))
    return walk, work, hunger


def active_temp_event(inventory, calendar_day: int) -> dict | None:
    impact = temperature_impact(
        ambient_temperature_c(calendar_day),
        float(getattr(inventory, "gear_heat_protection", 0.0) or 0.0),
        float(getattr(inventory, "gear_cold_protection", 0.0) or 0.0),
    )
    if not impact.active:
        return None
    label = TEMP_CAUSE_LABELS.get(impact.kind, impact.kind.title())
    return {
        "key": impact.kind,
        "icon": TEMP_CAUSE_ICONS.get(impact.kind, "hot"),
        "label": f"{label} (level {impact.level})",
        "tip": (
            f"{label} level {impact.level} at {impact.temp_c:.0f}C — "
            f"walk ×{format_buff_mult(impact.walk_mult)}, "
            f"energy drain ×{format_buff_mult(impact.energy_mult)}"
        ),
    }


def draw_effect_total_columns(
    surface: pygame.Surface,
    x: int,
    y: int,
    *,
    walk: float,
    work: float,
    hunger: float,
    font: pygame.font.Font,
    icon_size: int = 14,
    col_w: int = SKILL_COL_W,
) -> tuple[int, list[tuple[pygame.Rect, str]]]:
    """Draw walk/work/hunger totals as skill-table columns (icon + ×mult)."""
    cur = x
    tips: list[tuple[pygame.Rect, str]] = []
    for effect, mult in (("walk", walk), ("work", work), ("hunger", hunger)):
        cx = cur + col_w // 2
        try:
            blit_icon(surface, effect_icon(effect), cx, y + icon_size // 2, icon_size)
        except Exception:
            pass
        shown = format_buff_mult(mult)
        mult_t = font.render(f"×{shown}", True, COLOUR_TEXT)
        surface.blit(mult_t, (cx - mult_t.get_width() // 2, y + icon_size + 1))
        tip_rect = pygame.Rect(cur, y, col_w, icon_size + 14)
        tips.append((tip_rect, f"{EFFECT_LABELS[effect]} ×{shown}"))
        cur += col_w
    return cur - x, tips


def draw_compound_mod_icon(
    surface: pygame.Surface,
    rect: pygame.Rect,
    mod: StatusMod,
    *,
    hovered: bool = False,
    highlighted: bool = False,
) -> None:
    """Draw effect (large) + cause badge (bottom-right) compound icon."""
    if highlighted:
        colour = COLOUR_TOOLBAR_BTN_HOVER
    elif hovered:
        colour = COLOUR_TOOLBAR_BTN_HOVER
    else:
        colour = COLOUR_TOOLBAR_BTN
    layer = pygame.Surface(rect.size, pygame.SRCALPHA)
    layer.fill(_SLOT_BG_RGBA)
    surface.blit(layer, rect.topleft)
    edge = HIGHLIGHT_BORDER if highlighted else COLOUR_TOOLBAR_BORDER
    width = 2 if highlighted else 1
    pygame.draw.rect(surface, edge, rect, width, border_radius=4)

    pad = max(4, rect.w // 10)
    effect_size = max(16, rect.w - pad * 2 - 12)
    cause_size = max(14, rect.w // 3)
    blit_icon(
        surface,
        effect_icon(mod.effect),
        rect.x + pad + effect_size // 2,
        rect.y + pad + effect_size // 2,
        effect_size,
    )
    cx = rect.right - cause_size // 2 - pad
    cy = rect.bottom - cause_size // 2 - pad
    plate = pygame.Rect(0, 0, cause_size + 4, cause_size + 4)
    plate.center = (cx, cy)
    pygame.draw.rect(surface, (30, 32, 38), plate, border_radius=3)
    pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, plate, 1, border_radius=3)
    blit_icon(surface, mod.cause_icon, cx, cy, cause_size)


def draw_mod_row(
    surface: pygame.Surface,
    x: int,
    y: int,
    mods: list[StatusMod],
    *,
    mouse_pos: tuple[int, int] | None,
    hover: HoverState | None = None,
    icon_size: int = MOD_CELL,
    gap: int = MOD_GAP,
) -> tuple[
    int,
    list[tuple[pygame.Rect, StatusMod]],
    StatusMod | None,
    list[tuple[pygame.Rect, str]],
]:
    """Draw compound mods.

    Returns ``(width, hits, mod under cursor, tip_hits)``.
    Tip hits list badge cause names before slot effect tips so badge hover wins.
    """
    cur = x
    hits: list[tuple[pygame.Rect, StatusMod]] = []
    tip_hits: list[tuple[pygame.Rect, str]] = []
    hovered_mod: StatusMod | None = None
    if not mods:
        return 0, hits, None, tip_hits
    for mod in mods:
        rect = pygame.Rect(cur, y, icon_size, icon_size)
        pointer = mouse_pos is not None and rect.collidepoint(mouse_pos)
        if pointer:
            hovered_mod = mod
        draw_compound_mod_icon(
            surface,
            rect,
            mod,
            hovered=pointer,
            highlighted=mod_is_highlighted(mod, hover),
        )
        hits.append((rect, mod))
        tip_hits.append((cause_badge_rect(rect), mod.cause_name))
        tip_hits.append((rect, mod.effect_tip))
        cur += icon_size + gap
    return cur - x, hits, hovered_mod, tip_hits
