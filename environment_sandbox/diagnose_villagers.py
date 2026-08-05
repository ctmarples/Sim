"""Load a save, print job overview, simulate, find stuck villagers, diagnose causes.

Usage:
  SDL_VIDEODRIVER=dummy python diagnose_villagers.py [save] [--days 45] [--fix]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

pygame.init()
import settings as cfg

info = pygame.display.Info()
cfg.configure_for_display(max(info.current_w, 1280), max(info.current_h, 800))

from entities import (  # noqa: E402
    BuildingKind,
    VillagerState,
    WORKPLACE_TOOL,
    WorkMode,
    WorkPriority,
)
from game import Game  # noqa: E402
from save_load import load_from_path, save_to_path, saves_dir  # noqa: E402

INV_KEYS = (
    "logs",
    "hardwood_logs",
    "wood",
    "rock",
    "meat",
    "fish",
    "axe",
    "spear",
    "fishing_rod",
    "hoe",
    "knife",
    "twine",
    "mushrooms",
    "berries",
)


def inv_summary(v) -> dict[str, int]:
    return {k: int(getattr(v.inventory, k)) for k in INV_KEYS if int(getattr(v.inventory, k, 0)) > 0}


def job_label(game: Game, v) -> str:
    if v.building_id is not None:
        b = game.buildings.get(v.building_id)
        if b is None:
            return "INVALID_BUILDING"
        mode = f" ({b.work_mode.name})" if b.supported_work_modes() else ""
        return f"{b.kind.name}#{b.id}{mode}"
    if v.assigned_to_home:
        return "HAULER"
    return "UNASSIGNED"


def diagnose_villager(game: Game, v) -> list[str]:
    """Return human-readable reasons the villager may be blocked."""
    reasons: list[str] = []
    b = game.buildings.get(v.building_id) if v.building_id else None

    if v.seeking_food:
        reasons.append("seeking food (may pause workplace work)")

    if v.state == VillagerState.IDLE:
        if not game._workplace_has_work(v) and v.building_id is not None:
            reasons.append("IDLE: workplace_has_work=False")
        elif v.building_id is None and not game._transport_has_work(v):
            reasons.append("IDLE: no transport/build/workplace task")
        else:
            reasons.append("IDLE: waiting (may be transient)")

    if b is not None:
        tool = WORKPLACE_TOOL.get(b.kind)
        if tool and not v.inventory.has_equipped_tool(tool):
            home_have = int(getattr(game.home_storage, tool, 0))
            cargo = int(getattr(v.inventory, tool, 0))
            if home_have <= 0 and cargo <= 0:
                reasons.append(f"missing tool {tool} (none at home or in cargo)")
            elif v.target == game.world.home_pos or (
                v.x, v.y
            ) == game.world.home_pos:
                reasons.append(f"fetching/equipping {tool} from home")
            else:
                reasons.append(f"needs {tool} in tool slot (have home={home_have} cargo={cargo})")

        if b.kind == BuildingKind.FORESTER and b.work_mode in (WorkMode.SPLIT, WorkMode.ALL):
            if b.craftable_split_recipe() is None:
                if b.logs + b.hardwood_logs <= 0:
                    reasons.append("forester split: no logs in building storage")
                else:
                    reasons.append("forester split: building full / output blocked")

        if b.kind == BuildingKind.KITCHEN:
            if not b.has_cooking_fuel():
                reasons.append("kitchen: no fuel wood")
            if b.craftable_recipe() is None and b.has_cooking_fuel():
                reasons.append("kitchen: missing recipe inputs")

        if v.inventory.has_delivery_cargo() and v.state == VillagerState.DELIVERING:
            dest = game._delivery_destination(v, b)
            if dest == game.world.home_pos:
                reasons.append("delivering cargo to home (workplace full or wrong type)")
            else:
                reasons.append(f"delivering to workplace {dest}")

    if v.haul_building_id is not None:
        hb = game.buildings.get(v.haul_building_id)
        if hb is None:
            reasons.append(f"haul claim on missing building #{v.haul_building_id}")
        elif v.inventory.is_empty and v.state == VillagerState.HAULING:
            if hb.haulable_total() <= 0:
                reasons.append(f"hauling to empty source #{v.haul_building_id}")

    if v.construction_id is not None:
        reasons.append(f"construction claim site #{v.construction_id}")

    if not reasons:
        reasons.append("no obvious block (moving or working)")
    return reasons


def snapshot(game: Game, day: int) -> list[dict]:
    rows = []
    for v in game.villagers:
        rows.append(
            {
                "day": day,
                "id": v.id,
                "x": v.x,
                "y": v.y,
                "state": v.state.name,
                "job": job_label(game, v),
                "target": list(v.target) if v.target else None,
                "haul": v.haul_building_id,
                "equipped": v.inventory.equipped_tool,
                "inv": inv_summary(v),
                "satiation": round(v.satiation, 3),
                "seeking_food": v.seeking_food,
                "reasons": diagnose_villager(game, v),
            }
        )
    return rows


def detect_stuck(by_id: dict[int, list[dict]], min_days: int = 10) -> list[dict]:
    reports = []
    for vid, rows in by_id.items():
        run_pos = None
        run_len = 0
        run_start = 0
        worst = None
        for i, row in enumerate(rows):
            pos = (row["x"], row["y"])
            active = row["state"] != "IDLE" or row["seeking_food"] or row["target"]
            if pos == run_pos and active:
                run_len += 1
            else:
                if run_pos and run_len >= min_days:
                    cand = (run_len, run_start, i - 1, run_pos)
                    if worst is None or cand[0] > worst[0]:
                        worst = cand
                run_pos = pos if active else None
                run_start = i
                run_len = 1 if active else 0
        if run_pos and run_len >= min_days:
            cand = (run_len, run_start, len(rows) - 1, run_pos)
            if worst is None or cand[0] > worst[0]:
                worst = cand
        if worst is None:
            continue
        run_len, i0, i1, pos = worst
        end = rows[i1]
        reports.append(
            {
                "id": vid,
                "days": run_len,
                "pos": pos,
                "day_range": (rows[i0]["day"], rows[i1]["day"]),
                "end": end,
                "reasons_at_end": end["reasons"],
            }
        )
    reports.sort(key=lambda r: -r["days"])
    return reports


def print_overview(game: Game, title: str) -> None:
    print(f"\n=== {title} ===")
    print(f"Calendar day {game.calendar_day} · {len(game.villagers)} villagers · home {game.world.home_pos}")
    for v in sorted(game.villagers, key=lambda x: x.id):
        reasons = diagnose_villager(game, v)
        print(
            f"  V{v.id:2} {v.state.name:11} @({v.x:2},{v.y:2}) "
            f"{job_label(game, v):22} tgt={v.target} eq={v.inventory.equipped_tool or '—'}"
        )
        print(f"       inv={inv_summary(v) or '{}'} sat={v.satiation:.2f} seek={v.seeking_food}")
        print(f"       → {'; '.join(reasons)}")


def auto_fix_stuck(game: Game, stuck_ids: set[int]) -> list[str]:
    """Reassign stuck villagers: unassigned haulers stay; others → unassigned or home haul."""
    changes: list[str] = []
    home = game.buildings.get(next((b.id for b in game.buildings.values() if b.kind == BuildingKind.HOME), None))
    for v in game.villagers:
        if v.id not in stuck_ids:
            continue
        old = job_label(game, v)
        v.haul_building_id = None
        v.hunt_animal_id = None
        v.hunt_meat_pos = None
        v.fish_target_id = None
        v.fish_catch_pos = None
        v.construction_id = None
        v.target = None
        v.seeking_food = False
        if v.inventory.has_delivery_cargo():
            v.state = VillagerState.DELIVERING
            v.target = game.world.home_pos
            changes.append(f"V{v.id}: clear stuck state, deliver cargo home (was {old})")
            continue
        # Drop workplace assignment if stuck on tool/work deadlock
        if v.building_id is not None:
            v.building_id = None
            v.assigned_to_home = True
            v.priorities = [WorkPriority.TRANSPORT, WorkPriority.NONE, WorkPriority.WORKPLACE]
            v.state = VillagerState.IDLE
            changes.append(f"V{v.id}: reassigned {old} → HAULER")
        elif not v.assigned_to_home:
            v.assigned_to_home = True
            v.priorities = [WorkPriority.TRANSPORT, WorkPriority.NONE, WorkPriority.WORKPLACE]
            v.state = VillagerState.IDLE
            changes.append(f"V{v.id}: set to HAULER (was {old})")
    return changes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("save", nargs="?", default="crafting.json")
    parser.add_argument("--days", type=int, default=45)
    parser.add_argument("--stuck-days", type=int, default=10)
    parser.add_argument("--fix", action="store_true", help="Reassign stuck villagers and save _fixed.json")
    args = parser.parse_args()

    save_path = Path(args.save)
    if not save_path.is_file():
        save_path = saves_dir() / args.save
    if not save_path.is_file():
        print(f"Save not found: {args.save}", file=sys.stderr)
        sys.exit(1)

    game = Game(headless=True)
    load_from_path(game, save_path)
    game.sim_speed = 0
    game.fast_forward = True

    print_overview(game, f"JOB OVERVIEW — {save_path.name} (start)")

    by_id: dict[int, list[dict]] = defaultdict(list)
    for row in snapshot(game, 0):
        by_id[row["id"]].append(row)

    for d in range(1, args.days + 1):
        game.simulate_fast_day()
        for row in snapshot(game, d):
            by_id[row["id"]].append(row)

    stuck = detect_stuck(by_id, min_days=args.stuck_days)
    print(f"\n=== STUCK (≥{args.stuck_days} days same tile, active) ===")
    if not stuck:
        print("  none detected")
    stuck_ids = set()
    for r in stuck:
        stuck_ids.add(r["id"])
        e = r["end"]
        print(
            f"  V{r['id']} @ {r['pos']} for {r['days']}d (sim days {r['day_range'][0]}-{r['day_range'][1]}) "
            f"{e['job']} state={e['state']}"
        )
        print(f"    end inv={e['inv']} eq={e['equipped']} tgt={e['target']}")
        print(f"    → {'; '.join(r['reasons_at_end'])}")

    print_overview(game, f"END STATE after {args.days} sim days")

    # Count recurring diagnosis themes
    theme_counts: dict[str, int] = defaultdict(int)
    for rows in by_id.values():
        for row in rows[-1:]:
            for reason in row["reasons"]:
                key = reason.split("(")[0].strip()
                theme_counts[key] += 1
    print("\n=== END-STATE ISSUE THEMES (all villagers) ===")
    for theme, n in sorted(theme_counts.items(), key=lambda x: -x[1]):
        if "no obvious" not in theme:
            print(f"  {n}x {theme}")

    if args.fix and stuck_ids:
        changes = auto_fix_stuck(game, stuck_ids)
        out = save_path.parent / f"{save_path.stem}_fixed.json"
        save_to_path(game, out)
        print(f"\n=== FIXES APPLIED → {out.name} ===")
        for c in changes:
            print(f"  {c}")
        # Simulate again after fix
        game2 = Game(headless=True)
        load_from_path(game2, out)
        game2.sim_speed = 0
        game2.fast_forward = True
        by2: dict[int, list[dict]] = defaultdict(list)
        for row in snapshot(game2, 0):
            by2[row["id"]].append(row)
        for d in range(1, min(30, args.days) + 1):
            game2.simulate_fast_day()
            for row in snapshot(game2, d):
                by2[row["id"]].append(row)
        stuck2 = detect_stuck(by2, min_days=args.stuck_days)
        print(f"\n=== AFTER FIX: stuck in next {min(30, args.days)} days ===")
        print(f"  {len(stuck2)} stuck (was {len(stuck)})")
        for r in stuck2[:5]:
            print(f"  V{r['id']} {r['days']}d @ {r['pos']}: {'; '.join(r['reasons_at_end'])}")


if __name__ == "__main__":
    main()
