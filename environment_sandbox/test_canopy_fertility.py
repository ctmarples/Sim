"""Canopy litter fertility: trees / orchard shrubs raise nearby targets."""

from __future__ import annotations

import unittest

from crops import ORCHARD_CROP_KEYS
from soil import (
    CANOPY_FERTILITY_APPROACH,
    field_fertility_target,
    forest_floor_fertility_target,
    fertility_base_for,
    tick_canopy_fertility,
)
from world import FeatureType, TerrainType, World


class CanopyFertilityTests(unittest.TestCase):
    def test_forest_floor_target_exceeds_soil(self) -> None:
        forest = forest_floor_fertility_target()
        soil = fertility_base_for(TerrainType.SOIL)
        self.assertGreater(forest, soil)

    def test_orchard_shrub_and_neighbour_gain_forest_target(self) -> None:
        world = World(6, 6)
        shrub = world.cells[2][2]
        shrub.terrain = TerrainType.SOIL
        shrub.feature = FeatureType.CROP_HERB
        shrub.crop_kind = next(iter(ORCHARD_CROP_KEYS))
        shrub.fertility = 0.40
        neighbour = world.cells[2][3]
        neighbour.terrain = TerrainType.SOIL
        neighbour.feature = FeatureType.NONE
        neighbour.fertility = 0.40
        distant = world.cells[5][5]
        distant.terrain = TerrainType.SOIL
        distant.fertility = 0.40

        tick_canopy_fertility(world, approach=1.0)

        forest = forest_floor_fertility_target()
        self.assertTrue(shrub.canopy_fertility)
        self.assertTrue(neighbour.canopy_fertility)
        self.assertFalse(distant.canopy_fertility)
        self.assertAlmostEqual(field_fertility_target(shrub), forest)
        self.assertAlmostEqual(field_fertility_target(neighbour), forest)
        self.assertAlmostEqual(field_fertility_target(distant), fertility_base_for(TerrainType.SOIL))
        self.assertAlmostEqual(shrub.fertility, forest)
        self.assertAlmostEqual(neighbour.fertility, forest)
        self.assertAlmostEqual(distant.fertility, 0.40)

    def test_tree_tile_and_field_neighbour_approach_gradually(self) -> None:
        world = World(5, 5)
        tree = world.cells[1][1]
        tree.terrain = TerrainType.FOREST_FLOOR
        tree.feature = FeatureType.TREE
        tree.tree_species = "oak"
        tree.fertility = 0.50
        field = world.cells[1][2]
        field.terrain = TerrainType.SOIL
        field.ploughed = True
        field.fertility = 0.50

        forest = forest_floor_fertility_target()
        before = field.fertility
        tick_canopy_fertility(world)
        expected = before + (forest - before) * CANOPY_FERTILITY_APPROACH
        self.assertTrue(field.canopy_fertility)
        self.assertTrue(tree.canopy_fertility)
        self.assertAlmostEqual(field.fertility, expected, places=5)
        self.assertLess(field.fertility, forest)

        # Further samples keep climbing toward forest floor.
        for _ in range(60):
            tick_canopy_fertility(world)
        self.assertGreater(field.fertility, forest - 0.01)
        self.assertLessEqual(field.fertility, forest)

    def test_compost_overshoot_not_pulled_down(self) -> None:
        world = World(6, 6)
        cell = world.cells[1][1]
        cell.terrain = TerrainType.SOIL
        cell.feature = FeatureType.TREE
        cell.tree_species = "oak"
        cell.fertility = 0.98
        tick_canopy_fertility(world, approach=1.0)
        self.assertTrue(cell.canopy_fertility)
        self.assertAlmostEqual(cell.fertility, 0.98)


if __name__ == "__main__":
    unittest.main()
