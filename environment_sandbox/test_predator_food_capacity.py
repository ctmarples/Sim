import unittest
from unittest.mock import Mock

from wildlife import AnimalKind, AnimalSex, Colony, WildlifeManager, WolfMember, WolfPack
from recipes import hunt_recipe_outputs


def member(sex: AnimalSex = AnimalSex.MALE) -> WolfMember:
    return WolfMember(sex=sex, x=0, y=0)


class PredatorFoodCapacityTests(unittest.TestCase):
    def test_predator_and_bird_hunt_yields(self) -> None:
        self.assertEqual(hunt_recipe_outputs("wolf"), {"meat": 1, "fur": 2})
        self.assertEqual(hunt_recipe_outputs("fox"), {"meat": 1, "fur": 1})
        self.assertEqual(hunt_recipe_outputs("owl"), {"meat": 1, "feathers": 3})
        self.assertEqual(hunt_recipe_outputs("hawk"), {"meat": 1, "feathers": 3})

    def test_hunting_a_pack_member_does_not_remove_whole_pack(self) -> None:
        wildlife = WildlifeManager(seed=1)
        pack = WolfPack(
            7,
            2,
            3,
            [member(), member(AnimalSex.FEMALE)],
            kind=AnimalKind.WOLF,
        )
        wildlife.wolf_packs = [pack]

        target = wildlife.huntable_animals()[0]
        result = wildlife.kill_animal(target.id)

        self.assertEqual(result, (0, 0, AnimalKind.WOLF))
        self.assertEqual(pack.size(), 1)
        self.assertIn(pack, wildlife.wolf_packs)

    def test_each_pack_member_is_huntable_at_its_own_position(self) -> None:
        wildlife = WildlifeManager(seed=1)
        near = WolfMember(AnimalSex.MALE, 4, 5)
        far = WolfMember(AnimalSex.FEMALE, 20, 20)
        pack = WolfPack(7, 20, 20, [far, near], kind=AnimalKind.WOLF)
        wildlife.wolf_packs = [pack]

        adjacent = next(
            target
            for target in wildlife.huntable_animals()
            if (target.x, target.y) == (4, 5)
        )
        result = wildlife.kill_animal(adjacent.id)

        self.assertEqual(result, (4, 5, AnimalKind.WOLF))
        self.assertEqual(pack.members, [far])

    def test_extinct_forest_prey_get_a_new_breeding_pair(self) -> None:
        wildlife = WildlifeManager(seed=1)
        habitat = Mock()
        wildlife.habitats = [habitat]
        wildlife.count_kind = Mock(return_value=0)
        wildlife.breeding_grounds = Mock(return_value=[habitat])
        wildlife._seed_patch = Mock()

        wildlife._reseed_extinct_forest_species(Mock())

        self.assertEqual(wildlife._seed_patch.call_count, 2)
        seeded_kinds = {call.args[0] for call in wildlife._seed_patch.call_args_list}
        self.assertEqual(seeded_kinds, {AnimalKind.DEER, AnimalKind.BOAR})

    def test_capacity_scales_with_available_prey(self) -> None:
        wildlife = WildlifeManager(seed=1)
        wildlife.colonies = [
            Colony(1, AnimalKind.RABBIT, 0, 0, level=2, habitat_id=1),
            Colony(2, AnimalKind.VOLE, 0, 0, level=4, habitat_id=2),
        ]
        wildlife.wolf_packs = [WolfPack(1, 0, 0, [member()], kind=AnimalKind.FOX)]

        self.assertEqual(wildlife._pack_max_pop(AnimalKind.WOLF), 8)
        self.assertEqual(wildlife._pack_max_pop(AnimalKind.FOX), 12)

        wildlife.colonies[0].level = 1
        self.assertEqual(wildlife._pack_max_pop(AnimalKind.WOLF), 5)

    def test_hungry_excess_predators_starve_to_food_capacity(self) -> None:
        wildlife = WildlifeManager(seed=1)
        wildlife.colonies = [
            Colony(1, AnimalKind.RABBIT, 0, 0, level=2, habitat_id=1),
        ]
        wildlife.wolf_packs = [
            WolfPack(
                pack_id,
                0,
                0,
                [member(), member(AnimalSex.FEMALE)],
                kind=AnimalKind.WOLF,
            )
            for pack_id in range(1, 6)
        ]

        wildlife._cull_excess_predators()

        self.assertEqual(wildlife.wolf_count(), 6)

    def test_fed_pack_is_not_selected_for_starvation(self) -> None:
        wildlife = WildlifeManager(seed=1)
        fed = WolfPack(1, 0, 0, [member(), member()], fed_days_remaining=1.0)
        hungry = WolfPack(2, 0, 0, [member(), member()])
        wildlife.wolf_packs = [fed, hungry]

        wildlife._cull_excess_predators()

        self.assertEqual(fed.size(), 2)
        self.assertEqual(hungry.size(), 0)


if __name__ == "__main__":
    unittest.main()
