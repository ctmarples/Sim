import unittest
from unittest.mock import Mock

from entities import Inventory
from game import Game
from wildlife import AnimalKind
from wildlife import AnimalSex, WildlifeManager, WolfMember, WolfPack


class HuntingToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.game = Game.__new__(Game)
        self.game.record_produced = Mock()

    def test_rabbit_without_knife_gives_meat_but_no_fur(self) -> None:
        inventory = Inventory()

        applied = self.game._apply_hunt_recipe_to_inventory(
            inventory, "rabbit", has_knife=False
        )

        self.assertTrue(applied)
        self.assertEqual(inventory.meat, 3)
        self.assertEqual(inventory.fur, 0)

    def test_rabbit_with_knife_gives_full_yield(self) -> None:
        inventory = Inventory()

        applied = self.game._apply_hunt_recipe_to_inventory(
            inventory, "rabbit", has_knife=True
        )

        self.assertTrue(applied)
        self.assertEqual(inventory.meat, 3)
        self.assertEqual(inventory.fur, 1)

    def test_kill_without_knife_drops_meat_but_no_hide(self) -> None:
        self.game.world = Mock()

        meat = self.game._drop_hunt_yields(
            4, 7, AnimalKind.DEER, has_knife=False
        )

        self.assertEqual(meat, 3)
        self.game.world.add_meat_deposit.assert_called_once_with(4, 7, 3)
        self.game.world.add_hide_deposit.assert_not_called()
        self.game.world.add_fur_deposit.assert_not_called()

    def test_hunter_tools_only_require_a_weapon(self) -> None:
        villager = Mock()
        self.game._ensure_hunter_weapon = Mock(return_value=True)
        self.game._ensure_work_tool = Mock(return_value=False)

        self.assertTrue(self.game._ensure_hunter_tools(villager))
        self.game._ensure_hunter_weapon.assert_called_once_with(villager)
        self.game._ensure_work_tool.assert_not_called()

    def test_player_finds_wolf_member_within_one_square(self) -> None:
        wildlife = WildlifeManager(seed=1)
        wildlife.wolf_packs = [
            WolfPack(
                3,
                20,
                20,
                [WolfMember(AnimalSex.MALE, 6, 5)],
                kind=AnimalKind.WOLF,
            )
        ]
        self.game.wildlife = wildlife

        target = self.game._adjacent_animal(5, 5)

        self.assertIsNotNone(target)
        self.assertEqual(target.kind, AnimalKind.WOLF)
        self.assertEqual((target.x, target.y), (6, 5))


if __name__ == "__main__":
    unittest.main()
