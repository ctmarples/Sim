import unittest

from random_map_generator import MapOptions, TERRAINS, generate_map


class RandomMapGeneratorTests(unittest.TestCase):
    def test_seed_is_deterministic(self):
        options = MapOptions(width=24, height=18, seed=42)
        self.assertEqual(generate_map(options).terrain, generate_map(options).terrain)

    def test_dimensions_and_mix(self):
        mix = {name: 1 for name in TERRAINS}
        result = generate_map(MapOptions(width=30, height=20, terrain_mix=mix))
        self.assertEqual((len(result.terrain), len(result.terrain[0])), (20, 30))
        self.assertEqual(sum(result.counts().values()), 600)
        self.assertLessEqual(abs(result.counts()["water"] - 100), 1)
        self.assertGreater(result.counts()["riparian"], 0)

    def test_structure_changes_map(self):
        valley = generate_map(MapOptions(width=24, height=18, seed=7, composition="valley"))
        islands = generate_map(MapOptions(width=24, height=18, seed=7, composition="archipelago"))
        self.assertNotEqual(valley.elevation, islands.elevation)

    def test_export_shape(self):
        result = generate_map(MapOptions(width=16, height=16))
        self.assertEqual(result.to_dict()["format"], "sim-random-map-v1")

    def test_lake_and_river_options_change_hydrology(self):
        plain = generate_map(MapOptions(width=48, height=36, seed=91, generate_lake=False, generate_river=False))
        hydro = generate_map(MapOptions(width=48, height=36, seed=91, generate_lake=True, generate_river=True))
        self.assertNotEqual(plain.terrain, hydro.terrain)
        self.assertGreater(hydro.counts()["riparian"], 0)

    def test_starter_deposits_are_seeded_near_home(self):
        from world import FeatureType, World

        result = generate_map(MapOptions(width=32, height=24, seed=73))
        world = World(cols=32, rows=24, seed=73)
        result.apply_to_world(world)
        hx, hy = world.home_pos
        nearby = [
            world.cells[y][x].feature
            for y in range(max(0, hy - 6), min(world.rows, hy + 7))
            for x in range(max(0, hx - 6), min(world.cols, hx + 7))
        ]
        self.assertIn(FeatureType.WOOD_BUSH, nearby)
        self.assertIn(FeatureType.ROCK, nearby)


if __name__ == "__main__":
    unittest.main()
