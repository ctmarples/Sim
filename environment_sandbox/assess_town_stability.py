"""Run a save for N years and assess resource stability + supply-chain bugs.

Usage:
  SDL_VIDEODRIVER=dummy python assess_town_stability.py [save] [--years 3]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

pygame.init()
import settings as cfg

info = pygame.display.Info()
cfg.configure_for_display(max(info.current_w, 1280), max(info.current_h, 800))

from bug_log import BugLog, set_bug_log_path  # noqa: E402
from entities import BuildingKind, VillagerState  # noqa: E402
from game import Game  # noqa: E402
from save_load import _STORAGE_KEYS, load_from_path, saves_dir  # noqa: E402
from seasons import DAYS_PER_SEASON, YEAR_DAYS, format_date, season_for_day  # noqa: E402

# Focus resources for town stability / supply chains.
FOCUS_KEYS = (
    "meat",
    "fish",
    "blackberries",
    "mushrooms",
    "wheat",
    "rye",
    "wheat_grain",
    "rye_grain",
    "wheat_flour",
    "rye_flour",
    "bread",
    "carrot",
    "cabbage",
    "onion",
    "garlic",
    "flax",
    "straw",
    "logs",
    "hardwood_logs",
    "wood",
    "rock",
    "twine",
    "leather",
    "fur",
    "hide",
    "honey",
    "coins",
)

CHAIN_KEYS = (
    "wheat",
    "rye",
    "wheat_grain",
    "rye_grain",
    "wheat_flour",
    "rye_flour",
    "bread",
)


def _stock_home(game: Game) -> dict[str, int]:
    return {
        key: int(getattr(game.home_storage, key, 0))
        for key in _STORAGE_KEYS
        if int(getattr(game.home_storage, key, 0)) > 0
    }


def _stock_buildings(game: Game) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)
    for building in game.buildings.values():
        for key in _STORAGE_KEYS:
            amount = int(getattr(building, key, 0))
            if amount > 0:
                totals[key] += amount
    return dict(totals)


def _stock_focus(home: dict[str, int], buildings: dict[str, int]) -> dict[str, int]:
    out: dict[str, int] = {}
    for key in FOCUS_KEYS:
        total = int(home.get(key, 0)) + int(buildings.get(key, 0))
        if total:
            out[key] = total
    return out


def _job_counts(game: Game) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for villager in game.villagers:
        if villager.building_id is not None:
            building = game.buildings.get(villager.building_id)
            label = building.kind.name if building else "INVALID"
        elif villager.assigned_to_home:
            label = "HAULER"
        else:
            label = "UNASSIGNED"
        counts[label] += 1
    return dict(counts)


def _state_counts(game: Game) -> dict[str, int]:
    return dict(Counter(v.state.name for v in game.villagers))


def _processor_gaps(game: Game) -> list[dict]:
    rows = []
    for building in game.buildings.values():
        if building.kind not in (
            BuildingKind.MILL,
            BuildingKind.KITCHEN,
            BuildingKind.CRAFT_BENCH,
            BuildingKind.ALCHEMIST,
            BuildingKind.TAILOR,
            BuildingKind.COBBLER,
        ):
            continue
        try:
            demand = dict(game._building_supply_demand(building))
        except Exception:
            continue
        if not demand:
            continue
        try:
            can = game._processor_can_be_supplied(building)
        except Exception:
            can = False
        rows.append(
            {
                "id": building.id,
                "kind": building.kind.name,
                "demand": demand,
                "can_be_supplied": can,
                "stock": {
                    k: int(getattr(building, k, 0))
                    for k in demand
                    if int(getattr(building, k, 0)) > 0
                },
            }
        )
    return rows


def _tracker_cumuls(game: Game) -> tuple[dict[str, int], dict[str, int]]:
    """Sum produced/consumed across the in-game resource tracker window."""
    produced: Counter[str] = Counter()
    consumed: Counter[str] = Counter()
    for _idx, bucket in game.resource_history._window_buckets():
        produced.update(
            {k: int(v) for k, v in bucket.produced.items() if int(v) > 0}
        )
        consumed.update(
            {k: int(v) for k, v in bucket.consumed.items() if int(v) > 0}
        )
    return dict(produced), dict(consumed)


def _dict_delta(now: dict[str, int], prev: dict[str, int]) -> dict[str, int]:
    keys = set(now) | set(prev)
    out: dict[str, int] = {}
    for key in keys:
        delta = int(now.get(key, 0)) - int(prev.get(key, 0))
        if delta:
            out[key] = delta
    return out


def _sample(
    game: Game,
    elapsed: int,
    *,
    prev_produced: dict[str, int] | None = None,
    prev_consumed: dict[str, int] | None = None,
) -> dict:
    home = _stock_home(game)
    buildings = _stock_buildings(game)
    # Same totals the in-game tracker records as "stock".
    stock = {
        k: int(v)
        for k, v in game._village_stock_amounts().items()
        if int(v) > 0
    }
    produced_cum, consumed_cum = _tracker_cumuls(game)
    produced = (
        dict(produced_cum)
        if prev_produced is None
        else _dict_delta(produced_cum, prev_produced)
    )
    consumed = (
        dict(consumed_cum)
        if prev_consumed is None
        else _dict_delta(consumed_cum, prev_consumed)
    )
    hungry = sum(1 for v in game.villagers if v.needs_food() or v.seeking_food)
    idle_assigned = sum(
        1
        for v in game.villagers
        if v.building_id is not None
        and v.state == VillagerState.IDLE
        and not v.seeking_food
        and not v.needs_food()
    )
    return {
        "elapsed": elapsed,
        "calendar_day": int(game.calendar_day),
        "date": format_date(game.calendar_day),
        "season": season_for_day(game.calendar_day).name,
        "villagers": len(game.villagers),
        "hungry": hungry,
        "idle_assigned": idle_assigned,
        "jobs": _job_counts(game),
        "states": _state_counts(game),
        "home": home,
        "buildings": buildings,
        "focus": _stock_focus(home, buildings),
        "stock": stock,
        "produced": produced,
        "consumed": consumed,
        "produced_cum": produced_cum,
        "consumed_cum": consumed_cum,
        "tracker_days": int(game.resource_history.total_days),
        "processor_gaps": _processor_gaps(game),
    }


def _trend(series: list[tuple[int, int]]) -> str:
    if len(series) < 2:
        return "n/a"
    first = series[0][1]
    last = series[-1][1]
    peak = max(v for _, v in series)
    trough = min(v for _, v in series)
    if first <= 0 and last <= 0:
        return "absent"
    if last == 0 and first > 0:
        return f"COLLAPSED (was {first}, peak {peak})"
    if first > 0 and last < first * 0.25:
        return f"severe drop {first}→{last} (peak {peak}, low {trough})"
    if first > 0 and last < first * 0.5:
        return f"down {first}→{last} (peak {peak})"
    if last > first * 1.5:
        return f"up {first}→{last} (peak {peak})"
    return f"stable-ish {first}→{last} (peak {peak}, low {trough})"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("save", nargs="?", default=None, help="Save name or path")
    parser.add_argument("--years", type=float, default=3.0)
    parser.add_argument(
        "--sample-every",
        type=int,
        default=DAYS_PER_SEASON,
        help="Stock sample period in days (default: one season)",
    )
    parser.add_argument(
        "--scan-every",
        type=int,
        default=DAYS_PER_SEASON,
        help="Bug-log force scan period in days (default: one season)",
    )
    parser.add_argument(
        "--ticks",
        type=int,
        default=60,
        help="ticks_per_day for this run (default 60; save may be 240)",
    )
    args = parser.parse_args()

    if args.save:
        save_path = Path(args.save)
        if not save_path.is_file():
            save_path = saves_dir() / args.save
    else:
        saves = list(saves_dir().glob("*.json"))
        if not saves:
            print("No saves found", file=sys.stderr)
            return 1
        save_path = max(saves, key=lambda p: p.stat().st_mtime)

    days = max(1, int(round(args.years * YEAR_DAYS)))
    out_dir = Path(__file__).resolve().parent / "_debug"
    out_dir.mkdir(exist_ok=True)
    bug_path = out_dir / "stability_bug_log.jsonl"
    report_path = out_dir / "stability_report.json"
    if bug_path.exists():
        bug_path.unlink()
    set_bug_log_path(bug_path)

    print(f"Loading {save_path.name} …", flush=True)
    t0 = time.time()
    game = Game(headless=True)
    load_from_path(game, save_path)
    game._last_save_path = save_path
    game._loaded_save_name = save_path.name
    game.sim_speed = 0
    game.fast_forward = True
    game.bug_log = BugLog(enabled=True)
    # Clean ledger for this run (ignore prior months loaded from the save).
    game.resource_history.reset()
    if args.ticks and args.ticks != game.ticks_per_day:
        try:
            game._set_ticks_per_day(args.ticks)
        except Exception:
            game.ticks_per_day = args.ticks
            game.day_tick = min(game.day_tick, args.ticks)
            from seasons import set_ticks_per_day

            set_ticks_per_day(args.ticks)

    samples: list[dict] = []
    bug_counts: Counter[str] = Counter()
    samples.append(_sample(game, 0))
    prev_produced = dict(samples[0]["produced_cum"])
    prev_consumed = dict(samples[0]["consumed_cum"])
    print(
        f"Start: {samples[0]['date']} villagers={samples[0]['villagers']} "
        f"idle_assigned={samples[0]['idle_assigned']} "
        f"years={args.years} days={days} ticks/day={game.ticks_per_day} "
        f"sample={args.sample_every}d scan={args.scan_every}d",
        flush=True,
    )

    next_sample = args.sample_every
    for elapsed in range(1, days + 1):
        game.simulate_fast_day()
        if elapsed % args.scan_every == 0 or elapsed == days:
            logged = game.bug_log.scan(game, force=True)
            for event in logged:
                bug_counts[event.kind] += 1
        if elapsed >= next_sample or elapsed == days:
            sample = _sample(
                game,
                elapsed,
                prev_produced=prev_produced,
                prev_consumed=prev_consumed,
            )
            samples.append(sample)
            prev_produced = dict(sample["produced_cum"])
            prev_consumed = dict(sample["consumed_cum"])
            next_sample = elapsed + args.sample_every
            s = sample
            prod_n = sum(s["produced"].values())
            cons_n = sum(s["consumed"].values())
            print(
                f"  day {elapsed}/{days} {s['date']} "
                f"vills={s['villagers']} hungry={s['hungry']} "
                f"idle_asg={s['idle_assigned']} "
                f"+{prod_n}/-{cons_n} "
                f"meat={s['stock'].get('meat', 0)} "
                f"bread={s['stock'].get('bread', 0)} "
                f"wood={s['stock'].get('wood', 0)} "
                f"({time.time() - t0:.0f}s)",
                flush=True,
            )

    # Trends
    focus_series: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for sample in samples:
        for key in FOCUS_KEYS:
            focus_series[key].append((sample["elapsed"], int(sample["focus"].get(key, 0))))

    trends = {key: _trend(series) for key, series in focus_series.items() if any(v for _, v in series)}

    # Bug log summary
    bug_events: list[dict] = []
    if bug_path.is_file():
        for line in bug_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                bug_events.append(json.loads(line))
    bugs_by_kind = Counter(e.get("kind", "?") for e in bug_events)
    bugs_by_subject: Counter[str] = Counter()
    for event in bug_events:
        kind = event.get("kind")
        subjects = event.get("subjects") or {}
        if kind == "idle_assigned":
            vids = subjects.get("villager_ids") or []
            bids = subjects.get("building_ids") or []
            bugs_by_subject[f"idle v{vids[0] if vids else '?'} @b{bids[0] if bids else '?'}"] += 1
        elif kind == "supply_blocked":
            bids = subjects.get("building_ids") or []
            bugs_by_subject[f"supply b{bids[0] if bids else '?'}"] += 1
        else:
            bugs_by_subject[str(kind)] += 1

    # Population
    pop = [(s["elapsed"], s["villagers"], s["hungry"]) for s in samples]

    # Aggregate flow over the whole run (from last sample cumuls).
    end = samples[-1]
    year_produced = dict(sorted(end.get("produced_cum", {}).items(), key=lambda kv: -kv[1]))
    year_consumed = dict(sorted(end.get("consumed_cum", {}).items(), key=lambda kv: -kv[1]))

    payload = {
        "save": str(save_path),
        "years": args.years,
        "days": days,
        "ticks_per_day": game.ticks_per_day,
        "elapsed_s": round(time.time() - t0, 2),
        "start": samples[0],
        "end": end,
        "population": pop,
        "trends": trends,
        "year_produced": year_produced,
        "year_consumed": year_consumed,
        "tracker": game.resource_history.to_dict(),
        "bug_counts": dict(bugs_by_kind),
        "bug_hotspots": bugs_by_subject.most_common(20),
        "samples": samples,
        "bug_log_path": str(bug_path),
    }
    report_path.write_text(json.dumps(payload, indent=2))

    print("\n=== Population ===")
    for elapsed, n, hungry in pop:
        print(f"  day {elapsed:4d}: villagers={n} hungry={hungry}")

    print("\n=== Focus resource trends (town total stock) ===")
    for key in FOCUS_KEYS:
        if key in trends:
            print(f"  {key:16s}  {trends[key]}")

    print("\n=== Per-sample flow (tracker produced / consumed / stock) ===")
    for s in samples[1:]:
        top_p = sorted(s["produced"].items(), key=lambda kv: -kv[1])[:5]
        top_c = sorted(s["consumed"].items(), key=lambda kv: -kv[1])[:5]
        print(
            f"  day {s['elapsed']:3d} {s['season']}: "
            f"+{sum(s['produced'].values())}/-{sum(s['consumed'].values())} "
            f"stock_keys={len(s['stock'])}"
        )
        if top_p:
            print("    produced:", ", ".join(f"{k} {v}" for k, v in top_p))
        if top_c:
            print("    consumed:", ", ".join(f"{k} {v}" for k, v in top_c))

    print("\n=== Year totals (tracker) — top produced ===")
    for key, amount in list(year_produced.items())[:20]:
        cons = year_consumed.get(key, 0)
        stock = end.get("stock", {}).get(key, 0)
        print(f"  {key:20s}  +{amount:5d}  -{cons:5d}  stock={stock}")

    print("\n=== Year totals (tracker) — top consumed (not in top produced) ===")
    shown = set(list(year_produced)[:20])
    for key, amount in list(year_consumed.items())[:20]:
        if key in shown:
            continue
        stock = end.get("stock", {}).get(key, 0)
        prod = year_produced.get(key, 0)
        print(f"  {key:20s}  +{prod:5d}  -{amount:5d}  stock={stock}")

    print("\n=== Grain / flour / bread chain (stock start → end) ===")
    for key in CHAIN_KEYS:
        a = samples[0].get("stock", samples[0].get("focus", {})).get(key, 0)
        b = end.get("stock", {}).get(key, 0)
        print(
            f"  {key:16s}  {a} → {b}  "
            f"(+{year_produced.get(key, 0)}/-{year_consumed.get(key, 0)})"
        )

    print("\n=== Supply-chain bug log ===")
    print(f"  file: {bug_path}")
    if not bugs_by_kind:
        print("  no detector hits")
    else:
        for kind, count in bugs_by_kind.most_common():
            print(f"  {kind}: {count}")
        print("  hotspots:")
        for label, count in bugs_by_subject.most_common(15):
            print(f"    {label}: {count}")

    print("\n=== Final processor gaps ===")
    gaps = end["processor_gaps"]
    if not gaps:
        print("  none")
    for gap in gaps:
        print(
            f"  {gap['kind']}#{gap['id']} demand={gap['demand']} "
            f"can_supply={gap['can_be_supplied']} stock={gap['stock']}"
        )

    print("\n=== Final jobs / states ===")
    print(f"  jobs={end['jobs']}")
    print(f"  states={end['states']}")
    print(f"\nWrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
