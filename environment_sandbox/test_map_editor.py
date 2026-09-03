import os
import random
import unittest
from unittest.mock import Mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from entities import BuildingKind
from game import EDITOR_BUILDING_KINDS, Game
from trees import resolve_tree
from world import FeatureType, MapEditTool, TerrainType, World


class MapEditorWorldTests(unittest.TestCase):
    def test_named_forest_brush_uses_selected_species(self):
        world = World(cols=9, rows=9, seed=3)
        for row in world.cells:
            for cell in row:
                cell.terrain = TerrainType.GRASS
                cell.feature = FeatureType.NONE
        changed = world.seed_forest(4, 4, 0, random.Random(1), "cedar")
        cell = world.cells[4][4]
        self.assertTrue(changed)
        self.assertEqual(cell.feature, FeatureType.TREE)
        self.assertEqual(cell.tree_species, "cedar")
        self.assertEqual(cell.deposit, resolve_tree("cedar").yield_amount)
        self.assertEqual(cell.terrain, TerrainType.FOREST_FLOOR)

    def test_rock_brush_mixes_valid_deposit_sizes(self):
        world = World(cols=11, rows=11, seed=4)
        for row in world.cells:
            for cell in row:
                cell.terrain = TerrainType.GRASS
                cell.feature = FeatureType.NONE
        self.assertTrue(world.paint_rocks(5, 5, 3, random.Random(2)))
        deposits = [
            cell.deposit for row in world.cells for cell in row
            if cell.feature == FeatureType.ROCK
        ]
        self.assertTrue(any(value < 20 for value in deposits))
        self.assertTrue(any(value >= 20 for value in deposits))


