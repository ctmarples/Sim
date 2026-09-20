import unittest

from balance_config import BALANCE_CATEGORIES, BalanceState, set_active_balance
from wild_species import WILD_SPECIES
from world import FeatureType, TerrainType, World


class FloraBalanceTests(unittest.TestCase):
    def test_flora_category_has_one_tile_cap_per_terrain(self):
        flora = next(category for category in BALANCE_CATEGORIES if category.id == "flora")
        self.assertEqual(
            {param.key for param in flora.params},
            {f"FLORA_TILE_CAP_{terrain.name}" for terrain in TerrainType},
        )
        for param in flora.params:
            self.assertEqual(param.default, 0.20)
            self.assertEqual(param.minimum, 0.0)
            self.assertEqual(param.maximum, 1.0)
            self.assertEqual(param.step, 0.01)

    def test_flora_species_weights_cover_spawnable_catalogue(self):
        flora = next(
            category for category in BALANCE_CATEGORIES if category.id == "flora_species"
        )
        expected = {
            f"FLORA_SPECIES_WEIGHT_{s.key}"
            for s in WILD_SPECIES
            if float(s.spawn_peak) > 0.0
        }
        self.assertEqual({param.key for param in flora.params}, expected)

    def test_zero_tile_cap_prevents_new_flora_spawns(self):
        balance = BalanceState()
        balance.set("FLORA_TILE_CAP_GRASS", 0.0, autosave=False)
        set_active_balance(balance)
        try:
            world = World(cols=12, rows=12, seed=8)
            for row in world.cells:
                for cell in row:
                    cell.terrain = TerrainType.GRASS
                    cell.feature = FeatureType.NONE
                    cell.crop_kind = None
                    cell.extra_objects.clear()
            for day in range(0, 112, 7):
                world._tick_herbs_seasonal(float(day))
            self.assertTrue(
                all(cell.feature == FeatureType.NONE and not cell.extra_objects
                    for row in world.cells for cell in row)
            )
        finally:
            set_active_balance(BalanceState())

    def test_respawn_flora_preserves_trees_and_rebuilds_current_flora(self):
        set_active_balance(BalanceState())
        world = World(cols=20, rows=20, seed=19)
        tree_cells = {
            (x, y)
            for y, row in enumerate(world.cells)
            for x, cell in enumerate(row)
            if cell.feature in (FeatureType.TREE, FeatureType.SAPLING)
        }
        count = world.respawn_flora(42.0)
        self.assertGreaterEqual(count, 0)
        self.assertTrue(all(
            world.cells[y][x].feature in (FeatureType.TREE, FeatureType.SAPLING)
            for x, y in tree_cells
        ))

    def test_loaded_flora_reconciliation_removes_wrong_terrain_match(self):
        world = World(cols=8, rows=8, seed=3)
        cell = world.cells[0][0]
        cell.terrain = TerrainType.ROCK
        cell.feature = FeatureType.WILD_CROP
        cell.crop_kind = "wheat"
        self.assertEqual(world.reconcile_flora_with_catalogue(), 1)
        self.assertEqual(cell.feature, FeatureType.NONE)


if __name__ == "__main__":
    unittest.main()
