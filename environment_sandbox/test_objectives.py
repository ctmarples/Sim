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

    def test_handbook_tips_sit_under_objectives(self):
        rows = scenario_objectives(self.state('field_handbook', field_planner_unlocked=True, handbook_completed=0))
        quest = rows[-1]
        self.assertEqual(quest['id'], 'handbook_1')
        self.assertTrue(all(item.get('tip') for item in quest['objectives']))
        pygame.init()
        font = pygame.font.SysFont('menlo', 12)
        from quest_ui import detail_lines
        lines = detail_lines(font, quest, 300)
        tip_indexes = [i for i, (_, kind) in enumerate(lines) if kind in ('tip', 'child_tip')]
        objective_indexes = [i for i, (_, kind) in enumerate(lines)
                             if kind is True or kind is False or (isinstance(kind, tuple) and kind[0] == 'child')]
        tip_text = ' '.join(text for text, kind in lines if kind in ('tip', 'child_tip'))
        self.assertIn('Tip: inspect species with a cursor click.', tip_text)
        self.assertTrue(tip_indexes)
        self.assertTrue(all(any(o < t for o in objective_indexes) for t in tip_indexes))
        for tip_index in tip_indexes:
            prior = next(i for i in reversed(range(tip_index))
                         if lines[i][1] is True or lines[i][1] is False
                         or (isinstance(lines[i][1], tuple) and lines[i][1][0] == 'child'))
            self.assertLess(prior, tip_index)

    def test_enable_layer_nests_under_parent(self):
        state = self.state('field_handbook', field_planner_unlocked=True, handbook_completed=0,
                          quest_checks=['handbook_1:species'], inspected_species=['a','b','c','d'])
        quest = scenario_objectives(state)[-1]
        self.assertEqual([item['id'] for item in quest['objectives']], ['species', 'hive'])
        self.assertEqual([c['id'] for c in quest['objectives'][0]['children']], ['species_layer'])
        pygame.init()
        font = pygame.font.SysFont('menlo', 12)
        from quest_ui import detail_lines
        kinds = [kind for _, kind in detail_lines(font, quest, 320)]
        self.assertIn(('child', False), kinds)
        self.assertIn('gap', kinds)
