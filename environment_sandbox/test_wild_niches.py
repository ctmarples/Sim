import unittest

from wild_species import (
    NicheRange, WILD_BY_KEY, WildSpeciesDef, environment_allows_establishment,
    icon_recolour_for,
    niche_audit, niche_response, species_environment_suitability,
)
from world import TerrainType, World


class NicheMathTests(unittest.TestCase):
    def setUp(self):
        self.niche = NicheRange(.2, .4, .6, .8)

    def test_trapezoid_boundaries_and_transitions(self):
        self.assertEqual(niche_response(.1, self.niche), 0)
        self.assertEqual(niche_response(.2, self.niche), 0)
        self.assertTrue(0 < niche_response(.3, self.niche) < 1)
        self.assertEqual(niche_response(.5, self.niche), 1)
        self.assertTrue(0 < niche_response(.7, self.niche) < 1)
        self.assertEqual(niche_response(.8, self.niche), 0)
        self.assertEqual(niche_response(.9, self.niche), 0)
        self.assertEqual(niche_response(.5, None), 1)

    def test_weight_renormalisation_and_bounds(self):
        species = WildSpeciesDef("test", "Test", "HERB", ("GRASS",),
                                 moisture_niche=self.niche)
        score = species_environment_suitability(
            species, temperature=0, rainfall=0, soil_moisture=.5,
            fertility=0, disturbance=0)
        self.assertEqual(score.combined, 1)
        self.assertTrue(0 <= score.combined <= 1)

    def test_impossible_defined_niche_blocks_establishment(self):
        species = WildSpeciesDef("test", "Test", "HERB", ("GRASS",),
                                 moisture_niche=self.niche,
                                 fertility_niche=NicheRange(0, 0, 1, 1))
        score = species_environment_suitability(
            species, temperature=.5, rainfall=.5, soil_moisture=.1,
            fertility=.5, disturbance=.5)
        self.assertFalse(environment_allows_establishment(species, score))

    def test_rainless_day_reduces_quality_without_blocking_establishment(self):
        species = WildSpeciesDef(
            "test", "Test", "HERB", ("GRASS",),
            rainfall_niche=NicheRange(.3, .5, .8, 1),
            moisture_niche=NicheRange(.2, .4, .8, 1),
        )
        score = species_environment_suitability(
            species, temperature=.5, rainfall=0, soil_moisture=.6,
            fertility=.5, disturbance=.5)
        self.assertEqual(score.rainfall, 0)
        self.assertGreater(score.combined, 0)
        self.assertTrue(environment_allows_establishment(species, score))

    def test_terrain_remains_hard_filter(self):
        world = World(cols=8, rows=8, seed=2)
        species = WildSpeciesDef("test", "Test", "HERB", ("WATER",))
        world.cells[0][0].terrain = TerrainType.GRASS
        self.assertFalse(world.species_can_establish_at(0, 0, species))

    def test_audit_has_all_representative_scenarios(self):
        audit = niche_audit()
        self.assertEqual(len(audit), 7)
        self.assertTrue(all(audit.values()))

    def test_new_flowers_share_variant_base_and_define_both_colours(self):
        expected = {
            "clover": {"stem": (65, 145, 65), "flower": (65, 145, 65)},
            "yarrow": {"stem": (75, 130, 60), "flower": (240, 240, 225)},
            "meadowsweet": {"stem": (115, 170, 90), "flower": (225, 240, 210)},
            "nettle": {"stem": (35, 90, 45), "flower": (35, 90, 45)},
        }
        for key, colours in expected.items():
            species = WILD_BY_KEY[key]
            self.assertEqual(species.icon_base, "flower_plant")
            self.assertEqual(icon_recolour_for(species), colours)


if __name__ == "__main__":
    unittest.main()
