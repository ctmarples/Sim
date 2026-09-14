"""Run a save for 1 year and track villager positions for stuck detection.

Usage:
  SDL_VIDEODRIVER=dummy python track_villagers_year.py [save] [--days N]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

pygame.init()
import settings as cfg

info = pygame.display.Info()
cfg.configure_for_display(max(info.current_w, 1280), max(info.current_h, 800))

from entities import VillagerState  # noqa: E402
from game import Game  # noqa: E402
from save_load import load_from_path, saves_dir  # noqa: E402
from seasons import YEAR_DAYS  # noqa: E402


def villager_snapshot(game: Game, day: int) -> list[dict]:
    rows = []
    for v in game.villagers:
        b = game.buildings.get(v.building_id) if v.building_id else None
        inv = {
            k: int(getattr(v.inventory, k))
            for k in (
                "wood",
                "rock",
                "meat",
                "fish",
                "oak_saplings",
                "maple_saplings",
                "pine_saplings",
                "cedar_saplings",
                "mushrooms",
                "blackberries",
                "wheat",
                "rye",
                "wheat_grain",
                "rye_grain",
                "flax",
                "sage",
                "hemp",
                "onion",
                "cabbage",
                "carrot",
            )
            if int(getattr(v.inventory, k, 0)) > 0
        }
        seeds = {
            k: int(getattr(v.inventory, k))
            for k in (
                "berry_seeds",
                "wheat_grain",
                "flax_seeds",
                "sage_seeds",
                "hemp_seeds",
                "rye_grain",
                "onion_seeds",
                "cabbage_seeds",
                "carrot_seeds",
            )
            if int(getattr(v.inventory, k, 0)) > 0
        }
        rows.append(
            {
                "day": day,
                "id": v.id,
                "x": v.x,
                "y": v.y,
                "state": v.state.name,
                "building_id": v.building_id,
                "building_kind": b.kind.name if b else None,
                "home": v.assigned_to_home,
                "target": list(v.target) if v.target else None,
                "haul_building_id": v.haul_building_id,
                "hunt_animal_id": v.hunt_animal_id,
                "hunt_meat_pos": list(v.hunt_meat_pos) if v.hunt_meat_pos else None,
                "fish_target_id": v.fish_target_id,
                "fish_catch_pos": list(v.fish_catch_pos) if v.fish_catch_pos else None,
                "construction_id": v.construction_id,
                "satiation": round(v.satiation, 3),
                "seeking_food": v.seeking_food,
                "move_cd": v.move_cooldown,
                "work_cd": v.work_cooldown,
                "inv": inv,
                "seeds": seeds,
                "priorities": [p.name for p in v.priorities],
            }
        )
    return rows


def detect_stuck(samples_by_id: dict[int, list[dict]], stuck_days: int = 14) -> list[dict]:
    """Flag villagers who stay on one tile for `stuck_days` consecutive samples
    while not IDLE (or while IDLE with a sticky target / seeking food)."""
    reports = []
    for vid, rows in samples_by_id.items():
        if not rows:
            continue
        run_pos = None
        run_start = 0
        run_len = 0
        worst = None
        for i, row in enumerate(rows):
            pos = (row["x"], row["y"])
            active = (
                row["state"] != "IDLE"
                or row["seeking_food"]
                or row["target"] is not None
                or row["hunt_animal_id"] is not None
                or row["hunt_meat_pos"] is not None
                or row["fish_target_id"] is not None
                or row["fish_catch_pos"] is not None
                or row["construction_id"] is not None
                or bool(row["inv"])
                or bool(row["seeds"])
            )
            if pos == run_pos and active:
                run_len += 1
            else:
                if run_pos is not None and run_len >= stuck_days:
                    cand = (run_len, run_start, i - 1, run_pos)
                    if worst is None or cand[0] > worst[0]:
                        worst = cand
                run_pos = pos if active else None
                run_start = i
                run_len = 1 if active else 0
        if run_pos is not None and run_len >= stuck_days:
            cand = (run_len, run_start, len(rows) - 1, run_pos)
            if worst is None or cand[0] > worst[0]:
                worst = cand
        if worst is None:
            continue
        run_len, i0, i1, pos = worst
        mid = rows[(i0 + i1) // 2]
        end = rows[i1]
        # Unique states/targets during streak
        states = sorted({r["state"] for r in rows[i0 : i1 + 1]})
        targets = sorted(
            {tuple(r["target"]) if r["target"] else None for r in rows[i0 : i1 + 1]},
            key=lambda t: (t is None, t),
        )
        reports.append(
            {
                "id": vid,
                "stuck_days": run_len,
                "pos": list(pos),
                "day_start": rows[i0]["day"],
                "day_end": rows[i1]["day"],
                "states": states,
                "targets": [list(t) if t else None for t in targets],
                "building_kind": end["building_kind"],
                "home": end["home"],
                "sample_mid": mid,
                "sample_end": end,
                # Mobility across whole year
                "unique_tiles_year": len({(r["x"], r["y"]) for r in rows}),
                "moved_days": sum(
                    1
                    for a, b in zip(rows, rows[1:])
                    if (a["x"], a["y"]) != (b["x"], b["y"])
                ),
            }
        )
    reports.sort(key=lambda r: -r["stuck_days"])
    return reports


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("save", nargs="?", default="big_map_test.json")
    parser.add_argument("--days", type=int, default=YEAR_DAYS)
    parser.add_argument("--stuck-days", type=int, default=14)
    args = parser.parse_args()

    save_path = Path(args.save)
    if not save_path.is_file():
        save_path = saves_dir() / args.save
    if not save_path.is_file():
        print(f"Save not found: {args.save}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading {save_path} …")
    t0 = time.time()
    game = Game(headless=True)
    load_from_path(game, save_path)
    game.sim_speed = 0
    game.fast_forward = True

    samples: list[dict] = []
    samples.extend(villager_snapshot(game, 0))
    print(
        f"Start: day={game.calendar_day} villagers={len(game.villagers)} "
        f"buildings={len(game.buildings)}"
    )
    for elapsed in range(1, args.days + 1):
        game.simulate_fast_day()
        samples.extend(villager_snapshot(game, elapsed))
        if elapsed % 28 == 0 or elapsed == args.days:
            print(
                f"  day {elapsed}/{args.days} "
                f"cal={game.calendar_day} "
                f"({time.time() - t0:.1f}s)"
            )

    by_id: dict[int, list[dict]] = defaultdict(list)
    for row in samples:
        by_id[row["id"]].append(row)

    stuck = detect_stuck(by_id, stuck_days=args.stuck_days)

    out_dir = Path(__file__).resolve().parent / "_debug"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "villager_year_track.json"
    payload = {
        "save": str(save_path),
        "days": args.days,
        "stuck_days_threshold": args.stuck_days,
        "final_calendar_day": game.calendar_day,
        "elapsed_s": round(time.time() - t0, 2),
        "stuck": stuck,
        "summary": [
            {
                "id": vid,
                "unique_tiles": len({(r["x"], r["y"]) for r in rows}),
                "moved_days": sum(
                    1
                    for a, b in zip(rows, rows[1:])
                    if (a["x"], a["y"]) != (b["x"], b["y"])
                ),
                "final": rows[-1],
            }
            for vid, rows in sorted(by_id.items())
        ],
        "samples": samples,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"Wrote {out_path} ({len(samples)} samples)")

    print("\n=== Per-villager mobility ===")
    for s in payload["summary"]:
        f = s["final"]
        print(
            f"  V{s['id']}: tiles={s['unique_tiles']:3d} moved_days={s['moved_days']:3d} "
            f"end=({f['x']},{f['y']}) {f['state']} "
            f"job={f['building_kind'] or ('HOME' if f['home'] else '—')} "
            f"sat={f['satiation']:.2f} seek={f['seeking_food']} "
            f"tgt={f['target']} inv={f['inv'] or '{}'}"
        )

    print(f"\n=== Stuck (≥{args.stuck_days} consecutive active days same tile) ===")
    if not stuck:
        print("  none")
    for r in stuck:
        print(
            f"  V{r['id']} @ {r['pos']} for {r['stuck_days']}d "
            f"(days {r['day_start']}-{r['day_end']}) "
            f"states={r['states']} job={r['building_kind'] or ('HOME' if r['home'] else '—')}"
        )
        e = r["sample_end"]
        print(
            f"    end: tgt={e['target']} haul={e['haul_building_id']} "
            f"hunt={e['hunt_animal_id']}/{e['hunt_meat_pos']} "
            f"fish={e['fish_target_id']}/{e['fish_catch_pos']} "
            f"site={e['construction_id']} seek={e['seeking_food']} "
            f"sat={e['satiation']} inv={e['inv']} seeds={e['seeds']}"
        )


if __name__ == "__main__":
    main()
