import unittest

from balance_config import BalanceState, set_active_balance
from subtile_test_map import build_test_map
from subtile_layout import feature_subtile_layout, footprint_scale, object_footprint, tree_icon_scale
from wildlife import AnimalKind, WildlifeManager
from world import FeatureType, TerrainType, World


class HabitatTestMapTests(unittest.TestCase):
    def test_asset_footprints_make_subtiles_visible(self):
        rock = feature_subtile_layout("ROCK", 2, 3)
        sapling = feature_subtile_layout("SAPLING", 2, 3)
        young_tree = feature_subtile_layout("TREE", 2, 3, tree_age_years=3)
        large_tree = feature_subtile_layout("TREE", 2, 3, tree_age_years=8)
        large_rock = feature_subtile_layout("ROCK", 2, 3, deposit=20)
        reed = feature_subtile_layout("REED", 2, 3)
        vine_crop = feature_subtile_layout("WILD_CROP", 2, 3, crop_kind="peas")
        farmed_vine = feature_subtile_layout("CROP_HERB", 2, 3, crop_kind="beans")
        ordinary_crop = feature_subtile_layout("WILD_CROP", 2, 3, crop_kind="wheat")

        self.assertEqual(
            (rock[0], large_rock[0], sapling[0], young_tree[0], large_tree[0], reed[0]),
            (1, 4, 1, 4, 9, 4),
        )
        self.assertEqual((vine_crop[0], farmed_vine[0], ordinary_crop[0]), (4, 9, 1))
        self.assertTrue(object_footprint("ROCK", 2, 3, deposit=5).floor_layer)
        self.assertFalse(object_footprint("ROCK", 2, 3, deposit=20).floor_layer)
        self.assertTrue(object_footprint("WOOD_BUSH", 2, 3).floor_layer)
        self.assertTrue(object_footprint("MUSHROOM", 2, 3).floor_layer)
        self.assertTrue(object_footprint("SAPLING", 2, 3).floor_layer)
        self.assertTrue(
            object_footprint("WILD_CROP", 2, 3, crop_kind="wheat").floor_layer
        )
        self.assertFalse(
            object_footprint("WILD_CROP", 2, 3, crop_kind="peas").floor_layer
        )
        self.assertEqual(
            tuple(footprint_scale(item[0]) for item in (rock, young_tree, large_tree)),
            (1 / 3, 2 / 3, 1.0),
        )
        self.assertEqual((tree_icon_scale(4), tree_icon_scale(9)), (1.0, 1.5))

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
        self.assertGreater(
            sum(len(cell.extra_objects) for row in world.cells for cell in row),
            0,
        )

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
        # A centred 3x3 canopy leaves no parent subcell for another object;
        # hard rock cannot silently overlap it.
        self.assertIsNone(rock)
        self.assertIsNone(plant)
        self.assertEqual(len(cell.extra_objects), 0)
        self.assertTrue(world.is_position_walkable(5.0, 5.34))

    def test_shared_tree_and_wild_plant_capacity_rules(self):
        world = World(cols=10, rows=10, seed=8)
        cell = world.cells[5][5]
        cell.terrain = TerrainType.GRASS
        cell.feature = FeatureType.SAPLING
        cell.object_anchor_slot = 0

        self.assertIsNotNone(world.add_natural_object(5, 5, FeatureType.SAPLING))
        self.assertIsNotNone(world.add_natural_object(5, 5, FeatureType.SAPLING))
        self.assertIsNone(world.add_natural_object(5, 5, FeatureType.SAPLING))

        plants = World(cols=10, rows=10, seed=9)
        plant_cell = plants.cells[5][5]
        plant_cell.terrain = TerrainType.GRASS
        plant_cell.feature = FeatureType.WILD_CROP
        plant_cell.crop_kind = "wheat"
        plant_cell.object_anchor_slot = 0
        additions = [
            plants.add_natural_object(5, 5, FeatureType.WILD_CROP, crop_kind="wheat")
            for _ in range(9)
        ]
        # The family density cap remains three plants, but every accepted
        # plant must now own a different subcell.
        self.assertEqual(sum(obj is not None for obj in additions), 2)
        footprints = [
            object_footprint(
                FeatureType.WILD_CROP.name,
                5,
                5,
                crop_kind="wheat",
                anchor_slot=slot,
            )
            for slot in [plant_cell.object_anchor_slot]
            + [obj.anchor_slot for obj in additions if obj is not None]
        ]
        occupied = [slot for footprint in footprints for slot in footprint.occupied_slots]
        self.assertEqual(len(occupied), len(set(occupied)))

    def test_loose_drop_uses_free_subcell(self):
        world = World(cols=10, rows=10, seed=10)
        cell = world.cells[5][5]
        cell.terrain = TerrainType.GRASS
        cell.feature = FeatureType.SAPLING
        cell.object_anchor_slot = 4

        world.add_meat_deposit(5, 5, 2)

        self.assertIsNotNone(cell.meat_anchor_slot)
        self.assertNotEqual(cell.meat_anchor_slot, 4)

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

    def test_villager_steps_respect_off_centre_hard_anchors(self):
        world = World(cols=10, rows=10, seed=11)
        cell = world.cells[5][5]
        cell.terrain = TerrainType.GRASS
        cell.feature = FeatureType.TREE
        cell.object_anchor_slot = 3  # west-middle subcell
        # The destination centre is open, but the travel segment crosses trunk.
        self.assertTrue(world.is_walkable(5, 5))
        self.assertFalse(world.can_step(4, 5, 5, 5))

    def test_continuous_actor_can_pass_above_trunk_in_adjacent_cell(self):
        world = World(cols=16, rows=44, seed=12)
        cell = world.cells[39][11]
        cell.terrain = TerrainType.FOREST_FLOOR
        cell.feature = FeatureType.TREE
        cell.tree_age_years = 3
        cell.object_anchor_slot = 4

        # Cell-centre AI routing crosses the trunk, but the player's real path
        # at y=38.5658 passes above it (the new_stuck.json regression).
        self.assertFalse(world.can_step(12, 39, 11, 39))
        self.assertTrue(
            world.can_move_between_positions(11.5121, 38.5658, 11.4921, 38.5658)
        )

    def test_soft_secondary_object_keeps_path_cache(self):
        world = World(cols=10, rows=10, seed=13)
        cell = world.cells[5][5]
        cell.terrain = TerrainType.FOREST_FLOOR
        cell.feature = FeatureType.SAPLING
        cell.object_anchor_slot = 0
        world._can_step_cache[(1, 1, 1, 2)] = True

        self.assertIsNotNone(
            world.add_natural_object(5, 5, FeatureType.MUSHROOM)
        )
        self.assertIn((1, 1, 1, 2), world._can_step_cache)

    def test_building_walls_halo_and_bottom_door(self):
        world = World(cols=12, rows=12, seed=13)
        footprint = (3, 3, 3, 2)
        for y in range(3, 5):
            for x in range(3, 6):
                world.cells[y][x].terrain = TerrainType.GRASS
                world.cells[y][x].feature = FeatureType.NONE
        world.set_building_footprints([footprint])

        self.assertFalse(world.is_position_walkable(4.0, 3.0))  # wall/core
        self.assertTrue(world.is_position_walkable(2.7, 3.0))  # 1/3-cell halo
        self.assertTrue(world.is_position_walkable(4.0, 4.0 + 1.0 / 3.0))
        self.assertEqual(world.building_entrance_cell(footprint), (4, 4))
        self.assertTrue(world.is_walkable(4, 4))
        self.assertTrue(world.is_walkable(3, 4))
        self.assertEqual(
            world.building_navigation_position(footprint, 3, 4),
            (3.0 - 1.0 / 3.0, 4.0 + 1.0 / 3.0),
        )
        self.assertTrue(world.can_step(4, 5, 4, 4))
        self.assertTrue(world.can_step(3, 4, 4, 4))

    def test_single_cell_building_has_only_doorway_open(self):
        world = World(cols=8, rows=8, seed=15)
        footprint = (3, 3, 1, 1)
        for y in range(2, 5):
            for x in range(2, 5):
                world.cells[y][x].terrain = TerrainType.GRASS
                world.cells[y][x].feature = FeatureType.NONE
        world.set_building_footprints([footprint])
        self.assertFalse(world.is_position_walkable(3.0, 3.0))
        self.assertTrue(world.is_position_walkable(3.0, 3.0 + 1.0 / 3.0))
        self.assertFalse(world.is_position_walkable(2.84, 3.0))
        self.assertTrue(world.can_step(3, 4, 3, 3))
        self.assertFalse(world.can_step(2, 3, 3, 3))
        self.assertFalse(world.can_step(3, 2, 3, 3))


if __name__ == "__main__":
    unittest.main()
