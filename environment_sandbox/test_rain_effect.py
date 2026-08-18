import unittest

import pygame

from rain_effect import RainEffect


class RainEffectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_visual_density_follows_local_rainfall(self):
        width, height = 800, 400
        target = pygame.Surface((width, height), pygame.SRCALPHA)
        rainfall = [
            [0.8 if x < 50 else 0.04 for x in range(100)]
            for _ in range(50)
        ]
        RainEffect(seed=7).draw(
            target,
            pygame.Rect(0, 0, width, height),
            0.4,
            rainfall=rainfall,
            world_view=(0.0, 0.0, 100.0, 50.0),
        )
        alpha = pygame.surfarray.array_alpha(target)
        wet_pixels = int((alpha[: width // 2, :] > 0).sum())
        dry_pixels = int((alpha[width // 2 :, :] > 0).sum())
        self.assertGreater(wet_pixels, 1000)
        self.assertGreater(wet_pixels, dry_pixels * 6)


if __name__ == "__main__":
    unittest.main()
