"""Focused tests for happiness bands, breaks, return-to-work, and productivity cap."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from entities import Inventory, Villager, VillagerState
from society import (
    HAPPINESS_WORK_MULT,
    HappinessBand,
    happiness_band,
    happiness_break_chance_this_tick,
    happiness_break_cooldown_ticks,
    happiness_break_duration_ticks,
    happiness_work_mult,
    is_happiness_break_state,
)


class HappinessBandTests(unittest.TestCase):
    def test_band_selection(self) -> None:
        self.assertEqual(happiness_band(1.0), HappinessBand.ENGAGED)
        self.assertEqual(happiness_band(0.75), HappinessBand.ENGAGED)
        self.assertEqual(happiness_band(0.74), HappinessBand.CONTENT)
        self.assertEqual(happiness_band(0.50), HappinessBand.CONTENT)
        self.assertEqual(happiness_band(0.49), HappinessBand.DISENGAGED)
        self.assertEqual(happiness_band(0.25), HappinessBand.DISENGAGED)
        self.assertEqual(happiness_band(0.24), HappinessBand.UNHAPPY)
        self.assertEqual(happiness_band(0.0), HappinessBand.UNHAPPY)

    def test_productivity_cap(self) -> None:
        values = [happiness_work_mult(h) for h in (1.0, 0.6, 0.4, 0.1)]
        self.assertEqual(max(values), HAPPINESS_WORK_MULT[HappinessBand.ENGAGED])
        self.assertEqual(min(values), HAPPINESS_WORK_MULT[HappinessBand.UNHAPPY])
        self.assertAlmostEqual(max(values), 1.05)
        self.assertAlmostEqual(min(values), 0.80)
        self.assertLessEqual(max(values) - 1.0, 0.051)
        self.assertLessEqual(1.0 - min(values), 0.201)


class HappinessBreakTriggerTests(unittest.TestCase):
    def _game(self):
        from game import Game

        game = Game.__new__(Game)
        game.ticks_per_day = 240
        game.calendar_day = 3
        game.day_tick = 120
        game.buildings = {}
        game.world = SimpleNamespace(
            is_walkable=Mock(return_value=True),
            find_path=Mock(return_value=[(0, 0), (1, 0)]),
            home_pos=(0, 0),
        )
        game._clear_villager_path = Mock()
        game._step_villager_toward = Mock(return_value=True)
        return game

    def test_cannot_stack_while_already_breaking(self) -> None:
        game = self._game()
        v = Villager(id=1, x=2, y=2, building_id=1)
        v.state = VillagerState.DISENGAGED_BREAK
        v.break_ticks_left = 20
        v.happiness = 0.3
        self.assertFalse(game._can_start_happiness_break(v))
        self.assertFalse(game._maybe_start_happiness_break(v))

    def test_cannot_interrupt_cargo_haul(self) -> None:
        game = self._game()
        v = Villager(id=1, x=2, y=2, building_id=1)
        v.state = VillagerState.HAULING
        v.inventory = Inventory(bread=2)
        v.happiness = 0.1
        self.assertFalse(game._can_start_happiness_break(v))

    def test_disengaged_break_starts_and_returns(self) -> None:
        game = self._game()
        building = SimpleNamespace(
            id=7,
            center_cell=Mock(return_value=(5, 5)),
        )
        game.buildings = {7: building}
        v = Villager(id=1, x=5, y=5, building_id=7)
        v.state = VillagerState.WORKING
        v.happiness = 0.3
        v.craft_recipe_name = "stew"
        v.base_break_day = int(game.calendar_day)  # skip baseline
        # Force an extra break via direct start.
        game._start_happiness_break(v, "disengaged")
        self.assertTrue(is_happiness_break_state(v.state))
        self.assertGreater(v.break_ticks_left, 0)
        self.assertEqual(v.break_kind, "disengaged")
        self.assertTrue(v.break_reason)
        self.assertTrue(v.break_thought)
        self.assertEqual(v.craft_recipe_name, "stew")
        # Expire break → returning.
        v.break_ticks_left = 0
        v.state = VillagerState.DISENGAGED_BREAK
        game._update_happiness_break(v)
        self.assertEqual(v.state, VillagerState.RETURNING_TO_WORK)
        self.assertEqual(v.target, (5, 5))
        # Arrive → working again (not idle), job stickies kept.
        v.x, v.y = 5, 5
        game._update_happiness_break(v)
        self.assertEqual(v.state, VillagerState.WORKING)
        self.assertEqual(v.break_kind, "")
        self.assertEqual(v.craft_recipe_name, "stew")
        self.assertGreater(v.break_cooldown_ticks, 0)
        self.assertEqual(v.decision_cooldown, 0)

    def test_return_to_work_not_forced_idle_without_action(self) -> None:
        """Quiet workplace ticks must not demote WORKING → IDLE after a break."""
        from entities import WorkPriority

        game = self._game()
        building = SimpleNamespace(
            id=7,
            center_cell=Mock(return_value=(5, 5)),
            kind=SimpleNamespace(name="KITCHEN"),
        )
        game.buildings = {7: building}
        game._construction_delivery_active = Mock(return_value=False)
        game._leftover_build_mats_need_home = Mock(return_value=False)
        game._is_general_hauler = Mock(return_value=False)
        game._try_idle_transport = Mock(return_value=False)
        game._villager_workplace_ids = Mock(return_value=[7])
        game._pick_workplace_building = Mock(return_value=7)
        game._update_workplace_worker = Mock()
        game._villager_has_active_action = Mock(return_value=False)
        game._park_idle_decision = Mock()
        game._set_workplace_idle = Mock()

        v = Villager(id=1, x=5, y=5, building_id=7)
        v.state = VillagerState.WORKING
        v.priorities = [WorkPriority.WORKPLACE, WorkPriority.NONE, WorkPriority.NONE]
        v.happiness = 0.7
        # Simulate the post-break priority pass used inside _update_villagers.
        prios = [WorkPriority.WORKPLACE]
        acted = False
        if WorkPriority.WORKPLACE in prios:
            bid = game._pick_workplace_building(v)
            if bid is not None:
                game._update_workplace_worker(v, bid)
                acted = game._villager_has_active_action(v)
                # Promotion latch removed: IDLE must stay idle, but an already
                # WORKING villager is not demoted by a quiet tick either.
            elif v.state != VillagerState.WORKING:
                game._set_workplace_idle(v)
        elif v.state not in (
            VillagerState.DELIVERING,
            VillagerState.HAULING,
            VillagerState.BUILDING,
            VillagerState.WORKING,
        ):
            v.state = VillagerState.IDLE
        self.assertEqual(v.state, VillagerState.WORKING)
        game._set_workplace_idle.assert_not_called()
        game._park_idle_decision.assert_not_called()
        self.assertFalse(acted)

    def test_quiet_tick_does_not_promote_idle_to_working(self) -> None:
        """Unreachable forage idle must not be forced back into WORKING."""
        from entities import WorkPriority

        game = self._game()
        building = SimpleNamespace(
            id=7,
            center_cell=Mock(return_value=(5, 5)),
            kind=SimpleNamespace(name="FORAGER"),
        )
        game.buildings = {7: building}
        game._construction_delivery_active = Mock(return_value=False)
        game._leftover_build_mats_need_home = Mock(return_value=False)
        game._is_general_hauler = Mock(return_value=False)
        game._try_idle_transport = Mock(return_value=False)
        game._villager_workplace_ids = Mock(return_value=[7])
        game._pick_workplace_building = Mock(return_value=7)

        def _idle_worker(villager, _bid):
            villager.state = VillagerState.IDLE
            villager.target = None

        game._update_workplace_worker = Mock(side_effect=_idle_worker)
        game._park_idle_decision = Mock()

        v = Villager(id=1, x=5, y=5, building_id=7)
        v.state = VillagerState.WORKING
        v.priorities = [WorkPriority.WORKPLACE, WorkPriority.NONE, WorkPriority.NONE]
        v.happiness = 0.7
        game.villagers = [v]
        # Drive one priority pass with hunger/happiness gates skipped.
        game._update_happiness_break = Mock(return_value=False)
        game._villager_needs_food = Mock(return_value=False)
        game._try_start_happiness_break = Mock(return_value=False)
        game._update_villager_building_transition = Mock()
        game._tick_villager_building_transition = Mock()
        # Minimal world tick pieces used before workplace update.
        game._advance_decision_cooldowns = Mock()
        # Call the workplace branch the same way _update_villagers does.
        prios = [WorkPriority.WORKPLACE]
        acted = False
        if WorkPriority.WORKPLACE in prios and v.building_id is not None:
            bid = game._pick_workplace_building(v)
            if bid is not None:
                game._update_workplace_worker(v, bid)
                acted = game._villager_has_active_action(v)
        self.assertEqual(v.state, VillagerState.IDLE)
        self.assertIsNone(v.target)
        self.assertFalse(acted)

    def test_cannot_interrupt_empty_hauler(self) -> None:
        game = self._game()
        v = Villager(id=1, x=2, y=2, building_id=1)
        v.state = VillagerState.HAULING
        v.happiness = 0.1
        self.assertFalse(game._can_start_happiness_break(v))

    def test_wandering_uses_reachable_target_then_returns(self) -> None:
        game = self._game()
        building = SimpleNamespace(id=3, center_cell=Mock(return_value=(4, 4)))
        game.buildings = {3: building}
        game._pick_happiness_wander_target = Mock(return_value=(6, 4))
        v = Villager(id=2, x=4, y=4, building_id=3)
        v.state = VillagerState.WORKING
        v.happiness = 0.1
        # Force wander by patching chance.
        import society as society_mod

        old = society_mod.HAPPINESS_BREAK_CONFIG["unhappy"]["wander_chance"]
        society_mod.HAPPINESS_BREAK_CONFIG["unhappy"]["wander_chance"] = 1.0
        try:
            game._start_happiness_break(v, "unhappy")
        finally:
            society_mod.HAPPINESS_BREAK_CONFIG["unhappy"]["wander_chance"] = old
        self.assertEqual(v.state, VillagerState.WANDERING)
        self.assertEqual(v.target, (6, 4))
        # Step until arrived.
        v.x, v.y = 6, 4
        v.break_ticks_left = 5
        game._update_happiness_break(v)
        self.assertEqual(v.state, VillagerState.DISENGAGED_BREAK)
        v.break_ticks_left = 0
        game._update_happiness_break(v)
        self.assertEqual(v.state, VillagerState.RETURNING_TO_WORK)

    def test_break_config_is_data_driven(self) -> None:
        ticks = 480
        dur = happiness_break_duration_ticks("base", ticks)
        self.assertEqual(dur, happiness_break_duration_ticks("base", ticks))
        self.assertGreater(happiness_break_cooldown_ticks(ticks), 0)
        self.assertGreater(happiness_break_chance_this_tick("unhappy", ticks), 0)
        self.assertGreater(
            happiness_break_chance_this_tick("unhappy", ticks),
            happiness_break_chance_this_tick("disengaged", ticks),
        )

    def test_work_interval_uses_capped_happiness_mult(self) -> None:
        from game import Game

        game = Game.__new__(Game)
        game._satiation_work_mult = Mock(return_value=1.0)
        game._energy_speed_factor = Mock(return_value=1.0)
        game._work_interval_ticks = Mock(return_value=100)
        engaged = game._work_interval_for(
            satiation=1.0, food_work_mult=1.0, happiness=0.9, energy=1.0
        )
        unhappy = game._work_interval_for(
            satiation=1.0, food_work_mult=1.0, happiness=0.05, energy=1.0
        )
        # Higher happiness → shorter interval (faster work).
        self.assertLess(engaged, unhappy)
        # Cap: unhappy is 0.80 vs engaged 1.05 → interval ratio ≈ 1.05/0.80
        self.assertAlmostEqual(unhappy / engaged, 1.05 / 0.80, places=2)


if __name__ == "__main__":
    unittest.main()
