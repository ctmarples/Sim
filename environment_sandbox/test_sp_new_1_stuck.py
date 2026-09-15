"""Regression: SP_new_1_stuck market seek-food loop and farm TREAT stickiness."""

from __future__ import annotations

import unittest
from pathlib import Path

import pygame

from farm_pipeline import FarmJobKind
from game import Game
from save_load import load_from_path

SAVE = Path(__file__).resolve().parents[1] / "saves" / "SP_new_1_stuck.json"


@unittest.skipUnless(SAVE.is_file(), "SP_new_1_stuck.json missing")
class SPNew1StuckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()

    def setUp(self) -> None:
        self.game = Game(headless=True)
        load_from_path(self.game, SAVE)

    def test_market_rejects_undepositable_seeds(self) -> None:
        bram = next(v for v in self.game.villagers if v.id == 16)
        market = self.game.buildings[9]
        self.assertEqual(bram.inventory.garlic_seeds, 1)
        self.assertFalse(market.can_accept_from(bram.inventory))
        self.assertFalse(market.has_gather_cargo(bram.inventory))

    def test_treat_job_stays_valid_while_fetching_repellant(self) -> None:
        moss = next(v for v in self.game.villagers if v.id == 17)
        farm = self.game.buildings[4]
        moss.farm_job_kind = FarmJobKind.TREAT.name
        moss.farm_job_cell = (35, 42)
        moss.target = self.game.world.home_pos
        self.assertTrue(
            self.game._farm_job_still_valid(moss, farm, FarmJobKind.TREAT)
        )

    def test_starving_market_worker_stops_seeking_food(self) -> None:
        bram = next(v for v in self.game.villagers if v.id == 16)
        self.assertTrue(bram.seeking_food)
        for _ in range(250):
            self.game._advance_sim_ticks(1, flush=False)
        self.assertFalse(bram.seeking_food)
        self.assertGreater(bram.satiation, 0.5)


if __name__ == "__main__":
    unittest.main()
