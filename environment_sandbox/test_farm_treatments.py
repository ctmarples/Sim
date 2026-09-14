"""Farm amendment lifecycle and compost-recipe regression tests."""

from __future__ import annotations

import unittest

from entities import Building, BuildingKind, CropPlan, HomeStorage, Player, Villager
from game import Game
from recipes import COMPOST_HEAP_RECIPES
from save_load import _cell_from_save, _cell_to_dict
from settings import building_storage_spec
from world import Cell, FeatureType, TerrainType, World


class FarmTreatmentTests(unittest.TestCase):
    def test_compost_heap_recipe_uses_ten_spoilage(self) -> None:
        recipe = next(r for r in COMPOST_HEAP_RECIPES if r.name == "compost")
        self.assertEqual(recipe.inputs, {"spoilage": 10})
        self.assertEqual(recipe.outputs, {"compost": 1})

    def test_compost_heap_holds_500_and_demands_spoilage(self) -> None:
        self.assertEqual(building_storage_spec("COMPOST_HEAP").capacity, 500)
        heap = Building(2, BuildingKind.COMPOST_HEAP, 0, 0, capacity=500)
        heap.spoilage = 480
        self.assertEqual(heap.supply_demand(), {"spoilage": 20})
        self.assertEqual(heap.haul_keys(), ("compost",))

    def test_season_end_converts_complete_batches_when_enabled(self) -> None:
        farm = Building(1, BuildingKind.FARM, 0, 0)
        farm.linked_extensions = frozenset({BuildingKind.COMPOST_HEAP})
        heap = Building(2, BuildingKind.COMPOST_HEAP, 1, 0, capacity=500)
        heap.parent_building_id = farm.id
        heap.spoilage = 45
        game = Game.__new__(Game)
        game.buildings = {farm.id: farm, heap.id: heap}
        game.home_storage = HomeStorage()
        game.home_storage.spoilage = 100
        game.villagers = []
        game.record_consumed = lambda *_args: None
        game.record_produced = lambda *_args: None
        self.assertEqual(game._convert_seasonal_compost(), 4)
        self.assertEqual(heap.spoilage, 5)
        self.assertEqual(heap.compost, 4)
        self.assertEqual(game.home_storage.spoilage, 100)

        farm.set_recipe_enabled("compost", False)
        heap.spoilage = 25
        self.assertEqual(game._convert_seasonal_compost(), 0)
        self.assertEqual(heap.spoilage, 25)

    def test_extension_interaction_keeps_the_extension_selected(self) -> None:
        heap = Building(2, BuildingKind.COMPOST_HEAP, 1, 0)
        game = Game.__new__(Game)
        self.assertIs(game._player_interact_workplace(heap), heap)

    def test_treatment_state_round_trips_in_cell_save(self) -> None:
        cell = Cell(TerrainType.GRASS)
        cell.compost_cycle_applied = True
        cell.mineral_cycle_applied = True
        cell.weed_suppression = 0.10
        cell.repellant_season = "SUMMER"
        cell.compost_season = "SPRING"
        loaded = _cell_from_save(_cell_to_dict(cell))
        self.assertTrue(loaded.compost_cycle_applied)
        self.assertTrue(loaded.mineral_cycle_applied)
        self.assertAlmostEqual(loaded.weed_suppression, 0.10)
        self.assertEqual(loaded.repellant_season, "SUMMER")
        self.assertEqual(loaded.compost_season, "SPRING")

    def test_harvest_resets_crop_cycle_treatments(self) -> None:
        world = World(12, 12)
        cell = world.get_cell(0, 0)
        assert cell is not None
        cell.terrain = TerrainType.SOIL
        cell.feature = FeatureType.CROP_HERB
        cell.crop_kind = "wheat"
        cell.growth_ticks = 0
        cell.compost_cycle_applied = True
        cell.compost_season = "SPRING"
        cell.mineral_cycle_applied = True
        cell.weed_suppression = 0.10
        self.assertEqual(world.harvest_crop_herb(0, 0), "wheat")
        # Compost is seasonal; mineral resets each crop cycle.
        self.assertEqual(cell.compost_season, "SPRING")
        self.assertFalse(cell.mineral_cycle_applied)
        self.assertEqual(cell.weed_suppression, 0.0)

    def test_bare_harvested_soil_gets_compost_before_direct_resowing(self) -> None:
        farm = Building(1, BuildingKind.FARM, 0, 0)
        farm.compost = 1
        worker = Villager(1, 0, 0)
        cell = Cell(TerrainType.SOIL)
        cell.fertility = 0.40
        game = Game.__new__(Game)
        from seasons import Season

        game.calendar_day = 1  # Spring
        game.buildings = {farm.id: farm}
        game.home_storage = HomeStorage()
        consumed: list[tuple[str, int]] = []
        game.record_consumed = lambda key, amount: consumed.append((key, amount))

        game._farm_apply_preplant_treatments(worker, farm, cell, for_plough=True)

        self.assertEqual(cell.compost_season, "SPRING")
        self.assertTrue(cell.compost_cycle_applied)
        self.assertAlmostEqual(cell.fertility, 0.50)
        self.assertEqual(farm.compost, 0)
        self.assertEqual(consumed, [("compost", 1)])

    def test_player_can_sow_the_crop_planned_for_a_field_cell(self) -> None:
        field = Building(2, BuildingKind.FIELD, 2, 2)
        field.plot_w = field.plot_h = 1
        field.plans = [CropPlan(1, 2, 2, 2, 2, "wheat", field.id)]
        game = Game.__new__(Game)
        game.world = World(12, 12)
        cell = game.world.get_cell(2, 2)
        assert cell is not None
        cell.terrain = TerrainType.SOIL
        cell.feature = FeatureType.NONE
        cell.ploughed = True
        game.buildings = {field.id: field}
        game.player = Player(2, 2)
        game.player.inventory.wheat_grain = 1
        game.calendar_day = 56  # Autumn wheat planting season
        game.ticks_per_day = 10
        game.record_consumed = lambda *_args: None
        game._refresh_indicators = lambda: None
        game._finish_player_work = lambda: None
        game._set_status = lambda _status: None
        game.sounds = type("S", (), {"emit": lambda *a, **k: None})()

        # Bypass the timed job and apply sow immediately.
        crop = __import__("crops", fromlist=["CROP_BY_KEY"]).CROP_BY_KEY["wheat"]
        actions = game._field_tile_action_choices(field, 2, 2, crop)
        self.assertEqual([a[0] for a in actions], ["sow"])
        self.assertTrue(
            game._player_apply_sow_job(
                2, 2, {"crop_key": "wheat", "seed_key": "wheat_grain"}
            )
        )
        self.assertEqual(cell.feature, FeatureType.CROP_HERB)
        self.assertEqual(cell.crop_kind, "wheat")
        self.assertEqual(game.player.inventory.wheat_grain, 0)


if __name__ == "__main__":
    unittest.main()
