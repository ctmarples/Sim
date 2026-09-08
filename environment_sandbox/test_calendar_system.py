import unittest

from calendar_system import CalendarMode, CalendarPolicy
from seasons import DAYS_PER_SEASON, Season


class CalendarPolicyTests(unittest.TestCase):
    def test_legacy_uses_historical_day_step(self):
        policy = CalendarPolicy()
        policy.begin(Season.SPRING)
        self.assertEqual(policy.active_days_in_season, DAYS_PER_SEASON)
        self.assertEqual(policy.ecology_units_per_day, 1.0)

    def test_flexible_day_count_does_not_change_season_span(self):
        policy = CalendarPolicy(mode=CalendarMode.FLEXIBLE)
        policy.season_days[Season.SPRING] = 4
        policy.begin(Season.SPRING)
        self.assertEqual(policy.ecology_units_per_day, 7.0)
        self.assertEqual(policy.ecology_units_per_day * 4, DAYS_PER_SEASON)

    def test_mode_change_waits_for_season_boundary(self):
        policy = CalendarPolicy()
        policy.begin(Season.SPRING)
        policy.queue(CalendarMode.FLEXIBLE, {Season.SUMMER: 5})
        self.assertEqual(policy.mode, CalendarMode.LEGACY)
        self.assertEqual(policy.active_days_in_season, DAYS_PER_SEASON)
        policy.enter_season(Season.SUMMER)
        self.assertEqual(policy.mode, CalendarMode.FLEXIBLE)
        self.assertEqual(policy.active_days_in_season, 5)

    def test_apply_now_switches_mode_immediately(self):
        policy = CalendarPolicy()
        policy.begin(Season.SPRING)
        policy.apply_now(
            CalendarMode.FLEXIBLE,
            {Season.SPRING: 4, Season.SUMMER: 5},
            current_season=Season.SPRING,
        )
        self.assertEqual(policy.mode, CalendarMode.FLEXIBLE)
        self.assertIsNone(policy.pending_mode)
        self.assertEqual(policy.active_days_in_season, 4)
        self.assertEqual(policy.season_days[Season.SUMMER], 5)

    def test_current_season_length_change_waits_until_it_returns(self):
        policy = CalendarPolicy(mode=CalendarMode.FLEXIBLE)
        policy.begin(Season.SPRING)
        policy.queue(CalendarMode.FLEXIBLE, {Season.SPRING: 6})
        policy.enter_season(Season.SUMMER)
        self.assertEqual(policy.season_days[Season.SPRING], 4)
        policy.enter_season(Season.SPRING)
        self.assertEqual(policy.active_days_in_season, 6)

    def test_round_trip_preserves_pending_configuration(self):
        policy = CalendarPolicy(mode=CalendarMode.FLEXIBLE)
        policy.begin(Season.AUTUMN)
        policy.queue(CalendarMode.LEGACY, {Season.WINTER: 7})
        restored = CalendarPolicy.from_dict(policy.to_dict(), Season.AUTUMN)
        self.assertEqual(restored.mode, CalendarMode.FLEXIBLE)
        self.assertEqual(restored.pending_mode, CalendarMode.LEGACY)
        self.assertEqual(restored.pending_season_days[Season.WINTER], 7)


if __name__ == "__main__":
    unittest.main()
