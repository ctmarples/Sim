import unittest

from entities import Inventory
from resource_balance import (
    VILLAGER_FOOD_KEYS,
    food_covers_requirement,
    food_def,
)


class RawFoodTests(unittest.TestCase):
    def test_peas_beans_and_turnips_are_edible_vegetables(self) -> None:
        inventory = Inventory(peas=1, beans=1, turnip=1)

        for key in ("peas", "beans", "turnip"):
            with self.subTest(food=key):
                self.assertIn(key, VILLAGER_FOOD_KEYS)
                self.assertGreater(getattr(inventory, key), 0)
                self.assertGreater(food_def(key).satiation, 0)
                self.assertTrue(food_covers_requirement(key, "vegetables"))


if __name__ == "__main__":
    unittest.main()
