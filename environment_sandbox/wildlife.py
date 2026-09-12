"""Wildlife: deer, boars, and bee/rabbit colonies.

Forest habitats = connected forest-floor tiles (litter under mature trees).
Habitats are rebuilt on the same season start/mid sample window as biodiversity
(≤8 updates per year).

Deer / Boar
-----------
Individual animals with mating pairs, seasonal roaming, and migration.
Deer breed on forest-floor edge tiles bordering grass/meadow; boars use the
whole forest-floor patch (cold/warm roam still expands by the usual adjacency).

Bees / Rabbits
--------------
Colonies (not individuals). Each has a nest tile and level 1–4 controlling how
many visible members wander nearby. Colonies grow when forage food is available;
a level-3 colony may found a new level-1 colony on an empty nest site. Bees and
rabbits need forage tiles ≥ (balance N) × colony level (else level is clamped or
the colony is removed). If a kind has zero colonies at spring (new year), one
small colony is seeded.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum, auto

from seasons import (
    Season,
    YEAR_DAYS,
    animals_multiply,
    animals_slow,
    fish_breeding_allowed,
    freeze_amount,
    season_for_day,
    water_frozen,
)
from entities import arm_cell_step_visual, note_cell_step, snap_entity_visual
from resource_balance import (
    ANIMAL_MIGRATION_CHANCE,
    ANIMAL_TREES_PER_CAP,
    BOAR_CELLS_PER_CAP,
    BOAR_CROP_EAT_CHANCE,
    COLONY_HARVEST_COOLDOWN,
    COLONY_LEVEL_MAX,
    COLONY_MEMBER_RADIUS,
    COLONY_MEMBERS_BY_LEVEL,
    COLONY_RABBIT_CROP_EAT_CHANCE,
    COLONY_SEED_GROUNDS,
    COLONY_SPLIT_LEVEL,
    DEER_CROP_EAT_CHANCE,
    FISH_WATER_PER_CAP,
    FISH_SPAWN_WEIGHTS,
    HONEY_PER_BEE_LEVEL,
    HUNT_APPROACH_RADIUS,
    HUNT_SCARE_RADIUS,
    HUNT_SCARE_STEPS,
    MIN_BREEDING_CAPACITY,
    PATH_FIND_MAX_NODES,
    SMALL_GAME_FORAGE_RADIUS,
    WILDLIFE_RESEED_PAIR,
    WILDLIFE_SEED_COUNT,
    WILDLIFE_SEED_GROUNDS,
)
from settings import (
    ANIMAL_GROWTH_INTERVAL,
    ANIMAL_MOVE_SECONDS_AT_X1,
    ANIMAL_FLEE_SECONDS_AT_X1,
    FISH_GROWTH_INTERVAL,
    FISH_MOVE_SECONDS_AT_X1,
    RABBIT_MOVE_PAUSE_SECONDS_AT_X1,
    RANDOM_SEED,
    seconds_to_ticks,
)
from world import FeatureType, TerrainType, World, wildlife_ecology_multiplier, effective_disturbance_at


def _bal_seconds_ticks(key: str, default_seconds: float) -> int:
    """Convert a balance seconds-at-×1 knob to sim ticks."""
    from balance_config import active_balance

    try:
        seconds = float(active_balance().get_float(key))
    except Exception:
        seconds = float(default_seconds)
    return max(4, seconds_to_ticks(max(0.05, seconds)))


def animal_roam_interval() -> int:
    return _bal_seconds_ticks("ANIMAL_MOVE_SECONDS_AT_X1", ANIMAL_MOVE_SECONDS_AT_X1)


def animal_flee_interval() -> int:
    return _bal_seconds_ticks("ANIMAL_FLEE_SECONDS_AT_X1", ANIMAL_FLEE_SECONDS_AT_X1)


def fish_move_interval() -> int:
    return _bal_seconds_ticks("FISH_MOVE_SECONDS_AT_X1", FISH_MOVE_SECONDS_AT_X1)


def rabbit_pause_interval() -> int:
    return _bal_seconds_ticks(
        "RABBIT_MOVE_PAUSE_SECONDS_AT_X1", RABBIT_MOVE_PAUSE_SECONDS_AT_X1
    )


def wolf_speed_mult(key: str, default: float) -> float:
    from balance_config import active_balance

    try:
        return max(1.0, float(active_balance().get_float(key)))
    except Exception:
        return max(1.0, float(default))


def _bal_weight(key: str, default: float) -> float:
    from balance_config import active_balance

    try:
        return max(0.0, float(active_balance().get_float(key)))
    except Exception:
        return max(0.0, float(default))


def _bal_float(key: str, default: float) -> float:
    from balance_config import active_balance

    try:
        return float(active_balance().get_float(key))
    except Exception:
        return float(default)


def _bal_int(key: str, default: int, minimum: int = 0) -> int:
    from balance_config import active_balance

    try:
        return max(minimum, active_balance().get_int(key))
    except Exception:
        return max(minimum, int(default))


class AnimalKind(Enum):
    DEER = auto()
    BOAR = auto()
    BEE = auto()
    RABBIT = auto()
    FROG = auto()
    VOLE = auto()
    WOLF = auto()
    FOX = auto()
    OWL = auto()
    HAWK = auto()


class FishKind(Enum):
    CARP = auto()
    PERCH = auto()
    PIKE = auto()
    ROACH = auto()


def fish_yield_for(kind: FishKind) -> int:
    """Cargo fish units dropped/collected for this species."""
    from wildlife_species import fish_yield_amount

    return fish_yield_amount(kind.name)


def fish_icon_for(kind: FishKind) -> str:
    from wildlife_species import fish_icon_name

    return fish_icon_name(kind.name)


FOREST_KINDS: tuple[AnimalKind, ...] = (AnimalKind.DEER, AnimalKind.BOAR)
COLONY_KINDS: tuple[AnimalKind, ...] = (
    AnimalKind.BEE,
    AnimalKind.RABBIT,
    AnimalKind.FROG,
    AnimalKind.VOLE,
)
BIRD_KINDS: tuple[AnimalKind, ...] = (AnimalKind.OWL, AnimalKind.HAWK)
PACK_KINDS: tuple[AnimalKind, ...] = (AnimalKind.WOLF, AnimalKind.FOX)


def colony_forage_per_level(kind: AnimalKind) -> int:
    """Balance: forage tiles required per colony level."""
    from balance_config import active_balance

    if kind == AnimalKind.BEE:
        key = "WILDLIFE_BEE_FORAGE_PER_LEVEL"
    elif kind == AnimalKind.RABBIT:
        key = "WILDLIFE_RABBIT_FORAGE_PER_LEVEL"
    elif kind == AnimalKind.FROG:
        key = "WILDLIFE_FROG_FORAGE_PER_LEVEL"
    elif kind == AnimalKind.VOLE:
        key = "WILDLIFE_VOLE_FORAGE_PER_LEVEL"
    else:
        return 1
    try:
        return max(1, active_balance().get_int(key))
    except Exception:
        from settings import (
            WILDLIFE_BEE_FORAGE_PER_LEVEL,
            WILDLIFE_FROG_FORAGE_PER_LEVEL,
            WILDLIFE_RABBIT_FORAGE_PER_LEVEL,
            WILDLIFE_VOLE_FORAGE_PER_LEVEL,
        )

        defaults = {
            "WILDLIFE_BEE_FORAGE_PER_LEVEL": WILDLIFE_BEE_FORAGE_PER_LEVEL,
            "WILDLIFE_RABBIT_FORAGE_PER_LEVEL": WILDLIFE_RABBIT_FORAGE_PER_LEVEL,
            "WILDLIFE_FROG_FORAGE_PER_LEVEL": WILDLIFE_FROG_FORAGE_PER_LEVEL,
            "WILDLIFE_VOLE_FORAGE_PER_LEVEL": WILDLIFE_VOLE_FORAGE_PER_LEVEL,
        }
        return max(1, int(defaults.get(key, 10)))


def colony_max_level_for_forage(kind: AnimalKind, forage_count: int) -> int:
    """Highest colony level supported by ``forage_count`` tiles (0 = none)."""
    if kind not in COLONY_KINDS:
        return COLONY_LEVEL_MAX
    per = colony_forage_per_level(kind)
    if int(forage_count) < per:
        return 0
    return min(COLONY_LEVEL_MAX, int(forage_count) // per)


# Back-compat alias used by older call sites / scripts.
def bee_max_level_for_forage(forage_count: int) -> int:
    return colony_max_level_for_forage(AnimalKind.BEE, forage_count)


class AnimalSex(Enum):
    MALE = auto()
    FEMALE = auto()


@dataclass
class Animal:
    id: int
    x: int
    y: int
    kind: AnimalKind = AnimalKind.DEER
    sex: AnimalSex = AnimalSex.MALE
    patch_id: int | None = None
    mate_id: int | None = None
    age_days: float = 0.0
    move_cooldown: int = 0
    # Autumn roost retreat (still affiliated with a patch).
    retreat_target: tuple[int, int] | None = None
    # Dispersal: home patch while seeking a new ground (patch_id is None).
    migrate_home_id: int | None = None
    # Autumn/winter: walk toward this tile on a patch that has space.
    migrate_target: tuple[int, int] | None = None
    # True after leaving home this year; cleared each spring.
    migrated_this_year: bool = False
    # Hunt panic: flee away from kill site for scare_steps rapid hops.
    scare_from: tuple[int, int] | None = None
    scare_steps: int = 0
    # Hawks / owls face last horizontal move when drawn.
    facing_right: bool = True
    # Straight-line soar: remaining steps and heading (Chebyshev).
    roam_leg: int = 0
    roam_dx: int = 0
    roam_dy: int = 0
    # Live status for inspect / wildlife list (birds).
    activity: str = ""
    # Crop raid state. The animal must remain on the crop for a full day.
    crop_target: tuple[int, int] | None = None
    crop_arrived_day: float | None = None
    world_x: float | None = None
    world_y: float | None = None
    # Hunting wound state (non-colony animals). Colony harvest is separate.
    hp: int = 0
    max_hp: int = 0
    # Runtime-only path cache for migration / blocked steps (not saved).
    _path_cache: list[tuple[int, int]] | None = field(
        default=None, repr=False, compare=False
    )
    _path_goal: tuple[int, int] | None = field(
        default=None, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        self.world_x = float(self.x) if self.world_x is None else float(self.world_x)
        self.world_y = float(self.y) if self.world_y is None else float(self.world_y)
        if self.max_hp <= 0:
            from entities import hunt_max_hp

            self.max_hp = hunt_max_hp(self.kind.name)
        if self.hp <= 0:
            self.hp = int(self.max_hp)


@dataclass
class ColonyMember:
    """Visible individual that wanders near its colony nest."""

    x: int
    y: int
    move_cooldown: int = 0
    world_x: float | None = None
    world_y: float | None = None

    def __post_init__(self) -> None:
        self.world_x = float(self.x) if self.world_x is None else float(self.world_x)
        self.world_y = float(self.y) if self.world_y is None else float(self.world_y)


@dataclass
class Colony:
    """Bee or rabbit colony; level controls visible population around the nest."""

    id: int
    kind: AnimalKind
    x: int
    y: int
    level: int = 1
    habitat_id: int | None = None
    members: list[ColonyMember] = field(default_factory=list)
    # Growth ticks until hunt / honey collect is allowed again.
    harvest_cooldown: int = 0

    def clamp_level(self) -> None:
        self.level = max(1, min(COLONY_LEVEL_MAX, int(self.level)))

    def target_members(self) -> int:
        self.clamp_level()
        return COLONY_MEMBERS_BY_LEVEL[self.level - 1]

    def can_harvest(self) -> bool:
        return self.harvest_cooldown <= 0 and self.level >= 1


@dataclass
class WolfMember:
    """One wolf in a pack (drawn near the pack centre)."""

    sex: AnimalSex
    x: int
    y: int
    move_cooldown: int = 0
    world_x: float | None = None
    world_y: float | None = None
    hp: int = 0
    max_hp: int = 0

    def __post_init__(self) -> None:
        self.world_x = float(self.x) if self.world_x is None else float(self.world_x)
        self.world_y = float(self.y) if self.world_y is None else float(self.world_y)
        if self.max_hp <= 0:
            # Kind is on the pack; default to wolf until assigned.
            from entities import hunt_max_hp

            self.max_hp = hunt_max_hp("WOLF")
        if self.hp <= 0:
            self.hp = int(self.max_hp)


@dataclass
class WolfPack:
    """Mobile wolf pack — habitat is the whole walkable map."""

    id: int
    x: int
    y: int
    members: list[WolfMember] = field(default_factory=list)
    kind: AnimalKind = AnimalKind.WOLF
    # Days of food left (counts down; capped at boar feed duration).
    fed_days_remaining: float = 0.0
    move_cooldown: int = 0
    # Last successful kill (for inspect UI).
    last_prey: str = ""
    last_meal_day: float = -1.0
    # Live activity label refreshed each tick (Fleeing / Hunting / …).
    activity: str = "Roaming"
    world_x: float | None = None
    world_y: float | None = None

    def __post_init__(self) -> None:
        self.world_x = float(self.x) if self.world_x is None else float(self.world_x)
        self.world_y = float(self.y) if self.world_y is None else float(self.world_y)

    def size(self) -> int:
        return len(self.members)

    def has_pair(self) -> bool:
        sexes = {m.sex for m in self.members}
        return AnimalSex.MALE in sexes and AnimalSex.FEMALE in sexes

    def is_fed(self, day: float = 0.0) -> bool:
        del day
        return float(self.fed_days_remaining) > 0.0

    def food_days_left(self, day: float = 0.0) -> float:
        del day
        return max(0.0, float(self.fed_days_remaining))


@dataclass(frozen=True)
class PredatorTarget:
    """Hunting view of one member of a wolf or fox pack."""

    id: int
    x: int
    y: int
    kind: AnimalKind


@dataclass
class ForestHabitat:
    """Per-patch breeding / roaming areas for deer and boar."""

    id: int
    forest_tiles: list[tuple[int, int]]
    deer_breeding: list[tuple[int, int]]
    deer_roam_cold: set[tuple[int, int]]
    deer_roam_warm: set[tuple[int, int]]
    boar_breeding: list[tuple[int, int]]
    boar_roam_cold: set[tuple[int, int]]
    boar_roam_warm: set[tuple[int, int]]

    @property
    def deer_cap(self) -> int:
        per_cap = _bal_int("WILDLIFE_DEER_TILES_PER_CAP", ANIMAL_TREES_PER_CAP, 1)
        return len(self.deer_breeding) // per_cap

    @property
    def boar_cap(self) -> int:
        per_cap = _bal_int("WILDLIFE_BOAR_TILES_PER_CAP", BOAR_CELLS_PER_CAP, 1)
        return len(self.boar_breeding) // per_cap


@dataclass
class OpenHabitat:
    """Meadow / forest-edge nest sites for bee and rabbit colonies."""

    id: int
    nest_tiles: list[tuple[int, int]]
    forage_tiles: set[tuple[int, int]]
    allow_bee: bool = True
    allow_rabbit: bool = True
    allow_frog: bool = False
    allow_vole: bool = False

    # One colony of each allowed kind per nest site (UI / capacity display).
    @property
    def bee_cap(self) -> int:
        return 1 if self.allow_bee and self.nest_tiles else 0

    @property
    def rabbit_cap(self) -> int:
        return 1 if self.allow_rabbit and self.nest_tiles else 0

    @property
    def frog_cap(self) -> int:
        return 1 if self.allow_frog and self.nest_tiles else 0

    @property
    def vole_cap(self) -> int:
        return 1 if self.allow_vole and self.nest_tiles else 0


Habitat = ForestHabitat | OpenHabitat


class WildlifeManager:
    """Forest game (deer/boar), bee/rabbit colonies, and wolf packs."""

    def __init__(self, seed: int = RANDOM_SEED) -> None:
        self.rng = random.Random(seed + 7)
        self.animals: list[Animal] = []
        self.colonies: list[Colony] = []
        self.wolf_packs: list[WolfPack] = []
        self.next_id = 1
        self.next_colony_id = 1
        self.next_wolf_pack_id = 1
        self.growth_timer = ANIMAL_GROWTH_INTERVAL
        self.habitats: list[ForestHabitat] = []
        self.open_habitats: list[OpenHabitat] = []
        self._seeded = False
        self._colonies_need_seed = False
        self._prev_season: Season | None = None
        self._by_id: dict[int, Animal] = {}
        self._wolf_food_day: float | None = None
        self._last_breed_year: int = -1

    def reset(self) -> None:
        self.animals.clear()
        self.colonies.clear()
        self.wolf_packs.clear()
        self._by_id.clear()
        self.next_id = 1
        self.next_colony_id = 1
        self.next_wolf_pack_id = 1
        self.growth_timer = ANIMAL_GROWTH_INTERVAL
        self.habitats.clear()
        self.open_habitats.clear()
        self._seeded = False
        self._colonies_need_seed = False
        self._prev_season = None
        self._wolf_food_day = None
        self._last_breed_year = -1
        self.rng.seed(RANDOM_SEED + 7)

    def _index_animals(self) -> None:
        self._by_id = {a.id: a for a in self.animals}

    def deer(self) -> list[Animal]:
        return [a for a in self.animals if a.kind == AnimalKind.DEER]

    def boars(self) -> list[Animal]:
        return [a for a in self.animals if a.kind == AnimalKind.BOAR]

    def wolf_count(self) -> int:
        return sum(
            p.size() for p in self.wolf_packs if p.kind == AnimalKind.WOLF
        )

    def fox_count(self) -> int:
        return sum(p.size() for p in self.wolf_packs if p.kind == AnimalKind.FOX)

    def pack_count(self, kind: AnimalKind) -> int:
        return sum(p.size() for p in self.wolf_packs if p.kind == kind)

    def wolf_positions(self) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        for pack in self.wolf_packs:
            out.append((pack.x, pack.y))
            for m in pack.members:
                out.append((m.x, m.y))
        return out

    def bee_colonies(self) -> list[Colony]:
        return [c for c in self.colonies if c.kind == AnimalKind.BEE]

    def rabbit_colonies(self) -> list[Colony]:
        return [c for c in self.colonies if c.kind == AnimalKind.RABBIT]

    def colonies_of(self, kind: AnimalKind) -> list[Colony]:
        return [c for c in self.colonies if c.kind == kind]

    def count_kind(self, kind: AnimalKind) -> int:
        if kind in COLONY_KINDS:
            return len(self.colonies_of(kind))
        if kind == AnimalKind.FOX:
            return self.fox_count()
        if kind in BIRD_KINDS:
            return sum(1 for a in self.animals if a.kind == kind)
        return sum(1 for a in self.animals if a.kind == kind)

    def colony_members_total(self, kind: AnimalKind) -> int:
        return sum(c.target_members() for c in self.colonies_of(kind))

    def total_capacity(self, world: World | None = None) -> int:
        del world
        forest = sum(h.deer_cap + h.boar_cap for h in self.habitats)
        open_cap = sum(
            h.bee_cap + h.rabbit_cap + h.frog_cap + h.vole_cap
            for h in self.open_habitats
        )
        return forest + open_cap

    def animal_at(self, x: int, y: int) -> Animal | None:
        for animal in self.animals:
            if animal.x == x and animal.y == y:
                return animal
        return None

    def colony_member_at(self, x: int, y: int) -> tuple[Colony | None, ColonyMember | None]:
        """Return the colony and member standing on ``(x, y)``, if any."""
        for colony in self.colonies:
            if (colony.x, colony.y) == (x, y):
                return colony, None
            for member in colony.members:
                if (member.x, member.y) == (x, y):
                    return colony, member
        return None, None

    def animals_in_area(self, contains) -> list[Animal]:
        return [a for a in self.animals if contains(a.x, a.y)]

    def huntable_animals(self) -> list[Animal | PredatorTarget]:
        targets: list[Animal | PredatorTarget] = list(self.animals)
        for pack in self.wolf_packs:
            for member_index, member in enumerate(pack.members):
                targets.append(
                    PredatorTarget(
                        self._predator_target_id(pack.id, member_index),
                        member.x,
                        member.y,
                        pack.kind,
                    )
                )
        return targets

    @staticmethod
    def _predator_target_id(pack_id: int, member_index: int) -> int:
        """Stable-enough negative hunt ID for one member during a chase."""
        return -(int(pack_id) * 1000 + int(member_index) + 1)

    @staticmethod
    def _predator_target_parts(target_id: int) -> tuple[int, int]:
        encoded = -int(target_id) - 1
        return encoded // 1000, encoded % 1000

    def huntable_by_id(self, target_id: int) -> Animal | PredatorTarget | None:
        if target_id >= 0:
            self._index_animals()
            return self._by_id.get(target_id)
        pack_id, member_index = self._predator_target_parts(target_id)
        for pack in self.wolf_packs:
            if pack.id == pack_id and 0 <= member_index < len(pack.members):
                member = pack.members[member_index]
                return PredatorTarget(target_id, member.x, member.y, pack.kind)
        return None

    def kill_animal(self, animal_id: int) -> tuple[int, int, AnimalKind] | None:
        if animal_id < 0:
            pack_id, member_index = self._predator_target_parts(animal_id)
            for pack in list(self.wolf_packs):
                if pack.id != pack_id or not (0 <= member_index < len(pack.members)):
                    continue
                member = pack.members.pop(member_index)
                if not pack.members:
                    self.wolf_packs.remove(pack)
                return member.x, member.y, pack.kind
            return None
        self._index_animals()
        animal = self._by_id.get(animal_id)
        if animal is None:
            return None
        self._clear_mate(animal)
        pos = (animal.x, animal.y, animal.kind)
        self.animals.remove(animal)
        self._by_id.pop(animal_id, None)
        return pos

    def apply_hunt_damage(
        self, animal_id: int, damage: int
    ) -> tuple[bool, int, int, AnimalKind, int, int] | None:
        """Wound a huntable animal. Returns (dead, x, y, kind, hp, max_hp) or None."""
        from entities import hunt_max_hp

        dmg = max(0, int(damage))
        if animal_id < 0:
            pack_id, member_index = self._predator_target_parts(animal_id)
            for pack in self.wolf_packs:
                if pack.id != pack_id or not (0 <= member_index < len(pack.members)):
                    continue
                member = pack.members[member_index]
                desired = hunt_max_hp(pack.kind.name)
                if member.max_hp <= 0 or (
                    member.hp >= member.max_hp and member.max_hp != desired
                ):
                    member.max_hp = desired
                    member.hp = desired
                member.hp = max(0, int(member.hp) - dmg)
                if member.hp <= 0:
                    killed = self.kill_animal(animal_id)
                    if killed is None:
                        return None
                    x, y, kind = killed
                    return True, x, y, kind, 0, desired
                return False, member.x, member.y, pack.kind, member.hp, member.max_hp
            return None
        self._index_animals()
        animal = self._by_id.get(animal_id)
        if animal is None:
            return None
        if animal.max_hp <= 0:
            animal.max_hp = hunt_max_hp(animal.kind.name)
            animal.hp = animal.max_hp
        animal.hp = max(0, int(animal.hp) - dmg)
        if animal.hp <= 0:
            killed = self.kill_animal(animal_id)
            if killed is None:
                return None
            x, y, kind = killed
            return True, x, y, kind, 0, animal.max_hp
        return False, animal.x, animal.y, animal.kind, animal.hp, animal.max_hp

    def scare_from_kill(
        self,
        kill_x: int,
        kill_y: int,
        *,
        radius: int | None = None,
        steps: int | None = None,
    ) -> int:
        """Send nearby deer/boar fleeing rapidly from a hunt kill site.

        Returns how many animals entered (or refreshed) panic.
        """
        r = HUNT_SCARE_RADIUS if radius is None else max(0, int(radius))
        n_steps = HUNT_SCARE_STEPS if steps is None else max(0, int(steps))
        if n_steps <= 0:
            return 0
        scared = 0
        for animal in self.animals:
            if animal.kind not in FOREST_KINDS:
                continue
            if max(abs(animal.x - kill_x), abs(animal.y - kill_y)) > r:
                continue
            animal.scare_from = (kill_x, kill_y)
            animal.scare_steps = max(animal.scare_steps, n_steps)
            animal.move_cooldown = 0
            animal.retreat_target = None
            scared += 1
        return scared

    def _habitats_for(self, kind: AnimalKind) -> list[Habitat]:
        if kind in COLONY_KINDS:
            return list(self.open_habitats)
        return list(self.habitats)

    def habitat(
        self, patch_id: int | None, kind: AnimalKind | None = None
    ) -> Habitat | None:
        if patch_id is None:
            return None
        if kind in COLONY_KINDS:
            if 0 <= patch_id < len(self.open_habitats):
                return self.open_habitats[patch_id]
            return None
        if kind in FOREST_KINDS or kind is None:
            if 0 <= patch_id < len(self.habitats):
                return self.habitats[patch_id]
        return None

    def breeding_grounds(self, kind: AnimalKind) -> list[Habitat]:
        """Usable nest / breeding sites for this species."""
        if kind in COLONY_KINDS:
            return list(self._colony_sites(kind))
        return [
            h
            for h in self._habitats_for(kind)
            if self._breeding_for(kind, h)
            and self._cap_for(kind, h) >= MIN_BREEDING_CAPACITY
        ]

    def _colony_sites(self, kind: AnimalKind) -> list[OpenHabitat]:
        sites = [
            h
            for h in self.open_habitats
            if self._allows_colony(kind, h) and h.nest_tiles
        ]
        if kind in COLONY_KINDS:
            sites = [
                h
                for h in sites
                if colony_max_level_for_forage(kind, len(h.forage_tiles)) >= 1
            ]
        return sites

    @staticmethod
    def _allows_colony(kind: AnimalKind, hab: OpenHabitat) -> bool:
        if kind == AnimalKind.BEE:
            return hab.allow_bee
        if kind == AnimalKind.RABBIT:
            return hab.allow_rabbit
        if kind == AnimalKind.FROG:
            return hab.allow_frog
        if kind == AnimalKind.VOLE:
            return hab.allow_vole
        return False

    def _colony_forage_count(self, colony: Colony) -> int:
        hab = self._colony_habitat(colony)
        if hab is None:
            return 0
        return len(hab.forage_tiles)

    def _enforce_colony_forage_caps(self) -> None:
        """Clamp bee/rabbit levels to forage÷N; remove colonies below N forage tiles."""
        kept: list[Colony] = []
        for colony in self.colonies:
            if colony.kind not in COLONY_KINDS:
                kept.append(colony)
                continue
            hab = self._colony_habitat(colony)
            max_lv = colony_max_level_for_forage(
                colony.kind,
                len(hab.forage_tiles) if hab is not None else 0,
            )
            if max_lv < 1:
                continue
            if colony.level > max_lv:
                colony.level = max_lv
                colony.clamp_level()
                self._sync_colony_members(colony, hab)
            kept.append(colony)
        self.colonies = kept

    def _colony_on_habitat(self, kind: AnimalKind, habitat_id: int) -> Colony | None:
        for colony in self.colonies:
            if colony.kind == kind and colony.habitat_id == habitat_id:
                return colony
        return None

    def _empty_colony_sites(self, kind: AnimalKind) -> list[OpenHabitat]:
        return [
            h
            for h in self._colony_sites(kind)
            if self._colony_on_habitat(kind, h.id) is None
        ]

    def _random_sex(self) -> AnimalSex:
        return AnimalSex.MALE if self.rng.random() < 0.5 else AnimalSex.FEMALE

    def _clear_mate(self, animal: Animal) -> None:
        if animal.mate_id is None:
            return
        mate = self._by_id.get(animal.mate_id)
        if mate is not None and mate.mate_id == animal.id:
            mate.mate_id = None
        animal.mate_id = None

    def _mate_of(self, animal: Animal) -> Animal | None:
        if animal.mate_id is None:
            return None
        mate = self._by_id.get(animal.mate_id)
        if mate is None or mate.mate_id != animal.id:
            animal.mate_id = None
            return None
        if mate.kind != animal.kind:
            self._clear_mate(animal)
            return None
        if mate.patch_id != animal.patch_id:
            # Keep bond while dispersing / settling from the same home.
            same_home = (
                animal.migrate_home_id is not None
                and mate.migrate_home_id == animal.migrate_home_id
            )
            one_arrived = (
                animal.patch_id is not None
                and mate.patch_id is None
                and mate.migrate_home_id is not None
            ) or (
                mate.patch_id is not None
                and animal.patch_id is None
                and animal.migrate_home_id is not None
            )
            if not same_home and not one_arrived:
                self._clear_mate(animal)
                return None
        return mate


    # ------------------------------------------------------------------
    # Habitat refresh (same cadence as biodiversity samples)
    # ------------------------------------------------------------------
    def refresh_habitats(self, world: World) -> None:
        """Rebuild forest-patch and open-nest breeding/roaming maps."""
        old_forests = [set(h.forest_tiles) for h in self.habitats]
        old_forest_ids = [
            a.patch_id for a in self.animals if a.kind in FOREST_KINDS
        ]
        forest_animals = [a for a in self.animals if a.kind in FOREST_KINDS]

        patches = world.forest_floor_patches()
        habitats: list[ForestHabitat] = []
        for i, forest in enumerate(patches):
            deer_breeding = self._deer_breeding_tiles(world, forest)
            deer_cold = self._expand_walkable(world, deer_breeding, radius=1)
            deer_warm = self._warm_roam(world, forest, deer_cold)
            boar_breeding = list(forest)
            boar_cold = self._expand_walkable(world, boar_breeding, radius=1)
            boar_warm = self._warm_roam(world, forest, boar_cold)
            habitats.append(
                ForestHabitat(
                    id=i,
                    forest_tiles=list(forest),
                    deer_breeding=deer_breeding,
                    deer_roam_cold=deer_cold,
                    deer_roam_warm=deer_warm,
                    boar_breeding=boar_breeding,
                    boar_roam_cold=boar_cold,
                    boar_roam_warm=boar_warm,
                )
            )
        self.habitats = habitats
        self._remap_animals_after_refresh(
            forest_animals, old_forests, old_forest_ids, forest=True
        )
        self._refresh_open_habitats(world)
        if getattr(self, "_colonies_need_seed", False):
            self._colonies_need_seed = False
            # Seed any colony kinds that are still absent (not only when none exist).
            for kind in COLONY_KINDS:
                if self.count_kind(kind) > 0:
                    continue
                sites = self._empty_colony_sites(kind)
                self.rng.shuffle(sites)
                for hab in sites[:COLONY_SEED_GROUNDS]:
                    self._spawn_colony(kind, hab, level=1)
        for colony in self.colonies:
            self._sync_colony_members(colony, self._colony_habitat(colony))

    def _refresh_open_habitats(self, world: World) -> None:
        old_nests = [set(h.nest_tiles) for h in self.open_habitats]
        old_colony_ids = [c.habitat_id for c in self.colonies]

        meadow_terrain = (TerrainType.MEADOW, TerrainType.GRASS)
        vole_terrain = (TerrainType.MEADOW, TerrainType.GRASS, TerrainType.RIPARIAN)

        habitats: list[OpenHabitat] = []
        hid = 0
        for patch in world.meadow_patches():
            nest = list(patch)
            forage = self._forage_from_nests(world, nest, meadow_terrain)
            if not nest or not forage:
                continue
            habitats.append(
                OpenHabitat(
                    id=hid,
                    nest_tiles=nest,
                    forage_tiles=forage,
                    allow_bee=True,
                    allow_rabbit=True,
                    allow_vole=True,
                )
            )
            hid += 1
        for patch in world.grass_patches():
            nest = list(patch)
            forage = self._forage_from_nests(world, nest, (TerrainType.GRASS,))
            if not nest or not forage:
                continue
            habitats.append(
                OpenHabitat(
                    id=hid,
                    nest_tiles=nest,
                    forage_tiles=forage,
                    allow_vole=True,
                )
            )
            hid += 1
        for patch in world.riparian_patches():
            nest = list(patch)
            # Shore forage: riparian plus adjacent grass/meadow within radius.
            forage = self._forage_from_nests(world, nest, vole_terrain)
            if not nest or not forage:
                continue
            habitats.append(
                OpenHabitat(
                    id=hid,
                    nest_tiles=nest,
                    forage_tiles=forage,
                    allow_frog=True,
                    allow_vole=True,
                )
            )
            hid += 1
        for fh in self.habitats:
            if not fh.deer_breeding:
                continue
            nest = list(fh.deer_breeding)
            forage = self._forage_from_nests(world, nest, meadow_terrain)
            if not forage:
                continue
            habitats.append(
                OpenHabitat(
                    id=hid,
                    nest_tiles=nest,
                    forage_tiles=forage,
                    allow_bee=True,
                    allow_rabbit=False,
                )
            )
            hid += 1
        self.open_habitats = habitats
        self._remap_colonies_after_refresh(old_nests, old_colony_ids)
        self._enforce_colony_forage_caps()

    @staticmethod
    def _is_forage_tile(
        world: World,
        x: int,
        y: int,
        terrains: tuple[TerrainType, ...] | None = None,
    ) -> bool:
        cell = world.get_cell(x, y)
        if cell is None or not world.is_walkable(x, y):
            return False
        if terrains is None:
            terrains = (TerrainType.MEADOW, TerrainType.GRASS)
        if cell.terrain in terrains:
            return True
        return cell.feature == FeatureType.FIELD

    def _forage_from_nests(
        self,
        world: World,
        nests: list[tuple[int, int]],
        terrains: tuple[TerrainType, ...] | None = None,
    ) -> set[tuple[int, int]]:
        """Contiguous forage tiles within ``SMALL_GAME_FORAGE_RADIUS`` of nests."""
        radius = SMALL_GAME_FORAGE_RADIUS
        candidates: set[tuple[int, int]] = set()
        for nx, ny in nests:
            for cy, cx in world.neighbourhood(nx, ny, radius=radius):
                if self._is_forage_tile(world, cx, cy, terrains):
                    candidates.add((cx, cy))
        starts: set[tuple[int, int]] = set()
        for nx, ny in nests:
            if (nx, ny) in candidates:
                starts.add((nx, ny))
            for cy, cx in world.neighbourhood(nx, ny, radius=1):
                if (cx, cy) in candidates:
                    starts.add((cx, cy))
        if not starts:
            return set()
        forage: set[tuple[int, int]] = set()
        stack = list(starts)
        seen = set(starts)
        while stack:
            cx, cy = stack.pop()
            forage.add((cx, cy))
            for ny, nx in world.neighbourhood(cx, cy, radius=1):
                pos = (nx, ny)
                if pos in candidates and pos not in seen:
                    seen.add(pos)
                    stack.append(pos)
        return forage

    @staticmethod
    def _deer_breeding_tiles(
        world: World, forest: list[tuple[int, int]]
    ) -> list[tuple[int, int]]:
        """Forest-floor tiles that border open land (no tree/sapling there).

        Soil and riparian count as open edge so dense forests ringed by tilled
        or waterside ground still form usable deer habitats.
        """
        open_land = (
            TerrainType.GRASS,
            TerrainType.MEADOW,
            TerrainType.SOIL,
            TerrainType.RIPARIAN,
        )
        breeding: list[tuple[int, int]] = []
        for fx, fy in forest:
            for ny, nx in world.neighbourhood(fx, fy, radius=1):
                if (nx, ny) == (fx, fy):
                    continue
                cell = world.cells[ny][nx]
                if cell.terrain not in open_land:
                    continue
                if cell.feature in (FeatureType.TREE, FeatureType.SAPLING):
                    continue
                breeding.append((fx, fy))
                break
        return breeding

    @staticmethod
    def _expand_walkable(
        world: World, centres: list[tuple[int, int]], *, radius: int
    ) -> set[tuple[int, int]]:
        out: set[tuple[int, int]] = set()
        for cx, cy in centres:
            for ny, nx in world.neighbourhood(cx, cy, radius=radius):
                if world.is_walkable(nx, ny):
                    out.add((nx, ny))
        return out

    def _warm_roam(
        self,
        world: World,
        forest: list[tuple[int, int]],
        cold: set[tuple[int, int]],
    ) -> set[tuple[int, int]]:
        """Cold roam plus grass/meadow near the forest patch (spring/summer range)."""
        warm = set(cold)
        open_land = (TerrainType.GRASS, TerrainType.MEADOW)
        forest_set = set(forest)
        for cx, cy in forest:
            for ny, nx in world.neighbourhood(cx, cy, radius=2):
                if not world.is_walkable(nx, ny):
                    continue
                if world.cells[ny][nx].terrain in open_land:
                    warm.add((nx, ny))
        for cx, cy in cold:
            if (cx, cy) in forest_set:
                continue
            for ny, nx in world.neighbourhood(cx, cy, radius=1):
                if not world.is_walkable(nx, ny):
                    continue
                if world.cells[ny][nx].terrain in open_land:
                    warm.add((nx, ny))
        return warm

    def _remap_animals_after_refresh(
        self,
        animals: list[Animal],
        old_tiles: list[set[tuple[int, int]]],
        old_ids: list[int | None],
        *,
        forest: bool,
    ) -> None:
        """Keep patch affiliation by tile overlap; never auto-claim empty grounds."""
        habitats: list[Habitat] = (
            list(self.habitats) if forest else list(self.open_habitats)
        )

        def tiles_of(hab: Habitat) -> set[tuple[int, int]]:
            if isinstance(hab, ForestHabitat):
                return set(hab.forest_tiles)
            return set(hab.nest_tiles)

        if not habitats:
            for animal in animals:
                animal.patch_id = None
                animal.migrate_home_id = None
                animal.migrate_target = None
            return

        for animal, old_id in zip(animals, old_ids):
            mapped: int | None = None
            if old_id is not None and 0 <= old_id < len(old_tiles):
                old_set = old_tiles[old_id]
                best_overlap = 0
                for hab in habitats:
                    overlap = len(old_set & tiles_of(hab))
                    if overlap > best_overlap:
                        best_overlap = overlap
                        mapped = hab.id
            if mapped is not None:
                animal.patch_id = mapped
            else:
                animal.patch_id = None

            if animal.migrate_home_id is not None:
                home_mapped: int | None = None
                old_home = animal.migrate_home_id
                if 0 <= old_home < len(old_tiles):
                    old_set = old_tiles[old_home]
                    best_overlap = 0
                    for hab in habitats:
                        overlap = len(old_set & tiles_of(hab))
                        if overlap > best_overlap:
                            best_overlap = overlap
                            home_mapped = hab.id
                animal.migrate_home_id = home_mapped
                if home_mapped is None:
                    animal.migrate_target = None

    def _remap_colonies_after_refresh(
        self,
        old_nests: list[set[tuple[int, int]]],
        old_habitat_ids: list[int | None],
    ) -> None:
        if not self.open_habitats:
            for colony in self.colonies:
                colony.habitat_id = None
            return
        for colony, old_id in zip(self.colonies, old_habitat_ids):
            mapped: int | None = None
            if old_id is not None and 0 <= old_id < len(old_nests):
                old_set = old_nests[old_id]
                best_overlap = 0
                for hab in self.open_habitats:
                    if not self._allows_colony(colony.kind, hab):
                        continue
                    overlap = len(old_set & set(hab.nest_tiles))
                    if overlap > best_overlap:
                        best_overlap = overlap
                        mapped = hab.id
            if mapped is None:
                # Snap to habitat containing the nest tile.
                for hab in self.open_habitats:
                    if not self._allows_colony(colony.kind, hab):
                        continue
                    if (colony.x, colony.y) in hab.nest_tiles:
                        mapped = hab.id
                        break
            colony.habitat_id = mapped
            if mapped is not None:
                hab = self.open_habitats[mapped]
                if (colony.x, colony.y) not in hab.nest_tiles and hab.nest_tiles:
                    colony.x, colony.y = self.rng.choice(hab.nest_tiles)

    def _cap_for(self, kind: AnimalKind, hab: Habitat) -> int:
        if isinstance(hab, OpenHabitat):
            if kind == AnimalKind.BEE:
                return hab.bee_cap
            if kind == AnimalKind.RABBIT:
                return hab.rabbit_cap
            if kind == AnimalKind.FROG:
                return hab.frog_cap
            if kind == AnimalKind.VOLE:
                return hab.vole_cap
            return 0
        if kind == AnimalKind.DEER:
            return hab.deer_cap
        if kind == AnimalKind.BOAR:
            return hab.boar_cap
        return 0

    def _breeding_for(self, kind: AnimalKind, hab: Habitat) -> list[tuple[int, int]]:
        if isinstance(hab, OpenHabitat):
            if kind == AnimalKind.BEE and hab.allow_bee:
                return hab.nest_tiles
            if kind == AnimalKind.RABBIT and hab.allow_rabbit:
                return hab.nest_tiles
            if kind == AnimalKind.FROG and hab.allow_frog:
                return hab.nest_tiles
            if kind == AnimalKind.VOLE and hab.allow_vole:
                return hab.nest_tiles
            return []
        if kind == AnimalKind.DEER:
            return hab.deer_breeding
        if kind == AnimalKind.BOAR:
            return hab.boar_breeding
        return []

    def _roaming_for(
        self, kind: AnimalKind, hab: Habitat, season: Season
    ) -> set[tuple[int, int]]:
        if isinstance(hab, OpenHabitat):
            return set(hab.forage_tiles)
        warm = season in (Season.SPRING, Season.SUMMER)
        if kind == AnimalKind.DEER:
            return hab.deer_roam_warm if warm else hab.deer_roam_cold
        if kind == AnimalKind.BOAR:
            return hab.boar_roam_warm if warm else hab.boar_roam_cold
        return set()

    def _cold_roaming_for(self, kind: AnimalKind, hab: Habitat) -> set[tuple[int, int]]:
        if isinstance(hab, OpenHabitat):
            return set(hab.forage_tiles)
        if kind == AnimalKind.DEER:
            return hab.deer_roam_cold
        if kind == AnimalKind.BOAR:
            return hab.boar_roam_cold
        return set()

    def count_in_patch(self, kind: AnimalKind, patch_id: int) -> int:
        return sum(1 for a in self.animals if a.kind == kind and a.patch_id == patch_id)

    def count_migrating_from(self, kind: AnimalKind, patch_id: int) -> int:
        """Animals that left this home and have not yet claimed a new patch."""
        return sum(
            1
            for a in self.animals
            if a.kind == kind
            and a.migrate_home_id == patch_id
            and a.patch_id is None
        )

    def patch_occupancy(
        self, kind: AnimalKind, patch_id: int
    ) -> tuple[int, int, int, int]:
        """Return (present, migrating_out, total, pairs).

        Total = present + outbound migrants still affiliated with this home.
        """
        cache = getattr(self, "_occ_cache", None)
        if cache is None:
            present_map: dict[tuple[AnimalKind, int], list[Animal]] = {}
            outbound_map: dict[tuple[AnimalKind, int], list[Animal]] = {}
            for a in self.animals:
                if a.patch_id is not None:
                    present_map.setdefault((a.kind, a.patch_id), []).append(a)
                elif a.migrate_home_id is not None:
                    outbound_map.setdefault((a.kind, a.migrate_home_id), []).append(a)
            cache = {}
            keys = set(present_map) | set(outbound_map)
            for key in keys:
                present = present_map.get(key, [])
                outbound = outbound_map.get(key, [])
                paired = sum(1 for a in present + outbound if a.mate_id is not None) // 2
                cache[key] = (
                    len(present),
                    len(outbound),
                    len(present) + len(outbound),
                    paired,
                )
            self._occ_cache = cache
        return cache.get((kind, patch_id), (0, 0, 0, 0))

    def _count_in_patch(self, kind: AnimalKind, patch_id: int) -> int:
        return self.count_in_patch(kind, patch_id)

    def _room_on_patch(self, kind: AnimalKind, patch_id: int) -> int:
        """Free slots on a patch (present residents only)."""
        hab = self.habitat(patch_id, kind)
        if hab is None:
            return 0
        return max(0, self._cap_for(kind, hab) - self.count_in_patch(kind, patch_id))

    def _occupied(self) -> set[tuple[int, int]]:
        return {(a.x, a.y) for a in self.animals}

    def _patch_inhabited(self, kind: AnimalKind, patch_id: int) -> bool:
        return self._count_in_patch(kind, patch_id) > 0

    # ------------------------------------------------------------------
    # Initial seeding
    # ------------------------------------------------------------------
    def seed_breeding_grounds(self, world: World) -> None:
        """Seed deer/boar pairs and bee/rabbit colonies on suitable grounds."""
        if self._seeded:
            return
        if not self.habitats and not self.open_habitats:
            self.refresh_habitats(world)
        self.animals.clear()
        self.colonies.clear()
        self.wolf_packs.clear()
        self.next_id = 1
        self.next_colony_id = 1
        self.next_wolf_pack_id = 1
        occupied: set[tuple[int, int]] = set()

        for kind in FOREST_KINDS:
            grounds = self.breeding_grounds(kind)
            grounds.sort(
                key=lambda h: len(self._breeding_for(kind, h)),
                reverse=True,
            )
            seed_habitats = _bal_int("WILDLIFE_SEED_HABITATS", WILDLIFE_SEED_GROUNDS)
            seed_animals = _bal_int("WILDLIFE_SEED_ANIMALS", WILDLIFE_SEED_COUNT)
            for hab in grounds[:seed_habitats]:
                self._seed_patch(kind, hab, seed_animals, occupied)
        self._seed_colonies(world)
        self._seed_wolf_packs(world)
        self._seed_fox_packs(world)
        self._seed_birds(world)
        self._seeded = True

    def ensure_missing_wildlife(self, world: World) -> None:
        """Backfill species missing from older saves or after a partial seed.

        Habitats must be rebuilt first so bird nests / colony sites exist.
        """
        self.refresh_habitats(world)
        self._reseed_extinct_forest_species(world)
        for kind in COLONY_KINDS:
            if self.count_kind(kind) > 0:
                continue
            sites = self._empty_colony_sites(kind)
            self.rng.shuffle(sites)
            seed_habitats = _bal_int(
                "WILDLIFE_COLONY_SEED_HABITATS", COLONY_SEED_GROUNDS
            )
            for hab in sites[:seed_habitats]:
                self._spawn_colony(kind, hab, level=1)
        if self.pack_count(AnimalKind.WOLF) <= 0:
            self._seed_wolf_packs(world)
        if self.pack_count(AnimalKind.FOX) <= 0:
            self._seed_fox_packs(world)
        for kind in BIRD_KINDS:
            if self.count_kind(kind) <= 0:
                self._seed_birds(world, kind=kind)
        self._seeded = True

    def _seed_colonies(self, world: World) -> None:
        del world
        for kind in COLONY_KINDS:
            sites = self._empty_colony_sites(kind)
            self.rng.shuffle(sites)
            for hab in sites[:COLONY_SEED_GROUNDS]:
                self._spawn_colony(kind, hab, level=1)

    def _seed_patch(
        self,
        kind: AnimalKind,
        hab: Habitat,
        count: int,
        occupied: set[tuple[int, int]],
    ) -> None:
        breed = list(self._breeding_for(kind, hab))
        if not breed:
            return
        self.rng.shuffle(breed)
        roam = self._cold_roaming_for(kind, hab)
        # Prefer one male + one female so the seed patch can form a mating pair.
        sexes: list[AnimalSex] = []
        if count >= 2:
            sexes = [AnimalSex.MALE, AnimalSex.FEMALE]
            sexes.extend(self._random_sex() for _ in range(count - 2))
            self.rng.shuffle(sexes)
        else:
            sexes = [self._random_sex() for _ in range(count)]
        placed = 0
        lead_pos: tuple[int, int] | None = None
        for bx, by in breed:
            if placed >= count:
                break
            if placed > 0 and lead_pos is not None:
                near_lead = [
                    p
                    for p in roam
                    if p not in occupied
                    and max(abs(p[0] - lead_pos[0]), abs(p[1] - lead_pos[1])) <= 1
                ]
                pool = near_lead or [
                    p
                    for p in roam
                    if p not in occupied and max(abs(p[0] - bx), abs(p[1] - by)) <= 1
                ]
            else:
                near = [
                    p
                    for p in roam
                    if p not in occupied and max(abs(p[0] - bx), abs(p[1] - by)) <= 1
                ]
                pool = near or [p for p in roam if p not in occupied]
            if not pool and (bx, by) not in occupied:
                pool = [(bx, by)]
            if not pool:
                continue
            sx, sy = self.rng.choice(pool)
            self.animals.append(
                Animal(
                    id=self.next_id,
                    x=sx,
                    y=sy,
                    kind=kind,
                    sex=sexes[placed],
                    patch_id=hab.id,
                    age_days=float(YEAR_DAYS * 2),
                    move_cooldown=animal_roam_interval(),
                )
            )
            self.next_id += 1
            occupied.add((sx, sy))
            if lead_pos is None:
                lead_pos = (sx, sy)
            placed += 1
        self._index_animals()
        self._form_mating_pairs()

    # ------------------------------------------------------------------
    # Season transitions
    # ------------------------------------------------------------------
    def on_season_change(self, world: World, season: Season) -> None:
        """Hook for calendar season changes (autumn retreat; winter migrant deaths)."""
        if season == Season.SPRING:
            self._annual_mortality(world)
            if hasattr(world, "age_trees_one_year"):
                world.age_trees_one_year()
            for animal in self.animals:
                # Only reset settled animals; mid-dispersal pairs already used this year's move.
                if animal.patch_id is not None and animal.migrate_home_id is None:
                    animal.migrated_this_year = False
            self._reseed_extinct_species(world)
        elif season == Season.AUTUMN:
            self._start_autumn_retreat(world)
        elif season == Season.WINTER:
            self._kill_failed_migrants()
        self._prev_season = season

    def _reseed_extinct_species(self, world: World) -> None:
        """Restore extinct wildlife where suitable habitat still exists."""
        if not self.habitats and not self.open_habitats:
            self.refresh_habitats(world)
        self._reseed_extinct_forest_species(world)
        for kind in COLONY_KINDS:
            if self.count_kind(kind) > 0:
                continue
            sites = self._empty_colony_sites(kind)
            if not sites:
                continue
            self._spawn_colony(kind, self.rng.choice(sites), level=1)
        if self.pack_count(AnimalKind.FOX) <= 0:
            self._seed_fox_packs(world)
        for kind in BIRD_KINDS:
            if self.count_kind(kind) > 0:
                continue
            self._seed_birds(world, kind=kind)

    def _reseed_extinct_forest_species(self, world: World) -> None:
        """Maintain one breeding pair of deer and boar after extinction."""
        if not self.habitats:
            self.refresh_habitats(world)
        occupied = self._occupied()
        for kind in FOREST_KINDS:
            if self.count_kind(kind) > 0:
                continue
            grounds = self.breeding_grounds(kind)
            if not grounds:
                continue
            hab = self.rng.choice(grounds)
            self._seed_patch(kind, hab, WILDLIFE_RESEED_PAIR, occupied)

    def ensure_lone_animals_have_mates(self, world: World) -> int:
        """Maintain a settled, mixed-sex deer/boar breeding population."""
        if not self.habitats:
            self.refresh_habitats(world)
        occupied = self._occupied()
        spawned = 0
        for kind in FOREST_KINDS:
            settled = [
                animal
                for animal in self.animals
                if animal.kind == kind and animal.patch_id is not None
            ]
            if not settled and self.count_kind(kind) > 0:
                grounds = self.breeding_grounds(kind)
                if grounds:
                    before = self.next_id
                    self._seed_patch(
                        kind,
                        self.rng.choice(grounds),
                        WILDLIFE_RESEED_PAIR,
                        occupied,
                    )
                    spawned += self.next_id - before
                continue
            if not settled:
                continue
            candidates: list[tuple[Habitat, AnimalSex]] = []
            for hab in self._habitats_for(kind):
                residents = [
                    a for a in self.animals
                    if a.kind == kind and a.patch_id == hab.id
                ]
                sexes = {animal.sex for animal in residents}
                if (
                    residents
                    and len(sexes) == 1
                    and len(residents) < self._cap_for(kind, hab)
                ):
                    candidates.append((hab, residents[0].sex))
            if not candidates:
                continue
            hab, resident_sex = self.rng.choice(candidates)
            before = self.next_id
            self._seed_patch(kind, hab, 1, occupied)
            if self.next_id == before:
                continue
            mate = self.animals[-1]
            mate.sex = (
                AnimalSex.FEMALE
                if resident_sex == AnimalSex.MALE
                else AnimalSex.MALE
            )
            spawned += 1
        for kind in PACK_KINDS:
            lone_packs = [
                pack for pack in self.wolf_packs
                if pack.kind == kind and len(pack.members) == 1
            ]
            if not lone_packs:
                continue
            pack = self.rng.choice(lone_packs)
            lone = pack.members[0]
            pack.members.append(
                self._new_pack_member(
                    pack.kind,
                    (AnimalSex.FEMALE
                     if lone.sex == AnimalSex.MALE else AnimalSex.MALE),
                    pack.x,
                    pack.y,
                )
            )
            spawned += 1
        if spawned:
            self._index_animals()
            self._form_mating_pairs()
        return spawned

    def _kill_failed_migrants(self) -> None:
        """Animals still searching for a new breeding ground die when winter arrives."""
        survivors: list[Animal] = []
        for animal in self.animals:
            if animal.migrate_home_id is not None and animal.patch_id is None:
                self._clear_mate(animal)
                continue
            survivors.append(animal)
        if len(survivors) != len(self.animals):
            self.animals = survivors
            self._index_animals()

    def _start_autumn_retreat(self, world: World) -> None:
        open_land = (TerrainType.GRASS, TerrainType.MEADOW)
        for animal in self.animals:
            if animal.kind in BIRD_KINDS:
                continue
            cell = world.get_cell(animal.x, animal.y)
            if cell is None or cell.terrain not in open_land:
                animal.retreat_target = None
                continue
            target = self._nearest_breeding_tile(animal.kind, animal.x, animal.y)
            animal.retreat_target = target

    def _nearest_breeding_tile(
        self, kind: AnimalKind, x: int, y: int
    ) -> tuple[int, int] | None:
        """Nearest breeding tile of this kind (empty or inhabited grounds)."""
        best: tuple[int, tuple[int, int]] | None = None
        for hab in self._habitats_for(kind):
            breed = self._breeding_for(kind, hab)
            if not breed:
                continue
            for bx, by in breed:
                dist = max(abs(bx - x), abs(by - y))
                if best is None or dist < best[0]:
                    best = (dist, (bx, by))
        return best[1] if best is not None else None

    def _nearest_breeding_habitat(
        self, kind: AnimalKind, x: int, y: int
    ) -> Habitat | None:
        best_h: Habitat | None = None
        best_d = 10**9
        for hab in self._habitats_for(kind):
            breed = self._breeding_for(kind, hab)
            if not breed:
                continue
            d = min(max(abs(bx - x), abs(by - y)) for bx, by in breed)
            if d < best_d:
                best_d = d
                best_h = hab
        return best_h

    # ------------------------------------------------------------------
    # Simulation tick
    # ------------------------------------------------------------------
    def tick(
        self,
        world: World,
        day: float = 0.0,
        *,
        hunter_threats: list[tuple[int, int]] | None = None,
        flee_interval: int | None = None,
        biodiversity: list[list[float]] | None = None,
    ) -> None:
        if not self.habitats and not self.open_habitats:
            self.refresh_habitats(world)
        self._occ_cache = None
        self._index_animals()
        season = season_for_day(int(day))
        if self._prev_season is None:
            self._prev_season = season
        elif season != self._prev_season:
            self.on_season_change(world, season)
        self._form_mating_pairs(reindex=False)
        self._move_animals(
            world,
            day,
            season,
            hunter_threats=hunter_threats,
            flee_interval=flee_interval,
            biodiversity=biodiversity,
        )
        self._move_colony_members(world, day, biodiversity=biodiversity)
        self._tick_wolf_packs(
            world,
            day,
            biodiversity=biodiversity,
            villager_threats=hunter_threats,
            flee_interval=flee_interval,
        )
        self._tick_birds(world, day, biodiversity=biodiversity)
        if not animals_multiply(day):
            return
        self.growth_timer -= 1
        if self.growth_timer <= 0:
            self.growth_timer = ANIMAL_GROWTH_INTERVAL
            self._graze(world)
            self._form_mating_pairs()
            year = max(0, int(day) // YEAR_DAYS)
            if season == Season.SPRING and year != self._last_breed_year:
                self._breed(world)
                self._last_breed_year = year
            self._cull_excess()
            # Predation can erase a species between annual spring reseeds. Keep
            # minimum viable prey wherever suitable habitat remains.
            self._reseed_extinct_species(world)
            self._migrate()
            self._tick_colonies(world)
            self._breed_wolves(world)

    def _form_mating_pairs(self, *, reindex: bool = True) -> None:
        """Pair unpaired males and females that share a patch."""
        if reindex:
            self._index_animals()
        for animal in self.animals:
            if animal.mate_id is not None:
                self._mate_of(animal)

        for kind in FOREST_KINDS:
            by_patch: dict[int, list[Animal]] = {}
            for animal in self.animals:
                if animal.kind != kind or animal.patch_id is None:
                    continue
                by_patch.setdefault(animal.patch_id, []).append(animal)
            for group in by_patch.values():
                males = [
                    a for a in group if a.sex == AnimalSex.MALE and a.mate_id is None
                ]
                females = [
                    a
                    for a in group
                    if a.sex == AnimalSex.FEMALE and a.mate_id is None
                ]
                self.rng.shuffle(males)
                self.rng.shuffle(females)
                for male, female in zip(males, females):
                    male.mate_id = female.id
                    female.mate_id = male.id

    def _breeding_center(
        self, kind: AnimalKind, hab: Habitat
    ) -> tuple[float, float] | None:
        breed = self._breeding_for(kind, hab)
        if not breed:
            return None
        return (
            sum(p[0] for p in breed) / len(breed),
            sum(p[1] for p in breed) / len(breed),
        )

    def _weighted_away_choice(
        self,
        options: list[tuple[int, int]],
        center: tuple[float, float] | None,
    ) -> tuple[int, int]:
        """Pick a tile; prefer those farther from the breeding-ground centre."""
        if not options:
            raise ValueError("options empty")
        if center is None or len(options) == 1:
            return self.rng.choice(options)
        cx, cy = center
        weights: list[float] = []
        for x, y in options:
            dist = max(abs(x - cx), abs(y - cy))
            weights.append(1.0 + dist * dist)
        total = sum(weights)
        pick = self.rng.random() * total
        acc = 0.0
        for pos, w in zip(options, weights):
            acc += w
            if pick <= acc:
                return pos
        return options[-1]

    def _wolf_threat_positions(self) -> list[tuple[int, int]]:
        threats: list[tuple[int, int]] = []
        for pack in self.wolf_packs:
            if pack.kind != AnimalKind.WOLF:
                continue
            threats.append((pack.x, pack.y))
            threats.extend((m.x, m.y) for m in pack.members)
        return threats

    def _bio_at(
        self,
        biodiversity: list[list[float]] | None,
        x: int,
        y: int,
    ) -> float:
        if not biodiversity:
            return 0.0
        rows = len(biodiversity)
        cols = len(biodiversity[0]) if rows else 0
        if 0 <= y < rows and 0 <= x < cols:
            return float(biodiversity[y][x])
        return 0.0

    def _pick_weighted_step(
        self,
        world: World,
        options: list[tuple[int, int]],
        *,
        biodiversity: list[list[float]] | None = None,
        bio_weight: float = 0.0,
        away_disturbance_weight: float = 0.0,
        toward: tuple[int, int] | None = None,
        toward_weight: float = 0.0,
        away_center: tuple[float, float] | None = None,
        away_center_weight: float = 0.0,
    ) -> tuple[int, int]:
        """Weighted neighbour pick for soft movement biases."""
        if not options:
            raise ValueError("options empty")
        if len(options) == 1:
            return options[0]
        weights: list[float] = []
        for x, y in options:
            w = 1.0
            if bio_weight > 0.0:
                w += bio_weight * self._bio_at(biodiversity, x, y)
            if away_disturbance_weight > 0.0:
                dist = effective_disturbance_at(world, x, y)
                w += away_disturbance_weight * (1.0 - float(dist))
            if toward is not None and toward_weight > 0.0:
                d = max(abs(x - toward[0]), abs(y - toward[1]))
                w += toward_weight / (1.0 + float(d))
            if away_center is not None and away_center_weight > 0.0:
                d = max(abs(x - away_center[0]), abs(y - away_center[1]))
                w += away_center_weight * (1.0 + d * d)
            weights.append(max(0.01, w))
        total = sum(weights)
        pick = self.rng.random() * total
        acc = 0.0
        for pos, w in zip(options, weights):
            acc += w
            if pick <= acc:
                return pos
        return options[-1]

    def _animal_roam_pick(
        self,
        world: World,
        options: list[tuple[int, int]],
        *,
        biodiversity: list[list[float]] | None = None,
        warm_center: tuple[float, float] | None = None,
    ) -> tuple[int, int]:
        return self._pick_weighted_step(
            world,
            options,
            biodiversity=biodiversity,
            bio_weight=_bal_weight("ANIMAL_WEIGHT_BIODIVERSITY", 1.0),
            away_disturbance_weight=_bal_weight(
                "ANIMAL_WEIGHT_AWAY_DISTURBANCE", 1.0
            ),
            away_center=warm_center,
            away_center_weight=1.0 if warm_center is not None else 0.0,
        )

    def _place_animal(
        self,
        world: World,
        animal: Animal,
        nx: int,
        ny: int,
        occupied: set[tuple[int, int]],
    ) -> bool:
        if not world.can_step(animal.x, animal.y, nx, ny):
            self._clear_animal_path(animal)
            return False
        occupied.discard((animal.x, animal.y))
        # Logical occupancy remains cell-based, but animals need not stand on
        # the cell centre. Keep a margin so their derived cell stays stable.
        target = self._subcell_target(nx, ny)
        note_cell_step(animal, nx, ny, world_target=target)
        occupied.add((nx, ny))
        return True

    def _subcell_target(self, x: int, y: int) -> tuple[float, float]:
        """A free position inside a logical habitat/resource cell."""
        return (
            float(x) + self.rng.uniform(-0.36, 0.36),
            float(y) + self.rng.uniform(-0.36, 0.36),
        )

    @staticmethod
    def _arm_move(animal: Animal, move_interval: int) -> None:
        animal.move_cooldown = move_interval
        arm_cell_step_visual(animal, move_interval)

    def _clear_animal_path(self, animal: Animal) -> None:
        animal._path_cache = None
        animal._path_goal = None

    def _step_toward(
        self,
        world: World,
        animal: Animal,
        tx: int,
        ty: int,
        occupied: set[tuple[int, int]],
    ) -> bool:
        """Take one walkable step toward (tx, ty). Uses cached BFS when greedy is stuck."""
        if (animal.x, animal.y) == (tx, ty):
            self._clear_animal_path(animal)
            return False

        cur_d = max(abs(animal.x - tx), abs(animal.y - ty))
        improving: list[tuple[int, int]] = []
        sideways: list[tuple[int, int]] = []
        for ny, nx in world.neighbourhood(animal.x, animal.y, radius=1):
            if (nx, ny) == (animal.x, animal.y):
                continue
            if not world.can_step(animal.x, animal.y, nx, ny) or (nx, ny) in occupied:
                continue
            d = max(abs(nx - tx), abs(ny - ty))
            if d < cur_d:
                improving.append((nx, ny))
            elif d == cur_d:
                sideways.append((nx, ny))

        choice: tuple[int, int] | None = None
        if improving:
            choice = self.rng.choice(improving)
            self._clear_animal_path(animal)
        else:
            choice = self._cached_path_step(world, animal, tx, ty, occupied)
            if choice is None and sideways:
                choice = self.rng.choice(sideways)

        if choice is None:
            return False
        self._place_animal(world, animal, choice[0], choice[1], occupied)
        return True

    def _step_flee(
        self,
        world: World,
        animal: Animal,
        threat: tuple[int, int],
        occupied: set[tuple[int, int]],
    ) -> bool:
        """One panic step that maximizes Chebyshev distance from ``threat``."""
        self._clear_animal_path(animal)
        tx, ty = threat
        cur_d = max(abs(animal.x - tx), abs(animal.y - ty))
        best: list[tuple[int, int]] = []
        best_d = cur_d
        for ny, nx in world.neighbourhood(animal.x, animal.y, radius=1):
            if (nx, ny) == (animal.x, animal.y):
                continue
            if not world.can_step(animal.x, animal.y, nx, ny) or (nx, ny) in occupied:
                continue
            d = max(abs(nx - tx), abs(ny - ty))
            if d > best_d:
                best_d = d
                best = [(nx, ny)]
            elif d == best_d and d > cur_d:
                best.append((nx, ny))
        if not best:
            # No improving step — still try any free neighbour away-ish.
            options = [
                (nx, ny)
                for ny, nx in world.neighbourhood(animal.x, animal.y, radius=1)
                if (nx, ny) != (animal.x, animal.y)
                and world.can_step(animal.x, animal.y, nx, ny)
                and (nx, ny) not in occupied
            ]
            if not options:
                return False
            choice = self._weighted_away_choice(
                options, (float(tx), float(ty))
            )
        else:
            choice = self.rng.choice(best)
        self._place_animal(world, animal, choice[0], choice[1], occupied)
        return True

    def _nearest_hunter_threat(
        self,
        animal: Animal,
        threats: list[tuple[int, int]] | None,
        radius: int,
    ) -> tuple[int, int] | None:
        """Closest hunter/player within Chebyshev ``radius``, or None."""
        if not threats or radius <= 0:
            return None
        best: tuple[int, int] | None = None
        best_d = radius
        ax, ay = animal.x, animal.y
        for tx, ty in threats:
            d = max(abs(ax - tx), abs(ay - ty))
            if d <= best_d:
                best_d = d
                best = (tx, ty)
        return best

    @staticmethod
    def _nearby_crop(world: World, animal: Animal, radius: int = 3) -> tuple[int, int] | None:
        # Keep a live target until it is eaten or disappears. Re-selecting the
        # nearest tile every step makes animals orbit between dense crop rows.
        if animal.crop_target is not None:
            current = world.get_cell(*animal.crop_target)
            if current is not None and current.feature == FeatureType.CROP_HERB:
                return animal.crop_target
        crops: list[tuple[int, int, int]] = []
        for ny, nx in world.neighbourhood(animal.x, animal.y, radius=radius):
            cell = world.get_cell(nx, ny)
            if cell is None or cell.feature != FeatureType.CROP_HERB:
                continue
            dist = max(abs(nx - animal.x), abs(ny - animal.y))
            crops.append((dist, nx, ny))
        if not crops:
            return None
        _, x, y = min(crops)
        return x, y

    def _seek_or_eat_crop(
        self,
        world: World,
        animal: Animal,
        day: float,
        occupied: set[tuple[int, int]],
        move_interval: int,
    ) -> bool:
        """Attract deer/boar to nearby crops; eat after occupying one for a day."""
        if animal.kind not in (AnimalKind.DEER, AnimalKind.BOAR):
            animal.crop_target = None
            animal.crop_arrived_day = None
            return False
        target = self._nearby_crop(world, animal, radius=3)
        if target is None:
            animal.crop_target = None
            animal.crop_arrived_day = None
            return False
        animal.crop_target = target
        if (animal.x, animal.y) != target:
            animal.crop_arrived_day = None
            self._step_toward(world, animal, target[0], target[1], occupied)
            if (animal.x, animal.y) == target:
                animal.crop_arrived_day = float(day)
                animal.activity = "Eating crop"
            else:
                animal.activity = "Seeking crops"
        else:
            if animal.crop_arrived_day is None:
                animal.crop_arrived_day = float(day)
            else:
                elapsed = float(day) - animal.crop_arrived_day
                if elapsed < 0.0:
                    from seasons import YEAR_DAYS

                    elapsed += YEAR_DAYS
                if elapsed < 1.0:
                    animal.activity = "Eating crop"
                    self._arm_move(animal, move_interval)
                    return True
                cell = world.get_cell(*target)
                if cell is not None and cell.feature == FeatureType.CROP_HERB:
                    cell.feature = FeatureType.NONE
                    cell.crop_kind = None
                    cell.growth_ticks = 0
                    world.mark_terrain_dirty(*target)
                animal.crop_target = None
                animal.crop_arrived_day = None
                animal.activity = "Ate crop"
        self._arm_move(animal, move_interval)
        return True

    def _step_along_path(
        self,
        world: World,
        animal: Animal,
        tx: int,
        ty: int,
        occupied: set[tuple[int, int]],
    ) -> bool:
        """One step along a cached BFS path — used for migration so detours are not undone."""
        if (animal.x, animal.y) == (tx, ty):
            self._clear_animal_path(animal)
            return False
        nxt = self._cached_path_step(world, animal, tx, ty, occupied)
        if nxt is None:
            # Fallback: greedy improve only (no sideways undo of a detour).
            cur_d = max(abs(animal.x - tx), abs(animal.y - ty))
            improving = [
                (nx, ny)
                for ny, nx in world.neighbourhood(animal.x, animal.y, radius=1)
                if (nx, ny) != (animal.x, animal.y)
                and world.can_step(animal.x, animal.y, nx, ny)
                and (nx, ny) not in occupied
                and max(abs(nx - tx), abs(ny - ty)) < cur_d
            ]
            if not improving:
                return False
            nxt = self.rng.choice(improving)
        self._place_animal(world, animal, nxt[0], nxt[1], occupied)
        return True

    def _cached_path_step(
        self,
        world: World,
        animal: Animal,
        tx: int,
        ty: int,
        occupied: set[tuple[int, int]],
    ) -> tuple[int, int] | None:
        """Pop the next step from a cached path, recomputing with capped BFS on miss."""
        goal = (tx, ty)
        cache = animal._path_cache
        if cache and animal._path_goal == goal:
            nxt = cache[0]
            if (
                max(abs(nxt[0] - animal.x), abs(nxt[1] - animal.y)) <= 1
                and world.can_step(animal.x, animal.y, *nxt)
                and (nxt == goal or nxt not in occupied)
            ):
                animal._path_cache = cache[1:] or None
                if not animal._path_cache:
                    animal._path_goal = None
                return nxt
        path = self._bfs_path(
            world, animal.x, animal.y, tx, ty, occupied
        )
        if not path:
            self._clear_animal_path(animal)
            return None
        animal._path_cache = path[1:] or None
        animal._path_goal = goal if animal._path_cache else None
        return path[0]

    def _bfs_path(
        self,
        world: World,
        sx: int,
        sy: int,
        tx: int,
        ty: int,
        occupied: set[tuple[int, int]],
        *,
        limit: int | None = None,
    ) -> list[tuple[int, int]] | None:
        """Shortest cardinal path from (sx,sy) to (tx,ty), excluding start."""
        from collections import deque

        start = (sx, sy)
        goal = (tx, ty)
        if start == goal:
            return []
        blocked = set(occupied)
        blocked.discard(start)
        blocked.discard(goal)
        straight = abs(tx - sx) + abs(ty - sy)
        # Cap failed searches: don't flood the whole map when goal is cut off.
        max_nodes = limit if limit is not None else min(
            PATH_FIND_MAX_NODES,
            max(256, straight * 8 + 128),
            world.rows * world.cols + 8,
        )

        prev: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        queue: deque[tuple[int, int]] = deque([start])
        found = False
        while queue and len(prev) < max_nodes:
            cx, cy = queue.popleft()
            # Prefer axes toward the goal (same idea as world.find_path).
            local: list[tuple[int, int]] = []
            rest: list[tuple[int, int]] = []
            for dx, dy in (
                (0, -1), (0, 1), (-1, 0), (1, 0),
                (-1, -1), (1, -1), (-1, 1), (1, 1),
            ):
                if abs(tx - cx) >= abs(ty - cy):
                    (local if dx != 0 else rest).append((dx, dy))
                else:
                    (local if dy != 0 else rest).append((dx, dy))
            for dx, dy in local + rest:
                nx, ny = cx + dx, cy + dy
                nxt = (nx, ny)
                if nxt in prev:
                    continue
                if nxt != goal and (not world.can_step(cx, cy, nx, ny) or nxt in blocked):
                    continue
                prev[nxt] = (cx, cy)
                if nxt == goal:
                    found = True
                    break
                queue.append(nxt)
            if found:
                break

        if not found or goal not in prev:
            return None

        path: list[tuple[int, int]] = []
        cur: tuple[int, int] | None = goal
        while cur is not None and cur != start:
            path.append(cur)
            cur = prev[cur]
        path.reverse()
        return path

    def _bfs_next_step(
        self,
        world: World,
        sx: int,
        sy: int,
        tx: int,
        ty: int,
        occupied: set[tuple[int, int]],
        *,
        limit: int | None = None,
    ) -> tuple[int, int] | None:
        """First step of a shortest walkable path from (sx,sy) toward (tx,ty)."""
        path = self._bfs_path(world, sx, sy, tx, ty, occupied, limit=limit)
        if not path:
            return None
        return path[0]

    def _patches_with_space(
        self, kind: AnimalKind, *, need: int, exclude_id: int | None
    ) -> list[Habitat]:
        out: list[Habitat] = []
        for hab in self._habitats_for(kind):
            if exclude_id is not None and hab.id == exclude_id:
                continue
            if self._cap_for(kind, hab) < MIN_BREEDING_CAPACITY:
                continue
            if not self._breeding_for(kind, hab):
                continue
            if self._room_on_patch(kind, hab.id) >= need:
                out.append(hab)
        return out

    def _nearest_patch_with_space(
        self, kind: AnimalKind, x: int, y: int, *, need: int, exclude_id: int | None
    ) -> Habitat | None:
        best: tuple[int, Habitat] | None = None
        for hab in self._patches_with_space(kind, need=need, exclude_id=exclude_id):
            breed = self._breeding_for(kind, hab)
            if not breed:
                continue
            d = min(max(abs(bx - x), abs(by - y)) for bx, by in breed)
            if best is None or d < best[0]:
                best = (d, hab)
        return best[1] if best is not None else None

    def _home_center(self, animal: Animal) -> tuple[float, float] | None:
        home = self.habitat(animal.migrate_home_id, animal.kind)
        if home is None:
            return None
        return self._breeding_center(animal.kind, home)

    def _try_settle_dispersal(self, animal: Animal, need: int) -> bool:
        """Claim a new patch if standing in its cold roost and it has room."""
        if animal.migrate_home_id is None or animal.patch_id is not None:
            return False
        for hab in self._habitats_for(animal.kind):
            if hab.id == animal.migrate_home_id:
                continue
            if self._cap_for(animal.kind, hab) < MIN_BREEDING_CAPACITY:
                continue
            if not self._breeding_for(animal.kind, hab):
                continue
            if self._room_on_patch(animal.kind, hab.id) < need:
                continue
            cold = self._cold_roaming_for(animal.kind, hab)
            if (animal.x, animal.y) in cold:
                animal.patch_id = hab.id
                animal.migrate_home_id = None
                animal.migrate_target = None
                animal.retreat_target = None
                return True
        return False

    def _autumn_seek_target(
        self, animal: Animal, *, need: int
    ) -> tuple[int, int] | None:
        dest = self._nearest_patch_with_space(
            animal.kind,
            animal.x,
            animal.y,
            need=need,
            exclude_id=animal.migrate_home_id,
        )
        if dest is None:
            return None
        cold = self._cold_roaming_for(animal.kind, dest)
        if not cold:
            return None
        return min(
            cold,
            key=lambda p: max(abs(p[0] - animal.x), abs(p[1] - animal.y)),
        )

    def _step_dispersal(
        self,
        world: World,
        animal: Animal,
        occupied: set[tuple[int, int]],
        move_interval: int,
        moved: set[int],
        season: Season,
    ) -> bool:
        """Dispersing pair: explore away from home, or autumn-seek a patch with space."""
        if animal.migrate_home_id is None:
            return False
        mate = self._mate_of(animal)
        # How many slots we still need to place (self + unsettle mate).
        if mate is not None and mate.patch_id is None:
            need = 2
        else:
            need = 1
        cold_season = season in (Season.AUTUMN, Season.WINTER)

        if mate is not None:
            occupied.discard((mate.x, mate.y))

        # If the partner already claimed a patch, walk there.
        if mate is not None and mate.patch_id is not None:
            dest = self.habitat(mate.patch_id, animal.kind)
            if dest is not None:
                cold = self._cold_roaming_for(animal.kind, dest)
                if cold:
                    animal.migrate_target = min(
                        cold,
                        key=lambda p: max(abs(p[0] - animal.x), abs(p[1] - animal.y)),
                    )
                    self._step_along_path(
                        world,
                        animal,
                        animal.migrate_target[0],
                        animal.migrate_target[1],
                        occupied,
                    )
            self._try_settle_dispersal(animal, need=1)
            mate_hab = self.habitat(mate.patch_id, animal.kind)
            if (
                animal.patch_id is None
                and mate.patch_id is not None
                and mate_hab is not None
                and (animal.x, animal.y)
                in self._cold_roaming_for(animal.kind, mate_hab)
                and self._room_on_patch(animal.kind, mate.patch_id) >= 1
            ):
                animal.patch_id = mate.patch_id
                animal.migrate_home_id = None
                animal.migrate_target = None
            self._arm_move(animal, move_interval)
            moved.add(animal.id)
            return True

        if cold_season:
            animal.migrate_target = self._autumn_seek_target(animal, need=need)
            if animal.migrate_target is not None:
                self._step_along_path(
                    world,
                    animal,
                    animal.migrate_target[0],
                    animal.migrate_target[1],
                    occupied,
                )
            else:
                self._step_explore_away(world, animal, occupied)
        else:
            animal.migrate_target = None
            self._step_explore_away(world, animal, occupied)

        if mate is not None and (mate.x, mate.y) != (animal.x, animal.y):
            occupied.add((mate.x, mate.y))

        settled = self._try_settle_dispersal(animal, need=need)
        self._arm_move(animal, move_interval)
        moved.add(animal.id)

        if mate is not None and mate.id not in moved:
            mate.migrate_home_id = (
                animal.migrate_home_id
                if animal.migrate_home_id is not None
                else mate.migrate_home_id
            )
            if settled and animal.patch_id is not None:
                dest = self.habitat(animal.patch_id, animal.kind)
                if dest is not None:
                    cold = self._cold_roaming_for(mate.kind, dest)
                    if cold:
                        mate.migrate_target = min(
                            cold,
                            key=lambda p: max(
                                abs(p[0] - mate.x), abs(p[1] - mate.y)
                            ),
                        )
            elif animal.migrate_target is not None:
                mate.migrate_target = animal.migrate_target

            occupied.discard((animal.x, animal.y))
            if max(abs(mate.x - animal.x), abs(mate.y - animal.y)) > 1:
                self._step_along_path(world, mate, animal.x, animal.y, occupied)
            elif mate.migrate_target is not None:
                self._step_along_path(
                    world,
                    mate,
                    mate.migrate_target[0],
                    mate.migrate_target[1],
                    occupied,
                )
            else:
                self._step_explore_away(world, mate, occupied)
            occupied.add((animal.x, animal.y))
            if (mate.x, mate.y) != (animal.x, animal.y):
                occupied.add((mate.x, mate.y))

            if animal.patch_id is not None:
                if self._try_settle_dispersal(mate, need=1):
                    pass
                else:
                    claimed = self.habitat(animal.patch_id, mate.kind)
                    if (
                        claimed is not None
                        and (mate.x, mate.y)
                        in self._cold_roaming_for(mate.kind, claimed)
                        and self._room_on_patch(mate.kind, animal.patch_id) >= 1
                    ):
                        mate.patch_id = animal.patch_id
                        mate.migrate_home_id = None
                        mate.migrate_target = None
            else:
                self._try_settle_dispersal(mate, need=need)
            self._arm_move(mate, move_interval)
            moved.add(mate.id)
        return True

    def _step_explore_away(
        self,
        world: World,
        animal: Animal,
        occupied: set[tuple[int, int]],
    ) -> None:
        """One walkable step, weighted away from the home breeding centre."""
        center = self._home_center(animal)
        opts = [
            (nx, ny)
            for ny, nx in world.neighbourhood(animal.x, animal.y, radius=1)
            if (nx, ny) != (animal.x, animal.y)
            and world.can_step(animal.x, animal.y, nx, ny)
            and (nx, ny) not in occupied
        ]
        if not opts:
            return
        dest = self._weighted_away_choice(opts, center)
        self._place_animal(world, animal, dest[0], dest[1], occupied)

    def _move_pair_away(
        self,
        world: World,
        a: Animal,
        b: Animal,
        hab: Habitat,
        roam: set[tuple[int, int]],
        occupied: set[tuple[int, int]],
        move_interval: int,
        *,
        biodiversity: list[list[float]] | None = None,
    ) -> None:
        """Step a mating pair one tile, biased by warm-season spread + balance weights."""
        center = self._breeding_center(a.kind, hab)

        def _adjacent_in_roam(x: int, y: int) -> list[tuple[int, int]]:
            return [
                (nx, ny)
                for ny, nx in world.neighbourhood(x, y, radius=1)
                if (nx, ny) != (x, y)
                and (nx, ny) in roam
                and (nx, ny) not in occupied
            ]

        lead_opts = _adjacent_in_roam(a.x, a.y)
        if not lead_opts:
            # Outside roam: one step toward nearest roam tile (never teleport).
            if (a.x, a.y) not in roam and roam:
                nearest = min(
                    roam, key=lambda p: max(abs(p[0] - a.x), abs(p[1] - a.y))
                )
                self._step_toward(world, a, nearest[0], nearest[1], occupied)
        else:
            dest = self._animal_roam_pick(
                world, lead_opts, biodiversity=biodiversity, warm_center=center
            )
            self._place_animal(world, a, dest[0], dest[1], occupied)

        # Mate stays adjacent: step toward leader first if separated.
        if max(abs(b.x - a.x), abs(b.y - a.y)) > 1:
            self._step_toward(world, b, a.x, a.y, occupied)
        else:
            mate_opts = [
                (nx, ny)
                for ny, nx in world.neighbourhood(b.x, b.y, radius=1)
                if (nx, ny) != (b.x, b.y)
                and (nx, ny) not in occupied
                and world.can_step(b.x, b.y, nx, ny)
                and max(abs(nx - a.x), abs(ny - a.y)) <= 1
            ]
            in_roam = [p for p in mate_opts if p in roam]
            pool = in_roam or mate_opts
            if pool:
                mdest = self._animal_roam_pick(
                    world, pool, biodiversity=biodiversity, warm_center=center
                )
                self._place_animal(world, b, mdest[0], mdest[1], occupied)

        self._arm_move(a, move_interval)
        self._arm_move(b, move_interval)

    def _move_animals(
        self,
        world: World,
        day: float,
        season: Season,
        *,
        hunter_threats: list[tuple[int, int]] | None = None,
        flee_interval: int | None = None,
        biodiversity: list[list[float]] | None = None,
    ) -> None:
        slow = 1 + int(2 * freeze_amount(day)) if animals_slow(day) else 1
        move_interval = animal_roam_interval() * slow
        flee_iv = max(
            4,
            int(
                flee_interval
                if flee_interval is not None
                else animal_flee_interval()
            ),
        )
        occupied = self._occupied()
        cold_season = season in (Season.AUTUMN, Season.WINTER)
        warm_season = season in (Season.SPRING, Season.SUMMER)
        moved: set[int] = set()
        prey_threats = list(hunter_threats or []) + self._wolf_threat_positions()

        for animal in self.animals:
            if animal.id in moved:
                continue
            # Tutorial/set-piece movement owns both the logical step and its
            # render cooldown. Normal roaming resumes when this marker clears.
            if getattr(animal, "_scenario_controlled", False):
                continue
            if animal.kind in BIRD_KINDS:
                if animal.move_cooldown > 0:
                    animal.move_cooldown -= 1
                continue
            # Once logically on its chosen crop, hold the animal exactly on that
            # square before cooldown/roaming logic. A nearby villager/player/wolf
            # still breaks the hold immediately and drives it away.
            on_crop_target = (
                animal.kind in (AnimalKind.DEER, AnimalKind.BOAR)
                and animal.crop_target == (animal.x, animal.y)
            )
            if on_crop_target:
                crop_cell = world.get_cell(animal.x, animal.y)
                if crop_cell is not None and crop_cell.feature == FeatureType.CROP_HERB:
                    threat = self._nearest_hunter_threat(
                        animal, prey_threats, HUNT_APPROACH_RADIUS
                    )
                    if threat is None:
                        snap_entity_visual(animal)
                        self._seek_or_eat_crop(
                            world, animal, day, occupied, move_interval
                        )
                        moved.add(animal.id)
                        continue
                    self._step_flee(world, animal, threat, occupied)
                    animal.crop_arrived_day = None
                    self._arm_move(animal, flee_iv)
                    moved.add(animal.id)
                    continue
            if animal.move_cooldown > 0:
                animal.move_cooldown -= 1
                continue

            # Hunt panic: deer/boar scatter away from a nearby kill.
            if (
                animal.scare_steps > 0
                and animal.scare_from is not None
                and animal.kind in FOREST_KINDS
            ):
                self._step_flee(world, animal, animal.scare_from, occupied)
                animal.scare_steps -= 1
                if animal.scare_steps <= 0:
                    animal.scare_from = None
                    animal.scare_steps = 0
                self._arm_move(animal, flee_iv)
                moved.add(animal.id)
                continue

            # Flee villagers / player / wolves.
            if animal.kind in (AnimalKind.DEER, AnimalKind.BOAR):
                threat = self._nearest_hunter_threat(
                    animal, prey_threats, HUNT_APPROACH_RADIUS
                )
                if threat is not None:
                    self._step_flee(world, animal, threat, occupied)
                    animal.retreat_target = None
                    self._arm_move(animal, flee_iv)
                    moved.add(animal.id)
                    continue

                # Crops attract nearby animals, but only after villager/player/wolf
                # fear has had the opportunity to drive them away.
                if self._seek_or_eat_crop(
                    world, animal, day, occupied, move_interval
                ):
                    moved.add(animal.id)
                    continue

            # Dispersing pair: explore away from home / autumn-seek space.
            if animal.migrate_home_id is not None and animal.patch_id is None:
                self._step_dispersal(
                    world, animal, occupied, move_interval, moved, season
                )
                continue

            if animal.retreat_target is not None:
                tx, ty = animal.retreat_target
                hab = self.habitat(animal.patch_id, animal.kind)
                cold = (
                    self._cold_roaming_for(animal.kind, hab)
                    if hab is not None
                    else set()
                )
                if (animal.x, animal.y) in cold or (animal.x, animal.y) == (tx, ty):
                    animal.retreat_target = None
                else:
                    self._step_toward(world, animal, tx, ty, occupied)
                    if animal.patch_id is None and animal.migrate_home_id is None:
                        near = self._nearest_breeding_habitat(
                            animal.kind, animal.x, animal.y
                        )
                        if near is not None:
                            cold_n = self._cold_roaming_for(animal.kind, near)
                            if (animal.x, animal.y) in cold_n:
                                animal.patch_id = near.id
                    self._arm_move(animal, move_interval)
                    moved.add(animal.id)
                    continue

            if animal.patch_id is None:
                # True orphans (not dispersing): walk to nearest breeding.
                target = self._nearest_breeding_tile(animal.kind, animal.x, animal.y)
                if target is not None:
                    self._step_toward(world, animal, target[0], target[1], occupied)
                    near = self._nearest_breeding_habitat(
                        animal.kind, animal.x, animal.y
                    )
                    if near is not None and (animal.x, animal.y) in self._cold_roaming_for(
                        animal.kind, near
                    ):
                        animal.patch_id = near.id
                        animal.retreat_target = None
                self._arm_move(animal, move_interval)
                moved.add(animal.id)
                continue

            hab = self.habitat(animal.patch_id, animal.kind)
            if hab is None:
                animal.patch_id = None
                self._arm_move(animal, move_interval)
                moved.add(animal.id)
                continue

            roam = self._roaming_for(animal.kind, hab, season)
            cold = self._cold_roaming_for(animal.kind, hab)

            if cold_season and (animal.x, animal.y) not in cold:
                if animal.retreat_target is None:
                    animal.retreat_target = self._nearest_breeding_tile(
                        animal.kind, animal.x, animal.y
                    )
                if animal.retreat_target is not None:
                    self._step_toward(
                        world,
                        animal,
                        animal.retreat_target[0],
                        animal.retreat_target[1],
                        occupied,
                    )
                self._arm_move(animal, move_interval)
                moved.add(animal.id)
                continue

            if not roam:
                self._arm_move(animal, move_interval)
                moved.add(animal.id)
                continue

            mate = self._mate_of(animal) if warm_season else None
            if (
                mate is not None
                and mate.id not in moved
                and mate.move_cooldown <= 0
                and mate.patch_id == animal.patch_id
                and mate.migrate_home_id is None
            ):
                self._move_pair_away(
                    world,
                    animal,
                    mate,
                    hab,
                    roam,
                    occupied,
                    move_interval,
                    biodiversity=biodiversity,
                )
                moved.add(animal.id)
                moved.add(mate.id)
                continue

            neighbours = [
                (nx, ny)
                for ny, nx in world.neighbourhood(animal.x, animal.y, radius=1)
                if (nx, ny) != (animal.x, animal.y)
                and (nx, ny) in roam
                and (nx, ny) not in occupied
                and world.can_step(animal.x, animal.y, nx, ny)
            ]
            if neighbours:
                center = (
                    self._breeding_center(animal.kind, hab) if warm_season else None
                )
                dest = self._animal_roam_pick(
                    world,
                    neighbours,
                    biodiversity=biodiversity,
                    warm_center=center,
                )
                occupied.discard((animal.x, animal.y))
                self._place_animal(world, animal, dest[0], dest[1], occupied)
            elif (animal.x, animal.y) not in roam:
                nearest = min(
                    roam, key=lambda p: max(abs(p[0] - animal.x), abs(p[1] - animal.y))
                )
                self._step_toward(world, animal, nearest[0], nearest[1], occupied)
            self._arm_move(animal, move_interval)
            moved.add(animal.id)

    def _adjacent_wild_crops(self, world: World, x: int, y: int) -> list[tuple[int, int]]:
        found: list[tuple[int, int]] = []
        for ny, nx in world.neighbourhood(x, y, radius=1):
            if (nx, ny) == (x, y):
                continue
            cell = world.cells[ny][nx]
            if cell.feature in (FeatureType.WILD_CROP, FeatureType.HERB):
                found.append((nx, ny))
        return found

    def _forage_features(self, kind: AnimalKind) -> tuple[FeatureType, ...]:
        common = (FeatureType.WILD_CROP, FeatureType.HERB)
        if kind == AnimalKind.DEER:
            return (*common, FeatureType.SAPLING)
        if kind == AnimalKind.BOAR:
            return (*common, FeatureType.MUSHROOM)
        return common

    def _habitat_forage(self, world: World, kind: AnimalKind, hab: Habitat) -> float:
        roam = self._cold_roaming_for(kind, hab)
        total = 0.0
        for x, y in roam:
            cell = world.get_cell(x, y)
            if cell is None:
                continue
            if cell.feature in (FeatureType.WILD_CROP, FeatureType.HERB):
                total += 3.0
            elif kind == AnimalKind.DEER and cell.feature == FeatureType.SAPLING:
                total += 4.0
            elif kind == AnimalKind.BOAR and cell.feature == FeatureType.MUSHROOM:
                total += 5.0
            elif kind == AnimalKind.DEER and cell.terrain in (TerrainType.GRASS, TerrainType.MEADOW):
                total += 0.25
            elif kind == AnimalKind.BOAR and cell.terrain == TerrainType.FOREST_FLOOR:
                total += 0.35
        return total

    def _habitat_quality(self, world: World, kind: AnimalKind, hab: Habitat) -> float:
        tiles = self._breeding_for(kind, hab)
        if not tiles:
            return 0.0
        sample = tiles[::max(1, len(tiles) // 32)]
        avg = sum(effective_disturbance_at(world, x, y) for x, y in sample) / len(sample)
        return wildlife_ecology_multiplier(avg)

    def _forage_sufficiency(self, world: World, kind: AnimalKind, hab: Habitat) -> float:
        count = self._count_in_patch(kind, hab.id)
        if count <= 0:
            return 1.0
        default = 6 if kind == AnimalKind.DEER else 5
        key = (
            "WILDLIFE_DEER_FORAGE_PER_ANIMAL"
            if kind == AnimalKind.DEER
            else "WILDLIFE_BOAR_FORAGE_PER_ANIMAL"
        )
        need = _bal_int(key, default, 1) * count
        return max(0.0, min(1.0, self._habitat_forage(world, kind, hab) / need))

    def _birth_count(
        self,
        kind: AnimalKind,
        hab: Habitat,
        ecology: float,
        food: float,
    ) -> int:
        """Return a density- and habitat-sensitive litter size from one to three.

        Total capacity is deliberately recalculated from every current habitat.
        Consequently, restoring or creating habitat raises reproductive potential
        immediately, while a population near the world's supported capacity falls
        back to single births. Local patch capacity remains a hard safety limit.
        """
        local_room = max(
            0,
            self._cap_for(kind, hab) - self._count_in_patch(kind, hab.id),
        )
        if local_room <= 0:
            return 0
        total_cap = sum(self._cap_for(kind, candidate) for candidate in self._habitats_for(kind))
        if total_cap <= 0:
            return 0
        world_room = max(0, total_cap - self.count_kind(kind))
        vacancy = min(1.0, world_room / total_cap)
        health = max(0.0, min(1.0, min(ecology, food)))
        potential = health * vacancy
        births = max(1, min(3, int(potential * 3.0 + 0.999999)))
        return min(births, local_room)

    def _eat_wild_crop(self, world: World, x: int, y: int) -> bool:
        cell = world.get_cell(x, y)
        if cell is None or cell.feature not in (
            FeatureType.WILD_CROP, FeatureType.HERB, FeatureType.MUSHROOM,
            FeatureType.SAPLING,
        ):
            return False
        cell.feature = FeatureType.NONE
        cell.crop_kind = None
        cell.tree_species = None
        cell.tree_age_years = 0
        cell.deposit = 0
        cell.growth_ticks = 0
        return True

    def _try_spawn_in_patch(
        self,
        kind: AnimalKind,
        hab: Habitat,
        occupied: set[tuple[int, int]],
    ) -> bool:
        """Spawn one offspring in this patch only; no-op at capacity."""
        cap = self._cap_for(kind, hab)
        if cap <= 0 or self._count_in_patch(kind, hab.id) >= cap:
            return False
        roam = self._cold_roaming_for(kind, hab)
        breed = [
            p for p in self._breeding_for(kind, hab) if p not in occupied and p in roam
        ]
        free_roam = [p for p in roam if p not in occupied]
        pool = breed or free_roam
        if not pool:
            return False
        sx, sy = self.rng.choice(pool)
        newborn = Animal(
            id=self.next_id,
            x=sx,
            y=sy,
            kind=kind,
            sex=self._random_sex(),
            patch_id=hab.id,
            move_cooldown=animal_roam_interval(),
        )
        self.next_id += 1
        self.animals.append(newborn)
        self._by_id[newborn.id] = newborn
        occupied.add((sx, sy))
        return True

    def _graze(self, world: World) -> None:
        """Eat adjacent wild crops only — never spawns animals."""
        for animal in list(self.animals):
            if animal.patch_id is None:
                continue
            edible = self._forage_features(animal.kind)
            forage = [
                (nx, ny)
                for ny, nx in world.neighbourhood(animal.x, animal.y, radius=1)
                if (nx, ny) != (animal.x, animal.y)
                and world.cells[ny][nx].feature in edible
            ]
            if not forage:
                continue
            chance = {
                AnimalKind.DEER: _bal_float(
                    "WILDLIFE_DEER_GRAZE_CHANCE", DEER_CROP_EAT_CHANCE
                ),
                AnimalKind.BOAR: _bal_float(
                    "WILDLIFE_BOAR_GRAZE_CHANCE", BOAR_CROP_EAT_CHANCE
                ),
            }.get(animal.kind, 0.0)
            if chance <= 0.0 or self.rng.random() >= chance:
                continue
            if animal.kind == AnimalKind.DEER:
                saplings = [p for p in forage if world.cells[p[1]][p[0]].feature == FeatureType.SAPLING]
                browse = _bal_float("WILDLIFE_DEER_SAPLING_BROWSE_CHANCE", 0.35)
                pool = saplings if saplings and self.rng.random() < browse else [
                    p for p in forage if p not in saplings
                ] or forage
            else:
                mushrooms = [p for p in forage if world.cells[p[1]][p[0]].feature == FeatureType.MUSHROOM]
                pool = mushrooms or forage
            cx, cy = self.rng.choice(pool)
            self._eat_wild_crop(world, cx, cy)

    def _breed(self, world: World) -> None:
        """Mating pairs produce up to three offspring in their current patch."""
        occupied = self._occupied()
        seen: set[frozenset[int]] = set()
        for animal in list(self.animals):
            mate = self._mate_of(animal)
            if mate is None:
                continue
            key = frozenset({animal.id, mate.id})
            if key in seen:
                continue
            seen.add(key)
            # Process each pair once (from the lower id).
            if animal.id > mate.id:
                continue
            if animal.age_days < YEAR_DAYS or mate.age_days < YEAR_DAYS:
                continue
            if animal.patch_id is None:
                continue
            hab = self.habitat(animal.patch_id, animal.kind)
            if hab is None:
                continue
            cap = self._cap_for(animal.kind, hab)
            if self._count_in_patch(animal.kind, hab.id) >= cap:
                continue
            ecology = self._habitat_quality(world, animal.kind, hab)
            food = self._forage_sufficiency(world, animal.kind, hab)
            density = max(0.0, 1.0 - self._count_in_patch(animal.kind, hab.id) / max(1, cap))
            from balance_config import active_balance

            breed_chance = active_balance().get_float("WILDLIFE_BREED_CHANCE")
            if self.rng.random() >= breed_chance * ecology * food * density:
                continue
            births = self._birth_count(animal.kind, hab, ecology, food)
            for _ in range(births):
                if not self._try_spawn_in_patch(animal.kind, hab, occupied):
                    break

    def _cull_excess(self) -> None:
        self._index_animals()
        if not self.habitats and not self.open_habitats:
            for animal in self.animals:
                animal.patch_id = None
                self._clear_mate(animal)
            return
        for kind in FOREST_KINDS:
            for hab in self.habitats:
                self._cull_kind_on_habitat(kind, hab)

    def _annual_mortality(self, world: World) -> None:
        """Age forest wildlife and apply food-, habitat-, and age-driven deaths."""
        from seasons import YEAR_DAYS

        self._index_animals()
        survivors: list[Animal] = []
        base = _bal_float("WILDLIFE_ANNUAL_MORTALITY", 0.06)
        starvation = _bal_float("WILDLIFE_STARVATION_MORTALITY", 0.45)
        for animal in self.animals:
            animal.age_days += YEAR_DAYS
            if animal.kind not in FOREST_KINDS:
                survivors.append(animal)
                continue
            hab = self.habitat(animal.patch_id, animal.kind)
            if hab is None:
                food = 0.0
                quality = 0.0
            else:
                food = self._forage_sufficiency(world, animal.kind, hab)
                quality = self._habitat_quality(world, animal.kind, hab)
            max_age = _bal_int(
                "WILDLIFE_DEER_MAX_AGE_YEARS" if animal.kind == AnimalKind.DEER
                else "WILDLIFE_BOAR_MAX_AGE_YEARS",
                12 if animal.kind == AnimalKind.DEER else 10,
                2,
            )
            age_years = animal.age_days / YEAR_DAYS
            old_age = max(0.0, (age_years - max_age + 1.0) * 0.25)
            risk = min(0.98, base + starvation * (1.0 - food) + base * (1.0 - quality) + old_age)
            if self.rng.random() < risk:
                self._clear_mate(animal)
                continue
            survivors.append(animal)
        self.animals = survivors
        self._index_animals()

    def _cull_kind_on_habitat(self, kind: AnimalKind, hab: Habitat) -> None:
        group = [
            a for a in self.animals if a.kind == kind and a.patch_id == hab.id
        ]
        cap = self._cap_for(kind, hab)
        if cap <= 0 or not self._breeding_for(kind, hab):
            for a in group:
                a.patch_id = None
                self._clear_mate(a)
            return
        while len(group) > cap:
            victim = group.pop()
            if victim in self.animals:
                self._clear_mate(victim)
                self.animals.remove(victim)
                self._by_id.pop(victim.id, None)

    def _migrate(self) -> None:
        """Mating pairs leave home at most once per year; then roam until spring."""
        self._index_animals()
        started: set[int] = set()
        for animal in list(self.animals):
            if animal.id in started or animal.patch_id is None:
                continue
            if animal.migrate_home_id is not None or animal.migrated_this_year:
                continue
            if len(self._habitats_for(animal.kind)) < 2:
                continue
            mate = self._mate_of(animal)
            if mate is None or mate.id in started:
                continue
            if mate.migrate_home_id is not None or mate.patch_id != animal.patch_id:
                continue
            if mate.migrated_this_year:
                continue
            if animal.id > mate.id:
                continue
            if self.rng.random() >= _bal_float(
                "WILDLIFE_MIGRATION_CHANCE", ANIMAL_MIGRATION_CHANCE
            ):
                continue
            home_id = animal.patch_id
            # Only leave if some other patch could take the pair.
            if not self._patches_with_space(
                animal.kind, need=2, exclude_id=home_id
            ):
                continue
            for member in (animal, mate):
                member.migrate_home_id = home_id
                member.migrate_target = None
                member.patch_id = None
                member.retreat_target = None
                member.migrated_this_year = True
                started.add(member.id)

    # ------------------------------------------------------------------
    # Bee / rabbit colonies
    # ------------------------------------------------------------------
    def _spawn_colony(
        self, kind: AnimalKind, hab: OpenHabitat, *, level: int = 1
    ) -> Colony | None:
        if not hab.nest_tiles or not self._allows_colony(kind, hab):
            return None
        if self._colony_on_habitat(kind, hab.id) is not None:
            return None
        if kind in COLONY_KINDS:
            max_lv = colony_max_level_for_forage(kind, len(hab.forage_tiles))
            if max_lv < 1:
                return None
            level = min(int(level), max_lv)
        occupied = {(c.x, c.y) for c in self.colonies}
        nest = [p for p in hab.nest_tiles if p not in occupied] or list(hab.nest_tiles)
        nx, ny = self.rng.choice(nest)
        colony = Colony(
            id=self.next_colony_id,
            kind=kind,
            x=nx,
            y=ny,
            level=max(1, min(COLONY_LEVEL_MAX, level)),
            habitat_id=hab.id,
        )
        self.next_colony_id += 1
        self._sync_colony_members(colony, hab)
        self.colonies.append(colony)
        return colony

    def _colony_habitat(self, colony: Colony) -> OpenHabitat | None:
        if colony.habitat_id is None:
            return None
        if 0 <= colony.habitat_id < len(self.open_habitats):
            return self.open_habitats[colony.habitat_id]
        return None

    def _colony_has_food(self, world: World, colony: Colony) -> bool:
        hab = self._colony_habitat(colony)
        if hab is None:
            return False
        food_features = (
            FeatureType.HERB,
            FeatureType.WILD_CROP,
            FeatureType.CROP_HERB,
            FeatureType.BERRY_BUSH,
            FeatureType.FIELD,
        )
        for x, y in hab.forage_tiles:
            cell = world.get_cell(x, y)
            if cell is None:
                continue
            if cell.feature in food_features:
                return True
            if colony.kind == AnimalKind.BEE and cell.terrain == TerrainType.MEADOW:
                return True
            if colony.kind == AnimalKind.RABBIT and cell.terrain in (
                TerrainType.MEADOW,
                TerrainType.GRASS,
            ):
                return True
            if colony.kind == AnimalKind.VOLE and cell.terrain in (
                TerrainType.MEADOW,
                TerrainType.GRASS,
                TerrainType.RIPARIAN,
            ):
                return True
            if colony.kind == AnimalKind.FROG and cell.terrain == TerrainType.RIPARIAN:
                return True
        return False

    def _sync_colony_members(self, colony: Colony, hab: OpenHabitat | None) -> None:
        want = colony.target_members()
        if len(colony.members) == want:
            return
        roam = set(hab.forage_tiles) if hab is not None else set()
        roam.add((colony.x, colony.y))
        # Prefer tiles near the nest within member radius.
        near = [
            p
            for p in roam
            if max(abs(p[0] - colony.x), abs(p[1] - colony.y)) <= COLONY_MEMBER_RADIUS
        ]
        pool = near or list(roam) or [(colony.x, colony.y)]
        while len(colony.members) < want:
            sx, sy = self.rng.choice(pool)
            colony.members.append(
                ColonyMember(x=sx, y=sy, move_cooldown=animal_roam_interval())
            )
        if len(colony.members) > want:
            colony.members = colony.members[:want]

    def _move_colony_members(
        self,
        world: World,
        day: float,
        *,
        biodiversity: list[list[float]] | None = None,
    ) -> None:
        del day
        occupied = {(a.x, a.y) for a in self.animals}
        occupied.update((c.x, c.y) for c in self.colonies)
        wolf_threats = self._wolf_threat_positions()
        flee_iv = animal_flee_interval()
        for colony in self.colonies:
            hab = self._colony_habitat(colony)
            self._sync_colony_members(colony, hab)
            ready: list[ColonyMember] = []
            for member in colony.members:
                if member.move_cooldown > 0:
                    member.move_cooldown -= 1
                else:
                    ready.append(member)
            if not ready:
                continue
            roam = set(hab.forage_tiles) if hab is not None else {(colony.x, colony.y)}
            roam = {
                p
                for p in roam
                if max(abs(p[0] - colony.x), abs(p[1] - colony.y))
                <= COLONY_MEMBER_RADIUS
            }
            if not roam:
                roam = {(colony.x, colony.y)}
            # Rabbits: hop one tile, then pause. Bees: shorter continuous roam.
            pause = (
                rabbit_pause_interval()
                if colony.kind
                in (AnimalKind.RABBIT, AnimalKind.FROG, AnimalKind.VOLE)
                else animal_roam_interval()
            )
            for member in ready:
                options = [
                    p
                    for p in roam
                    if p not in occupied
                    and max(abs(p[0] - member.x), abs(p[1] - member.y)) <= 1
                    and world.can_step(member.x, member.y, p[0], p[1])
                ]
                if not options:
                    options = [
                        p
                        for p in roam
                        if p not in occupied
                        and world.can_step(member.x, member.y, p[0], p[1])
                    ]
                if options:
                    occupied.discard((member.x, member.y))
                    threat = None
                    if colony.kind == AnimalKind.RABBIT and wolf_threats:
                        best_d = HUNT_APPROACH_RADIUS + 1
                        for tx, ty in wolf_threats:
                            d = max(abs(member.x - tx), abs(member.y - ty))
                            if d < best_d:
                                best_d = d
                                threat = (tx, ty)
                        if best_d > HUNT_APPROACH_RADIUS:
                            threat = None
                    if threat is not None:
                        tx, ty = threat
                        nx, ny = max(
                            options,
                            key=lambda p: max(abs(p[0] - tx), abs(p[1] - ty)),
                        )
                        step_pause = flee_iv
                    else:
                        nx, ny = self._animal_roam_pick(
                            world, options, biodiversity=biodiversity
                        )
                        step_pause = pause
                    if world.can_step(member.x, member.y, nx, ny):
                        note_cell_step(
                            member, nx, ny, world_target=self._subcell_target(nx, ny)
                        )
                        occupied.add((nx, ny))
                else:
                    step_pause = pause
                arm_cell_step_visual(member, step_pause)
                member.move_cooldown = step_pause

    def colony_at(self, x: int, y: int) -> Colony | None:
        for colony in self.colonies:
            if colony.x == x and colony.y == y:
                return colony
        return None

    def colony_by_id(self, colony_id: int) -> Colony | None:
        for colony in self.colonies:
            if colony.id == colony_id:
                return colony
        return None

    def harvest_colony(
        self, colony_id: int, *, kind: AnimalKind | None = None
    ) -> tuple[AnimalKind, int] | None:
        """Drop one colony level; return (kind, yield_amount) or None.

        Rabbits yield meat; bees yield honey. Colony is removed at level 0.
        Sets harvest cooldown so the colony cannot be hit again until it expires.
        """
        colony = self.colony_by_id(colony_id)
        if colony is None or not colony.can_harvest():
            return None
        if kind is not None and colony.kind != kind:
            return None
        if colony.kind in (
            AnimalKind.RABBIT,
            AnimalKind.FROG,
            AnimalKind.VOLE,
        ):
            amount = 1  # actual loot comes from hunter recipe outputs in game.py
        elif colony.kind == AnimalKind.BEE:
            amount = HONEY_PER_BEE_LEVEL
        else:
            return None
        harvested_kind = colony.kind
        colony.level -= 1
        colony.harvest_cooldown = COLONY_HARVEST_COOLDOWN
        if colony.level <= 0:
            self.colonies.remove(colony)
        else:
            colony.clamp_level()
            self._sync_colony_members(colony, self._colony_habitat(colony))
        return harvested_kind, amount

    def _tick_colonies(self, world: World) -> None:
        """Grow colony levels and found new small colonies from level-3 parents."""
        for colony in self.colonies:
            if colony.harvest_cooldown > 0:
                colony.harvest_cooldown -= 1

        # Snap orphans onto a free site or drop them.
        for colony in list(self.colonies):
            hab = self._colony_habitat(colony)
            if hab is None or not self._allows_colony(colony.kind, hab):
                sites = self._empty_colony_sites(colony.kind)
                if not sites:
                    self.colonies.remove(colony)
                    continue
                hab = self.rng.choice(sites)
                colony.habitat_id = hab.id
                colony.x, colony.y = self.rng.choice(hab.nest_tiles)
            self._sync_colony_members(colony, hab)

        self._enforce_colony_forage_caps()

        # Rabbit colonies may nibble nearby wild crops.
        for colony in self.colonies:
            if colony.kind != AnimalKind.RABBIT:
                continue
            if self.rng.random() >= _bal_float(
                "WILDLIFE_RABBIT_GRAZE_CHANCE", COLONY_RABBIT_CROP_EAT_CHANCE
            ):
                continue
            crops = self._adjacent_wild_crops(world, colony.x, colony.y)
            if crops:
                self._eat_wild_crop(world, *self.rng.choice(crops))

        # Level growth, then fission from level-3 colonies with food.
        from balance_config import active_balance

        grow_chance = active_balance().get_float("WILDLIFE_COLONY_GROW_CHANCE")
        split_chance = active_balance().get_float("WILDLIFE_COLONY_SPLIT_CHANCE")
        for colony in list(self.colonies):
            if not self._colony_has_food(world, colony):
                continue
            nest = world.get_cell(colony.x, colony.y)
            ecology = (
                wildlife_ecology_multiplier(
                    effective_disturbance_at(world, colony.x, colony.y)
                )
                if nest is not None
                else 1.0
            )
            if colony.kind in COLONY_KINDS:
                max_lv = colony_max_level_for_forage(
                    colony.kind, self._colony_forage_count(colony)
                )
                if colony.level >= max_lv:
                    continue
            if colony.level < COLONY_LEVEL_MAX and self.rng.random() < grow_chance * ecology:
                colony.level += 1
                colony.clamp_level()
                self._sync_colony_members(colony, self._colony_habitat(colony))

        for colony in list(self.colonies):
            if colony.level != COLONY_SPLIT_LEVEL:
                continue
            if not self._colony_has_food(world, colony):
                continue
            nest = world.get_cell(colony.x, colony.y)
            ecology = (
                wildlife_ecology_multiplier(
                    effective_disturbance_at(world, colony.x, colony.y)
                )
                if nest is not None
                else 1.0
            )
            if self.rng.random() >= split_chance * ecology:
                continue
            sites = self._empty_colony_sites(colony.kind)
            if not sites:
                continue
            # Prefer a nearby empty site.
            sites.sort(
                key=lambda h: min(
                    max(abs(bx - colony.x), abs(by - colony.y))
                    for bx, by in h.nest_tiles
                )
            )
            self._spawn_colony(colony.kind, sites[0], level=1)

    # ------------------------------------------------------------------
    # Wolf / fox packs
    # ------------------------------------------------------------------
    def _pack_max_pop(self, kind: AnimalKind) -> int:
        """Predator carrying capacity supplied by the prey currently on the map.

        A prey unit contributes one predator-place per day that it would feed a
        pack. Prey-derived room is hard-capped by WOLF_MAX_POPULATION /
        FOX_MAX_POPULATION so abundant rabbits cannot flood the map with packs.
        """
        if kind == AnimalKind.FOX:
            from settings import (
                FOX_FEED_FROG_DAYS,
                FOX_FEED_RABBIT_DAYS,
                FOX_FEED_VOLE_DAYS,
                FOX_MAX_POPULATION,
            )

            prey = (
                (AnimalKind.RABBIT, FOX_FEED_RABBIT_DAYS),
                (AnimalKind.FROG, FOX_FEED_FROG_DAYS),
                (AnimalKind.VOLE, FOX_FEED_VOLE_DAYS),
            )
            prey_cap = max(
                0,
                int(
                    sum(
                        c.level * feed_days
                        for c in self.colonies
                        for prey_kind, feed_days in prey
                        if c.kind == prey_kind and c.can_harvest()
                    )
                ),
            )
            hard = max(0, _bal_int("FOX_MAX_POPULATION", FOX_MAX_POPULATION, 0))
            return min(prey_cap, hard) if hard > 0 else prey_cap

        from settings import WOLF_MAX_POPULATION

        animal_food = sum(
            self._wolf_feed_days("boar" if a.kind == AnimalKind.BOAR else "deer")
            for a in self.animals
            if a.kind in (AnimalKind.BOAR, AnimalKind.DEER)
        )
        # Rabbits count at half weight so small-game bloom cannot alone support
        # a huge wolf population on open maps.
        rabbit_food = sum(
            c.level * self._wolf_feed_days("rabbit") * 0.5
            for c in self.colonies
            if c.kind == AnimalKind.RABBIT and c.can_harvest()
        )
        fox_food = self.fox_count() * self._wolf_feed_days("fox")
        prey_cap = max(0, int(animal_food + rabbit_food + fox_food))
        hard = max(0, _bal_int("WOLF_MAX_POPULATION", WOLF_MAX_POPULATION, 0))
        return min(prey_cap, hard) if hard > 0 else prey_cap

    def _pack_room(self, kind: AnimalKind) -> int:
        return max(0, self._pack_max_pop(kind) - self.pack_count(kind))

    def _wolf_max_pop(self) -> int:
        return self._pack_max_pop(AnimalKind.WOLF)

    def _wolf_room(self) -> int:
        return self._pack_room(AnimalKind.WOLF)

    def _seed_wolf_packs(self, world: World) -> None:
        from balance_config import active_balance

        n_packs = max(0, active_balance().get_int("WOLF_SEED_PACKS"))
        if n_packs <= 0:
            return
        for _ in range(n_packs):
            if self._pack_room(AnimalKind.WOLF) < 2:
                break
            cell = self._random_walkable_cell(world)
            if cell is None:
                break
            self._spawn_wolf_pack(
                world,
                cell[0],
                cell[1],
                sexes=(AnimalSex.MALE, AnimalSex.FEMALE),
                kind=AnimalKind.WOLF,
            )

    def _seed_fox_packs(self, world: World) -> None:
        from balance_config import active_balance

        n_packs = max(0, active_balance().get_int("FOX_SEED_PACKS"))
        if n_packs <= 0:
            return
        for _ in range(n_packs):
            if self._pack_room(AnimalKind.FOX) < 2:
                break
            cell = self._random_walkable_cell(world)
            if cell is None:
                break
            self._spawn_wolf_pack(
                world,
                cell[0],
                cell[1],
                sexes=(AnimalSex.MALE, AnimalSex.FEMALE),
                kind=AnimalKind.FOX,
            )

    def _random_walkable_cell(self, world: World) -> tuple[int, int] | None:
        """Cheap random land sample — avoids full-map scans on seed."""
        cols, rows = world.cols, world.rows
        for _ in range(64):
            x = self.rng.randrange(cols)
            y = self.rng.randrange(rows)
            if world.is_walkable(x, y):
                return x, y
        for y in range(0, rows, max(1, rows // 16)):
            for x in range(0, cols, max(1, cols // 16)):
                if world.is_walkable(x, y):
                    return x, y
        return None

    def _spawn_wolf_pack(
        self,
        world: World,
        x: int,
        y: int,
        *,
        sexes: tuple[AnimalSex, ...],
        kind: AnimalKind = AnimalKind.WOLF,
    ) -> WolfPack | None:
        if not world.is_walkable(x, y):
            return None
        if self._pack_room(kind) < len(sexes):
            return None
        pack = WolfPack(
            id=self.next_wolf_pack_id, x=x, y=y, members=[], kind=kind
        )
        self.next_wolf_pack_id += 1
        for sex in sexes:
            mx, my = self._place_wolf_near(world, pack, x, y)
            pack.members.append(
                self._new_pack_member(pack.kind, sex, mx, my)
            )
        pack.move_cooldown = animal_roam_interval()
        self.wolf_packs.append(pack)
        return pack

    @staticmethod
    def _new_pack_member(
        kind: AnimalKind, sex: AnimalSex, x: int, y: int
    ) -> WolfMember:
        from entities import hunt_max_hp

        hp = hunt_max_hp(kind.name)
        return WolfMember(
            sex=sex,
            x=x,
            y=y,
            move_cooldown=animal_roam_interval(),
            max_hp=hp,
            hp=hp,
        )

    def _place_wolf_near(
        self, world: World, pack: WolfPack, x: int, y: int
    ) -> tuple[int, int]:
        taken = {(pack.x, pack.y)} | {(m.x, m.y) for m in pack.members}
        for ny, nx in world.neighbourhood(x, y, radius=1):
            if (nx, ny) in taken:
                continue
            if world.is_walkable(nx, ny):
                return nx, ny
        return x, y

    def _wolf_move_pack(
        self, world: World, pack: WolfPack, nx: int, ny: int
    ) -> None:
        """Move pack centre and members together (same step style as deer pairs)."""
        ox, oy = pack.x, pack.y
        if (nx, ny) == (ox, oy):
            return
        if not world.can_step(ox, oy, nx, ny):
            return
        dx, dy = nx - ox, ny - oy
        note_cell_step(pack, nx, ny, world_target=self._subcell_target(nx, ny))
        for member in pack.members:
            mx, my = member.x + dx, member.y + dy
            if world.can_step(member.x, member.y, mx, my):
                note_cell_step(member, mx, my, world_target=self._subcell_target(mx, my))
            else:
                px, py = self._place_wolf_near(world, pack, pack.x, pack.y)
                note_cell_step(member, px, py, world_target=self._subcell_target(px, py))

    def _wolf_member_step_toward(
        self,
        world: World,
        member: WolfMember,
        tx: int,
        ty: int,
        *,
        biodiversity: list[list[float]] | None = None,
        hunting: bool = False,
    ) -> bool:
        """One Chebyshev step for a single wolf toward ``(tx, ty)``."""
        if (member.x, member.y) == (tx, ty):
            return False
        opts = [
            (nx, ny)
            for ny, nx in world.neighbourhood(member.x, member.y, radius=1)
            if (nx, ny) != (member.x, member.y)
            and world.can_step(member.x, member.y, nx, ny)
        ]
        if not opts:
            return False
        cur = max(abs(member.x - tx), abs(member.y - ty))
        better = [
            p for p in opts if max(abs(p[0] - tx), abs(p[1] - ty)) < cur
        ]
        pool = better or opts
        nx, ny = self._pick_weighted_step(
            world,
            pool,
            biodiversity=biodiversity,
            bio_weight=_bal_weight("WOLF_WEIGHT_BIODIVERSITY", 1.0),
            away_disturbance_weight=_bal_weight(
                "WOLF_WEIGHT_AWAY_DISTURBANCE", 0.5
            ),
            toward=(tx, ty) if hunting else None,
            toward_weight=(
                _bal_weight("WOLF_WEIGHT_TOWARD_PREY", 2.0) if hunting else 0.0
            ),
        )
        if not world.can_step(member.x, member.y, nx, ny):
            return False
        note_cell_step(member, nx, ny, world_target=self._subcell_target(nx, ny))
        return True

    def _wolf_step_toward(
        self,
        world: World,
        pack: WolfPack,
        tx: int,
        ty: int,
        *,
        biodiversity: list[list[float]] | None = None,
        hunting: bool = False,
    ) -> bool:
        """One Chebyshev step toward ``(tx, ty)`` — same idea as animal ``_step_toward``."""
        opts = [
            (nx, ny)
            for ny, nx in world.neighbourhood(pack.x, pack.y, radius=1)
            if (nx, ny) != (pack.x, pack.y)
            and world.can_step(pack.x, pack.y, nx, ny)
        ]
        if not opts:
            return False
        cur = max(abs(pack.x - tx), abs(pack.y - ty))
        better = [
            p for p in opts if max(abs(p[0] - tx), abs(p[1] - ty)) < cur
        ]
        pool = better or opts
        nx, ny = self._pick_weighted_step(
            world,
            pool,
            biodiversity=biodiversity,
            bio_weight=_bal_weight("WOLF_WEIGHT_BIODIVERSITY", 1.0),
            away_disturbance_weight=_bal_weight(
                "WOLF_WEIGHT_AWAY_DISTURBANCE", 0.5
            ),
            toward=(tx, ty) if hunting else None,
            toward_weight=(
                _bal_weight("WOLF_WEIGHT_TOWARD_PREY", 2.0) if hunting else 0.0
            ),
        )
        self._wolf_move_pack(world, pack, nx, ny)
        return True

    def _wolf_hunt_approach(
        self,
        world: World,
        pack: WolfPack,
        px: int,
        py: int,
        *,
        close: bool,
        biodiversity: list[list[float]] | None = None,
    ) -> None:
        """Seek as a pack; when close, peel the nearest wolf onto the prey cell."""
        if not close:
            self._wolf_step_toward(
                world, pack, px, py, biodiversity=biodiversity, hunting=True
            )
            return
        hunter = min(
            pack.members,
            key=lambda m: max(abs(m.x - px), abs(m.y - py)),
        )
        self._wolf_member_step_toward(
            world, hunter, px, py, biodiversity=biodiversity, hunting=True
        )
        note_cell_step(
            pack,
            hunter.x,
            hunter.y,
            world_target=self._subcell_target(hunter.x, hunter.y),
        )
        for member in pack.members:
            if member is hunter:
                continue
            if max(abs(member.x - pack.x), abs(member.y - pack.y)) > 2:
                self._wolf_member_step_toward(
                    world,
                    member,
                    pack.x,
                    pack.y,
                    biodiversity=biodiversity,
                    hunting=False,
                )

    def _wolf_step_flee(
        self, world: World, pack: WolfPack, threat: tuple[int, int]
    ) -> bool:
        tx, ty = threat
        opts = [
            (nx, ny)
            for ny, nx in world.neighbourhood(pack.x, pack.y, radius=1)
            if (nx, ny) != (pack.x, pack.y)
            and world.can_step(pack.x, pack.y, nx, ny)
        ]
        if not opts:
            return False
        cur = max(abs(pack.x - tx), abs(pack.y - ty))
        best = max(opts, key=lambda p: max(abs(p[0] - tx), abs(p[1] - ty)))
        if max(abs(best[0] - tx), abs(best[1] - ty)) < cur:
            best = self.rng.choice(opts)
        self._wolf_move_pack(world, pack, best[0], best[1])
        return True

    def _tick_wolf_packs(
        self,
        world: World,
        day: float,
        *,
        biodiversity: list[list[float]] | None = None,
        villager_threats: list[tuple[int, int]] | None = None,
        flee_interval: int | None = None,
    ) -> None:
        self._decay_wolf_food(day)
        slow = 1 + int(2 * freeze_amount(day)) if animals_slow(day) else 1
        roam_iv = max(4, animal_roam_interval() * slow)
        flee_iv = max(
            4,
            int(
                flee_interval
                if flee_interval is not None
                else animal_flee_interval()
            ),
        )
        seek_mult = wolf_speed_mult("WOLF_SEEK_SPEED_MULT", 1.5)
        chase_mult = wolf_speed_mult("WOLF_CHASE_SPEED_MULT", 1.5)
        # Seek faster than deer/boar roam; close chase faster than flee pace.
        seek_iv = max(4, int(round(roam_iv / seek_mult)))
        chase_iv = max(4, int(round(flee_iv / chase_mult)))

        for pack in list(self.wolf_packs):
            if not pack.members:
                if pack in self.wolf_packs:
                    self.wolf_packs.remove(pack)
                continue
            if pack.move_cooldown > 0:
                pack.move_cooldown -= 1
                for m in pack.members:
                    if m.move_cooldown > 0:
                        m.move_cooldown -= 1
                continue

            # Avoid villagers / player like deer and boar.
            threat = self._nearest_pack_threat(
                pack, villager_threats, HUNT_APPROACH_RADIUS
            )
            if threat is not None:
                pack.activity = "Fleeing villagers"
                self._wolf_step_flee(world, pack, threat)
                self._arm_wolf_pack(pack, flee_iv)
                continue

            if pack.kind == AnimalKind.FOX:
                wolf_threat = self._nearest_pack_threat(
                    pack, self._wolf_threat_positions(), HUNT_APPROACH_RADIUS
                )
                if wolf_threat is not None:
                    pack.activity = "Fleeing wolves"
                    self._wolf_step_flee(world, pack, wolf_threat)
                    self._arm_wolf_pack(pack, flee_iv)
                    continue

            if pack.is_fed(day):
                pack.activity = "Fed — seeking cover"
                self._wolf_retreat_step(world, pack, biodiversity)
                self._arm_wolf_pack(pack, roam_iv)
                continue

            hunted = self._wolf_try_hunt(world, pack, day)
            if hunted:
                pack.activity = "Feeding"
                self._arm_wolf_pack(pack, roam_iv)
                continue

            prey = self._wolf_nearest_prey(pack)
            if prey is None:
                pack.activity = "Roaming"
                opts = self._wolf_neighbour_opts(world, pack)
                if opts:
                    nx, ny = self._pick_weighted_step(
                        world,
                        opts,
                        biodiversity=biodiversity,
                        bio_weight=_bal_weight("WOLF_WEIGHT_BIODIVERSITY", 1.0),
                        away_disturbance_weight=_bal_weight(
                            "WOLF_WEIGHT_AWAY_DISTURBANCE", 0.5
                        ),
                    )
                    self._wolf_move_pack(world, pack, nx, ny)
                self._arm_wolf_pack(pack, roam_iv)
                continue

            px, py, dist = prey
            close = dist <= HUNT_APPROACH_RADIUS
            pack.activity = "Chasing prey" if close else "Hunting"
            interval = chase_iv if close else seek_iv
            self._wolf_hunt_approach(
                world, pack, px, py, close=close, biodiversity=biodiversity
            )
            if self._wolf_try_hunt(world, pack, day):
                pack.activity = "Feeding"
                interval = roam_iv
            self._arm_wolf_pack(pack, interval)

    def _arm_wolf_pack(self, pack: WolfPack, interval: int) -> None:
        pack.move_cooldown = interval
        for m in pack.members:
            arm_cell_step_visual(m, interval)
            m.move_cooldown = interval

    def _nearest_pack_threat(
        self,
        pack: WolfPack,
        threats: list[tuple[int, int]] | None,
        radius: int,
    ) -> tuple[int, int] | None:
        if not threats:
            return None
        best: tuple[int, int] | None = None
        best_d = radius + 1
        for tx, ty in threats:
            d = max(abs(pack.x - tx), abs(pack.y - ty))
            if d < best_d:
                best_d = d
                best = (tx, ty)
        return best if best_d <= radius else None

    def _wolf_can_hunt(self, pack: WolfPack, prey: str) -> bool:
        from balance_config import active_balance

        if pack.kind == AnimalKind.FOX:
            return prey in ("rabbit", "frog", "vole")
        bal = active_balance()
        need = {
            "boar": bal.get_int("WOLF_HUNT_BOAR_MIN"),
            "deer": bal.get_int("WOLF_HUNT_DEER_MIN"),
            "rabbit": bal.get_int("WOLF_HUNT_RABBIT_MIN"),
            "fox": bal.get_int("WOLF_HUNT_FOX_MIN"),
        }.get(prey, 99)
        return pack.size() >= max(1, need)

    def _wolf_feed_days(self, prey: str, pack: WolfPack | None = None) -> float:
        from balance_config import active_balance
        from settings import (
            FOX_FEED_FROG_DAYS,
            FOX_FEED_RABBIT_DAYS,
            FOX_FEED_VOLE_DAYS,
        )

        bal = active_balance()
        kind = pack.kind if pack is not None else AnimalKind.WOLF
        if kind == AnimalKind.FOX:
            return {
                "rabbit": FOX_FEED_RABBIT_DAYS,
                "frog": FOX_FEED_FROG_DAYS,
                "vole": FOX_FEED_VOLE_DAYS,
            }.get(prey, 1.0)
        return {
            "boar": bal.get_float("WOLF_FEED_BOAR_DAYS"),
            "deer": bal.get_float("WOLF_FEED_DEER_DAYS"),
            "rabbit": bal.get_float("WOLF_FEED_RABBIT_DAYS"),
            "fox": bal.get_float("WOLF_FEED_FOX_DAYS"),
        }.get(prey, 1.0)

    def _pack_feed_cap(self, pack: WolfPack) -> float:
        if pack.kind == AnimalKind.FOX:
            return max(
                0.0,
                self._wolf_feed_days("rabbit", pack),
                self._wolf_feed_days("frog", pack),
                self._wolf_feed_days("vole", pack),
            )
        return max(
            0.0,
            self._wolf_feed_days("boar", pack),
            self._wolf_feed_days("deer", pack),
            self._wolf_feed_days("rabbit", pack),
            self._wolf_feed_days("fox", pack),
        )

    def _wolf_feed_cap(self) -> float:
        """Largest single-meal feed duration for wolf packs (legacy / save cap)."""
        return max(0.0, self._wolf_feed_days("boar"))

    def _apply_wolf_feed(self, pack: WolfPack, prey: str, day: float) -> None:
        """Set pack food from a kill; capped at the largest meal for this pack kind."""
        feed = max(0.0, self._wolf_feed_days(prey, pack))
        cap = self._pack_feed_cap(pack)
        pack.fed_days_remaining = min(cap, feed)
        pack.last_prey = prey
        pack.last_meal_day = float(day)

    def _decay_wolf_food(self, day: float) -> None:
        """Count down fed_days_remaining across calendar wraps."""
        from seasons import YEAR_DAYS

        if self._wolf_food_day is None:
            self._wolf_food_day = float(day)
            return
        prev = float(self._wolf_food_day)
        cur = float(day)
        delta = cur - prev
        if delta < -0.5 * YEAR_DAYS:
            delta += float(YEAR_DAYS)
        elif delta < 0.0:
            delta = 0.0
        self._wolf_food_day = cur
        if delta <= 0.0:
            return
        for pack in self.wolf_packs:
            if pack.fed_days_remaining <= 0.0:
                continue
            cap = self._pack_feed_cap(pack)
            pack.fed_days_remaining = min(
                cap, max(0.0, float(pack.fed_days_remaining) - delta)
            )

    def _wolf_member_on_prey(self, pack: WolfPack, x: int, y: int) -> bool:
        return any(m.x == x and m.y == y for m in pack.members)

    def _try_harvest_colony_prey(
        self,
        pack: WolfPack,
        prey_name: str,
        colony_kind: AnimalKind,
        day: float,
    ) -> bool:
        for colony in self.colonies:
            if colony.kind != colony_kind or not colony.can_harvest():
                continue
            cells = {(colony.x, colony.y)}
            cells.update((m.x, m.y) for m in colony.members)
            if not any(self._wolf_member_on_prey(pack, cx, cy) for cx, cy in cells):
                continue
            if self.harvest_colony(colony.id, kind=colony_kind) is None:
                continue
            self._apply_wolf_feed(pack, prey_name, day)
            return True
        return False

    def _wolf_try_hunt(self, world: World, pack: WolfPack, day: float) -> bool:
        """Kill prey only when a pack member stands on the same cell."""
        del world
        if pack.kind == AnimalKind.FOX:
            for prey_name, colony_kind in (
                ("rabbit", AnimalKind.RABBIT),
                ("frog", AnimalKind.FROG),
                ("vole", AnimalKind.VOLE),
            ):
                if not self._wolf_can_hunt(pack, prey_name):
                    continue
                if self._try_harvest_colony_prey(pack, prey_name, colony_kind, day):
                    return True
            return False

        if self._wolf_can_hunt(pack, "boar"):
            for animal in self.animals:
                if animal.kind != AnimalKind.BOAR:
                    continue
                if not self._wolf_member_on_prey(pack, animal.x, animal.y):
                    continue
                if self.kill_animal(animal.id) is None:
                    continue
                self._apply_wolf_feed(pack, "boar", day)
                return True
        if self._wolf_can_hunt(pack, "deer"):
            for animal in self.animals:
                if animal.kind != AnimalKind.DEER:
                    continue
                if not self._wolf_member_on_prey(pack, animal.x, animal.y):
                    continue
                if self.kill_animal(animal.id) is None:
                    continue
                self._apply_wolf_feed(pack, "deer", day)
                return True
        if self._wolf_can_hunt(pack, "fox"):
            for fox_pack in list(self.wolf_packs):
                if fox_pack.kind != AnimalKind.FOX:
                    continue
                for member in list(fox_pack.members):
                    if not self._wolf_member_on_prey(pack, member.x, member.y):
                        continue
                    fox_pack.members.remove(member)
                    if not fox_pack.members and fox_pack in self.wolf_packs:
                        self.wolf_packs.remove(fox_pack)
                    self._apply_wolf_feed(pack, "fox", day)
                    return True
        if self._wolf_can_hunt(pack, "rabbit"):
            if self._try_harvest_colony_prey(
                pack, "rabbit", AnimalKind.RABBIT, day
            ):
                return True
        return False

    def _wolf_nearest_prey(
        self, pack: WolfPack
    ) -> tuple[int, int, int] | None:
        """Nearest huntable prey as ``(x, y, chebyshev_dist)`` from closest wolf."""
        best: tuple[int, int, int] | None = None

        def _dist_to(x: int, y: int) -> int:
            return min(max(abs(m.x - x), abs(m.y - y)) for m in pack.members)

        def _consider(x: int, y: int) -> None:
            nonlocal best
            d = _dist_to(x, y)
            if best is None or d < best[2]:
                best = (x, y, d)

        if pack.kind == AnimalKind.FOX:
            colony_targets = (
                ("rabbit", AnimalKind.RABBIT),
                ("frog", AnimalKind.FROG),
                ("vole", AnimalKind.VOLE),
            )
            any_prey = False
            for prey_name, colony_kind in colony_targets:
                if not self._wolf_can_hunt(pack, prey_name):
                    continue
                any_prey = True
                for colony in self.colonies:
                    if colony.kind != colony_kind or not colony.can_harvest():
                        continue
                    _consider(colony.x, colony.y)
                    for member in colony.members:
                        _consider(member.x, member.y)
            return best if any_prey else None

        can_boar = self._wolf_can_hunt(pack, "boar")
        can_deer = self._wolf_can_hunt(pack, "deer")
        can_rabbit = self._wolf_can_hunt(pack, "rabbit")
        can_fox = self._wolf_can_hunt(pack, "fox")
        if not (can_boar or can_deer or can_rabbit or can_fox):
            return None

        for animal in self.animals:
            if animal.kind == AnimalKind.BOAR and not can_boar:
                continue
            if animal.kind == AnimalKind.DEER and not can_deer:
                continue
            if animal.kind not in (AnimalKind.BOAR, AnimalKind.DEER):
                continue
            _consider(animal.x, animal.y)
        if can_fox:
            for fox_pack in self.wolf_packs:
                if fox_pack.kind != AnimalKind.FOX:
                    continue
                _consider(fox_pack.x, fox_pack.y)
                for member in fox_pack.members:
                    _consider(member.x, member.y)
        if can_rabbit:
            for colony in self.colonies:
                if colony.kind != AnimalKind.RABBIT or not colony.can_harvest():
                    continue
                _consider(colony.x, colony.y)
                for member in colony.members:
                    _consider(member.x, member.y)
        return best

    def harvestable_rabbit_count(self) -> int:
        return sum(
            1
            for c in self.colonies
            if c.kind == AnimalKind.RABBIT and c.can_harvest()
        )

    def wolf_pack(self, pack_id: int) -> WolfPack | None:
        for pack in self.wolf_packs:
            if pack.id == pack_id:
                return pack
        return None

    def _wolf_neighbour_opts(self, world: World, pack: WolfPack) -> list[tuple[int, int]]:
        return [
            (nx, ny)
            for ny, nx in world.neighbourhood(pack.x, pack.y, radius=1)
            if (nx, ny) != (pack.x, pack.y)
            and world.can_step(pack.x, pack.y, nx, ny)
        ]

    def _wolf_retreat_step(
        self,
        world: World,
        pack: WolfPack,
        biodiversity: list[list[float]] | None,
    ) -> None:
        opts = self._wolf_neighbour_opts(world, pack)
        if not opts:
            return
        nx, ny = self._pick_weighted_step(
            world,
            opts,
            biodiversity=biodiversity,
            bio_weight=_bal_weight("WOLF_WEIGHT_BIODIVERSITY", 1.0),
            away_disturbance_weight=_bal_weight(
                "WOLF_WEIGHT_AWAY_DISTURBANCE", 0.5
            ),
        )
        self._wolf_move_pack(world, pack, nx, ny)

    def _breed_wolves(self, world: World) -> None:
        from balance_config import active_balance

        bal = active_balance()
        for pack_kind in PACK_KINDS:
            chance_key = (
                "WOLF_BREED_CHANCE"
                if pack_kind == AnimalKind.WOLF
                else "FOX_BREED_CHANCE"
            )
            chance = bal.get_float(chance_key)
            for pack in list(self.wolf_packs):
                if pack.kind != pack_kind:
                    continue
                if self._pack_room(pack_kind) <= 0:
                    break
                # A pair must have secured food before investing in offspring.
                if not pack.is_fed(0.0):
                    continue
                if not pack.has_pair():
                    continue
                if self.rng.random() >= chance:
                    continue
                males = sum(1 for m in pack.members if m.sex == AnimalSex.MALE)
                females = len(pack.members) - males
                sex = AnimalSex.FEMALE if males > females else AnimalSex.MALE
                if males == females:
                    sex = self._random_sex()
                if (
                    pack.size() >= 4
                    and self._pack_room(pack_kind) >= 2
                    and self.rng.random() < 0.35
                ):
                    land = self._wolf_neighbour_opts(world, pack) or [(pack.x, pack.y)]
                    sx, sy = self.rng.choice(land)
                    self._spawn_wolf_pack(
                        world,
                        sx,
                        sy,
                        sexes=(AnimalSex.MALE, AnimalSex.FEMALE),
                        kind=pack_kind,
                    )
                    continue
                mx, my = self._place_wolf_near(world, pack, pack.x, pack.y)
                pack.members.append(
                    self._new_pack_member(pack_kind, sex, mx, my)
                )

        self._cull_excess_predators()

    def _cull_excess_predators(self) -> None:
        """Trim packs above hard/prey carrying capacity (hungry packs first)."""
        for kind in PACK_KINDS:
            excess = max(0, self.pack_count(kind) - self._pack_max_pop(kind))
            if excess <= 0:
                continue
            # Prefer starving packs, then largest fed packs.
            ordered = sorted(
                (p for p in self.wolf_packs if p.kind == kind),
                key=lambda p: (p.is_fed(0.0), -p.size()),
            )
            for pack in ordered:
                while pack.members and excess > 0:
                    pack.members.pop()
                    excess -= 1
                if not pack.members and pack in self.wolf_packs:
                    self.wolf_packs.remove(pack)
                if excess <= 0:
                    break

    # ------------------------------------------------------------------
    # Hawks / owls
    # ------------------------------------------------------------------
    def _bird_nest_sites(self) -> list[tuple[int, int]]:
        nests: list[tuple[int, int]] = []
        for fh in self.habitats:
            nests.extend(fh.deer_breeding)
        return nests

    def _seed_birds(self, world: World, *, kind: AnimalKind | None = None) -> None:
        from settings import BIRD_SEED_COUNT

        kinds = [kind] if kind is not None else list(BIRD_KINDS)
        n_each = _bal_int("BIRD_SEED_COUNT", BIRD_SEED_COUNT)
        if n_each <= 0:
            return
        nests = self._bird_nest_sites()
        if not nests:
            return
        occupied = self._occupied()
        self.rng.shuffle(nests)
        for bird_kind in kinds:
            placed = 0
            for nx, ny in nests:
                if placed >= n_each:
                    break
                if not world.is_walkable(nx, ny):
                    continue
                if (nx, ny) in occupied:
                    continue
                self.animals.append(
                    Animal(
                        id=self.next_id,
                        x=nx,
                        y=ny,
                        kind=bird_kind,
                        move_cooldown=animal_roam_interval(),
                        retreat_target=(nx, ny),
                    )
                )
                self.next_id += 1
                occupied.add((nx, ny))
                placed += 1
        self._index_animals()

    def _bird_prey_kinds(self, kind: AnimalKind) -> tuple[AnimalKind, ...]:
        if kind == AnimalKind.HAWK:
            return (AnimalKind.RABBIT, AnimalKind.VOLE, AnimalKind.FROG)
        if kind == AnimalKind.OWL:
            return (AnimalKind.VOLE, AnimalKind.FROG)
        return ()

    def _bird_on_colony(self, bird: Animal, colony: Colony) -> bool:
        if (bird.x, bird.y) == (colony.x, colony.y):
            return True
        return any(m.x == bird.x and m.y == bird.y for m in colony.members)

    def _bird_try_hunt(self, bird: Animal) -> bool:
        for prey_kind in self._bird_prey_kinds(bird.kind):
            for colony in self.colonies:
                if colony.kind != prey_kind or not colony.can_harvest():
                    continue
                if not self._bird_on_colony(bird, colony):
                    continue
                if self.harvest_colony(colony.id, kind=prey_kind) is None:
                    continue
                return True
        return False

    def _bird_nearest_other(self, bird: Animal) -> tuple[int, int] | None:
        other = AnimalKind.HAWK if bird.kind == AnimalKind.OWL else AnimalKind.OWL
        best: tuple[int, tuple[int, int]] | None = None
        for other_bird in self.animals:
            if other_bird.kind != other:
                continue
            d = max(abs(bird.x - other_bird.x), abs(bird.y - other_bird.y))
            if d > HUNT_APPROACH_RADIUS:
                continue
            if best is None or d < best[0]:
                best = (d, (other_bird.x, other_bird.y))
        return best[1] if best is not None else None

    def _bird_can_fly(self, world: World, x: int, y: int) -> bool:
        """Birds soar over land, water, and roofs — only the map edge stops them."""
        return world.in_bounds(x, y)

    def _bird_step(self, world: World, bird: Animal, nx: int, ny: int) -> None:
        del world
        if nx != bird.x:
            bird.facing_right = nx > bird.x
        note_cell_step(bird, nx, ny, world_target=self._subcell_target(nx, ny))

    def _bird_pick_heading(self) -> tuple[int, int, int]:
        """Return (dx, dy, leg_length) for a long straight soar."""
        dirs = [
            (1, 0),
            (-1, 0),
            (0, 1),
            (0, -1),
            (1, 1),
            (1, -1),
            (-1, 1),
            (-1, -1),
        ]
        dx, dy = self.rng.choice(dirs)
        leg = self.rng.randint(10, 22)
        return dx, dy, leg

    def _bird_continue_leg(
        self,
        world: World,
        bird: Animal,
        occupied: set[tuple[int, int]],
    ) -> bool:
        """Take one step along the current heading if possible."""
        if bird.roam_leg <= 0 or (bird.roam_dx == 0 and bird.roam_dy == 0):
            return False
        nx, ny = bird.x + bird.roam_dx, bird.y + bird.roam_dy
        if (
            not self._bird_can_fly(world, nx, ny)
            or (nx, ny) in occupied
            or (nx, ny) == (bird.x, bird.y)
        ):
            bird.roam_leg = 0
            return False
        occupied.discard((bird.x, bird.y))
        self._bird_step(world, bird, nx, ny)
        occupied.add((bird.x, bird.y))
        bird.roam_leg -= 1
        return True

    def _bird_step_flee(
        self,
        world: World,
        bird: Animal,
        threat: tuple[int, int],
        occupied: set[tuple[int, int]],
    ) -> None:
        tx, ty = threat
        opts = [
            (nx, ny)
            for ny, nx in world.neighbourhood(bird.x, bird.y, radius=1)
            if (nx, ny) != (bird.x, bird.y)
            and self._bird_can_fly(world, nx, ny)
            and (nx, ny) not in occupied
        ]
        if not opts:
            return
        best = max(opts, key=lambda p: max(abs(p[0] - tx), abs(p[1] - ty)))
        ox, oy = bird.x, bird.y
        occupied.discard((bird.x, bird.y))
        self._bird_step(world, bird, best[0], best[1])
        occupied.add((bird.x, bird.y))
        bird.roam_dx = 0 if best[0] == ox else (1 if best[0] > ox else -1)
        bird.roam_dy = 0 if best[1] == oy else (1 if best[1] > oy else -1)
        bird.roam_leg = self.rng.randint(6, 12)

    def _tick_birds(
        self,
        world: World,
        day: float,
        *,
        biodiversity: list[list[float]] | None = None,
    ) -> None:
        from settings import BIRD_ROAM_SPEED_MULT

        del biodiversity
        slow = 1 + int(2 * freeze_amount(day)) if animals_slow(day) else 1
        roam_iv = max(
            4,
            int(
                round(
                    animal_roam_interval()
                    * slow
                    / max(0.5, _bal_float("BIRD_ROAM_SPEED_MULT", BIRD_ROAM_SPEED_MULT))
                )
            ),
        )
        occupied = self._occupied()
        for bird in self.animals:
            if bird.kind not in BIRD_KINDS:
                continue
            if bird.move_cooldown > 0:
                bird.move_cooldown -= 1
                continue

            other = self._bird_nearest_other(bird)
            if other is not None:
                bird.activity = "Avoiding rival"
                self._bird_step_flee(world, bird, other, occupied)
                self._arm_move(bird, roam_iv)
                continue

            if self._bird_try_hunt(bird):
                bird.activity = "Hunting"
                bird.roam_leg = 0
                self._arm_move(bird, roam_iv)
                continue

            # Prefer continuing a long straight leg.
            if self._bird_continue_leg(world, bird, occupied):
                bird.activity = "Soaring"
                self._arm_move(bird, roam_iv)
                continue

            # Start a new leg — bias toward nearest huntable colony if any.
            prey_pos: tuple[int, int] | None = None
            best_d = 10**9
            for prey_kind in self._bird_prey_kinds(bird.kind):
                for colony in self.colonies:
                    if colony.kind != prey_kind or not colony.can_harvest():
                        continue
                    d = max(abs(bird.x - colony.x), abs(bird.y - colony.y))
                    if d < best_d:
                        best_d = d
                        prey_pos = (colony.x, colony.y)
            if prey_pos is not None and best_d <= 24:
                px, py = prey_pos
                bird.roam_dx = 0 if px == bird.x else (1 if px > bird.x else -1)
                bird.roam_dy = 0 if py == bird.y else (1 if py > bird.y else -1)
                bird.roam_leg = self.rng.randint(8, 18)
                bird.activity = "Hunting"
            else:
                bird.roam_dx, bird.roam_dy, bird.roam_leg = self._bird_pick_heading()
                bird.activity = "Soaring"
            if not self._bird_continue_leg(world, bird, occupied):
                # Blocked immediately — random neighbour step, then new heading next tick.
                opts = [
                    (nx, ny)
                    for ny, nx in world.neighbourhood(bird.x, bird.y, radius=1)
                    if (nx, ny) != (bird.x, bird.y)
                    and self._bird_can_fly(world, nx, ny)
                    and (nx, ny) not in occupied
                ]
                if opts:
                    occupied.discard((bird.x, bird.y))
                    nx, ny = self.rng.choice(opts)
                    self._bird_step(world, bird, nx, ny)
                    occupied.add((bird.x, bird.y))
                bird.roam_leg = 0
            self._arm_move(bird, roam_iv)


@dataclass
class Fish:
    id: int
    x: int
    y: int
    kind: FishKind = FishKind.ROACH
    move_cooldown: int = 0
    world_x: float | None = None
    world_y: float | None = None

    def __post_init__(self) -> None:
        self.world_x = float(self.x) if self.world_x is None else float(self.world_x)
        self.world_y = float(self.y) if self.world_y is None else float(self.world_y)


class FishManager:
    """Spawn, cull, and roam fish on water patches."""

    def __init__(self, seed: int = RANDOM_SEED) -> None:
        self.rng = random.Random(seed + 17)
        self.fish: list[Fish] = []
        self.next_id = 1
        self.growth_timer = FISH_GROWTH_INTERVAL

    def reset(self) -> None:
        self.fish.clear()
        self.next_id = 1
        self.growth_timer = FISH_GROWTH_INTERVAL
        self.rng.seed(RANDOM_SEED + 17)

    def _subcell_target(self, x: int, y: int) -> tuple[float, float]:
        return (
            float(x) + self.rng.uniform(-0.36, 0.36),
            float(y) + self.rng.uniform(-0.36, 0.36),
        )

    def total_capacity(self, world: World) -> int:
        rev = getattr(world, "terrain_revision", 0)
        water_per_cap = _bal_int(
            "WILDLIFE_FISH_WATER_PER_CAP", FISH_WATER_PER_CAP, 1
        )
        cache_key = (rev, water_per_cap)
        if getattr(self, "_cap_key", None) == cache_key and hasattr(self, "_cap_cache"):
            return self._cap_cache
        self._cap_key = cache_key
        self._cap_cache = sum(len(p) // water_per_cap for p in world.water_patches())
        return self._cap_cache

    def fish_at(self, x: int, y: int) -> Fish | None:
        for item in self.fish:
            if item.x == x and item.y == y:
                return item
        return None

    def fish_in_area(self, contains) -> list[Fish]:
        return [f for f in self.fish if contains(f.x, f.y)]

    def pick_kind(self) -> FishKind:
        """Weighted species roll (carp:perch:pike:roach = 2:3:1:4)."""
        kinds = list(FishKind)
        weights = [max(0, int(FISH_SPAWN_WEIGHTS.get(k.name, 1))) for k in kinds]
        if sum(weights) <= 0:
            return FishKind.ROACH
        return self.rng.choices(kinds, weights=weights, k=1)[0]

    def kill_fish(self, fish_id: int) -> tuple[int, int, FishKind] | None:
        for i, item in enumerate(self.fish):
            if item.id == fish_id:
                pos = (item.x, item.y, item.kind)
                self.fish.pop(i)
                return pos
        return None

    def tick(
        self,
        world: World,
        day: float = 0.0,
        *,
        attractors: list[tuple[int, int]] | None = None,
    ) -> None:
        self._move_fish(world, day, attractors=attractors)
        if not fish_breeding_allowed(day):
            return
        self.growth_timer -= 1
        if self.growth_timer <= 0:
            self.growth_timer = FISH_GROWTH_INTERVAL
            self._update_population(world)

    def _move_fish(
        self,
        world: World,
        day: float = 0.0,
        *,
        attractors: list[tuple[int, int]] | None = None,
    ) -> None:
        from world import TerrainType

        lake_frozen = water_frozen(day)
        water_age = getattr(self, "_water_age", 0)
        if water_age <= 0 or not hasattr(self, "_water_cache"):
            self._water_cache = set(world.water_cells())
            self._water_age = 80
        else:
            self._water_age = water_age - 1
        water = self._water_cache
        if not water:
            for item in self.fish:
                if item.move_cooldown > 0:
                    item.move_cooldown -= 1
            return

        for item in self.fish:
            if item.move_cooldown > 0:
                item.move_cooldown -= 1
                continue
            # Lakes ice over; rivers stay open so fish there keep swimming.
            if lake_frozen:
                cell = world.get_cell(item.x, item.y)
                if cell is not None and cell.terrain == TerrainType.WATER:
                    continue
            neighbours = [
                (nx, ny)
                for ny, nx in world.neighbourhood(item.x, item.y, radius=1)
                if (nx, ny) != (item.x, item.y) and (nx, ny) in water
            ]
            if neighbours:
                nearby = [
                    post
                    for post in (attractors or [])
                    if max(abs(post[0] - item.x), abs(post[1] - item.y)) <= 10
                ]
                if nearby:
                    post = min(
                        nearby,
                        key=lambda p: abs(p[0] - item.x) + abs(p[1] - item.y),
                    )
                    current_d = abs(post[0] - item.x) + abs(post[1] - item.y)
                    closer = [
                        pos
                        for pos in neighbours
                        if abs(post[0] - pos[0]) + abs(post[1] - pos[1]) < current_d
                    ]
                    nx, ny = self.rng.choice(closer or neighbours)
                else:
                    nx, ny = self.rng.choice(neighbours)
                note_cell_step(item, nx, ny, world_target=self._subcell_target(nx, ny))
            elif (item.x, item.y) not in water:
                nx, ny = self.rng.choice(list(water))
                note_cell_step(item, nx, ny, world_target=self._subcell_target(nx, ny))
            item.move_cooldown = fish_move_interval()
            arm_cell_step_visual(item, fish_move_interval())

    def _fish_per_patch(self, world: World) -> list[list[Fish]]:
        patches = world.water_patches()
        buckets: list[list[Fish]] = [[] for _ in patches]
        patch_lookup: dict[tuple[int, int], int] = {}
        for i, patch in enumerate(patches):
            for pos in patch:
                patch_lookup[pos] = i
        unassigned: list[Fish] = []
        for item in self.fish:
            idx = patch_lookup.get((item.x, item.y))
            if idx is None:
                unassigned.append(item)
            else:
                buckets[idx].append(item)
        self._unassigned = unassigned
        return buckets

    def _update_population(self, world: World) -> None:
        patches = world.water_patches()
        if not patches:
            self.fish.clear()
            return
        water_per_cap = _bal_int(
            "WILDLIFE_FISH_WATER_PER_CAP", FISH_WATER_PER_CAP, 1
        )
        caps = [len(p) // water_per_cap for p in patches]
        buckets = self._fish_per_patch(world)
        unassigned = getattr(self, "_unassigned", [])

        for item in list(unassigned):
            if item in self.fish:
                self.fish.remove(item)

        for i, group in enumerate(buckets):
            cap = caps[i] if i < len(caps) else 0
            while len(group) > cap:
                victim = group.pop()
                if victim in self.fish:
                    self.fish.remove(victim)

        buckets = self._fish_per_patch(world)
        if self.rng.random() >= _bal_float("WILDLIFE_FISH_BREED_CHANCE", 1.0):
            return
        for i, patch in enumerate(patches):
            cap = caps[i]
            group = buckets[i] if i < len(buckets) else []
            if len(group) >= cap or not patch:
                continue
            sx, sy = self.rng.choice(patch)
            self.fish.append(
                Fish(
                    id=self.next_id,
                    x=sx,
                    y=sy,
                    kind=self.pick_kind(),
                    move_cooldown=fish_move_interval(),
                )
            )
            self.next_id += 1
            break
