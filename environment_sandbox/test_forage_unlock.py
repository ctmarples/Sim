import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest

from entities import Building, BuildingKind, Inventory
from wild_species import ALWAYS_FORAGE_KEYS, forage_resource_keys_for_flora


class ForageUnlockTests(unittest.TestCase):
    def test_always_includes_wood_rock_honey(self):
        keys = forage_resource_keys_for_flora(set())
        self.assertEqual(keys, ALWAYS_FORAGE_KEYS)
        self.assertIn("wood", keys)
        self.assertIn("rock", keys)

    def test_flora_unlocks_matching_produce(self):
        keys = forage_resource_keys_for_flora({"wild:wheat", "wild:mushroom", "wild:blackberry"})
        self.assertIn("wheat", keys)
        self.assertIn("mushrooms", keys)
        self.assertIn("blackberries", keys)
        self.assertNotIn("sage", keys)
        self.assertIn("wood", keys)

    def test_unrestricted_when_flora_none(self):
        self.assertIsNone(forage_resource_keys_for_flora(None))


class PlantForageYieldTests(unittest.TestCase):
    def test_scenic_herbs_are_not_sage(self):
        from wild_species import plant_forage_yield

        for kind in ("clover", "yarrow", "meadowsweet", "nettle"):
            self.assertIsNone(plant_forage_yield("HERB", kind))
            self.assertIsNone(plant_forage_yield("WILD_CROP", kind))

    def test_wild_crops_keep_their_produce(self):
        from wild_species import plant_forage_yield

        self.assertEqual(plant_forage_yield("WILD_CROP", "mint")[0], "mint")
        self.assertEqual(plant_forage_yield("WILD_CROP", "sage")[0], "sage")
        self.assertEqual(plant_forage_yield("WILD_CROP", "wheat")[0], "wheat")
        self.assertEqual(plant_forage_yield("WILD_CROP", None)[0], "sage")


class ForageInventoryTests(unittest.TestCase):
    def test_deposit_berry_food_stays_on_forager(self):
        building = Building(1, BuildingKind.FORAGER, 0, 0)
        inv = Inventory()
        self.assertTrue(inv.add_item("blackberries", 5))
        self.assertTrue(inv.add_item("mushrooms", 3))
        building.deposit_from_inventory(inv)
        self.assertEqual(building.blackberries, 5)
        self.assertEqual(building.mushrooms, 3)
        self.assertEqual(inv.blackberries, 0)
        self.assertEqual(inv.mushrooms, 0)
        # No duplicate depositable keys (display / haul should not double-hit).
        keys = building.depositable_keys()
        self.assertEqual(len(keys), len(set(keys)))

    def test_legacy_berries_deposit_as_blackberries(self):
        building = Building(1, BuildingKind.FORAGER, 0, 0)
        inv = Inventory()
        inv.berries = 4
        building.deposit_from_inventory(inv)
        self.assertEqual(building.blackberries, 4)
        self.assertEqual(building.berries, 0)
        self.assertEqual(inv.berries, 0)

    def test_inventory_clear_keeps_berry_food_in_deposit_dict(self):
        inv = Inventory()
        inv.add_item("blackberries", 2)
        inv.add_item("sloe_berries", 1)
        deposited = inv.clear()
        self.assertEqual(deposited.get("blackberries"), 2)
        self.assertEqual(deposited.get("sloe_berries"), 1)
        self.assertEqual(inv.blackberries, 0)


class ForageRecipeTests(unittest.TestCase):
    def test_forager_recipes_use_species_foods_not_legacy_berries(self):
        from recipes import FORAGER_RECIPES

        names = {r.name for r in FORAGER_RECIPES}
        self.assertNotIn("berries", names)
        self.assertIn("blackberries", names)
        self.assertIn("wood", names)
        self.assertIn("rock", names)

    def test_forager_crop_recipes_keep_plant_flower_recolour(self):
        from recipes import FORAGER_RECIPES
        from resources import resource_icon_style

        sage = next(r for r in FORAGER_RECIPES if r.name == "sage")
        style = resource_icon_style(sage.display_icon_key())
        self.assertEqual(style.name, "flower_plant")
        self.assertIn("flower", style.recolour)
        self.assertEqual(style.recolour["flower"], (70, 110, 200))
        # Must not collapse to a bare dense glyph with no plant colours.
        self.assertNotEqual(style.name, "crop_plant_dense")
        self.assertNotEqual(style.recolour, {})


if __name__ == "__main__":
    unittest.main()
