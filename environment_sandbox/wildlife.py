"""Wildlife: deer and boars on contiguous forest patches.

Forest patches = connected tree/sapling tiles. Habitats are rebuilt on the same
season start/mid sample window as biodiversity (≤8 updates per year).

Deer
----
Breeding: forest tiles that border open grass (no tree/sapling).
Capacity: breeding tiles // ANIMAL_TREES_PER_CAP.

Boar
----
Breeding: internal forest (all tree/sapling tiles in the patch).
Capacity: forest tiles // BOAR_CELLS_PER_CAP.

Seasonal roaming
----------------
Autumn/Winter: within 1 of breeding tiles.
Spring/Summer: cold roam plus nearby grass/meadow.

Empty patches are only populated by migration (or initial seeding).
Initial seed: WILDLIFE_SEED_GROUNDS deer + boar habitats get WILDLIFE_SEED_COUNT each.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum, auto

from seasons import (
    Season,
    animals_multiply,
    animals_slow,
    freeze_amount,
    season_for_day,
    water_frozen,
)
from settings import (
    ANIMAL_GROWTH_INTERVAL,
    ANIMAL_MIGRATION_CHANCE,
    ANIMAL_MOVE_INTERVAL,
    ANIMAL_TREES_PER_CAP,
    BOAR_CELLS_PER_CAP,
    BOAR_CROP_EAT_CHANCE,
    DEER_CROP_EAT_CHANCE,
    FISH_GROWTH_INTERVAL,
    FISH_MOVE_INTERVAL,
    FISH_WATER_PER_CAP,
    RANDOM_SEED,
    WILDLIFE_SEED_COUNT,
    WILDLIFE_SEED_GROUNDS,
)
from world import FeatureType, TerrainType, World


class AnimalKind(Enum):
    DEER = auto()
    BOAR = auto()


@dataclass
class Animal:
    id: int
    x: int
    y: int
    kind: AnimalKind = AnimalKind.DEER
    patch_id: int | None = None
    move_cooldown: int = 0
    # Autumn retreat: walk toward this breeding tile until inside cold roam.
    retreat_target: tuple[int, int] | None = None


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


class WildlifeManager:
    """Spawn, cull, roam, graze, and migrate deer + boars on forest patches."""

    def __init__(self, seed: int = RANDOM_SEED) -> None:
        self.rng = random.Random(seed + 7)
        self.animals: list[Animal] = []
        self.next_id = 1
        self.growth_timer = ANIMAL_GROWTH_INTERVAL
        self.habitats: list[ForestHabitat] = []
        self._seeded = False
        self._prev_season: Season | None = None

    def reset(self) -> None:
        self.animals.clear()
        self.next_id = 1
        self.growth_timer = ANIMAL_GROWTH_INTERVAL
        self.habitats.clear()
        self._seeded = False
        self._prev_season = None
        self.rng.seed(RANDOM_SEED + 7)

    def deer(self) -> list[Animal]:
        return [a for a in self.animals if a.kind == AnimalKind.DEER]

    def boars(self) -> list[Animal]:
        return [a for a in self.animals if a.kind == AnimalKind.BOAR]

    def total_capacity(self, world: World | None = None) -> int:
        del world
        return sum(h.deer_cap + h.boar_cap for h in self.habitats)

    def animal_at(self, x: int, y: int) -> Animal | None:
        for animal in self.animals:
            if animal.x == x and animal.y == y:
                return animal
        return None

    def animals_in_area(self, contains) -> list[Animal]:
        return [a for a in self.animals if contains(a.x, a.y)]

    def kill_animal(self, animal_id: int) -> tuple[int, int, AnimalKind] | None:
        for i, animal in enumerate(self.animals):
            if animal.id == animal_id:
                pos = (animal.x, animal.y, animal.kind)
                self.animals.pop(i)
                return pos
        return None

    def habitat(self, patch_id: int | None) -> ForestHabitat | None:
        if patch_id is None or not (0 <= patch_id < len(self.habitats)):
            return None
        return self.habitats[patch_id]

    def breeding_grounds(self, kind: AnimalKind) -> list[ForestHabitat]:
        """Habitats with a usable breeding area for this species."""
        return [
            h
            for h in self.habitats
            if self._breeding_for(kind, h) and self._cap_for(kind, h) > 0
        ]

    # ------------------------------------------------------------------
    # Habitat refresh (same cadence as biodiversity samples)
    # ------------------------------------------------------------------
    def refresh_habitats(self, world: World) -> None:
        """Rebuild forest-patch breeding/roaming maps from current world state."""
        old_forests = [set(h.forest_tiles) for h in self.habitats]
        old_ids = [a.patch_id for a in self.animals]

        patches = world.forest_patches()
        habitats: list[ForestHabitat] = []
        for i, forest in enumerate(patches):
            forest_set = set(forest)
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
        self._remap_animals_after_refresh(old_forests, old_ids)

    @staticmethod
    def _deer_breeding_tiles(
        world: World, forest: list[tuple[int, int]]
    ) -> list[tuple[int, int]]:
        """Forest tiles that border grass without a tree/sapling."""
        breeding: list[tuple[int, int]] = []
        for fx, fy in forest:
            for ny, nx in world.neighbourhood(fx, fy, radius=1):
                if (nx, ny) == (fx, fy):
                    continue
                cell = world.cells[ny][nx]
                if cell.terrain != TerrainType.GRASS:
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
        old_forests: list[set[tuple[int, int]]],
        old_ids: list[int | None],
    ) -> None:
        """Keep patch affiliation by forest overlap; never auto-claim empty grounds."""
        if not self.habitats:
            for animal in self.animals:
                animal.patch_id = None
            return

        for animal, old_id in zip(self.animals, old_ids):
            mapped: int | None = None
            if old_id is not None and 0 <= old_id < len(old_forests):
                old_set = old_forests[old_id]
                best_overlap = 0
                for hab in self.habitats:
                    overlap = len(old_set & set(hab.forest_tiles))
                    if overlap > best_overlap:
                        best_overlap = overlap
                        mapped = hab.id
            if mapped is not None:
                animal.patch_id = mapped
            else:
                # Orphaned: do not silently join a nearby empty patch.
                animal.patch_id = None

    def _cap_for(self, kind: AnimalKind, hab: ForestHabitat) -> int:
        return hab.deer_cap if kind == AnimalKind.DEER else hab.boar_cap

    def _breeding_for(self, kind: AnimalKind, hab: ForestHabitat) -> list[tuple[int, int]]:
        return hab.deer_breeding if kind == AnimalKind.DEER else hab.boar_breeding

    def _roaming_for(
        self, kind: AnimalKind, hab: ForestHabitat, season: Season
    ) -> set[tuple[int, int]]:
        warm = season in (Season.SPRING, Season.SUMMER)
        if kind == AnimalKind.DEER:
            return hab.deer_roam_warm if warm else hab.deer_roam_cold
        return hab.boar_roam_warm if warm else hab.boar_roam_cold

    def _cold_roaming_for(self, kind: AnimalKind, hab: ForestHabitat) -> set[tuple[int, int]]:
        return hab.deer_roam_cold if kind == AnimalKind.DEER else hab.boar_roam_cold

    def count_in_patch(self, kind: AnimalKind, patch_id: int) -> int:
        return sum(1 for a in self.animals if a.kind == kind and a.patch_id == patch_id)

    def _count_in_patch(self, kind: AnimalKind, patch_id: int) -> int:
        return self.count_in_patch(kind, patch_id)

    def _occupied(self) -> set[tuple[int, int]]:
        return {(a.x, a.y) for a in self.animals}

    def _patch_inhabited(self, kind: AnimalKind, patch_id: int) -> bool:
        return self._count_in_patch(kind, patch_id) > 0

    # ------------------------------------------------------------------
    # Initial seeding
    # ------------------------------------------------------------------
    def seed_breeding_grounds(self, world: World) -> None:
        """Seed WILDLIFE_SEED_GROUNDS deer + boar habitats with WILDLIFE_SEED_COUNT each."""
        if self._seeded:
            return
        if not self.habitats:
            self.refresh_habitats(world)
        self.animals.clear()
        self.next_id = 1
        occupied: set[tuple[int, int]] = set()

        deer_grounds = self.breeding_grounds(AnimalKind.DEER)
        boar_grounds = self.breeding_grounds(AnimalKind.BOAR)
        deer_grounds.sort(key=lambda h: len(h.deer_breeding), reverse=True)
        boar_grounds.sort(key=lambda h: len(h.boar_breeding), reverse=True)

        for hab in deer_grounds[:WILDLIFE_SEED_GROUNDS]:
            self._seed_patch(AnimalKind.DEER, hab, WILDLIFE_SEED_COUNT, occupied)
        for hab in boar_grounds[:WILDLIFE_SEED_GROUNDS]:
            self._seed_patch(AnimalKind.BOAR, hab, WILDLIFE_SEED_COUNT, occupied)
        self._seeded = True

    def _seed_patch(
        self,
        kind: AnimalKind,
        hab: ForestHabitat,
        count: int,
        occupied: set[tuple[int, int]],
    ) -> None:
        breed = list(self._breeding_for(kind, hab))
        if not breed:
            return
        self.rng.shuffle(breed)
        roam = self._cold_roaming_for(kind, hab)
        placed = 0
        for bx, by in breed:
            if placed >= count:
                break
            near = [
                p
                for p in roam
                if p not in occupied and max(abs(p[0] - bx), abs(p[1] - by)) <= 1
            ]
            pool = near or [p for p in roam if p not in occupied]
            if not pool:
                continue
            sx, sy = self.rng.choice(pool)
            self.animals.append(
                Animal(
                    id=self.next_id,
                    x=sx,
                    y=sy,
                    kind=kind,
                    patch_id=hab.id,
                    move_cooldown=ANIMAL_MOVE_INTERVAL,
                )
            )
            self.next_id += 1
            occupied.add((sx, sy))
            placed += 1

    # ------------------------------------------------------------------
    # Season transitions
    # ------------------------------------------------------------------
    def on_season_change(self, world: World, season: Season) -> None:
        """Hook for calendar season changes (autumn retreat onto breeding grounds)."""
        if season == Season.AUTUMN:
            self._start_autumn_retreat(world)
        self._prev_season = season

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
        for hab in self.habitats:
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
    ) -> ForestHabitat | None:
        best_h: ForestHabitat | None = None
        best_d = 10**9
        for hab in self.habitats:
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
        if not self.habitats:
            self.refresh_habitats(world)
        season = season_for_day(int(day))
        if self._prev_season is None:
            self._prev_season = season
        elif season != self._prev_season:
            self.on_season_change(world, season)
        self._move_animals(world, day, season)
        if not animals_multiply(day):
            return
        self.growth_timer -= 1
        if self.growth_timer <= 0:
            self.growth_timer = ANIMAL_GROWTH_INTERVAL
            self._graze(world)
            self._cull_excess()
            self._migrate()

    def _step_toward(
        self,
        world: World,
        animal: Animal,
        tx: int,
        ty: int,
        occupied: set[tuple[int, int]],
    ) -> bool:
        """Take one Chebyshev step toward (tx, ty) onto a free walkable tile."""
        best: list[tuple[int, int]] = []
        best_d = max(abs(animal.x - tx), abs(animal.y - ty))
        for ny, nx in world.neighbourhood(animal.x, animal.y, radius=1):
            if (nx, ny) == (animal.x, animal.y):
                continue
            if not world.is_walkable(nx, ny) or (nx, ny) in occupied:
                continue
            d = max(abs(nx - tx), abs(ny - ty))
            if d < best_d:
                best_d = d
                best = [(nx, ny)]
            elif d == best_d:
                best.append((nx, ny))
        if not best:
            return False
        occupied.discard((animal.x, animal.y))
        animal.x, animal.y = self.rng.choice(best)
        occupied.add((animal.x, animal.y))
        return True

    def _move_animals(self, world: World, day: float, season: Season) -> None:
        slow = 1 + int(2 * freeze_amount(day)) if animals_slow(day) else 1
        move_interval = ANIMAL_MOVE_INTERVAL * slow
        occupied = self._occupied()
        cold_season = season in (Season.AUTUMN, Season.WINTER)

        for animal in self.animals:
            if animal.move_cooldown > 0:
                animal.move_cooldown -= 1
                continue

            # Autumn/winter retreat from open grass/meadow toward breeding.
            if animal.retreat_target is not None:
                tx, ty = animal.retreat_target
                hab = self.habitat(animal.patch_id)
                cold = (
                    self._cold_roaming_for(animal.kind, hab)
                    if hab is not None
                    else set()
                )
                if (animal.x, animal.y) in cold or (animal.x, animal.y) == (tx, ty):
                    animal.retreat_target = None
                else:
                    self._step_toward(world, animal, tx, ty, occupied)
                    # Arriving near any breeding claims that habitat (migration/retreat).
                    if animal.patch_id is None:
                        near = self._nearest_breeding_habitat(
                            animal.kind, animal.x, animal.y
                        )
                        if near is not None:
                            cold_n = self._cold_roaming_for(animal.kind, near)
                            if (animal.x, animal.y) in cold_n:
                                animal.patch_id = near.id
                    animal.move_cooldown = move_interval
                    continue

            # Orphans must walk to a breeding ground — they do not auto-join.
            if animal.patch_id is None:
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
                animal.move_cooldown = move_interval
                continue

            hab = self.habitat(animal.patch_id)
            if hab is None:
                animal.patch_id = None
                animal.move_cooldown = move_interval
                continue

            roam = self._roaming_for(animal.kind, hab, season)
            cold = self._cold_roaming_for(animal.kind, hab)

            # Outside cold roam in autumn/winter → head for breeding.
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
                animal.move_cooldown = move_interval
                continue

            if not roam:
                animal.move_cooldown = move_interval
                continue

            neighbours = [
                (nx, ny)
                for ny, nx in world.neighbourhood(animal.x, animal.y, radius=1)
                if (nx, ny) != (animal.x, animal.y)
                and (nx, ny) in roam
                and (nx, ny) not in occupied
            ]
            if neighbours:
                occupied.discard((animal.x, animal.y))
                animal.x, animal.y = self.rng.choice(neighbours)
                occupied.add((animal.x, animal.y))
            elif (animal.x, animal.y) not in roam:
                free = [p for p in roam if p not in occupied]
                if free:
                    occupied.discard((animal.x, animal.y))
                    animal.x, animal.y = self.rng.choice(free)
                    occupied.add((animal.x, animal.y))
            animal.move_cooldown = move_interval

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
        hab: ForestHabitat,
        occupied: set[tuple[int, int]],
    ) -> bool:
        """Local breed only in an already-inhabited patch (never colonises empty grounds)."""
        if not self._patch_inhabited(kind, hab.id):
            return False
        cap = self._cap_for(kind, hab)
        if self._count_in_patch(kind, hab.id) >= cap:
            return False
        roam = self._cold_roaming_for(kind, hab)
        breed = [p for p in self._breeding_for(kind, hab) if p not in occupied and p in roam]
        free_roam = [p for p in roam if p not in occupied]
        pool = breed or free_roam
        if not pool:
            return False
        sx, sy = self.rng.choice(pool)
        self.animals.append(
            Animal(
                id=self.next_id,
                x=sx,
                y=sy,
                kind=kind,
                patch_id=hab.id,
                move_cooldown=ANIMAL_MOVE_INTERVAL,
            )
        )
        self.next_id += 1
        occupied.add((sx, sy))
        return True

    def _graze(self, world: World) -> None:
        occupied = self._occupied()
        for animal in list(self.animals):
            if animal.patch_id is None:
                continue
            crops = self._adjacent_wild_crops(world, animal.x, animal.y)
            if not crops:
                continue
            chance = (
                DEER_CROP_EAT_CHANCE
                if animal.kind == AnimalKind.DEER
                else BOAR_CROP_EAT_CHANCE
            )
            if self.rng.random() >= chance:
                continue
            cx, cy = self.rng.choice(crops)
            if not self._eat_wild_crop(world, cx, cy):
                continue
            hab = self.habitat(animal.patch_id)
            if hab is None:
                continue
            self._try_spawn_in_patch(animal.kind, hab, occupied)

    def _cull_excess(self) -> None:
        if not self.habitats:
            # Keep animals; they become orphans and must retreat/migrate.
            for animal in self.animals:
                animal.patch_id = None
            return
        for hab in self.habitats:
            for kind in (AnimalKind.DEER, AnimalKind.BOAR):
                group = [a for a in self.animals if a.kind == kind and a.patch_id == hab.id]
                cap = self._cap_for(kind, hab)
                if cap <= 0 or not self._breeding_for(kind, hab):
                    for a in group:
                        a.patch_id = None
                    continue
                while len(group) > cap:
                    victim = group.pop()
                    if victim in self.animals:
                        self.animals.remove(victim)

    def _migrate(self) -> None:
        """Randomly move animals into other patches (how empty grounds populate)."""
        if len(self.habitats) < 2:
            return
        occupied = self._occupied()
        for animal in list(self.animals):
            if animal.patch_id is None:
                continue
            if self.rng.random() >= ANIMAL_MIGRATION_CHANCE:
                continue
            hab = self.habitat(animal.patch_id)
            if hab is None:
                continue
            options: list[ForestHabitat] = []
            for other in self.habitats:
                if other.id == hab.id:
                    continue
                if not self._breeding_for(animal.kind, other):
                    continue
                cap = self._cap_for(animal.kind, other)
                if cap <= 0:
                    continue
                if self._count_in_patch(animal.kind, other.id) < cap:
                    options.append(other)
            if not options:
                continue
            dest = self.rng.choice(options)
            # Prefer cold roost so migrants arrive inside breeding range.
            roam = self._cold_roaming_for(animal.kind, dest)
            breed = [
                p
                for p in self._breeding_for(animal.kind, dest)
                if p not in occupied and p in roam
            ]
            free = [p for p in roam if p not in occupied]
            pool = breed or free
            if not pool:
                continue
            occupied.discard((animal.x, animal.y))
            animal.x, animal.y = self.rng.choice(pool)
            animal.patch_id = dest.id
            animal.retreat_target = None
            occupied.add((animal.x, animal.y))
            animal.move_cooldown = ANIMAL_MOVE_INTERVAL


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
                item.x, item.y = self.rng.choice(neighbours)
            elif (item.x, item.y) not in water:
                item.x, item.y = self.rng.choice(list(water))
            item.move_cooldown = FISH_MOVE_INTERVAL

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
