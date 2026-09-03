import unittest
from game import Game


class DailyEnergyTests(unittest.TestCase):
    def test_energy_speed_bands(self):
        self.assertEqual(Game._energy_speed_factor(0.75), 1.0)
        self.assertEqual(Game._energy_speed_factor(0.40), 0.9)
        self.assertEqual(Game._energy_speed_factor(0.20), 0.8)
        self.assertEqual(Game._energy_speed_factor(0.05), 0.7)

    def test_satiation_is_two_full_bars_per_day(self):
        game = Game.__new__(Game)
        game.ticks_per_day = 36000
        self.assertAlmostEqual(game._satiation_decay() * game.ticks_per_day, 2.0)

    def test_satiation_does_not_reduce_speed(self):
        self.assertEqual(Game._satiation_speed_factor(None, 0.0), 1.0)
        self.assertEqual(Game._satiation_speed_factor(None, 1.0), 1.0)

    def test_seasonal_work_hours(self):
        game = Game.__new__(Game)
        expected = {
            0: (7.0, 20.0),
            28: (5.0, 22.0),
            56: (7.0, 20.0),
            84: (9.0, 18.0),
        }
        for calendar_day, hours in expected.items():
            game.calendar_day = calendar_day
            self.assertEqual(game._work_hours(), hours)


if __name__ == "__main__":
    unittest.main()
