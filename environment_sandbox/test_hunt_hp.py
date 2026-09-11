"""Multi-strike hunting HP and barn sheaf migration."""

from __future__ import annotations

import random
import unittest
import unittest.mock

from entities import (
    Building,
    BuildingKind,
    arrow_hunt_damage,
    hunt_max_hp,
    hunter_bow_hit_chance,
    spear_hunt_damage,
)
from wildlife import Animal, AnimalKind, AnimalSex, WildlifeManager, WolfMember, WolfPack


class HuntDamageMathTests(unittest.TestCase):
    def test_max_hp_by_kind(self):
        self.assertEqual(hunt_max_hp("DEER"), 2)
        self.assertEqual(hunt_max_hp("BOAR"), 3)
        self.assertEqual(hunt_max_hp("WOLF"), 3)
        self.assertEqual(hunt_max_hp("FOX"), 2)

    def test_spear_damage_is_one_or_two(self):
        rng = random.Random(0)
        values = {spear_hunt_damage(rng) for _ in range(40)}
        self.assertTrue(values <= {1, 2})
        self.assertIn(1, values)

    def test_arrow_damage_exceeds_typical_spear(self):
        rng = random.Random(1)
        arrows = [arrow_hunt_damage(rng) for _ in range(30)]
        self.assertTrue(min(arrows) >= 2)
        self.assertTrue(max(arrows) <= 3)

    def test_bow_hit_chance_rises_with_skill(self):
        self.assertLess(hunter_bow_hit_chance(1), hunter_bow_hit_chance(4))
        self.assertLess(hunter_bow_hit_chance(4), hunter_bow_hit_chance(10))
        self.assertLessEqual(hunter_bow_hit_chance(10), 0.95)


class HuntHpRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.wildlife = WildlifeManager()
        self.wildlife.animals = [
            Animal(id=1, x=5, y=5, kind=AnimalKind.DEER, sex=AnimalSex.MALE),
            Animal(id=2, x=6, y=6, kind=AnimalKind.BOAR, sex=AnimalSex.FEMALE),
        ]
        self.wildlife._index_animals()
        self.wildlife.wolf_packs = [
            WolfPack(
                id=1,
                x=8,
                y=8,
                kind=AnimalKind.FOX,
                members=[
                    WildlifeManager._new_pack_member(
                        AnimalKind.FOX, AnimalSex.MALE, 8, 8
                    )
                ],
            )
        ]

    def test_animal_starts_at_full_hp(self):
        deer = self.wildlife.animals[0]
        self.assertEqual(deer.hp, 2)
        self.assertEqual(deer.max_hp, 2)

    def test_spear_needs_multiple_hits_on_deer(self):
        first = self.wildlife.apply_hunt_damage(1, 1)
        self.assertIsNotNone(first)
        dead, *_rest = first
        self.assertFalse(dead)
        self.assertEqual(self.wildlife.animals[0].hp, 1)
        second = self.wildlife.apply_hunt_damage(1, 1)
        self.assertTrue(second[0])
        self.assertIsNone(self.wildlife.huntable_by_id(1))

    def test_fox_pack_member_hp(self):
        fox = self.wildlife.wolf_packs[0].members[0]
        self.assertEqual(fox.max_hp, 2)
        target_id = self.wildlife._predator_target_id(1, 0)
        outcome = self.wildlife.apply_hunt_damage(target_id, 1)
        self.assertFalse(outcome[0])
        self.assertEqual(fox.hp, 1)


class BarnSheafMigrationTests(unittest.TestCase):
    def test_migrate_sheaves_does_not_require_can_add(self):
        import os

        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        import pygame

        pygame.init()
        pygame.display.set_mode((1, 1))
        from farm_pipeline import barn_sheaf_keys
        from game import Game
        from entities import apply_building_storage

        game = Game(headless=True)
        farm = Building(id=1, kind=BuildingKind.FARM, x=2, y=2)
        barn = Building(id=2, kind=BuildingKind.BARN, x=3, y=3)
        apply_building_storage(farm)
        apply_building_storage(barn)
        keys = barn_sheaf_keys()
        self.assertTrue(keys)
        key = keys[0]
        setattr(farm, key, 3)
        game.buildings = {farm.id: farm, barn.id: barn}
        # Should not raise AttributeError on Building.can_add
        with unittest.mock.patch.object(game, "_linked_barn", return_value=barn):
            game._migrate_sheaves_to_barn(farm)
        self.assertEqual(int(getattr(farm, key, 0)), 0)
        self.assertEqual(int(getattr(barn, key, 0)), 3)


if __name__ == "__main__":
    unittest.main()
