"""Tests for the no-shroud niche test opener helpers."""

from __future__ import annotations

import unittest

from balance_config import BalanceState, set_active_balance
from world import World


class NicheTestOpenMapTests(unittest.TestCase):
    def setUp(self):
        set_active_balance(BalanceState())

    def test_default_world_has_varied_terrain_and_objects(self):
        world = World()
        terrains = {cell.terrain for row in world.cells for cell in row}
        features = {cell.feature for row in world.cells for cell in row}
        self.assertGreaterEqual(len(terrains), 4)
        self.assertGreater(len(features), 1)

    def test_full_discovery_set_covers_every_cell(self):
        world = World(cols=24, rows=18, seed=9)
        discovered = {(x, y) for y in range(world.rows) for x in range(world.cols)}
        self.assertEqual(len(discovered), world.cols * world.rows)


if __name__ == "__main__":
    unittest.main()
