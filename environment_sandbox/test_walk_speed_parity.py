"""Player continuous walk must match villager discrete pace at the same factor."""

from __future__ import annotations

import unittest

from entities import Inventory, Villager
from game import Game
from settings import PLAYBACK_TICKS_AT_X1


class WalkSpeedParityTests(unittest.TestCase):
    def test_continuous_distance_matches_discrete_tiles_per_tick_budget(self) -> None:
        game = Game.__new__(Game)
        game.sim_speed = 1
        game._playback_ticks = lambda: PLAYBACK_TICKS_AT_X1
        game._walk_interval_ticks = lambda: 48
        game._frame_sim_ticks = PLAYBACK_TICKS_AT_X1

        # Identical modifiers → identical move intervals.
        game._player_move_interval = lambda: 48
        game._villager_move_interval = lambda _v: 48

        ticks = game._frame_sim_ticks
        player_tiles = ticks / max(1, game._player_move_interval())
        villager = Villager(1, 0, 0)
        villager_tiles = ticks / max(1, game._villager_move_interval(villager))
        self.assertAlmostEqual(player_tiles, villager_tiles)
        self.assertAlmostEqual(player_tiles, ticks / 48)

    def test_walk_speed_factor_matches_move_interval_scaling(self) -> None:
        game = Game.__new__(Game)
        game._walk_interval_ticks = lambda: 48
        game._satiation_walk_mult = lambda s: 1.0
        game._energy_speed_factor = Game._energy_speed_factor

        slow = game._walk_speed_factor(
            satiation=1.0, food_walk_mult=1.0, happiness=1.0, energy=0.0
        )
        fast = game._walk_speed_factor(
            satiation=1.0, food_walk_mult=1.0, happiness=1.0, energy=1.0
        )
        self.assertLess(slow, fast)
        slow_iv = game._move_interval_for(
            satiation=1.0, food_walk_mult=1.0, happiness=1.0, energy=0.0
        )
        fast_iv = game._move_interval_for(
            satiation=1.0, food_walk_mult=1.0, happiness=1.0, energy=1.0
        )
        self.assertGreater(slow_iv, fast_iv)

    def test_effect_totals_walk_includes_energy(self) -> None:
        from status_effects_ui import effect_totals

        inv = Inventory()
        rested = effect_totals(
            food_walk=1.0,
            food_work=1.0,
            food_hunger=1.0,
            inventory=inv,
            calendar_day=1,
            satiation=1.0,
            happiness=1.0,
            energy=1.0,
        )[0]
        exhausted = effect_totals(
            food_walk=1.0,
            food_work=1.0,
            food_hunger=1.0,
            inventory=inv,
            calendar_day=1,
            satiation=1.0,
            happiness=1.0,
            energy=0.0,
        )[0]
        self.assertAlmostEqual(exhausted / rested, 0.7)


if __name__ == "__main__":
    unittest.main()
