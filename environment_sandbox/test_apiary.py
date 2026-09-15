"""Apiary: forage (incl. crops), yields, colonise, harvest gates, forager skip."""

from __future__ import annotations

import unittest

from balance_config import BalanceState, set_active_balance
from entities import Building, BuildingKind, Villager, apply_building_storage
from game import Game
from resource_balance import honey_yield_for_level
from wildlife import (
    AnimalKind,
    Colony,
    WildlifeManager,
    colony_max_level_for_forage,
)
from world import FeatureType, TerrainType, World


class ApiaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.balance = BalanceState()
        set_active_balance(self.balance)
        self.world = World(cols=24, rows=24, seed=7)
        for row in self.world.cells:
            for cell in row:
                cell.terrain = TerrainType.ROCK
                cell.feature = FeatureType.NONE
        self.wildlife = WildlifeManager(seed=7)

    def _meadow_patch(self, cx: int, cy: int, radius: int = 6) -> None:
        for y in range(cy - radius, cy + radius + 1):
            for x in range(cx - radius, cx + radius + 1):
                cell = self.world.get_cell(x, y)
                if cell is None:
                    continue
                cell.terrain = TerrainType.MEADOW
                cell.feature = FeatureType.NONE

    def test_honey_yields_wild_and_apiary(self) -> None:
        self.assertEqual(honey_yield_for_level(1), 5)
        self.assertEqual(honey_yield_for_level(4), 5)
        self.assertEqual(honey_yield_for_level(5, apiary=True), 10)
        self.assertEqual(honey_yield_for_level(6, apiary=True), 15)
        self.assertEqual(honey_yield_for_level(4, apiary=True), 5)

    def test_apiary_level_cap_higher_than_wild(self) -> None:
        self.assertEqual(colony_max_level_for_forage(AnimalKind.BEE, 60), 4)
        self.assertEqual(
            colony_max_level_for_forage(AnimalKind.BEE, 60, apiary=True), 6
        )

    def test_crop_tiles_count_as_bee_forage_without_consuming(self) -> None:
        # Barren rock with a ring of farmed crops — forage must still register.
        ax, ay = 12, 12
        for y in range(ay - 3, ay + 4):
            for x in range(ax - 3, ax + 4):
                cell = self.world.get_cell(x, y)
                assert cell is not None
                cell.terrain = TerrainType.SOIL
                cell.feature = FeatureType.CROP_HERB
                cell.crop_kind = "sage"
                cell.growth_ticks = 100
                cell.deposit = 1
        colony = self.wildlife.colonise_apiary(building_id=1, x=ax, y=ay, level=1)
        assert colony is not None
        before_features = [
            self.world.cells[y][x].feature
            for y in range(ay - 3, ay + 4)
            for x in range(ax - 3, ax + 4)
        ]
        forage_n = self.wildlife._colony_forage_count(colony, self.world)
        self.assertGreater(forage_n, 10)
        self.assertTrue(self.wildlife._colony_has_food(self.world, colony))
        # Growth tick must not clear crops (bees do not graze).
        self.balance.set("WILDLIFE_COLONY_GROW_CHANCE", 1.0)
        self.wildlife._tick_colonies(self.world)
        after_features = [
            self.world.cells[y][x].feature
            for y in range(ay - 3, ay + 4)
            for x in range(ax - 3, ax + 4)
        ]
        self.assertEqual(before_features, after_features)
        self.assertEqual(self.world.cells[ay][ax].feature, FeatureType.CROP_HERB)

    def test_colonise_and_level1_harvest_empties(self) -> None:
        colony = self.wildlife.colonise_apiary(1, 5, 5, level=1)
        assert colony is not None
        self.assertTrue(colony.is_apiary)
        self.assertEqual(colony.level, 1)
        result = self.wildlife.harvest_colony(colony.id, kind=AnimalKind.BEE)
        self.assertEqual(result, (AnimalKind.BEE, 5))
        self.assertIsNone(self.wildlife.colony_for_apiary(1))

    def test_apiary_min_harvest_gate_helpers(self) -> None:
        building = Building(id=9, kind=BuildingKind.APIARY, x=4, y=4)
        apply_building_storage(building)
        building.apiary_min_harvest_level = 3
        self.assertEqual(building.depositable_keys(), ("honey",))
        colony = self.wildlife.colonise_apiary(9, 4, 4, level=2)
        assert colony is not None
        self.assertFalse(colony.level >= building.apiary_min_harvest_level)
        colony.level = 3
        self.assertTrue(colony.level >= building.apiary_min_harvest_level)

    def test_forager_target_predicate_skips_apiary(self) -> None:
        wild = Colony(
            id=1, kind=AnimalKind.BEE, x=2, y=2, level=2, habitat_id=0
        )
        apiary = Colony(
            id=2,
            kind=AnimalKind.BEE,
            x=3,
            y=3,
            level=4,
            apiary_building_id=7,
        )
        self.wildlife.colonies = [wild, apiary]
        targets = [
            c
            for c in self.wildlife.colonies
            if c.kind == AnimalKind.BEE and not c.is_apiary and c.can_harvest()
        ]
        self.assertEqual([c.id for c in targets], [1])


