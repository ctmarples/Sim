"""Wildlife: deer near tree patches, boars on soil/riparian.

Deer keep the original tree-habitat roaming and density rules.
Boars live on connected soil/riparian patches (cap 1 per BOAR_CELLS_PER_CAP
cells) and roam within one square of their patch.

Both may graze adjacent wild crops and breed into free patch capacity.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum, auto

from seasons import (
    animals_multiply,
    animals_slow,
    freeze_amount,
    water_frozen,
)
from settings import (
    ANIMAL_GROWTH_INTERVAL,
    ANIMAL_MOVE_INTERVAL,
    ANIMAL_TREES_PER_CAP,
    BOAR_CELLS_PER_CAP,
    BOAR_CROP_EAT_CHANCE,
    DEER_CROP_EAT_CHANCE,
    FISH_GROWTH_INTERVAL,
    FISH_MOVE_INTERVAL,
    FISH_WATER_PER_CAP,
    RANDOM_SEED,
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
    move_cooldown: int = 0


class WildlifeManager:
    """Spawn, cull, roam, and graze deer + boars."""

    def __init__(self, seed: int = RANDOM_SEED) -> None:
        self.rng = random.Random(seed + 7)
        self.animals: list[Animal] = []
        self.next_id = 1
        self.growth_timer = ANIMAL_GROWTH_INTERVAL

    def reset(self) -> None:
        self.animals.clear()
        self.next_id = 1
        self.growth_timer = ANIMAL_GROWTH_INTERVAL
        self.rng.seed(RANDOM_SEED + 7)

    def deer(self) -> list[Animal]:
        return [a for a in self.animals if a.kind == AnimalKind.DEER]

    def boars(self) -> list[Animal]:
        return [a for a in self.animals if a.kind == AnimalKind.BOAR]

    def patch_capacity(self, world: World) -> dict[int, int]:
        """Deer: map tree-patch index → max deer."""
        patches = world.tree_patches()
        return {
            i: len(patch) // ANIMAL_TREES_PER_CAP
            for i, patch in enumerate(patches)
        }

    def total_capacity(self, world: World) -> int:
        """UI total: deer tree-patch caps + boar soil/riparian caps."""
        deer_cap = sum(self.patch_capacity(world).values())
        boar_cap = sum(
            len(p) // BOAR_CELLS_PER_CAP for p in world.soil_riparian_patches()
        )
        return deer_cap + boar_cap

    def animal_at(self, x: int, y: int) -> Animal | None:
        for animal in self.animals:
            if animal.x == x and animal.y == y:
                return animal
        return None

    def animals_in_area(self, contains) -> list[Animal]:
        return [a for a in self.animals if contains(a.x, a.y)]

    def kill_animal(self, animal_id: int) -> tuple[int, int, AnimalKind] | None:
        """Remove animal; return (x, y, kind) or None."""
        for i, animal in enumerate(self.animals):
            if animal.id == animal_id:
                pos = (animal.x, animal.y, animal.kind)
                self.animals.pop(i)
                return pos
        return None

    def tick(self, world: World, day: float = 0.0) -> None:
        self._move_animals(world, day)
        if not animals_multiply(day):
            return
        self.growth_timer -= 1
        if self.growth_timer <= 0:
            self.growth_timer = ANIMAL_GROWTH_INTERVAL
            self._graze(world)
            self._update_deer_population(world)
            self._update_boar_population(world)

    # ------------------------------------------------------------------
    # Habitat helpers
    # ------------------------------------------------------------------
    def _deer_habitat(self, world: World) -> set[tuple[int, int]]:
        age = getattr(self, "_deer_habitat_age", 0)
        if age <= 0 or not hasattr(self, "_deer_habitat_cache"):
            self._deer_habitat_cache = set(world.habitat_cells_near_trees())
            self._deer_habitat_age = 40
        else:
            self._deer_habitat_age = age - 1
        return self._deer_habitat_cache

    def _boar_habitat(self, world: World) -> set[tuple[int, int]]:
        age = getattr(self, "_boar_habitat_age", 0)
        if age <= 0 or not hasattr(self, "_boar_habitat_cache"):
            self._boar_habitat_cache = set(world.boar_habitat_cells())
            self._boar_habitat_age = 40
        else:
            self._boar_habitat_age = age - 1
        return self._boar_habitat_cache

    def _patch_for_deer(
        self, x: int, y: int, patches: list[list[tuple[int, int]]]
    ) -> int | None:
        best: tuple[int, int] | None = None
        for i, patch in enumerate(patches):
            for tx, ty in patch:
                dist = max(abs(tx - x), abs(ty - y))
                if dist <= 1:
                    if best is None or dist < best[0]:
                        best = (dist, i)
        return best[1] if best is not None else None

    def _patch_for_boar(
        self, x: int, y: int, patches: list[list[tuple[int, int]]]
    ) -> int | None:
        best: tuple[int, int] | None = None
        for i, patch in enumerate(patches):
            for px, py in patch:
                dist = max(abs(px - x), abs(py - y))
                if dist <= 1:
                    if best is None or dist < best[0]:
                        best = (dist, i)
        return best[1] if best is not None else None

    # ------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------
    def _move_animals(self, world: World, day: float = 0.0) -> None:
        slow = 1 + int(2 * freeze_amount(day)) if animals_slow(day) else 1
        move_interval = ANIMAL_MOVE_INTERVAL * slow
        deer_hab = self._deer_habitat(world)
        boar_hab = self._boar_habitat(world)

        for animal in self.animals:
            if animal.move_cooldown > 0:
                animal.move_cooldown -= 1
                continue
            habitat = deer_hab if animal.kind == AnimalKind.DEER else boar_hab
            if not habitat:
                animal.move_cooldown = move_interval
                continue
            neighbours = [
                (nx, ny)
                for ny, nx in world.neighbourhood(animal.x, animal.y, radius=1)
                if (nx, ny) != (animal.x, animal.y) and (nx, ny) in habitat
            ]
            if neighbours:
                animal.x, animal.y = self.rng.choice(neighbours)
            elif (animal.x, animal.y) not in habitat:
                animal.x, animal.y = self.rng.choice(list(habitat))
            animal.move_cooldown = move_interval

    # ------------------------------------------------------------------
    # Grazing / opportunistic breed
    # ------------------------------------------------------------------
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

    def _occupied(self) -> set[tuple[int, int]]:
        return {(a.x, a.y) for a in self.animals}

    def _try_spawn(
        self,
        kind: AnimalKind,
        candidates: list[tuple[int, int]],
        occupied: set[tuple[int, int]],
    ) -> bool:
        free = [p for p in candidates if p not in occupied]
        if not free:
            return False
        sx, sy = self.rng.choice(free)
        self.animals.append(
            Animal(
                id=self.next_id,
                x=sx,
                y=sy,
                kind=kind,
                move_cooldown=ANIMAL_MOVE_INTERVAL,
            )
        )
        self.next_id += 1
        occupied.add((sx, sy))
        return True

    def _graze(self, world: World) -> None:
        tree_patches = world.tree_patches()
        deer_caps = [len(p) // ANIMAL_TREES_PER_CAP for p in tree_patches]
        soil_patches = world.soil_riparian_patches()
        boar_caps = [len(p) // BOAR_CELLS_PER_CAP for p in soil_patches]
        occupied = self._occupied()

        deer_buckets: list[list[Animal]] = [[] for _ in tree_patches]
        for animal in self.deer():
            idx = self._patch_for_deer(animal.x, animal.y, tree_patches)
            if idx is not None:
                deer_buckets[idx].append(animal)

        boar_buckets: list[list[Animal]] = [[] for _ in soil_patches]
        for animal in self.boars():
            idx = self._patch_for_boar(animal.x, animal.y, soil_patches)
            if idx is not None:
                boar_buckets[idx].append(animal)

        for animal in list(self.animals):
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
            # Breed into free patch capacity when possible.
            if animal.kind == AnimalKind.DEER:
                idx = self._patch_for_deer(animal.x, animal.y, tree_patches)
                if idx is None or idx >= len(deer_caps):
                    continue
                if len(deer_buckets[idx]) >= deer_caps[idx]:
                    continue
                candidates: list[tuple[int, int]] = []
                seen: set[tuple[int, int]] = set()
                for tx, ty in tree_patches[idx]:
                    for ny, nx in world.neighbourhood(tx, ty, radius=1):
                        if (nx, ny) in seen or not world.is_walkable(nx, ny):
                            continue
                        seen.add((nx, ny))
                        candidates.append((nx, ny))
                if self._try_spawn(AnimalKind.DEER, candidates, occupied):
                    deer_buckets[idx].append(self.animals[-1])
            else:
                idx = self._patch_for_boar(animal.x, animal.y, soil_patches)
                if idx is None or idx >= len(boar_caps):
                    continue
                if len(boar_buckets[idx]) >= boar_caps[idx]:
                    continue
                candidates = list(world.boar_habitat_for_patch(soil_patches[idx]))
                if self._try_spawn(AnimalKind.BOAR, candidates, occupied):
                    boar_buckets[idx].append(self.animals[-1])

    # ------------------------------------------------------------------
    # Population
    # ------------------------------------------------------------------
    def _update_deer_population(self, world: World) -> None:
        patches = world.tree_patches()
        caps = [len(p) // ANIMAL_TREES_PER_CAP for p in patches]
        habitat = world.habitat_cells_near_trees()
        if not habitat:
            self.animals = [a for a in self.animals if a.kind != AnimalKind.DEER]
            return

        buckets: list[list[Animal]] = [[] for _ in patches]
        unassigned: list[Animal] = []
        for animal in self.deer():
            idx = self._patch_for_deer(animal.x, animal.y, patches)
            if idx is None:
                unassigned.append(animal)
            else:
                buckets[idx].append(animal)

        for animal in unassigned:
            if animal in self.animals:
                self.animals.remove(animal)

        for i, group in enumerate(buckets):
            cap = caps[i] if i < len(caps) else 0
            while len(group) > cap:
                victim = group.pop()
                if victim in self.animals:
                    self.animals.remove(victim)

        buckets = [[] for _ in patches]
        for animal in self.deer():
            idx = self._patch_for_deer(animal.x, animal.y, patches)
            if idx is not None:
                buckets[idx].append(animal)

        occupied = self._occupied()
        for i, patch in enumerate(patches):
            cap = caps[i]
            group = buckets[i] if i < len(buckets) else []
            if len(group) >= cap:
                continue
            candidates: list[tuple[int, int]] = []
            seen: set[tuple[int, int]] = set()
            for tx, ty in patch:
                for ny, nx in world.neighbourhood(tx, ty, radius=1):
                    if (nx, ny) in seen or not world.is_walkable(nx, ny):
                        continue
                    seen.add((nx, ny))
                    candidates.append((nx, ny))
            if self._try_spawn(AnimalKind.DEER, candidates, occupied):
                break

    def _update_boar_population(self, world: World) -> None:
        patches = world.soil_riparian_patches()
        if not patches:
            self.animals = [a for a in self.animals if a.kind != AnimalKind.BOAR]
            return
        caps = [len(p) // BOAR_CELLS_PER_CAP for p in patches]
        habitat = world.boar_habitat_cells()
        if not habitat:
            self.animals = [a for a in self.animals if a.kind != AnimalKind.BOAR]
            return

        buckets: list[list[Animal]] = [[] for _ in patches]
        unassigned: list[Animal] = []
        for animal in self.boars():
            idx = self._patch_for_boar(animal.x, animal.y, patches)
            if idx is None:
                unassigned.append(animal)
            else:
                buckets[idx].append(animal)

        for animal in unassigned:
            if animal in self.animals:
                self.animals.remove(animal)

        for i, group in enumerate(buckets):
            cap = caps[i] if i < len(caps) else 0
            while len(group) > cap:
                victim = group.pop()
                if victim in self.animals:
                    self.animals.remove(victim)

        buckets = [[] for _ in patches]
        for animal in self.boars():
            idx = self._patch_for_boar(animal.x, animal.y, patches)
            if idx is not None:
                buckets[idx].append(animal)

        occupied = self._occupied()
        for i, patch in enumerate(patches):
            cap = caps[i]
            group = buckets[i] if i < len(buckets) else []
            if len(group) >= cap or cap <= 0:
                continue
            candidates = list(world.boar_habitat_for_patch(patch))
            if self._try_spawn(AnimalKind.BOAR, candidates, occupied):
                break


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
