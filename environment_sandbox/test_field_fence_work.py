import unittest
from unittest.mock import Mock

from entities import BuildingKind, ConstructionSite, Player, Villager
from game import Game
from world import FeatureType


class FieldFenceWorkTests(unittest.TestCase):
    def test_player_harvests_ripe_crop_before_working_overlapping_fence(self) -> None:
        game = Game.__new__(Game)
        game.control_mode = "dog"
        game.sim_speed = 1
        game.player = Player(4, 5)
        cell = Mock(feature=FeatureType.CROP_HERB)
        game.world = Mock()
        game.world.get_cell.return_value = cell
        game.world.crop_herb_ready.return_value = True
        site = ConstructionSite(
            1, 4, 5, BuildingKind.FIELD, fence_field_id=10, fence_edges=("N",)
        )
        game._construction_at = Mock(return_value=site)
        game._harvest_farm_herb = Mock(return_value=True)
        game._finish_player_work = Mock()
        game._player_work_construction = Mock()

        game._interact_at_player()

        game._harvest_farm_herb.assert_called_once_with(
            4, 5, game.player.inventory, status=True
        )
        game._player_work_construction.assert_not_called()

    def test_builder_movement_target_tracks_claimed_fence_site(self) -> None:
        game = Game.__new__(Game)
        villager = Villager(1, 2, 2)
        villager.inventory.wood = 1
        site = ConstructionSite(
            9, 8, 7, BuildingKind.FIELD, need_wood=1,
            fence_field_id=10, fence_edges=("W",),
        )
        game.construction_sites = {site.id: site}
        game._find_site_needing_materials = Mock(return_value=site)
        game._carrying_build_mats = Mock(return_value=True)
        game._step_villager_toward = Mock(return_value=True)

        game._update_builder(villager)

        self.assertEqual(villager.construction_id, site.id)
        self.assertEqual(villager.target, site.center_cell())
        game._step_villager_toward.assert_called_once_with(villager, site.center_cell())

    def test_builder_finishes_supplied_fence_before_delivering_spare_wood(self) -> None:
        game = Game.__new__(Game)
        villager = Villager(1, 8, 7)
        villager.inventory.wood = 3
        villager.construction_id = 9
        site = ConstructionSite(
            9, 8, 7, BuildingKind.FIELD, need_wood=1, have_wood=1,
            fence_field_id=10, fence_edges=("W",),
        )
        game.construction_sites = {site.id: site}
        game._carrying_build_mats = Mock(return_value=True)
        game._find_site_needing_materials = Mock()
        game._villager_work_interval = Mock(return_value=1)
        game._spend_work_energy = Mock()
        game._gain_job_skill = Mock()

        game._update_builder(villager)

        self.assertGreater(site.build_progress, 0)
        game._find_site_needing_materials.assert_not_called()


if __name__ == "__main__":
    unittest.main()
