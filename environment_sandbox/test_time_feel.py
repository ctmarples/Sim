"""Day seconds match 60 FPS playback: ×1 burns playback ticks each frame."""

from __future__ import annotations

import os
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from settings import (
    DAY_SECONDS_AT_X1,
    FPS,
    PLAYBACK_TICKS_AT_X1,
    playback_ticks_this_frame,
    seconds_to_ticks,
    sim_hz_at_x1,
    ticks_to_seconds,
)


def _frames_for_day(day_seconds: float, *, speed: int = 1, playback: int = PLAYBACK_TICKS_AT_X1) -> int:
    per_frame = playback_ticks_this_frame(speed, playback)
    return seconds_to_ticks(day_seconds, playback) // per_frame


def _calendar_days_after_frames(
    day_seconds: float,
    frames: int,
    *,
    speed: int = 1,
    playback: int = PLAYBACK_TICKS_AT_X1,
) -> int:
    tpd = seconds_to_ticks(day_seconds, playback)
    day_tick = tpd
    days = 0
    per_frame = playback_ticks_this_frame(speed, playback)
    for _ in range(frames):
        for _ in range(per_frame):
            day_tick -= 1
            if day_tick <= 0:
                day_tick = tpd
                days += 1
    return days


def _wall_clock_for_labeled_day(
    day_seconds: float,
    *,
    speed: int = 1,
    playback: int = PLAYBACK_TICKS_AT_X1,
) -> float:
    frames = _frames_for_day(day_seconds, speed=speed, playback=playback)
    clock = pygame.time.Clock()
    clock.tick(FPS)
    t0 = time.perf_counter()
    for _ in range(frames):
        clock.tick(FPS)
    return time.perf_counter() - t0


def test_seconds_match_ticks_per_frame() -> None:
    pb = PLAYBACK_TICKS_AT_X1
    assert pb == 2
    assert playback_ticks_this_frame(1, pb) == pb
    assert playback_ticks_this_frame(2, pb) == 2 * pb
    assert playback_ticks_this_frame(0, pb) == 0
    assert seconds_to_ticks(1.0, pb) == FPS * pb
    assert seconds_to_ticks(2.0, pb) == FPS * pb * 2
    assert seconds_to_ticks(10.0, pb) == FPS * pb * 10
    assert _frames_for_day(1.0) == FPS
    assert _frames_for_day(2.0) == FPS * 2
    assert _frames_for_day(10.0) == FPS * 10
    assert _frames_for_day(1.0, speed=2) == FPS // 2
    assert abs(ticks_to_seconds(seconds_to_ticks(10.0, pb), pb) - 10.0) < 1e-9
    assert DAY_SECONDS_AT_X1 == 300.0
    assert sim_hz_at_x1(pb) == FPS * pb
    # Ignoring playback (seconds * FPS only) made 1s last half a second.
    assert seconds_to_ticks(1.0, pb) != FPS


def test_legacy_intervals_scale_with_playback() -> None:
    from settings import pace_ticks, BUILD_TICKS_PER_ITEM, ANIMAL_MOVE_INTERVAL
    from resource_balance import satiation_decay_per_tick, VILLAGER_SATIATION_SECONDS

    pb = PLAYBACK_TICKS_AT_X1
    assert pace_ticks(60, pb) == seconds_to_ticks(1.0, pb)
    assert BUILD_TICKS_PER_ITEM == seconds_to_ticks(2.0, pb)
    assert ANIMAL_MOVE_INTERVAL == pace_ticks(80, pb)
    decay = satiation_decay_per_tick(pb)
    ticks = seconds_to_ticks(VILLAGER_SATIATION_SECONDS, pb)
    assert abs(decay * ticks - 1.0) < 1e-9


def test_labeled_day_matches_frame_count() -> None:
    assert _calendar_days_after_frames(1.0, FPS) == 1
    assert _calendar_days_after_frames(2.0, FPS * 2) == 1
    assert _calendar_days_after_frames(2.0, FPS) == 0
    assert _calendar_days_after_frames(1.0, FPS * 2) == 2
    assert _calendar_days_after_frames(10.0, FPS * 10) == 1
    assert _calendar_days_after_frames(1.0, FPS, speed=2) == 2


def test_pygame_clock_1s_and_2s_days() -> None:
    pygame.init()
    elapsed_1 = _wall_clock_for_labeled_day(1.0)
    elapsed_2 = _wall_clock_for_labeled_day(2.0)
    elapsed_1_x2 = _wall_clock_for_labeled_day(1.0, speed=2)
    print(
        f"wall clock: 1s day={elapsed_1:.3f}s  2s day={elapsed_2:.3f}s  "
        f"1s day at ×2={elapsed_1_x2:.3f}s"
    )
    assert 0.80 <= elapsed_1 <= 1.40, f"1s day lasted {elapsed_1:.3f}s"
    assert 1.60 <= elapsed_2 <= 2.80, f"2s day lasted {elapsed_2:.3f}s"
    assert 0.30 <= elapsed_1_x2 <= 0.85, f"1s day at ×2 lasted {elapsed_1_x2:.3f}s"
    assert elapsed_2 > elapsed_1 * 1.5


def test_game_one_tick_per_playback_slot_each_frame() -> None:
    pygame.init()
    from game import Game

    g = Game(headless=True)
    g.sim_speed = 1
    g.balance.set("DAY_SECONDS_AT_X1", 1.0)
    g._apply_time_balance()
    pb = g._playback_ticks()
    assert pb == 2
    assert g.ticks_per_day == seconds_to_ticks(1.0, pb)
    g.calendar_day = 0
    g.day_tick = g.ticks_per_day

    calls = {"n": 0}
    original = g._advance_sim_ticks

    def _count(ticks: int, *, flush: bool = True) -> None:
        calls["n"] += ticks
        original(ticks, flush=flush)

    g._advance_sim_ticks = _count  # type: ignore[method-assign]
    n = g._step_sim()
    assert n == pb, f"×1 should burn {pb} ticks this frame, got {n}"
    for _ in range(FPS - 1):
        g._step_sim()
    assert calls["n"] == FPS * pb
    assert g.calendar_day == 1, f"after {FPS} frames, calendar_day={g.calendar_day}"


if __name__ == "__main__":
    test_seconds_match_ticks_per_frame()
    test_legacy_intervals_scale_with_playback()
    test_labeled_day_matches_frame_count()
    test_pygame_clock_1s_and_2s_days()
    test_game_one_tick_per_playback_slot_each_frame()
    print("all time-feel tests passed")
