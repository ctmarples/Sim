"""Compost extraction contracts, exercised without constructing Game or a UI."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest

from entities import Building, BuildingKind, HomeStorage, apply_building_storage
from food_spoilage import food_quality
from recipes import COMPOST_HEAP_RECIPES
from simulation import compost


class CompostSimulationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.farm = Building(1, BuildingKind.FARM, 4, 4)
        self.heap = Building(2, BuildingKind.COMPOST_HEAP, 5, 4)
        for building in (self.farm, self.heap):
            apply_building_storage(building)
        self.farm.linked_extensions = frozenset({BuildingKind.COMPOST_HEAP})
        self.heap.parent_building_id = self.farm.id
        self.buildings = {self.farm.id: self.farm, self.heap.id: self.heap}
        self.home = HomeStorage()
        self.recipe = next(r for r in COMPOST_HEAP_RECIPES if r.name == "compost")
        self.events: list[tuple[str, str, int]] = []

    def surplus(self, key: str, reserve: int) -> int:
        return max(0, int(getattr(self.home, key, 0)) - max(0, int(reserve)))

    def consumed(self, key: str, amount: int) -> None:
        self.events.append(("consumed", key, amount))

    def produced(self, key: str, amount: int) -> None:
        self.events.append(("produced", key, amount))

    def convert(self) -> int:
        return compost.convert_seasonal_compost(
            self.buildings, self.home,
            storehouse_surplus=self.surplus,
            record_consumed=self.consumed,
            record_produced=self.produced,
        )

    def test_linkage_uses_parent_id_and_preserves_first_match(self) -> None:
        second = Building(3, BuildingKind.COMPOST_HEAP, 6, 4)
        second.parent_building_id = self.farm.id
        self.buildings[second.id] = second
        same_id = Building(self.farm.id, BuildingKind.FARM, 0, 0)
        self.assertIs(compost.linked_compost_heap(same_id, self.buildings), self.heap)
        self.heap.parent_building_id = 99
        self.assertIs(compost.linked_compost_heap(same_id, self.buildings), second)
        self.assertIsNone(compost.linked_compost_heap(second, self.buildings))

    def test_readiness_still_migrates_even_when_recipe_is_not_ready(self) -> None:
        self.farm.spoilage = 5
        self.assertFalse(
            compost.compost_recipe_ready(self.farm, self.recipe, self.buildings)
        )
        self.assertEqual((self.farm.spoilage, self.heap.spoilage), (0, 5))

    def test_migration_stops_at_capacity_and_counts_both_stores(self) -> None:
        # Capacity is measured in stacks; use an explicit per-item cap here.
        self.heap.item_caps["spoilage"] = 500
        self.heap.spoilage = 498
        self.farm.spoilage = 7
        compost.migrate_spoilage_to_heap(self.farm, self.buildings)
        self.assertEqual((self.farm.spoilage, self.heap.spoilage), (5, 500))
        self.assertEqual(
            compost.compost_input_have(self.farm, "spoilage", self.buildings), 505
        )

    def test_no_heap_preserves_readiness_and_apply_asymmetry(self) -> None:
        self.buildings.pop(self.heap.id)
        self.farm.spoilage = 10
        self.assertTrue(
            compost.compost_recipe_ready(self.farm, self.recipe, self.buildings)
        )
        compost.apply_compost_recipe(
            self.farm, self.recipe, self.buildings,
            record_consumed=self.consumed, record_produced=self.produced,
        )
        self.assertEqual(self.farm.spoilage, 10)
        self.assertEqual(self.events, [])

    def test_accounting_callbacks_observe_each_mutation_immediately(self) -> None:
        self.heap.spoilage = 10
        observed = []

        def consumed(key: str, amount: int) -> None:
            observed.append((key, amount, self.heap.spoilage, self.heap.compost))

        def produced(key: str, amount: int) -> None:
            observed.append((key, amount, self.heap.spoilage, self.heap.compost))

        compost.apply_compost_recipe(
            self.farm, self.recipe, self.buildings,
            record_consumed=consumed, record_produced=produced,
        )
        self.assertEqual(observed, [("spoilage", 10, 0, 0), ("compost", 1, 0, 1)])

    def test_unchecked_apply_keeps_existing_partial_input_behaviour(self) -> None:
        # The caller checks readiness; extraction must not add a new guard here.
        self.heap.spoilage = 3
        compost.apply_compost_recipe(
            self.farm, self.recipe, self.buildings,
            record_consumed=self.consumed, record_produced=self.produced,
        )
        self.assertEqual((self.heap.spoilage, self.heap.compost), (0, 1))
        self.assertEqual(self.events, [("consumed", "spoilage", 3), ("produced", "compost", 1)])

    def test_food_pull_respects_reserve_target_capacity_and_quality(self) -> None:
        for stock, reserve, cap, item_cap, expected in (
            (30, 25, 20, 500, 5),  # reserve limits withdrawal
            (30, 0, 12, 500, 10),  # existing two food count toward target
            (30, 0, 20, 4, 2),  # storage's item cap limits withdrawal
        ):
            with self.subTest(stock=stock, reserve=reserve, cap=cap, item_cap=item_cap):
                self.home.blackberries = stock
                self.home.food_quality["blackberries"] = 0.2
                self.heap.blackberries = 2
                self.heap.item_caps["blackberries"] = item_cap
                self.heap.food_quality["blackberries"] = 0.4
                self.heap.set_compost_food_enabled("blackberries", True)
                self.heap.set_compost_food_cap("blackberries", cap)
                self.heap.set_compost_food_reserve("blackberries", reserve)
                moved = compost.pull_compost_food_from_storehouse(
                    self.heap, self.home, storehouse_surplus=self.surplus,
                )
                self.assertEqual(moved, expected)
                self.assertEqual(self.home.blackberries, stock - expected)
                self.assertEqual(self.heap.blackberries, 2 + expected)
                self.assertEqual(food_quality(self.home, "blackberries"), 1.0)
                self.assertEqual(food_quality(self.heap, "blackberries"), 0.4)

    def test_full_heap_does_not_pull_food_or_migrate_spoilage(self) -> None:
        self.heap.compost = 10
        self.heap.capacity = self.heap.cargo_stored_total
        self.farm.spoilage = 5
        self.home.blackberries = 20
        self.heap.set_compost_food_enabled("blackberries", True)
        compost.migrate_spoilage_to_heap(self.farm, self.buildings)
        moved = compost.pull_compost_food_from_storehouse(
            self.heap, self.home, storehouse_surplus=self.surplus,
        )
        self.assertEqual(moved, 0)
        self.assertEqual((self.farm.spoilage, self.heap.spoilage), (5, 0))
        self.assertEqual((self.home.blackberries, self.heap.blackberries), (20, 0))

    def test_seasonal_conversion_preserves_food_order_and_remainder(self) -> None:
        self.heap.spoilage = 5
        for key, amount in (("meat", 8), ("blackberries", 12)):
            self.heap.set_compost_food_enabled(key, True)
            setattr(self.heap, key, amount)
            self.heap.food_quality[key] = 0.2
        self.assertEqual(self.convert(), 2)
        self.assertEqual((self.heap.spoilage, self.heap.meat, self.heap.blackberries), (0, 0, 5))
        self.assertEqual(food_quality(self.heap, "blackberries"), 1.0)
        self.assertEqual(self.events, [
            ("consumed", "spoilage", 5),
            ("consumed", "meat", 8),
            ("consumed", "blackberries", 7),
            ("produced", "compost", 2),
        ])

    def test_disabled_recipe_does_not_migrate_or_pull(self) -> None:
        self.farm.set_recipe_enabled(self.recipe.name, False)
        self.farm.spoilage = 10
        self.home.blackberries = 20
        self.heap.set_compost_food_enabled("blackberries", True)
        self.assertEqual(self.convert(), 0)
        self.assertEqual((self.farm.spoilage, self.heap.spoilage), (10, 0))
        self.assertEqual((self.home.blackberries, self.heap.blackberries), (20, 0))
        self.assertEqual(self.events, [])

    def test_multiple_farms_share_storehouse_in_building_order(self) -> None:
        other_farm = Building(3, BuildingKind.FARM, 7, 4)
        other_heap = Building(4, BuildingKind.COMPOST_HEAP, 8, 4)
        apply_building_storage(other_farm)
        apply_building_storage(other_heap)
        other_farm.linked_extensions = frozenset({BuildingKind.COMPOST_HEAP})
        other_heap.parent_building_id = other_farm.id
        # Higher IDs are processed first when inserted first, as before.
        self.buildings = {3: other_farm, 4: other_heap, 1: self.farm, 2: self.heap}
        for heap in (other_heap, self.heap):
            heap.set_compost_food_enabled("blackberries", True)
            heap.set_compost_food_cap("blackberries", 20)
        self.home.blackberries = 30
        self.assertEqual(self.convert(), 3)
        self.assertEqual((other_heap.compost, self.heap.compost), (2, 1))
        self.assertEqual(self.home.blackberries, 0)

    def test_can_execute_with_pygame_and_game_imports_forbidden(self) -> None:
        # A clean process catches transitive imports masked by the other tests.
        script = '''
import importlib.abc
import random
import sys

class BlockPresentation(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'pygame', 'game', 'ui', 'status_effects_ui'}:
            raise AssertionError('Presentation dependency: ' + fullname)

sys.meta_path.insert(0, BlockPresentation())
from test_simulation_compost import CompostSimulationTests
case = CompostSimulationTests()
case.setUp()
case.heap.spoilage = 25
before_rng = random.getstate()
assert case.convert() == 2
assert case.heap.spoilage == 5
assert random.getstate() == before_rng
assert 'pygame' not in sys.modules and 'game' not in sys.modules
'''
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parent,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
