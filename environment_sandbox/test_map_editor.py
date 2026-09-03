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


if __name__ == "__main__":
    unittest.main()
