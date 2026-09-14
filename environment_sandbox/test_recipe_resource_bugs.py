"""Regression tests for confirmed recipe/resource data bugs."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from recipes import (
    KITCHEN_RECIPES,
    SOFT_BERRY_INPUT_KEYS,
    apply_recipe,
    missing_inputs,
    recipe_ready,
)
from resource_balance import food_def
from resources import resource_label


def _kitchen_recipe(name: str):
    for recipe in KITCHEN_RECIPES:
        if recipe.name == name:
            return recipe
    raise AssertionError(f"missing kitchen recipe {name!r}")


class BreadWheatRecipeTests(unittest.TestCase):
    def test_bread_wheat_produces_bread_not_fish(self):
        recipe = _kitchen_recipe("bread_wheat")
        self.assertEqual(recipe.outputs, {"bread": 1})
        self.assertEqual(recipe.inputs, {"wheat_flour": 1})

    def test_fish_label_and_food_def_not_overwritten(self):
        self.assertEqual(resource_label("fish"), "Fish")
        fish = food_def("fish")
        self.assertAlmostEqual(fish.satiation, 5.0 / 3.0, places=5)
        self.assertAlmostEqual(fish.walk_speed, 0.8, places=5)
        self.assertAlmostEqual(fish.work_efficiency, 0.8, places=5)

    def test_craft_bread_wheat_adds_bread(self):
        storage = SimpleNamespace(wheat_flour=1, bread=0, fish=0)
        apply_recipe(storage, _kitchen_recipe("bread_wheat"))
        self.assertEqual(storage.wheat_flour, 0)
        self.assertEqual(storage.bread, 1)
        self.assertEqual(storage.fish, 0)


class BerryJamInputTests(unittest.TestCase):
    def test_soft_berry_keys_cover_typed_forage(self):
        self.assertIn("blackberries", SOFT_BERRY_INPUT_KEYS)
        self.assertIn("sloe_berries", SOFT_BERRY_INPUT_KEYS)
        self.assertIn("elderberries", SOFT_BERRY_INPUT_KEYS)
        self.assertNotIn("hazelnuts", SOFT_BERRY_INPUT_KEYS)
        self.assertNotIn("berries", SOFT_BERRY_INPUT_KEYS)

    def test_jam_ready_with_blackberries(self):
        recipe = _kitchen_recipe("blackberry_jam")
        storage = SimpleNamespace(blackberries=3, honey=1)
        self.assertTrue(recipe_ready(storage, recipe))

    def test_jam_consumes_typed_berries(self):
        recipe = _kitchen_recipe("blackberry_jam")
        storage = SimpleNamespace(
            blackberries=3, honey=1, berry_jam=0
        )
        apply_recipe(storage, recipe)
        self.assertEqual(storage.blackberries, 0)
        self.assertEqual(storage.honey, 0)
        self.assertEqual(storage.berry_jam, 2)

    def test_tart_uses_jam(self):
        recipe = _kitchen_recipe("berry_tart")
        storage = SimpleNamespace(
            berry_jam=1,
            honey=1,
            wheat_flour=1,
            berry_tart=0,
        )
        self.assertTrue(recipe_ready(storage, recipe))
        apply_recipe(storage, recipe)
        self.assertEqual(storage.berry_jam, 0)
        self.assertEqual(storage.berry_tart, 1)

    def test_missing_berries_requests_blackberries(self):
        recipe = _kitchen_recipe("blackberry_jam")
        storage = SimpleNamespace(blackberries=0, honey=1)
        self.assertEqual(missing_inputs(storage, recipe), {"blackberries": 3})


class KitchenFireAndStepsTests(unittest.TestCase):
    def test_kitchen_includes_fire_recipes(self):
        from entities import Building, BuildingKind
        from recipes import FIRE_RECIPES

        kitchen = Building(id=1, kind=BuildingKind.KITCHEN, x=0, y=0)
        names = {r.name for r in kitchen.known_recipes()}
        for recipe in FIRE_RECIPES:
            self.assertIn(recipe.name, names)
        self.assertIn("honey_porridge", names)
        self.assertIn("mushroom_stew", names)

    def test_default_steps_match_processor_default(self):
        from settings import PROCESSOR_RECIPE_STEPS

        recipe = _kitchen_recipe("mushroom_stew")
        self.assertEqual(recipe.steps, 0)
        self.assertEqual(recipe.work_steps(), PROCESSOR_RECIPE_STEPS)


if __name__ == "__main__":
    unittest.main()
