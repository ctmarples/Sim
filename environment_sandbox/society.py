"""Villager society: skills, housing, hire pools, communities."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from entities import Building, BuildingKind, Villager


class SkillType(Enum):
    EXTRACTION = auto()
    FARMING = auto()
    HUNTING = auto()
    CRAFTING = auto()
    LABOUR = auto()
    TRANSPORT = auto()


SKILL_LABELS: dict[SkillType, str] = {
    SkillType.EXTRACTION: "Extraction",
    SkillType.FARMING: "Farming",
    SkillType.HUNTING: "Hunting",
    SkillType.CRAFTING: "Crafting",
    SkillType.LABOUR: "Labour",
    SkillType.TRANSPORT: "Transport",
}

# Short labels for compact UI.
SKILL_SHORT: dict[SkillType, str] = {
    SkillType.EXTRACTION: "Ex",
    SkillType.FARMING: "Fa",
    SkillType.HUNTING: "Hu",
    SkillType.CRAFTING: "Cr",
    SkillType.LABOUR: "La",
    SkillType.TRANSPORT: "Tr",
}

# Icon asset names for skill badges.
SKILL_ICONS: dict[SkillType, str] = {
    SkillType.EXTRACTION: "axe",
    SkillType.FARMING: "hoe",
    SkillType.HUNTING: "wooden_spear",
    SkillType.CRAFTING: "craft_bench",
    SkillType.LABOUR: "construction_site",
    SkillType.TRANSPORT: "storehouse",
}

SKILL_ORDER: tuple[SkillType, ...] = tuple(SkillType)

# Efficiency: 1.0 at skill 1 → ~1.72 at skill 10.
SKILL_EFFICIENCY_PER_LEVEL: float = 0.08
# Floor after decay: keep at least this fraction of peak skill level.
SKILL_DECAY_FLOOR_FRAC: float = 0.70
SKILL_IDLE_DAYS_BEFORE_DECAY: float = 8.0
SKILL_XP_DECAY_PER_DAY: float = 4.0
SKILL_XP_PER_ACTION: float = 8.0
SKILL_XP_BASE_TO_NEXT: float = 20.0  # xp_to_next = base * level

# Job → skill used for efficiency / recipe gating (assignment is always allowed).
JOB_SKILL_REQUIREMENTS: dict[str, tuple[SkillType, int]] = {
    "FORESTER": (SkillType.EXTRACTION, 1),
    "MASON": (SkillType.EXTRACTION, 1),
    "FORAGER": (SkillType.EXTRACTION, 1),
    "FISHER": (SkillType.EXTRACTION, 1),
    "HUNTER": (SkillType.HUNTING, 1),
    "FARM": (SkillType.FARMING, 1),
    "FIELD": (SkillType.FARMING, 1),
    "MILL": (SkillType.CRAFTING, 1),
    "KITCHEN": (SkillType.CRAFTING, 1),
    "CRAFT_BENCH": (SkillType.CRAFTING, 1),
    "ALCHEMIST": (SkillType.CRAFTING, 1),
    "TAILOR": (SkillType.CRAFTING, 1),
    "HOME": (SkillType.TRANSPORT, 1),
    "BUILD": (SkillType.LABOUR, 1),
}

# Housing level / beds.
HOUSING_LEVEL: dict[str, int] = {
    "TENT": 1,
    "HOUSE_SMALL": 2,
    "HOUSE": 3,
}
HOUSING_BEDS: dict[str, int] = {
    "TENT": 2,
    "HOUSE_SMALL": 4,
    "HOUSE": 8,
}

# Hire / happiness balance.
HAPPINESS_LEAVE_THRESHOLD: float = 0.18
HAPPINESS_LEAVE_DAYS: float = 5.0
ENERGY_SLEEP_THRESHOLD: float = 0.22
ENERGY_WORK_DRAIN: float = 0.0012
ENERGY_MOVE_DRAIN: float = 0.0004
ENERGY_SLEEP_GAIN: float = 0.004
HAPPINESS_FOOD_VARIETY_BONUS: float = 0.04
HAPPINESS_HOUSING_BONUS_PER_LEVEL: float = 0.06
HAPPINESS_MISSING_REQ_PENALTY: float = 0.08
HAPPINESS_FAVOURITE_MISS_PENALTY: float = 0.05
PAY_TO_JOIN_LOGS: int = 4
PAY_TO_JOIN_WOOD: int = 2
SEASON_MISSING_REQ_PAY_LOGS: int = 2

HIRE_STAPLE_FOODS: tuple[str, ...] = ("meat", "fish", "bread")

VIRTUE_POOL: tuple[str, ...] = (
    "Hardy",
    "Cheerful",
    "Diligent",
    "Patient",
    "Loyal",
    "Curious",
    "Steady",
    "Kind",
)
VICE_POOL: tuple[str, ...] = (
    "Glutton",
    "Lazy",
    "Greedy",
    "Moody",
    "Restless",
    "Picky",
    "Stubborn",
    "Nervous",
)


@dataclass
class SkillState:
    """Integer skill level 1–10 with XP toward the next level."""

    level: int = 1
    xp: float = 0.0
    potential: int = 5
    peak: int = 1
    idle_days: float = 0.0

    def clamp(self) -> None:
        self.potential = max(1, min(10, int(self.potential)))
        self.level = max(1, min(self.potential, int(self.level)))
        self.peak = max(self.peak, self.level, 1)
        self.peak = min(10, int(self.peak))
        self.xp = max(0.0, float(self.xp))
        self.idle_days = max(0.0, float(self.idle_days))
        if self.level >= self.potential:
            self.xp = 0.0

    def xp_to_next(self) -> float:
        if self.level >= self.potential:
            return 0.0
        return SKILL_XP_BASE_TO_NEXT * float(self.level)

    def efficiency(self) -> float:
        return 1.0 + max(0, self.level - 1) * SKILL_EFFICIENCY_PER_LEVEL

    def gain(self, amount: float = SKILL_XP_PER_ACTION) -> None:
        """Gain XP from work; levels up when threshold is reached."""
        self.idle_days = 0.0
        if self.level >= self.potential:
            return
        self.xp += max(0.0, float(amount))
        while self.level < self.potential and self.xp >= self.xp_to_next():
            need = self.xp_to_next()
            if need <= 0:
                break
            self.xp -= need
            self.level += 1
            self.peak = max(self.peak, self.level)
        if self.level >= self.potential:
            self.xp = 0.0
        self.clamp()

    def tick_idle(self, days: float) -> None:
        self.idle_days += days
        if self.idle_days < SKILL_IDLE_DAYS_BEFORE_DECAY:
            return
        floor = max(1, int(self.peak * SKILL_DECAY_FLOOR_FRAC))
        if self.level <= floor and self.xp <= 0:
            return
        self.xp -= SKILL_XP_DECAY_PER_DAY * days
        while self.xp < 0 and self.level > floor:
            self.level -= 1
            # Refund a full prior level's XP bar, then apply remaining debt.
            self.xp += SKILL_XP_BASE_TO_NEXT * float(self.level)
        if self.level <= floor:
            self.xp = max(0.0, self.xp)
        self.clamp()

    def to_dict(self) -> dict:
        return {
            "level": int(self.level),
            "xp": round(self.xp, 4),
            "potential": int(self.potential),
            "peak": int(self.peak),
            "idle_days": round(self.idle_days, 4),
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> SkillState:
        data = data or {}
        # Migrate legacy float levels (0–10 continuous) into int + xp.
        raw_level = data.get("level", 1)
        if isinstance(raw_level, float) and not float(raw_level).is_integer():
            level = max(1, min(10, int(raw_level)))
            frac = float(raw_level) - level
            xp = frac * SKILL_XP_BASE_TO_NEXT * float(level)
        else:
            level = int(raw_level)
            xp = float(data.get("xp", 0.0))
        potential = data.get("potential", 5)
        if isinstance(potential, float):
            potential = max(1, min(10, int(round(potential))))
        peak = data.get("peak", level)
        if isinstance(peak, float):
            peak = max(1, min(10, int(round(peak))))
        s = cls(
            level=level,
            xp=xp,
            potential=int(potential),
            peak=int(peak),
            idle_days=float(data.get("idle_days", 0.0)),
        )
        s.clamp()
        return s


def blank_skills(rng: random.Random | None = None) -> dict[SkillType, SkillState]:
    rng = rng or random.Random()
    out: dict[SkillType, SkillState] = {}
    for skill in SKILL_ORDER:
        potential = rng.randint(4, 10)
        level = rng.randint(1, min(3, potential))
        xp = round(rng.uniform(0.0, SKILL_XP_BASE_TO_NEXT * level * 0.4), 1)
        st = SkillState(level=level, xp=xp, potential=potential, peak=level)
        st.clamp()
        out[skill] = st
    return out


def skills_to_dict(skills: dict[SkillType, SkillState]) -> dict[str, dict]:
    return {s.name.lower(): st.to_dict() for s, st in skills.items()}


def skills_from_dict(data: dict | None) -> dict[SkillType, SkillState]:
    data = data or {}
    out: dict[SkillType, SkillState] = {}
    for skill in SKILL_ORDER:
        raw = data.get(skill.name.lower()) or data.get(skill.name)
        out[skill] = SkillState.from_dict(raw if isinstance(raw, dict) else None)
    return out


def skill_for_building(kind_name: str) -> tuple[SkillType, int]:
    return JOB_SKILL_REQUIREMENTS.get(kind_name, (SkillType.LABOUR, 1))


def villager_meets_skill(villager: Villager, kind_name: str) -> bool:
    """Deprecated for assignment — always True. Kept for callers/tests."""
    return True


def villager_skill_level(villager: Villager, skill: SkillType) -> int:
    state = villager.skills.get(skill)
    if state is None:
        return 1
    return max(1, int(state.level))


def villager_can_use_recipe(villager: Villager, recipe, kind_name: str) -> bool:
    """True if the worker's workplace skill meets the recipe's min_skill."""
    skill, _ = skill_for_building(kind_name)
    need = max(1, int(getattr(recipe, "min_skill", 1) or 1))
    return villager_skill_level(villager, skill) >= need


def skill_efficiency(villager: Villager, skill: SkillType) -> float:
    state = villager.skills.get(skill)
    if state is None:
        return 1.0
    return state.efficiency()


def gain_skill(
    villager: Villager, skill: SkillType, amount: float = SKILL_XP_PER_ACTION
) -> None:
    state = villager.skills.get(skill)
    if state is None:
        state = SkillState()
        villager.skills[skill] = state
    state.gain(amount)


def tick_skill_decay(villager: Villager, day_fraction: float) -> None:
    for state in villager.skills.values():
        state.tick_idle(day_fraction)


def housing_level_of(kind: BuildingKind | str) -> int:
    name = kind.name if hasattr(kind, "name") else str(kind)
    return int(HOUSING_LEVEL.get(name, 0))


def housing_beds_of(kind: BuildingKind | str) -> int:
    name = kind.name if hasattr(kind, "name") else str(kind)
    return int(HOUSING_BEDS.get(name, 0))


def is_housing_kind(kind: BuildingKind | str) -> bool:
    return housing_beds_of(kind) > 0


def total_housing_beds(buildings: dict[int, Building]) -> int:
    return sum(housing_beds_of(b.kind) for b in buildings.values())


def max_housing_level(buildings: dict[int, Building]) -> int:
    return max((housing_level_of(b.kind) for b in buildings.values()), default=0)


def free_housing_beds(buildings: dict[int, Building], villagers: list[Villager]) -> int:
    beds = total_housing_beds(buildings)
    housed = sum(1 for v in villagers if getattr(v, "housed", False))
    return max(0, beds - housed)


def housed_count(villagers: list[Villager]) -> int:
    return sum(1 for v in villagers if getattr(v, "housed", False))


def pick_traits(rng: random.Random) -> tuple[list[str], list[str]]:
    virtues = rng.sample(list(VIRTUE_POOL), k=rng.randint(1, 2))
    vices = rng.sample(list(VICE_POOL), k=rng.randint(1, 2))
    return virtues, vices


@dataclass
class HireCandidate:
    """Unhired villager living in a map community."""

    id: int
    name: str
    community_id: int
    x: int
    y: int
    skills: dict[SkillType, SkillState] = field(default_factory=blank_skills)
    housing_need: int = 1
    required_foods: list[str] = field(default_factory=lambda: ["meat"])
    favourite_foods: list[str] = field(default_factory=list)
    favourite_is_junk: bool = False
    virtues: list[str] = field(default_factory=list)
    vices: list[str] = field(default_factory=list)
    energy: float = 1.0
    satiation: float = 0.75
    happiness: float = 0.7
    join_fee_paid: bool = False
    seasons_without_reqs: int = 0
    portrait_seed: int = 0

    def __post_init__(self) -> None:
        if not self.portrait_seed:
            self.portrait_seed = self.id * 9973 + hash(self.name) % 10000
        if not self.virtues and not self.vices:
            rng = random.Random(self.portrait_seed)
            self.virtues, self.vices = pick_traits(rng)
            if self.favourite_is_junk and "Glutton" not in self.vices:
                self.vices = (self.vices + ["Glutton"])[:2]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "community_id": self.community_id,
            "x": self.x,
            "y": self.y,
            "skills": skills_to_dict(self.skills),
            "housing_need": self.housing_need,
            "required_foods": list(self.required_foods),
            "favourite_foods": list(self.favourite_foods),
            "favourite_is_junk": self.favourite_is_junk,
            "virtues": list(self.virtues),
            "vices": list(self.vices),
            "energy": round(self.energy, 4),
            "satiation": round(self.satiation, 4),
            "happiness": round(self.happiness, 4),
            "join_fee_paid": self.join_fee_paid,
            "seasons_without_reqs": self.seasons_without_reqs,
            "portrait_seed": self.portrait_seed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> HireCandidate:
        cand = cls(
            id=int(data["id"]),
            name=str(data.get("name", f"Traveller {data['id']}")),
            community_id=int(data.get("community_id", 0)),
            x=int(data["x"]),
            y=int(data["y"]),
            skills=skills_from_dict(data.get("skills")),
            housing_need=int(data.get("housing_need", 1)),
            required_foods=list(data.get("required_foods") or ["meat"]),
            favourite_foods=list(data.get("favourite_foods") or []),
            favourite_is_junk=bool(data.get("favourite_is_junk", False)),
            virtues=list(data.get("virtues") or []),
            vices=list(data.get("vices") or []),
            energy=float(data.get("energy", 1.0)),
            satiation=float(data.get("satiation", 0.75)),
            happiness=float(data.get("happiness", 0.7)),
            join_fee_paid=bool(data.get("join_fee_paid", False)),
            seasons_without_reqs=int(data.get("seasons_without_reqs", 0)),
            portrait_seed=int(data.get("portrait_seed", 0)),
        )
        cand.__post_init__()
        return cand


@dataclass
class Community:
    id: int
    name: str
    x: int
    y: int
    radius: int = 2

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "radius": self.radius,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Community:
        return cls(
            id=int(data["id"]),
            name=str(data.get("name", f"Camp {data['id']}")),
            x=int(data["x"]),
            y=int(data["y"]),
            radius=int(data.get("radius", 2)),
        )


_NAME_A = (
    "Ash", "Bram", "Cora", "Dell", "Elsie", "Finn", "Gwen", "Holt",
    "Ivy", "Joss", "Kade", "Lina", "Moss", "Nell", "Orin", "Pia",
)
_NAME_B = (
    "Reed", "Stone", "Brook", "Hill", "Vale", "Thorn", "Lake", "Fern",
)


def random_name(rng: random.Random) -> str:
    return f"{rng.choice(_NAME_A)} {rng.choice(_NAME_B)}"


def _pick_foods(rng: random.Random) -> tuple[list[str], list[str], bool]:
    staples = list(HIRE_STAPLE_FOODS)
    rng.shuffle(staples)
    required = [staples[0]]
    if rng.random() < 0.35:
        required.append(staples[1])
    favourites: list[str] = []
    junk = False
    if rng.random() < 0.45:
        favourites = [rng.choice(("meat", "grilled_meat", "stew"))]
        junk = rng.random() < 0.55
    elif rng.random() < 0.35:
        favourites = [rng.choice(("bread", "berries", "honey", "fish"))]
    return required, favourites, junk


def generate_communities(
    world,
    rng: random.Random,
    *,
    count: int = 3,
    candidates_per: tuple[int, int] = (2, 4),
    avoid: tuple[int, int] | None = None,
) -> tuple[list[Community], list[HireCandidate]]:
    """Place camps on walkable land away from the player start."""
    from world import FeatureType, is_water_terrain

    cols, rows = world.cols, world.rows
    ax, ay = avoid if avoid is not None else world.start_pos
    communities: list[Community] = []
    candidates: list[HireCandidate] = []
    next_c = 1
    next_v = 1
    attempts = 0
    while len(communities) < count and attempts < 400:
        attempts += 1
        x = rng.randint(3, cols - 4)
        y = rng.randint(3, rows - 4)
        if abs(x - ax) + abs(y - ay) < 18:
            continue
        if any(abs(x - c.x) + abs(y - c.y) < 14 for c in communities):
            continue
        cell = world.get_cell(x, y)
        if cell is None or is_water_terrain(cell.terrain):
            continue
        if cell.feature not in (FeatureType.NONE, FeatureType.TREE, FeatureType.SAPLING):
            continue
        camp = Community(
            id=next_c,
            name=f"{rng.choice(('Oak', 'River', 'Pine', 'Stone', 'Wind'))} Camp",
            x=x,
            y=y,
            radius=2,
        )
        next_c += 1
        communities.append(camp)
        n = rng.randint(candidates_per[0], candidates_per[1])
        for _ in range(n):
            req, fav, junk = _pick_foods(rng)
            skills = blank_skills(rng)
            focus = rng.choice(SKILL_ORDER)
            skills[focus].level = min(
                skills[focus].potential,
                skills[focus].level + rng.randint(1, 3),
            )
            skills[focus].peak = skills[focus].level
            skills[focus].xp = 0.0
            virtues, vices = pick_traits(rng)
            if junk and "Glutton" not in vices:
                vices = (vices + ["Glutton"])[:2]
            name = random_name(rng)
            candidates.append(
                HireCandidate(
                    id=next_v,
                    name=name,
                    community_id=camp.id,
                    x=x + rng.randint(-1, 1),
                    y=y + rng.randint(-1, 1),
                    skills=skills,
                    housing_need=rng.choice((1, 1, 1, 2, 2, 3)),
                    required_foods=req,
                    favourite_foods=fav,
                    favourite_is_junk=junk,
                    virtues=virtues,
                    vices=vices,
                    portrait_seed=next_v * 9973 + hash(name) % 10000,
                )
            )
            next_v += 1
    return communities, candidates


def staple_food_available(amounts: dict[str, int], required: list[str]) -> bool:
    """True if every required staple key has stock > 0."""
    for key in required:
        if int(amounts.get(key, 0)) <= 0:
            return False
    return True


def any_staple_available(amounts: dict[str, int]) -> bool:
    return any(int(amounts.get(k, 0)) > 0 for k in HIRE_STAPLE_FOODS)
