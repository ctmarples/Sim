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
from entities import BuildingKind,VillagerState


class TutorialScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.game=Game(headless=True)
        load_from_path(cls.game,Path(__file__).resolve().parents[1]/"saves"/"tutorial_slice.json")
        cls.game.scenario.start_tutorial(cls.game)

    def test_tutorial_flow_and_shroud_reset(self):
        game=self.game
        def update():
            game._update_scenario()
            while game.scenario.quest_feedback.holding:
                game.scenario.quest_feedback.until = 0
                game._update_scenario()
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
        self.assertEqual(len(game.hire_candidates),2)
        traveller=game.scenario._tutorial_traveller(game)
        rhea=game.scenario._tutorial_rhea(game)
        self.assertEqual((traveller.x,traveller.y),(62,63))
        field=next(b for b in game.buildings.values() if b.kind==BuildingKind.FIELD)
        self.assertEqual((rhea.name,rhea.x,rhea.y),("Rhea",field.x,field.y))
        update();self.assertTrue(game.scenario_dialog.open)
        game.scenario_dialog.dismissed=True;update()
        self.assertEqual(game.scenario.prompt,"Press I to open inventory")
        game.player_inventory.open_window();update()
        self.assertEqual(game.scenario.prompt,"Right click on the berries to eat.")
        game._player_eat_item("berries");update()
        self.assertTrue(game.scenario_dialog.open)
        game.scenario_dialog.dismissed=True;update()
        self.assertEqual(game.scenario.prompt,"Look around for some more food")
        bushes=[(x,y) for y,row in enumerate(game.world.cells) for x,cell in enumerate(row) if cell.feature==FeatureType.BERRY_BUSH and cell.deposit>0 and (x,y) not in game.discovered_cells]
        bush=min(bushes,key=lambda p:(p[0]-62)**2+(p[1]-63)**2)
        game.discovered_cells.add(bush);update()
        self.assertIn("where they come from",game.scenario_dialog.text)
        game.scenario_dialog.dismissed=True;update()
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
        for _ in range(120):update()
        self.assertTrue(game.scenario_dialog.open)
        self.assertEqual(len(game.scenario_dialog.choices),2)

    def test_scenario_progress_serializes(self):
        payload=serialize_game(self.game)
        self.assertEqual(payload["scenario"]["key"],"tutorial_slice")
        self.assertEqual(payload["scenario"]["step"],self.game.scenario.state.step)
        self.assertIn("completed",payload["scenario"])

    def test_broken_tent_and_northern_wood_are_seeded(self):
        game=Game(headless=True)
        load_from_path(game,Path(__file__).resolve().parents[1]/"saves"/"tutorial_slice.json")
        game.scenario.start_tutorial(game)
        state=game.scenario.state
        rhea=game.scenario._tutorial_rhea(game)
        rhea_start=(rhea.x,rhea.y,rhea.world_x,rhea.world_y)
        game.scenario.state.step="find_tent"
        for _ in range(20):game.scenario.update(game)
        self.assertEqual((rhea.x,rhea.y,rhea.world_x,rhea.world_y),rhea_start)
        self.assertNotIn(15,game.buildings)
        site=game.construction_sites[state.broken_tent_site_id]
        self.assertEqual((site.kind,site.need_wood,site.source_building_id),(BuildingKind.TENT,1,15))
        woods=[]
        for y,row in enumerate(game.world.cells):
            for x,cell in enumerate(row):
                if cell.feature==FeatureType.WOOD_BUSH and y < state.broken_tent_y:
                    woods.append((x,y))
        self.assertGreaterEqual(len(woods),1)
        self.assertTrue(any(
            game.world.get_cell(x+dx,y+dy) is not None
            and game.world.get_cell(x+dx,y+dy).feature==FeatureType.TREE
            for x,y in woods for dx,dy in ((-1,0),(1,0),(0,-1),(0,1))
        ))

    def test_rhea_offers_tent_repair_then_player_sleeps(self):
        game=Game(headless=True)
        load_from_path(game,Path(__file__).resolve().parents[1]/"saves"/"tutorial_slice.json")
        game.scenario.start_tutorial(game)
        occupied=game.buildings[9]
        game.scenario.state.step="find_tent"
        game.discovered_cells.add((occupied.x,occupied.y))
        game.scenario.update(game)
        self.assertEqual(game.scenario.state.step,"rhea_approaches")
        rhea=game.scenario._tutorial_rhea(game)
        rhea.x,rhea.y=game.player.x,game.player.y
        rhea.world_x,rhea.world_y=float(rhea.x),float(rhea.y)
        game.scenario.update(game)
        self.assertEqual(game.scenario.take_dialog_request()[0],"Hi there, can I help you?")
        game.scenario.dismiss_dialog()
        self.assertEqual(game.scenario.take_dialog_request()[0],"I'm looking for a place to stay for the night")
        game.scenario.dismiss_dialog()
        offer=game.scenario.take_dialog_request()[0]
        self.assertIn("old collapsed tent",offer)
        game.scenario.dismiss_dialog()
        game.scenario.update(game)
        self.assertEqual(game.scenario.prompt,"Fix the tent")
        self.assertIsNone(game.scenario._tutorial_rhea(game))
        joined=game._get_villager(game.scenario.state.rhea_villager_id)
        self.assertIsNotNone(joined)
        self.assertIsNone(joined.building_id)
        site=game.construction_sites[game.scenario.state.broken_tent_site_id]
        site.have_wood=site.need_wood
        site.build_progress=site.build_required_ticks()
        game._complete_construction(site)
        game.scenario.update(game)
        joined=game._get_villager(game.scenario.state.rhea_villager_id)
        joined.x,joined.y=game.player.x,game.player.y
        joined.world_x,joined.world_y=float(joined.x),float(joined.y)
        game.scenario.update(game)
        self.assertEqual(game.scenario.state.step,"tent_repaired_dialog")
        self.assertIn("talk in the morning",game.scenario.take_dialog_request()[0])
        game.scenario.dismiss_dialog()
        tent=game.buildings[game.scenario.state.repaired_tent_id]
        entrance=game.world.building_entrance_position((tent.x,tent.y,tent.plot_w,tent.plot_h))
        game.player.x,game.player.y=tent.center_cell()
        game.player.world_x,game.player.world_y=entrance
        game._interact_at_player()
        game.scenario.update(game)
        game.scenario.update(game)
        self.assertEqual(game.scenario.state.step,"talk_to_rhea")
        self.assertFalse(game.scenario.state.completed)
        self.assertEqual(game.player.energy,1.0)
        self.assertTrue(all(v.energy==1.0 for v in game.villagers if v.housed))

    def test_intro_clock_freezes_and_checkpoint_files_load(self):
        game=Game(headless=True)
        path=Path(__file__).resolve().parents[1]/"saves"/"tutorial_intro_5.json"
        load_from_path(game,path)
        self.assertEqual(game.scenario.state.step,"fix_tent")
        self.assertEqual((game.player.x,game.player.y),(22,23))
        before=(game.calendar_day,game.day_tick)
        game._step_sim()
        self.assertEqual((game.calendar_day,game.day_tick),before)

    def test_checkpoint_residents_keep_separate_homes(self):
        root=Path(__file__).resolve().parents[1]/"saves"
        game=Game(headless=True);load_from_path(game,root/"tutorial_intro_3.json")
        berry=game._get_villager(game.scenario.state.berry_villager_id)
        self.assertIsNotNone(berry)
        self.assertEqual((berry.community_id,berry.building_id,berry.housing_id),(1001,None,12))
        self.assertEqual(game.buildings[9].kind,BuildingKind.HOUSE)
        game=Game(headless=True);load_from_path(game,root/"tutorial_intro_5.json")
        village=[v for v in game.villagers if v.community_id==0]
        self.assertEqual(len(village),3)
        self.assertTrue(all(v.housed and v.housing_id==9 for v in village))
        berry=game._get_villager(game.scenario.state.berry_villager_id)
        self.assertEqual(berry.housing_id,12)

    def test_settlement_logistics_reject_cross_group_claims(self):
        game=Game(headless=True)
        load_from_path(game,Path(__file__).resolve().parents[1]/"saves"/"tutorial_intro_5.json")
        rhea=game._get_villager(game.scenario.state.rhea_villager_id)
        berry_fire=game.buildings[14]
        self.assertFalse(game.scenario.can_villager_use_building(rhea,berry_fire))
        rhea.haul_building_id=berry_fire.id
        rhea.state=VillagerState.HAULING
        rhea.target=berry_fire.center_cell()
        start=(rhea.x,rhea.y)
        game._update_hauler(rhea)
        self.assertIsNone(rhea.haul_building_id)
        self.assertEqual(rhea.state,VillagerState.IDLE)
        self.assertEqual((rhea.x,rhea.y),start)
        berry=game._get_villager(game.scenario.state.berry_villager_id)
        self.assertFalse(game.scenario.can_villager_use_village_storehouse(berry))

    def test_morning_rhea_weed_tutorial(self):
        game=Game(headless=True)
        load_from_path(game,Path(__file__).resolve().parents[1]/"saves"/"tutorial_intro_7.json")
        rhea=game._get_villager(game.scenario.state.rhea_villager_id)
        self.assertTrue(game.scenario.interact_villager(game,rhea))
        self.assertIn("can I help",game.scenario.take_dialog_request()[0])
        expected=("Thanks for the place","small community","Sure!","prosperous village","Weeds!")
        for text in expected:
            game.scenario.dismiss_dialog()
            self.assertIn(text,game.scenario.take_dialog_request()[0])
        game.scenario.dismiss_dialog()
        field=game.scenario._village_field(game)
        rhea.x,rhea.y=field.x,field.y
        rhea.world_x,rhea.world_y=float(rhea.x),float(rhea.y)
        game.player.move_to(field.x+1,field.y)
        game.scenario.update(game)
        self.assertEqual(game.scenario.state.step,"field_reaction")
        game.scenario.take_dialog_request()
        game.scenario.dismiss_dialog();game.scenario.take_dialog_request()
        game.scenario.dismiss_dialog();game.scenario.update(game)
        self.assertEqual(game.scenario.state.step,"equip_hoe")
        self.assertEqual(game.player.inventory.hoe,1)
        game.player.inventory.equip_tool("hoe");game.scenario.update(game)
        self.assertEqual(game.scenario.state.step,"clear_weeds")
        for x,y in field.plot_cells():game.world.get_cell(x,y).weeds=0.0
        game.scenario.update(game)
        rhea.x,rhea.y=game.player.x,game.player.y
        rhea.world_x,rhea.world_y=float(rhea.x),float(rhea.y)
        game.scenario.update(game)
        self.assertIn("light work",game.scenario.take_dialog_request()[0])

    def test_talking_to_rhea_stops_ai_and_unifies_position(self):
        game=Game(headless=True)
        load_from_path(game,Path(__file__).resolve().parents[1]/"saves"/"tutorial_intro_7.json")
        rhea=game._get_villager(game.scenario.state.rhea_villager_id)
        rhea.world_x,rhea.world_y=rhea.x+.45,rhea.y+.35
        rhea.target=(rhea.x+5,rhea.y+5)
        rhea._path_cache=[(rhea.x+1,rhea.y+1)]
        self.assertTrue(game.scenario.interact_villager(game,rhea))
        self.assertTrue(rhea._scenario_controlled)
        self.assertIsNone(rhea.target)
        self.assertIsNone(rhea._path_cache)
        self.assertEqual((rhea.world_x,rhea.world_y),(float(rhea.x),float(rhea.y)))
        start=(rhea.x,rhea.y,rhea.world_x,rhea.world_y)
        for _ in range(20):game._update_villagers()
        self.assertEqual((rhea.x,rhea.y,rhea.world_x,rhea.world_y),start)

    def test_farm_history_interviews_unlock_book_and_field_planner(self):
        game=Game(headless=True)
        load_from_path(game,Path(__file__).resolve().parents[1]/"saves"/"tutorial_intro_9.json")
        game.scenario.state.step="weeds_complete_dialog"
        dialogs=("more abundant","enough to feed four","other villagers")
        for expected in dialogs:
            game.scenario.dismiss_dialog()
            self.assertIn(expected,game.scenario.take_dialog_request()[0])
        game.scenario.dismiss_dialog()
        self.assertEqual(game.scenario.state.step,"ask_villagers")
        self.assertEqual(game.scenario.tutorial_management_flora(),{"wild:wheat","wild:dandelion","wild:daisy"})
        gwen=next(v for v in game.villagers if v.name=="Gwen Hill")
        joss=next(v for v in game.villagers if v.name=="Joss Fern")
        self.assertTrue(game.scenario.interact_villager(game,gwen))
        self.assertEqual(game.player.inventory.honey,1)
        for _ in range(3):game.scenario.dismiss_dialog();game.scenario.take_dialog_request()
        game.scenario.update(game)
        self.assertTrue(game.scenario.state.gwen_asked)
        self.assertTrue(game.scenario.interact_villager(game,joss))
        for _ in range(5):game.scenario.dismiss_dialog();game.scenario.take_dialog_request()
        game.scenario.update(game)
        self.assertEqual(game.scenario.state.step,"enter_farmhouse")
        farm=game.scenario._village_field(game)
        farmhouse=next(b for b in game.buildings.values() if b.kind.name=="FARM")
        self.assertIn(farmhouse.id,game.scenario.tutorial_management_buildings(game))
        game._player_inside_building_id=farmhouse.id
        game.scenario.update(game)
        self.assertEqual(game.player.inventory.book,1)
        self.assertTrue(game.scenario.use_inventory_item(game,"book"))
        self.assertEqual(game.player.inventory.book,0)
        self.assertTrue(game.scenario.state.field_planner_unlocked)
        self.assertEqual(game.field_plan_dialog.building_id,farm.id)
        visible=game.scenario.tutorial_management_buildings(game)
        from management_window import _iter_building_list_rows
        rows=_iter_building_list_rows(visible,{})
        self.assertIn(("building",farm,1),rows)
        alerts = ([game._tutorial_unlock_popup] if game._tutorial_unlock_popup else []) + game._tutorial_alert_queue
        self.assertIn(("Field Planner added under the Farmhouse", "field", f"building:{farm.id}"), alerts)

    def test_bug_save_discards_unrelated_seasonal_travellers(self):
        path=Path(__file__).resolve().parents[1]/"saves"/"tutorial_slice_bug.json"
        if not path.exists():self.skipTest("tutorial_slice_bug save is not present")
        game=Game(headless=True);load_from_path(game,path)
        self.assertEqual([candidate.name for candidate in game.hire_candidates],["Rhea"])
        before=list(game.hire_candidates)
        game._top_up_hire_candidates()
        self.assertEqual(game.hire_candidates,before)

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
        self.assertTrue(game.scenario.quest_feedback.holding)
        self.assertFalse(game.scenario_dialog.open)
        game.scenario.quest_feedback.until = 0
        game._update_scenario()
        self.assertTrue(game.scenario_dialog.open)
        self.assertIn("Oh look it's a farm",game.scenario_dialog.text)

    def test_wheat_makes_rhea_walk_from_afar(self):
        game=Game(headless=True)
        load_from_path(game,Path(__file__).resolve().parents[1]/"saves"/"tutorial_intro_20.json")
        field=game.scenario._village_field(game)
        game.field_plan_dialog._on_action('add_current_wheat',field)
        game._apply_pending_field_plan()
        game.scenario.quest_feedback.until=0
        game._update_scenario()
        self.assertEqual(game.scenario.state.step,"rhea_forage_approaches")
        rhea=game._get_villager(game.scenario.state.rhea_villager_id)
        rhea.world_x,rhea.world_y=game.player.x+8.0,float(game.player.y)
        rhea.x,rhea.y=round(rhea.world_x),round(rhea.world_y)
        start=rhea.world_x
        for _ in range(12):
            game.scenario.update(game)
        self.assertLess(rhea.world_x,start)
        self.assertEqual(game.scenario.state.step,"rhea_forage_approaches")

    def test_wheat_leads_to_gwen_forage_and_unlocks_hut(self):
        game=Game(headless=True)
        load_from_path(game,Path(__file__).resolve().parents[1]/"saves"/"tutorial_intro_21.json")
        self.assertEqual(game.scenario.state.step,"rhea_forage_approaches")
        self.assertFalse(game.scenario.state.completed)
        rhea=game._get_villager(game.scenario.state.rhea_villager_id)
        rhea.x,rhea.y=game.player.x,game.player.y
        rhea.world_x,rhea.world_y=float(rhea.x),float(rhea.y)
        game.scenario.update(game)
        self.assertIn("helping Gwen with the foraging",game.scenario.take_dialog_request()[0])
        game.scenario.dismiss_dialog()
        self.assertEqual(game.scenario.take_dialog_request()[0],"Sure! I've been waiting all day for someone to take me for a walk")
        game.scenario.dismiss_dialog()
        game.scenario.update(game)
        gwen=next(v for v in game.villagers if v.name=="Gwen Hill")
        gwen.x,gwen.y=game.player.x,game.player.y
        gwen.world_x,gwen.world_y=float(gwen.x),float(gwen.y)
        game.scenario.update(game)
        self.assertEqual(game.scenario.state.step,"walk_to_forager")
        hut=game.scenario._village_forager(game)
        hx,hy=hut.center_cell()
        gwen.x,gwen.y=hx,hy
        gwen.world_x,gwen.world_y=float(hx),float(hy)
        game.player.x,game.player.y=hx+1,hy
        game.player.world_x,game.player.world_y=float(hx+1),float(hy)
        game.scenario.update(game)
        self.assertIn("foraged goods together",game.scenario.take_dialog_request()[0])
        game.scenario.dismiss_dialog()
        game.scenario.update(game)
        self.assertTrue(game.scenario.state.forager_unlocked)
        self.assertIn(hut.id,game.scenario.tutorial_management_buildings(game))
        alerts=([game._tutorial_unlock_popup] if game._tutorial_unlock_popup else [])+game._tutorial_alert_queue
        self.assertTrue(any(alert[0]=="Forager huts unlocked" for alert in alerts))
        self.assertIn("haulers will then transport",game.scenario.take_dialog_request()[0])
        game.scenario.dismiss_dialog()
        game.scenario.update(game)
        self.assertEqual(game.scenario.state.step,"walk_to_meadow")

    def test_satchel_equip_starts_forage_objectives(self):
        game=Game(headless=True)
        load_from_path(game,Path(__file__).resolve().parents[1]/"saves"/"tutorial_intro_22.json")
        self.assertEqual(game.scenario.state.step,"equip_satchel")
        self.assertTrue(game.player.inventory.equip_clothing("leather_satchel"))
        game.scenario.update(game)
        self.assertIn("set to forage",game.scenario.take_dialog_request()[0])
        game.scenario.dismiss_dialog()
        self.assertEqual(game.scenario.state.step,"forage_meadow")
        self.assertEqual([q['id'] for q in game.scenario.objectives() if not q['completed']],['forage_meadow'])


if __name__=="__main__":unittest.main()
