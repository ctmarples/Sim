import unittest
from unittest.mock import patch

from camera import Camera


class CameraProjectionTests(unittest.TestCase):
    def test_small_height_map_centres_projected_bounds(self) -> None:
        camera = Camera()
        camera.zoom = 1.0
        camera.zoom_target = 1.0
        camera.y_overscan = 6.0
        with patch("camera.map_view_width", return_value=640), patch(
            "camera.map_view_height", return_value=640
        ):
            camera.clamp(10, 10)
            _visible_w, visible_h = camera.visible_cells()
        self.assertAlmostEqual(camera.y, -6.0 + (16.0 - visible_h) / 2.0)

    def test_visible_range_includes_cells_lifted_from_south(self) -> None:
        camera = Camera()
        camera.zoom = 1.0
        camera.zoom_target = 1.0
        camera.x = 0.0
        camera.y = 5.0
        camera.y_overscan = 7.0
        with patch("camera.map_view_width", return_value=320), patch(
            "camera.map_view_height", return_value=320
        ):
            _x0, _y0, _x1, y1 = camera.visible_range(100, 100)
            _visible_w, visible_h = camera.visible_cells()
        self.assertEqual(y1, int(camera.y + visible_h) + 1 + 7)


if __name__ == "__main__":
    unittest.main()
