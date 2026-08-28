import unittest

from balance_config import BalanceState, set_active_balance
from subtile_test_map import build_test_map
from subtile_layout import feature_subtile_layout, footprint_scale
from wildlife import AnimalKind, WildlifeManager
from world import FeatureType, TerrainType, World


class HabitatTestMapTests(unittest.TestCase):
    def test_asset_footprints_make_subtiles_visible(self):
        rock = feature_subtile_layout("ROCK", 2, 3)
        sapling = feature_subtile_layout("SAPLING", 2, 3)
        young_tree = feature_subtile_layout("TREE", 2, 3, tree_age_years=3)
        large_tree = feature_subtile_layout("TREE", 2, 3, tree_age_years=8)
        large_rock = feature_subtile_layout("ROCK", 2, 3, deposit=20)

        self.assertEqual(
            (rock[0], large_rock[0], sapling[0], young_tree[0], large_tree[0]),
            (1, 4, 1, 4, 9),
        )
        self.assertEqual(
            tuple(footprint_scale(item[0]) for item in (rock, young_tree, large_tree)),
            (1 / 3, 2 / 3, 1.0),
        )

    def test_real_map_builds_habitats_and_seeds_forest_wildlife(self):
        set_active_balance(BalanceState())
        generated = build_test_map()
        world = World(
            cols=generated.options.width,
            rows=generated.options.height,
            seed=generated.options.seed,
        )
        generated.apply_to_world(world)
        wildlife = WildlifeManager(seed=generated.options.seed)
        wildlife.refresh_habitats(world)
        wildlife.seed_breeding_grounds(world)

        self.assertEqual((world.cols, world.rows), (24, 18))
        self.assertGreaterEqual(len(wildlife.breeding_grounds(AnimalKind.DEER)), 2)
        self.assertGreaterEqual(len(wildlife.breeding_grounds(AnimalKind.BOAR)), 2)
        self.assertGreater(wildlife.count_kind(AnimalKind.DEER), 0)
        self.assertGreater(wildlife.count_kind(AnimalKind.BOAR), 0)
        self.assertGreater(len(wildlife.colonies), 0)

    def test_tree_anchor_stays_fixed_while_footprint_grows(self):
        young = feature_subtile_layout("TREE", 4, 6, tree_age_years=3, anchor_slot=2)
        mature = feature_subtile_layout("TREE", 4, 6, tree_age_years=8, anchor_slot=2)
        self.assertEqual((young[0], mature[0]), (4, 9))
        # The 3x3 crown is centred on the unchanged east-side trunk anchor and
        # therefore overhangs its parent ecology cell.
        self.assertEqual(mature[1:], (5.0 / 6.0, 1.0 / 6.0))
        self.assertGreater(mature[1] + footprint_scale(mature[0]) / 2.0, 1.0)

    def test_hard_anchor_collision_and_overlapping_objects(self):
        world = World(cols=10, rows=10, seed=7)
        cell = world.cells[5][5]
        cell.terrain = TerrainType.GRASS
        cell.feature = FeatureType.TREE
        cell.tree_age_years = 8
        cell.object_anchor_slot = 4

        self.assertFalse(world.is_position_walkable(5.0, 5.0))
        self.assertTrue(world.is_position_walkable(5.4, 5.0))

        rock = world.add_natural_object(
            5, 5, FeatureType.ROCK, anchor_slot=8, deposit=24
        )
        plant = world.add_natural_object(
            5, 5, FeatureType.WILD_CROP, anchor_slot=7
        )
        self.assertIsNotNone(rock)
        self.assertIsNotNone(plant)
        self.assertEqual(len(cell.extra_objects), 2)
        self.assertFalse(world.is_position_walkable(5.34, 5.34))
        self.assertTrue(world.is_position_walkable(5.0, 5.34))

    def test_small_natural_objects_are_walkable(self):
        world = World(cols=10, rows=10, seed=9)
        cell = world.cells[5][5]
        cell.terrain = TerrainType.GRASS
        cell.feature = FeatureType.ROCK
        cell.deposit = 10
        cell.object_anchor_slot = 4
        world.add_natural_object(5, 5, FeatureType.WOOD_BUSH, anchor_slot=3)
        world.add_natural_object(5, 5, FeatureType.CROP_HERB, anchor_slot=5)
        self.assertTrue(world.is_position_walkable(5.0, 5.0))


if __name__ == "__main__":
    unittest.main()
