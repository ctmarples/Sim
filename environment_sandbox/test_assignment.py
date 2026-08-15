"""Worker assignment: seasonal workplace plan, labourer-only build, field wake."""

from __future__ import annotations

import unittest

from entities import (
    Villager,
    WorkPriority,
    WorkplaceSlot,
)
from seasons import Season, TICKS_PER_DAY
from world import FeatureType, TerrainType, World


class SeasonalWorkplaceTests(unittest.TestCase):
    def test_seasonal_row_is_what_ai_reads(self) -> None:
        villager = Villager(id=1, x=0, y=0)
        villager.seasonal_priorities = True
        villager.workplace_plan = [
            WorkplaceSlot(WorkPriority.WORKPLACE, 3),
            WorkplaceSlot(WorkPriority.LABOURER),
            WorkplaceSlot(),
        ]
        villager._sync_legacy_from_plan()
        villager.ensure_season_workplace_plan(copy_from=villager.workplace_plan)
        villager.set_workplace_slot(
            0, clear=True, season=Season.WINTER
        )
        self.assertNotIn(
            WorkPriority.WORKPLACE, villager.active_priorities(Season.WINTER)
        )
        self.assertIn(
            WorkPriority.WORKPLACE, villager.active_priorities(Season.SUMMER)
        )

    def test_unassigned_labourer_keeps_build(self) -> None:
        villager = Villager(id=1, x=0, y=0)
        villager.workplace_plan = [
            WorkplaceSlot(WorkPriority.LABOURER),
            WorkplaceSlot(),
            WorkplaceSlot(),
        ]
        villager._sync_legacy_from_plan()
        self.assertIn(WorkPriority.BUILD, villager.active_priorities())
        self.assertIn(WorkPriority.TRANSPORT, villager.active_priorities())

    def test_assigned_worker_cannot_build(self) -> None:
        villager = Villager(id=1, x=0, y=0, building_id=3)
        villager.workplace_plan = [
            WorkplaceSlot(WorkPriority.WORKPLACE, 3),
            WorkplaceSlot(WorkPriority.LABOURER),
            WorkplaceSlot(),
        ]
        villager._sync_legacy_from_plan()
        self.assertNotIn(WorkPriority.BUILD, villager.active_priorities())
        self.assertIn(WorkPriority.TRANSPORT, villager.active_priorities())

    def test_home_hauler_cannot_build(self) -> None:
        villager = Villager(id=1, x=0, y=0, assigned_to_home=True)
        villager.set_default_priorities()
        self.assertNotIn(WorkPriority.BUILD, villager.active_priorities())
        self.assertIn(WorkPriority.TRANSPORT, villager.active_priorities())

    def test_legacy_build_transport_merges_to_labourer(self) -> None:
        villager = Villager(id=1, x=0, y=0)
        villager.priorities = [
            WorkPriority.BUILD,
            WorkPriority.TRANSPORT,
            WorkPriority.NONE,
        ]
        villager.workplace_slots = [None, None, None]
        plan = villager.ensure_workplace_plan()
        self.assertEqual(plan[0].kind, WorkPriority.LABOURER)
        self.assertEqual(plan[1].kind, WorkPriority.NONE)


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
        cell.weeds = 0.099
        cell.fertility = 1.0
        cell.weed_appearances = 1
        cell.disturbance = 0.0
        self.assertTrue(world.tick_bulk(TICKS_PER_DAY, day=20.0))
        self.assertGreaterEqual(cell.weeds, 0.1)


if __name__ == "__main__":
    unittest.main()
