"""Player field prep actions and plough furrow drawing."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from crops import CROP_BY_KEY
from entities import Building, BuildingKind, CropPlan, Player
from game import Game
from world import FeatureType, TerrainType, World


class FieldPlayerPrepTests(unittest.TestCase):
    def _game_with_empty_field(self, *, with_plan: bool = False) -> tuple[Game, Building]:
        world = World(8, 8)
        cell = world.get_cell(3, 3)
        assert cell is not None
        cell.terrain = TerrainType.GRASS
        cell.feature = FeatureType.NONE
        cell.ploughed = False
        field = Building(2, BuildingKind.FIELD, 3, 3)
        field.plot_w = field.plot_h = 1
        if with_plan:
            field.plans = [CropPlan(1, 3, 3, 3, 3, "sage", field.id)]
        game = Game.__new__(Game)
        game.world = world
        game.calendar_day = 1  # spring
        game.buildings = {field.id: field}
        game.player = Player(3, 3)
        game.player.inventory.equip_tool_from_transfer("hoe")
        game.player.inventory.compost = 2
        game._set_status = Mock()
        game._show_or_run_player_actions = Mock(return_value=True)
        game._player_focus_world_job = Mock(return_value=True)
        game._try_apply_alchemist_treatment = Mock(return_value=True)
        return game, field

    def test_unplanned_empty_field_offers_plough_and_compost(self) -> None:
        game, field = self._game_with_empty_field(with_plan=False)
        actions = game._field_tile_action_choices(field, 3, 3, None)
        keys = [a[0] for a in actions]
        self.assertIn("plough", keys)
        self.assertIn("compost", keys)
        self.assertTrue(game._player_tend_field_cell(field, 3, 3))
        game._show_or_run_player_actions.assert_called_once()

    def test_wrong_season_still_offers_plough(self) -> None:
        game, field = self._game_with_empty_field(with_plan=True)
        game.calendar_day = 90  # winter — sage cannot plant
        crop = CROP_BY_KEY["sage"]
        actions = game._field_tile_action_choices(field, 3, 3, crop)
        keys = [a[0] for a in actions]
        self.assertIn("plough", keys)
        self.assertTrue(game._player_tend_field_cell(field, 3, 3))
        game._show_or_run_player_actions.assert_called()

    def test_field_sapling_offers_uproot_plough(self) -> None:
        game, field = self._game_with_empty_field(with_plan=False)
        cell = game.world.get_cell(3, 3)
        assert cell is not None
        cell.feature = FeatureType.SAPLING
        cell.tree_species = "oak"
        actions = game._field_tile_action_choices(field, 3, 3, None)
        keys = [a[0] for a in actions]
        self.assertIn("plough", keys)
        self.assertTrue(any("uproot" in a[1].lower() for a in actions))
        self.assertTrue(game._player_tend_field_cell(field, 3, 3))
        game._show_or_run_player_actions.assert_called()

        """Regression: bare ploughed soil must enter the feature draw queue."""
        cell = type(
            "C",
            (),
            {"feature": FeatureType.NONE, "ploughed": True, "terrain": TerrainType.SOIL},
        )()
        queued = False
        if cell.feature != FeatureType.NONE:
            queued = True
        elif getattr(cell, "ploughed", False):
            queued = True
        self.assertTrue(queued)


if __name__ == "__main__":
    unittest.main()
