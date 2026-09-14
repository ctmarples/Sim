"""Scenic HERBs must follow their own seasons, not wild-crop dieback."""

from __future__ import annotations

import unittest

from seasons import herb_despawn_rate
from wild_species import WILD_BY_KEY, activity_at_day, species_despawn_rate, species_spawn_rate


class AutumnScenicFloraTests(unittest.TestCase):
    def test_scenic_herbs_not_cleared_by_wild_crop_autumn_dieback(self) -> None:
        day = 70.0  # mid autumn
        clover = WILD_BY_KEY["clover"]
        flax = WILD_BY_KEY["flax"]
        self.assertGreater(species_despawn_rate(flax, day), 0.05)
        self.assertEqual(species_despawn_rate(clover, day), 0.0)
        self.assertEqual(herb_despawn_rate(day, 0, 0, kind="clover"), 0.0)
        self.assertGreater(herb_despawn_rate(day, 0, 0, kind="flax"), 0.05)

    def test_scenic_herbs_can_establish_in_autumn(self) -> None:
        day = 70.0
        clover = WILD_BY_KEY["clover"]
        self.assertGreater(species_spawn_rate(clover, day), 0.0)
        self.assertGreater(activity_at_day(clover, day), 0.2)
        # Effective establishment weight used by the world tick.
        self.assertGreater(
            species_spawn_rate(clover, day)
            * clover.spawn_activity
            * activity_at_day(clover, day),
            0.0,
        )

    def test_wild_crops_still_die_back_in_autumn(self) -> None:
        day = 70.0
        self.assertEqual(species_spawn_rate(WILD_BY_KEY["flax"], day), 0.0)
        self.assertGreater(species_despawn_rate(WILD_BY_KEY["wheat"], day), 0.0)


if __name__ == "__main__":
    unittest.main()
