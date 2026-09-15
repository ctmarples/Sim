"""Toggleable performance HUD and lightweight frame profiler.

Tracks sim vs draw time, world-layer cache, season-density bake, FPS, RAM,
and GC so sudden slowdowns after load are visible in-game (F7).
"""

from __future__ import annotations

import gc
import sys
import time
from collections import deque
from dataclasses import dataclass, field

import pygame

from settings import (
    COLOUR_TEXT,
    COLOUR_TEXT_DIM,
    COLOUR_TOOLBAR_BORDER,
    MAP_OFFSET_Y,
    map_view_width,
)


def _rss_mb() -> float | None:
    """Best-effort resident set size in MiB."""
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS reports bytes; Linux reports KiB.
        if sys.platform == "darwin":
            return float(usage) / (1024.0 * 1024.0)
        return float(usage) / 1024.0
    except Exception:
        pass
    try:
        import psutil  # type: ignore

        return float(psutil.Process().memory_info().rss) / (1024.0 * 1024.0)
    except Exception:
        return None


@dataclass
class FrameSample:
    """One rendered frame's timing breakdown (milliseconds)."""

    total_ms: float = 0.0
    events_ms: float = 0.0
    sim_ms: float = 0.0
    input_ms: float = 0.0
    audio_ms: float = 0.0
    draw_ms: float = 0.0
    world_ms: float = 0.0
    entities_ms: float = 0.0
    fx_ms: float = 0.0  # rain, day/night, shrouds
    ui_ms: float = 0.0
    flip_ms: float = 0.0
    sim_ticks: int = 0
    world_layer_hit: bool = False
    density_bake_step: int = 0
    density_bake_done: bool = False


