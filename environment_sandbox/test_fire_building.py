import unittest

from building_unlock import building_cost,unlocked_kinds
from entities import Building,BuildingKind,Inventory,apply_building_storage,default_building_plot
from recipes import apply_recipe


class FireBuildingTests(unittest.TestCase):
    def test_fire_uses_one_by_one_footprint(self):
        self.assertEqual(default_building_plot(BuildingKind.FIRE),(1,1))

    def test_fire_is_start_unlocked_and_costs_two_wood(self):
        self.assertIn(BuildingKind.FIRE,unlocked_kinds(set()))
        cost=building_cost(BuildingKind.FIRE)
        self.assertEqual((cost.wood,cost.logs,cost.rock,cost.hardwood),(2,0,0,0))

    def test_fire_has_only_grilled_recipes_and_uses_wood_fuel(self):
        fire=Building(id=1,kind=BuildingKind.FIRE,x=0,y=0)
        apply_building_storage(fire)
        self.assertEqual(
            {r.name for r in fire.known_recipes()},
            {
                "grilled_meat",
                "grilled_fish",
                "grilled_mushrooms",
                "roasted_turnips",
                "root_soup",
                "pea_s",
                "barley_gruel",
                "wheat_porridge",
                "rye_porridge",
                "vegetable_pottage",
                "pease_pottage",
                "mushroom_pottage",
                "berry_porridge",
            },
        )
        self.assertTrue(fire.is_processor())
        inv=Inventory(wood=1,meat=1)
        self.assertTrue(fire.deposit_one_from(inv,"wood"))
        self.assertEqual(fire.fuel_wood,1)
        self.assertTrue(fire.deposit_one_from(inv,"meat"))
        recipe=next(r for r in fire.known_recipes() if r.name=="grilled_meat")
        apply_recipe(fire,recipe)
        self.assertEqual(fire.grilled_meat,1)


if __name__=="__main__":unittest.main()
