"""Haul pickup/drop-off timing uses Transport skill × 0.5 effort."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from society import SkillState, SkillType, work_effort_mult


class HaulTransferTimingTests(unittest.TestCase):
    def test_haul_effort_is_half(self) -> None:
        self.assertAlmostEqual(work_effort_mult("haul"), 0.5)

    def test_transfer_interval_uses_transport_not_building_skill(self) -> None:
        from game import Game

        game = Game.__new__(Game)
        game.political = object()
        game.buildings = {}
        game._trait_work_mult = lambda _v: 1.0
        game._work_interval_for = (
            lambda **kwargs: max(6, int(round(100 / max(0.15, kwargs["skill_mult"]))))
        )
        game._villager_inside_building = lambda _v: None
        game._gain_job_skill = Mock()

        # Transport L3 → efficiency 1.16; Crafting L1 must not affect haul time.
        villager = SimpleNamespace(
            satiation=1.0,
            food_work_mult=1.0,
            happiness=1.0,
            energy=1.0,
            skills={
                SkillType.TRANSPORT: SkillState(level=3, potential=10),
                SkillType.CRAFTING: SkillState(level=1, potential=10),
            },
            building_id=1,
            assigned_to_home=False,
            work_cooldown=0,
            name="Tester",
            id=1,
        )
        with (
            patch(
                "sociopolitical.work_efficiency_multiplier",
                return_value=1.0,
            ),
            patch(
                "sociopolitical_hooks.job_matches_strongest",
                return_value=False,
            ),
        ):
            ticks = game._hauler_transfer_interval(villager)
            # 100 / 1.16 * 0.5 ≈ 43
            self.assertEqual(ticks, 43)
            game._apply_hauler_transfer_cooldown(villager)

        self.assertEqual(villager.work_cooldown, 43)
        game._gain_job_skill.assert_called_once_with(
            villager, "HOME", action="haul"
        )


if __name__ == "__main__":
    unittest.main()
