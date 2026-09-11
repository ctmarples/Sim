"""Farmers must plough bare soil before sowing — not reclaim the same PLOUGH forever."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from entities import Building, BuildingKind, CropPlan, HomeStorage, Villager
from farm_pipeline import FarmJobKind
from game import Game
from world import FeatureType, TerrainType, World


class FarmPloughLoopTests(unittest.TestCase):
    def test_villager_ploughs_unfurrowed_soil_instead_of_noop(self) -> None:
        game = Game.__new__(Game)
        game.world = World(8, 8)
        game.calendar_day = 30  # Summer — cabbage plant season
        game.home_storage = HomeStorage()
        game.sounds = Mock()
        game.record_consumed = Mock()
        game._refresh_indicators = Mock()
        game._spend_work_energy = Mock()
        game._gain_job_skill = Mock()
        game._farm_apply_preplant_treatments = Mock()
        game._field_sow_growth_ticks = Mock(return_value=10)

        field = Building(2, BuildingKind.FIELD, 1, 1)
        field.plot_w = field.plot_h = 1
        field.plans = [CropPlan(1, 1, 1, 1, 1, "cabbage", field.id)]
        farm = Building(1, BuildingKind.FARM, 0, 0)
        game.buildings = {farm.id: farm, field.id: field}
        game._fields_near_farm = Mock(return_value=[field])

        cell = game.world.get_cell(1, 1)
        assert cell is not None
        cell.terrain = TerrainType.SOIL
        cell.feature = FeatureType.NONE
        cell.ploughed = False

        villager = Villager(1, 1, 1)
        villager.farm_job_kind = FarmJobKind.PLOUGH.name

        self.assertTrue(game._villager_perform_farm(villager, farm, (1, 1)))
        self.assertTrue(cell.ploughed)
        self.assertEqual(cell.feature, FeatureType.NONE)

    def test_sow_finder_skips_unploughed_soil(self) -> None:
        game = Game.__new__(Game)
        game.world = World(8, 8)
        game.calendar_day = 30  # Summer — cabbage plant season
        field = Building(2, BuildingKind.FIELD, 1, 1)
        field.plot_w = field.plot_h = 1
        field.plans = [CropPlan(1, 1, 1, 1, 1, "cabbage", field.id)]
        farm = Building(1, BuildingKind.FARM, 0, 0)
        game.buildings = {farm.id: farm, field.id: field}
        game._fields_near_farm = Mock(return_value=[field])
        game._claimed_work_cells = Mock(return_value=set())
        game._plant_stock_at = Mock(return_value=5)
        game._tick_farm_sow = None

        cell = game.world.get_cell(1, 1)
        assert cell is not None
        cell.terrain = TerrainType.SOIL
        cell.feature = FeatureType.NONE
        cell.ploughed = False

        villager = Villager(1, 1, 1)
        villager.inventory.cabbage_seeds = 2
        self.assertIsNone(game._find_farm_sow_work(villager, farm))

        cell.ploughed = True
        self.assertEqual(game._find_farm_sow_work(villager, farm), (1, 1))


if __name__ == "__main__":
    unittest.main()
