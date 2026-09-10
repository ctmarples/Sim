"""Villager virtue / vice traits → gameplay multipliers.

Every trait in ``VIRTUE_POOL`` / ``VICE_POOL`` must appear here with at least one
mechanical effect. Magnitudes are balanced across the full catalogue (not only
traits present in a given save).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class TraitEffect:
    """Relative multipliers / additives applied while the trait is present."""

    work: float = 1.0
    walk: float = 1.0
    hunger: float = 1.0
    break_chance: float = 1.0
    break_duration: float = 1.0
    happiness_target: float = 0.0  # ongoing target shift
    meal_food_delta: int = 0  # ±max food types/units at a meal
    meal_mood_scale: float = 1.0  # scale favourite/disliked temporary caps
    label: str = ""
    tip: str = ""


# Ordinary trait swing ≈ 0.04–0.08 happiness, 5–10% speed/work, mild break bias.
TRAIT_EFFECTS: dict[str, TraitEffect] = {
    # --- Virtues ---
    "Hardy": TraitEffect(
        hunger=0.90,
        walk=1.04,
        label="Hardy",
        tip="Hungers slower; walks a little faster",
    ),
    "Cheerful": TraitEffect(
        happiness_target=0.04,
        break_chance=0.85,
        label="Cheerful",
        tip="Happier baseline; fewer morale breaks",
    ),
    "Diligent": TraitEffect(
        work=1.08,
        label="Diligent",
        tip="+8% work speed",
    ),
    "Patient": TraitEffect(
        break_chance=0.88,
        break_duration=0.85,
        label="Patient",
        tip="Fewer, shorter breaks",
    ),
    "Loyal": TraitEffect(
        happiness_target=0.03,
        work=1.03,
        label="Loyal",
        tip="Steady morale; slight work bonus",
    ),
    "Curious": TraitEffect(
        walk=1.07,
        meal_food_delta=1,
        label="Curious",
        tip="Faster on foot; samples one extra food at meals",
    ),
    "Steady": TraitEffect(
        meal_mood_scale=0.75,
        break_chance=0.90,
        label="Steady",
        tip="Meal moods hit softer; steadier work rhythm",
    ),
    "Kind": TraitEffect(
        happiness_target=0.03,
        hunger=0.95,
        label="Kind",
        tip="Gentle morale lift; slightly slower hunger",
    ),
    # --- Vices ---
    "Glutton": TraitEffect(
        hunger=1.15,
        meal_food_delta=1,
        label="Glutton",
        tip="Hungers faster; takes more food per meal",
    ),
    "Lazy": TraitEffect(
        work=0.90,
        break_chance=1.30,
        break_duration=1.15,
        label="Lazy",
        tip="Slower work; more and longer breaks",
    ),
    "Greedy": TraitEffect(
        happiness_target=-0.03,
        meal_food_delta=1,
        meal_mood_scale=1.15,
        label="Greedy",
        tip="Lower morale; grabs extra food; stronger meal moods",
    ),
    "Moody": TraitEffect(
        meal_mood_scale=1.35,
        break_chance=1.20,
        happiness_target=-0.02,
        label="Moody",
        tip="Stronger meal moods; more breaks; slightly gloomier",
    ),
    "Restless": TraitEffect(
        walk=1.06,
        break_chance=1.25,
        break_duration=0.90,
        label="Restless",
        tip="Quick on foot; breaks often but briefly",
    ),
    "Picky": TraitEffect(
        meal_mood_scale=1.40,
        meal_food_delta=-1,
        hunger=1.08,
        label="Picky",
        tip="Stronger food moods; fewer foods per meal; hungers faster",
    ),
    "Stubborn": TraitEffect(
        work=1.05,
        walk=0.94,
        happiness_target=-0.03,
        label="Stubborn",
        tip="Works hard but slowly afoot; lower morale",
    ),
    "Nervous": TraitEffect(
        walk=0.94,
        break_chance=1.25,
        hunger=1.08,
        label="Nervous",
        tip="Slower steps; more breaks; hungers faster",
    ),
}


def _traits_of(villager: object) -> list[str]:
    names: list[str] = []
    for key in ("virtues", "vices"):
        for name in getattr(villager, key, None) or []:
            text = str(name).strip()
            if text:
                names.append(text)
    return names


def iter_trait_effects(villager: object) -> Iterable[tuple[str, TraitEffect]]:
    for name in _traits_of(villager):
        effect = TRAIT_EFFECTS.get(name)
        if effect is not None:
            yield name, effect


def trait_work_mult(villager: object) -> float:
    mult = 1.0
    for _, effect in iter_trait_effects(villager):
        mult *= float(effect.work)
    return mult


def trait_walk_mult(villager: object) -> float:
    mult = 1.0
    for _, effect in iter_trait_effects(villager):
        mult *= float(effect.walk)
    return mult


def trait_hunger_mult(villager: object) -> float:
    mult = 1.0
    for _, effect in iter_trait_effects(villager):
        mult *= float(effect.hunger)
    return mult


def trait_break_chance_mult(villager: object) -> float:
    mult = 1.0
    for _, effect in iter_trait_effects(villager):
        mult *= float(effect.break_chance)
    return mult


def trait_break_duration_mult(villager: object) -> float:
    mult = 1.0
    for _, effect in iter_trait_effects(villager):
        mult *= float(effect.break_duration)
    return mult


def trait_happiness_target_bonus(villager: object) -> float:
    total = 0.0
    for _, effect in iter_trait_effects(villager):
        total += float(effect.happiness_target)
    return total


def trait_meal_food_delta(villager: object) -> int:
    total = 0
    for _, effect in iter_trait_effects(villager):
        total += int(effect.meal_food_delta)
    return total


def trait_meal_mood_scale(villager: object) -> float:
    scale = 1.0
    for _, effect in iter_trait_effects(villager):
        scale *= float(effect.meal_mood_scale)
    return scale


def trait_happiness_components(villager: object) -> list[tuple[str, str, float]]:
    """(key, label, amount) ongoing happiness target pieces from traits."""
    out: list[tuple[str, str, float]] = []
    for name, effect in iter_trait_effects(villager):
        if abs(effect.happiness_target) < 1e-9:
            continue
        out.append(
            (
                f"trait_{name.lower()}",
                effect.label or name,
                float(effect.happiness_target),
            )
        )
    return out


def missing_trait_definitions(virtue_pool: Iterable[str], vice_pool: Iterable[str]) -> list[str]:
    """Traits listed in pools but missing from TRAIT_EFFECTS."""
    missing = []
    for name in list(virtue_pool) + list(vice_pool):
        if name not in TRAIT_EFFECTS:
            missing.append(name)
    return missing
