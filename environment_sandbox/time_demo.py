"""Small window that shows how sim ticks, playback, and cooldowns work.

Run:  python time_demo.py
  or: File → Time demo… from the main game.
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEO_CENTERED", "1")

import pygame

from settings import (
    COLOUR_BG,
    COLOUR_PANEL_BORDER,
    COLOUR_PLAYER,
    COLOUR_TEXT,
    COLOUR_TEXT_DIM,
    COLOUR_TOOLBAR_BORDER,
    COLOUR_TOOLBAR_BTN,
    COLOUR_TOOLBAR_BTN_HOVER,
    COLOUR_STATUS,
    DAY_SECONDS_AT_X1,
    DAY_SECONDS_OPTIONS,
    FPS,
    PLAYBACK_TICKS_AT_X1,
    WALK_SECONDS_AT_X1,
    WORK_SECONDS_AT_X1,
    playback_ticks_this_frame,
    seconds_to_ticks,
    sim_hz_at_x1,
    ticks_to_seconds,
)

GRID = 8
CELL = 44
GRID_PX = GRID * CELL
PAD = 16
PANEL_W = 340
WIN_W = PAD + GRID_PX + PAD + PANEL_W + PAD
WIN_H = PAD + GRID_PX + PAD + 36


class TimeDemo:
    def __init__(self) -> None:
        pygame.display.set_caption("Time demo — ticks & cooldowns")
        self.screen = pygame.display.set_mode((WIN_W, WIN_H))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("menlo", 13)
        self.font_small = pygame.font.SysFont("menlo", 12)
        self.font_title = pygame.font.SysFont("menlo", 15, bold=True)
        self.running = True

        self.speed = 1
        self.playback = int(PLAYBACK_TICKS_AT_X1)
        self.day_s = float(DAY_SECONDS_AT_X1)
        self.walk_s = float(WALK_SECONDS_AT_X1)
        self.work_s = float(WORK_SECONDS_AT_X1)

        self.x = GRID // 2
        self.y = GRID // 2
        self.move_cd = 0
        self.work_cd = 0
        self.vis_from = (float(self.x), float(self.y))
        self.vis_duration = 0
        self.held: tuple[int, int] | None = None

        self.frame_i = 0
        self.sim_ticks = 0
        self.ticks_this_frame = 0
        self.calendar_day = 0
        self.day_tick = self.ticks_per_day
        self.steps = 0
        self.works = 0
        self.flash = 0

        self.hits: list[tuple[pygame.Rect, str]] = []
        self.hover: str | None = None

    @property
    def ticks_per_day(self) -> int:
        return seconds_to_ticks(self.day_s, self.playback)

    @property
    def walk_interval(self) -> int:
        return max(4, seconds_to_ticks(self.walk_s, self.playback))

    @property
    def work_interval(self) -> int:
        return max(6, seconds_to_ticks(self.work_s, self.playback))

    def _rescale_day(self, old_tpd: int) -> None:
        frac = 1.0 - (self.day_tick / max(1, old_tpd))
        self.day_tick = max(1, min(self.ticks_per_day, int(round(frac * self.ticks_per_day))))

    def _try_move(self, dx: int, dy: int) -> None:
        if self.speed <= 0 or self.move_cd > 0:
            return
        nx, ny = self.x + dx, self.y + dy
        if not (0 <= nx < GRID and 0 <= ny < GRID):
            return
        self.vis_from = (float(self.x), float(self.y))
        self.x, self.y = nx, ny
        interval = self.walk_interval
        self.move_cd = interval
        self.vis_duration = interval
        self.steps += 1

    def _try_work(self) -> None:
        if self.speed <= 0 or self.work_cd > 0:
            return
        interval = self.work_interval
        self.work_cd = interval
        self.works += 1
        self.flash = 12

    def _sim_tick(self) -> None:
        self.sim_ticks += 1
        self.day_tick -= 1
        if self.day_tick <= 0:
            self.day_tick = self.ticks_per_day
            self.calendar_day += 1
        if self.move_cd > 0:
            self.move_cd -= 1
        if self.work_cd > 0:
            self.work_cd -= 1
        if self.held and self.move_cd == 0:
            self._try_move(*self.held)

    def _step_frame(self) -> None:
        n = playback_ticks_this_frame(self.speed, self.playback)
        self.ticks_this_frame = n
        for _ in range(n):
            self._sim_tick()
        self.frame_i += 1
        if self.flash > 0:
            self.flash -= 1

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_q):
                self.running = False
            elif event.key == pygame.K_SPACE:
                self._try_work()
            elif event.key == pygame.K_LEFT:
                self.held = (-1, 0)
                self._try_move(-1, 0)
            elif event.key == pygame.K_RIGHT:
                self.held = (1, 0)
                self._try_move(1, 0)
            elif event.key == pygame.K_UP:
                self.held = (0, -1)
                self._try_move(0, -1)
            elif event.key == pygame.K_DOWN:
                self.held = (0, 1)
                self._try_move(0, 1)
        elif event.type == pygame.KEYUP:
            mapping = {
                pygame.K_LEFT: (-1, 0),
                pygame.K_RIGHT: (1, 0),
                pygame.K_UP: (0, -1),
                pygame.K_DOWN: (0, 1),
            }
            if mapping.get(event.key) == self.held:
                self.held = None
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for rect, action in self.hits:
                if rect.collidepoint(event.pos):
                    self._do(action)
                    break

    def _do(self, action: str) -> None:
        old_tpd = self.ticks_per_day
        if action.startswith("speed_"):
            self.speed = int(action.split("_")[1])
            return
        if action == "pb-":
            self.playback = max(1, self.playback - 1)
        elif action == "pb+":
            self.playback = min(8, self.playback + 1)
        elif action == "day-":
            idx = min(range(len(DAY_SECONDS_OPTIONS)), key=lambda i: abs(DAY_SECONDS_OPTIONS[i] - self.day_s))
            self.day_s = DAY_SECONDS_OPTIONS[(idx - 1) % len(DAY_SECONDS_OPTIONS)]
        elif action == "day+":
            idx = min(range(len(DAY_SECONDS_OPTIONS)), key=lambda i: abs(DAY_SECONDS_OPTIONS[i] - self.day_s))
            self.day_s = DAY_SECONDS_OPTIONS[(idx + 1) % len(DAY_SECONDS_OPTIONS)]
        elif action == "walk-":
            self.walk_s = max(0.05, round(self.walk_s - 0.05, 2))
        elif action == "walk+":
            self.walk_s = min(2.0, round(self.walk_s + 0.05, 2))
        elif action == "work-":
            self.work_s = max(0.15, round(self.work_s - 0.15, 2))
        elif action == "work+":
            self.work_s = min(6.0, round(self.work_s + 0.15, 2))
        elif action == "reset":
            self.speed = 1
            self.playback = int(PLAYBACK_TICKS_AT_X1)
            self.day_s = float(DAY_SECONDS_AT_X1)
            self.walk_s = float(WALK_SECONDS_AT_X1)
            self.work_s = float(WORK_SECONDS_AT_X1)
            self.frame_i = 0
            self.sim_ticks = 0
            self.calendar_day = 0
            self.steps = 0
            self.works = 0
            self.move_cd = 0
            self.work_cd = 0
            self.day_tick = self.ticks_per_day
            return
        if self.ticks_per_day != old_tpd:
            self._rescale_day(old_tpd)

    def _draw_xy(self) -> tuple[float, float]:
        if self.vis_duration <= 0 or self.move_cd <= 0:
            return float(self.x), float(self.y)
        t = 1.0 - (self.move_cd / self.vis_duration)
        t = max(0.0, min(1.0, t))
        fx, fy = self.vis_from
        return fx + (self.x - fx) * t, fy + (self.y - fy) * t

    def _btn(self, rect: pygame.Rect, label: str, action: str, mouse: tuple[int, int]) -> None:
        hover = rect.collidepoint(mouse)
        bg = COLOUR_TOOLBAR_BTN_HOVER if hover else COLOUR_TOOLBAR_BTN
        pygame.draw.rect(self.screen, bg, rect)
        pygame.draw.rect(self.screen, COLOUR_TOOLBAR_BORDER, rect, 1)
        text = self.font_small.render(label, True, COLOUR_TEXT)
        self.screen.blit(
            text,
            (rect.x + (rect.w - text.get_width()) // 2, rect.y + (rect.h - text.get_height()) // 2),
        )
        self.hits.append((rect, action))

    def _bar(self, x: int, y: int, w: int, h: int, frac: float, colour: tuple[int, int, int]) -> None:
        pygame.draw.rect(self.screen, (28, 30, 36), pygame.Rect(x, y, w, h))
        pygame.draw.rect(self.screen, COLOUR_PANEL_BORDER, pygame.Rect(x, y, w, h), 1)
        inner = max(0, int(w * max(0.0, min(1.0, frac))))
        if inner:
            pygame.draw.rect(self.screen, colour, pygame.Rect(x, y, inner, h))

    def _line(self, text: str, x: int, y: int, dim: bool = False) -> int:
        colour = COLOUR_TEXT_DIM if dim else COLOUR_TEXT
        self.screen.blit(self.font_small.render(text, True, colour), (x, y))
        return y + 16

    def draw(self, mouse: tuple[int, int]) -> None:
        self.hits.clear()
        self.screen.fill(COLOUR_BG)

        ox, oy = PAD, PAD
        pygame.draw.rect(self.screen, (22, 24, 28), pygame.Rect(ox, oy, GRID_PX, GRID_PX))
        for i in range(GRID + 1):
            pygame.draw.line(self.screen, COLOUR_PANEL_BORDER, (ox + i * CELL, oy), (ox + i * CELL, oy + GRID_PX))
            pygame.draw.line(self.screen, COLOUR_PANEL_BORDER, (ox, oy + i * CELL), (ox + GRID_PX, oy + i * CELL))

        px, py = self._draw_xy()
        cx = int(ox + (px + 0.5) * CELL)
        cy = int(oy + (py + 0.5) * CELL)
        pygame.draw.circle(self.screen, COLOUR_PLAYER, (cx, cy), 12)
        pygame.draw.circle(self.screen, (180, 210, 255), (cx, cy), 12, 2)
        if self.flash:
            pygame.draw.circle(self.screen, COLOUR_STATUS, (cx, cy), 16 + (12 - self.flash), 2)

        hint = "Arrows move  ·  Space work  ·  Esc quit"
        ht = self.font_small.render(hint, True, COLOUR_TEXT_DIM)
        self.screen.blit(ht, (ox, oy + GRID_PX + 10))

        x = ox + GRID_PX + PAD
        y = PAD
        self.screen.blit(self.font_title.render("Counts", True, COLOUR_TEXT), (x, y))
        y += 22
        hz = sim_hz_at_x1(self.playback)
        y = self._line(f"Display frames     {self.frame_i}", x, y)
        y = self._line(f"Sim ticks          {self.sim_ticks}", x, y)
        y = self._line(f"Ticks this frame   {self.ticks_this_frame}  (= speed × playback)", x, y, dim=True)
        y = self._line(f"Sim Hz at ×1       {hz}  (60 FPS × {self.playback})", x, y, dim=True)
        y += 4
        y = self._line(
            f"Calendar day       {self.calendar_day}   tick {self.day_tick}/{self.ticks_per_day}",
            x,
            y,
        )
        day_frac = 1.0 - self.day_tick / max(1, self.ticks_per_day)
        self._bar(x, y, PANEL_W - 8, 8, day_frac, (80, 170, 120))
        y += 16
        y = self._line(
            f"Day length         {self.day_s:g}s at ×1  →  {self.ticks_per_day} ticks",
            x,
            y,
            dim=True,
        )
        y += 6
        y = self._line(
            f"Move cooldown      {self.move_cd}/{self.walk_interval} ticks   steps {self.steps}",
            x,
            y,
        )
        self._bar(
            x,
            y,
            PANEL_W - 8,
            8,
            self.move_cd / max(1, self.walk_interval),
            COLOUR_PLAYER,
        )
        y += 16
        y = self._line(
            f"Walk               {self.walk_s:.2f}s/tile  ({ticks_to_seconds(self.walk_interval, self.playback):.2f}s)",
            x,
            y,
            dim=True,
        )
        y += 4
        y = self._line(
            f"Work cooldown      {self.work_cd}/{self.work_interval} ticks   actions {self.works}",
            x,
            y,
        )
        self._bar(
            x,
            y,
            PANEL_W - 8,
            8,
            self.work_cd / max(1, self.work_interval),
            (220, 140, 50),
        )
        y += 16
        y = self._line(
            f"Work               {self.work_s:.2f}s/action  ({ticks_to_seconds(self.work_interval, self.playback):.2f}s)",
            x,
            y,
            dim=True,
        )
        tiles = self.ticks_per_day / max(1, self.walk_interval)
        acts = self.ticks_per_day / max(1, self.work_interval)
        y += 4
        y = self._line(f"≈ {tiles:.1f} tiles/day   ·   ≈ {acts:.1f} work/day", x, y)

        y += 10
        self.screen.blit(self.font_title.render("Edit", True, COLOUR_TEXT), (x, y))
        y += 22

        y = self._knob_row(x, y, "Playback ticks/frame", str(self.playback), "pb-", "pb+", mouse)
        y = self._knob_row(x, y, "Day length", f"{self.day_s:g}s", "day-", "day+", mouse)
        y = self._knob_row(x, y, "Walk / tile", f"{self.walk_s:.2f}s", "walk-", "walk+", mouse)
        y = self._knob_row(x, y, "Work / action", f"{self.work_s:.2f}s", "work-", "work+", mouse)

        y += 4
        self.screen.blit(self.font_small.render("Speed", True, COLOUR_TEXT), (x, y + 4))
        bx = x + 78
        for sp in (0, 1, 2, 4, 8):
            label = "Pause" if sp == 0 else f"×{sp}"
            r = pygame.Rect(bx, y, 42 if sp else 52, 22)
            if self.speed == sp:
                pygame.draw.rect(self.screen, (70, 90, 130), r)
                pygame.draw.rect(self.screen, COLOUR_TOOLBAR_BORDER, r, 1)
                t = self.font_small.render(label, True, COLOUR_TEXT)
                self.screen.blit(t, (r.x + (r.w - t.get_width()) // 2, r.y + 4))
                self.hits.append((r, f"speed_{sp}"))
            else:
                self._btn(r, label, f"speed_{sp}", mouse)
            bx = r.right + 4
        y += 30
        self._btn(pygame.Rect(x, y, 88, 22), "Reset", "reset", mouse)

    def _knob_row(
        self,
        x: int,
        y: int,
        label: str,
        value: str,
        dec: str,
        inc: str,
        mouse: tuple[int, int],
    ) -> int:
        self.screen.blit(self.font_small.render(label, True, COLOUR_TEXT), (x, y + 4))
        val = self.font.render(value, True, COLOUR_STATUS)
        vx = x + 168
        self.screen.blit(val, (vx, y + 3))
        self._btn(pygame.Rect(x + 248, y, 24, 22), "−", dec, mouse)
        self._btn(pygame.Rect(x + 276, y, 24, 22), "+", inc, mouse)
        return y + 26

    def run(self) -> None:
        pygame.key.set_repeat(180, 40)
        while self.running:
            mouse = pygame.mouse.get_pos()
            for event in pygame.event.get():
                self.handle_event(event)
            self._step_frame()
            self.draw(mouse)
            pygame.display.flip()
            self.clock.tick(FPS)
        pygame.quit()


def main() -> None:
    pygame.init()
    TimeDemo().run()


if __name__ == "__main__":
    main()
