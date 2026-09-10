"""Scenario tests for the three-mode happiness model."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from entities import (
    Building,
    BuildingKind,
    RationMode,
    Villager,
    VillagerState,
)
from happiness import (
    HAP_COVENANT_EXTRACTIVE,
    HAP_HALF_RATION,
    HAP_JOB_OFF_SKILL_WORKING,
    HAP_MEAL_DISLIKED_CAP,
    HAP_MEAL_FAVOURITE_CAP,
    HAP_OFFICE_OFF_SKILL,
    HAP_PROTECTED_HABITAT_EXTRACTIVE,
    HAP_THERMAL_PER_LEVEL,
    HAPPINESS_BASE,
    HAPPINESS_CONVERGENCE_PER_DAY,
    HAPPINESS_TARGET_MAX,
    HAPPINESS_TARGET_MIN,
    apply_immediate_happiness,
    apply_meal_mood,
    clamp_target,
    compute_happiness_target,
    refresh_happiness_breakdown,
    set_temporary_capped_mood,
    sum_temporary_moods,
    sync_displayed_happiness,
    tick_underlying_happiness,
    temporary_mood_value,
)
from seasons import TempImpact
from society import SkillType, skills_from_dict
from sociopolitical import SettlementPoliticalState


def _skills(**levels: int):
    return skills_from_dict(
        {k: {"level": v, "potential": max(5, v), "peak": v} for k, v in levels.items()}
    )


def _building(bid: int, kind: BuildingKind) -> Building:
    b = Building(id=bid, kind=kind, x=0, y=0)
    return b


class HappinessTargetTests(unittest.TestCase):
    def test_ordinary_stable_conditions_around_content(self) -> None:
        v = Villager(id=1, x=0, y=0, housed=True, housing_id=1, housing_need=1)
        v.last_meal = ["bread", "meat"]
        v.ration_mode = RationMode.NORMAL
        v.state = VillagerState.IDLE
        buildings = {1: _building(1, BuildingKind.HOUSE)}
        target, comps = compute_happiness_target(v, buildings=buildings)
        self.assertGreaterEqual(target, 0.50)
        self.assertLessEqual(target, 0.74)
        keys = {c.key for c in comps}
        self.assertIn("base", keys)
        self.assertIn("meal_variety", keys)

    def test_best_plausible_target_reaches_engaged(self) -> None:
        v = Villager(
            id=1,
            x=0,
            y=0,
            housed=True,
            housing_id=1,
            housing_need=1,
            building_id=2,
            skills=_skills(farming=5, labour=2),
        )
        v.last_meal = ["bread", "meat", "stew"]
        v.ration_mode = RationMode.DOUBLE
        v.state = VillagerState.WORKING
        buildings = {
            1: _building(1, BuildingKind.HOUSE),  # level high enough for excess
            2: _building(2, BuildingKind.FARM),
        }
        # HOUSE is level 3 typically; ensure excess path exists via housing_level_of
        target, _ = compute_happiness_target(v, buildings=buildings)
        self.assertGreaterEqual(target, 0.90)
        self.assertLessEqual(target, HAPPINESS_TARGET_MAX)

    def test_worst_plausible_target_near_floor(self) -> None:
        v = Villager(
            id=1,
            x=0,
            y=0,
            housed=False,
            building_id=2,
            skills=_skills(farming=5, labour=1),
        )
        v.last_meal = []
        v.ration_mode = RationMode.HALF
        v.state = VillagerState.WORKING
        buildings = {2: _building(2, BuildingKind.FORESTER)}
        political = SettlementPoliticalState(
            enacted_principle_ids=["assigned_labour", "protected_habitat"],
            institution_ids=["settlement_office", "covenant_of_the_land"],
        )
        peers = [
            v,
            Villager(id=2, x=0, y=0, ration_mode=RationMode.DOUBLE),
        ]
        temp = TempImpact(
            kind="cold", level=3, raw_level=3, protection=0,
            walk_mult=0.7, energy_mult=1.3, temp_c=-5.0,
        )
        target, comps = compute_happiness_target(
            v,
            buildings=buildings,
            political=political,
            villagers=peers,
            temp_impact=temp,
        )
        self.assertLessEqual(target, 0.10)
        self.assertGreaterEqual(target, HAPPINESS_TARGET_MIN)
        keys = {c.key for c in comps}
        self.assertIn("housing_missing", keys)
        self.assertIn("office_off_skill", keys)
        self.assertIn("covenant_extractive", keys)
        self.assertIn("thermal_cold", keys)

    def test_off_skill_only_while_working_then_recovers(self) -> None:
        v = Villager(
            id=1,
            x=0,
            y=0,
            housed=True,
            housing_id=1,
            building_id=2,
            skills=_skills(farming=5),
            underlying_happiness=0.65,
            happiness=0.65,
        )
        v.last_meal = ["bread"]
        buildings = {
            1: _building(1, BuildingKind.HOUSE_SMALL),
            2: _building(2, BuildingKind.FORESTER),
        }
        v.state = VillagerState.WORKING
        t_work, comps = compute_happiness_target(v, buildings=buildings)
        self.assertTrue(any(c.key == "job_off_skill" for c in comps))
        v.state = VillagerState.IDLE
        t_idle, comps2 = compute_happiness_target(v, buildings=buildings)
        self.assertFalse(any(c.key == "job_off_skill" for c in comps2))
        self.assertGreater(t_idle, t_work)

        # Drift recovery after reassignment to matched farm.
        v.building_id = 3
        buildings[3] = _building(3, BuildingKind.FARM)
        v.state = VillagerState.WORKING
        for _ in range(400):
            tick_underlying_happiness(
                v, 1.0 / 240.0, buildings=buildings, villagers=[v]
            )
        self.assertGreater(float(v.underlying_happiness), 0.60)

    def test_thermal_scales_and_recovers(self) -> None:
        v = Villager(id=1, x=0, y=0, housed=True, housing_id=1, last_meal=["bread"])
        buildings = {1: _building(1, BuildingKind.HOUSE_SMALL)}
        cold1 = TempImpact(
            kind="cold", level=1, raw_level=2, protection=1,
            walk_mult=0.95, energy_mult=1.05, temp_c=0.0,
        )
        cold3 = TempImpact(
            kind="cold", level=3, raw_level=3, protection=0,
            walk_mult=0.7, energy_mult=1.3, temp_c=-10.0,
        )
        t1, c1 = compute_happiness_target(v, buildings=buildings, temp_impact=cold1)
        t3, c3 = compute_happiness_target(v, buildings=buildings, temp_impact=cold3)
        self.assertAlmostEqual(
            next(c.amount for c in c1 if c.key.startswith("thermal")),
            HAP_THERMAL_PER_LEVEL,
        )
        self.assertAlmostEqual(
            next(c.amount for c in c3 if c.key.startswith("thermal")),
            HAP_THERMAL_PER_LEVEL * 3,
        )
        self.assertLess(t3, t1)
        t_ok, c_ok = compute_happiness_target(v, buildings=buildings, temp_impact=None)
        self.assertTrue(any(c.key == "thermal_comfort" for c in c_ok))
        self.assertFalse(any(c.key.startswith("thermal_cold") for c in c_ok))
        self.assertGreater(t_ok, t1)


def _plain_villager(**kwargs) -> Villager:
    v = Villager(**kwargs)
    v.virtues = []
    v.vices = []
    return v


class MealMoodTests(unittest.TestCase):
    def test_disliked_food_resets_not_stacks(self) -> None:
        v = _plain_villager(id=1, x=0, y=0, underlying_happiness=0.6, happiness=0.6)
        apply_meal_mood(
            v, favourite=False, ticks_per_day=2400, icon="garlic", label="disliked", day=1
        )
        first = sum_temporary_moods(v)
        self.assertAlmostEqual(first, HAP_MEAL_DISLIKED_CAP, places=3)
        # Partial decay then eat again → reset to same cap.
        moods = v.happiness_temporary
        moods[0]["ticks_left"] = moods[0]["ticks_total"] // 2
        mid = sum_temporary_moods(v)
        self.assertLess(abs(mid), abs(first))
        apply_meal_mood(
            v, favourite=False, ticks_per_day=2400, icon="garlic", label="disliked", day=2
        )
        self.assertEqual(len(v.happiness_temporary), 1)
        self.assertAlmostEqual(sum_temporary_moods(v), HAP_MEAL_DISLIKED_CAP, places=3)

    def test_favourite_food_resets_not_stacks(self) -> None:
        v = _plain_villager(id=1, x=0, y=0, underlying_happiness=0.6, happiness=0.6)
        apply_meal_mood(
            v, favourite=True, ticks_per_day=2400, icon="stew", label="fav", day=1
        )
        apply_meal_mood(
            v, favourite=True, ticks_per_day=2400, icon="stew", label="fav", day=2
        )
        self.assertEqual(len(v.happiness_temporary), 1)
        self.assertAlmostEqual(sum_temporary_moods(v), HAP_MEAL_FAVOURITE_CAP, places=3)

    def test_normal_food_does_not_clear_meal_mood(self) -> None:
        v = _plain_villager(id=1, x=0, y=0, underlying_happiness=0.6, happiness=0.6)
        apply_meal_mood(
            v, favourite=True, ticks_per_day=2400, icon="stew", label="fav", day=1
        )
        apply_meal_mood(
            v, favourite=None, ticks_per_day=2400, icon="bread", label="ok", day=2
        )
        self.assertEqual(len(v.happiness_temporary), 1)
        self.assertAlmostEqual(sum_temporary_moods(v), HAP_MEAL_FAVOURITE_CAP, places=3)


class PoliticalConflictTests(unittest.TestCase):
    def test_assigned_labour_conflict_begins_and_ends(self) -> None:
        v = Villager(id=1, x=0, y=0, housed=True, housing_id=1)
        buildings = {1: _building(1, BuildingKind.HOUSE_SMALL)}
        pol = SettlementPoliticalState(enacted_principle_ids=["assigned_labour"])
        t0, c0 = compute_happiness_target(v, buildings=buildings, political=None)
        t1, c1 = compute_happiness_target(v, buildings=buildings, political=pol)
        self.assertTrue(any(c.key == "assigned_labour_unassigned" for c in c1))
        self.assertLess(t1, t0)
        v.building_id = 2
        buildings[2] = _building(2, BuildingKind.FARM)
        v.skills = _skills(farming=4)
        v.state = VillagerState.WORKING
        t2, c2 = compute_happiness_target(v, buildings=buildings, political=pol)
        self.assertFalse(any("unassigned" in c.key for c in c2))
        self.assertGreater(t2, t1)

    def test_institution_replaces_principle_off_skill(self) -> None:
        v = Villager(
            id=1,
            x=0,
            y=0,
            housed=True,
            housing_id=1,
            building_id=2,
            skills=_skills(farming=5),
            state=VillagerState.WORKING,
        )
        buildings = {
            1: _building(1, BuildingKind.HOUSE_SMALL),
            2: _building(2, BuildingKind.FORESTER),
        }
        principle = SettlementPoliticalState(enacted_principle_ids=["assigned_labour"])
        office = SettlementPoliticalState(
            enacted_principle_ids=["assigned_labour"],
            institution_ids=["settlement_office"],
        )
        _, cp = compute_happiness_target(v, buildings=buildings, political=principle)
        _, co = compute_happiness_target(v, buildings=buildings, political=office)
        self.assertTrue(any(c.key == "assigned_labour_off_skill" for c in cp))
        self.assertTrue(any(c.key == "office_off_skill" for c in co))
        self.assertFalse(any(c.key == "assigned_labour_off_skill" for c in co))
        office_amt = next(c.amount for c in co if c.key == "office_off_skill")
        self.assertAlmostEqual(office_amt, HAP_OFFICE_OFF_SKILL)
        # Covenant replaces protected habitat extractive
        v.building_id = 3
        buildings[3] = _building(3, BuildingKind.FORESTER)
        hab = SettlementPoliticalState(enacted_principle_ids=["protected_habitat"])
        cov = SettlementPoliticalState(
            enacted_principle_ids=["protected_habitat"],
            institution_ids=["covenant_of_the_land"],
        )
        _, ch = compute_happiness_target(v, buildings=buildings, political=hab)
        _, cc = compute_happiness_target(v, buildings=buildings, political=cov)
        self.assertTrue(any(c.key == "protected_habitat_extractive" for c in ch))
        self.assertTrue(any(c.key == "covenant_extractive" for c in cc))
        self.assertFalse(any(c.key == "protected_habitat_extractive" for c in cc))
        self.assertAlmostEqual(
            next(c.amount for c in cc if c.key == "covenant_extractive"),
            HAP_COVENANT_EXTRACTIVE,
        )

    def test_common_harvest_unequal_cleared_by_provision(self) -> None:
        a = Villager(id=1, x=0, y=0, housed=True, housing_id=1, ration_mode=RationMode.HALF)
        b = Villager(id=2, x=0, y=0, housed=True, housing_id=1, ration_mode=RationMode.DOUBLE)
        buildings = {1: _building(1, BuildingKind.HOUSE)}
        pol = SettlementPoliticalState(enacted_principle_ids=["common_harvest"])
        _, c1 = compute_happiness_target(
            a, buildings=buildings, political=pol, villagers=[a, b]
        )
        self.assertTrue(any(c.key == "common_harvest_unequal" for c in c1))
        pol.institution_ids.append("common_provision")
        _, c2 = compute_happiness_target(
            a, buildings=buildings, political=pol, villagers=[a, b]
        )
        self.assertFalse(any(c.key == "common_harvest_unequal" for c in c2))


class ImmediateAndConvergenceTests(unittest.TestCase):
    def test_immediate_decision_cannot_zero_content_villager(self) -> None:
        v = Villager(id=1, x=0, y=0, underlying_happiness=0.65, happiness=0.65)
        apply_immediate_happiness(v, -20, label="harsh")  # capped
        self.assertGreaterEqual(float(v.underlying_happiness), 0.50)

    def test_convergence_rate_constant(self) -> None:
        self.assertGreater(HAPPINESS_CONVERGENCE_PER_DAY, 1.0)
        self.assertLess(HAPPINESS_CONVERGENCE_PER_DAY, 6.0)


class SaveLoadHappinessTests(unittest.TestCase):
    def test_round_trip_underlying_and_temporary(self) -> None:
        import tempfile
        from pathlib import Path

        import pygame

        pygame.init()
        pygame.display.set_mode((8, 8))
        from game import Game
        from save_load import load_from_path, save_to_path

        g = Game(headless=True)
        v = _plain_villager(id=1, x=2, y=2, name="Pat", underlying_happiness=0.58, happiness=0.58)
        apply_meal_mood(
            v, favourite=True, ticks_per_day=2400, icon="stew", label="fav", day=3
        )
        g.villagers = [v]
        g.next_villager_id = 2
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hap.json"
            save_to_path(g, path)
            g2 = Game(headless=True)
            load_from_path(g2, path)
        self.assertEqual(len(g2.villagers), 1)
        v2 = g2.villagers[0]
        self.assertAlmostEqual(float(v2.underlying_happiness), 0.58, places=2)
        self.assertEqual(len(v2.happiness_temporary), 1)
        self.assertAlmostEqual(sum_temporary_moods(v2), HAP_MEAL_FAVOURITE_CAP, places=2)


class BootstrapFlagTests(unittest.TestCase):
    def test_sociopolitical_bootstrap_sets_test_active(self) -> None:
        import pygame

        pygame.init()
        pygame.display.set_mode((8, 8))
        from game import Game
        from sociopolitical_hooks import bootstrap_sociopolitical_test

        g = Game(headless=True)
        # Minimal world already present for headless Game.
        state = bootstrap_sociopolitical_test(g)
        self.assertTrue(state.test_active)
        self.assertTrue(g.political.test_active)
        for villager in g.villagers:
            if villager.building_id is not None:
                from entities import WorkPriority

                self.assertIn(WorkPriority.WORKPLACE, villager.active_priorities(None))


if __name__ == "__main__":
    unittest.main()
