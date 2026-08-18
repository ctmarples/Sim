import unittest

from environment import EnvLayer, EnvMaps, temperature_grid
from seasons import DAYS_PER_SEASON
from world import FeatureType, TerrainType, World


class TemperatureLayerTests(unittest.TestCase):
    def setUp(self):
        self.world = World(cols=9, rows=9, seed=23)
        for row in self.world.cells:
            for cell in row:
                cell.terrain = TerrainType.GRASS
                cell.feature = FeatureType.NONE

    def test_open_grassland_follows_yearly_wave(self):
        summer = temperature_grid(self.world, DAYS_PER_SEASON + DAYS_PER_SEASON // 2)
        winter = temperature_grid(self.world, 3 * DAYS_PER_SEASON + DAYS_PER_SEASON // 2)
        self.assertGreater(summer[4][4], winter[4][4])
        self.assertAlmostEqual(summer[4][4], 35.0, places=4)
        self.assertAlmostEqual(winter[4][4], -10.0, places=4)

    def test_forest_damps_summer_and_winter_extremes(self):
        for row in self.world.cells:
            for cell in row:
                cell.terrain = TerrainType.FOREST_FLOOR
                cell.feature = FeatureType.TREE
        summer = temperature_grid(self.world, 42)
        winter = temperature_grid(self.world, 98)
        self.assertLess(summer[4][4], 35.0)
        self.assertGreater(winter[4][4], -10.0)

    def test_large_water_body_stays_cool_and_moderates_shore(self):
        open_summer = temperature_grid(self.world, 42)
        for y in range(9):
            for x in range(4):
                self.world.cells[y][x].terrain = TerrainType.WATER
        summer = temperature_grid(self.world, 42)
        winter = temperature_grid(self.world, 98)
        self.assertLess(summer[4][0], 15.0)
        self.assertGreater(winter[4][0], 0.0)
        self.assertLess(summer[4][4], open_summer[4][4])

    def test_env_map_exposes_and_saves_temperature(self):
        maps = EnvMaps.blank(self.world.rows, self.world.cols)
        maps.temperature = temperature_grid(self.world, 42)
        self.assertEqual(
            maps.value_at(EnvLayer.TEMPERATURE, 4, 4), maps.temperature[4][4]
        )
        loaded = EnvMaps.blank(self.world.rows, self.world.cols)
        loaded.load_save_dict(maps.to_save_dict())
        self.assertEqual(loaded.temperature, maps.temperature)


if __name__ == "__main__":
    unittest.main()
