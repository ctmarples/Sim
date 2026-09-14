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


def villager(required=("bread",), favourites=("stew",), *, virtues=(), vices=()):
    return SimpleNamespace(
        required_foods=list(required), favourite_foods=list(favourites),
        virtues=list(virtues), vices=list(vices),
    )


class VillagerRequirementTests(unittest.TestCase):
    def test_meal_satisfaction_cases_and_selection_order(self):
        eater = villager()
        stock = ["stew", "bread", "blackberries"]
        chosen = min(stock, key=lambda key: food_preference_key(
            key, eater.required_foods, eater.favourite_foods
        ))
        self.assertEqual(chosen, "stew")
        self.assertIs(classify_food_satisfaction(eater, ["stew"]), FoodSatisfaction.FAVOURITE)
        self.assertIs(classify_food_satisfaction(eater, ["bread"]), FoodSatisfaction.ACCEPTABLE)
        self.assertIs(classify_food_satisfaction(eater, ["blackberries"]), FoodSatisfaction.UNWANTED)
        self.assertIs(classify_food_satisfaction(eater, []), FoodSatisfaction.NONE)

    def test_or_and_and_cooked_food_requirement_matching(self):
        self.assertTrue(staple_food_available({"fish": 1}, ["meat/fish"]))
        self.assertTrue(staple_food_available({"bread": 1, "carrot": 1}, ["bread", "vegetables"]))
        self.assertFalse(staple_food_available({"bread": 1}, ["bread", "vegetables"]))
        self.assertTrue(requirement_met_in_stock({"stew": 1}, "vegetables"))
        self.assertTrue(requirement_met_in_stock({"stew": 1}, "meat"))

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
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "travellers.csv"
            path.write_text(
                "template_id,name,tier,housing_need,required_foods,favourite_foods,favourite_is_junk,virtues,vices,"
                "extraction,farming,hunting,crafting,labour,transport,extraction_cap,farming_cap,hunting_cap,crafting_cap,labour_cap,transport_cap\n"
                "old,Old,1,1,bread,stew,0,,,1,1,1,1,1,1,1,1,1,1,1,1\n",
                encoding="utf-8",
            )
            template = load_traveller_templates(str(path))[0]
            self.assertEqual(template.required_workplace, "")
            self.assertEqual(template.signing_fee, 0)

    def test_workplace_and_signing_fee_are_hard_hiring_gates(self):
        game = Game.__new__(Game)
        game.buildings = {1: SimpleNamespace(kind=BuildingKind.TENT)}
        game.villagers = []
        game.regional_wealth = 10
        game._village_food_amounts = lambda: {"bread": 1}
        candidate = HireCandidate(
            id=1, name="Worker", community_id=1, x=0, y=0,
            required_foods=["bread"], required_workplace="farm", signing_fee=2,
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
