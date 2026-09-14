import unittest

from balance_config import BalanceState, set_active_balance
from entities import arm_cell_step_visual, entity_draw_xy, note_cell_step
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

    def test_wildlife_tracks_fractional_world_position_between_cells(self):
        deer = Animal(1, 2, 3, AnimalKind.DEER)
        note_cell_step(deer, 3, 3)
        deer.move_cooldown = 10
        arm_cell_step_visual(deer, 10)
        deer.move_cooldown = 5

        self.assertEqual(entity_draw_xy(deer), (2.5, 3.0))
        self.assertEqual((deer.x, deer.y), (3, 3))
        self.assertEqual((deer.world_x, deer.world_y), (2.5, 3.0))

    def test_wildlife_pathfinder_uses_direct_diagonal_route(self):
        path = self.wildlife._bfs_path(
            self.world, 1, 1, 5, 5, occupied=set()
        )

        self.assertEqual(path, [(2, 2), (3, 3), (4, 4), (5, 5)])

    def test_wildlife_step_can_end_away_from_cell_centre(self):
        deer = Animal(1, 2, 3, AnimalKind.DEER)
        occupied = {(2, 3)}

        self.assertTrue(self.wildlife._place_animal(self.world, deer, 3, 3, occupied))
        deer.move_cooldown = 10
        arm_cell_step_visual(deer, 10)
        deer.move_cooldown = 0
        wx, wy = entity_draw_xy(deer)

        self.assertEqual((deer.x, deer.y), (3, 3))
        self.assertTrue(abs(wx - 3.0) > 1e-6 or abs(wy - 3.0) > 1e-6)

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

    def test_healthy_empty_habitat_produces_three_births(self):
        tiles = [(x, y) for y in range(8) for x in range(8)]
        habitat = ForestHabitat(
            0, tiles, tiles, set(tiles), set(tiles),
            tiles, set(tiles), set(tiles),
        )
        self.wildlife.habitats = [habitat]
        self.wildlife.animals = [
            Animal(
                1, 2, 2, AnimalKind.BOAR, AnimalSex.MALE,
                patch_id=0, mate_id=2, age_days=224,
            ),
            Animal(
                2, 3, 2, AnimalKind.BOAR, AnimalSex.FEMALE,
                patch_id=0, mate_id=1, age_days=224,
            ),
        ]
        self.wildlife._index_animals()
        self.balance.set("WILDLIFE_BREED_CHANCE", 1.0)

        self.wildlife._breed(self.world)

        self.assertEqual(len(self.wildlife.animals), 5)

    def test_habitat_refresh_adds_mate_when_residents_are_same_sex(self):
        tiles = [(x, y) for y in range(8) for x in range(8)]
        habitat = ForestHabitat(
            0, tiles, tiles, set(tiles), set(tiles),
            tiles, set(tiles), set(tiles),
        )
        self.wildlife.habitats = [habitat]
        self.wildlife.animals = [
            Animal(1, 2, 2, AnimalKind.BOAR, AnimalSex.MALE, patch_id=0),
            Animal(2, 3, 2, AnimalKind.BOAR, AnimalSex.MALE, patch_id=0),
        ]
        self.wildlife.next_id = 3

        spawned = self.wildlife.ensure_lone_animals_have_mates(self.world)

        boars = [a for a in self.wildlife.animals if a.kind == AnimalKind.BOAR]
        self.assertEqual(spawned, 1)
        self.assertEqual(len(boars), 3)
        self.assertEqual({a.sex for a in boars}, {AnimalSex.MALE, AnimalSex.FEMALE})

    def test_habitat_refresh_repopulates_when_all_deer_are_migrating(self):
        tiles = [(x, y) for y in range(8) for x in range(8)]
        habitat = ForestHabitat(
            0, tiles, tiles, set(tiles), set(tiles),
            tiles, set(tiles), set(tiles),
        )
        self.wildlife.habitats = [habitat]
        self.wildlife.animals = [
            Animal(
                1, 2, 2, AnimalKind.DEER, AnimalSex.MALE,
                patch_id=None, mate_id=2, migrate_home_id=4,
            ),
            Animal(
                2, 3, 2, AnimalKind.DEER, AnimalSex.FEMALE,
                patch_id=None, mate_id=1, migrate_home_id=4,
            ),
        ]
        self.wildlife.next_id = 3

        spawned = self.wildlife.ensure_lone_animals_have_mates(self.world)

        settled = [
            a for a in self.wildlife.animals
            if a.kind == AnimalKind.DEER and a.patch_id == habitat.id
        ]
        self.assertEqual(spawned, 2)
        self.assertEqual(len(settled), 2)
        self.assertEqual(
            {a.sex for a in settled},
            {AnimalSex.MALE, AnimalSex.FEMALE},
        )

    def test_birth_count_uses_new_world_habitat_potential(self):
        small_tiles = [(x, 1) for x in range(1, 7)]
        large_tiles = [(x, y) for y in range(2, 8) for x in range(1, 8)]
        occupied = ForestHabitat(
            0, small_tiles, small_tiles, set(small_tiles), set(small_tiles),
            small_tiles, set(small_tiles), set(small_tiles),
        )
        new_habitat = ForestHabitat(
            1, large_tiles, large_tiles, set(large_tiles), set(large_tiles),
            large_tiles, set(large_tiles), set(large_tiles),
        )
        self.wildlife.habitats = [occupied]
        self.wildlife.animals = [
            Animal(1, 1, 1, AnimalKind.BOAR, patch_id=0),
            Animal(2, 2, 1, AnimalKind.BOAR, patch_id=0),
        ]
        self.assertEqual(self.wildlife._birth_count(AnimalKind.BOAR, occupied, 1.0, 1.0), 0)

        self.wildlife.habitats.append(new_habitat)

        # The new patch raises global potential, though the occupied patch's
        # local cap still prevents births until the pair migrates or it expands.
        self.assertEqual(self.wildlife._birth_count(AnimalKind.BOAR, new_habitat, 1.0, 1.0), 3)

    def test_old_tree_becomes_fallen_wood(self):
        self.balance.set("TREE_LIFESPAN_YEARS", 4)
        self.balance.set("TREE_OLD_AGE_DEATH_CHANCE", 1.0)
        cell = self.world.cells[3][3]
        cell.feature = FeatureType.TREE
        cell.tree_species = "oak"
        cell.tree_age_years = 3
        self.assertEqual(self.world.age_trees_one_year(), 1)
        self.assertEqual(cell.feature, FeatureType.WOOD_BUSH)
        self.assertEqual(cell.tree_species, "oak")
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
