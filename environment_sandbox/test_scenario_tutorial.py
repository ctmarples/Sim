import os
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER","dummy")
os.environ.setdefault("SDL_AUDIODRIVER","dummy")

import pygame

from game import Game
from save_load import load_from_path,serialize_game
from world import FeatureType
from wildlife import AnimalKind,AnimalSex,animal_roam_interval


class TutorialScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.game=Game(headless=True)
        load_from_path(cls.game,Path(__file__).resolve().parents[1]/"saves"/"tutorial_slice.json")
        cls.game.scenario.start_tutorial(cls.game)

    def test_tutorial_flow_and_shroud_reset(self):
        game=self.game
        self.assertEqual(game.scenario.state.key,"tutorial_slice")
        self.assertEqual(game.player.inventory.berries,1)
        self.assertEqual((game.player.x,game.player.y),(game.world.cols-6,game.world.rows-3))
        self.assertEqual((game.player.energy,game.player.satiation),(.5,.5))
        self.assertEqual(game.sim_speed,1)
        self.assertEqual(game.overlay_mode.name,"NONE")
        self.assertGreater(len(game.discovered_cells),1)
        self.assertFalse(any(game.world.get_cell(x,y).feature==FeatureType.BERRY_BUSH for x,y in game.discovered_cells))
        forest_animals=[a for a in game.wildlife.animals if a.kind in (AnimalKind.DEER,AnimalKind.BOAR)]
        self.assertEqual(len(forest_animals),1)
        self.assertEqual((forest_animals[0].kind,forest_animals[0].sex,forest_animals[0].x,forest_animals[0].y),
                         (AnimalKind.DEER,AnimalSex.MALE,36,60))
        self.assertEqual(len(game.villagers),2)
        jobs={game.buildings[v.building_id].kind.name for v in game.villagers}
        self.assertEqual(jobs,{"FORAGER","FARM"})
        self.assertEqual(len(game.hire_candidates),1)
        self.assertEqual((game.hire_candidates[0].x,game.hire_candidates[0].y),(62,63))
        game._update_scenario();self.assertTrue(game.scenario_dialog.open)
        game.scenario_dialog.dismissed=True;game._update_scenario()
        self.assertEqual(game.scenario.prompt,"Press I to open inventory")
        game.player_inventory.open_window();game._update_scenario()
        self.assertEqual(game.scenario.prompt,"Right click on the berries to eat.")
        game._player_eat_item("berries");game._update_scenario()
        self.assertTrue(game.scenario_dialog.open)
        game.scenario_dialog.dismissed=True;game._update_scenario()
        self.assertEqual(game.scenario.prompt,"Look around for some more food")
        bushes=[(x,y) for y,row in enumerate(game.world.cells) for x,cell in enumerate(row) if cell.feature==FeatureType.BERRY_BUSH and cell.deposit>0 and (x,y) not in game.discovered_cells]
        bush=min(bushes,key=lambda p:(p[0]-62)**2+(p[1]-63)**2)
        game.discovered_cells.add(bush);game._update_scenario()
        self.assertIn("where they come from",game.scenario_dialog.text)
        game.scenario_dialog.dismissed=True;game._update_scenario()
        self.assertEqual(game.scenario.state.step,"pick_berries")
        self.assertIn("Enter",game.scenario.prompt)
        self.assertEqual((game.scenario.state.bush_x,game.scenario.state.bush_y),bush)
        bx,by=bush
        before=len(game.discovered_cells)
        self.assertIn((bx,by),game.discovered_cells)
        self.assertGreater(len(game.discovered_cells),before-1)
        game.player.move_to(bx,by)
        game.scenario.note_berry_collected(game,bx,by,1)
        self.assertEqual(game.scenario.state.step,"traveller_approaches")
        for _ in range(120):game._update_scenario()
        self.assertTrue(game.scenario_dialog.open)
        self.assertEqual(len(game.scenario_dialog.choices),2)

    def test_scenario_progress_serializes(self):
        payload=serialize_game(self.game)
        self.assertEqual(payload["scenario"]["key"],"tutorial_slice")
        self.assertEqual(payload["scenario"]["step"],self.game.scenario.state.step)
        self.assertIn("completed",payload["scenario"])

    def test_tutorial_slice_1_follow_deer_moves(self):
        path=Path(__file__).resolve().parents[1]/"saves"/"tutorial_slice_1.json"
        if not path.exists():self.skipTest("tutorial_slice_1 save is not present")
        game=Game(headless=True);load_from_path(game,path)
        self.assertEqual(game.scenario.state.step,"follow_deer")
        deer=game.scenario._tutorial_deer(game)
        start=(deer.x,deer.y)
        game.scenario.state.deer_move_wait=animal_roam_interval()
        deer.move_cooldown=game.scenario.state.deer_move_wait
        game.sim_speed=0
        for _ in range(24):game._update_scenario()
        self.assertEqual((deer.x,deer.y),start)
        self.assertEqual(game.scenario.state.deer_move_wait,animal_roam_interval())
        game.sim_speed=1
        frames=animal_roam_interval()//game._playback_ticks()+2
        for _ in range(frames):game._update_scenario()
        self.assertNotEqual((deer.x,deer.y),start)

    def test_farm_shroud_reveal_starts_flee_and_tent_objective(self):
        path=Path(__file__).resolve().parents[1]/"saves"/"tutorial_slice_1.json"
        if not path.exists():self.skipTest("tutorial_slice_1 save is not present")
        game=Game(headless=True);load_from_path(game,path)
        from entities import BuildingKind
        farm=next(b for b in game.buildings.values() if b.kind==BuildingKind.FARM)
        game.scenario.state.step="follow_deer"
        game.discovered_cells.add((farm.x,farm.y))
        game.sim_speed=0
        game._update_scenario()
        self.assertEqual(game.scenario.state.step,"deer_flee")
        self.assertEqual(game.scenario.prompt,"Find a tent")
        self.assertTrue(game.scenario_dialog.open)
        self.assertIn("Oh look it's a farm",game.scenario_dialog.text)


if __name__=="__main__":unittest.main()
