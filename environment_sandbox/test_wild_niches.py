import unittest

from wild_species import (
    NicheRange, WILD_BY_KEY, WildSpeciesDef, environment_allows_establishment,
    icon_recolour_for,
    niche_audit, niche_response, spawn_probability, species_environment_suitability,
)
from world import FeatureType, TerrainType, World


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
            species, temperature=0, soil_moisture=.5,
            fertility=0, disturbance=0)
        self.assertEqual(score.combined, 1)
        self.assertTrue(0 <= score.combined <= 1)

    def test_impossible_defined_niche_blocks_establishment(self):
        species = WildSpeciesDef("test", "Test", "HERB", ("GRASS",),
                                 moisture_niche=self.niche,
                                 fertility_niche=NicheRange(0, 0, 1, 1))
        score = species_environment_suitability(
            species, temperature=.5, soil_moisture=.1,
            fertility=.5, disturbance=.5)
        self.assertFalse(environment_allows_establishment(species, score))

    def test_texture_mismatch_blocks_establishment(self):
        species = WildSpeciesDef(
            "test", "Test", "HERB", ("GRASS",),
            moisture_niche=NicheRange(0, 0, 1, 1),
            texture_niche=NicheRange(.0, .05, .25, .40),
        )
        score = species_environment_suitability(
            species, temperature=.5, soil_moisture=.5,
            fertility=.5, disturbance=.5, soil_texture=.9)
        self.assertEqual(score.soil_texture, 0)
        self.assertFalse(environment_allows_establishment(species, score))

    def test_spawn_probability_strengthens_middling_sites(self):
        self.assertEqual(spawn_probability(1.0), 1.0)
        self.assertEqual(spawn_probability(0.0), 0.0)
        self.assertLess(spawn_probability(0.5), 0.5)

    def test_terrain_remains_hard_filter(self):
        world = World(cols=8, rows=8, seed=2)
        species = WildSpeciesDef("test", "Test", "HERB", ("WATER",))
        world.cells[0][0].terrain = TerrainType.GRASS
        self.assertFalse(world.species_can_establish_at(0, 0, species))

    def test_fallen_wood_requires_an_adjacent_tree(self):
        world = World(cols=8, rows=8, seed=2)
        for row in world.cells:
            for cell in row:
                cell.feature = FeatureType.NONE
                cell.terrain = TerrainType.GRASS
        wood = WILD_BY_KEY["wood_bush"]
        self.assertFalse(world._species_can_occupy(4, 4, wood))
        world.cells[4][3].feature = FeatureType.TREE
        self.assertTrue(world._species_can_occupy(4, 4, wood))

    def test_fallen_wood_uses_loose_wood_variants(self):
        from icons import variant_names

        self.assertEqual(WILD_BY_KEY["wood_bush"].icon_base, "wood_loose")
        self.assertEqual(
            variant_names("wood_loose"),
            ("wood_loose_1", "wood_loose_2", "wood_loose_3", "wood_loose_4"),
        )

    def test_mushroom_can_establish_on_dry_autumn_forest_floor(self):
        mushroom = WILD_BY_KEY["mushroom"]
        score = species_environment_suitability(
            mushroom,
            temperature=.4,
            soil_moisture=.10,
            fertility=.6,
            disturbance=.05,
        )
        self.assertTrue(environment_allows_establishment(mushroom, score))
        self.assertGreater(score.combined, 0)

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

    def test_catalogue_has_no_rainfall_niche(self):
        for species in WILD_BY_KEY.values():
            self.assertFalse(hasattr(species, "rainfall_niche") and
                             getattr(species, "rainfall_niche") is not None
                             and "rainfall_niche" in species.__dataclass_fields__)
        self.assertNotIn("rainfall_niche", WildSpeciesDef.__dataclass_fields__)

    def test_plants_json_projection_keeps_texture_niches(self):
        """Startup plant reload must not wipe authored texture preferences."""
        from developer_tools.plant_editor import PlantEditorService

        ok, _message = PlantEditorService().load()
        self.assertTrue(ok)
        self.assertIsNotNone(WILD_BY_KEY["yarrow"].texture_niche)
        self.assertIsNotNone(WILD_BY_KEY["sage"].texture_niche)
        self.assertIsNone(WILD_BY_KEY["nettle"].texture_niche)


if __name__ == "__main__":
    unittest.main()
