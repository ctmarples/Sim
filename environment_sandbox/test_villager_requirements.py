import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from resource_balance import (
    FoodSatisfaction, classify_food_satisfaction, food_preference_key,
    food_satisfaction_points, requirement_met_in_stock,
)
from society import HireCandidate, load_traveller_templates, staple_food_available
from entities import BuildingKind
from game import Game


def villager(required=("t1",), favourites=("meat_stew",), *, virtues=(), vices=()):
    return SimpleNamespace(
        required_foods=list(required), favourite_foods=list(favourites),
        virtues=list(virtues), vices=list(vices),
    )


class VillagerRequirementTests(unittest.TestCase):
    def test_meal_satisfaction_cases_and_selection_order(self):
        import recipes  # noqa: F401

        eater = villager()
        stock = ["meat_stew", "roasted_turnips", "blackberries"]
        chosen = min(stock, key=lambda key: food_preference_key(
            key, eater.required_foods, eater.favourite_foods
        ))
        self.assertEqual(chosen, "meat_stew")
        self.assertIs(
            classify_food_satisfaction(eater, ["meat_stew"]), FoodSatisfaction.FAVOURITE
        )
        self.assertIs(
            classify_food_satisfaction(eater, ["roasted_turnips"]),
            FoodSatisfaction.ACCEPTABLE,
        )
        self.assertIs(
            classify_food_satisfaction(eater, ["blackberries"]),
            FoodSatisfaction.UNWANTED,
        )
        self.assertIs(classify_food_satisfaction(eater, []), FoodSatisfaction.NONE)

    def test_or_and_and_cooked_food_requirement_matching(self):
        import recipes  # noqa: F401 — register food tiers from kitchen CSV

        self.assertTrue(staple_food_available({"roasted_turnips": 1}, ["t1"]))
        self.assertTrue(
            staple_food_available(
                {"roasted_turnips": 1, "pea_soup": 1}, ["t1", "t2"]
            )
        )
        self.assertFalse(staple_food_available({"pea_soup": 1}, ["t1", "t2"]))
        self.assertTrue(requirement_met_in_stock({"meat_stew": 1}, "t3"))
        self.assertFalse(requirement_met_in_stock({"meat_stew": 1}, "t1"))

    def test_traits_modify_reaction_without_new_requirements(self):
        picky = villager(vices=("Picky",))
        cheerful = villager(virtues=("Cheerful",))
        self.assertEqual(food_satisfaction_points(picky, FoodSatisfaction.FAVOURITE), 3)
        self.assertEqual(food_satisfaction_points(picky, FoodSatisfaction.UNWANTED), -3)
        self.assertEqual(food_satisfaction_points(cheerful, FoodSatisfaction.UNWANTED), -1)
        self.assertEqual(food_satisfaction_points(picky, FoodSatisfaction.NONE), 0)

    def test_new_fields_have_save_and_template_defaults(self):
        candidate = HireCandidate.from_dict({"id": 1, "x": 0, "y": 0})
        self.assertEqual(candidate.required_workplace, "")
        self.assertEqual(candidate.signing_fee, 0)
        self.assertEqual(candidate.required_foods, ["t1"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "travellers.csv"
            path.write_text(
                "template_id,name,tier,housing_need,required_foods,favourite_foods,favourite_is_junk,virtues,vices,"
                "extraction,farming,hunting,crafting,labour,transport,extraction_cap,farming_cap,hunting_cap,crafting_cap,labour_cap,transport_cap\n"
                "old,Old,2,1,bread;meat,stew,0,,,1,1,1,1,1,1,1,1,1,1,1,1\n",
                encoding="utf-8",
            )
            template = load_traveller_templates(str(path))[0]
            self.assertEqual(template.required_workplace, "")
            self.assertEqual(template.signing_fee, 0)
            self.assertEqual(template.required_foods, ["t1", "t2"])

    def test_workplace_and_signing_fee_are_hard_hiring_gates(self):
        import recipes  # noqa: F401

        game = Game.__new__(Game)
        game.buildings = {1: SimpleNamespace(kind=BuildingKind.TENT)}
        game.villagers = []
        game.regional_wealth = 10
        game._village_food_amounts = lambda: {"roasted_turnips": 1}
        candidate = HireCandidate(
            id=1, name="Worker", community_id=1, x=0, y=0,
            required_foods=["t1"], required_workplace="farm", signing_fee=2,
        )
        ok, reason = game._hire_requirements_met(candidate)
        self.assertFalse(ok)
        self.assertIn("workplace", reason.lower())

        game.buildings[2] = SimpleNamespace(kind=BuildingKind.FARM)
        game.regional_wealth = 1
        ok, reason = game._hire_requirements_met(candidate)
        self.assertFalse(ok)
        self.assertIn("coins", reason.lower())

        game.regional_wealth = 2
        self.assertTrue(game._hire_requirements_met(candidate)[0])


if __name__ == "__main__":
    unittest.main()
