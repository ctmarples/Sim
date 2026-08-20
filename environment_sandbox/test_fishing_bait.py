import unittest

from entities import Building, BuildingKind, apply_building_storage
from recipes import FISHER_RECIPES, apply_recipe
from wildlife import Fish, FishManager
from world import FeatureType, TerrainType, World



class FishingBaitTests(unittest.TestCase):
    def test_bait_recipe_turns_one_meat_into_four_bait(self) -> None:
        recipe = next(r for r in FISHER_RECIPES if r.name == "bait")
        fisher = Building(1, BuildingKind.FISHER, 0, 0)
        apply_building_storage(fisher)
        fisher.meat = 1

        apply_recipe(fisher, recipe)

        self.assertEqual(fisher.meat, 0)
        self.assertEqual(fisher.bait, 4)

    def test_bait_attractor_moves_nearby_fish_closer(self) -> None:
        world = World(cols=12, rows=12, seed=3)
        for row in world.cells:
            for cell in row:
                cell.terrain = TerrainType.WATER
                cell.feature = FeatureType.NONE
        world.bump_terrain()
        manager = FishManager(seed=4)
        fish = Fish(id=1, x=9, y=9)
        manager.fish = [fish]
        post = (2, 2)
        before = abs(fish.x - post[0]) + abs(fish.y - post[1])

        manager._move_fish(world, 40, attractors=[post])

        after = abs(fish.x - post[0]) + abs(fish.y - post[1])
        self.assertLess(after, before)


if __name__ == "__main__":
    unittest.main()