class ApiaryNetworkTests(unittest.TestCase):
    """Shared workers across apiaries; per-hive mins; bee transfer from harvestable hives."""

    @classmethod
    def setUpClass(cls) -> None:
        import pygame

        pygame.init()

    def setUp(self) -> None:
        self.game = Game(headless=True)
        self.game.sim_speed = 1
        # Clear default world clutter; place two apiaries and one worker.
        g = self.game
        g.buildings.clear()
        g.villagers.clear()
        g.wildlife.colonies.clear()
        from entities import apply_building_storage

        a = Building(id=1, kind=BuildingKind.APIARY, x=4, y=4)
        b = Building(id=2, kind=BuildingKind.APIARY, x=10, y=4)
        apply_building_storage(a)
        apply_building_storage(b)
        a.apiary_min_harvest_level = 4
        b.apiary_min_harvest_level = 2
        g.buildings[1] = a
        g.buildings[2] = b
        g.next_building_id = 3
        v = Villager(1, 4, 4)
        v.name = "Beekeeper"
        g.villagers.append(v)
        g.wildlife = WildlifeManager(seed=3)

    def test_assign_to_one_apiary_covers_network(self) -> None:
        g = self.game
        g._assign_villager_to_building(1, 1)
        self.assertTrue(g._villager_on_apiary_network(g.villagers[0]))
        self.assertEqual(g._apiary_workers(), [g.villagers[0]])
        g.wildlife.colonies.append(
            Colony(id=99, kind=AnimalKind.BEE, x=8, y=8, level=2, habitat_id=0)
        )
        self.assertTrue(g._apiary_has_work(g.villagers[0], g.buildings[1]))
        self.assertTrue(g._apiary_has_work(g.villagers[0], g.buildings[2]))

    def test_min_harvest_levels_stay_independent(self) -> None:
        g = self.game
        g.wildlife.colonise_apiary(1, 4, 4, level=3)
        g.wildlife.colonise_apiary(2, 10, 4, level=3)
        self.assertFalse(g._apiary_can_harvest(g.buildings[1]))  # min 4
        self.assertTrue(g._apiary_can_harvest(g.buildings[2]))  # min 2

    def test_colonise_empty_from_harvestable_apiary(self) -> None:
        g = self.game
        source = g.wildlife.colonise_apiary(1, 4, 4, level=4)
        assert source is not None
        self.assertTrue(g._apiary_can_harvest(g.buildings[1]))
        self.assertTrue(g._apiary_needs_colonise(g.buildings[2]))
        found = g._find_bee_source_for_apiary(g.villagers[0])
        self.assertIsNotNone(found)
        assert found is not None
        self.assertTrue(found.is_apiary)
        self.assertEqual(found.apiary_building_id, 1)
        # Below min on A: cannot transfer.
        g.buildings[1].apiary_min_harvest_level = 6
        self.assertIsNone(g._find_bee_source_for_apiary(g.villagers[0]))

    def test_harvest_transfer_drops_source_and_fills_empty(self) -> None:
        g = self.game
        source = g.wildlife.colonise_apiary(1, 4, 4, level=4)
        assert source is not None
        result = g.wildlife.harvest_colony(source.id, kind=AnimalKind.BEE)
        self.assertIsNotNone(result)
        left = g.wildlife.colony_for_apiary(1)
        self.assertIsNotNone(left)
        assert left is not None
        self.assertEqual(left.level, 3)
        started = g.wildlife.colonise_apiary(2, 10, 4, level=1)
        self.assertIsNotNone(started)
        self.assertEqual(g.wildlife.colony_for_apiary(2).level, 1)

    def test_unreachable_bees_falls_back_to_harvest(self) -> None:
        """Empty hives must not park the worker when a hive can still be collected."""
        from unittest.mock import Mock

        from entities import VillagerState

        g = self.game
        g._assign_villager_to_building(1, 1)
        v = g.villagers[0]
        g.wildlife.colonise_apiary(1, 4, 4, level=4)
        g._find_bee_source_for_apiary = Mock(return_value=None)
        g._step_villager_toward = Mock()
        g._work_swing_complete = Mock(return_value=False)
        g._spend_work_energy = Mock()
        g._gain_job_skill = Mock()
        g.record_produced = Mock()
        v._work_search_cd = 0  # type: ignore[attr-defined]
        g._update_apiary(v, g.buildings[1])
        self.assertEqual(v.state, VillagerState.WORKING)
        self.assertEqual(v.target, (4, 4))
        self.assertEqual(int(getattr(v, "_work_search_cd", 0)), 0)

    def test_search_cd_still_allows_harvest(self) -> None:
        from unittest.mock import Mock

        g = self.game
        g._assign_villager_to_building(1, 1)
        v = g.villagers[0]
        g.wildlife.colonise_apiary(1, 4, 4, level=4)
        v._work_search_cd = 20  # type: ignore[attr-defined]
        g._step_villager_toward = Mock()
        g._work_swing_complete = Mock(return_value=False)
        g._update_apiary(v, g.buildings[1])
        self.assertEqual(v.target, (4, 4))
        self.assertEqual(int(getattr(v, "_work_search_cd", 0)), 0)

    def test_releases_foreign_haul_when_hives_need_work(self) -> None:
        from entities import VillagerState

        g = self.game
        g._assign_villager_to_building(1, 1)
        v = g.villagers[0]
        g.wildlife.colonise_apiary(1, 4, 4, level=4)
        mill = Building(id=9, kind=BuildingKind.MILL, x=2, y=2)
        apply_building_storage(mill)
        mill.flour = 5
        g.buildings[9] = mill
        v.state = VillagerState.HAULING
        v.haul_building_id = 9
        v.target = (2, 2)
        self.assertTrue(g._release_helper_haul_for_primary(v))
        self.assertIsNone(v.haul_building_id)
        self.assertEqual(v.state, VillagerState.IDLE)

    def test_partial_honey_does_not_force_assigned_transport(self) -> None:
        g = self.game
        g._assign_villager_to_building(1, 1)
        v = g.villagers[0]
        g.wildlife.colonise_apiary(1, 4, 4, level=4)
        v.inventory.honey = 2
        self.assertTrue(g._apiary_has_work(v, g.buildings[1]))
        self.assertFalse(g._assigned_transport_has_work(v, g.buildings[1]))


if __name__ == "__main__":
    unittest.main()
