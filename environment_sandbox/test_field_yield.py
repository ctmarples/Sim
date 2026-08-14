"""Focused tests for field yield helpers and fertility/pest semantics."""

from __future__ import annotations

import unittest

from field_yield import (
    build_field_factors,
    calculate_tile_yield_breakdown,
    label_fertility_relative,
    main_limitation,
    stage_effect_pct,
)
from world import disturbance_activity_multiplier


class YieldBreakdownTests(unittest.TestCase):
    def test_pest_not_in_product(self) -> None:
        a = calculate_tile_yield_breakdown(
            base=9,
            pest_control=0.75,
            crop_health=1.0,
            pollination=1.0,
            ecology=1.0,
            fertility=1.0,
            weed_penalty=1.0,
        )
        b = calculate_tile_yield_breakdown(
            base=9,
            pest_control=1.15,
            crop_health=1.0,
            pollination=1.0,
            ecology=1.0,
            fertility=1.0,
            weed_penalty=1.0,
        )
        self.assertEqual(a.final_unrounded, b.final_unrounded)
        self.assertEqual(a.final_rounded, 9)

    def test_staircase_matches_product(self) -> None:
        bd = calculate_tile_yield_breakdown(
            base=9,
            pest_control=0.8,
            crop_health=0.85,
            pollination=1.1,
            ecology=0.5,
            fertility=1.0,
            weed_penalty=0.9,
        )
        self.assertAlmostEqual(bd.after_landscape, 9 * 1.1 * 0.5)
        self.assertAlmostEqual(
            bd.after_crop_condition, bd.after_landscape * 0.85 * 0.9
        )
        self.assertAlmostEqual(bd.final_unrounded, bd.after_crop_condition * 1.0)

    def test_stage_effect_pct(self) -> None:
        self.assertEqual(stage_effect_pct(9.0, 9.0), "±0%")
        self.assertEqual(stage_effect_pct(9.0, 4.5), "-50%")
        self.assertEqual(stage_effect_pct(9.0, 9.9)[:1], "+")


class FertilityLabelTests(unittest.TestCase):
    def test_at_potential_is_optimal_not_degraded(self) -> None:
        self.assertEqual(label_fertility_relative(1.0), "Optimal")
        self.assertEqual(label_fertility_relative(0.99), "Optimal")
        fac = build_field_factors(
            {
                "fertility": 1.0,
                "fertility_potential": 1.0,
                "pest_mult": 1.0,
                "pest_from_bio": 1.0,
                "health": 1.0,
                "health_cap": 1.0,
                "poll_coverage": 0.8,
                "poll_mult": 1.14,
                "ecology": 1.0,
                "disturbance": 0.1,
                "weeds": 0.0,
                "weed_mult": 1.0,
                "erosion": 0.2,
            }
        )
        fert = next(f for f in fac if f.key == "fertility")
        self.assertEqual(fert.state_text, "Optimal")
        self.assertIsNone(fert.effect_text)

    def test_legacy_absolute_confusion_case(self) -> None:
        """0.80 absolute vs 0.80 potential → Optimal, no −20% badge."""
        fac = build_field_factors(
            {
                "fertility": 0.8,
                "fertility_potential": 0.8,
                "pest_mult": 1.0,
                "pest_from_bio": 1.0,
                "health": 1.0,
                "health_cap": 1.0,
                "poll_coverage": 0.5,
                "poll_mult": 1.0,
                "ecology": 1.0,
                "disturbance": 0.1,
                "weeds": 0.0,
                "weed_mult": 1.0,
                "erosion": 0.1,
            }
        )
        fert = next(f for f in fac if f.key == "fertility")
        self.assertEqual(fert.state_text, "Optimal")
        self.assertIsNone(fert.effect_text)
        self.assertEqual(fert.effect_mult, 1.0)


class MainLimitationTests(unittest.TestCase):
    def test_worst_negative_wins(self) -> None:
        fac = build_field_factors(
            {
                "fertility": 1.0,
                "fertility_potential": 1.0,
                "pest_mult": 0.8,
                "pest_from_bio": 0.8,
                "health": 0.9,
                "health_cap": 0.9,
                "poll_coverage": 0.9,
                "poll_mult": 1.17,
                "ecology": 0.4,
                "disturbance": 0.8,
                "weeds": 0.0,
                "weed_mult": 1.0,
                "erosion": 0.5,
            }
        )
        self.assertEqual(main_limitation(fac), "Disturbance")
        pest = next(f for f in fac if f.key == "pest")
        self.assertIsNone(pest.effect_text)
        self.assertEqual(pest.effect_mult, 1.0)


class DisturbanceMonotonicTests(unittest.TestCase):
    def test_multiplier_falls_as_disturbance_rises(self) -> None:
        prev = 1.0
        for d in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
            m = disturbance_activity_multiplier(d)
            self.assertLessEqual(m, prev + 1e-9)
            prev = m


if __name__ == "__main__":
    unittest.main()
