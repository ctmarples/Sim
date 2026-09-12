"""1×1 buildings (fire, tent, annexes) must paint on the world map."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from entities import BuildingKind, default_building_plot
from game import Game
from ui import draw_feature
from world import FeatureType

_ONE_CELL = (
    (BuildingKind.FIRE, FeatureType.FIRE),
    (BuildingKind.TENT, FeatureType.TENT),
    (BuildingKind.BARN, FeatureType.BARN),
    (BuildingKind.COMPOST_HEAP, FeatureType.COMPOST_HEAP),
    (BuildingKind.PANTRY, FeatureType.PANTRY),
    (BuildingKind.CELLAR, FeatureType.CELLAR),
    (BuildingKind.DRYING_RACK, FeatureType.DRYING_RACK),
)


def _opaque_count(surf: pygame.Surface) -> int:
    return sum(
        1
        for x in range(surf.get_width())
        for y in range(surf.get_height())
        if surf.get_at((x, y))[3] > 16
    )


class OneCellBuildingDrawTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    def test_draw_feature_paints_one_cell_buildings(self):
        for _kind, feature in _ONE_CELL:
            canvas = pygame.Surface((160, 160), pygame.SRCALPHA)
            draw_feature(canvas, feature, 80, 80, 80)
            self.assertGreater(
                _opaque_count(canvas),
                200,
                msg=f"{feature.name} draw_feature painted nothing",
            )

    def test_map_draw_shows_fire_and_tent(self):
        game = Game(headless=True)
        game.discovered_cells = {
            (x, y) for y in range(game.world.rows) for x in range(game.world.cols)
        }
        placed: dict[str, tuple[int, int]] = {}
        for kind, feature in (
            (BuildingKind.FIRE, FeatureType.FIRE),
            (BuildingKind.TENT, FeatureType.TENT),
            (BuildingKind.BARN, FeatureType.BARN),
        ):
            found = None
            pw, ph = default_building_plot(kind)
            for y in range(4, game.world.rows - 4):
                for x in range(4, game.world.cols - 4):
                    ox, oy = x - pw // 2, y - ph // 2
                    cells = [
                        (px, py)
                        for py in range(oy, oy + ph)
                        for px in range(ox, ox + pw)
                    ]
                    if game._footprint_blocked(cells) is None:
                        found = (x, y)
                        break
                if found is not None:
                    break
            self.assertIsNotNone(found, msg=f"no site for {kind.name}")
            self.assertTrue(game._editor_place_building(kind, *found))
            cell = game.world.get_cell(*found)
            self.assertIsNotNone(cell)
            self.assertEqual(cell.feature, feature)
            placed[kind.name] = found

        for name, (gx, gy) in placed.items():
            game.camera.x = gx - 4
            game.camera.y = gy - 3
            game._world_layer = None
            game._world_layer_key = None
            game._center_cache = {}
            game._draw_world()
            cx, cy = game._cell_center(gx, gy)
            hits = 0
            for y in range(max(0, cy - 36), min(game.screen.get_height(), cy + 37)):
                for x in range(max(0, cx - 36), min(game.screen.get_width(), cx + 37)):
                    r, g, b = game.screen.get_at((x, y))[:3]
                    # Terrain warp is grey-green; building art is warmer.
                    if r >= 140 and r > g + 8 and r > b + 8:
                        hits += 1
            self.assertGreater(hits, 40, msg=f"{name} missing from map around ({gx},{gy})")


if __name__ == "__main__":
    unittest.main()
