import unittest
from types import SimpleNamespace
from unittest.mock import patch

from game import Game


class _PathWorld:
    rows = 20
    cols = 20

    @staticmethod
    def is_walkable(x, y):
        return 0 <= x < 20 and 0 <= y < 20

    @staticmethod
    def find_path(origin, goal):
        return [goal]


class MapDiscoveryTests(unittest.TestCase):
    def make_game(self):
        game = Game.__new__(Game)
        game.world = _PathWorld()
        game.player = SimpleNamespace(x=10, y=10)
        game.discovered_cells = set()
        return game

    def test_reveal_is_tunable_clipped_and_permanent(self):
        game = self.make_game()
        with patch("game.MAP_DISCOVERY_RADIUS", 1):
            game._reveal_around_player()
            self.assertEqual(len(game.discovered_cells), 5)
            game.player.x = game.player.y = 0
            game._reveal_around_player()
        self.assertIn((11, 10), game.discovered_cells)
        self.assertNotIn((11, 11), game.discovered_cells)
        self.assertIn((0, 0), game.discovered_cells)
        self.assertNotIn((-1, -1), game.discovered_cells)

    def test_common_target_picker_rejects_undiscovered_cells(self):
        game = self.make_game()
        game.discovered_cells = {(4, 4)}
        chosen = game._pick_nearest_reachable(
            (0, 0),
            [(1, 1), (4, 4)],
            pos_fn=lambda pos: pos,
            max_radius=20,
        )
        self.assertEqual(chosen, (4, 4))


if __name__ == "__main__":
    unittest.main()
