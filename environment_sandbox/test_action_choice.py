"""Player multi-choice actions and seasonal compost threshold."""

from __future__ import annotations

import unittest

from entities import Building, BuildingKind, CropPlan, HomeStorage, Player, Villager
from game import Game
from world import Cell, FeatureType, TerrainType, World


class FieldActionChoiceTests(unittest.TestCase):
    def test_field_offers_plough_and_compost(self) -> None:
        field = Building(2, BuildingKind.FIELD, 2, 2)
        field.plot_w = field.plot_h = 1
        game = Game.__new__(Game)
        game.player = Player(2, 2)
        game.player.inventory.compost = 2
        game.player.inventory.equip_tool_from_transfer("hoe")
        game.world = World(8, 8)
        cell = game.world.get_cell(2, 2)
        assert cell is not None
        cell.terrain = TerrainType.SOIL
        cell.feature = FeatureType.NONE
        cell.ploughed = False
        game.buildings = {field.id: field}
        game.calendar_day = 1
        actions = game._field_tile_action_choices(field, 2, 2, None)
        ids = [a[0] for a in actions]
        self.assertIn("plough", ids)
        self.assertIn("compost", ids)

    def test_single_action_runs_immediately(self) -> None:
        field = Building(2, BuildingKind.FIELD, 2, 2)
        field.plot_w = field.plot_h = 1
        field.plans = [CropPlan(1, 2, 2, 2, 2, "wheat", field.id)]
        game = Game.__new__(Game)
        game.world = World(8, 8)
        cell = game.world.get_cell(2, 2)
        assert cell is not None
        cell.terrain = TerrainType.SOIL
        cell.feature = FeatureType.NONE
        cell.ploughed = True
        game.buildings = {field.id: field}
        game.player = Player(2, 2)
        game.player.inventory.wheat_grain = 1
        game.calendar_day = 56
        game.ticks_per_day = 10
        game.record_consumed = lambda *_a: None
        game._refresh_indicators = lambda: None
        game._finish_player_work = lambda: None
        game._set_status = lambda _s: None
        game.sounds = type("S", (), {"emit": lambda *a, **k: None})()
        from crops import CROP_BY_KEY

        crop = CROP_BY_KEY["wheat"]
        actions = game._field_tile_action_choices(field, 2, 2, crop)
        self.assertEqual([a[0] for a in actions], ["sow"])


