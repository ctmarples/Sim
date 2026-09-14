"""Regression tests for workers reversing or displaying stale tasks."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from entities import (
    Building,
    BuildingKind,
    Villager,
    VillagerState,
    WorkplaceSlot,
    WorkPriority,
    apply_building_storage,
)
from game import Game
from seasons import Season


class WorkerStickinessTests(unittest.TestCase):
    def test_farmer_keeps_harvesting_with_room_in_pack(self) -> None:
        game = Game.__new__(Game)
        farm = Building(id=3, kind=BuildingKind.FARM, x=4, y=4)
        apply_building_storage(farm)
        game.buildings = {farm.id: farm}
        farmer = Villager(id=1, x=8, y=8)
        farmer.inventory.garlic = 5

        self.assertFalse(game._farm_pack_needs_barn_or_farm_unload(farmer, farm))

        farmer.inventory.garlic = farmer.inventory.effective_capacity
        self.assertTrue(game._farm_pack_needs_barn_or_farm_unload(farmer, farm))

    def test_fisher_keeps_valid_post_until_reaching_it(self) -> None:
        game = Game.__new__(Game)
        game._is_fishing_shore = lambda x, y: True
        game._within_work_search = lambda origin, post: True
        game._fisher_candidate_fish = lambda villager, building: self.fail(
            "moving fish should not invalidate a post while the fisher is en route"
        )

        fisher = Villager(id=2, x=5, y=5)
        fisher.fish_post_pos = (9, 5)

        self.assertEqual(
            game._resolve_fish_post(fisher, SimpleNamespace()), (9, 5)
        )

    def test_fisher_keeps_static_post_for_day_without_catch(self) -> None:
        game = Game.__new__(Game)
        game.ticks_per_day = 1200
        game.calendar_day = 10
        game.day_tick = 600
        game._is_fishing_shore = lambda x, y: True
        game._within_work_search = lambda origin, post: True

        fisher = Villager(id=2, x=9, y=5)
        fisher.fish_post_pos = (9, 5)
        fisher._fish_post_last_catch_tick = game._simulation_clock_tick() - 1199

        self.assertEqual(
            game._resolve_fish_post(fisher, SimpleNamespace()), (9, 5)
        )

    def test_season_change_clears_old_fishing_post(self) -> None:
        game = Game.__new__(Game)
        game.calendar_day = 84
        fisher_hut = Building(id=11, kind=BuildingKind.FISHER, x=5, y=5)
        hunter_hut = Building(id=8, kind=BuildingKind.HUNTER, x=8, y=8)
        game.buildings = {8: hunter_hut, 11: fisher_hut}

        villager = Villager(id=2, x=9, y=5, building_id=11)
        villager.seasonal_priorities = True
        villager.ensure_season_workplace_plan()
        villager.season_workplace_plan[Season.WINTER.name] = [
            WorkplaceSlot(WorkPriority.WORKPLACE, 8),
            WorkplaceSlot(),
            WorkplaceSlot(),
        ]
        villager.fish_post_pos = (9, 5)
        villager.target = (9, 5)
        villager.state = VillagerState.WORKING

        game._reconcile_seasonal_workplace(villager)

        self.assertEqual(villager.building_id, 8)
        self.assertIsNone(villager.fish_post_pos)
        self.assertIsNone(villager.target)
        self.assertEqual(villager.state, VillagerState.IDLE)

    def test_partially_switched_hunter_drops_saved_fishing_post(self) -> None:
        game = Game.__new__(Game)
        game.calendar_day = 84
        hunter_hut = Building(id=8, kind=BuildingKind.HUNTER, x=8, y=8)
        game.buildings = {8: hunter_hut}
        game._clear_villager_path = lambda villager: None

        villager = Villager(id=2, x=9, y=5, building_id=8)
        villager.seasonal_priorities = True
        villager.ensure_season_workplace_plan()
        villager.season_workplace_plan[Season.WINTER.name] = [
            WorkplaceSlot(WorkPriority.WORKPLACE, 8),
            WorkplaceSlot(),
            WorkplaceSlot(),
        ]
        villager.fish_post_pos = (9, 5)
        villager.target = (9, 5)
        villager.state = VillagerState.WORKING

        game._reconcile_seasonal_workplace(villager)

        self.assertIsNone(villager.fish_post_pos)
        self.assertIsNone(villager.target)
        self.assertEqual(villager.state, VillagerState.IDLE)

    def test_empty_hauler_target_matches_claimed_pickup(self) -> None:
        game = Game.__new__(Game)
        game.world = SimpleNamespace(home_pos=(0, 0))
        hunter = Building(id=8, kind=BuildingKind.HUNTER, x=10, y=10)
        apply_building_storage(hunter)
        hunter.leather = 2
        game.buildings = {hunter.id: hunter}
        game._owns_haul_claim = lambda villager, building_id: True

        orin = Villager(id=16, x=4, y=4)
        orin.state = VillagerState.HAULING
        orin.haul_building_id = hunter.id
        orin.target = (99, 99)
        orin.move_cooldown = 10

        game._update_hauler(orin)

        self.assertEqual(orin.target, hunter.center_cell())

    def test_fish_post_counts_as_active_workplace_action(self) -> None:
        fisher = Villager(id=2, x=5, y=5)
        fisher.fish_post_pos = (9, 5)
        self.assertTrue(Game._villager_has_active_action(fisher))

    def test_claimed_farm_job_counts_as_active_action(self) -> None:
        farmer = Villager(id=3, x=4, y=4)
        farmer.farm_job_kind = "PLOUGH"
        farmer.target = (5, 5)
        farmer.state = VillagerState.WORKING
        self.assertTrue(Game._villager_has_active_action(farmer))

    def test_fisher_bait_without_knife_does_not_claim_tick(self) -> None:
        game = Game.__new__(Game)
        game._village_stock_amounts = lambda: {}
        hut = Building(id=11, kind=BuildingKind.FISHER, x=5, y=5)
        apply_building_storage(hut)
        hut.meat = 2
        hut.bait = 0
        hut.ensure_recipe_state()
        fisher = Villager(id=2, x=5, y=5)
        game._tool_fetchable = lambda villager, tool: False
        game._ensure_work_tool = lambda villager, tool: False
        self.assertFalse(game._try_fisher_bait_craft(fisher, hut))

    def test_fisher_does_not_deliver_while_small_fish_still_fit(self) -> None:
        game = Game.__new__(Game)
        hut = Building(id=11, kind=BuildingKind.FISHER, x=5, y=5)
        apply_building_storage(hut)
        fisher = Villager(id=2, x=5, y=5)
        fisher.inventory.fish = 1
        # Leave a few free slots — max fish yield is >1, but small catches still fit.
        fisher.inventory.capacity = fisher.inventory.cargo_total + 2
        self.assertFalse(game._gather_cargo_needs_delivery(fisher, hut))
        fisher.inventory.capacity = fisher.inventory.cargo_total
        self.assertTrue(game._gather_cargo_needs_delivery(fisher, hut))


if __name__ == "__main__":
    unittest.main()
