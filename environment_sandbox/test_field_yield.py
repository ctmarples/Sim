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

    def test_moisture_and_texture_enter_product(self) -> None:
        neutral = calculate_tile_yield_breakdown(
            base=10,
            pest_control=1.0,
            crop_health=1.0,
            pollination=1.0,
            ecology=1.0,
            fertility=1.0,
            weed_penalty=1.0,
            moisture=1.0,
            soil_texture=1.0,
        )
        stressed = calculate_tile_yield_breakdown(
            base=10,
            pest_control=1.0,
            crop_health=1.0,
            pollination=1.0,
            ecology=1.0,
            fertility=1.0,
            weed_penalty=1.0,
            moisture=0.8,
            soil_texture=0.9,
        )
        self.assertAlmostEqual(neutral.final_unrounded, 10.0)
        self.assertAlmostEqual(stressed.final_unrounded, 10.0 * 0.8 * 0.9)

    def test_crop_niche_multipliers_neutral_without_species(self) -> None:
        from field_yield import crop_moisture_texture_multipliers

        m, t = crop_moisture_texture_multipliers(
            "not_a_real_crop", soil_moisture=0.2, soil_texture=0.9
        )
        self.assertEqual(m, 1.0)
        self.assertEqual(t, 1.0)

    def test_crop_niche_multipliers_follow_wild_niche(self) -> None:
        from field_yield import crop_moisture_texture_multipliers
        from wild_species import WILD_BY_KEY

        # Sage prefers dry/coarse conditions.
        self.assertIsNotNone(WILD_BY_KEY["sage"].moisture_niche)
        dry, _ = crop_moisture_texture_multipliers(
            "sage", soil_moisture=0.3, soil_texture=0.25
        )
        wet, _ = crop_moisture_texture_multipliers(
            "sage", soil_moisture=0.95, soil_texture=0.25
        )
        self.assertGreater(dry, wet)

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
        self.assertAlmostEqual(bd.after_landscape, 9 * 1.1)
        self.assertAlmostEqual(
            bd.after_crop_condition, bd.after_landscape * 0.5 * 0.85 * 0.9
        )
        self.assertAlmostEqual(bd.final_unrounded, bd.after_crop_condition * 1.0)

    def test_relative_fertility_boost_above_potential(self) -> None:
        from field_yield import fertility_yield_multiplier

        self.assertAlmostEqual(fertility_yield_multiplier(0.8, 0.8), 1.0)
        self.assertAlmostEqual(fertility_yield_multiplier(0.88, 0.8), 1.1)
        boosted = calculate_tile_yield_breakdown(
            base=10,
            pest_control=1.0,
            crop_health=1.0,
            pollination=1.0,
            ecology=1.0,
            fertility=fertility_yield_multiplier(0.88, 0.8),
            weed_penalty=1.0,
        )
        self.assertAlmostEqual(boosted.final_unrounded, 11.0)

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

    def test_compost_above_potential_shows_boost(self) -> None:
        self.assertEqual(label_fertility_relative(1.1), "Boosted")
        fac = build_field_factors(
            {
                "fertility": 0.88,
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
        self.assertEqual(fert.state_text, "Boosted")
        self.assertEqual(fert.effect_text, "+10%")
        self.assertAlmostEqual(fert.effect_mult, 1.1)


class FactorCopyTests(unittest.TestCase):
    def test_expanded_copy_is_plain_language(self) -> None:
        fac = build_field_factors(
            {
                "fertility": 0.65,
                "fertility_potential": 0.70,
                "pest_mult": 1.0,
                "pest_from_bio": 1.0,
                "health": 0.88,
                "health_cap": 1.0,
                "previous_crop_health": 0.60,
                "poll_coverage": 0.3,
                "poll_mult": 0.9,
                "ecology": 0.95,
                "disturbance": 0.15,
                "weeds": 0.3,
                "weed_mult": 0.85,
                "erosion": 0.35,
                "foot_traffic": 0.1,
                "settlement_disturbance": 0.1,
                "nearest_colony_tiles": 7,
                "moisture": 0.5,
                "moisture_mult": 0.95,
                "soil_texture": 0.3,
                "soil_texture_mult": 0.75,
            }
        )
        by_key = {f.key: f for f in fac}
        self.assertIn("bee colonies cover this field", by_key["pollination"].detail_lines[0])
        self.assertEqual(by_key["pollination"].detail_lines[1], "Nearest colony: 7 tiles away")
        self.assertTrue(by_key["pest"].detail_lines[0].startswith("Nearby plant"))
        self.assertEqual(by_key["pest"].right_badge, "cap 100%")
        self.assertIn("current planting", by_key["health"].detail_lines[0])
        self.assertIn("halfway", by_key["health"].detail_lines[0])
        self.assertEqual(
            by_key["health"].detail_lines[1],
            "Current: 88% · Pest-control cap: 100%",
        )
        self.assertIn("Previous crop ended at 60%", by_key["health"].detail_lines[2])
        self.assertIn("started at 80%", by_key["health"].detail_lines[2])
        self.assertEqual(by_key["erosion"].right_badge, "35% risk")
        for key in by_key:
            blob = " ".join(by_key[key].detail_lines)
            self.assertNotIn("×", blob)
            self.assertNotRegex(blob, r"yield [+-]?\d")

    def test_carryover_midpoint(self) -> None:
        from environment import crop_health_carryover

        self.assertAlmostEqual(crop_health_carryover(0.60), 0.80)
        self.assertAlmostEqual(crop_health_carryover(1.0), 1.0)
        self.assertAlmostEqual(crop_health_carryover(0.80), 0.90)


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
