import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from entities import VillagerState
from game import Game


class FoodSeekingTests(unittest.TestCase):
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

    def test_priority_food_in_store_is_sought_before_carried_fallback(self):
        game = Game.__new__(Game)
        game.world = SimpleNamespace(home_pos=(5, 5))
        game.home_storage = SimpleNamespace(meat=1)
        game.buildings = {}
        game._eat_random_from = Mock(return_value=1)
        game._inventory_needs_store_deposit = Mock(return_value=True)
        game._villager_needs_home_restock = Mock(return_value=False)
        game._step_villager_toward = Mock(return_value=True)

        villager = SimpleNamespace(
            x=1,
            y=1,
            inventory=SimpleNamespace(cabbage=1, is_full=False),
            required_foods=["meat"],
            favourite_foods=[],
            seeking_food=True,
            target=None,
            work_cooldown=0,
            state=VillagerState.IDLE,
        )

        game._update_seek_food(villager)

        game._eat_random_from.assert_not_called()
        game._step_villager_toward.assert_called_once_with(villager, (5, 5))
        self.assertEqual(villager.target, (5, 5))


if __name__ == "__main__":
    unittest.main()
