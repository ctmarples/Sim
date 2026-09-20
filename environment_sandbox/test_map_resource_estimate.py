"""Tests for theoretical map resource estimates (equilibrium activity×niche)."""

from __future__ import annotations

import unittest

from map_resource_estimate import (
    MAX_WILD_PER_CELL,
    estimate_map_resources,
    estimate_terrain_counts,
    half_season_sample_day,
    resource_matrix,
    wild_plant_capacity,
)
from random_map_generator import MapOptions
from seasons import N_HALF_SEASONS
from wild_species import WILD_PLANT_MAX_FRACTION


class MapResourceEstimateTests(unittest.TestCase):
    def test_terrain_counts_respect_mix_and_riparian(self):
        counts = estimate_terrain_counts(MapOptions(width=96, height=72))
        total = sum(counts.counts.values())
        self.assertAlmostEqual(total, 96 * 72, places=3)
        self.assertGreater(counts.counts["riparian"], 0.0)
        self.assertGreater(counts.counts["forest"], 0.0)

    def test_half_season_sample_days_cover_year(self):
        days = [half_season_sample_day(h) for h in range(N_HALF_SEASONS)]
        self.assertEqual(days[0], 7.0)
        self.assertEqual(days[7], 105.0)
        self.assertTrue(all(0 <= d < 112 for d in days))

    def test_capacity_matches_game_fraction_times_subcells(self):
        self.assertEqual(WILD_PLANT_MAX_FRACTION, 0.20)
        self.assertEqual(MAX_WILD_PER_CELL, 3)
        self.assertAlmostEqual(wild_plant_capacity(1000.0), 600.0)

    def test_spring_weighted_crops_present(self):
        est = estimate_map_resources(MapOptions())
        spring = est.by_resource(0)
        self.assertGreater(spring.get("peas", 0.0) + spring.get("wheat", 0.0), 50.0)

    def test_thyme_strong_at_authored_summer_late(self):
        """Authored summer-late peak stays strong vs spring (share war vs rivals)."""
        est = estimate_map_resources(MapOptions())
        thyme = [est.by_resource(h).get("thyme", 0.0) for h in range(N_HALF_SEASONS)]
        self.assertGreater(thyme[3], thyme[0])
        self.assertGreater(thyme[3], 10.0)
    def test_activity_profile_shapes_summer_legumes(self):
        est = estimate_map_resources(MapOptions())
        beans = [est.by_resource(h).get("beans", 0.0) for h in range(N_HALF_SEASONS)]
        self.assertGreater(beans[3] + beans[2], beans[0])
        self.assertGreater(max(beans), 10.0)

    def test_pumpkin_follows_autumn_weighted_profile(self):
        est = estimate_map_resources(MapOptions())
        pumpkin = [est.by_resource(h).get("pumpkin", 0.0) for h in range(N_HALF_SEASONS)]
        self.assertLess(pumpkin[0], pumpkin[4])
        self.assertGreater(pumpkin[4], 10.0)

    def test_berries_fruit_in_summer(self):
        est = estimate_map_resources(MapOptions())
        matrix = resource_matrix(est)
        berries = matrix.get("blackberries", [0.0] * 8)
        self.assertGreater(berries[2] + berries[3], 0.0)
        self.assertEqual(berries[0], 0.0)

    def test_flora_cap_not_exceeded_per_terrain(self):
        est = estimate_map_resources(MapOptions())
        meadow_tiles = est.terrain.counts["meadow"]
        cap = wild_plant_capacity(meadow_tiles)
        for half in range(N_HALF_SEASONS):
            plants = sum(
                row.expected_plants
                for row in est.half_seasons[half]
                if row.notes == "on MEADOW"
            )
            self.assertLessEqual(plants, cap + 1e-6)

    def test_temperature_bias_affects_cold_crops(self):
        cold = estimate_map_resources(MapOptions(temperature=0.15))
        hot = estimate_map_resources(MapOptions(temperature=0.85))
        self.assertGreater(
            cold.by_resource(0).get("rye", 0.0),
            hot.by_resource(0).get("rye", 0.0),
        )

    def test_arid_climate_reduces_moisture_loving_stock(self):
        temperate = estimate_map_resources(MapOptions(climate="temperate"))
        arid = estimate_map_resources(MapOptions(climate="arid", rainfall=0.18))
        self.assertGreaterEqual(
            temperate.by_resource(2).get("reeds", 0.0),
            arid.by_resource(2).get("reeds", 0.0),
        )

    def test_terrain_tile_cap_scales_abundance(self):
        """FLORA_TILE_CAP must change absolute plants (not cancel in shares)."""
        from unittest.mock import patch

        from map_resource_estimate import estimate_flora_year, estimate_terrain_counts

        opt = MapOptions()
        terrain = estimate_terrain_counts(opt)
        with patch("map_resource_estimate._flora_tile_cap", return_value=0.20):
            full = estimate_flora_year(terrain, opt)
        with patch("map_resource_estimate._flora_tile_cap", return_value=0.10):
            half = estimate_flora_year(terrain, opt)
        thyme_full = sum(
            r.expected_stock for r in full[3] if r.species_key == "thyme"
        )
        thyme_half = sum(
            r.expected_stock for r in half[3] if r.species_key == "thyme"
        )
        self.assertGreater(thyme_full, 0.0)
        self.assertAlmostEqual(thyme_half / thyme_full, 0.5, places=2)

    def test_species_weight_amplifies_before_competition(self):
        from unittest.mock import patch

        from map_resource_estimate import estimate_flora_year, estimate_terrain_counts

        opt = MapOptions()
        terrain = estimate_terrain_counts(opt)

        def boost_peas(key: str) -> float:
            return 4.0 if key == "peas" else 1.0

        with patch("map_resource_estimate._flora_species_weight", return_value=1.0):
            baseline = estimate_flora_year(terrain, opt)
        with patch(
            "map_resource_estimate._flora_species_weight", side_effect=boost_peas
        ):
            boosted = estimate_flora_year(terrain, opt)
        peas0 = sum(r.expected_stock for r in baseline[0] if r.species_key == "peas")
        peas1 = sum(r.expected_stock for r in boosted[0] if r.species_key == "peas")
        self.assertGreater(peas0, 0.0)
        self.assertGreater(peas1, peas0)

    def test_species_peak_shifts_relative_share(self):
        est = estimate_map_resources(MapOptions())
        spring = est.by_resource(0)
        self.assertGreater(spring.get("peas", 0.0), spring.get("thyme", 0.0))

    def test_unit_yield_range_scales_stock(self):
        from map_resource_estimate import _species_row
        from wild_species import WILD_BY_KEY

        peas = WILD_BY_KEY["peas"]
        low = _species_row(
            peas, half=0, day=7.0, suitability=0.9, ok=True, plants=10.0,
            note="t", forageable=True, unit_lo=1, unit_hi=1,
        )
        high = _species_row(
            peas, half=0, day=7.0, suitability=0.9, ok=True, plants=10.0,
            note="t", forageable=True, unit_lo=3, unit_hi=3,
        )
        self.assertAlmostEqual(low.expected_stock, 10.0)
        self.assertAlmostEqual(high.expected_stock, 30.0)


if __name__ == "__main__":
    unittest.main()
