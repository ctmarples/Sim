import unittest
from types import SimpleNamespace

from entities import Villager
from game import Game
from world import TerrainType, World


class VillagerUnstuckTests(unittest.TestCase):
    def setUp(self):
        self.game = Game.__new__(Game)
        self.game.world = World(cols=9, rows=9, seed=21)
        for row in self.game.world.cells:
            for cell in row:
                cell.terrain = TerrainType.GRASS

    def test_moves_trapped_villager_to_nearest_open_space(self):
        villager = Villager(id=1, x=4, y=4)
        villager.world_x = 4.0
        villager.world_y = 4.0
        self.game.villagers = [villager]
        for dx, dy in ((0, 0), (0, -1), (1, 0), (0, 1), (-1, 0)):
            self.game.world.cells[4 + dy][4 + dx].terrain = TerrainType.WATER

        moved = self.game._unstick_villagers()

        self.assertEqual(moved, 1)
        self.assertNotEqual((villager.x, villager.y), (4, 4))
        self.assertTrue(
            self.game.world.is_position_walkable(villager.world_x, villager.world_y)
        )
        self.assertIsNone(getattr(villager, "_path_cache", None))

    def test_leaves_mobile_villager_in_place(self):
        villager = Villager(id=1, x=4, y=4)
        villager.world_x = 4.0
        villager.world_y = 4.0
        self.game.villagers = [villager]

        self.assertEqual(self.game._unstick_villagers(), 0)
        self.assertEqual((villager.x, villager.y), (4, 4))

    def test_sleeping_villager_uses_exterior_when_home_door_is_sealed(self):
        villager = Villager(id=1, x=7, y=7)
        villager.target = (4, 4)
        self.game.villagers = [villager]
        self.game.world.set_building_footprints(
            [(4, 4, 1, 1), (4, 5, 1, 2)]
        )
        house = SimpleNamespace(center_cell=lambda: (4, 4))

        recovered = self.game._recover_villager_sleep_route(villager, house)

        self.assertTrue(recovered)
        self.assertNotEqual(villager.target, (4, 4))
        self.assertIsNotNone(
            self.game.world.find_path((villager.x, villager.y), villager.target)
        )


if __name__ == "__main__":
    unittest.main()
