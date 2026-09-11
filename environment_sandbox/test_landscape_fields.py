"""Headless checks for the isolated Landscape Fields prototype."""

from __future__ import annotations

import unittest

from landscape_fields import (
    LandscapeFieldsParams,
    apply_landscape_texture_to_world,
    build_landscape_fields_map,
    field_correlations,
    generate_landscape_fields,
)
from world import World


class LandscapeFieldsTests(unittest.TestCase):
    def _generate(self, seed: int = 4201):
        params = LandscapeFieldsParams(seed=seed)
        generated = build_landscape_fields_map(params)
        world = World(
            cols=generated.options.width,
            rows=generated.options.height,
            seed=generated.options.seed,
        )
        generated.apply_to_world(world)
        state = generate_landscape_fields(world, params)
        apply_landscape_texture_to_world(world, state)
        return world, state

    def test_same_seed_is_deterministic(self):
        _, a = self._generate(4201)
        _, b = self._generate(4201)
        self.assertEqual(a.soil_texture, b.soil_texture)
        self.assertEqual(a.fertility_potential, b.fertility_potential)
        self.assertEqual(a.hydrological_position, b.hydrological_position)
        self.assertEqual(a.soil_moisture_baseline, b.soil_moisture_baseline)

    def test_different_seeds_differ(self):
        _, a = self._generate(4201)
        _, b = self._generate(4202)
        self.assertNotEqual(a.soil_texture, b.soil_texture)

    def test_ranges_and_water(self):
        world, state = self._generate(7)
        water_count = 0
        for y in range(world.rows):
            for x in range(world.cols):
                for grid in (
                    state.soil_texture,
                    state.fertility_potential,
                    state.hydrological_position,
                    state.soil_moisture_baseline,
                ):
                    self.assertGreaterEqual(grid[y][x], 0.0)
                    self.assertLessEqual(grid[y][x], 1.0)
                if state.water_mask[y][x]:
                    water_count += 1
                    self.assertEqual(state.hydrological_position[y][x], 1.0)
                    self.assertEqual(state.soil_moisture_baseline[y][x], 1.0)
        self.assertGreater(water_count, 5)

    def test_hydrology_moisture_correlation_positive(self):
        correlations = []
        for seed in (11, 42, 99, 4201, 7777):
            _, state = self._generate(seed)
            corr = field_correlations(state)
            correlations.append(corr)
            self.assertGreater(corr["hydrology_vs_moisture"], 0.45)
            self.assertLess(corr["hydrology_vs_moisture"], 0.97)
            # Independence guardrails — not near ±1.
            self.assertLess(abs(corr["texture_vs_fertility"]), 0.75)
            self.assertLess(abs(corr["texture_vs_moisture"]), 0.75)

    def test_texture_written_to_cells(self):
        world, state = self._generate(55)
        self.assertAlmostEqual(
            world.cells[3][3].soil_texture, state.soil_texture[3][3], places=5
        )

    def test_species_suitability_deterministic_and_differentiated(self):
        from wild_species import WILD_BY_KEY
        from landscape_fields import suitability_grid

        world, state = self._generate(4201)
        yarrow = suitability_grid(world, state, WILD_BY_KEY["yarrow"])
        meadow = suitability_grid(world, state, WILD_BY_KEY["meadowsweet"])
        world2, state2 = self._generate(4201)
        self.assertEqual(yarrow, suitability_grid(world2, state2, WILD_BY_KEY["yarrow"]))
        y_hi = sum(1 for row in yarrow for v in row if v >= 0.5)
        m_hi = sum(1 for row in meadow for v in row if v >= 0.5)
        overlap = sum(
            1
            for y, row in enumerate(yarrow)
            for x, v in enumerate(row)
            if v >= 0.5 and meadow[y][x] >= 0.5
        )
        self.assertGreater(y_hi, 50)
        self.assertGreater(m_hi, 0)
        # Specialists should mostly diverge; allow a little transitional overlap
        # on full-size maps with mixed cover.
        self.assertLess(overlap / max(1, min(y_hi, m_hi)), 0.35)


if __name__ == "__main__":
    unittest.main()
