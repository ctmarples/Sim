"""Non-harvestable field flora must not trap farm plough jobs."""

from __future__ import annotations

import unittest

from entities import Building, BuildingKind, CropPlan, HomeStorage, Villager, apply_building_storage
from farm_pipeline import FarmJobKind
from game import Game
from world import FeatureType, NaturalObject, TerrainType, World


class FieldFloraPloughTests(unittest.TestCase):
    def test_scenic_herb_is_cleared_so_plough_can_finish(self) -> None:
        world = World(8, 8)
        cell = world.get_cell(3, 3)
        assert cell is not None
        cell.terrain = TerrainType.GRASS
        cell.feature = FeatureType.HERB
        cell.crop_kind = "clover"  # scenery — no resource_key

        farm = Building(1, BuildingKind.FARM, 1, 1)
        apply_building_storage(farm)
        field = Building(2, BuildingKind.FIELD, 3, 3)
        field.plot_w = field.plot_h = 1
        # sage plants in spring; wheat would fail crop_allows_plant early
        field.plans = [CropPlan(1, 3, 3, 3, 3, "sage", field.id)]
        worker = Villager(1, 3, 3)
        worker.inventory.equip_tool_from_transfer("hoe")

        game = Game.__new__(Game)
        game.world = world
        game.calendar_day = 1
        game.buildings = {farm.id: farm, field.id: field}
        game.home_storage = HomeStorage()
        game.record_consumed = lambda *_a: None
        game.record_produced = lambda *_a: None
        game._refresh_indicators = lambda: None
        game._spend_work_energy = lambda *_a, **_k: None
        game._gain_job_skill = lambda *_a, **_k: None
        game.sounds = type("S", (), {"emit": lambda *a, **k: None})()
        game._drop_rng = __import__("random").Random(0)

        self.assertTrue(game._villager_perform_farm(worker, farm, (3, 3)))
        self.assertEqual(cell.feature, FeatureType.NONE)
        self.assertTrue(cell.ploughed)
        self.assertEqual(cell.terrain, TerrainType.SOIL)

    def test_scenic_extra_flora_cleared_on_plough(self) -> None:
        world = World(8, 8)
        cell = world.get_cell(4, 4)
        assert cell is not None
        cell.terrain = TerrainType.SOIL
        cell.feature = FeatureType.NONE
        cell.ploughed = False
        cell.extra_objects.append(
            NaturalObject(
                feature=FeatureType.HERB,
                anchor_slot=4,
                crop_kind="yarrow",
            )
        )

        farm = Building(1, BuildingKind.FARM, 1, 1)
        apply_building_storage(farm)
        field = Building(2, BuildingKind.FIELD, 4, 4)
        field.plot_w = field.plot_h = 1
        field.plans = [CropPlan(1, 4, 4, 4, 4, "sage", field.id)]
        worker = Villager(1, 4, 4)
        worker.inventory.equip_tool_from_transfer("hoe")

        game = Game.__new__(Game)
        game.world = world
        game.calendar_day = 1
        game.buildings = {farm.id: farm, field.id: field}
        game.home_storage = HomeStorage()
        game.record_consumed = lambda *_a: None
        game.record_produced = lambda *_a: None
        game._refresh_indicators = lambda: None
        game._spend_work_energy = lambda *_a, **_k: None
        game._gain_job_skill = lambda *_a, **_k: None
        game.sounds = type("S", (), {"emit": lambda *a, **k: None})()
        game._drop_rng = __import__("random").Random(0)

        self.assertTrue(game._villager_perform_farm(worker, farm, (4, 4)))
        self.assertEqual(cell.extra_objects, [])
        self.assertTrue(cell.ploughed)

    def test_plough_uplifts_sapling_to_inventory(self) -> None:
        world = World(8, 8)
        cell = world.get_cell(2, 2)
        assert cell is not None
        cell.terrain = TerrainType.GRASS
        cell.feature = FeatureType.SAPLING
        cell.tree_species = "maple"

        farm = Building(1, BuildingKind.FARM, 1, 1)
        apply_building_storage(farm)
        field = Building(2, BuildingKind.FIELD, 2, 2)
        field.plot_w = field.plot_h = 1
        field.plans = [CropPlan(1, 2, 2, 2, 2, "sage", field.id)]
        worker = Villager(1, 2, 2)
        worker.inventory.equip_tool_from_transfer("hoe")

        game = Game.__new__(Game)
        game.world = world
        game.calendar_day = 1
        game.buildings = {farm.id: farm, field.id: field}
        game.home_storage = HomeStorage()
        game.record_consumed = lambda *_a: None
        game.record_produced = lambda *_a: None
        game._refresh_indicators = lambda: None
        game._spend_work_energy = lambda *_a, **_k: None
        game._gain_job_skill = lambda *_a, **_k: None
        game.sounds = type("S", (), {"emit": lambda *a, **k: None})()
        game._drop_rng = __import__("random").Random(0)

        self.assertTrue(game._villager_perform_farm(worker, farm, (2, 2)))
        self.assertEqual(cell.feature, FeatureType.NONE)
        self.assertTrue(cell.ploughed)
        self.assertEqual(worker.inventory.maple_saplings, 1)

    def test_player_plough_uplifts_sapling(self) -> None:
        world = World(8, 8)
        cell = world.get_cell(1, 1)
        assert cell is not None
        cell.terrain = TerrainType.SOIL
        cell.feature = FeatureType.SAPLING
        cell.tree_species = "oak"
        cell.ploughed = False

        game = Game.__new__(Game)
        game.world = world
        from entities import Inventory

        inv = Inventory()
        inv.equip_tool_from_transfer("hoe")
        game.player = type("P", (), {"inventory": inv})()
        game.record_produced = lambda *_a: None
        game._refresh_indicators = lambda: None
        game._set_status = lambda *_a: None
        game.world.apply_disturbance = lambda *_a, **_k: None

        self.assertTrue(game._player_apply_plough_job(1, 1, {"crop_label": "Wheat"}))
        self.assertEqual(cell.feature, FeatureType.NONE)
        self.assertTrue(cell.ploughed)
        self.assertEqual(game.player.inventory.oak_saplings, 1)

    def test_player_plough_requires_hoe(self) -> None:
        world = World(8, 8)
        cell = world.get_cell(1, 1)
        assert cell is not None
        cell.terrain = TerrainType.SOIL
        cell.feature = FeatureType.SAPLING
        cell.tree_species = "oak"
        game = Game.__new__(Game)
        game.world = world
        from entities import Inventory

        game.player = type("P", (), {"inventory": Inventory()})()
        game._set_status = lambda *_a: None
        self.assertFalse(game._player_apply_plough_job(1, 1, {}))
        self.assertEqual(cell.feature, FeatureType.SAPLING)

    def test_farm_assigns_sapling_plough_before_weed(self) -> None:
        """Weeds on another tile must not starve sapling clearance."""
        world = World(10, 10)
        sap = world.get_cell(5, 5)
        weed = world.get_cell(4, 4)
        assert sap is not None and weed is not None
        sap.terrain = TerrainType.SOIL
        sap.feature = FeatureType.SAPLING
        sap.tree_species = "oak"
        sap.ploughed = True
        weed.terrain = TerrainType.SOIL
        weed.feature = FeatureType.CROP_HERB
        weed.crop_kind = "flax"
        weed.weeds = 0.5
        weed.ploughed = True

        farm = Building(1, BuildingKind.FARM, 1, 1)
        apply_building_storage(farm)
        field = Building(2, BuildingKind.FIELD, 4, 4)
        field.plot_w = field.plot_h = 2
        field.plans = [CropPlan(1, 4, 4, 5, 5, "flax", field.id)]
        worker = Villager(1, 4, 4)
        worker.inventory.equip_tool_from_transfer("hoe")
        worker.building_id = farm.id

        game = Game.__new__(Game)
        game.world = world
        game.calendar_day = 1
        game.buildings = {farm.id: farm, field.id: field}
        game.villagers = [worker]
        game.home_storage = HomeStorage()
        game._claimed_work_cells = lambda *_a, **_k: set()
        game._ensure_work_tool = lambda *_a, **_k: True
        game._fields_near_farm = lambda _b: [field]
        game._field_rotation_year = lambda _f: 1
        game._find_farm_harvest = lambda *_a, **_k: None
        game._find_farm_sow_work = lambda *_a, **_k: None
        game._find_farm_repellant_work = lambda *_a, **_k: None
        game._farm_barn_craft_available = lambda *_a, **_k: False
        game._farm_barn_needs_sheaf_delivery = lambda *_a, **_k: False
        game._farm_has_unsown_soil = lambda *_a, **_k: False
        game._farm_or_processor_needs_clear = lambda *_a, **_k: False
        game._general_hauler_serving = lambda *_a, **_k: False
        game._closest_of = Game._closest_of.__get__(game, Game)

        job = game._assign_farm_job(worker, farm)
        self.assertIsNotNone(job)
        assert job is not None
        self.assertEqual(job.kind, FarmJobKind.PLOUGH)
        self.assertEqual(job.cell, (5, 5))

    def test_farm_assigns_harvest_before_weed(self) -> None:
        """Ripe harvest must not lose to weedy tiles (even weedy ripe ones)."""
        world = World(12, 12)
        ripe = world.get_cell(5, 5)
        weedy_ripe = world.get_cell(10, 10)
        growing_weedy = world.get_cell(4, 4)
        assert ripe is not None and weedy_ripe is not None and growing_weedy is not None
        for cell, kind, ticks, weeds in (
            (ripe, "peas", 0, 0.05),
            (weedy_ripe, "peas", 0, 0.5),
            (growing_weedy, "peas", 20, 0.4),
        ):
            cell.terrain = TerrainType.SOIL
            cell.feature = FeatureType.CROP_HERB
            cell.crop_kind = kind
            cell.growth_ticks = ticks
            cell.deposit = 0
            cell.weeds = weeds
            cell.ploughed = True

        farm = Building(1, BuildingKind.FARM, 1, 1)
        apply_building_storage(farm)
        field_near = Building(2, BuildingKind.FIELD, 4, 4)
        field_near.plot_w = field_near.plot_h = 2
        field_near.plans = [CropPlan(1, 4, 4, 5, 5, "peas", field_near.id)]
        field_far = Building(3, BuildingKind.FIELD, 10, 10)
        field_far.plot_w = field_far.plot_h = 1
        field_far.plans = [CropPlan(1, 10, 10, 10, 10, "peas", field_far.id)]
        worker = Villager(1, 5, 5)
        worker.inventory.equip_tool_from_transfer("hoe")
        worker.building_id = farm.id

        game = Game.__new__(Game)
        game.world = world
        game.calendar_day = 28  # summer — peas harvest season
        game.buildings = {farm.id: farm, field_near.id: field_near, field_far.id: field_far}
        game.villagers = [worker]
        game.home_storage = HomeStorage()
        game.balance = type("B", (), {"get_float": lambda self, key: 0.2})()
        game._claimed_work_cells = lambda *_a, **_k: set()
        game._ensure_work_tool = lambda *_a, **_k: True
        game._fields_near_farm = lambda _b: [field_near, field_far]
        game._field_rotation_year = lambda _f: 1
        game._find_farm_sapling_clear_work = lambda *_a, **_k: None
        game._find_farm_sow_work = lambda *_a, **_k: None
        game._find_farm_repellant_work = lambda *_a, **_k: None
        game._find_farm_plough_work = lambda *_a, **_k: None
        game._farm_barn_craft_available = lambda *_a, **_k: False
        game._farm_barn_needs_sheaf_delivery = lambda *_a, **_k: False
        game._farm_has_unsown_soil = lambda *_a, **_k: False
        game._farm_or_processor_needs_clear = lambda *_a, **_k: False
        game._general_hauler_serving = lambda *_a, **_k: False
        game._tick_farm_harvest = None
        game._tick_farm_weed = None
        game._closest_of = Game._closest_of.__get__(game, Game)

        job = game._assign_farm_job(worker, farm)
        self.assertIsNotNone(job)
        assert job is not None
        self.assertEqual(job.kind, FarmJobKind.HARVEST)
        self.assertEqual(job.cell, (5, 5))

        weed = game._find_farm_weed_work(worker, farm)
        self.assertEqual(weed, (4, 4), "ripe tiles must not be claimed as WEED")


if __name__ == "__main__":
    unittest.main()
