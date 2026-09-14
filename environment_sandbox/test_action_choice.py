"""Player multi-choice actions and seasonal compost threshold."""

from __future__ import annotations

import unittest

from entities import Building, BuildingKind, CropPlan, HomeStorage, Player, Villager
from game import Game
from world import Cell, TerrainType


class FieldActionChoiceTests(unittest.TestCase):
    def test_field_offers_plough_and_compost(self) -> None:
        game = Game.__new__(Game)
        game.calendar_day = 1  # Spring
        game.player = Player(0, 0)
        game.player.inventory.compost = 2
        game.player.inventory.equip_tool_from_transfer("hoe")
        field = Building(1, BuildingKind.FIELD, 0, 0)
        field.plans = [CropPlan(1, 0, 0, 0, 0, "wheat", field.id)]
        cell = Cell(TerrainType.GRASS)
        cell.fertility = 0.4
        game.world = type("W", (), {"get_cell": lambda self, x, y: cell})()
        game._field_building_at = lambda x, y: field
        crop = type("C", (), {"key": "wheat", "label": "Wheat", "seed_key": "wheat_grain"})()
        actions = game._field_tile_action_choices(field, 0, 0, crop)
        ids = [a[0] for a in actions]
        self.assertIn("compost", ids)
        self.assertIn("plough", ids)

    def test_single_action_runs_immediately(self) -> None:
        game = Game.__new__(Game)
        game.action_choice = type("D", (), {"open": False, "show": lambda *a, **k: None})()
        ran = []
        game._pending_action_handlers = {}
        self.assertTrue(
            game._show_or_run_player_actions(
                [("plough", "Plough", lambda: ran.append(1))]
            )
        )
        self.assertEqual(ran, [1])


class CompostSeasonThresholdTests(unittest.TestCase):
    def test_workers_compost_only_when_below_seventy_percent(self) -> None:
        farm = Building(1, BuildingKind.FARM, 0, 0)
        farm.compost = 2
        worker = Villager(1, 0, 0)
        cell = Cell(TerrainType.SOIL)
        cell.fertility = 0.80  # above 70% of soil fertility max
        game = Game.__new__(Game)
        game.calendar_day = 1  # Spring
        game.buildings = {farm.id: farm}
        game.home_storage = HomeStorage()
        game.record_consumed = lambda *_a: None
        game._farm_apply_preplant_treatments(worker, farm, cell, for_plough=True)
        self.assertIsNone(cell.compost_season)
        self.assertEqual(farm.compost, 2)

        from soil import field_fertility_max, COMPOST_FERTILITY_FRACTION

        cap = field_fertility_max(cell)
        cell.fertility = max(0.0, COMPOST_FERTILITY_FRACTION * cap - 0.05)
        before = cell.fertility
        game._farm_apply_preplant_treatments(worker, farm, cell, for_plough=True)
        self.assertEqual(cell.compost_season, "SPRING")
        self.assertAlmostEqual(cell.fertility, before + 0.05)
        self.assertEqual(farm.compost, 1)

        # Once per season.
        game._farm_apply_preplant_treatments(worker, farm, cell, for_plough=True)
        self.assertEqual(farm.compost, 1)


if __name__ == "__main__":
    unittest.main()
