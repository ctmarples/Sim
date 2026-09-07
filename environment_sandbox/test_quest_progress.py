import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock
from scenario import ScenarioDirector, ScenarioState, TUTORIAL_KEY
from quest_progress import (
    inspect_species, inspect_field, check_shroud, ready, mark,
    active_objectives, overlay_unlocked, mark_overlay_enabled,
)
from world import TerrainType

class QuestProgressTests(unittest.TestCase):
    def setUp(self):
        d=ScenarioDirector();d.state=ScenarioState(key=TUTORIAL_KEY,step='field_handbook',field_planner_unlocked=True)
        self.state=d.state
        coords=[(20,20),(21,20),(22,20),(23,20)]
        f=NS(plot_cells=lambda:coords,contains_plot=lambda x,y:(x,y) in coords)
        d._village_field=lambda game:f
        cells={(x,y):NS(terrain=TerrainType.GRASS,fertility=.8,weeds=.04,crop_kind='wheat') for y in range(45) for x in range(45)}
        self.game=NS(scenario=d,wildlife=NS(colonies=[]),discovered_cells=set(coords),
            world=NS(rows=45,cols=45,get_cell=lambda x,y:cells[x,y],ensure_height_corners=lambda:None,
                     height_corners=[[0.]*46 for _ in range(46)],height_at_cell=lambda x,y:0.),
            _building_at=lambda x,y:None,_path_traffic={},
            _field_env_status=lambda field:dict(health=.9,health_cap=.85),
            env_maps=NS(soil_moisture=[[.5]*45 for _ in range(45)]))

    def test_species_and_full_shroud_are_separate_conditions(self):
        for key in ['tree:oak','tree:oak','tree:pine','plant:daisy','plant:berry_bush']:
            inspect_species(self.game,20,20,key)
        self.assertEqual(len(self.state.inspected_species),4)
        self.assertIn('handbook_1:species', self.state.quest_checks)
        self.assertEqual([k for k,_ in active_objectives(self.state)],
                         ['species','species_layer','hive'])
        self.assertTrue(overlay_unlocked(self.state, 'BIODIVERSITY'))
        self.assertFalse(overlay_unlocked(self.state, 'POLLINATION'))
        mark_overlay_enabled(self.state, 'BIODIVERSITY')
        check_shroud(self.game);self.assertFalse(ready(self.state))
        self.game.discovered_cells={(x,y) for y in range(10,31) for x in range(10,34)}
        self.game.discovered_cells.remove((10,10))
        check_shroud(self.game);self.assertFalse(ready(self.state))
        self.game.discovered_cells.add((10,10));check_shroud(self.game)
        self.assertTrue(overlay_unlocked(self.state, 'POLLINATION'))
        self.assertFalse(ready(self.state))
        mark_overlay_enabled(self.state, 'POLLINATION')
        self.assertTrue(ready(self.state));self.assertTrue(self.state.quest_no_hives)
        restored=ScenarioDirector();restored.load_dict(self.game.scenario.to_dict())
        self.assertEqual(restored.state.quest_checks,self.state.quest_checks)

    def test_clicking_hive_does_not_replace_shroud_assessment(self):
        from wildlife import AnimalKind
        from game import Game
        c=NS(kind=AnimalKind.BEE,level=1,x=26,y=20)
        self.game.wildlife.colonies=[c];self.game.discovered_cells.add((26,20))
        self.game.place_kind=None;self.game.assign_workplace_mode=False;self.game.height_edit_mode=False
        self.game.resource_inspect=NS(open_details=Mock())
        Game._handle_click(self.game,(26,20),screen_pos=(100,100))
        self.assertEqual(self.game.resource_inspect.open_details.call_args.kwargs['title'],'Beehive')
        self.assertNotIn('handbook_1:hive',self.state.quest_checks)
        self.game.discovered_cells={(x,y) for y in range(10,31) for x in range(10,34)}
        check_shroud(self.game);self.assertFalse(self.state.quest_no_hives)
        self.assertIn('handbook_1:hive',self.state.quest_checks)

    def test_distinct_crop_traffic_and_soil_squares(self):
        self.state.handbook_completed=1
        inspect_field(self.game,20,20);inspect_field(self.game,20,20)
        self.assertEqual(self.state.quest_checks,['handbook_2:health'])
        inspect_field(self.game,21,20);self.assertTrue(ready(self.state))
        self.state.handbook_completed=2
        for _ in range(4):inspect_field(self.game,20,20)
        self.assertNotIn('handbook_3:traffic',self.state.quest_checks)
        for x in (21,22,23):inspect_field(self.game,x,20)
        self.assertIn('handbook_3:traffic',self.state.quest_checks)
        mark(self.state, 'disturbance_layer')
        self.game._building_at=lambda x,y:NS(kind=NS(name='HOME')) if (x,y)==(24,20) else None
        self.game.discovered_cells.add((24,20))
        inspect_field(self.game,24,20)
        self.assertTrue(ready(self.state))
        self.state.handbook_completed=3
        for x in (20,21,22,23):inspect_field(self.game,x,20)
        self.assertEqual(len(self.state.quest_cells['soil']),4)
        for key in ('fertility_layer','moisture_layer','erosion_layer'):
            mark(self.state, key)
        self.assertFalse(ready(self.state))
        self.game.discovered_cells.add((25,20))
        self.game.world.height_corners[20][25]=2.
        self.game.world.height_at_cell=lambda x,y:2. if x==25 else 0.
        inspect_field(self.game,25,20);self.assertTrue(ready(self.state))

    def test_backfill_partial_interviews(self):
        self.state.step='ask_villagers';self.state.gwen_asked=True
        rows=self.game.scenario.objectives()
        self.assertTrue(all(i['completed'] for q in rows[:-1] for i in q['objectives']))
        self.assertEqual([i['completed'] for i in rows[-1]['objectives']],[True,False])

    def test_forage_counts_new_plants_and_yields(self):
        from quest_progress import (
            begin_forage, forage_ready, inspect_species, note_forage_collect,
            FORAGE_FOOD_GOAL, FORAGE_HERB_GOAL, FORAGE_SPECIES_GOAL,
        )
        self.state.step='forage_meadow'
        self.state.handbook_completed=5
        self.state.inspected_species=['plant:daisy','plant:dandelion','tree:oak','plant:wheat']
        self.state.discovered_flora=['wild:wheat','wild:dandelion','wild:daisy']
        self.game.player=NS(inventory=NS())
        begin_forage(self.state)
        inspect_species(self.game,1,1,'plant:daisy')
        inspect_species(self.game,1,1,'plant:sage')
        inspect_species(self.game,1,1,'tree:oak')
        inspect_species(self.game,1,1,'plant:mint')
        self.assertEqual(self.state.foraged_species,['plant:sage','plant:mint'])
        note_forage_collect(self.game,self.game.player.inventory,'sage',4)
        note_forage_collect(self.game,self.game.player.inventory,'berries',6)
        note_forage_collect(self.game,NS(),'berries',20)
        self.assertEqual(self.state.forage_herbs,4)
        self.assertEqual(self.state.forage_food,6)
        self.assertFalse(forage_ready(self.state))
        for key in ('plant:clover','plant:flax','plant:peas','plant:yarrow'):
            inspect_species(self.game,1,1,key)
        note_forage_collect(self.game,self.game.player.inventory,'berries',FORAGE_FOOD_GOAL)
        note_forage_collect(self.game,self.game.player.inventory,'mint',FORAGE_HERB_GOAL)
        self.assertGreaterEqual(len(self.state.foraged_species),FORAGE_SPECIES_GOAL)
        self.assertTrue(forage_ready(self.state))

    def test_forage_completion_starts_diversity_quest(self):
        from quest_progress import FORAGE_FOOD_GOAL, FORAGE_HERB_GOAL
        self.state.step='forage_meadow'
        self.state.handbook_completed=5
        self.state.foraged_species=['plant:sage','plant:mint','plant:flax','plant:peas','plant:clover','plant:yarrow']
        self.state.forage_food=FORAGE_FOOD_GOAL
        self.state.forage_herbs=FORAGE_HERB_GOAL
        self.game.scenario._sync_management_unlocks=lambda game: None
        self.game.scenario.update(self.game)
        self.assertFalse(self.state.completed)
        self.assertEqual(self.state.step,'abundance_dialog')
        text,_=self.game.scenario.take_dialog_request()
        self.assertIn('abundance of food and plants',text)

    def test_diversity_quiz_removes_wrong_answers(self):
        from quest_progress import DIVERSITY_OPTIONS, diversity_option_labels
        self.state.step='diversity_quiz'
        self.state.handbook_completed=5
        self.state.diversity_remaining=[key for key,_ in DIVERSITY_OPTIONS]
        self.state.hotspot_x,self.state.hotspot_y=22,20
        self.game.scenario._request_dialog(
            "So here is the hotspot. Hmm, I wonder why there are so many species here.",
            diversity_option_labels(self.state),
        )
        text,choices=self.game.scenario.take_dialog_request()
        self.assertIn('hotspot',text)
        self.assertEqual(len(choices),3)
        self.game.scenario.dismiss_dialog(0)
        wrong,_=self.game.scenario.take_dialog_request()
        self.assertIn('more diverse',wrong)
        self.game.scenario.dismiss_dialog()
        text,choices=self.game.scenario.take_dialog_request()
        self.assertEqual(len(choices),2)
        self.assertNotIn(DIVERSITY_OPTIONS[0][1],choices)
        soil_index=list(choices).index(DIVERSITY_OPTIONS[1][1])
        self.game.scenario.dismiss_dialog(soil_index)
        wrong,_=self.game.scenario.take_dialog_request()
        self.assertIn('vegetables',wrong)
        self.game.scenario.dismiss_dialog()
        text,choices=self.game.scenario.take_dialog_request()
        self.assertEqual(choices,(DIVERSITY_OPTIONS[2][1],))
        self.game.scenario.dismiss_dialog(0)
        correct,_=self.game.scenario.take_dialog_request()
        self.assertIn('most diverse',correct)
        self.game.scenario.dismiss_dialog()
        self.assertEqual(self.state.step,'inspect_hotspot_flora')

    def test_wildlife_absent_uses_footprints(self):
        self.state.step='find_hotspot_wildlife'
        self.state.handbook_completed=5
        self.state.hotspot_x,self.state.hotspot_y=22,20
        self.state.hotspot_flora=['plant:a','plant:b','plant:c','plant:d','plant:e']
        self.game.wildlife=NS(animals=[],colonies=[])
        self.game.scenario._sync_management_unlocks=lambda game: None
        self.game.scenario.update(self.game)
        self.assertEqual(self.state.step,'wildlife_footprints')
        text,_=self.game.scenario.take_dialog_request()
        self.assertIn('footprints',text)
        self.game.scenario.dismiss_dialog()
        self.assertEqual(self.state.step,'return_to_rhea')
        self.assertFalse(self.state.completed)