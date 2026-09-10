"""Recipe progress display regression tests."""

from __future__ import annotations

import unittest

from entities import Building, BuildingKind, Villager, VillagerState, apply_building_storage
from game import Game


class RecipeProgressDisplayTests(unittest.TestCase):
    def test_active_mill_worker_never_rewinds_saved_two_thirds(self) -> None:
        game = Game.__new__(Game)
        game.player_craft_building_id = None
        game._villager_work_interval = lambda worker: 50

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
        worker.work_in_progress = True
        worker.work_anchor = (0, 0)

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

    def test_kitchen_partial_waiting_for_supply_does_not_block_ready_food(self) -> None:
        kitchen = Building(id=7, kind=BuildingKind.KITCHEN, x=0, y=0)
        apply_building_storage(kitchen)
        kitchen.ensure_recipe_state()
        kitchen.fuel_wood = 5
        kitchen.onion = 2
        kitchen.garlic = 1
        kitchen.cabbage = 2
        kitchen.carrot = 2
        kitchen.recipe_progress["grilled_meat"] = 1

        picked = kitchen.craftable_recipe()

        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertEqual(picked.name, "vegetable_soup")

    def test_partial_tailor_order_allows_upstream_thread_recipe(self) -> None:
        tailor = Building(id=23, kind=BuildingKind.TAILOR, x=0, y=0)
        apply_building_storage(tailor)
        tailor.ensure_recipe_state()
        tailor.flax = 2
        tailor.recipe_progress["light_shirt"] = 1

        picked = tailor.craftable_recipe()

        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertEqual(picked.name, "linen_thread")

    def test_capped_partial_order_does_not_freeze_other_recipes(self) -> None:
        bench = Building(id=3, kind=BuildingKind.CRAFT_BENCH, x=0, y=0)
        apply_building_storage(bench)
        bench.ensure_recipe_state()
        bench.hemp = 1
        bench.flax = 1
        bench.recipe_progress["knife"] = 1
        bench.item_caps["knife"] = 10

        picked = bench.craftable_recipe(stock_amounts={"knife": 10, "twine": 0})

        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertEqual(picked.name, "twine")

    def test_lower_priority_recipes_are_weighted_without_starving(self) -> None:
        kitchen = Building(id=7, kind=BuildingKind.KITCHEN, x=0, y=0)
        apply_building_storage(kitchen)
        kitchen.ensure_recipe_state()
        kitchen.fuel_wood = 20
        kitchen.mushrooms = 20
        kitchen.sage = 20
        kitchen.wheat_flour = 20
        kitchen.meat = 20
        kitchen.set_recipe_priority("mushroom_stew", 1)
        kitchen.set_recipe_priority("bread_wheat", 2)
        kitchen.set_recipe_priority("grilled_meat", 3)
        for name in kitchen.recipe_enabled:
            kitchen.recipe_enabled[name] = name in {
                "mushroom_stew",
                "bread_wheat",
                "grilled_meat",
            }

        picks: list[str] = []
        for _ in range(3):
            recipe = kitchen.craftable_recipe()
            self.assertIsNotNone(recipe)
            assert recipe is not None
            picks.append(recipe.name)
            for _step in range(recipe.work_steps()):
                kitchen.advance_recipe_progress(recipe)

        self.assertEqual(picks, ["mushroom_stew", "bread_wheat", "grilled_meat"])


if __name__ == "__main__":
    unittest.main()
