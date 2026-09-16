"""Wildlife food-web rebalance: seasons, condition, density, forage, immigration."""

from __future__ import annotations

import unittest

from balance_config import BalanceState, set_active_balance
from seasons import Season
from wildlife import (
    AnimalKind,
    AnimalSex,
    WildlifeManager,
    WolfMember,
    WolfPack,
)
from world import FeatureType, TerrainType, World


class WildlifeRebalanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.balance = BalanceState()
        set_active_balance(self.balance)
        self.world = World(16, 16, seed=3)
        self.wildlife = WildlifeManager(seed=3)

    def test_bees_only_breed_in_growing_season(self) -> None:
        for season in (Season.AUTUMN, Season.WINTER):
            self.assertFalse(self.wildlife._colony_breed_season_ok(AnimalKind.BEE, season))
        self.assertTrue(self.wildlife._colony_breed_season_ok(AnimalKind.BEE, Season.SPRING))

    def test_sparse_food_reduces_condition(self) -> None:
        from wildlife import Colony

        colony = Colony(id=1, kind=AnimalKind.BEE, x=0, y=0, level=3, habitat_id=None)
        self.wildlife._colony_food_score = lambda *_: 0.1
        before = colony.condition
        self.wildlife._update_colony_condition(self.world, colony)
        self.assertLess(colony.condition, before)

    def test_split_transfers_parent_population(self) -> None:
        for row in self.world.cells:
            for cell in row:
                cell.terrain = TerrainType.MEADOW
                cell.feature = FeatureType.NONE
        self.wildlife.refresh_habitats(self.world)
        sites = self.wildlife._empty_colony_sites(AnimalKind.BEE)
        from dataclasses import replace

        second = replace(sites[0], id=len(self.wildlife.open_habitats))
        self.wildlife.open_habitats.append(second)
        colony = self.wildlife._spawn_colony(AnimalKind.BEE, sites[0], level=3)
        colony.condition = 1.0
        self.balance.set("WILDLIFE_COLONY_GROW_CHANCE", 0.0)
        self.balance.set("WILDLIFE_COLONY_SPLIT_CHANCE", 1.0)
        self.wildlife._colony_food_score = lambda *_: 1.0
        self.wildlife.rng.random = lambda: 0.5
        before = sum(c.level for c in self.wildlife.colonies)
        self.wildlife._tick_colonies(self.world, season=Season.SPRING)
        self.assertEqual(len(self.wildlife.colonies), 2)
        self.assertEqual(sum(c.level for c in self.wildlife.colonies), before)

    def test_bare_field_is_not_forage(self) -> None:
        cell = self.world.get_cell(4, 4)
        assert cell is not None
        cell.terrain = TerrainType.SOIL
        cell.feature = FeatureType.FIELD
        self.assertFalse(self.wildlife._is_forage_tile(self.world, 4, 4))

    def test_growing_crop_is_forage_ready_dormant_is_not(self) -> None:
        cell = self.world.get_cell(5, 5)
        assert cell is not None
        cell.terrain = TerrainType.SOIL
        cell.feature = FeatureType.CROP_HERB
        cell.growth_ticks = 40
        cell.deposit = 1
        self.assertTrue(self.wildlife._crop_provides_forage(cell))
        cell.growth_ticks = 0
        cell.deposit = -1
        self.assertFalse(self.wildlife._crop_provides_forage(cell))

    def test_colony_growth_is_density_dependent(self) -> None:
        for y in range(16):
            for x in range(16):
                cell = self.world.get_cell(x, y)
                assert cell is not None
                cell.terrain = TerrainType.MEADOW
                cell.feature = FeatureType.NONE
        self.wildlife.refresh_habitats(self.world)
        sites = self.wildlife._empty_colony_sites(AnimalKind.BEE)
        self.assertTrue(sites)
        colony = self.wildlife._spawn_colony(AnimalKind.BEE, sites[0], level=3)
        colony.condition = 1.0
        self.balance.set("WILDLIFE_COLONY_GROW_CHANCE", 1.0)
        before = colony.level
        grew = 0
        for _ in range(20):
            colony.level = before
            colony.condition = 1.0
            self.wildlife._tick_colonies(self.world, season=Season.SPRING)
            if colony.level > before:
                grew += 1
        self.assertLess(grew, 20)

    def test_rabbit_does_not_grow_in_winter(self) -> None:
        for y in range(16):
            for x in range(16):
                cell = self.world.get_cell(x, y)
                assert cell is not None
                cell.terrain = TerrainType.MEADOW
        self.wildlife.refresh_habitats(self.world)
        sites = self.wildlife._empty_colony_sites(AnimalKind.RABBIT)
        self.assertTrue(sites)
        colony = self.wildlife._spawn_colony(AnimalKind.RABBIT, sites[0], level=1)
        colony.condition = 1.0
        self.balance.set("WILDLIFE_COLONY_GROW_CHANCE", 1.0)
        self.wildlife._tick_colonies(self.world, season=Season.WINTER)
        self.assertEqual(colony.level, 1)

    def test_wolves_need_condition_to_breed(self) -> None:
        pack = WolfPack(
            1,
            2,
            2,
            [
                WolfMember(AnimalSex.MALE, 2, 2),
                WolfMember(AnimalSex.FEMALE, 2, 3),
            ],
            fed_days_remaining=3.0,
            condition=0.1,
        )
        self.wildlife.wolf_packs = [pack]
        self.wildlife._pack_room = lambda _k: 10  # type: ignore[method-assign]
        self.wildlife._cull_excess_predators = lambda: None  # type: ignore[method-assign]
        self.balance.set("WOLF_BREED_CHANCE", 1.0)
        before = pack.size()
        self.wildlife._breed_wolves(self.world)
        self.assertEqual(pack.size(), before)

    def test_colony_condition_rises_with_food(self) -> None:
        for y in range(16):
            for x in range(16):
                cell = self.world.get_cell(x, y)
                assert cell is not None
                cell.terrain = TerrainType.MEADOW
        self.wildlife.refresh_habitats(self.world)
        sites = self.wildlife._empty_colony_sites(AnimalKind.BEE)
        colony = self.wildlife._spawn_colony(AnimalKind.BEE, sites[0], level=1)
        colony.condition = 0.2
        self.wildlife._update_colony_condition(self.world, colony)
        self.assertGreater(colony.condition, 0.2)

    def test_food_web_seed_prefers_prey_over_predators(self) -> None:
        for y in range(16):
            for x in range(16):
                cell = self.world.get_cell(x, y)
                assert cell is not None
                cell.terrain = TerrainType.MEADOW
                cell.feature = FeatureType.NONE
        # A strip of forest floor so deer habitats exist.
        for x in range(2, 14):
            cell = self.world.get_cell(x, 2)
            assert cell is not None
            cell.terrain = TerrainType.FOREST_FLOOR
            cell.feature = FeatureType.TREE
        self.wildlife.refresh_habitats(self.world)
        self.wildlife.seed_breeding_grounds(self.world)
        rabbits = [c for c in self.wildlife.colonies if c.kind == AnimalKind.RABBIT]
        self.assertGreaterEqual(len(rabbits), 1)
        self.assertGreaterEqual(min(c.level for c in rabbits), 2)
        small_game = sum(
            c.level
            for c in self.wildlife.colonies
            if c.kind in (AnimalKind.RABBIT, AnimalKind.VOLE, AnimalKind.FROG)
        )
        ungulates = self.wildlife.count_kind(AnimalKind.DEER) + self.wildlife.count_kind(
            AnimalKind.BOAR
        )
        foxes = self.wildlife.fox_count()
        wolves = self.wildlife.wolf_count()
        self.assertLessEqual(foxes, max(0, small_game // 2 * 2))
        self.assertLessEqual(wolves, max(0, (ungulates // 3) * 2))
        for pack in self.wildlife.wolf_packs:
            self.assertGreater(pack.fed_days_remaining, 0.0)


if __name__ == "__main__":
    unittest.main()
