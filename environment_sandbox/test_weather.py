import unittest

from environment import EnvLayer, EnvMaps, rainfall_modifier_grid
from weather import WeatherState
from world import FeatureType, TerrainType, World


class WeatherTests(unittest.TestCase):
    def test_weather_is_deterministic_and_persistent_across_save(self):
        first = WeatherState(seed=91)
        sequence = [first.advance_day(day % 112) for day in range(40)]
        replay = WeatherState(seed=91)
        self.assertEqual(sequence, [replay.advance_day(day % 112) for day in range(40)])
        restored = WeatherState(seed=0)
        restored.load_dict(first.to_dict())
        self.assertEqual(first.advance_day(41), restored.advance_day(41))
        self.assertTrue(any(value > 0.0 for value in sequence))
        self.assertTrue(any(value == 0.0 for value in sequence))
        first_rain = next(i for i, value in enumerate(sequence) if value > 0.0)
        self.assertEqual(
            sequence[first_rain:first_rain + 3],
            [sequence[first_rain]] * 3,
        )
        self.assertEqual(sequence[first_rain + 3], 0.0)

    def test_rain_cells_create_strong_local_variation(self):
        weather = WeatherState(seed=3, raining=True, intensity=0.8)
        weather.rain_cells = [(0.2, 0.5, 0.18, 1.1)]
        grid = weather.localisation_grid(20, 20)
        values = [value for row in grid for value in row]
        self.assertGreater(max(values), 0.9)
        self.assertLess(min(values), 0.2)

    def test_landscape_changes_effective_rainfall(self):
        world = World(cols=7, rows=5, seed=4)
        for row in world.cells:
            for cell in row:
                cell.terrain = TerrainType.GRASS
                cell.feature = FeatureType.NONE
        base = rainfall_modifier_grid(world)
        world.cells[2][0].terrain = TerrainType.WATER
        world.cells[2][5].feature = FeatureType.TREE
        changed = rainfall_modifier_grid(world)
        self.assertGreater(changed[2][1], base[2][1])
        self.assertLess(changed[2][5], base[2][5])

    def test_rain_recharges_persistent_soil_moisture(self):
        world = World(cols=5, rows=5, seed=5)
        for row in world.cells:
            for cell in row:
                cell.terrain = TerrainType.SOIL
                cell.feature = FeatureType.NONE
        maps = EnvMaps.blank(world.rows, world.cols)
        maps.soil_moisture = [[0.2] * world.cols for _ in range(world.rows)]
        maps.temperature = [[18.0] * world.cols for _ in range(world.rows)]
        maps.rainfall_modifiers = rainfall_modifier_grid(world)
        maps.update_weather(world, 0.8, 20)
        wet = maps.value_at(EnvLayer.SOIL_MOISTURE, 2, 2)
        maps.update_weather(world, 0.0, 21)
        dry = maps.value_at(EnvLayer.SOIL_MOISTURE, 2, 2)
        self.assertGreater(wet, 0.2)
        self.assertLess(dry, wet)
        self.assertGreater(maps.value_at(EnvLayer.RAINFALL, 2, 2), -0.01)


if __name__ == "__main__":
    unittest.main()