class MapEditorGameTests(unittest.TestCase):
    def setUp(self):
        import pygame

        pygame.init()
        pygame.display.set_mode((1, 1))
        self.game = Game(headless=True)

    def test_t_toggles_map_object_editor(self):
        import pygame

        self.assertFalse(self.game.height_edit_mode)
        self.game._on_keydown(pygame.K_t)
        self.assertTrue(self.game.height_edit_mode)
        shroud = Mock()
        self.game._draw_map_shroud = shroud
        self.game._draw()
        shroud.assert_not_called()
        self.game._on_keydown(pygame.K_t)
        self.assertFalse(self.game.height_edit_mode)

    def test_derived_environment_refresh_waits_for_editor_exit(self):
        self.game.height_edit_mode = True
        sample = Mock()
        self.game._sample_environment = sample
        self.game._after_map_edit(terrain_changed=True)
        sample.assert_not_called()
        self.game._toggle_height_edit()
        sample.assert_called_once_with()

    def test_editor_building_palette_ignores_progression_unlocks(self):
        self.assertEqual(set(EDITOR_BUILDING_KINDS), set(BuildingKind))

    def test_editor_places_template_as_non_village_traveller(self):
        self.game._open_map_edit_traveller_picker()
        choice = self.game._map_edit_traveller_choices[0]
        self.game.map_edit_traveller_template_id = choice.template_id
        target = next(
            (x, y)
            for y in range(self.game.world.rows)
            for x in range(self.game.world.cols)
            if self.game.world.is_walkable(x, y)
            and all((c.x, c.y) != (x, y) for c in self.game.hire_candidates)
            and all((v.x, v.y) != (x, y) for v in self.game.villagers)
        )
        village_count = len(self.game.villagers)
        traveller_count = len(self.game.hire_candidates)
        self.assertTrue(self.game._editor_place_traveller(*target))
        self.assertEqual(len(self.game.villagers), village_count)
        self.assertEqual(len(self.game.hire_candidates), traveller_count + 1)
        placed = self.game.hire_candidates[-1]
        self.assertEqual((placed.x, placed.y), target)
        self.assertEqual(placed.template_id, choice.template_id)

    def test_tab_toggles_sidebar_visibility(self):
        import pygame
        import settings

        before = settings.PANEL_COLLAPSED
        self.game._on_keydown(pygame.K_TAB)
        self.assertNotEqual(settings.PANEL_COLLAPSED, before)
        self.game._on_keydown(pygame.K_TAB)
        self.assertEqual(settings.PANEL_COLLAPSED, before)

    def test_file_menu_launches_terrain_type_editor_in_new_process(self):
        self.assertIn(
            "file_terrain_types",
            {button.action for button in self.game.toolbar._menu_buttons},
        )
        with unittest.mock.patch("subprocess.Popen") as popen:
            self.game._handle_toolbar_action("file_terrain_types")
        popen.assert_called_once()
        args, kwargs = popen.call_args
        self.assertTrue(str(args[0][1]).endswith("preview_terrain_fills.py"))
        self.assertTrue(kwargs["start_new_session"])
        self.assertIn("new window", self.game.status_message.lower())

    def test_editor_places_and_moves_completed_building(self):
        # Find two clear buildable centres in the generated map.
        centres = []
        for y in range(2, self.game.world.rows - 2):
            for x in range(2, self.game.world.cols - 2):
                w, h = (1, 1)
                if self.game._footprint_blocked([(x, y)]) is None:
                    centres.append((x, y))
                if len(centres) == 2:
                    break
            if len(centres) == 2:
                break
        self.assertEqual(len(centres), 2)
        self.assertTrue(self.game._editor_place_building(BuildingKind.TENT, *centres[0]))
        building = max(self.game.buildings.values(), key=lambda b: b.id)
        self.assertFalse(self.game.construction_sites)
        self.game.map_edit_tool = MapEditTool.MOVE_BUILDING
        self.assertTrue(self.game._editor_move_building_at(*centres[0]))
        self.assertTrue(self.game._editor_move_building_at(*centres[1]))
        self.assertEqual((building.x, building.y), centres[1])

    def test_select_mode_is_neutral_and_default(self):
        self.assertEqual(self.game.map_edit_tool,MapEditTool.SELECT)
        before=[row[:] for row in self.game.world.height_corners]
        self.game._paint_height_at(0,0)
        self.assertEqual(self.game.world.height_corners,before)

    def test_editor_draws_completed_field_and_opens_planner(self):
        site=None
        for y in range(self.game.world.rows):
            for x in range(self.game.world.cols):
                cell=self.game.world.cells[y][x]
                if cell.terrain in (TerrainType.SOIL,TerrainType.GRASS,TerrainType.MEADOW) and self.game._building_at(x,y) is None and not self.game._field_plot_covers(x,y):site=(x,y);break
            if site:break
        self.assertIsNotNone(site)
        self.game.world.cells[site[1]][site[0]].feature=FeatureType.NONE
        self.assertTrue(self.game._editor_place_field(site,site))
        field=max((b for b in self.game.buildings.values() if b.kind==BuildingKind.FIELD),key=lambda b:b.id)
        self.assertFalse(any(site.kind==BuildingKind.FIELD for site in self.game.construction_sites.values()))
        self.assertEqual(self.game.field_plan_dialog.building_id,field.id)

    def test_crop_brush_only_paints_established_fields_with_current_phase(self):
        from crops import CROP_BY_KEY,SeasonPhase,phase_for_crop
        site=None
        for y in range(self.game.world.rows):
            for x in range(self.game.world.cols):
                cell=self.game.world.cells[y][x]
                if cell.terrain in (TerrainType.SOIL,TerrainType.GRASS,TerrainType.MEADOW) and self.game._building_at(x,y) is None and not self.game._field_plot_covers(x,y):site=(x,y);break
            if site:break
        self.assertIsNotNone(site);self.game.world.cells[site[1]][site[0]].feature=FeatureType.NONE
        self.assertTrue(self.game._editor_place_field(site,site))
        crop=next(iter(CROP_BY_KEY.values()));self.game.map_edit_crop_key=crop.key
        self.assertEqual(self.game._editor_paint_crop(*site,0),1)
        cell=self.game.world.cells[site[1]][site[0]];self.assertEqual(cell.crop_kind,crop.key);self.assertEqual(cell.feature,FeatureType.CROP_HERB)
        ripe=phase_for_crop(crop,self.game.season) in (SeasonPhase.HARVEST,SeasonPhase.HARVEST_PLOUGH_PLANT)
        self.assertEqual(cell.growth_ticks==0,ripe)
        outside=next((x,y) for y in range(self.game.world.rows) for x in range(self.game.world.cols) if self.game._field_building_at(x,y) is None)
        before=self.game.world.cells[outside[1]][outside[0]].feature;self.assertEqual(self.game._editor_paint_crop(*outside,0),0);self.assertEqual(self.game.world.cells[outside[1]][outside[0]].feature,before)

    def test_berry_brush_places_permanent_seasonal_bush(self):
        from seasons import DAYS_PER_SEASON

        site=next((x,y) for y in range(self.game.world.rows) for x in range(self.game.world.cols) if self.game.world.cells[y][x].terrain==TerrainType.GRASS and self.game.world.cells[y][x].feature==FeatureType.NONE)
        self.game.calendar_day=0
        self.assertEqual(self.game._editor_paint_berry_bushes(*site,0),1)
        cell=self.game.world.cells[site[1]][site[0]]
        self.assertEqual(cell.feature,FeatureType.BERRY_BUSH)
        self.assertGreater(cell.deposit,0)
        self.game.calendar_day=DAYS_PER_SEASON*2
        self.game.world._tick_berry_fruit(self.game.calendar_day)
        self.assertEqual(cell.feature,FeatureType.BERRY_BUSH)
        self.assertEqual(cell.deposit,0)
        self.game.calendar_day=0
        self.game.world._tick_berry_fruit(self.game.calendar_day)
        self.assertEqual(cell.feature,FeatureType.BERRY_BUSH)
        self.assertGreater(cell.deposit,0)

    def test_editor_removes_selected_building_and_villager(self):
        centre=next((x,y) for y in range(2,self.game.world.rows-2) for x in range(2,self.game.world.cols-2) if self.game._footprint_blocked([(x,y)]) is None)
        self.assertTrue(self.game._editor_place_building(BuildingKind.TENT,*centre));building=max(self.game.buildings.values(),key=lambda b:b.id);self.game.selected_building_id=building.id
        self.assertTrue(self.game._editor_remove_selected_building());self.assertNotIn(building.id,self.game.buildings)
        villager=self.game.villagers[0];self.game.selected_villager_id=villager.id
        self.assertTrue(self.game._editor_remove_selected_villager());self.assertIsNone(self.game._get_villager(villager.id))

    def test_editor_remove_building_tool_also_removes_selected_construction(self):
        centre=next((x,y) for y in range(2,self.game.world.rows-2) for x in range(2,self.game.world.cols-2) if self.game._footprint_blocked([(x,y)]) is None)
        self.assertTrue(self.game._place_construction_site(BuildingKind.TENT,*centre))
        site=max(self.game.construction_sites.values(),key=lambda item:item.id)
        self.game._select_construction(site,detail_only=True)
        self.assertTrue(self.game._editor_remove_selected_building())
        self.assertNotIn(site.id,self.game.construction_sites)
        self.assertIsNone(self.game.selected_construction_id)

    def test_save_dialog_reuses_last_save_name(self):
        self.game._loaded_save_name="my-valley.json"
        self.game._handle_toolbar_action("file_save")
        self.assertEqual(self.game.file_dialog.save_name,"my-valley")

    def test_map_editor_height_view_toggle_persists_when_editor_closes(self):
        self.game.height_sample_enabled=True
        self.game._toggle_height_edit()
        self.assertTrue(self.game.height_sample_enabled)
        self.game._toggle_height_sample()
        self.assertFalse(self.game.height_sample_enabled)
        self.game._toggle_height_edit()
        self.assertFalse(self.game.height_sample_enabled)


if __name__ == "__main__":
    unittest.main()
