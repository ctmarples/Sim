"""Apiary: forage (incl. crops), yields, colonise, harvest gates, forager skip."""

from __future__ import annotations

import unittest

from balance_config import BalanceState, set_active_balance
from entities import Building, BuildingKind, apply_building_storage
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


if __name__ == "__main__":
    unittest.main()
