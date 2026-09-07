import unittest

from tutorial_progress import normalize_step, reached, step_rank


class TutorialProgressTests(unittest.TestCase):
    def test_story_order(self):
        self.assertLess(step_rank("forage_meadow"), step_rank("create_orchard_field"))
        self.assertLess(step_rank("gwen_forager_intro"), step_rank("plant_orchard_bushes"))
        self.assertTrue(reached("plant_orchard_bushes", "forage_meadow"))
        self.assertTrue(reached("plant_orchard_bushes", "gwen_forager_intro"))
        self.assertFalse(reached("rhea_forage_approaches", "forage_meadow"))
        self.assertFalse(reached("equip_satchel", "forage_meadow"))

    def test_aliases(self):
        self.assertEqual(normalize_step("gwen_forager_haulers"), "gwen_forager_intro")
        self.assertTrue(reached("berry_trade_terms", "visit_berry_traveller"))


if __name__ == "__main__":
    unittest.main()
