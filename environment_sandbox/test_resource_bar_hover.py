import unittest
from unittest.mock import patch

import pygame

from resource_bar import ResourceBar


class ResourceBarHoverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.font.init()

    def setUp(self) -> None:
        self.bar = ResourceBar()
        self.bar._chip_rects = {"food": pygame.Rect(10, 10, 80, 24)}
        self.bar._popup_rect = pygame.Rect(10, 44, 200, 200)

    def test_popup_stays_open_while_crossing_gap_for_one_second(self) -> None:
        with patch("pygame.time.get_ticks", return_value=100):
            self.bar.update_hover((20, 20))
        with patch("pygame.time.get_ticks", return_value=1099):
            self.bar.update_hover((20, 39))

        self.assertEqual(self.bar._hover_group, "food")

        with patch("pygame.time.get_ticks", return_value=1101):
            self.bar.update_hover((20, 39))
        self.assertIsNone(self.bar._hover_group)

    def test_popup_closes_immediately_after_cursor_leaves_grid(self) -> None:
        with patch("pygame.time.get_ticks", return_value=100):
            self.bar.update_hover((20, 20))
        with patch("pygame.time.get_ticks", return_value=200):
            self.bar.update_hover((20, 60))
        with patch("pygame.time.get_ticks", return_value=201):
            self.bar.update_hover((300, 300))

        self.assertIsNone(self.bar._hover_group)


if __name__ == "__main__":
    unittest.main()
