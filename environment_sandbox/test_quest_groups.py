import unittest
from types import SimpleNamespace as NS
import pygame
from scenario import ScenarioState,TUTORIAL_KEY
from objectives import scenario_objectives
from quest_navigation import QuestNavigation
from field_fertility_tint import FieldFertilityTint

class QuestGroupTests(unittest.TestCase):
    def test_group_boundaries_and_focus(self):
        state=ScenarioState(key=TUTORIAL_KEY,step='field_handbook',field_planner_unlocked=True,handbook_completed=1)
        rows=scenario_objectives(state)
        self.assertEqual(next(r for r in rows if r['id']=='go_to_sleep')['group_title'],'Shelter from the Storm')
        self.assertEqual(next(r for r in rows if r['id']=='talk_to_rhea')['group_title'],'Lay of the Land')
        nav=QuestNavigation();self.assertEqual(nav.focused(rows)['id'],'handbook_2')
        nav.step(rows,-1);self.assertEqual(nav.focused(rows)['id'],'handbook_1')
        state.handbook_completed=2
        self.assertEqual(nav.focused(scenario_objectives(state))['id'],'handbook_3')
        nav.select('open_inventory');nav.step(scenario_objectives(state),-1)
        self.assertEqual(nav.focused(scenario_objectives(state))['id'],'open_inventory')

    def test_fertility_tint_smooth_and_cached(self):
        base=pygame.Surface((64,32));base.fill((200,180,140))
        world=NS(terrain_revision=0,get_cell=lambda x,y:NS(fertility=float(x)))
        field=NS(plot_bounds=lambda:(0,0,1,0))
        tint=FieldFertilityTint();a=tint.apply(base,world,[field],0,32)
        self.assertGreater(a.get_at((8,16)).r,a.get_at((55,16)).r)
        self.assertLess(abs(a.get_at((31,16)).r-a.get_at((32,16)).r),5)
        self.assertIs(tint.apply(base,world,[field],0,32),a)
        self.assertIsNot(tint.apply(base,world,[field],1,32),a)
        self.assertEqual(base.get_at((55,16)).r,200)
