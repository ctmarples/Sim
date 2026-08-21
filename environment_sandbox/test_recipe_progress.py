"""Recipe progress display regression tests."""

from __future__ import annotations

import unittest

from entities import Building, BuildingKind, Villager, VillagerState, apply_building_storage
from game import Game


class RecipeProgressDisplayTests(unittest.TestCase):
    def test_active_mill_worker_never_rewinds_saved_two_thirds(self) -> None:
        game = Game.__new__(Game)
        game.player_craft_building_id = None

        mill = Building(id=21, kind=BuildingKind.MILL, x=0, y=0)
        apply_building_storage(mill)
        mill.ensure_recipe_state()
        mill.recipe_progress["wheat_flour"] = 2
        game.buildings = {mill.id: mill}

        worker = Villager(id=5, x=0, y=0)
        worker.building_id = mill.id
        worker.state = VillagerState.WORKING
        worker.craft_recipe_name = "wheat_flour"
        worker.work_cooldown = 25

        shown = game._smooth_recipe_progress(mill, [worker])

        self.assertGreaterEqual(
            shown["wheat_flour"], mill.recipe_progress_fraction("wheat_flour")
        )

    def test_hauling_cooldown_does_not_rewind_partial_recipe(self) -> None:
        game = Game.__new__(Game)
        game.player_craft_building_id = None

        mill = Building(id=21, kind=BuildingKind.MILL, x=0, y=0)
        apply_building_storage(mill)
        mill.ensure_recipe_state()
        mill.recipe_progress["wheat_flour"] = 2

        worker = Villager(id=5, x=0, y=0)
        worker.building_id = mill.id
        worker.state = VillagerState.HAULING
        worker.craft_recipe_name = "wheat_flour"
        worker.work_cooldown = 25

        shown = game._smooth_recipe_progress(mill, [worker])

        self.assertEqual(
            shown["wheat_flour"], mill.recipe_progress_fraction("wheat_flour")
        )

    def test_partial_recipe_wins_over_new_higher_priority_recipe(self) -> None:
        kitchen = Building(id=7, kind=BuildingKind.KITCHEN, x=0, y=0)
        apply_building_storage(kitchen)
        kitchen.ensure_recipe_state()
        kitchen.fuel_wood = 5
        kitchen.meat = 2
        kitchen.onion = 2
        kitchen.cabbage = 1
        kitchen.carrot = 1
        kitchen.recipe_progress["grilled_meat"] = 1

        picked = kitchen.craftable_recipe()

        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertEqual(picked.name, "grilled_meat")

    def test_partial_recipe_waits_for_supply_without_starting_another(self) -> None:
        kitchen = Building(id=7, kind=BuildingKind.KITCHEN, x=0, y=0)
        apply_building_storage(kitchen)
        kitchen.ensure_recipe_state()
        kitchen.fuel_wood = 5
        kitchen.onion = 2
        kitchen.garlic = 1
        kitchen.cabbage = 2
        kitchen.carrot = 2
        kitchen.recipe_progress["grilled_meat"] = 1

        self.assertIsNone(kitchen.craftable_recipe())


if __name__ == "__main__":
    unittest.main()
