import os
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER","dummy")
os.environ.setdefault("SDL_AUDIODRIVER","dummy")

import pygame

from game import Game
from save_load import load_from_path,serialize_game
from world import FeatureType


class TutorialScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.game=Game(headless=True)
        load_from_path(cls.game,Path(__file__).resolve().parents[1]/"saves"/"tutorial_slice.json")

    def test_tutorial_flow_and_shroud_reset(self):
        game=self.game
        self.assertEqual(game.scenario.state.key,"tutorial_slice")
        self.assertEqual(game.player.inventory.berries,1)
        self.assertGreater(len(game.discovered_cells),1)
        self.assertFalse(any(game.world.get_cell(x,y).feature==FeatureType.BERRY_BUSH for x,y in game.discovered_cells))
        game._update_scenario();self.assertTrue(game.scenario_dialog.open)
        game.scenario_dialog.dismissed=True;game._update_scenario()
        self.assertEqual(game.scenario.prompt,"Press I to open inventory")
        game.player_inventory.open_window();game._update_scenario()
        self.assertEqual(game.scenario.prompt,"Right click on the berries to eat.")
        game._player_eat_item("berries");game._update_scenario()
        self.assertTrue(game.scenario_dialog.open)
        game.scenario_dialog.dismissed=True;game._update_scenario()
        self.assertEqual(game.scenario.prompt,"Look around for some more food")
        bush=next((x,y) for y,row in enumerate(game.world.cells) for x,cell in enumerate(row) if cell.feature==FeatureType.BERRY_BUSH and cell.deposit>0 and (x,y) not in game.discovered_cells)
        game.discovered_cells.add(bush);game._update_scenario()
        self.assertIn("where they come from",game.scenario_dialog.text)
        game.scenario_dialog.dismissed=True;game._update_scenario()
        self.assertTrue(game.scenario.state.completed)
        self.assertIsNone(game.scenario.prompt)

    def test_scenario_progress_serializes(self):
        payload=serialize_game(self.game)
        self.assertEqual(payload["scenario"]["key"],"tutorial_slice")
        self.assertEqual(payload["scenario"]["step"],self.game.scenario.state.step)
        self.assertIn("completed",payload["scenario"])


if __name__=="__main__":unittest.main()
