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

from settings import (
    ANIMAL_GROWTH_INTERVAL,
    ANIMAL_MOVE_INTERVAL,
    ANIMAL_TREES_PER_CAP,
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

    def tick(self, world: World) -> None:
        self._move_animals(world)
        self.growth_timer -= 1
        if self.growth_timer <= 0:
            self.growth_timer = ANIMAL_GROWTH_INTERVAL
            self._update_population(world)

    def _move_animals(self, world: World) -> None:
        habitat = set(world.habitat_cells_near_trees())
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
            animal.move_cooldown = ANIMAL_MOVE_INTERVAL

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
