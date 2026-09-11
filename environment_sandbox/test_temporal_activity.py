"""Temporal activity_profile + shared half-season calendar."""

from __future__ import annotations

import unittest

from environment import env_sample_period
from seasons import (
    HALF_SEASON_DAYS,
    N_HALF_SEASONS,
    YEAR_DAYS,
    half_season_index,
    half_season_progress,
    mushroom_spawn_rate,
    wood_bush_spawn_rate,
)
from terrain_flecks import period_for_day
from wild_species import (
    WILD_BY_KEY,
    activity_at_day,
    normalize_activity_profile,
    species_fruiting,
)
from world import FeatureType, TerrainType, World


class HalfSeasonCalendarTests(unittest.TestCase):
    def test_shared_helpers_agree(self):
        for day in range(YEAR_DAYS):
            self.assertEqual(half_season_index(day), period_for_day(day))
            self.assertEqual(half_season_index(day), env_sample_period(day))

    def test_period_bounds(self):
        self.assertEqual(half_season_index(0), 0)
        self.assertEqual(half_season_index(13), 0)
        self.assertEqual(half_season_index(14), 1)
        self.assertEqual(half_season_index(56), 4)  # autumn early
        self.assertEqual(half_season_index(70), 5)  # autumn late
        self.assertEqual(half_season_index(84), 6)  # winter early
        self.assertEqual(half_season_index(111), 7)


class ActivityProfileTests(unittest.TestCase):
    def test_none_profile_is_full_activity(self):
        from wild_species import WildSpeciesDef

        species = WildSpeciesDef("x", "X", "HERB", ("GRASS",))
        self.assertEqual(activity_at_day(species, 0), 1.0)
        self.assertEqual(activity_at_day(None, 40), 1.0)

    def test_wraparound_winter_late_to_spring_early(self):
        mushroom = WILD_BY_KEY["mushroom"]
        # Mid winter-late → spring-early boundary (day 0 / 112).
        at_end = activity_at_day(mushroom, YEAR_DAYS - 0.01)
        at_start = activity_at_day(mushroom, 0.0)
        # Profile[7]=0.05, profile[0]=0.05 — near-constant across wrap.
        self.assertAlmostEqual(at_end, 0.05, places=2)
        self.assertAlmostEqual(at_start, 0.05, places=2)

    def test_same_day_is_deterministic(self):
        rye = WILD_BY_KEY["rye"]
        a = activity_at_day(rye, 91.25)
        b = activity_at_day(rye, 91.25)
        self.assertEqual(a, b)

    def test_mushroom_strongly_autumnal(self):
        m = WILD_BY_KEY["mushroom"]
        # Sample near the start of each half-season (before lerp toward next).
        spring = activity_at_day(m, 0.5)
        summer = activity_at_day(m, 28.5)
        autumn_early = activity_at_day(m, 56.5)
        autumn_late = activity_at_day(m, 70.5)
        self.assertLess(spring, 0.2)
        self.assertLess(summer, 0.2)
        self.assertGreater(autumn_early, 0.85)
        self.assertGreater(autumn_late, 0.85)
        self.assertGreater(autumn_early, summer * 5)

    def test_fallen_wood_appearance_peaks_late_autumn_winter_early(self):
        w = WILD_BY_KEY["wood_bush"]
        summer = activity_at_day(w, 28.5)
        autumn_late = activity_at_day(w, 70.5)
        winter_early = activity_at_day(w, 84.5)
        self.assertGreater(autumn_late, summer)
        self.assertGreater(winter_early, 0.6)
        self.assertGreaterEqual(autumn_late, winter_early * 0.9)

    def test_rye_more_cool_season_active_than_wheat(self):
        rye = WILD_BY_KEY["rye"]
        wheat = WILD_BY_KEY["wheat"]
        winter_late = 98.5
        spring_early = 0.5
        self.assertGreater(
            activity_at_day(rye, winter_late),
            activity_at_day(wheat, winter_late),
        )
        self.assertGreater(
            activity_at_day(rye, spring_early),
            activity_at_day(wheat, spring_early),
        )

    def test_peas_earlier_than_beans(self):
        peas = WILD_BY_KEY["peas"]
        beans = WILD_BY_KEY["beans"]
        spring_late = 14.5
        summer_late = 42.5
        self.assertGreater(
            activity_at_day(peas, spring_late),
            activity_at_day(beans, spring_late),
        )
        self.assertGreater(
            activity_at_day(beans, summer_late),
            activity_at_day(peas, summer_late),
        )

    def test_cabbage_turnip_strong_autumn(self):
        for key in ("cabbage", "turnip"):
            sp = WILD_BY_KEY[key]
            autumn_early = activity_at_day(sp, 56.5)
            self.assertGreaterEqual(autumn_early, 0.9)

    def test_normalize_rejects_bad_length(self):
        with self.assertRaises(ValueError):
            normalize_activity_profile((1.0, 0.0))


