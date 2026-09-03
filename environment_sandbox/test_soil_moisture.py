import unittest

from environment import EnvLayer, EnvMaps, soil_moisture_grid
from seasons import DAYS_PER_SEASON
from world import FeatureType, TerrainType, World


class SoilMoistureTests(unittest.TestCase):
    def test_environment_save_records_terrain_ecology_version(self):
        from environment import EnvMaps
        from developer_tools.terrain_editor import ecology_signature
        saved=EnvMaps(1,1).to_save_dict()
        self.assertEqual(saved["terrain_ecology_signature"],ecology_signature())

    def setUp(self):
        self.world = World(cols=7, rows=5, seed=22)
        for row in self.world.cells:
            for cell in row:
                cell.terrain = TerrainType.GRASS
                cell.feature = FeatureType.NONE
        self.world.cells[2][0].terrain = TerrainType.RIVER

    def test_water_proximity_and_terrain_affect_moisture(self):
        grid = soil_moisture_grid(self.world, 0)
        self.assertEqual(grid[2][0], 1.0)
        self.assertGreater(grid[2][1], grid[2][5])
        self.world.cells[2][5].terrain = TerrainType.FOREST_FLOOR
        wetter = soil_moisture_grid(self.world, 0)
        self.assertGreater(wetter[2][5], grid[2][5])

    def test_features_and_environmental_conditions_affect_moisture(self):
        spring = soil_moisture_grid(self.world, 0)
        self.world.cells[2][5].feature = FeatureType.TREE
        tree = soil_moisture_grid(self.world, 0)
        summer = soil_moisture_grid(self.world, DAYS_PER_SEASON)
        self.assertGreater(tree[2][5], spring[2][5])
        self.assertGreater(tree[2][5], summer[2][5])

    def test_env_map_exposes_and_saves_layer(self):
        maps = EnvMaps.blank(self.world.rows, self.world.cols)
        maps.soil_moisture = soil_moisture_grid(self.world, 0)
        self.assertEqual(maps.value_at(EnvLayer.SOIL_MOISTURE, 0, 2), 1.0)
        saved = maps.to_save_dict()
        loaded = EnvMaps.blank(self.world.rows, self.world.cols)
        loaded.load_save_dict(saved)
        self.assertEqual(loaded.soil_moisture, maps.soil_moisture)


if __name__ == "__main__":
    unittest.main()
