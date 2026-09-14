"""Headless economy speed-runs — real sim rules, no rendering.

Bottleneck was full-map work scans every cooldown tick; workers now keep sticky
targets and idle waits are jumped. Typical: 5 years × 5 seeds in tens of seconds.

Usage:
  SDL_VIDEODRIVER=dummy python speed_run_economy.py [save] [--years 5] [--runs 5]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

pygame.init()
import settings as cfg

info = pygame.display.Info()
cfg.configure_for_display(max(info.current_w, 1280), max(info.current_h, 800))

from crops import PRODUCE_KEYS  # noqa: E402
from game import Game  # noqa: E402
from resources import amounts_from_obj, group_totals, merge_amounts  # noqa: E402
from save_load import load_from_path, saves_dir  # noqa: E402
from seasons import YEAR_DAYS  # noqa: E402


def stockpile_amounts(game: Game) -> dict[str, int]:
    """Home + building storage (same as resource-bar Total view)."""
    parts = [amounts_from_obj(game.home_storage)]
    parts.extend(amounts_from_obj(b) for b in game.buildings.values())
    return merge_amounts(*parts)


def sample_row(game: Game, elapsed_day: int) -> dict[str, float | int]:
    amounts = stockpile_amounts(game)
    groups = group_totals(amounts)
    crop_produce = sum(int(amounts.get(k, 0)) for k in PRODUCE_KEYS)
    return {
        "day": elapsed_day,
        "calendar_day": game.calendar_day,
        "food": groups["food"],
        "wares": groups["wares"],
        "agriculture": groups["agriculture"],
        "wood": amounts["wood"],
        "rock": amounts["rock"],
        "sage": amounts.get("sage", 0),
        "crop_produce": crop_produce,
        "meat": amounts["meat"],
        "fish": amounts["fish"],
        "blackberries": amounts["blackberries"],
        "mushrooms": amounts["mushrooms"],
    }


def run_once(save_path: Path, days: int, run_index: int) -> list[dict[str, float | int]]:
    game = Game(headless=True)
    load_from_path(game, save_path)
    game.sim_speed = 0
    game.fast_forward = True
    game._drop_rng.seed(42 + run_index * 97)
    game._food_rng.seed(99 + run_index * 53)
    game.wildlife.rng.seed(cfg.RANDOM_SEED + 7 + run_index * 11)
    game.fish.rng.seed(cfg.RANDOM_SEED + 17 + run_index * 13)
    game.world._sprout_rng.seed(game.world.seed + 99 + run_index)
    game.world._forage_rng.seed(game.world.seed + 123 + run_index)

    samples = [sample_row(game, 0)]
    for elapsed in range(1, days + 1):
        game.simulate_fast_day()
        # Sample daily for short runs; every 7 days for multi-year to keep JSON light.
        if days <= YEAR_DAYS or elapsed % 7 == 0 or elapsed == days:
            samples.append(sample_row(game, elapsed))
    game.fast_forward = False
    return samples


def average_runs(runs: list[list[dict[str, float | int]]]) -> list[dict[str, float | int]]:
    if not runs:
        return []
    n = min(len(r) for r in runs)
    keys = [
        "food",
        "wares",
        "agriculture",
        "wood",
        "rock",
        "sage",
        "crop_produce",
        "meat",
        "fish",
        "blackberries",
        "mushrooms",
    ]
    out: list[dict[str, float | int]] = []
    for i in range(n):
        row: dict[str, float | int] = {"day": runs[0][i]["day"]}
        for key in keys:
            vals = [float(r[i][key]) for r in runs]
            row[key] = sum(vals) / len(vals)
            row[f"{key}_min"] = min(vals)
            row[f"{key}_max"] = max(vals)
        out.append(row)
    return out


def downsample(rows: list[dict[str, float | int]], max_points: int = 120) -> list[dict[str, float | int]]:
    if len(rows) <= max_points:
        return rows
    step = max(1, (len(rows) - 1) // (max_points - 1))
    picked = rows[::step]
    if picked[-1] is not rows[-1]:
        picked.append(rows[-1])
    return picked


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("save", nargs="?", default="test.json")
    parser.add_argument("--years", type=float, default=5.0)
    parser.add_argument("--days", type=int, default=None, help="Override years")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    days = args.days if args.days is not None else int(round(args.years * YEAR_DAYS))
    save_path = Path(args.save)
    if not save_path.is_file():
        save_path = saves_dir() / args.save
    if not save_path.is_file():
        print(f"Save not found: {args.save}", file=sys.stderr)
        sys.exit(1)

    out_path = args.out or (saves_dir() / f"{save_path.stem}_economy_runs.json")
    print(f"Fast-sim {save_path.name}: {args.runs} runs × {days} days ({days / YEAR_DAYS:.1f}y)")
    print("  (real cooldowns + pathfinding; no render / wall-clock waits)")

    t0 = time.perf_counter()
    runs: list[list[dict[str, float | int]]] = []
    for i in range(args.runs):
        t_run = time.perf_counter()
        runs.append(run_once(save_path, days, i))
        print(f"  run {i + 1}/{args.runs} done in {time.perf_counter() - t_run:.2f}s", flush=True)

    avg = average_runs(runs)
    payload = {
        "save": str(save_path),
        "days": days,
        "years": days / YEAR_DAYS,
        "runs": args.runs,
        "mode": "fast_forward",
        "wall_seconds": time.perf_counter() - t0,
        "average": avg,
        "average_plot": downsample(avg),
        "raw_final": [r[-1] for r in runs],
    }
    out_path.write_text(json.dumps(payload), encoding="utf-8")
    print(f"Wrote {out_path} in {payload['wall_seconds']:.2f}s total")

    if avg:
        first, last = avg[0], avg[-1]
        print(
            f"Mean food {first['food']:.0f} → {last['food']:.0f}; "
            f"wares {first['wares']:.0f} → {last['wares']:.0f}; "
            f"agri {first['agriculture']:.0f} → {last['agriculture']:.0f}"
        )


if __name__ == "__main__":
    main()
