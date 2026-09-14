"""Spoilage routes to the compost heap; player can craft compost."""

from __future__ import annotations

import unittest

from entities import Building, BuildingKind, Inventory, apply_building_storage
from game import Game
from recipes import COMPOST_HEAP_RECIPES


class CompostSpoilageTests(unittest.TestCase):
    def _farm_with_heap(self) -> tuple[Game, Building, Building]:
        game = Game.__new__(Game)
        game.buildings = {}
        farm = Building(id=1, kind=BuildingKind.FARM, x=4, y=4)
        heap = Building(id=2, kind=BuildingKind.COMPOST_HEAP, x=5, y=4)
        apply_building_storage(farm)
        apply_building_storage(heap)
        farm.linked_extensions = frozenset({BuildingKind.COMPOST_HEAP})
        heap.parent_building_id = farm.id
        game.buildings = {farm.id: farm, heap.id: heap}
        game.record_consumed = lambda *a, **k: None
        game.record_produced = lambda *a, **k: None
        return game, farm, heap

    def test_compost_heap_accepts_spoilage_supply(self) -> None:
        heap = Building(id=2, kind=BuildingKind.COMPOST_HEAP, x=5, y=4)
        apply_building_storage(heap)
        inv = Inventory()
        inv.spoilage = 15
        moved = heap.deposit_supply_from(inv)
        self.assertEqual(moved, 15)
        self.assertEqual(heap.spoilage, 15)
        self.assertEqual(inv.spoilage, 0)

    def test_farm_spoilage_migrates_to_heap(self) -> None:
        game, farm, heap = self._farm_with_heap()
        farm.spoilage = 12
        game._migrate_spoilage_to_heap(farm)
        self.assertEqual(farm.spoilage, 0)
        self.assertEqual(heap.spoilage, 12)

    def test_player_compost_craft_consumes_heap_spoilage(self) -> None:
        game, farm, heap = self._farm_with_heap()
        recipe = COMPOST_HEAP_RECIPES[0]
        heap.spoilage = 10
        self.assertTrue(game._compost_recipe_ready(farm, recipe))
        game._apply_compost_recipe(farm, recipe)
        self.assertEqual(heap.spoilage, 0)
        self.assertEqual(heap.compost, 1)

    def test_farm_does_not_haul_spoilage_when_heap_linked(self) -> None:
        farm = Building(id=1, kind=BuildingKind.FARM, x=4, y=4)
        apply_building_storage(farm)
        farm.linked_extensions = frozenset({BuildingKind.COMPOST_HEAP})
        self.assertNotIn("spoilage", farm.haul_keys())
        self.assertNotIn("spoilage", farm.depositable_keys())

    def test_pantry_spoilage_is_haulable_for_compost(self) -> None:
        pantry = Building(id=3, kind=BuildingKind.PANTRY, x=2, y=2)
        apply_building_storage(pantry)
        pantry.spoilage = 8
        self.assertEqual(pantry.haul_keys(), ("spoilage",))
        self.assertEqual(pantry.haulable_amount("spoilage"), 8)

    def test_farm_does_not_reserve_spoilage_for_compost_recipe(self) -> None:
        farm = Building(id=1, kind=BuildingKind.FARM, x=4, y=4)
        apply_building_storage(farm)
        farm.linked_extensions = frozenset({BuildingKind.COMPOST_HEAP})
        farm.ensure_recipe_state()
        policy = farm._ensure_input_policy()
        self.assertNotIn("spoilage", policy["active"])

    def test_compost_food_toggle_demands_up_to_cap(self) -> None:
        heap = Building(id=2, kind=BuildingKind.COMPOST_HEAP, x=5, y=4, capacity=500)
        apply_building_storage(heap)
        heap.set_compost_food_enabled("blackberries", True)
        heap.set_compost_food_cap("blackberries", 12)
        heap.set_compost_food_reserve("blackberries", 4)
        demand = heap.supply_demand()
        self.assertEqual(demand.get("blackberries"), 12)
        self.assertIn("spoilage", demand)
        self.assertIn("blackberries", heap.depositable_keys())

    def test_season_convert_uses_food_with_spoilage_ratio(self) -> None:
        from entities import HomeStorage

        game, farm, heap = self._farm_with_heap()
        farm.ensure_recipe_state()
        farm.set_recipe_enabled("compost", True)
        game.home_storage = HomeStorage()
        game.home_storage.blackberries = 30
        heap.set_compost_food_enabled("blackberries", True)
        heap.set_compost_food_cap("blackberries", 20)
        heap.set_compost_food_reserve("blackberries", 5)
        heap.spoilage = 5
        # Surplus above reserve = 25, capped to 20 → pull 20 food + 5 spoilage = 25 → 2 batches
        made = game._convert_seasonal_compost()
        self.assertEqual(made, 2)
        self.assertEqual(heap.compost, 2)
        self.assertEqual(game.home_storage.blackberries, 10)  # 30 - 20
        # 25 consumed: 5 spoilage + 20 food; remainder 5 food stays
        self.assertEqual(heap.spoilage, 0)
        self.assertEqual(heap.blackberries, 5)


if __name__ == "__main__":
    unittest.main()
