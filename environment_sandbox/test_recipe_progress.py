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

    def test_multiple_workers_combine_mid_swing_progress(self) -> None:
        """Two cooks mid-swing on the same recipe advance the bar together."""
        game = Game.__new__(Game)
        game.player_craft_building_id = None
        game._villager_work_interval = lambda worker: 50

        kitchen = Building(id=8, kind=BuildingKind.KITCHEN, x=0, y=0)
        apply_building_storage(kitchen)
        kitchen.ensure_recipe_state()
        kitchen.recipe_progress["mushroom_stew"] = 0
        game.buildings = {kitchen.id: kitchen}

        workers = []
        for vid in (1, 2):
            worker = Villager(id=vid, x=0, y=0)
            worker.building_id = kitchen.id
            worker.state = VillagerState.WORKING
            worker.craft_recipe_name = "mushroom_stew"
            worker.work_cooldown = 25  # half-way through swing
            worker.work_in_progress = True
            worker.work_anchor = (0, 0)
            workers.append(worker)

        shown = game._smooth_recipe_progress(kitchen, workers)
        # Two half-swings ≈ one full step on a 3-step stew.
        steps = 3
        for recipe in kitchen.known_recipes():
            if recipe.name == "mushroom_stew":
                steps = max(1, recipe.work_steps())
                break
        self.assertAlmostEqual(shown["mushroom_stew"], min(1.0, 1.0 / steps), places=5)

    def test_player_help_combines_with_villager_craft_progress(self) -> None:
        game = Game.__new__(Game)
        game._villager_work_interval = lambda worker: 40
        game._player_work_interval = lambda *a, **k: 40

        kitchen = Building(id=8, kind=BuildingKind.KITCHEN, x=0, y=0)
        apply_building_storage(kitchen)
        kitchen.ensure_recipe_state()
        kitchen.recipe_progress["mushroom_stew"] = 1
        game.buildings = {kitchen.id: kitchen}
        game.player_craft_building_id = kitchen.id
        game.player_craft_recipe = "mushroom_stew"
        game.player = type("P", (), {"work_cooldown": 20})()

        worker = Villager(id=3, x=0, y=0)
        worker.building_id = kitchen.id
        worker.state = VillagerState.WORKING
        worker.craft_recipe_name = "mushroom_stew"
        worker.work_cooldown = 20
        worker.work_in_progress = True
        worker.work_anchor = (0, 0)

        shown = game._smooth_recipe_progress(kitchen, [worker])
        steps = 3
        for recipe in kitchen.known_recipes():
            if recipe.name == "mushroom_stew":
                steps = max(1, recipe.work_steps())
                break
        # completed 1 + two half-phases = 2 steps of work.
        self.assertAlmostEqual(shown["mushroom_stew"], min(1.0, 2.0 / steps), places=5)

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
        kitchen.meat = 1
        kitchen.onion = 1
        kitchen.cabbage = 1
        kitchen.carrot = 1
        kitchen.recipe_progress["stew"] = 1

        picked = kitchen.craftable_recipe()

        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertEqual(picked.name, "stew")

    def test_kitchen_partial_waiting_for_supply_does_not_block_ready_food(self) -> None:
        kitchen = Building(id=7, kind=BuildingKind.KITCHEN, x=0, y=0)
        apply_building_storage(kitchen)
        kitchen.ensure_recipe_state()
        kitchen.fuel_wood = 5
        kitchen.cabbage = 1
        kitchen.turnip = 1
        kitchen.carrot = 1
        kitchen.onion = 1
        kitchen.recipe_progress["stew"] = 1

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

    def test_higher_priority_recipes_always_beat_lower_when_ready(self) -> None:
        kitchen = Building(id=7, kind=BuildingKind.KITCHEN, x=0, y=0)
        apply_building_storage(kitchen)
        kitchen.ensure_recipe_state()
        kitchen.fuel_wood = 20
        kitchen.fish = 20
        kitchen.onion = 20
        kitchen.garlic = 20
        kitchen.blackberries = 20
        kitchen.honey = 20
        kitchen.set_recipe_priority("fish_stew", 1)
        kitchen.set_recipe_priority("blackberry_jam", 2)
        for name in kitchen.recipe_enabled:
            kitchen.recipe_enabled[name] = name in {"fish_stew", "blackberry_jam"}

        picks: list[str] = []
        for _ in range(4):
            recipe = kitchen.craftable_recipe()
            self.assertIsNotNone(recipe)
            assert recipe is not None
            picks.append(recipe.name)
            for _step in range(recipe.work_steps()):
                kitchen.advance_recipe_progress(recipe)

        self.assertEqual(picks, ["fish_stew", "fish_stew", "fish_stew", "fish_stew"])

    def test_lower_priority_runs_when_higher_cannot(self) -> None:
        kitchen = Building(id=7, kind=BuildingKind.KITCHEN, x=0, y=0)
        apply_building_storage(kitchen)
        kitchen.ensure_recipe_state()
        kitchen.fuel_wood = 5
        kitchen.blackberries = 6
        kitchen.honey = 2
        kitchen.set_recipe_priority("fish_stew", 1)
        kitchen.set_recipe_priority("blackberry_jam", 2)
        for name in kitchen.recipe_enabled:
            kitchen.recipe_enabled[name] = name in {"fish_stew", "blackberry_jam"}

        recipe = kitchen.craftable_recipe()
        self.assertIsNotNone(recipe)
        assert recipe is not None
        self.assertEqual(recipe.name, "blackberry_jam")


if __name__ == "__main__":
    unittest.main()
