"""Stack spoilage and transfer behavior."""

from __future__ import annotations

import unittest

from entities import (
    Building,
    BuildingKind,
    HomeStorage,
    Inventory,
    apply_building_storage,
)
from food_spoilage import food_quality, tick_storage_spoilage


class FoodSpoilageTests(unittest.TestCase):
    def test_large_time_step_spoils_only_one_item_from_stack(self) -> None:
        storage = HomeStorage(meat=5)
        storage.food_quality["meat"] = 0.1

        produced = tick_storage_spoilage(storage, day_frac=50.0, days_to_spoil=10.0)

        self.assertEqual(produced, 1)
        self.assertEqual(storage.meat, 4)
        self.assertEqual(storage.spoilage, 1)
        self.assertEqual(food_quality(storage, "meat"), 1.0)

    def test_split_moves_spoiling_item_and_refreshes_source_stack(self) -> None:
        storage = HomeStorage(meat=5)
        storage.food_quality["meat"] = 0.2
        inventory = Inventory()

        self.assertTrue(storage.withdraw_one_to(inventory, "meat"))

        self.assertEqual(storage.meat, 4)
        self.assertEqual(food_quality(storage, "meat"), 1.0)
        self.assertEqual(inventory.meat, 1)
        self.assertEqual(food_quality(inventory, "meat"), 0.2)

    def test_food_workplaces_accept_spoilage(self) -> None:
        for kind in (
            BuildingKind.HUNTER,
            BuildingKind.FISHER,
            BuildingKind.FORAGER,
            BuildingKind.FARM,
            BuildingKind.KITCHEN,
        ):
            with self.subTest(kind=kind):
                building = Building(id=1, kind=kind, x=0, y=0)
                apply_building_storage(building)
                inventory = Inventory()
                inventory.spoilage = 2

                building.deposit_from_inventory(inventory)

                self.assertEqual(building.spoilage, 2)
                self.assertEqual(inventory.spoilage, 0)

    def test_non_food_workplace_rejects_spoilage(self) -> None:
        mason = Building(id=1, kind=BuildingKind.MASON, x=0, y=0)
        apply_building_storage(mason)
        inventory = Inventory()
        inventory.spoilage = 2

        mason.deposit_from_inventory(inventory)

        self.assertEqual(mason.spoilage, 0)
        self.assertEqual(inventory.spoilage, 2)


if __name__ == "__main__":
    unittest.main()
