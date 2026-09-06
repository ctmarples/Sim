import os
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
import unittest
import json
from pathlib import Path
import pygame
from game import Game
from save_load import load_from_path
from quest_progress import FIELD_OBJECTIVES, check_key, ready
from tutorial_checkpoints import CHECKPOINTS, available, checkpoint_path

class TutorialCheckpointTests(unittest.TestCase):
    def test_all_files_and_new_field_stages(self):
        root=Path(__file__).resolve().parents[1]/'saves'
        for number in range(1,22):
            self.assertIn('tutorial_checkpoint',json.loads((root/f'tutorial_intro_{number}.json').read_text()))
        pygame.init()
        game=Game(headless=True)
        for number in range(15,22):
            with self.subTest(checkpoint=number):
                path=root/f'tutorial_intro_{number}.json'
                config=json.loads(path.read_text())['tutorial_checkpoint']
                load_from_path(game,path)
                state=game.scenario.state
                field=game.scenario._village_field(game)
                stage=config['handbook_completed']
                self.assertEqual(state.handbook_completed,stage)
                self.assertEqual(state.step,config['step'])
                self.assertTrue(state.gwen_asked and state.joss_asked)
                self.assertTrue(state.wildlife_seeded)
                self.assertTrue(game.player.inventory.has_equipped_tool('hoe'))
                self.assertTrue(all(game.world.get_cell(x,y).weeds==0 for x,y in field.plot_cells()))
                self.assertEqual(game.field_plan_dialog.tab,config['planner_tab'])
                self.assertIsNone(game._tutorial_unlock_popup)
                self.assertFalse(game._tutorial_alert_queue)
                expected={check_key(i,key) for i in range(stage) for key,_ in FIELD_OBJECTIVES[i]}
                self.assertTrue(expected.issubset(state.quest_checks))
                if stage>=1:
                    self.assertTrue(state.quest_shroud_checked)
                    self.assertEqual(len(state.inspected_species),4)
                if number<21:
                    self.assertFalse(ready(state))
                    self.assertEqual([q['id'] for q in game.scenario.objectives() if not q['completed']], [f'handbook_{stage+1}'])
                else:
                    self.assertTrue(state.completed)
                    self.assertTrue(all(q['completed'] for q in game.scenario.objectives()))
                if number==20:
                    self.assertNotIn('handbook_5:wheat',state.quest_checks)
                    game.field_plan_dialog._on_action('add_current_wheat',field)
                    game._apply_pending_field_plan()
                    self.assertIn('handbook_5:wheat',state.quest_checks)

    def test_named_catalog_matches_files(self):
        self.assertEqual([number for number, _, _ in CHECKPOINTS], list(range(1, 22)))
        self.assertTrue(all(isinstance(label, str) and not label.isdigit() for _, _, label in CHECKPOINTS))
        self.assertEqual({label for _, _, label in available('land')},
                         {label for number, group, label in CHECKPOINTS
                          if group == 'land' and checkpoint_path(number).is_file()})
        self.assertIn('Beyond the fence', [label for _, _, label in available('land')])
        self.assertNotIn('15', [label for _, _, label in available()])
