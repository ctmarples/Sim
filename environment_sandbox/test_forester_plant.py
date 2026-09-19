"""Forester planting / sapling stock regressions."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from entities import Building, BuildingKind, HomeStorage, TaskArea, TaskType, Villager
from game import Game
from seasons import Season
from world import FeatureType, TerrainType, World


class ForesterPlantTests(unittest.TestCase):
    def _forester_with_plant_area(self) -> tuple[Game, Building, Villager]:
        game = Game.__new__(Game)
        game.world = World(12, 12)
        game.calendar_day = 10
        game.home_storage = HomeStorage()
        game.buildings = {}
        game._claimed_work_cells = Mock(return_value=set())
        game.is_discovered = Mock(return_value=True)
        game._craftable_split_recipe = Mock(return_value=Mock(name="split_logs"))
        game._find_forester_collect_by_priority = Mock(return_value=None)
        game._pick_nearest_reachable = (
            lambda origin, cells, **kwargs: cells[0] if cells else None
        )

        lodge = Building(5, BuildingKind.FORESTER, 2, 2)
        lodge.ensure_recipe_state()
        lodge.areas = [TaskArea(4, 4, 4, 4, TaskType.PLANT_SAPLINGS, lodge.id)]
        lodge.oak_saplings = 2
        lodge.maple_saplings = 0
        lodge.pine_saplings = 0
        lodge.cedar_saplings = 0

        cell = game.world.get_cell(4, 4)
        assert cell is not None
        cell.terrain = TerrainType.GRASS
        cell.feature = FeatureType.NONE

        villager = Villager(1, 2, 2)
        game.buildings = {lodge.id: lodge}
        return game, lodge, villager

    def test_plant_beats_split_when_plant_areas_have_work(self) -> None:
        game, lodge, villager = self._forester_with_plant_area()
        picked = game._pick_forester_all_work(villager, lodge)
        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertEqual(picked[1], "plant")
        self.assertEqual(picked[0], (4, 4))

    def test_home_saplings_count_for_plant_recipe(self) -> None:
        game, lodge, villager = self._forester_with_plant_area()
        lodge.oak_saplings = 0
        lodge.maple_saplings = 0
        self.assertFalse(game._can_plant_recipe(villager, lodge, "plant_hardwood"))
        game.home_storage.oak_saplings = 3
        self.assertTrue(game._can_plant_recipe(villager, lodge, "plant_hardwood"))

    def test_plant_only_areas_still_find_nearby_softwood_trees(self) -> None:
        game, lodge, villager = self._forester_with_plant_area()
        game._pick_nearest_reachable = (
            lambda origin, cells, **kwargs: min(
                cells, key=lambda p: abs(p[0] - origin[0]) + abs(p[1] - origin[1])
            )
            if cells
            else None
        )
        tree = game.world.get_cell(6, 2)
        assert tree is not None
        tree.terrain = TerrainType.GRASS
        tree.feature = FeatureType.TREE
        tree.tree_species = "pine"
        tree.deposit = 3
        found = game._find_forester_tree_target(
            villager, lodge, "logs", claimed=set()
        )
        self.assertEqual(found, (6, 2))

    def test_player_can_plant_with_hunt_weapon_equipped(self) -> None:
        game = Game.__new__(Game)
        game.world = World(8, 8)
        game.player = Villager(1, 3, 3)  # type: ignore[assignment]
        from entities import Player

        game.player = Player(3, 3)
        game.player.inventory.oak_saplings = 1
        game.player.inventory.equip_tool("spear")
        game._huntable_near = Mock(return_value=None)
        cell = game.world.get_cell(3, 3)
        assert cell is not None
        cell.terrain = TerrainType.GRASS
        cell.feature = FeatureType.NONE
        self.assertTrue(game._player_can_plant_here(3, 3))

    def test_split_deposit_keeps_saplings(self) -> None:
        """Withdrawing plant stock then splitting must not dump saplings back."""
        game, lodge, villager = self._forester_with_plant_area()
        lodge.hardwood_logs = 2
        lodge.oak_saplings = 0
        villager.inventory.oak_saplings = 4
        villager.inventory.equip_tool("axe")
        villager.x, villager.y = lodge.center_cell()
        game._forester_try_split = Mock(return_value=True)
        game._forester_needs_axe = Mock(return_value=True)
        game._ensure_forester_axe = Mock(return_value=True)
        game._update_plant_stock_withdraw = Mock(return_value=False)
        game._gather_cargo_needs_delivery = Mock(return_value=False)
        game._workplace_primary_available = Mock(return_value=True)
        game._maybe_assigned_transport = Mock(return_value=False)
        game._should_force_carry_deposit = Mock(return_value=False)
        game._pick_forester_all_work = Mock(
            return_value=(lodge.center_cell(), "split")
        )
        game._register_field_claim = Mock()
        game._clear_villager_path = Mock()
        game._update_forester(villager, lodge)
        self.assertEqual(villager.inventory.oak_saplings, 4)
        self.assertEqual(lodge.oak_saplings, 0)


if __name__ == "__main__":
    unittest.main()
