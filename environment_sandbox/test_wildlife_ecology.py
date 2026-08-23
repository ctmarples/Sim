import unittest

from balance_config import BalanceState, set_active_balance
from wildlife import Animal, AnimalKind, AnimalSex, ForestHabitat, WildlifeManager
from world import FeatureType, TerrainType, World


class WildlifeEcologyTests(unittest.TestCase):
    def setUp(self):
        self.balance = BalanceState()
        set_active_balance(self.balance)
        self.world = World(cols=8, rows=8, seed=41)
        for row in self.world.cells:
            for cell in row:
                cell.terrain = TerrainType.FOREST_FLOOR
                cell.feature = FeatureType.NONE
                cell.disturbance = 0.0
        self.wildlife = WildlifeManager(seed=41)

    def test_deer_browses_and_removes_sapling(self):
        self.balance.set("WILDLIFE_DEER_GRAZE_CHANCE", 1.0)
        self.balance.set("WILDLIFE_DEER_SAPLING_BROWSE_CHANCE", 1.0)
        self.world.cells[3][4].feature = FeatureType.SAPLING
        self.world.cells[3][4].tree_species = "oak"
        self.wildlife.animals = [
            Animal(1, 3, 3, AnimalKind.DEER, AnimalSex.FEMALE, patch_id=0)
        ]
        self.wildlife._graze(self.world)
        self.assertEqual(self.world.cells[3][4].feature, FeatureType.NONE)
        self.assertIsNone(self.world.cells[3][4].tree_species)

    def test_boar_prefers_and_removes_mushroom(self):
        self.balance.set("WILDLIFE_BOAR_GRAZE_CHANCE", 1.0)
        self.world.cells[3][4].feature = FeatureType.MUSHROOM
        self.wildlife.animals = [
            Animal(1, 3, 3, AnimalKind.BOAR, AnimalSex.MALE, patch_id=0)
        ]
        self.wildlife._graze(self.world)
        self.assertEqual(self.world.cells[3][4].feature, FeatureType.NONE)

    def test_no_forage_prevents_breeding(self):
        for row in self.world.cells:
            for cell in row:
                cell.terrain = TerrainType.SOIL
        tiles = [(x, y) for y in range(2, 6) for x in range(2, 6)]
        habitat = ForestHabitat(0, tiles, tiles, set(tiles), set(tiles), tiles, set(tiles), set(tiles))
        self.wildlife.habitats = [habitat]
        self.wildlife.animals = [
            Animal(1, 3, 3, AnimalKind.DEER, AnimalSex.MALE, 0, 2, 224),
            Animal(2, 4, 3, AnimalKind.DEER, AnimalSex.FEMALE, 0, 1, 224),
        ]
        self.wildlife._index_animals()
        self.balance.set("WILDLIFE_BREED_CHANCE", 1.0)
        self.wildlife._breed(self.world)
        self.assertEqual(len(self.wildlife.animals), 2)

    def test_old_tree_becomes_fallen_wood(self):
        self.balance.set("TREE_LIFESPAN_YEARS", 4)
        self.balance.set("TREE_OLD_AGE_DEATH_CHANCE", 1.0)
        cell = self.world.cells[3][3]
        cell.feature = FeatureType.TREE
        cell.tree_species = "oak"
        cell.tree_age_years = 3
        self.assertEqual(self.world.age_trees_one_year(), 1)
        self.assertEqual(cell.feature, FeatureType.WOOD_BUSH)
        self.assertGreater(cell.growth_ticks, 0)

    def test_existing_trees_receive_accelerated_lifecycle_ages(self):
        self.world.cells[2][2].feature = FeatureType.TREE
        self.world.cells[2][2].tree_age_years = 0
        self.world.cells[2][3].feature = FeatureType.TREE
        self.world.cells[2][3].tree_age_years = 0
        assigned = self.world.ensure_tree_ages()
        self.assertEqual(assigned, 2)
        self.assertTrue(1 <= self.world.cells[2][2].tree_age_years <= 5)
        self.assertTrue(1 <= self.world.cells[2][3].tree_age_years <= 5)


if __name__ == "__main__":
    unittest.main()
