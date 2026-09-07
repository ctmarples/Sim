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
        for number in range(1,34):
            self.assertIn('tutorial_checkpoint',json.loads((root/f'tutorial_intro_{number}.json').read_text()))
        pygame.init()
        game=Game(headless=True)
        for number in range(15,34):
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
                current=[q['id'] for q in game.scenario.objectives() if not q['completed']]
                if number<21:
                    self.assertFalse(ready(state))
                    self.assertEqual(current, [f'handbook_{stage+1}'])
                elif number==21:
                    self.assertFalse(state.completed)
                    self.assertEqual(current, [])
                elif number==22:
                    self.assertFalse(state.completed)
                    self.assertEqual(current, ['equip_satchel'])
                    self.assertGreater(int(getattr(game.player.inventory,'leather_satchel',0)),0)
                elif number==23:
                    self.assertFalse(state.completed)
                    self.assertEqual(current, ['forage_meadow'])
                    self.assertEqual(game.player.inventory.equipped_in_slot('bag'),'leather_satchel')
                    self.assertTrue(state.village_buildings_unlocked or state.forager_unlocked)
                elif number==24:
                    self.assertFalse(state.completed)
                    self.assertEqual(current, ['find_diversity_hotspot'])
                elif number==25:
                    self.assertFalse(state.completed)
                    self.assertEqual(current, ['inspect_hotspot_flora'])
                elif number==26:
                    self.assertFalse(state.completed)
                    self.assertEqual(current, ['find_hotspot_wildlife'])
                elif number==27:
                    self.assertFalse(state.completed)
                    self.assertEqual(current, ['return_to_rhea'])
                    self.assertEqual(
                        [q['group_title'] for q in game.scenario.objectives() if not q['completed']],
                        ['New knowledge'],
                    )
                elif number==28:
                    self.assertFalse(state.completed)
                    self.assertEqual(current, ['visit_berry_traveller'])
                elif number==29:
                    self.assertFalse(state.completed)
                    self.assertEqual(current, ['collect_trade_food'])
                elif number==30:
                    self.assertFalse(state.completed)
                    self.assertEqual(current, ['create_orchard_field'])
                    self.assertTrue(state.forager_unlocked)
                    self.assertTrue(state.village_buildings_unlocked)
                    self.assertEqual(game.player.inventory.equipped_in_slot('bag'),'leather_satchel')
                    hut = game.scenario._village_forager(game)
                    self.assertIsNotNone(hut)
                    self.assertTrue(game.scenario.can_player_interact_building(hut))
                    self.assertTrue(any(cell in game.discovered_cells for cell in hut.plot_cells()))
                elif number==31:
                    self.assertFalse(state.completed)
                    self.assertEqual(current, ['plan_orchard_crops'])
                    self.assertIsNotNone(game.scenario._quest_orchard(game))
                    self.assertTrue(state.forager_unlocked)
                    self.assertTrue(state.village_buildings_unlocked)
                    self.assertEqual(game.player.inventory.equipped_in_slot('bag'),'leather_satchel')
                    hut = game.scenario._village_forager(game)
                    self.assertIsNotNone(hut)
                    self.assertTrue(game.scenario.can_player_interact_building(hut))
                elif number==32:
                    self.assertFalse(state.completed)
                    self.assertEqual(current, ['plant_orchard_bushes'])
                    self.assertTrue(game.scenario._orchard_plan_ready(game.scenario._quest_orchard(game)))
                    self.assertTrue(state.forager_unlocked)
                    self.assertTrue(state.village_buildings_unlocked)
                    self.assertEqual(game.player.inventory.equipped_in_slot('bag'),'leather_satchel')
                    hut = game.scenario._village_forager(game)
                    self.assertIsNotNone(hut)
                    self.assertTrue(game.scenario.can_player_interact_building(hut))
                    self.assertTrue(any(cell in game.discovered_cells for cell in hut.plot_cells()))
                    from berry_bushes import TRADE_SEED_REWARDS
                    for key, n in TRADE_SEED_REWARDS:
                        self.assertGreaterEqual(int(getattr(game.player.inventory, key, 0) or 0), n)
                else:
                    self.assertTrue(state.completed)
                    self.assertTrue(all(q['completed'] for q in game.scenario.objectives()))
                if number==20:
                    self.assertNotIn('handbook_5:wheat',state.quest_checks)
                    game.field_plan_dialog._on_action('add_current_wheat',field)
                    game._apply_pending_field_plan()
                    self.assertIn('handbook_5:wheat',state.quest_checks)

    def test_named_catalog_matches_files(self):
        self.assertEqual([number for number, _, _ in CHECKPOINTS], list(range(1, 34)))
        self.assertTrue(all(isinstance(label, str) and not label.isdigit() for _, _, label in CHECKPOINTS))
        self.assertEqual({label for _, _, label in available('land')},
                         {label for number, group, label in CHECKPOINTS
                          if group == 'land' and checkpoint_path(number).is_file()})
        self.assertIn('Beyond the fence', [label for _, _, label in available('land')])
        self.assertNotIn('15', [label for _, _, label in available()])
