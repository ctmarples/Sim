"""Farm and field estimate coverage tests."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from game import Game
from world import FeatureType


class FieldEstimateTests(unittest.TestCase):
    def test_empty_planned_field_has_no_live_yield_cells(self) -> None:
        game = Game.__new__(Game)
        cells = {
            (0, 0): SimpleNamespace(feature=FeatureType.NONE, crop_kind=None),
            (1, 0): SimpleNamespace(feature=FeatureType.NONE, crop_kind=None),
        }
        game.world = SimpleNamespace(get_cell=lambda x, y: cells.get((x, y)))
        field = SimpleNamespace(plot_cells=lambda: tuple(cells))

        self.assertEqual(game._field_yield_cells(field), set())

    def test_estimate_counts_only_planted_squares(self) -> None:
        game = Game.__new__(Game)
        cells = {
            (0, 0): SimpleNamespace(feature=FeatureType.CROP_HERB, crop_kind="wheat"),
            (1, 0): SimpleNamespace(feature=FeatureType.NONE, crop_kind=None),
            (0, 1): SimpleNamespace(feature=FeatureType.NONE, crop_kind=None),
            (1, 1): SimpleNamespace(feature=FeatureType.NONE, crop_kind=None),
        }
        game.world = SimpleNamespace(get_cell=lambda x, y: cells.get((x, y)))
        game._farm_produce_yield_at = lambda x, y: 7

        rows = game._crop_overview_from_cells({"wheat": set(cells)})

        self.assertEqual(rows[0]["tiles"], 4)
        self.assertEqual(rows[0]["planted_tiles"], 1)
        self.assertEqual(rows[0]["est_yield"], 7)
        self.assertGreater(rows[0]["max_yield"], rows[0]["est_yield"])


if __name__ == "__main__":
    unittest.main()
