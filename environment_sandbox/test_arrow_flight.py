"""Arrow flight timing should be short and distance-based."""

from __future__ import annotations

import unittest

from game import Game


class ArrowFlightTests(unittest.TestCase):
    def test_arrow_flight_is_short_not_work_interval(self) -> None:
        game = Game.__new__(Game)
        # Adjacent prey: a few ticks, not hundreds.
        self.assertEqual(game._arrow_flight_duration(0, 0, 1, 0), 4)
        # Max bow range (~5): still under a second at 60 FPS.
        self.assertEqual(game._arrow_flight_duration(0, 0, 5, 0), 12)
        self.assertLessEqual(game._arrow_flight_duration(0, 0, 20, 0), 14)


if __name__ == "__main__":
    unittest.main()
