"""Worker assignment: seasonal priorities, labourer-only build, field wake."""

from __future__ import annotations

import unittest

from entities import (
    DEFAULT_PRIORITIES_HOME,
    Villager,
    WorkPriority,
)
from seasons import Season, TICKS_PER_DAY
from world import FeatureType, TerrainType, World


class SeasonalPriorityTests(unittest.TestCase):
    def test_seasonal_row_is_what_ai_reads(self) -> None:
        villager = Villager(id=1, x=0, y=0)
        villager.seasonal_priorities = True
        villager.priorities = [
            WorkPriority.WORKPLACE,
            WorkPriority.TRANSPORT,
            WorkPriority.NONE,
        ]
        villager.cycle_priority_slot(0, season=Season.WINTER)
        self.assertEqual(
            villager.active_priorities(Season.WINTER)[0],
            WorkPriority.NONE,
        )
        self.assertEqual(
            villager.active_priorities(Season.SUMMER)[0],
            WorkPriority.WORKPLACE,
        )

    def test_unassigned_labourer_keeps_build(self) -> None:
        villager = Villager(id=1, x=0, y=0)
        villager.priorities = [
            WorkPriority.BUILD,
            WorkPriority.TRANSPORT,
            WorkPriority.NONE,
        ]
        self.assertIn(WorkPriority.BUILD, villager.active_priorities())

    def test_assigned_worker_cannot_build(self) -> None:
        villager = Villager(id=1, x=0, y=0, building_id=3)
        villager.priorities = [
            WorkPriority.WORKPLACE,
            WorkPriority.BUILD,
            WorkPriority.TRANSPORT,
        ]
        self.assertNotIn(WorkPriority.BUILD, villager.active_priorities())

    def test_home_hauler_cannot_build(self) -> None:
        villager = Villager(id=1, x=0, y=0, assigned_to_home=True)
        villager.priorities = list(DEFAULT_PRIORITIES_HOME)
        self.assertNotIn(WorkPriority.BUILD, villager.active_priorities())


class FieldWakeTests(unittest.TestCase):
    def _quiet_world(self) -> World:
        world = World(cols=24, rows=24, seed=1)
        for row in world.cells:
            for cell in row:
                if cell.feature == FeatureType.CROP_HERB:
                    cell.growth_ticks = 0
                    cell.weeds = 1.0
        return world

    def test_crop_ripeness_wakes_once(self) -> None:
        world = self._quiet_world()
        cell = world.cells[1][1]
        cell.terrain = TerrainType.SOIL
        cell.feature = FeatureType.CROP_HERB
        cell.crop_kind = "wheat"
        cell.growth_ticks = 1
        cell.weeds = 0.0
        cell.disturbance = 0.0
        for ny in range(0, 3):
            for nx in range(0, 3):
                world.cells[ny][nx].disturbance = 0.0
        self.assertTrue(world.tick_bulk(1, day=20.0))
        self.assertEqual(cell.growth_ticks, 0)
        self.assertFalse(world.tick_bulk(1, day=20.0))

    def test_weeds_crossing_hoe_line_wakes(self) -> None:
        world = self._quiet_world()
        cell = world.cells[1][1]
        cell.terrain = TerrainType.SOIL
        cell.feature = FeatureType.CROP_HERB
        cell.crop_kind = "wheat"
        cell.growth_ticks = 0
        cell.weeds = 0.199
        cell.fertility = 1.0
        cell.weed_appearances = 1
        cell.disturbance = 0.0
        self.assertTrue(world.tick_bulk(TICKS_PER_DAY, day=20.0))
        self.assertGreaterEqual(cell.weeds, 0.2)


if __name__ == "__main__":
    unittest.main()
