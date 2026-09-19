"""Villager society: skills, housing, hire pools, communities."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

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

# Relative work effort vs one standard swing (field harvest / craft step ≈ 1.0).
# Scales both work duration and XP. Light pickups are quick and low XP.
WORK_EFFORT_MIN: float = 0.15
WORK_EFFORT_MAX: float = 2.5
WORK_EFFORT_BY_ACTION: dict[str, float] = {
    # Loose / single-item pickups
    "meat": 0.20,
    "fish_deposit": 0.20,
    "herb": 0.30,
    "mushroom": 0.30,
    "wood_bush": 0.35,
    "berries": 0.45,
    "rock": 0.50,
    "weeds": 0.40,
    # Field / planting
    "plant": 0.50,
    "sow": 0.55,
    "plough": 0.85,
    "harvest_crop": 1.00,
    # Extraction / hunt
    "honey": 0.70,
    "fish_catch": 0.80,
    "warren": 1.00,
    "hunt": 1.15,
    "chop": 1.35,
    # Workplace
    "craft": 1.00,
    "split": 1.00,
    "build": 1.00,
    "market": 0.60,
    # Logistics load/unload (Transport skill scales the base work interval).
    "haul": 0.50,
    "default": 1.00,
}


def work_effort_mult(action: str | None = None, *, amount: int = 1) -> float:
    """Duration/XP multiplier for a work action (1.0 = standard swing)."""
    key = str(action or "default").lower()
    base = float(WORK_EFFORT_BY_ACTION.get(key, WORK_EFFORT_BY_ACTION["default"]))
    amt = max(1, int(amount))
    if amt > 1:
        # Soft scale with yield size (2 units ≈ ×1.35, soft-capped).
        base *= min(2.0, 0.65 + 0.35 * float(amt))
    return max(WORK_EFFORT_MIN, min(WORK_EFFORT_MAX, base))


def skill_xp_for_action(action: str | None = None, *, amount: int = 1) -> float:
    """XP granted for completing one swing of ``action``."""
    return float(SKILL_XP_PER_ACTION) * work_effort_mult(action, amount=amount)


# Job → skill used for efficiency / recipe gating (assignment is always allowed).
JOB_SKILL_REQUIREMENTS: dict[str, tuple[SkillType, int]] = {
    "FORESTER": (SkillType.EXTRACTION, 1),
    "MASON": (SkillType.EXTRACTION, 1),
    "FORAGER": (SkillType.EXTRACTION, 1),
    "FISHER": (SkillType.HUNTING, 1),
    "HUNTER": (SkillType.HUNTING, 1),
    "FARM": (SkillType.FARMING, 1),
    "FIELD": (SkillType.FARMING, 1),
    "MILL": (SkillType.CRAFTING, 1),
    "KITCHEN": (SkillType.CRAFTING, 1),
    "CRAFT_BENCH": (SkillType.CRAFTING, 1),
    "ALCHEMIST": (SkillType.CRAFTING, 1),
    "TAILOR": (SkillType.CRAFTING, 1),
    "COBBLER": (SkillType.CRAFTING, 1),
    "MARKET": (SkillType.TRANSPORT, 1),
    "APIARY": (SkillType.EXTRACTION, 1),
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
HAPPINESS_LEAVE_THRESHOLD: float = 0.10
HAPPINESS_LEAVE_SEASONS: int = 2
ENERGY_SLEEP_THRESHOLD: float = 0.22
ENERGY_WORK_DRAIN: float = 0.0012
ENERGY_MOVE_DRAIN: float = 0.0004
ENERGY_SLEEP_GAIN: float = 0.004
HAPPINESS_FOOD_VARIETY_BONUS: float = 0.03  # legacy alias; see happiness.HAP_MEAL_VARIETY_PER
# Happiness from each housing level above the villager's requirement.
HAPPINESS_HOUSING_BONUS_PER_LEVEL: float = 0.03
HAPPINESS_MISSING_REQ_PENALTY: float = 0.10
HAPPINESS_FAVOURITE_MISS_PENALTY: float = 0.05  # unused; meal mood is temporary_capped
# Continuous happiness-target shift while on half / double rations.
HAPPINESS_HALF_RATION_PENALTY: float = 0.12
HAPPINESS_DOUBLE_RATION_BONUS: float = 0.10
# Coins charged each season for every unmet hire requirement (housing / staple).
SEASON_MISSING_REQ_PAY_COINS: int = 2
HAPPINESS_EVENT_HISTORY: int = 8
# Timed happiness impacts (UI buffs/debuffs) gradually unwind toward the prior level.
HAPPINESS_IMPACT_DEFAULT_HOURS: float = 6.0
HAPPINESS_IMPACT_MAX_ACTIVE: int = 6
# Discrete event deltas are shown as integer happiness points.
HAPPINESS_POINT_SCALE: float = 0.01
MAX_TRAVELLERS: int = 10

# ---------------------------------------------------------------------------
# Happiness behaviour bands (0–1 bar ↔ percentage labels in UI)
# ---------------------------------------------------------------------------


class HappinessBand(str, Enum):
    ENGAGED = "engaged"  # 75–100%
    CONTENT = "content"  # 50–74%
    DISENGAGED = "disengaged"  # 25–49%
    UNHAPPY = "unhappy"  # 0–24%


HAPPINESS_BAND_LABELS: dict[HappinessBand, str] = {
    HappinessBand.ENGAGED: "Engaged",
    HappinessBand.CONTENT: "Content",
    HappinessBand.DISENGAGED: "Disengaged",
    HappinessBand.UNHAPPY: "Unhappy",
}

# Inclusive lower bounds on the 0–1 bar.
HAPPINESS_BAND_MIN: dict[HappinessBand, float] = {
    HappinessBand.ENGAGED: 0.75,
    HappinessBand.CONTENT: 0.50,
    HappinessBand.DISENGAGED: 0.25,
    HappinessBand.UNHAPPY: 0.0,
}

# Work-speed multiplier from happiness alone (capped ≈ +5% … −20%).
HAPPINESS_WORK_MULT: dict[HappinessBand, float] = {
    HappinessBand.ENGAGED: 1.05,
    HappinessBand.CONTENT: 1.00,
    HappinessBand.DISENGAGED: 0.90,
    HappinessBand.UNHAPPY: 0.80,
}

# Break policy (hours of a 24h day). Tunable without code changes to callers.
HAPPINESS_BREAK_CONFIG: dict[str, Any] = {
    # Baseline rest every villager takes (~1 hour / day of local wandering).
    "base": {
        "duration_hours": 1.0,
        "wander_chance": 0.85,
        "wander_radius": 2,
        "thoughts": (
            "A short stretch will help.",
            "Just a moment to clear my head.",
        ),
    },
    # Extra breaks when happiness < 50%.
    "disengaged": {
        "chance_per_work_hour": 0.12,
        "duration_hours": (0.5, 1.0),
        "wander_chance": 0.55,
        "wander_radius": 3,
        "thoughts": (
            "Why am I always assigned this job?",
            "Does anyone notice the work piling up?",
            "I could use a longer pause.",
        ),
    },
    "unhappy": {
        "chance_per_work_hour": 0.28,
        "duration_hours": (1.0, 2.0),
        "wander_chance": 0.80,
        "wander_radius": 5,
        "thoughts": (
            "Why am I always assigned this job?",
            "I can't keep this pace.",
            "Nothing here feels right today.",
            "I need to get away from this for a while.",
        ),
    },
    # Minimum hours between any two happiness breaks.
    "cooldown_hours": 2.0,
    # Engaged villagers finish returning to work a bit sooner (move factor).
    "engaged_return_walk_mult": 1.15,
}

HIRE_STAPLE_FOODS: tuple[str, ...] = ("t1", "t2", "t3", "t4")


def required_foods_for_tier(tier: int) -> list[str]:
    """Hire food needs: tier N requires cooked dishes of steps 1…N (``t1``…``tN``)."""
    from resource_balance import FOOD_TIER_KEYS

    n = max(1, min(len(FOOD_TIER_KEYS), int(tier or 1)))
    return [FOOD_TIER_KEYS[i] for i in range(n)]


def normalize_required_foods(
    foods: list[str] | None, *, tier: int = 1
) -> list[str]:
    """Keep only generic food-tier keys; rewrite legacy meat/bread/veg lists."""
    from resource_balance import FOOD_TIER_KEYS

    keys = [str(k).strip() for k in (foods or []) if str(k).strip()]
    if keys and all(k in FOOD_TIER_KEYS for k in keys):
        # Deduplicate, preserve order.
        seen: set[str] = set()
        out: list[str] = []
        for k in keys:
            if k not in seen:
                seen.add(k)
                out.append(k)
        return out
    return required_foods_for_tier(tier)

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

    def gain(self, amount: float = SKILL_XP_PER_ACTION) -> int:
        """Gain XP from work; levels up when threshold is reached.

        Returns how many levels were gained this call (0 if none).
        """
        self.idle_days = 0.0
        if self.level >= self.potential:
            return 0
        before = int(self.level)
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
        return max(0, int(self.level) - before)

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


def player_skills() -> dict[SkillType, SkillState]:
    """Player skills: all start at 1 with a hard cap of 10."""
    out: dict[SkillType, SkillState] = {}
    for skill in SKILL_ORDER:
        st = SkillState(level=1, xp=0.0, potential=10, peak=1)
        st.clamp()
        out[skill] = st
    return out


def ensure_skills(
    skills: dict | None, *, player: bool = False
) -> dict[SkillType, SkillState]:
    """Fill missing skill entries; player caps stay at 10."""
    base = player_skills() if player else {
        s: SkillState() for s in SKILL_ORDER
    }
    raw = skills or {}
    out: dict[SkillType, SkillState] = {}
    for skill in SKILL_ORDER:
        existing = raw.get(skill)
        if existing is None:
            existing = raw.get(skill.name) or raw.get(skill.name.lower())
        if isinstance(existing, SkillState):
            st = existing
        elif isinstance(existing, dict):
            st = SkillState.from_dict(existing)
        else:
            st = base[skill]
        if player:
            st.potential = 10
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


def skills_used_by_building(building) -> frozenset[SkillType]:
    """Skills relevant to a workplace: job skill plus any recipe skill gates."""
    skills: set[SkillType] = set()
    kind_name = getattr(getattr(building, "kind", None), "name", None) or ""
    primary, _ = skill_for_building(str(kind_name))
    skills.add(primary)
    for getter in ("known_recipes", "split_recipes", "plant_recipes"):
        fn = getattr(building, getter, None)
        if not callable(fn):
            continue
        try:
            recipes = fn() or ()
        except Exception:
            continue
        for recipe in recipes:
            for sk, _need in getattr(recipe, "skill_reqs", ()) or ():
                skills.add(sk)
    return frozenset(skills)


def villager_meets_skill(villager: Villager, kind_name: str) -> bool:
    """Deprecated for assignment — always True. Kept for callers/tests."""
    return True


def villager_skill_level(villager: Villager, skill: SkillType) -> int:
    state = villager.skills.get(skill)
    if state is None:
        return 1
    return max(1, int(state.level))


def villager_can_use_recipe(
    villager: Villager, recipe, kind_name: str | None = None
) -> bool:
    """True if the worker meets every skill requirement on the recipe."""
    del kind_name  # workplace skill no longer gates recipes alone
    reqs = getattr(recipe, "skill_reqs", None)
    if not reqs:
        # Legacy recipes with only min_skill + workplace kind.
        need = int(getattr(recipe, "min_skill", 1) or 1)
        if need <= 1:
            return True
        if kind_name:
            skill, _ = skill_for_building(kind_name)
            return villager_skill_level(villager, skill) >= need
        return villager_skill_level(villager, SkillType.CRAFTING) >= need
    for skill, need in reqs:
        if villager_skill_level(villager, skill) < int(need):
            return False
    return True


def recipe_skill_gate(
    recipe, *, worker: Villager | None = None, worker_skill_level: int | None = None
) -> bool:
    """Return True if ``recipe`` is allowed for the given worker / level check."""
    if worker is not None:
        return villager_can_use_recipe(worker, recipe)
    if worker_skill_level is None:
        return True
    # Single-level legacy: only allow when every required skill ≤ level.
    reqs = getattr(recipe, "skill_reqs", ()) or ()
    if not reqs:
        return int(getattr(recipe, "min_skill", 1) or 1) <= int(worker_skill_level)
    return all(int(need) <= int(worker_skill_level) for _, need in reqs)


def skill_efficiency(villager: Villager, skill: SkillType) -> float:
    state = villager.skills.get(skill)
    if state is None:
        return 1.0
    return state.efficiency()


def gain_skill(
    actor: Any, skill: SkillType, amount: float = SKILL_XP_PER_ACTION
) -> int | None:
    """Apply XP to ``actor.skills``. Returns the new level if leveled up."""
    skills = getattr(actor, "skills", None)
    if not isinstance(skills, dict):
        return None
    state = skills.get(skill)
    if state is None:
        state = SkillState()
        skills[skill] = state
    if type(actor).__name__ == "Player":
        state.potential = 10
    gained = int(state.gain(amount) or 0)
    if gained <= 0:
        return None
    return int(state.level)


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
    required_foods: list[str] = field(default_factory=lambda: required_foods_for_tier(1))
    favourite_foods: list[str] = field(default_factory=list)
    favourite_is_junk: bool = False
    required_workplace: str = ""
    signing_fee: int = 0
    virtues: list[str] = field(default_factory=list)
    vices: list[str] = field(default_factory=list)
    energy: float = 1.0
    satiation: float = 0.75
    happiness: float = 0.7
    join_fee_paid: bool = False
    seasons_without_reqs: int = 0
    portrait_seed: int = 0
    template_id: str = ""
    tier: int = 1

    def __post_init__(self) -> None:
        if not self.portrait_seed:
            self.portrait_seed = self.id * 9973 + hash(self.name) % 10000
        if not self.virtues and not self.vices:
            rng = random.Random(self.portrait_seed)
            self.virtues, self.vices = pick_traits(rng)
            if self.favourite_is_junk and "Glutton" not in self.vices:
                self.vices = (self.vices + ["Glutton"])[:2]
        self.tier = max(1, min(3, int(self.tier or 1)))
        self.required_foods = normalize_required_foods(
            self.required_foods, tier=self.tier
        )

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
            "required_workplace": self.required_workplace,
            "signing_fee": self.signing_fee,
            "virtues": list(self.virtues),
            "vices": list(self.vices),
            "energy": round(self.energy, 4),
            "satiation": round(self.satiation, 4),
            "happiness": round(self.happiness, 4),
            "join_fee_paid": self.join_fee_paid,
            "seasons_without_reqs": self.seasons_without_reqs,
            "portrait_seed": self.portrait_seed,
            "template_id": self.template_id,
            "tier": self.tier,
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
            required_foods=list(data.get("required_foods") or []),
            favourite_foods=list(data.get("favourite_foods") or []),
            favourite_is_junk=bool(data.get("favourite_is_junk", False)),
            required_workplace=str(data.get("required_workplace", "") or ""),
            signing_fee=max(0, int(data.get("signing_fee", 0) or 0)),
            virtues=list(data.get("virtues") or []),
            vices=list(data.get("vices") or []),
            energy=float(data.get("energy", 1.0)),
            satiation=float(data.get("satiation", 0.75)),
            happiness=float(data.get("happiness", 0.7)),
            join_fee_paid=bool(data.get("join_fee_paid", False)),
            seasons_without_reqs=int(data.get("seasons_without_reqs", 0)),
            portrait_seed=int(data.get("portrait_seed", 0)),
            template_id=str(data.get("template_id", "") or ""),
            tier=int(data.get("tier", 1) or 1),
        )
        cand.__post_init__()
        return cand


@dataclass
class TravellerTemplate:
    """Row from society_data/travellers.csv."""

    template_id: str
    name: str
    tier: int
    housing_need: int
    required_foods: list[str]
    favourite_foods: list[str]
    favourite_is_junk: bool
    required_workplace: str
    signing_fee: int
    virtues: list[str]
    vices: list[str]
    skill_levels: dict[SkillType, int]
    skill_caps: dict[SkillType, int]


def _travellers_csv_path() -> str:
    from pathlib import Path

    return str(Path(__file__).resolve().parent / "society_data" / "travellers.csv")


def _split_csv_list(raw: str) -> list[str]:
    return [p.strip() for p in str(raw or "").split(";") if p.strip()]


def load_traveller_templates(path: str | None = None) -> list[TravellerTemplate]:
    import csv
    from pathlib import Path

    csv_path = Path(path or _travellers_csv_path())
    if not csv_path.is_file():
        return []
    out: list[TravellerTemplate] = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            levels: dict[SkillType, int] = {}
            caps: dict[SkillType, int] = {}
            for skill in SKILL_ORDER:
                key = skill.name.lower()
                levels[skill] = max(1, min(10, int(row.get(key, 1) or 1)))
                caps[skill] = max(
                    levels[skill],
                    min(10, int(row.get(f"{key}_cap", levels[skill]) or levels[skill])),
                )
            out.append(
                TravellerTemplate(
                    template_id=str(row.get("template_id") or row.get("name") or ""),
                    name=str(row.get("name") or "Traveller"),
                    tier=max(1, min(3, int(row.get("tier", 1) or 1))),
                    housing_need=max(1, min(3, int(row.get("housing_need", 1) or 1))),
                    required_foods=normalize_required_foods(
                        _split_csv_list(row.get("required_foods", "")),
                        tier=max(1, min(3, int(row.get("tier", 1) or 1))),
                    ),
                    favourite_foods=_split_csv_list(row.get("favourite_foods", "")),
                    favourite_is_junk=str(row.get("favourite_is_junk", "0")).strip()
                    in ("1", "true", "True", "yes"),
                    required_workplace=str(row.get("required_workplace", "") or "").strip().lower(),
                    signing_fee=max(0, int(row.get("signing_fee", 0) or 0)),
                    virtues=_split_csv_list(row.get("virtues", "")),
                    vices=_split_csv_list(row.get("vices", "")),
                    skill_levels=levels,
                    skill_caps=caps,
                )
            )
    return out


def skills_from_template(template: TravellerTemplate) -> dict[SkillType, SkillState]:
    out: dict[SkillType, SkillState] = {}
    for skill in SKILL_ORDER:
        level = int(template.skill_levels.get(skill, 1))
        potential = int(template.skill_caps.get(skill, level))
        st = SkillState(level=level, xp=0.0, potential=potential, peak=level)
        st.clamp()
        out[skill] = st
    return out


def hire_candidate_from_template(
    template: TravellerTemplate,
    *,
    cand_id: int,
    community: Community,
    rng: random.Random,
    name: str | None = None,
) -> HireCandidate:
    display_name = name or template.name
    return HireCandidate(
        id=cand_id,
        name=display_name,
        community_id=community.id,
        x=community.x + rng.randint(-1, 1),
        y=community.y + rng.randint(-1, 1),
        skills=skills_from_template(template),
        housing_need=template.housing_need,
        required_foods=normalize_required_foods(
            template.required_foods, tier=template.tier
        ),
        favourite_foods=list(template.favourite_foods),
        favourite_is_junk=template.favourite_is_junk,
        required_workplace=template.required_workplace,
        signing_fee=template.signing_fee,
        virtues=list(template.virtues),
        vices=list(template.vices),
        portrait_seed=cand_id * 9973 + hash(display_name) % 10000,
        template_id=template.template_id,
        tier=template.tier,
    )


_TRAVELLER_TEMPLATES: list[TravellerTemplate] | None = None


def traveller_templates() -> list[TravellerTemplate]:
    global _TRAVELLER_TEMPLATES
    if _TRAVELLER_TEMPLATES is None:
        _TRAVELLER_TEMPLATES = load_traveller_templates()
    return list(_TRAVELLER_TEMPLATES)


def pick_traveller_templates(
    rng: random.Random,
    *,
    count: int,
    exclude_ids: set[str] | None = None,
) -> list[TravellerTemplate]:
    """Pick templates with a mix of tiers (round-robin 1→2→3)."""
    exclude = exclude_ids or set()
    by_tier: dict[int, list[TravellerTemplate]] = {1: [], 2: [], 3: []}
    for tmpl in traveller_templates():
        if tmpl.template_id and tmpl.template_id in exclude:
            continue
        by_tier.setdefault(tmpl.tier, []).append(tmpl)
    for tier in by_tier:
        rng.shuffle(by_tier[tier])
    picked: list[TravellerTemplate] = []
    while len(picked) < count:
        progressed = False
        for tier in (1, 2, 3):
            pool = by_tier.get(tier) or []
            if not pool:
                continue
            picked.append(pool.pop())
            progressed = True
            if len(picked) >= count:
                break
        if not progressed:
            break
    # If still short, recycle any templates (new name later).
    if len(picked) < count:
        all_tmpls = list(traveller_templates())
        rng.shuffle(all_tmpls)
        while len(picked) < count and all_tmpls:
            picked.append(rng.choice(all_tmpls))
    return picked[:count]


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
    from resource_balance import FOOD_TIER_KEYS

    tier = rng.randint(1, 3)
    required = list(FOOD_TIER_KEYS[:tier])
    favourites: list[str] = []
    junk = False
    if rng.random() < 0.45:
        favourites = [
            rng.choice(
                ("meat_stew", "grilled_meat", "fish_soup", "pea_soup", "spiced_stew")
            )
        ]
        junk = rng.random() < 0.55
    elif rng.random() < 0.35:
        favourites = [
            rng.choice(
                ("blackberries", "honey", "roasted_turnips", "grilled_fish", "wheat_bread")
            )
        ]
    return required, favourites, junk


def generate_communities(
    world,
    rng: random.Random,
    *,
    count: int = 3,
    candidates_per: tuple[int, int] = (2, 4),
    avoid: tuple[int, int] | None = None,
    max_travellers: int = MAX_TRAVELLERS,
) -> tuple[list[Community], list[HireCandidate]]:
    """Place camps on walkable land and fill travellers from travellers.csv."""
    del candidates_per  # pool size comes from max_travellers + CSV templates
    from world import FeatureType, is_water_terrain

    cols, rows = world.cols, world.rows
    ax, ay = avoid if avoid is not None else world.start_pos
    communities: list[Community] = []
    next_c = 1
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

    candidates, _next_id = spawn_travellers_from_templates(
        communities,
        rng,
        count=max_travellers,
        next_id=1,
    )
    return communities, candidates


def spawn_travellers_from_templates(
    communities: list[Community],
    rng: random.Random,
    *,
    count: int,
    next_id: int,
    exclude_template_ids: set[str] | None = None,
) -> tuple[list[HireCandidate], int]:
    """Create hire candidates from CSV templates, spread across camps."""
    if count <= 0 or not communities:
        return [], next_id
    templates = pick_traveller_templates(
        rng, count=count, exclude_ids=exclude_template_ids
    )
    used_names = set()
    candidates: list[HireCandidate] = []
    for i, tmpl in enumerate(templates):
        camp = communities[i % len(communities)]
        name = tmpl.name
        if name in used_names:
            name = random_name(rng)
        used_names.add(name)
        candidates.append(
            hire_candidate_from_template(
                tmpl,
                cand_id=next_id,
                community=camp,
                rng=rng,
                name=name,
            )
        )
        next_id += 1
    return candidates, next_id


def staple_food_available(amounts: dict[str, int], required: list[str]) -> bool:
    """True if every required food category has stock > 0."""
    from resource_balance import requirement_met_in_stock

    for key in required:
        if not requirement_met_in_stock(amounts, str(key)):
            return False
    return True


def any_staple_available(amounts: dict[str, int]) -> bool:
    from resource_balance import FOOD_TIER_KEYS, requirement_met_in_stock

    return any(requirement_met_in_stock(amounts, key) for key in FOOD_TIER_KEYS)


def hire_unmet_requirements(
    *,
    housing_need: int,
    required_foods: list[str],
    foods: dict[str, int],
    free_beds: int,
    max_housing_level: int,
) -> list[str]:
    """Requirement keys unmet for a hire candidate (bed, housing, each staple)."""
    from resource_balance import requirement_met_in_stock

    missing: list[str] = []
    if int(free_beds) <= 0:
        missing.append("bed")
    if int(max_housing_level) < int(housing_need):
        missing.append("housing")
    for food in required_foods:
        if not requirement_met_in_stock(foods, str(food)):
            missing.append(str(food))
    return missing


def villager_unmet_requirements(
    villager: Villager,
    buildings: dict[int, Building],
    foods: dict[str, int],
) -> list[str]:
    """Requirement keys unmet for a hired villager (housing + each staple)."""
    from resource_balance import requirement_met_in_stock

    missing: list[str] = []
    if not villager.housed:
        missing.append("housing")
    else:
        house = buildings.get(villager.housing_id or -1)
        if house is None or housing_level_of(house.kind) < int(villager.housing_need):
            missing.append("housing")
    for food in list(getattr(villager, "required_foods", []) or []):
        if not requirement_met_in_stock(foods, str(food)):
            missing.append(str(food))
    return missing


def season_pay_coins(unmet: list[str], *, coins_per: int | None = None) -> int:
    rate = SEASON_MISSING_REQ_PAY_COINS if coins_per is None else max(0, int(coins_per))
    return len(unmet) * rate


def requirement_label(key: str) -> str:
    if key == "bed":
        return "Free bed"
    if key == "housing":
        return "Housing"
    from resource_balance import FOOD_TIER_KEYS, REQUIREMENT_LABELS, food_tier_requirement_hint

    if key in FOOD_TIER_KEYS:
        return food_tier_requirement_hint(key)
    if key in REQUIREMENT_LABELS:
        return REQUIREMENT_LABELS[key]
    from resources import resource_label

    try:
        return resource_label(key)
    except Exception:
        return key.replace("_", " ").title()


def requirement_icon(key: str) -> str:
    from resource_balance import REQUIREMENT_ICONS
    from resources import resource_icon

    mapped = REQUIREMENT_ICONS.get(key)
    if mapped:
        # Prefer resolving through the resource catalogue so recipe keys like
        # grilled_mushrooms map to a real icon stem (mushroom).
        try:
            return resource_icon(mapped)
        except Exception:
            return mapped
    try:
        return resource_icon(key)
    except Exception:
        return key


def villager_requirement_rows(
    villager: Villager,
    buildings: dict[int, Building],
    foods: dict[str, int],
    *,
    housing_icon: str = "tent",
) -> list[dict]:
    """Requirement icons for inspect UI: housing + each required staple."""
    rows: list[dict] = []
    need = int(getattr(villager, "housing_need", 1) or 1)
    housed = bool(getattr(villager, "housed", False))
    house = buildings.get(villager.housing_id or -1) if housed else None
    level = housing_level_of(house.kind) if house is not None else 0
    housing_met = housed and level >= need
    rows.append(
        {
            "key": "housing",
            "icon": housing_icon if housing_met else "tent",
            "met": housing_met,
            "label": (
                f"Housing level {level} (need ≥{need})"
                if housed
                else f"Needs housing level ≥{need}"
            ),
            "coins": 0 if housing_met else SEASON_MISSING_REQ_PAY_COINS,
        }
    )
    for food in list(getattr(villager, "required_foods", []) or []):
        key = str(food)
        from resource_balance import requirement_met_in_stock

        met = requirement_met_in_stock(foods, key)
        base = requirement_label(key)
        rows.append(
            {
                "key": key,
                "icon": requirement_icon(key),
                "met": met,
                "label": f"{base} — in stock" if met else f"{base} — missing",
                "coins": 0 if met else SEASON_MISSING_REQ_PAY_COINS,
            }
        )
    return rows


def candidate_requirement_rows(
    *,
    housing_need: int,
    required_foods: list[str],
    foods: dict[str, int],
    free_beds: int,
    max_housing_level: int,
    housing_icon: str = "tent",
) -> list[dict]:
    """Requirement icons for a hire candidate (bed/level + staples)."""
    from resource_balance import requirement_met_in_stock

    need = int(housing_need)
    bed_met = int(free_beds) > 0
    housing_met = int(max_housing_level) >= need
    rows: list[dict] = [
        {
            "key": "bed",
            "icon": "tent",
            "met": bed_met,
            "label": "Free bed" if bed_met else "Free bed missing",
            "coins": 0,
        },
        {
            "key": "housing",
            "icon": housing_icon if housing_met else "tent",
            "met": housing_met,
            "label": (
                f"Housing ready (need ≥{need})"
                if housing_met
                else f"Needs housing level ≥{need}"
            ),
            "coins": 0 if housing_met else SEASON_MISSING_REQ_PAY_COINS,
        }
    ]
    for food in required_foods:
        key = str(food)
        met = requirement_met_in_stock(foods, key)
        base = requirement_label(key)
        rows.append(
            {
                "key": key,
                "icon": requirement_icon(key),
                "met": met,
                "label": f"{base} — in stock" if met else f"{base} — missing",
                "coins": 0 if met else SEASON_MISSING_REQ_PAY_COINS,
            }
        )
    return rows


def push_happiness_event(
    villager: Villager,
    *,
    icon: str,
    label: str,
    delta: int | float,
    day: int = 0,
) -> None:
    """Append a recent happiness event (keeps last N). Delta is happiness points."""
    events = list(
        getattr(villager, "happiness_events", None)
        or getattr(villager, "happiness_impacts", None)
        or []
    )
    events.append(
        {
            "icon": str(icon),
            "label": str(label),
            "delta": int(round(float(delta))),
            "day": int(day),
        }
    )
    setattr(villager, "happiness_events", events[-HAPPINESS_EVENT_HISTORY:])
    # Keep legacy attribute in sync for any old readers.
    setattr(villager, "happiness_impacts", list(getattr(villager, "happiness_events")))


# Back-compat alias
push_happiness_impact = push_happiness_event


def apply_happiness_points(villager: Villager, points: int | float) -> float:
    """Immediate one-shot change to underlying happiness (legacy entry point)."""
    from happiness import apply_immediate_happiness

    return apply_immediate_happiness(
        villager, points, label="Happiness", source="immediate"
    )


def _happiness_modifiers(villager: Villager) -> list[dict]:
    """Legacy view of temporary moods (for older UI/save helpers)."""
    from happiness import _temporary_moods, temporary_mood_value

    out: list[dict] = []
    for mood in _temporary_moods(villager):
        amount = temporary_mood_value(mood)
        out.append(
            {
                "icon": str(mood.get("icon") or "stew"),
                "label": str(mood.get("label") or "Mood"),
                "peak": float(mood.get("peak", 0) or 0),
                "remaining": amount,
                "ticks_left": int(mood.get("ticks_left", 0) or 0),
                "ticks_total": int(mood.get("ticks_total", 1) or 1),
                "until_meal": str(mood.get("channel") or "") == "meal",
                "points": int(round(float(mood.get("peak", 0) or 0) / HAPPINESS_POINT_SCALE)),
                "channel": str(mood.get("channel") or ""),
            }
        )
    setattr(villager, "happiness_modifiers", out)
    return out


def apply_timed_happiness_impact(
    villager: Villager,
    points: int | float,
    *,
    icon: str,
    label: str,
    day: int = 0,
    until_meal: bool = False,
    duration_hours: float | None = None,
    ticks_per_day: int = 240,
    channel: str | None = None,
) -> float:
    """Temporary capped mood (non-stacking). Preferred for lingering event effects."""
    from happiness import (
        HAP_IMMEDIATE_POINT_SCALE,
        apply_timed_happiness_impact_legacy_bridge,
        sync_displayed_happiness,
    )

    points_f = float(points)
    if abs(points_f) < 1e-9:
        return 0.0
    apply_timed_happiness_impact_legacy_bridge(
        villager,
        points_f,
        icon=icon,
        label=label,
        day=day,
        duration_hours=duration_hours,
        until_meal=until_meal,
        ticks_per_day=ticks_per_day,
        channel=channel,
    )
    sync_displayed_happiness(villager)
    return float(points_f) * HAP_IMMEDIATE_POINT_SCALE


def tick_happiness_modifiers(villager: Villager) -> None:
    """Advance temporary mood decay one tick (underlying drift is separate)."""
    from happiness import sync_displayed_happiness, tick_temporary_moods

    tick_temporary_moods(villager, ticks=1)
    sync_displayed_happiness(villager)


def clear_meal_happiness_modifiers(villager: Villager) -> None:
    """No-op: normal meals must not abruptly clear an existing meal mood."""
    return


def active_happiness_status_mods(villager: Villager) -> list:
    """Buff/debuff tiles for temporary moods, ongoing target shifts, and mood band."""
    from status_effects_ui import StatusMod

    mods: list = []
    # Temporary capped moods (meal etc.).
    for imp in _happiness_modifiers(villager):
        remaining = float(imp.get("remaining", 0.0) or 0.0)
        if abs(remaining) < 0.005:
            continue
        pct = int(round(remaining * 100))
        if pct == 0:
            continue
        label = str(imp.get("label") or "Happiness")
        short = label
        for prefix in ("Ate favourite food: ", "Ate unwanted food: "):
            if short.startswith(prefix):
                short = ("Favourite: " if "favourite" in prefix else "Unwanted: ") + short[
                    len(prefix) :
                ]
                break
        mods.append(
            StatusMod(
                cause_key=f"hap_{short}",
                cause_icon=str(imp.get("icon") or "stew"),
                cause_group="events",
                effect="happiness",
                mult=float(pct),
                cause_label=short[:32],
                tip_override=f"Happiness {pct:+d}% (temporary)",
                display_kind="buff" if pct > 0 else "debuff",
            )
        )

    # Ongoing target components (stable while condition holds).
    try:
        from happiness import happiness_breakdown_for

        bd = happiness_breakdown_for(villager)
        if bd is not None:
            for comp in bd.target_components:
                if comp.key == "base":
                    continue
                if abs(comp.amount) < 0.005:
                    continue
                pct = int(round(comp.amount * 100))
                if pct == 0:
                    continue
                icon = "stew"
                if "housing" in comp.key:
                    icon = "tent"
                elif "ration" in comp.key:
                    icon = "bread"
                elif "job" in comp.key or "office" in comp.key or "assigned" in comp.key:
                    icon = "construction_site"
                elif "thermal" in comp.key:
                    icon = "cold" if "cold" in comp.key else "hot"
                elif "trait" in comp.key:
                    icon = "stew"
                elif "extractive" in comp.key or "habitat" in comp.key or "covenant" in comp.key:
                    icon = "tree_round"
                mods.append(
                    StatusMod(
                        cause_key=f"hap_target_{comp.key}",
                        cause_icon=icon,
                        cause_group="events",
                        effect="happiness",
                        mult=float(pct),
                        cause_label=str(comp.label)[:32],
                        tip_override=(
                            f"Happiness target {pct:+d}% ← {comp.source}"
                        ),
                        display_kind="buff" if pct > 0 else "debuff",
                    )
                )
    except Exception:
        pass

    band = happiness_band(float(getattr(villager, "happiness", 0.7) or 0.7))
    work = happiness_work_mult(float(getattr(villager, "happiness", 0.7) or 0.7))
    if band != HappinessBand.CONTENT:
        label = HAPPINESS_BAND_LABELS[band]
        tip = f"Work efficiency ×{work:.2f}"
        if band == HappinessBand.DISENGAGED:
            tip += " — extra breaks"
        elif band == HappinessBand.UNHAPPY:
            tip += " — longer breaks / wandering"
        elif band == HappinessBand.ENGAGED:
            tip += " — quicker return to work"
        mods.append(
            StatusMod(
                cause_key=f"mood_{band.value}",
                cause_icon="stew",
                cause_group="events",
                effect="work",
                mult=float(work),
                cause_label=label,
                tip_override=tip,
                display_kind="buff" if work > 1.01 else "debuff",
            )
        )
    return mods


def happiness_band(happiness: float) -> HappinessBand:
    """Map 0–1 happiness onto the four behaviour bands."""
    h = max(0.0, min(1.0, float(happiness)))
    if h >= HAPPINESS_BAND_MIN[HappinessBand.ENGAGED]:
        return HappinessBand.ENGAGED
    if h >= HAPPINESS_BAND_MIN[HappinessBand.CONTENT]:
        return HappinessBand.CONTENT
    if h >= HAPPINESS_BAND_MIN[HappinessBand.DISENGAGED]:
        return HappinessBand.DISENGAGED
    return HappinessBand.UNHAPPY


def happiness_band_label(happiness: float) -> str:
    return HAPPINESS_BAND_LABELS[happiness_band(happiness)]


def happiness_work_mult(happiness: float) -> float:
    """Work-speed multiplier from happiness, capped ≈ +5% … −20%."""
    return float(HAPPINESS_WORK_MULT[happiness_band(happiness)])


def happiness_break_hours_to_ticks(hours: float, ticks_per_day: int) -> int:
    return max(1, int(round(float(hours) * max(1, int(ticks_per_day)) / 24.0)))


def happiness_break_duration_ticks(
    kind: str, ticks_per_day: int, *, rng: random.Random | None = None
) -> int:
    """Resolve configured break duration for ``base`` / ``disengaged`` / ``unhappy``."""
    cfg = HAPPINESS_BREAK_CONFIG.get(kind) or HAPPINESS_BREAK_CONFIG["base"]
    raw = cfg.get("duration_hours", 1.0)
    rng = rng or random
    if isinstance(raw, (tuple, list)) and len(raw) >= 2:
        lo, hi = float(raw[0]), float(raw[1])
        hours = float(rng.uniform(lo, hi))
    else:
        hours = float(raw)
    return happiness_break_hours_to_ticks(hours, ticks_per_day)


def happiness_break_cooldown_ticks(ticks_per_day: int) -> int:
    hours = float(HAPPINESS_BREAK_CONFIG.get("cooldown_hours", 2.0))
    return happiness_break_hours_to_ticks(hours, ticks_per_day)


def happiness_break_chance_this_tick(
    kind: str, ticks_per_day: int
) -> float:
    """Per-tick probability while working for an extra (non-base) break."""
    cfg = HAPPINESS_BREAK_CONFIG.get(kind) or {}
    per_hour = float(cfg.get("chance_per_work_hour", 0.0))
    ticks_per_hour = max(1, int(ticks_per_day) / 24.0)
    # 1 - (1-p_hour)^(1/ticks_per_hour) ≈ p_hour / ticks_per_hour for small p.
    return max(0.0, min(1.0, per_hour / ticks_per_hour))


def pick_happiness_break_thought(kind: str, *, rng: random.Random | None = None) -> str:
    cfg = HAPPINESS_BREAK_CONFIG.get(kind) or HAPPINESS_BREAK_CONFIG["base"]
    thoughts = tuple(cfg.get("thoughts") or ("…",))
    rng = rng or random
    return str(rng.choice(thoughts))


def happiness_break_wander_params(kind: str) -> tuple[float, int]:
    """Return ``(wander_chance, wander_radius)`` for a break kind."""
    cfg = HAPPINESS_BREAK_CONFIG.get(kind) or HAPPINESS_BREAK_CONFIG["base"]
    return float(cfg.get("wander_chance", 0.5)), int(cfg.get("wander_radius", 2))


def engaged_return_walk_mult() -> float:
    return float(HAPPINESS_BREAK_CONFIG.get("engaged_return_walk_mult", 1.15))


def is_happiness_break_state(state: object) -> bool:
    name = getattr(state, "name", str(state))
    return name in {"DISENGAGED_BREAK", "WANDERING", "RETURNING_TO_WORK"}
