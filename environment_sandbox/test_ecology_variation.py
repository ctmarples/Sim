"""Ecology variation, moisture reach, and soil-texture overlay ramp."""

from __future__ import annotations

import unittest

from developer_tools.terrain_editor import (
    DEFAULTS,
    adjust_terrain_ecology_band_part,
    invalidate_ecology_cache,
    terrain_band,
    terrain_value,
)
from environment import (
    RAIN_TO_MOISTURE_GAIN,
    WATER_MOISTURE_BOOST,
    WATER_MOISTURE_RADIUS,
    soil_moisture_grid,
    update_soil_moisture_from_rain,
)
from indicators import OverlayMode, overlay_colour
from settings import (
    COLOUR_SOIL_TEXTURE_CLAY,
    COLOUR_SOIL_TEXTURE_LOAM,
    COLOUR_SOIL_TEXTURE_SANDY,
)
from world import FeatureType, TerrainType, World


class SoilTextureOverlayTests(unittest.TestCase):
    def test_texture_ramp_yellow_white_orange(self):
        self.assertEqual(overlay_colour(OverlayMode.SOIL_TEXTURE, 0.0), COLOUR_SOIL_TEXTURE_SANDY)
        self.assertEqual(overlay_colour(OverlayMode.SOIL_TEXTURE, 0.5), COLOUR_SOIL_TEXTURE_LOAM)
        self.assertEqual(overlay_colour(OverlayMode.SOIL_TEXTURE, 1.0), COLOUR_SOIL_TEXTURE_CLAY)


class FertilityVariationTests(unittest.TestCase):
    def setUp(self):
        invalidate_ecology_cache()

    def test_fertility_varies_within_terrain(self):
        world = World(cols=24, rows=18, seed=41)
        for row in world.cells:
            for cell in row:
                cell.terrain = TerrainType.GRASS
        world.init_fertility()
        values = [cell.fertility for row in world.cells for cell in row]
        self.assertGreater(max(values) - min(values), 0.12)
        self.assertLess(max(values), 0.95)
        self.assertGreater(min(values), 0.35)

    def test_authored_bases_are_not_uniform_ones(self):
        self.assertLess(DEFAULTS["GRASS"]["fertility"]["centre"], 0.95)
        self.assertNotAlmostEqual(
            DEFAULTS["GRASS"]["fertility"]["centre"],
            DEFAULTS["FOREST_FLOOR"]["fertility"]["centre"],
        )


class MoistureVariationTests(unittest.TestCase):
    def setUp(self):
        invalidate_ecology_cache()
        self.world = World(cols=12, rows=7, seed=17)
        for row in self.world.cells:
            for cell in row:
                cell.terrain = TerrainType.GRASS
                cell.feature = FeatureType.NONE
        self.world.cells[3][0].terrain = TerrainType.WATER

    def test_water_influence_reaches_farther(self):
        self.assertGreaterEqual(WATER_MOISTURE_RADIUS, 7.0)
        self.assertGreaterEqual(WATER_MOISTURE_BOOST, 0.4)
        grid = soil_moisture_grid(self.world, 0)
        self.assertEqual(grid[3][0], 1.0)
        self.assertGreater(grid[3][5], grid[3][10])
        self.assertGreater(grid[3][6], 0.45)

    def test_within_terrain_moisture_is_mottled(self):
        grid = soil_moisture_grid(self.world, 0)
        band = [grid[1][x] for x in range(4, 11)]
        self.assertGreater(max(band) - min(band), 0.05)

    def test_rain_gain_is_stronger(self):
        self.assertGreaterEqual(RAIN_TO_MOISTURE_GAIN, 0.5)
        moisture = [[0.3] * self.world.cols for _ in range(self.world.rows)]
        rainfall = [[0.8] * self.world.cols for _ in range(self.world.rows)]
        temperature = [[12.0] * self.world.cols for _ in range(self.world.rows)]
        after = update_soil_moisture_from_rain(
            self.world, moisture, rainfall, temperature, 0
        )
        self.assertGreater(after[3][5], 0.55)


class TerrainEcologyBandTests(unittest.TestCase):
    def setUp(self):
        invalidate_ecology_cache()

    def tearDown(self):
        invalidate_ecology_cache()

    def test_bands_expose_centre_and_spread(self):
        centre, spread = terrain_band("GRASS", "fertility")
        self.assertAlmostEqual(centre, terrain_value("GRASS", "fertility"))
        self.assertGreater(spread, 0.0)

    def test_spread_adjust_updates_cache(self):
        before = terrain_band("GRASS", "fertility")[1]
        after = adjust_terrain_ecology_band_part(
            "GRASS", "fertility", "spread", 0.02, persist=False
        )
        self.assertAlmostEqual(after, before + 0.02)
        self.assertAlmostEqual(terrain_band("GRASS", "fertility")[1], after)


if __name__ == "__main__":
    unittest.main()
