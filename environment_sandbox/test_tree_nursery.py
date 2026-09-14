"""Tree seeds, nursery growth, and action-choice labels."""

from __future__ import annotations

import unittest

from entities import Building, BuildingKind, HomeStorage, Villager, apply_building_storage
from game import Game
from seasons import SEASON_LENGTH_TICKS, Season
from trees import TREE_SEED_KEYS, seed_item_key
from world import FeatureType, TerrainType, World


class ActionChoiceLabelTests(unittest.TestCase):
    def test_gather_label_uses_species(self) -> None:
        game = Game.__new__(Game)
        cell = type(
            "C",
            (),
            {
                "feature": FeatureType.WILD_CROP,
                "crop_kind": "flax",
                "deposit": 0,
                "tree_age_years": 0,
                "icon_variant": 1,
                "tree_species": None,
            },
        )()
        game.world = type("W", (), {"get_cell": lambda self, x, y: cell})()
        action = game._natural_feature_action(0, 0, FeatureType.WILD_CROP, None, 0)
        self.assertIsNotNone(action)
        assert action is not None
        self.assertEqual(action[1], "Gather flax")


class TreeSeedAndNurseryTests(unittest.TestCase):
    def test_tree_seed_resources_exist(self) -> None:
        from resources import RESOURCE_KEYS

        for key in TREE_SEED_KEYS:
            self.assertIn(key, RESOURCE_KEYS)

    def test_chop_can_drop_tree_seed(self) -> None:
        world = World(6, 6)
        cell = world.get_cell(0, 5)
        assert cell is not None
        cell.terrain = TerrainType.GRASS
        cell.feature = FeatureType.TREE
        cell.tree_species = "maple"
        cell.deposit = 3
        game = Game.__new__(Game)
        game.world = world
        game._drop_rng = __import__("random").Random(0)
        game._seed_chance = lambda chance: 1.0
        game.record_produced = lambda *_a: None
        game._refresh_indicators = lambda: None
        game.sounds = type("S", (), {"emit": lambda *a, **k: None})()
        inv = Villager(1, 0, 5).inventory
        self.assertTrue(game._chop_tree(0, 5, inv, status=False))
        self.assertGreaterEqual(inv.maple_seeds, 1)

    def test_loose_wood_can_drop_tree_seed(self) -> None:
        world = World(6, 6)
        cell = world.get_cell(1, 1)
        assert cell is not None
        cell.terrain = TerrainType.GRASS
        cell.feature = FeatureType.WOOD_BUSH
        cell.crop_kind = "wood_bush"
        cell.tree_species = "pine"
        cell.deposit = 1
        game = Game.__new__(Game)
        game.world = world
        game._drop_rng = __import__("random").Random(0)
        game._seed_chance = lambda chance: 1.0
        game.record_produced = lambda *_a: None
        game._refresh_indicators = lambda: None
        game.world.apply_extraction_disturbance = lambda *_a, **_k: None
        inv = Villager(1, 1, 1).inventory
        self.assertTrue(game._collect_wood_bush(1, 1, inv, status=False))
        self.assertEqual(inv.wood, 1)
        self.assertGreaterEqual(inv.pine_seeds, 1)
        self.assertEqual(cell.feature, FeatureType.NONE)

    def test_nursery_seed_matures_to_collectable_sapling(self) -> None:
        world = World(8, 8)
        cell = world.get_cell(0, 7)
        assert cell is not None
        cell.terrain = TerrainType.SOIL
        cell.feature = FeatureType.NONE
        cell.ploughed = True
        self.assertTrue(world.sow_tree_seed(0, 7, "oak"))
        self.assertEqual(cell.feature, FeatureType.SAPLING)
        self.assertEqual(cell.deposit, -1)
        self.assertFalse(cell.ploughed)
        world.tick_bulk(SEASON_LENGTH_TICKS + 5, day=10.0)
        cell = world.get_cell(0, 7)
        assert cell is not None
        self.assertEqual(cell.feature, FeatureType.SAPLING)
        self.assertTrue(world.nursery_sapling_ready(0, 7))
        self.assertEqual(world.harvest_nursery_sapling(0, 7), "oak")
        self.assertEqual(cell.feature, FeatureType.NONE)

    def test_nursery_matures_across_winter_growth_halt(self) -> None:
        """Nursery seedlings keep ripening when tree growth is halted."""
        world = World(8, 8)
        cell = world.get_cell(0, 7)
        assert cell is not None
        cell.terrain = TerrainType.SOIL
        cell.ploughed = True
        self.assertTrue(world.sow_tree_seed(0, 7, "oak"))
        # Mid-winter day — trees_grow_factor is ~0.
        world.tick_bulk(SEASON_LENGTH_TICKS + 5, day=98.0)
        self.assertTrue(world.nursery_sapling_ready(0, 7))

    def test_season_change_matures_nursery_and_forester_collects(self) -> None:
        world = World(12, 12)
        cell = world.get_cell(0, 0)
        assert cell is not None
        cell.terrain = TerrainType.SOIL
        cell.ploughed = True
        self.assertTrue(world.sow_tree_seed(0, 0, "oak"))
        self.assertFalse(world.nursery_sapling_ready(0, 0))

        lodge = Building(1, BuildingKind.FORESTER, 2, 2)
        apply_building_storage(lodge)
        lodge.ensure_recipe_state()
        lodge.recipe_enabled["saplings_from_seed"] = True
        nursery = Building(2, BuildingKind.TREE_NURSERY, 0, 0)
        nursery.plot_w = nursery.plot_h = 1
        worker = Villager(1, 0, 0)
        game = Game.__new__(Game)
        game.world = world
        game.buildings = {lodge.id: lodge, nursery.id: nursery}
        game.home_storage = HomeStorage()
        game._work_gen = 0
        game._bump_work_gen = lambda: setattr(game, "_work_gen", game._work_gen + 1)
        game._refresh_indicators = lambda: None
        game.record_produced = lambda *_a: None
        game._spend_work_energy = lambda *_a, **_k: None
        game._gain_job_skill = lambda *_a, **_k: None
        game.sounds = type("S", (), {"emit": lambda *a, **k: None})()
        game._claimed_work_cells = lambda *_a, **_k: set()

        game._mature_nursery_seedlings()
        self.assertTrue(world.nursery_sapling_ready(0, 0))
        target = game._find_nursery_collect(worker, lodge)
        self.assertEqual(target, (0, 0))
        self.assertTrue(game._villager_perform_nursery(worker, lodge, (0, 0)))
        self.assertEqual(worker.inventory.oak_saplings, 1)
        self.assertEqual(cell.feature, FeatureType.NONE)

    def test_growing_nursery_tile_is_not_sticky_target(self) -> None:
        world = World(12, 12)
        cell = world.get_cell(0, 0)
        assert cell is not None
        cell.terrain = TerrainType.SOIL
        cell.ploughed = True
        self.assertTrue(world.sow_tree_seed(0, 0, "oak"))
        lodge = Building(1, BuildingKind.FORESTER, 2, 2)
        apply_building_storage(lodge)
        lodge.ensure_recipe_state()
        lodge.recipe_enabled["saplings_from_seed"] = True
        lodge.oak_seeds = 2
        nursery = Building(2, BuildingKind.TREE_NURSERY, 0, 0)
        nursery.plot_w = nursery.plot_h = 1
        worker = Villager(1, 0, 0)
        game = Game.__new__(Game)
        game.world = world
        game.calendar_day = 1
        game.buildings = {lodge.id: lodge, nursery.id: nursery}
        game.home_storage = HomeStorage()
        game.is_discovered = lambda *_a: True
        self.assertFalse(
            game._work_target_valid(worker, lodge, (0, 0))
        )

    def test_forester_ploughs_and_sows_nursery(self) -> None:
        world = World(12, 12)
        cell = world.get_cell(0, 0)
        assert cell is not None
        cell.terrain = TerrainType.GRASS
        cell.feature = FeatureType.NONE
        lodge = Building(1, BuildingKind.FORESTER, 8, 8)
        apply_building_storage(lodge)
        lodge.ensure_recipe_state()
        lodge.recipe_enabled["saplings_from_seed"] = True
        lodge.oak_seeds = 2
        nursery = Building(2, BuildingKind.TREE_NURSERY, 0, 0)
        nursery.plot_w = nursery.plot_h = 1
        nursery.plans = []  # no rotation plan — any seed, any tile
        worker = Villager(1, 0, 0)
        game = Game.__new__(Game)
        game.world = world
        game.calendar_day = 1  # spring
        game.buildings = {lodge.id: lodge, nursery.id: nursery}
        game.home_storage = HomeStorage()
        game.record_consumed = lambda *_a: None
        game.record_produced = lambda *_a: None
        game._refresh_indicators = lambda: None
        game._spend_work_energy = lambda *_a, **_k: None
        game._gain_job_skill = lambda *_a, **_k: None
        game.sounds = type("S", (), {"emit": lambda *a, **k: None})()
        game._claimed_work_cells = lambda *_a, **_k: set()
        self.assertEqual(game.season, Season.SPRING)
        self.assertTrue(game._villager_perform_nursery(worker, lodge, (0, 0)))
        cell = world.get_cell(0, 0)
        assert cell is not None
        self.assertTrue(cell.ploughed)
        self.assertEqual(cell.terrain, TerrainType.SOIL)
        # Second swing sows the seed.
        worker.inventory.oak_seeds = 0
        lodge.oak_seeds = 1
        self.assertTrue(game._villager_perform_nursery(worker, lodge, (0, 0)))
        self.assertEqual(cell.feature, FeatureType.SAPLING)
        self.assertEqual(cell.tree_species, "oak")
        self.assertEqual(seed_item_key("oak"), "oak_seeds")

    def test_nursery_planner_has_no_rotation_tab(self) -> None:
        import os

        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        import pygame

        from field_plan_dialog import FieldPlanDialog

        pygame.init()
        panel = FieldPlanDialog()
        nursery = Building(2, BuildingKind.TREE_NURSERY, 0, 0)
        nursery.plot_w = nursery.plot_h = 3
        panel.open_for(nursery)
        surface = pygame.Surface((400, 400))
        panel.draw(surface, nursery)
        buttons = dict(panel._buttons)
        self.assertNotIn("tab_rotation", buttons)
        self.assertNotIn("tab_crop", buttons)
        self.assertIn("tab_status", buttons)


if __name__ == "__main__":
    unittest.main()
