"""Hide must stay at the hunter hut for drying-rack leather, not vanish home."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from entities import (
    Building,
    BuildingKind,
    Inventory,
    Villager,
    VillagerState,
    apply_building_storage,
)
from extensions import apply_extension_storage_boosts
from game import Game


class HunterLeatherTests(unittest.TestCase):
    def _hunter_with_rack(self) -> tuple[Game, Building, Villager]:
        game = Game.__new__(Game)
        game.world = SimpleNamespace(home_pos=(0, 0))
        game.home_storage = Inventory()
        game.villagers = []
        game.buildings = {}
        game.sounds = SimpleNamespace(emit=lambda *a, **k: None)
        game.calendar_day = 1
        game.day_tick = 0
        game.ticks_per_day = 100
        game._village_stock_amounts = lambda: {}
        game._villager_work_interval = lambda v: 0
        game._spend_work_energy = lambda v: None
        game._gain_job_skill = lambda v, k: None
        game._ensure_work_tool = lambda v, tool: True
        game._coworker_addon_craft_claims = lambda b, vid: set()
        game.record_consumed = lambda *a, **k: None
        game.record_produced = lambda *a, **k: None
        game._step_villager_toward = lambda v, dest: True
        game._clear_villager_path = lambda v: None
        game._restock_workplace_gear_at_home = lambda v: None
        game._clear_gather_stickies = lambda v: None
        game._owns_haul_claim = lambda v, bid: True
        game._workplace_primary_available = lambda v, b: True
        game._village_supply_have = lambda key: int(getattr(game.home_storage, key, 0))
        game._best_supply_pickup = lambda demand: (
            (game.home_storage, game.world.home_pos)
            if any(int(getattr(game.home_storage, k, 0)) > 0 for k in demand)
            else (None, None)
        )
        game._building_supply_demand = lambda b: dict(b.supply_demand())
        game._general_hauler_serving = lambda bid: False
        game._walk_goal_for_target = lambda *a, **k: None
        game._withdraw_processor_supply = Game._withdraw_processor_supply.__get__(game, Game)
        game._assigned_transport_destination = (
            Game._assigned_transport_destination.__get__(game, Game)
        )

        hunter = Building(id=1, kind=BuildingKind.HUNTER, x=5, y=5)
        rack = Building(
            id=2,
            kind=BuildingKind.DRYING_RACK,
            x=5,
            y=7,
            parent_building_id=1,
        )
        apply_building_storage(hunter)
        apply_building_storage(rack)
        game.buildings = {hunter.id: hunter, rack.id: rack}
        apply_extension_storage_boosts(game.buildings)
        hunter.recipe_enabled["leather"] = True

        villager = Villager(id=10, x=5, y=5)
        villager.building_id = hunter.id
        villager.inventory.equip_tool_from_transfer("knife")
        villager.work_cooldown = 0
        villager.move_cooldown = 0
        game.villagers = [villager]
        return game, hunter, villager

    def test_hide_deposits_before_meat_when_hut_nearly_full(self) -> None:
        game, hunter, villager = self._hunter_with_rack()
        hunter.meat = hunter.capacity - 1
        villager.inventory.hide = 1
        villager.inventory.meat = 3
        game._deposit_workplace_cargo(hunter, villager.inventory)
        self.assertGreaterEqual(hunter.hide, 1)
        self.assertEqual(villager.inventory.hide, 0)

    def test_full_hut_swaps_meat_out_for_hide(self) -> None:
        game, hunter, villager = self._hunter_with_rack()
        hunter.meat = hunter.capacity
        villager.inventory.hide = 1
        game._hunter_bank_hide_for_tanning(hunter, villager.inventory)
        self.assertEqual(hunter.hide, 1)
        self.assertEqual(villager.inventory.hide, 0)
        self.assertEqual(villager.inventory.meat, 1)

    def test_delivery_does_not_dump_hide_to_storehouse(self) -> None:
        game, hunter, villager = self._hunter_with_rack()
        hunter.meat = hunter.capacity - 1
        villager.inventory.hide = 1
        villager.inventory.meat = 2
        villager.state = VillagerState.DELIVERING
        villager.target = hunter.center_cell()
        game._force_assigned_delivery(villager, hunter)
        self.assertGreaterEqual(hunter.hide, 1)
        self.assertEqual(villager.inventory.hide, 0)
        self.assertEqual(game.home_storage.hide, 0)

    def test_addon_craft_turns_hide_into_leather(self) -> None:
        game, hunter, villager = self._hunter_with_rack()
        hunter.hide = 1
        villager.x, villager.y = hunter.center_cell()
        for _ in range(5):
            villager.work_cooldown = 0
            game._try_addon_craft(villager, hunter)
            if hunter.leather > 0:
                break
        self.assertEqual(hunter.hide, 0)
        self.assertEqual(hunter.leather, 2)

    def test_hunter_fetches_storehouse_hide_while_prey_available(self) -> None:
        game, hunter, villager = self._hunter_with_rack()
        game.home_storage.hide = 2
        self.assertTrue(game._workplace_needs_home_supply(hunter))
        self.assertTrue(game._hunter_should_fetch_leather_inputs(villager, hunter))
        self.assertTrue(game._assigned_transport_has_work(villager, hunter))
        self.assertTrue(game._maybe_assigned_transport(villager, hunter))


if __name__ == "__main__":
    unittest.main()
