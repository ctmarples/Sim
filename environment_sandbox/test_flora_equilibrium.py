"""Live World flora uses half-season equilibrium cohorts."""

from __future__ import annotations

import unittest
from collections import Counter

from balance_config import BalanceState, set_active_balance
from flora_equilibrium import allocate_capacity, composition_weight, wild_plant_capacity
from seasons import HALF_SEASON_DAYS, half_season_index
from world import FeatureType, TerrainType, World


class FloraEquilibriumUnitTests(unittest.TestCase):
    def test_allocate_respects_activity_underfill(self):
        from wild_species import WILD_BY_KEY

        a = WILD_BY_KEY["thyme"]
        b = WILD_BY_KEY["hemp"]
        claims = [
            (a, 1.0, 1.0),
            (b, 1.0, 0.0),
        ]
        out = dict(allocate_capacity(claims, capacity=100.0, terrain_fill=1.0))
        self.assertAlmostEqual(out[a], 50.0)
        self.assertAlmostEqual(out[b], 0.0)

    def test_weighted_sample_not_greedy_top_n(self):
        """Suitability-weighted picks must sometimes choose below the top scores."""
        import random

        # Five excellent cells + many mediocre ones. Greedy need=5 always takes
        # only the excellent band; weighted sampling should often include y=1.
        sites = [(1.0, i, 0) for i in range(5)] + [(0.25, i, 1) for i in range(95)]
        low_hits = 0
        trials = 200
        for seed in range(trials):
            picked = World._weighted_sample_sites(sites, 5, random.Random(seed))
            if any(y == 1 for _x, y in picked):
                low_hits += 1
        self.assertGreater(low_hits, trials // 4)

    def test_weighted_sample_respects_cell_load_cap(self):
        import random

        from flora_equilibrium import MAX_WILD_PER_CELL as CAP

        sites = [(1.0, 0, 0), (0.9, 1, 0), (0.8, 2, 0)]
        load = {(0, 0): CAP}
        picked = World._weighted_sample_sites(
            sites, 3, random.Random(1), cell_load=load, max_per_cell=CAP
        )
        self.assertNotIn((0, 0), picked)
        self.assertEqual(len(picked), 2)


class FloraEquilibriumWorldTests(unittest.TestCase):
    def setUp(self) -> None:
        set_active_balance(BalanceState())

    def _flora_count(self, world: World) -> int:
        return sum(
            int(
                cell.feature
                in (
                    FeatureType.WILD_CROP,
                    FeatureType.HERB,
                    FeatureType.MUSHROOM,
                    FeatureType.WOOD_BUSH,
                    FeatureType.REED,
                )
            )
            + sum(
                obj.feature
                in (
                    FeatureType.WILD_CROP,
                    FeatureType.HERB,
                    FeatureType.MUSHROOM,
                    FeatureType.WOOD_BUSH,
                    FeatureType.REED,
                )
                for obj in cell.extra_objects
            )
            for row in world.cells
            for cell in row
        )

    def test_establish_places_wild_crops_on_fresh_map(self) -> None:
        world = World(cols=36, rows=36, seed=11)
        world.generate()
        kinds = Counter(
            cell.crop_kind
            for row in world.cells
            for cell in row
            if cell.feature == FeatureType.WILD_CROP and cell.crop_kind
        )
        self.assertGreater(sum(kinds.values()), 0)
        self.assertIn("hemp", kinds)

    def test_respawn_places_open_land_not_only_forest(self) -> None:
        world = World(cols=40, rows=40, seed=5)
        world.respawn_flora(35.0, passes=32)
        open_crops = 0
        litter = 0
        for row in world.cells:
            for cell in row:
                if cell.feature == FeatureType.WILD_CROP and cell.terrain in (
                    TerrainType.GRASS,
                    TerrainType.MEADOW,
                    TerrainType.SOIL,
                ):
                    open_crops += 1
                if cell.feature in (FeatureType.MUSHROOM, FeatureType.WOOD_BUSH):
                    litter += 1
                litter += sum(
                    1
                    for obj in cell.extra_objects
                    if obj.feature in (FeatureType.MUSHROOM, FeatureType.WOOD_BUSH)
                )
        self.assertGreater(open_crops, 0)
        # Mush/wood share terrain capacity — must not dominate open forage.
        self.assertLess(litter, open_crops)

    def test_summer_heat_does_not_empty_grass(self) -> None:
        """Temperature must not hard-veto seasonal flora (wood_bush has no niches)."""
        from types import SimpleNamespace

        world = World(cols=40, rows=40, seed=5)
        world.generate()
        world.env_maps = SimpleNamespace(
            soil_moisture=[[0.45] * world.cols for _ in range(world.rows)],
            temperature=[[30.0] * world.cols for _ in range(world.rows)],
            rainfall=[[0.3] * world.cols for _ in range(world.rows)],
        )
        world.respawn_flora(35.0, passes=32)
        grass_crops = 0
        grass_wood = 0
        for row in world.cells:
            for cell in row:
                if cell.terrain != TerrainType.GRASS:
                    continue
                if cell.feature == FeatureType.WILD_CROP:
                    grass_crops += 1
                if cell.feature == FeatureType.WOOD_BUSH:
                    grass_wood += 1
                grass_wood += sum(
                    1 for obj in cell.extra_objects if obj.feature == FeatureType.WOOD_BUSH
                )
        self.assertGreater(grass_crops, 0)
        self.assertGreater(grass_crops, grass_wood)

    def test_no_mass_despawn_after_mid_half_respawn(self) -> None:
        world = World(cols=36, rows=36, seed=11)
        world.respawn_flora(20.0, passes=32)
        start = self._flora_count(world)
        self.assertGreater(start, 0)
        for day in range(20, 50):
            world._tick_flora_half_season(float(day))
            count = self._flora_count(world)
            self.assertGreater(
                count,
                start * 0.5,
                f"flora collapsed at day {day}: {count} vs start {start}",
            )

    def test_half_boundary_swaps_stand_atomically(self) -> None:
        world = World(cols=28, rows=28, seed=2)
        world.respawn_flora(10.0, passes=32)
        before = self._flora_count(world)
        self.assertGreater(before, 0)
        first_half = world._flora_half_index
        next_day = float((first_half + 1) * HALF_SEASON_DAYS)
        world._tick_flora_half_season(next_day)
        self.assertEqual(world._flora_half_index, half_season_index(next_day))
        after = self._flora_count(world)
        self.assertGreater(after, before * 0.5)
        # Same-day re-tick must not clear again.
        world._tick_flora_half_season(next_day)
        self.assertEqual(self._flora_count(world), after)

    def test_plants_stable_within_half_season(self) -> None:
        world = World(cols=28, rows=28, seed=9)
        world.respawn_flora(20.0, passes=32)
        before = self._flora_count(world)
        for _ in range(8):
            world._tick_herbs_seasonal(20.0)
        self.assertEqual(self._flora_count(world), before)

    def test_capacity_helper_matches_fraction_times_subcells(self) -> None:
        self.assertAlmostEqual(wild_plant_capacity(100), 100 * 0.20 * 3)


if __name__ == "__main__":
    unittest.main()
