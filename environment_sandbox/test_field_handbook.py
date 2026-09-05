import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
import unittest
from types import SimpleNamespace
import pygame
from scenario import ScenarioDirector, ScenarioState, TUTORIAL_KEY
from field_plan_dialog import FieldPlanDialog
from entities import BuildingKind

class HandbookTests(unittest.TestCase):
    def test_reveals_and_persistence(self):
        pygame.init()
        panel = FieldPlanDialog()
        director = ScenarioDirector()
        director.state = ScenarioState(key=TUTORIAL_KEY, step='field_handbook', field_planner_unlocked=True)
        director._sync_management_unlocks = lambda game: None
        game = SimpleNamespace(field_plan_dialog=panel)
        field = SimpleNamespace(id=10, kind=BuildingKind.FIELD, plot_w=6, plot_h=6, plot_size_label=lambda: '6 × 6')
        panel.building_id = 10
        panel.configure_embed(pygame.Rect(0, 0, 620, 700))
        surface = pygame.Surface((620, 700))
        counts = [0, 2, 4, 5, 8]
        for stage in range(5):
            panel.handbook_stage = stage
            panel.tab = 'status'
            panel._on_action('tab_rotation', field)
            self.assertEqual(panel.tab, 'status')
            panel.draw(surface, field, env_status={'health': .9, 'moisture': .5})
            self.assertEqual(len(panel._factors), counts[stage])
            self.assertNotIn('tab_rotation', dict(panel._buttons))
            panel.tab = 'handbook'
            panel.draw(surface, field)
            panel._on_action('record_observations', field)
            director.update(game)
            restored = ScenarioDirector()
            restored.load_dict(director.to_dict())
            self.assertEqual(restored.state.handbook_completed, stage + 1)
        self.assertTrue(director.state.completed)
        self.assertEqual(panel.tab, 'rotation')
        self.assertIn("I'll draw in the current crop: Wheat", director.take_dialog_request()[0])
