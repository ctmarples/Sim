"""Hemp (and wild forage crops) should appear on generated maps."""

from __future__ import annotations

import unittest

from world import FeatureType, TerrainType, World


class TestHempFlora(unittest.TestCase):
    def test_generate_seeds_hemp_on_open_land(self) -> None:
        world = World(48, 48, seed=7)
        world.generate()
        hemp = sum(
            1
            for row in world.cells
            for cell in row
            if cell.crop_kind == "hemp"
            and cell.feature == FeatureType.WILD_CROP
        )
        self.assertGreater(
            hemp,
            0,
            "fresh maps should already have wild hemp after generate()",
        )

    def test_hemp_can_establish_on_grass_and_meadow(self) -> None:
        from developer_tools.plant_editor import PlantEditorService
        from wild_species import WILD_BY_KEY
        from world import refresh_wild_crops_by_terrain, WILD_CROPS_BY_TERRAIN

        ok, _msg = PlantEditorService().load()
        self.assertTrue(ok)
        refresh_wild_crops_by_terrain()
        species = WILD_BY_KEY["hemp"]
        self.assertIn("MEADOW", species.terrains)
        self.assertIn("GRASS", species.terrains)
        self.assertIn("hemp", WILD_CROPS_BY_TERRAIN.get(TerrainType.MEADOW, ()))
        self.assertIn("hemp", WILD_CROPS_BY_TERRAIN.get(TerrainType.GRASS, ()))


if __name__ == "__main__":
    unittest.main()