@dataclass
class PerfMonitor:
    """Accumulates frame samples and draws the F7 performance HUD."""

    enabled: bool = False
    history: deque[FrameSample] = field(default_factory=lambda: deque(maxlen=120))
    _frame: FrameSample = field(default_factory=FrameSample)
    _mark: float = 0.0
    _section: str = ""
    world_hits: int = 0
    world_misses: int = 0
    frames: int = 0
    # Wall-clock FPS from recent totals.
    _fps_ema: float = 0.0
    bottleneck: str = "—"
    _font: pygame.font.Font | None = None
    _font_s: pygame.font.Font | None = None
    _cpu_t0: float = 0.0
    _wall_t0: float = 0.0
    _cpu_pct_ema: float = 0.0

    def toggle(self) -> bool:
        self.enabled = not self.enabled
        if self.enabled:
            self.history.clear()
            self.world_hits = 0
            self.world_misses = 0
            self.frames = 0
            self._fps_ema = 0.0
            self._cpu_pct_ema = 0.0
        return self.enabled

    def begin_frame(self) -> None:
        if not self.enabled:
            return
        self._frame = FrameSample()
        self._mark = time.perf_counter()
        self._wall_t0 = self._mark
        self._cpu_t0 = time.process_time()
        self._section = "events"

    def _close_section(self) -> None:
        if not self.enabled or not self._section:
            return
        now = time.perf_counter()
        ms = (now - self._mark) * 1000.0
        name = self._section
        self._mark = now
        f = self._frame
        if name == "events":
            f.events_ms = ms
        elif name == "sim":
            f.sim_ms = ms
        elif name == "input":
            f.input_ms = ms
        elif name == "audio":
            f.audio_ms = ms
        elif name == "draw":
            f.draw_ms += ms
        elif name == "world":
            f.world_ms = ms
            f.draw_ms += ms
        elif name == "entities":
            f.entities_ms = ms
            f.draw_ms += ms
        elif name == "fx":
            f.fx_ms = ms
            f.draw_ms += ms
        elif name == "ui":
            f.ui_ms = ms
            f.draw_ms += ms
        elif name == "flip":
            f.flip_ms = ms

    def section(self, name: str) -> None:
        """Start timing ``name`` (closes the previous section)."""
        if not self.enabled:
            return
        self._close_section()
        self._section = name

    def note_sim_ticks(self, n: int) -> None:
        if self.enabled:
            self._frame.sim_ticks = int(n)

    def note_world_layer(self, *, hit: bool) -> None:
        if not self.enabled:
            return
        self._frame.world_layer_hit = hit
        if hit:
            self.world_hits += 1
        else:
            self.world_misses += 1

    def note_density_bake(self, *, step: int, done: bool) -> None:
        if not self.enabled:
            return
        self._frame.density_bake_step = int(step)
        self._frame.density_bake_done = bool(done)

    def end_frame(self, clock: pygame.time.Clock) -> None:
        if not self.enabled:
            return
        self._close_section()
        self._section = ""
        f = self._frame
        f.total_ms = (
            f.events_ms
            + f.sim_ms
            + f.input_ms
            + f.audio_ms
            + f.draw_ms
            + f.flip_ms
        )
        # Prefer clock frame time when available (includes tick wait).
        raw = float(clock.get_time())
        if raw > 0:
            f.total_ms = max(f.total_ms, raw)
        self.history.append(f)
        self.frames += 1
        fps = float(clock.get_fps())
        if fps > 0:
            self._fps_ema = fps if self._fps_ema <= 0 else (self._fps_ema * 0.85 + fps * 0.15)
        wall = max(1e-6, time.perf_counter() - self._wall_t0)
        cpu = max(0.0, time.process_time() - self._cpu_t0)
        cpu_pct = 100.0 * cpu / wall
        self._cpu_pct_ema = (
            cpu_pct if self._cpu_pct_ema <= 0 else (self._cpu_pct_ema * 0.85 + cpu_pct * 0.15)
        )
        self.bottleneck = self._compute_bottleneck(f)

    def _compute_bottleneck(self, f: FrameSample) -> str:
        parts = {
            "sim": f.sim_ms,
            "world": f.world_ms,
            "entities": f.entities_ms,
            "fx": f.fx_ms,
            "ui": f.ui_ms,
            "audio": f.audio_ms,
        }
        if not f.world_layer_hit and f.world_ms >= 8.0:
            return "world redraw (cache miss)"
        if not f.density_bake_done and f.world_ms >= 5.0:
            return "season density bake"
        name, ms = max(parts.items(), key=lambda kv: kv[1])
        if ms < 2.0 and f.total_ms < 18.0:
            return "ok"
        labels = {
            "sim": "simulation / AI",
            "world": "world draw",
            "entities": "entities draw",
            "fx": "day/night / shrouds",
            "ui": "UI / panel",
            "audio": "audio proximity",
        }
        return labels.get(name, name)

    def _avg(self, attr: str, n: int = 30) -> float:
        if not self.history:
            return 0.0
        samples = list(self.history)[-n:]
        return sum(getattr(s, attr) for s in samples) / max(1, len(samples))

    def draw(
        self,
        surface: pygame.Surface,
        *,
        sim_speed: int,
        playback_ticks: int,
        density_step: int,
        density_total: int,
        density_done: bool,
        villager_count: int,
        building_count: int,
    ) -> None:
        if not self.enabled:
            return
        if self._font is None:
            self._font = pygame.font.SysFont("menlo", 13, bold=True)
            self._font_s = pygame.font.SysFont("menlo", 12)
        font = self._font
        font_s = self._font_s
        assert font is not None and font_s is not None

        fps = self._fps_ema
        frame_ms = self._avg("total_ms")
        sim_ms = self._avg("sim_ms")
        world_ms = self._avg("world_ms")
        ent_ms = self._avg("entities_ms")
        fx_ms = self._avg("fx_ms")
        ui_ms = self._avg("ui_ms")
        draw_ms = self._avg("draw_ms")
        ticks = self._avg("sim_ticks")
        hits = self.world_hits
        misses = self.world_misses
        hit_rate = 100.0 * hits / max(1, hits + misses)
        rss = _rss_mb()
        gc_counts = gc.get_count()
        latest = self.history[-1] if self.history else FrameSample()

        tick_hz = ticks * max(1.0, fps)
        lines = [
            "PERF  F7 toggle",
            f"FPS {fps:5.1f}   frame {frame_ms:5.1f} ms   target 16.7   "
            f"CPU {self._cpu_pct_ema:5.0f}%",
            f"sim  {sim_ms:5.1f} ms   draw {draw_ms:5.1f} ms   "
            f"world {world_ms:5.1f}  ent {ent_ms:5.1f}  fx {fx_ms:5.1f}  ui {ui_ms:5.1f}",
            f"ticks/frame {ticks:.0f}   tick Hz ~{tick_hz:.0f}   "
            f"speed ×{sim_speed}  playback {playback_ticks}",
            f"world cache hit {hit_rate:5.1f}%  "
            f"({hits} hit / {misses} miss)  last={'HIT' if latest.world_layer_hit else 'MISS'}",
            f"density bake "
            f"{'DONE' if density_done else f'{density_step}/{density_total}'}   "
            f"villagers {villager_count}  buildings {building_count}",
            f"GC gen0/1/2 {gc_counts[0]}/{gc_counts[1]}/{gc_counts[2]}"
            + (f"   RSS peak {rss:.0f} MiB" if rss is not None else ""),
            f"bottleneck: {self.bottleneck}",
        ]
        # Hint when the classic post-load cliff is visible.
        if not density_done:
            lines.append("note: season density still baking (~8ms/frame when world redraws)")
        elif misses > hits and self.frames > 30:
            lines.append("note: world layer thrashing — camera/day_tick invalidates cache")

        pad_x, pad_y, gap = 10, 8, 2
        rendered = [font.render(lines[0], True, COLOUR_TEXT)]
        rendered.extend(font_s.render(line, True, COLOUR_TEXT_DIM) for line in lines[1:])
        box_w = max(t.get_width() for t in rendered) + pad_x * 2
        box_h = sum(t.get_height() for t in rendered) + gap * (len(rendered) - 1) + pad_y * 2
        x = 8
        y = MAP_OFFSET_Y + 8
        # Keep clear of centred overlay HUD.
        max_x = map_view_width() - box_w - 8
        x = min(x, max(8, max_x))
        panel = pygame.Rect(x, y, box_w, box_h)
        bg = pygame.Surface((panel.w, panel.h), pygame.SRCALPHA)
        bg.fill((16, 18, 24, 220))
        surface.blit(bg, panel.topleft)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, panel, 1, border_radius=4)
        cy = panel.y + pad_y
        for t in rendered:
            surface.blit(t, (panel.x + pad_x, cy))
            cy += t.get_height() + gap
