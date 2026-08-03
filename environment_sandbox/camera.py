"""Camera: pan/zoom over a world larger than the viewport."""

from __future__ import annotations

from settings import (
    CAMERA_PAN_CELLS,
    CELL_SIZE,
    MAP_OFFSET_Y,
    ZOOM_MAX,
    ZOOM_MIN,
    map_view_height,
    map_view_width,
)


class Camera:
    """Top-left of the viewport in world cell coordinates + zoom scale."""

    def __init__(self) -> None:
        self.x: float = 0.0
        self.y: float = 0.0
        self.zoom: float = 1.0

    def view_cell(self) -> int:
        return max(6, int(round(CELL_SIZE * self.zoom)))

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
        """Zoom keeping the world point under screen_pos stable."""
        mx, my = screen_pos
        before = self.screen_to_world_float(mx, my)
        if before is None:
            new_zoom = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom * factor))
            self.zoom = new_zoom
            self.clamp(world_cols, world_rows)
            return
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom * factor))
        after_vc = self.view_cell()
        # Reposition so `before` stays under the cursor.
        self.x = before[0] - mx / after_vc
        self.y = before[1] - (my - MAP_OFFSET_Y) / after_vc
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

    def cell_rect(self, x: int, y: int):
        import pygame

        vc = self.view_cell()
        sx, sy = self.world_to_screen(x, y)
        return pygame.Rect(sx, sy, vc, vc)

    def visible_range(self, world_cols: int, world_rows: int) -> tuple[int, int, int, int]:
        vis_w, vis_h = self.visible_cells()
        x0 = max(0, int(self.x) - 1)
        y0 = max(0, int(self.y) - 1)
        x1 = min(world_cols - 1, int(self.x + vis_w) + 1)
        y1 = min(world_rows - 1, int(self.y + vis_h) + 1)
        return x0, y0, x1, y1
