"""Night sight shroud and player sleep-until-morning."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from entities import Player
from game import Game
from settings import NIGHT_SIGHT_MAX_CELLS, NIGHT_SIGHT_MIN_CELLS


class NightSightAndSleepTests(unittest.TestCase):
    def _game(self) -> Game:
        game = Game.__new__(Game)
        game.calendar_day = 10
        game.ticks_per_day = 2400
        game.player = Player(0, 0)
        game.player.energy = 0.2
        game.scenario = Mock()
        game.scenario.forces_night = Mock(return_value=False)
        game.buildings = {}
        game.villagers = []
        game._set_status = Mock()
        game.building_inspect = Mock(open=False, close=Mock())
        game.headless = True
        game._sleep_started = None
        game._sleep_finished = False
        game._sleep_clock_applied = False
        game._sleep_kind = None
        game._advance_day = Mock()
        game.camera = Mock()
        game.camera.view_cell = Mock(return_value=40.0)
        game._player_inside_building_id = None
        game.balance = Mock()
        game.balance.get_int = Mock(return_value=1)
        return game

    def test_sight_radius_narrowest_at_night_midpoint(self) -> None:
        game = self._game()
        # Spring work 7–20 → dusk at 20/24, dawn at 7/24.
        # Mid-night: halfway through night span.
        start_h, end_h = 7.0, 20.0
        night_len = (24.0 - end_h) + start_h
        mid_hour = (end_h + night_len / 2.0) % 24.0
        game._work_hours = Mock(return_value=(start_h, end_h))
        game._is_night = Mock(return_value=True)

        def set_hour(hour: float) -> None:
            game._calendar_day_fraction = Mock(return_value=hour / 24.0)

        set_hour(end_h)  # dusk
        dusk_r = game._night_sight_radius_cells()
        set_hour(mid_hour)
        mid_r = game._night_sight_radius_cells()
        set_hour(start_h - 0.01)  # just before dawn
        dawn_r = game._night_sight_radius_cells()

        self.assertIsNotNone(dusk_r)
        self.assertIsNotNone(mid_r)
        self.assertIsNotNone(dawn_r)
        assert dusk_r is not None and mid_r is not None and dawn_r is not None
        self.assertAlmostEqual(mid_r, NIGHT_SIGHT_MIN_CELLS, places=2)
        self.assertGreater(dusk_r, mid_r)
        self.assertGreater(dawn_r, mid_r)
        # Dusk / dawn open to the authored max (world cells, zoom-independent).
        self.assertAlmostEqual(dusk_r, NIGHT_SIGHT_MAX_CELLS, places=2)
        self.assertGreater(dawn_r, NIGHT_SIGHT_MAX_CELLS * 0.95)

    def test_sight_radius_ignores_zoom(self) -> None:
        game = self._game()
        game._work_hours = Mock(return_value=(7.0, 20.0))
        game._is_night = Mock(return_value=True)
        game._calendar_day_fraction = Mock(return_value=22.0 / 24.0)
        game.camera.view_cell = Mock(return_value=20.0)
        zoomed_in = game._night_sight_radius_cells()
        game.camera.view_cell = Mock(return_value=80.0)
        zoomed_out = game._night_sight_radius_cells()
        self.assertEqual(zoomed_in, zoomed_out)

    def test_dusk_sight_uses_authored_max_cells(self) -> None:
        game = self._game()
        game._work_hours = Mock(return_value=(7.0, 20.0))
        game._is_night = Mock(return_value=True)
        game._calendar_day_fraction = Mock(return_value=20.0 / 24.0)
        dusk_r = game._night_sight_radius_cells()
        assert dusk_r is not None
        self.assertAlmostEqual(dusk_r, NIGHT_SIGHT_MAX_CELLS, places=2)

    def test_daytime_has_no_sight_shroud(self) -> None:
        game = self._game()
        game._is_night = Mock(return_value=False)
        self.assertIsNone(game._night_sight_radius_cells())

    def test_indoor_does_not_disable_sight_shroud(self) -> None:
        game = self._game()
        game._work_hours = Mock(return_value=(7.0, 20.0))
        game._is_night = Mock(return_value=True)
        game._calendar_day_fraction = Mock(return_value=22.0 / 24.0)
        game._player_inside_building_id = 3
        game._sleep_blocking = Mock(return_value=False)
        self.assertIsNotNone(game._night_sight_radius_cells())

    def test_sleep_from_evening_advances_to_next_dawn(self) -> None:
        game = self._game()
        game._work_hours = Mock(return_value=(7.0, 20.0))
        # 21:00 — after dusk, same calendar night.
        game.day_tick = round(2400 * (1.0 - 21.0 / 24.0))
        game._skip_to_next_morning()
        # hour 21 >= 7 → advance day, then dawn tick
        game._advance_day.assert_called_once()
        expected = round(2400 * (1.0 - 7.0 / 24.0))
        self.assertEqual(game.day_tick, expected)
        self.assertEqual(game.player.energy, 1.0)

    def test_sleep_before_dawn_stays_same_morning(self) -> None:
        game = self._game()
        game._work_hours = Mock(return_value=(7.0, 20.0))
        game.day_tick = round(2400 * (1.0 - 3.0 / 24.0))  # 03:00
        game._skip_to_next_morning()
        game._advance_day.assert_not_called()
        self.assertEqual(game.day_tick, round(2400 * (1.0 - 7.0 / 24.0)))

    def test_player_sleep_applies_clock_when_eyes_closed(self) -> None:
        game = self._game()
        game._work_hours = Mock(return_value=(7.0, 20.0))
        game.day_tick = round(2400 * (1.0 - 22.0 / 24.0))
        game.begin_player_sleep()
        self.assertEqual(game._sleep_kind, "player")
        self.assertTrue(game._sleep_blocking())
        # Force mid-veil time.
        import time as time_mod

        game._sleep_started = time_mod.monotonic() - 0.6
        game.headless = False
        game._tick_sleep_transition()
        self.assertTrue(game._sleep_clock_applied)
        self.assertEqual(game.player.energy, 1.0)

    def test_player_sleep_rests_and_homes_villagers(self) -> None:
        from entities import Building, BuildingKind, Villager, VillagerState
        from world import World

        game = self._game()
        game._work_hours = Mock(return_value=(7.0, 20.0))
        game.day_tick = round(2400 * (1.0 - 22.0 / 24.0))
        game.world = World(8, 8)
        house = Building(9, BuildingKind.HOUSE, 4, 4)
        game.buildings = {house.id: house}
        housed = Villager(1, 1, 1, housed=True, housing_id=house.id)
        housed.energy = 0.15
        housed.state = VillagerState.WORKING
        housed.haul_building_id = 3
        housed.target = (2, 2)
        unhoused = Villager(2, 6, 6, housed=False, housing_id=None)
        unhoused.energy = 0.2
        unhoused.state = VillagerState.HAULING
        game.villagers = [housed, unhoused]
        game._abort_work_swing = Mock()
        game._clear_villager_path = Mock()

        game._skip_to_next_morning()

        self.assertEqual(housed.energy, 1.0)
        self.assertEqual(housed.state, VillagerState.IDLE)
        self.assertIsNone(housed.haul_building_id)
        self.assertEqual((housed.x, housed.y), house.center_cell())
        self.assertEqual(unhoused.energy, 1.0)
        self.assertEqual(unhoused.state, VillagerState.IDLE)
        self.assertEqual((unhoused.x, unhoused.y), (6, 6))


if __name__ == "__main__":
    unittest.main()
