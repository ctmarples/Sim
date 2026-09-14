"""Multi-year field rotation and fertility boost regressions."""

from __future__ import annotations

import unittest

from crops import CROP_BY_KEY
from entities import Building, BuildingKind
from soil import (
    COMPOST_FERTILITY_BOOST,
    FIELD_FERTILITY_HARD_CAP,
    apply_compost_to_cell,
    drop_fertility_on_harvest,
    field_fertility_target,
)
from world import Cell, TerrainType


class FertilityBoostTests(unittest.TestCase):
    def test_compost_boost_is_ten_percent(self) -> None:
        self.assertAlmostEqual(COMPOST_FERTILITY_BOOST, 0.10)
        cell = Cell(TerrainType.SOIL)
        target = field_fertility_target(cell)
        cell.fertility = target
        apply_compost_to_cell(cell, "SPRING")
        self.assertAlmostEqual(cell.fertility, min(FIELD_FERTILITY_HARD_CAP, target + 0.10))
        self.assertGreater(cell.fertility, target)

    def test_peas_and_beans_add_five_percent(self) -> None:
        for key in ("peas", "beans"):
            self.assertAlmostEqual(CROP_BY_KEY[key].fertility_effect, 0.05)
        cell = Cell(TerrainType.SOIL)
        cell.fertility = 0.50
        drop_fertility_on_harvest(cell, crop_key="peas")
        # harvest drop then +0.05 — exact value depends on FERTILITY_HARVEST_DROP
        after_peas = cell.fertility
        cell.fertility = 0.50
        drop_fertility_on_harvest(cell, crop_key="wheat")
        after_wheat = cell.fertility
        self.assertAlmostEqual(after_peas - after_wheat, 0.05, places=4)


class MultiYearRotationTests(unittest.TestCase):
    def test_plans_do_not_conflict_across_years(self) -> None:
        field = Building(1, BuildingKind.FIELD, 2, 2, plot_w=2, plot_h=2)
        field.set_rotation_years(3)
        a = field.add_field_plan(2, 2, 3, 3, "wheat", year=1)
        b = field.add_field_plan(2, 2, 3, 3, "wheat", year=2)
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        self.assertEqual(a.year, 1)
        self.assertEqual(b.year, 2)
        self.assertEqual(len(field.plans), 2)
        self.assertEqual(len(field.plans_for_year(1)), 1)
        self.assertEqual(len(field.plans_for_year(2)), 1)

    def test_same_year_conflicting_plans_carve(self) -> None:
        field = Building(1, BuildingKind.FIELD, 2, 2, plot_w=2, plot_h=2)
        field.set_rotation_years(2)
        field.add_field_plan(2, 2, 3, 3, "wheat", year=1)
        field.add_field_plan(2, 2, 3, 3, "rye", year=1)
        year1 = field.plans_for_year(1)
        # rye and wheat both plant in autumn — schedules conflict, so only latest remains
        kinds = {p.crop_kind for p in year1}
        self.assertEqual(len(kinds), 1)

    def test_rotation_year_advances_with_elapsed_years(self) -> None:
        from game import Game

        game = Game.__new__(Game)
        game.elapsed_years = 0
        field = Building(1, BuildingKind.FIELD, 0, 0, plot_w=1, plot_h=1)
        field.set_rotation_years(3)
        self.assertEqual(game._field_rotation_year(field), 1)
        game.elapsed_years = 1
        self.assertEqual(game._field_rotation_year(field), 2)
        game.elapsed_years = 2
        self.assertEqual(game._field_rotation_year(field), 3)
        game.elapsed_years = 3
        self.assertEqual(game._field_rotation_year(field), 1)

    def test_overview_uses_current_year_only(self) -> None:
        from game import Game
        from world import World

        game = Game.__new__(Game)
        game.elapsed_years = 0
        game.world = World(8, 8)
        game.buildings = {}
        field = Building(1, BuildingKind.FIELD, 2, 2, plot_w=2, plot_h=2)
        field.set_rotation_years(2)
        field.add_field_plan(2, 2, 2, 2, "sage", year=1)
        field.add_field_plan(2, 2, 2, 2, "wheat", year=2)
        overview = game._field_crop_overview(field)
        self.assertEqual([row["key"] for row in overview], ["sage"])
        game.elapsed_years = 1
        overview2 = game._field_crop_overview(field)
        self.assertEqual([row["key"] for row in overview2], ["wheat"])

    def test_reducing_rotation_years_drops_extra_plans(self) -> None:
        field = Building(1, BuildingKind.FIELD, 2, 2, plot_w=1, plot_h=1)
        field.set_rotation_years(3)
        field.add_field_plan(2, 2, 2, 2, "sage", year=1)
        field.add_field_plan(2, 2, 2, 2, "wheat", year=3)
        field.set_rotation_years(2)
        self.assertEqual(field.clamped_rotation_years(), 2)
        self.assertEqual({p.year for p in field.plans}, {1})


if __name__ == "__main__":
    unittest.main()
