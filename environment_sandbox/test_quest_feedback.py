import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace as NS
from quest_feedback import QuestFeedback, queue_alert, update_alerts
from objectives import scenario_objectives
from scenario import ScenarioDirector, ScenarioState, TUTORIAL_KEY
from quest_progress import inspect_species
from sound_system import load_sound_catalogue

class QuestFeedbackTests(unittest.TestCase):
    def test_completed_checkbox_stays_visible_before_new_quest_sound(self):
        game=NS(sounds=Mock())
        feedback=QuestFeedback()
        state=ScenarioState(key=TUTORIAL_KEY,step='open_inventory')
        with patch('quest_feedback.time.monotonic',return_value=10):
            feedback.sync(game,scenario_objectives(state))
            state.step='eat_berries'
            actual=scenario_objectives(state)
            feedback.sync(game,actual)
            shown=feedback.rows(actual)[-1]
            self.assertEqual(shown['id'],'open_inventory')
            self.assertTrue(shown['objectives'][0]['completed'])
            self.assertTrue(feedback.holding)
            self.assertEqual([c.args[0] for c in game.sounds.emit.call_args_list],['quest.new','quest.objective_complete'])
        with patch('quest_feedback.time.monotonic',return_value=12.1):
            feedback.sync(game,actual)
            self.assertEqual(feedback.rows(actual)[-1]['id'],'eat_berries')
            self.assertEqual(game.sounds.emit.call_args.args[0],'quest.new')
            feedback.sync(game,actual)
            self.assertEqual(game.sounds.emit.call_count,3)

    def test_alerts_queue_and_each_plays_notification(self):
        game=NS(sounds=Mock(),_tutorial_unlock_popup=None)
        with patch('quest_feedback.time.monotonic',return_value=1):
            queue_alert(game,'Oak added','tree','flora:tree:oak')
            queue_alert(game,'Pine added','tree','flora:tree:pine')
            self.assertEqual(game._tutorial_unlock_popup[0],'Oak added')
            self.assertEqual(len(game._tutorial_alert_queue),1)
            self.assertEqual(game.sounds.emit.call_count,1)
        with patch('quest_feedback.time.monotonic',return_value=5.1):
            update_alerts(game)
            self.assertEqual(game._tutorial_unlock_popup[0],'Pine added')
            self.assertEqual(game.sounds.emit.call_count,2)

    def test_individual_flora_discoveries_are_persistent_and_deduplicated(self):
        director=ScenarioDirector()
        director.state=ScenarioState(key=TUTORIAL_KEY,step='find_food')
        game=NS(scenario=director,discovered_cells={(1,1)},sounds=Mock(),_tutorial_unlock_popup=None)
        inspect_species(game,1,1,'tree:oak')
        inspect_species(game,1,1,'tree:oak')
        inspect_species(game,1,1,'plant:berry_bush')
        self.assertEqual(director.tutorial_management_flora(),{'tree:oak','wild:berry_bush'})
        self.assertEqual(len(game._tutorial_alert_queue),1)
        restored=ScenarioDirector();restored.load_dict(director.to_dict())
        self.assertEqual(restored.tutorial_management_flora(),director.tutorial_management_flora())
        self.assertIn('flora:tree:oak',restored.state.announced_unlocks)

    def test_exact_sound_bindings_exist(self):
        from pathlib import Path
        import sound_system
        catalogue=load_sound_catalogue()
        expected={'quest.new':'055','quest.objective_complete':'pencil_check_mark','management.item_added':'040'}
        for trigger,filename in expected.items():
            records=[v for v in catalogue.values() if v.get('trigger')==trigger]
            self.assertEqual(len(records),1)
            self.assertIn(filename,records[0]['file'])
            self.assertTrue((sound_system.SOUNDS/records[0]['file']).is_file())
