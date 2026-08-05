"""Wildlife: deer, boars, and bee/rabbit colonies.

Forest patches = connected tree/sapling tiles. Habitats are rebuilt on the same
season start/mid sample window as biodiversity (≤8 updates per year).

Deer / Boar
-----------
Individual animals with mating pairs, seasonal roaming, and migration.
Deer breed on forest edge; boars in forest interior.

Bees / Rabbits
--------------
Colonies (not individuals). Each has a nest tile and level 1–4 controlling how
many visible members wander nearby. Colonies grow when forage food is available;
a level-3 colony may found a new level-1 colony on an empty nest site. If a kind
has zero colonies at spring (new year), one small colony is seeded.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum, auto

from seasons import (
    Season,
    animals_multiply,
    animals_slow,
    freeze_amount,
    season_for_day,
    water_frozen,
)
from entities import arm_cell_step_visual, note_cell_step
from resource_balance import (
    ANIMAL_BREED_CHANCE,
    ANIMAL_MIGRATION_CHANCE,
    ANIMAL_TREES_PER_CAP,
    BOAR_CELLS_PER_CAP,
    BOAR_CROP_EAT_CHANCE,
    COLONY_GROW_CHANCE,
    COLONY_HARVEST_COOLDOWN,
    COLONY_LEVEL_MAX,
    COLONY_MEMBER_RADIUS,
    COLONY_MEMBERS_BY_LEVEL,
    COLONY_RABBIT_CROP_EAT_CHANCE,
    COLONY_SEED_GROUNDS,
    COLONY_SPLIT_CHANCE,
    COLONY_SPLIT_LEVEL,
    DEER_CROP_EAT_CHANCE,
    FISH_WATER_PER_CAP,
    HONEY_PER_BEE_LEVEL,
    MIN_BREEDING_CAPACITY,
    RABBIT_MEAT_PER_LEVEL,
    RABBIT_MOVE_PAUSE,
    SMALL_GAME_FORAGE_RADIUS,
    WILDLIFE_RESEED_PAIR,
    WILDLIFE_SEED_COUNT,
    WILDLIFE_SEED_GROUNDS,
)
from settings import (
    ANIMAL_GROWTH_INTERVAL,
    ANIMAL_MOVE_INTERVAL,
    FISH_GROWTH_INTERVAL,
    FISH_MOVE_INTERVAL,
    RANDOM_SEED,
)
from world import FeatureType, TerrainType, World


class AnimalKind(Enum):
    DEER = auto()
    BOAR = auto()
    BEE = auto()
    RABBIT = auto()


FOREST_KINDS: tuple[AnimalKind, ...] = (AnimalKind.DEER, AnimalKind.BOAR)
COLONY_KINDS: tuple[AnimalKind, ...] = (AnimalKind.BEE, AnimalKind.RABBIT)


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
    move_cooldown: int = 0
    # Autumn roost retreat (still affiliated with a patch).
    retreat_target: tuple[int, int] | None = None
    # Dispersal: home patch while seeking a new ground (patch_id is None).
    migrate_home_id: int | None = None
    # Autumn/winter: walk toward this tile on a patch that has space.
    migrate_target: tuple[int, int] | None = None
    # True after leaving home this year; cleared each spring.
    migrated_this_year: bool = False


@dataclass
class ColonyMember:
    """Visible individual that wanders near its colony nest."""

    x: int
    y: int
    move_cooldown: int = 0


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
        return len(self.deer_breeding) // ANIMAL_TREES_PER_CAP

    @property
    def boar_cap(self) -> int:
        return len(self.boar_breeding) // BOAR_CELLS_PER_CAP


@dataclass
class OpenHabitat:
    """Meadow / forest-edge nest sites for bee and rabbit colonies."""

    id: int
    nest_tiles: list[tuple[int, int]]
    forage_tiles: set[tuple[int, int]]
    allow_bee: bool = True
    allow_rabbit: bool = True

    # One colony of each allowed kind per nest site (UI / capacity display).
    @property
    def bee_cap(self) -> int:
        return 1 if self.allow_bee and self.nest_tiles else 0

    @property
    def rabbit_cap(self) -> int:
        return 1 if self.allow_rabbit and self.nest_tiles else 0


Habitat = ForestHabitat | OpenHabitat


class WildlifeManager:
    """Forest game (deer/boar) plus bee/rabbit colonies on open nest sites."""

    def __init__(self, seed: int = RANDOM_SEED) -> None:
        self.rng = random.Random(seed + 7)
        self.animals: list[Animal] = []
        self.colonies: list[Colony] = []
        self.next_id = 1
        self.next_colony_id = 1
        self.growth_timer = ANIMAL_GROWTH_INTERVAL
        self.habitats: list[ForestHabitat] = []
        self.open_habitats: list[OpenHabitat] = []
        self._seeded = False
        self._colonies_need_seed = False
        self._prev_season: Season | None = None
        self._by_id: dict[int, Animal] = {}

    def reset(self) -> None:
        self.animals.clear()
        self.colonies.clear()
        self._by_id.clear()
        self.next_id = 1
        self.next_colony_id = 1
        self.growth_timer = ANIMAL_GROWTH_INTERVAL
        self.habitats.clear()
        self.open_habitats.clear()
        self._seeded = False
        self._colonies_need_seed = False
        self._prev_season = None
        self.rng.seed(RANDOM_SEED + 7)

    def _index_animals(self) -> None:
        self._by_id = {a.id: a for a in self.animals}

    def deer(self) -> list[Animal]:
        return [a for a in self.animals if a.kind == AnimalKind.DEER]

    def boars(self) -> list[Animal]:
        return [a for a in self.animals if a.kind == AnimalKind.BOAR]

    def bee_colonies(self) -> list[Colony]:
        return [c for c in self.colonies if c.kind == AnimalKind.BEE]

    def rabbit_colonies(self) -> list[Colony]:
        return [c for c in self.colonies if c.kind == AnimalKind.RABBIT]

    def colonies_of(self, kind: AnimalKind) -> list[Colony]:
        return [c for c in self.colonies if c.kind == kind]

    def count_kind(self, kind: AnimalKind) -> int:
        if kind in COLONY_KINDS:
            return len(self.colonies_of(kind))
        return sum(1 for a in self.animals if a.kind == kind)

    def colony_members_total(self, kind: AnimalKind) -> int:
        return sum(c.target_members() for c in self.colonies_of(kind))

    def total_capacity(self, world: World | None = None) -> int:
        del world
        forest = sum(h.deer_cap + h.boar_cap for h in self.habitats)
        open_cap = sum(h.bee_cap + h.rabbit_cap for h in self.open_habitats)
        return forest + open_cap

    def animal_at(self, x: int, y: int) -> Animal | None:
        for animal in self.animals:
            if animal.x == x and animal.y == y:
                return animal
        return None

    def animals_in_area(self, contains) -> list[Animal]:
        return [a for a in self.animals if contains(a.x, a.y)]

    def kill_animal(self, animal_id: int) -> tuple[int, int, AnimalKind] | None:
        self._index_animals()
        animal = self._by_id.get(animal_id)
        if animal is None:
            return None
        self._clear_mate(animal)
        pos = (animal.x, animal.y, animal.kind)
        self.animals.remove(animal)
        self._by_id.pop(animal_id, None)
        return pos

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
        return [
            h
            for h in self.open_habitats
            if self._allows_colony(kind, h) and h.nest_tiles
        ]

    @staticmethod
    def _allows_colony(kind: AnimalKind, hab: OpenHabitat) -> bool:
        if kind == AnimalKind.BEE:
            return hab.allow_bee
        if kind == AnimalKind.RABBIT:
            return hab.allow_rabbit
        return False

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

        patches = world.forest_patches()
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
            if not self.colonies:
                self._seed_colonies(world)
        for colony in self.colonies:
            self._sync_colony_members(colony, self._colony_habitat(colony))

    def _refresh_open_habitats(self, world: World) -> None:
        old_nests = [set(h.nest_tiles) for h in self.open_habitats]
        old_colony_ids = [c.habitat_id for c in self.colonies]

        habitats: list[OpenHabitat] = []
        hid = 0
        for patch in world.meadow_patches():
            nest = list(patch)
            forage = self._forage_from_nests(world, nest)
            if not nest or not forage:
                continue
            habitats.append(
                OpenHabitat(
                    id=hid,
                    nest_tiles=nest,
                    forage_tiles=forage,
                    allow_bee=True,
                    allow_rabbit=True,
                )
            )
            hid += 1
        for fh in self.habitats:
            if not fh.deer_breeding:
                continue
            nest = list(fh.deer_breeding)
            forage = self._forage_from_nests(world, nest)
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

    @staticmethod
    def _is_forage_tile(world: World, x: int, y: int) -> bool:
        cell = world.get_cell(x, y)
        if cell is None or not world.is_walkable(x, y):
            return False
        if cell.terrain in (TerrainType.MEADOW, TerrainType.GRASS):
            return True
        return cell.feature == FeatureType.FIELD

    def _forage_from_nests(
        self, world: World, nests: list[tuple[int, int]]
    ) -> set[tuple[int, int]]:
        """Contiguous forage tiles within ``SMALL_GAME_FORAGE_RADIUS`` of nests."""
        radius = SMALL_GAME_FORAGE_RADIUS
        candidates: set[tuple[int, int]] = set()
        for nx, ny in nests:
            for cy, cx in world.neighbourhood(nx, ny, radius=radius):
                if self._is_forage_tile(world, cx, cy):
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
        """Forest tiles that border open grass/meadow (no tree/sapling on that neighbour)."""
        open_land = (TerrainType.GRASS, TerrainType.MEADOW)
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
        present = [
            a for a in self.animals if a.kind == kind and a.patch_id == patch_id
        ]
        outbound = [
            a
            for a in self.animals
            if a.kind == kind
            and a.migrate_home_id == patch_id
            and a.patch_id is None
        ]
        paired = sum(1 for a in present + outbound if a.mate_id is not None) // 2
        return len(present), len(outbound), len(present) + len(outbound), paired

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
        self.next_id = 1
        self.next_colony_id = 1
        occupied: set[tuple[int, int]] = set()

        for kind in FOREST_KINDS:
            grounds = self.breeding_grounds(kind)
            grounds.sort(
                key=lambda h: len(self._breeding_for(kind, h)),
                reverse=True,
            )
            for hab in grounds[:WILDLIFE_SEED_GROUNDS]:
                self._seed_patch(kind, hab, WILDLIFE_SEED_COUNT, occupied)
        self._seed_colonies(world)
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
                    move_cooldown=ANIMAL_MOVE_INTERVAL,
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
        """At new year, restore extinct forest pairs / empty colony kinds."""
        if not self.habitats and not self.open_habitats:
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
        for kind in COLONY_KINDS:
            if self.count_kind(kind) > 0:
                continue
            sites = self._empty_colony_sites(kind)
            if not sites:
                continue
            self._spawn_colony(kind, self.rng.choice(sites), level=1)

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
    def tick(self, world: World, day: float = 0.0) -> None:
        if not self.habitats and not self.open_habitats:
            self.refresh_habitats(world)
        self._index_animals()
        season = season_for_day(int(day))
        if self._prev_season is None:
            self._prev_season = season
        elif season != self._prev_season:
            self.on_season_change(world, season)
        self._form_mating_pairs()
        self._move_animals(world, day, season)
        self._move_colony_members(world, day)
        if not animals_multiply(day):
            return
        self.growth_timer -= 1
        if self.growth_timer <= 0:
            self.growth_timer = ANIMAL_GROWTH_INTERVAL
            self._graze(world)
            self._form_mating_pairs()
            self._breed()
            self._cull_excess()
            self._migrate()
            self._tick_colonies(world)

    def _form_mating_pairs(self) -> None:
        """Pair unpaired males and females that share a patch."""
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

    @staticmethod
    def _place_animal(
        animal: Animal,
        nx: int,
        ny: int,
        occupied: set[tuple[int, int]],
    ) -> None:
        occupied.discard((animal.x, animal.y))
        note_cell_step(animal, nx, ny)
        occupied.add((nx, ny))

    @staticmethod
    def _arm_move(animal: Animal, move_interval: int) -> None:
        animal.move_cooldown = move_interval
        arm_cell_step_visual(animal, move_interval)

    def _step_toward(
        self,
        world: World,
        animal: Animal,
        tx: int,
        ty: int,
        occupied: set[tuple[int, int]],
    ) -> bool:
        """Take one walkable step toward (tx, ty). Uses BFS when greedy is stuck."""
        if (animal.x, animal.y) == (tx, ty):
            return False

        cur_d = max(abs(animal.x - tx), abs(animal.y - ty))
        improving: list[tuple[int, int]] = []
        sideways: list[tuple[int, int]] = []
        for ny, nx in world.neighbourhood(animal.x, animal.y, radius=1):
            if (nx, ny) == (animal.x, animal.y):
                continue
            if not world.is_walkable(nx, ny) or (nx, ny) in occupied:
                continue
            d = max(abs(nx - tx), abs(ny - ty))
            if d < cur_d:
                improving.append((nx, ny))
            elif d == cur_d:
                sideways.append((nx, ny))

        choice: tuple[int, int] | None = None
        if improving:
            choice = self.rng.choice(improving)
        else:
            # Obstacle in the way — follow a BFS path around water / blockers.
            choice = self._bfs_next_step(
                world, animal.x, animal.y, tx, ty, occupied
            )
            if choice is None and sideways:
                choice = self.rng.choice(sideways)

        if choice is None:
            return False
        self._place_animal(animal, choice[0], choice[1], occupied)
        return True

    def _step_along_path(
        self,
        world: World,
        animal: Animal,
        tx: int,
        ty: int,
        occupied: set[tuple[int, int]],
    ) -> bool:
        """One step along a BFS path — used for migration so detours are not undone."""
        if (animal.x, animal.y) == (tx, ty):
            return False
        nxt = self._bfs_next_step(world, animal.x, animal.y, tx, ty, occupied)
        if nxt is None:
            # Fallback: greedy improve only (no sideways undo of a detour).
            cur_d = max(abs(animal.x - tx), abs(animal.y - ty))
            improving = [
                (nx, ny)
                for ny, nx in world.neighbourhood(animal.x, animal.y, radius=1)
                if (nx, ny) != (animal.x, animal.y)
                and world.is_walkable(nx, ny)
                and (nx, ny) not in occupied
                and max(abs(nx - tx), abs(ny - ty)) < cur_d
            ]
            if not improving:
                return False
            nxt = self.rng.choice(improving)
        self._place_animal(animal, nxt[0], nxt[1], occupied)
        return True

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
        from collections import deque

        start = (sx, sy)
        goal = (tx, ty)
        if start == goal:
            return None
        blocked = set(occupied)
        blocked.discard(start)
        blocked.discard(goal)
        max_nodes = limit if limit is not None else world.rows * world.cols + 8

        prev: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        queue: deque[tuple[int, int]] = deque([start])
        found = False
        while queue and len(prev) < max_nodes:
            cx, cy = queue.popleft()
            for ny, nx in world.neighbourhood(cx, cy, radius=1):
                nxt = (nx, ny)
                if nxt in prev:
                    continue
                if nxt != goal and (not world.is_walkable(nx, ny) or nxt in blocked):
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

        cur = goal
        while prev[cur] is not None and prev[cur] != start:
            cur = prev[cur]  # type: ignore[assignment]
        if prev.get(cur) == start:
            return cur
        return None

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
            and world.is_walkable(nx, ny)
            and (nx, ny) not in occupied
        ]
        if not opts:
            return
        dest = self._weighted_away_choice(opts, center)
        self._place_animal(animal, dest[0], dest[1], occupied)

    def _move_pair_away(
        self,
        world: World,
        a: Animal,
        b: Animal,
        hab: Habitat,
        roam: set[tuple[int, int]],
        occupied: set[tuple[int, int]],
        move_interval: int,
    ) -> None:
        """Step a mating pair one tile, weighted away from breeding ground."""
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
            dest = self._weighted_away_choice(lead_opts, center)
            self._place_animal(a, dest[0], dest[1], occupied)

        # Mate stays adjacent: step toward leader first if separated.
        if max(abs(b.x - a.x), abs(b.y - a.y)) > 1:
            self._step_toward(world, b, a.x, a.y, occupied)
        else:
            mate_opts = [
                (nx, ny)
                for ny, nx in world.neighbourhood(b.x, b.y, radius=1)
                if (nx, ny) != (b.x, b.y)
                and (nx, ny) not in occupied
                and world.is_walkable(nx, ny)
                and max(abs(nx - a.x), abs(ny - a.y)) <= 1
            ]
            in_roam = [p for p in mate_opts if p in roam]
            pool = in_roam or mate_opts
            if pool:
                mdest = self._weighted_away_choice(pool, center)
                self._place_animal(b, mdest[0], mdest[1], occupied)

        self._arm_move(a, move_interval)
        self._arm_move(b, move_interval)

    def _move_animals(self, world: World, day: float, season: Season) -> None:
        slow = 1 + int(2 * freeze_amount(day)) if animals_slow(day) else 1
        move_interval = ANIMAL_MOVE_INTERVAL * slow
        occupied = self._occupied()
        cold_season = season in (Season.AUTUMN, Season.WINTER)
        warm_season = season in (Season.SPRING, Season.SUMMER)
        moved: set[int] = set()

        for animal in self.animals:
            if animal.id in moved:
                continue
            if animal.move_cooldown > 0:
                animal.move_cooldown -= 1
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
                    world, animal, mate, hab, roam, occupied, move_interval
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
            ]
            if neighbours:
                center = (
                    self._breeding_center(animal.kind, hab) if warm_season else None
                )
                dest = (
                    self._weighted_away_choice(neighbours, center)
                    if warm_season
                    else self.rng.choice(neighbours)
                )
                occupied.discard((animal.x, animal.y))
                note_cell_step(animal, dest[0], dest[1])
                occupied.add(dest)
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

    def _eat_wild_crop(self, world: World, x: int, y: int) -> bool:
        cell = world.get_cell(x, y)
        if cell is None or cell.feature not in (FeatureType.WILD_CROP, FeatureType.HERB):
            return False
        cell.feature = FeatureType.NONE
        cell.crop_kind = None
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
            move_cooldown=ANIMAL_MOVE_INTERVAL,
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
            crops = self._adjacent_wild_crops(world, animal.x, animal.y)
            if not crops:
                continue
            chance = {
                AnimalKind.DEER: DEER_CROP_EAT_CHANCE,
                AnimalKind.BOAR: BOAR_CROP_EAT_CHANCE,
            }.get(animal.kind, 0.0)
            if chance <= 0.0 or self.rng.random() >= chance:
                continue
            cx, cy = self.rng.choice(crops)
            self._eat_wild_crop(world, cx, cy)

    def _breed(self) -> None:
        """Mating pairs may produce one offspring in their current patch only."""
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
            if animal.patch_id is None:
                continue
            hab = self.habitat(animal.patch_id, animal.kind)
            if hab is None:
                continue
            cap = self._cap_for(animal.kind, hab)
            if self._count_in_patch(animal.kind, hab.id) >= cap:
                continue
            if self.rng.random() >= ANIMAL_BREED_CHANCE:
                continue
            self._try_spawn_in_patch(animal.kind, hab, occupied)

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
            if self.rng.random() >= ANIMAL_MIGRATION_CHANCE:
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
        return False

    def _sync_colony_members(self, colony: Colony, hab: OpenHabitat | None) -> None:
        want = colony.target_members()
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
                ColonyMember(x=sx, y=sy, move_cooldown=ANIMAL_MOVE_INTERVAL)
            )
        if len(colony.members) > want:
            colony.members = colony.members[:want]

    def _move_colony_members(self, world: World, day: float) -> None:
        del day
        occupied = {(a.x, a.y) for a in self.animals}
        occupied.update((c.x, c.y) for c in self.colonies)
        for colony in self.colonies:
            hab = self._colony_habitat(colony)
            self._sync_colony_members(colony, hab)
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
                RABBIT_MOVE_PAUSE
                if colony.kind == AnimalKind.RABBIT
                else ANIMAL_MOVE_INTERVAL
            )
            for member in colony.members:
                if member.move_cooldown > 0:
                    member.move_cooldown -= 1
                    continue
                options = [
                    p
                    for p in roam
                    if p not in occupied
                    and max(abs(p[0] - member.x), abs(p[1] - member.y)) <= 1
                    and world.is_walkable(p[0], p[1])
                ]
                if not options:
                    options = [
                        p
                        for p in roam
                        if p not in occupied and world.is_walkable(p[0], p[1])
                    ]
                if options:
                    occupied.discard((member.x, member.y))
                    nx, ny = self.rng.choice(options)
                    note_cell_step(member, nx, ny)
                    occupied.add((nx, ny))
                arm_cell_step_visual(member, pause)
                member.move_cooldown = pause

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
        if colony.kind == AnimalKind.RABBIT:
            amount = RABBIT_MEAT_PER_LEVEL
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

        # Rabbit colonies may nibble nearby wild crops.
        for colony in self.colonies:
            if colony.kind != AnimalKind.RABBIT:
                continue
            if self.rng.random() >= COLONY_RABBIT_CROP_EAT_CHANCE:
                continue
            crops = self._adjacent_wild_crops(world, colony.x, colony.y)
            if crops:
                self._eat_wild_crop(world, *self.rng.choice(crops))

        # Level growth, then fission from level-3 colonies with food.
        for colony in list(self.colonies):
            if not self._colony_has_food(world, colony):
                continue
            if colony.level < COLONY_LEVEL_MAX and self.rng.random() < COLONY_GROW_CHANCE:
                colony.level += 1
                colony.clamp_level()
                self._sync_colony_members(colony, self._colony_habitat(colony))

        for colony in list(self.colonies):
            if colony.level != COLONY_SPLIT_LEVEL:
                continue
            if not self._colony_has_food(world, colony):
                continue
            if self.rng.random() >= COLONY_SPLIT_CHANCE:
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


@dataclass
class Fish:
    id: int
    x: int
    y: int
    move_cooldown: int = 0


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

    def total_capacity(self, world: World) -> int:
        return sum(len(p) // FISH_WATER_PER_CAP for p in world.water_patches())

    def fish_at(self, x: int, y: int) -> Fish | None:
        for item in self.fish:
            if item.x == x and item.y == y:
                return item
        return None

    def fish_in_area(self, contains) -> list[Fish]:
        return [f for f in self.fish if contains(f.x, f.y)]

    def kill_fish(self, fish_id: int) -> tuple[int, int] | None:
        for i, item in enumerate(self.fish):
            if item.id == fish_id:
                pos = (item.x, item.y)
                self.fish.pop(i)
                return pos
        return None

    def tick(self, world: World, day: float = 0.0) -> None:
        self._move_fish(world, day)
        if water_frozen(day) or not animals_multiply(day):
            return
        self.growth_timer -= 1
        if self.growth_timer <= 0:
            self.growth_timer = FISH_GROWTH_INTERVAL
            self._update_population(world)

    def _move_fish(self, world: World, day: float = 0.0) -> None:
        if water_frozen(day):
            for item in self.fish:
                if item.move_cooldown > 0:
                    item.move_cooldown -= 1
            return
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
            neighbours = [
                (nx, ny)
                for ny, nx in world.neighbourhood(item.x, item.y, radius=1)
                if (nx, ny) != (item.x, item.y) and (nx, ny) in water
            ]
            if neighbours:
                nx, ny = self.rng.choice(neighbours)
                note_cell_step(item, nx, ny)
            elif (item.x, item.y) not in water:
                nx, ny = self.rng.choice(list(water))
                note_cell_step(item, nx, ny)
            item.move_cooldown = FISH_MOVE_INTERVAL
            arm_cell_step_visual(item, FISH_MOVE_INTERVAL)

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
        caps = [len(p) // FISH_WATER_PER_CAP for p in patches]
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
        for i, patch in enumerate(patches):
            cap = caps[i]
            group = buckets[i] if i < len(buckets) else []
            if len(group) >= cap or not patch:
                continue
            sx, sy = self.rng.choice(patch)
            self.fish.append(
                Fish(id=self.next_id, x=sx, y=sy, move_cooldown=FISH_MOVE_INTERVAL)
            )
            self.next_id += 1
            break
