"""Tests for SP field/hall repair, happiness buffs, and trait mechanics."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from entities import Building, BuildingKind, Villager, VillagerState
from happiness import compute_happiness_target, refresh_happiness_breakdown
from society import VICE_POOL, VIRTUE_POOL, active_happiness_status_mods
from traits import (
    TRAIT_EFFECTS,
    missing_trait_definitions,
    trait_hunger_mult,
    trait_meal_food_delta,
    trait_work_mult,
)


class TraitCatalogueTests(unittest.TestCase):
    def test_every_pool_trait_has_mechanics(self) -> None:
        missing = missing_trait_definitions(VIRTUE_POOL, VICE_POOL)
        self.assertEqual(missing, [], msg=f"Traits without effects: {missing}")
        for name, effect in TRAIT_EFFECTS.items():
            changed = (
                abs(effect.work - 1.0) > 0.001
                or abs(effect.walk - 1.0) > 0.001
                or abs(effect.hunger - 1.0) > 0.001
                or abs(effect.break_chance - 1.0) > 0.001
                or abs(effect.break_duration - 1.0) > 0.001
                or abs(effect.happiness_target) > 0.001
                or effect.meal_food_delta != 0
                or abs(effect.meal_mood_scale - 1.0) > 0.001
            )
            self.assertTrue(changed, msg=f"{name} has no mechanical impact")

    def test_diligent_and_lazy_oppose(self) -> None:
        diligent = Villager(id=1, x=0, y=0, virtues=["Diligent"], vices=[])
        lazy = Villager(id=2, x=0, y=0, virtues=[], vices=["Lazy"])
        self.assertGreater(trait_work_mult(diligent), 1.0)
        self.assertLess(trait_work_mult(lazy), 1.0)
        self.assertGreater(trait_hunger_mult(Villager(id=3, x=0, y=0, vices=["Glutton"])), 1.0)
        self.assertNotEqual(trait_meal_food_delta(Villager(id=4, x=0, y=0, vices=["Picky"])), 0)


class HappinessBuffCoverageTests(unittest.TestCase):
    def test_ongoing_and_temporary_appear_in_status_mods(self) -> None:
        from happiness import apply_meal_mood

        v = Villager(
            id=1,
            x=0,
            y=0,
            housed=False,
            ration_mode=__import__("entities").RationMode.HALF,
            virtues=["Cheerful"],
            underlying_happiness=0.6,
            happiness=0.6,
        )
        v.last_meal = ["bread"]
        buildings = {}
        refresh_happiness_breakdown(v, buildings=buildings, ticks_per_day=2400)
        apply_meal_mood(
            v, favourite=True, ticks_per_day=2400, icon="stew", label="Ate favourite food: Stew"
        )
        refresh_happiness_breakdown(v, buildings=buildings, ticks_per_day=2400)
        mods = active_happiness_status_mods(v)
        effects = [m.effect for m in mods]
        self.assertIn("happiness", effects)
        labels = " ".join(str(m.cause_label) for m in mods)
        self.assertTrue(
            any("Half" in str(m.cause_label) or "housing" in m.cause_key or "No housing" in str(m.cause_label) for m in mods)
            or "housing_missing" in " ".join(m.cause_key for m in mods),
        )
        self.assertTrue(any("favourite" in str(m.cause_label).lower() or "Favourite" in str(m.cause_label) for m in mods) or any("meal" in m.cause_key for m in mods) or any(m.tip_override and "temporary" in m.tip_override for m in mods))


class SPTrialRepairTests(unittest.TestCase):
    def test_field_ploughable_and_single_hall(self) -> None:
        import pygame
        from pathlib import Path

        pygame.init()
        pygame.display.set_mode((8, 8))
        from game import Game
        from save_load import load_from_path
        from world import FeatureType, TerrainType

        path = Path(__file__).resolve().parents[1] / "saves" / "SP_trial.json"
        if not path.exists():
            self.skipTest("SP_trial.json not present")
        g = Game(headless=True)
        load_from_path(g, path)
        fields = [b for b in g.buildings.values() if b.kind == BuildingKind.FIELD]
        self.assertTrue(fields)
        field = fields[0]
        self.assertTrue(field.plans, "field needs a crop plan")
        # No structure pads on field tiles
        for x, y in field.plot_cells():
            cell = g.world.get_cell(x, y)
            self.assertIsNotNone(cell)
            self.assertNotEqual(cell.feature, FeatureType.STRUCTURE_PAD)
            self.assertEqual(cell.terrain, TerrainType.SOIL)
        # Exactly one WORKSTATION feature, on the hiring hall footprint
        halls = [b for b in g.buildings.values() if b.kind == BuildingKind.WORKSTATION]
        self.assertEqual(len(halls), 1)
        hall_cells = set(halls[0].plot_cells())
        ws_features = [
            (x, y)
            for y in range(g.world.rows)
            for x in range(g.world.cols)
            if (c := g.world.get_cell(x, y)) is not None
            and c.feature == FeatureType.WORKSTATION
        ]
        self.assertEqual(len(ws_features), 1)
        self.assertIn(ws_features[0], hall_cells)
        # Plough path works after pad clear
        x, y = next(iter(field.plot_cells()))
        cell = g.world.get_cell(x, y)
        cell.feature = FeatureType.NONE
        cell.terrain = TerrainType.GRASS
        self.assertTrue(g.world.plough_tile(x, y))


class BootstrapFieldHallTests(unittest.TestCase):
    def test_bootstrap_field_clear_and_one_hall(self) -> None:
        import pygame

        pygame.init()
        pygame.display.set_mode((8, 8))
        from game import Game
        from sociopolitical_hooks import bootstrap_sociopolitical_test
        from world import FeatureType

        g = Game(headless=True)
        bootstrap_sociopolitical_test(g)
        fields = [b for b in g.buildings.values() if b.kind == BuildingKind.FIELD]
        self.assertTrue(fields)
        field = fields[0]
        self.assertTrue(field.plans)
        for x, y in field.plot_cells():
            cell = g.world.get_cell(x, y)
            self.assertNotEqual(cell.feature, FeatureType.STRUCTURE_PAD)
        halls = [b for b in g.buildings.values() if b.kind == BuildingKind.WORKSTATION]
        self.assertEqual(len(halls), 1)
        hall_cells = set(halls[0].plot_cells())
        ws_features = [
            (x, y)
            for y in range(g.world.rows)
            for x in range(g.world.cols)
            if (c := g.world.get_cell(x, y)) is not None
            and c.feature == FeatureType.WORKSTATION
        ]
        self.assertTrue(ws_features)
        self.assertTrue(all(pos in hall_cells for pos in ws_features))


if __name__ == "__main__":
    unittest.main()
