"""Tests for persistent continuous soil_texture generation."""

from __future__ import annotations

import unittest

from soil_texture import (
    TEXTURE_BASE,
    clamp01,
    effective_soil_texture,
    ensure_soil_texture,
    generate_soil_texture,
)
from wild_species import WILD_BY_KEY, species_environment_suitability
from world import TerrainType, World


class SoilTextureGenerationTests(unittest.TestCase):
    def test_values_clamped_and_clustered(self):
        world = World(cols=48, rows=36, seed=42)
        values = [cell.soil_texture for row in world.cells for cell in row]
        self.assertTrue(all(0.0 <= v <= 1.0 for v in values))
        self.assertTrue(all(v >= 0.0 for v in values))

        # Neighbours usually similar (mean |Δ| well below random ~0.33).
        diffs = []
        for y in range(world.rows):
            for x in range(world.cols - 1):
                diffs.append(abs(world.cells[y][x].soil_texture - world.cells[y][x + 1].soil_texture))
        self.assertLess(sum(diffs) / len(diffs), 0.08)

    def test_deterministic_for_seed(self):
        a = World(cols=32, rows=24, seed=99)
        b = World(cols=32, rows=24, seed=99)
        for ya, yb in zip(a.cells, b.cells):
            for ca, cb in zip(ya, yb):
                self.assertAlmostEqual(ca.soil_texture, cb.soil_texture, places=6)

    def test_terrain_paint_does_not_change_texture(self):
        world = World(cols=24, rows=18, seed=7)
        x = y = 10
        before = world.cells[y][x].soil_texture
        world.paint_terrain(x, y, TerrainType.SOIL, 0)
        self.assertAlmostEqual(world.cells[y][x].soil_texture, before, places=6)
        world.paint_terrain(x, y, TerrainType.MEADOW, 0)
        self.assertAlmostEqual(world.cells[y][x].soil_texture, before, places=6)

    def test_forest_meadow_boundary_not_abrupt(self):
        world = World(cols=40, rows=30, seed=11)
        # Find a forest_floor / meadow adjacency and check soft Δ.
        jumps = []
        for y in range(world.rows):
            for x in range(world.cols - 1):
                a = world.cells[y][x]
                b = world.cells[y][x + 1]
                pair = {a.terrain, b.terrain}
                if pair == {TerrainType.FOREST_FLOOR, TerrainType.MEADOW} or pair == {
                    TerrainType.FOREST_FLOOR,
                    TerrainType.GRASS,
                }:
                    jumps.append(abs(a.soil_texture - b.soil_texture))
        if jumps:
            self.assertLess(sum(jumps) / len(jumps), 0.12)

    def test_ensure_fills_legacy_unset(self):
        world = World(cols=16, rows=12, seed=3)
        for row in world.cells:
            for cell in row:
                cell.soil_texture = -1.0
        ensure_soil_texture(world)
        self.assertTrue(
            all(0.0 <= cell.soil_texture <= 1.0 for row in world.cells for cell in row)
        )

    def test_species_without_texture_niche_unaffected(self):
        nettle = WILD_BY_KEY["nettle"]
        self.assertIsNone(nettle.texture_niche)
        sandy = species_environment_suitability(
            nettle, temperature=0.5, soil_moisture=0.5,
            fertility=0.85, disturbance=0.4, soil_texture=0.1,
        )
        clayey = species_environment_suitability(
            nettle, temperature=0.5, soil_moisture=0.5,
            fertility=0.85, disturbance=0.4, soil_texture=0.9,
        )
        self.assertAlmostEqual(sandy.combined, clayey.combined, places=5)
        self.assertEqual(sandy.soil_texture, 1.0)
        self.assertEqual(clayey.soil_texture, 1.0)

    def test_texture_sensitive_species_prefer_matching_band(self):
        yarrow = WILD_BY_KEY["yarrow"]
        elder = WILD_BY_KEY["elderberry"]
        self.assertIsNotNone(yarrow.texture_niche)
        self.assertIsNotNone(elder.texture_niche)
        yarrow_sandy = species_environment_suitability(
            yarrow, temperature=0.6, soil_moisture=0.35,
            fertility=0.35, disturbance=0.4, soil_texture=0.15,
        )
        yarrow_clay = species_environment_suitability(
            yarrow, temperature=0.6, soil_moisture=0.35,
            fertility=0.35, disturbance=0.4, soil_texture=0.85,
        )
        self.assertGreater(yarrow_sandy.combined, yarrow_clay.combined)
        elder_fine = species_environment_suitability(
            elder, temperature=0.55, soil_moisture=0.55,
            fertility=0.6, disturbance=0.15, soil_texture=0.7,
        )
        elder_sand = species_environment_suitability(
            elder, temperature=0.55, soil_moisture=0.55,
            fertility=0.6, disturbance=0.15, soil_texture=0.1,
        )
        self.assertGreater(elder_fine.combined, elder_sand.combined)

    def test_effective_unset_defaults_to_base(self):
        from world import Cell

        cell = Cell(terrain=TerrainType.GRASS, soil_texture=-1.0)
        self.assertAlmostEqual(effective_soil_texture(cell), TEXTURE_BASE)
        self.assertEqual(clamp01(1.5), 1.0)


class SoilTextureSaveRoundTripTests(unittest.TestCase):
    def test_cell_dict_round_trip(self):
        from save_load import _cell_from_save, _cell_to_dict

        world = World(cols=12, rows=10, seed=5)
        cell = world.cells[3][4]
        data = _cell_to_dict(cell)
        self.assertIn("soil_texture", data)
        restored = _cell_from_save(data)
        self.assertAlmostEqual(restored.soil_texture, cell.soil_texture, places=6)

    def test_missing_texture_triggers_ensure(self):
        from save_load import _cell_from_save, _cell_to_dict

        world = World(cols=12, rows=10, seed=5)
        data = _cell_to_dict(world.cells[1][1])
        data.pop("soil_texture", None)
        restored = _cell_from_save(data)
        self.assertLess(restored.soil_texture, 0.0)
        # mimic load path
        world.cells[1][1] = restored
        ensure_soil_texture(world)
        self.assertGreaterEqual(world.cells[1][1].soil_texture, 0.0)


if __name__ == "__main__":
    unittest.main()
