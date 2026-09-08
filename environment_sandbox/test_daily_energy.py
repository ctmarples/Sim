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

    def test_satiation_hunger_speed_bands(self):
        game = Game.__new__(Game)
        self.assertEqual(game._satiation_work_mult(0.50), 1.0)
        self.assertEqual(game._satiation_work_mult(0.20), 0.9)
        self.assertEqual(game._satiation_work_mult(0.05), 0.8)
        self.assertEqual(game._satiation_walk_mult(0.50), 1.0)
        self.assertEqual(game._satiation_walk_mult(0.20), 1.0)
        self.assertEqual(game._satiation_walk_mult(0.05), 0.9)

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
