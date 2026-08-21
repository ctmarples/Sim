"""Kitchen input monopoly and farm seed-withdraw helpers."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from entities import (
    Building,
    BuildingKind,
    Inventory,
    apply_building_storage,
)
from game import Game


def _kitchen(*enabled: str) -> Building:
    building = Building(id=1, kind=BuildingKind.KITCHEN, x=0, y=0)
    apply_building_storage(building)
    building.ensure_recipe_state()
    building.fuel_wood = 5
    if enabled:
        for recipe in building.known_recipes():
            building.recipe_enabled[recipe.name] = recipe.name in enabled
    return building


class KitchenTrayTests(unittest.TestCase):
    def test_full_meat_leaves_no_room_and_is_haulable(self) -> None:
        kitchen = _kitchen("stew", "grilled_meat")
        kitchen.meat = kitchen.input_capacity
        self.assertEqual(kitchen.input_space_left(), 0)
        self.assertEqual(kitchen.space_for_key("onion"), 0)
        self.assertIn("meat", kitchen.haul_keys())
        self.assertGreater(kitchen.haulable_amount("meat"), 0)
        self.assertIsNone(kitchen.craftable_recipe())

    def test_meat_stockpile_reserves_room_for_stew_veg(self) -> None:
        kitchen = _kitchen("stew", "grilled_meat")
        kitchen.meat = 30
        self.assertEqual(kitchen.space_for_key("meat"), 0)
        self.assertGreater(kitchen.space_for_key("onion"), 0)
        self.assertGreater(kitchen.space_for_key("cabbage"), 0)
        self.assertGreater(kitchen.space_for_key("carrot"), 0)

    def test_fair_share_stops_one_item_filling_the_tray(self) -> None:
        kitchen = _kitchen("stew", "grilled_meat")
        hold = kitchen.input_hold_amount("meat")
        kitchen.meat = hold
        self.assertEqual(kitchen.space_for_key("meat"), 0)
        self.assertGreater(kitchen.input_space_left(), 0)
        self.assertGreater(kitchen.space_for_key("onion"), 0)

    def test_ready_stew_still_cooks(self) -> None:
        kitchen = _kitchen("stew", "grilled_meat")
        kitchen.meat = 2
        kitchen.onion = 2
        kitchen.cabbage = 1
        kitchen.carrot = 1
        recipe = kitchen.craftable_recipe()
        self.assertIsNotNone(recipe)
        assert recipe is not None
        self.assertEqual(recipe.name, "stew")


class FarmSeedWithdrawTests(unittest.TestCase):
    def test_withdraw_only_requested_seed_keys(self) -> None:
        farm = Building(id=2, kind=BuildingKind.FARM, x=0, y=0)
        apply_building_storage(farm)
        farm.cabbage_seeds = 10
        farm.onion_seeds = 10
        inv = Inventory()
        taken = farm.withdraw_plantables_to(
            inv, max_items=3, keys=("onion_seeds",)
        )
        self.assertEqual(taken, 3)
        self.assertEqual(inv.onion_seeds, 3)
        self.assertEqual(inv.cabbage_seeds, 0)
        self.assertEqual(farm.onion_seeds, 7)
        self.assertEqual(farm.cabbage_seeds, 10)


class RoutedSupplyDemandTests(unittest.TestCase):
    def test_hauler_sees_extension_demand_excluded_by_building(self) -> None:
        """Barn sheaves are injected by Game, not Building.supply_demand()."""
        game = Game.__new__(Game)
        farm = SimpleNamespace(id=7)
        game.buildings = {farm.id: farm}
        game._claimed_haul_targets = lambda _villager_id: set()
        game._building_supply_demand = lambda building: {"wheat": 4}
        game._processor_can_be_supplied = lambda building: True
        game._supply_sink_sort_key = lambda building: (building.id,)

        villager = SimpleNamespace(id=3)
        self.assertIs(game._find_processor_needing_supply_for(villager), farm)


if __name__ == "__main__":
    unittest.main()
