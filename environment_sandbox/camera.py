"""Camera: pan/zoom over a world larger than the viewport."""

from __future__ import annotations

import math

from settings import (
    CAMERA_PAN_CELLS,
    CAMERA_PAN_SPEED,
    CELL_SIZE,
    MAP_OFFSET_Y,
    ZOOM_MAX,
    ZOOM_MIN,
    ZOOM_SMOOTH_RATE,
    map_view_height,
    map_view_width,
)


class Camera:
    """Top-left of the viewport in world cell coordinates + zoom scale."""

    def __init__(self) -> None:
        self.x: float = 0.0
        self.y: float = 0.0
        self.zoom: float = 1.0
        self.zoom_target: float = 1.0
        self._zoom_focus: tuple[float, float] | None = None
        self._zoom_screen: tuple[int, int] | None = None

    def view_cell(self) -> float:
        """On-screen pixels per world cell (continuous; not snapped to integers)."""
        return max(6.0, CELL_SIZE * self.zoom)

    def view_cell_px(self) -> int:
        """Integer pixel size for icon blits / pygame drawing."""
        return max(6, int(round(self.view_cell())))

    def visible_cells(self) -> tuple[float, float]:
        vc = self.view_cell()
        return map_view_width() / vc, map_view_height() / vc

    def clamp(self, world_cols: int, world_rows: int) -> None:
        vis_w, vis_h = self.visible_cells()
        max_x = max(0.0, world_cols - vis_w)
        max_y = max(0.0, world_rows - vis_h)
        self.x = max(0.0, min(self.x, max_x))
        self.y = max(0.0, min(self.y, max_y))

    def pan(self, dx_cells: float, dy_cells: float, world_cols: int, world_rows: int) -> None:
        # Pan distance scales inversely with zoom so motion feels similar on screen.
        scale = 1.0 / max(0.25, self.zoom)
        self.x += dx_cells * CAMERA_PAN_CELLS * scale
        self.y += dy_cells * CAMERA_PAN_CELLS * scale
        self.clamp(world_cols, world_rows)

    def pan_continuous(
        self,
        dx_dir: float,
        dy_dir: float,
        dt: float,
        world_cols: int,
        world_rows: int,
    ) -> None:
        """Pan by direction vector (typically unit) at CAMERA_PAN_SPEED cells/sec."""
        length = math.hypot(dx_dir, dy_dir)
        if length < 1e-6 or dt <= 0.0:
            return
        scale = 1.0 / max(0.25, self.zoom)
        speed = CAMERA_PAN_SPEED * scale
        self.x += (dx_dir / length) * speed * dt
        self.y += (dy_dir / length) * speed * dt
        self.clamp(world_cols, world_rows)

    def center_on(self, cx: float, cy: float, world_cols: int, world_rows: int) -> None:
        vis_w, vis_h = self.visible_cells()
        self.x = cx - vis_w / 2
        self.y = cy - vis_h / 2
        self.clamp(world_cols, world_rows)

    def zoom_at(
        self,
        factor: float,
        screen_pos: tuple[int, int],
        world_cols: int,
        world_rows: int,
    ) -> None:
        """Queue a zoom toward ``zoom_target``, keeping the world point under the cursor."""
        mx, my = screen_pos
        before = self.screen_to_world_float(mx, my)
        self.zoom_target = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom_target * factor))
        if before is not None:
            self._zoom_focus = before
            self._zoom_screen = screen_pos
        else:
            self._zoom_focus = None
            self._zoom_screen = None
        # Apply one immediate step so wheel feels responsive, then smooth the rest.
        self.update(1.0 / 60.0, world_cols, world_rows)

    def update(self, dt: float, world_cols: int, world_rows: int) -> None:
        """Smoothly approach zoom_target while holding the focus world point stable."""
        if abs(self.zoom - self.zoom_target) < 1e-5:
            self.zoom = self.zoom_target
            return
        alpha = 1.0 - math.exp(-ZOOM_SMOOTH_RATE * max(0.0, dt))
        self.zoom += (self.zoom_target - self.zoom) * alpha
        if abs(self.zoom - self.zoom_target) < 1e-4:
            self.zoom = self.zoom_target
        if self._zoom_focus is not None and self._zoom_screen is not None:
            mx, my = self._zoom_screen
            wx, wy = self._zoom_focus
            vc = self.view_cell()
            self.x = wx - mx / vc
            self.y = wy - (my - MAP_OFFSET_Y) / vc
        self.clamp(world_cols, world_rows)

    def world_to_screen(self, wx: float, wy: float) -> tuple[int, int]:
        vc = self.view_cell()
        return (
            int((wx - self.x) * vc),
            int((wy - self.y) * vc) + MAP_OFFSET_Y,
        )

    def screen_to_world(self, sx: int, sy: int) -> tuple[int, int] | None:
        pt = self.screen_to_world_float(sx, sy)
        if pt is None:
            return None
        return int(pt[0]), int(pt[1])

    def screen_to_world_float(self, sx: int, sy: int) -> tuple[float, float] | None:
        mw, mh = map_view_width(), map_view_height()
        if sx < 0 or sx >= mw or sy < MAP_OFFSET_Y or sy >= MAP_OFFSET_Y + mh:
            return None
        vc = self.view_cell()
        return sx / vc + self.x, (sy - MAP_OFFSET_Y) / vc + self.y

    def cell_rect(self, x: int | float, y: int | float):
        import pygame

        vc = self.view_cell()
        sx, sy = self.world_to_screen(float(x), float(y))
        size = max(1, int(round(vc)))
        return pygame.Rect(sx, sy, size, size)

    def visible_range(self, world_cols: int, world_rows: int) -> tuple[int, int, int, int]:
        vis_w, vis_h = self.visible_cells()
        x0 = max(0, int(self.x) - 1)
        y0 = max(0, int(self.y) - 1)
        x1 = min(world_cols - 1, int(self.x + vis_w) + 1)
        y1 = min(world_rows - 1, int(self.y + vis_h) + 1)
        return x0, y0, x1, y1