class CompostSeasonThresholdTests(unittest.TestCase):
    def test_workers_apply_one_carried_compost_per_season(self) -> None:
        farm = Building(1, BuildingKind.FARM, 0, 0)
        farm.compost_min_fertility = 0.70
        worker = Villager(1, 0, 0)
        worker.inventory.compost = 3
        cell = Cell(TerrainType.SOIL)
        cell.fertility = 0.80  # above Compost-to — no apply
        game = Game.__new__(Game)
        game.calendar_day = 1  # Spring
        game.buildings = {farm.id: farm}
        game.home_storage = HomeStorage()
        game.record_consumed = lambda *_a: None
        game._farm_apply_preplant_treatments(worker, farm, cell, for_plough=True)
        self.assertIsNone(cell.compost_season)
        self.assertEqual(worker.inventory.compost, 3)

        cell.fertility = 0.50
        game._farm_apply_preplant_treatments(worker, farm, cell, for_plough=True)
        self.assertEqual(cell.compost_season, "SPRING")
        self.assertAlmostEqual(cell.fertility, 0.60)  # +0.10 once
        self.assertEqual(worker.inventory.compost, 2)

        # Once per season — further applications blocked even with pack stock.
        game._farm_apply_preplant_treatments(worker, farm, cell, for_plough=True)
        self.assertAlmostEqual(cell.fertility, 0.60)
        self.assertEqual(worker.inventory.compost, 2)

    def test_workers_do_not_remote_consume_compost(self) -> None:
        farm = Building(1, BuildingKind.FARM, 0, 0)
        farm.compost = 5
        farm.compost_min_fertility = 0.70
        worker = Villager(1, 0, 0)
        worker.inventory.compost = 0
        cell = Cell(TerrainType.SOIL)
        cell.fertility = 0.40
        game = Game.__new__(Game)
        game.calendar_day = 1
        game.buildings = {farm.id: farm}
        game.home_storage = HomeStorage()
        game.home_storage.compost = 5
        game.record_consumed = lambda *_a: None
        game._farm_apply_preplant_treatments(worker, farm, cell, for_plough=True)
        self.assertIsNone(cell.compost_season)
        self.assertAlmostEqual(cell.fertility, 0.40)
        self.assertEqual(farm.compost, 5)
        self.assertEqual(game.home_storage.compost, 5)

    def _field_needing_compost(self, game: Game, farm: Building, n: int = 6) -> Building:
        field = Building(99, BuildingKind.FIELD, 4, 4)
        field.plot_w = field.plot_h = 3
        field.compost_min_fertility = 0.70
        game.buildings[field.id] = field
        for pos in list(field.plot_cells())[:n]:
            cell = game.world.get_cell(*pos)
            assert cell is not None
            cell.terrain = TerrainType.SOIL
            cell.feature = FeatureType.NONE
            cell.ploughed = False
            cell.fertility = 0.40
            cell.compost_season = None
        return field

    def test_ensure_carry_fetches_compost_from_heap(self) -> None:
        farm = Building(1, BuildingKind.FARM, 5, 5)
        farm.compost = 0
        farm.linked_extensions = frozenset({BuildingKind.COMPOST_HEAP})
        heap = Building(2, BuildingKind.COMPOST_HEAP, 6, 5)
        heap.parent_building_id = farm.id
        heap.compost = 8
        worker = Villager(1, 6, 5)  # already at heap
        worker.inventory.compost = 0
        game = Game.__new__(Game)
        game.world = World(12, 12)
        game.calendar_day = 1
        game.buildings = {farm.id: farm, heap.id: heap}
        game.home_storage = HomeStorage()
        game.villagers = [worker]
        game._apply_hauler_transfer_cooldown = lambda _v: None
        game._force_assigned_delivery = lambda *_a: False
        game._step_villager_toward = lambda *_a: True
        game._claimed_work_cells = lambda _vid: set()
        self._field_needing_compost(game, farm, n=6)
        self.assertTrue(
            game._farm_ensure_carry_supply(worker, farm, "compost", required=False)
        )
        # Batch for upcoming plough tiles, not one unit per trip.
        self.assertEqual(worker.inventory.compost, 6)
        self.assertEqual(heap.compost, 2)

    def test_ensure_carry_fetches_from_storehouse(self) -> None:
        farm = Building(1, BuildingKind.FARM, 5, 5)
        farm.compost = 0
        worker = Villager(1, 1, 1)
        worker.inventory.compost = 0
        game = Game.__new__(Game)
        game.world = World(12, 12)
        game.world.home_pos = (1, 1)
        game.calendar_day = 1
        game.buildings = {farm.id: farm}
        game.home_storage = HomeStorage()
        game.home_storage.compost = 12
        game.villagers = [worker]
        game._apply_hauler_transfer_cooldown = lambda _v: None
        game._force_assigned_delivery = lambda *_a: False
        game._step_villager_toward = lambda *_a: True
        game._claimed_work_cells = lambda _vid: set()
        self._field_needing_compost(game, farm, n=5)
        self.assertTrue(
            game._farm_ensure_carry_supply(worker, farm, "compost", required=False)
        )
        self.assertEqual(worker.inventory.compost, 5)
        self.assertEqual(game.home_storage.compost, 7)

    def test_farm_job_cell_stays_claimed_while_fetching_supply(self) -> None:
        from entities import VillagerState
        from farm_pipeline import FarmJobKind

        a = Villager(1, 0, 0)
        a.state = VillagerState.WORKING
        a.target = (5, 5)  # walking to farm/store, not the field
        a.farm_job_cell = (3, 3)
        a.farm_job_kind = FarmJobKind.PLOUGH.name
        b = Villager(2, 1, 1)
        game = Game.__new__(Game)
        game.villagers = [a, b]
        game.buildings = {}
        game.world = World(8, 8)
        game.world.home_pos = (0, 0)
        claimed = game._claimed_work_cells(b.id)
        self.assertIn((3, 3), claimed)


if __name__ == "__main__":
    unittest.main()
