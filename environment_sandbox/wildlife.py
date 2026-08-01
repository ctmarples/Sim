"""Wildlife that roams near tree patches.

Animals prefer walkable cells within one square of a tree.
Population grows slowly toward a per-patch cap of 1 animal per
ANIMAL_TREES_PER_CAP trees in each connected tree patch.

Future extension points:
- species / predation
- hunting / biodiversity indicators
- seasonal migration
"""

from __future__ import annotations

import random
from dataclasses import dataclass

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
    FISH_GROWTH_INTERVAL,
    FISH_MOVE_INTERVAL,
    FISH_WATER_PER_CAP,
    RANDOM_SEED,
)
from world import World


@dataclass
class Animal:
    id: int
    x: int
    y: int
    move_cooldown: int = 0


class WildlifeManager:
    """Spawn, cull, and roam animals relative to tree patches."""

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

    def patch_capacity(self, world: World) -> dict[int, int]:
        """Map patch index → max animals for that patch."""
        patches = world.tree_patches()
        return {
            i: len(patch) // ANIMAL_TREES_PER_CAP
            for i, patch in enumerate(patches)
        }

    def total_capacity(self, world: World) -> int:
        return sum(self.patch_capacity(world).values())

    def _patch_for_cell(
        self, x: int, y: int, patches: list[list[tuple[int, int]]]
    ) -> int | None:
        """Nearest patch that has a tree within 1 of this cell."""
        best: tuple[int, int] | None = None  # (dist, patch_index)
        for i, patch in enumerate(patches):
            for tx, ty in patch:
                dist = max(abs(tx - x), abs(ty - y))
                if dist <= 1:
                    if best is None or dist < best[0]:
                        best = (dist, i)
        return best[1] if best is not None else None

    def _animals_per_patch(self, world: World) -> list[list[Animal]]:
        patches = world.tree_patches()
        buckets: list[list[Animal]] = [[] for _ in patches]
        unassigned: list[Animal] = []
        for animal in self.animals:
            idx = self._patch_for_cell(animal.x, animal.y, patches)
            if idx is None:
                unassigned.append(animal)
            else:
                buckets[idx].append(animal)
        # Unassigned animals (no nearby trees) count against nothing for spawn,
        # but are preferred for despawn.
        self._unassigned = unassigned
        return buckets

    def animal_at(self, x: int, y: int) -> Animal | None:
        for animal in self.animals:
            if animal.x == x and animal.y == y:
                return animal
        return None

    def animals_in_area(self, contains) -> list[Animal]:
        """Return animals whose position is inside the callable contains(x, y)."""
        return [a for a in self.animals if contains(a.x, a.y)]

    def kill_animal(self, animal_id: int) -> tuple[int, int] | None:
        """Remove animal; return its (x, y) or None if missing."""
        for i, animal in enumerate(self.animals):
            if animal.id == animal_id:
                pos = (animal.x, animal.y)
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
            self._update_population(world)

    def _move_animals(self, world: World, day: float = 0.0) -> None:
        slow = 1 + int(2 * freeze_amount(day)) if animals_slow(day) else 1
        move_interval = ANIMAL_MOVE_INTERVAL * slow
        # Habitat set is expensive; refresh every few seconds of sim time.
        age = getattr(self, "_habitat_age", 0)
        if age <= 0 or not hasattr(self, "_habitat_cache"):
            self._habitat_cache = set(world.habitat_cells_near_trees())
            self._habitat_age = 40
        else:
            self._habitat_age = age - 1
        habitat = self._habitat_cache
        if not habitat:
            # No tree habitat — animals stay put (population tick will cull).
            for animal in self.animals:
                if animal.move_cooldown > 0:
                    animal.move_cooldown -= 1
            return

        for animal in self.animals:
            if animal.move_cooldown > 0:
                animal.move_cooldown -= 1
                continue
            # Prefer a random neighbour that is still tree habitat; else any habitat cell.
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

    def _update_population(self, world: World) -> None:
        patches = world.tree_patches()
        caps = [len(p) // ANIMAL_TREES_PER_CAP for p in patches]
        buckets = self._animals_per_patch(world)
        unassigned = getattr(self, "_unassigned", [])

        # Despawn animals with no habitat first, then excess per patch.
        habitat = world.habitat_cells_near_trees()
        if not habitat:
            self.animals.clear()
            return

        for animal in list(unassigned):
            self.animals.remove(animal)

        for i, group in enumerate(buckets):
            cap = caps[i] if i < len(caps) else 0
            while len(group) > cap:
                victim = group.pop()
                if victim in self.animals:
                    self.animals.remove(victim)

        # Refresh after culls
        buckets = self._animals_per_patch(world)

        # Spawn into under-capacity patches.
        for i, patch in enumerate(patches):
            cap = caps[i]
            group = buckets[i] if i < len(buckets) else []
            if len(group) >= cap:
                continue
            # Spawn cells: walkable within 1 of this patch's trees.
            candidates: list[tuple[int, int]] = []
            seen: set[tuple[int, int]] = set()
            for tx, ty in patch:
                for ny, nx in world.neighbourhood(tx, ty, radius=1):
                    if (nx, ny) in seen:
                        continue
                    if world.is_walkable(nx, ny):
                        seen.add((nx, ny))
                        candidates.append((nx, ny))
            if not candidates:
                continue
            # One spawn attempt per growth tick per underfilled patch.
            sx, sy = self.rng.choice(candidates)
            animal = Animal(id=self.next_id, x=sx, y=sy, move_cooldown=ANIMAL_MOVE_INTERVAL)
            self.next_id += 1
            self.animals.append(animal)
            # Only one spawn per growth tick overall to keep growth slow.
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
        # Frozen water: fish stay put under the ice.
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