class FruitPhenologyTests(unittest.TestCase):
    def test_hazel_fruits_in_autumn_not_spring(self):
        hazel = WILD_BY_KEY["hazel"]
        self.assertFalse(species_fruiting(hazel, 10))
        self.assertTrue(species_fruiting(hazel, 60))

    def test_blackberry_fruits_in_summer_window(self):
        bush = WILD_BY_KEY["blackberry"]
        self.assertTrue(species_fruiting(bush, 40))
        self.assertFalse(species_fruiting(bush, 70))


class RuntimeIntegrationTests(unittest.TestCase):
    def test_mushroom_spawn_rate_uses_activity(self):
        # Mid-summer should be near-zero; autumn early much higher.
        summer = mushroom_spawn_rate(35, 0, 0)
        autumn = mushroom_spawn_rate(56 + 7, 0, 0)
        self.assertLess(summer, autumn * 0.25)

    def test_wood_spawn_rate_high_in_winter_early(self):
        summer = wood_bush_spawn_rate(35, 0, 0)
        winter_early = wood_bush_spawn_rate(84 + 7, 0, 0)
        self.assertGreater(winter_early, summer)

    def test_fallen_wood_persists_when_activity_drops(self):
        world = World(8, 8)
        cell = world.cells[3][3]
        cell.terrain = TerrainType.GRASS
        cell.feature = FeatureType.WOOD_BUSH
        cell.crop_kind = "wood_bush"
        cell.deposit = 1
        cell.growth_ticks = world._fallen_wood_lifetime_ticks()
        world._rebuild_growth_index()
        # Age a few ticks in spring — wood must remain (lifetime ≫ ticks).
        world.tick_bulk(10, day=10.0)
        self.assertEqual(world.cells[3][3].feature, FeatureType.WOOD_BUSH)
        self.assertGreater(world.cells[3][3].growth_ticks, 0)

    def test_berry_bushes_not_removed_in_winter(self):
        world = World(6, 6)
        cell = world.cells[2][2]
        cell.terrain = TerrainType.GRASS
        cell.feature = FeatureType.BERRY_BUSH
        cell.crop_kind = "blackberry"
        cell.tree_age_years = 1
        cell.deposit = 4
        world._tick_berry_fruit(90.0)  # winter
        self.assertEqual(world.cells[2][2].feature, FeatureType.BERRY_BUSH)
        self.assertEqual(world.cells[2][2].deposit, 0)  # fruit cleared, bush remains

    def test_plants_json_projection_keeps_activity_profiles(self):
        from developer_tools.plant_editor import PlantEditorService

        ok, _ = PlantEditorService().load()
        self.assertTrue(ok)
        self.assertIsNotNone(WILD_BY_KEY["wheat"].activity_profile)
        self.assertEqual(len(WILD_BY_KEY["mushroom"].activity_profile), 8)
        self.assertEqual(WILD_BY_KEY["mushroom"].activity_profile[4], 1.0)


class ProgressHelperTests(unittest.TestCase):
    def test_progress_fraction(self):
        period, frac = half_season_progress(14 + HALF_SEASON_DAYS * 0.25)
        self.assertEqual(period, 1)
        self.assertAlmostEqual(frac, 0.25, places=5)
        self.assertEqual(N_HALF_SEASONS, 8)


if __name__ == "__main__":
    unittest.main()
