import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
import unittest
import pygame
from scenario import ScenarioDirector, ScenarioState, TUTORIAL_KEY
from objectives import scenario_objectives
from management_window import ManagementWindow, MgmtTab
from scenario_dialog import ScenarioDialog


class ObjectiveTests(unittest.TestCase):
    def state(self, step, **kwargs):
        return ScenarioState(key=TUTORIAL_KEY, step=step, **kwargs)

    def test_history_current_and_locked(self):
        rows = scenario_objectives(self.state('clear_weeds'))
        self.assertEqual([r['id'] for r in rows if not r['completed']], ['clear_weeds'])
        self.assertEqual(rows[0]['id'], 'open_inventory')
        self.assertEqual(rows[-2]['id'], 'equip_hoe')
        self.assertNotIn('open_book', [r['id'] for r in rows])
        self.assertTrue(all(r['completed'] for r in scenario_objectives(self.state('weeds_complete_dialog'))))

    def test_interviews_remain_open_and_saves_restore_history(self):
        director = ScenarioDirector()
        director.state = self.state('joss_books', gwen_asked=True)
        before = director.objectives()
        self.assertEqual([r['id'] for r in before if not r['completed']], ['ask_villagers'])
        restored = ScenarioDirector()
        restored.load_dict(director.to_dict())
        self.assertEqual(restored.objectives(), before)

    def test_handbook_unlocks_one_step_at_a_time(self):
        for stage in range(5):
            rows = scenario_objectives(self.state('field_handbook', field_planner_unlocked=True, handbook_completed=stage))
            self.assertEqual([r['id'] for r in rows if not r['completed']], [f'handbook_{stage+1}'])
        rows = scenario_objectives(self.state('complete', completed=True, field_planner_unlocked=True, handbook_completed=5))
        self.assertTrue(all(r['completed'] for r in rows))
        self.assertEqual(rows[-1]['id'], 'handbook_5')
        self.assertEqual(scenario_objectives(ScenarioState()), [])

    def test_page_filters_expand_and_scroll(self):
        pygame.init()
        pygame.display.set_mode((1100, 800))
        window = ManagementWindow()
        window.open_window(MgmtTab.PLAYER)
        rows = scenario_objectives(self.state('field_handbook', field_planner_unlocked=True, handbook_completed=3))
        screen = pygame.Surface((1100, 800))
        def draw():
            window.draw(screen, villagers=[], buildings={}, construction_sites={}, wildlife_rows=[], habitat_view=None, objectives=rows)
        window.focus_objective('handbook_4')
        draw()
        self.assertTrue(window.show_list)
        self.assertGreater(window.list_rect().x, window.detail_rect().x)
        buttons = dict(window._buttons)
        self.assertIn('objective:handbook_4', buttons)
        self.assertNotIn('objective:open_inventory', buttons)
        window.handle_mousedown(buttons['objective:handbook_4'].center)
        self.assertIsNone(window.expanded_objective)
        window.handle_mousedown(buttons['objectives_filter:all'].center)
        draw()
        self.assertIn('objective:open_inventory', dict(window._buttons))
        self.assertNotIn('objective:handbook_4', dict(window._buttons))
        self.assertGreater(window._objective_max_scroll, 0)
        window.objectives_filter = 'current'
        window.focus_objective('handbook_4')
        draw()
        pygame.image.save(screen, '/private/tmp/objectives-page.png')

    def test_hud_hit_target_clears(self):
        pygame.init()
        dialog = ScenarioDialog()
        surface = pygame.Surface((1100, 800))
        dialog.draw(surface, 'Know the ground')
        self.assertGreater(dialog.objective_rect.w, 0)
        dialog.draw(surface)
        self.assertEqual(dialog.objective_rect.w, 0)
