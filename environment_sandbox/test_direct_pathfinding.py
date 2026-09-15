import unittest

from world import TerrainType, World


class DirectPathfindingTests(unittest.TestCase):
    def setUp(self):
        self.world = World(cols=8, rows=8, seed=9)
        for row in self.world.cells:
            for cell in row:
                cell.terrain = TerrainType.GRASS

    def test_offset_route_uses_diagonals_before_straight_steps(self):
        path = self.world.find_path((6, 5), (2, 3))

        self.assertEqual(path, [(5, 4), (4, 3), (3, 3), (2, 3)])

    def test_diagonal_does_not_cut_between_blocked_terrain(self):
        self.world.cells[1][2].terrain = TerrainType.WATER
        self.world.cells[2][1].terrain = TerrainType.WATER

        self.assertFalse(self.world.can_step(1, 1, 2, 2))

    def test_detour_does_not_overshoot_with_global_diagonal_bias(self):
        """Equal-length BFS must not zigzag past the goal line."""
        big = World(cols=50, rows=50, seed=9)
        for row in big.cells:
            for cell in row:
                cell.terrain = TerrainType.GRASS
        for y in range(5, 40):
            big.cells[y][20].terrain = TerrainType.WATER
        big.cells[22][20].terrain = TerrainType.GRASS
        path = big.find_path((5, 10), (35, 30))
        self.assertIsNotNone(path)
        ys = [p[1] for p in path]
        self.assertLessEqual(max(ys), 30)


if __name__ == "__main__":
    unittest.main()
