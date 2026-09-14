"""Hunter idle / search / tool-fetch regressions from the worker audit."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from entities import (
    Building,
    BuildingKind,
    HomeStorage,
    TaskArea,
    TaskType,
    Villager,
    VillagerState,
    apply_building_storage,
)
from game import Game
from society import SkillType


class HunterWorkerAuditTests(unittest.TestCase):
    def _hunter_game(self) -> tuple[Game, Building, Villager]:
        game = Game.__new__(Game)
        game.ticks_per_day = 400
        game._work_gen = 1
        game.world = SimpleNamespace(home_pos=(1, 1))
        game.home_storage = HomeStorage()
        game.wildlife = SimpleNamespace(
            huntable_animals=lambda: [],
            colonies=[],
            colony_by_id=lambda _i: None,
        )
        hut = Building(id=8, kind=BuildingKind.HUNTER, x=5, y=5)
        apply_building_storage(hut)
        hut.ensure_recipe_state()
        game.buildings = {hut.id: hut}
        hunter = Villager(id=3, x=5, y=5, building_id=hut.id)
        hunter.inventory.equip_tool_from_transfer("spear")
        game.villagers = [hunter]
        game._try_addon_craft = Mock(return_value=False)
        game._maybe_assigned_transport = Mock(return_value=False)
        game._meat_deposit_available = Mock(return_value=False)
        game._under_production_max = Mock(return_value=True)
        game._claimed_animal_ids = Mock(return_value=set())
        game._claimed_colony_ids = Mock(return_value=set())
        game._find_meat_in_hunt_areas = Mock(return_value=None)
        game._pick_nearest_reachable = Mock(return_value=None)
        game._resolve_hunt_colony = Mock(return_value=None)
        game._resolve_hunt_animal = Mock(return_value=None)
        game._clear_villager_path = Mock()
        game._step_villager_toward = Mock(return_value=True)
        game._register_field_claim = Mock()
        game._abort_work_swing = Mock()
        game._work_swing_complete = Mock(return_value=True)
        return game, hut, hunter

    def test_failed_hunt_search_does_not_park_day_slot(self) -> None:
        game, hut, hunter = self._hunter_game()
        game._update_hunter(hunter, hut)
        self.assertEqual(int(getattr(hunter, "_work_search_cd", 0)), 48)
        self.assertEqual(hunter.decision_cooldown, 0)
        self.assertEqual(hunter.state, VillagerState.IDLE)

    def test_search_cooldown_does_not_repark_idle(self) -> None:
        game, hut, hunter = self._hunter_game()
        hunter._work_search_cd = 20  # type: ignore[attr-defined]
        hunter.decision_cooldown = 0
        game._update_hunter(hunter, hut)
        self.assertEqual(hunter.decision_cooldown, 0)
        # Cooldown is drained by _update_villagers, not by the hunt update.
        self.assertEqual(int(getattr(hunter, "_work_search_cd", 0)), 20)

    def test_tool_fetch_does_not_idle_clear_home_walk(self) -> None:
        game, hut, hunter = self._hunter_game()
        hunter.inventory.unequip_tool("spear")
        setattr(hunter.inventory, "spear", 0)
        hunter.inventory.equipped_tools.clear()
        game.home_storage.spear = 1
        game.home_storage.bow = 0
        hunter.x, hunter.y = 5, 5
        hunter.target = None
        hunter.move_cooldown = 0
        self.assertFalse(hunter.inventory.has_equipped_tool("spear"))
        game._update_hunter(hunter, hut)
        self.assertEqual(hunter.target, game.world.home_pos)
        self.assertEqual(hunter.state, VillagerState.WORKING)
        self.assertEqual(hunter.decision_cooldown, 0)

    def test_primary_respects_empty_hunt_area(self) -> None:
        game, hut, hunter = self._hunter_game()
        animal = SimpleNamespace(
            kind=SimpleNamespace(name="deer"),
            x=20,
            y=20,
            id=1,
        )
        game.wildlife.huntable_animals = lambda: [animal]
        hut.areas = [
            TaskArea(x0=0, y0=0, x1=2, y1=2, task_type=TaskType.HUNT, building_id=hut.id)
        ]
        # Deer outside the drawn area → not primary work.
        self.assertFalse(game._workplace_primary_available(hunter, hut))
        # Deer inside the area → primary.
        animal.x, animal.y = 1, 1
        self.assertTrue(game._workplace_primary_available(hunter, hut))

    def test_bow_without_arrows_falls_back_to_spear(self) -> None:
        game, hut, hunter = self._hunter_game()
        hunter.inventory.unequip_tool("spear")
        hunting = hunter.skills[SkillType.HUNTING]
        hunting.level = 4
        hunting.potential = max(int(hunting.potential), 4)
        hunting.peak = max(int(hunting.peak), 4)
        game.home_storage.bow = 1
        game.home_storage.stone_arrows = 0
        game.home_storage.spear = 1
        hunter.x, hunter.y = 1, 1  # already at home
        self.assertTrue(game._ensure_hunter_weapon(hunter))
        self.assertTrue(hunter.inventory.has_equipped_tool("spear"))
        self.assertFalse(hunter.inventory.has_equipped_tool("bow"))

    def test_work_search_cd_drains_while_idle_parked(self) -> None:
        game, hut, hunter = self._hunter_game()
        hunter._work_search_cd = 3  # type: ignore[attr-defined]
        hunter.decision_cooldown = 10
        hunter.idle_work_gen = game._work_gen
        hunter.move_cooldown = 0
        hunter.work_cooldown = 0
        # Minimal stubs for the rest of _update_villagers.
        game._tick_villager_building_transition = Mock()
        game._begin_villager_building_entry = Mock()
        game._village_food_amounts = Mock(return_value={})
        game._rebuild_villager_claim_snapshot = Mock()
        game._reset_tick_claims = Mock()
        game._update_villager_wellbeing = Mock()
        game._reconcile_seasonal_workplace = Mock()
        game._calendar_rate_per_tick = Mock(return_value=0.0)
        game._god_dog_villager = None
        game._update_villager_break = Mock(return_value=False)
        game._update_villager_food = Mock()
        game._update_workplace_worker = Mock()
        game._update_hauler = Mock()
        game._update_unassigned = Mock()
        # Only drain the first loop of _update_villagers.
        for villager in game.villagers:
            game._tick_villager_building_transition(villager)
            if villager.decision_cooldown > 0:
                villager.decision_cooldown -= 1
            search_cd = int(getattr(villager, "_work_search_cd", 0) or 0)
            if search_cd > 0:
                villager._work_search_cd = search_cd - 1  # type: ignore[attr-defined]
        self.assertEqual(int(getattr(hunter, "_work_search_cd", 0)), 2)
        self.assertEqual(hunter.decision_cooldown, 9)


if __name__ == "__main__":
    unittest.main()
