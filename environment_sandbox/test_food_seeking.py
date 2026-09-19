import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from entities import Inventory, VillagerState
from game import Game


class FoodSeekingTests(unittest.TestCase):
    def test_empty_hungry_hauler_may_interrupt_pickup_to_eat(self):
        game = Game.__new__(Game)
        game.villagers = []
        game.ticks_per_day = 240
        game.day_tick = 0
        game._tick_job_change_deposit = Mock(return_value=False)
        game._satiation_decay = Mock(return_value=0.0)
        game._idle_decision_pending = Mock(return_value=False)
        game._update_seek_food = Mock()
        game._update_villager_wellbeing = Mock()
        game._rebuild_villager_claim_snapshot = Mock()
        game._reset_tick_claims = Mock()
        game._village_food_amounts = Mock(return_value={})
        game._villager_needs_ai_pass = Mock(return_value=True)
        game._food_count = Mock(return_value=0)
        game._find_nearest_food_store = Mock(return_value=(5, 5))
        game._find_nearest_map_food = Mock(return_value=None)
        game._begin_villager_building_entry = Mock()
        game._reconcile_seasonal_workplace = Mock()
        game._calendar_rate_per_tick = Mock(return_value=0.0)
        game._trait_hunger_mult = Mock(return_value=1.0)
        game.buildings = {}

        villager = SimpleNamespace(
            id=1,
            inventory=Inventory(),
            state=VillagerState.HAULING,
            move_cooldown=0,
            work_cooldown=0,
            decision_cooldown=0,
            fish_bait_ticks=0,
            satiation=0.0,
            food_hunger_mult=1.0,
            seeking_food=True,
            needs_food=Mock(return_value=True),
        )
        game.villagers = [villager]

        game._update_villagers()

        game._update_seek_food.assert_called_once_with(villager)

    def test_hungry_villager_eats_carried_food_before_depositing_cargo(self):
        game = Game.__new__(Game)
        game.world = SimpleNamespace(home_pos=(5, 5))
        game._food_count = Mock(return_value=1)
        game._find_nearest_food_store = Mock(return_value=None)
        game._eat_random_from = Mock(return_value=1)
        game._villager_work_interval = Mock(return_value=12)
        game._inventory_needs_store_deposit = Mock(return_value=True)
        game._villager_needs_home_restock = Mock(return_value=True)
        game._step_villager_toward = Mock()

        villager = SimpleNamespace(
            inventory=SimpleNamespace(cabbage=1, sage=3),
            craft_recipe_name="leather_satchel",
            seeking_food=True,
            target=(9, 9),
            work_cooldown=0,
            state=VillagerState.IDLE,
        )

        game._update_seek_food(villager)

        game._eat_random_from.assert_called_once_with(villager.inventory, villager)
        game._inventory_needs_store_deposit.assert_not_called()
        game._step_villager_toward.assert_not_called()
        self.assertFalse(villager.seeking_food)
        self.assertIsNone(villager.target)
        self.assertEqual(villager.work_cooldown, 12)
        self.assertEqual(villager.state, VillagerState.WORKING)
        self.assertIsNone(villager.craft_recipe_name)

    def test_priority_food_in_store_is_sought_before_carried_fallback(self):
        game = Game.__new__(Game)
        game.world = SimpleNamespace(home_pos=(5, 5))
        game.home_storage = SimpleNamespace(roasted_turnips=1)
        game.buildings = {}
        game._eat_random_from = Mock(return_value=1)
        game._inventory_needs_store_deposit = Mock(return_value=True)
        game._villager_needs_home_restock = Mock(return_value=False)
        game._step_villager_toward = Mock(return_value=True)
        game._food_count = Mock(return_value=1)
        game._find_nearest_food_store = Mock(
            side_effect=lambda v, preferred_only=False: (5, 5) if preferred_only else None
        )
        game._food_store_at = Mock(return_value=SimpleNamespace(roasted_turnips=1))

        villager = SimpleNamespace(
            x=1,
            y=1,
            inventory=SimpleNamespace(cabbage=1, is_full=False),
            required_foods=["t1"],
            favourite_foods=[],
            seeking_food=True,
            satiation=0.5,
            target=None,
            work_cooldown=0,
            state=VillagerState.IDLE,
            building_id=None,
        )

        game._update_seek_food(villager)

        game._eat_random_from.assert_not_called()
        game._step_villager_toward.assert_called_once_with(villager, (5, 5))
        self.assertEqual(villager.target, (5, 5))

    def test_critical_hunger_skips_preference_detour(self):
        game = Game.__new__(Game)
        game.world = SimpleNamespace(home_pos=(5, 5))
        game._food_count = Mock(return_value=0)
        game._find_nearest_food_store = Mock(return_value=(5, 5))
        game._find_nearest_map_food = Mock(return_value=None)
        game._food_store_at = Mock(return_value=SimpleNamespace(cabbage=1))
        game._inventory_needs_store_deposit = Mock(return_value=False)
        game._villager_needs_home_restock = Mock(return_value=False)
        game._step_villager_toward = Mock(return_value=True)

        villager = SimpleNamespace(
            x=4,
            y=5,
            inventory=SimpleNamespace(is_full=False),
            satiation=0.1,
            seeking_food=True,
            target=None,
            work_cooldown=0,
            state=VillagerState.IDLE,
        )

        game._update_seek_food(villager)

        self.assertNotIn(
            unittest.mock.call(villager, preferred_only=True),
            game._find_nearest_food_store.call_args_list,
        )
        game._find_nearest_food_store.assert_called_once_with(villager)
        game._step_villager_toward.assert_called_once_with(villager, (5, 5))

    def test_arrived_hungry_worker_eats_during_work_cooldown(self):
        game = Game.__new__(Game)
        store = SimpleNamespace(fish=1)
        game.world = SimpleNamespace(home_pos=(5, 5))
        game._food_count = Mock(return_value=1)
        game._find_nearest_food_store = Mock(return_value=(2, 3))
        game._food_store_at = Mock(return_value=store)
        game._inventory_needs_store_deposit = Mock(return_value=False)
        game._villager_needs_home_restock = Mock(return_value=False)
        game._eat_random_from = Mock(return_value=1)
        game._villager_work_interval = Mock(return_value=12)

        villager = SimpleNamespace(
            x=2,
            y=3,
            inventory=SimpleNamespace(is_full=False),
            favourite_foods=[],
            required_foods=[],
            satiation=0.2,
            seeking_food=True,
            target=(2, 3),
            work_cooldown=143,
            state=VillagerState.WORKING,
            needs_food=Mock(return_value=True),
        )

        game._update_seek_food(villager)

        game._eat_random_from.assert_called_once_with(store, villager)
        self.assertFalse(villager.seeking_food)
        self.assertIsNone(villager.target)
        self.assertEqual(villager.work_cooldown, 12)

    def test_map_food_skips_depleted_cells_still_in_index(self) -> None:
        game = Game.__new__(Game)
        depleted = SimpleNamespace()
        live = SimpleNamespace()
        game.world = SimpleNamespace(
            get_cell=Mock(side_effect=lambda x, y: depleted if (x, y) == (1, 1) else live)
        )
        game.scenario = SimpleNamespace(
            villager_foraging_near_home=Mock(return_value=True)
        )
        game._forage_cells_for_key = Mock(
            side_effect=lambda key: [(1, 1), (4, 4)] if key == "blackberries" else []
        )
        game._forage_key_for_cell = Mock(
            side_effect=lambda cell: None if cell is depleted else "blackberries"
        )
        game._pick_nearest_reachable = Mock(return_value=(4, 4))

        villager = SimpleNamespace(x=0, y=0)
        self.assertEqual(game._find_nearest_map_food(villager), (4, 4))
        game._pick_nearest_reachable.assert_called_once()
        self.assertEqual(game._pick_nearest_reachable.call_args.args[1], [(4, 4)])

    def test_failed_map_food_collect_clears_target_and_index(self) -> None:
        game = Game.__new__(Game)
        game.world = SimpleNamespace(home_pos=(9, 9))
        game._food_count = Mock(return_value=0)
        game._find_nearest_food_store = Mock(return_value=None)
        game._find_nearest_map_food = Mock(return_value=(3, 3))
        game._food_store_at = Mock(return_value=None)
        game._inventory_needs_store_deposit = Mock(return_value=False)
        game._villager_needs_home_restock = Mock(return_value=False)
        game._collect_map_food = Mock(return_value=False)
        game._invalidate_forage_index = Mock()

        villager = SimpleNamespace(
            x=3,
            y=3,
            inventory=SimpleNamespace(is_full=False),
            satiation=0.0,
            seeking_food=True,
            target=(3, 3),
            work_cooldown=0,
            state=VillagerState.WORKING,
            needs_food=Mock(return_value=True),
        )

        game._update_seek_food(villager)

        self.assertIsNone(villager.target)
        game._invalidate_forage_index.assert_called_once()
        self.assertTrue(villager.seeking_food)


if __name__ == "__main__":
    unittest.main()
