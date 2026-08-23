import unittest
from unittest.mock import Mock

import pygame

from entities import Player, WorkPriority
from game import Game
from toolbar import Toolbar


class ControlModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.font.init()

    def make_game(self) -> Game:
        game = Game.__new__(Game)
        game.player = Player(4, 5)
        game.villagers = []
        game.control_mode = "dog"
        game._god_dog_villager = None
        game.world = Mock(cols=100, rows=80)
        game.camera = Mock()
        game._set_status = Mock()
        return game

    def test_god_mode_adds_assignable_labourer_proxy(self) -> None:
        game = self.make_game()

        game._set_control_mode("god")

        dog = game._god_dog_villager
        self.assertEqual(game.control_mode, "god")
        self.assertIn(dog, game.villagers)
        self.assertIs(dog.inventory, game.player.inventory)
        self.assertEqual(dog.name, "Player Dog")
        self.assertEqual(dog.workplace_plan[0].kind, WorkPriority.LABOURER)

    def test_dog_mode_syncs_position_and_recenters_camera(self) -> None:
        game = self.make_game()
        game._set_control_mode("god")
        dog = game._god_dog_villager
        dog.x, dog.y = 17, 23

        game._set_control_mode("dog")

        self.assertEqual((game.player.x, game.player.y), (17, 23))
        self.assertNotIn(dog, game.villagers)
        game.camera.center_on.assert_called_with(17, 23, 100, 80)

    def test_toolbar_exposes_both_control_modes(self) -> None:
        toolbar = Toolbar()
        actions = {button.action for button in toolbar._buttons}
        self.assertIn("control_dog", actions)
        self.assertIn("control_god", actions)


if __name__ == "__main__":
    unittest.main()
